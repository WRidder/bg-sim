"""The simulation core without rendering: pacing, input shaping, the cyclic trim, wind, the
touchdown rating and the FMU in closed loop (the helicopter parked on the pad, the lift-off, the
reset, the hover, the landing of the scripted pilot, the crash detection) and a short headless run
of the whole app (Panda3D offscreen).

The FMU tests need ``build/a109_sim.fmu`` and ``build/starts.json`` (``uv run build_fmu.py``) and
are skipped without them.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from a109sim.core import WEIGHT, Pacer, Simulation, Turbulence, rate_touchdown, wrap180
from a109sim.fmu import INPUTS, Start, default_inputs, euler_to_world, ground_velocity
from a109sim.inputs import AXES, AxisMap, CyclicTrim, Keyboard, Mixer, load_config, map_axis, shape
from a109sim.pilot import SCRIPTS, Pilot, coll_level

APP = Path(__file__).resolve().parents[1]
FMU = APP / "build" / "a109_sim.fmu"
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
    # the collective on a throttle axis: lever forward (SDL -1) is full up
    assert map_axis(-1.0, AxisMap(invert=True, range="unipolar")) == pytest.approx(1.0)
    assert map_axis(1.0, AxisMap(invert=True, range="unipolar")) == pytest.approx(0.0)
    assert map_axis(0.0, AxisMap(range="unipolar")) == pytest.approx(0.5)


def test_the_axis_config_maps_every_control():
    axes, buttons, kb = load_config(APP / "config" / "devices.toml")
    assert set(axes) == set(AXES)
    assert axes["collective"].range == "unipolar" and axes["cyclic_lon"].invert
    assert kb["collective_rate"] > 0.0 and kb["spring"] > 0.0
    # SDL's stick forward (-1) is cyclic forward (+1, nose down)
    assert map_axis(-1.0, axes["cyclic_lon"]) == pytest.approx(1.0)


def test_keyboard_cyclic_springs_back_and_the_collective_stays():
    kb = Keyboard({})
    for _ in range(60):
        kb.update({"right": True, "fwd": True, "coll_up": True, "ped_left": True}, 1 / 60)
    assert kb.cyclic_lat == pytest.approx(1.0) and kb.cyclic_lon == pytest.approx(1.0)
    assert kb.pedals == pytest.approx(-1.0)
    coll = kb.collective
    assert 0.0 < coll <= 1.0
    for _ in range(60):
        kb.update({}, 1 / 60)
    assert kb.cyclic_lat == 0.0 and kb.cyclic_lon == 0.0 and kb.pedals == 0.0
    assert kb.collective == coll                      # the collective stays where it was put


def test_keyboard_works_next_to_a_bound_device():
    kb, mix = Keyboard({}), Mixer()
    centred = {"cyclic_lon": 0.0, "cyclic_lat": 0.0, "collective": 0.6}   # a stick and a lever at rest
    out = mix.mix(centred, kb, {})
    assert out["cyclic_lon"] == 0.0 and out["collective"] == 0.6 and out["pedals"] == 0.0
    held = {"aft": True}                     # a key takes the cyclic from the idle device
    kb.update(held, 0.2)
    out = mix.mix(centred, kb, held)
    assert out["cyclic_lon"] < 0.0 and out["cyclic_lat"] == 0.0
    assert mix.mix({**centred, "cyclic_lon": 0.4}, kb, {})["cyclic_lon"] == 0.4   # moving the device takes it back
    held = {"coll_up": True}                 # the collective keys continue from the lever's setting
    assert mix.mix(centred, kb, held)["collective"] == pytest.approx(0.6)


def test_cyclic_trim():
    kb, trim = Keyboard({}), CyclicTrim()
    kb.cyclic_lon, kb.cyclic_lat = 0.3, -0.2
    trim.force_trim(kb.cyclic_lon, kb.cyclic_lat, kb, device=False)
    assert kb.cyclic_lon == 0.0 and trim.apply(0.0, 0.0) == pytest.approx((0.3, -0.2))
    assert trim.apply(1.0, 0.0)[0] == 1.0    # clamped to the travel
    # a device: the cyclic holds the trimmed position until the stick comes back to its centre
    trim.release()
    trim.force_trim(0.5, 0.0, kb, device=True)
    assert trim.apply(0.5, 0.0) == pytest.approx((0.5, 0.0))
    assert trim.apply(0.2, 0.0) == pytest.approx((0.5, 0.0))
    assert trim.apply(0.0, 0.0) == pytest.approx((0.5, 0.0))
    assert trim.apply(0.2, 0.0) == pytest.approx((0.7, 0.0))   # the stick works about the new centre
    trim.nudge(-0.1)
    assert trim.lon == pytest.approx(0.4)
    trim.release()
    assert trim.apply(0.0, 0.0) == (0.0, 0.0)


def test_wind_falls_off_to_the_ground():
    w = Turbulence(steady=(0.0, 5.0, 0.0))
    assert np.allclose(w.sample(0.005, 50.0, 0.0), 0.0)
    assert w.sample(0.005, 50.0, 200.0)[1] == pytest.approx(5.0)
    assert 3.5 < w.sample(0.005, 50.0, 10.0)[1] < 5.0
    g = Turbulence(intensity=2.0, seed=3)
    samples = np.array([g.sample(0.005, 50.0, 300.0) for _ in range(20000)])
    assert 0.5 < samples[:, 0].std() < 3.0 and abs(samples[:, 0].mean()) < 1.0


def test_touchdown_rating_and_wrap():
    assert rate_touchdown(-0.3) == "smooth"
    assert rate_touchdown(-0.8) == "firm"
    assert rate_touchdown(-1.5) == "hard"
    assert rate_touchdown(-2.5) == "very hard"
    assert wrap180(350.0) == pytest.approx(-10.0) and wrap180(-190.0) == pytest.approx(170.0)


def test_euler_and_ground_velocity():
    R = euler_to_world(0.0, 0.0, math.radians(90.0))       # heading east
    assert np.allclose(R @ [1.0, 0.0, 0.0], [0.0, -1.0, 0.0], atol=1e-12)   # forward = east = -west
    y = {"phi_deg": 0.0, "theta_deg": 0.0, "psi_deg": 90.0, "u_mps": 10.0, "v_mps": 2.0, "w_mps": -1.0}
    n, e, up = ground_velocity(y)
    assert (n, e, up) == pytest.approx((-2.0, 10.0, 1.0))   # right of east is south; w up is climbing
    R = euler_to_world(math.radians(30.0), 0.0, 0.0)       # bank right: the left wing (+y) goes up
    assert (R @ [0.0, 1.0, 0.0])[2] == pytest.approx(0.5)


def test_default_inputs_take_the_start_controls():
    st = Start("x", {}, {"collective": 0.6})
    u = default_inputs(st)
    assert u[INPUTS.index("collective")] == 0.6 and u[INPUTS.index("scas")] == 1.0
    assert u[INPUTS.index("cyclic_lon")] == 0.0


def test_scripts_are_well_formed():
    for script in SCRIPTS.values():
        for leg in script.legs:
            Pilot(**leg.pilot)
            assert all(0.0 <= t < leg.duration for t, _ in leg.views)
            assert all(0.0 <= a < b <= leg.duration for a, b, _ in leg.captions)
    assert SCRIPTS["demo"].duration <= 60.0
    assert coll_level(0.0) > coll_level(60.0) < coll_level(140.0)   # the power bucket


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
def test_the_fmu_loads_and_steps(sim):
    sim.reset(2)
    y0 = sim.model.y.copy()
    sim.step_once()
    assert sim.model.time == pytest.approx(sim.model.step_size)
    assert np.all(np.isfinite(sim.model.y)) and not np.array_equal(y0, sim.model.y)
    assert sim.model["alt_m"] == pytest.approx(15.0, abs=0.01)


@needs_fmu
def test_parked_on_the_pad_is_at_rest(sim):
    sim.reset(0)
    run(sim, 3.0)
    m = sim.model
    assert abs(m["north_m"]) < 0.05 and abs(m["east_m"]) < 0.05
    assert math.hypot(*ground_velocity(m)[:2]) < 0.02
    assert m["wow"] > 0.999 and sim.on_ground and sim.on_pad()
    assert abs(m["theta_deg"]) < 0.5 and abs(m["phi_deg"]) < 0.5
    assert m["rotor_pct"] == pytest.approx(100.0, abs=0.1)
    # the weight and the small down-thrust of the rotor at flat pitch (collective down)
    assert WEIGHT < sim.gear_load < 1.05 * WEIGHT
    assert not sim.crashed and not sim.touchdowns


@needs_fmu
def test_collective_up_lifts_off(sim):
    sim.reset(0)
    pilot = Pilot(t_parked=0.5)
    run(sim, 12.0, pilot)
    m = sim.model
    assert [p for _, p in pilot.log][:2] == ["liftoff", "hover"]
    assert m["wow"] < 0.01 and sim.agl() > 2.0 and not sim.on_ground
    assert abs(m["north_m"]) < 2.0 and abs(m["east_m"]) < 2.0
    assert not sim.crashed and not sim.touchdowns          # the lift-off is not a touchdown


@needs_fmu
def test_hover_starts_hold_hands_off(sim):
    for k, st in enumerate(sim.starts):
        if not st.airborne or st.values["Pvx0"] != 0.0:
            continue
        sim.reset(k)
        h0 = sim.model["alt_m"]
        run(sim, 5.0)
        m = sim.model
        # the SCAS holds the attitude and the trim's collective the height (no position hold)
        assert m["alt_m"] == pytest.approx(h0, abs=1.0), st.label
        assert math.hypot(*ground_velocity(m)[:2]) < 1.5, st.label
        assert abs(m["phi_deg"]) < 5.0 and abs(m["theta_deg"]) < 8.0, st.label
        assert not sim.crashed, st.label


@needs_fmu
def test_reset_restarts_from_the_start(sim):
    sim.reset(2)
    sim.set_controls(cyclic_lat=0.5, cyclic_lon=0.3)
    run(sim, 2.0)
    assert abs(sim.model["phi_deg"]) > 5.0
    sim.reset(2)
    m = sim.model
    st = sim.start
    assert m.time == 0.0 and m["north_m"] == pytest.approx(st.values["x0"])
    assert m["alt_m"] == pytest.approx(st.values["z0"])
    assert sim.u[INPUTS.index("collective")] == pytest.approx(st.controls["collective"])
    assert sim.scas_on


@needs_fmu
def test_scas_switch(sim):
    sim.reset(2)
    run(sim, 0.5)
    b1_on = sim.model["B1_deg"]
    sim.set_scas(False)
    sim.set_controls(cyclic_lon=0.0)
    run(sim, 0.2)
    # off: the rigging's angle of the centred stick, not the SCAS's trim
    assert sim.model["B1_deg"] != pytest.approx(b1_on, abs=0.2)
    sim.toggle_scas()
    assert sim.scas_on


@needs_fmu
def test_the_scripted_landing_touches_down_on_the_pad(sim):
    sim.reset(3)                                           # short final, 30 kt
    pilot = Pilot(**SCRIPTS["landing"].legs[0].pilot)
    run(sim, 70.0, pilot)
    assert not sim.crashed, sim.crash_reason
    assert pilot.phase == "landed" and len(sim.touchdowns) == 1
    td = sim.touchdowns[0]
    assert td.rating == "smooth" and td.on_pad and td.gs_mps < 0.5


@needs_fmu
def test_collective_dumped_in_a_hover_is_a_crash(sim):
    sim.reset(2)                                           # hover at 15 m
    sim.set_controls(collective=0.0)
    run(sim, 10.0)
    assert sim.crashed
    assert "collapsed" in sim.crash_reason or "strike" in sim.crash_reason
    assert sim.advance(1.0) == 0                           # a crashed simulation does not advance
    sim.reset(2)
    assert not sim.crashed


@needs_fmu
def test_rolling_into_the_ground_is_a_crash(sim):
    sim.reset(1)                                           # hover at 3 m
    sim.set_scas(False)
    sim.set_controls(cyclic_lat=1.0)
    run(sim, 10.0)
    assert sim.crashed and sim.crash_reason


@needs_fmu
def test_headless_app_runs_the_demo_pilot():
    from a109sim.app import main

    assert main(["--headless", "--script", "smoke", "--seconds", "12", "--size", "320x180", "--fps", "20",
                 "--msaa", "0"]) == 0
