# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""The race track of the `cars` example and the car-sim host: a closed circuit of about 1.7 km.

The centre line is a periodic cubic spline through hand-placed control points (a 520 m main
straight with the start/finish line at the origin, heading +x, a hairpin, a chicane, fast
sweepers), sampled every metre. Surfaces, by the lateral distance d from the centre line:

    |d| <= HALF_WIDTH                  asphalt          mu 1.00
    kerb band (corners only)           red/white kerbs  mu 0.85
    run-off (outside of corners)       asphalt run-off  mu 0.95
    elsewhere                          grass            mu 0.60

Everything lies on the plane z = 0, which is the physics ground of the race car (a flat
ContactSurface); only the friction scale differs, and the host sets it per wheel (the FMU's
mu inputs).

    uv run examples/cars/design/track.py     # writes design/track.json (used by the host app)
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

CONTROL = [
    (0.0, 0.0), (250.0, 0.0), (450.0, 6.0), (565.0, 45.0), (595.0, 125.0), (545.0, 195.0),
    (430.0, 172.0), (345.0, 118.0), (262.0, 168.0), (182.0, 240.0), (60.0, 252.0),
    (-62.0, 205.0), (-112.0, 112.0), (-92.0, 32.0), (-42.0, 3.0),
]
HALF_WIDTH = 6.0
KERB = 1.4                # kerb band width
KERB_CURV = 1.0 / 180.0   # kerbs where the curvature exceeds this
RUNOFF = 14.0             # run-off asphalt beyond the kerbs on the outside of corners
MU = {"asphalt": 1.0, "kerb": 0.85, "runoff": 0.95, "grass": 0.6}
SURFACE_ID = {"asphalt": 0, "kerb": 1, "runoff": 2, "grass": 3}


def _periodic_spline(points: np.ndarray, n_out: int) -> np.ndarray:
    """Periodic cubic spline (C2) through the closed polygon `points`, parameterised by chord
    length, evaluated at n_out equally spaced parameter values."""
    P = np.asarray(points, dtype=float)
    n = len(P)
    d = np.linalg.norm(np.roll(P, -1, axis=0) - P, axis=1)
    # second derivatives M from the periodic tridiagonal system (per coordinate)
    A = np.zeros((n, n))
    for i in range(n):
        hp, hn = d[i - 1], d[i]
        A[i, (i - 1) % n] = hp / 6.0
        A[i, i] = (hp + hn) / 3.0
        A[i, (i + 1) % n] = hn / 6.0
    rhs = np.zeros((n, 2))
    for i in range(n):
        hp, hn = d[i - 1], d[i]
        rhs[i] = (P[(i + 1) % n] - P[i]) / hn - (P[i] - P[i - 1]) / hp
    M = np.linalg.solve(A, rhs)
    knots = np.concatenate([[0.0], np.cumsum(d)])
    total = knots[-1]
    u = np.linspace(0.0, total, n_out, endpoint=False)
    out = np.zeros((n_out, 2))
    for k, uk in enumerate(u):
        i = min(int(np.searchsorted(knots, uk, side="right") - 1), n - 1)
        h = d[i]
        a = (knots[i + 1] - uk) / h
        b = (uk - knots[i]) / h
        p0, p1 = P[i], P[(i + 1) % n]
        m0, m1 = M[i], M[(i + 1) % n]
        out[k] = a * p0 + b * p1 + ((a ** 3 - a) * m0 + (b ** 3 - b) * m1) * h * h / 6.0
    return out


def centreline(step: float = 1.0) -> dict:
    """The centre line resampled at `step` metres: points, unit tangents, left normals, signed
    curvature (left turns positive) and the arc length."""
    rough = _periodic_spline(np.array(CONTROL), 4000)
    seg = np.linalg.norm(np.roll(rough, -1, axis=0) - rough, axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    length = s[-1]
    n = int(round(length / step))
    sq = np.linspace(0.0, length, n, endpoint=False)
    closed = np.vstack([rough, rough[:1]])
    pts = np.column_stack([np.interp(sq, s, closed[:, 0]), np.interp(sq, s, closed[:, 1])])
    tang = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    tang /= np.linalg.norm(tang, axis=1)[:, None]
    normal = np.column_stack([-tang[:, 1], tang[:, 0]])
    dtan = np.roll(tang, -1, axis=0) - np.roll(tang, 1, axis=0)
    ds = np.linalg.norm(np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0), axis=1)
    curv = (tang[:, 0] * dtan[:, 1] - tang[:, 1] * dtan[:, 0]) / ds
    # smooth the curvature a little (the kerb layout should not flicker)
    kern = np.ones(15) / 15.0
    curv = np.convolve(np.concatenate([curv[-7:], curv, curv[:7]]), kern, mode="valid")
    return {"s": sq, "p": pts, "t": tang, "n": normal, "curv": curv, "length": float(length)}


def surface(curv: float, d: float) -> str:
    """Surface at lateral offset d (left +) from a centre-line point of signed curvature curv."""
    ad = abs(d)
    if ad <= HALF_WIDTH:
        return "asphalt"
    corner = abs(curv) > KERB_CURV
    if corner and ad <= HALF_WIDTH + KERB:
        return "kerb"
    outside = (curv > 0 and d < 0) or (curv < 0 and d > 0)
    if corner and outside and ad <= HALF_WIDTH + KERB + RUNOFF:
        return "runoff"
    return "grass"


def main() -> int:
    c = centreline(1.0)
    data = {
        "$comment": "Race track of the cars example (design/track.py): the centre line every metre, "
                    "its unit tangent, left normal and signed curvature; surfaces by lateral offset.",
        "length": c["length"], "half_width": HALF_WIDTH, "kerb": KERB, "kerb_curv": KERB_CURV,
        "runoff": RUNOFF, "mu": MU,
        "x": [round(float(v), 4) for v in c["p"][:, 0]], "y": [round(float(v), 4) for v in c["p"][:, 1]],
        "tx": [round(float(v), 6) for v in c["t"][:, 0]], "ty": [round(float(v), 6) for v in c["t"][:, 1]],
        "curv": [round(float(v), 7) for v in c["curv"]],
    }
    (HERE / "track.json").write_text(json.dumps(data) + "\n", encoding="utf-8", newline="\n")
    print(f"track: {c['length']:.1f} m, {len(c['s'])} points, max curvature {np.max(np.abs(c['curv'])):.4f} 1/m "
          f"(radius {1 / np.max(np.abs(c['curv'])):.1f} m)")
    # self-intersection guard: no two points far apart along the track are closer than 30 m
    p = c["p"]
    n = len(p)
    step = 5
    sub = p[::step]
    dmin = math.inf
    for i in range(len(sub)):
        dd = np.linalg.norm(sub - sub[i], axis=1)
        idx = np.arange(len(sub))
        gap = np.minimum(np.abs(idx - i), len(sub) - np.abs(idx - i)) * step
        mask = gap > 80
        if np.any(mask):
            dmin = min(dmin, float(np.min(dd[mask])))
    print(f"closest approach of separate parts of the track: {dmin:.1f} m")
    assert dmin > 2 * (HALF_WIDTH + KERB) + 6, "track parts too close"
    del n
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
