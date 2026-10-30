"""Shared design code of the fixed-pivot (pendubot-type) pendulum examples (X5.11).

``pendulum-double-fixed`` and ``pendulum-triple-fixed`` use this module through ``design.py``
(the triple imports it by path). Everything here works on the *same* plant as the bond graph:

* a chain of ``n`` planar links with distributed mass (the COM at ``lc`` along the rod, yaw inertia
  ``J = m L^2 / 12``), revolute joints with viscous friction ``b``, gravity in -y;
* joint 1 is driven by a DC motor through a gearbox: terminal voltage ``u``, ``R_w``, ``L_w``,
  ``k_t``, ``N`` (motor rate = N times the joint rate), rotor inertia ``J_m`` (reflected as
  ``N^2 J_m`` on joint 1);
* the other joints are passive.

Angles are the model's coordinates: ``q1`` is the absolute angle of link 1 from the +x axis
(hanging: -pi/2, upright: +pi/2), ``q2..qn`` are the relative joint angles (0 when the chain is
straight), so the absolute angle of link k is ``theta_k = q1 + ... + qk``.

The module provides the symbolic dynamics (CasADi), the infinite-horizon LQR, the direct-collocation
swing-up (Hermite-Simpson, IPOPT), the time-varying LQR along the optimised trajectory and a
sampled-data simulation of the whole scenario with the exact control law of ``library/*Ctrl.jl``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import casadi as ca
import numpy as np
from scipy.linalg import expm, solve_discrete_are

TS = 1.0e-3  # controller period (s)


@dataclass(frozen=True)
class Plant:
    name: str
    m: tuple[float, ...]  # link masses (kg)
    L: tuple[float, ...]  # link lengths (m)
    lc: tuple[float, ...]  # COM distance from the link's pivot (m)
    b: tuple[float, ...]  # viscous joint friction on the relative joint rate (N m s/rad)
    N: float  # gear ratio, motor rate = N * joint-1 rate
    kt: float  # motor torque / back-EMF constant (N m/A, V s/rad)
    Rw: float  # winding resistance (Ohm)
    Lw: float  # winding inductance (H)
    Jm: float  # rotor inertia (kg m^2)
    bm: float = 0.0  # rotor viscous loss (N m s/rad)
    ks: float = 5.0e3  # drive-train shaft stiffness on the motor side (N m/rad)
    ds: float = 0.2  # drive-train shaft damping on the motor side (N m s/rad)
    umax: float = 12.0  # supply voltage limit (V)
    g: float = 9.81

    @property
    def n(self) -> int:
        return len(self.m)

    @property
    def J(self) -> tuple[float, ...]:
        return tuple(m * L * L / 12.0 for m, L in zip(self.m, self.L))


class Dynamics:
    """Symbolic equations of motion and their CasADi functions."""

    def __init__(self, P: Plant) -> None:
        self.P = P
        n = P.n
        q = ca.SX.sym("q", n)
        qd = ca.SX.sym("qd", n)
        u = ca.SX.sym("u")
        i = ca.SX.sym("i")
        F = ca.SX.sym("F")  # force at the tip, perpendicular to the last link (N)
        th = [ca.sum1(q[: k + 1]) for k in range(n)]
        x = ca.SX(0)
        y = ca.SX(0)
        com = []
        for k in range(n):
            c, s = ca.cos(th[k]), ca.sin(th[k])
            com.append(ca.vertcat(x + P.lc[k] * c, y + P.lc[k] * s))
            x = x + P.L[k] * c
            y = y + P.L[k] * s
        tip = ca.vertcat(x, y)
        T = 0.5 * P.N**2 * P.Jm * qd[0] ** 2
        V = ca.SX(0)
        for k in range(n):
            v = ca.mtimes(ca.jacobian(com[k], q), qd)
            T += 0.5 * P.m[k] * ca.dot(v, v) + 0.5 * P.J[k] * ca.sum1(qd[: k + 1]) ** 2
            V += P.m[k] * P.g * com[k][1]
        p = ca.jacobian(T, qd).T
        M = ca.jacobian(p, qd)
        bias = ca.mtimes(ca.jacobian(p, q), qd) - ca.jacobian(T, q).T
        G = ca.jacobian(V, q).T
        Fgen = ca.mtimes(ca.jacobian(tip, q).T, F * ca.vertcat(-ca.sin(th[-1]), ca.cos(th[-1])))
        fric = ca.vertcat(*[P.b[k] * qd[k] for k in range(n)])
        fric[0] += P.N**2 * P.bm * qd[0]
        self.th = th
        xs = ca.vertcat(q, qd)
        # reduced model (winding inductance neglected): i = (u - N kt qd1) / Rw
        i_red = (u - P.N * P.kt * qd[0]) / P.Rw
        tau = -fric + Fgen
        tau[0] += P.N * P.kt * i_red
        qdd = ca.solve(M, tau - bias - G)
        self.f_red = ca.Function("f_red", [xs, u, F], [ca.vertcat(qd, qdd)])
        # full model with the winding current as a state
        tau_f = -fric + Fgen
        tau_f[0] += P.N * P.kt * i
        qdd_f = ca.solve(M, tau_f - bias - G)
        di = (u - P.Rw * i - P.N * P.kt * qd[0]) / P.Lw
        xf = ca.vertcat(q, qd, i)
        self.f_full = ca.Function("f_full", [xf, u, F], [ca.vertcat(qd, qdd_f, di)])
        rhs = self.f_red(xs, u, 0.0)
        self.A_fun = ca.Function("A", [xs, u], [ca.jacobian(rhs, xs)])
        self.B_fun = ca.Function("B", [xs, u], [ca.jacobian(rhs, u)])
        self.tip_fun = ca.Function("tip", [q], [tip])
        self.M_fun = ca.Function("M", [q], [M])
        self.n = n
        self.x_up = np.array([math.pi / 2] + [0.0] * (2 * n - 1))
        self.x_down = np.array([-math.pi / 2] + [0.0] * (2 * n - 1))

    def f(self, x, u, F=0.0):
        return np.array(self.f_red(x, u, F)).ravel()

    def linearise(self, x, u=0.0):
        return np.array(self.A_fun(x, u)), np.array(self.B_fun(x, u))

    def zoh(self, x, u, Ts=TS):
        """Exact zero-order-hold discretisation of the linearisation at (x, u)."""
        A, B = self.linearise(x, u)
        nx = A.shape[0]
        E = np.zeros((nx + 1, nx + 1))
        E[:nx, :nx] = A
        E[:nx, nx:] = B
        Phi = expm(E * Ts)
        return Phi[:nx, :nx], Phi[:nx, nx:]


# ------------------------------------------------------------------------------------------ LQR


def lqr_gain(dyn: Dynamics, Q: np.ndarray, R: float, Ts: float = TS):
    """Discrete infinite-horizon LQR at upright (ZOH, sample time Ts): K, P (u = -K (x - x_up))."""
    Ad, Bd = dyn.zoh(dyn.x_up, 0.0, Ts)
    P = solve_discrete_are(Ad, Bd, Q, np.array([[R]]))
    K = np.linalg.solve(np.array([[R]]) + Bd.T @ P @ Bd, Bd.T @ P @ Ad)
    return K.ravel(), P, Ad, Bd


# ----------------------------------------------------------------------------- swing-up (TO)


def swing_up(
    dyn: Dynamics,
    T: float,
    nk: int,
    u_limit: float,
    guess_amp: float = 4.0,
    guess_cycles: float = 1.5,
    w_reg: float = 1.0e-4,
    x_init: np.ndarray | None = None,
    u_init: np.ndarray | None = None,
    verbose: bool = False,
):
    """Direct collocation (Hermite-Simpson) from hanging to upright in the fixed time ``T``.

    Controls are the motor voltage at the knots (piecewise linear in between). The cost is the
    integral of (u/u_limit)^2 plus a small regularisation of the joint rates. Returns the knot
    times, states (nx x nk+1) and voltages (nk+1).
    """
    nx = 2 * dyn.n
    h = T / nk
    opti = ca.Opti()
    X = opti.variable(nx, nk + 1)
    U = opti.variable(nk + 1)
    f = dyn.f_red
    cost = 0
    for k in range(nk):
        xk, xn = X[:, k], X[:, k + 1]
        uk, un = U[k], U[k + 1]
        fk = f(xk, uk, 0.0)
        fn = f(xn, un, 0.0)
        xm = 0.5 * (xk + xn) + h / 8.0 * (fk - fn)
        um = 0.5 * (uk + un)
        fm = f(xm, um, 0.0)
        opti.subject_to(xn - xk == h / 6.0 * (fk + 4 * fm + fn))
        cost += h / 6.0 * ((uk / u_limit) ** 2 + 4 * (um / u_limit) ** 2 + (un / u_limit) ** 2)
        cost += w_reg * h * ca.sumsqr(xk[dyn.n :])
    opti.minimize(cost)
    opti.subject_to(X[:, 0] == dyn.x_down)
    opti.subject_to(X[:, nk] == dyn.x_up)
    opti.subject_to(opti.bounded(-u_limit, U, u_limit))
    tt = np.linspace(0.0, T, nk + 1)
    if x_init is None:
        s = tt / T
        xg = np.zeros((nx, nk + 1))
        xg[0] = -math.pi / 2 + math.pi * s
        xg[dyn.n] = math.pi / T
    else:
        xg = x_init
    opti.set_initial(X, xg)
    opti.set_initial(U, u_init if u_init is not None else guess_amp * np.sin(2 * math.pi * guess_cycles * tt / T))
    opts = {"ipopt.max_iter": 1500, "ipopt.tol": 1e-8, "ipopt.print_level": 5 if verbose else 0, "print_time": 0}
    opti.solver("ipopt", opts)
    sol = opti.solve()
    return tt, np.array(sol.value(X)), np.array(sol.value(U))


# ------------------------------------------------------------------------------- trajectory


class Nominal:
    """The optimised trajectory sampled at 1 kHz: cubic Hermite in the state, linear in the voltage.

    The swing-up is open-loop unstable (poles near +10 1/s), so the nominal states are the
    collocation knots (Hermite-interpolated with ``f(x_k, u_k)``), not a forward integration.
    """

    def __init__(self, dyn: Dynamics, tt, X, U, Ts: float = TS) -> None:
        from scipy.interpolate import CubicHermiteSpline

        self.dyn = dyn
        self.T = float(tt[-1])
        self.Ts = Ts
        self.steps = int(round(self.T / Ts))
        self.t = np.arange(self.steps + 1) * Ts
        self.u_knot = (np.asarray(tt), np.asarray(U))
        dX = np.array([dyn.f(X[:, k], U[k]) for k in range(len(tt))]).T
        spline = CubicHermiteSpline(tt, X.T, dX.T)
        self.x = spline(self.t)
        self.spline = spline

    def u(self, t: float) -> float:
        tt, U = self.u_knot
        return float(np.interp(t, tt, U))

    def x_at(self, t: float) -> np.ndarray:
        return np.asarray(self.spline(t))

    @property
    def u_samples(self) -> np.ndarray:
        return np.array([self.u(t) for t in self.t])


def tvlqr(dyn: Dynamics, nom: Nominal, Q: np.ndarray, R: float, S_end: np.ndarray):
    """Discrete time-varying LQR along the nominal trajectory; K[k] is the gain of tick k."""
    nx = 2 * dyn.n
    steps = nom.steps
    K = np.zeros((steps + 1, nx))
    S = S_end.copy()
    Rm = np.array([[R]])
    for k in range(steps - 1, -1, -1):
        xm = nom.x_at(nom.t[k] + 0.5 * nom.Ts)
        um = nom.u(nom.t[k] + 0.5 * nom.Ts)
        Ad, Bd = dyn.zoh(xm, um, nom.Ts)
        Kk = np.linalg.solve(Rm + Bd.T @ S @ Bd, Bd.T @ S @ Ad)
        S = Q + Ad.T @ S @ (Ad - Bd @ Kk)
        S = 0.5 * (S + S.T)
        K[k] = Kk.ravel()
    K[steps] = K[steps - 1]
    return K


# -------------------------------------------------------------------------------- controller


@dataclass
class Tables:
    """What goes into the controller block."""

    dt: float  # table spacing (s)
    xs: np.ndarray  # (rows, nx) nominal states
    us: np.ndarray  # (rows,)
    Ks: np.ndarray  # (rows, nx)
    K_lqr: np.ndarray  # (nx,)
    P_lqr: np.ndarray  # (nx, nx)
    t_on: float
    T_s: float
    V_catch: float
    u_max: float
    x_up: np.ndarray = field(default_factory=lambda: np.zeros(0))


def tables_from(nom: Nominal, K: np.ndarray, dt: float, lqr: tuple, t_on: float, V_catch: float, umax: float, x_up):
    stride = int(round(dt / nom.Ts))
    idx = np.arange(0, nom.steps + 1, stride)
    if idx[-1] != nom.steps:
        raise ValueError("T_s must be a multiple of the table spacing")
    return Tables(dt, nom.x[idx].copy(), nom.u_samples[idx].copy(), K[idx].copy(), lqr[0], lqr[1], t_on, nom.T,
                  V_catch, umax, np.asarray(x_up))


class Controller:
    """The control law of ``library/*Ctrl.jl`` in Python (same arithmetic, tick by tick)."""

    def __init__(self, tab: Tables) -> None:
        self.tab = tab
        self.caught = 0

    def tick(self, tm: float, x: np.ndarray) -> tuple[float, int]:
        tb = self.tab
        e_up = x - tb.x_up
        V = float(e_up @ tb.P_lqr @ e_up)
        phase = 0
        u = 0.0
        if tm >= tb.t_on:
            if self.caught == 0 and V < tb.V_catch:
                self.caught = 1
            if self.caught == 1:
                phase = 2
                u = -float(tb.K_lqr @ e_up)
            else:
                phase = 1
                s = (tm - tb.t_on) / tb.dt
                rows = len(tb.us)
                s = min(max(s, 0.0), rows - 1.0)
                k0 = min(int(math.floor(s)), rows - 2)
                w = s - k0
                xr = tb.xs[k0] * (1 - w) + tb.xs[k0 + 1] * w
                ur = tb.us[k0] * (1 - w) + tb.us[k0 + 1] * w
                Kr = tb.Ks[k0] * (1 - w) + tb.Ks[k0 + 1] * w
                u = ur - float(Kr @ (x - xr))
        return float(np.clip(u, -tb.u_max, tb.u_max)), phase


def simulate(dyn: Dynamics, tab: Tables, x0, t_end: float, dist=None, Ts: float = TS):
    """Sampled-data closed loop on the full model (with the winding current).

    ``dist = (t_start, duration, force)`` applies a tip force pulse. Returns time, states
    (rows: q, qd, i), voltage, phase.
    """
    nx = 2 * dyn.n
    xf = ca.SX.sym("xf", nx + 1)
    u = ca.SX.sym("u")
    F = ca.SX.sym("F")
    rhs = dyn.f_full(xf, u, F)
    integ = ca.integrator("sim", "cvodes", {"x": xf, "p": ca.vertcat(u, F), "ode": rhs}, 0.0, Ts,
                          {"abstol": 1e-11, "reltol": 1e-10})
    steps = int(round(t_end / Ts))
    out_t = np.zeros(steps + 1)
    out_x = np.zeros((steps + 1, nx + 1))
    out_u = np.zeros(steps + 1)
    out_ph = np.zeros(steps + 1, dtype=int)
    state = np.concatenate([x0, [0.0]])
    out_x[0] = state
    ctrl = Controller(tab)
    uh, ph = 0.0, 0
    for k in range(steps):
        t = k * Ts
        if k >= 1:
            uh, ph = ctrl.tick(t, state[:nx])
        Fk = 0.0
        if dist is not None and dist[0] <= t < dist[0] + dist[1] - 1e-12:
            Fk = dist[2]
        state = np.array(integ(x0=state, p=[uh, Fk])["xf"]).ravel()
        out_t[k + 1] = (k + 1) * Ts
        out_x[k + 1] = state
        out_u[k] = uh
        out_u[k + 1] = uh
        out_ph[k + 1] = ph
    return out_t, out_x, out_u, out_ph


def free_swing(dyn: Dynamics, x0, t_end: float, n_out: int):
    """Open-loop swing with the motor terminals at 0 V (full model with the winding current)."""
    from scipy.integrate import solve_ivp

    nx = 2 * dyn.n
    y0 = np.concatenate([x0, [0.0]])
    t_eval = np.linspace(0.0, t_end, n_out)
    sol = solve_ivp(lambda t, y: np.array(dyn.f_full(y, 0.0, 0.0)).ravel(), (0.0, t_end), y0,
                    method="Radau", t_eval=t_eval, rtol=1e-11, atol=1e-13)
    return sol.t, sol.y[:nx].T
