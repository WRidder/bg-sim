"""Shared design code of the rotary pendulums (X5.13): `pendulum-double-rotary` and
`pendulum-triple-rotary`.

A Quanser-style rotary arm (SRV02-like DC servo with gearbox) turns a horizontal arm about the
vertical axis; a chain of N pendulum links hangs from the arm tip and swings in the plane
perpendicular to the arm. The generalised coordinates are exactly the joint coordinates of the
bond graph (`Revolute3D.qout`):

    q[0]  arm angle about the world z axis (rad)
    q[1]  first link, from upright (rad, upright = 0, hanging = pi)
    q[k]  link k relative to link k-1 (rad)

This module builds the Lagrangian equations of motion with CasADi, designs the swing-up
trajectory (Hermite-Simpson direct collocation, IPOPT), the time-varying LQR along it and the
infinite-horizon LQR at the upright, simulates the closed loop and compares the design model with
the bond graph.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import casadi as ca
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import CubicHermiteSpline
from scipy.linalg import solve_continuous_are

G = 9.81

# ---------------------------------------------------------------- parameters
# Quanser rotary double inverted pendulum, product page
# https://www.quanser.com/products/rotary-double-inverted-pendulum/ (read 2026-10-30):
#   rotary arm length (pivot to tip) 21.59 cm, mass 0.2570 kg; short pendulum 20.0 cm, 0.097 kg;
#   medium pendulum 33.65 cm, 0.127 kg (both with their T-fitting).
# SRV02 servo (Quanser SRV02 user manual, specifications; recalled from the manual, not re-read
# in this session): Rm 8.4 Ohm, Lm 1.16 mH, kt = km 0.0333 N m/A, Jm 3.87e-7 kg m^2, total gear
# ratio Kg = 70 (14 x 5), equivalent viscous friction at the load Beq about 0.015 N m s/rad.
# ASSUMED (not published on the product page): the COM of every bar at its middle, thin-bar
# inertias, the bar radii for the axial inertia, the gear torsional stiffness, the 10 V amplifier
# limit, the third link of the triple (not a Quanser product).
ARM_L = 0.2159
ARM_M = 0.2570
ARM_R = 0.006  # bar radius for the axial inertia [m] (assumed)
LINK_R = 0.008
RM = 8.4
LM = 1.16e-3
KT = 0.0333
JM = 3.87e-7
NG = 70.0
BEQ = 0.015  # viscous friction at the load [N m s/rad]
BM = BEQ / NG**2  # ... referred to the motor shaft
KSHAFT = 1000.0  # gear torsional stiffness at the load [N m/rad] (assumed)
DSHAFT = 0.5  # gear torsional damping at the load [N m s/rad] (assumed)
VMAX = 10.0
JFRIC = 3.0e-5  # viscous friction of the pendulum bearings [N m s/rad] (assumed)

LINKS = {
    2: ([0.200, 0.3365], [0.097, 0.127]),
    3: ([0.200, 0.200, 0.3365], [0.097, 0.097, 0.127]),
}

# frame of joint 2 in the arm frame: local z = arm direction, local x = world z (upright)
RJF = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])


def rotz(a):
    c, s = ca.cos(a), ca.sin(a)
    return ca.vertcat(ca.horzcat(c, -s, 0), ca.horzcat(s, c, 0), ca.horzcat(0, 0, 1))


@dataclass
class Plant:
    n_links: int
    lengths: list[float]
    masses: list[float]
    arm_l: float = ARM_L
    arm_m: float = ARM_M
    jrotor: float = NG**2 * JM  # rotor inertia reflected to the arm axis

    # the derived numbers
    nq: int = field(init=False)
    nx: int = field(init=False)
    body_j: list = field(init=False)  # principal inertias about the COM, (Jx, Jy, Jz)

    def __post_init__(self) -> None:
        self.nq = self.n_links + 1
        self.nx = 2 * self.nq
        self.body_j = [self.rod_inertia(self.arm_m, self.arm_l, ARM_R)]
        for m, l in zip(self.masses, self.lengths, strict=True):
            self.body_j.append(self.rod_inertia(m, l, LINK_R))
        self._build()

    @staticmethod
    def rod_inertia(m: float, l: float, r: float) -> tuple[float, float, float]:
        jt = m * (l * l / 12.0 + r * r / 4.0)
        return (0.5 * m * r * r, jt, jt)

    # motor: torque at the arm axis = a V - c qd0 (quasi-static winding, L neglected)
    @property
    def a_motor(self) -> float:
        return NG * KT / RM

    @property
    def c_motor(self) -> float:
        return NG**2 * KT**2 / RM + NG**2 * BM

    def _build(self) -> None:
        n = self.nq
        q = ca.SX.sym("q", n)
        qd = ca.SX.sym("qd", n)
        v = ca.SX.sym("v")
        rjf = ca.DM(RJF)
        rots = [rotz(q[0])]
        pos = [rotz(q[0]) @ ca.vertcat(self.arm_l / 2, 0, 0)]
        origin = rotz(q[0]) @ ca.vertcat(self.arm_l, 0, 0)  # joint 2 origin
        r = rotz(q[0]) @ rjf @ rotz(q[1])
        rots.append(r)
        for k in range(self.n_links):
            l = self.lengths[k]
            pos.append(origin + r @ ca.vertcat(l / 2, 0, 0))
            origin = origin + r @ ca.vertcat(l, 0, 0)
            if k + 1 < self.n_links:
                r = r @ rotz(q[k + 2])
                rots.append(r)
        kin = 0.5 * self.jrotor * qd[0] ** 2
        pot = 0
        masses = [self.arm_m, *self.masses]
        for m, p, rot, j in zip(masses, pos, rots, self.body_j, strict=True):
            vel = ca.jtimes(p, q, qd)
            rd = ca.reshape(ca.jtimes(ca.vec(rot), q, qd), 3, 3)
            om = rot.T @ rd
            w = ca.vertcat(om[2, 1], om[0, 2], om[1, 0])
            kin += 0.5 * m * ca.dot(vel, vel) + 0.5 * (j[0] * w[0] ** 2 + j[1] * w[1] ** 2 + j[2] * w[2] ** 2)
            pot += m * G * p[2]
        mass = ca.hessian(kin, qd)[0]
        # force on the tip of the last link, perpendicular to the rod in the pendulum plane (body y)
        ydir = r @ ca.vertcat(0, 1, 0)
        jtip = ca.jacobian(origin, q)
        qforce = jtip.T @ ydir
        self.qdist = ca.Function("qdist", [q], [ca.solve(mass, qforce)]).expand()
        self.tip = ca.Function("tip", [q], [origin]).expand()
        dk_dqd = ca.gradient(kin, qd)
        coriolis = ca.jacobian(dk_dqd, q) @ qd
        gen = ca.vertcat(self.a_motor * v - self.c_motor * qd[0], -JFRIC * qd[1:])
        rhs = ca.gradient(kin, q) - coriolis - ca.gradient(pot, q) + gen
        qdd = ca.solve(mass, rhs)
        x = ca.vertcat(q, qd)
        xdot = ca.vertcat(qd, qdd)
        self.f = ca.Function("f", [x, v], [xdot]).expand()
        self.fa = ca.Function("fa", [x, v], [ca.jacobian(xdot, x)]).expand()
        self.fb = ca.Function("fb", [x, v], [ca.jacobian(xdot, v)]).expand()
        self.mass_fn = ca.Function("M", [q], [mass]).expand()
        energy = kin + pot
        self.energy = ca.Function("E", [x], [energy]).expand()

    # numeric helpers -----------------------------------------------------------------
    def rhs(self, x, v):
        return np.array(self.f(x, v)).ravel()

    def linearise(self, x, v):
        return np.array(self.fa(x, v)), np.array(self.fb(x, v)).reshape(self.nx, 1)

    def hanging(self) -> np.ndarray:
        x = np.zeros(self.nx)
        x[1] = math.pi
        return x


# ---------------------------------------------------------------- LQR
def lqr(plant: Plant, qdiag, r: float):
    a, b = plant.linearise(np.zeros(plant.nx), 0.0)
    q = np.diag(qdiag)
    p = solve_continuous_are(a, b, q, np.array([[r]]))
    k = (b.T @ p) / r
    return k.ravel(), p, a, b


# ---------------------------------------------------------------- closed-loop simulation
@dataclass
class Design:
    plant: Plant
    t_on: float
    t_s: float
    vmax: float
    qdiag: np.ndarray
    r: float
    k_lqr: np.ndarray
    p_lqr: np.ndarray
    dt_tab: float
    tab_x: np.ndarray  # (NT, nx) reference states
    tab_u: np.ndarray  # (NT,)
    tab_k: np.ndarray  # (NT, nx)
    catch_w: np.ndarray  # weights of the catch norm
    catch_tol: float
    ts: float = 1e-3


def table_row(design: Design, t: float):
    """Linear interpolation of the table at time `t` (the controller's own rule)."""
    nt = design.tab_x.shape[0]
    s = min(max((t - design.t_on) / design.dt_tab, 0.0), nt - 1)
    i = min(int(math.floor(s)), nt - 2)
    w = s - i
    x = (1 - w) * design.tab_x[i] + w * design.tab_x[i + 1]
    u = (1 - w) * design.tab_u[i] + w * design.tab_u[i + 1]
    k = (1 - w) * design.tab_k[i] + w * design.tab_k[i + 1]
    return x, u, k


def controller(design: Design, t: float, x: np.ndarray, state: dict) -> float:
    """The 1 kHz firmware: idle, TVLQR swing-up, LQR balance (latched)."""
    if t < design.t_on:
        state["phase"] = 0
        return 0.0
    tau = t - design.t_on
    if state["phase"] < 2 and tau >= design.t_s:
        e = x - table_row(design, design.t_on + design.t_s)[0]
        if math.sqrt(float(np.sum(design.catch_w * e * e))) < design.catch_tol:
            state["phase"] = 2
            state["t_catch"] = t
    if state["phase"] == 2:
        u = -float(design.k_lqr @ x)
    else:
        state["phase"] = 1
        xr, ur, k = table_row(design, t)
        u = ur - float(k @ (x - xr))
    return float(np.clip(u, -design.vmax, design.vmax))


def simulate(design: Design, x0, t_end, disturb=None, sub=2, state=None):
    """Closed loop at the sampling rate `design.ts` (zero-order hold), RK4 with `sub` steps."""
    plant = design.plant
    n = int(round(t_end / design.ts))
    x = np.array(x0, float)
    state = state if state is not None else {"phase": 0}
    out_t = np.zeros(n + 1)
    out_x = np.zeros((n + 1, plant.nx))
    out_u = np.zeros(n + 1)
    out_p = np.zeros(n + 1)
    out_x[0] = x
    h = design.ts / sub
    for i in range(n):
        t = i * design.ts
        u = controller(design, t, x, state)
        out_u[i] = u
        out_p[i] = state["phase"]
        for s in range(sub):
            ts = t + s * h
            f = lambda xx, tt: plant.rhs(xx, u) + (disturb(tt, xx) if disturb else 0.0)  # noqa: E731
            k1 = f(x, ts)
            k2 = f(x + 0.5 * h * k1, ts + 0.5 * h)
            k3 = f(x + 0.5 * h * k2, ts + 0.5 * h)
            k4 = f(x + h * k3, ts + h)
            x = x + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        out_t[i + 1] = t + design.ts
        out_x[i + 1] = x
    out_u[n] = out_u[n - 1]
    out_p[n] = out_p[n - 1]
    return out_t, out_x, out_u, out_p, state


# ---------------------------------------------------------------- trajectory optimisation
def swing_up(plant: Plant, t_s: float, vmax: float, nk: int = 60, theta_max: float = 1.5,
             guess=None, verbose: bool = False, rate_weight: float = 0.0, smooth: float = 0.02, rate_max: float | None = None):
    """Hermite-Simpson direct collocation from hanging to upright in the fixed time `t_s`."""
    nx = plant.nx
    h = t_s / nk
    opti = ca.Opti()
    xs = opti.variable(nx, nk + 1)
    us = opti.variable(1, nk + 1)
    um = opti.variable(1, nk)  # control at the interval midpoints
    f = plant.f
    cost = 0
    for k in range(nk):
        x0, x1 = xs[:, k], xs[:, k + 1]
        u0, u1, uc = us[:, k], us[:, k + 1], um[:, k]
        f0, f1 = f(x0, u0), f(x1, u1)
        xc = 0.5 * (x0 + x1) + h / 8.0 * (f0 - f1)
        fc = f(xc, uc)
        opti.subject_to(x1 - x0 == h / 6.0 * (f0 + 4 * fc + f1))
        cost += h / 6.0 * (u0**2 + 4 * uc**2 + u1**2)
        # smoothness of the voltage and a weak penalty on the arm travel
        cost += smooth * (u1 - u0) ** 2 / h
        cost += rate_weight * h * ca.sumsqr(x0[plant.nq + 1 :])
    opti.subject_to(xs[:, 0] == plant.hanging())
    opti.subject_to(xs[:, nk] == np.zeros(nx))
    opti.subject_to(opti.bounded(-vmax, us, vmax))
    opti.subject_to(opti.bounded(-vmax, um, vmax))
    opti.subject_to(opti.bounded(-theta_max, xs[0, :], theta_max))
    if rate_max is not None:
        opti.subject_to(opti.bounded(-rate_max, xs[plant.nq :, :], rate_max))
    opti.minimize(cost)
    if guess is None:
        x0g = np.zeros((nx, nk + 1))
        s = np.linspace(0, 1, nk + 1)
        x0g[1, :] = math.pi * (1 - s)
        opti.set_initial(xs, x0g)
        opti.set_initial(us, 1.0 * np.sin(2 * math.pi * 1.5 * np.linspace(0, t_s, nk + 1)))
        opti.set_initial(um, 0.0)
    else:
        opti.set_initial(xs, guess[0])
        opti.set_initial(us, guess[1])
        opti.set_initial(um, guess[2])
    opts = {"ipopt.max_iter": 3000, "ipopt.tol": 1e-8, "ipopt.print_level": 5 if verbose else 0,
            "print_time": False, "ipopt.mu_strategy": "adaptive"}
    opti.solver("ipopt", opts)
    sol = opti.solve()
    return sol.value(xs), sol.value(us), sol.value(um), float(sol.value(cost))


def tvlqr(plant: Plant, t_s: float, xs, us, um, qdiag, r: float, p_final, dt_tab: float):
    """Time-varying LQR along the collocation trajectory; the table on a `dt_tab` grid."""
    nk = xs.shape[1] - 1
    h = t_s / nk
    tn = np.linspace(0, t_s, nk + 1)
    xd = np.array([plant.rhs(xs[:, k], us[k]) for k in range(nk + 1)])
    spline = CubicHermiteSpline(tn, xs.T, xd)

    def uref(t):
        k = min(int(t / h), nk - 1)
        # piecewise quadratic through (u_k, u_mid, u_k+1)
        s = (t - k * h) / h
        u0, uc, u1 = us[k], um[k], us[k + 1]
        return u0 * (1 - s) * (1 - 2 * s) + uc * 4 * s * (1 - s) + u1 * s * (2 * s - 1)

    nt = int(round(t_s / dt_tab)) + 1
    fine = dt_tab / 5.0
    q = np.diag(qdiag)
    ri = 1.0 / r

    def ab(t):
        t = min(max(t, 0.0), t_s)
        return plant.linearise(spline(t), uref(t))

    def pdot(t, p, a, b):
        return -(q + a.T @ p + p @ a - ri * (p @ b) @ (b.T @ p))

    p = p_final.copy()
    ks = np.zeros((nt, plant.nx))
    ks[nt - 1] = (ri * (ab(t_s)[1].T @ p)).ravel()
    for i in range(nt - 2, -1, -1):
        for j in range(5):
            t1 = (i + 1) * dt_tab - j * fine
            t0 = t1 - fine
            tm = 0.5 * (t0 + t1)
            a1, b1 = ab(t1)
            am, bm = ab(tm)
            a0, b0 = ab(t0)
            # backward RK4 from t1 to t0 (step -fine)
            k1 = pdot(t1, p, a1, b1)
            k2 = pdot(tm, p - 0.5 * fine * k1, am, bm)
            k3 = pdot(tm, p - 0.5 * fine * k2, am, bm)
            k4 = pdot(t0, p - fine * k3, a0, b0)
            p = p - fine / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        ks[i] = (ri * (ab(i * dt_tab)[1].T @ p)).ravel()
    ts_tab = np.arange(nt) * dt_tab
    tab_x = np.array([spline(t) for t in ts_tab])
    tab_u = np.array([uref(min(t, t_s - 1e-12)) for t in ts_tab])
    tab_u[-1] = us[-1]
    return tab_x, tab_u, ks


def sim_guess(plant: Plant, t_s: float, nk: int, amp: float, freq: float, vmax: float):
    """Forward simulation of a sinusoidal voltage from hanging: a dynamically feasible guess."""
    tn = np.linspace(0, t_s, nk + 1)
    def u_of(t):
        return float(np.clip(amp * math.sin(2 * math.pi * freq * t), -vmax, vmax))
    sol = solve_ivp(lambda t, x: plant.rhs(x, u_of(t)), (0, t_s), plant.hanging(), t_eval=tn,
                    rtol=1e-8, atol=1e-8)
    xs = sol.y
    if xs.shape[1] != nk + 1:
        return None
    us = np.array([u_of(t) for t in tn])
    um = np.array([u_of(0.5 * (tn[k] + tn[k + 1])) for k in range(nk)])
    return xs, us, um


def refine_guess(plant: Plant, t_s: float, xs, us, um, nk2: int):
    """Resample a collocation solution onto a finer grid (the warm start of a finer solve)."""
    nk = xs.shape[1] - 1
    tn = np.linspace(0, t_s, nk + 1)
    xd = np.array([plant.rhs(xs[:, k], us[k]) for k in range(nk + 1)])
    spline = CubicHermiteSpline(tn, xs.T, xd)
    t2 = np.linspace(0, t_s, nk2 + 1)
    # the control as the piecewise quadratic through (u_k, u_mid, u_k+1)
    def uref(t):
        h = t_s / nk
        k = min(int(t / h), nk - 1)
        s = (t - k * h) / h
        return us[k] * (1 - s) * (1 - 2 * s) + um[k] * 4 * s * (1 - s) + us[k + 1] * s * (2 * s - 1)
    x2 = spline(t2).T
    u2 = np.array([uref(t) for t in t2])
    m2 = np.array([uref(0.5 * (t2[k] + t2[k + 1])) for k in range(nk2)])
    return x2, u2, m2
