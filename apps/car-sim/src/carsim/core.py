"""The simulation core, without rendering: fixed-step pacing, the surfaces under the wheels, laps.

The FMU advances in fixed 5 ms communication steps. The render loop calls ``Simulation.advance``
once per frame with the real (or, when recording, the fixed) frame time; the pacer turns that
into a whole number of steps and keeps the remainder for the next frame. When a frame comes too
late (a window drag, a slow machine) at most ``max_steps`` are run and the rest of the backlog is
dropped, so the simulation slows down instead of spiralling: ``behind`` counts those frames.

Before each step the host sets the friction scale of every wheel from the surface under its
contact point (the FMU's ``<w>_xc``, ``<w>_yc`` of the last step): asphalt, kerb, run-off or
grass on the race track; the buggy's hills are one surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .fmu import CORNERS, INPUTS, Start, VehicleModel, quat_matrix
from .terrain import EXTENT, Hills
from .track import LapTimer, Track

IDX = {n: k for k, n in enumerate(INPUTS)}
HILLS_MU = 1.0


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


class Simulation:
    """The FMU plus the game state. ``u`` holds the FMU inputs (INPUTS order)."""

    def __init__(self, vehicle: str, fmu_path, starts: list[Start], params: dict[str, float] | None = None):
        self.vehicle = vehicle
        self.model = VehicleModel(fmu_path)
        self.starts = starts
        self.params = dict(params or {})
        self.pacer = Pacer(self.model.step_size)
        self.track = Track() if vehicle == "racecar" else None
        self.hills = Hills() if vehicle == "buggy" else None
        self.laps = LapTimer(self.track.length) if self.track else None
        self.paused = False
        self.crashed = False
        self.crash_reason = ""
        self.warning = ""
        self.start_index = 0
        self.u = np.zeros(len(INPUTS))
        self.surfaces = ["asphalt"] * 4
        self.steps = 0
        self.reset(0)

    # ---- state
    def reset(self, index: int | None = None) -> None:
        if index is not None:
            self.start_index = index % len(self.starts)
        self.model.reset(self.start, self.params)
        self.y_prev = self.model.y.copy()
        self.pacer.reset()
        self.crashed = False
        self.crash_reason = ""
        self.warning = ""
        self.u[:] = 0.0
        self.u[IDX["mu_fl"]:] = 1.0
        if self.track:
            self.laps = LapTimer(self.track.length)
            self._lap_update()
        self._surfaces()

    @property
    def start(self) -> Start:
        return self.starts[self.start_index]

    def set_controls(self, steer: float, throttle: float, brake: float, handbrake: float = 0.0) -> None:
        self.u[IDX["steer"]] = min(1.0, max(-1.0, steer))
        self.u[IDX["throttle"]] = min(1.0, max(0.0, throttle))
        self.u[IDX["brake"]] = min(1.0, max(0.0, brake))
        self.u[IDX["handbrake"]] = min(1.0, max(0.0, handbrake))

    @property
    def reverse(self) -> bool:
        return self.u[IDX["reverse"]] > 0.5

    def toggle_reverse(self) -> bool:
        """Forward/reverse, only (nearly) at a standstill; True when it changed."""
        if self.model["speed"] > 1.0:
            return False
        self.u[IDX["reverse"]] = 0.0 if self.reverse else 1.0
        return True

    # ---- stepping
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
        self._surfaces()
        self.y_prev[:] = m.y
        m.step(self.u)
        self.steps += 1
        if not np.all(np.isfinite(m.y)):
            self.crashed, self.crash_reason = True, "the FMU returned a non-finite state"
            return
        if self.track:
            self._lap_update()
        up = quat_matrix(m["chassis_qw"], m["chassis_qx"], m["chassis_qy"], m["chassis_qz"])[2, 2]
        if up < 0.2:
            self.warning = "rolled over: R resets"
        elif self.hills is not None and max(abs(m["chassis_px"]), abs(m["chassis_py"])) > EXTENT - 10.0:
            self.warning = "at the edge of the map: turn back"
        else:
            self.warning = ""

    def _surfaces(self) -> None:
        m = self.model
        for k, c in enumerate(CORNERS):
            x, y = m[f"{c}_xc"], m[f"{c}_yc"]
            if self.track:
                s = self.track.surface_at(x, y)
                self.surfaces[k] = s
                self.u[IDX["mu_" + c]] = self.track.mu[s]
            else:
                self.surfaces[k] = "dirt"
                self.u[IDX["mu_" + c]] = HILLS_MU

    def _lap_update(self) -> None:
        m = self.model
        _, s, _ = self.track.locate(m["chassis_px"], m["chassis_py"])
        self.laps.update(m.time, s)

    def alpha(self) -> float:
        """Where the drawn state lies between the last two steps (0: the previous, 1: the last)."""
        return min(1.0, self.pacer.acc / self.pacer.step) if not (self.paused or self.crashed) else 1.0

    def motor_power_kw(self) -> float:
        return sum(self.model.get(f"motor_{a}_power") for a in self.model.motors) / 1000.0

    def close(self) -> None:
        self.model.close()


def heading_deg(model: VehicleModel) -> float:
    return math.degrees(model["yaw"])
