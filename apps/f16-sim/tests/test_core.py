"""The simulation core without rendering: pacing, input shaping and the FMU in closed loop.

The FMU tests need ``build/f16_sim.fmu`` (``uv run build_fmu.py``) and are skipped without it.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from f16sim.core import Pacer, Simulation
from f16sim.fmu import Start, body_to_ned, euler_to_ned
from f16sim.inputs import AxisMap, Keyboard, map_axis, shape

APP = Path(__file__).resolve().parents[1]
FMU = APP / "build" / "f16_sim.fmu"
STARTS = APP / "build" / "starts.json"
needs_fmu = pytest.mark.skipif(not FMU.exists() or not STARTS.exists(), reason="run `uv run build_fmu.py` first")


def test_pacer_carries_the_remainder():
    p = Pacer(0.005)
    steps = [p.steps_for(1.0 / 60.0) for _ in range(60)]
    assert sum(steps) == 200                 # one second of frames -> one second of steps
    assert set(steps) <= {3, 4}
    assert p.behind == 0


def test_pacer_bounds_the_catch_up():
    p = Pacer(0.005, max_steps=20)
    assert p.steps_for(1.0) == 20            # a one-second hitch runs 0.1 s and drops the rest
    assert p.behind == 1 and p.dropped == pytest.approx(0.9)
    assert p.steps_for(0.005) == 1


def test_shape_dead_zone_and_expo():
    assert shape(0.03, 0.05, 0.0) == 0.0
    assert shape(1.0, 0.05, 0.5) == pytest.approx(1.0)
    assert shape(-1.0, 0.05, 0.5) == pytest.approx(-1.0)
    assert 0.0 < shape(0.5, 0.0, 0.5) < 0.5          # expo softens the centre
    assert map_axis(-1.0, AxisMap(invert=True, range="unipolar")) == pytest.approx(1.0)
    assert map_axis(0.0, AxisMap(range="unipolar")) == pytest.approx(0.5)


def test_keyboard_springs_back():
    kb = Keyboard({"stick_rate": 2.5, "spring": 4.0, "throttle_rate": 0.4})
    for _ in range(30):
        kb.update({"right": True, "pull": True}, 1 / 60)
    assert kb.roll == pytest.approx(1.0) and kb.pitch == pytest.approx(1.0)
    for _ in range(30):
        kb.update({}, 1 / 60)
    assert kb.roll == 0.0 and kb.pitch == 0.0


@pytest.fixture(scope="module")
def sim():
    s = Simulation(FMU, Start.load_all(STARTS))
    yield s
    s.close()


def run(sim, seconds, controls=(0.0, 0.0, 0.0, None)):
    p, r, y, thr = controls
    sim.set_controls(p, r, y, sim.start.thtl0 if thr is None else thr)
    for _ in range(round(seconds / sim.model.step_size)):
        sim.step_once()


@needs_fmu
def test_trimmed_level_flight_stays_level(sim):
    sim.reset(0)
    st = sim.start
    run(sim, 5.0)
    m = sim.model
    assert abs(m["phi_deg"]) < 0.05
    assert abs(m["alt_m"] - st.h0) < 1.0
    assert m["tas_mps"] == pytest.approx(st.vt0, abs=0.3)
    assert m["theta_deg"] == pytest.approx(st.alpha0, abs=0.1)     # level: theta = alpha
    assert m["north_m"] == pytest.approx(5.0 * st.vt0, rel=2e-3)   # flying north
    assert not sim.crashed


@needs_fmu
def test_roll_stick_right_rolls_right_and_turns_right(sim):
    sim.reset(0)
    run(sim, 1.0, (0.0, 0.3, 0.0, None))
    assert sim.model["phi_deg"] > 30.0
    run(sim, 3.0)                                   # stick centred: the bank holds, the turn goes on
    m = sim.model
    assert 45.0 < m["phi_deg"] < 80.0
    assert m["psi_deg"] > 3.0 and m["east_m"] > 0.0
    assert abs(m["beta_deg"]) < 1.0                 # coordinated


@needs_fmu
def test_pull_hits_the_limiter_and_the_quaternion_matches_the_euler_angles(sim):
    sim.reset(2)
    run(sim, 3.0, (1.0, 0.0, 0.0, 1.0))
    m = sim.model
    assert m["limiter_active"] > 0.5
    assert m["nz_g"] < 9.3 and m["alpha_deg"] < 26.0
    R1 = body_to_ned(m["q_w"], m["q_x"], m["q_y"], m["q_z"])
    R2 = euler_to_ned(*np.radians([m["phi_deg"], m["theta_deg"], m["psi_deg"]]))
    assert np.max(np.abs(R1 - R2)) < 1e-6


@needs_fmu
def test_reset_restarts_from_the_trim(sim):
    sim.reset(1)
    run(sim, 1.0, (0.5, 0.5, 0.0, None))
    sim.reset(1)
    m = sim.model
    assert m.time == 0.0 and m["north_m"] == 0.0 and abs(m["phi_deg"]) < 1e-9
    assert math.isclose(m["alt_m"], sim.start.h0, abs_tol=1e-6)


RUNWAY = 6      # index of the runway start in build/starts.json
APPROACH = 7


@needs_fmu
def test_the_runway_start_rests_on_the_gear_and_stops_on_the_brakes(sim):
    sim.reset(RUNWAY)
    st = sim.start
    sim.set_brakes(1.0)
    run(sim, 3.0, (0.0, 0.0, 0.0, 0.0))
    m = sim.model
    assert m["on_ground"] > 0.5 and m["gear_pos"] == pytest.approx(1.0)
    assert m["ground_contact"] < 0.5 and m["departed"] < 0.5 and not sim.crashed
    assert m["fn_left"] == pytest.approx(m["fn_right"], rel=1e-3)
    assert m["fn_nose"] + m["fn_left"] + m["fn_right"] == pytest.approx(91100.0, rel=0.03)
    assert m["north_m"] - st.north0 < 0.2                  # the idle thrust only creeps against the brakes
    sim.toggle_gear()
    run(sim, 2.0, (0.0, 0.0, 0.0, 0.0))
    assert sim.model["gear_pos"] == pytest.approx(1.0)     # the interlock holds it down on the ground
    sim.set_brakes(0.0)


@needs_fmu
def test_taxi_steers_right_with_right_pedal(sim):
    sim.reset(RUNWAY)
    sim.set_brakes(0.0)
    run(sim, 8.0, (0.0, 0.0, 0.0, 0.3))
    run(sim, 4.0, (0.0, 0.0, 0.5, 0.0))
    m = sim.model
    assert m["steer_rad"] > 0.01 and m["east_m"] > sim.start.east0 + 1.0
    assert not sim.crashed


@needs_fmu
def test_the_approach_lands_on_the_gear(sim):
    sim.reset(APPROACH)
    sim.set_brakes(0.0)
    m = sim.model
    for _ in range(round(120.0 / m.step_size)):
        sim.set_controls(0.0, 0.0, 0.0, 0.0 if m["alt_m"] < 15.0 else sim.start.thtl0)
        sim.step_once()
        if m["on_ground"] > 0.5:
            break
    assert m["on_ground"] > 0.5 and not sim.crashed
    assert m["vs_mps"] > -5.0
    sim.set_brakes(0.0)
    run(sim, 5.0, (0.0, 0.0, 0.0, 0.0))
    assert not sim.crashed and sim.model["theta_deg"] < 5.0


@needs_fmu
def test_gear_up_ground_contact_is_still_a_crash(sim):
    sim.reset(5)                                    # 350 ft/s at 2000 ft, gear up
    run(sim, 30.0, (-0.6, 0.0, 0.0, 0.0))
    assert sim.crashed and sim.crash_reason == "ground contact"


def test_keyboard_works_next_to_a_bound_device():
    from f16sim.inputs import Mixer
    kb, mix = Keyboard({"stick_rate": 2.5, "spring": 4.0, "throttle_rate": 0.4}), Mixer()
    centred = {"pitch": 0.0, "roll": 0.0, "throttle": 0.6}   # e.g. a gamepad SDL lists first, at rest
    # no key held: the device flies
    assert mix.mix(centred, kb, {}) == (0.0, 0.0, 0.0, 0.6)
    # the up arrow (push) takes the pitch from the idle device; roll stays with the device
    held = {"push": True}
    kb.update(held, 0.2)
    p, r, _, t = mix.mix(centred, kb, held)
    assert p == pytest.approx(-0.5) and r == 0.0 and t == 0.6
    # released: the keyboard stick springs back, still in charge while the device does not move
    kb.update({}, 0.05)
    assert mix.mix(centred, kb, {})[0] == pytest.approx(-0.3)
    # moving the device's axis gives it back
    assert mix.mix({**centred, "pitch": 0.4}, kb, {})[0] == 0.4
    # throttle keys continue from the lever's setting, no jump
    held = {"throttle_up": True}
    t = mix.mix(centred, kb, held)[3]
    assert t == pytest.approx(0.6)
