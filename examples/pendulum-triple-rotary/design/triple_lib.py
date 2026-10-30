"""Design code of `pendulum-triple-rotary` (X5.13b): the model, the trajectory optimisation, the
discrete time-varying LQR, the firmware and the closed loop.

Adapted from `examples/pendulum-double-rotary/design/rotary_lib.py` (same kinematics and the same
generalised coordinates), with the changes the triple needs:

- the drive is a parameter set (`Drive`), the triple's amplifier limit is 15 V;
- the collocation is **implicit** (accelerations are decision variables, `M(q) a = rhs(q, qd, u)`
  at every knot and midpoint): no symbolic inverse of the mass matrix, so a 250-interval solve
  takes about two minutes instead of tens of minutes;
- the voltage is piecewise linear and its rate is penalised, link rates are penalised: smooth,
  trackable trajectories;
- the time-varying LQR is the **discrete** Riccati recursion of the 1 kHz zero-order-hold model
  (the exact Jacobians of the RK4 step), with the infinite-horizon discrete LQR as the terminal
  cost; the nominal is re-made consistent with the sampled model by one closed-loop roll-out.

The generalised coordinates are exactly the joint coordinates of the bond graph
(`Revolute3D.qout`):

    q[0]  arm angle about the world z axis (rad)
    q[1]  first link, from upright (rad, upright = 0, hanging = pi)
    q[k]  link k relative to link k-1 (rad)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import casadi as ca
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import CubicHermiteSpline
from scipy.linalg import expm, solve_discrete_are

G = 9.81
TS = 1e-3  # firmware sampling time [s]

# ---------------------------------------------------------------- parameters
# Arm and links: the Quanser rotary double inverted pendulum, product page
# https://www.quanser.com/products/rotary-double-inverted-pendulum/ : rotary arm 21.59 cm,
# 0.2570 kg; short pendulum 20.0 cm, 0.097 kg; medium pendulum 33.65 cm, 0.127 kg.
# The triple (NOT a Quanser product) stacks short + short + medium: a second short pendulum is
# inserted between the two links of the double.
ARM_L = 0.2159
ARM_M = 0.2570
ARM_R = 0.006  # bar radius for the axial inertia [m] (assumed)
LINK_R = 0.008
LINKS = ([0.200, 0.200, 0.3365], [0.097, 0.097, 0.127])
JFRIC = 3.0e-5  # viscous friction of the pendulum bearings [N m s/rad] (assumed)

# frame of joint 2 in the arm frame: local z = arm direction, local x = world z (upright)
RJF = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])


@dataclass
class Drive:
    """SRV02-like servo: Quanser SRV02 manual values (Rm, Lm, kt, Jm, Kg = 70, Beq), as in the
    double. `vmax` is the amplifier limit: 15 V for the triple (the double: 10 V)."""

    rm: float = 8.4
    lm: float = 1.16e-3
    kt: float = 0.0333
    jm: float = 3.87e-7
    ng: float = 70.0
    beq: float = 0.015  # viscous friction at the load [N m s/rad]
    vmax: float = 15.0

    @property
    def a(self) -> float:
        """Arm torque per volt at standstill [N m/V]."""
        return self.ng * self.kt / self.rm

    @property
    def c(self) -> float:
        """Back-EMF plus load friction at the arm [N m s/rad]."""
        return self.ng**2 * self.kt**2 / self.rm + self.beq

    @property
    def bm(self) -> float:
        """Load friction referred to the motor shaft."""
        return self.beq / self.ng**2

    @property
    def jrot(self) -> float:
        """Rotor inertia reflected to the arm axis, with the winding inductance to first order.

        The design model has no current state: the winding lag tau_e = lm/rm (0.14 ms) delays the
        back-EMF torque -n^2 kt^2/rm qd0 by tau_e, i.e. adds c_emf tau_e qdd0 to it, which acts as
        an inertia of -lm n^2 kt^2 / rm^2 (-8.9e-5 kg m^2, 1.5 % of the arm) at the arm axis. With it
        the free swing of the design model matches the bond graph (ElectricDrive with L) about 25
        times better."""
        return self.ng**2 * self.jm - self.lm * self.ng**2 * self.kt**2 / self.rm**2


def rotz(a):
    c, s = ca.cos(a), ca.sin(a)
    return ca.vertcat(ca.horzcat(c, -s, 0), ca.horzcat(s, c, 0), ca.horzcat(0, 0, 1))


class Plant:
    """Lagrangian model of the rotary arm with an N-link chain (the bond graph's mechanism)."""

    def __init__(self, lengths, masses, drive: Drive, jfric: float = JFRIC, arm_l: float = ARM_L, arm_m: float = ARM_M):
        self.lengths = list(lengths)
        self.masses = list(masses)
        self.drive = drive
        self.jfric = jfric
        self.arm_l = arm_l
        self.arm_m = arm_m
        self.n_links = len(self.lengths)
        self.nq = self.n_links + 1
        self.nx = 2 * self.nq
        self.body_j = [self.rod_inertia(arm_m, arm_l, ARM_R)]
        for m, l in zip(self.masses, self.lengths, strict=True):
            self.body_j.append(self.rod_inertia(m, l, LINK_R))
        self._build()

    @staticmethod
    def rod_inertia(m: float, l: float, r: float) -> tuple[float, float, float]:
        jt = m * (l * l / 12.0 + r * r / 4.0)
        return (0.5 * m * r * r, jt, jt)

    def _build(self) -> None:
        n = self.nq
        q = ca.SX.sym("q", n)
        qd = ca.SX.sym("qd", n)
        v = ca.SX.sym("v")
        rots = [rotz(q[0])]
        pos = [rotz(q[0]) @ ca.vertcat(self.arm_l / 2, 0, 0)]
        origin = rotz(q[0]) @ ca.vertcat(self.arm_l, 0, 0)  # joint 2 origin
        r = rotz(q[0]) @ ca.DM(RJF) @ rotz(q[1])
        rots.append(r)
        for k in range(self.n_links):
            l = self.lengths[k]
            pos.append(origin + r @ ca.vertcat(l / 2, 0, 0))
            origin = origin + r @ ca.vertcat(l, 0, 0)
            if k + 1 < self.n_links:
                r = r @ rotz(q[k + 2])
                rots.append(r)
        kin = 0.5 * self.drive.jrot * qd[0] ** 2
        pot = 0
        for m, p, rot, j in zip([self.arm_m, *self.masses], pos, rots, self.body_j, strict=True):
            vel = ca.jtimes(p, q, qd)
            rd = ca.reshape(ca.jtimes(ca.vec(rot), q, qd), 3, 3)
            om = rot.T @ rd
            w = ca.vertcat(om[2, 1], om[0, 2], om[1, 0])
            kin += 0.5 * m * ca.dot(vel, vel) + 0.5 * (j[0] * w[0] ** 2 + j[1] * w[1] ** 2 + j[2] * w[2] ** 2)
            pot += m * G * p[2]
        mass = ca.hessian(kin, qd)[0]
        coriolis = ca.jacobian(ca.gradient(kin, qd), q) @ qd
        gen = ca.vertcat(self.drive.a * v - self.drive.c * qd[0], -self.jfric * qd[1:])
        rhs = ca.gradient(kin, q) - coriolis - ca.gradient(pot, q) + gen
        self.mass_fn = ca.Function("M", [q], [mass])
        self.rhs_fn = ca.Function("rhs", [q, qd, v], [rhs])
        # a force on the tip of the last link along its body y axis (perpendicular to the rod, in
        # the pendulum plane): the generalised force J^T y
        ydir = r @ ca.vertcat(0, 1, 0)
        self.qforce = ca.Function("qforce", [q], [ca.jacobian(origin, q).T @ ydir])
        x = ca.vertcat(q, qd)
        fz = ca.SX.sym("fz")
        xdot = ca.vertcat(qd, ca.solve(mass, rhs + self.qforce(q) * fz))
        self.f = ca.Function("f", [x, v, fz], [xdot])
        xdot0 = ca.substitute(xdot, fz, 0)
        self.lin_fn = ca.Function("lin", [x, v], [ca.jacobian(xdot0, x), ca.jacobian(xdot0, v)])
        self.energy = ca.Function("E", [x], [kin + pot])

    def rhs(self, x, v, fz=0.0) -> np.ndarray:
        return np.array(self.f(x, v, fz)).ravel()

    def hanging(self) -> np.ndarray:
        x = np.zeros(self.nx)
        x[1] = math.pi
        return x

    def steps(self, ts: float = TS, sub: int = 2):
        """The sampled model: RK4 with `sub` steps over one sample, zero-order-hold voltage and tip
        force. Returns the step x+ = F(x, u, fz) and its Jacobians (A, B) as CasADi functions."""
        x = ca.SX.sym("x", self.nx)
        v = ca.SX.sym("v")
        fz = ca.SX.sym("fz")
        h = ts / sub
        xx = x
        for _ in range(sub):
            k1 = self.f(xx, v, fz)
            k2 = self.f(xx + 0.5 * h * k1, v, fz)
            k3 = self.f(xx + 0.5 * h * k2, v, fz)
            k4 = self.f(xx + h * k3, v, fz)
            xx = xx + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        step = ca.Function("step", [x, v, fz], [xx]).expand()
        jac = ca.Function("jstep", [x, v, fz], [ca.jacobian(xx, x), ca.jacobian(xx, v)]).expand()
        return step, jac


# ---------------------------------------------------------------- feasibility
def feasibility(plant: Plant, t_s: float) -> dict:
    """The cheap argument: energy to raise the chain against the servo's power and speed."""
    d = plant.drive
    de = float(plant.energy(np.zeros(plant.nx)) - plant.energy(plant.hanging()))
    return {
        "dE": de,
        "p_mean_needed": de / t_s,
        "p_max": d.vmax**2 / (4 * d.rm),  # matched-load power of the winding at vmax
        "stall_torque": d.a * d.vmax,
        "noload_rate": d.a * d.vmax / d.c,
        "noload_rate_10V": d.a * 10.0 / d.c,
    }


# ---------------------------------------------------------------- LQR at the upright
def dlqr(plant: Plant, qdiag, r: float, ts: float = TS):
    a, b = (np.array(m) for m in plant.lin_fn(np.zeros(plant.nx), 0.0))
    n = plant.nx
    mm = expm(np.block([[a, b], [np.zeros((1, n + 1))]]) * ts)
    ad, bd = mm[:n, :n], mm[:n, n:]
    q = np.diag(qdiag)
    p = solve_discrete_are(ad, bd, q, np.array([[r]]))
    k = np.linalg.solve(r + bd.T @ p @ bd, bd.T @ p @ ad)
    poles = np.log(np.linalg.eigvals(ad - bd @ k)) / ts  # equivalent continuous poles
    return k.ravel(), p, poles


# ---------------------------------------------------------------- trajectory optimisation
def collocate(plant: Plant, t_s: float, nk: int, guess, vmax: float, theta_max: float, w_du: float, w_rate: float,
              max_iter: int = 1500, verbose: bool = False) -> dict:
    """Separated Hermite-Simpson collocation from hanging to upright in the fixed time `t_s`.

    Decision variables: knot states X, knot and midpoint accelerations A, AC, midpoint states XC,
    knot voltages U (piecewise linear). Cost: the integral of u^2 + w_du du/dt^2 + w_rate |link rates|^2.
    """
    nq, nx = plant.nq, plant.nx
    h = t_s / nk
    q = ca.SX.sym("q", nq)
    qd = ca.SX.sym("qd", nq)
    acc = ca.SX.sym("a", nq)
    v = ca.SX.sym("v")
    dyn = ca.Function("dyn", [q, qd, acc, v], [plant.mass_fn(q) @ acc - plant.rhs_fn(q, qd, v)]).expand()
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
    opti.subject_to(X[:, 0] == plant.hanging())
    opti.subject_to(X[:, nk] == 0)
    opti.subject_to(U[0, 0] == 0)
    opti.subject_to(U[0, nk] == 0)
    opti.subject_to(opti.bounded(-vmax, U, vmax))
    opti.subject_to(opti.bounded(-theta_max, X[0, :], theta_max))
    du = (U[:, 1:] - U[:, :-1]) / h
    rates, rates_c = X[nq + 1:, :], XC[nq + 1:, :]
    cost = h / 6 * ca.sum2(U[:, :-1] ** 2 + 4 * UC**2 + U[:, 1:] ** 2)
    cost += w_du * h * ca.sumsqr(du)
    cost += w_rate * h / 6 * (ca.sumsqr(rates[:, :-1]) + 4 * ca.sumsqr(rates_c) + ca.sumsqr(rates[:, 1:]))
    opti.minimize(cost)
    xg, ug = guess
    ag = np.zeros((nq, nk + 1))
    for k in range(nk + 1):
        m = np.array(plant.mass_fn(xg[:nq, k]))
        ag[:, k] = np.linalg.solve(m, np.array(plant.rhs_fn(xg[:nq, k], xg[nq:, k], ug[k])).ravel())
    opti.set_initial(X, xg)
    opti.set_initial(U, ug.reshape(1, -1))
    opti.set_initial(A, ag)
    opti.set_initial(XC, 0.5 * (xg[:, :-1] + xg[:, 1:]))
    opti.set_initial(AC, 0.5 * (ag[:, :-1] + ag[:, 1:]))
    opti.solver("ipopt", {"ipopt.max_iter": max_iter, "ipopt.tol": 1e-7, "ipopt.print_level": 5 if verbose else 0,
                          "print_time": False, "ipopt.mu_strategy": "adaptive"})
    started = time.time()
    sol = opti.solve()  # raises when IPOPT does not converge
    return {"x": sol.value(X), "u": np.atleast_1d(sol.value(U)).ravel(), "cost": float(sol.value(cost)),
            "iters": int(opti.stats()["iter_count"]), "seconds": time.time() - started, "t_s": t_s, "nk": nk}


def linear_guess(plant: Plant, nk: int):
    """The first guess: link 1 turned linearly from hanging to upright, everything else at rest."""
    x = np.zeros((plant.nx, nk + 1))
    x[1] = math.pi * (1 - np.linspace(0, 1, nk + 1))
    return x, np.zeros(nk + 1)


def spline(plant: Plant, traj: dict) -> CubicHermiteSpline:
    x, u, t_s = traj["x"], traj["u"], traj["t_s"]
    nk = x.shape[1] - 1
    tn = np.linspace(0, t_s, nk + 1)
    xd = np.array([plant.rhs(x[:, k], u[k]) for k in range(nk + 1)])
    return CubicHermiteSpline(tn, x.T, xd)


def resample(plant: Plant, traj: dict, nk2: int):
    """The solution on a finer grid (the warm start of the next solve)."""
    t2 = np.linspace(0, traj["t_s"], nk2 + 1)
    tn = np.linspace(0, traj["t_s"], traj["x"].shape[1])
    return spline(plant, traj)(t2).T, np.interp(t2, tn, traj["u"])


# ---------------------------------------------------------------- discrete TVLQR
def riccati(jac, xr, ur, q, r: float, p_end):
    """Backward discrete Riccati recursion along (xr, ur), terminal cost p_end."""
    n = len(ur) - 1
    ks = np.zeros((n + 1, xr.shape[1]))
    p = p_end.copy()
    for k in range(n - 1, -1, -1):
        a, b = (np.array(m) for m in jac(xr[k], ur[k], 0.0))
        bp = b.T @ p
        kk = np.linalg.solve(r + bp @ b, bp @ a)
        p = q + a.T @ p @ (a - b @ kk)
        p = 0.5 * (p + p.T)
        ks[k] = kk.ravel()
    return ks


def tvlqr(plant: Plant, traj: dict, qdiag, r: float, k_lqr, p_lqr, ts: float = TS):
    """Discrete TVLQR on the 1 kHz grid. The collocation reference (Hermite spline, the voltage at
    the sample midpoints) is tracked once by the sampled model under its own TVLQR; that roll-out
    is consistent with the sampled model and becomes the nominal, and the gains are recomputed
    along it. Returns the 1 kHz nominal, the voltage and the gains (the last row: upright, 0 V,
    the LQR gain)."""
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
    x = plant.hanging()
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
    """The 1 kHz firmware of `library/RotaryCtrl.jl`, line by line."""

    t_on: float
    t_s: float
    dt_tab: float
    tab_x: np.ndarray
    tab_u: np.ndarray
    tab_k: np.ndarray
    k_lqr: np.ndarray
    p_catch: np.ndarray  # catch rule: V = x' P x < catch_tol (P: the LQR cost-to-go)
    catch_tol: float
    vmax: float
    ts: float = TS


def table_row(fw: Firmware, t: float):
    nt = fw.tab_x.shape[0]
    s = min(max((t - fw.t_on) / fw.dt_tab, 0.0), nt - 1)
    i = min(int(math.floor(s)), nt - 2)
    w = s - i
    return ((1 - w) * fw.tab_x[i] + w * fw.tab_x[i + 1], (1 - w) * fw.tab_u[i] + w * fw.tab_u[i + 1],
            (1 - w) * fw.tab_k[i] + w * fw.tab_k[i + 1])


def tick(fw: Firmware, t: float, x: np.ndarray, st: dict) -> float:
    if t < fw.t_on:
        st["phase"] = 0
        return 0.0
    tau = t - fw.t_on
    v = float(x @ fw.p_catch @ x)
    if st.get("latched", 0) < 0.5 and tau >= fw.t_s and v < fw.catch_tol:
        st["latched"] = 1
        st["t_catch"] = t
    if st.get("latched", 0) > 0.5:
        st["phase"] = 2
        u = -float(fw.k_lqr @ x)
    else:
        st["phase"] = 1
        xr, ur, k = table_row(fw, t)
        u = ur - float(k @ (x - xr))
    return float(np.clip(u, -fw.vmax, fw.vmax))


def closed_loop(step, fw: Firmware, x0, t_end: float, force=None):
    """The sampled closed loop: firmware tick, zero-order hold, `step` (RK4) over each sample.
    `force(t)` is the tip force [N], evaluated at the middle of the sample."""
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


def free_swing(plant: Plant, start, t_end: float, dt: float = 0.01):
    """Open-loop free swing of the design model (motor terminals at 0 V) from rest at `start`."""
    x0 = np.concatenate([start, np.zeros(plant.nq)])
    tn = np.arange(0.0, t_end + 1e-9, dt)
    sol = solve_ivp(lambda t, x: plant.rhs(x, 0.0), (0, t_end), x0, t_eval=tn, rtol=1e-11, atol=1e-12, method="DOP853")
    phi = np.cumsum(sol.y[1:plant.nq].T, axis=1)
    return tn, sol.y.T, phi
