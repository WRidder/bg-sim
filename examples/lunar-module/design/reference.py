# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Independent reference: the lunar module's flight equations integrated with scipy.

The same physics and the same guidance as the bond-graph models, written from scratch as a
rigid body in the inertial site frame (origin at the landing site, x downrange, z up, the Moon's
centre at (0, 0, -R)):

    m dv/dt = T x_b + F_gravity,          dp/dt = v
    J dw/dt = tau_RCS - w x (J w),         dq/dt = q (x) [0, w] / 2
    dm/dt   = -T / c,                      dT/dt = (T_cmd - T) / tau_engine

(m dv/dt = F is the variable-mass law for mass that leaves at the body's own velocity; the bond
graph gets it from its modulated inertia and the outflow MRs.) The guidance, throttle logic,
attitude loop and inertia law are the ones of the Julia blocks in library/, re-implemented here.
Mode switches (throttle recovery, phase changes, engine cutoff) are solve_ivp events.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data as d  # noqa: E402

C = np.array([0.0, 0.0, -d.RM])
EY = np.array([0.0, 1.0, 0.0])


def rotm(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[w * w + x * x - y * y - z * z, 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), w * w - x * x + y * y - z * z, 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), w * w - x * x - y * y + z * z]])


def quat_from_rotm(R):
    tr = np.trace(R)
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        return np.array([0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s])
    i = int(np.argmax(np.diag(R)))
    if i == 0:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        return np.array([(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s])
    if i == 1:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        return np.array([(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s])
    s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
    return np.array([(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s])


def gravity(p, scale=1.0):
    rc = p - C
    r = np.linalg.norm(rc)
    return -scale * d.MU * rc / r ** 3


def desired_frame(u, phi):
    """Desired body axes: x along the thrust direction u, z ('windows') = e_y x u turned by phi
    about u (phi = 0: windows up / forward, pi: windows down)."""
    x = u / np.linalg.norm(u)
    z0 = np.cross(EY, x)
    z0 /= np.linalg.norm(z0)
    z = math.cos(phi) * z0 + math.sin(phi) * np.cross(x, z0)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


def attitude_torque(R, w, Rd, J, wn, zeta, tmax):
    E = Rd.T @ R - R.T @ Rd
    e = 0.5 * np.array([E[2, 1], E[0, 2], E[1, 0]])
    tau = np.asarray(J) * (-wn * wn * e - 2 * zeta * wn * w)
    return np.clip(tau, -tmax, tmax)


def interp(x, xs, ys):
    return float(np.interp(x, xs, ys))


@dataclass
class Descent:
    """Powered descent PDI -> touchdown. `phase`: 0 trim+FTP (P63), recovered (P63), P64, P66."""
    range_pdi: float
    t_hg: float = d.T_HG
    t_p66: float = d.T_P66
    tgo63_hg: float = 60.0
    a_hg: tuple = (-1.3, 0.0, 0.4)
    t64_end: float = 690.0
    h64: float = 30.0
    v64: float = -0.9144
    isp: float = d.DPS_ISP
    gravity_scale: float = 1.0
    p66_rate_scale: float = 1.0
    tgt63: dict = field(default_factory=dict)

    def __post_init__(self):
        x_hg = -d.AIM_SHIFT - d.RANGE_HG
        vh = math.sqrt(d.V_HG_PREMISSION ** 2 - d.HDOT_HG ** 2)
        r = np.array([x_hg, 0.0, d.H_HG])
        v = np.array([vh, 0.0, d.HDOT_HG])
        a = np.array(self.a_hg)
        dt = self.tgo63_hg
        self.tgt63 = {"r": r + v * dt + 0.5 * a * dt * dt, "v": v + a * dt, "a": a, "T": self.t_hg + dt}
        self.tgt64 = {"r": np.array([-d.AIM_SHIFT, 0.0, self.h64]), "v": np.array([0.0, 0.0, self.v64]),
                      "a": np.zeros(3), "T": self.t64_end}
        self.c = self.isp * d.G0
        self.m_dry = d.M_PDI - d.PROP_PDI

    def J(self, m):
        return np.array(d.j_of_m(m, d.M_PDI, d.J_PDI, d.M_LANDING, d.J_LANDING))

    @staticmethod
    def quadratic(p, v, tgt, t):
        tgo = tgt["T"] - t
        return tgt["a"] + 12 * (tgt["r"] - p) / tgo ** 2 - 6 * (v + tgt["v"]) / tgo

    def accel_cmd(self, t, p, v):
        if t < self.t_hg:
            return self.quadratic(p, v, self.tgt63, t)
        if t < self.t_p66:
            return self.quadratic(p, v, self.tgt64, t)
        h = (np.linalg.norm(p - C) - d.RM) / d.FT
        rate = interp(h, d.P66_H, d.P66_RATE) * d.FT * self.p66_rate_scale
        fwd = interp(h, d.P66_FWD_H, d.P66_FWD) * d.FT
        ah = np.clip((np.array([fwd, 0.0]) - v[0:2]) / d.TAU_H, -d.A_H_MAX, d.A_H_MAX)
        return np.array([ah[0], ah[1], (-rate - v[2]) / d.TAU_V])

    def command(self, t, y, mode):
        p, v, q, w, m, T = y[0:3], y[3:6], y[6:10], y[10:13], y[13], y[14]
        at = self.accel_cmd(t, p, v) - gravity(p, self.gravity_scale)
        treq = m * np.linalg.norm(at)
        u = at / np.linalg.norm(at)
        if mode["off"]:
            tc = 0.0
        elif t < d.T_TRIM:
            tc = d.DPS_MIN * d.DPS_RATED
        elif mode["ftp"]:
            tc = d.DPS_FTP
        else:
            tc = min(max(treq, d.DPS_MIN * d.DPS_RATED), d.DPS_MAX * d.DPS_RATED)
        return u, tc, treq

    def phi(self, t):
        return math.pi * min(max((d.T_YAW_END - t) / (d.T_YAW_END - d.T_YAW_START), 0.0), 1.0)

    def rhs(self, t, y, mode):
        p, v, q, w, m, T = y[0:3], y[3:6], y[6:10], y[10:13], y[13], y[14]
        R = rotm(q)
        u, tc, _ = self.command(t, y, mode)
        J = self.J(m)
        tau = attitude_torque(R, w, desired_frame(u, self.phi(t)), J, d.ATT_WN, d.ATT_ZETA, d.RCS_TORQUE)
        acc = (T * R[:, 0]) / m + gravity(p, self.gravity_scale)
        wd = (tau - np.cross(w, J * w)) / J
        qw, qx, qy, qz = q
        qd = 0.5 * np.array([-qx * w[0] - qy * w[1] - qz * w[2], qw * w[0] + qy * w[2] - qz * w[1],
                             qw * w[1] + qz * w[0] - qx * w[2], qw * w[2] + qx * w[1] - qy * w[0]])
        return np.concatenate([v, acc, qd, wd, [-T / self.c], [(tc - T) / d.TAU_ENGINE], [T / m]])

    def pad_height(self, y):
        """Lowest footpad sole above the sphere."""
        R = rotm(y[6:10])
        hs = []
        for b in ((-d.D_CG, d.TREAD, 0.0), (-d.D_CG, -d.TREAD, 0.0), (-d.D_CG, 0.0, d.TREAD), (-d.D_CG, 0.0, -d.TREAD)):
            pw = y[0:3] + R @ np.array(b)
            hs.append(np.linalg.norm(pw - C) - d.RM)
        return min(hs)

    def initial(self):
        s = d.pdi_state(self.range_pdi)
        p, v = np.array(s["p"]), np.array(s["v"])
        at = self.quadratic(p, v, self.tgt63, 0.0) - gravity(p, self.gravity_scale)
        q0 = quat_from_rotm(desired_frame(at, math.pi))
        return np.concatenate([p, v, q0, np.zeros(3), [d.M_PDI], [d.DPS_MIN * d.DPS_RATED], [0.0]])

    def run(self, t_end=780.0, dt=0.1, rtol=1e-10, atol=1e-8):
        mode = {"ftp": True, "off": False}
        y0 = self.initial()
        ts, ys, ev = [], [], {}
        breaks = sorted({d.T_TRIM, self.t_hg, self.t_p66, d.T_YAW_START, d.T_YAW_END})
        t0 = 0.0
        grid = np.round(np.arange(0.0, t_end + 1e-9, dt), 9)

        def rec(sol, a, b):
            g = grid[(grid >= a - 1e-12) & (grid < b - 1e-12)]
            if len(g):
                ts.extend(g)
                ys.extend(sol.sol(g).T)

        while t0 < t_end - 1e-12:
            t1 = min([b for b in breaks if b > t0 + 1e-12] + [t_end])
            events = []

            def e_rec(t, y, mode=mode):
                return self.command(t, y, mode)[2] - d.DPS_RECOVER * d.DPS_RATED
            e_rec.terminal = True
            e_rec.direction = -1

            def e_td(t, y):
                return self.pad_height(y)
            e_td.terminal = True
            e_td.direction = -1

            def e_fuel(t, y):
                return y[13] - self.m_dry - d.PROP_UNUSABLE
            e_fuel.terminal = True
            e_fuel.direction = -1
            if mode["ftp"] and t0 >= d.T_TRIM - 1e-9:
                events.append(e_rec)
            if not mode["off"]:
                events += [e_td, e_fuel]
            sol = solve_ivp(lambda t, y: self.rhs(t, y, mode), (t0, t1), y0, method="DOP853", rtol=rtol, atol=atol,
                            dense_output=True, events=events or None)
            te = sol.t[-1]
            rec(sol, t0, te)
            if sol.status == 1:
                for k, e in enumerate(events):
                    if len(sol.t_events[k]):
                        if e is e_rec:
                            mode["ftp"] = False
                            ev["throttle_recovery"] = te
                        elif e is e_td:
                            mode["off"] = True
                            ev["touchdown"] = te
                            ev["td_state"] = sol.y[:, -1].copy()
                        else:
                            mode["off"] = True
                            ev["fuel_out"] = te
            y0 = sol.y[:, -1]
            t0 = te
        out = {"t": np.array(ts), "y": np.array(ys), "ev": ev}
        return out


@dataclass
class Ascent:
    isp: float = d.APS_ISP
    thrust: float = d.APS_THRUST
    gravity_scale: float = 1.0
    steer: float = 1.0
    tgo_min: float = 1.0

    def __post_init__(self):
        self.c = self.isp * d.G0
        self.m_dry = d.M_LIFTOFF - d.APS_PROP

    def J(self, m):
        return np.array(d.j_of_m(m, d.M_LIFTOFF, d.J_LIFTOFF, d.M_INSERTION, d.J_INSERTION))

    def local(self, p, v):
        rc = p - C
        r = np.linalg.norm(rc)
        er = rc / r
        eh = np.cross(EY, er)
        eh /= np.linalg.norm(eh)
        return r, er, eh, float(v @ er), float(v @ eh)

    def direction(self, t, y, mode):
        p, v, m, T = y[0:3], y[3:6], y[13], y[14]
        r, er, eh, rdot, vh = self.local(p, v)
        if not mode["insert"]:
            return er
        aT = max(T, 1.0) / m
        vgo = math.hypot(d.ASC_VH_T - vh, d.ASC_RDOT_T - rdot)
        tgo = max(m * self.c / max(T, 1.0) * (1 - math.exp(-vgo / self.c)), self.tgo_min)
        rT = d.RM + d.ASC_H_T
        ar = 6 * (rT - r - rdot * tgo) / tgo ** 2 - 2 * (d.ASC_RDOT_T - rdot) / tgo
        fr = ar + self.gravity_scale * d.MU / r ** 2 - vh * vh / r
        fr = min(fr, aT)
        fh = math.sqrt(max(aT * aT - fr * fr, 0.0))
        u = fr * er + fh * eh
        return u / np.linalg.norm(u)

    def rhs(self, t, y, mode):
        p, v, q, w, m, T = y[0:3], y[3:6], y[6:10], y[10:13], y[13], y[14]
        R = rotm(q)
        u = self.direction(t, y, mode)
        J = self.J(m)
        tau = attitude_torque(R, w, desired_frame(u, 0.0), J, d.ATT_WN, d.ATT_ZETA, d.RCS_TORQUE)
        tc = 0.0 if mode["off"] else self.thrust
        acc = (T * R[:, 0]) / m + gravity(p, self.gravity_scale)
        wd = (tau - np.cross(w, J * w)) / J
        qw, qx, qy, qz = q
        qd = 0.5 * np.array([-qx * w[0] - qy * w[1] - qz * w[2], qw * w[0] + qy * w[2] - qz * w[1],
                             qw * w[1] + qz * w[0] - qx * w[2], qw * w[2] + qx * w[1] - qy * w[0]])
        return np.concatenate([v, acc, qd, wd, [-T / self.c], [(tc - T) / d.TAU_APS], [T / m]])

    def initial(self):
        q0 = quat_from_rotm(desired_frame(np.array([0.0, 0.0, 1.0]), 0.0))
        return np.concatenate([[0.0, 0.0, d.H_ASC0], np.zeros(3), q0, np.zeros(3), [d.M_LIFTOFF], [self.thrust], [0.0]])

    def run(self, t_end=460.0, dt=0.1, rtol=1e-10, atol=1e-8):
        mode = {"insert": False, "off": False}
        y0 = self.initial()
        ts, ys, ev = [], [], {}
        t0 = 0.0
        grid = np.round(np.arange(0.0, t_end + 1e-9, dt), 9)
        while t0 < t_end - 1e-12:
            events = []

            def e_vr(t, y):
                return self.local(y[0:3], y[3:6])[3] - d.ASC_VRISE_RATE
            e_vr.terminal = True
            e_vr.direction = 1

            def e_cut(t, y):
                # the lagged thrust adds T tau / m after the cutoff: anticipate it
                return self.local(y[0:3], y[3:6])[4] + d.TAU_APS * y[14] / y[13] - d.ASC_VH_T
            e_cut.terminal = True
            e_cut.direction = 1

            def e_fuel(t, y):
                return y[13] - self.m_dry
            e_fuel.terminal = True
            e_fuel.direction = -1
            if not mode["insert"] and self.steer > 0.5:
                events.append(e_vr)
            if not mode["off"]:
                events += [e_cut, e_fuel]
            sol = solve_ivp(lambda t, y: self.rhs(t, y, mode), (t0, t_end), y0, method="DOP853", rtol=rtol,
                            atol=atol, dense_output=True, events=events or None)
            te = sol.t[-1]
            g = grid[(grid >= t0 - 1e-12) & (grid < te - 1e-12)]
            if len(g):
                ts.extend(g)
                ys.extend(sol.sol(g).T)
            if sol.status == 1:
                for k, e in enumerate(events):
                    if len(sol.t_events[k]):
                        if e is e_vr:
                            mode["insert"] = True
                            ev["pitchover"] = te
                        elif e is e_cut:
                            mode["off"] = True
                            ev["cutoff"] = te
                            ev["cut_state"] = sol.y[:, -1].copy()
                        else:
                            mode["off"] = True
                            ev["fuel_out"] = te
            y0 = sol.y[:, -1]
            t0 = te
        if abs(ts[-1] - t_end) > 1e-9:
            ts.append(t_end)
            ys.append(y0)
        return {"t": np.array(ts), "y": np.array(ys), "ev": ev}


def orbit(p, v):
    """Apolune and perilune heights above the mean radius."""
    rc = p - C
    r = np.linalg.norm(rc)
    e_spec = v @ v / 2 - d.MU / r
    a = -d.MU / (2 * e_spec)
    h = np.linalg.norm(np.cross(rc, v))
    e = math.sqrt(max(1 + 2 * e_spec * h * h / d.MU ** 2, 0.0))
    return a * (1 + e) - d.RM, a * (1 - e) - d.RM


def readouts(p, v):
    rc = p - C
    r = np.linalg.norm(rc)
    er = rc / r
    eh = np.cross(EY, er)
    eh /= np.linalg.norm(eh)
    return {"h": r - d.RM, "rdot": float(v @ er), "vh": float(v @ eh), "speed": float(np.linalg.norm(v)),
            "s": d.RM * math.atan2(rc[0], rc[2])}


if __name__ == "__main__":
    import json
    ds = json.loads((Path(__file__).resolve().parent / "design.json").read_text())
    des = Descent(**ds["descent_cfg"])
    r = des.run()
    print({k: v for k, v in r["ev"].items() if not isinstance(v, np.ndarray)})
