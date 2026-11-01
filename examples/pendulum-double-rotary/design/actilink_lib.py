"""Design code of the ACTILINK-JD rotary double pendulum (models `actilink-*` of pendulum-double-rotary).

A Synapticon ACTILINK-JD actuator (vertical axis) turns a 0.3 m horizontal arm; at its tip a passive
joint carries pendulum link 1 (0.6 m), and link 2 (0.6 m) hangs on a passive joint at the tip of
link 1, offset 40 mm outward along the joint axis so that both links can turn through. The passive
joints are measured by AS5048 14-bit magnetic encoders.

Coordinates (exactly the bond graph's `Revolute3D.qout`):

    q[0]  arm angle about the world z axis (output side of the gear)
    q[1]  link 1 from upright (upright 0, hanging pi)
    q[2]  link 2 relative to link 1

Two plant models:

* `ALPlant`, the rigid design model: the motor rotor reflected to the arm axis, a rigid gear,
  viscous friction, torque input at the gear output. It has the interface of `rotary_lib.Plant`
  (`f`, `rhs`, `linearise`, `hanging`, `nq`, `nx`, `qdist`), so the collocation swing-up and
  the TVLQR of `rotary_lib` run on it unchanged.
* `ALTwin`, the Python twin of the bond graph: the q-axis winding (R, L, back-EMF), the rotor as its
  own degree of freedom, the gear spring with smooth backlash and hardening, smooth Stribeck
  friction on the motor side, output-bearing and passive-joint friction.

Plus Python replicas of every discrete block of the bond-graph model (current loop, drive loop,
AS5048 encoders, the 1 kHz outer controller with its alpha-beta-gamma estimators), so the
closed loop can be designed and checked here before it runs in bg-sim.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import casadi as ca
import numpy as np
from scipy.linalg import expm, solve_discrete_are

HERE = Path(__file__).resolve().parent
G = 9.81
SQ2 = math.sqrt(2.0)
TWO_PI = 2.0 * math.pi
ARCMIN = math.pi / (180.0 * 60.0)
DEG = math.pi / 180.0


def hardware() -> dict:
    return json.loads((HERE / "actilink_hardware.json").read_text(encoding="utf-8"))


def val(entry):
    return entry["value"] if isinstance(entry, dict) and "value" in entry else entry


# ------------------------------------------------------------------ drive parameters (SI)
@dataclass
class Drive:
    """One ACTILINK-JD size in the units of the model (output side unless named _m)."""

    name: str
    N: float  # gear ratio
    tau_rated: float
    tau_peak: float
    w_max: float  # no-load output speed [rad/s]
    J_out: float  # rotor reflected to the output [kg m^2]
    backlash: float  # total lost motion [rad]
    k1: float  # gear stiffness below the knee [N m/rad]
    k3: float  # gear stiffness above the knee
    tau_knee: float
    Fc_in: float  # motor-side friction, output-referred
    Fs_in: float
    vs_in: float
    Fv_in: float
    Fc_out: float  # output bearing
    Fv_out: float
    pole_pairs: int
    kt_rms: float  # motor side [N m/A_rms]
    R: float  # phase resistance
    L: float  # phase inductance
    I_max_rms: float
    I_cont_rms: float
    mass: float
    diameter: float
    length: float
    motor_bits: int
    out_bits: int
    V_dc: float = 48.0
    uq_factor: float = 0.95

    # dq (amplitude invariant): i_q is the phase-current amplitude, torque = kt_q i_q
    @property
    def kt_q(self) -> float:
        return self.kt_rms / SQ2

    # bond-graph equivalent winding: flow i' = 1.5 i_q, so that u_q i' is the electrical power
    @property
    def r_gy(self) -> float:  # gyrator modulus (= p * flux linkage) [V s/rad = N m/A]
        return self.kt_q / 1.5

    @property
    def R_eq(self) -> float:
        return self.R / 1.5

    @property
    def L_eq(self) -> float:
        return self.L / 1.5

    @property
    def J_m(self) -> float:  # rotor inertia on the motor shaft
        return self.J_out / self.N**2

    @property
    def uq_max(self) -> float:
        return self.uq_factor * self.V_dc / math.sqrt(3.0)

    @property
    def iq_peak(self) -> float:
        """q-current limit: the max. acceleration torque (end of current-torque linearity), never
        above the drive's peak current."""
        return min(self.tau_peak / (self.N * self.kt_q), self.I_max_rms * SQ2)

    @property
    def tau_limit(self) -> float:
        return self.iq_peak * self.N * self.kt_q

    @property
    def gear_damping(self) -> float:
        """Contact damping of the gear spring: 5 % of critical on the rotor against the stiff side."""
        return 2.0 * 0.05 * math.sqrt(self.k3 * self.J_out)


def drive(size: str = "JD08", hw: dict | None = None) -> Drive:
    hw = hw or hardware()
    a = hw["actuators"][size]
    c = hw["drive_common"]
    v = lambda k: float(val(a[k]))
    return Drive(
        name=size, N=v("ratio"), tau_rated=v("tau_rated"), tau_peak=v("tau_peak"),
        w_max=v("speed_max") * TWO_PI / 60.0, J_out=v("J_out"), backlash=v("backlash") * ARCMIN,
        k1=v("k_gear_low"), k3=v("k_gear_high"), tau_knee=v("tau_knee"),
        Fc_in=v("fric_in_Fc"), Fs_in=v("fric_in_Fs"), vs_in=v("fric_in_vs"), Fv_in=v("fric_in_Fv"),
        Fc_out=v("fric_out_Fc"), Fv_out=v("fric_out_Fv"), pole_pairs=int(v("pole_pairs")),
        kt_rms=v("kt_rms"), R=v("R_phase"), L=v("L_phase"), I_max_rms=v("I_max"), I_cont_rms=v("I_cont"),
        mass=v("mass"), diameter=v("diameter"), length=v("length"),
        motor_bits=int(v("motor_encoder_bits")), out_bits=int(v("output_encoder_bits")),
        V_dc=float(val(c["V_dc"])), uq_factor=float(val(c["uq_max_factor"])),
    )  # fmt: skip


# ------------------------------------------------------------------ the rig (mass properties)
@dataclass
class Body:
    name: str
    m: float
    c: float  # COM along the body x axis from the joint [m]
    J: tuple  # principal inertias about the COM (x along the body, z the joint axis)


def rig(hw: dict | None = None) -> dict:
    """Arm, link 1, link 2 as composite bodies of tube + clamps + joint housings (rig in the JSON)."""
    hw = hw or hardware()
    r = hw["rig"]
    la = float(val(r["arm_length"]))
    ll = float(val(r["link_length"]))
    m_hub, m_atube, m_h1 = r["hub"]["mass"], r["arm_tube"]["mass"], r["joint1_housing"]["mass"]
    m_tube = r["link_tube"]["mass_per_link"]
    m_s1, m_h2, m_s2 = r["link1_shaft"]["mass"], r["joint2_housing"]["mass"], r["link2_shaft"]["mass"]

    def composite(parts):
        """parts: (m, x, own (Jx, Jy, Jz) about the part's COM). Masses on the body x axis."""
        m = sum(p[0] for p in parts)
        c = sum(p[0] * p[1] for p in parts) / m
        jx = sum(p[2][0] for p in parts)
        jy = sum(p[2][1] + p[0] * (p[1] - c) ** 2 for p in parts)
        jz = sum(p[2][2] + p[0] * (p[1] - c) ** 2 for p in parts)
        return m, c, (jx, jy, jz)

    def tube(m, length, ro, ri):
        jt = m * (length**2 / 12.0 + (ro**2 + ri**2) / 4.0)
        return (0.5 * m * (ro**2 + ri**2), jt, jt)

    def block(m, a):
        j = m * 2 * a * a / 12.0
        return (j, j, j)

    # arm: hub (disc d 80 mm on the axis), square tube 30x30x2 from -40 mm to 290 mm, the joint-1
    # housing centred 30 mm inside the link-1 plane (the link turns beside it, at x = la)
    hub_j = (0.25 * m_hub * 0.04**2, 0.25 * m_hub * 0.04**2, 0.5 * m_hub * 0.04**2)
    arm = composite([(m_hub, 0.0, hub_j), (m_atube, 0.125, tube(m_atube, 0.33, 0.015, 0.013)),
                     (m_h1, la - 0.03, block(m_h1, 0.04))])
    link1 = composite([(m_s1, 0.0, block(m_s1, 0.015)), (m_tube, ll / 2, tube(m_tube, ll, 0.010, 0.008)),
                       (m_h2, ll, block(m_h2, 0.04))])
    link2 = composite([(m_s2, 0.0, block(m_s2, 0.015)), (m_tube, ll / 2, tube(m_tube, ll, 0.010, 0.008))])
    return {
        "arm_l": la, "link_l": ll, "offset2": float(val(r["link2_offset"])),
        "bodies": [Body("Arm", *arm), Body("Link1", *link1), Body("Link2", *link2)],
        "Fc_j": float(val(r["joint_fric_Fc"])), "Fv_j": float(val(r["joint_fric_Fv"])),
    }


# ------------------------------------------------------------------ kinematics (CasADi)
RJF = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])  # joint-2 frame in the arm frame


def rotz(a):
    c, s = ca.cos(a), ca.sin(a)
    return ca.vertcat(ca.horzcat(c, -s, 0), ca.horzcat(s, c, 0), ca.horzcat(0, 0, 1))


def kinematics(rg: dict, q):
    """World rotation and COM position of the three bodies, and the link-2 tip, for joint angles q."""
    b = rg["bodies"]
    r0 = rotz(q[0])
    p0 = r0 @ ca.vertcat(b[0].c, 0, 0)
    o1 = r0 @ ca.vertcat(rg["arm_l"], 0, 0)
    r1 = r0 @ ca.DM(RJF) @ rotz(q[1])
    p1 = o1 + r1 @ ca.vertcat(b[1].c, 0, 0)
    o2 = o1 + r1 @ ca.vertcat(rg["link_l"], 0, rg["offset2"])
    r2 = r1 @ rotz(q[2])
    p2 = o2 + r2 @ ca.vertcat(b[2].c, 0, 0)
    tip = o2 + r2 @ ca.vertcat(rg["link_l"], 0, 0)
    return [r0, r1, r2], [p0, p1, p2], tip, r2


def lagrangian(rg: dict, q, qd, j_axis: float):
    rots, pos, tip, r2 = kinematics(rg, q)
    kin = 0.5 * j_axis * qd[0] ** 2
    pot = 0
    for body, p, rot in zip(rg["bodies"], pos, rots, strict=True):
        vel = ca.jtimes(p, q, qd)
        rd = ca.reshape(ca.jtimes(ca.vec(rot), q, qd), 3, 3)
        om = rot.T @ rd
        w = ca.vertcat(om[2, 1], om[0, 2], om[1, 0])
        kin += 0.5 * body.m * ca.dot(vel, vel) + 0.5 * (body.J[0] * w[0] ** 2 + body.J[1] * w[1] ** 2 + body.J[2] * w[2] ** 2)
        pot += body.m * G * p[2]
    return kin, pot, tip, r2


# ------------------------------------------------------------------ the rigid design model
class ALPlant:
    """Rigid design model, torque input u [N m] at the gear output; `rotary_lib.Plant` interface."""

    n_links = 2
    nq = 3
    nx = 6

    def __init__(self, dr: Drive, rg: dict, coulomb_eps: float | None = None) -> None:
        self.dr, self.rg = dr, rg
        q = ca.SX.sym("q", 3)
        qd = ca.SX.sym("qd", 3)
        u = ca.SX.sym("u")
        kin, pot, tip, r2 = lagrangian(rg, q, qd, dr.J_out)
        mass = ca.hessian(kin, qd)[0]
        coriolis = ca.jacobian(ca.gradient(kin, qd), q) @ qd
        fv0 = dr.Fv_in + dr.Fv_out
        gen = ca.vertcat(u - fv0 * qd[0], -rg["Fv_j"] * qd[1], -rg["Fv_j"] * qd[2])
        if coulomb_eps is not None:
            gen[0] -= (dr.Fc_in + dr.Fc_out) * ca.tanh(qd[0] / coulomb_eps)
        rhs = ca.gradient(kin, q) - coriolis - ca.gradient(pot, q) + gen
        qdd = ca.solve(mass, rhs)
        x = ca.vertcat(q, qd)
        xdot = ca.vertcat(qd, qdd)
        self.f = ca.Function("f", [x, u], [xdot]).expand()
        self.fa = ca.Function("fa", [x, u], [ca.jacobian(xdot, x)]).expand()
        self.fb = ca.Function("fb", [x, u], [ca.jacobian(xdot, u)]).expand()
        self.mass_fn = ca.Function("M", [q], [mass]).expand()
        self.energy = ca.Function("E", [x], [kin + pot]).expand()
        ydir = r2 @ ca.vertcat(0, 1, 0)
        qforce = ca.jacobian(tip, q).T @ ydir
        self.qdist = ca.Function("qdist", [q], [ca.solve(mass, qforce)]).expand()
        self.tip = ca.Function("tip", [q], [tip]).expand()
        # support moment at the output flange (origin): M = dL_O/dt - sum r_i x m_i g; its
        # horizontal part is the tilting moment the actuator's output bearing carries
        qdd_s = ca.SX.sym("qdd", 3)
        rots, pos, _, _ = kinematics(rg, q)
        lo = ca.SX.zeros(3)
        mg = ca.SX.zeros(3)
        for body, p_i, rot in zip(rg["bodies"], pos, rots, strict=True):
            vel = ca.jtimes(p_i, q, qd)
            rd = ca.reshape(ca.jtimes(ca.vec(rot), q, qd), 3, 3)
            om = rot.T @ rd
            w_b = ca.vertcat(om[2, 1], om[0, 2], om[1, 0])
            lo += body.m * ca.cross(p_i, vel) + rot @ ca.vertcat(body.J[0] * w_b[0], body.J[1] * w_b[1], body.J[2] * w_b[2])
            mg += ca.cross(p_i, ca.vertcat(0, 0, -body.m * G))
        dlo = ca.jacobian(lo, q) @ qd + ca.jacobian(lo, qd) @ qdd_s
        m_sup = dlo - mg
        self.tilt = ca.Function("tilt", [q, qd, qdd_s], [ca.sqrt(m_sup[0] ** 2 + m_sup[1] ** 2)]).expand()

    def tilt_moment(self, x, u) -> float:
        qdd = self.rhs(x, u)[3:6]
        return float(self.tilt(x[0:3], x[3:6], qdd))

    def rhs(self, x, u):
        return np.array(self.f(x, u)).ravel()

    def linearise(self, x, u):
        return np.array(self.fa(x, u)), np.array(self.fb(x, u)).reshape(self.nx, 1)

    def hanging(self) -> np.ndarray:
        x = np.zeros(self.nx)
        x[1] = math.pi
        return x


# ------------------------------------------------------------------ smooth gear and friction
def smooth_relu(x, eps):
    return 0.5 * (x + ca.sqrt(x * x + eps * eps)) if isinstance(x, (ca.SX, ca.MX)) else 0.5 * (x + np.sqrt(x * x + eps * eps))


def gear_terms(dr: Drive, phi, w, sqrt=ca.sqrt, tanh=ca.tanh):
    """Gear spring torque (output side) for the deflection phi = theta_motor/N - q0 and rate w.

    D(phi) = s(phi - b) - s(-phi - b), s(x) = (x + sqrt(x^2 + eps^2))/2: a smooth dead zone of
    half width b = backlash/2 (no max/abs kink, no event). The spring hardens from k1 to k3 over
    the knee: T = k3 D - (k3 - k1) Dk tanh(D/Dk), Dk = tau_knee/k1. Contact damping d w D'(phi).
    """
    b = 0.5 * dr.backlash
    eps = 0.2 * b + 1e-9
    a1, a2 = phi - b, -phi - b
    r1, r2 = sqrt(a1 * a1 + eps * eps), sqrt(a2 * a2 + eps * eps)
    dz = 0.5 * (a1 + r1) - 0.5 * (a2 + r2)
    slope = 0.5 * (1 + a1 / r1) + 0.5 * (1 + a2 / r2)
    dk = dr.tau_knee / dr.k1
    t_spring = dr.k3 * dz - (dr.k3 - dr.k1) * dk * tanh(dz / dk)
    t_damp = dr.gear_damping * w * slope
    return t_spring, t_damp


def stribeck(fc, fs, vs, fv, w, veps, tanh=ca.tanh, exp=ca.exp):
    return (fc + (fs - fc) * exp(-(w / vs) ** 2)) * tanh(w / veps) + fv * w


V_EPS_OUT = 0.002  # [rad/s] friction smoothing at the output (motor side: N times larger)
V_EPS_J = 0.005  # passive joints


# ------------------------------------------------------------------ the full twin
class ALTwin:
    """Python twin of the bond graph. State x = [q0 q1 q2  w0 w1 w2  thm  wm  ie]:
    thm/wm the rotor angle/rate referred to the output (motor angle / N), ie = 1.5 i_q the
    bond-graph winding flow. Inputs: u_q [V] and an optional generalised disturbance."""

    nq = 3

    def __init__(self, dr: Drive, rg: dict, joint_coulomb: bool = True) -> None:
        self.dr, self.rg = dr, rg
        x = ca.SX.sym("x", 9)
        uq = ca.SX.sym("uq")
        fd = ca.SX.sym("fd")  # force on the link-2 tip (N), perpendicular in the pendulum plane
        q, qd = x[0:3], x[3:6]
        thm, wm, ie = x[6], x[7], x[8]
        kin, pot, tip, r2 = lagrangian(rg, q, qd, 0.0)
        mass = ca.hessian(kin, qd)[0]
        coriolis = ca.jacobian(ca.gradient(kin, qd), q) @ qd
        t_spring, t_damp = gear_terms(dr, thm - q[0], wm - qd[0])
        t_gear = t_spring + t_damp
        f_out = stribeck(dr.Fc_out, dr.Fc_out, 1.0, dr.Fv_out, qd[0], V_EPS_OUT)
        fj = rg["Fc_j"] if joint_coulomb else 0.0
        f_j1 = stribeck(fj, fj, 1.0, rg["Fv_j"], qd[1], V_EPS_J)
        f_j2 = stribeck(fj, fj, 1.0, rg["Fv_j"], qd[2], V_EPS_J)
        ydir = r2 @ ca.vertcat(0, 1, 0)
        qforce = ca.jacobian(tip, q).T @ ydir
        gen = ca.vertcat(t_gear - f_out, -f_j1, -f_j2) + qforce * fd
        rhs = ca.gradient(kin, q) - coriolis - ca.gradient(pot, q) + gen
        qdd = ca.solve(mass, rhs)
        n = dr.N
        f_in = stribeck(dr.Fc_in, dr.Fs_in, dr.vs_in, dr.Fv_in, wm, V_EPS_OUT)
        t_motor = n * dr.r_gy * ie  # output-referred motor torque
        wmd = (t_motor - t_gear - f_in) / dr.J_out
        ied = (uq - dr.R_eq * ie - dr.r_gy * n * wm) / dr.L_eq
        xdot = ca.vertcat(qd, qdd, wm, wmd, ied)
        self.f = ca.Function("f", [x, uq, fd], [xdot]).expand()
        # energy bookkeeping: stored (kinetic + potential + rotor + winding); gear spring by quadrature
        e_store = kin + pot + 0.5 * dr.J_out * wm**2 + 0.5 * dr.L_eq * ie**2
        p_loss = (dr.R_eq * ie**2 + f_in * wm + t_damp * (wm - qd[0]) + f_out * qd[0] + f_j1 * qd[1] + f_j2 * qd[2])
        self.aux = ca.Function("aux", [x, uq], [ca.vertcat(t_spring, t_damp, e_store, p_loss, uq * ie, ie / 1.5,
                                                          t_motor)]).expand()
        self.tip = ca.Function("tip", [q], [tip]).expand()

    def rhs(self, x, uq, fd=0.0):
        return np.array(self.f(x, uq, fd)).ravel()

    def state(self, q, w=None) -> np.ndarray:
        """At rest at q, with the gear spring relaxed: the rotor at the arm angle."""
        x = np.zeros(9)
        x[0:3] = q
        if w is not None:
            x[3:6] = w
            x[7] = w[0]
        x[6] = q[0]
        return x


# ------------------------------------------------------------------ firmware replicas
@dataclass
class Firmware:
    """Every number of the discrete blocks (the bond-graph blocks get the same values)."""

    dr: Drive
    Ts_i: float = 1.0 / 16000.0  # current loop
    Ts_v: float = 1.0 / 4000.0  # drive velocity/torque loop
    Ts_c: float = 1.0e-3  # EtherCAT / outer controller
    delay: int = 1  # EtherCAT cycles between the computation and the drive
    # current loop PI (designed by `tune_current`)
    kp_i: float = 0.0
    ki_i: float = 0.0
    # CSV velocity loop PI at the output (designed by `tune_velocity`)
    kp_w: float = 0.0
    ki_w: float = 0.0
    # AS5048
    bits: int = 14
    lat_a: float = 0.1875e-3
    lat_b: float = 0.4375e-3
    noise: float = 0.06 * DEG
    inl1: tuple = (0.25 * DEG, 30.0 * DEG, 0.15 * DEG, -60.0 * DEG)  # link-1 encoder
    inl2: tuple = (0.20 * DEG, -100.0 * DEG, 0.12 * DEG, 45.0 * DEG)  # link-2 encoder
    zero: tuple = (1.234, 4.0)  # magnet mounting angles

    def tune_current(self, bw_hz: float = 1500.0) -> None:
        """PI on the q current: zero on the winding pole, crossover at bw_hz (continuous design,
        the 16 kHz sampling costs about 15 deg of phase at 1.5 kHz)."""
        wc = TWO_PI * bw_hz
        self.kp_i = wc * self.dr.L  # V/A on i_q: L di/dt = u
        self.ki_i = self.kp_i * self.dr.R / self.dr.L

    def tune_velocity(self, j_load: float, bw_hz: float = 15.0) -> None:
        wc = TWO_PI * bw_hz
        self.kp_w = wc * j_load  # N m s/rad
        self.ki_w = self.kp_w * wc / 4.0


def wrap(a: float) -> float:
    return (a + math.pi) % TWO_PI - math.pi


def as5048(theta: float, z: float, fw: Firmware, zero: float = 0.0, inl_p=None) -> float:
    """The angle register of an AS5048 (14 bit) for the true angle theta and a unit noise sample z:
    INL (first and second harmonic), output noise, quantisation, modulo one turn; returned as an
    angle in [0, 2 pi)."""
    a1, p1, a2, p2 = inl_p if inl_p is not None else fw.inl1
    th = theta + a1 * math.sin(theta + p1) + a2 * math.sin(2 * theta + p2) + fw.noise * z + zero
    n = 2**fw.bits
    c = math.floor(th * n / TWO_PI) % n
    return c * TWO_PI / n


def inl(theta, p):
    a1, p1, a2, p2 = p
    return a1 * np.sin(theta + p1) + a2 * np.sin(2 * theta + p2)


def abg_gains(T: float, sigma: float, q_jerk: float) -> np.ndarray:
    """Steady-state Kalman gain of the white-jerk kinematic model [angle, rate, acceleration]."""
    F = np.array([[1, T, T * T / 2], [0, 1, T], [0, 0, 1]])
    Gm = np.array([[T**3 / 6], [T * T / 2], [T]])
    Q = q_jerk * (Gm @ Gm.T) / T  # discretised white jerk of PSD q_jerk
    H = np.array([[1.0, 0, 0]])
    P = solve_discrete_are(F.T, H.T, Q, np.array([[sigma**2]]))
    S = H @ P @ H.T + sigma**2
    return (P @ H.T / S).ravel()


def dlqr_delay(a, b, Ts: float, qdiag, r: float, delay: int):
    """Discrete LQR on the ZOH model, augmented with `delay` held inputs (the EtherCAT cycle).
    Returns K for z = [x, u_{k-1}, ...] (u_k = -K z)."""
    n = a.shape[0]
    m = np.zeros((n + 1, n + 1))
    m[:n, :n] = a * Ts
    m[:n, n:] = b * Ts
    e = expm(m)
    ad, bd = e[:n, :n], e[:n, n:]
    if delay == 0:
        A, B, Q = ad, bd, np.diag(qdiag)
    else:
        A = np.zeros((n + delay, n + delay))
        A[:n, :n] = ad
        A[:n, n:n + 1] = bd  # the oldest command acts now
        for k in range(1, delay):
            A[n + k - 1, n + k] = 1.0
        B = np.zeros((n + delay, 1))
        B[n + delay - 1, 0] = 1.0
        Q = np.zeros((n + delay, n + delay))
        Q[:n, :n] = np.diag(qdiag)
    P = solve_discrete_are(A, B, Q, np.array([[r]]))
    K = np.linalg.solve(B.T @ P @ B + r, B.T @ P @ A)
    return K.ravel(), A, B


class Controller:
    """Python replica of the `ALCtrl` block (1 kHz): encoder selection and unwrapping, alpha-beta-
    gamma estimators, idle / TVLQR swing-up / latched LQR balance, the torque limit and the EtherCAT
    delay. Units: angles rad, torque N m at the output."""

    def __init__(self, cfg: dict) -> None:
        self.c = cfg
        self.th = [0.0, 0.0, 0.0]
        self.est = np.zeros((3, 3))  # per joint [angle, rate, acc]
        self.init = False
        self.latched = False
        self.u_hist = [0.0] * max(1, cfg["delay"])
        self.mode = 0.0

    def step(self, t: float, q0_meas: float, m1: float, m2: float) -> float:
        c = self.c
        if not self.init:
            self.th = [q0_meas, c["th1_init"] + wrap(m1 - c["z1"] - c["th1_init"]), wrap(m2 - c["z2"])]
            self.est[:, 0] = self.th
            self.init = True
        self.th[0] = q0_meas
        self.th[1] = self.th[1] + wrap(m1 - c["z1"] - self.th[1])
        self.th[2] = self.th[2] + wrap(m2 - c["z2"] - self.th[2])
        T = c["Ts"]
        for j in range(3):
            g = c["abg"][j]
            a, w, acc = self.est[j]
            ap = a + T * w + 0.5 * T * T * acc
            wp = w + T * acc
            r = self.th[j] - ap
            self.est[j] = [ap + g[0] * r, wp + g[1] * r, acc + g[2] * r]
        x = np.concatenate([self.est[:, 0], self.est[:, 1]])
        u = 0.0
        tau = t - c["t_on"]
        if t < c["t_on"]:
            self.mode = 0.0
        else:
            if c["balance_only"]:
                self.latched = True
            elif not self.latched and tau >= c["t_s"]:
                en = math.sqrt(float(np.sum(c["catch_w"] * x * x)))
                if en < c["catch_tol"]:
                    self.latched = True
            if self.latched:
                z = np.concatenate([x - c["x_ref"], self.u_hist])
                u = -float(np.dot(c["K"], z))
                self.mode = 2.0
            else:
                xr, ur, k = table_row(c, t)
                u = ur - float(np.dot(k, x - xr))
                self.mode = 1.0
        u = float(np.clip(u, -c["umax"], c["umax"]))
        out = self.u_hist[0] if c["delay"] > 0 else u
        if c["delay"] > 0:
            self.u_hist = self.u_hist[1:] + [u]
        return out


def table_row(c: dict, t: float):
    tab = c["tab"]
    nt = tab.shape[0]
    s = min(max((t - c["t_on"]) / c["dt_tab"], 0.0), nt - 1)
    i = min(math.floor(s), nt - 2)
    w = s - i
    row = (1 - w) * tab[i] + w * tab[i + 1]
    return row[0:6], row[6], row[7:13]


class DriveFw:
    """The drive: velocity/torque loop at Ts_v (CST: the target torque; CSV: a PI on the speed from
    the motor encoder) and the q-current PI at Ts_i with the voltage clamp and anti-windup."""

    def __init__(self, fw: Firmware, mode: int = 0) -> None:
        self.fw = fw
        self.mode = mode
        self.iref = 0.0
        self.uq = 0.0
        self.ii = 0.0  # current-loop integrator (V)
        self.wi = 0.0  # velocity integrator (N m)
        self.th_prev = None

    def vel_tick(self, tau_cmd: float, w_cmd: float, thm_meas: float) -> None:
        fw, dr = self.fw, self.fw.dr
        if self.mode == 1:
            w = 0.0 if self.th_prev is None else (thm_meas - self.th_prev) / fw.Ts_v
            e = w_cmd - w
            tau = fw.kp_w * e + self.wi
            self.wi = float(np.clip(self.wi + fw.ki_w * fw.Ts_v * e, -dr.tau_limit, dr.tau_limit))
        else:
            tau = tau_cmd
        self.th_prev = thm_meas
        self.iref = float(np.clip(tau / (dr.N * dr.kt_q), -dr.iq_peak, dr.iq_peak))

    def cur_tick(self, iq: float) -> None:
        fw, dr = self.fw, self.fw.dr
        e = self.iref - iq
        u = fw.kp_i * e + self.ii
        lim = dr.uq_max
        self.uq = float(np.clip(u, -lim, lim))
        if abs(u) < lim or (u > 0) != (e > 0):  # conditional integration (anti-windup)
            self.ii = float(np.clip(self.ii + fw.ki_i * fw.Ts_i * e, -lim, lim))


def quant(x: float, bits: int) -> float:
    n = 2**bits
    return math.floor(x * n / TWO_PI) * TWO_PI / n


def simulate_closed_loop(twin: ALTwin, fw: Firmware, ctrl_cfg: dict, x0, t_end: float, *,
                         bus: int = 0, dist=None, sub: int = 2, seed: int = 1, noise: bool = True,
                         drive_mode: int = 0, w_cmd=None, tau_cmd_fn=None, record_every: int = 16,
                         energy: bool = False, nrd: int = 1):
    """Fixed-step simulation of twin + firmware: RK4 with `sub` steps per current-loop tick.
    The AS5048 samples are taken `lat` before each controller tick (the bond graph's offset clocks).
    Returns a dict of recorded arrays (every `record_every` current ticks)."""
    rng = np.random.default_rng(seed)
    dr = fw.dr
    x = np.array(x0, float)
    ctrl = Controller(ctrl_cfg) if ctrl_cfg is not None else None
    drv = DriveFw(fw, drive_mode)
    n_i = round(t_end / fw.Ts_i)
    per_v = round(fw.Ts_v / fw.Ts_i)
    per_c = round(fw.Ts_c / fw.Ts_i)
    lat = fw.lat_a if bus == 0 else fw.lat_b
    lat_ticks = round(lat / fw.Ts_i)
    h = fw.Ts_i / sub
    tau_cmd = 0.0
    enc = [0.0, 0.0]
    zs = [0.0, 0.0]
    rec = {k: [] for k in ("t", "x", "uq", "iq", "tau_cmd", "mode", "est", "enc", "ts", "loss", "pin", "estore")}
    e_loss = 0.0
    e_in = 0.0
    n_read = 0
    for k in range(n_i):
        t = k * fw.Ts_i
        # AS5048 sampling: `lat` before the next controller tick
        if (k + lat_ticks) % per_c == 0 and k > 0:
            n_read += 1
            if n_read >= nrd:
                n_read = 0
                zs = list(rng.standard_normal(2)) if noise else [0.0, 0.0]
                enc = [as5048(x[1], zs[0], fw, fw.zero[0], fw.inl1), as5048(x[2], zs[1], fw, fw.zero[1], fw.inl2)]
        if k % per_c == 0 and k > 0 and ctrl is not None:
            q0m = quant(x[0], dr.out_bits)
            tau_cmd = ctrl.step(t, q0m, *enc)
        if tau_cmd_fn is not None:
            tau_cmd = tau_cmd_fn(t)
        if k % per_v == 0 and k > 0:
            wc = w_cmd(t) if w_cmd is not None else 0.0
            drv.vel_tick(tau_cmd, wc, quant(x[6] * dr.N, dr.motor_bits) / dr.N)
        if k > 0:
            drv.cur_tick(x[8] / 1.5)
        uq = drv.uq
        fd = dist(t) if dist else 0.0
        for s in range(sub):
            k1 = twin.rhs(x, uq, fd)
            k2 = twin.rhs(x + 0.5 * h * k1, uq, fd)
            k3 = twin.rhs(x + 0.5 * h * k2, uq, fd)
            k4 = twin.rhs(x + h * k3, uq, fd)
            if energy:
                aux0 = np.array(twin.aux(x, uq)).ravel()
            x = x + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
            if energy:
                aux1 = np.array(twin.aux(x, uq)).ravel()
                e_loss += 0.5 * h * (aux0[3] + aux1[3])
                e_in += 0.5 * h * (aux0[4] + aux1[4])
        if k % record_every == 0:
            aux = np.array(twin.aux(x, uq)).ravel()
            rec["t"].append(t + fw.Ts_i)
            rec["x"].append(x.copy())
            rec["uq"].append(uq)
            rec["iq"].append(x[8] / 1.5)
            rec["tau_cmd"].append(tau_cmd)
            rec["mode"].append(ctrl.mode if ctrl else 0.0)
            rec["est"].append(np.concatenate([ctrl.est[:, 0], ctrl.est[:, 1]]) if ctrl else np.zeros(6))
            rec["enc"].append(list(enc))
            rec["ts"].append(aux[0])
            rec["loss"].append(e_loss)
            rec["pin"].append(e_in)
            rec["estore"].append(aux[2])
    return {k: np.array(v) for k, v in rec.items()}
