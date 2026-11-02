"""The nonlinear DHC-2 'Beaver' model of FDC 1.4 (Rauw), an independent scipy implementation.

Written from the equations of the FDC Simulink library (see beaver_data.py for the sources), not from
FDC code. State and input vectors as in FDC's system BEAVER:

    x = [V alpha beta p q r psi theta phi xe ye H]      (m/s, rad, rad/s, m; body axes FRD)
    u = [de da dr df n pz]                               (rad, rpm, inches of mercury)

Wind is zero. The side force of beta-dot (CYbdot) is handled as FDC does: the aerodynamic model omits
it and the beta-dot equation is divided by 1 - cos(beta) rho b S CYbdot/(4 m) (FDC block xdotcorr);
V-dot and alpha-dot are not corrected (FDC's choice, kept here so the numbers match).

`xdot_ext` adds the drivetrain of the bg-sim model (our addition, not in the source): the crank and
propeller inertia J with the engine torque P/omega, a constant-speed propeller whose governor sets
the absorbed torque, and the thrust computed from the absorbed shaft power. With `drivetrain=0` the
thrust uses the source's algebraic power at the commanded rpm, exactly as FDC.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import fsolve

import beaver_data as D

A = D.AERO
PR = D.PROP
M = D.MASS
S, B, C = D.S_WING, D.SPAN, D.CBAR
IN = np.array([[D.IX, 0.0, -D.JXZ], [0.0, D.IY, 0.0], [-D.JXZ, 0.0, D.IZ]])
IN_INV = np.linalg.inv(IN)
RPM = 30.0 / math.pi          # rad/s -> rpm


# --------------------------------------------------------------------------- pieces
def atmosphere(H):
    a = D.ATMO
    T = a["T0"] - a["lapse"] * H
    g = a["g0"] * (a["Re"] / (a["Re"] + H)) ** 2
    ps = a["p0"] * (T / a["T0"]) ** (g / a["Rl"])
    rho = ps / (a["Rgas"] * T)
    return rho, ps, T, g


def engine_power_kw(pz, n, rho):
    """Engine power (kW) from the manifold pressure (inch Hg), engine speed (rpm) and density."""
    p = D.POWER
    return p["k"] * (p["c0"] + p["c1"] * (pz + p["pz0"]) * (n + p["n0"])
                     + (p["c2"] - p["c3"] * n) * (1.0 - rho / p["rho0"]))


def dpt_of(P_kw, rho, V):
    return D.DPT_C1 + D.DPT_C2 * P_kw / (0.5 * rho * V ** 3)


def aero_coeffs(V, alpha, beta, p, q, r, de, da, dr, df):
    """[CX CY CZ Cl Cm Cn] of the airframe (without the beta-dot term)."""
    ph, qh, rh = p * B / (2 * V), q * C / V, r * B / (2 * V)
    a, b = alpha, beta
    CX = (A["CX0"] + A["CXa"] * a + A["CXa2"] * a ** 2 + A["CXa3"] * a ** 3 + A["CXq"] * qh
          + A["CXdr"] * dr + A["CXdf"] * df + A["CXadf"] * a * df)
    CY = (A["CY0"] + A["CYb"] * b + A["CYp"] * ph + A["CYr"] * rh + A["CYda"] * da
          + A["CYdr"] * dr + A["CYdra"] * dr * a)
    CZ = (A["CZ0"] + A["CZa"] * a + A["CZa3"] * a ** 3 + A["CZq"] * qh + A["CZde"] * de
          + A["CZdeb2"] * de * b ** 2 + A["CZdf"] * df + A["CZadf"] * a * df)
    Cl = (A["Cl0"] + A["Clb"] * b + A["Clp"] * ph + A["Clr"] * rh + A["Clda"] * da
          + A["Cldr"] * dr + A["Cldaa"] * da * a)
    Cm = (A["Cm0"] + A["Cma"] * a + A["Cma2"] * a ** 2 + A["Cmq"] * qh + A["Cmde"] * de
          + A["Cmb2"] * b ** 2 + A["Cmr"] * rh + A["Cmdf"] * df)
    Cn = (A["Cn0"] + A["Cnb"] * b + A["Cnp"] * ph + A["Cnr"] * rh + A["Cnda"] * da
          + A["Cndr"] * dr + A["Cnq"] * qh + A["Cnb3"] * b ** 3)
    return np.array([CX, CY, CZ, Cl, Cm, Cn])


def prop_coeffs(alpha, dpt):
    return np.array([PR["CXdpt"] * dpt + PR["CXadpt2"] * alpha * dpt ** 2, 0.0, PR["CZdpt"] * dpt,
                     PR["Cla2dpt"] * alpha ** 2 * dpt, PR["Cmdpt"] * dpt, PR["Cndpt3"] * dpt ** 3])


def kbdot(rho, beta):
    """The beta-dot correction factor term: cos(beta) rho b S CYbdot / (4 m)."""
    return math.cos(beta) * rho * B * S * A["CYbdot"] / (4.0 * M)


def forces(x, u, P_kw=None):
    """Body forces (N, FRD) and moments (N m) without gravity, plus air data. P_kw overrides the
    engine power that drives dpt (the drivetrain's shaft power)."""
    V, alpha, beta, p, q, r = x[:6]
    H = x[11]
    de, da, dr, df, n, pz = u[:6]
    rho, ps, T, g = atmosphere(H)
    qd = 0.5 * rho * V * V
    if P_kw is None:
        P_kw = engine_power_kw(pz, n, rho)
    dpt = dpt_of(P_kw, rho, V)
    Ct = aero_coeffs(V, alpha, beta, p, q, r, de, da, dr, df) + prop_coeffs(alpha, dpt)
    F = qd * S * Ct[:3]
    Mo = qd * S * np.array([B * Ct[3], C * Ct[4], B * Ct[5]])
    return F, Mo, {"rho": rho, "g": g, "qd": qd, "P": P_kw, "dpt": dpt, "T": T, "ps": ps}


def xdot(x, u, P_kw=None):
    V, alpha, beta, p, q, r, psi, theta, phi = x[:9]
    F, Mo, ad = forces(x, u, P_kw)
    g = ad["g"]
    Fx = F[0] - M * g * math.sin(theta)
    Fy = F[1] + M * g * math.cos(theta) * math.sin(phi)
    Fz = F[2] + M * g * math.cos(theta) * math.cos(phi)
    ca, sa, cb, sb, tb = math.cos(alpha), math.sin(alpha), math.cos(beta), math.sin(beta), math.tan(beta)
    Vd = (Fx * ca * cb + Fy * sb + Fz * sa * cb) / M
    ad_ = (-Fx * sa + Fz * ca) / (M * V * cb) - tb * (p * ca + r * sa) + q
    bd = (-Fx * ca * sb + Fy * cb - Fz * sa * sb) / (M * V) + p * sa - r * ca
    bd = bd / (1.0 - kbdot(ad["rho"], beta))
    w = np.array([p, q, r])
    wd = IN_INV @ (Mo - np.cross(w, IN @ w))
    sphi, cphi, sth, cth = math.sin(phi), math.cos(phi), math.sin(theta), math.cos(theta)
    phid = p + math.tan(theta) * (q * sphi + r * cphi)
    thd = q * cphi - r * sphi
    psid = (q * sphi + r * cphi) / cth
    ub, vb, wb = V * ca * cb, V * sb, V * sa * cb
    spsi, cpsi = math.sin(psi), math.cos(psi)
    t1 = ub * cth + (vb * sphi + wb * cphi) * sth
    t2 = vb * cphi - wb * sphi
    xed = t1 * cpsi - t2 * spsi
    yed = t1 * spsi + t2 * cpsi
    Hd = ub * sth - (vb * sphi + wb * cphi) * cth
    return np.array([Vd, ad_, bd, wd[0], wd[1], wd[2], psid, thd, phid, xed, yed, Hd])


# --------------------------------------------------------------------------- trim and linearisation
def theta_of(alpha, beta, phi, gamma):
    """FDC acconstr.m: the pitch angle for a given flight-path angle (wings level or banked)."""
    a = math.cos(alpha) * math.cos(beta)
    b = math.sin(phi) * math.sin(beta) + math.cos(phi) * math.sin(alpha) * math.cos(beta)
    sg = math.sin(gamma)
    return math.atan((a * b + sg * math.sqrt(a * a - sg * sg + b * b)) / (a * a - sg * sg))


def trim(V, H, n=1800.0, df=0.0, gamma=0.0, guess=None):
    """Steady wings-level flight (FDC ACTRIM, 'steady-state wings-level flight', phi = 0,
    zero rates): solve the six force/moment equations for alpha, beta, de, da, dr, pz."""

    def build(v):
        al, be, de, da, dr, pz = v
        th = theta_of(al, be, 0.0, gamma)
        x = np.array([V, al, be, 0, 0, 0, 0, th, 0, 0, 0, H], dtype=float)
        u = np.array([de, da, dr, df, n, pz], dtype=float)
        return x, u

    def res(v):
        x, u = build(v)
        return xdot(x, u)[:6] * np.array([1, 10, 10, 10, 10, 10])

    v0 = guess if guess is not None else [0.14, -0.015, -0.04, 0.01, -0.045, 21.0]
    v = fsolve(res, v0, xtol=1e-13)
    for _ in range(3):   # polish with Newton steps on a central-difference Jacobian
        Jm = jacobian(res, v, np.full(6, 1e-7))
        v = v - np.linalg.solve(Jm, res(v))
    x, u = build(v)
    assert np.max(np.abs(xdot(x, u)[:6])) < 1e-10
    return x, u


def jacobian(f, z0, h):
    z0 = np.asarray(z0, dtype=float)
    f0 = f(z0)
    J = np.zeros((len(f0), len(z0)))
    for k in range(len(z0)):
        dz = np.zeros_like(z0)
        dz[k] = h[k]
        J[:, k] = (f(z0 + dz) - f(z0 - dz)) / (2 * h[k])
    return J


XH = np.array([1e-4, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6, 1e-3, 1e-3, 1e-3])
UH = np.array([1e-6, 1e-6, 1e-6, 1e-6, 1e-3, 1e-5])


def linearise(x0, u0):
    Am = jacobian(lambda x: xdot(x, u0), x0, XH)
    Bm = jacobian(lambda u: xdot(x0, u), u0, UH)
    return Am, Bm


LON = [0, 1, 4, 7]   # V alpha q theta
LAT = [2, 3, 5, 8]   # beta p r phi


def modes(Am):
    """Decoupled longitudinal [V a q th] and lateral [b p r phi] eigenvalues, as THESIS Table 5-3."""
    lon = np.linalg.eigvals(Am[np.ix_(LON, LON)])
    lat = np.linalg.eigvals(Am[np.ix_(LAT, LAT)])
    return classify(lon, lat)


def classify(lon, lat):
    lon_c = sorted([e for e in lon if e.imag > 0], key=lambda e: abs(e))
    lat_c = [e for e in lat if e.imag > 0]
    lat_r = sorted([e.real for e in lat if abs(e.imag) < 1e-12])
    return {"phugoid": complex(lon_c[0]), "short_period": complex(lon_c[1]),
            "dutch_roll": complex(lat_c[0]), "roll": float(lat_r[0]), "spiral": float(lat_r[1])}


def mode_props(lam):
    lam = complex(lam)
    wn = abs(lam)
    if abs(lam.imag) < 1e-12:
        return {"lambda": lam.real, "T_half": -math.log(2) / lam.real if lam.real < 0 else None}
    return {"re": lam.real, "im": lam.imag, "wn": wn, "zeta": -lam.real / wn, "period": 2 * math.pi / lam.imag,
            "T_half": -math.log(2) / lam.real}


# --------------------------------------------------------------------------- the drivetrain (ours)
# Constant-speed propeller on the R-985 crank. Not in the source: FDC takes the rpm as an input and
# the power as algebraic. J and the governor are our assumptions (see the README).
DRIVE = {
    "J": 12.0,          # kg m^2, crank + Hamilton Standard two-blade propeller (assumed)
    "D": 2.59,          # m, propeller diameter [REP Table C.1]
    "wn": 2.0,          # rad/s, governor loop natural frequency (design target)
    "zeta": 0.7,        # governor loop damping (design target)
}


def drive_gains(x0, u0):
    """Governor gains (Kp, Ki on the relative speed error, in units of the torque coefficient) that
    place the linearised shaft-speed loop at wn, zeta at the operating point (x0, u0)."""
    rho = atmosphere(x0[11])[0]
    n_rpm, pz = u0[4], u0[5]
    w0 = n_rpm / RPM
    P0 = 1000.0 * engine_power_kw(pz, n_rpm, rho)
    dPdw = 1000.0 * (engine_power_kw(pz, n_rpm + 1e-3, rho) - engine_power_kw(pz, n_rpm - 1e-3, rho)) / 2e-3 * RPM
    dTe = dPdw / w0 - P0 / w0 ** 2
    Q0 = P0 / w0
    kQ = rho * (w0 / (2 * math.pi)) ** 2 * DRIVE["D"] ** 5     # dQ/dCq
    J = DRIVE["J"]
    wn, z = DRIVE["wn"], DRIVE["zeta"]
    # J dw' = dTe dw - (2 Q0/w0) dw - kQ (Kp dw/w0 + ci),  ci' = Ki dw/w0
    Kp = (2 * z * wn * J + dTe - 2 * Q0 / w0) * w0 / kQ
    Ki = J * wn ** 2 * w0 / kQ
    return {"Kp": Kp, "Ki": Ki, "Cq0": Q0 / kQ, "kQ0": kQ, "w0": w0, "Q0": Q0, "P0": P0}


def prop_torque(Cq, rho, w):
    return Cq * rho * (w / (2 * math.pi)) ** 2 * DRIVE["D"] ** 5


def xdot_ext(z, u, gov, drivetrain=1):
    """14 states: x (12), omega (rad/s), ci (governor integrator, torque coefficient).
    u = [de da dr df n_cmd pz]. With drivetrain=0 the thrust comes from the source's power at n_cmd."""
    x, w, ci = z[:12], z[12], z[13]
    rho = atmosphere(x[11])[0]
    n_cmd, pz = u[4], u[5]
    e = (w - n_cmd / RPM) / (n_cmd / RPM)
    Cq = ci + gov["Kp"] * e
    Q = prop_torque(Cq, rho, w)
    Te = 1000.0 * engine_power_kw(pz, w * RPM, rho) / w
    P_shaft = Q * w / 1000.0
    xd = xdot(x, u, P_kw=P_shaft if drivetrain else None)
    return np.concatenate([xd, [(Te - Q) / DRIVE["J"], gov["Ki"] * e]])
