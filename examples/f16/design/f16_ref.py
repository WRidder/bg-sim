"""Reference implementation of the Stevens & Lewis nonlinear F-16 in the book's own units.

This is the independent check of the bg-sim model: a direct port of the book's `F16` subroutine
(Stevens & Lewis, *Aircraft Control and Simulation*, 2nd ed., Section 3.6 and Appendix A) with the
13-state vector of the book,

    x = [Vt (ft/s), alpha, beta (rad), phi, theta, psi (rad), P, Q, R (rad/s),
         pn, pe, h (ft), pow (percent)],      u = [throttle (0..1), el, ail, rdr (deg)],

and the book's table interpolation: bilinear on the regular grids, extrapolated linearly from the
end cells (`interp_book`). The bg-sim model holds the edge value instead (`interp_clamp`, the
`interp1`/`interp2` intrinsics); inside the data (-10 <= alpha <= 45 deg, |beta| <= 30 deg,
|el| <= 24 deg) both are the same function.

The moment equations are written with the inertia matrix instead of the book's c1..c9 constants
(the same numbers, see `_inertia_check`), because the bg-sim airframe is a rigid body with a full
inertia tensor on principal axes.
"""

from __future__ import annotations

import math

import numpy as np

import f16_data as D

# --------------------------------------------------------------------------- book constants
S_FT2 = 300.0          # wing area
B_FT = 30.0            # span
CBAR_FT = 11.32        # mean aerodynamic chord
WEIGHT_LB = 20500.0    # weight
G_FT = 32.17           # ft/s^2
RM = 1.57e-3           # 1/mass, 1/slug (the book's constant: m = 636.94 slug)
XCGR = 0.35            # reference CG (fraction of cbar)
HE = 160.0             # engine angular momentum, slug ft^2/s (along body x)
JXX, JYY, JZZ, JXZ = 9496.0, 55814.0, 63100.0, 982.0   # slug ft^2
RTOD = 57.29578

ALPHA_GRID = np.arange(-10.0, 45.0 + 1e-9, 5.0)   # 12 points
EL_GRID = np.array([-24.0, -12.0, 0.0, 12.0, 24.0])
BABS_GRID = np.arange(0.0, 30.0 + 1e-9, 5.0)       # |beta| 0..30, 7 points
BETA_GRID = np.arange(-30.0, 30.0 + 1e-9, 10.0)    # beta -30..30, 7 points
ALT_GRID = np.arange(0.0, 50000.0 + 1e-9, 10000.0)  # 6 points
MACH_GRID = np.arange(0.0, 1.0 + 1e-9, 0.2)        # 6 points

CX = np.array(D.CX)          # [el, alpha]
CM = np.array(D.CM)
CZ = np.array(D.CZ)          # [alpha]
CL = np.array(D.CL)          # [|beta|, alpha]
CN = np.array(D.CN)
DLDA = np.array(D.DLDA)      # [beta, alpha]
DLDR = np.array(D.DLDR)
DNDA = np.array(D.DNDA)
DNDR = np.array(D.DNDR)
DAMP = np.array(D.DAMP)      # [coefficient, alpha]
T_IDLE = np.array(D.THRUST_IDLE)   # [mach, alt]
T_MIL = np.array(D.THRUST_MIL)
T_MAX = np.array(D.THRUST_MAX)


# --------------------------------------------------------------------------- interpolation
def _cell(u, grid, extrapolate):
    n = len(grid)
    if not extrapolate:
        u = min(max(u, grid[0]), grid[-1])
    k = int(np.searchsorted(grid, u, side="right")) - 1
    k = min(max(k, 0), n - 2)
    f = (u - grid[k]) / (grid[k + 1] - grid[k])
    return k, f


def interp1(u, grid, vals, extrapolate=True):
    k, f = _cell(u, grid, extrapolate)
    return (1 - f) * vals[k] + f * vals[k + 1]


def interp2(x, y, xgrid, ygrid, table, ex_x=True, ex_y=True):
    """table[iy, ix] at (xgrid[ix], ygrid[iy]); bilinear, extrapolated from the end cells."""
    j, fx = _cell(x, xgrid, ex_x)
    i, fy = _cell(y, ygrid, ex_y)
    lo = (1 - fx) * table[i, j] + fx * table[i, j + 1]
    hi = (1 - fx) * table[i + 1, j] + fx * table[i + 1, j + 1]
    return (1 - fy) * lo + fy * hi


# The book extrapolates every table linearly beyond its data. The bg-sim tables (the
# interp1/interp2 intrinsics) hold the edge value in alpha and beta instead; the elevator axis
# is extended to +-25 deg (the actuator limit) with the book's extrapolation, so in el both agree.
# `CLAMP_AB = True` reproduces the bg-sim model (design.py sets it for the scenario references).
CLAMP_AB = False


def cx(a, el):
    return interp2(a, el, ALPHA_GRID, EL_GRID, CX, not CLAMP_AB, True)


def cm(a, el):
    return interp2(a, el, ALPHA_GRID, EL_GRID, CM, not CLAMP_AB, True)


def cz(a, b, el):
    return interp1(a, ALPHA_GRID, CZ, not CLAMP_AB) * (1 - (b / 57.3) ** 2) - 0.19 * (el / 25.0)


def cy(b, ail, rdr):
    return -0.02 * b + 0.021 * (ail / 20.0) + 0.086 * (rdr / 30.0)


def cl(a, b):
    if b == 0:
        return 0.0
    return math.copysign(1.0, b) * interp2(a, abs(b), ALPHA_GRID, BABS_GRID, CL, not CLAMP_AB, not CLAMP_AB)


def cn(a, b):
    if b == 0:
        return 0.0
    return math.copysign(1.0, b) * interp2(a, abs(b), ALPHA_GRID, BABS_GRID, CN, not CLAMP_AB, not CLAMP_AB)


def dlda(a, b):
    return interp2(a, b, ALPHA_GRID, BETA_GRID, DLDA, not CLAMP_AB, not CLAMP_AB)


def dldr(a, b):
    return interp2(a, b, ALPHA_GRID, BETA_GRID, DLDR, not CLAMP_AB, not CLAMP_AB)


def dnda(a, b):
    return interp2(a, b, ALPHA_GRID, BETA_GRID, DNDA, not CLAMP_AB, not CLAMP_AB)


def dndr(a, b):
    return interp2(a, b, ALPHA_GRID, BETA_GRID, DNDR, not CLAMP_AB, not CLAMP_AB)


def damp(a):
    return np.array([interp1(a, ALPHA_GRID, DAMP[i], not CLAMP_AB) for i in range(9)])


# --------------------------------------------------------------------------- engine and air data
def tgear(thtl):
    return 64.94 * thtl if thtl <= 0.77 else 217.38 * thtl - 117.38


def rtau(dp):
    if dp <= 25.0:
        return 1.0
    if dp >= 50.0:
        return 0.1
    return 1.9 - 0.036 * dp


def pdot(p3, p1):
    if p1 >= 50.0:
        if p3 >= 50.0:
            t, p2 = 5.0, p1
        else:
            p2 = 60.0
            t = rtau(p2 - p3)
    else:
        if p3 >= 50.0:
            t, p2 = 5.0, 40.0
        else:
            p2 = p1
            t = rtau(p2 - p3)
    return t * (p2 - p3)


def thrust(power, alt, mach):
    """The book's THRUST: bilinear in (alt, Mach) per table, then blended on the power level.

    The book's index logic clamps the cell (alt 0..50000 ft, Mach 0..1) and extrapolates beyond it;
    `CLAMP_AB = True` holds the edge instead, like the bg-sim Lookup2D."""
    alt = max(alt, 0.01)
    ex = not CLAMP_AB
    tmil = interp2(alt, mach, ALT_GRID, MACH_GRID, T_MIL, ex, ex)
    if power < 50.0:
        tidl = interp2(alt, mach, ALT_GRID, MACH_GRID, T_IDLE, ex, ex)
        return tidl + (tmil - tidl) * power * 0.02
    tmax = interp2(alt, mach, ALT_GRID, MACH_GRID, T_MAX, ex, ex)
    return tmil + (tmax - tmil) * (power - 50.0) * 0.02


def adc(vt, alt):
    """The book's air-data computer: a troposphere fit (lapse 3.6 R per 1000 ft); 390 R above 35000 ft."""
    tfac = 1.0 - 0.703e-5 * alt
    t = 390.0 if alt >= 35000.0 else 519.0 * tfac
    rho = 2.377e-3 * tfac ** 4.14
    mach = vt / math.sqrt(1.4 * 1716.3 * t)
    qbar = 0.5 * rho * vt * vt
    return mach, qbar


# --------------------------------------------------------------------------- equations of motion
J_FRD = np.array([[JXX, 0.0, -JXZ], [0.0, JYY, 0.0], [-JXZ, 0.0, JZZ]])
J_FRD_INV = np.linalg.inv(J_FRD)


def _inertia_check():
    gam = JXX * JZZ - JXZ ** 2
    c3, c4, c9 = JZZ / gam, JXZ / gam, JXX / gam
    c7 = 1.0 / JYY
    return np.allclose([c3, c4, c7, c9], [1.055e-4, 1.642e-6, 1.792e-5, 1.587e-5], rtol=2e-3)


def coefficients(vt, a_deg, b_deg, p, q, r, el, ail, rdr, xcg):
    """Body-axis force and moment coefficients (CX, CY, CZ, Cl, Cm, Cn) with damping and CG shift."""
    cxt = cx(a_deg, el)
    cyt = cy(b_deg, ail, rdr)
    czt = cz(a_deg, b_deg, el)
    dail, drdr = ail / 20.0, rdr / 30.0
    clt = cl(a_deg, b_deg) + dlda(a_deg, b_deg) * dail + dldr(a_deg, b_deg) * drdr
    cmt = cm(a_deg, el)
    cnt = cn(a_deg, b_deg) + dnda(a_deg, b_deg) * dail + dndr(a_deg, b_deg) * drdr
    tvt = 0.5 / vt
    b2v = B_FT * tvt
    cq = CBAR_FT * q * tvt
    d = damp(a_deg)
    cxt += cq * d[0]
    cyt += b2v * (d[1] * r + d[2] * p)
    czt += cq * d[3]
    clt += b2v * (d[4] * r + d[5] * p)
    cmt += cq * d[6] + czt * (XCGR - xcg)
    cnt += b2v * (d[7] * r + d[8] * p) - cyt * (XCGR - xcg) * CBAR_FT / B_FT
    return cxt, cyt, czt, clt, cmt, cnt


def f16(x, u, xcg=0.35, book_constants=False):
    """State derivative of the book's 13-state model; also returns nz (g, at the CG, body -z)."""
    vt, alpha, beta, phi, theta, psi, p, q, r, pn, pe, alt, power = x
    thtl, el, ail, rdr = u
    mach, qbar = adc(vt, alt)
    xd = np.zeros(13)
    xd[12] = pdot(power, tgear(thtl))
    t = thrust(power, alt, mach)
    a_deg, b_deg = alpha * RTOD, beta * RTOD
    cxt, cyt, czt, clt, cmt, cnt = coefficients(vt, a_deg, b_deg, p, q, r, el, ail, rdr, xcg)

    cb = math.cos(beta)
    uu = vt * math.cos(alpha) * cb
    vv = vt * math.sin(beta)
    ww = vt * math.sin(alpha) * cb
    sth, cth = math.sin(theta), math.cos(theta)
    sph, cph = math.sin(phi), math.cos(phi)
    spsi, cpsi = math.sin(psi), math.cos(psi)
    qs = qbar * S_FT2
    ax = RM * (qs * cxt + t)
    ay = RM * qs * cyt
    az = RM * qs * czt
    udot = r * vv - q * ww - G_FT * sth + ax
    vdot = p * ww - r * uu + G_FT * cth * sph + ay
    wdot = q * uu - p * vv + G_FT * cth * cph + az
    dum = uu * uu + ww * ww
    xd[0] = (uu * udot + vv * vdot + ww * wdot) / vt
    xd[1] = (uu * wdot - ww * udot) / dum
    xd[2] = (vt * vdot - vv * xd[0]) * cb / dum
    xd[3] = p + (sth / cth) * (q * sph + r * cph)
    xd[4] = q * cph - r * sph
    xd[5] = (q * sph + r * cph) / cth
    w = np.array([p, q, r])
    mom = np.array([qs * B_FT * clt, qs * CBAR_FT * cmt, qs * B_FT * cnt])
    if book_constants:   # the book's rounded c1..c9 (only to show the check to all its digits)
        c1, c2, c3, c4, c5, c6, c7, c8, c9 = -.770, .02755, 1.055e-4, 1.642e-6, .9604, 1.759e-2, 1.792e-5, -.7336, 1.587e-5
        qsb = qs * B_FT
        xd[6] = (c2 * p + c1 * r + c4 * HE) * q + qsb * (c3 * clt + c4 * cnt)
        xd[7] = (c5 * p - c7 * HE) * r + c6 * (r * r - p * p) + qs * CBAR_FT * c7 * cmt
        xd[8] = (c8 * p - c2 * r + c9 * HE) * q + qsb * (c4 * clt + c9 * cnt)
    else:
        h = J_FRD @ w + np.array([HE, 0.0, 0.0])
        xd[6:9] = J_FRD_INV @ (mom - np.cross(w, h))
    t1, t2, t3 = sph * cpsi, cph * sth, sph * spsi
    s1, s2 = cth * cpsi, cth * spsi
    s3, s4 = t1 * sth - cph * spsi, t3 * sth + cph * cpsi
    s5, s6 = sph * cth, t2 * cpsi + t3
    s7, s8 = t2 * spsi - t1, cph * cth
    xd[9] = uu * s1 + vv * s3 + ww * s6
    xd[10] = uu * s2 + vv * s4 + ww * s7
    xd[11] = uu * sth - vv * s5 - ww * s8
    nz = -az / G_FT          # load factor at the CG (1 g in level flight)
    return xd, nz


# Stevens & Lewis, 2nd ed., the check case of the F16 subroutine (Section 3.6): xcg = 0.4.
CHECK_X = [500.0, 0.5, -0.2, -1.0, 1.0, -1.0, 0.7, -0.8, 0.9, 1000.0, 900.0, 10000.0, 90.0]
CHECK_U = [0.9, 20.0, -15.0, -20.0]
CHECK_XCG = 0.4
CHECK_XD = [-75.23724, -0.8813491, -0.4759990, 2.505734, 0.3250820, 2.145926, 12.62679, 0.9649671,
            0.5809759, 342.4439, -266.7707, 248.1241, -58.68999]


if __name__ == "__main__":
    print("inertia constants match c3, c4, c7, c9:", _inertia_check())
    xd, _ = f16(np.array(CHECK_X), CHECK_U, CHECK_XCG, book_constants=True)
    for k, (a, b) in enumerate(zip(xd, CHECK_XD)):
        print(f"xd[{k:2d}] = {a:14.7g}   book {b:14.7g}   rel {abs(a - b) / abs(b):.2e}")
