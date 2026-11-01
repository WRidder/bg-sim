"""The race track: the centre line of ``examples/cars/design/track.json`` (design/track.py), the
surface and its friction scale under any point, and the lap timer.

The whole circuit lies on z = 0, the race car's physics ground (a flat ContactSurface): only the
friction differs, and the host sets it per wheel (the FMU's ``mu_*`` inputs) from the surface
under that wheel's contact point. The surface rules are those of design/track.py.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

TRACK_JSON = Path(__file__).resolve().parents[4] / "examples" / "cars" / "design" / "track.json"


class Track:
    def __init__(self, path: Path = TRACK_JSON):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        self.p = np.column_stack([d["x"], d["y"]])
        self.t = np.column_stack([d["tx"], d["ty"]])
        self.n = np.column_stack([-self.t[:, 1], self.t[:, 0]])     # left normal
        self.curv = np.asarray(d["curv"], float)
        self.length = float(d["length"])
        self.half_width = float(d["half_width"])
        self.kerb = float(d["kerb"])
        self.kerb_curv = float(d["kerb_curv"])
        self.runoff = float(d["runoff"])
        self.mu = dict(d["mu"])
        seg = np.linalg.norm(np.roll(self.p, -1, axis=0) - self.p, axis=1)
        self.s = np.concatenate([[0.0], np.cumsum(seg)[:-1]])

    def locate(self, x: float, y: float) -> tuple[int, float, float]:
        """Nearest centre-line sample, the arc length there (interpolated along the tangent)
        and the signed lateral offset (left +)."""
        dp = self.p - np.array([x, y])
        k = int(np.argmin(np.einsum("ij,ij->i", dp, dp)))
        r = np.array([x, y]) - self.p[k]
        along = float(r @ self.t[k])
        s = (self.s[k] + along) % self.length
        return k, s, float(r @ self.n[k])

    def surface_at(self, x: float, y: float) -> str:
        k, _, d = self.locate(x, y)
        return surface(self.curv[k], d, self.half_width, self.kerb, self.kerb_curv, self.runoff)

    def mu_at(self, x: float, y: float) -> float:
        return float(self.mu[self.surface_at(x, y)])

    def pose_at(self, s: float, offset: float = 0.0) -> tuple[float, float, float]:
        """A point on the track at arc length s, `offset` to the left, and the heading there."""
        s %= self.length
        k = int(np.searchsorted(self.s, s, side="right") - 1)
        frac = s - self.s[k]
        x, y = self.p[k] + frac * self.t[k] + offset * self.n[k]
        return float(x), float(y), math.atan2(self.t[k, 1], self.t[k, 0])


def surface(curv: float, d: float, half_width: float, kerb: float, kerb_curv: float, runoff: float) -> str:
    """Surface at lateral offset d (left +) from a centre-line point of signed curvature curv
    (the rules of design/track.py)."""
    ad = abs(d)
    if ad <= half_width:
        return "asphalt"
    corner = abs(curv) > kerb_curv
    if corner and ad <= half_width + kerb:
        return "kerb"
    outside = (curv > 0 and d < 0) or (curv < 0 and d > 0)
    if corner and outside and ad <= half_width + kerb + runoff:
        return "runoff"
    return "grass"


@dataclass
class LapTimer:
    """Lap times from the arc length of the car: a lap is a crossing of the start/finish line
    (s = 0) going forward, after more than half a lap of progress since the last one. The clock
    starts at the first crossing."""

    length: float
    laps: list[float] = field(default_factory=list)
    t_start: float | None = None
    s_prev: float | None = None
    progress: float = 0.0

    def update(self, t: float, s: float) -> bool:
        """The time t and the arc length s of a new step; True when a lap was completed."""
        done = False
        if self.s_prev is not None:
            ds = s - self.s_prev
            if ds < -0.5 * self.length:
                ds += self.length          # forward over the line
                crossed = True
            elif ds > 0.5 * self.length:
                ds -= self.length          # backwards over the line
                crossed = False
            else:
                crossed = False
            self.progress += ds
            if crossed:
                if self.t_start is not None and self.progress > 0.5 * self.length:
                    self.laps.append(t - self.t_start)
                    done = True
                if self.t_start is None or done:
                    self.t_start = t
                    self.progress = 0.0
        self.s_prev = s
        return done

    def current(self, t: float) -> float | None:
        return None if self.t_start is None else t - self.t_start

    @property
    def best(self) -> float | None:
        return min(self.laps) if self.laps else None

    @property
    def last(self) -> float | None:
        return self.laps[-1] if self.laps else None
