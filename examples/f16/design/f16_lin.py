"""Trim and linearisation of the reference model (book units)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import fsolve

import f16_ref as F


def state13(vt, alpha, theta, h, power, q=0.0):
    x = np.zeros(13)
    x[0], x[1], x[4], x[7], x[11], x[12] = vt, alpha, theta, q, h, power
    return x


def trim_level(vt, h, xcg, guess=(0.15, -1.0, 0.04)):
    """Wings-level, gamma = 0: throttle, elevator (deg), alpha (rad) with Vt' = alpha' = q' = 0."""
    def res(z):
        thtl, el, a = z
        xd, _ = F.f16(state13(vt, a, a, h, F.tgear(thtl)), [thtl, el, 0.0, 0.0], xcg)
        return [xd[0], xd[1], xd[7]]
    z = fsolve(res, guess, xtol=1e-13)
    assert max(abs(r) for r in res(z)) < 1e-9, res(z)
    thtl, el, a = z
    return {"throttle": float(thtl), "el": float(el), "alpha": float(a), "theta": float(a),
            "power": float(F.tgear(thtl)), "vt": vt, "h": h, "xcg": xcg}


LON = (0, 1, 4, 7, 11, 12)    # Vt, alpha, theta, q, h, pow
LON_NAMES = ["vt", "alpha", "theta", "q", "h", "pow"]


def linearise(tr, idx=LON):
    x0 = state13(tr["vt"], tr["alpha"], tr["theta"], tr["h"], tr["power"])
    u0 = [tr["throttle"], tr["el"], 0.0, 0.0]
    n = len(idx)
    A = np.zeros((n, n))
    Bm = np.zeros((n, 2))
    for j, k in enumerate(idx):
        e = 1e-6 * max(1.0, abs(x0[k]))
        xp, xm = x0.copy(), x0.copy()
        xp[k] += e
        xm[k] -= e
        A[:, j] = (F.f16(xp, u0, tr["xcg"])[0][list(idx)] - F.f16(xm, u0, tr["xcg"])[0][list(idx)]) / (2 * e)
    for j, k in enumerate((1, 0)):      # el, throttle
        e = 1e-6
        up, um = list(u0), list(u0)
        up[k] += e
        um[k] -= e
        Bm[:, j] = (F.f16(x0, up, tr["xcg"])[0][list(idx)] - F.f16(x0, um, tr["xcg"])[0][list(idx)]) / (2 * e)
    return A, Bm


def modes(A):
    lam, vec = np.linalg.eig(A)
    order = np.argsort(-lam.real)
    return lam[order], vec[:, order]


def classify(lam):
    """Name the longitudinal modes: engine lag (-1), height mode (~0), phugoid, short period."""
    out = {}
    cplx = [l for l in lam if l.imag > 1e-9]
    real = sorted([l.real for l in lam if abs(l.imag) <= 1e-9], reverse=True)
    if len(cplx) == 2:
        sp, ph = sorted(cplx, key=lambda l: abs(l))[::-1]
        out["short_period"] = [sp.real, sp.imag]
        out["phugoid"] = [ph.real, ph.imag]
    else:
        ph = cplx[0]
        out["phugoid"] = [ph.real, ph.imag]
        sp = [r for r in real if abs(r + 1.0) > 1e-6 and abs(r) > 0.01]
        out["short_period_real"] = sp
    out["all"] = [[l.real, l.imag] for l in lam]
    return out
