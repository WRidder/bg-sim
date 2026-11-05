"""The simulation core, without rendering: fixed-step pacing, the game state, wind, the ring course.

The FMU advances in fixed 5 ms communication steps. The render loop calls ``Simulation.advance``
once per frame with the real (or, when recording, the fixed) frame time; the pacer turns that
into a whole number of steps and keeps the remainder for the next frame. When a frame comes too
late (a window drag, a slow machine) at most ``max_steps`` are run and the rest of the backlog is
dropped, so the simulation slows down instead of spiralling: ``behind`` counts those frames.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import terrain
from .fmu import INPUTS, FlightModel, Settings, Start

IDX = {n: k for k, n in enumerate(INPUTS)}


@dataclass
class Pacer:
    """Fixed-step pacing: whole steps per frame, remainder carried, bounded catch-up."""

    step: float
    max_steps: int = 20           # 100 ms of simulation per frame at most
    acc: float = 0.0
    behind: int = 0               # frames whose backlog was dropped
    dropped: float = 0.0          # s of real time dropped in total

    def steps_for(self, dt: float) -> int:
        self.acc += max(0.0, dt)
        n = int((self.acc + 1e-12) // self.step)
        if n > self.max_steps:
            self.behind += 1
            self.dropped += (n - self.max_steps) * self.step
            self.acc -= n * self.step
            n = self.max_steps
        else:
            self.acc -= n * self.step
        return n

    def reset(self) -> None:
        self.acc = 0.0


@dataclass
class Turbulence:
    """Wind: a steady part plus first-order filtered noise (a crude stand-in for a Dryden filter)."""

    steady_ned: tuple[float, float, float] = (0.0, 0.0, 0.0)
    intensity: float = 0.0        # m/s rms of the gusts; 0: off
    length: float = 300.0         # m, the gust length scale (time constant = length / speed)
    seed: int = 1
    state: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)

    def sample(self, dt: float, speed: float) -> np.ndarray:
        if self.intensity > 0.0:
            tau = self.length / max(speed, 30.0)
            a = math.exp(-dt / tau)
            self.state = a * self.state + math.sqrt(1.0 - a * a) * self.intensity * self.rng.standard_normal(3)
        return np.asarray(self.steady_ned) + self.state


@dataclass
class Ring:
    north: float
    east: float
    alt: float
    heading_deg: float            # the direction to fly through it
    radius: float = 45.0
    passed: bool = False          # flown through or past
    hit: bool = False             # through, inside the radius


def ring_course(start_north: float, start_east: float, alt: float, heading_deg: float = 0.0) -> list[Ring]:
    """A course of gates ahead of the start: straight, a right turn, a climb, a left turn, a dive."""
    legs = [(0.0, 0.0), (0.0, 0.0), (35.0, 0.0), (35.0, 150.0), (35.0, 250.0), (-50.0, 250.0),
            (-50.0, 0.0), (-50.0, -250.0), (0.0, -150.0), (0.0, 0.0)]
    rings = []
    n, e, h, psi = start_north, start_east, alt, math.radians(heading_deg)
    for turn, climb in legs:
        psi += math.radians(turn)
        dist = 2200.0
        n += dist * math.cos(psi)
        e += dist * math.sin(psi)
        h = max(400.0, h + climb)
        rings.append(Ring(n, e, h, math.degrees(psi)))
    return rings


class Simulation:
    """The FMU plus the game state. ``inputs`` holds the pilot inputs (stick, pedals, throttle)."""

    def __init__(self, fmu_path, starts: list[Start], settings: Settings | None = None):
        self.model = FlightModel(fmu_path)
        self.starts = starts
        self.settings = settings or Settings()
        self.pacer = Pacer(self.model.step_size)
        self.wind = Turbulence()
        self.paused = False
        self.crashed = False
        self.rings: list[Ring] = []
        self.ring_time: float | None = None
        self.ring_done: float | None = None
        self.start_index = 0
        self.u = np.zeros(len(INPUTS))
        self.steps = 0
        self.crash_reason = ""
        self.reset(0)

    # ---- state
    def reset(self, index: int | None = None) -> None:
        if index is not None:
            self.start_index = index % len(self.starts)
        start = self.starts[self.start_index]
        self.model.reset(start, self.settings)
        self.y_prev = self.model.y.copy()
        self.pacer.reset()
        self.crashed = False
        self.crash_reason = ""
        self.u[:] = 0.0
        self.u[IDX["throttle"]] = start.thtl0
        self.u[IDX["gear_cmd"]] = start.gear0
        self.prev = self.position()
        if self.rings:
            self.start_rings()

    @property
    def start(self) -> Start:
        return self.starts[self.start_index]

    def position(self) -> np.ndarray:
        m = self.model
        return np.array([m["north_m"], m["east_m"], m["alt_m"]])

    def toggle_rings(self) -> None:
        if self.rings:
            self.rings, self.ring_time, self.ring_done = [], None, None
        else:
            self.start_rings()

    def start_rings(self) -> None:
        n, e, h = self.position()
        self.rings = ring_course(n, e, h, self.model["psi_deg"])
        self.ring_time, self.ring_done = 0.0, None

    # ---- stepping
    def set_controls(self, stick_pitch: float, stick_roll: float, pedals: float, throttle: float) -> None:
        self.u[IDX["stick_pitch"]] = min(1.0, max(-1.0, stick_pitch))
        self.u[IDX["stick_roll"]] = min(1.0, max(-1.0, stick_roll))
        self.u[IDX["pedals"]] = min(1.0, max(-1.0, pedals))
        self.u[IDX["throttle"]] = min(1.0, max(0.0, throttle))

    def set_brakes(self, left: float, right: float | None = None) -> None:
        self.u[IDX["brake_l"]] = min(1.0, max(0.0, left))
        self.u[IDX["brake_r"]] = min(1.0, max(0.0, left if right is None else right))

    def toggle_gear(self) -> None:
        """The gear handle. On the ground the FMU's interlock holds the gear down."""
        self.u[IDX["gear_cmd"]] = 0.0 if self.u[IDX["gear_cmd"]] > 0.5 else 1.0

    def advance(self, dt: float, control=None) -> int:
        """Advance by the frame time ``dt`` (s of real time): the paced number of FMU steps.
        ``control(t)``, when given, sets the controls before each step (scripted inputs)."""
        if self.paused or self.crashed:
            self.pacer.reset()
            return 0
        n = self.pacer.steps_for(dt)
        for _ in range(n):
            if control is not None:
                control(self.model.time)
            self.step_once()
            if self.crashed:
                break
        return n

    def step_once(self) -> None:
        m = self.model
        w = self.wind.sample(m.step_size, m["tas_mps"])
        self.u[IDX["wind_n"]], self.u[IDX["wind_e"]], self.u[IDX["wind_d"]] = w
        self.y_prev[:] = m.y
        m.step(self.u)
        self.steps += 1
        pos = self.position()
        if not np.all(np.isfinite(m.y)):
            self.crashed, self.crash_reason = True, "the FMU returned a non-finite state"
        elif m["ground_contact"] > 0.5 or pos[2] <= float(terrain.height(pos[0], pos[1])):
            self.crashed, self.crash_reason = True, "ground contact"
        self._rings(self.prev, pos)
        self.prev = pos

    def _rings(self, a: np.ndarray, b: np.ndarray) -> None:
        if not self.rings or self.ring_done is not None:
            return
        self.ring_time += self.model.step_size
        ring = next((r for r in self.rings if not r.passed), None)
        if ring is None:
            return
        c = np.array([ring.north, ring.east, ring.alt])
        nrm = np.array([math.cos(math.radians(ring.heading_deg)), math.sin(math.radians(ring.heading_deg)), 0.0])
        da, db = float(np.dot(a - c, nrm)), float(np.dot(b - c, nrm))
        if da < 0.0 <= db:
            p = a + (b - a) * (-da / (db - da))
            miss = float(np.linalg.norm(p - c))
            if miss <= 800.0:            # a crossing of the gate plane near the gate (not far off the course)
                ring.passed, ring.hit = True, miss <= ring.radius
                if all(r.passed for r in self.rings):
                    self.ring_done = self.ring_time

    def agl(self) -> float:
        n, e, h = self.position()
        return h - float(terrain.height(n, e))

    def alpha(self) -> float:
        """Where the drawn state lies between the last two steps (0: the previous, 1: the last)."""
        return min(1.0, self.pacer.acc / self.pacer.step) if not (self.paused or self.crashed) else 1.0

    def next_ring(self) -> Ring | None:
        return next((r for r in self.rings if not r.passed), None)

    def close(self) -> None:
        self.model.close()
