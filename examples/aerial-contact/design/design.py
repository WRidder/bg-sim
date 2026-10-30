# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.11"]
# ///
"""Parameters, gains and the contact-controller derivation for the `aerial-contact` sample (X5.8).

The system is the multimodal aerial manipulator of Wopereis et al., "Multimodal Aerial Locomotion: An
Approach to Active Tool Handling", IEEE Robotics & Automation Magazine, Dec. 2018: a hexarotor with a
one-DoF arm (a servo about y_b and a rigid carbon tube), a rubber shock mount (a compliant spherical joint)
and an end-effector with three omnidirectional wheels that rolls on a vertical wall.

Everything the model needs is derived here, and checked on small linear models:

1. the airframe and propulsion data (hexarotor, 950 Kv motors, 10x4.5 in propellers, 16 V tether);
2. the allocation matrix `M` ([F, tx, ty, tz] = M T) and its pseudo-inverse for the six-rotor mixer;
3. the ESC speed loop, the body-rate loop, the attitude / velocity / position loops of the free-flight
   cascade (all firmware at 4 ms; this is the same derivation as the X5.7 quadcopter with the hexarotor data);
4. **the contact controller** (the heart of the paper): the constrained dynamics of the multirotor with the
   arm while the end-effector is held on the wall by its wheels, their linearisation about the equilibrium
   of a pitch set-point theta_sp, and an LQR gain K(theta_sp) on a grid of theta_sp (gain scheduling);
5. the Butterworth low-pass coefficients of the IMU filters (bilinear transform at 250 Hz).

Running it prints the derivation and the checks. ``build_model.py`` imports `design.PARAMS` to generate the
model document and ``docs.py`` imports the contact-controller data for the model docs.

Run: ``uv run examples/aerial-contact/design/design.py``.

Conventions. World frame z up. Body frame: x forward, y left, z up (along the thrust), origin at the
centre of mass of the multirotor. Euler angles Z-Y-X (R = Rz(psi) Ry(theta) Rx(phi)): a positive pitch
theta is a rotation about +y, which tips the nose DOWN and tilts the thrust vector forward (towards the
wall). The manipulator angle mu is the elevation of the arm above the body x axis (the servo angle is
q = -mu): in free flight mu_sp = theta keeps the arm level in the world.
"""

from __future__ import annotations

import math
import sys

import numpy as np
from scipy.linalg import solve_continuous_are

# ----------------------------------------------------------------------------- plant data
G = 9.81
M_B = 2.1                         # kg   multirotor (paper: 2.1 kg)
M_ARM = 0.23                      # kg   carbon tube + servo horn (paper: 0.23 kg)
M_EE = 0.15                       # kg   end-effector (paper: 0.15 kg)
M_TRUE = M_B + M_ARM + M_EE       # kg   total mass in free flight
M_NOM = 2.50                      # kg   what the position controller believes (0.8 % too high)
M_D = M_B + M_ARM                 # kg   mass the thrust carries in contact (the end-effector hangs on the wall)
L_M = 0.60                        # m    constant distance from the multirotor centre of mass to the elastic joint
EE_CX = 0.03                      # m    end-effector centre of mass ahead of the elastic joint
EE_WX = 0.06                      # m    wheel contact points ahead of the elastic joint (the wheel plane)
EE_RHO = 0.045                    # m    radius of the three wheel contact points about the end-effector axis
WALL_X = 1.6                      # m    wall plane x_w

J_B = np.array([0.055, 0.055, 0.105])        # kg m^2  principal inertia of the hexarotor about its centre of mass
J_ARM = np.array([2.0e-4, M_ARM * L_M ** 2 / 12.0, M_ARM * L_M ** 2 / 12.0])   # tube about its own centre (x: the axial inertia of the tube plus the servo horn and the clamps)
J_EE = np.array([2.0e-4, 2.0e-4, 2.0e-4])    # kg m^2  end-effector (a 9 cm disc with a 0.15 kg payload)

N_ROT = 6
ARM_R = 0.40                      # m    centre to motor (80 cm diameter)
ANG = np.deg2rad(30.0 + 60.0 * np.arange(N_ROT))     # rotors at 30, 90, ... 330 deg: the front gap holds the arm
RX = ARM_R * np.cos(ANG)
RY = ARM_R * np.sin(ANG)
SPIN = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0])   # +1 counter-clockwise seen from above, alternating

# 950 Kv motor, 10x4.5 in propeller, 16 V (4S) tether
KV_RPM = 950.0
K_E = 1.0 / (KV_RPM * 2.0 * math.pi / 60.0)  # V s/rad  (= k_t in SI)
K_T = K_E                         # N m/A
R_W = 0.11                        # Ohm  winding resistance (plus ESC and wiring)
L_W = 40e-6                       # H
J_M = 5.0e-5                      # kg m^2  rotor bell 5e-6 + 10 in propeller 4.5e-5
B_M = 2.0e-6                      # N m s/rad bearing friction
KT_PROP = 1.42e-5                 # N/(rad/s)^2   thrust: 13 N at 957 rad/s
KQ_PROP = 2.03e-7                 # N m/(rad/s)^2 drag torque, kQ/kT = 0.0143 m
V_SUPPLY = 16.0                   # V    tethered supply (a constant source: no battery, no sag)
CD = (0.25, 0.25, 0.35)           # N s/m linear drag (body x, y, z)
CDR = 3.0e-3                      # N m s/rad rotational air damping

T_MAX_TOTAL = 78.0                # N    paper: maximum total thrust
T_MAX = T_MAX_TOTAL / N_ROT       # N    per rotor (13 N, omega = 957 rad/s)
T_MIN = 0.5                       # N    idle thrust while armed

# manipulator: servo about y_b (Dynamixel MX-106R class), tube along the joint x axis
SERVO_TAU_MAX = 8.4               # N m  stall torque
J_ARM_LOAD = M_ARM * L_M ** 2 / 3.0 + M_EE * (L_M + EE_CX) ** 2     # kg m^2 arm + end-effector about the servo axis
SERVO_W = 40.0                    # rad/s servo position-loop bandwidth
SERVO_KP = J_ARM_LOAD * SERVO_W ** 2
SERVO_KD = 2.0 * 0.8 * J_ARM_LOAD * SERVO_W
# rubber shock mount (M5): a rotational spring-damper between the arm tip and the end-effector
RUBBER_K = 1.0                    # N m/rad
RUBBER_B = 0.03                   # N m s/rad

# contact of the three omni-wheels with the wall (Hertz/Hunt-Crossley normal, anisotropic traction)
CONTACT = {"k": 4000.0, "xref": 1.0e-3, "c": 4.0, "mu_d": 0.7, "mu_r": 0.04, "vs": 2.0e-3, "vr": 5.0e-3, "eps": 1.0e-6}
WHEEL_R = 0.02                    # m    wheel radius (only for the animated wheel angle)
V_EE_MAX = 0.40                   # m/s  end-effector speed at a velocity command of 1 (the "velocity scale")
WHEEL_ALPHA = np.deg2rad(90.0 + 120.0 * np.arange(3))   # angular position of the wheel contacts about the axis

# sample times: the whole firmware runs at 250 Hz (keeps the recorded run small: every tick is stored twice)
TS = 4e-3
TS_POS = 20e-3

# ----------------------------------------------------------------------------- scenario (compressed run)
X0 = 0.45                         # m   hover start x of the multirotor
Z0 = 1.0                          # m   hover height
SCEN = {
    "t_move1": 1.5, "d_move1": 2.5, "dx1": 0.30,    # approach in free flight: x 0.45 -> 0.75
    "t_engage": 4.5,                                # engage request (guard: end-effector within 30 cm of the wall)
    "d_guard": 0.30,                                # m   engage allowed only inside this distance
    "d_contact": 0.02,                              # m   the wheel plane counts as at the wall within this distance
    "theta0": 12.0, "theta1": 20.0, "t_ramp1": 4.0, # engage ramp 12 -> 20 deg over 4 s (from the engage instant)
    "theta2": 27.0, "t_ramp2_start": 4.0, "t_ramp2": 3.0,   # contact ramp to 27 deg (starts 4 s after the engage instant)
    "t_loc": 13.0, "t_up": 6.0, "t_pause": 2.0, "t_down": 6.0, "v_cmd": 0.125,   # ground locomotion
    "t_disengage": 28.5, "C": 0.75,                 # disengage request, back-off distance C
    "t_end": 34.0,
}


# ----------------------------------------------------------------------------- helpers
def butterworth2(fc: float, ts: float) -> tuple[list[float], list[float]]:
    """Second-order Butterworth low-pass by the bilinear transform: ``b0 b1 b2`` and ``a1 a2`` (a0 = 1)."""
    k = math.tan(math.pi * fc * ts)
    norm = 1.0 / (1.0 + math.sqrt(2.0) * k + k * k)
    b0 = k * k * norm
    return [b0, 2.0 * b0, b0], [2.0 * (k * k - 1.0) * norm, (1.0 - math.sqrt(2.0) * k + k * k) * norm]


def allocation() -> tuple[np.ndarray, np.ndarray]:
    """``M`` with [F, tx, ty, tz]' = M T (6 rotors), and the pseudo-inverse used by the mixer (6 x 4)."""
    m = np.vstack([np.ones(N_ROT), RY, -RX, -SPIN * KQ_PROP / KT_PROP])
    return m, np.linalg.pinv(m)


def freq_margins(loop, w: np.ndarray) -> tuple[float, float, float]:
    """Gain crossover (rad/s), phase margin (deg) and gain margin (dB) of a loop ``L(jw)``."""
    ell = np.array([loop(1j * x) for x in w])
    mag = np.abs(ell)
    phase = np.unwrap(np.angle(ell))
    idx = np.where((mag[:-1] >= 1.0) & (mag[1:] < 1.0))[0]
    if idx.size == 0:
        return float("nan"), float("nan"), float("nan")
    i = int(idx[0])
    wc = float(np.interp(1.0, [mag[i + 1], mag[i]], [w[i + 1], w[i]]))
    pm = 180.0 + math.degrees(float(np.interp(wc, w, phase)))
    j = np.where((phase[:-1] > -math.pi) & (phase[1:] <= -math.pi))[0]
    if j.size == 0:
        gm = float("inf")
    else:
        k = int(j[0])
        wpi = float(np.interp(-math.pi, [phase[k + 1], phase[k]], [w[k + 1], w[k]]))
        gm = -20.0 * math.log10(float(np.interp(wpi, w, mag)))
    return wc, pm, gm


def delay(ts: float):
    """Zero-order hold plus computation: the exact ZOH half-sample delay as exp(-s Ts/2) * sinc."""
    return lambda s: (1.0 - np.exp(-s * ts)) / (s * ts) * np.exp(-s * ts / 2.0) if abs(s) > 0 else 1.0


def vec(x) -> str:
    return "[" + ", ".join(f"{float(v):.9g}" for v in x) + "]"


def mat(x) -> str:
    return "[" + "; ".join(" ".join(f"{float(v):.9g}" for v in row) for row in x) + "]"


# ----------------------------------------------------------------------------- free-flight cascade
def omega_hover() -> float:
    return math.sqrt(M_NOM * G / N_ROT / KT_PROP)


def esc_design(report: list[str]) -> dict[str, float]:
    """Speed loop: u = u_ff + Kp e + I.  Linearised at the hover speed:  J w' = k_t i - d_p w,
    L i' = u - R i - k_e w, with d_p = 2 kQ w_h + b_m (propeller drag slope plus friction)."""
    wh = omega_hover()
    d_p = 2.0 * KQ_PROP * wh + B_M
    kp, ki = 0.035, 1.6

    def plant(s):
        return K_T / ((L_W * s + R_W) * (J_M * s + d_p) + K_T * K_E)

    def loop(s):
        return (kp + ki / s) * plant(s) * delay(TS)(s)

    w = np.logspace(0, 4, 4000)
    wc, pm, gm = freq_margins(loop, w)
    closed = lambda s: loop(s) / (1.0 + loop(s))  # noqa: E731
    mags = [20 * math.log10(abs(closed(1j * x))) for x in w]
    idx = np.where(np.array(mags) < -3.0)[0]
    w3 = float(w[idx[0]]) if idx.size else float("nan")
    assert pm > 55.0 and gm > 8.0, "ESC speed loop margins"
    report.append(
        f"ESC speed loop ({TS * 1e3:.0f} ms, hover w = {wh:.0f} rad/s): Kp {kp}, Ki {ki}: crossover {wc:.0f} rad/s, "
        f"phase margin {pm:.0f} deg, gain margin {gm:.1f} dB, closed-loop -3 dB at {w3:.0f} rad/s"
    )
    return {"Kp": kp, "Ki": ki, "bw": w3, "wc": wc, "pm": pm}


def rate_design(report: list[str], esc_bw: float) -> dict[str, np.ndarray | float]:
    """Rate loop per axis: tau -> rotor thrust differences -> rotor speed (ESC closed loop, a first-order
    lag at esc_bw) -> torque on the airframe; inertia J.  Delays: gyro low-pass (60 Hz Butterworth), the
    250 Hz hold, the ESC hold.  The yaw torque is the reaction of the rotors, sum(spin (Q + Jm dw/dt)), so
    the rotor acceleration adds a lead (zero at Q'/Jm) and the yaw gain is limited by the plateau
    Kp Jm / (Jz Q'); the yaw torque demand gets a first-order low-pass (`f_alpha` of RateCtrl)."""
    fc_gyro = 60.0
    wn = 2.0 * math.pi * fc_gyro
    lp = lambda s: wn * wn / (s * s + math.sqrt(2.0) * wn * s + wn * wn)  # noqa: E731
    act = lambda s: 1.0 / (s / esc_bw + 1.0)  # noqa: E731
    qslope = 2.0 * KQ_PROP * omega_hover()
    wf_yaw = 20.0
    alpha_yaw = 1.0 - math.exp(-TS * wf_yaw)
    kp = np.zeros(3)
    ki = np.zeros(3)
    kd = np.zeros(3)
    w = np.logspace(-1, 3, 6000)
    d_alpha = 0.3
    dfilt = lambda s: 1.0 / (s * TS / d_alpha + 1.0)  # noqa: E731

    def loop_of(axis, kp_a, ki_a, kd_a):
        j = J_B[axis] + (0.0 if axis == 2 else 0.0)

        def loop(s):
            c = kp_a + ki_a / s + kd_a * s * dfilt(s)
            plant = act(s) * np.exp(-s * 1.0e-3)
            if axis == 2:
                plant = plant * (1.0 + s * J_M / qslope) / (s / wf_yaw + 1.0)
            return c * delay(TS)(s) * lp(s) * plant / (j * s)

        return loop

    for axis, (name, wr, ti, td) in enumerate([("roll", 26.0, 0.30, 0.008), ("pitch", 26.0, 0.30, 0.008), ("yaw", 0.0, 1.5, 0.0)]):
        if axis < 2:
            kp[axis] = (J_B[axis] + 0.02) * wr          # the arm and end-effector add about 0.02 kg m^2 of pitch inertia
            ki[axis] = kp[axis] / ti
            kd[axis] = kp[axis] * td
        else:
            best = None
            for k in np.arange(0.01, 0.6, 0.005):
                _, pm_k, gm_k = freq_margins(loop_of(2, k, k / ti, 0.0), w)
                if np.isfinite(pm_k) and pm_k >= 55.0 and gm_k >= 12.0:
                    best = float(k)
            kp[axis] = best if best is not None else 0.03
            ki[axis] = kp[axis] / ti
        wc, pm, gm = freq_margins(loop_of(axis, kp[axis], ki[axis], kd[axis]), w)
        report.append(
            f"rate loop {name:5s}: Kp {kp[axis]:.3f} Ki {ki[axis]:.3f} Kd {kd[axis]:.4f}: crossover {wc:.1f} rad/s, "
            f"phase margin {pm:.0f} deg, gain margin {gm:.1f} dB"
        )
        assert pm > 45.0 and gm > 8.0, f"rate loop {name} margins"
    report.append(
        f"yaw actuator: lead zero Q'/Jm = {qslope / J_M:.1f} rad/s, torque low-pass {wf_yaw:.0f} rad/s "
        f"(f_alpha {alpha_yaw:.3f} per {TS * 1e3:.0f} ms tick)"
    )
    return {"Kp": kp, "Ki": ki, "Kd": kd, "alpha_yaw": alpha_yaw, "d_alpha": d_alpha}


def outer_design(report: list[str], esc_bw: float) -> dict[str, float]:
    """Attitude P + velocity PI + position P on the chain (one horizontal axis):
    p -> v_cmd -> a_cmd -> tilt_cmd = a/g -> attitude P -> rate loop -> tilt -> a = g tilt -> v -> p.
    The vertical axis has no attitude loop: a_cmd -> thrust -> rotor speed (ESC lag) -> a."""
    k_att, kv, ki, kp = 5.0, 3.0, 1.2, 1.0
    kv_z, ki_z, kp_z = 5.0, 3.0, 1.5
    wr = 26.0
    t_rate = 1.0 / wr + 0.016
    w = np.logspace(-2, 2, 4000)

    def att_loop(s):
        return k_att * np.exp(-s * (TS / 2.0)) / (s * (t_rate * s + 1.0))

    def att_cl(s):
        return att_loop(s) / (1.0 + att_loop(s))

    def vel_loop(s):
        return (kv + ki / s) * att_cl(s) * np.exp(-s * (TS_POS * 1.5)) / s

    def pos_loop(s):
        vcl = vel_loop(s) / (1.0 + vel_loop(s))
        return kp * vcl / s

    def vel_z_loop(s):
        return (kv_z + ki_z / s) * np.exp(-s * (TS_POS * 1.5)) / (s / esc_bw + 1.0) / s

    def pos_z_loop(s):
        vcl = vel_z_loop(s) / (1.0 + vel_z_loop(s))
        return kp_z * vcl / s

    out = {}
    for name, loop in (("attitude", att_loop), ("velocity", vel_loop), ("position", pos_loop),
                       ("vertical velocity", vel_z_loop), ("vertical position", pos_z_loop)):
        wc, pm, gm = freq_margins(loop, w)
        report.append(f"{name:17s} loop: crossover {wc:.2f} rad/s, phase margin {pm:.0f} deg, gain margin {gm:.1f} dB")
        assert pm > 40.0, f"{name} loop phase margin"
        out[name] = pm
    return {"K_rp": k_att, "Kv_xy": kv, "Ki_xy": ki, "Kp_xy": kp, "Kv_z": kv_z, "Ki_z": ki_z, "Kp_z": kp_z}


def nav_design(report: list[str]) -> dict[str, float]:
    """Error dynamics of one horizontal axis of the NavFilter (delta = truth - estimate):
        dp' = dv - L1 dp ;  dv' = F dth - L2 dp - L3 dv ;  dth' = -db - (kth / F) dv ;  db' = (kb kth / F) dv."""
    f = G
    l1, l2, l3, kth, kb, kpsi = 6.0, 9.0, 8.0, 12.0, 0.8, 2.0
    a = np.array([[-l1, 1.0, 0.0, 0.0], [-l2, -l3, f, 0.0], [0.0, -kth / f, 0.0, -1.0], [0.0, kb * kth / f, 0.0, 0.0]])
    poles = np.linalg.eigvals(a)
    report.append(
        f"nav filter (L1 {l1}, L2 {l2}, L3 {l3}, kth {kth}, kb {kb}): error poles "
        + ", ".join(f"{p.real:.2f}{p.imag:+.2f}j" for p in sorted(poles, key=lambda z: z.real))
    )
    assert max(p.real for p in poles) < -0.3, "navigation filter error dynamics are not stable enough"
    return {"L1": l1, "L2": l2, "L3": l3, "kth": kth, "kb": kb, "kpsi": kpsi}


# ----------------------------------------------------------------------------- contact controller
def rot_zyx(phi: float, theta: float, psi: float) -> np.ndarray:
    cf, sf, ct, st, cp, sp = math.cos(phi), math.sin(phi), math.cos(theta), math.sin(theta), math.cos(psi), math.sin(psi)
    return np.array([
        [cp * ct, cp * st * sf - sp * cf, cp * st * cf + sp * sf],
        [sp * ct, sp * st * sf + cp * cf, sp * st * cf - cp * sf],
        [-st, ct * sf, ct * cf],
    ])


def euler_w(phi: float, theta: float) -> np.ndarray:
    """Body rate from the Euler rates: omega = A(phi, theta) [phi', theta', psi']."""
    sf, cf, st, ct = math.sin(phi), math.cos(phi), math.sin(theta), math.cos(theta)
    return np.array([[1.0, 0.0, -st], [0.0, cf, sf * ct], [0.0, -sf, cf * ct]])


def skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


class ContactModel:
    """Multirotor + arm as ONE rigid body pinned at the elastic joint (the end-effector is held on the wall
    by its three wheels, so the origin of the end-effector frame Sigma_e does not move and the spherical joint
    transmits a force and no torque; the rubber mount torque, 1 N m/rad, is neglected).

    Parameters: the servo holds the arm at the elevation mu = mu_c; the thrust F acts along the body z axis
    at the multirotor centre of mass; the torque vector tau (rotors) acts on the body.  The unknown joint
    reaction F_E is eliminated (quasi-static reaction wrench, no contact-force unknown remains): with the
    composite centre of mass c, e the vector from c to the joint E in body axes, I_c the composite inertia,
    M = m_b + m_arm and u = (cos mu, 0, sin mu) the arm direction,

        M c'' = R F e_z - M g e_z + F_E ,    E = c + R e = const  =>  c'' = -R (w' x e + w x (w x e))
        (I_c + M S) w' = tau - L u x (F e_z) - w x (I_c w) - M e x (w x (w x e)) + M g e x (R^T e_z),   S = |e|^2 I - e e^T

    i.e. the Euler equation about E (I_E = I_c + M S).  The thrust moment arm about E is -L u (the thrust
    acts at the multirotor centre of mass, the arm length away from E).  The state is the Euler-angle state
    X = [phi, phi', theta, theta', psi, psi'] (Z-Y-X); the input is U = [tau_x, F, tau_z, tau_y].
    """

    def __init__(self, mu: float):
        self.mu = mu
        u = np.array([math.cos(mu), 0.0, math.sin(mu)])
        self.u = u
        self.m = M_B + M_ARM
        # composite centre of mass (body origin = multirotor CoM, the arm CoM sits at L/2 along u)
        self.cb = M_ARM * 0.5 * L_M * u / self.m
        self.e = L_M * u - self.cb
        # composite inertia about c: body (diag J_B shifted by -cb) + arm (rotated rod inertia shifted)
        r_b = -self.cb
        r_a = 0.5 * L_M * u - self.cb
        # rod axes: x along u, y = y_b, z perpendicular in the x-z plane
        ex = u
        ey = np.array([0.0, 1.0, 0.0])
        ez = np.cross(ex, ey)
        rot_arm = np.column_stack([ex, ey, ez])
        i_arm = rot_arm @ np.diag(J_ARM) @ rot_arm.T
        sh = lambda r, m: m * (float(r @ r) * np.eye(3) - np.outer(r, r))  # noqa: E731
        self.ic = np.diag(J_B) + sh(r_b, M_B) + i_arm + sh(r_a, M_ARM)
        self.s = float(self.e @ self.e) * np.eye(3) - np.outer(self.e, self.e)
        self.ie = self.ic + self.m * self.s            # inertia about the joint E

    def wdot(self, theta3: np.ndarray, omega: np.ndarray, tau: np.ndarray, f: float) -> np.ndarray:
        r = rot_zyx(*theta3)
        ez = np.array([0.0, 0.0, 1.0])
        rhs = (tau - L_M * np.cross(self.u, f * ez) - np.cross(omega, self.ic @ omega)
               - self.m * np.cross(self.e, np.cross(omega, np.cross(omega, self.e)))
               + self.m * G * np.cross(self.e, r.T @ ez))
        return np.linalg.solve(self.ie, rhs)

    def xdot(self, x: np.ndarray, uvec: np.ndarray) -> np.ndarray:
        """State derivative; ``uvec`` = [tau_x, F, tau_z, tau_y]."""
        th = np.array([x[0], x[2], x[4]])
        thd = np.array([x[1], x[3], x[5]])
        a = euler_w(th[0], th[1])
        omega = a @ thd
        tau = np.array([uvec[0], uvec[3], uvec[2]])
        wd = self.wdot(th, omega, tau, uvec[1])
        h = 1e-6
        adot = (euler_w(th[0] + h * thd[0], th[1] + h * thd[1]) - euler_w(th[0] - h * thd[0], th[1] - h * thd[1])) / (2 * h)
        thdd = np.linalg.solve(a, wd - adot @ thd)
        return np.array([thd[0], thdd[0], thd[1], thdd[1], thd[2], thdd[2]])

    def equilibrium(self) -> tuple[np.ndarray, np.ndarray]:
        """X_eq and U_eq at theta = mu (arm level in the world): F = M g / cos(theta), tau_y from the moment
        about E; all other torques are zero."""
        theta = self.mu
        x_eq = np.array([0.0, 0.0, theta, 0.0, 0.0, 0.0])
        f = self.m * G / math.cos(theta)
        # tau_y from the Euler equation about E with w = 0
        u0 = np.array([0.0, f, 0.0, 0.0])
        tau_y = -self.xdot_acc_pitch(u0, x_eq)
        return x_eq, np.array([0.0, f, 0.0, tau_y])

    def xdot_acc_pitch(self, uvec: np.ndarray, x_eq: np.ndarray) -> float:
        """Pitch angular acceleration (rad/s^2) times I_E[1,1] for a zero-torque input (the residual torque)."""
        th = np.array([x_eq[0], x_eq[2], x_eq[4]])
        wd = self.wdot(th, np.zeros(3), np.zeros(3), uvec[1])
        return float((self.ie @ wd)[1])

    def linearise(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        x_eq, u_eq = self.equilibrium()
        assert np.allclose(self.xdot(x_eq, u_eq), 0.0, atol=1e-7), "not an equilibrium"
        n, m = 6, 4
        a = np.zeros((n, n))
        b = np.zeros((n, m))
        for i in range(n):
            h = 1e-6
            d = np.zeros(n)
            d[i] = h
            a[:, i] = (self.xdot(x_eq + d, u_eq) - self.xdot(x_eq - d, u_eq)) / (2 * h)
        for j in range(m):
            h = 1e-6
            d = np.zeros(m)
            d[j] = h
            b[:, j] = (self.xdot(x_eq, u_eq + d) - self.xdot(x_eq, u_eq - d)) / (2 * h)
        return a, b, x_eq, u_eq


#: LQR weights.  Rows of X: [phi, phi', theta, theta', psi, psi']; inputs U = [tau_x, F, tau_z, tau_y].
#: R is the inverse square of the input size that costs as much as one unit of state cost: 1.5 N m of roll
#: torque, 1.2 N of thrust variation, 0.3 N m of yaw torque (the rotor drag torque is weak), 1 N m of pitch torque.
#: The closed loops sit at 2 to 4 rad/s, well below the 40 rad/s of the rotor speed loops and the 60 Hz gyro
#: filter, and the torques stay inside the authority of the rotors for errors of several degrees.
Q_DIAG = np.array([40.0, 2.0, 100.0, 3.0, 40.0, 3.0])
R_DIAG = np.array([1.0 / 1.5 ** 2, 1.0 / 1.2 ** 2, 1.0 / 0.3 ** 2, 1.0 / 1.0 ** 2])
THETA_GRID_DEG = np.arange(10.0, 45.1, 5.0)


def lqr_gain(theta_deg: float) -> dict:
    mdl = ContactModel(math.radians(theta_deg))
    a, b, x_eq, u_eq = mdl.linearise()
    q = np.diag(Q_DIAG)
    r = np.diag(R_DIAG)
    # the linearisation decouples exactly into the symmetric (pitch) and antisymmetric (roll, yaw) motion of the
    # plane of symmetry x-z; solve the two blocks so that the structure of K is exact, not rounded
    pitch_x, pitch_u = [2, 3], [1, 3]       # states theta, theta' ; inputs F, tau_y
    ry_x, ry_u = [0, 1, 4, 5], [0, 2]       # states phi, phi', psi, psi' ; inputs tau_x, tau_z
    cross_a = np.abs(a[np.ix_(pitch_x, ry_x)]).max() + np.abs(a[np.ix_(ry_x, pitch_x)]).max()
    cross_b = np.abs(b[np.ix_(pitch_x, ry_u)]).max() + np.abs(b[np.ix_(ry_x, pitch_u)]).max()
    assert cross_a < 1e-6 and cross_b < 1e-6, f"the linearisation does not decouple ({cross_a:.2e}, {cross_b:.2e})"
    k = np.zeros((4, 6))
    for xs, us in ((pitch_x, pitch_u), (ry_x, ry_u)):
        aa, bb = a[np.ix_(xs, xs)], b[np.ix_(xs, us)]
        p = solve_continuous_are(aa, bb, q[np.ix_(xs, xs)], r[np.ix_(us, us)])
        kk = np.linalg.solve(r[np.ix_(us, us)], bb.T @ p)
        k[np.ix_(us, xs)] = kk
    eig = np.linalg.eigvals(a - b @ k)
    return {"theta_deg": theta_deg, "A": a, "B": b, "K": k, "x_eq": x_eq, "u_eq": u_eq, "eig": eig,
            "open_eig": np.linalg.eigvals(a), "model": mdl}


def contact_design(report: list[str]) -> dict:
    table = [lqr_gain(t) for t in THETA_GRID_DEG]
    for t in table:
        assert max(t["eig"].real) < -0.5, f"closed loop not stable at {t['theta_deg']} deg"
        # exact sparsity of the paper: roll/yaw columns only in the tau_x, tau_z rows; pitch columns only in F, tau_y
        k = t["K"]
        assert np.all(k[[0, 2]][:, [2, 3]] == 0.0) and np.all(k[[1, 3]][:, [0, 1, 4, 5]] == 0.0)
    ex = ContactModel(math.radians(20.0))
    x_eq, u_eq = ex.equilibrium()
    report.append(
        f"contact model (theta_sp 20 deg): composite mass {ex.m:.2f} kg, joint-to-CoM e = {np.round(ex.e, 4).tolist()} m, "
        f"I_E = diag {np.round(np.diag(ex.ie), 4).tolist()} kg m^2"
    )
    report.append(
        f"equilibrium U_eq(20 deg): F = {u_eq[1]:.3f} N (m g / cos theta = {ex.m * G / math.cos(math.radians(20)):.3f}), "
        f"tau_y = {u_eq[3]:.3f} N m (-m_arm g L/2 = {-M_ARM * G * L_M / 2:.3f}), wall force m g tan theta = {ex.m * G * math.tan(math.radians(20)):.2f} N"
    )
    for t in table:
        if t["theta_deg"] in (10.0, 20.0, 30.0, 45.0):
            ev = np.sort_complex(t["eig"])
            ol = np.sort_complex(t["open_eig"])
            report.append(
                f"  theta_sp {t['theta_deg']:4.1f} deg: open-loop poles {np.round(ol, 2).tolist()} -> closed loop "
                + ", ".join(f"{e.real:.2f}{e.imag:+.2f}j" for e in ev)
            )
    for deg in (20.0, 27.0):
        t = lqr_gain(deg)
        report.append(f"K({deg:g} deg) rows [tau_x, F, tau_z, tau_y], columns [phi phi' theta theta' psi psi']:")
        for name, row in zip(("tau_x", "F    ", "tau_z", "tau_y"), t["K"]):
            report.append("    " + name + " " + " ".join(f"{v:9.4f}" for v in row))
    return {"table": table}


def build() -> tuple[dict, list[str]]:
    """All model parameters (strings in the model-document format) and the derivation report."""
    report: list[str] = []
    m_alloc, minv = allocation()
    assert np.allclose(m_alloc @ minv, np.eye(4)), "allocation matrix is not invertible"
    wh = omega_hover()
    report.append(
        f"hexarotor {N_ROT} x (10x4.5 in, 950 Kv, 16 V): total mass {M_TRUE:.2f} kg (multirotor {M_B}, arm {M_ARM}, end-effector {M_EE}); "
        f"hover T = {M_TRUE * G / N_ROT:.2f} N per rotor, w = {wh:.0f} rad/s ({wh * 60 / 2 / math.pi:.0f} rpm); "
        f"T_max {T_MAX:.1f} N = {math.sqrt(T_MAX / KT_PROP):.0f} rad/s, thrust-to-weight {T_MAX_TOTAL / (M_TRUE * G):.2f}"
    )
    tau_ff = -G * (M_ARM * 0.5 * L_M + M_EE * (L_M + EE_CX))
    report.append(f"static CoM-correction torque about y_b (arm {M_ARM} kg at L/2, end-effector {M_EE} kg at L + {EE_CX}): {tau_ff:.3f} N m")
    tau_max = np.array([2.0 * ARM_R * 0.5 * (T_MAX - M_TRUE * G / N_ROT) * 2.0, 2.0 * ARM_R * (T_MAX - M_TRUE * G / N_ROT) * 1.0,
                        6.0 * KQ_PROP / KT_PROP * (T_MAX - M_TRUE * G / N_ROT) * 0.5])
    report.append(f"torque authority at hover (indicative): roll {tau_max[0]:.1f}, pitch {tau_max[1]:.1f}, yaw {tau_max[2]:.3f} N m")
    esc = esc_design(report)
    rate = rate_design(report, esc["bw"])
    outer = outer_design(report, esc["bw"])
    nav = nav_design(report)
    bg, ag = butterworth2(60.0, TS)
    ba, aa = butterworth2(25.0, TS)
    report.append(f"IMU low-pass: gyro 60 Hz b {np.round(bg, 6).tolist()} a {np.round(ag, 6).tolist()}; accel 25 Hz")
    report.append(f"servo: J_load {J_ARM_LOAD:.4f} kg m^2, Kp {SERVO_KP:.2f} N m/rad, Kd {SERVO_KD:.3f} N m s/rad, bandwidth {SERVO_W:.0f} rad/s, limit {SERVO_TAU_MAX} N m")
    contact = contact_design(report)
    ktab = np.array([t["K"].reshape(-1) for t in contact["table"]])      # (n_grid, 24) row-major 4 x 6

    p = {
        "mass": M_TRUE, "J": vec(J_B), "rx": vec(RX), "ry": vec(RY), "spin": vec(SPIN), "onev": vec(np.ones(N_ROT)),
        "Minv": mat(minv),
        "esc": {"Kp": f"{esc['Kp']:.9g}", "Ki": f"{esc['Ki']:.9g}"},
        "rate": {"Kp": vec(rate["Kp"]), "Ki": vec(rate["Ki"]), "Kd": vec(rate["Kd"]),
                 "f_alpha": vec([1.0, 1.0, rate["alpha_yaw"]]), "d_alpha": f"{rate['d_alpha']:.9g}",
                 "tau_max": vec([3.0, 3.0, 0.45]), "i_max": vec([1.0, 1.0, 0.1])},
        "outer": {k: f"{v:.9g}" for k, v in outer.items()},
        "nav": {k: f"{v:.9g}" for k, v in nav.items()},
        "lp": {"bgc": vec(bg), "agc": vec(ag), "bac": vec(ba), "aac": vec(aa)},
        "tau_ff": tau_ff,
        "lqr": {"th": vec(np.deg2rad(THETA_GRID_DEG)), "Ktab": mat(ktab), "n": len(THETA_GRID_DEG),
                "sa": vec([max(t["eig"].real) for t in contact["table"]]),
                "tau_y_eq": -M_ARM * G * L_M / 2.0},
    }
    return p | {"_contact": contact}, report


PARAMS, REPORT = build()


def main() -> int:
    print("aerial-contact design report")
    print("-" * 28)
    for line in REPORT:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
