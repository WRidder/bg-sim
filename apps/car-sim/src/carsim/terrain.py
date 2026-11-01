"""The buggy's rolling hills: the analytic height field of ``examples/cars/design/hills.json``.

    h(x, y) = h0 + sx x + sy y + sum_i a_i cos(kx_i x + ky_i y + ph_i)

These are the parameters of the TerrainSurface elements inside the buggy-sim FMU (one per wheel),
written by design/build_model.py from the same table, so the ground drawn here is the ground the
tyres roll on: the rendered grid has this height exactly at its vertices (2 m apart, the shortest
wavelength is 25 m).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HILLS_JSON = Path(__file__).resolve().parents[4] / "examples" / "cars" / "design" / "hills.json"
EXTENT = 400.0          # m: the drawn (and drivable) square is |x|, |y| <= EXTENT


class Hills:
    def __init__(self, path: Path = HILLS_JSON):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        self.h0, self.sx, self.sy = float(d["h0"]), float(d["sx"]), float(d["sy"])
        self.a = np.asarray(d["a"], float)
        self.kx = np.asarray(d["kx"], float)
        self.ky = np.asarray(d["ky"], float)
        self.ph = np.asarray(d["ph"], float)

    def height(self, x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        arg = np.multiply.outer(x, self.kx) + np.multiply.outer(y, self.ky) + self.ph
        return self.h0 + self.sx * x + self.sy * y + np.sum(self.a * np.cos(arg), axis=-1)

    def gradient(self, x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        arg = np.multiply.outer(x, self.kx) + np.multiply.outer(y, self.ky) + self.ph
        s = -self.a * np.sin(arg)
        return self.sx + np.sum(s * self.kx, axis=-1), self.sy + np.sum(s * self.ky, axis=-1)

    def start_height(self, x: float, y: float, yaw: float, corners, h_s: float) -> float:
        """The chassis CG height for a level start at (x, y, yaw): every wheel at or above the
        ground at the static ride height (`corners`: (x, y) in the chassis frame)."""
        c, s = np.cos(yaw), np.sin(yaw)
        hs = [float(self.height(x + c * cx - s * cy, y + s * cx + c * cy)) for cx, cy in corners]
        return max(hs) + h_s + 0.01
