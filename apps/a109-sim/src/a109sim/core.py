"""The simulation core, without rendering: fixed-step pacing, the pilot's controls, wind, the SCAS
switch, crash and touchdown detection.

The FMU advances in fixed 5 ms communication steps. The render loop calls ``Simulation.advance``
once per frame with the real (or, when recording, the fixed) frame time; the pacer turns that
into a whole number of steps and keeps the remainder for the next frame. When a frame comes too
late (a window drag, a slow machine) at most ``max_steps`` are run and the rest of the backlog is
dropped, so the simulation slows down instead of spiralling: ``behind`` counts those frames.

The world is the model's: x north, y west, z up, the ground at z = 0 everywhere (the FMU's gear
meets a flat ground, examples/a109/design/build_model.py: GEAR). The helipad "H" is at the origin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .fmu import INPUTS, FlightModel, Start, euler_to_world, ground_velocity

IDX = {n: k for k, n in enumerate(INPUTS)}
G0 = 9.80665
MASS = 2449.856                # kg, the model's gross weight (5401 lb)
WEIGHT = MASS * G0
PAD_RADIUS = 12.0              # m: the touchdown and lift-off area (TLOF) around the "H"
GEAR_Z = 1.32                  # m: the wheels' contact points below the CG
WHEELS = {"nose": (1.9, 0.0, -1.32), "left": (-0.8, 0.95, -1.32), "right": (-0.8, -0.95, -1.32)}
HUB = (0.00762, 0.0, 1.51638)  # m: the main-rotor hub from the CG (body frame, examples/a109: SI pos HUB)
SHAFT_TILT = 0.10995574        # rad: the shaft's forward tilt (the report's IS, 6.3 deg)
R_MR = 5.4864                  # m: main-rotor radius
TR_HUB = (-6.56082, 0.25, 0.8001)
R_TR = 0.94488                 # m: tail-rotor radius
# points of the airframe that must not touch the ground (body frame x fwd, y left, z up, from
# the CG; the scene's solids): the tail-rotor tip, the ventral fin, the nose and the cabin belly
STRIKE = {"tail rotor": (TR_HUB[0], TR_HUB[1], TR_HUB[2] - R_TR), "tail": (-6.25, 0.0, -0.30),
          "nose": (2.2, 0.0, -0.75), "belly": (0.35, 0.0, -0.80)}
FN_CRASH = 2.5 * WEIGHT        # N on one wheel: the gear collapses
VS_CRASH = 3.0                 # m/s of sink at touchdown: the gear collapses
NR_STALL = 80.0                # %: the rotor stalls below this (an unrecoverable decay)
ROLLOVER = 25.0                # deg of bank with weight on the wheels: dynamic rollover
P_LIMIT = 740.0                # hp: the take-off power (the governor's engine-torque limit)


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
    length: float = 60.0          # m, the gust length scale (time constant = length / speed)
    seed: int = 1
    state: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)

    def sample(self, dt: float, speed: float, agl: float) -> np.ndarray:
        if self.intensity > 0.0:
            tau = self.length / max(speed, 5.0)
            a = math.exp(-dt / tau)
            self.state = a * self.state + math.sqrt(1.0 - a * a) * self.intensity * self.rng.standard_normal(3)
            self.state[2] *= 1.0 if agl > 20.0 else max(0.0, agl / 20.0)   # no vertical gusts at the ground
        # the steady wind falls off towards the ground (a 1/7 power law below 100 m)
        k = min(1.0, max(0.0, agl / 100.0)) ** (1.0 / 7.0) if agl > 0.0 else 0.0
        return k * np.asarray(self.steady) + self.state


@dataclass
class Touchdown:
    t: float
    vs_mps: float                 # climb rate at the touchdown (negative: sinking)
    gs_mps: float                 # ground speed at the touchdown
    distance_m: float             # from the centre of the "H"
    on_pad: bool
    bank_deg: float
    rating: str


def rate_touchdown(vs_mps: float) -> str:
    sink = -vs_mps
    if sink < 0.5:
        return "smooth"
    if sink < 1.0:
        return "firm"
    if sink < 2.0:
        return "hard"
    return "very hard"


def wrap180(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


class Simulation:
    """The FMU plus the game state: ``u`` holds all FMU inputs (the pilot's sticks, the SCAS
    switch, the wind)."""

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
        self.ground_time = 0.0 if start.airborne else 10.0
        self.max_fn = 0.0
        self.vs_hist = [0.0] * 20            # the last 0.1 s of climb rate (the value at touchdown)

    @property
    def start(self) -> Start:
        return self.starts[self.start_index]

    def position(self) -> np.ndarray:
        m = self.model
        return np.array([m["north_m"], m["east_m"], m["alt_m"]])

    # ---- the pilot
    def set_controls(self, **kw: float) -> None:
        """Collective (0..1), cyclic and pedals (-1..1) by their input names."""
        for k, v in kw.items():
            lo = 0.0 if k == "collective" else -1.0
            self.u[IDX[k]] = min(1.0, max(lo, float(v)))

    @property
    def scas_on(self) -> bool:
        return self.u[IDX["scas"]] > 0.5

    def set_scas(self, on: bool) -> None:
        self.u[IDX["scas"]] = 1.0 if on else 0.0

    def toggle_scas(self) -> None:
        self.set_scas(not self.scas_on)

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
        w = self.wind.sample(m.step_size, m["tas_mps"], self.agl())
        self.u[IDX["wind_n"]], self.u[IDX["wind_e"]], self.u[IDX["wind_d"]] = w
        self.y_prev[:] = m.y
        m.step(self.u)
        self.steps += 1
        self._watch()

    @property
    def gear_load(self) -> float:
        m = self.model
        return m["fn_nose"] + m["fn_left"] + m["fn_right"]

    @property
    def on_ground(self) -> bool:
        return self.gear_load > 0.02 * WEIGHT

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
        if m["rotor_pct"] < NR_STALL:
            self.crashed, self.crash_reason = True, f"the rotor stalled ({m['rotor_pct']:.0f} % NR)"
            return
        self.vs_hist = self.vs_hist[1:] + [m["vs_mps"]]
        if self.on_ground:
            if abs(m["phi_deg"]) > ROLLOVER:
                self.crashed, self.crash_reason = True, "dynamic rollover"
                return
            if self.air_time > 2.0:           # a touchdown after a flight
                vs = min(self.vs_hist)
                n, e, _ = self.position()
                gn, ge, _ = ground_velocity(m)
                d = math.hypot(n, e)
                self.touchdowns.append(Touchdown(m.time, vs, math.hypot(gn, ge), d, d <= PAD_RADIUS, m["phi_deg"],
                                                 rate_touchdown(vs)))
                if -vs > VS_CRASH:
                    self.crashed, self.crash_reason = True, f"the landing gear collapsed ({-vs:.1f} m/s sink)"
                    return
            self.air_time = 0.0
            self.ground_time += dt
        else:
            self.air_time += dt
            if self.air_time > 0.5:
                self.ground_time = 0.0

    def body_to_world(self) -> np.ndarray:
        m = self.model
        return euler_to_world(*np.radians([m["phi_deg"], m["theta_deg"], m["psi_deg"]]))

    def strike(self) -> str:
        """The airframe point (or main-rotor tip) below the ground, if any."""
        m = self.model
        z = m["alt_m"]
        if z > 12.0:
            return ""
        R = self.body_to_world()
        for name, r in STRIKE.items():
            if z + float(R[2] @ np.asarray(r)) < 0.0:
                return name
        # the main-rotor disc: tilted forward with the shaft, eight tip azimuths (flapping ignored)
        c, s = math.cos(SHAFT_TILT), math.sin(SHAFT_TILT)
        for k in range(8):
            a = k * math.pi / 4
            tip = np.array([HUB[0] + R_MR * math.cos(a) * c, HUB[1] + R_MR * math.sin(a), HUB[2] - R_MR * math.cos(a) * s])
            if z + float(R[2] @ tip) < 0.0:
                return "main rotor"
        return ""

    def agl(self) -> float:
        """Height of the lowest wheel above the ground (m)."""
        m = self.model
        R = self.body_to_world()
        return m["alt_m"] + min(float(R[2] @ np.asarray(r)) for r in WHEELS.values())

    def on_pad(self) -> bool:
        n, e, _ = self.position()
        return math.hypot(n, e) <= PAD_RADIUS

    def alpha(self) -> float:
        """Where the drawn state lies between the last two steps (0: the previous, 1: the last)."""
        return min(1.0, self.pacer.acc / self.pacer.step) if not (self.paused or self.crashed) else 1.0

    def close(self) -> None:
        self.model.close()
