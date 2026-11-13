"""Design model of `pendulum-triple-rotary-flex`: the rotary triple pendulum on a flexible arm.

The rigid model of `triple_lib.Plant` with the arm replaced by a uniform Euler-Bernoulli beam,
discretised by the same assumed modes as the bond graph's `FlexibleBeam3D` (clamped-free basis at
the hub, `src/mech/modes.jl`): `ny` bending modes along the arm's local y (horizontal, the plane of
the motor torque), `nz` along local z (vertical) and `nt` torsion modes about the arm axis.

Generalised coordinates, in this order::

    q[0]            arm (hub) angle about world z         J1/qout
    q[1 .. 3]       link angles, as in the rigid model    L2/J/qout .. L4/J/qout (relative to the arm TIP frame)
    eta_y[1..ny]    horizontal bending, m                 Arm/eta_y[k]
    eta_z[1..nz]    vertical bending, m                   Arm/eta_z[k]
    eta_t[1..nt]    torsion, rad                          Arm/eta_t[k]

The pendulum encoders measure the link angle relative to the arm's tip frame, which turns with the
tip slopes and the tip twist; that is what `q[1]` is here and in the bond graph. Arm kinetic energy
(rotating frame of the hub, r(s) = (s, w_y, w_z), axial foreshortening neglected):

    T_arm = 1/2 rho A int |w x r + r'|^2 ds + 1/2 rho I_z L q0'^2 + 1/2 rho I_p L sum eta_t'^2

with the modal integrals (1/L) int phi_i phi_j = delta_ij, (1/L^2) int s phi_i = tb_i. Strain energy
1/2 k_i eta_i^2 with k = lambda^4 E I / L^3 (bending) and (k pi)^2 G J_t / L (torsion); modal damping
2 zeta omega m. The tip frame is R0 Rz(w_y'(L)) Ry(-w_z'(L)) Rx(theta(L)) at (L, w_y(L), w_z(L)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import casadi as ca
import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

import triple_lib as tl

LAMBDA_CF = (1.87510407, 4.69409113, 7.85475744)


def phi(n: int, xi):
    """Clamped-free bending shape n (1-based) at xi = s/L (numpy)."""
    l = LAMBDA_CF[n - 1]
    s = (math.sinh(l) - math.sin(l)) / (math.cosh(l) + math.cos(l))
    x = l * np.asarray(xi, float)
    return np.cosh(x) - np.cos(x) - s * (np.sinh(x) - np.sin(x))


def dphi(n: int, xi):
    """d phi / d xi."""
    l = LAMBDA_CF[n - 1]
    s = (math.sinh(l) - math.sin(l)) / (math.cosh(l) + math.cos(l))
    x = l * np.asarray(xi, float)
    return l * (np.sinh(x) + np.sin(x) - s * (np.cosh(x) - np.cos(x)))


def psi(n: int, xi):
    """Clamped-free torsion shape."""
    return math.sqrt(2.0) * np.sin((2 * n - 1) * math.pi / 2 * np.asarray(xi, float))


@dataclass
class Beam:
    """A uniform rectangular bar: b along local y (horizontal), h along local z (vertical)."""

    L: float
    b: float
    h: float
    E: float
    rho: float
    nu: float
    zeta: float = 0.01
    ny: int = 2
    nz: int = 2
    nt: int = 1

    @property
    def A(self) -> float:
        return self.b * self.h

    @property
    def m(self) -> float:
        return self.rho * self.A * self.L

    @property
    def Iz(self) -> float:  # int y^2 dA: bending along y (horizontal)
        return self.h * self.b**3 / 12.0

    @property
    def Iy(self) -> float:  # int z^2 dA: bending along z (vertical)
        return self.b * self.h**3 / 12.0

    @property
    def Ip(self) -> float:
        return self.Iy + self.Iz

    @property
    def G(self) -> float:
        return self.E / (2.0 * (1.0 + self.nu))

    @property
    def Jt(self) -> float:
        """Roark's torsion constant of a rectangle, as in ModalBeam3D."""
        a, c = max(self.b, self.h), min(self.b, self.h)
        return a * c**3 * (1.0 / 3.0 - 0.21 * c / a * (1.0 - c**4 / (12.0 * a**4)))

    def f_bending(self, n: int, horizontal: bool) -> float:
        """Free clamped-free eigenfrequency (Hz) of the bare beam, mode n."""
        i = self.Iz if horizontal else self.Iy
        return LAMBDA_CF[n - 1] ** 2 * math.sqrt(self.E * i / (self.rho * self.A * self.L**4)) / (2 * math.pi)

    def f_torsion(self, n: int) -> float:
        k = (2 * n - 1) / 2
        return k * math.pi / self.L * math.sqrt(self.G * self.Jt / (self.rho * self.Ip)) / (2 * math.pi)

    def modal(self):
        """Per-mode constants: ta = int phi / L, tb = int s phi / L^2, pL = phi(L), sL = L phi'(L), qL = psi(L)."""
        out = {}
        for n in (1, 2, 3):
            out[n] = {
                "ta": quad(lambda x: float(phi(n, x)), 0, 1, epsabs=1e-13)[0],
                "tb": quad(lambda x: x * float(phi(n, x)), 0, 1, epsabs=1e-13)[0],
                "pL": float(phi(n, 1.0)),
                "sL": float(dphi(n, 1.0)),
                "qL": float(psi(n, 1.0)),
            }
        return out


def rotx(a):
    c, s = ca.cos(a), ca.sin(a)
    return ca.vertcat(ca.horzcat(1, 0, 0), ca.horzcat(0, c, -s), ca.horzcat(0, s, c))


def roty(a):
    c, s = ca.cos(a), ca.sin(a)
    return ca.vertcat(ca.horzcat(c, 0, s), ca.horzcat(0, 1, 0), ca.horzcat(-s, 0, c))


class FlexPlant:
    """The Lagrangian model of the rotary arm as a flexible beam with an N-link chain at its tip."""

    def __init__(self, rigid: tl.Plant, beam: Beam):
        self.rigid = rigid
        self.beam = beam
        self.n_links = rigid.n_links
        self.nr = rigid.nq  # rigid coordinates (hub + links)
        self.ne = beam.ny + beam.nz + beam.nt
        self.nq = self.nr + self.ne
        self.nx = 2 * self.nq
        self._build()

    def _build(self) -> None:
        rp, bm = self.rigid, self.beam
        md = bm.modal()
        n, nr = self.nq, self.nr
        q = ca.SX.sym("q", n)
        qd = ca.SX.sym("qd", n)
        v = ca.SX.sym("v")
        ey = q[nr: nr + bm.ny]
        ez = q[nr + bm.ny: nr + bm.ny + bm.nz]
        et = q[nr + bm.ny + bm.nz:]
        eyd = qd[nr: nr + bm.ny]
        ezd = qd[nr + bm.ny: nr + bm.ny + bm.nz]
        etd = qd[nr + bm.ny + bm.nz:]
        L, m = bm.L, bm.m
        r0 = tl.rotz(q[0])
        # tip deflection, slopes and twist
        wy = sum(md[k + 1]["pL"] * ey[k] for k in range(bm.ny)) if bm.ny else 0
        wz = sum(md[k + 1]["pL"] * ez[k] for k in range(bm.nz)) if bm.nz else 0
        sy = sum(md[k + 1]["sL"] / L * ey[k] for k in range(bm.ny)) if bm.ny else 0
        sz = sum(md[k + 1]["sL"] / L * ez[k] for k in range(bm.nz)) if bm.nz else 0
        th = sum(md[k + 1]["qL"] * et[k] for k in range(bm.nt)) if bm.nt else 0
        # arm kinetic energy (closed-form modal integrals)
        q0d = qd[0]
        kin = 0.5 * rp.drive.jrot * q0d**2
        kin += 0.5 * (m * L**2 / 3.0 + bm.rho * bm.Iz * L) * q0d**2
        kin += 0.5 * m * q0d**2 * ca.sumsqr(ey)
        kin += q0d * m * L * sum(md[k + 1]["tb"] * eyd[k] for k in range(bm.ny)) if bm.ny else 0
        kin += 0.5 * m * (ca.sumsqr(eyd) + ca.sumsqr(ezd))
        kin += 0.5 * bm.rho * bm.Ip * L * ca.sumsqr(etd)
        # arm potential: strain and its own weight
        pot = 0
        stiff = []
        damp = []
        for k in range(bm.ny):
            kk = LAMBDA_CF[k] ** 4 * bm.E * bm.Iz / L**3
            stiff.append(kk)
            damp.append(2 * bm.zeta * math.sqrt(kk * m))
        for k in range(bm.nz):
            kk = LAMBDA_CF[k] ** 4 * bm.E * bm.Iy / L**3
            stiff.append(kk)
            damp.append(2 * bm.zeta * math.sqrt(kk * m))
        mt = bm.rho * bm.Ip * L
        for k in range(bm.nt):
            kk = ((2 * k + 1) / 2 * math.pi) ** 2 * bm.G * bm.Jt / L
            stiff.append(kk)
            damp.append(2 * bm.zeta * math.sqrt(kk * mt))
        eta = q[nr:]
        etad = qd[nr:]
        pot += 0.5 * sum(stiff[i] * eta[i] ** 2 for i in range(self.ne))
        pot += m * tl.G * sum(md[k + 1]["ta"] * ez[k] for k in range(bm.nz)) if bm.nz else 0
        self.stiff = np.array(stiff)
        self.damp = np.array(damp)
        # tip frame and the chain (the rigid model's kinematics from the joint-2 frame on)
        tip = r0 @ ca.vertcat(L, wy, wz)
        rtip = r0 @ tl.rotz(sy) @ roty(-sz) @ rotx(th)
        r = rtip @ ca.DM(tl.RJF) @ tl.rotz(q[1])
        origin = tip
        rots, pos = [], []
        rots.append(r)
        for k in range(self.n_links):
            l = rp.lengths[k]
            pos.append(origin + r @ ca.vertcat(l / 2, 0, 0))
            origin = origin + r @ ca.vertcat(l, 0, 0)
            if k + 1 < self.n_links:
                r = r @ tl.rotz(q[k + 2])
                rots.append(r)
        for mk, p, rot, j in zip(rp.masses, pos, rots, rp.body_j[1:], strict=True):
            vel = ca.jtimes(p, q, qd)
            rd = ca.reshape(ca.jtimes(ca.vec(rot), q, qd), 3, 3)
            om = rot.T @ rd
            w = ca.vertcat(om[2, 1], om[0, 2], om[1, 0])
            kin += 0.5 * mk * ca.dot(vel, vel) + 0.5 * (j[0] * w[0] ** 2 + j[1] * w[1] ** 2 + j[2] * w[2] ** 2)
            pot += mk * tl.G * p[2]
        mass = ca.hessian(kin, qd)[0]
        coriolis = ca.jacobian(ca.gradient(kin, qd), q) @ qd
        gen = ca.vertcat(rp.drive.a * v - rp.drive.c * qd[0], -rp.jfric * qd[1:nr], -ca.DM(self.damp) * etad)
        rhs = ca.gradient(kin, q) - coriolis - ca.gradient(pot, q) + gen
        self.mass_fn = ca.Function("M", [q], [mass])
        self.rhs_fn = ca.Function("rhs", [q, qd, v], [rhs])
        self.pot_fn = ca.Function("U", [q], [pot])
        self.grad_pot = ca.Function("dU", [q], [ca.gradient(pot, q)])
        # a force on the tip of the last link along its body y axis (as triple_lib.Plant.qforce)
        ydir = r @ ca.vertcat(0, 1, 0)
        qforce = ca.jacobian(origin, q).T @ ydir
        x = ca.vertcat(q, qd)
        fz = ca.SX.sym("fz")
        xdot_f = ca.vertcat(qd, ca.solve(mass, rhs + qforce * fz))
        self.f_force = ca.Function("ff", [x, v, fz], [xdot_f])
        xdot = ca.substitute(xdot_f, fz, 0)
        self.f = ca.Function("f", [x, v], [xdot])
        self.lin_fn = ca.Function("lin", [x, v], [ca.jacobian(xdot, x), ca.jacobian(xdot, v)])
        self.tip_fn = ca.Function("tip", [q], [ca.vertcat(wy, wz, sy, sz, th)])

    def steps(self, ts: float = tl.TS, sub: int = 4):
        """The sampled model (RK4, `sub` steps per sample, zero-order hold): x+ = F(x, u, fz)."""
        x = ca.SX.sym("x", self.nx)
        v = ca.SX.sym("v")
        fz = ca.SX.sym("fz")
        h = ts / sub
        xx = x
        for _ in range(sub):
            k1 = self.f_force(xx, v, fz)
            k2 = self.f_force(xx + 0.5 * h * k1, v, fz)
            k3 = self.f_force(xx + 0.5 * h * k2, v, fz)
            k4 = self.f_force(xx + h * k3, v, fz)
            xx = xx + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        return ca.Function("step", [x, v, fz], [xx]).expand()

    def hanging(self) -> np.ndarray:
        """At rest, hanging, in the static gravity sag."""
        q = self.equilibrium([0.0, math.pi] + [0.0] * (self.n_links - 1))
        return np.concatenate([q, np.zeros(self.nq)])

    # ------------------------------------------------------------------ equilibria and linear models
    def equilibrium(self, rigid_q) -> np.ndarray:
        """The static deflection under gravity with the rigid coordinates held at `rigid_q`."""
        q = np.zeros(self.nq)
        q[: self.nr] = rigid_q
        for _ in range(30 if self.ne else 0):
            g = np.array(self.grad_pot(q)).ravel()[self.nr:]
            # Newton on the elastic coordinates with the numerical Hessian of U
            eps = 1e-9
            hess = np.zeros((self.ne, self.ne))
            for i in range(self.ne):
                dq = q.copy()
                dq[self.nr + i] += eps
                hess[:, i] = (np.array(self.grad_pot(dq)).ravel()[self.nr:] - g) / eps
            step = np.linalg.solve(hess, g)
            q[self.nr:] -= step
            if np.max(np.abs(step)) < 1e-14:
                break
        return q

    def linear(self, rigid_q=None, v: float = 0.0):
        """(A, B) at the gravity equilibrium with the rigid coordinates at `rigid_q` (default upright)."""
        rq = np.zeros(self.nr) if rigid_q is None else np.asarray(rigid_q, float)
        q = self.equilibrium(rq)
        x = np.concatenate([q, np.zeros(self.nq)])
        a, b = (np.array(m) for m in self.lin_fn(x, v))
        return a, b, x

    def measured(self) -> np.ndarray:
        """C: the firmware's measurement x_rigid = [q0..q3, q0'..q3'] from the full state."""
        c = np.zeros((2 * self.nr, self.nx))
        for i in range(self.nr):
            c[i, i] = 1.0
            c[self.nr + i, self.nq + i] = 1.0
        return c


def discretise(a, b, ts: float = tl.TS):
    n = a.shape[0]
    mm = expm(np.block([[a, b], [np.zeros((b.shape[1], n + b.shape[1]))]]) * ts)
    return mm[:n, :n], mm[:n, n:]


def closed_loop_poles(fp: FlexPlant, k_rigid, ts: float = tl.TS, notch=None):
    """Equivalent continuous poles of the sampled loop u = -K x_rigid on the flexible plant (upright).

    `notch` = (w0, zeta_num, zeta_den): a discrete notch filter (Tustin, prewarped) on the voltage."""
    a, b, _ = fp.linear()
    ad, bd = discretise(a, b, ts)
    c = fp.measured()
    k = np.asarray(k_rigid, float).reshape(1, -1) @ c
    if notch is None:
        acl = ad - bd @ k
    else:
        fa, fb, fc, fd = notch_ss(*notch, ts)
        n = ad.shape[0]
        nf = fa.shape[0]
        # filter input r = -K x, output u = fc z + fd r; z+ = fa z + fb r
        acl = np.block([[ad - bd @ (fd * k), bd @ fc], [-fb @ k, fa]])
        assert acl.shape == (n + nf, n + nf)
    z = np.linalg.eigvals(acl)
    return np.log(z.astype(complex)) / ts, z


def notch_ss(w0: float, zn: float, zd: float, ts: float):
    """Discrete state space (A, B, C, D) of the notch (s^2 + 2 zn w0 s + w0^2)/(s^2 + 2 zd w0 s + w0^2),
    Tustin with prewarping at w0."""
    c = w0 / math.tan(w0 * ts / 2)
    # bilinear: s = c (z - 1)/(z + 1)
    def poly(z2):
        # s^2 + 2 z2 w0 s + w0^2 -> coefficients in z^2, z, 1
        return np.array([c * c + 2 * z2 * w0 * c + w0 * w0, -2 * c * c + 2 * w0 * w0, c * c - 2 * z2 * w0 * c + w0 * w0])
    num, den = poly(zn), poly(zd)
    num, den = num / den[0], den / den[0]
    # controllable canonical form of (b0 z^2 + b1 z + b2)/(z^2 + a1 z + a2)
    b0, b1, b2 = num
    _, a1, a2 = den
    fa = np.array([[-a1, -a2], [1.0, 0.0]])
    fb = np.array([[1.0], [0.0]])
    fc = np.array([[b1 - b0 * a1, b2 - b0 * a2]])
    fd = b0
    return fa, fb, fc, fd


@dataclass
class ChainTip:
    """The pendulum assembly seen from the arm tip, hanging or upright (the rigid model's chain)."""

    mass: float
    com: float  # distance of the centre of mass from the tip along the chain, m
    j_tip_perp: float  # inertia about the tip, axis perpendicular to the chain and to the arm (kg m^2)
    j_tip_axial: float  # inertia about the chain's own line through the tip (vertical axis), kg m^2
    extra: dict = field(default_factory=dict)


def chain_tip(rigid: tl.Plant) -> ChainTip:
    m_tot = sum(rigid.masses)
    s0 = 0.0
    first = 0.0
    j_perp = 0.0
    j_ax = 0.0
    for m, l, j in zip(rigid.masses, rigid.lengths, rigid.body_j[1:], strict=True):
        c = s0 + l / 2
        first += m * c
        j_perp += j[1] + m * c * c
        j_ax += j[0]
        s0 += l
    return ChainTip(m_tot, first / m_tot, j_perp, j_ax)


# ---------------------------------------------------------------- analytic arm frequencies
def chain_impedance(rigid: tl.Plant):
    """The hanging chain seen from a pivot that translates sideways (along the arm's local y).

    Returns (m_yy, b, M_qq, K_qq): the kinetic energy of the chain with the pivot coordinate y is
    1/2 [y' q'] [[m_yy, b^T], [b, M_qq]] [y'; q'] and its gravity stiffness about hanging K_qq, so the
    force the pivot needs for a harmonic motion y e^{i w t} is -w^2 M_eff(w) y with
    M_eff(w) = m_yy + w^2 b^T (K_qq - w^2 M_qq)^-1 b (Lagrange; the hinge is free about the arm axis)."""
    n = rigid.n_links
    z = ca.SX.sym("z", 1 + n)
    zd = ca.SX.sym("zd", 1 + n)
    origin = ca.vertcat(0, z[0], 0)
    r = ca.DM(tl.RJF) @ tl.rotz(z[1])
    kin = 0
    pot = 0
    for k in range(n):
        l = rigid.lengths[k]
        p = origin + r @ ca.vertcat(l / 2, 0, 0)
        vel = ca.jtimes(p, z, zd)
        rd = ca.reshape(ca.jtimes(ca.vec(r), z, zd), 3, 3)
        om = r.T @ rd
        j = rigid.body_j[k + 1]
        kin += 0.5 * rigid.masses[k] * ca.dot(vel, vel) + 0.5 * (j[0] * om[2, 1] ** 2 + j[1] * om[0, 2] ** 2 + j[2] * om[1, 0] ** 2)
        pot += rigid.masses[k] * tl.G * p[2]
        origin = origin + r @ ca.vertcat(l, 0, 0)
        if k + 1 < n:
            r = r @ tl.rotz(z[k + 2])
    z0 = np.array([0.0, math.pi] + [0.0] * (n - 1))
    mm = np.array(ca.Function("m", [z], [ca.hessian(kin, zd)[0]])(z0))
    kk = np.array(ca.Function("k", [z], [ca.hessian(pot, z)[0]])(z0))
    return float(mm[0, 0]), mm[1:, 0], mm[1:, 1:], kk[1:, 1:]


def m_eff(imp, w: float) -> float:
    m_yy, b, mq, kq = imp
    return m_yy + w * w * float(b @ np.linalg.solve(kq - w * w * mq, b))


def cantilever_det(w: float, EI: float, rhoA: float, L: float, tip_mass, j_tip: float, k_rot: float = 0.0) -> float:
    """Frequency determinant of a clamped Euler-Bernoulli beam with a tip body at s = L.

    w(s) = C1 (cosh bs - cos bs) + C2 (sinh bs - sin bs), b^4 = rhoA w^2 / EI; at the tip
    EI w'' = (J w^2 - k_rot) w' (rotary inertia, a rotational spring) and EI w''' = -M(w) w^2 w
    (`tip_mass(w)` may depend on the frequency)."""
    beta = (rhoA * w * w / EI) ** 0.25
    lam = beta * L
    ch, sh, c, s = math.cosh(lam), math.sinh(lam), math.cos(lam), math.sin(lam)
    m = tip_mass(w) if callable(tip_mass) else tip_mass
    jr = j_tip * w * w - k_rot
    # rows: moment and shear conditions, columns C1, C2
    a11 = EI * beta**2 * (ch + c) - jr * beta * (sh + s)
    a12 = EI * beta**2 * (sh + s) - jr * beta * (ch - c)
    a21 = EI * beta**3 * (sh - s) + m * w * w * (ch - c)
    a22 = EI * beta**3 * (ch + c) + m * w * w * (sh - s)
    return (a11 * a22 - a12 * a21) / (EI * EI * beta**5)


def first_root(fun, w_lo: float, w_hi: float, n: int = 4000) -> float:
    """The lowest sign change of `fun` on (w_lo, w_hi), refined by brentq."""
    from scipy.optimize import brentq

    ws = np.linspace(w_lo, w_hi, n)
    vals = [fun(w) for w in ws]
    for i in range(n - 1):
        if np.sign(vals[i]) != np.sign(vals[i + 1]) and np.isfinite(vals[i]) and np.isfinite(vals[i + 1]):
            # skip the poles of a frequency-dependent tip mass (a sign change through infinity)
            if abs(vals[i]) > 1e6 * (abs(vals[0]) + 1) or abs(vals[i + 1]) > 1e6 * (abs(vals[0]) + 1):
                continue
            root = brentq(fun, ws[i], ws[i + 1], xtol=1e-12)
            if abs(fun(root)) < 1e-6 * max(abs(vals[i]), abs(vals[i + 1]), 1e-30) + 1e-9:
                return root
    raise ValueError("no root found")


def clamped_hub_frequencies(fp: FlexPlant, rigid_q) -> tuple[np.ndarray, np.ndarray]:
    """Undamped eigenfrequencies (Hz) and mode vectors of the linearised flexible plant about the
    gravity equilibrium at `rigid_q`, with the hub angle q0 held (clamped arm root)."""
    q = fp.equilibrium(rigid_q)
    qs = ca.SX.sym("q", fp.nq)
    zero = np.zeros(fp.nq)
    mass = np.array(fp.mass_fn(q))
    stiff = -np.array(ca.Function("dk", [qs], [ca.jacobian(fp.rhs_fn(qs, ca.DM(zero), 0.0), qs)])(q))
    keep = list(range(1, fp.nq))
    m, k = mass[np.ix_(keep, keep)], stiff[np.ix_(keep, keep)]
    from scipy.linalg import eig

    ev, vec = eig(k, m)
    order = np.argsort(ev.real)
    w2 = ev.real[order]
    return np.sqrt(np.maximum(w2, 0.0)) / (2 * math.pi), vec[:, order].real
