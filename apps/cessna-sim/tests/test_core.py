"""The simulation core without rendering: pacing, input shaping, wind, the touchdown rating and
the FMU in closed loop (the runway at rest, the take-off, the reset, the quaternion, the
touchdown and the crash detection).

The FMU tests need ``build/cessna_sim.fmu`` and ``build/starts.json`` (``uv run build_fmu.py``)
and are skipped without them.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from cessnasim.core import (FN_CRASH, RUNWAY_X0, Pacer, Simulation, Turbulence, rate_touchdown,
                            wrap180)
from cessnasim.fmu import INPUTS, Start, body_to_world, default_inputs, euler_to_world
from cessnasim.inputs import AxisMap, Keyboard, Mixer, map_axis, shape
from cessnasim.pilot import SCRIPTS, Pilot

APP = Path(__file__).resolve().parents[1]
FMU = APP / "build" / "cessna_sim.fmu"
STARTS = APP / "build" / "starts.json"
needs_fmu = pytest.mark.skipif(not FMU.exists() or not STARTS.exists(), reason="run `uv run build_fmu.py` first")


# ---- without the FMU

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


def test_keyboard_yoke_springs_back_and_levers_stay():
    kb = Keyboard({})
    for _ in range(60):
        kb.update({"right": True, "pull": True, "throttle_up": True}, 1 / 60)
    assert kb.roll == pytest.approx(1.0) and kb.pitch == pytest.approx(1.0)
    thr = kb.throttle
    assert 0.0 < thr <= 1.0
    for _ in range(60):
        kb.update({}, 1 / 60)
    assert kb.roll == 0.0 and kb.pitch == 0.0
    assert kb.throttle == thr                         # the throttle stays where it was put
    kb.update({"brakes": True}, 1 / 60)
    assert kb.brake_l == 1.0 and kb.brake_r == 1.0
    kb.update({"brake_l": True}, 1 / 60)
    assert kb.brake_l == 1.0 and kb.brake_r == 0.0


def test_keyboard_works_next_to_a_bound_device():
    kb, mix = Keyboard({}), Mixer()
    centred = {"pitch": 0.0, "roll": 0.0, "throttle": 0.6}   # e.g. a yoke and quadrant at rest
    out = mix.mix(centred, kb, {})
    assert out["pitch"] == 0.0 and out["throttle"] == 0.6 and out["yaw"] == 0.0
    held = {"push": True}                    # a key takes the pitch from the idle device
    kb.update(held, 0.2)
    out = mix.mix(centred, kb, held)
    assert out["pitch"] < 0.0 and out["roll"] == 0.0
    assert mix.mix({**centred, "pitch": 0.4}, kb, {})["pitch"] == 0.4   # moving the device takes it back
    held = {"throttle_up": True}             # the throttle keys continue from the lever's setting
    assert mix.mix(centred, kb, held)["throttle"] == pytest.approx(0.6)


def test_wind_falls_off_to_the_ground():
    w = Turbulence(steady=(0.0, 5.0, 0.0))
    assert np.allclose(w.sample(0.005, 50.0, 0.0), 0.0)
    assert w.sample(0.005, 50.0, 200.0)[1] == pytest.approx(5.0)
    assert 3.5 < w.sample(0.005, 50.0, 10.0)[1] < 5.0
    g = Turbulence(intensity=2.0, seed=3)
    samples = np.array([g.sample(0.005, 50.0, 300.0) for _ in range(20000)])
    assert 0.5 < samples[:, 0].std() < 3.0 and abs(samples[:, 0].mean()) < 1.0


def test_touchdown_rating_and_wrap():
    assert rate_touchdown(-150.0) == "smooth"
    assert rate_touchdown(-300.0) == "firm"
    assert rate_touchdown(-600.0) == "hard"
    assert rate_touchdown(-1000.0) == "very hard"
    assert wrap180(350.0) == pytest.approx(-10.0) and wrap180(-190.0) == pytest.approx(170.0)


def test_quaternion_matches_the_euler_angles():
    phi, theta, psi = math.radians(20.0), math.radians(5.0), math.radians(300.0)
    # the FMU's quaternion of these angles: yaw (-psi about up), pitch (-theta about left), roll (phi about fwd)
    def q(axis, a):
        return np.array([math.cos(a / 2), *(math.sin(a / 2) * np.asarray(axis, float))])

    def mul(a, b):
        w1, x1, y1, z1 = a
        w2, x2, y2, z2 = b
        return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                         w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])

    qq = mul(mul(q((0, 0, 1), -psi), q((0, 1, 0), -theta)), q((1, 0, 0), phi))
    assert np.max(np.abs(body_to_world(*qq) - euler_to_world(phi, theta, psi))) < 1e-12


def test_default_inputs_take_the_start_controls():
    st = Start("x", {}, {"throttle": 0.7, "flaps": 3.0, "trim": 0.1})
    u = default_inputs(st)
    assert u[INPUTS.index("throttle")] == 0.7 and u[INPUTS.index("flaps")] == 3.0
    assert u[INPUTS.index("mixture")] == 1.0 and u[INPUTS.index("ap_roll_mode")] == 0.0


def test_scripts_are_well_formed():
    for script in SCRIPTS.values():
        for leg in script.legs:
            Pilot(**leg.pilot)
            assert all(0.0 <= t < leg.duration for t, _ in leg.views)
            assert all(0.0 <= a < b <= leg.duration for a, b, _ in leg.captions)


# ---- the FMU in closed loop

@pytest.fixture(scope="module")
def sim():
    s = Simulation(FMU, Start.load_all(STARTS))
    yield s
    s.close()


def run(sim, seconds, pilot=None):
    for _ in range(round(seconds / sim.model.step_size)):
        if pilot is not None:
            pilot(sim)
        sim.step_once()
        if sim.crashed:
            break


@needs_fmu
def test_runway_start_is_at_rest(sim):
    sim.reset(0)
    sim.set_controls(brake_l=1.0, brake_r=1.0)
    run(sim, 3.0)
    m = sim.model
    assert abs(m["north_m"]) < 0.05 and abs(m["east_m"]) < 0.05   # braked at idle (it creeps without)
    assert m["kias"] < 0.5 and m["on_ground"] > 0.5
    assert 2.0 < m["theta_deg"] < 5.0                      # the nose-up sit of the tricycle gear
    assert 500.0 < m["rpm"] < 900.0                        # idle
    assert m["fn_left"] + m["fn_right"] + m["fn_nose"] == pytest.approx(1088.62 * 9.80665, rel=0.02)
    assert sim.on_runway() and not sim.crashed and not sim.touchdowns


@needs_fmu
def test_full_power_takes_off(sim):
    sim.reset(0)
    pilot = Pilot()
    run(sim, 45.0, pilot)
    m = sim.model
    phases = [p for _, p in pilot.log]
    assert phases[:2] == ["rotate", "climb"]
    assert m["on_ground"] < 0.5 and sim.agl() > 3.0 and m["vs_fpm"] > 0.0
    assert 55.0 < m["kias"] < 80.0 and abs(m["east_m"]) < 30.0
    assert 2200.0 < m["rpm"] < 2600.0
    assert not sim.crashed and not sim.touchdowns          # the lift-off is not a touchdown


@needs_fmu
def test_airborne_trims_hold(sim):
    for k, st in enumerate(sim.starts):
        if not st.airborne:
            continue
        sim.reset(k)
        h0, v0, vs0 = sim.model["alt_m"], sim.model["kias"], sim.model["vs_fpm"]
        run(sim, 5.0)
        m = sim.model
        # hands off the yoke the longitudinal trim holds; the start's controls are the levers
        # only (the yoke and pedals are the pilot's), so the lateral trim is not held and the
        # aircraft rolls off slowly
        assert m["kias"] == pytest.approx(v0, abs=1.5), st.label
        assert m["alt_m"] == pytest.approx(h0 + 5.0 * vs0 * 0.3048 / 60.0, abs=3.0), st.label
        assert abs(m["phi_deg"]) < 10.0, st.label
        assert not sim.crashed, st.label


@needs_fmu
def test_reset_restarts_from_the_start(sim):
    sim.reset(1)
    sim.set_controls(yoke_roll=0.5, yoke_pitch=0.3)
    run(sim, 2.0)
    assert abs(sim.model["phi_deg"]) > 5.0
    sim.reset(1)
    m = sim.model
    st = sim.start
    assert m.time == 0.0 and abs(m["phi_deg"]) < 1e-6
    assert m["north_m"] == pytest.approx(st.values["x0"]) and m["alt_m"] == pytest.approx(st.values["z0"])
    assert sim.u[INPUTS.index("throttle")] == pytest.approx(st.controls["throttle"])


@needs_fmu
def test_quaternion_output_matches_the_euler_outputs(sim):
    sim.reset(4)                                           # heading east
    sim.set_controls(yoke_roll=-0.4, yoke_pitch=0.2)
    run(sim, 3.0)
    m = sim.model
    R1 = body_to_world(m["q_w"], m["q_x"], m["q_y"], m["q_z"])
    R2 = euler_to_world(*np.radians([m["phi_deg"], m["theta_deg"], m["psi_deg"]]))
    assert abs(m["phi_deg"]) > 10.0
    assert np.max(np.abs(R1 - R2)) < 1e-6


@needs_fmu
def test_landing_from_final_is_a_smooth_touchdown(sim):
    sim.reset(2)
    pilot = Pilot(phase="final")
    run(sim, 115.0, pilot)
    assert not sim.crashed
    assert len(sim.touchdowns) == 1
    td = sim.touchdowns[0]
    assert td.rating in ("smooth", "firm")
    assert 0.0 < td.distance_m < 600.0 and abs(td.offset_m) < 15.0
    assert sim.on_runway() and pilot.phase == "landed"


@needs_fmu
def test_a_dive_into_the_ground_is_a_crash(sim):
    sim.reset(3)                                           # short final, 300 ft
    sim.set_controls(yoke_pitch=-1.0, throttle=1.0)
    run(sim, 30.0)
    assert sim.crashed
    assert "strike" in sim.crash_reason or "collapsed" in sim.crash_reason
    n = round(1.0 / sim.model.step_size)
    assert sim.advance(1.0) == 0 and n > 0                 # a crashed simulation does not advance
    sim.reset(3)
    assert not sim.crashed and FN_CRASH > 0.0 and RUNWAY_X0 < 0.0
