"""Trim, linearisation and modes of the reference model (`c172_ref.py`)."""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import least_squares

import c172_ref as M
import c172_si as S


# The ground of the free-air trims and performance points: far below, so a "sea-level" point is
# out of ground effect (KCLGE, KCDGE act below one span of height above the ground).
FREE_AIR = -1.0e4


def penetration(x, name, ground_z=0.0):
    """Geometric penetration of a gear contact point (the strut state's consistent value)."""
    R = M.quat_to_R(x[M.I_Q:M.I_Q + 4])
    return ground_z - (x[M.I_POS + 2] + (R @ S.GEAR[name]["r"])[2])


def make_state(V, h, alpha, beta, theta, phi=0.0, psi=0.0, omega=250.0, MAP=None, flap=0.0, w_b=(0.0, 0.0, 0.0),
               pos_xy=(0.0, 0.0), throttle=None, ground_z=0.0):
    """A full state from flight variables (angles in rad; FRD alpha/beta; body rates FLU)."""
    x = np.zeros(M.NX)
    x[M.I_POS:M.I_POS + 3] = (pos_xy[0], pos_xy[1], h)
    x[M.I_Q:M.I_Q + 4] = M.euler_quat(phi, theta, psi)
    u = V * math.cos(alpha) * math.cos(beta)
    v = V * math.sin(beta)
    w = V * math.sin(alpha) * math.cos(beta)
    x[M.I_V:M.I_V + 3] = (u, -v, -w)
    x[M.I_W:M.I_W + 3] = w_b
    x[M.I_H] = S.PROP_J * (omega + w_b[0])
    T, pa, rho, a = S.atmosphere(h)
    if MAP is None:
        mach = V / a
        p_tot = pa * (1.0 + 0.2 * mach * mach) ** 3.5
        MAP = M.map_target(omega, 0.0 if throttle is None else throttle, p_tot)
    x[M.I_MAP] = MAP
    x[M.I_AD] = math.atan(w / math.sqrt(u * u + M.V_FLOOR ** 2))
    x[M.I_FLAP] = flap
    for k, name in enumerate(M.GEARS):
        x[M.I_STRUT + k] = penetration(x, name, ground_z)
    return x


def trim(V, h, flap_deg=0.0, gamma=None, throttle=None, par: M.Params | None = None, guess=None,
         mixture=1.0):
    """Wings-level straight flight at TAS V (m/s) and altitude h: give `gamma` (flight-path angle,
    rad) to solve the throttle, or `throttle` to solve the flight-path angle. Unknowns: alpha,
    beta, yoke pitch, yoke roll, pedals, throttle (or gamma), engine speed. Returns
    (x, controls, info)."""
    par = M.Params(gear=False, ground_z=FREE_AIR) if par is None else par
    solve_thr = throttle is None
    flaps = flap_deg / 10.0

    def build(z):
        alpha, beta, ep, ea, er, tg, omega = z
        thr = tg if solve_thr else throttle
        gam = gamma if solve_thr else tg
        theta = alpha + math.asin(max(-1.0, min(1.0, math.sin(gam) / math.cos(beta))))
        T, pa, rho, a = S.atmosphere(h)
        mach = V / a
        MAP = M.map_target(omega, thr, pa * (1.0 + 0.2 * mach * mach) ** 3.5)
        x = make_state(V, h, alpha, beta, theta, omega=omega, MAP=MAP, flap=flap_deg)
        c = M.Controls(yoke_pitch=ep, yoke_roll=ea, pedals=er, throttle=thr, flaps=flaps, mixture=mixture)
        return x, c, thr, gam

    def res(z):
        x, c, _, _ = build(z)
        dx = M.deriv(0.0, x, c, par)
        return np.concatenate([dx[M.I_V:M.I_V + 3] / 1.0, dx[M.I_W:M.I_W + 3] * 10.0, [dx[M.I_H] / 10.0]])

    z0 = np.array(guess if guess is not None else
                  [0.05, 0.0, 0.0, 0.0, 0.0, 0.6 if solve_thr else 0.0, 230.0])
    lo = [-0.3, -0.3, -1.0, -1.0, -1.0, 0.0 if solve_thr else -0.5, 30.0]
    hi = [0.5, 0.3, 1.0, 1.0, 1.0, 1.0 if solve_thr else 0.5, 400.0]
    sol = least_squares(res, z0, bounds=(lo, hi), xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=2000)
    x, c, thr, gam = build(sol.x)
    out = M.outputs(x, c, par)
    info = {"alpha": sol.x[0], "beta": sol.x[1], "yoke_pitch": sol.x[2], "yoke_roll": sol.x[3],
            "pedals": sol.x[4], "throttle": thr, "gamma": gam, "omega": sol.x[6], "rpm": out["rpm"],
            "hp": out["hp"], "MAP": x[M.I_MAP], "cas": out["cas"], "vt": V, "h": h, "theta": out["theta"],
            "residual": float(np.max(np.abs(sol.fun))), "de": out["de"], "da": out["da"], "dr": out["dr"],
            "thrust": out["thrust"], "flap": flap_deg, "J": out["J"], "ok": bool(np.max(np.abs(sol.fun)) < 1e-8)}
    return x, c, info


# --------------------------------------------------------------------------- linearisation
LIN = ["u", "v", "w", "p", "q", "r", "phi", "theta", "psi", "h", "omega", "MAP", "xad"]


def to_lin(x):
    R = M.quat_to_R(x[M.I_Q:M.I_Q + 4])
    phi, theta, psi = M.euler_of_R(R)
    vb, wb = x[M.I_V:M.I_V + 3], x[M.I_W:M.I_W + 3]
    return np.array([vb[0], -vb[1], -vb[2], wb[0], -wb[1], -wb[2], phi, theta, psi, x[M.I_POS + 2],
                     x[M.I_H] / S.PROP_J - wb[0], x[M.I_MAP], x[M.I_AD]])


def from_lin(z, x_ref):
    x = x_ref.copy()
    u, v, w, p, q, r, phi, theta, psi, h, omega, MAP, xad = z
    x[M.I_V:M.I_V + 3] = (u, -v, -w)
    x[M.I_W:M.I_W + 3] = (p, -q, -r)
    x[M.I_Q:M.I_Q + 4] = M.euler_quat(phi, theta, psi)
    x[M.I_POS + 2] = h
    x[M.I_H] = S.PROP_J * (omega + p)
    x[M.I_MAP] = MAP
    x[M.I_AD] = xad
    return x


def lin_deriv(z, x_ref, c, par):
    x = from_lin(z, x_ref)
    dx = M.deriv(0.0, x, c, par)
    u, v, w, p, q, r, phi, theta, psi = z[:9]
    vb_dot, wb_dot = dx[M.I_V:M.I_V + 3], dx[M.I_W:M.I_W + 3]
    tt = math.tan(theta)
    phid = p + tt * (q * math.sin(phi) + r * math.cos(phi))
    thd = q * math.cos(phi) - r * math.sin(phi)
    psid = (q * math.sin(phi) + r * math.cos(phi)) / math.cos(theta)
    omega_dot = dx[M.I_H] / S.PROP_J - wb_dot[0]
    return np.array([vb_dot[0], -vb_dot[1], -vb_dot[2], wb_dot[0], -wb_dot[1], -wb_dot[2], phid, thd, psid,
                     dx[M.I_POS + 2], omega_dot, dx[M.I_MAP], dx[M.I_AD]])


def linearise(x0, c, par):
    z0 = to_lin(x0)
    scale = np.array([0.1, 0.1, 0.1, 1e-3, 1e-3, 1e-3, 1e-4, 1e-4, 1e-4, 1.0, 0.1, 10.0, 1e-4])
    n = len(z0)
    A = np.zeros((n, n))
    for j in range(n):
        dz = np.zeros(n)
        dz[j] = scale[j]
        A[:, j] = (lin_deriv(z0 + dz, x0, c, par) - lin_deriv(z0 - dz, x0, c, par)) / (2 * scale[j])
    return A, z0


LONG_IDX = [0, 2, 4, 7, 9]      # u, w, q, theta, h
LAT_IDX = [1, 3, 5, 6, 8]       # v, p, r, phi, psi


def classify(A):
    """Eigenvalues with their mode names: short period, phugoid, dutch roll, roll, spiral, and the
    engine (speed, manifold), alpha-dot filter and heading/altitude integrators."""
    lam, V = np.linalg.eig(A)
    nrm = np.array([1.0, 1.0, 1.0, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 10.0, 5.0, 1000.0, 0.05])
    modes = []
    for k in range(len(lam)):
        v = V[:, k] / nrm
        e_long = np.linalg.norm(v[LONG_IDX])
        e_lat = np.linalg.norm(v[LAT_IDX])
        e_eng = np.linalg.norm(v[[10, 11, 12]])
        modes.append({"lam": lam[k], "vec": V[:, k], "long": e_long, "lat": e_lat, "eng": e_eng})
    out = {}
    osc = [m for m in modes if m["lam"].imag > 1e-6]
    real = [m for m in modes if abs(m["lam"].imag) <= 1e-6]
    lon_osc = sorted([m for m in osc if m["long"] > m["lat"]], key=lambda m: abs(m["lam"]))
    lat_osc = sorted([m for m in osc if m["lat"] >= m["long"]], key=lambda m: abs(m["lam"]))
    if len(lon_osc) >= 2:
        out["phugoid"], out["short_period"] = lon_osc[0], lon_osc[-1]
    elif len(lon_osc) == 1:
        out["phugoid"] = lon_osc[0]
    if lat_osc:
        out["dutch_roll"] = lat_osc[-1]
    # the real lateral modes: identified on the decoupled lateral system (v, p, r, phi), then the
    # nearest eigenvalue of the full matrix is taken (the altitude/density mode is real and slow
    # too, and the full eigenvectors mix it with the spiral)
    lat4 = [1, 3, 5, 6]
    lam_lat = np.linalg.eigvals(A[np.ix_(lat4, lat4)])
    lam_lat_real = sorted([lm for lm in lam_lat if abs(lm.imag) <= 1e-9], key=lambda lm: abs(lm))
    if len(lam_lat_real) >= 2:
        for name, target in (("spiral", lam_lat_real[0]), ("roll", lam_lat_real[-1])):
            out[name] = min(real, key=lambda m: abs(m["lam"] - target))
    out["all"] = modes
    return out


def mode_numbers(m):
    lam = m["lam"]
    wn = abs(lam)
    zeta = -lam.real / wn if wn > 0 else 0.0
    rec = {"re": float(lam.real), "im": float(lam.imag), "wn": float(wn), "zeta": float(zeta)}
    if abs(lam.imag) > 1e-9:
        rec["period"] = float(2 * math.pi / abs(lam.imag))
    elif lam.real != 0:
        rec["tau"] = float(-1.0 / lam.real)
        rec["t_half_or_double"] = float(math.log(2) / abs(lam.real))
    return rec
