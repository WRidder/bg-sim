"""The pick-and-place planner: trajectory families, IK, timeline and gripper sequence (dual mode).

Written once against `sym.F`/`sym.Code`: with numbers (or numpy time arrays) it is the Python
reference of the optimizer and the validation; with `Sym` values `build_library.py` turns it
into the 1 kHz `@discrete` block `library/PickPlanner.jl`, so both compute the same formulas.

Motion (the flange, tool pointing straight down, gripper frame yaw psi):

    A --approach--> B (pick contact) --wait T_seal-- --lift S1--> C --transfer S2--> D
      --lower S3--> E (place contact) --vent T_rel-- --depart--> F

Every move uses the same normalised jerk-limited profile `s(tau; alpha, lam)`: acceleration
phase `alpha` of the duration, jerk ramps `lam/2` of each acceleration phase (lam = 0 is the
trapezoid, lam = 1 the pure S-curve), cruise in between. A move whose time scales are
`V = max_i L_i / v_i` (velocity) and `A = max_i L_i / a_i / (1 - lam/2)` (acceleration) takes the
shortest time that keeps every axis within its limits with one common profile:

    T = V + A/V, alpha = (A/V)/T    when V^2 >= A (it cruises)
    T = 2 sqrt(A), alpha = 1/2       otherwise.

Families (global `family`):
1. joint PTP with stops: Cartesian lift, synchronised joint transfer, Cartesian lower;
2. Cartesian with stops: three straight lines, yaw turned during the transfer;
3. Cartesian blended: the same lines superposed; the transfer starts when the lift has `r_b`
   to go, the lowering `r_b`-worth of time before the transfer ends (corner cut ~ r_b);
4. joint blended: lift, transfer and lower as synchronised joint moves, superposed the same way.
Approach and depart are Cartesian in every family. The joint limits are `kv`, `ka` times the
datasheet values (`ka` also scales the jerk limits); the Cartesian ones `v_c`, `a_c`, `j_c`
(TCP) and `w_c`, `al_c`, `jw_c` (yaw). A move whose jerk scale `Jm = max_i L_i/j_i` asks for it
is stretched to `T = (Jm jj)^(1/3)` (the alpha kept), `jj` the normalised peak jerk.

The arm is kinematic: it follows the joint reference exactly, so the gripper pose is the forward
kinematics of q(t) (`fk_down`) and the planner hands the gripper's body twist to the model
(`V`, its rate `Vd` and the tick time `tk`: a first-order hold between the ticks). The datasheet
limits are checked, not enforced by a servo: the planned joint rate, acceleration, jerk and range
use and the wrist load (payload, moment and inertia ratings) are outputs in % of the limits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import fanuc as fz
import params as P
from sym import F, Code, Sym

DEG = math.pi / 180.0

#: block parameters of the planner, all bound to the globals of the same name
PLANNER_PARAMS = [
    "family", "kv", "ka", "v_c", "a_c", "j_c", "w_c", "al_c", "jw_c", "lam", "r_b", "H_lift", "h_app", "h_dep",
    "t0", "t_ext", "t_vac", "T_seal", "ret_hold", "t_ret", "t_ext2", "T_rel",
    "xp", "yp", "psip_deg", "xq", "yq", "psiq_deg", "psig_deg", "gx", "gy", "z_s",
    "L_p", "W_p", "H_p", "h_stack", "r_p", "lay_deg", "D_lip", "e_m",
    "zone1", "zone2", "zone3", "zone4", "zone5",
    "qdmax1", "qdmax2", "qdmax3", "qdmax4", "qdmax5", "qdmax6",
    "qddmax1", "qddmax2", "qddmax3", "qddmax4", "qddmax5", "qddmax6",
    "qdddmax1", "qdddmax2", "qdddmax3", "qdddmax4", "qdddmax5", "qdddmax6",
    "qmin1", "qmin2", "qmin3", "qmin4", "qmin5", "qmin6",
    "qmax1", "qmax2", "qmax3", "qmax4", "qmax5", "qmax6",
    "m_g", "zc_g", "Jg45", "Jg6", "m_p", "cx", "cy", "cz", "Jpx", "Jpy", "Jpz",
    "m_max", "M45_max", "M6_max", "I45_max", "I6_max",
    "tilt_gain", "tilt_max_deg", "T_tw", "T_tr",
    "f5_Ta", "f5_Tp", "f5_Tl", "f5_Tx", "f5_ox", "f5_ax", "f5_dx", "f5_ex", "f5_Td", "f5_y0", "f5_y1",
]


class NS:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)


def sym_params() -> NS:
    return NS(**{n: Sym(n, atom=True) for n in PLANNER_PARAMS})


# ------------------------------------------------------------------ the profile
def prof_time(c: Code, pre: str, V, A, lam1, J, lam):
    """(T, alpha) of a move with the velocity, acceleration and jerk scales V = max L_i/v_i,
    A = max L_i/a_i and J = max L_i/j_i. The v/a time is then stretched (alpha kept) until the
    jerk of the profile, L jj/T^3 with jj = ap/tj its normalised jerk, is within the limits:
    a stretch lowers the speed, acceleration and jerk together."""
    A2 = c.let(f"{pre}_A", A / lam1)
    Vg = c.let(f"{pre}_Vg", F.max(V, 1e-9))
    cruise = V * V >= A2
    T0 = c.let(f"{pre}_T0", F.max(F.ifelse(cruise, V + A2 / Vg, 2.0 * F.sqrt(A2)), 1.0e-3))
    al = c.let(f"{pre}_al", F.ifelse(cruise, F.clamp((A2 / Vg) / T0, 1.0e-3, 0.5), 0.5))
    tj = F.max(0.5 * lam * al, 1.0e-6 * al)
    jj = c.let(f"{pre}_jn", 1.0 / ((1.0 - al) * (al - tj) * tj))
    T = c.let(f"{pre}_T", F.max(T0, (F.max(J, 0.0) * jj) ** (1.0 / 3.0)))
    return T, al


def prof_s(c: Code, pre: str, tau, al, lam):
    """Normalised position s(tau) for tau already clamped to [0, 1]."""
    tj = c.let(f"{pre}_tj", F.max(0.5 * lam * al, 1.0e-6 * al))
    vp = c.let(f"{pre}_vp", 1.0 / (1.0 - al))
    ap = c.let(f"{pre}_ap", vp / (al - tj))
    jj = c.let(f"{pre}_jj", ap / tj)

    def sacc(u, nm):
        w = c.let(f"{pre}_{nm}w", al - u)
        r1 = jj * u * u * u / 6.0
        du = u - tj
        r2 = ap * tj * tj / 6.0 + 0.5 * ap * tj * du + 0.5 * ap * du * du
        r3 = 0.5 * vp * al - (vp * w - jj * w * w * w / 6.0)
        return c.let(f"{pre}_{nm}", F.ifelse(u <= tj, r1, F.ifelse(u <= al - tj, r2, r3)))

    ua = c.let(f"{pre}_ua", F.min(tau, al))
    ub = c.let(f"{pre}_ub", F.min(1.0 - tau, al))
    sa = sacc(ua, "sa")
    sb = sacc(ub, "sb")
    mid = 0.5 * vp * al + vp * (tau - al)
    return c.let(f"{pre}_s", F.ifelse(tau <= al, sa, F.ifelse(tau <= 1.0 - al, mid, 1.0 - sb)))


def seg_s(c: Code, pre: str, tk, ts, T, al, lam):
    tau = c.let(f"{pre}_tau", F.clamp((tk - ts) / T, 0.0, 1.0))
    return prof_s(c, pre, tau, al, lam)


def prof_s2(c: Code, pre: str, tau, aa, ad, lam):
    """Asymmetric normalised profile (family 5): an acceleration phase `aa` and a deceleration
    phase `ad` of the duration (aa + ad <= 1), each with jerk ramps lam/2 of the phase, the
    cruise in between at the peak speed vp = 1/(1 - aa/2 - ad/2)."""
    vp = c.let(f"{pre}_vp", 1.0 / (1.0 - 0.5 * aa - 0.5 * ad))

    def sacc(u, al, nm):
        tj = c.let(f"{pre}_{nm}tj", F.max(0.5 * lam * al, 1.0e-6 * al))
        ap = c.let(f"{pre}_{nm}ap", vp / (al - tj))
        jj = c.let(f"{pre}_{nm}jj", ap / tj)
        w = c.let(f"{pre}_{nm}w", al - u)
        r1 = jj * u * u * u / 6.0
        du = u - tj
        r2 = ap * tj * tj / 6.0 + 0.5 * ap * tj * du + 0.5 * ap * du * du
        r3 = 0.5 * vp * al - (vp * w - jj * w * w * w / 6.0)
        return c.let(f"{pre}_{nm}", F.ifelse(u <= tj, r1, F.ifelse(u <= al - tj, r2, r3)))

    sa = sacc(c.let(f"{pre}_ua", F.min(tau, aa)), aa, "sa")
    sb = sacc(c.let(f"{pre}_ub", F.min(1.0 - tau, ad)), ad, "sb")
    mid = 0.5 * vp * aa + vp * (tau - aa)
    return c.let(f"{pre}_s", F.ifelse(tau <= aa, sa, F.ifelse(tau <= 1.0 - ad, mid, 1.0 - sb)))


def smooth7(x):
    """C3 smooth step on [0, 1] (x already clamped)."""
    return x * x * x * x * (35.0 - 84.0 * x + 70.0 * x * x - 20.0 * x * x * x)


def inv_prof(c: Code, pre: str, f, al, lam, iters: int = 40):
    """tau with s(tau) = f (bisection; f in [0, 1])."""
    if not c.emit:
        lo, hi = 0.0, 1.0
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            s = prof_s(c, pre, mid, al, lam)
            if s < f:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)
    c.lines.append(f"{pre}_lo = 0.0")
    c.lines.append(f"{pre}_hi = 1.0")
    c.lines.append(f"for {pre}_it in 1:{iters}")
    sub = Code(True)
    mid = sub.let(f"{pre}_mid", 0.5 * (Sym(f"{pre}_lo", True) + Sym(f"{pre}_hi", True)))
    s = prof_s(sub, pre, mid, al, lam)
    below = s < f
    sub.lines.append(f"{pre}_lo = ifelse({below.text}, {mid.text}, {pre}_lo)")
    sub.lines.append(f"{pre}_hi = ifelse({below.text}, {pre}_hi, {mid.text})")
    c.lines.extend("    " + ln for ln in sub.lines)
    c.lines.append("end")
    return c.let(f"{pre}_tauinv", 0.5 * (Sym(f"{pre}_lo", True) + Sym(f"{pre}_hi", True)))


# ------------------------------------------------------------------ IK for the tool pointing down
def ik_down(c: Code, pre: str, x, y, z, psi):
    """q1..q6 of the flange at (x, y, z), tool down, gripper yaw psi (fanuc.ik_down, closed form:
    q4 = 0, q5 = q2 - q3 - pi/2, q6 = psi - q1)."""
    # the atan arguments are made dimensionless (bgsim checks the units of atan)
    hh = c.let(f"{pre}_h", F.hypot(x, y))
    q1 = c.let(f"{pre}_q1", F.atan2(y / hh, x / hh))
    rr = c.let(f"{pre}_rr", hh - fz.A1)
    zz = c.let(f"{pre}_zz", z + fz.D6 - fz.D1)
    nn = c.let(f"{pre}_n", F.hypot(rr, zz))
    sg = c.let(f"{pre}_sg", F.clamp((rr * rr + zz * zz - fz.A2 * fz.A2 - fz.L3 * fz.L3) / (2.0 * fz.A2 * fz.L3), -1.0, 1.0))
    g = c.let(f"{pre}_g", F.asin(sg))
    aa = c.let(f"{pre}_aa", fz.A2 + fz.L3 * F.sin(g))
    bb = c.let(f"{pre}_bb", fz.L3 * F.cos(g))
    q2 = c.let(f"{pre}_q2", F.atan2((aa * rr - bb * zz) / nn, (bb * rr + aa * zz) / nn))
    q3 = c.let(f"{pre}_q3", g - fz.PHI3)
    q5 = c.let(f"{pre}_q5", q2 - q3 - 0.5 * math.pi)
    q6 = c.let(f"{pre}_q6", psi - q1)
    return [q1, q2, q3, 0.0, q5, q6]


def fk_down(c: Code, pre: str, q):
    """Flange position and gripper yaw of a tool-down configuration (fanuc.fk_down)."""
    g = c.let(f"{pre}_fg", q[2] + fz.PHI3)
    aa = c.let(f"{pre}_fa", fz.A2 + fz.L3 * F.sin(g))
    bb = c.let(f"{pre}_fb", fz.L3 * F.cos(g))
    c2 = c.let(f"{pre}_c2", F.cos(q[1]))
    s2 = c.let(f"{pre}_s2", F.sin(q[1]))
    rr = c.let(f"{pre}_fr", fz.A1 + aa * s2 + bb * c2)
    x = c.let(f"{pre}_fx", rr * F.cos(q[0]))
    y = c.let(f"{pre}_fy", rr * F.sin(q[0]))
    z = c.let(f"{pre}_fz", aa * c2 - bb * s2 + fz.D1 - fz.D6)
    return x, y, z, c.let(f"{pre}_fp", q[0] + q[5])


def com_lever(c: Code, p: NS):
    """The parcel centre of mass seen from the flange, gripper frame (z up): (cxg, cyg, zcg)."""
    psg = p.psig_deg * DEG
    cxg = c.let("w_cx", F.cos(psg) * (p.cx - p.gx) + F.sin(psg) * (p.cy - p.gy))
    cyg = c.let("w_cy", -F.sin(psg) * (p.cx - p.gx) + F.cos(psg) * (p.cy - p.gy))
    zcg = c.let("w_zc", -(p.h_stack + 0.5 * p.H_p - p.cz))
    return cxg, cyg, zcg


def wrist_load(c: Code, p: NS, lev, pf, n, a_f, a_c, com, psidd, held):
    """Wrist moment, inertia and payload use (fraction of the LR-10iA/10 ratings).

    Gripper (m_g at zc_g below the flange, on the tool axis n) and, while held, the parcel (m_p at
    its centre of mass `com`) as point masses with their own inertias; the moment about the wrist
    centre (the J5 axis, D6 above the flange along n) is what accelerates them against gravity,
    M = sum r x m (a - g) + J_axial psi''. Bending (M across n) is rated by J4/J5, the axial
    part M.n by J6. `a_f` is the flange acceleration, `a_c` that of the parcel centre of mass. The
    inertia about J4/J5 is bounded by the inertia about an axis across n through the wrist centre.
    """
    cxg, cyg, zcg = lev
    zp = c.let("w_zp", zcg - fz.D6)
    zg = c.let("w_zg", -p.zc_g - fz.D6)
    wc = [c.let(f"w_wc{i}", pf[i] + fz.D6 * n[i]) for i in range(3)]
    rp = [c.let(f"w_rp{i}", com[i] - wc[i]) for i in range(3)]
    rg = [zg * n[i] for i in range(3)]
    mp = c.let("w_mp", held * p.m_p)
    fg = [a_f[0], a_f[1], a_f[2] + fz.G0]
    fp = [c.let(f"w_fp{i}", a_c[i] + (fz.G0 if i == 2 else 0.0)) for i in range(3)]

    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    mg_ = cross(rg, fg)
    mpp = cross(rp, fp)
    M = [c.let(f"w_M{i}", p.m_g * mg_[i] + mp * mpp[i]) for i in range(3)]
    ma = c.let("w_Ma", M[0] * n[0] + M[1] * n[1] + M[2] * n[2])
    mb = [c.let(f"w_Mb{i}", M[i] - ma * n[i]) for i in range(3)]
    mz = c.let("w_Mz", ma + (p.Jg6 + held * p.Jpz) * psidd)
    um = c.let("w_uM", F.max(F.sqrt(mb[0] * mb[0] + mb[1] * mb[1] + mb[2] * mb[2] + 1e-12) / p.M45_max,
                             F.abs(mz) / p.M6_max))
    mx, my = M[0], M[1]
    c2 = c.let("w_c2", cxg * cxg + cyg * cyg)
    i45 = c.let("w_I45", p.Jg45 + p.m_g * zg * zg + held * (F.max(p.Jpx, p.Jpy) + p.m_p * (zp * zp + c2)))
    i6 = c.let("w_I6", p.Jg6 + held * (p.Jpz + p.m_p * c2))
    ui = c.let("w_uI", F.max(i45 / p.I45_max, i6 / p.I6_max))
    upl = c.let("w_um", (p.m_g + held * p.m_p) / p.m_max)
    return um, ui, upl, (mx, my, M[2])


# ------------------------------------------------------------------ the plan
@dataclass
class Timeline:
    """The event times and move data (parameters only)."""
    v: dict


def timeline(c: Code, p: NS):
    """Waypoints, move durations and event times (functions of the parameters only)."""
    lam1 = c.let("lam1", 1.0 - 0.5 * p.lam)
    psp = c.let("psp", p.psip_deg * DEG)
    psq = c.let("psq", p.psiq_deg * DEG)
    psB = c.let("psB", psp + p.psig_deg * DEG)
    psE = c.let("psE", psq + p.psig_deg * DEG)
    dpsi = c.let("dpsi", psE - psB)
    xB = c.let("xB", p.xp + F.cos(psp) * p.gx - F.sin(psp) * p.gy)
    yB = c.let("yB", p.yp + F.sin(psp) * p.gx + F.cos(psp) * p.gy)
    xE = c.let("xE", p.xq + F.cos(psq) * p.gx - F.sin(psq) * p.gy)
    yE = c.let("yE", p.yq + F.sin(psq) * p.gx + F.cos(psq) * p.gy)
    zB = c.let("zB", p.z_s + p.H_p + p.h_stack)
    zC = c.let("zC", zB + p.H_lift)
    # Cartesian move times
    T_app, al_app = prof_time(c, "app", p.h_app / p.v_c, p.h_app / p.a_c, lam1, p.h_app / p.j_c, p.lam)
    T_dep, al_dep = prof_time(c, "dep", p.h_dep / p.v_c, p.h_dep / p.a_c, lam1, p.h_dep / p.j_c, p.lam)
    T1c, al1c = prof_time(c, "l1c", p.H_lift / p.v_c, p.H_lift / p.a_c, lam1, p.H_lift / p.j_c, p.lam)
    Lxy = c.let("Lxy", F.hypot(xE - xB, yE - yB))
    T2c, al2c = prof_time(c, "l2c", F.max(Lxy / p.v_c, F.abs(dpsi) / p.w_c),
                          F.max(Lxy / p.a_c, F.abs(dpsi) / p.al_c), lam1,
                          F.max(Lxy / p.j_c, F.abs(dpsi) / p.jw_c), p.lam)
    # joint waypoints
    qB = ik_down(c, "wB", xB, yB, zB, psB)
    qC = ik_down(c, "wC", xB, yB, zC, psB)
    qD = ik_down(c, "wD", xE, yE, zC, psE)
    qE = ik_down(c, "wE", xE, yE, zB, psE)
    vmax = [p.qdmax1, p.qdmax2, p.qdmax3, p.qdmax4, p.qdmax5, p.qdmax6]
    amax = [p.qddmax1, p.qddmax2, p.qddmax3, p.qddmax4, p.qddmax5, p.qddmax6]
    jmax = [p.qdddmax1, p.qdddmax2, p.qdddmax3, p.qdddmax4, p.qdddmax5, p.qdddmax6]

    def joint_move(pre, qa, qb):
        V = A = J = 0.0
        for j in range(6):
            d = F.abs(qb[j] - qa[j]) if not (isinstance(qb[j], float) and isinstance(qa[j], float)) else abs(qb[j] - qa[j])
            V = F.max(V, d / (p.kv * vmax[j])) if j else d / (p.kv * vmax[j])
            A = F.max(A, d / (p.ka * amax[j])) if j else d / (p.ka * amax[j])
            J = F.max(J, d / (p.ka * jmax[j])) if j else d / (p.ka * jmax[j])
        return prof_time(c, pre, c.let(f"{pre}_V", V), c.let(f"{pre}_Am", A), lam1, c.let(f"{pre}_Jm", J), p.lam)

    T1j, al1j = joint_move("j1", qB, qC)
    T2j, al2j = joint_move("j2", qC, qD)
    T3j, al3j = joint_move("j3", qD, qE)
    fam = p.family
    # family 5 (free timing): every move has its own duration and start, see the module docstring
    fam5 = fam > 4.5
    fam4 = F.and_(fam > 3.5, fam < 4.5)
    joint2 = F.or_(fam < 1.5, fam4)
    joint13 = fam4
    blend = F.and_(fam > 2.5, fam < 4.5)
    T1 = c.let("T1", F.ifelse(joint13, T1j, T1c))
    al1 = c.let("al1", F.ifelse(joint13, al1j, al1c))
    T2 = c.let("T2", F.ifelse(joint2, T2j, T2c))
    al2 = c.let("al2", F.ifelse(joint2, al2j, al2c))
    T3 = c.let("T3", F.ifelse(joint13, T3j, T1c))
    al3 = c.let("al3", F.ifelse(joint13, al3j, al1c))
    # blend overlaps (the lift and the lower are both H_lift long)
    fb = c.let("fb", F.clamp(p.r_b / F.max(p.H_lift, 1e-6), 0.0, 1.0))
    u1 = inv_prof(c, "b1", fb, al1, p.lam)
    u3 = inv_prof(c, "b3", fb, al3, p.lam)
    ov1 = c.let("ov1", F.ifelse(blend, F.min(T1 * u1, 0.5 * T2), 0.0))
    ov3 = c.let("ov3", F.ifelse(blend, F.min(T3 * u3, 0.5 * T2), 0.0))
    # family 5: the carry lasts f5_ox + f5_Tx + f5_ex; the lift and the lower are clipped to it
    Tc5 = c.let("Tc5", F.max(p.f5_ox, 0.0) + F.max(p.f5_Tx, 1.0e-3) + F.max(p.f5_ex, 0.0))
    aa5 = c.let("aa5", F.clamp(p.f5_ax, 0.02, 0.98))
    ad5 = c.let("ad5", F.clamp(p.f5_dx, 0.02, 1.0 - aa5))
    T_app = c.let("T_app", F.ifelse(fam5, F.max(p.f5_Ta, 1.0e-3), T_app))
    al_app = c.let("al_app", F.ifelse(fam5, 0.5, al_app))
    T_dep = c.let("T_dep", F.ifelse(fam5, F.max(p.f5_Tp, 1.0e-3), T_dep))
    al_dep = c.let("al_dep", F.ifelse(fam5, 0.5, al_dep))
    tA = c.let("tA", p.t0)
    tB = c.let("tB", tA + T_app)
    tL = c.let("tL", tB + p.T_seal)
    T1 = c.let("T1f", F.ifelse(fam5, F.clamp(p.f5_Tl, 1.0e-3, Tc5), T1))
    al1 = c.let("al1f", F.ifelse(fam5, 0.5, al1))
    T3 = c.let("T3f", F.ifelse(fam5, F.clamp(p.f5_Td, 1.0e-3, Tc5), T3))
    al3 = c.let("al3f", F.ifelse(fam5, 0.5, al3))
    T2 = c.let("T2f", F.ifelse(fam5, F.max(p.f5_Tx, 1.0e-3), T2))
    t2s = c.let("t2s", F.ifelse(fam5, tL + F.max(p.f5_ox, 0.0), tL + T1 - ov1))
    t3s0 = c.let("t3s0", t2s + T2 - ov3)
    tE = c.let("tE", F.ifelse(fam5, tL + Tc5, t3s0 + T3))
    t3s = c.let("t3s", F.ifelse(fam5, tE - T3, t3s0))
    # yaw (family 5): turned between the fractions f5_y0 and f5_y1 of the carry
    ty0 = c.let("ty0", tL + F.clamp(p.f5_y0, 0.0, 0.99) * (tE - tL))
    Ty = c.let("Ty", F.max((F.clamp(p.f5_y1, 0.01, 1.0) - F.clamp(p.f5_y0, 0.0, 0.99)) * (tE - tL), 1.0e-3))
    tD = c.let("tD", tE + p.T_rel)
    tF = c.let("tF", tD + T_dep)
    return dict(lam1=lam1, psB=psB, psE=psE, dpsi=dpsi, xB=xB, yB=yB, xE=xE, yE=yE, zB=zB, zC=zC,
                T_app=T_app, al_app=al_app, T_dep=T_dep, al_dep=al_dep, T1=T1, al1=al1, T2=T2, al2=al2,
                T3=T3, al3=al3, qB=qB, qC=qC, qD=qD, qE=qE, fam=fam, fam4=fam4, fam5=fam5, joint2=joint2,
                joint13=joint13, aa5=aa5, ad5=ad5, ty0=ty0, Ty=Ty,
                tA=tA, tB=tB, tL=tL, t2s=t2s, t3s=t3s, tE=tE, tD=tD, tF=tF, ov1=ov1, ov3=ov3)


def joint_ref(c: Code, p: NS, tl: dict, pre: str, tk):
    """Joint reference q(tk) (six values)."""
    lam = p.lam
    s_app = seg_s(c, f"{pre}a", tk, tl["tA"], tl["T_app"], tl["al_app"], lam)
    s1 = seg_s(c, f"{pre}1", tk, tl["tL"], tl["T1"], tl["al1"], lam)
    s2s = seg_s(c, f"{pre}2", tk, tl["t2s"], tl["T2"], tl["al2"], lam)
    # family 5: the asymmetric transfer profile and the yaw on its own window
    tau2 = c.let(f"{pre}5_tau", F.clamp((tk - tl["t2s"]) / tl["T2"], 0.0, 1.0))
    s25 = prof_s2(c, f"{pre}5", tau2, tl["aa5"], tl["ad5"], lam)
    s2 = c.let(f"{pre}_s2", F.ifelse(tl["fam5"], s25, s2s))
    sy5 = seg_s(c, f"{pre}y", tk, tl["ty0"], tl["Ty"], 0.5, lam)
    sy = c.let(f"{pre}_sy", F.ifelse(tl["fam5"], sy5, s2))
    s3 = seg_s(c, f"{pre}3", tk, tl["t3s"], tl["T3"], tl["al3"], lam)
    s_dep = seg_s(c, f"{pre}d", tk, tl["tD"], tl["T_dep"], tl["al_dep"], lam)
    xc = c.let(f"{pre}_px", tl["xB"] + (tl["xE"] - tl["xB"]) * s2)
    yc = c.let(f"{pre}_py", tl["yB"] + (tl["yE"] - tl["yB"]) * s2)
    zc = c.let(f"{pre}_pz", tl["zB"] + p.h_app * (1.0 - s_app) + p.H_lift * (s1 - s3) + p.h_dep * s_dep)
    psc = c.let(f"{pre}_pps", tl["psB"] + tl["dpsi"] * sy)
    qc = ik_down(c, f"{pre}k", xc, yc, zc, psc)
    fam = tl["fam"]
    out = []
    for j in range(6):
        qB, qC, qD, qE = tl["qB"][j], tl["qC"][j], tl["qD"][j], tl["qE"][j]
        jtr = qC + (qD - qC) * s2                                   # family 1 transfer
        jbl = qB + (qC - qB) * s1 + (qD - qC) * s2 + (qE - qD) * s3  # family 4
        f1 = F.ifelse(F.and_(tk >= tl["t2s"], tk < tl["t3s"]), jtr, qc[j])
        f4 = F.ifelse(F.and_(tk >= tl["tL"], tk < tl["tE"]), jbl, qc[j])
        out.append(c.let(f"{pre}q{j + 1}", F.ifelse(fam < 1.5, f1, F.ifelse(tl["fam4"], f4, qc[j]))))
    return out, (xc, yc, zc, psc)


def zones(c: Code, p: NS):
    """Active zones: the cup lip (with the edge margin) inside the parcel top face at the pick."""
    lay = c.let("lay", p.lay_deg * DEG)
    psg = c.let("psg", p.psig_deg * DEG)
    allowed = [p.zone1, p.zone2, p.zone3, p.zone4, p.zone5]
    act = []
    for k, (dx, dy) in enumerate(P.ZONE_DIRS):
        # cup centre in the gripper frame, then in the parcel frame
        if dx == 0.0 and dy == 0.0:
            xg, yg = 0.0, 0.0
        else:
            xg = c.let(f"zx{k + 1}", p.r_p * (dx * F.cos(lay) - dy * F.sin(lay)))
            yg = c.let(f"zy{k + 1}", p.r_p * (dx * F.sin(lay) + dy * F.cos(lay)))
        xpk = p.gx + F.cos(psg) * xg - F.sin(psg) * yg
        ypk = p.gy + F.sin(psg) * xg + F.cos(psg) * yg
        hx = 0.5 * p.L_p - 0.5 * p.D_lip - p.e_m
        hy = 0.5 * p.W_p - 0.5 * p.D_lip - p.e_m
        fits = F.and_(F.and_(F.abs(xpk) <= hx, F.abs(ypk) <= hy), allowed[k] > 0.5)
        act.append(c.let(f"act{k + 1}", F.b2f(fits)))
    return act


def sequence(c: Code, p: NS, tl: dict, act, t):
    """Cylinder commands (+1 extend, -1 retract), vacuum valves and the held flag at time t."""
    te1 = tl["tB"] - p.t_ext
    tr1 = tl["tL"] + p.t_ret
    te2 = tl["tE"] - p.t_ext2
    out_ext = F.and_(t >= te1, t < tl["tD"])
    pulled = F.and_(p.ret_hold > 0.5, F.and_(t >= tr1, t < te2))
    ext = c.let("ext_on", F.b2f(F.and_(out_ext, F.not_(pulled))))
    vac = c.let("vac_on", F.b2f(F.and_(t >= tl["tB"] - p.t_vac, t < tl["tE"])))
    ue = [c.let(f"ue{k + 1}", act[k] * (2.0 * ext - 1.0) + (1.0 - act[k]) * (-1.0)) for k in range(5)]
    uv = [c.let(f"uv{k + 1}", act[k] * vac) for k in range(5)]
    held = c.let("held_f", F.b2f(F.and_(t >= tl["tL"], t < tl["tE"])))
    return ue, uv, held


# ------------------------------------------------------------------ waiter motion and the general IK
def tilt_consts(c: Code, p: NS):
    """Filter window, tan of the largest tilt and the fade time (parameters only)."""
    tw = c.let("tw_w", F.max(p.T_tw, 1.0e-3))
    tm = c.let("tw_tm", F.tan(F.clamp(p.tilt_max_deg, 0.1, 60.0) * DEG))
    ttr = c.let("tw_tr", F.max(p.T_tr, 1.0e-3))
    return tw, tm, ttr


def nominal(c: Code, p: NS, tl: dict, lev, pre: str, tk):
    """The tool-down plan at tk: joints, flange pose and the parcel centre of mass (world)."""
    q, _ = joint_ref(c, p, tl, pre, tk)
    x, y, z, psi = fk_down(c, pre, q)
    cxg, cyg, zcg = lev
    cp = c.let(f"{pre}_ca", F.cos(psi))
    sp = c.let(f"{pre}_sa", F.sin(psi))
    rx = c.let(f"{pre}_rx", cp * cxg - sp * cyg)
    ry = c.let(f"{pre}_ry", sp * cxg + cp * cyg)
    com = (c.let(f"{pre}_cx", x + rx), c.let(f"{pre}_cy", y + ry), c.let(f"{pre}_cz", z + zcg))
    return dict(q=q, x=x, y=y, z=z, psi=psi, cps=cp, sps=sp, r=(rx, ry, zcg), com=com)


def waiter_pose(c: Code, p: NS, tl: dict, lev, tc, pre: str, tk):
    """The commanded gripper pose at tk with the waiter tilt.

    The planned acceleration of the parcel centre of mass, averaged over a triangle window of
    +-T_tw (the second difference of the planned path over T_tw: smooth wrist motion, no lag),
    gives the tilt u = tilt_gain a_h / (g + a_z) (tan of the angle, saturated smoothly at
    tilt_max), faded in after the lift start and out before the place contact (T_tr). The gripper
    z axis is turned onto n = (u, 1)/|(u, 1)| by the shortest rotation R_t, about the parcel
    centre of mass (the load keeps the planned path): flange = p_nom + (I - R_t) r_c.
    """
    tw, tm, ttr = tc
    n0 = nominal(c, p, tl, lev, f"{pre}_0", tk)
    nm = nominal(c, p, tl, lev, f"{pre}_m", tk - tw)
    npp = nominal(c, p, tl, lev, f"{pre}_p", tk + tw)
    af = [c.let(f"{pre}_af{i}", (npp["com"][i] - 2.0 * n0["com"][i] + nm["com"][i]) / (tw * tw)) for i in range(3)]
    den = c.let(f"{pre}_den", F.max(fz.G0 + af[2], 0.5 * fz.G0))
    e1 = c.let(f"{pre}_e1", F.clamp((tk - tl["tL"]) / ttr, 0.0, 1.0))
    e2 = c.let(f"{pre}_e2", F.clamp((tl["tE"] - tk) / ttr, 0.0, 1.0))
    env = c.let(f"{pre}_env", smooth7(e1) * smooth7(e2))
    ux0 = c.let(f"{pre}_ux0", p.tilt_gain * af[0] / den)
    uy0 = c.let(f"{pre}_uy0", p.tilt_gain * af[1] / den)
    ur = c.let(f"{pre}_ur", F.sqrt(ux0 * ux0 + uy0 * uy0 + 1.0e-12))
    sat = c.let(f"{pre}_sat", env * tm * F.tanh(ur / tm) / ur)
    ux = c.let(f"{pre}_ux", ux0 * sat)
    uy = c.let(f"{pre}_uy", uy0 * sat)
    nn = c.let(f"{pre}_nn", F.sqrt(1.0 + ux * ux + uy * uy))
    nx = c.let(f"{pre}_nx", ux / nn)
    ny = c.let(f"{pre}_ny", uy / nn)
    nz = c.let(f"{pre}_nz", 1.0 / nn)
    k = c.let(f"{pre}_k", 1.0 / (1.0 + nz))
    R = [[c.let(f"{pre}_R11", 1.0 - nx * nx * k), c.let(f"{pre}_R12", -(nx * ny * k)), nx],
         [c.let(f"{pre}_R21", -(nx * ny * k)), c.let(f"{pre}_R22", 1.0 - ny * ny * k), ny],
         [-nx, -ny, nz]]
    r = n0["r"]
    base = (n0["x"], n0["y"], n0["z"])
    pf = [c.let(f"{pre}_f{i}", base[i] + r[i] - (R[i][0] * r[0] + R[i][1] * r[1] + R[i][2] * r[2])) for i in range(3)]
    return dict(nom=n0, n=(nx, ny, nz), R=R, pf=pf, ux=ux, uy=uy)


def ik_full(c: Code, pre: str, w: dict):
    """Closed-form IK of the tilted gripper pose (fanuc.ik: wrist centre, arm plane, X-Y-X wrist),
    q6 unwrapped next to its tool-down value psi - q1."""
    nx, ny, nz = w["n"]
    R = w["R"]
    nom = w["nom"]
    cps, sps, psi = nom["cps"], nom["sps"], nom["psi"]
    ex = [c.let(f"{pre}_ex{i}", R[i][0] * cps + R[i][1] * sps) for i in range(3)]
    ey = [c.let(f"{pre}_ey{i}", R[i][1] * cps - R[i][0] * sps) for i in range(3)]
    pf = w["pf"]
    wx = c.let(f"{pre}_wx", pf[0] + fz.D6 * nx)
    wy = c.let(f"{pre}_wy", pf[1] + fz.D6 * ny)
    wz = c.let(f"{pre}_wz", pf[2] + fz.D6 * nz)
    hh = c.let(f"{pre}_h", F.hypot(wx, wy))
    q1 = c.let(f"{pre}_q1", F.atan2(wy / hh, wx / hh))
    rr = c.let(f"{pre}_rr", hh - fz.A1)
    zz = c.let(f"{pre}_zz", wz - fz.D1)
    nn = c.let(f"{pre}_n", F.hypot(rr, zz))
    sg = c.let(f"{pre}_sg", F.clamp((rr * rr + zz * zz - fz.A2 * fz.A2 - fz.L3 * fz.L3) / (2.0 * fz.A2 * fz.L3), -1.0, 1.0))
    g = c.let(f"{pre}_g", F.asin(sg))
    aa = c.let(f"{pre}_aa", fz.A2 + fz.L3 * F.sin(g))
    bb = c.let(f"{pre}_bb", fz.L3 * F.cos(g))
    q2 = c.let(f"{pre}_q2", F.atan2((aa * rr - bb * zz) / nn, (bb * rr + aa * zz) / nn))
    q3 = c.let(f"{pre}_q3", g - fz.PHI3)
    c1 = c.let(f"{pre}_c1", F.cos(q1))
    s1 = c.let(f"{pre}_s1", F.sin(q1))
    cb = c.let(f"{pre}_cb", F.cos(q2 - q3))
    sb = c.let(f"{pre}_sb", F.sin(q2 - q3))

    def r03t(v, nm):
        w0 = c.let(f"{pre}_{nm}0", c1 * v[0] + s1 * v[1])
        w1 = c.let(f"{pre}_{nm}1", c1 * v[1] - s1 * v[0])
        return [cb * w0 - sb * v[2], w1, sb * w0 + cb * v[2]]

    m0 = r03t([-nx, -ny, -nz], "a")
    m01 = c.let(f"{pre}_m01", r03t(ey, "b")[0])
    m02 = c.let(f"{pre}_m02", r03t(ex, "c")[0])
    m00 = c.let(f"{pre}_m00", m0[0])
    m10 = c.let(f"{pre}_m10", m0[1])
    m20 = c.let(f"{pre}_m20", m0[2])
    b = c.let(f"{pre}_b5", F.acos(F.clamp(m00, -1.0, 1.0)))
    a = c.let(f"{pre}_a4", F.atan2(m10, -m20))
    cc = c.let(f"{pre}_c6", F.atan2(m01, m02))
    ref6 = c.let(f"{pre}_r6", psi - q1)
    d6 = c.let(f"{pre}_d6", F.atan2(F.sin(-cc - ref6), F.cos(-cc - ref6)))
    return [q1, q2, q3, -a, -b, c.let(f"{pre}_q6", ref6 + d6)]


def command(c: Code, p: NS, tl: dict, lev, tc, pre: str, tk):
    """The joint command at tk: the tool-down plan, or the IK of the waiter pose when tilting."""
    w = waiter_pose(c, p, tl, lev, tc, pre, tk)
    qf = ik_full(c, f"{pre}_i", w)
    on = p.tilt_gain > 1.0e-9
    q = [c.let(f"{pre}_q{j + 1}", F.ifelse(on, qf[j], w["nom"]["q"][j])) for j in range(6)]
    return q, w


def _vee_prod(c: Code, pre: str, A, B):
    """vee(A B^T) (the rotation vector of A B^T for small angles)."""
    def e(i, j):
        return A[i][0] * B[j][0] + A[i][1] * B[j][1] + A[i][2] * B[j][2]
    return [c.let(f"{pre}{k}", 0.5 * v) for k, v in
            enumerate((e(2, 1) - e(1, 2), e(0, 2) - e(2, 0), e(1, 0) - e(0, 1)))]


# ------------------------------------------------------------------ tick outputs (shared)
def tick(c: Code, p: NS, tl: dict, act, t, ts, prev):
    """Everything the block computes at the tick t (ts = the period). `prev(j)` is the previous
    tick's joint acceleration qddr[j] (the jerk is its backward difference)."""
    lev = com_lever(c, p)
    tc = tilt_consts(c, p)
    qm, wm = command(c, p, tl, lev, tc, "im", t - ts)
    q0, w0 = command(c, p, tl, lev, tc, "ic", t)
    qp, wp = command(c, p, tl, lev, tc, "ip", t + ts)
    qd = [c.let(f"qd{j + 1}", (qp[j] - qm[j]) / (2.0 * ts)) for j in range(6)]
    qdd = [c.let(f"qdd{j + 1}", (qp[j] - 2.0 * q0[j] + qm[j]) / (ts * ts)) for j in range(6)]
    # the gripper: pose at the three instants, body twist and its rate
    pm, p0, pp = wm["pf"], w0["pf"], wp["pf"]
    vel = [c.let(f"gv{k + 1}", (pp[k] - pm[k]) / (2.0 * ts)) for k in range(3)]
    acc = [c.let(f"ga{k + 1}", (pp[k] - 2.0 * p0[k] + pm[k]) / (ts * ts)) for k in range(3)]
    psm, ps0, psp = wm["nom"]["psi"], w0["nom"]["psi"], wp["nom"]["psi"]
    psd = c.let("gv4", (psp - psm) / (2.0 * ts))
    psdd = c.let("ga4", (psp - 2.0 * ps0 + psm) / (ts * ts))
    n = w0["n"]
    R0 = w0["R"]
    cps, sps = w0["nom"]["cps"], w0["nom"]["sps"]
    # tilt rate (world) from the three tilt rotations; yaw about the tool axis n
    wt = [v / (2.0 * ts) for v in _vee_prod(c, "wtv", wp["R"], wm["R"])]
    va = _vee_prod(c, "wta", wp["R"], R0)
    vb_ = _vee_prod(c, "wtb", R0, wm["R"])
    wtd = [(va[k] - vb_[k]) / (ts * ts) for k in range(3)]
    ww = [c.let(f"ww{k}", wt[k] + psd * n[k]) for k in range(3)]
    wxn = [wt[1] * n[2] - wt[2] * n[1], wt[2] * n[0] - wt[0] * n[2], wt[0] * n[1] - wt[1] * n[0]]
    wwd = [c.let(f"wwd{k}", wtd[k] + psdd * n[k] + psd * wxn[k]) for k in range(3)]
    ex = [c.let(f"gex{i}", R0[i][0] * cps + R0[i][1] * sps) for i in range(3)]
    ey = [c.let(f"gey{i}", R0[i][1] * cps - R0[i][0] * sps) for i in range(3)]

    def body(v, nm):
        return [c.let(f"{nm}{k}", a[0] * v[0] + a[1] * v[1] + a[2] * v[2]) for k, a in enumerate((ex, ey, n))]

    wb = body(ww, "wb")
    wbd = body(wwd, "wbd")
    vb = body(vel, "vb")
    ab = body(acc, "ab")
    # d/dt (R^T v) = R^T a - w_b x (R^T v)
    vbd = [c.let("vbd0", ab[0] - (wb[1] * vb[2] - wb[2] * vb[1])),
           c.let("vbd1", ab[1] - (wb[2] * vb[0] - wb[0] * vb[2])),
           c.let("vbd2", ab[2] - (wb[0] * vb[1] - wb[1] * vb[0]))]
    V = [wb[0], wb[1], wb[2], vb[0], vb[1], vb[2]]
    Vd = [wbd[0], wbd[1], wbd[2], vbd[0], vbd[1], vbd[2]]
    # quaternion of R_t Rz(psi): q_t = (sqrt((1 + nz)/2), -ny/s, nx/s, 0), s = sqrt(2 (1 + nz))
    qa = c.let("qta", F.sqrt(0.5 * (1.0 + n[2])))
    sq = c.let("qts", F.sqrt(2.0 * (1.0 + n[2])))
    qb = c.let("qtb", -n[1] / sq)
    qc_ = c.let("qtc", n[0] / sq)
    ch = c.let("qch", F.cos(0.5 * ps0))
    sh = c.let("qsh", F.sin(0.5 * ps0))
    g = [qa * ch, qb * ch + qc_ * sh, qc_ * ch - qb * sh, qa * sh, p0[0], p0[1], p0[2]]
    ue, uv, held = sequence(c, p, tl, act, t)
    # utilisation of the limits (fractions)
    vmax = [getattr(p, f"qdmax{j}") for j in range(1, 7)]
    amax = [getattr(p, f"qddmax{j}") for j in range(1, 7)]
    jmax = [getattr(p, f"qdddmax{j}") for j in range(1, 7)]
    lo = [getattr(p, f"qmin{j}") for j in range(1, 7)]
    hi = [getattr(p, f"qmax{j}") for j in range(1, 7)]
    uvj = [c.let(f"uvj{j + 1}", F.abs(qd[j]) / vmax[j]) for j in range(6)]
    uaj = [c.let(f"uaj{j + 1}", F.abs(qdd[j]) / amax[j]) for j in range(6)]
    ujj = [c.let(f"ujj{j + 1}", F.abs(qdd[j] - prev(j)) / ts / jmax[j]) for j in range(6)]
    urj = [c.let(f"urj{j + 1}", F.abs(2.0 * q0[j] - hi[j] - lo[j]) / (hi[j] - lo[j])) for j in range(6)]
    # the parcel centre of mass follows the planned (tool-down) path: its acceleration
    cm, c0, cp_ = wm["nom"]["com"], w0["nom"]["com"], wp["nom"]["com"]
    a_c = [c.let(f"gac{k}", (cp_[k] - 2.0 * c0[k] + cm[k]) / (ts * ts)) for k in range(3)]
    um, ui, upl, mom = wrist_load(c, p, lev, p0, n, acc, a_c, c0, psdd, held)
    # tilt angle and its misalignment with the specific force a_c - g of the load (degrees)
    tilt = c.let("tilt_a", F.atan2(F.sqrt(n[0] * n[0] + n[1] * n[1] + 1.0e-30), n[2]) / DEG)
    fz_ = c.let("tilt_fz", a_c[2] + fz.G0)
    cr = [n[1] * fz_ - n[2] * a_c[1], n[2] * a_c[0] - n[0] * fz_, n[0] * a_c[1] - n[1] * a_c[0]]
    dot = n[0] * a_c[0] + n[1] * a_c[1] + n[2] * fz_
    terr = c.let("tilt_e", F.atan2(F.sqrt(cr[0] * cr[0] + cr[1] * cr[1] + cr[2] * cr[2] + 1.0e-30), dot) / DEG)
    fang = c.let("tilt_f", F.atan2(F.sqrt(a_c[0] * a_c[0] + a_c[1] * a_c[1] + 1.0e-30), fz_) / DEG)

    def mx(vals):
        out = vals[0]
        for v in vals[1:]:
            out = F.max(out, v)
        return out

    return dict(q=q0, qd=qd, qdd=qdd, V=V, Vd=Vd, g=g, ue=ue, uv=uv, held=held,
                uvj=uvj, uaj=uaj, ujj=ujj, urj=urj, uv_all=mx(uvj), ua_all=mx(uaj), uj_all=mx(ujj),
                ur_all=mx(urj), uM=um, uI=ui, um=upl, M=mom, n=n, com=c0, tilt=tilt, tilt_err=terr,
                f_ang=fang, a_c=a_c)


# ------------------------------------------------------------------ numeric reference
def num_params(globals_: dict) -> NS:
    return NS(**{n: float(globals_[n]) for n in PLANNER_PARAMS})


def _arr(v, t):
    return np.broadcast_to(np.asarray(v, dtype=float), t.shape).astype(float)


def return_time(p: NS, tl: dict) -> float:
    """The empty return from the depart end F back to the approach start A of the next cycle:
    one synchronised joint move at 100 % of the datasheet rates and the assumed accelerations
    and jerks (no load, so no grip limit). Pick rate = 60 / (T_cyc + T_ret) per minute."""
    c = Code(False)
    qF = ik_down(c, "rF", tl["xE"], tl["yE"], tl["zB"] + p.h_dep, tl["psE"])
    qA = ik_down(c, "rA", tl["xB"], tl["yB"], tl["zB"] + p.h_app, tl["psB"])
    V = A = J = 0.0
    for j in range(6):
        d = abs(qA[j] - qF[j])
        V = max(V, d / getattr(p, f"qdmax{j + 1}"))
        A = max(A, d / getattr(p, f"qddmax{j + 1}"))
        J = max(J, d / getattr(p, f"qdddmax{j + 1}"))
    T, _ = prof_time(c, "ret", V, A, 1.0 - 0.5 * p.lam, J, p.lam)
    return float(T)


def reference(globals_: dict, dt: float = P.TS, t_end: float | None = None) -> dict:
    """The planner evaluated on the tick grid t_k = k dt (vectorised; the same formulas as the
    block): q, qd, qdd, the gripper pose, twist and twist rate, the gripper sequence, and the
    planned use of every limit (fractions; the block reports running maxima in %)."""
    p = num_params(globals_)
    c = Code(False)
    tl = timeline(c, p)
    if t_end is None:
        t_end = tl["tF"] + P.T_END_PAD
    t = np.arange(0.0, t_end + 0.5 * dt, dt)
    act = zones(c, p)
    # the block's previous(qddr): qdd one tick earlier (0 before the first tick)
    c0 = Code(False)
    lev, tc = com_lever(c0, p), tilt_consts(c0, p)
    qa, _ = command(c0, p, tl, lev, tc, "m", t - 2 * dt)
    qb, _ = command(c0, p, tl, lev, tc, "c", t - dt)
    qc, _ = command(c0, p, tl, lev, tc, "p", t)
    qdd_prev = [np.where(t > 0.5 * dt, (_arr(qc[j], t) - 2 * _arr(qb[j], t) + _arr(qa[j], t)) / dt ** 2, 0.0)
                for j in range(6)]
    r = tick(c, p, tl, act, t, dt, lambda j: qdd_prev[j])
    out = {
        "n": np.array([_arr(v, t) for v in r["n"]]), "com": np.array([_arr(v, t) for v in r["com"]]),
        "a_c": np.array([_arr(v, t) for v in r["a_c"]]),
        "tilt": _arr(r["tilt"], t), "tilt_err": _arr(r["tilt_err"], t), "f_ang": _arr(r["f_ang"], t),
        "T_ret": return_time(p, tl),
        "t": t, "q": np.array([_arr(v, t) for v in r["q"]]),
        "qd": np.array([_arr(v, t) for v in r["qd"]]), "qdd": np.array([_arr(v, t) for v in r["qdd"]]),
        "V": np.array([_arr(v, t) for v in r["V"]]), "Vd": np.array([_arr(v, t) for v in r["Vd"]]),
        "g": np.array([_arr(v, t) for v in r["g"]]),
        "tl": {k: (float(v) if np.ndim(v) == 0 and not isinstance(v, (list, bool)) else v) for k, v in tl.items()},
        "T_cyc": float(tl["tF"] - tl["tA"]),
        "act": [float(a) for a in act],
        "ue": np.array([_arr(v, t) for v in r["ue"]]), "uv": np.array([_arr(v, t) for v in r["uv"]]),
        "held": _arr(r["held"], t),
        "M": np.array([_arr(v, t) for v in r["M"]]),
    }
    for key in ("uvj", "uaj", "ujj", "urj"):
        out[key] = np.array([float(np.max(_arr(v, t))) for v in r[key]])
    for key, name in (("uv_all", "util_v"), ("ua_all", "util_a"), ("uj_all", "util_j"), ("ur_all", "util_r"),
                      ("uM", "util_M"), ("uI", "util_I"), ("um", "util_m")):
        out[name] = float(np.max(_arr(r[key], t)))
    out["util_w"] = max(out["util_M"], out["util_I"], out["util_m"])
    out["util_max"] = max(out["util_v"], out["util_a"], out["util_j"], out["util_r"], out["util_w"])
    return out


#: outputs of the block: name, type, unit, description
OUTPUTS = [
    ("qr", "Vec{6}", "rad", "Joint reference (the arm follows it exactly)"),
    ("qdr", "Vec{6}", "rad/s", "Joint rate"),
    ("qddr", "Vec{6}", "rad/s^2", "Joint acceleration"),
    ("V", "Vec{6}", None, "Body twist of the gripper frame at the tick [w; v] (rad/s, m/s)"),
    ("Vd", "Vec{6}", None, "Rate of the body twist at the tick (rad/s^2, m/s^2)"),
    ("tk", "Real", "s", "Time of the last tick"),
    ("gref", "Vec{7}", None, "Gripper frame pose (flange origin, z up, yaw)"),
    ("uv_j", "Vec{6}", "1", "Peak joint rate / limit, per joint"),
    ("ua_j", "Vec{6}", "1", "Peak joint acceleration / limit, per joint"),
    ("uj_j", "Vec{6}", "1", "Peak joint jerk / limit, per joint"),
    ("util_v", "Real", "1", "Peak joint rate, % of the LR-10iA/10 limit"),
    ("util_a", "Real", "1", "Peak joint acceleration, % of the limit"),
    ("util_j", "Real", "1", "Peak joint jerk, % of the limit"),
    ("util_r", "Real", "1", "Peak joint range use, % (100 = at a range limit)"),
    ("util_M", "Real", "1", "Peak wrist load moment, % of the J4/J5 or J6 rating"),
    ("util_I", "Real", "1", "Peak wrist load inertia, % of the J4/J5 or J6 rating"),
    ("util_m", "Real", "1", "Peak payload, % of 10 kg"),
    ("util_max", "Real", "1", "Largest of the utilisations above, %"),
    ("M_w", "Vec{3}", "N*m", "Wrist load moment about the wrist centre (world axes)"),
    ("tilt", "Real", "1", "Waiter motion: tool tilt from the vertical, degrees"),
    ("tilt_pk", "Real", "1", "Waiter motion: peak tool tilt so far, degrees"),
    ("tilt_err", "Real", "1", "Angle between the tool axis and the specific force a - g of the load's centre of mass, degrees"),
    ("f_ang", "Real", "1", "Angle of the specific force a - g of the load from the vertical, degrees"),
] + [(f"ue{k}", "Real", "1", f"Zone {k} cylinder valve (+1 extend, -1 retract)") for k in range(1, 6)] \
  + [(f"uv{k}", "Real", "1", f"Zone {k} vacuum valve (1 on)") for k in range(1, 6)] + [
    ("act", "Vec{5}", "1", "Active zones"),
    ("held", "Real", "1", "1 while the load is carried (t_lift <= t < t_place)"),
    ("T_cyc", "Real", "s", "Cycle time (approach start to depart end)"),
    ("t_lift", "Real", "s", "Lift start"),
    ("t_place", "Real", "s", "Place contact (vacuum off)"),
    ("t_end", "Real", "s", "Depart end"),
]


def output_defaults(globals_: dict) -> dict:
    """The value of every output at t = 0 (the declared defaults of the block)."""
    ref = reference(globals_, t_end=0.0)
    tl = ref["tl"]
    d = {
        "qr": ref["q"][:, 0], "qdr": [0.0] * 6, "qddr": [0.0] * 6, "V": [0.0] * 6, "Vd": [0.0] * 6, "tk": 0.0,
        "gref": ref["g"][:, 0], "uv_j": [0.0] * 6, "ua_j": [0.0] * 6, "uj_j": [0.0] * 6, "M_w": [0.0] * 3,
        "tilt": 0.0, "tilt_pk": 0.0, "tilt_err": 0.0, "f_ang": 0.0,
        "act": ref["act"], "held": 0.0, "T_cyc": tl["tF"] - tl["tA"], "t_lift": tl["tL"], "t_place": tl["tE"],
        "t_end": tl["tF"],
    }
    for k in range(1, 6):
        d[f"ue{k}"] = -1.0
        d[f"uv{k}"] = 0.0
    for n in ("util_v", "util_a", "util_j", "util_r", "util_M", "util_I", "util_m", "util_max"):
        d[n] = 0.0
    return d


def emit_block() -> str:
    """The body of the generated `@discrete` block (see build_library.py)."""
    p = sym_params()
    c = Code(True)
    c.comment("timeline: waypoints, move times, event times (parameters only)")
    tl = timeline(c, p)
    act = zones(c, p)
    t = Sym("t", atom=True)
    ts = Sym("Ts", atom=True)
    c.comment("joint reference at t - Ts, t, t + Ts; the gripper twist; the limit use")
    r = tick(c, p, tl, act, t, ts, lambda j: Sym(f"previous(qddr[{j + 1}])", True))
    for j in range(6):
        c.assign(f"qr[{j + 1}]", r["q"][j])
        c.assign(f"qdr[{j + 1}]", r["qd"][j])
        c.assign(f"qddr[{j + 1}]", r["qdd"][j])
    for k in range(6):
        c.assign(f"V[{k + 1}]", r["V"][k])
        c.assign(f"Vd[{k + 1}]", r["Vd"][k])
    c.assign("tk", t)
    for k in range(7):
        c.assign(f"gref[{k + 1}]", r["g"][k])
    for j in range(6):
        for key, name in (("uvj", "uv_j"), ("uaj", "ua_j"), ("ujj", "uj_j")):
            c.assign(f"{name}[{j + 1}]", F.max(Sym(f"previous({name}[{j + 1}])", True), r[key][j]))
    for key, name in (("uv_all", "util_v"), ("ua_all", "util_a"), ("uj_all", "util_j"), ("ur_all", "util_r"),
                      ("uM", "util_M"), ("uI", "util_I"), ("um", "util_m")):
        c.assign(name, F.max(Sym(f"previous({name})", True), 100.0 * r[key]))
    c.assign("util_max", F.max(F.max(F.max(Sym("util_v", True), Sym("util_a", True)),
                                     F.max(Sym("util_j", True), Sym("util_r", True))),
                               F.max(F.max(Sym("util_M", True), Sym("util_I", True)), Sym("util_m", True))))
    for k in range(3):
        c.assign(f"M_w[{k + 1}]", r["M"][k])
    c.assign("tilt", r["tilt"])
    c.assign("tilt_pk", F.max(Sym("previous(tilt_pk)", True), r["tilt"]))
    c.assign("tilt_err", r["tilt_err"])
    c.assign("f_ang", r["f_ang"])
    for k in range(5):
        c.assign(f"ue{k + 1}", r["ue"][k])
        c.assign(f"uv{k + 1}", r["uv"][k])
        c.assign(f"act[{k + 1}]", act[k])
    c.assign("held", r["held"])
    for name, key in (("T_cyc", None), ("t_lift", "tL"), ("t_place", "tE"), ("t_end", "tF")):
        c.assign(name, tl["tF"] - tl["tA"] if key is None else tl[key])
    return c.text(8)


if __name__ == "__main__":
    import json
    import sys

    sys.path.insert(0, str(fz.HERE))
    fam = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    g = P.global_values({"family": fam})
    ref = reference(g)
    for k in ("uvj", "uaj", "ujj", "urj"):
        print(k, np.round(ref[k], 3))
    print("T_cyc", ref["T_cyc"], "act", ref["act"])
    print({k: round(ref[k], 3) for k in ("util_v", "util_a", "util_j", "util_r", "util_M", "util_I", "util_m")})
    print("lines of the block:", emit_block().count("\n") + 1)
