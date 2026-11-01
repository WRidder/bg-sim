"""Analytic sizing of the suction gripper (no simulation).

* :func:`quasi_static` - per-cup loads of a rigid parcel on six linear bellows under gravity plus
  a steady acceleration (the exact 6 x 6 elastic statics, i.e. the model's linearisation), and
  :func:`bolt_group` - the hand formula (rigid parcel, equal cups, axial couple only).
* :func:`a_max` - the largest steady acceleration with ``max U <= 1/S`` for a yaw and a tilt gain.
* :func:`operating_vacuum` - where the generator curve meets the leak demand of the cups.
* :func:`pickup` - vacuum build-up after the valve opens (the same lumped equations as the model).
"""

from __future__ import annotations

import math

import numpy as np

import params as P

C = P.CUP
S = P.SUPPLY


def rot_y(t: float) -> np.ndarray:
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(t: float) -> np.ndarray:
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def cup_points(parcel: dict = P.PARCEL, cups=P.CUPS) -> np.ndarray:
    """Attach points relative to the centre of mass, gripper/parcel frame (z up)."""
    return np.array([[x - parcel["cx"], y - parcel["cy"], parcel["H_p"] / 2 - parcel["cz"]] for x, y in cups])


def specific_force(a_x: float, a_z: float, psi: float, theta: float) -> np.ndarray:
    """The force per unit mass the cups must apply, (a - g), in the gripper frame G."""
    f_world = np.array([a_x, 0.0, a_z + P.G0])
    rg = rot_y(theta) @ rot_z(psi)
    return rg.T @ f_world


def bottoming(ext: float, cup: dict = C) -> tuple[float, float]:
    """Bottoming push F_bot and its slope dF_bot/d(-ext) of the stdlib SuctionCup law."""
    xo = -ext - cup.get("s_bot", 0.01)
    root = math.sqrt(xo * xo + 1.0e-12)
    xb, dxb = 0.5 * (xo + root), 0.5 * (1 + xo / root)
    kb, nb, xr = cup.get("k_bot", 0.0), cup.get("n_bot", 3.0), cup.get("x_bot", 1.0e-3)
    return kb * xb * (xb / xr) ** (nb - 1), nb * kb * (xb / xr) ** (nb - 1) * dxb


def operating_cup(dp: float, t_ax: float, cup: dict = C) -> dict:
    """The cup linearised about a static hold at vacuum ``dp`` with axial pull ``t_ax`` (N).

    The stdlib SuctionCup law is k_ax ext + A_fold dp - F_bot(ext) = T (lift stroke, bottoming),
    and its lateral and tilt stiffness carry kf = (1 + c_vac dp/p_atm) exp(-c_ext ext/L0). Returns
    the cup with the tangent stiffnesses k_ax, k_lat, k_tilt at that point plus ``ext`` and ``kf``.
    """
    def law(e):
        return cup["k_ax"] * e + cup.get("A_fold", 0.0) * dp - bottoming(e, cup)[0]

    lo, hi = -cup["L0"], cup["L0"]
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if law(mid) < t_ax else (lo, mid)
    ext = 0.5 * (lo + hi)
    kf = (1 + cup.get("c_vac", 0.0) * dp / P.P_ATM) * math.exp(-cup.get("c_ext", 0.0) * ext / cup["L0"])
    return {**cup, "k_ax": cup["k_ax"] + bottoming(ext, cup)[1], "k_lat": cup["k_lat"] * kf,
            "k_tilt": cup["k_tilt"] * kf, "ext": ext, "kf": kf}


def quasi_static(a_x: float, a_z: float = 0.0, psi: float = 0.0, theta: float = 0.0,
                 dp: float = S["dp_max"], parcel: dict = P.PARCEL, cup: dict = C, cups=P.CUPS) -> dict:
    """Per-cup loads from the elastic statics of the bellows, linearised about the static hold.

    Unknowns: the parcel's translation u and small rotation phi relative to the gripper (G frame).
    Cup i at r_i (from the CoM) deflects d_i = u + phi x r_i and pushes -K d_i (K = diag(k_lat,
    k_lat, k_ax)) plus a moment -diag(k_tilt, k_tilt, k_tor) phi. The sum of the cup forces is
    m f (f = a - g in G) and their moment about the CoM is zero (no angular acceleration). The
    nonlinear bellows enter through their tangent stiffnesses at the hanging parcel (vacuum dp,
    T = m g / N per cup; :func:`operating_cup`).
    """
    r = cup_points(parcel, cups)
    m = parcel["m_p"]
    cup = operating_cup(dp, m * P.G0 / len(cups), cup)
    kd = np.diag([cup["k_lat"], cup["k_lat"], cup["k_ax"]])
    kr = np.diag([cup["k_tilt"], cup["k_tilt"], cup.get("k_tor", 5.0)])
    stiff = np.zeros((6, 6))
    for ri in r:
        h = np.array([[0, -ri[2], ri[1]], [ri[2], 0, -ri[0]], [-ri[1], ri[0], 0]])  # hat(r)
        # d = u - hat(r) phi ; force on parcel F = -K d ; moment r x F
        jac = np.hstack([np.eye(3), -h])
        stiff[:3] += kd @ jac
        stiff[3:] += h @ kd @ jac
        stiff[3:, 3:] += kr
    load = np.concatenate([m * specific_force(a_x, a_z, psi, theta), np.zeros(3)])
    # F_cups = -stiff x = load
    x = np.linalg.solve(-stiff, load)
    u, phi = x[:3], x[3:]
    out = {"T": [], "F_lat": [], "M": [], "U": []}
    fcap = cup["A_eff"] * dp
    for ri in r:
        d = u + np.cross(phi, ri)
        f = -kd @ d
        mom = cup["k_tilt"] * math.hypot(phi[0], phi[1])
        t_ax, f_lat = f[2], math.hypot(f[0], f[1])
        out["T"].append(t_ax)
        out["F_lat"].append(f_lat)
        out["M"].append(mom)
        out["U"].append((t_ax + 4 * mom / cup["D_lip"] + f_lat / cup["mu"]) / fcap)
    out = {k: np.array(v) for k, v in out.items()}
    out["phi"], out["u"], out["Fcap"] = phi, u, fcap
    return out


def bolt_group(a_x: float, psi: float = 0.0, theta: float = 0.0, dp: float = S["dp_max"],
               parcel: dict = P.PARCEL, cup: dict = C, cups=P.CUPS) -> dict:
    """Hand formula: equal shear m f_xy / N, axial share m f_z / N plus the linear couple that
    balances the moment m h f_xy of the shear about the CoM (h = cup plane above the CoM),
    T_i = m f_z/N + m h (f_xy . (Sigma^-1 rho_i)), Sigma = sum rho rho^T (rho_i = cup xy - centroid)."""
    m = parcel["m_p"]
    f = specific_force(a_x, 0.0, psi, theta)
    rho = np.array(cups, dtype=float)
    rho -= rho.mean(axis=0)
    sigma = rho.T @ rho
    n = len(cups)
    h = cup["L0"] * 0 + parcel["H_p"] / 2 - parcel["cz"]  # cup attach plane above the CoM
    beta = np.linalg.solve(sigma, f[:2]) * m * h
    t_ax = m * f[2] / n + rho @ beta
    f_lat = np.full(n, m * math.hypot(f[0], f[1]) / n)
    fcap = cup["A_eff"] * dp
    return {"T": t_ax, "F_lat": f_lat, "U": (t_ax + f_lat / cup["mu"]) / fcap, "Fcap": fcap}


def tilt_for(a_x: float, k_tilt: float, th_max: float = P.MOTION["th_max"]) -> float:
    cmd = k_tilt * math.atan(a_x / P.G0)
    return th_max * math.tanh(cmd / th_max) if k_tilt > 0 else 0.0


def a_max(psi: float = 0.0, k_tilt: float = 0.0, safety: float = P.SAFETY, dp: float = S["dp_max"],
          parcel: dict = P.PARCEL) -> float:
    """Largest steady acceleration along the path with max U <= 1/S (bisection)."""
    def worst(a):
        return quasi_static(a, 0.0, psi, tilt_for(a, k_tilt), dp=dp, parcel=parcel)["U"].max()

    if worst(0.0) > 1.0 / safety:
        return 0.0
    lo, hi = 0.0, 100.0
    if worst(hi) <= 1.0 / safety:
        return hi
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if worst(mid) <= 1.0 / safety else (lo, mid)
    return lo


# ------------------------------------------------------------------ pneumatics
def gen_flow(dp_m: float, dp_max: float = S["dp_max"], q_max: float = S["Q_max"], n: float = S["n_gen"]) -> float:
    x = dp_m / dp_max
    return q_max * (1 - x * abs(x) ** (n - 1))


def orifice(area: float, dp: float, p_tr: float = 500.0) -> float:
    """The regularised free-air orifice law of SuctionCup / CupValve (flow for a drop dp > 0)."""
    return 0.6 * area * dp * math.sqrt(2.0 / (P.RHO_AIR * math.sqrt(dp * dp + p_tr * p_tr)))


def cup_leak(dp_c: float, perm: float, a_lip: float = C["A_lip0"]) -> float:
    return perm * C["A_eff"] * dp_c + orifice(a_lip, dp_c)


def line_dp(q: float, a_line: float = S["A_line"], p_tr: float = 200.0) -> float:
    """Pressure drop of the line for the flow q: the orifice law inverted in closed form.

    With s = q / (Cd A): s^2 = 2 dP^2 / (rho sqrt(dP^2 + p_tr^2)), so u = dP^2 solves
    u^2 - c u - c p_tr^2 = 0, c = (rho s^2 / 2)^2."""
    s_ = q / (0.6 * a_line)
    c = (P.RHO_AIR * s_ * s_ / 2.0) ** 2
    u = 0.5 * (c + math.sqrt(c * c + 4.0 * c * p_tr * p_tr))
    return math.sqrt(u)


def operating_vacuum(perm: float, q_max: float = S["Q_max"], dp_max: float = S["dp_max"], n: float = S["n_gen"],
                     n_cups: int = len(P.CUPS), a_line: float = S["A_line"], extra=None) -> dict:
    """Steady state: manifold vacuum dp_m with gen_flow(dp_m) = sum of cup flows, each cup at the
    vacuum dp_c where its leak equals the line flow, dp_m - dp_c = line_dp(leak).

    ``extra`` optionally gives cup 0 an extra leak area (a cup over an edge)."""
    def cup_dp(dp_m, a_lip):
        lo, hi = 0.0, dp_m
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            q = cup_leak(mid, perm, a_lip)
            lo, hi = (mid, hi) if mid + line_dp(q, a_line) < dp_m else (lo, mid)
        return 0.5 * (lo + hi)

    def demand(dp_m):
        total, dps = 0.0, []
        d_good = cup_dp(dp_m, C["A_lip0"])
        for i in range(n_cups):
            if extra and i == 0:
                a_lip = C["A_lip0"] + extra
                dc = cup_dp(dp_m, a_lip)
            else:
                a_lip, dc = C["A_lip0"], d_good
            dps.append(dc)
            total += cup_leak(dc, perm, a_lip)
        return total, dps

    lo, hi = 0.0, dp_max
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        q, _ = demand(mid)
        lo, hi = (mid, hi) if gen_flow(mid, dp_max, q_max, n) > q else (lo, mid)
    dp_m = 0.5 * (lo + hi)
    q, dps = demand(dp_m)
    return {"dp_man": dp_m, "dp_cups": np.array(dps), "Q": q}


def pickup(perm: float, q_max: float = S["Q_max"], dp_max: float = S["dp_max"], n_exp: float = S["n_gen"],
           t_end: float = 1.5, dt: float = 2e-5) -> dict:
    """Vacuum build-up from the valve opening (t = 0), cups sealed on the parcel: the manifold
    and six cup chambers with the model's laws (free-air flows, C = V / p_atm)."""
    nc = len(P.CUPS)
    pm, pc = 0.0, 0.0           # manifold and (identical) cup gauge pressures
    n = int(round(t_end / dt))
    ts = np.empty(n)
    dpc = np.empty(n)
    for k in range(n):
        qg = gen_flow(-pm, dp_max, q_max, n_exp)
        x = pc - pm
        ql = math.copysign(orifice(S["A_line"], abs(x), 200.0), x)
        leak = cup_leak(-pc, perm) if pc < 0 else 0.0
        pm += dt * P.P_ATM * (nc * ql - qg) / S["V_man"]
        pc += dt * P.P_ATM * (leak - ql) / C["V_cup"]
        ts[k] = (k + 1) * dt
        dpc[k] = -pc
    return {"t": ts, "dp": dpc}
