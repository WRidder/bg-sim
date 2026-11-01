"""Design library of the `quad-pendulum` example: a chain of four pendulum links on a cart (planar)
or on a rotary arm (Furuta, spatial).

Everything here is *design*, not model: the Lagrangian twin of the bond graph (CasADi), the discrete
LQR, the implicit Hermite-Simpson swing-up optimisation (IPOPT), the discrete time-varying LQR along
it, a line-by-line replica of the 1 kHz firmware (`library/Quad*Ctrl.jl`) and the sampled closed
loop. `design.py` sets the parameters and runs it; `build_models.py` writes the bond graphs.

State. Both rigs use the same design state

    z = [s, phi_1 .. phi_4, sd, phid_1 .. phid_4]

with ``s`` the base coordinate (cart position x in m, or arm angle in rad) and ``phi_i`` the
*absolute* angle of link i from the upward vertical (rad, upright = 0, hanging = -pi for the cart
and +pi for the rotary arm, the sign conventions of the bond-graph joints). The firmware converts the
bond-graph joint readings (relative angles) to this state.

Cart: link direction u_i = (-sin phi_i, cos phi_i) in the world x-y plane (y up), counter-clockwise
angles; the bond-graph joint angles are Q_1 = phi_1 + pi/2 and Q_k = phi_k - phi_{k-1}.

Rotary: the arm turns about the world z axis by s; the chain swings in the plane perpendicular to the
arm, joint 1 at the arm tip; Revolute3D coordinates q_1 = s, q_2 = phi_1, q_{k+1} = phi_k - phi_{k-1}
(the frames of `examples/pendulum-triple-rotary`).

Input. The actuator is ideal: a force F on the cart (N) or a torque on the arm (N m). The firmware
saturates it, limits its slew rate and can delay it by whole samples (dashboard options).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import casadi as ca
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.linalg import expm, solve_discrete_are

G = 9.81
TS = 1e-3  # firmware sampling time (s)

# frame of the first pendulum joint in the arm frame (rotary): local z = the arm direction,
# local x = world z (upright). Same as pendulum-triple-rotary.
RJF = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])


def rotz(a):
    c, s = ca.cos(a), ca.sin(a)
    return ca.vertcat(ca.horzcat(c, -s, 0), ca.horzcat(s, c, 0), ca.horzcat(0, 0, 1))


@dataclass
class Rig:
    """Parameters of one rig. `kind` is "cart" or "rotary"."""

    kind: str
    L: list            # link lengths (m)
    m: list            # link masses (kg), uniform rods: COM at the middle
    b_joint: float     # viscous friction of every pendulum joint (N m s/rad)
    m_base: float      # cart mass (kg) / arm mass (kg)
    b_base: float      # rail friction (N s/m) / arm bearing friction (N m s/rad)
    u_max: float       # actuator limit (N or N m)
    slew: float        # actuator slew-rate limit (N/s or N m/s)
    s_max: float       # rail half travel (m) / arm cable limit (rad)
    arm_l: float = 0.0     # rotary: arm length (m)
    J_hub: float = 0.0     # rotary: hub + rotor inertia about the vertical axis (kg m^2)
    J_cart: float = 2.0e-3  # cart yaw inertia (bond graph only, never moves)
    r_link: float = 0.006  # rod radius for the axial inertia (rotary) (m)
    r_arm: float = 0.008

    @property
    def n(self) -> int:
        return len(self.L)

    @property
    def nq(self) -> int:
        return self.n + 1

    @property
    def nx(self) -> int:
        return 2 * self.nq

    @property
    def c(self) -> list:
        return [l / 2 for l in self.L]

    @property
    def J(self) -> list:
        """Rod inertia about the COM, perpendicular to the rod (kg m^2)."""
        return [mi * li * li / 12.0 for mi, li in zip(self.m, self.L)]

    @property
    def hang_sign(self) -> float:
        return -1.0 if self.kind == "cart" else 1.0

    def hanging(self) -> np.ndarray:
        z = np.zeros(self.nx)
        z[1 : 1 + self.n] = self.hang_sign * math.pi
        return z

    def upright_pe(self) -> list:
        """Potential energy of each link at the upright, measured from its hanging rest (J)."""
        out = []
        for i in range(self.n):
            h = 2.0 * (sum(self.L[:i]) + self.c[i])
            out.append(self.m[i] * G * h)
        return out


class Plant:
    """Lagrangian twin of the bond graph: f(z, u, fd) with fd a tip force perpendicular to the top link."""

    def __init__(self, rig: Rig):
        self.rig = rig
        self.n, self.nq, self.nx = rig.n, rig.nq, rig.nx
        if rig.kind == "cart":
            self._build_cart()
        else:
            self._build_rotary()
        self._finish()

    # ---------------------------------------------------------------- kinematics
    def _build_cart(self):
        R = self.rig
        q = ca.SX.sym("q", self.nq)
        qd = ca.SX.sym("qd", self.nq)
        phi = q[1:]
        px, py = q[0], ca.SX(0)
        T = 0.5 * R.m_base * qd[0] ** 2
        V = ca.SX(0)
        ke, pe = [], []
        for i in range(self.n):
            ux, uy = -ca.sin(phi[i]), ca.cos(phi[i])
            cx, cy = px + R.c[i] * ux, py + R.c[i] * uy
            vc = ca.jtimes(ca.vertcat(cx, cy), q, qd)
            ki = 0.5 * R.m[i] * ca.dot(vc, vc) + 0.5 * R.J[i] * qd[1 + i] ** 2
            # potential from the hanging rest of this link (cy = -(sum L_j + c_i) there)
            pi_ = R.m[i] * G * (cy + sum(R.L[:i]) + R.c[i])
            ke.append(ki)
            pe.append(pi_)
            T += ki
            V += pi_
            px, py = px + R.L[i] * ux, py + R.L[i] * uy
        tip = ca.vertcat(px, py)
        nperp = ca.vertcat(-ca.cos(phi[-1]), -ca.sin(phi[-1]))
        self.q, self.qd, self.T, self.V = q, qd, T, V
        self.ke, self.pe, self.ke_base = ke, pe, 0.5 * R.m_base * qd[0] ** 2
        self.qforce_expr = ca.jacobian(tip, q).T @ nperp
        # generalised forces: input on the base, viscous friction (rail on x, joints on relative rates)
        rel = [qd[1]] + [qd[1 + i] - qd[i] for i in range(1, self.n)]
        D = 0.5 * R.b_base * qd[0] ** 2 + sum(0.5 * R.b_joint * r**2 for r in rel)
        self.D = D
        self.tip = tip

    def _build_rotary(self):
        R = self.rig
        q = ca.SX.sym("q", self.nq)      # [arm, phi_1 .. phi_n]
        qd = ca.SX.sym("qd", self.nq)
        # joint coordinates of the bond graph
        jq = [q[0], q[1]] + [q[1 + k] - q[k] for k in range(1, self.n)]
        rot0 = rotz(jq[0])
        T = 0.5 * R.J_hub * qd[0] ** 2
        V = ca.SX(0)
        # arm: a rod along its local x
        pa = rot0 @ ca.vertcat(R.arm_l / 2, 0, 0)
        ja = (0.5 * R.m_base * R.r_arm**2, R.m_base * (R.arm_l**2 / 12 + R.r_arm**2 / 4),
              R.m_base * (R.arm_l**2 / 12 + R.r_arm**2 / 4))
        bodies = [(R.m_base, pa, rot0, ja)]
        origin = rot0 @ ca.vertcat(R.arm_l, 0, 0)
        r = rot0 @ ca.DM(RJF) @ rotz(jq[1])
        rots = [r]
        pos = []
        for k in range(self.n):
            l = R.L[k]
            pos.append(origin + r @ ca.vertcat(l / 2, 0, 0))
            origin = origin + r @ ca.vertcat(l, 0, 0)
            if k + 1 < self.n:
                r = r @ rotz(jq[k + 2])
                rots.append(r)
        for k in range(self.n):
            jt = R.m[k] * (R.L[k] ** 2 / 12 + R.r_link**2 / 4)
            bodies.append((R.m[k], pos[k], rots[k], (0.5 * R.m[k] * R.r_link**2, jt, jt)))
        ke, pe = [], []
        for idx, (mm, p, rot, j) in enumerate(bodies):
            vel = ca.jtimes(p, q, qd)
            rd = ca.reshape(ca.jtimes(ca.vec(rot), q, qd), 3, 3)
            om = rot.T @ rd
            w = ca.vertcat(om[2, 1], om[0, 2], om[1, 0])
            ki = 0.5 * mm * ca.dot(vel, vel) + 0.5 * (j[0] * w[0] ** 2 + j[1] * w[1] ** 2 + j[2] * w[2] ** 2)
            T += ki
            if idx == 0:
                self.ke_base = ki + 0.5 * R.J_hub * qd[0] ** 2
                continue
            i = idx - 1
            # world z of the COM is +h at the upright; hanging rest at -(sum L_j + c_i)
            pi_ = mm * G * (p[2] + sum(R.L[:i]) + R.c[i])
            V += pi_
            ke.append(ki)
            pe.append(pi_)
        ydir = r @ ca.vertcat(0, 1, 0)
        self.q, self.qd, self.T, self.V = q, qd, T, V
        self.ke, self.pe = ke, pe
        self.qforce_expr = ca.jacobian(origin, q).T @ ydir
        rel = [qd[1]] + [qd[1 + i] - qd[i] for i in range(1, self.n)]
        self.D = 0.5 * R.b_base * qd[0] ** 2 + sum(0.5 * R.b_joint * rr**2 for rr in rel)
        self.tip = origin

    def _finish(self):
        q, qd, T, V = self.q, self.qd, self.T, self.V
        u = ca.SX.sym("u")
        fd = ca.SX.sym("fd")
        M = ca.hessian(T, qd)[0]
        cor = ca.jacobian(ca.gradient(T, qd), q) @ qd
        gen = ca.vertcat(u, ca.SX.zeros(self.n)) - ca.gradient(self.D, qd)
        rhs = ca.gradient(T, q) - cor - ca.gradient(V, q) + gen
        self.mass_fn = ca.Function("M", [q], [M])
        self.rhs_fn = ca.Function("rhs", [q, qd, u], [rhs])
        z = ca.vertcat(q, qd)
        zdot = ca.vertcat(qd, ca.solve(M, rhs + self.qforce_expr * fd))
        self.f = ca.Function("f", [z, u, fd], [zdot])
        zdot0 = ca.substitute(zdot, fd, 0)
        self.lin_fn = ca.Function("lin", [z, u], [ca.jacobian(zdot0, z), ca.jacobian(zdot0, u)])
        self.energy = ca.Function("E", [z], [T + V])
        self.link_energy = ca.Function("El", [z], [ca.vertcat(*[k + p for k, p in zip(self.ke, self.pe)])])
        self.power_loss = ca.Function("Pl", [z], [2 * self.D])   # Rayleigh: dissipated power = 2 D
        self.tip_fn = ca.Function("tip", [z], [self.tip])

    def rhs(self, z, u=0.0, fd=0.0) -> np.ndarray:
        return np.array(self.f(z, u, fd)).ravel()

    def steps(self, ts: float = TS, sub: int = 2):
        """Sampled model: RK4 with `sub` steps over one sample, zero-order-hold input and tip force."""
        x = ca.SX.sym("x", self.nx)
        u = ca.SX.sym("u")
        fd = ca.SX.sym("fd")
        h = ts / sub
        xx = x
        for _ in range(sub):
            k1 = self.f(xx, u, fd)
            k2 = self.f(xx + 0.5 * h * k1, u, fd)
            k3 = self.f(xx + 0.5 * h * k2, u, fd)
            k4 = self.f(xx + h * k3, u, fd)
            xx = xx + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        step = ca.Function("step", [x, u, fd], [xx]).expand()
        jac = ca.Function("jstep", [x, u, fd], [ca.jacobian(xx, x), ca.jacobian(xx, u)]).expand()
        return step, jac


# ---------------------------------------------------------------- LQR at the upright
def dlqr(plant: Plant, qdiag, r: float, ts: float = TS):
    a, b = (np.array(mm) for mm in plant.lin_fn(np.zeros(plant.nx), 0.0))
    n = plant.nx
    mm = expm(np.block([[a, b], [np.zeros((1, n + 1))]]) * ts)
    ad, bd = mm[:n, :n], mm[:n, n:]
    q = np.diag(qdiag)
    p = solve_discrete_are(ad, bd, q, np.array([[r]]))
    k = np.linalg.solve(r + bd.T @ p @ bd, bd.T @ p @ ad)
    poles = np.log(np.linalg.eigvals(ad - bd @ k).astype(complex)) / ts
    open_poles = np.linalg.eigvals(a)
    return k.ravel(), p, poles, open_poles


# ---------------------------------------------------------------- trajectory optimisation
def collocate(plant: Plant, t_s: float, nk: int, guess, u_lim: float, s_lim: float, slew: float,
              w_du: float, w_rate: float, w_s: float = 0.0, max_iter: int = 3000, verbose: bool = False) -> dict:
    """Implicit (separated) Hermite-Simpson collocation from hanging rest to upright rest in `t_s`.

    Decision variables: knot states X, knot and midpoint accelerations A, AC, midpoint states XC, knot
    inputs U (piecewise linear). Constraints: the dynamics M(q) a = rhs(q, qd, u) at knots and
    midpoints, |u| <= u_lim, |s| <= s_lim, |du/dt| <= slew. Cost: the integral of
    u^2 + w_du du/dt^2 + w_rate |link rates|^2 + w_s s^2.
    """
    nq, nx = plant.nq, plant.nx
    h = t_s / nk
    q = ca.SX.sym("q", nq)
    qd = ca.SX.sym("qd", nq)
    acc = ca.SX.sym("a", nq)
    u = ca.SX.sym("u")
    dyn = ca.Function("dyn", [q, qd, acc, u], [plant.mass_fn(q) @ acc - plant.rhs_fn(q, qd, u)]).expand()
    x0, x1, xc = ca.SX.sym("x0", nx), ca.SX.sym("x1", nx), ca.SX.sym("xc", nx)
    a0, a1, ac = ca.SX.sym("a0", nq), ca.SX.sym("a1", nq), ca.SX.sym("ac", nq)
    f0, f1, fc = ca.vertcat(x0[nq:], a0), ca.vertcat(x1[nq:], a1), ca.vertcat(xc[nq:], ac)
    defect = ca.Function("defect", [x0, x1, xc, a0, a1, ac], [ca.vertcat(
        xc - (0.5 * (x0 + x1) + h / 8 * (f0 - f1)), x1 - x0 - h / 6 * (f0 + 4 * fc + f1))]).expand()
    opti = ca.Opti()
    X = opti.variable(nx, nk + 1)
    A = opti.variable(nq, nk + 1)
    XC = opti.variable(nx, nk)
    AC = opti.variable(nq, nk)
    U = opti.variable(1, nk + 1)
    UC = 0.5 * (U[:, :-1] + U[:, 1:])
    opti.subject_to(ca.vec(dyn.map(nk + 1)(X[:nq, :], X[nq:, :], A, U)) == 0)
    opti.subject_to(ca.vec(dyn.map(nk)(XC[:nq, :], XC[nq:, :], AC, UC)) == 0)
    opti.subject_to(ca.vec(defect.map(nk)(X[:, :-1], X[:, 1:], XC, A[:, :-1], A[:, 1:], AC)) == 0)
    opti.subject_to(X[:, 0] == plant.rig.hanging())
    opti.subject_to(X[:, nk] == 0)
    opti.subject_to(U[0, 0] == 0)
    opti.subject_to(U[0, nk] == 0)
    opti.subject_to(opti.bounded(-u_lim, U, u_lim))
    opti.subject_to(opti.bounded(-s_lim, X[0, :], s_lim))
    opti.subject_to(opti.bounded(-s_lim, XC[0, :], s_lim))
    du = (U[:, 1:] - U[:, :-1]) / h
    opti.subject_to(opti.bounded(-slew, du, slew))
    rates, rates_c = X[nq + 1:, :], XC[nq + 1:, :]
    cost = h / 6 * ca.sum2(U[:, :-1] ** 2 + 4 * UC**2 + U[:, 1:] ** 2)
    cost += w_du * h * ca.sumsqr(du)
    cost += w_rate * h / 6 * (ca.sumsqr(rates[:, :-1]) + 4 * ca.sumsqr(rates_c) + ca.sumsqr(rates[:, 1:]))
    cost += w_s * h / 6 * (ca.sumsqr(X[0, :-1]) + 4 * ca.sumsqr(XC[0, :]) + ca.sumsqr(X[0, 1:]))
    opti.minimize(cost)
    xg, ug = guess
    ag = np.zeros((nq, nk + 1))
    for k in range(nk + 1):
        mm = np.array(plant.mass_fn(xg[:nq, k]))
        ag[:, k] = np.linalg.solve(mm, np.array(plant.rhs_fn(xg[:nq, k], xg[nq:, k], ug[k])).ravel())
    opti.set_initial(X, xg)
    opti.set_initial(U, ug.reshape(1, -1))
    opti.set_initial(A, ag)
    opti.set_initial(XC, 0.5 * (xg[:, :-1] + xg[:, 1:]))
    opti.set_initial(AC, 0.5 * (ag[:, :-1] + ag[:, 1:]))
    opti.solver("ipopt", {"ipopt.max_iter": max_iter, "ipopt.tol": 1e-7, "ipopt.print_level": 5 if verbose else 0,
                          "print_time": False, "ipopt.mu_strategy": "adaptive", "ipopt.linear_solver": "mumps"})
    started = time.time()
    sol = opti.solve()
    return {"x": np.array(sol.value(X)), "u": np.atleast_1d(sol.value(U)).ravel(), "cost": float(sol.value(cost)),
            "iters": int(opti.stats()["iter_count"]), "seconds": time.time() - started, "t_s": t_s, "nk": nk}


def guess_linear(plant: Plant, nk: int, swings: float = 0.0, s_amp: float = 0.0):
    """First guess: every link turned smoothly from hanging to upright, the base oscillating `swings` times."""
    R = plant.rig
    x = np.zeros((plant.nx, nk + 1))
    tt = np.linspace(0, 1, nk + 1)
    s = 0.5 - 0.5 * np.cos(np.pi * tt)
    for i in range(R.n):
        x[1 + i] = R.hang_sign * math.pi * (1 - s)
    if swings:
        x[0] = s_amp * np.sin(2 * np.pi * swings * tt) * np.sin(np.pi * tt)
    T = 1.0
    x[plant.nq:] = np.gradient(x[: plant.nq], tt * T, axis=1)
    return x, np.zeros(nk + 1)


def spline(plant: Plant, traj: dict) -> CubicHermiteSpline:
    x, u, t_s = traj["x"], traj["u"], traj["t_s"]
    nk = x.shape[1] - 1
    tn = np.linspace(0, t_s, nk + 1)
    xd = np.array([plant.rhs(x[:, k], u[k]) for k in range(nk + 1)])
    return CubicHermiteSpline(tn, x.T, xd)


def resample(plant: Plant, traj: dict, nk2: int, t_s2: float | None = None):
    """The solution on another grid (and optionally stretched to another duration)."""
    t_s = traj["t_s"]
    t_s2 = t_s if t_s2 is None else t_s2
    t2 = np.linspace(0, t_s, nk2 + 1)
    tn = np.linspace(0, t_s, traj["x"].shape[1])
    x2 = spline(plant, traj)(t2).T
    x2[plant.nq:] *= t_s / t_s2
    return x2, np.interp(t2, tn, traj["u"])


# ---------------------------------------------------------------- discrete TVLQR
def riccati(jac, xr, ur, q, r: float, p_end):
    n = len(ur) - 1
    ks = np.zeros((n + 1, xr.shape[1]))
    p = p_end.copy()
    for k in range(n - 1, -1, -1):
        a, b = (np.array(mm) for mm in jac(xr[k], ur[k], 0.0))
        bp = b.T @ p
        kk = np.linalg.solve(r + bp @ b, bp @ a)
        p = q + a.T @ p @ (a - b @ kk)
        p = 0.5 * (p + p.T)
        ks[k] = kk.ravel()
    return ks


def tvlqr(plant: Plant, traj: dict, qdiag, r: float, k_lqr, p_lqr, ts: float = TS):
    """Discrete TVLQR on the 1 kHz grid; the nominal is made consistent with the sampled model by one
    closed-loop roll-out (see pendulum-triple-rotary). Returns the 1 kHz nominal, input and gains."""
    step, jac = plant.steps(ts)
    t_s = traj["t_s"]
    n = int(round(t_s / ts))
    tk = np.arange(n + 1) * ts
    xr = spline(plant, traj)(tk)
    tn = np.linspace(0, t_s, traj["x"].shape[1])
    ur = np.interp(np.minimum(tk + 0.5 * ts, t_s), tn, traj["u"])
    ur[-1] = 0.0
    q = np.diag(qdiag)
    ks = riccati(jac, xr, ur, q, r, p_lqr)
    x = plant.rig.hanging()
    xs = np.zeros_like(xr)
    us = np.zeros(n + 1)
    xs[0] = x
    for k in range(n):
        us[k] = ur[k] - ks[k] @ (x - xr[k])
        x = np.array(step(x, us[k], 0.0)).ravel()
        xs[k + 1] = x
    end_err = float(np.max(np.abs(xs[-1])))
    ks = riccati(jac, xs, us, q, r, p_lqr)
    ks[-1] = k_lqr
    return xs, us, ks, end_err


# ---------------------------------------------------------------- firmware and closed loop
@dataclass
class Firmware:
    """The 1 kHz firmware of `library/Quad*Ctrl.jl`, line by line."""

    t_on: float
    t_s: float
    dt_tab: float
    tab_x: np.ndarray
    tab_u: np.ndarray
    tab_k: np.ndarray
    k_lqr: np.ndarray
    p_catch: np.ndarray
    catch_tol: float
    u_max: float
    slew: float
    balance_only: bool = False
    delay: int = 0             # actuator delay in whole samples
    quant: bool = False        # encoder quantisation + difference rates
    res_s: float = 1e-5        # base encoder resolution (m or rad)
    res_q: float = 2 * math.pi / 4096 / 4   # joint encoder resolution (rad): 4096 lines, x4
    tau_f: float = 0.002       # rate filter time constant (s) when quantised
    ts: float = TS


def table_row(fw: Firmware, t: float):
    nt = fw.tab_x.shape[0]
    s = min(max((t - fw.t_on) / fw.dt_tab, 0.0), nt - 1)
    i = min(int(math.floor(s)), nt - 2)
    w = s - i
    return ((1 - w) * fw.tab_x[i] + w * fw.tab_x[i + 1], (1 - w) * fw.tab_u[i] + w * fw.tab_u[i + 1],
            (1 - w) * fw.tab_k[i] + w * fw.tab_k[i + 1])


def measure(fw: Firmware, z: np.ndarray, st: dict, nq: int) -> np.ndarray:
    """What the firmware sees: the exact state, or quantised positions with filtered difference rates."""
    if not fw.quant:
        return z
    pos = z[:nq].copy()
    pos[0] = fw.res_s * np.round(pos[0] / fw.res_s)
    # the encoders measure the relative joint angles
    rel = np.concatenate([[pos[1]], np.diff(z[1:nq])])
    rel = fw.res_q * np.round(rel / fw.res_q)
    pos[1:] = np.cumsum(rel)
    prev = st.get("prev")
    wf = st.get("wf")
    if prev is None:
        prev, wf = pos.copy(), np.zeros(nq)
    a = fw.ts / (fw.ts + fw.tau_f)
    wf = wf + a * ((pos - prev) / fw.ts - wf)
    st["prev"], st["wf"] = pos, wf
    return np.concatenate([pos, wf])


def tick(fw: Firmware, t: float, z: np.ndarray, st: dict) -> float:
    """One firmware tick: returns the applied actuator value; st holds mode, slew and delay state."""
    nq = len(z) // 2
    x = measure(fw, z, st, nq)
    if fw.balance_only:
        st["latched"] = 1
    tau = t - fw.t_on
    v = float(x @ fw.p_catch @ x)
    if st.get("latched", 0) < 0.5 and t >= fw.t_on and tau >= fw.t_s - 0.5 and v < fw.catch_tol:
        st["latched"] = 1
        st["t_catch"] = t
    if st.get("latched", 0) > 0.5:
        st["phase"] = 2
        cmd = -float(fw.k_lqr @ x)
    elif t >= fw.t_on:
        st["phase"] = 1
        xr, ur, k = table_row(fw, t)
        cmd = ur - float(k @ (x - xr))
    else:
        st["phase"] = 0
        cmd = 0.0
    cmd = min(max(cmd, -fw.u_max), fw.u_max)
    last = st.get("last", 0.0)
    du = fw.slew * fw.ts
    out = min(max(cmd, last - du), last + du)
    st["last"] = out
    line = st.setdefault("line", [0.0] * 16)
    line.insert(0, out)
    line.pop()
    st["v"] = v
    return line[fw.delay]


def closed_loop(step, fw: Firmware, x0, t_end: float, force=None):
    """Sampled closed loop: firmware tick, zero-order hold, `step` (RK4) over each sample."""
    n = int(round(t_end / fw.ts))
    x = np.array(x0, float)
    st = {"phase": 0}
    ts = np.arange(n + 1) * fw.ts
    xs = np.full((n + 1, len(x)), np.nan)
    us = np.zeros(n + 1)
    ph = np.zeros(n + 1)
    xs[0] = x
    for i in range(n):
        u = tick(fw, ts[i], x, st)
        us[i] = u
        ph[i] = st["phase"]
        x = np.array(step(x, u, force(ts[i] + 0.5 * fw.ts) if force else 0.0)).ravel()
        if not np.all(np.isfinite(x)) or np.max(np.abs(x[len(x) // 2:])) > 1e3:
            break
        xs[i + 1] = x
    us[n] = us[n - 1]
    ph[n] = ph[n - 1]
    return ts, xs, us, ph, st


def free_swing(plant: Plant, z0, t_grid, h: float = 2e-4):
    """Open-loop free swing (u = 0) of the design model, RK4 with step h, sampled at t_grid."""
    from scipy.integrate import solve_ivp
    sol = solve_ivp(lambda t, z: plant.rhs(z, 0.0), (0, float(t_grid[-1])), np.array(z0, float), t_eval=t_grid,
                    rtol=1e-11, atol=1e-12, method="DOP853")
    return sol.y.T


def read_run(run_dir):
    """Time and signal dict of a run folder (manifest.json + columns.f64)."""
    import json
    from pathlib import Path
    man = json.load(open(Path(run_dir) / "manifest.json"))
    ids = [s["id"] for s in man["signals"]]
    n = man["time"]["n"]
    raw = np.fromfile(Path(run_dir) / "columns.f64", dtype="<f8").reshape(len(ids) + 1, n)
    return raw[0], {k: raw[i + 1] for i, k in enumerate(ids)}


@dataclass
class Design:
    rig: Rig
    plant: Plant
    traj: dict | None
    fw: Firmware
    info: dict = field(default_factory=dict)
