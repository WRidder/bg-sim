"""The simulation core, without rendering: fixed-step pacing, the pilot's levers, wind, the
autopilot switches, crash and touchdown detection.

The FMU advances in fixed 5 ms communication steps. The render loop calls ``Simulation.advance``
once per frame with the real (or, when recording, the fixed) frame time; the pacer turns that
into a whole number of steps and keeps the remainder for the next frame. When a frame comes too
late (a window drag, a slow machine) at most ``max_steps`` are run and the rest of the backlog is
dropped, so the simulation slows down instead of spiralling: ``behind`` counts those frames.

The world is the model's: x north, y west, z up, the runway surface at z = 0 everywhere (the FMU's
gear meets a flat ground). Runway 36 runs north from x = RUNWAY_X0 along y = 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .fmu import INPUTS, FlightModel, Start, body_to_world

IDX = {n: k for k, n in enumerate(INPUTS)}
G0 = 9.80665
MASS = 1088.62                 # kg, the model's gross weight (2400 lb)
RUNWAY_X0, RUNWAY_LENGTH, RUNWAY_WIDTH = -30.0, 1200.0, 30.0
H_CG0 = 1.2546                 # m, the CG above the runway at rest
# points of the airframe that must not touch the ground (body frame x fwd, y left, z up, from
# the CG; JSBSim c172p's contact points): wing tips, tail skid, the lowest propeller tip
STRIKE = {
    "left wing tip": (0.061, 5.456, 0.607), "right wing tip": (0.061, -5.456, 0.607),
    "tail": (-3.617, 0.0, -0.699), "propeller": (2.116, 0.0, -0.226 - 0.9525),
}
FN_CRASH = 3.5 * MASS * G0     # N on one wheel: the gear collapses
FLAP_DETENTS = (0, 10, 20, 30)


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
    """Wind: a steady part plus first-order filtered noise (a crude stand-in for a Dryden filter).
    ``steady`` is (north, east, down), the direction the air moves to."""

    steady: tuple[float, float, float] = (0.0, 0.0, 0.0)
    intensity: float = 0.0        # m/s rms of the gusts; 0: off
    length: float = 150.0         # m, the gust length scale (time constant = length / speed)
    seed: int = 1
    state: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)

    def sample(self, dt: float, speed: float, agl: float) -> np.ndarray:
        if self.intensity > 0.0:
            tau = self.length / max(speed, 10.0)
            a = math.exp(-dt / tau)
            self.state = a * self.state + math.sqrt(1.0 - a * a) * self.intensity * self.rng.standard_normal(3)
            self.state[2] *= 1.0 if agl > 30.0 else max(0.0, agl / 30.0)   # no vertical gusts at the ground
        # the steady wind falls off towards the ground (a 1/7 power law below 100 m)
        k = min(1.0, max(0.0, agl / 100.0)) ** (1.0 / 7.0) if agl > 0.0 else 0.0
        return k * np.asarray(self.steady) + self.state


@dataclass
class Touchdown:
    t: float
    vs_fpm: float
    kias: float
    distance_m: float             # from the threshold of runway 36
    offset_m: float               # from the centre line, positive right (east)
    pitch_deg: float
    rating: str


def rate_touchdown(vs_fpm: float) -> str:
    sink = -vs_fpm
    if sink < 200.0:
        return "smooth"
    if sink < 450.0:
        return "firm"
    if sink < 800.0:
        return "hard"
    return "very hard"


def wrap180(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


class Simulation:
    """The FMU plus the game state. ``levers`` holds the levers the pilot moves step by step
    (flap detent, trim) and ``u`` all FMU inputs."""

    def __init__(self, fmu_path, starts: list[Start]):
        self.model = FlightModel(fmu_path)
        self.starts = starts
        self.pacer = Pacer(self.model.step_size)
        self.wind = Turbulence()
        self.paused = False
        self.start_index = 0
        self.u = np.zeros(len(INPUTS))
        self.steps = 0
        self.reset(0)

    # ---- state
    def reset(self, index: int | None = None) -> None:
        if index is not None:
            self.start_index = index % len(self.starts)
        start = self.starts[self.start_index]
        self.model.reset(start)
        self.u[:] = self.model.u
        self.y_prev = self.model.y.copy()
        self.pacer.reset()
        self.crashed = False
        self.crash_reason = ""
        self.touchdowns: list[Touchdown] = []
        self.air_time = 0.0 if not start.airborne else 10.0
        self.ground_time = 0.0
        self.max_fn = 0.0
        self.vs_hist = [0.0] * 20            # the last 0.1 s of vertical speed (the value at touchdown)

    @property
    def start(self) -> Start:
        return self.starts[self.start_index]

    def position(self) -> np.ndarray:
        m = self.model
        return np.array([m["north_m"], m["east_m"], m["alt_m"]])

    # ---- the pilot
    def set_controls(self, **kw: float) -> None:
        """Yoke, pedals (-1..1), throttle, mixture, brakes (0..1) by their input names."""
        for k, v in kw.items():
            lo = -1.0 if k in ("yoke_pitch", "yoke_roll", "pedals", "trim") else 0.0
            self.u[IDX[k]] = min(1.0, max(lo, float(v)))

    def flaps(self, step: int) -> None:
        self.u[IDX["flaps"]] = float(min(3, max(0, round(self.u[IDX["flaps"]]) + step)))

    def trim(self, delta: float) -> None:
        self.u[IDX["trim"]] = min(1.0, max(-1.0, self.u[IDX["trim"]] + delta))

    def ap_roll_cycle(self) -> None:
        """Autopilot roll: off -> wing leveller -> heading hold (the heading bug set to the
        heading now) -> off."""
        mode = (round(self.u[IDX["ap_roll_mode"]]) + 1) % 3
        self.u[IDX["ap_roll_mode"]] = mode
        if mode == 2:
            self.u[IDX["ap_hdg_deg"]] = round(self.model["psi_deg"])

    def ap_alt_toggle(self) -> None:
        """Altitude hold on (at the altitude now) or off."""
        on = round(self.u[IDX["ap_alt_mode"]]) == 0
        self.u[IDX["ap_alt_mode"]] = 1.0 if on else 0.0
        if on:
            self.u[IDX["ap_alt_m"]] = self.model["alt_m"]

    def heading_bug(self, delta: float) -> None:
        self.u[IDX["ap_hdg_deg"]] = (self.u[IDX["ap_hdg_deg"]] + delta) % 360.0

    def ap(self, roll_mode: int | None = None, alt_mode: int | None = None, hdg: float | None = None,
           alt: float | None = None) -> None:
        if roll_mode is not None:
            self.u[IDX["ap_roll_mode"]] = roll_mode
        if alt_mode is not None:
            self.u[IDX["ap_alt_mode"]] = alt_mode
        if hdg is not None:
            self.u[IDX["ap_hdg_deg"]] = hdg % 360.0
        if alt is not None:
            self.u[IDX["ap_alt_m"]] = alt

    # ---- stepping
    def advance(self, dt: float, control=None) -> int:
        """Advance by the frame time ``dt`` (s of real time): the paced number of FMU steps.
        ``control(sim)``, when given, sets the controls before each step (a scripted pilot)."""
        if self.paused or self.crashed:
            self.pacer.reset()
            return 0
        n = self.pacer.steps_for(dt)
        for _ in range(n):
            if control is not None:
                control(self)
            self.step_once()
            if self.crashed:
                break
        return n

    def step_once(self) -> None:
        m = self.model
        w = self.wind.sample(m.step_size, m["ktas"] * 0.514444, self.agl())
        self.u[IDX["wind_n"]], self.u[IDX["wind_e"]], self.u[IDX["wind_d"]] = w
        self.y_prev[:] = m.y
        m.step(self.u)
        self.steps += 1
        self._watch()

    def _watch(self) -> None:
        m = self.model
        dt = m.step_size
        if not np.all(np.isfinite(m.y)):
            self.crashed, self.crash_reason = True, "the FMU returned a non-finite state"
            return
        strike = self.strike()
        if strike:
            self.crashed, self.crash_reason = True, f"{strike} strike"
            return
        fn = max(m["fn_nose"], m["fn_left"], m["fn_right"])
        self.max_fn = max(self.max_fn, fn)
        if fn > FN_CRASH:
            self.crashed, self.crash_reason = True, "the landing gear collapsed"
            return
        self.vs_hist = self.vs_hist[1:] + [m["vs_fpm"]]
        if m["on_ground"] > 0.5:
            if self.air_time > 2.0:           # a touchdown after a flight
                n, e, _ = self.position()
                vs = min(self.vs_hist)
                self.touchdowns.append(Touchdown(m.time, vs, m["kias"], n - RUNWAY_X0, e, m["theta_deg"],
                                                 rate_touchdown(vs)))
            self.air_time = 0.0
            self.ground_time += dt
        else:
            self.air_time += dt
            if self.air_time > 0.5:
                self.ground_time = 0.0

    def strike(self) -> str:
        """The airframe point below the ground, if any."""
        m = self.model
        R = body_to_world(m["q_w"], m["q_x"], m["q_y"], m["q_z"])
        z = m["alt_m"]
        if z > 8.0:
            return ""
        for name, r in STRIKE.items():
            if z + float(R[2] @ np.asarray(r)) < 0.0:
                return name
        return ""

    def agl(self) -> float:
        return self.model["alt_m"] - H_CG0

    def on_runway(self) -> bool:
        n, e, _ = self.position()
        return RUNWAY_X0 <= n <= RUNWAY_X0 + RUNWAY_LENGTH and abs(e) <= RUNWAY_WIDTH / 2

    def alpha(self) -> float:
        """Where the drawn state lies between the last two steps (0: the previous, 1: the last)."""
        return min(1.0, self.pacer.acc / self.pacer.step) if not (self.paused or self.crashed) else 1.0

    def close(self) -> None:
        self.model.close()
