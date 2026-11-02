"""Closed-loop scipy reference of `beaver-sim`: airframe, drivetrain, pilot mapping, the FDC
'Beaver' autopilot and its servos, written to the same equations as the bg-sim blocks
(library/BeaverPitchAP.jl, BeaverRollAP.jl, BeaverServo.jl, BeaverControls.jl).

The autopilot is the one of FDC 1.4 (apilot/aplib.mdl, [REP] chapter 11): the pitch attitude hold
(PAH) with the altitude hold (ALH) as its outer loop, and the roll attitude hold (RAH) with the
heading hold (HH) as its outer loop and the turn coordinator on the rudder. Gains are scheduled on
the true airspeed. What is ours (labelled in the README):
  * the servos: a first-order lag (tau 0.09 s) with the speed-dependent DC gain of the FDC
    third-order actuator and cable models (data/actmod35/45/55.dat) fitted as a quadratic in V;
  * the limited integrators as back-calculation integrators (time constant T_AW), and the bleed of
    an integrator to zero while its loop is off (T_OFF);
  * the absolute references (theta_ref, phi_ref, psi_ref, H_ref) instead of FDC's deviations from
    the trim, and the heading error wrapped to (-pi, pi];
  * the turn compensation of the ALH mode in ALH (FDC's switch has threshold 0 on a 0/1 flag and
    always picks the PAH formula; [REP] section 11 gives the ALH formula for the outer loops);
  * the pilot mapping (column, pedals, trim offsets, travel limits).

State z = [x (12), omega, ci, ye, ya, yr, I_pah, xw, I_rah]; FDC units (rad, rad/s, m).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.integrate import solve_ivp

import beaver_ref as R

D2R = math.pi / 180.0
T_AW = 0.05     # s, back-calculation of the limited integrators (ours)
T_OFF = 0.5     # s, bleed of an integrator while its loop is off (ours)
TAU_SERVO = 0.09
# DC gain of the FDC actuator + cable models from command (rad, 1 V = 1 deg) to deflection, at
# 35, 45, 55 m/s (data/actmod*.dat, first input): quadratic fits through the three points.
SERVO_DC = {"e": (1.848, 1.900, 1.963), "a": (1.662, 1.429, 1.196), "r": (0.784, 0.661, 0.582)}


def quad_through(ys, xs=(35.0, 45.0, 55.0)):
    a, b, c = np.polyfit(xs, ys, 2)
    return float(a), float(b), float(c)


SERVO_POLY = {k: quad_through(v) for k, v in SERVO_DC.items()}

# The pilot mapping (ours): column, pedals in -1..1 -> deflection; travel limits. deg.
PILOT = {"k_col_e": 15.0, "k_col_a": 15.0, "k_ped": 15.0, "lim_e": 20.0, "lim_a": 20.0, "lim_r": 20.0,
         "flap_max": 20.0, "pz_min": 10.0, "pz_max": 30.0, "n_min": 1600.0, "n_max": 2300.0}


def clamp(v, lo, hi):
    return min(max(v, lo), hi)


def poly(c, V):
    return sum(ci * V ** (len(c) - 1 - k) for k, ci in enumerate(c))


def pitch_ap(mode, theta, q, r, phi, V, H, theta_ref, H_ref, theta0, I, xw):
    """FDC PAH/ALH. Returns (elevator command rad, dI, dxw, diagnostics)."""
    on = mode > 0.5
    alh = mode > 1.5
    Kth = poly((-1.375e-3, 0.1575, -4.8031), V)
    Kq = poly((-4.75e-4, 0.0540, -1.5931), V)
    Kd = poly((-2.5e-3, 0.2875), V)
    KH = poly((-1.0e-4, 0.015, -0.5975), V) * D2R
    dth_ref = KH * (H_ref - H) / Kth if alh else theta_ref - theta0
    dth_lim = clamp(dth_ref, -8.0 * D2R, 18.0 * D2R)
    fb = (theta - theta0) - clamp(Kd * xw, -20.0 * D2R, 20.0 * D2R)
    e = dth_lim - fb
    u1 = clamp(Kth * e, -2.0 * D2R, 2.0 * D2R)
    if alh:
        tc = r * math.tan(phi) + poly((0.03, 0.25), V) * (1.0 / math.cos(phi + 0.03491) - 1.0)
    else:
        tc = r * math.tan(phi) + poly((5.0e-4, -0.03, 0.9375), V) * (1.0 / math.cos(phi) - 1.0)
    Il = clamp(I, -10.0 * D2R, 10.0 * D2R)
    cmd = (u1 + Il - Kq * (q - tc)) if on else 0.0
    dI = (0.5 * u1 + (Il - I) / T_AW) if on else -I / T_OFF
    dxw = ((theta - theta0) if alh else 0.0) - Kd * xw
    return cmd, dI, dxw, {"dth_ref": dth_lim}


def roll_ap(mode, phi, r, psi, V, phi_ref, psi_ref, I):
    """FDC RAH/HH and the turn coordinator. Returns (aileron cmd, rudder cmd, dI, diagnostics)."""
    on = mode > 0.5
    hh = mode > 1.5
    Kphi = poly((9.75e-4, -0.108, 2.335625), V)
    Kpsi = poly((0.05, -1.1), V)
    drr = poly((-7.5e-5, 0.0095, -0.4606), V)
    epsi = math.atan2(math.sin(psi_ref - psi), math.cos(psi_ref - psi))
    dphi_ref = Kpsi * epsi if hh else phi_ref
    e = clamp(dphi_ref, -30.0 * D2R, 30.0 * D2R) - phi
    u1 = clamp(Kphi * e, -3.75 * D2R, 3.75 * D2R)
    Il = clamp(I, -1.0 * D2R, 1.0 * D2R)
    da = (u1 + Il + 0.165 * r) if on else 0.0
    dr = (-4.0 * (9.80665 / V) * math.sin(phi) + (drr + 4.0) * r) if on else 0.0
    dI = (0.25 * u1 + (Il - I) / T_AW) if on else -I / T_OFF
    return da, dr, dI, {"phi_ref": clamp(dphi_ref, -30.0 * D2R, 30.0 * D2R)}


def servo_rate(axis, u, y, V):
    return (poly(SERVO_POLY[axis], V) * u - y) / TAU_SERVO


def controls(pil, ye, ya, yr):
    """Pilot inputs (deg, inch Hg, rpm) plus the servo outputs (rad) -> u = [de da dr df n pz]."""
    P = PILOT
    de = clamp(pil["elev_trim"] - P["k_col_e"] * pil["col_pitch"] + ye / D2R, -P["lim_e"], P["lim_e"])
    da = clamp(pil["ail_trim"] - P["k_col_a"] * pil["col_roll"] + ya / D2R, -P["lim_a"], P["lim_a"])
    dr = clamp(pil["rud_trim"] - P["k_ped"] * pil["pedals"] + yr / D2R, -P["lim_r"], P["lim_r"])
    df = clamp(pil["flaps"], 0.0, P["flap_max"])
    n = clamp(pil["rpm"], P["n_min"], P["n_max"])
    pz = clamp(pil["pz"], P["pz_min"], P["pz_max"])
    return np.array([de * D2R, da * D2R, dr * D2R, df * D2R, n, pz])


def zdot(t, z, inputs, gov, theta0, drivetrain):
    x = z[:12]
    w, ci, ye, ya, yr, Ip, xw, Ir = z[12:]
    pil = inputs(t)
    V, alpha, beta, p, q, r, psi, theta, phi = x[:9]
    H = x[11]
    cmd_e, dIp, dxw, _ = pitch_ap(pil["ap_pitch"], theta, q, r, phi, V, H, pil["theta_ref"] * D2R,
                                  pil["h_ref"], theta0, Ip, xw)
    cmd_a, cmd_r, dIr, _ = roll_ap(pil["ap_roll"], phi, r, psi, V, pil["phi_ref"] * D2R, pil["psi_ref"] * D2R, Ir)
    u = controls(pil, ye, ya, yr)
    xd = R.xdot_ext(np.concatenate([x, [w, ci]]), u, gov, drivetrain)
    return np.concatenate([xd, [servo_rate("e", cmd_e, ye, V), servo_rate("a", cmd_a, ya, V),
                                servo_rate("r", cmd_r, yr, V), dIp, dxw, dIr]])


def ramp(t, t0, dur):
    """The stdlib Ramp shape with slope 1/dur: 0 before t0, 1 after t0 + dur."""
    if t < t0:
        return 0.0
    return min(t - t0, dur) / dur


def simulate(inputs, z0, t_end, breaks, gov, theta0, drivetrain, dt_out=0.1):
    """Integrate between the stimulus breakpoints (DOP853, tight tolerances)."""
    pts = sorted({0.0, t_end, *[b for b in breaks if 0.0 < b < t_end]})
    ts = np.round(np.arange(0.0, t_end + 1e-9, dt_out), 10)
    out = np.zeros((len(ts), len(z0)))
    z = np.array(z0, dtype=float)
    k = 0
    for a, b in zip(pts[:-1], pts[1:]):
        sel = ts[(ts >= a - 1e-12) & (ts <= b + 1e-12)]
        sol = solve_ivp(zdot, (a, b), z, method="DOP853", rtol=1e-11, atol=1e-11, dense_output=True,
                        args=(inputs, gov, theta0, drivetrain))
        for tt in sel:
            idx = int(round(tt / dt_out))
            out[idx] = sol.sol(tt)
        z = sol.y[:, -1]
        k += 1
    return ts, out


def initial(x0, u0, gov):
    return np.concatenate([x0, [u0[4] / R.RPM, gov["Cq0"], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]])
