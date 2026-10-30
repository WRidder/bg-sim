"""The Lissajous figure (horizontal 1:2 figure of eight with an optional gentle altitude component)."""

from __future__ import annotations

import numpy as np


def table(A: float, B: float, Cz: float, z0: float, ds: float = 2.0, laps: float = 1.6, zharm: int = 1):
    """Points at constant arc-length spacing ds: x, y, z, heading, curvature (left positive), s.

    x = A sin(th), y = B sin(2 th), z = z0 + Cz sin(zharm th), th in [0, 2 pi laps]; the length of one lap is returned too.
    """
    th = np.linspace(0.0, 2 * np.pi * laps, int(40000 * laps) + 1)
    dx, dy = A * np.cos(th), 2 * B * np.cos(2 * th)
    ddx, ddy = -A * np.sin(th), -4 * B * np.sin(2 * th)
    sp = np.hypot(dx, dy)
    s = np.concatenate([[0.0], np.cumsum(0.5 * (sp[1:] + sp[:-1]) * np.diff(th))])
    n = int(s[-1] // ds) + 1
    sg = np.arange(n) * ds
    t = np.interp(sg, s, th)
    x, y = A * np.sin(t), B * np.sin(2 * t)
    z = z0 + Cz * np.sin(zharm * t)
    dxs, dys = A * np.cos(t), 2 * B * np.cos(2 * t)
    ddxs, ddys = -A * np.sin(t), -4 * B * np.sin(2 * t)
    spd = np.hypot(dxs, dys)
    psi = np.unwrap(np.arctan2(dys, dxs))
    kap = (dxs * ddys - dys * ddxs) / spd**3
    lap = np.interp(2 * np.pi, th, s)
    return dict(x=x, y=y, z=z, psi=psi, kappa=kap, s=sg, lap=float(lap), theta=t)


def stats(A: float, B: float):
    t = table(A, B, 0.0, 0.0, ds=1.0, laps=1.0)
    k = np.abs(t["kappa"])
    return dict(length=t["lap"], rmin=float(1 / k.max()), at=int(k.argmax()))
