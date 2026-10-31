"""SI version of the Stevens & Lewis F-16 data for the bg-sim model, plus the principal axes.

Every number of the bg-sim model comes from here; `f16_ref.py` (book units) stays the reference.

Units: the bg-sim model is in SI (m, kg, s, N, Pa); angles in the tables and the control laws are
in degrees (the unit of the NASA data), body rates in rad/s or deg/s as named. Conversions are the
exact definitions: 1 ft = 0.3048 m, 1 slug = 14.5939029372 kg, 1 lbf = 4.4482216152605 N.
"""

from __future__ import annotations

import math

import numpy as np

import f16_ref as F

FT = 0.3048
SLUG = 14.593902937206364
LBF = 4.4482216152605
SLUGFT2 = SLUG * FT * FT          # slug ft^2 -> kg m^2
PSF = LBF / (FT * FT)             # lbf/ft^2 -> Pa

MASS = 1.0 / F.RM * SLUG          # kg (the book's 1/rm = 636.94 slug; W = 20500 lb)
G0 = F.G_FT * FT                  # 9.805416 m/s^2
S = F.S_FT2 * FT * FT             # 27.870912 m^2
B = F.B_FT * FT                   # 9.144 m
CBAR = F.CBAR_FT * FT             # 3.450336 m
HE = F.HE * SLUGFT2               # kg m^2/s
JXX, JYY, JZZ, JXZ = (v * SLUGFT2 for v in (F.JXX, F.JYY, F.JZZ, F.JXZ))

# Atmosphere (the book's ADC in SI)
RHO0 = 2.377e-3 * SLUG / FT ** 3
KLAPSE = 0.703e-5 / FT
H_TROP = 35000.0 * FT
A_GAS = math.sqrt(1.4 * 1716.3) * FT


def principal_axes():
    """Inertia in the geometric body frame B (x forward, y left, z up): the FRD tensor
    [[Jx, 0, -Jxz], [0, Jy, 0], [-Jxz, 0, Jz]] becomes [[Jx, 0, Jxz], [0, Jy, 0], [Jxz, 0, Jz]] in FLU.
    Returns (J principal, eps): B = R_y(eps) P, i.e. the principal x axis is the body x axis
    rotated by eps about y (a positive eps tips it nose down in FLU)."""
    I_b = np.array([[JXX, 0.0, JXZ], [0.0, JYY, 0.0], [JXZ, 0.0, JZZ]])
    # R_y(e) diag(J1, Jy, J3) R_y(e)^T has the xz entry sin(e)cos(e)(J3 - J1) = Jxz.
    eps = 0.5 * math.atan2(2.0 * JXZ, JZZ - JXX)
    c, s = math.cos(eps), math.sin(eps)
    R = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    Jp = R.T @ I_b @ R
    assert abs(Jp[0, 2]) < 1e-9 * JZZ and abs(Jp[2, 0]) < 1e-9 * JZZ
    return np.array([Jp[0, 0], Jp[1, 1], Jp[2, 2]]), eps, R


J_PRINCIPAL, EPS, R_BP = principal_axes()


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_from_euler_ned(phi, theta, psi):
    """Quaternion of R_WB for the bg-sim world (x north, y west, z up) and body FLU, from the
    book's NED/FRD Euler angles. R_WB = T R_ned T with T = diag(1, -1, -1); in quaternion terms
    the NED quaternion (w, x, y, z) becomes (w, x, -y, -z)."""
    cphi, sphi = math.cos(phi / 2), math.sin(phi / 2)
    cth, sth = math.cos(theta / 2), math.sin(theta / 2)
    cpsi, spsi = math.cos(psi / 2), math.sin(psi / 2)
    w = cphi * cth * cpsi + sphi * sth * spsi
    x = sphi * cth * cpsi - cphi * sth * spsi
    y = cphi * sth * cpsi + sphi * cth * spsi
    z = cphi * cth * spsi - sphi * sth * cpsi
    return np.array([w, x, -y, -z])


def initial_state(x13, xcg=None):
    """bg-sim start values for one airframe from the book's 13-state vector (ft units).

    Returns the Free3D pose starts (principal frame), the RigidBody3D momentum start (principal
    frame) and the engine power level."""
    vt, alpha, beta, phi, theta, psi, p, q, r, pn, pe, h, power = x13
    q_wb = quat_from_euler_ned(phi, theta, psi)
    # q_WP = q_WB (x) q_BP, q_BP = rotation by eps about y.
    q_bp = np.array([math.cos(EPS / 2), 0.0, math.sin(EPS / 2), 0.0])
    q_wp = quat_mul(q_wb, q_bp)
    vt_si = vt * FT
    u = vt_si * math.cos(alpha) * math.cos(beta)
    v = vt_si * math.sin(beta)
    w = vt_si * math.sin(alpha) * math.cos(beta)
    v_b = np.array([u, -v, -w])          # FLU
    w_b = np.array([p, -q, -r])
    v_p = R_BP.T @ v_b
    w_p = R_BP.T @ w_b
    P = np.concatenate([J_PRINCIPAL * w_p, MASS * v_p])
    pose = {"qw": q_wp[0], "qx": q_wp[1], "qy": q_wp[2], "qz": q_wp[3],
            "px": pn * FT, "py": -pe * FT, "pz": h * FT}
    return pose, P, power
