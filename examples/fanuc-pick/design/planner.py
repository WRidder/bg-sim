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


def wrist_load(c: Code, p: NS, acc, psi, psid, psidd, held):
    """Wrist moment, inertia and payload use (fraction of the LR-10iA/10 ratings).

    Gripper (m_g at zc_g below the flange) and, while held, the parcel (m_p at its centre of mass)
    as point masses with their own inertias; the moment about the wrist centre (the J5 axis, D6
    above the flange) is what accelerates them against gravity, M = sum r x m (a - g) +
    J_axial psi''. Bending |M_xy| is rated by J4/J5, the axial |M_z| by J6. The inertia about J4/J5
    is bounded by the inertia about a horizontal axis through the wrist centre.
    """
    psg = p.psig_deg * DEG
    # parcel centre of mass in the gripper frame (z up, origin at the flange)
    cxg = c.let("w_cx", F.cos(psg) * (p.cx - p.gx) + F.sin(psg) * (p.cy - p.gy))
    cyg = c.let("w_cy", -F.sin(psg) * (p.cx - p.gx) + F.cos(psg) * (p.cy - p.gy))
    zp = c.let("w_zp", -(p.h_stack + 0.5 * p.H_p - p.cz) - fz.D6)
    zg = c.let("w_zg", -p.zc_g - fz.D6)
    cp = c.let("w_cps", F.cos(psi))
    sp = c.let("w_sps", F.sin(psi))
    rx = c.let("w_rx", cp * cxg - sp * cyg)      # parcel lever (world), horizontal part
    ry = c.let("w_ry", sp * cxg + cp * cyg)
    mp = c.let("w_mp", held * p.m_p)
    # accelerations of the two centres of mass plus gravity (world)
    ax, ay, az = acc
    gx_ = ax
    gy_ = ay
    gz_ = az + fz.G0
    px_ = c.let("w_pax", ax - psidd * ry - psid * psid * rx)
    py_ = c.let("w_pay", ay + psidd * rx - psid * psid * ry)
    pz_ = gz_
    # M = r_g x m_g (a_g - g) + r_p x m_p (a_p - g), r_g = (0, 0, zg), r_p = (rx, ry, zp)
    mx = c.let("w_Mx", p.m_g * (-zg * gy_) + mp * (ry * pz_ - zp * py_))
    my = c.let("w_My", p.m_g * (zg * gx_) + mp * (zp * px_ - rx * pz_))
    mz = c.let("w_Mz", mp * (rx * py_ - ry * px_) + (p.Jg6 + held * p.Jpz) * psidd)
    um = c.let("w_uM", F.max(F.sqrt(mx * mx + my * my + 1e-12) / p.M45_max, F.abs(mz) / p.M6_max))
    c2 = c.let("w_c2", cxg * cxg + cyg * cyg)
    i45 = c.let("w_I45", p.Jg45 + p.m_g * zg * zg + held * (F.max(p.Jpx, p.Jpy) + p.m_p * (zp * zp + c2)))
    i6 = c.let("w_I6", p.Jg6 + held * (p.Jpz + p.m_p * c2))
    ui = c.let("w_uI", F.max(i45 / p.I45_max, i6 / p.I6_max))
    upl = c.let("w_um", (p.m_g + held * p.m_p) / p.m_max)
    return um, ui, upl, (mx, my, mz)


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
    joint2 = F.or_(fam < 1.5, fam > 3.5)
    joint13 = fam > 3.5
    blend = fam > 2.5
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
    tA = c.let("tA", p.t0)
    tB = c.let("tB", tA + T_app)
    tL = c.let("tL", tB + p.T_seal)
    t2s = c.let("t2s", tL + T1 - ov1)
    t3s = c.let("t3s", t2s + T2 - ov3)
    tE = c.let("tE", t3s + T3)
    tD = c.let("tD", tE + p.T_rel)
    tF = c.let("tF", tD + T_dep)
    return dict(lam1=lam1, psB=psB, psE=psE, dpsi=dpsi, xB=xB, yB=yB, xE=xE, yE=yE, zB=zB, zC=zC,
                T_app=T_app, al_app=al_app, T_dep=T_dep, al_dep=al_dep, T1=T1, al1=al1, T2=T2, al2=al2,
                T3=T3, al3=al3, qB=qB, qC=qC, qD=qD, qE=qE, fam=fam, joint2=joint2, joint13=joint13,
                tA=tA, tB=tB, tL=tL, t2s=t2s, t3s=t3s, tE=tE, tD=tD, tF=tF, ov1=ov1, ov3=ov3)


def joint_ref(c: Code, p: NS, tl: dict, pre: str, tk):
    """Joint reference q(tk) (six values)."""
    lam = p.lam
    s_app = seg_s(c, f"{pre}a", tk, tl["tA"], tl["T_app"], tl["al_app"], lam)
    s1 = seg_s(c, f"{pre}1", tk, tl["tL"], tl["T1"], tl["al1"], lam)
    s2 = seg_s(c, f"{pre}2", tk, tl["t2s"], tl["T2"], tl["al2"], lam)
    s3 = seg_s(c, f"{pre}3", tk, tl["t3s"], tl["T3"], tl["al3"], lam)
    s_dep = seg_s(c, f"{pre}d", tk, tl["tD"], tl["T_dep"], tl["al_dep"], lam)
    xc = c.let(f"{pre}_px", tl["xB"] + (tl["xE"] - tl["xB"]) * s2)
    yc = c.let(f"{pre}_py", tl["yB"] + (tl["yE"] - tl["yB"]) * s2)
    zc = c.let(f"{pre}_pz", tl["zB"] + p.h_app * (1.0 - s_app) + p.H_lift * (s1 - s3) + p.h_dep * s_dep)
    psc = c.let(f"{pre}_pps", tl["psB"] + tl["dpsi"] * s2)
    qc = ik_down(c, f"{pre}k", xc, yc, zc, psc)
    fam = tl["fam"]
    out = []
    for j in range(6):
        qB, qC, qD, qE = tl["qB"][j], tl["qC"][j], tl["qD"][j], tl["qE"][j]
        jtr = qC + (qD - qC) * s2                                   # family 1 transfer
        jbl = qB + (qC - qB) * s1 + (qD - qC) * s2 + (qE - qD) * s3  # family 4
        f1 = F.ifelse(F.and_(tk >= tl["t2s"], tk < tl["t3s"]), jtr, qc[j])
        f4 = F.ifelse(F.and_(tk >= tl["tL"], tk < tl["tE"]), jbl, qc[j])
        out.append(c.let(f"{pre}q{j + 1}", F.ifelse(fam < 1.5, f1, F.ifelse(fam > 3.5, f4, qc[j]))))
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


# ------------------------------------------------------------------ tick outputs (shared)
def tick(c: Code, p: NS, tl: dict, act, t, ts, prev):
    """Everything the block computes at the tick t (ts = the period). `prev(j)` is the previous
    tick's joint acceleration qddr[j] (the jerk is its backward difference)."""
    qm, _ = joint_ref(c, p, tl, "m", t - ts)
    q0, _ = joint_ref(c, p, tl, "c", t)
    qp, _ = joint_ref(c, p, tl, "p", t + ts)
    qd = [c.let(f"qd{j + 1}", (qp[j] - qm[j]) / (2.0 * ts)) for j in range(6)]
    qdd = [c.let(f"qdd{j + 1}", (qp[j] - 2.0 * q0[j] + qm[j]) / (ts * ts)) for j in range(6)]
    # the gripper: forward kinematics at the three instants, body twist and its rate
    fm = fk_down(c, "km", qm)
    f0 = fk_down(c, "kc", q0)
    fp = fk_down(c, "kp", qp)
    vel = [c.let(f"gv{k + 1}", (fp[k] - fm[k]) / (2.0 * ts)) for k in range(4)]
    acc = [c.let(f"ga{k + 1}", (fp[k] - 2.0 * f0[k] + fm[k]) / (ts * ts)) for k in range(4)]
    psi = f0[3]
    cps = c.let("cps", F.cos(psi))
    sps = c.let("sps", F.sin(psi))
    vbx = c.let("vbx", cps * vel[0] + sps * vel[1])
    vby = c.let("vby", -sps * vel[0] + cps * vel[1])
    # d/dt (R^T v) = R^T a - w x (R^T v), w = (0, 0, psi')
    abx = c.let("abx", cps * acc[0] + sps * acc[1] + vel[3] * vby)
    aby = c.let("aby", -sps * acc[0] + cps * acc[1] - vel[3] * vbx)
    V = [0.0, 0.0, vel[3], vbx, vby, vel[2]]
    Vd = [0.0, 0.0, acc[3], abx, aby, acc[2]]
    g = [F.cos(0.5 * psi), 0.0, 0.0, F.sin(0.5 * psi), f0[0], f0[1], f0[2]]
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
    um, ui, upl, mom = wrist_load(c, p, acc[:3], psi, vel[3], acc[3], held)

    def mx(vals):
        out = vals[0]
        for v in vals[1:]:
            out = F.max(out, v)
        return out

    return dict(q=q0, qd=qd, qdd=qdd, V=V, Vd=Vd, g=g, ue=ue, uv=uv, held=held,
                uvj=uvj, uaj=uaj, ujj=ujj, urj=urj, uv_all=mx(uvj), ua_all=mx(uaj), uj_all=mx(ujj),
                ur_all=mx(urj), uM=um, uI=ui, um=upl, M=mom)


# ------------------------------------------------------------------ numeric reference
def num_params(globals_: dict) -> NS:
    return NS(**{n: float(globals_[n]) for n in PLANNER_PARAMS})


def _arr(v, t):
    return np.broadcast_to(np.asarray(v, dtype=float), t.shape).astype(float)


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
    qa, _ = joint_ref(c0, p, tl, "m", t - 2 * dt)
    qb, _ = joint_ref(c0, p, tl, "c", t - dt)
    qc, _ = joint_ref(c0, p, tl, "p", t)
    qdd_prev = [np.where(t > 0.5 * dt, (_arr(qc[j], t) - 2 * _arr(qb[j], t) + _arr(qa[j], t)) / dt ** 2, 0.0)
                for j in range(6)]
    r = tick(c, p, tl, act, t, dt, lambda j: qdd_prev[j])
    out = {
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
