"""Drones, seeker lock-on and the AIM-9X FMU in the host (no rendering)."""

from __future__ import annotations

from pathlib import Path

import pytest
from f16sim.missile_model import (
    IR_W,
    Launch,
    MissileManager,
    local_to_world,
    target_input,
)
from f16sim.tactical import Drone, DroneManager, LockOn

APP = Path(__file__).resolve().parents[1]
MISSILE = APP / "build" / "aim9x_fmu.fmu"
needs_missile = pytest.mark.skipif(not MISSILE.exists(), reason="run `uv run build_fmu.py` first")


def test_at_most_three_drones_and_a_replacement_after_a_kill():
    spawner = DroneManager(seed=1)
    spawner.reset(0.0, 0.0, 3000.0, 0.0)
    assert len(spawner.alive()) == 3
    assert spawner.spawn(0.0, 0.0, 3000.0, 0.0) is None
    first = spawner.alive()[0]
    spawner.kill(first.id)
    assert len(spawner.alive()) == 2
    for _ in range(1000):
        spawner.step(0.005, 0.0, 0.0, 3000.0, 0.0)
    assert len(spawner.alive()) == 3
    assert spawner.by_id(first.id).alive is False


def test_lock_builds_in_one_second_and_breaks_out_of_the_field():
    drones = DroneManager(seed=2)
    drones.reset(0.0, 0.0, 3000.0, 0.0)
    lock = LockOn()
    own = (0.0, 0.0, 3000.0)
    nose = (1.0, 0.0, 0.0)
    for _ in range(250):
        state = lock.update(0.005, own, nose, drones)
    assert state.locked and state.selected_id is not None
    assert state.angle_deg < 5.0
    # turn the nose away: the selected target is outside the 45 deg half-angle
    for _ in range(250):
        state = lock.update(0.005, own, (0.0, 0.0, 1.0), drones)
    assert not state.locked and state.reason in ("OUT OF FOV", "TOO FAR")


def test_target_input_is_the_launch_relative_ned_state():
    launch = Launch(1000.0, 2000.0, 3000.0, 90.0, 400.0, 0)
    target = Drone(1, 3000.0, 2000.0, 3100.0, 90.0, 150.0)
    u = target_input(launch, target)
    # heading 90: the launch's local north points east; the target is 2000 m north of it
    assert u[0] == pytest.approx(0.0)
    assert u[1] == pytest.approx(-2000.0)
    assert u[2] == pytest.approx(-3100.0)
    assert u[3] == pytest.approx(150.0)
    assert u[4] == pytest.approx(0.0)
    assert u[6] == IR_W
    # the same local point comes back to the world
    n, e, h = local_to_world(launch, u[0], -u[1], -u[2])
    assert (n, e, h) == pytest.approx((3000.0, 2000.0, 3100.0))


def target_drone(north: float, east: float, alt: float, heading: float, speed: float) -> Drone:
    return Drone(1, north, east, alt, heading, speed)


@needs_missile
def test_a_shot_flies_from_a_wingtip_and_fires_the_fuze():
    manager = MissileManager(MISSILE)
    try:
        launch = Launch(0.0, 0.0, 3000.0, 0.0, 400.0, 0)
        target = target_drone(2000.0, 0.0, 3000.0, 0.0, 150.0)
        missile = manager.fire(launch, target)
        assert missile is not None
        for _ in range(1400):
            manager.step(_Drones(target))
            if missile.done:
                break
        assert missile.fuze_latched
        assert missile.killed
        assert missile.time < 5.0
        assert missile.y[0] > 1500.0                            # it flew north (local north, heading 0)
    finally:
        manager.close()


@needs_missile
def test_two_instances_are_independent():
    manager = MissileManager(MISSILE)
    try:
        a = manager.fire(Launch(0.0, 0.0, 3000.0, 0.0, 400.0, 0),
                         target_drone(2000.0, 0.0, 3000.0, 0.0, 150.0))
        b = manager.fire(Launch(0.0, 0.0, 3000.0, 180.0, 400.0, 1),
                         target_drone(-2000.0, 0.0, 3000.0, 180.0, 150.0))
        assert a is not None and b is not None
        for _ in range(200):
            a.step(target_drone(2000.0, 0.0, 3000.0, 0.0, 150.0))
            b.step(target_drone(-2000.0, 0.0, 3000.0, 180.0, 150.0))
        na = local_to_world(a.launch, a.y[0], a.y[1], a.y[2])[0]
        nb = local_to_world(b.launch, b.y[0], b.y[1], b.y[2])[0]
        assert na > 100.0 and nb < -100.0
        assert na == pytest.approx(-nb, abs=20.0)
    finally:
        manager.close()


class _Drones:
    """The tiny slice of DroneManager the missile step needs in the tests."""

    def __init__(self, *drones: Drone):
        self._drones = list(drones)

    def by_id(self, drone_id):
        return next((d for d in self._drones if d.id == drone_id), None)

    def kill(self, drone_id):
        return None
