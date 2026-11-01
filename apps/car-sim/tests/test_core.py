"""The simulation core without rendering: pacing, inputs, the track, the hills and the FMUs in closed loop.

The FMU tests need ``build/<vehicle>_sim.fmu`` and ``build/starts.json`` (``uv run build_fmu.py``)
and are skipped without them.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from carsim.core import Pacer, Simulation
from carsim.fmu import CORNERS, quat_matrix
from carsim.game import load_starts
from carsim.inputs import AxisMap, Keyboard, Mixer, map_axis, shape
from carsim.scripts import Driver, Path as DrivePath, hills_loop
from carsim.terrain import Hills
from carsim.track import LapTimer, Track, surface

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent.parent
STARTS = APP / "build" / "starts.json"
KB = {"steer_rate": 2.2, "steer_return": 3.0, "pedal_rate": 3.0, "pedal_release": 5.0}


def fmu(vehicle: str) -> Path:
    return APP / "build" / f"{vehicle}_sim.fmu"


def needs(vehicle: str):
    return pytest.mark.skipif(not fmu(vehicle).exists() or not STARTS.exists(), reason="run `uv run build_fmu.py` first")


# ---------------------------------------------------------------- pure parts
def test_pacer_carries_the_remainder():
    p = Pacer(0.005)
    steps = [p.steps_for(1.0 / 60.0) for _ in range(60)]
    assert sum(steps) == 200
    assert set(steps) <= {3, 4}
    assert p.behind == 0


def test_pacer_bounds_the_catch_up():
    p = Pacer(0.005, max_steps=20)
    assert p.steps_for(1.0) == 20
    assert p.behind == 1 and p.dropped == pytest.approx(0.9)


def test_shape_and_unipolar_pedals():
    assert shape(0.01, 0.02, 0.0) == 0.0
    assert shape(1.0, 0.02, 0.3) == pytest.approx(1.0)
    assert map_axis(-1.0, AxisMap(range="unipolar")) == 0.0          # a trigger at rest
    assert map_axis(1.0, AxisMap(range="unipolar")) == pytest.approx(1.0)


def test_keyboard_steering_returns_and_pedals_release():
    kb = Keyboard(KB)
    for _ in range(60):
        kb.update({"right": True, "accel": True}, 1 / 60)
    assert kb.steer == pytest.approx(1.0) and kb.throttle == pytest.approx(1.0)
    for _ in range(60):
        kb.update({}, 1 / 60)
    assert kb.steer == 0.0 and kb.throttle == 0.0


def test_mixer_last_touched_wins():
    kb = Keyboard(KB)
    mx = Mixer()
    # a bound but idle wheel: the keyboard still steers while its key is held
    kb.update({"left": True}, 0.2)
    s, _, _ = mx.mix({"steer": 0.0, "throttle": 0.0, "brake": 0.0}, kb, {"left": True})
    assert s == pytest.approx(kb.steer) and s < 0
    # released: the keyboard value returns, the device has not moved: still the keyboard's
    kb.update({}, 0.05)
    s, _, _ = mx.mix({"steer": 0.0, "throttle": 0.0, "brake": 0.0}, kb, {})
    assert mx.source["steer"] == "keyboard"
    # the wheel moves: it takes the control back
    s, _, _ = mx.mix({"steer": 0.4, "throttle": 0.0, "brake": 0.0}, kb, {})
    assert s == pytest.approx(0.4) and mx.source["steer"] == "device"


def test_track_surfaces_follow_the_rules():
    tr = Track()
    assert tr.length > 1000
    x, y, _ = tr.pose_at(100.0)
    assert tr.surface_at(x, y) == "asphalt"
    assert surface(0.0, 7.0, 6.0, 1.4, 1 / 180, 14.0) == "grass"          # no kerbs on a straight
    assert surface(0.02, 6.5, 6.0, 1.4, 1 / 180, 14.0) == "kerb"
    assert surface(0.02, -12.0, 6.0, 1.4, 1 / 180, 14.0) == "runoff"      # outside of a left-hander
    assert surface(0.02, 12.0, 6.0, 1.4, 1 / 180, 14.0) == "grass"        # inside
    assert tr.mu["grass"] < tr.mu["kerb"] < tr.mu["asphalt"]


def test_lap_timer_counts_forward_crossings():
    lt = LapTimer(100.0)
    t = 0.0
    for lap in range(3):
        for s in np.arange(0.0, 100.0, 1.0):
            lt.update(t, (s + 50.0) % 100.0)
            t += 0.1
    assert lt.laps == pytest.approx([10.0, 10.0])
    assert lt.best == pytest.approx(10.0)


def test_hills_are_the_fmu_terrain():
    """The drawn height field and the buggy-sim model's TerrainSurface parameters are one table."""
    doc = json.loads((ROOT / "examples" / "cars" / "models" / "buggy-sim.bgmodel.json").read_text(encoding="utf-8"))
    nodes = [n for n in doc["diagram"]["nodes"] if n.get("block", {}).get("ref") == "stdlib:contact/TerrainSurface"]
    assert len(nodes) == 4
    h = Hills()
    for n in nodes:
        p = n["params"]
        assert float(p["h0"]) == h.h0 and float(p["sx"]) == h.sx and float(p["sy"]) == h.sy
        for k in ("a", "kx", "ky", "ph"):
            assert np.array_equal(np.array(json.loads(p[k]), float), getattr(h, k))
    # the gradient is the derivative of the height
    x, y, e = 37.0, -52.0, 1e-5
    gx, gy = h.gradient(x, y)
    assert gx == pytest.approx((h.height(x + e, y) - h.height(x - e, y)) / (2 * e), rel=1e-6)
    assert gy == pytest.approx((h.height(x, y + e) - h.height(x, y - e)) / (2 * e), rel=1e-6)


def test_driver_steers_towards_the_path():
    path = DrivePath(hills_loop())
    d = Driver(path, 15.0, 4.0, wheelbase=2.7, steer_max=math.radians(30.0))
    steer, thr, brk = d.controls(0.0, -120.0, 0.0, 0.0)           # on the loop, heading along it
    assert abs(steer) < 0.3 and thr > 0 and brk == 0
    steer, _, _ = d.controls(0.0, -130.0, 0.0, 5.0)               # 10 m right of it: steer left
    assert steer < -0.2


# ---------------------------------------------------------------- the FMUs
def run(sim, seconds, steer=0.0, throttle=0.0, brake=0.0, hand=0.0):
    sim.set_controls(steer, throttle, brake, hand)
    for _ in range(round(seconds / sim.model.step_size)):
        sim.step_once()


@pytest.fixture(scope="module")
def racecar():
    s = Simulation("racecar", fmu("racecar"), load_starts(STARTS, "racecar"))
    yield s
    s.close()


@pytest.fixture(scope="module")
def buggy():
    s = Simulation("buggy", fmu("buggy"), load_starts(STARTS, "buggy"))
    yield s
    s.close()


@needs("racecar")
def test_racecar_rests_on_the_grid(racecar):
    racecar.reset(0)
    st = racecar.start
    run(racecar, 2.0, brake=0.3)
    m = racecar.model
    assert math.hypot(m["chassis_px"] - st.x0, m["chassis_py"] - st.y0) < 0.02
    assert abs(m["chassis_pz"] - st.z0) < 0.02
    assert m["speed"] < 0.05
    assert racecar.surfaces == ["asphalt"] * 4
    assert m["soc"] == pytest.approx(st.soc0, abs=1e-4)


@needs("racecar")
def test_racecar_launch_at_the_torque_limit(racecar):
    racecar.reset(0)
    run(racecar, 0.5, brake=0.3)
    run(racecar, 3.0, throttle=1.0)
    m = racecar.model
    # design/reference.py: 8.1 m/s^2 at the 300 N m limit (traction control trims the first 0.1 s)
    assert 22.0 < m["speed"] < 25.5
    assert m["motor_r_torque"] == pytest.approx(300.0, rel=0.02)
    assert m["soc"] < racecar.start.soc0
    assert m["battery_a"] > 100.0
    # the heading did not wander on the straight
    R = quat_matrix(m["chassis_qw"], m["chassis_qx"], m["chassis_qy"], m["chassis_qz"])
    assert abs(math.atan2(R[1, 0], R[0, 0]) - racecar.start.yaw0) < 0.02


@needs("racecar")
def test_racecar_regenerates_when_braking(racecar):
    racecar.reset(0)
    run(racecar, 4.0, throttle=1.0)
    soc = racecar.model["soc"]
    v = racecar.model["speed"]
    run(racecar, 1.5, brake=0.4)
    m = racecar.model
    assert m["speed"] < v - 5.0
    assert m["motor_r_torque"] < -10.0 and m["battery_a"] < 0.0
    assert m["soc"] > soc


@needs("racecar")
def test_racecar_reverses_only_at_rest(racecar):
    racecar.reset(0)
    run(racecar, 2.0, throttle=0.5)
    assert not racecar.toggle_reverse()
    racecar.reset(0)
    run(racecar, 0.5)
    assert racecar.toggle_reverse()
    run(racecar, 2.0, throttle=0.4)
    m = racecar.model
    R = quat_matrix(m["chassis_qw"], m["chassis_qx"], m["chassis_qy"], m["chassis_qz"])
    fwd = R[:2, 0]
    moved = np.array([m["chassis_px"] - racecar.start.x0, m["chassis_py"] - racecar.start.y0])
    assert float(fwd @ moved) < -1.0


@needs("racecar")
def test_racecar_grass_lowers_the_friction(racecar):
    racecar.reset(0)
    st = racecar.start
    # move the start 20 m to the left of the grid: on the grass (no kerbs on the straight)
    nx, ny = -math.sin(st.yaw0), math.cos(st.yaw0)
    racecar.starts.append(type(st)("grass", st.x0 + 20 * nx, st.y0 + 20 * ny, st.z0, st.yaw0, st.soc0))
    racecar.reset(len(racecar.starts) - 1)
    run(racecar, 0.2)
    assert racecar.surfaces == ["grass"] * 4
    assert racecar.u[5:9] == pytest.approx([racecar.track.mu["grass"]] * 4)
    racecar.starts.pop()


@needs("buggy")
def test_buggy_wheels_on_the_drawn_terrain(buggy):
    buggy.reset(0)
    run(buggy, 2.0, brake=0.5)
    m = buggy.model
    h = Hills()
    for c in CORNERS:
        # the contact the FMU uses lies on the height field the host draws
        assert m[f"{c}_zc"] == pytest.approx(float(h.height(m[f"{c}_xc"], m[f"{c}_yc"])), abs=2e-3)
        assert m[f"{c}_fz"] > 1000.0
    assert m["speed"] < 0.1


@needs("buggy")
def test_buggy_climbs_with_four_wheel_drive(buggy):
    buggy.reset(0)
    run(buggy, 0.5, brake=0.5)
    run(buggy, 6.0, throttle=0.6)
    m = buggy.model
    assert m["speed"] > 5.0
    assert m["motor_f_torque"] > 5.0 and m["motor_r_torque"] > 5.0
    assert buggy.warning == ""
