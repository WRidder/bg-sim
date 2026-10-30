"""Shared design code of the X5.12 cart pendulums (`pendulum-double-cart`, `pendulum-triple-cart`).

An ``n``-link pendulum hangs from a cart on a rail. The cart is driven by a DC motor through a
gearbox and a belt/pulley; the pendulum joints are passive. This module holds everything the two
examples share and that is *design*, not model: the Lagrangian dynamics (CasADi), the LQR and the
time-varying LQR, the direct-collocation swing-up (IPOPT), a replica of the closed loop that is
used to produce the reference numbers, and the writer of the controller block's constant tables.
`design.py` of each example sets the parameters and calls these functions; `cartmodel.py` writes
the bond-graph model document from the same ``Plant``.

Coordinates. ``q = [x, th_1 .. th_n]`` with ``x`` the cart position (m) and ``th_i`` the *absolute*
angle of link ``i`` measured from the upward vertical, counter-clockwise (rad). The link direction
is ``u_i = (-sin th_i, cos th_i)``, joint ``i`` sits at ``p_i = p_{i-1} + L_{i-1} u_{i-1}`` (``p_1``
is the cart centre) and the centre of mass of link ``i`` is ``p_i + c_i u_i``. The bond-graph joint
angles are ``Q_1 = th_1 + pi/2`` (angle from the world x axis) and ``Q_j = th_j - th_{j-1}``.
The state is ``z = [q, qdot]`` and the input is the motor terminal voltage ``V``.

Drive. With the gear ratio ``N`` (motor turns per pulley turn) and the pulley radius ``r`` the
motor sees the cart through the factor ``N/r``. The armature inductance is neglected (the
electrical time constant L/R is 70 us), the rotor inertia ``J_m`` is reflected onto the cart mass:

    m_eff = m_cart + J_m (N/r)^2
    F     = alpha V - beta xdot,   alpha = k_t N/(r R),   beta = (k_t^2/R + b_m) (N/r)^2
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import casadi as ca
import numpy as np
import scipy.linalg as sla
from scipy.integrate import solve_ivp

G0 = 9.81


@dataclass
class Plant:
    name: str
    L: list            # link lengths (m)
    m: list            # link masses (kg)
    c: list            # joint -> centre of mass distance along the link (m)
    J: list            # inertia about the centre of mass (kg m^2)
    b: list            # joint viscous friction (N m s/rad)
    m_cart: float
    J_cart: float
    # motor and transmission
    R_m: float
    L_m: float
    k_t: float
    J_m: float
    b_m: float
    N: float
    r: float
    u_max: float       # supply voltage limit (V)
    x_rail: float      # rail half travel of the cart centre (m)
    # compliances of the bond-graph model (not seen by the design model)
    kt_pivot: float = 1.0e8
    bt_pivot: float = 1.0e3
    kr_rail: float = 1.0e5
    br_rail: float = 2.0
    kd_rail: float = 1.0e8
    bd_rail: float = 2.0e3
    k_belt: float = 4.0e5
    d_belt: float = 60.0

    @property
    def n(self) -> int:
        return len(self.L)

    @property
    def nq(self) -> int:
        return self.n + 1

    @property
    def nx(self) -> int:
        return 2 * (self.n + 1)

    @property
    def m_eff(self) -> float:
        return self.m_cart + self.J_m * (self.N / self.r) ** 2

    @property
    def alpha(self) -> float:
        return self.k_t * self.N / (self.r * self.R_m)

    @property
    def beta(self) -> float:
        return (self.k_t**2 / self.R_m + self.b_m) * (self.N / self.r) ** 2


# --------------------------------------------------------------------------------- dynamics


class Dynamics:
    """CasADi functions of the design model: ``f(z, V, Fd)`` and the energy."""

    def __init__(self, P: Plant):
        self.P = P
        n, nq = P.n, P.nq
        q = ca.SX.sym("q", nq)
        qd = ca.SX.sym("qd", nq)
        V = ca.SX.sym("V")
        Fd = ca.SX.sym("Fd")
        th = q[1:]
        px, py = q[0], ca.SX(0)
        T = 0.5 * P.m_eff * qd[0] ** 2
        Vpot = ca.SX(0)
        for i in range(n):
            ux, uy = -ca.sin(th[i]), ca.cos(th[i])
            cx, cy = px + P.c[i] * ux, py + P.c[i] * uy
            vc = ca.jacobian(ca.vertcat(cx, cy), q) @ qd
            T += 0.5 * P.m[i] * (vc[0] ** 2 + vc[1] ** 2) + 0.5 * P.J[i] * qd[1 + i] ** 2
            Vpot += P.m[i] * G0 * cy
            px, py = px + P.L[i] * ux, py + P.L[i] * uy
        tip = ca.vertcat(px, py)
        # tip force direction: n_perp = d u / d th = (-cos th, -sin th)
        thn = th[n - 1]
        nperp = ca.vertcat(-ca.cos(thn), -ca.sin(thn))
        Qd = ca.jacobian(tip, q).T @ (Fd * nperp)
        # Rayleigh dissipation of the joint friction
        D = ca.SX(0)
        for i in range(n):
            rel = qd[1 + i] - (qd[i] if i > 0 else 0)
            D += 0.5 * P.b[i] * rel**2
        Fm = P.alpha * V - P.beta * qd[0]
        Q = ca.vertcat(Fm, ca.SX.zeros(n)) - ca.jacobian(D, qd).T + Qd
        Lag = T - Vpot
        pmom = ca.jacobian(T, qd).T
        M = ca.jacobian(pmom, qd)
        rhs = Q + ca.jacobian(Lag, q).T - ca.jacobian(pmom, q) @ qd
        qdd = ca.solve(M, rhs)
        z = ca.vertcat(q, qd)
        zdot = ca.vertcat(qd, qdd)
        self.f = ca.Function("f", [z, V, Fd], [zdot])
        self.A = ca.Function("A", [z, V, Fd], [ca.jacobian(zdot, z)])
        self.B = ca.Function("B", [z, V, Fd], [ca.jacobian(zdot, V)])
        self.energy = ca.Function("E", [z], [T + Vpot])
        self.M = ca.Function("M", [z], [M])
        self.tip = ca.Function("tip", [z], [tip])

    def __call__(self, z, V=0.0, Fd=0.0):
        return np.array(self.f(z, V, Fd)).ravel()

    def lin(self, z, V=0.0):
        return np.array(self.A(z, V, 0.0)), np.array(self.B(z, V, 0.0)).reshape(-1, 1)


def rk4(f, z, V, Fd, h):
    k1 = f(z, V, Fd)
    k2 = f(z + 0.5 * h * k1, V, Fd)
    k3 = f(z + 0.5 * h * k2, V, Fd)
    k4 = f(z + h * k3, V, Fd)
    return z + h / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)


# --------------------------------------------------------------------------------- LQR


def dlqr(P: Plant, dyn: Dynamics, Q, R, Ts):
    """Discrete LQR at the upright for the zero-order-hold sampled linearisation."""
    A, B = dyn.lin(np.zeros(P.nx))
    n = A.shape[0]
    M = sla.expm(np.block([[A, B], [np.zeros((1, n)), np.zeros((1, 1))]]) * Ts)
    Ad, Bd = M[:n, :n], M[:n, n:]
    Pd = sla.solve_discrete_are(Ad, Bd, Q, np.atleast_2d(R))
    K = np.linalg.solve(np.atleast_2d(R) + Bd.T @ Pd @ Bd, Bd.T @ Pd @ Ad)
    return K.ravel(), Pd, (Ad, Bd)


def clqr(P: Plant, dyn: Dynamics, Q, R):
    A, B = dyn.lin(np.zeros(P.nx))
    Pc = sla.solve_continuous_are(A, B, Q, np.atleast_2d(R))
    K = np.linalg.solve(np.atleast_2d(R), B.T @ Pc)
    return K.ravel(), Pc, (A, B)


# --------------------------------------------------------------------------------- swing-up


def hang_state(P: Plant) -> np.ndarray:
    z = np.zeros(P.nx)
    z[1 : 1 + P.n] = -np.pi
    return z


def swingup(P: Plant, dyn: Dynamics, T: float, K: int, u_lim: float, x_lim: float,
            guess=None, w_du=0.02, w_x=0.0, x_end=0.0, verbose=True, max_iter=1500):
    """Hermite-Simpson direct collocation from hanging to upright, rest at both ends.

    Minimises ``int V^2 + w_x x^2 dt + w_du sum (dV)^2`` with ``|V| <= u_lim`` and ``|x| <= x_lim``.
    The inputs are piecewise linear in time. Returns the node times, states, inputs and the
    state derivatives at the nodes.
    """
    nx, h = P.nx, T / K
    opti = ca.Opti()
    Z = opti.variable(nx, K + 1)
    U = opti.variable(1, K + 1)
    f = dyn.f
    F = [f(Z[:, k], U[0, k], 0.0) for k in range(K + 1)]
    cost = 0
    for k in range(K):
        zm = 0.5 * (Z[:, k] + Z[:, k + 1]) + h / 8.0 * (F[k] - F[k + 1])
        um = 0.5 * (U[0, k] + U[0, k + 1])
        fm = f(zm, um, 0.0)
        opti.subject_to(Z[:, k + 1] - Z[:, k] - h / 6.0 * (F[k] + 4 * fm + F[k + 1]) == 0)
        cost += h / 6.0 * (U[0, k] ** 2 + 4 * um**2 + U[0, k + 1] ** 2)
        cost += h / 6.0 * w_x * (Z[0, k] ** 2 + 4 * zm[0] ** 2 + Z[0, k + 1] ** 2)
        cost += w_du * (U[0, k + 1] - U[0, k]) ** 2
    opti.minimize(cost)
    opti.subject_to(Z[:, 0] == hang_state(P))
    opti.subject_to(Z[1:, K] == np.zeros(nx - 1))
    opti.subject_to(Z[0, K] == x_end)
    opti.subject_to(opti.bounded(-x_lim, Z[0, :], x_lim))
    opti.subject_to(opti.bounded(-u_lim, U, u_lim))
    if guess is None:
        tt = np.linspace(0, 1, K + 1)
        s = 0.5 - 0.5 * np.cos(np.pi * tt)
        g = np.zeros((nx, K + 1))
        for i in range(P.n):
            g[1 + i] = -np.pi * (1 - s)
        g[0] = 0.15 * np.sin(2 * np.pi * 2 * tt) * np.sin(np.pi * tt)
        guess = (g, np.zeros(K + 1))
    opti.set_initial(Z, guess[0])
    opti.set_initial(U, guess[1])
    opts = {"ipopt.max_iter": max_iter, "ipopt.tol": 1e-8, "ipopt.print_level": 5 if verbose else 0,
            "print_time": verbose, "ipopt.mu_strategy": "adaptive"}
    opti.solver("ipopt", opts)
    sol = opti.solve()
    Zs, Us = np.array(sol.value(Z)), np.array(sol.value(U)).ravel()
    Fs = np.array([dyn(Zs[:, k], Us[k], 0.0) for k in range(K + 1)]).T
    return {"t": np.linspace(0, T, K + 1), "Z": Zs, "U": Us, "F": Fs, "T": T, "K": K}


class Nominal:
    """Cubic-Hermite state and linear input interpolation of a collocation solution."""

    def __init__(self, traj):
        self.t, self.Z, self.U, self.F = traj["t"], traj["Z"], traj["U"], traj["F"]
        self.T = traj["T"]

    def z(self, t):
        t = min(max(t, 0.0), self.T)
        k = min(int(np.searchsorted(self.t, t, side="right") - 1), len(self.t) - 2)
        h = self.t[k + 1] - self.t[k]
        s = (t - self.t[k]) / h
        h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
        h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
        return h00 * self.Z[:, k] + h10 * h * self.F[:, k] + h01 * self.Z[:, k + 1] + h11 * h * self.F[:, k + 1]

    def u(self, t):
        t = min(max(t, 0.0), self.T)
        return float(np.interp(t, self.t, self.U))


def tvlqr(P: Plant, dyn: Dynamics, nom: Nominal, Q, R, Pf, t_knots):
    """Backward Riccati along the nominal. Returns K[k] (nx,) at every knot, and P at the knots."""
    nx = P.nx
    Ri = np.linalg.inv(np.atleast_2d(R))

    def rhs(t, p):
        Pm = p.reshape(nx, nx)
        A, B = dyn.lin(nom.z(t), nom.u(t))
        dP = -(Q + A.T @ Pm + Pm @ A - Pm @ B @ Ri @ B.T @ Pm)
        return dP.ravel()

    T = t_knots[-1]
    sol = solve_ivp(rhs, [T, t_knots[0]], Pf.ravel(), t_eval=t_knots[::-1], rtol=1e-8, atol=1e-10,
                    method="RK45", max_step=0.01)
    Ps = sol.y.T[::-1].reshape(len(t_knots), nx, nx)
    Ks = np.zeros((len(t_knots), nx))
    for k, t in enumerate(t_knots):
        _, B = dyn.lin(nom.z(t), nom.u(t))
        Ks[k] = (Ri @ B.T @ Ps[k]).ravel()
    return Ks, Ps


# --------------------------------------------------------------------------------- closed loop


@dataclass
class Tables:
    """What the controller block holds: knots, feed-forward, nominal state, TVLQR gains, LQR gain."""
    t_on: float
    T_s: float
    tk: np.ndarray
    uff: np.ndarray
    xs: np.ndarray      # (nk, nx)
    Ks: np.ndarray      # (nk, nx)
    Klqr: np.ndarray    # (nx,)
    u_max: float
    Ts: float = 1e-3


def control(tab: Tables, t, z, state):
    """The firmware of `library/*Ctrl.jl` (one tick). `state` = dict(mode). Returns (u, mode)."""
    if t >= tab.t_on:
        state["mode"] = 2.0 if t - tab.t_on >= tab.T_s else 1.0
    if state["mode"] > 1.5:
        out = -float(tab.Klqr @ z)
    elif state["mode"] > 0.5:
        tau = t - tab.t_on
        xs = np.array([np.interp(tau, tab.tk, tab.xs[:, i]) for i in range(len(z))])
        Kt = np.array([np.interp(tau, tab.tk, tab.Ks[:, i]) for i in range(len(z))])
        out = np.interp(tau, tab.tk, tab.uff) - float(Kt @ (z - xs))
    else:
        out = 0.0
    return float(np.clip(out, -tab.u_max, tab.u_max)), state["mode"]


def disturbance(t, t_d, dur, amp):
    """Rectangular force pulse (N), perpendicular to the tip link."""
    return amp if t_d <= t < t_d + dur else 0.0


def simulate(P: Plant, dyn: Dynamics, tab: Tables, t_end: float, z0, dist=None, sample=1e-3,
             out_dt=0.005):
    """Closed loop of the design model under the 1 kHz zero-order-hold firmware (RK4, 0.25 ms).

    Returns rows ``[t, u, mode, z...]`` every ``out_dt``.
    """
    state = {"mode": 0.0}
    z = np.array(z0, float)
    n_tick = int(round(t_end / sample))
    sub = 4
    hs = sample / sub
    rec = []
    for k in range(n_tick):
        t = k * sample
        u, ph = control(tab, t, z, state)
        if k % int(round(out_dt / sample)) == 0:
            rec.append(np.concatenate([[t, u, ph], z]))
        for s in range(sub):
            Fd = dist(t + (s + 0.5) * hs) if dist else 0.0
            z = rk4(dyn, z, u, Fd, hs)
    rec.append(np.concatenate([[n_tick * sample, 0.0, state["mode"]], z]))
    return np.array(rec)


# --------------------------------------------------------------------------------- Julia tables


def _vec(a, fmt="%.9g"):
    return "[" + ", ".join(fmt % v for v in a) + "]"


def write_controller(lib: Path, prefix: str, P: Plant, tab: Tables, doc: str):
    """Write `library/<prefix>Traj.jl` (the continuous table lookup) and `<prefix>Ctrl.jl` (the 1 kHz firmware).

    `interp1` is an equation-scope intrinsic, so the nominal trajectory and the TVLQR gains are looked
    up in a continuous block; the firmware samples its outputs at every tick (zero-order hold).
    """
    nx, n = P.nx, P.n
    nk = len(tab.tk)
    names = ["x"] + [f"th{i + 1}" for i in range(n)] + ["v"] + [f"w{i + 1}" for i in range(n)]
    # ---- the lookup block
    L = []
    A = L.append
    A(f"@block {prefix}Traj begin")
    A("    # Swing-up trajectory tables (design/design.py, 10 ms knots): the feed-forward voltage, the nominal")
    A("    # state z* = [x, th_1.., v, w_1..] and the TVLQR gain row K (u = u_ff - K (z - z*)), looked up")
    A("    # linearly at tau = t - t_on (held at the ends). The firmware samples these outputs at its ticks.")
    A("    # Generated: do not edit the tables by hand.")
    A(f"    @constants NK::Int = {nk}")
    A("    @inputs tm::Real")
    A("    @outputs begin")
    A('        ff::Real, [unit = "V", description = "Feed-forward voltage"]')
    A(f"        xs::Vec{{{nx}}}")
    A(f"        Ks::Vec{{{nx}}}")
    A("    end")
    A("    @parameters begin")
    A(f'        t_on::Real = {tab.t_on:.9g}, [unit = "s", description = "Start of the swing-up"]')
    A(f'        tk::Vec{{NK}} = {_vec(tab.tk)}, [unit = "s", description = "Trajectory knots"]')
    A(f'        uff::Vec{{NK}} = {_vec(tab.uff)}, [unit = "V", description = "Feed-forward voltage"]')
    for i in range(nx):
        A(f'        z{i + 1}::Vec{{NK}} = {_vec(tab.xs[:, i])}, [description = "Nominal {names[i]}"]')
    for i in range(nx):
        A(f'        k{i + 1}::Vec{{NK}} = {_vec(tab.Ks[:, i])}, [description = "TVLQR gain on {names[i]}"]')
    A("    end")
    A("    @equations begin")
    A("        ff ~ interp1(tm - t_on, tk, uff)")
    for i in range(nx):
        A(f"        xs[{i + 1}] ~ interp1(tm - t_on, tk, z{i + 1})")
    for i in range(nx):
        A(f"        Ks[{i + 1}] ~ interp1(tm - t_on, tk, k{i + 1})")
    A("    end")
    A("end")
    with open(lib / f"{prefix}Traj.jl", "w", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")

    # ---- the firmware
    L = []
    A = L.append
    A(f"@block {prefix}Ctrl begin")
    for ln in doc.strip("\n").split("\n"):
        A(("    # " + ln).rstrip())
    A("    @inputs begin")
    A('        tm::Real, [unit = "s"]')
    A('        x::Real, [unit = "m"]')
    A('        v::Real, [unit = "m/s"]')
    for i in range(n):
        A(f'        q{i + 1}::Real, [unit = "rad"]')
    for i in range(n):
        A(f'        wq{i + 1}::Real, [unit = "rad/s"]')
    A('        ff::Real, [unit = "V"]')
    A(f"        xs::Vec{{{nx}}}")
    A(f"        Ks::Vec{{{nx}}}")
    A("    end")
    A("    @outputs begin")
    A('        u::Real = 0.0, [unit = "V", description = "Motor terminal voltage"]')
    A('        phase::Real = 0.0, [description = "0 hold, 1 swing-up (TVLQR), 2 balance (LQR)"]')
    for i in range(n):
        A(f'        th{i + 1}::Real = {-np.pi:.17g}, [unit = "rad", description = "Absolute angle of link {i + 1} from the upward vertical"]')
    A("    end")
    A("    @parameters begin")
    A(f'        t_on::Real = {tab.t_on:.9g}, [unit = "s", description = "Start of the swing-up"]')
    A(f'        T_s::Real = {tab.T_s:.9g}, [unit = "s", description = "Swing-up duration (the catch follows at t_on + T_s)"]')
    A(f'        u_max::Real = {tab.u_max:.9g}, [unit = "V", min = 0, description = "Voltage limit"]')
    A(f'        Klqr::Vec{{{nx}}} = {_vec(tab.Klqr)}, [description = "LQR gain on [{", ".join(names)}] (u = -K z)"]')
    A("    end")
    A("    @variables begin")
    A('        mode::Real = 0.0, [description = "Latched phase"]')
    A("    end")
    A(f"    @discrete Ts = {tab.Ts:g} begin")
    A(f"        t1 = q1 - {np.pi / 2:.17g}")
    for i in range(1, n):
        A(f"        t{i + 1} = t{i} + q{i + 1}")
    A("        w1a = wq1")
    for i in range(1, n):
        A(f"        w{i + 1}a = w{i}a + wq{i + 1}")
    for i in range(n):
        A(f"        th{i + 1} = t{i + 1}")
    zlist = ["x"] + [f"t{i + 1}" for i in range(n)] + ["v"] + [f"w{i + 1}a" for i in range(n)]
    A("        tau = tm - t_on")
    A("        out = 0.0")
    A("        if tm >= t_on")
    A("            if tau >= T_s")
    A("                mode = 2.0")
    A("            else")
    A("                mode = 1.0")
    A("            end")
    A("        end")
    A("        if mode > 1.5")
    terms = " + ".join(f"Klqr[{i + 1}] * {zlist[i]}" for i in range(nx))
    A(f"            out = -({terms})")
    A("        end")
    A("        if mode > 0.5 && mode < 1.5")
    terms = " + ".join(f"Ks[{i + 1}] * ({zlist[i]} - xs[{i + 1}])" for i in range(nx))
    A(f"            out = ff - ({terms})")
    A("        end")
    A("        u = clamp(out, -u_max, u_max)")
    A("        phase = mode")
    A("    end")
    A("end")
    with open(lib / f"{prefix}Ctrl.jl", "w", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")


# --------------------------------------------------------------------------------- scenario driver


@dataclass
class Scenario:
    """Everything a cart-pendulum example sets: plant, swing-up, controller weights, disturbance."""
    prefix: str            # block prefix, e.g. "DoubleCart" (library/<prefix>Traj.jl, <prefix>Ctrl.jl)
    model: str             # model name, e.g. "pendulum-double-cart"
    root: Path             # the example folder
    plant: Plant
    t_on: float            # s, start of the swing-up
    t_s: float             # s, swing-up duration
    k_int: int             # collocation intervals
    u_lim: float           # V, voltage bound of the optimisation
    x_lim: float           # m, cart bound of the optimisation
    dt_tab: float          # s, knot spacing of the controller tables
    t_dist: float          # s, disturbance start
    dist_dur: float        # s
    dist_amp: float        # N, force perpendicular to the tip link
    t_end: float
    Q: np.ndarray
    R: float
    free_th0: list
    free_x0: float
    free_t: float
    doc: str
    scene: str
    w_du: float = 0.02
    guess: object = None


def design(sc: Scenario, verbose=True):
    import time
    P = sc.plant
    dyn = Dynamics(P)
    t0 = time.time()
    traj = swingup(P, dyn, sc.t_s, sc.k_int, sc.u_lim, sc.x_lim, guess=sc.guess, w_du=sc.w_du, verbose=False)
    nom = Nominal(traj)
    tk = np.arange(0.0, sc.t_s + 1e-9, sc.dt_tab)
    _, Pc, _ = clqr(P, dyn, sc.Q, sc.R)
    Ks, _ = tvlqr(P, dyn, nom, sc.Q, sc.R, Pc, tk)
    Kd, _, _ = dlqr(P, dyn, sc.Q, sc.R, 1e-3)
    tab = Tables(t_on=sc.t_on, T_s=sc.t_s, tk=tk, uff=np.array([nom.u(t) for t in tk]),
                 xs=np.array([nom.z(t) for t in tk]), Ks=Ks, Klqr=Kd, u_max=P.u_max)
    if verbose:
        print(f"design time {time.time() - t0:.1f} s; swing-up |u| max {np.abs(traj['U']).max():.2f} V, "
              f"|x| max {np.abs(traj['Z'][0]).max():.3f} m; |K_lqr| {np.abs(Kd).max():.0f}")
    return dyn, traj, tab


def run_scenario(sc: Scenario, dyn, tab, amp=None, t_end=None):
    amp = sc.dist_amp if amp is None else amp
    return simulate(sc.plant, dyn, tab, sc.t_end if t_end is None else t_end, hang_state(sc.plant),
                    dist=lambda t: disturbance(t, sc.t_dist, sc.dist_dur, amp))


def free_swing(sc: Scenario, dyn, t_grid):
    """Design-model open-loop free swing (V = 0) from the check's initial pose, RK4 0.2 ms."""
    P = sc.plant
    z = np.zeros(P.nx)
    z[0] = sc.free_x0
    z[1 : 1 + P.n] = sc.free_th0
    out, tt = [], 0.0
    for tq in t_grid:
        while tt < tq - 1e-12:
            hh = min(2e-4, tq - tt)
            z = rk4(dyn, z, 0.0, 0.0, hh)
            tt += hh
        out.append(z.copy())
    return np.array(out)


def read_run(run_dir):
    """Time and signal dict of a run folder (manifest.json + columns.f64)."""
    import json
    man = json.load(open(Path(run_dir) / "manifest.json"))
    ids = [s["id"] for s in man["signals"]]
    n = man["time"]["n"]
    raw = np.fromfile(Path(run_dir) / "columns.f64", dtype="<f8").reshape(len(ids) + 1, n)
    return raw[0], {k: raw[i + 1] for i, k in enumerate(ids)}


def compare_free(sc: Scenario, dyn, run_dir):
    """Max difference between the design ODE and a bond-graph free-swing run (angles, cart)."""
    t, S = read_run(run_dir)
    P = sc.plant
    ref = free_swing(sc, dyn, t)
    th = np.cumsum(np.stack([S[f"Joint{i + 1}/qout"] for i in range(P.n)], 1), axis=1) - np.pi / 2
    dth = np.abs(th - ref[:, 1 : 1 + P.n]).max(0)
    dx = np.abs(S["Rail/qout"] - ref[:, 0]).max()
    print(f"free swing {sc.free_t:g} s: max |d th_i| = {', '.join('%.3e' % v for v in dth)} rad, "
          f"max angle difference {dth.max():.3e} rad, max |d x| = {dx:.3e} m")
    return dth.max(), dx


def write_all(sc: Scenario, tab):
    import cartmodel
    P = sc.plant
    write_controller(sc.root / "library", sc.prefix, P, tab, sc.doc)
    push = {"amplitude": sc.dist_amp, "t_start": sc.t_dist, "duration": sc.dist_dur}
    full = cartmodel.build(P, sc.prefix, t_end=sc.t_end, points=int(round(sc.t_end / 0.005)) + 1, push=push,
                           scene=sc.scene, title=sc.model)
    free = cartmodel.build(P, sc.prefix, free=True, th0=sc.free_th0, x0=sc.free_x0, t_end=sc.free_t,
                           points=int(round(sc.free_t / 0.002)) + 1, scene=sc.scene, title=sc.model + "-free")
    cartmodel.write(sc.root / "models" / f"{sc.model}.bgmodel.json", full)
    cartmodel.write(sc.root / "models" / f"{sc.model}-free.bgmodel.json", free)


def report(sc: Scenario, res):
    """Print the closed-loop numbers of the design replica."""
    P = sc.plant
    n = P.n
    t, u, ph, z = res[:, 0], res[:, 1], res[:, 2], res[:, 3:]
    t_catch = t[ph > 1.5][0]
    print(f"catch (mode 2) at t = {t_catch:.3f} s")
    sel = (t > t_catch + 0.1) & (t < sc.t_dist)
    print(f"upright band between catch and disturbance: {np.degrees(np.abs(z[sel][:, 1:1 + n]).max()):.4f} deg")
    sel = t > sc.t_dist
    print("post-disturbance max |th_i| (deg):", np.degrees(np.abs(z[sel][:, 1:1 + n]).max(0)).round(2))
    m = np.abs(z[:, 1:1 + n]).max(1)
    bad = np.where((t > sc.t_dist + 0.05) & (m > np.radians(0.5)))[0]
    print(f"recovered inside 0.5 deg at t = {t[bad[-1] + 1]:.3f} s ({t[bad[-1] + 1] - sc.t_dist:.2f} s after the pulse)")
    print(f"peak |u| {np.abs(u).max():.2f} V of {P.u_max:g} V; peak |x| {np.abs(z[:, 0]).max():.3f} m of {P.x_rail:g} m")


def main(sc: Scenario):
    dyn, traj, tab = design(sc)
    res = run_scenario(sc, dyn, tab)
    report(sc, res)
    argv = sys.argv
    if "--write" in argv:
        write_all(sc, tab)
        print("wrote library/%sTraj.jl, %sCtrl.jl and models/%s*.bgmodel.json" % (sc.prefix, sc.prefix, sc.model))
    if "--compare-free" in argv:
        compare_free(sc, dyn, argv[argv.index("--compare-free") + 1])
    return dyn, tab, res


def measure(sc: Scenario, t, S) -> dict:
    """The numbers of a bond-graph run of the full model (the README, the docs and the report quote them)."""
    P = sc.plant
    n = P.n
    th = np.stack([S[f"Ctrl/th{i + 1}"] for i in range(n)], 1)
    x, u, ph = S["Rail/qout"], S["Ctrl/u"], S["Ctrl/phase"]
    m = np.abs(th).max(1)
    out = {}
    pre = t < sc.t_on - 0.01
    out["rest_dth"] = float(np.abs(th[pre] + np.pi).max())
    out["rest_dx"] = float(np.abs(x[pre]).max())
    out["t_catch"] = float(t[np.argmax(ph > 1.5)])
    before = t < sc.t_dist
    bad = np.where(before & (t > sc.t_on) & (m > np.radians(2.0)))[0]
    out["t_swingup"] = float(t[bad[-1] + 1]) - sc.t_on          # all links inside 2 deg for good
    sel = (t > out["t_catch"] + 0.1) & before
    out["band_deg"] = float(np.degrees(m[sel].max()))
    out["band_x"] = float(np.abs(x[sel]).max())
    after = t > sc.t_dist
    out["defl_deg"] = np.degrees(np.abs(th[after]).max(0)).tolist()
    out["defl_x"] = float(np.abs(x[after]).max())
    bad = np.where((t > sc.t_dist + 0.05) & (m > np.radians(0.5)))[0]
    out["t_rec"] = float(t[bad[-1] + 1]) - sc.t_dist             # after the pulse, inside 0.5 deg for good
    bad = np.where((t > sc.t_dist + 0.05) & (m > np.radians(1.0)))[0]
    out["t_rec1"] = float(t[bad[-1] + 1]) - sc.t_dist
    out["u_peak"] = float(np.abs(u).max())
    out["u_peak_swing"] = float(np.abs(u[before]).max())
    out["x_peak"] = float(np.abs(x).max())
    out["end_deg"] = float(np.degrees(m[t > t[-1] - 1.0].max()))
    return out
