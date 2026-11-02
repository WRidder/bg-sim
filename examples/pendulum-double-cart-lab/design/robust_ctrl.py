"""The robust classical controllers of the double-cart lab rig on the robustness harness (plan C1-C3).

    uv run examples/pendulum-double-cart-lab/design/robustness.py run --controller robust_ctrl:make \
        --opt balance=mm_lqr [--opt swing=nominal|robust] [--opt mode=timed|rearm] --name robust-...

`LabController` is the firmware structure of the rig at 1 kHz, written out (the replica of
`lablib.firmware` for the timed variant, checked against it):

- the EKF of `lablib.setup` on the nominal twin (process noise lablib.EKF_Q, the nominal 2-sample delay),
  the cart Coulomb compensation (comp 1.0), the clamp;
- swing-up: the feed-forward + TVLQR tables of a plan (`design/design.json`, or the C2 robust plan
  `design/robust_c2.json`), started at t_on = 1 s (timed) or armed at the hanging rest (rearm);
- the catch: at tau = T_s (timed, the nominal firmware) or when the state enters the catch region
  z' P z < catch_tol of the balance controller from tau >= T_s - catch_lead (region);
- balance: a C1 balance law (`design/robust_c1.json`: the state feedback u = -K [x_hat; u_{k-1}; u_{k-2}] on
  the EKF estimate, or with its own linear observer gain L, initialised from the EKF at the catch);
- rearm (C3): a drop (a link more than drop_deg from upright, or z' P z > drop_tol) switches to `damp`: the
  energy of the links is removed through the cart (collocated partial feedback linearisation: the cart
  acceleration is the input, a = -k_E (E - E_hang) P_x / (1 + |..|) with P_x the links' horizontal momentum,
  plus cart centring), then a hanging LQR settles the links and the cart at the rail centre; at the hanging
  rest the swing-up is armed again (the plan shifted to the cart's position and the links' turn count);
- pump (C3, energy-based swing-up): the same partial feedback linearisation pumping the links' energy to the
  upright level (a = k_E (E_up - E) P_x, rail-aware), with the catch region of the balance law; a state-driven
  swing-up with no plan.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import lablib as lb

HERE = Path(__file__).resolve().parent
ql = lb.ql
TWO_PI = 2 * math.pi
G0 = 9.81


def wrap(a):
    return np.remainder(np.asarray(a) + math.pi, TWO_PI) - math.pi


def load_plan(name: str) -> dict:
    """Swing-up tables: 'nominal' (design.json) or a C2 plan in robust_c2.json."""
    if name == "nominal":
        d = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
        return {"t_s": d["t_s"], "tk": np.array(d["tk"]), "xs": np.array(d["xs"]), "uff": np.array(d["uff"]),
                "Ks": np.array(d["Ks"]), "Klqr": np.array(d["Klqr"])}
    d = json.loads((HERE / "robust_c2.json").read_text(encoding="utf-8"))["plans"][name]
    return {"t_s": d["t_s"], "tk": np.array(d["tk"]), "xs": np.array(d["xs"]), "uff": np.array(d["uff"]),
            "Ks": np.array(d["Ks"])}


def load_balance(name: str) -> dict:
    """A C1 balance law: {'K': (8,), 'L': (6, 3) or None, 'P': (6, 6) catch metric, 'catch_tol', 'drop_tol'}."""
    if name == "nominal":
        K = np.array(json.loads((HERE / "design.json").read_text(encoding="utf-8"))["Klqr"])
        return {"K": np.concatenate([K, [0.0, 0.0]]), "L": None, "P": None}
    d = json.loads((HERE / "robust_c1.json").read_text(encoding="utf-8"))["designs"][name]
    return {"K": np.array(d["K"], float), "L": None if d.get("L") is None else np.array(d["L"], float),
            "P": None if d.get("P") is None else np.array(d["P"], float),
            "catch_tol": d.get("catch_tol"), "drop_tol": d.get("drop_tol")}


class LabController:
    rate_hz = 1000.0

    def __init__(self, p_nominal: dict, balance: str = "nominal", swing: str = "nominal", mode: str = "timed",
                 catch: str | None = None, t_on: float = 1.0, catch_tol: float | None = None, catch_lead: float = 0.6,
                 drop_deg: float = 20.0, comp: float = 1.0, ekf_q=None, pump: bool = False, k_e: float = 40.0,
                 a_max: float = 25.0, e_lqr: float = 0.3, kc_x: float = 1.0, kc_v: float = 2.0, k_p: float = 10.0):
        self.p = p_nominal
        rs = lb.setup(p_nominal, lb.EFFECTS, "ekf", ekf_q=ekf_q, comp=comp)
        kw = rs.fw_kw
        self.ekf = kw["ekf"]
        self.d_ekf = int(p_nominal["delay"])
        self.fc, self.fc_eps = kw.get("fc_base", 0.0), kw.get("fc_eps", 0.01)
        self.u_max = float(p_nominal["u_max"])
        self.plan = load_plan(swing)
        self.bal = load_balance(balance)
        self.mode_kind = mode
        self.catch = catch or ("timed" if mode == "timed" else "region")
        self.t_on = float(t_on)
        self.catch_lead = float(catch_lead)
        self.drop = math.radians(float(drop_deg))
        self.pump = bool(pump) if not isinstance(pump, str) else pump.lower() in ("1", "true", "yes")
        self.k_e, self.a_max, self.e_lqr = float(k_e), float(a_max), float(e_lqr)
        self.kc = (float(kc_x), float(kc_v))
        self.k_p = float(k_p)
        # catch metric: the balance law's P (or the nominal LQR's cost-to-go)
        P = self.bal.get("P")
        if P is None:
            P = _lqr_P()
        self.P = P
        self.catch_tol = float(catch_tol if catch_tol is not None else (self.bal.get("catch_tol") or 25.0))
        # the observer model of a linear-observer balance law
        if self.bal["L"] is not None:
            import robust_lin as rl
            A, B, _ = rl.lin_cont(p_nominal)
            self.Ad, self.Bd = rl.zoh(A, B)
            self.H = np.zeros((3, 6))
            self.H[:, :3] = rl.T_REL
        # nominal twin functions for the partial feedback linearisation and the energy
        rig, alpha = lb.twin_rig(p_nominal | {"ripple_rel": 0.0, "cogging": 0.0})
        self.twin = lb.LabPlant(rig, alpha)
        self.alpha = alpha
        m, c, J = lb.link_props(p_nominal)
        self.m, self.c, self.J, self.L1 = m, c, J, p_nominal["L1"]
        self.E_up = G0 * (m[0] * c[0] + m[1] * (self.L1 + c[1]))
        self.K_hang = _hang_lqr(p_nominal)
        self.phase = 0

    # ---------------------------------------------------------------- run state
    def reset(self, *, seed: int, start: str):
        self.st = {}
        self.line = [0.0] * 8          # the commands applied, newest first (the EKF's input history)
        self.mode = "balance" if start == "upright" else ("hold" if self.mode_kind == "timed" else "settle")
        self.t_arm = self.t_on if self.mode_kind == "timed" else None
        self.offset = np.zeros(6)
        self.xo = None
        self.t_mode = 0.0
        self.n_drops = 0
        self.phase = 2 if self.mode == "balance" else 0
        self.rest_count = 0
        self.damping = True
        self.balance_init = True

    # ---------------------------------------------------------------- pieces
    def energy(self, z):
        """Energy of the links in the cart frame (kinetic relative to the cart + potential from the hanging
        rest) and the horizontal momentum P_x of the links relative to the cart (dE/dt = a P_x - losses)."""
        m, c, J, L1 = self.m, self.c, self.J, self.L1
        th1, th2, w1, w2 = z[1], z[2], z[4], z[5]
        v1 = np.array([-c[0] * math.cos(th1) * w1, -c[0] * math.sin(th1) * w1])
        v2 = np.array([-L1 * math.cos(th1) * w1 - c[1] * math.cos(th2) * w2, -L1 * math.sin(th1) * w1 - c[1] * math.sin(th2) * w2])
        T = 0.5 * m[0] * v1 @ v1 + 0.5 * J[0] * w1 * w1 + 0.5 * m[1] * v2 @ v2 + 0.5 * J[1] * w2 * w2
        V = G0 * (m[0] * c[0] * (math.cos(th1) + 1) + m[1] * (L1 * (math.cos(th1) + 1) + c[1] * (math.cos(th2) + 1)))
        Px = -(m[0] * v1[0] + m[1] * v2[0])
        return T + V, Px

    def volts_for_acc(self, z, a):
        """Collocated partial feedback linearisation on the nominal twin: the voltage that gives the cart
        acceleration a (the back-EMF, the friction and the link coupling included)."""
        q, qd = z[:3], z[3:]
        M = np.array(self.twin.mass_fn(q))
        r = np.array(self.twin.rhs_fn(q, qd, 0.0)).ravel()
        thdd = np.linalg.solve(M[1:, 1:], r[1:] - M[1:, 0] * a)
        F = M[0, 0] * a + M[0, 1:] @ thdd - r[0]
        return F / self.alpha

    def table(self, tau):
        pl = self.plan
        dt = pl["tk"][1] - pl["tk"][0]
        nt = len(pl["tk"])
        s = min(max(tau / dt, 0.0), nt - 1)
        i = min(int(math.floor(s)), nt - 2)
        w = s - i
        return ((1 - w) * pl["xs"][i] + w * pl["xs"][i + 1], (1 - w) * pl["uff"][i] + w * pl["uff"][i + 1],
                (1 - w) * pl["Ks"][i] + w * pl["Ks"][i + 1])

    def balance_u(self, xh, y):
        K = self.bal["K"]
        zb = xh.copy()
        zb[1:3] = wrap(zb[1:3])
        if self.bal["L"] is None:
            xb = zb
        else:
            if self.balance_init or self.xo is None:
                self.xo = zb.copy()
            else:
                xm = self.Ad @ self.xo + self.Bd[:, 0] * self.line[self.d_ekf]
                yr = np.array([y[0], wrap(y[1]), y[2]])
                innov = yr - self.H @ xm
                innov[1:] = wrap(innov[1:])
                self.xo = xm + self.bal["L"] @ innov
            xb = self.xo
        self.balance_init = False
        return -float(K[:6] @ xb) - K[6] * self.line[0] - K[7] * self.line[1]

    def damp_u(self, xh):
        """Energy removal, then the hanging LQR (the links to the hanging rest, the cart to the centre)."""
        E, Px = self.energy(xh)
        x, v = xh[0], xh[3]
        zh = xh.copy()
        zh[1:3] = wrap(zh[1:3] + math.pi)            # deviation from hanging
        x_stop = x + v * abs(v) / (2 * 0.6 * self.a_max)
        if abs(x_stop) > 0.6:
            # the rail first: brake (the stopping point would pass 0.6 m)
            a = -self.a_max * math.copysign(1.0, v) - 4.0 * x
        elif E > self.e_lqr or self.damping:
            self.damping = E > 0.5 * self.e_lqr
            a = -self.k_e * Px - self.kc[0] * x - self.kc[1] * v
        else:
            return -float(self.K_hang @ zh)
        a = min(max(a, -self.a_max), self.a_max)
        return self.volts_for_acc(xh, a)

    def pump_u(self, xh):
        E, Px = self.energy(xh)
        x, v = xh[0], xh[3]
        x_stop = x + v * abs(v) / (2 * 0.6 * self.a_max)
        if abs(x_stop) > 0.6:
            a = -self.a_max * math.copysign(1.0, v) - 4.0 * x       # the rail first
        else:
            a = self.k_p * (self.E_up - E) * Px - self.kc[0] * x - self.kc[1] * v
        a = min(max(a, -self.a_max), self.a_max)
        return self.volts_for_acc(xh, a)

    def in_catch(self, xh) -> bool:
        z = xh.copy()
        z[1:3] = wrap(z[1:3])
        return float(z @ self.P @ z) < self.catch_tol

    def at_rest(self, xh) -> bool:
        dev = wrap(xh[1:3] + math.pi)
        return bool(np.all(np.abs(dev) < math.radians(3.0)) and np.all(np.abs(xh[4:6]) < 0.15)
                    and abs(xh[0]) < 0.05 and abs(xh[3]) < 0.05)

    # ---------------------------------------------------------------- the tick
    def step(self, s) -> float:
        t = s.t
        pos = s.positions()
        y = np.array([pos[0], pos[1], pos[2] - pos[1]])
        xh = self.ekf.update(self.st, y, self.line[self.d_ekf])
        u = 0.0
        if self.mode == "hold":
            if t >= self.t_on - 1e-9:
                self.mode, self.t_arm = "swing", self.t_on
        if self.mode == "settle":
            # rearm: settle at the hanging rest (or pump), then arm
            if self.pump:
                self.mode, self.t_mode = "pump", t
            elif self.at_rest(xh):
                self.rest_count += 1
                if self.rest_count >= 100:
                    self.arm(t, xh)
            else:
                self.rest_count = 0
        if self.mode == "swing":
            tau = t - self.t_arm
            ts_ = self.plan["t_s"]
            if self.catch == "timed" and tau >= ts_ - 1e-9:
                self.to_balance()
            elif self.catch == "region" and tau >= ts_ - self.catch_lead and (self.in_catch(xh - self.offset) or tau >= ts_ - 1e-9):
                self.to_balance()
            elif self.catch == "region" and tau > ts_ + 0.5:
                self.mode, self.t_mode = "settle", t             # missed the catch: settle and retry
                self.damping = True
        if self.mode == "pump" and self.in_catch(xh):
            self.to_balance()
        if self.mode == "balance" and self.mode_kind == "rearm":
            if np.any(np.abs(wrap(xh[1:3])) > self.drop):
                self.mode, self.t_mode = "settle", t
                self.damping = True
                self.n_drops += 1
                self.rest_count = 0
        # the law of the mode
        if self.mode == "swing":
            xr, ur, k = self.table(t - self.t_arm)
            u = ur - float(k @ (xh - (xr + self.offset)))
            self.phase = 1
        elif self.mode == "balance":
            u = self.balance_u(xh, y)
            self.phase = 2
        elif self.mode == "settle":
            u = self.damp_u(xh)
            self.phase = 3
        elif self.mode == "pump":
            u = self.pump_u(xh)
            self.phase = 4
        else:
            self.phase = 0
        if self.fc and self.mode in ("swing", "balance"):
            u += self.fc * math.tanh(xh[3] / self.fc_eps)
        u = min(max(u, -self.u_max), self.u_max)
        self.line.insert(0, u)
        self.line.pop()
        return u

    def arm(self, t, xh):
        self.mode, self.t_arm = "swing", t
        self.offset = np.zeros(6)
        self.offset[0] = xh[0]
        # the turn count of each link (the plan starts at -pi)
        for i in (1, 2):
            self.offset[i] = TWO_PI * round((xh[i] + math.pi) / TWO_PI)

    def to_balance(self):
        self.mode = "balance"
        self.balance_init = True


_P_CACHE: dict = {}


def _lqr_P():
    """Cost-to-go of the nominal discrete LQR (design weights) as the default catch metric."""
    if "P" not in _P_CACHE:
        import scipy.linalg as sla
        import robust_lin as rl
        A, B, _ = rl.lin_cont(lb.nominal())
        Ad, Bd = rl.zoh(A, B)
        Q = np.diag([300.0, 400.0, 400.0, 10.0, 8.0, 8.0])
        _P_CACHE["P"] = sla.solve_discrete_are(Ad, Bd, Q, np.array([[0.3]]))
    return _P_CACHE["P"]


def _hang_lqr(p):
    """Discrete LQR at the hanging equilibrium (cart to the centre, the link swings damped)."""
    import scipy.linalg as sla
    import robust_lin as rl
    rig, alpha = lb.twin_rig(p | rl.NO_COULOMB)
    plant = lb.LabPlant(rig, alpha)
    z0 = np.array([0.0, -math.pi, -math.pi, 0, 0, 0])
    A, B = (np.array(m, float) for m in plant.lin_fn(z0, 0.0))
    Ad, Bd = rl.zoh(A, B)
    Q = np.diag([50.0, 100.0, 100.0, 5.0, 5.0, 5.0])
    P = sla.solve_discrete_are(Ad, Bd, Q, np.array([[0.3]]))
    return np.linalg.solve(np.array([[0.3]]) + Bd.T @ P @ Bd, Bd.T @ P @ Ad).ravel()


def make(p_nominal: dict, **opts):
    """Factory for the harness: options balance, swing, mode, catch, catch_tol, catch_lead, drop_deg, pump, k_e, a_max."""
    kw = {}
    for k, v in opts.items():
        if k in ("catch_tol", "catch_lead", "drop_deg", "t_on", "k_e", "a_max", "comp", "e_lqr", "kc_x", "kc_v", "k_p"):
            kw[k] = float(v)
        else:
            kw[k] = v
    return LabController(p_nominal, **kw)
