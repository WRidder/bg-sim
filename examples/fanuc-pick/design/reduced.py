# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "numba>=0.60"]
# ///
"""The reduced pick model of the optimizer (`optimize.py`), validated against bg-sim (`reference.py`).

The same laws as the bg-sim models where they decide the holding margin, with fewer parts:

* the gripper motion is prescribed: `planner.reference` on the 1 ms grid, held to second order
  between the ticks like `ToolMotion` (the arm is kinematic in both);
* the rods are rigid at their extended stop (bg-sim: compliant guides, about 145 Hz lateral), so
  the reduced model needs the cylinders out during the carry (`ret_hold = 0`, the default);
* every ACTIVE cup is the `SuctionCup` law: bellows springs, the smooth seal capacity A_eff dp,
  the lip lift with the moment loss chi, the Dahl lip slip and the vacuum chamber with its
  ejector, lip leak and the porous carton (inactive cups are retracted and carry nothing);
* the parcel (or the carton shell) is a rigid body on the four `ContactPoint` corners;
* the loose content is a second rigid body with the `SphereInBox` / `CylinderInBox` law.

Two phases: the seal (the cup pressures alone, from the lip contact to the lift start; the
gripper is at rest then) and the carry (everything, from the lift start to the place contact).
The holding margin of a zone is 1 - max U over the carry, as `PickMonitor`; a drop is a parcel
centre more than 20 mm from where it sat in the gripper at the lift start.

The right-hand side is compiled with numba (a run takes well under a second once compiled; the
first call compiles for about half a minute and caches the result next to this file).

    uv run examples/fanuc-pick/design/reduced.py [model name]    # one run, prints the margins
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numba as nb
import numpy as np
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import params as P  # noqa: E402
import planner  # noqa: E402

G0 = P.G0
# SuctionCup parameters the models leave at their defaults
CUP_DEF = dict(Cd=0.6, rho=1.2, p_tr=500.0, h_ref=5.0e-4, F_eps=0.1, v_eps=1.0e-4, p_eps=1.0, h_eps=1.0e-6)
D_DROP = 0.02
#: the numeric parameters of the kernel, in this order
PNAMES = ("A_eff", "L0", "k_ax", "d_ax", "k_tilt", "k_tor", "d_rot", "D_lip", "mu", "F_min", "k_lat", "d_lat",
          "A_lip0", "perm", "V_cup", "Q_max", "dp_max", "G_rel", "k_w", "xref_w", "c_w", "mu_w", "vs_w", "z_s",
          "r_s", "r_c", "l_c")
KIND = {"box": 0, "sphere": 1, "cylinder": 2}


# ------------------------------------------------------------------ small rotation helpers
@nb.njit(cache=True)
def quat_R(q):
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    w, x, y, z = q[0] / n, q[1] / n, q[2] / n, q[3] / n
    r = np.empty((3, 3))
    r[0, 0] = 1 - 2 * (y * y + z * z)
    r[0, 1] = 2 * (x * y - w * z)
    r[0, 2] = 2 * (x * z + w * y)
    r[1, 0] = 2 * (x * y + w * z)
    r[1, 1] = 1 - 2 * (x * x + z * z)
    r[1, 2] = 2 * (y * z - w * x)
    r[2, 0] = 2 * (x * z - w * y)
    r[2, 1] = 2 * (y * z + w * x)
    r[2, 2] = 1 - 2 * (x * x + y * y)
    return r


@nb.njit(cache=True)
def R_quat(r):
    q = np.empty(4)
    tr = r[0, 0] + r[1, 1] + r[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q[0], q[1], q[2], q[3] = 0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q[0], q[1], q[2], q[3] = (r[2, 1] - r[1, 2]) / s, 0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q[0], q[1], q[2], q[3] = (r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s
    else:
        s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q[0], q[1], q[2], q[3] = (r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s
    if q[0] < 0:
        q = -q
    return q


@nb.njit(cache=True)
def rotz(a):
    c, s = math.cos(a), math.sin(a)
    r = np.zeros((3, 3))
    r[0, 0], r[0, 1], r[1, 0], r[1, 1], r[2, 2] = c, -s, s, c, 1.0
    return r


@nb.njit(cache=True)
def cross(a, b):
    out = np.empty(3)
    out[0] = a[1] * b[2] - a[2] * b[1]
    out[1] = a[2] * b[0] - a[0] * b[2]
    out[2] = a[0] * b[1] - a[1] * b[0]
    return out


@nb.njit(cache=True)
def qdot(q, w):
    """d/dt q for the body rate w (body frame)."""
    out = np.empty(4)
    out[0] = -0.5 * (w[0] * q[1] + w[1] * q[2] + w[2] * q[3])
    out[1] = 0.5 * (w[0] * q[0] + w[2] * q[2] - w[1] * q[3])
    out[2] = 0.5 * (w[1] * q[0] + w[0] * q[3] - w[2] * q[1])
    out[3] = 0.5 * (w[2] * q[0] + w[1] * q[1] - w[0] * q[2])
    return out


# ------------------------------------------------------------------ the laws
CD, RHO_AIR, P_TR, H_REF, F_EPS, V_EPS, P_EPS, H_EPS = (CUP_DEF[k] for k in
                                                         ("Cd", "rho", "p_tr", "h_ref", "F_eps", "v_eps", "p_eps", "h_eps"))
FL_K, FL_XREF, FL_C, FL_MU, FL_VS = (P.FLOOR[k] for k in ("k", "xref", "c", "mu", "vs"))


@nb.njit(cache=True)
def cup_law(gp, r, R, rd, wr, e, p, out):
    """SuctionCup: fills out = [f_cup (3, cup frame), tau_pt (3, point frame), de (2), U, h, Qin]."""
    A_eff, L0, k_ax, d_ax, k_tilt, k_tor, d_rot, D_lip = gp[0], gp[1], gp[2], gp[3], gp[4], gp[5], gp[6], gp[7]
    mu, F_min, k_lat, d_lat, A_lip0, perm = gp[8], gp[9], gp[10], gp[11], gp[12], gp[13]
    q = R_quat(R)
    dp = 0.5 * (-p + math.sqrt(p * p + P_EPS * P_EPS))
    Fcap = A_eff * dp
    ext = -r[2] - L0
    Fs = k_ax * ext - d_ax * rd[2]
    Mb0 = 2 * q[0] * k_tilt * q[1] + d_rot * wr[0]
    Mb1 = 2 * q[0] * k_tilt * q[2] + d_rot * wr[1]
    Mb2 = 2 * q[0] * k_tor * q[3] + d_rot * wr[2]
    Mbt = math.sqrt(Mb0 * Mb0 + Mb1 * Mb1 + 1e-12 * k_tilt * k_tilt)
    a = (Fs + 4 * Mbt / D_lip - Fcap) / k_ax
    h = 0.5 * (a + math.sqrt(a * a + H_EPS * H_EPS))
    T = 0.5 * (Fs + Fcap - math.sqrt((Fs - Fcap) ** 2 + F_EPS * F_EPS))
    N = Fcap - T
    chi = 1.0 / (1.0 + (h / H_REF) ** 2)
    Fc = mu * N + F_min
    vn = math.sqrt(rd[0] * rd[0] + rd[1] * rd[1] + V_EPS * V_EPS)
    rx, ry = k_lat * e[0] / Fc, k_lat * e[1] / Fc
    rho4 = (rx * rx + ry * ry) ** 2
    gs = rho4 / (1 + 0.01 * rho4)
    dex = rd[0] - vn * rx * gs
    dey = rd[1] - vn * ry * gs
    Flx = k_lat * e[0] + d_lat * dex
    Fly = k_lat * e[1] + d_lat * dey
    F_lat = math.sqrt(Flx * Flx + Fly * Fly)
    out[0], out[1], out[2] = -Flx, -Fly, T
    out[3], out[4], out[5] = -chi * Mb0, -chi * Mb1, -chi * Mb2
    out[6], out[7] = dex, dey
    out[8] = (T + 4 * chi * Mbt / D_lip + F_lat / mu) / (Fcap + F_EPS)
    out[9] = h
    A_lip = A_lip0 + math.pi * D_lip * h
    Q_leak = CD * A_lip * (-p) * math.sqrt(2.0 / (RHO_AIR * math.sqrt(p * p + P_TR * P_TR)))
    out[10] = Q_leak + perm * A_eff * dp


@nb.njit(cache=True)
def generator_flow(gp, u, p):
    """VacuumGenerator (n = 1, vent to atmosphere): free-air flow drawn out of the cup."""
    Q_max, dp_max, G_rel = gp[15], gp[16], gp[17]
    return u * Q_max * (1.0 - (-p) / dp_max) + (1.0 - u) * G_rel * p


@nb.njit(cache=True)
def contact_point(h, vel_n, vtx, vty):
    """ContactPoint normal and friction law (h = height above the plane, vel_n its rate)."""
    eps, feps = 1e-6, 1e-6
    delta = -h
    r = math.sqrt(delta * delta + eps * eps)
    x = 0.5 * eps * eps / (r - delta) if r - delta > 1e-300 else delta
    sig = x / r
    xd = -sig * vel_n
    Fk = FL_K * x * math.sqrt(x / FL_XREF)
    Fx = Fk * (1 + FL_C * xd)
    fn = sig * 0.5 * (Fx + math.sqrt(Fx * Fx + feps * feps))
    return fn, FL_MU * fn * math.tanh(vtx / FL_VS), FL_MU * fn * math.tanh(vty / FL_VS)


@nb.njit(cache=True)
def wall_law(gp, d, u_n_out, uts):
    """SphereInBox/CylinderInBox normal and friction law at one wall (u_n_out = slip velocity
    along the outward wall axis, uts = |tangential slip|^2)."""
    k_w, xref_w, c_w, mu_w, vs_w = gp[18], gp[19], gp[20], gp[21], gp[22]
    eps, feps = 1e-6, 1e-6
    rt = math.sqrt(d * d + eps * eps)
    x = 0.5 * (d + rt)
    sg = 0.5 * (1 + d / rt)
    Fk = k_w * x * math.sqrt(x / xref_w)
    Fx = Fk * (1 + c_w * sg * u_n_out)
    fn = sg * 0.5 * (Fx + math.sqrt(Fx * Fx + feps * feps))
    S = math.sqrt(uts + (vs_w / 100) ** 2)
    return fn, mu_w * fn * math.tanh(S / vs_w) / S


@nb.njit(cache=True)
def content_forces(gp, kind, hbox, cb, Rb, vb_w, wb_w, cc, Rc, vc_w, wc_w, res):
    """Wall forces between the carton and the content, as the generated SphereInBox /
    CylinderInBox blocks. res = [force on the content (world, 3), torque on the content (content
    body frame, 3), torque on the carton about cb (world, 3), sum of the normal forces]."""
    r_s, r_c, l_c = gp[24], gp[25], gp[26]
    rr = Rb.T @ (cc - cb)
    wb, vb = Rb.T @ wb_w, Rb.T @ vb_w
    wcb, vcb = Rb.T @ wc_w, Rb.T @ vc_w
    Fsum = np.zeros(3)
    Tc = np.zeros(3)
    Tbx = np.zeros(3)
    Fmag = 0.0
    ax = Rb.T @ Rc[:, 2]
    npts = 1 if kind == 1 else 2
    e = np.zeros(3)
    for mi in range(npts):
        sgn_end = 1.0 if mi == 0 else -1.0
        for i in range(3):
            for s in (1.0, -1.0):
                e[:] = 0.0
                e[i] = s
                if kind == 1:
                    arm = r_s * e
                    d = r_s + s * rr[i] - hbox[i]
                else:
                    m = rr + sgn_end * 0.5 * l_c * ax
                    ea = s * ax[i]
                    nr = math.sqrt(1 - ea * ea + 1e-6)
                    Pk = m + r_c * (e - ea * ax) / nr
                    d = s * Pk[i] - hbox[i]
                    arm = Pk - rr
                if d < -0.01:
                    continue
                Pp = rr + arm
                u = (vcb + cross(wcb, arm)) - (vb + cross(wb, Pp))
                ut = u.copy()
                ut[i] = 0.0
                fn, gf = wall_law(gp, d, s * u[i], ut[0] * ut[0] + ut[1] * ut[1] + ut[2] * ut[2])
                Fk = -gf * ut
                Fk[i] = -s * fn
                Fsum += Fk
                Tc += cross(arm, Fk)
                Tbx += cross(Pp, -Fk)
                Fmag += fn
    Fc_w = Rb @ Fsum
    res[0:3] = Fc_w
    res[3:6] = Rc.T @ (Rb @ Tc)
    res[6:9] = Rb @ Tbx
    res[9] = Fmag


@nb.njit(cache=True)
def carry_rhs(t, y, gp, tg, pos, vel, acc, psi, wz, wzd, uv, cupG, ptB, Rpt, corners, m, J, kind, mc, Jc,
              hbox, rec):
    """The carry phase right-hand side; rec gets the utilisation of every active cup and the
    content wall force."""
    dt = tg[1] - tg[0]
    k = int((t - tg[0]) / dt + 1e-9)
    k = min(max(k, 0), len(tg) - 1)
    tau = t - tg[k]
    pG = pos[k] + vel[k] * tau + 0.5 * acc[k] * tau * tau
    vG = vel[k] + acc[k] * tau
    RG = rotz(psi[k] + wz[k] * tau + 0.5 * wzd[k] * tau * tau)
    wG = np.zeros(3)
    wG[2] = wz[k] + wzd[k] * tau
    c, q, v, w = y[0:3], y[3:7], y[7:10], y[10:13]
    R = quat_R(q)
    F = np.zeros(3)
    F[2] = -m * G0
    Tb = np.zeros(3)
    dy = np.zeros(len(y))
    ww = R @ np.ascontiguousarray(w)
    na = cupG.shape[0]
    cl = np.empty(11)
    wC = RG.T @ wG
    RP = R @ Rpt
    Rrel = RG.T @ RP
    for i in range(na):
        j = 13 + 3 * i
        oc_rel = RG @ cupG[i]
        oC = pG + oc_rel
        vC = vG + cross(wG, oc_rel)
        arm = R @ ptB[i]
        oP = c + arm
        vP = v + cross(ww, arm)
        r = RG.T @ (oP - oC)
        rd = RG.T @ (vP - vC) - cross(wC, r)
        wr = RP.T @ ww - Rrel.T @ wC
        p = y[j + 2]
        cup_law(gp, r, Rrel, rd, wr, y[j:j + 2], p, cl)
        dy[j] = cl[6]
        dy[j + 1] = cl[7]
        dy[j + 2] = P.P_ATM * (cl[10] - generator_flow(gp, uv[i, k], p)) / gp[14]
        Fw = RG @ cl[0:3]
        F += Fw
        Tb += R.T @ (RP @ cl[3:6]) + cross(ptB[i], R.T @ Fw)
        rec[i] = cl[8]
    # support plane under the corners
    for ci in range(4):
        pc = corners[ci]
        arm = R @ pc
        Pc = c + arm
        vp = v + cross(ww, arm)
        fn, ftx, fty = contact_point(Pc[2] - gp[23], vp[2], vp[0], vp[1])
        Fw = np.array([-ftx, -fty, fn])
        F += Fw
        Tb += cross(pc, R.T @ Fw)
    rec[na] = 0.0
    if kind != 0:
        n = len(y)
        cc, qc, vc, wc = y[n - 13:n - 10], y[n - 10:n - 6], y[n - 6:n - 3], y[n - 3:n]
        Rc = quat_R(qc)
        res = np.empty(10)
        content_forces(gp, kind, hbox, c, R, v, ww, cc, Rc, vc, Rc @ wc, res)
        F -= res[0:3]
        Tb += R.T @ res[6:9]
        Fc = res[0:3].copy()
        Fc[2] -= mc * G0
        dy[n - 13:n - 10] = vc
        dy[n - 10:n - 6] = qdot(qc, wc)
        dy[n - 6:n - 3] = Fc / mc
        dy[n - 3:n] = (res[3:6] - cross(wc, Jc * wc)) / Jc
        rec[na] = res[9]
    dy[0:3] = v
    dy[3:7] = qdot(q, w)
    dy[7:10] = F / m
    dy[10:13] = (Tb - cross(w, J * w)) / J
    return dy


def generator_flow_py(g: dict, u: float, p: float) -> float:
    return u * g["Q_max"] * (1.0 - (-p) / g["dp_max"]) + (1.0 - u) * g["G_rel"] * p


# ------------------------------------------------------------------ the plant
class Pick:
    def __init__(self, globals_: dict, kind: str = "box", ref: dict | None = None) -> None:
        g = dict(globals_)
        g.update({"xref_w": P.CONTENT_CONTACT["xref_w"], "vs_w": P.CONTENT_CONTACT["vs_w"]})
        for key in ("r_s", "r_c", "l_c"):
            g.setdefault(key, 0.0)
        self.g, self.kind = g, kind
        self.ref = ref if ref is not None else planner.reference(g)
        r = self.ref
        self.t = np.ascontiguousarray(r["t"], dtype=float)
        self.dt = float(self.t[1] - self.t[0])
        tl = r["tl"]
        self.tB, self.tL, self.tE = tl["tB"], tl["tL"], tl["tE"]
        # gripper world position, yaw and their rates per tick
        self.pos = np.ascontiguousarray(r["g"][4:7].T)
        self.psi = np.ascontiguousarray(2 * np.arctan2(r["g"][3], r["g"][0]))
        cps, sps = np.cos(self.psi), np.sin(self.psi)
        vb, ab = r["V"][3:6], r["Vd"][3:6]
        wz = r["V"][2]
        # world rates from the body twist: v = Rz v_b, a = Rz (vd_b + w x v_b)
        ax_b = ab[0] - wz * vb[1]
        ay_b = ab[1] + wz * vb[0]
        self.vel = np.ascontiguousarray(np.stack([cps * vb[0] - sps * vb[1], sps * vb[0] + cps * vb[1], vb[2]], axis=1))
        self.acc = np.ascontiguousarray(np.stack([cps * ax_b - sps * ay_b, sps * ax_b + cps * ay_b, ab[2]], axis=1))
        self.wz, self.wzd = np.ascontiguousarray(wz, dtype=float), np.ascontiguousarray(r["Vd"][2], dtype=float)
        # active cups and geometry
        self.act = [k for k in range(P.N_ZONES) if r["act"][k] > 0.5]
        self.uv = np.ascontiguousarray(np.array([r["uv"][k] for k in self.act], dtype=float).reshape(len(self.act), -1))
        la, psg = g["lay_deg"] * math.pi / 180, g["psig_deg"] * math.pi / 180
        q_ext = g["stroke"] + (g["F_ext"] + g["m_rod"] * G0) / g["k_stop"]
        zm = -(g["h_base"] + g["L_cyl"] + g["rod0"] + q_ext)
        cup_G, pt_B = [], []
        loose = kind != "box"
        cvec = np.zeros(3) if loose else np.array([g["cx"], g["cy"], g["cz"]])
        for k in self.act:
            dx, dy = P.ZONE_DIRS[k]
            xg = g["r_p"] * (dx * math.cos(la) - dy * math.sin(la))
            yg = g["r_p"] * (dx * math.sin(la) + dy * math.cos(la))
            cup_G.append([xg, yg, zm])
            pb = np.array([g["gx"] + math.cos(psg) * xg - math.sin(psg) * yg,
                           g["gy"] + math.sin(psg) * xg + math.cos(psg) * yg, g["H_p"] / 2])
            pt_B.append(pb - cvec)
        self.cup_G = np.array(cup_G, dtype=float).reshape(-1, 3)
        self.pt_B = np.array(pt_B, dtype=float).reshape(-1, 3)
        self.R_pt = rotz(psg)
        self.corners = np.array([[sx * g["L_p"] / 2, sy * g["W_p"] / 2, -g["H_p"] / 2]
                                 for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1))]) - cvec
        self.mc, self.Jc, self.hbox = 1.0, np.ones(3), np.ones(3)
        if loose:
            self.m = g["m_shell"]
            L, W, H = g["L_p"], g["W_p"], g["H_p"]
            A = W * H + L * H + L * W
            ms = g["m_shell"]
            self.J = np.array([
                ms / A * (W * H * (W * W + H * H) / 12 + L * H * (H * H / 12 + W * W / 4) + L * W * (W * W / 12 + H * H / 4)),
                ms / A * (L * H * (L * L + H * H) / 12 + W * H * (H * H / 12 + L * L / 4) + L * W * (L * L / 12 + H * H / 4)),
                ms / A * (L * W * (L * L + W * W) / 12 + W * H * (W * W / 12 + L * L / 4) + L * H * (L * L / 12 + W * W / 4)),
            ])
            self.hbox = np.array([L / 2 - g["wall"], W / 2 - g["wall"], H / 2 - g["wall"]])
            if kind == "sphere":
                self.mc, rr = g["m_s"], g["r_s"]
                self.Jc = np.full(3, 0.4 * g["m_s"] * rr * rr)
            else:
                self.mc, rr, lc = g["m_c"], g["r_c"], g["l_c"]
                self.Jc = np.array([g["m_c"] * (3 * rr * rr + lc * lc) / 12] * 2 + [g["m_c"] * rr * rr / 2])
        else:
            self.m = g["m_p"]
            self.J = np.array([g["Jpx"], g["Jpy"], g["Jpz"]], dtype=float)
        self.na = len(self.act)
        self.gp = np.array([float(g[k]) for k in PNAMES])
        self.kind_i = KIND[kind]
        self._rec = np.zeros(self.na + 1)

    # -------------------------------------------------------------- gripper motion (FOH like ToolMotion)
    def gripper(self, t: float):
        k = min(max(int(t / self.dt + 1e-9), 0), len(self.t) - 1)
        tau = t - self.t[k]
        p = self.pos[k] + self.vel[k] * tau + 0.5 * self.acc[k] * tau * tau
        v = self.vel[k] + self.acc[k] * tau
        psi = self.psi[k] + self.wz[k] * tau + 0.5 * self.wzd[k] * tau * tau
        wz = self.wz[k] + self.wzd[k] * tau
        return p, v, psi, wz, k

    # -------------------------------------------------------------- initial state at the lift start
    def initial(self, p_cups: np.ndarray) -> np.ndarray:
        g = self.g
        psp = g["psip_deg"] * math.pi / 180
        R0 = rotz(psp)
        cvec = np.zeros(3) if self.kind != "box" else np.array([g["cx"], g["cy"], g["cz"]])
        c0 = np.array([g["xp"], g["yp"], g["z_s"] + g["H_p"] / 2 - g["pen0"]]) + R0 @ cvec
        y = [c0, R_quat(R0), np.zeros(3), np.zeros(3)]
        for k in range(self.na):
            y.append(np.array([0.0, 0.0, p_cups[k]]))
        if self.kind != "box":
            rr = g["r_s"] if self.kind == "sphere" else g["r_c"]
            cc = np.array([g["xp"], g["yp"], g["z_s"] + g["wall"] + rr - g["pen_c"] - g["pen0"]])
            qc = R_quat(R0) if self.kind == "sphere" else R_quat(R0 @ np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float))
            y += [cc, qc, np.zeros(3), np.zeros(3)]
        return np.concatenate(y)

    # -------------------------------------------------------------- seal phase: the cup pressures alone
    def seal(self) -> np.ndarray:
        """Cup pressures at the lift start: lip contact (the last d_press of the approach) to tL,
        the lips sealed (h = 0), the ejector on."""
        g = self.g
        zB = self.pos[int(round(self.tB / self.dt)), 2]
        # contact time: the flange within the press depth of B on the approach
        idx = np.nonzero((self.t <= self.tB) & (self.pos[:, 2] - zB > g["d_press"]))[0]
        t_c = float(self.t[idx[-1]]) if len(idx) else self.tB
        t_on = self.tB - g["t_vac"]

        def rhs(t, y):
            out = np.empty_like(y)
            for i, p in enumerate(y):
                dp = 0.5 * (-p + math.sqrt(p * p + 1.0))
                Q_leak = CD * g["A_lip0"] * (-p) * math.sqrt(2.0 / (RHO_AIR * math.sqrt(p * p + P_TR ** 2)))
                Q_por = g["perm"] * g["A_eff"] * dp
                u = 1.0 if t >= t_on else 0.0
                out[i] = P.P_ATM * (Q_leak + Q_por - generator_flow_py(g, u, p)) / g["V_cup"]
            return out

        if self.tL <= t_c:
            return np.zeros(self.na)
        sol = solve_ivp(rhs, (t_c, self.tL), np.zeros(self.na), method="LSODA", rtol=1e-7, atol=1e-3)
        return sol.y[:, -1]

    # -------------------------------------------------------------- carry phase
    def rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        return carry_rhs(t, y, self.gp, self.t, self.pos, self.vel, self.acc, self.psi, self.wz, self.wzd,
                         self.uv, self.cup_G, self.pt_B, self.R_pt, self.corners, float(self.m), self.J,
                         self.kind_i, float(self.mc), self.Jc, self.hbox, self._rec)

    def run(self, rtol: float = 1e-5, atol: float = 1e-7, n_out: int | None = None) -> dict:
        """The carry; U is sampled every 1 ms (as PickMonitor) unless n_out is given."""
        p0 = self.seal()
        y0 = self.initial(p0)
        t0, t1 = self.tL, self.tE
        if n_out is None:
            n_out = int(round((t1 - t0) / P.TS)) + 1
        sol = solve_ivp(self.rhs, (t0, t1), y0, method="LSODA", rtol=rtol, atol=atol, max_step=2e-3,
                        t_eval=np.linspace(t0, t1, n_out))
        if not sol.success:
            return {"ok": False, "message": sol.message, "T_cyc": self.ref["T_cyc"]}
        Ut = np.zeros((self.na, len(sol.t)))
        Fw = np.zeros(len(sol.t))
        sep = np.zeros(len(sol.t))
        rel0 = None
        for n, (tt, yy) in enumerate(zip(sol.t, sol.y.T, strict=True)):
            self.rhs(tt, yy)
            Ut[:, n] = self._rec[:self.na]
            Fw[n] = self._rec[self.na]
            pG, _, psi, _, _ = self.gripper(tt)
            rel = rotz(psi).T @ (yy[0:3] - pG)
            if rel0 is None:
                rel0 = rel
            sep[n] = float(np.linalg.norm(rel - rel0))
        # the carry window [tL, tE): drop the last instant (the place contact)
        Umax = Ut[:, :-1].max(axis=1) if Ut.shape[1] > 1 else Ut[:, 0]
        margins = np.ones(P.N_ZONES)
        for i, k in enumerate(self.act):
            margins[k] = 1.0 - Umax[i]
        dropped = bool(sep.max() > D_DROP)
        return {
            "ok": True, "T_cyc": self.ref["T_cyc"], "margins": margins.tolist(), "M_tot": float(margins.min()),
            "dropped": dropped, "sep_max": float(sep.max()), "dp_lift": [float(-p) for p in p0],
            "t": sol.t, "U": Ut, "Fwall": Fw, "sep": sep, "y": sol.y, "act": self.act,
        }


def globals_of(model: str) -> tuple[dict, str]:
    """Numeric globals and plant kind of a model of build_models.py."""
    import build_models as B

    kind, _comment, ov = B.all_scenarios()[model]
    ov = {**B.kind_overrides(kind), **ov}
    return P.eval_globals(P.global_rows() + B.extra_rows(kind), ov), kind


def main(argv: list[str]) -> int:
    import time

    model = argv[0] if argv else "pick-place"
    g, kind = globals_of(model)
    t0 = time.time()
    res = Pick(g, kind).run()
    print(f"{model}: {time.time() - t0:.1f} s  T_cyc {res['T_cyc']:.3f}  M_tot {res.get('M_tot')}  "
          f"dropped {res.get('dropped')}  sep {res.get('sep_max')}")
    print("margins", np.round(res.get("margins", []), 3), "dp at lift", np.round(res.get("dp_lift", []), 0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
