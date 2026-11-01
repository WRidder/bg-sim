"""The terrain as data: hills, the airfield and the landmarks, shared by the renderer and the
crash check (the FMU knows only its flat ground at 0 m; the hills are the host's)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

AIRFIELD = (3000.0, -1800.0)     # north, east of the runway centre (m): ahead and left of the start
RUNWAY_LENGTH, RUNWAY_WIDTH = 3000.0, 45.0
TOWN = (14000.0, 5000.0)
LAKE = (-6000.0, 7000.0, 2500.0)  # north, east, radius


@dataclass(frozen=True)
class Hill:
    north: float
    east: float
    height: float
    radius: float                 # m, the Gaussian's sigma


def hills(seed: int = 7) -> list[Hill]:
    """A ridge to the east, scattered hills elsewhere; none on the airfield, the town or the lake."""
    rng = np.random.default_rng(seed)
    out = [Hill(9000.0 + 2500.0 * k, 16000.0 + 900.0 * math.sin(k), 700.0 + 250.0 * math.cos(1.7 * k), 2200.0)
           for k in range(-6, 8)]
    keep_clear = [(AIRFIELD[0], AIRFIELD[1], 6000.0), (TOWN[0], TOWN[1], 4000.0), (LAKE[0], LAKE[1], LAKE[2] + 2500.0),
                  (0.0, 0.0, 3000.0)]
    while len(out) < 60:
        n, e = rng.uniform(-34000.0, 34000.0, 2)
        if any(math.hypot(n - a, e - b) < r for a, b, r in keep_clear):
            continue
        out.append(Hill(float(n), float(e), float(rng.uniform(120.0, 650.0)), float(rng.uniform(900.0, 2600.0))))
    return out


HILLS = hills()
_H = np.array([[h.north, h.east, h.height, h.radius] for h in HILLS])


def height(north, east):
    """Terrain height (m) at a point or arrays of points: the sum of the Gaussian hills."""
    n = np.asarray(north, dtype=float)[..., None]
    e = np.asarray(east, dtype=float)[..., None]
    d2 = (n - _H[:, 0]) ** 2 + (e - _H[:, 1]) ** 2
    return np.sum(_H[:, 2] * np.exp(-0.5 * d2 / _H[:, 3] ** 2), axis=-1)
