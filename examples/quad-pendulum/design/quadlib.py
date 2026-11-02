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

Realism (phase B). `realism.json` holds the non-idealities of both rigs (nominal, min, max, unit):
encoder and cable masses, smooth Coulomb friction, cable springs and dampers, sensor resolution and
noise, loop delay, current-loop lag, torque ripple and cogging. `realistic_rig` turns a parameter set
(`realism_nominal` or `sample_realism`) into a Rig for the twin; `sensor_options` (Firmware fields) and
the `tau_act` of `closed_loop` carry the sensor and loop parts into the firmware replica and the closed loop. All new
Rig fields default to the ideal rig, so the existing designs are unchanged.
"""

from __future__ import annotations

import dataclasses
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

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
    b_joint: float     # viscous friction of every pendulum joint (N m s/rad), or a list with one value per joint
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
    # ---- realism (realism.json); the defaults are the ideal rig
    c_eq: list | None = None     # COM of each link from its pivot (m); default L/2
    J_eq: list | None = None     # inertia of each link about its COM, perpendicular to it (kg m^2)
    J_ax: list | None = None     # rotary: axial inertia of each link (kg m^2)
    tc_joint: float = 0.0        # Coulomb friction of every pendulum joint (N m), tc tanh(w / eps_joint); or a list per joint
    eps_joint: float = 0.01
    tc_base: float = 0.0         # Coulomb friction of the base (N or N m)
    eps_base: float = 0.01
    k_cable: list | None = None  # spring across each pendulum joint (N m/rad), neutral at the upright
    b_cable: list | None = None  # damper across each pendulum joint (N m s/rad)
    k_cable_base: float = 0.0    # cable spring on the base (N/m or N m/rad), neutral at 0
    b_cable_base: float = 0.0
    ripple_rel: float = 0.0      # u (1 + ripple_rel sin(ripple_n th_m)) + cogging sin(cogging_n th_m)
    ripple_n: float = 0.0
    cogging: float = 0.0
    cogging_n: float = 0.0
    motor_per_base: float = 1.0  # motor angle th_m per base coordinate (rad/m or rad/rad)

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
        return list(self.c_eq) if self.c_eq is not None else [l / 2 for l in self.L]

    @property
    def J(self) -> list:
        """Rod inertia about the COM, perpendicular to the rod (kg m^2)."""
        if self.J_eq is not None:
            return list(self.J_eq)
        return [mi * li * li / 12.0 for mi, li in zip(self.m, self.L)]

    def J_trans(self, k: int) -> float:
        """Rotary: inertia of link k about its COM, perpendicular to the rod (with the rod radius)."""
        if self.J_eq is not None:
            return self.J_eq[k]
        return self.m[k] * (self.L[k] ** 2 / 12 + self.r_link**2 / 4)

    def J_axial(self, k: int) -> float:
        if self.J_ax is not None:
            return self.J_ax[k]
        return 0.5 * self.m[k] * self.r_link**2

    @property
    def hang_sign(self) -> float:
        return -1.0 if self.kind == "cart" else 1.0

    def hanging(self) -> np.ndarray:
        z = np.zeros(self.nx)
        z[1 : 1 + self.n] = self.hang_sign * math.pi
        return z

    def per_joint(self, v, k: int):
        """The value of joint k of a per-joint field that is a scalar (every joint) or a list."""
        return v[k] if isinstance(v, (list, tuple)) else v

    def upright_pe(self) -> list:
        """Potential energy of each link at the upright, measured from its hanging rest (J)."""
        out = []
        for i in range(self.n):
            h = 2.0 * (sum(self.L[:i]) + self.c[i])
            out.append(self.m[i] * G * h)
        return out


# ---------------------------------------------------------------- realism (realism.json)
REALISM_PATH = Path(__file__).resolve().with_name("realism.json")
_NEW_FIELDS = ("c_eq", "J_eq", "J_ax", "tc_joint", "eps_joint", "tc_base", "eps_base", "k_cable", "b_cable",
               "k_cable_base", "b_cable_base", "ripple_rel", "ripple_n", "cogging", "cogging_n", "motor_per_base")


def rig_key(rig: Rig) -> dict:
    """The Rig as a dict for cache keys, without the realism fields that are at their (ideal) defaults, so
    that the keys of the ideal designs do not change."""
    d = dataclasses.asdict(rig)
    defaults = {f.name: f.default for f in dataclasses.fields(Rig) if f.name in _NEW_FIELDS}
    return {k: v for k, v in d.items() if k not in defaults or v != defaults[k]}


def load_realism(path: Path = REALISM_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def realism_nominal(kind: str, path: Path = REALISM_PATH) -> dict:
    """The nominal non-ideality parameters of a rig: {name: value}."""
    return {k: v["nominal"] for k, v in load_realism(path)["rigs"][kind]["params"].items()}


def sample_realism(kind: str, rng: np.random.Generator, path: Path = REALISM_PATH) -> dict:
    """One random parameter set: uniform between min and max (integers for integer ranges)."""
    out = {}
    for k, v in load_realism(path)["rigs"][kind]["params"].items():
        lo, hi = v["min"], v["max"]
        if lo == hi:
            out[k] = v["nominal"]
        elif isinstance(lo, int) and isinstance(hi, int):
            out[k] = int(rng.integers(lo, hi + 1))
        else:
            out[k] = float(rng.uniform(lo, hi))
    return out


def realistic_rig(rig: Rig, p: dict) -> Rig:
    """The rig with the non-idealities `p` (realism.json names): link masses, lengths and centres of mass
    with the encoder boards, magnets and cables lumped into each link; base mass (cart) or hub inertia
    (arm) with the first encoder board and the cables along the arm; Coulomb friction, cable springs and
    dampers, motor ripple and cogging. Sensors and loop delays are not part of the plant (see
    `sensor_options`)."""
    n = rig.n
    L = [l * p["link_length_scale"] for l in rig.L]
    m_rod = [mi * p["link_mass_scale"] for mi in rig.m]
    mb, mm, rho = p["m_enc_board"], p["m_enc_magnet"], p["rho_cable"]
    m, c, J, Jax = [], [], [], []
    for k in range(n):
        if rig.kind == "cart":
            j_rod = m_rod[k] * L[k] ** 2 / 12
        else:
            j_rod = m_rod[k] * (L[k] ** 2 / 12 + rig.r_link**2 / 4)
        parts = [(m_rod[k], L[k] * (0.5 + p["com_shift"]), j_rod), (mm, 0.0, 0.0)]
        if k < n - 1:
            parts.append((mb, L[k], 0.0))                       # board of the joint above, at the tip
        ncab = n - 1 - k                                        # cables of the encoders above this link
        if ncab:
            mc = ncab * rho * L[k]
            parts.append((mc, L[k] / 2, mc * L[k] ** 2 / 12))
        mt = sum(a for a, _, _ in parts)
        ct = sum(a * x for a, x, _ in parts) / mt
        jt = sum(j + a * (x - ct) ** 2 for a, x, j in parts)
        m.append(mt)
        c.append(ct)
        J.append(jt)
        Jax.append(0.5 * m_rod[k] * rig.r_link**2)
    ncross = [n - 1 - k for k in range(n)]                      # cables across each pendulum joint
    kw = dict(L=L, m=m, c_eq=c, J_eq=J, b_joint=p["b_joint"], b_base=p["b_base"],
              tc_joint=p["tc_joint"], eps_joint=p["eps_joint"], tc_base=p["tc_base"], eps_base=p["eps_base"],
              k_cable=[nc * p["k_cable"] for nc in ncross], b_cable=[nc * p["b_cable"] for nc in ncross],
              k_cable_base=p["k_cable_base"], b_cable_base=p["b_cable_base"],
              ripple_rel=p["ripple_rel"], ripple_n=p["ripple_per_rev"], cogging=p["cogging"],
              cogging_n=p["cogging_per_rev"], motor_per_base=p["motor_per_base"])
    if rig.kind == "cart":
        kw["m_base"] = rig.m_base * p["base_mass_scale"] + mb
    else:
        kw["m_base"] = rig.m_base * p["base_mass_scale"]
        kw["J_ax"] = Jax
        # board of joint 1 at the arm tip, the cables of all encoders along the arm
        kw["J_hub"] = rig.J_hub + mb * rig.arm_l**2 + n * rho * rig.arm_l * rig.arm_l**2 / 3
    return dataclasses.replace(rig, **kw)


def design_rig(rig: Rig) -> Rig:
    """What a designer would model of a realistic rig: masses, inertias, viscous friction and cable springs,
    no Coulomb friction (non-smooth; left to the feedback) and no motor ripple."""
    return dataclasses.replace(rig, tc_joint=0.0, tc_base=0.0, ripple_rel=0.0, cogging=0.0)


def sensor_options(kind: str, p: dict) -> dict:
    """Firmware replica options of the sensors and the loop for the parameter set `p`."""
    return {"quant": True, "res_q": 2 * math.pi / 2 ** int(p["joint_bits"]), "noise_q": math.radians(p["joint_noise"]),
            "res_s": p["base_res"], "noise_s": (math.radians(p["base_noise"]) if kind == "rotary" else p["base_noise"]),
            "delay": int(p["delay"])}


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
        D = 0.5 * R.b_base * qd[0] ** 2 + sum(0.5 * R.per_joint(R.b_joint, k) * r**2 for k, r in enumerate(rel))
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
            pos.append(origin + r @ ca.vertcat(R.c[k], 0, 0))
            origin = origin + r @ ca.vertcat(l, 0, 0)
            if k + 1 < self.n:
                r = r @ rotz(jq[k + 2])
                rots.append(r)
        for k in range(self.n):
            jt = R.J_trans(k)
            bodies.append((R.m[k], pos[k], rots[k], (R.J_axial(k), jt, jt)))
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
        self.D = 0.5 * R.b_base * qd[0] ** 2 + sum(0.5 * R.per_joint(R.b_joint, k) * rr**2 for k, rr in enumerate(rel))
        self.tip = origin

    def _finish(self):
        q, qd, T, V = self.q, self.qd, self.T, self.V
        u = ca.SX.sym("u")
        fd = ca.SX.sym("fd")
        M = ca.hessian(T, qd)[0]
        cor = ca.jacobian(ca.gradient(T, qd), q) @ qd
        gen = ca.vertcat(self.actuator(u, q[0]), ca.SX.zeros(self.n)) - ca.gradient(self.D, qd) + self.extra_forces(q, qd)
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

    def actuator(self, u, s):
        """Force or torque the actuator applies for the command u at base coordinate s: ripple and cogging
        of the motor (realism), else u."""
        R = self.rig
        if R.ripple_rel == 0.0 and R.cogging == 0.0:
            return u
        th = R.motor_per_base * s
        return u * (1 + R.ripple_rel * ca.sin(R.ripple_n * th)) + R.cogging * ca.sin(R.cogging_n * th)

    def extra_forces(self, q, qd):
        """Generalised forces of the realism terms: smooth Coulomb friction on the base and the pendulum
        joints, cable springs (neutral at the upright) and dampers. Zero for the ideal rig."""
        R = self.rig
        out = ca.SX.zeros(self.nq)
        if R.tc_base or R.k_cable_base or R.b_cable_base:
            out[0] += -R.tc_base * ca.tanh(qd[0] / R.eps_base) - R.k_cable_base * q[0] - R.b_cable_base * qd[0]
        kc = R.k_cable or [0.0] * self.n
        bc = R.b_cable or [0.0] * self.n
        tcj = [R.per_joint(R.tc_joint, k) for k in range(self.n)]
        if any(tcj) or any(kc) or any(bc):
            relq = ca.vertcat(q[1], *[q[1 + i] - q[i] for i in range(1, self.n)])
            relw = ca.vertcat(qd[1], *[qd[1 + i] - qd[i] for i in range(1, self.n)])
            tau = ca.vertcat(*[-tcj[k] * ca.tanh(relw[k] / R.eps_joint) - kc[k] * relq[k] - bc[k] * relw[k]
                               for k in range(self.n)])
            out += ca.jacobian(relw, qd).T @ tau
        return out

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


def tvlqr(plant: Plant, traj: dict, qdiag, r: float, k_lqr, p_lqr, ts: float = TS, u_clamp: float | None = None):
    """Discrete TVLQR on the 1 kHz grid; the nominal is made consistent with the sampled model by one
    closed-loop roll-out (see pendulum-triple-rotary). Returns the 1 kHz nominal, input and gains.
    `u_clamp`: clamp the roll-out input to +-u_clamp (the actuator limit), so that the nominal is feasible."""
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
        if u_clamp is not None:
            us[k] = min(max(us[k], -u_clamp), u_clamp)
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
    # the catch is armed from tau >= t_s - catch_lead (and latches when z'Pz < catch_tol); catch_lead = 0 with
    # catch_tol = inf is the time-based catch at tau = t_s of the cart-pendulum firmwares (cartpend.py)
    catch_lead: float = 0.5
    delay: int = 0             # actuator delay in whole samples
    quant: bool = False        # encoder quantisation + difference rates
    res_s: float = 1e-5        # base encoder resolution (m or rad)
    res_q: float = 2 * math.pi / 4096 / 4   # joint encoder resolution (rad): 4096 lines, x4
    tau_f: float = 0.002       # rate filter time constant (s) when quantised
    ts: float = TS
    # the combined feed-forward v = u* + K z* per knot: the firmware computes u = v(t) - K(t) z with v and K
    # interpolated (one table less per state than u* - K (z - z*): the bond-graph run time grows with the
    # total table size). None: the separate form.
    tab_v: np.ndarray | None = None
    # realism of the sensors: white noise (rms, before the quantisation) and the rate estimator: "diff"
    # filtered backward differences (tau_f), "ekf" an extended Kalman filter on a design model (`ekf`)
    noise_q: float = 0.0       # joint angle noise (rad rms)
    noise_s: float = 0.0       # base noise (m or rad rms)
    estimator: str = "diff"
    ekf: object | None = None
    ekf_delay: int | None = None   # the delay the estimator assumes (None: delay)
    seed: int = 0
    # Coulomb friction compensation of the base: u += fc_base tanh(rate / fc_eps) (0: off)
    fc_base: float = 0.0
    fc_eps: float = 0.01


def table_row(fw: Firmware, t: float):
    nt = fw.tab_x.shape[0]
    s = min(max((t - fw.t_on) / fw.dt_tab, 0.0), nt - 1)
    i = min(int(math.floor(s)), nt - 2)
    w = s - i
    return ((1 - w) * fw.tab_x[i] + w * fw.tab_x[i + 1], (1 - w) * fw.tab_u[i] + w * fw.tab_u[i + 1],
            (1 - w) * fw.tab_k[i] + w * fw.tab_k[i + 1])


def measure(fw: Firmware, z: np.ndarray, st: dict, nq: int) -> np.ndarray:
    """What the firmware sees: the exact state, or quantised (and noisy) positions with filtered
    difference rates or the EKF estimate."""
    if not fw.quant:
        return z
    pos = z[:nq].copy()
    # the encoders measure the relative joint angles
    rel = np.concatenate([[pos[1]], np.diff(z[1:nq])])
    if fw.noise_q or fw.noise_s:
        rng = st.setdefault("rng", np.random.default_rng(fw.seed))
        pos[0] += fw.noise_s * rng.standard_normal()
        rel = rel + fw.noise_q * rng.standard_normal(nq - 1)
    pos[0] = fw.res_s * np.round(pos[0] / fw.res_s)
    rel = fw.res_q * np.round(rel / fw.res_q)
    pos[1:] = np.cumsum(rel)
    if fw.estimator == "ekf":
        line = st.get("line")
        d = fw.delay if fw.ekf_delay is None else fw.ekf_delay
        u_prev = line[d] if line is not None else 0.0
        return fw.ekf.update(st, np.concatenate([[pos[0]], rel]), u_prev)
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
    if st.get("latched", 0) < 0.5 and t >= fw.t_on and tau >= fw.t_s - fw.catch_lead and v < fw.catch_tol:
        st["latched"] = 1
        st["t_catch"] = t
    if st.get("latched", 0) > 0.5:
        st["phase"] = 2
        cmd = -float(fw.k_lqr @ x)
    elif t >= fw.t_on:
        st["phase"] = 1
        xr, ur, k = table_row(fw, t)
        if fw.tab_v is not None:
            nt = fw.tab_v.shape[0]
            s = min(max(tau / fw.dt_tab, 0.0), nt - 1)
            i = min(int(math.floor(s)), nt - 2)
            w = s - i
            cmd = (1 - w) * fw.tab_v[i] + w * fw.tab_v[i + 1] - float(k @ x)
        else:
            cmd = ur - float(k @ (x - xr))
    else:
        st["phase"] = 0
        cmd = 0.0
    if fw.fc_base and st["phase"] > 0:
        # Coulomb friction compensation on the base from the measured (estimated) base rate
        cmd += fw.fc_base * math.tanh(x[nq] / fw.fc_eps)
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


class EKF:
    """Extended Kalman filter of the firmware option `estimator="ekf"`: the sampled design model (RK4) for
    the prediction with the command the firmware applied one sample earlier (its own delay line), the
    measured base coordinate and relative joint angles (linear in the state) for the update. Process noise
    as random accelerations (q_acc: base, links), measurement noise from the encoder resolution and noise."""

    def __init__(self, plant: "Plant", q_acc, r_meas, ts: float = TS):
        self.step, self.jac = plant.steps(ts)
        nq, nx = plant.nq, plant.nx
        self.nq, self.nx = nq, nx
        h = np.zeros((nq, nx))
        h[0, 0] = 1.0
        h[1, 1] = 1.0
        for k in range(2, nq):
            h[k, k] = 1.0
            h[k, k - 1] = -1.0
        self.H = h
        qv = np.array([q_acc[0]] + [q_acc[1]] * (nq - 1)) * ts
        self.Q = np.diag(np.concatenate([(0.5 * qv * ts) ** 2, qv**2]))
        self.R = np.diag(r_meas)

    def update(self, st: dict, y: np.ndarray, u_prev: float) -> np.ndarray:
        if "xh" not in st:
            xh = np.zeros(self.nx)
            xh[: self.nq] = np.concatenate([[y[0]], np.cumsum(y[1:])])
            p = np.diag(np.concatenate([np.diag(self.R), np.full(self.nq, 1e-2)]))
        else:
            x0, p = st["xh"], st["P"]
            xh = np.array(self.step(x0, u_prev, 0.0)).ravel()
            a = np.array(self.jac(x0, u_prev, 0.0)[0])
            p = a @ p @ a.T + self.Q
        h = self.H
        s_ = h @ p @ h.T + self.R
        k = np.linalg.solve(s_, h @ p).T
        xh = xh + k @ (y - h @ xh)
        p = p - k @ h @ p
        st["xh"], st["P"] = xh, 0.5 * (p + p.T)
        return xh


def closed_loop(step, fw: Firmware, x0, t_end: float, force=None, tau_act: float = 0.0):
    """Sampled closed loop: firmware tick, zero-order hold, `step` (RK4) over each sample. `tau_act`: a
    first-order current loop after the firmware's delay; the plant sees its mean over each sample."""
    n = int(round(t_end / fw.ts))
    x = np.array(x0, float)
    st = {"phase": 0}
    ts = np.arange(n + 1) * fw.ts
    xs = np.full((n + 1, len(x)), np.nan)
    us = np.zeros(n + 1)
    ph = np.zeros(n + 1)
    xs[0] = x
    uf = 0.0
    if tau_act > 0:
        ea = math.exp(-fw.ts / tau_act)
        wa = 1.0 - tau_act / fw.ts * (1.0 - ea)
    for i in range(n):
        u = tick(fw, ts[i], x, st)
        if tau_act > 0:
            u, uf = uf + (u - uf) * wa, u + (uf - u) * ea
        us[i] = u
        ph[i] = st["phase"]
        x = np.array(step(x, u, force(ts[i] + 0.5 * fw.ts) if force else 0.0)).ravel()
        if not np.all(np.isfinite(x)) or np.max(np.abs(x[len(x) // 2:])) > 1e3:
            break
        xs[i + 1] = x
    us[n] = us[n - 1]
    ph[n] = ph[n - 1]
    return ts, xs, us, ph, st


# ----------------------------------------------------------------------------- realistic twin + replica
# One parameter set of realism.json -> the truth twin and the firmware-replica options. Shared by the
# feasibility screen (screen.py), multi-model designs and the RL domain randomisation.
EFFECTS = ("mass", "fbase", "fjoint", "cable", "sensor", "loop", "ripple")
# EKF process noise (random accelerations: base, links) covering the unmodelled Coulomb friction, ripple
# and model errors; per rig (the cart value is the screen's tuning)
EKF_Q = {"cart": (1.0, 10.0), "rotary": (15.0, 60.0)}


def effects_only(rig: Rig, p: dict, effects=EFFECTS) -> dict:
    """`p` with the effects not in `effects` switched back to the ideal rig `rig` (mass: link and base
    masses, encoders, cables; fbase/fjoint: base/joint friction; cable: cable springs; ripple: ripple and
    cogging; sensor and loop act on the firmware options, see `realistic_setup`)."""
    q = dict(p)
    on = set(effects)
    if "mass" not in on:
        q |= {"link_mass_scale": 1.0, "link_length_scale": 1.0, "com_shift": 0.0, "base_mass_scale": 1.0,
              "m_enc_board": 0.0, "m_enc_magnet": 0.0, "rho_cable": 0.0}
    if "fbase" not in on:
        q |= {"tc_base": 0.0, "b_base": rig.b_base}
    if "fjoint" not in on:
        q |= {"tc_joint": 0.0, "b_joint": rig.b_joint}
    if "cable" not in on:
        q |= {"k_cable": 0.0, "b_cable": 0.0, "k_cable_base": 0.0, "b_cable_base": 0.0}
    if "ripple" not in on:
        q |= {"ripple_rel": 0.0, "cogging": 0.0}
    return q


def firmware_from_design(dz: dict, **kw) -> Firmware:
    """The firmware replica of a design file (`design_<variant>.json`), with options `kw` (sensors, loop,
    estimator, compensation) over the design's own encoder settings."""
    tab_v = np.array(dz["tab_v"]) if dz.get("tab_v") is not None else None
    kw = {"res_s": dz["res_s"], "res_q": dz["res_q"], "tau_f": dz["tau_f"]} | kw
    return Firmware(t_on=dz["t_on"], t_s=dz["t_s"], dt_tab=dz["dt_tab"], tab_x=np.array(dz["tab_x"]),
                    tab_u=np.array(dz["tab_u"]), tab_k=np.array(dz["tab_k"]), tab_v=tab_v,
                    k_lqr=np.array(dz["k_lqr"]), p_catch=np.array(dz["p_lqr"]), catch_tol=dz["catch_tol"],
                    u_max=dz["u_max"], slew=dz["slew"], **kw)


def rest_state(plant: Plant) -> np.ndarray:
    """The hanging rest of a (realistic) twin: the cable springs move it slightly off the straight hang.
    Solved for the link angles with the base at 0 (the cart has no restoring force)."""
    from scipy.optimize import fsolve
    z0 = plant.rig.hanging()
    nq = plant.nq

    def acc(a):
        z = np.concatenate([[0.0], a, np.zeros(nq)])
        return plant.rhs(z, 0.0)[nq + 1:]

    a, info, ier, msg = fsolve(acc, z0[1:nq], xtol=1e-13, full_output=True)
    if ier != 1 or np.max(np.abs(a - z0[1:nq])) > 0.2:
        raise RuntimeError(f"rest state: {msg}")
    return np.concatenate([[0.0], a, np.zeros(nq)])


@dataclass
class Realistic:
    """The truth twin and the firmware-replica options of one realism parameter set."""
    p: dict              # the parameter set with the switched-off effects at their ideal values
    truth: Rig           # the realistic rig
    plant: Plant         # its twin
    step: object         # RK4 sample step of the twin (sub substeps)
    fw_kw: dict          # Firmware options: sensors, delay, estimator (with the EKF), compensation, seed
    tau_act: float       # current-loop time constant for closed_loop


def realistic_setup(rig: Rig, p: dict, effects=EFFECTS, estimator: str = "diff", ekf_q=None, comp: float = 0.0,
                    seed: int = 0, sub: int = 8, make_plant=None, make_ekf=None) -> Realistic:
    """The truth twin and the firmware replica of the ideal rig `rig` with the realism parameters `p` (a
    `realism_nominal` or `sample_realism` dict), effects `effects` on.

    - sensor: quantised, noisy encoders (`sensor_options`); off: exact positions (the EKF still gets them
      through its measurement update);
    - loop: the whole-sample delay and the current loop (`tau_act`);
    - estimator "diff" (filtered differences, the design's tau_f) or "ekf": an EKF on the observer model,
      the nominal realistic rig with its Coulomb friction (calibrated) and without ripple, process noise
      `ekf_q` (default EKF_Q), measurement noise from the encoder resolution and noise;
    - comp: base Coulomb compensation, the fraction `comp` of the nominal tc_base.

    The firmware's own model knowledge (observer rig, EKF delay, compensation) is the nominal parameter
    set; only the truth follows `p`.

    `make_plant(rig) -> (plant, step)` and `make_ekf(observer_rig, q_acc, r_meas) -> EKF` let a caller cache
    the CasADi builds (default: build fresh). Use with `firmware_from_design(dz, **setup.fw_kw)` and
    `closed_loop(setup.step, fw, x0, t_end, tau_act=setup.tau_act)`."""
    kind = rig.kind
    q = effects_only(rig, p, effects)
    truth = realistic_rig(rig, q)
    if make_plant is None:
        plant = Plant(truth)
        step = plant.steps(sub=sub)[0]
    else:
        plant, step = make_plant(truth)
    on = set(effects)
    kw = {}
    if "sensor" in on:
        so = sensor_options(kind, q)
        kw |= {k: so[k] for k in ("quant", "res_q", "noise_q", "res_s", "noise_s")}
    elif estimator == "ekf":
        kw |= {"quant": True, "res_q": 1e-12, "res_s": 1e-12}     # exact positions through the estimator
    if "loop" in on:
        kw["delay"] = int(q["delay"])
    if estimator == "ekf":
        obs = dataclasses.replace(realistic_rig(rig, realism_nominal(kind)), ripple_rel=0.0, cogging=0.0)
        res_q, res_s = kw.get("res_q", 1e-9), kw.get("res_s", 1e-9)
        r_meas = tuple([max(res_s**2 / 12 + kw.get("noise_s", 0.0) ** 2, 1e-12)]
                       + [max(res_q**2 / 12 + kw.get("noise_q", 0.0) ** 2, 1e-12)] * rig.n)
        q_acc = tuple(ekf_q or EKF_Q[kind])
        kw["estimator"] = "ekf"
        kw["ekf"] = EKF(Plant(obs), q_acc, r_meas) if make_ekf is None else make_ekf(obs, q_acc, r_meas)
        kw["ekf_delay"] = int(realism_nominal(kind)["delay"]) if "loop" in on else 0   # designed for the nominal delay
    kw["seed"] = int(seed)
    if comp:
        nom = realism_nominal(kind)
        kw["fc_base"] = comp * nom["tc_base"]
        kw["fc_eps"] = 2.0 * nom["eps_base"]
    return Realistic(p=q, truth=truth, plant=plant, step=step, fw_kw=kw,
                     tau_act=q["tau_current"] if "loop" in on else 0.0)


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
