"""Scripted drivers for the headless smoke test and the videos: deterministic functions of the state.

The driver follows a closed path (the race track's centre line, or a loop over the hills) with a
pure-pursuit steering law and holds a target speed that the curvature ahead allows
(v = sqrt(ay_max / curvature), at most v_max), with the accelerator and brake on the speed error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def hills_loop(n: int = 720) -> np.ndarray:
    """The buggy's demo loop over the hills: an ellipse of 170 m by 120 m, counter-clockwise,
    starting at (0, -120) heading +x."""
    th = np.linspace(-math.pi / 2, 1.5 * math.pi, n, endpoint=False)
    return np.column_stack([170.0 * np.cos(th), 120.0 * np.sin(th)])


class Path:
    def __init__(self, pts: np.ndarray):
        self.p = np.asarray(pts, float)
        d = np.roll(self.p, -1, axis=0) - self.p
        self.seg = np.linalg.norm(d, axis=1)
        self.s = np.concatenate([[0.0], np.cumsum(self.seg)[:-1]])
        self.length = float(np.sum(self.seg))
        t = d / self.seg[:, None]
        tp = np.roll(t, 1, axis=0)
        cross = tp[:, 0] * t[:, 1] - tp[:, 1] * t[:, 0]
        self.curv = cross / np.maximum(0.5 * (self.seg + np.roll(self.seg, 1)), 1e-9)
        k = np.ones(9) / 9.0
        self.curv = np.convolve(np.concatenate([self.curv[-4:], self.curv, self.curv[:4]]), k, mode="valid")

    def nearest(self, x: float, y: float) -> int:
        dp = self.p - np.array([x, y])
        return int(np.argmin(np.einsum("ij,ij->i", dp, dp)))

    def ahead(self, k: int, dist: float) -> int:
        n = len(self.p)
        s = 0.0
        j = k
        while s < dist:
            s += self.seg[j]
            j = (j + 1) % n
        return j


@dataclass
class Driver:
    """Pure pursuit plus a speed profile. ``offset`` moves the line to the left (m)."""

    path: Path
    v_max: float
    ay_max: float
    lookahead: tuple[float, float] = (8.0, 0.45)    # m + s * speed
    preview: float = 60.0                            # m of curvature looked at for the speed
    wheelbase: float = 2.8
    steer_max: float = math.radians(20.0)
    k_v: float = 0.35                                # pedal per m/s of speed error

    def controls(self, x: float, y: float, yaw: float, speed: float, ay_g: float = 0.0,
                 beta: float = 0.0) -> tuple[float, float, float]:
        """Steering, accelerator and brake for the state; ``ay_g`` (lateral acceleration, g) and
        ``beta`` (body slip, rad) take the accelerator back in a corner and when the rear slides
        (a driver's feel for the friction circle: a 260 kW rear drive oversteers on power)."""
        steer, throttle, brake = self._controls(x, y, yaw, speed)
        ay_lim = self.ay_max / 9.81 + 0.15
        throttle *= min(1.0, max(0.1, (ay_lim - abs(ay_g)) / 0.4))
        if speed > 4.0:      # the body slip angle means nothing near standstill
            throttle *= min(1.0, max(0.0, 1.0 - (abs(beta) - 0.03) / 0.04))
        return steer, throttle, brake

    def _controls(self, x: float, y: float, yaw: float, speed: float) -> tuple[float, float, float]:
        k = self.path.nearest(x, y)
        la = self.lookahead[0] + self.lookahead[1] * speed
        j = self.path.ahead(k, la)
        tx, ty = self.path.p[j]
        dx, dy = tx - x, ty - y
        c, s = math.cos(yaw), math.sin(yaw)
        lx, ly = c * dx + s * dy, -s * dx + c * dy
        delta = math.atan2(2.0 * self.wheelbase * ly, lx * lx + ly * ly)
        steer = max(-1.0, min(1.0, -delta / self.steer_max))     # + = right: the road wheels turn right
        jj = self.path.ahead(k, self.preview)
        idx = np.arange(k, jj if jj > k else jj + len(self.path.p)) % len(self.path.p)
        cmax = float(np.max(np.abs(self.path.curv[idx]))) if len(idx) else 0.0
        v_ref = min(self.v_max, math.sqrt(self.ay_max / max(cmax, 1e-6)))
        e = v_ref - speed
        throttle = max(0.0, min(1.0, self.k_v * e + 0.15)) if e > -0.5 else 0.0
        brake = max(0.0, min(1.0, -self.k_v * 0.5 * e)) if e < -1.0 else 0.0
        return steer, throttle, brake


@dataclass
class Script:
    name: str
    vehicle: str
    start: int
    duration: float
    v_max: float
    ay_max: float
    views: list[tuple[float, str]] = field(default_factory=lambda: [(0.0, "chase")])
    captions: list[tuple[float, float, str]] = field(default_factory=list)
    hold: float = 1.0                    # s at rest before the driver starts

    def view(self, t: float) -> str:
        v = self.views[0][1]
        for t0, name in self.views:
            if t >= t0:
                v = name
        return v

    def caption(self, t: float) -> str:
        return next((c for t0, t1, c in self.captions if t0 <= t < t1), "")


SCRIPTS = {
    "smoke": Script("smoke", "racecar", 0, 10.0, 40.0, 12.0, views=[(0.0, "chase"), (6.0, "cockpit")]),
    "smoke-buggy": Script("smoke-buggy", "buggy", 0, 10.0, 14.0, 4.0, views=[(0.0, "chase"), (6.0, "cockpit")]),
    "demo": Script("demo", "racecar", 0, 75.0, 70.0, 13.0,
                   views=[(0.0, "chase"), (22.0, "cockpit"), (40.0, "chase"), (55.0, "tv"), (66.0, "chase")],
                   captions=[(0.0, 5.0, "racecar-sim FMU: electric race car, 260 kW rear motor, traction control"),
                             (5.0, 14.0, "launch at the torque limit, then the power limit"),
                             (14.0, 22.0, "braking: regeneration first, the friction brakes for the rest"),
                             (22.0, 40.0, "cockpit view: speed, motor, battery charge on the HUD"),
                             (55.0, 66.0, "track-side camera")]),
    "demo-buggy": Script("demo-buggy", "buggy", 0, 60.0, 16.0, 4.0,
                         views=[(0.0, "chase"), (25.0, "cockpit"), (40.0, "tv"), (50.0, "chase")],
                         captions=[(0.0, 6.0, "buggy-sim FMU: four-wheel drive, a 60 kW motor per axle"),
                                   (6.0, 25.0, "over the rolling hills: long-travel suspension, terrain contact"),
                                   (25.0, 40.0, "cockpit view"),
                                   (40.0, 50.0, "a camera on the hillside")]),
}
