"""Fly-by-wire design: a gain-scheduled pitch-rate / g-command law for the aft-CG F-16.

Control law (angles in deg, rates in deg/s, elevator in deg; the bg-sim `PitchFBW` block):

    q_stick = (g0/Vt) (nz_stick - cos(gamma) cos(phi)) * 180/pi       g-command: stick -> nz -> q
    q_cmd   = min(q_stick, q_alpha_lim, q_g_lim)        (limiter on; q_stick alone when off)
    u       = Ka alpha + Kq (q - Kff q_cmd) + xi,    dxi/dt = Ki (q - q_cmd) + (sat(u) - u)/T_aw

Ka, Kq, Ki are LQR gains on the short-period model (alpha, q) plus the integral of the pitch-rate
error, computed at every point of a (qbar, Mach) grid. Half of the command also goes straight into
the proportional path (Kff = 0.5): the integrator alone would have to fight the alpha feedback for
every change of the trimmed alpha, and the pitch-rate response would take seconds. The control weight is normalised by the
elevator's pitch effectiveness M_delta at that point, so the weights mean the same thing over the
whole envelope and the gains fall roughly as 1/qbar: the classic dynamic-pressure schedule. The
airframe is the aft-CG one (xcg = 0.38, statically unstable).

The book's aerodynamic data have no Mach effects; the Mach dependence of the gains is real all
the same: at a fixed dynamic pressure a higher Mach means a higher true airspeed, and the lift
and damping terms of the short period scale with qbar/Vt (the unstable pole grows with Mach).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.linalg import expm, solve_continuous_are

import f16_ref as F
from f16_lin import linearise, trim_level

RTOD = 180.0 / math.pi
XCG_DESIGN = 0.38
Q_W = (0.1, 0.5, 30.0)    # LQR state weights: alpha (deg), q (deg/s), integral of q error (deg)
R_REF = 6.0               # control weight R = (M_delta / R_REF)^2, M_delta in (deg/s^2)/deg
QBAR_PSF = [80.0, 200.0, 400.0, 800.0, 1400.0]
MACH = [0.2, 0.4, 0.6, 0.8, 1.0]
A_SL = math.sqrt(1.4 * 1716.3 * 519.0)    # ft/s, the book's sea-level speed of sound

# Actuator (Stevens & Lewis: 20.2 rad/s lag, +-25 deg, +-60 deg/s)
ACT_W, ACT_POS, ACT_RATE = 20.2, 25.0, 60.0
T_AW = 0.1           # s, anti-windup back-calculation time constant
# Limiter
ALPHA_MAX = 25.0     # deg
NZ_MAX = 9.0         # g
K_ALIM = 3.0         # (deg/s)/deg: q_alpha_lim = K_ALIM (ALPHA_MAX - alpha)
K_GLIM = 4.0         # (deg/s)/g: q_g_lim = q(nz_max) + K_GLIM (NZ_MAX - nz)
NZ_PER_STICK = 10.0  # g per unit stick: full aft stick asks for 11 g, more than the 9 g limit
KFF = 0.5            # share of q_cmd in the proportional path


def point_altitude(qbar_psf, mach):
    """The (virtual) altitude in the book's atmosphere where Mach `mach` gives dynamic pressure
    `qbar_psf` (below sea level for low-Mach, high-qbar points: the formula is just extended)."""
    vt = mach * A_SL
    rho = 2.0 * qbar_psf / (vt * vt)
    tfac = (rho / 2.377e-3) ** (1.0 / 4.14)
    return vt, (1.0 - tfac) / 0.703e-5


def short_period(qbar_psf, mach, xcg=XCG_DESIGN):
    vt, h = point_altitude(qbar_psf, mach)
    tr = trim_level(vt, h, xcg, guess=(0.3, -1.0, 0.05))
    A6, B6 = linearise(tr)
    i = [1, 3]                  # alpha, q of (Vt, alpha, theta, q, h, pow)
    A = A6[np.ix_(i, i)]        # in deg and deg/s A is unchanged (both states scale alike)
    Bm = B6[i, 0:1] * RTOD      # (deg/s) per deg of elevator
    return A, Bm, tr


def gains_at(qbar_psf, mach, xcg=XCG_DESIGN):
    A, Bm, tr = short_period(qbar_psf, mach, xcg)
    Aa = np.zeros((3, 3))
    Aa[:2, :2] = A
    Aa[2, 1] = 1.0              # z' = q - q_cmd
    Ba = np.vstack([Bm, [[0.0]]])
    R = np.array([[(Bm[1, 0] / R_REF) ** 2]])
    P = solve_continuous_are(Aa, Ba, np.diag(Q_W), R)
    k = np.linalg.solve(R, Ba.T @ P)[0]               # u = -k x
    return {"Ka": float(-k[0]), "Kq": float(-k[1]), "Ki": float(-k[2]), "M_delta": float(Bm[1, 0]),
            "alpha_trim_deg": tr["alpha"] * RTOD, "el_trim": tr["el"],
            "open_loop": [[complex(l).real, complex(l).imag] for l in np.linalg.eigvals(A)]}


def closed_loop(qbar_psf, mach, xcg, g):
    """Full 6-state linear model + actuator lag + the law. Returns (A, B, C) with the input q_cmd
    (deg/s) and the output q (deg/s)."""
    vt, h = point_altitude(qbar_psf, mach)
    tr = trim_level(vt, h, xcg, guess=(0.3, -1.0, 0.05))
    A6, B6 = linearise(tr)
    n = 8      # Vt, alpha, theta, q, h, pow, el (actuator), xi
    A = np.zeros((n, n))
    A[:6, :6] = A6
    A[:6, 6] = B6[:, 0]
    A[6, 1] = ACT_W * g["Ka"] * RTOD
    A[6, 3] = ACT_W * g["Kq"] * RTOD
    A[6, 7] = ACT_W
    A[6, 6] = -ACT_W
    A[7, 3] = g["Ki"] * RTOD
    B = np.zeros(n)
    B[7] = -g["Ki"]
    B[6] = -ACT_W * g["Kq"] * KFF
    C = np.zeros(n)
    C[3] = RTOD
    return A, B, C


def step_metrics(A, B, C, t_end=4.0, dt=0.002):
    n = len(B)
    M = np.zeros((n + 1, n + 1))
    M[:n, :n] = A * dt
    M[:n, n] = B * dt
    E = expm(M)
    Ad, Bd = E[:n, :n], E[:n, n]
    x = np.zeros(n)
    ys = []
    for _ in range(int(t_end / dt) + 1):
        ys.append(C @ x)
        x = Ad @ x + Bd
    y = np.array(ys)
    t = np.arange(len(y)) * dt
    t10 = t[np.argmax(y >= 0.1)]
    t90 = t[np.argmax(y >= 0.9)]
    return {"rise": float(t90 - t10), "overshoot": float(max(y.max() - 1.0, 0.0)), "y_end": float(y[-1])}


def design(_design):
    table = {"Ka": [], "Kq": [], "Ki": []}
    metrics = []
    worst = -1e9
    for qb in QBAR_PSF:
        rows = {k: [] for k in table}
        for m in MACH:
            gg = gains_at(qb, m)
            for k in table:
                rows[k].append(gg[k])
            A, B, C = closed_loop(qb, m, XCG_DESIGN, gg)
            ev = np.linalg.eigvals(A)
            fast = [e for e in ev if abs(e) > 0.05]   # the height mode sits at ~0 whatever the law does
            worst = max(worst, max(e.real for e in fast))
            sm = step_metrics(A, B, C)
            metrics.append({"qbar_psf": qb, "mach": m, **sm, "max_real": float(max(e.real for e in fast)),
                            "Ka": gg["Ka"], "Kq": gg["Kq"], "Ki": gg["Ki"], "open_loop": gg["open_loop"]})
        for k in table:
            table[k].append(rows[k])
    rises = [mm["rise"] for mm in metrics]
    overs = [mm["overshoot"] for mm in metrics]
    print(f"fbw: gains on {len(QBAR_PSF)}x{len(MACH)} points; worst closed-loop real part {worst:.3f}; "
          f"q step rise {min(rises):.3f}..{max(rises):.3f} s, overshoot {min(overs):.3f}..{max(overs):.3f}")
    psf = 47.88025898033584
    return {
        "q_weights": list(Q_W), "r_ref": R_REF, "xcg_design": XCG_DESIGN,
        "qbar_psf": QBAR_PSF, "qbar_pa": [q * psf for q in QBAR_PSF], "mach": MACH,
        "Ka": table["Ka"], "Kq": table["Kq"], "Ki": table["Ki"], "metrics": metrics,
        "act": {"w": ACT_W, "pos": ACT_POS, "rate": ACT_RATE}, "t_aw": T_AW,
        "limiter": {"alpha_max": ALPHA_MAX, "nz_max": NZ_MAX, "k_alim": K_ALIM, "k_glim": K_GLIM},
        "nz_per_stick": NZ_PER_STICK, "kff": KFF, "worst_real": worst,
    }


def gain(design_out, name, qbar_pa, mach):
    """The bg-sim Lookup2D: bilinear over (qbar, Mach), edge values held."""
    return F.interp2(qbar_pa, mach, np.array(design_out["qbar_pa"]), np.array(design_out["mach"]),
                     np.array(design_out[name]).T, False, False)
