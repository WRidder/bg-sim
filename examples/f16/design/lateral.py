"""Lateral-directional fly-by-wire design of the `f16-sim` model (roll and yaw axes).

Control law (the `LateralFBW` block; angles in deg, rates in deg/s, surfaces in deg):

    ps, rs  = stability-axis roll and yaw rate: ps = p cos(alpha) + r sin(alpha),
              rs = r cos(alpha) - p sin(alpha)  (vv_roll = 1; body axes p, r with vv_roll = 0)
    p_lim   = P_MAX clamp(qbar/QBAR_FULL, 0.3, 1) clamp(1 - 0.075 (nz - 1), 0.4, 1)
    p_cmd   = p_lim stick_roll
    ail     = Kp (ps - 0.5 p_cmd) + xi_p,       xi_p' = Kip (ps - p_cmd) + (sat(ail) - ail)/T_aw
    r_wo    = rs - xw,  xw' = r_wo/TAU_WO       (the washed-out yaw rate: zero in a steady turn)
    rdr     = K_ari(alpha) ail + Kr r_wo + Kb (beta - beta_cmd) + xi_b,
              xi_b' = Kib (beta - beta_cmd) + (sat(rdr) - rdr)/T_aw,   beta_cmd = -6 deg pedals

The design point grid is the pitch law's (qbar 80..1400 psf x Mach 0.2..1.0, `fbw.py`). At each
point, trimmed level at the (virtual) altitude where that Mach gives that qbar:

1. ARI. The aileron-rudder interconnect K_ari makes the angular acceleration of an aileron
   command point along the stability x axis, (r'/p') = tan(alpha):
       K_ari = (tan(a) L'da - N'da) / (N'dr - tan(a) L'dr)
   (primed: including the inertia coupling). The ratio of the NASA derivatives is the same at
   every dynamic pressure, so K_ari is a table over alpha only (Lookup1D), computed at beta = 0.
2. Roll. The stability-axis roll mode ps' = Lp ps + Ld ail_eff (ail_eff includes the ARI
   rudder) with the PI law has the characteristic polynomial s^2 - (Lp + Ld Kp) s - Ld Kip;
   Kp and Kip place it at W_ROLL, Z_ROLL. The gains fall as 1/qbar (Ld is proportional to qbar).
3. Yaw damper. With the roll law and the sideslip loop off, Kr is the smallest gain that gives
   the dutch roll ZETA_YD (or the most damping the washout loop can give).
4. Sideslip hold. Kb, Kib minimise the settling time of a sideslip command and the sideslip of a
   roll-rate step (turn coordination) with the dutch roll kept above ZETA_DR_MIN, on the full
   closed loop (airframe, servos, both laws).

`modes` evaluates the open loop, the yaw damper alone and the full law at a point for the
dutch-roll comparison; `sim3.linearise` checks the same numbers on the nonlinear closed loop.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.linalg import expm
from scipy.optimize import minimize

import f16_ref as F
import fbw
import sim3
from f16_lin import state13, trim_level

RTOD = 180.0 / math.pi
XCG = 0.38                       # the pitch law's design CG (the lateral axes barely depend on it)
W_ROLL, Z_ROLL = 4.0, 0.8        # rad/s, -: the PI roll loop (roll time constant about 0.3 s)
ZETA_YD = 0.6                    # dutch-roll damping of the yaw damper alone
ZETA_DR_MIN = 0.6                # the full law keeps the dutch roll at least this damped
ALPHA_GRID = [float(a) for a in F.ALPHA_GRID]   # -10 .. 45 deg
ARI_MIN, ARI_MAX = -1.0, 2.0     # deg of rudder per deg of aileron (the table is clamped to this)
W_ACT = sim3.ACT["ail"]["w"]


# --------------------------------------------------------------------------- linear models
def lat_model(vt, h, alpha, xcg=XCG, el=0.0, thtl=0.5, power=None, beta=0.0):
    """Open-loop lateral model at a trim: x = (beta, phi, p, r) in deg, deg/s; u = (ail, rdr) deg."""
    # table extrapolation as in fbw.py (the virtual design points leave the data)
    x0 = state13(vt, alpha, alpha, h, power if power is not None else F.tgear(thtl))
    x0[2] = beta
    u0 = [thtl, el, 0.0, 0.0]
    idx = [2, 3, 6, 8]
    A = np.zeros((4, 4))
    B = np.zeros((4, 2))
    for j, k in enumerate(idx):
        e = 1e-6
        xp, xm = x0.copy(), x0.copy()
        xp[k] += e
        xm[k] -= e
        A[:, j] = (F.f16(xp, u0, xcg)[0][idx] - F.f16(xm, u0, xcg)[0][idx]) / (2 * e)
    for j, k in enumerate((2, 3)):
        e = 1e-4
        up, um = list(u0), list(u0)
        up[k] += e
        um[k] -= e
        B[:, j] = (F.f16(x0, up, xcg)[0][idx] - F.f16(x0, um, xcg)[0][idx]) / (2 * e) * RTOD
    return A, B


def ari_table():
    """K_ari over the alpha grid from the control derivatives at beta = 0 (any qbar: the ratio)."""
    out = []
    for a in ALPHA_GRID:
        A, B = lat_model(500.0, 10000.0, a / RTOD)
        Lda, Ldr, Nda, Ndr = B[2, 0], B[2, 1], B[3, 0], B[3, 1]
        ta = math.tan(a / RTOD)
        k = (ta * Lda - Nda) / (Ndr - ta * Ldr)
        print(f"ari alpha {a:5.1f}: raw {k:.4f}")
        out.append(float(np.clip(k, ARI_MIN, ARI_MAX)))
    return out


def closed(A, B, alpha, g, k_ari, sw=(1.0, 1.0, 1.0, 1.0, 1.0)):
    """The lateral closed loop: z = (beta, phi, p, r, ail, rdr, xi_p, xi_b, xw); inputs
    (p_cmd, beta_cmd); outputs (ps, beta). `sw` = (roll_law, yaw_damper, beta_hold, ari, vv_roll)."""
    roll, yd, bh, ari, vv = sw
    ca = vv * math.cos(alpha) + (1 - vv)
    sa = vv * math.sin(alpha)
    n = 9
    Az = np.zeros((n, n))
    Bz = np.zeros((n, 2))
    Az[:4, :4] = A
    Az[:4, 4:6] = B
    # ps, rs as rows over z
    ps = np.zeros(n)
    ps[2], ps[3] = ca, sa
    rs = np.zeros(n)
    rs[2], rs[3] = -sa, ca
    beta = np.zeros(n)
    beta[0] = 1.0
    e = np.eye(n)
    # ail command = roll*Kp*(ps - kff pc) + xi_p
    ail_z = roll * g["Kp"] * ps + e[6]
    ail_w = np.array([-roll * g["Kp"] * sim3.KFF_P, 0.0])
    rwo_z = rs - e[8]
    rdr_z = ari * k_ari * ail_z + yd * g["Kr"] * rwo_z + bh * g["Kb"] * beta + e[7]
    rdr_w = ari * k_ari * ail_w + np.array([0.0, -bh * g["Kb"]])
    Az[4] = W_ACT * (ail_z - e[4])
    Bz[4] = W_ACT * ail_w
    Az[5] = W_ACT * (rdr_z - e[5])
    Bz[5] = W_ACT * rdr_w
    Az[6] = roll * g["Kip"] * ps
    Bz[6] = [-roll * g["Kip"], 0.0]
    Az[7] = bh * g["Kib"] * beta
    Bz[7] = [0.0, -bh * g["Kib"]]
    Az[8] = rwo_z / sim3.TAU_WO
    C = np.vstack([ps, beta, e[3], e[1]])      # ps, beta, r, phi
    return Az, Bz, C


dutch_roll = sim3.dutch_roll


def step(Az, Bz, C, j, t_end=4.0, dt=0.005):
    n = len(Az)
    M = np.zeros((n + 1, n + 1))
    M[:n, :n] = Az * dt
    M[:n, n] = Bz[:, j] * dt
    E = expm(M)
    Ad, Bd = E[:n, :n], E[:n, n]
    x = np.zeros(n)
    ys = []
    for _ in range(int(round(t_end / dt)) + 1):
        ys.append(C @ x)
        x = Ad @ x + Bd
    return np.arange(len(ys)) * dt, np.array(ys)


def metrics(t, y):
    yf = 1.0
    t10 = t[np.argmax(y >= 0.1 * yf)] if np.any(y >= 0.1 * yf) else np.inf
    t90 = t[np.argmax(y >= 0.9 * yf)] if np.any(y >= 0.9 * yf) else np.inf
    out = np.abs(y - yf) > 0.05
    ts = t[np.nonzero(out)[0][-1]] if np.any(out) else 0.0
    return {"rise": float(t90 - t10), "overshoot": float(max(0.0, y.max() - yf)), "settle": float(ts)}


# --------------------------------------------------------------------------- design at a point
def design_point(qbar_psf, mach, k_ari_fn, prev=None):
    vt, h = fbw.point_altitude(qbar_psf, mach)
    tr = trim_level(vt, h, XCG, guess=(0.3, -1.0, 0.05))
    a = tr["alpha"]
    A, B = lat_model(vt, h, a, el=tr["el"], thtl=tr["throttle"])
    k_ari = k_ari_fn(a * RTOD)
    # 2. roll loop on the stability-axis roll mode, with the ARI rudder in the aileron input
    ca, sa = math.cos(a), math.sin(a)
    T = np.array([[ca, sa], [-sa, ca]])               # (p, r) -> (ps, rs)
    Apr = T @ A[2:4, 2:4] @ T.T
    bd = T @ (B[2:4, 0] + k_ari * B[2:4, 1])
    Lp, Ld = Apr[0, 0], bd[0]
    # Where the airframe's own roll damping is above 2 Z_ROLL W_ROLL (high qbar), Kp comes out
    # negative: the loop takes some of that damping away to reach the same bandwidth.
    Kp = (-2.0 * Z_ROLL * W_ROLL - Lp) / Ld
    Kip = -W_ROLL ** 2 / Ld
    g = {"Kp": Kp, "Kip": Kip, "Kr": 0.0, "Kb": 0.0, "Kib": 0.0}
    # 3. yaw damper and sideslip loop together on the full closed loop (airframe, servos, roll law,
    #    ARI): the gains in units of the rudder's yaw effectiveness, z = K |N_dr|
    Ndr = (T @ B[2:4, 1])[1]                            # rs' per deg of rudder (negative)
    sc = 1.0 / abs(Ndr)

    def cost(z):
        g["Kr"], g["Kb"], g["Kib"] = z[0] * sc, z[1] * sc, z[2] * sc
        Az, Bz, C = closed(A, B, a, g, k_ari)
        if np.max(np.linalg.eigvals(Az).real) > 1e-6:   # the bank angle is neutral (rate command)
            return 1e3
        dr = dutch_roll(Az)
        t, yb = step(Az, Bz, C, 1, t_end=4.0, dt=0.01)
        iae = float(np.sum(np.abs(yb[:, 1] - 1.0)) * 0.01)
        t, yp = step(Az, Bz, C, 0, t_end=3.0, dt=0.01)
        coord = float(np.max(np.abs(yp[:, 1]))) * 100.0    # deg of beta per 100 deg/s of roll command
        pen = 0.0 if dr is None else 300.0 * max(0.0, ZETA_DR_MIN - dr["zeta"]) ** 2
        return iae + 0.3 * coord + pen + 1e-3 * float(np.dot(z, z))

    best = None
    for z0 in ([prev] if prev is not None else []) + [np.array(v, float) for v in ([5.0, -12.0, -10.0], [4.0, -4.0, -8.0], [3.0, -1.0, -4.0])]:
        res = minimize(cost, z0, method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-5, "maxiter": 800})
        if best is None or res.fun < best.fun:
            best = res
    res = best
    g["Kr"], g["Kb"], g["Kib"] = res.x[0] * sc, res.x[1] * sc, res.x[2] * sc
    return g, res.x, {"vt": vt, "h": h, "alpha_deg": a * RTOD, "A": A, "B": B, "k_ari": k_ari, "tr": tr}


def modes(info, g):
    """Dutch roll: open loop, yaw damper alone, full law; roll and sideslip step metrics."""
    A, B, a, k = info["A"], info["B"], info["tr"]["alpha"], info["k_ari"]
    out = {"open_loop": dutch_roll(A),
           "yaw_damper": dutch_roll(closed(A, B, a, g, k, (0.0, 1.0, 0.0, 0.0, 1.0))[0]),
           "full": dutch_roll(closed(A, B, a, g, k)[0])}
    Az, Bz, C = closed(A, B, a, g, k)
    t, y = step(Az, Bz, C, 0, t_end=3.0)
    out["roll_step"] = {**metrics(t, y[:, 0]), "beta_per_100": float(np.max(np.abs(y[:, 1]))) * 100.0}
    t, y = step(Az, Bz, C, 1, t_end=6.0)
    out["beta_step"] = metrics(t, y[:, 1])
    out["max_real"] = float(np.max(np.linalg.eigvals(Az).real))
    return out


def design(_design):
    F.CLAMP_AB = False
    ari = ari_table()
    k_ari_fn = lambda a_deg: F.interp1(a_deg, np.array(ALPHA_GRID), np.array(ari), False)  # noqa: E731
    tables = {k: [] for k in ("Kp", "Kip", "Kr", "Kb", "Kib")}
    pts = []
    for qb in fbw.QBAR_PSF:
        rows = {k: [] for k in tables}
        prev = None
        for m in fbw.MACH:
            g, prev, info = design_point(qb, m, k_ari_fn, prev)
            for k in tables:
                rows[k].append(float(g[k]))
            md = modes(info, g)
            pts.append({"qbar_psf": qb, "mach": m, "alpha_deg": info["alpha_deg"], **{k: float(v) for k, v in g.items()},
                        "k_ari": info["k_ari"], **md})
            print(f"lat {qb:6.0f} psf M{m:.1f} a {info['alpha_deg']:6.2f}: Kp {g['Kp']:.4f} Kip {g['Kip']:.4f} "
                  f"Kr {g['Kr']:.4f} Kb {g['Kb']:.4f} Kib {g['Kib']:.4f} | DR ol {md['open_loop']['zeta']:.3f} "
                  f"yd {md['yaw_damper']['zeta']:.3f} full {md['full']['zeta'] if md['full'] else float('nan'):.3f} | "
                  f"roll rise {md['roll_step']['rise']:.3f} os {md['roll_step']['overshoot']:.3f} "
                  f"b/100 {md['roll_step']['beta_per_100']:.3f} | beta settle {md['beta_step']['settle']:.2f} "
                  f"os {md['beta_step']['overshoot']:.3f} | max re {md['max_real']:.3f}")
        for k in tables:
            tables[k].append(rows[k])
    psf = 47.88025898033584
    return {"qbar_psf": fbw.QBAR_PSF, "qbar_pa": [q * psf for q in fbw.QBAR_PSF], "mach": fbw.MACH,
            **tables, "ari_alpha": ALPHA_GRID, "ari": ari, "points": pts, "xcg_design": XCG,
            "w_roll": W_ROLL, "z_roll": Z_ROLL, "zeta_yd": ZETA_YD, "zeta_dr_min": ZETA_DR_MIN,
            "p_max": sim3.P_MAX, "qbar_full": sim3.QBAR_FULL, "fq_min": sim3.FQ_MIN, "kn": sim3.KN,
            "fn_min": sim3.FN_MIN, "beta_per_pedal": sim3.BETA_PER_PEDAL, "tau_wo": sim3.TAU_WO,
            "kff_p": sim3.KFF_P, "act": sim3.ACT}


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    out = design(None)
    print("ARI", np.round(out["ari"], 3))
    Path(sys.argv[1] if len(sys.argv) > 1 else "lat.json").write_text(json.dumps(out, indent=1, default=float))
