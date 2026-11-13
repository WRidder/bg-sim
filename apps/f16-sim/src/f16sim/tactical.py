"""Drones, the seeker lock-on and the tactical contacts, without rendering.

The AIM-9X seeker is cued by the aircraft (radar or the helmet-mounted cueing system) and then
tracks the infrared contrast of a target inside its 90 deg field of view. This module models
the pilot's side of that loop: a selected drone, the off-boresight angle to the aircraft nose,
the range limit of the seeker and a one-second track build-up. The missile's own seeker is in
its FMU; the host lock is the pre-launch cue and the firing interlock.

Coordinates are the simulation's NED: north and east in metres, altitude up in metres; the
aircraft nose is the body x axis in NED.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import terrain

MAX_DRONES = 3
SPAWN_DELAY = 4.0
SEEKER_FOV_DEG = 90.0          # the model's imaging seeker: 90 deg full field of view
SEEKER_HALF_DEG = SEEKER_FOV_DEG * 0.5
SEEKER_RANGE_M = 7000.0        # 1e6 W / r^2 above the 0.02 W/m^2 detection threshold
SEEKER_TRACK_S = 1.0           # from MissileSeeker/t_lock


@dataclass
class Drone:
    """A kinematic target drone: straight flight with an optional gentle turn."""

    id: int
    north: float
    east: float
    alt: float
    heading_deg: float
    speed: float
    turn_rate: float = 0.0       # deg/s
    turn_at: float = 1.0e9       # s after spawn
    age: float = 0.0
    alive: bool = True

    def step(self, dt: float) -> None:
        if not self.alive:
            return
        self.age += dt
        if self.age >= self.turn_at:
            self.heading_deg += self.turn_rate * dt
        psi = math.radians(self.heading_deg)
        self.north += self.speed * math.cos(psi) * dt
        self.east += self.speed * math.sin(psi) * dt


class DroneManager:
    """The drones in the play area: at most ``max_drones``, replaced after a kill."""

    def __init__(self, max_drones: int = MAX_DRONES, seed: int = 17):
        self.max_drones = max_drones
        self.rng = random.Random(seed)
        self.drones: list[Drone] = []
        self.next_id = 1
        self.respawn_in = 0.0
        self._own = (0.0, 0.0, 1000.0, 0.0)

    def reset(self, north: float, east: float, alt: float, heading_deg: float) -> None:
        self.drones.clear()
        self.next_id = 1
        self.respawn_in = 0.0
        self._own = (north, east, alt, heading_deg)
        for k in range(self.max_drones):
            self.spawn(north, east, alt, heading_deg, slot=k)

    def spawn(self, north: float, east: float, alt: float, heading_deg: float,
              slot: int | None = None) -> Drone | None:
        if sum(d.alive for d in self.drones) >= self.max_drones:
            return None
        slot = sum(d.alive for d in self.drones) if slot is None else slot
        # In front of the aircraft, fanned out: the first is nearly on the boresight.
        bearing = heading_deg + (0.0, -32.0, 32.0, -58.0, 58.0)[slot % 5]
        if slot > 0:
            bearing += self.rng.uniform(-6.0, 6.0)
        distance = 1500.0 + 500.0 * (slot % 3) + self.rng.uniform(-100.0, 150.0)
        psi = math.radians(bearing)
        n = north + distance * math.cos(psi)
        e = east + distance * math.sin(psi)
        h = max(alt + (self.rng.uniform(-120.0, 120.0) if slot > 0 else 0.0), 350.0)
        h = max(h, float(terrain.height(n, e)) + 350.0)
        # The target flies roughly away from the launch point, so a chase has time to develop.
        drone = Drone(
            id=self.next_id, north=n, east=e, alt=h,
            heading_deg=bearing + (self.rng.uniform(-12.0, 12.0) if slot > 0 else 0.0),
            speed=85.0 + self.rng.uniform(0.0, 30.0),
            turn_rate=self.rng.choice((-1.4, 1.4)),
            turn_at=6.0 + self.rng.uniform(0.0, 5.0),
        )
        self.next_id += 1
        self.drones.append(drone)
        return drone

    def step(self, dt: float, north: float, east: float, alt: float, heading_deg: float) -> None:
        self._own = (north, east, alt, heading_deg)
        for d in self.drones:
            d.step(dt)
        if sum(d.alive for d in self.drones) < self.max_drones:
            self.respawn_in -= dt
            if self.respawn_in <= 0.0:
                self.spawn(north, east, alt, heading_deg)
                self.respawn_in = SPAWN_DELAY

    def kill(self, drone_id: int) -> Drone | None:
        for d in self.drones:
            if d.id == drone_id and d.alive:
                d.alive = False
                self.respawn_in = SPAWN_DELAY
                return d
        return None

    def alive(self) -> list[Drone]:
        return [d for d in self.drones if d.alive]

    def by_id(self, drone_id: int | None) -> Drone | None:
        if drone_id is None:
            return None
        return next((d for d in self.drones if d.id == drone_id), None)

    def contacts(self) -> list[dict]:
        own_n, own_e, own_h, _ = self._own
        out = []
        for d in self.drones:
            if not d.alive:
                continue
            out.append({"id": d.id, "north": d.north, "east": d.east, "alt": d.alt,
                        "range": math.dist((own_n, own_e, own_h), (d.north, d.east, d.alt))})
        return out


@dataclass
class LockState:
    selected_id: int | None = None
    locked: bool = False
    progress: float = 0.0        # 0..1, the one-second track build-up
    angle_deg: float = 180.0     # off-boresight of the selected target
    range_m: float = 0.0
    in_fov: bool = False
    reason: str = "NO TARGET"


class LockOn:
    """The pilot's seeker cue: select a drone, keep it in the 45 deg half-angle, wait 1 s."""

    def __init__(self, fov_half_deg: float = SEEKER_HALF_DEG, max_range_m: float = SEEKER_RANGE_M,
                 track_s: float = SEEKER_TRACK_S):
        self.fov_half = fov_half_deg
        self.max_range = max_range_m
        self.track_s = track_s
        self.selected_id: int | None = None
        self.progress = 0.0
        self.locked = False
        self.angle_deg = 180.0
        self.range_m = 0.0
        self.in_fov = False
        self.reason = "NO TARGET"

    def reset(self) -> None:
        self.selected_id = None
        self.progress = 0.0
        self.locked = False
        self.angle_deg = 180.0
        self.range_m = 0.0
        self.in_fov = False
        self.reason = "NO TARGET"

    def _geometry(self, drone: Drone, own: tuple[float, float, float], nose: tuple[float, float, float]):
        dn, de, dh = drone.north - own[0], drone.east - own[1], drone.alt - own[2]
        rng = math.sqrt(dn * dn + de * de + dh * dh)
        if rng < 1.0:
            return 180.0, 0.0
        # NED line of sight (down is -altitude) and the nose vector, both unit length.
        los = (dn / rng, de / rng, -dh / rng)
        dot = max(-1.0, min(1.0, los[0] * nose[0] + los[1] * nose[1] + los[2] * nose[2]))
        return math.degrees(math.acos(dot)), rng

    def update(self, dt: float, own: tuple[float, float, float], nose: tuple[float, float, float],
               drones: DroneManager) -> LockState:
        alive = drones.alive()
        sel = drones.by_id(self.selected_id)
        if sel is None or not sel.alive:
            self.selected_id = None
            self.progress = 0.0
        if self.selected_id is None and alive:
            best = None
            for d in alive:
                ang, rng = self._geometry(d, own, nose)
                if rng <= self.max_range and ang <= self.fov_half and (best is None or ang < best[0]):
                    best = (ang, d)
            if best is not None:
                self.selected_id = best[1].id
                self.progress = 0.0
        if self.selected_id is None:
            self.locked = False
            self.reason = "NO TARGET"
            return self.state()

        sel = drones.by_id(self.selected_id)
        assert sel is not None
        self.angle_deg, self.range_m = self._geometry(sel, own, nose)
        self.in_fov = self.angle_deg <= self.fov_half and self.range_m <= self.max_range
        if self.in_fov:
            self.progress = min(1.0, self.progress + dt / self.track_s)
            self.reason = "LOCK" if self.progress >= 1.0 else "SEEKER"
        else:
            # Leaving the seeker field breaks the track; the target stays selected for the cue.
            self.progress = max(0.0, self.progress - 3.0 * dt)
            self.reason = "OUT OF FOV" if self.range_m <= self.max_range else "TOO FAR"
        self.locked = self.progress >= 1.0
        return self.state()

    def state(self) -> LockState:
        return LockState(self.selected_id, self.locked, self.progress, self.angle_deg, self.range_m,
                         self.in_fov, self.reason)

    def cycle(self, drones: DroneManager) -> None:
        """The cue switch: select the next live drone (the radar/HMCS designation)."""
        alive = sorted(drones.alive(), key=lambda d: d.id)
        if not alive:
            self.reset()
            return
        ids = [d.id for d in alive]
        if self.selected_id in ids:
            self.selected_id = ids[(ids.index(self.selected_id) + 1) % len(ids)]
        else:
            self.selected_id = ids[0]
        self.progress = 0.0
        self.locked = False

    def consume(self) -> None:
        """After a launch the next missile has to build its own track."""
        self.progress = 0.0
        self.locked = False
