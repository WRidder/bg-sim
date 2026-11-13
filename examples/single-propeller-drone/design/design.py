# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Reference numbers for the single-propeller drone.

This is a **swashplateless** mono-rotor: one motor, no servos. The motor torque is modulated
once per revolution; the rotor accelerates and decelerates within every turn, the lag-pitch
hinges turn that acceleration into a cyclic blade pitch, and the unequal lift of the two blades
gives a hub moment about the body x and y axes. Throttle is rotor speed. There is no yaw
actuator: four fins in the slipstream carry the motor reaction and damp the yaw rate.

Everything the model and the checks need is derived here, and `build_model.py` imports it:

* the mass properties from a parts list placed about the true centre of mass, with the spinning
  rotor's axial inertia `Ja` kept out of the body inertia (it lives in `PropRotor`);
* the hover trim: the slipstream from momentum theory, the fin incidence that balances the
  motor reaction, the fin download and the rotor speed that carries weight plus download;
* the passive yaw time constant (Jz + Ja)/D from the linearised fin law;
* the electrical operating point of the drive (motor, inverter, 6S pack);
* the control gains from stated targets, checked on a linear model of one tilt axis;
* the free nutation frequency of the body plus gyrostat, h/sqrt(Jx Jy);
* the touchdown: the flat impact with the drive's sampled foot-load law, the one-foot
  pivot, the unload, and the wind landing bounds.

The fin law below is a Python twin of `library/FinSet.jl`; keep the two in step.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

G = 9.81
RHO = 1.225

# --------------------------------------------------------------------------- rotor
R_PROP = 0.1524               # m   12 inch two-blade propeller
A_PROP = math.pi * R_PROP**2  # m^2 disc area
K_T = 4.35e-5                 # N s^2/rad^2  thrust coefficient (CT = 0.162 on the 12 in disc)
K_Q = 1.05e-6                 # N m s^2/rad^2  drag torque coefficient
K_THRUST_CYC = 0.02           # mean thrust lost per (N m)^2 of cyclic torque amplitude

# --------------------------------------------------------------------------- parts list
# Build frame: z up, origin at the centre of the body cylinder. Every part is a point mass plus
# its own inertia about its centre (Ixx = Iyy, Izz). The CoM is computed from this list and all
# model positions are then measured from it.
R_BODY = 0.050                # m   body cylinder radius
H_BODY = 0.26                 # m   body cylinder height
Z_ROTOR_B = 0.19              # m   rotor plane (build frame)
Z_STATOR_B = 0.155            # m   motor stator and mount
FIN_ROOT = 0.055              # m   fin root radius (just off the body)
FIN_TIP = 0.105               # m   fin tip radius: inside the contracted slipstream (checked below)
FIN_CHORD = 0.18              # m   fin chord, along the body axis
Z_FIN_B = -0.06               # m   fin centre (build frame)
FOOT_XY = 0.10                # m   feet at (+-0.10, +-0.10)
Z_FOOT_B = -0.17              # m   foot contact points (build frame)
FOOT_R = 0.009                # m   foot sphere radius (scene only; the contact is the sphere's lowest point)

M_FUS = 0.86                  # kg  body tube, battery, avionics
M_STATOR = 0.08               # kg  motor stator and mount (does not spin)
M_FIN = 0.02                  # kg  each fin
M_LEG = 0.02                  # kg  each leg
M_PROP = 0.035                # kg  propeller (spins)
M_BELL = 0.065                # kg  motor bell and hub (spins)
R_BELL = 0.035                # m   bell radius
M_ROTOR = M_PROP + M_BELL

# spinning inertia about the shaft: a slender two-blade propeller (rod of length 2R) plus a ring
JA = M_PROP * R_PROP**2 / 3.0 + M_BELL * R_BELL**2
# transverse inertia of the rotor about its own centre, averaged over a revolution
JA_T = JA / 2.0

R_FIN = 0.5 * (FIN_ROOT + FIN_TIP)    # m  fin mid-span radius
FIN_SPAN = FIN_TIP - FIN_ROOT
S_FIN = FIN_SPAN * FIN_CHORD          # m^2 area of one fin

feet = [(-FOOT_XY, -FOOT_XY), (FOOT_XY, -FOOT_XY), (FOOT_XY, FOOT_XY), (-FOOT_XY, FOOT_XY)]
fins = [(R_FIN * math.cos(k * math.pi / 2), R_FIN * math.sin(k * math.pi / 2)) for k in range(4)]

# (name, mass, (x, y, z) in the build frame, (Ixx, Iyy, Izz) about the part's own centre, spins?)
PARTS = [
    ("fuselage", M_FUS, (0.0, 0.0, 0.0),
     (M_FUS * (3 * R_BODY**2 + H_BODY**2) / 12, M_FUS * (3 * R_BODY**2 + H_BODY**2) / 12, M_FUS * R_BODY**2 / 2), False),
    ("stator", M_STATOR, (0.0, 0.0, Z_STATOR_B), (0.0, 0.0, M_STATOR * 0.025**2 / 2), False),
    *[(f"fin{k + 1}", M_FIN, (fx, fy, Z_FIN_B), (0.0, 0.0, 0.0), False) for k, (fx, fy) in enumerate(fins)],
    *[(f"leg{k + 1}", M_LEG, (fx, fy, Z_FOOT_B), (0.0, 0.0, 0.0), False) for k, (fx, fy) in enumerate(feet)],
    ("rotor", M_ROTOR, (0.0, 0.0, Z_ROTOR_B), (JA_T, JA_T, JA), True),
]
M = sum(p[1] for p in PARTS)
Z_COM_B = sum(p[1] * p[2][2] for p in PARTS) / M


def _body_inertia() -> tuple[float, float, float]:
    """Inertia of everything that does not spin about the shaft, about the CoM, body axes.

    The rotor's mass and its transverse inertia move with the body, so they are in Jx and Jy;
    its axial inertia `JA` is not in Jz, because `PropRotor` stores the axial spin momentum
    Ja (w_z + w_rel) itself.
    """
    jx = jy = jz = 0.0
    for _name, m, (x, y, z), (ixx, iyy, izz), spins in PARTS:
        zc = z - Z_COM_B
        jx += ixx + m * (y * y + zc * zc)
        jy += iyy + m * (x * x + zc * zc)
        jz += (0.0 if spins else izz) + m * (x * x + y * y)
    return jx, jy, jz


JX, JY, JZ = _body_inertia()

# model positions, measured from the CoM
Z_ROTOR = Z_ROTOR_B - Z_COM_B
Z_FIN = Z_FIN_B - Z_COM_B
Z_FOOT = Z_FOOT_B - Z_COM_B
Z_BODY_C = 0.0 - Z_COM_B      # body cylinder centre
Z_STATOR = Z_STATOR_B - Z_COM_B

# --------------------------------------------------------------------------- slipstream (momentum theory)
D_FIN = Z_ROTOR_B - Z_FIN_B                               # m  fin station below the rotor plane
K_WAKE = 1.0 + D_FIN / math.sqrt(D_FIN**2 + R_PROP**2)    # axial velocity at the fins / induced velocity
R_WAKE = R_PROP / math.sqrt(K_WAKE)                       # m  slipstream radius at the fins
assert FIN_TIP < R_WAKE, "the fin tips must be inside the slipstream"

# --------------------------------------------------------------------------- fin aerodynamics
# Low-aspect-ratio flat plates on the body (the body is a reflection plane, so the effective
# aspect ratio is twice the geometric one). Normal force C_N = a sin(al) cos(al) + b sin(al)|sin(al)|
# (linear lift slope `a` from Helmbold's formula, cross-flow drag `b`), chordwise friction `C_f`,
# spanwise drag `C_r`.
AR_EFF = 2.0 * FIN_SPAN**2 / S_FIN
CLA_FIN = 2 * math.pi * AR_EFF / (2.0 + math.sqrt(AR_EFF**2 + 4.0))
CDN_FIN = 1.2
CF_FIN = 0.02
CR_FIN = 0.05
EPS_V = 1.0e-3


def slipstream(T: float, Q: float, vc: float = 0.0) -> tuple[float, float, float]:
    """Induced velocity at the disc, induced axial wake speed and swirl speed at the fin radius.

    Momentum theory in axial flight at climb speed vc (negative: descent, valid well above the
    vortex-ring state): v_i = -vc/2 + sqrt(vc^2/4 + T / (2 rho A)),  w_a = K_WAKE v_i,
    u_t = Q / (mdot r_f),  mdot = rho A (vc + v_i) (angular momentum flux of the wake = rotor
    torque, uniform r u_t over the wake).
    """
    tp = 0.5 * (T + math.sqrt(T * T + 1.0e-6))       # smooth positive part, as FinSet.jl
    vi = -0.5 * vc + math.sqrt(0.25 * vc * vc + tp / (2 * RHO * A_PROP) + 0.01)
    mdot = RHO * A_PROP * (vc + vi)
    return vi, K_WAKE * vi, Q / (mdot * R_FIN)


def fin_wrench(V, T: float, Q: float, delta: float, wind_b=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Wrench (tx, ty, tz, fx, fy, fz) of the four fins on the body, about the CoM, body axes.

    Python twin of `FinSet.jl`. V = (wx, wy, wz, vx, vy, vz) is the body twist.
    """
    wx, wy, wz, vx, vy, vz = V
    _vi, wa, ut = slipstream(T, Q, vz - wind_b[2])
    sd, cd = math.sin(delta), math.cos(delta)
    out = np.zeros(6)
    for k in range(4):
        phi = k * math.pi / 2
        c, s = round(math.cos(phi)), round(math.sin(phi))
        x, y, z = R_FIN * c, R_FIN * s, Z_FIN
        er = np.array([c, s, 0.0])
        et = np.array([-s, c, 0.0])
        ez = np.array([0.0, 0.0, 1.0])
        vp = np.array([vx + wy * z - wz * y, vy + wz * x - wx * z, vz + wx * y - wy * x])
        air = -wa * ez + ut * et + np.array(wind_b)
        U = air - vp
        Ur, Ut, Uz = float(U @ er), float(U @ et), float(U @ ez)
        Uc = -cd * Uz - sd * Ut
        Un = -sd * Uz + cd * Ut
        q = 0.5 * RHO * S_FIN
        Fn = q * (CLA_FIN * Un * Uc + CDN_FIN * Un * math.sqrt(Un * Un + EPS_V**2))
        Fc = q * CF_FIN * Uc * math.sqrt(Uc * Uc + EPS_V**2)
        Fr = q * CR_FIN * Ur * math.sqrt(Ur * Ur + EPS_V**2)
        Ft = Fn * cd - Fc * sd
        Fz = -Fn * sd - Fc * cd
        F = Fr * er + Ft * et + Fz * ez
        r = np.array([x, y, z])
        out[0:3] += np.cross(r, F)
        out[3:6] += F
    return out


def _solve_trim() -> tuple[float, float, float, float]:
    """Fin incidence delta and hover thrust: fins carry Q, thrust carries weight + fin download.

    Both the fin forces and Q scale with w^2 (the slipstream scales with w), so the incidence that
    balances the torque at hover balances it at every rotor speed.
    """
    T = M * G
    delta = 0.0
    for _ in range(60):
        w = math.sqrt(T / K_T)
        Q = K_Q * w * w
        lo, hi = -0.5, 0.5
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if fin_wrench((0, 0, 0, 0, 0, 0), T, Q, mid)[2] < Q:
                lo = mid
            else:
                hi = mid
        delta = 0.5 * (lo + hi)
        fz = fin_wrench((0, 0, 0, 0, 0, 0), T, Q, delta)[5]
        T = M * G - fz
    w = math.sqrt(T / K_T)
    return delta, T, w, K_Q * w * w


DELTA_FIN, T0, OMEGA0, Q0 = _solve_trim()
F_DOWN = T0 - M * G
VI0, WA0, UT0 = slipstream(T0, Q0)
ALPHA_FIN0 = math.atan2(UT0, WA0) + DELTA_FIN
H_ROTOR = JA * OMEGA0

# passive yaw: D = -d(fin yaw torque)/d(body yaw rate) at the trim; with the rotor-speed loop
# holding the relative speed, the rotor follows the body's yaw acceleration (inertia Jz + Ja) and
# the change of rotor drag with the absolute speed is matched by the change of fin torque (both
# scale with w^2), so the fin rate derivative alone is the damping.
_dr = 1.0e-4
D_YAW = -(fin_wrench((0, 0, _dr, 0, 0, 0), T0, Q0, DELTA_FIN)[2]
          - fin_wrench((0, 0, -_dr, 0, 0, 0), T0, Q0, DELTA_FIN)[2]) / (2 * _dr)
TAU_YAW = (JZ + JA) / D_YAW
# yaw torque in a steady crossflow: four identical fins at 90 deg, so no heading is preferred; the
# torque change is even in the crossflow speed (second order), the same in every direction
DQ_CROSS_1 = fin_wrench((0, 0, 0, 1.0, 0, 0), T0, Q0, DELTA_FIN)[2] - Q0
DQ_CROSS_1_45 = fin_wrench((0, 0, 0, math.sqrt(0.5), math.sqrt(0.5), 0), T0, Q0, DELTA_FIN)[2] - Q0
# pitch moment of the fins in a 1 m/s crossflow along x (they sit below the CoM)
MY_FIN_CROSS_1 = fin_wrench((0, 0, 0, 1.0, 0, 0), T0, Q0, DELTA_FIN)[1]

# lateral derivatives of the fins at hover (per m/s of body velocity along x): the slipstream
# fins act as a linear drag (momentum drag of the plates) and, sitting below the CoM, as a pitch
# moment that tips the body further into the motion
_dv = 1.0e-3
_wp = fin_wrench((0, 0, 0, _dv, 0, 0), T0, Q0, DELTA_FIN)
_wm = fin_wrench((0, 0, 0, -_dv, 0, 0), T0, Q0, DELTA_FIN)
C_LIN_AERO = 0.08                                   # N s/m  AeroWrench's linear drag
C_FIN_X = -(_wp[3] - _wm[3]) / (2 * _dv)            # N s/m  fin drag derivative
M_FIN_V = (_wp[1] - _wm[1]) / (2 * _dv)             # N m s/m pitch moment per m/s
K_DRAG = (C_FIN_X + C_LIN_AERO) / M                 # 1/s  drag feed-forward of the position loop

# rotor H-force (disc drag) above the CoM and body drag: a pitch moment that grows with u^2
C_DD = 0.5
A_BODY = 2 * R_BODY * H_BODY
C_DB = 1.0
Z_BODY_DRAG = Z_BODY_C
MY_DRAG_1 = 0.5 * RHO * (A_PROP * C_DD * Z_ROTOR + A_BODY * C_DB * Z_BODY_DRAG) * 1.0**2

# --------------------------------------------------------------------------- drive and battery
K_MOT = 0.030                 # N m/A  torque and back-EMF constant (Kv about 318 rpm/V)
R_W = 0.08                    # Ohm    winding plus inverter resistance
L_W = 50e-6                   # H      winding inductance
B_M = 3.7e-5                  # N m s/rad  bearing and iron loss, as viscous
P_AUX = 3.0                   # W      avionics (a constant current draw at the nominal voltage)
V_NOM = 22.8                  # V      6S nominal
I_AUX = P_AUX / V_NOM
W_CURRENT = 2 * math.pi * 600.0   # rad/s  current-loop bandwidth of the drive
K_CUR = L_W * W_CURRENT - R_W     # Ohm    current-loop proportional gain
BAT_CAP = 3.0                 # A h
BAT_SOC = [0.0, 0.1, 0.5, 0.9, 1.0]
BAT_OCV = [19.8, 21.6, 22.8, 24.3, 25.2]
BAT_R0 = 0.030
BAT_R1 = 0.010
BAT_C1 = 2000.0

I_MOT0 = (Q0 + B_M * OMEGA0) / K_MOT                 # motor current at hover
V_MOT0 = K_MOT * OMEGA0 + R_W * I_MOT0               # inverter output voltage at hover
P_SHAFT0 = Q0 * OMEGA0
I_BAT0 = None                                        # solved with the pack voltage below
V_BUS0 = BAT_OCV[-1]
for _ in range(50):
    I_BAT0 = V_MOT0 * I_MOT0 / V_BUS0 + I_AUX
    V_BUS0 = BAT_OCV[-1] - (BAT_R0 + BAT_R1) * I_BAT0
P_BAT0 = V_BUS0 * I_BAT0
ETA0 = P_SHAFT0 / (V_MOT0 * I_MOT0)
# the hover model's checks average over 6-8 s: by the middle (7 s) the pack has given
# I_BAT0 * 7 s of its charge, and the OCV table falls 9 V per unit of charge near full
T_BAT_MID = 7.0
SOC_MID = 1.0 - I_BAT0 * T_BAT_MID / (BAT_CAP * 3600.0)
OCV_MID = float(np.interp(SOC_MID, BAT_SOC, BAT_OCV))
I_BAT_MID, V_BUS_MID = I_BAT0, V_BUS0
for _ in range(50):
    I_BAT_MID = V_MOT0 * I_MOT0 / V_BUS_MID + I_AUX
    V_BUS_MID = OCV_MID - (BAT_R0 + BAT_R1) * I_BAT_MID
P_BAT_MID = V_BUS_MID * I_BAT_MID

# --------------------------------------------------------------------------- cyclic actuation
# hub moment law (PropRotor): M = 2 kM tau_net (cos psi, sin psi), tau_net = motor torque minus
# drag (= Ja dw/dt). With tau_net = cx cos psi + cy sin psi the mean over a revolution is
# kM (cx, cy). kM is an assumed value (no bench data); the allocation uses its own estimate.
K_M = 0.25                    # plant: hub moment per N m of cyclic torque amplitude (global cyclic_gain)
K_M_EST = 0.25                # the allocation's fixed estimate of the same gain
A_MAX = 0.8                   # N m cyclic torque amplitude limit (global cyclic_limit)
M_MAX = K_M_EST * A_MAX       # N m hub-moment limit seen by the rate loop
D_OMEGA = A_MAX / (JA * OMEGA0)   # rad/s speed ripple amplitude at full cyclic

# --------------------------------------------------------------------------- control design
# Targets (one tilt axis, the gyroscopic coupling removed by the rate loop's feed-forward
# w x (h e_z) with h = Ja_est w_rotor):
#   rate loop      crossover 20 rad/s, PI zero a quarter of that
#   attitude loop  5 rad/s (a factor 4 below the rate loop)
#   velocity loop  2 rad/s, position loop 0.6 rad/s (factors 2.5 to 3.5)
#   every closed-loop mode damped with zeta >= 0.7, delays of the discrete loops included
#   the mission's jerk is fed forward as a tilt-rate set-point (j/g), so a min-jerk move is
#   tracked within about 1 cm by the linear model instead of lagging the attitude loop
W_RATE = 20.0
KP_RATE = JX * W_RATE
KI_RATE = KP_RATE * W_RATE / 4.0
K_ATT = 5.0
KV_XY = 2.0
KI_XY = 0.8
KP_XY = 0.6
KV_Z = 4.0
KI_Z = 2.0
KP_Z = 1.5
TILT_MAX = 0.20               # rad  tilt limit of the thrust vector (global tilt_limit)
T_INNER = 0.006               # s  delay of the 400 Hz rate path (gyro filter, nav, ZOH, allocation)
T_OUTER = 0.025               # s  delay of the 50 Hz position path (ZOH and one-tick latency)


def axis_model(kp_r=KP_RATE, ki_r=KI_RATE, k_att=K_ATT, kv=KV_XY, ki=KI_XY, kp=KP_XY,
               t_in=T_INNER, t_out=T_OUTER, j=JX):
    """Linear model of one horizontal axis: A and the input matrix for the set-point.

    States: x, v, th, q, Ir (rate integral), Iv (velocity integral), d1 (inner delay), d2 (outer
    delay of the tilt command), d3 (outer delay of the tilt-rate feed-forward). The delays are
    first-order lags. Inputs: x_sp, v_sp, a_sp, j_sp.
    """
    n = 9
    A = np.zeros((n, n))
    B = np.zeros((n, 4))
    X, V, TH, Q, IR, IV, D1, D2, D3 = range(n)
    # plant: v' = g th - (c/m) v, th' = q, J q' = tau + M_v v (tau = d1, the delayed torque);
    # c and M_v are the fin and airframe lateral derivatives; the position loop's drag
    # feed-forward (PosCtrl.k_drag) is set to the same c/m = K_DRAG
    A[X, V] = 1.0
    A[V, TH] = G
    A[V, V] = -K_DRAG
    A[TH, Q] = 1.0
    A[Q, D1] = 1.0 / j
    A[Q, V] = M_FIN_V / j
    # outer loop: a_cmd = a_sp + kv (v_sp + kp (x_sp - x) - v) + Iv; th_cmd = a_cmd / g, delayed (d2)
    # Iv' = ki (v_sp + kp (x_sp - x) - v)
    A[IV, X] = -ki * kp
    A[IV, V] = -ki
    B[IV, 0] = ki * kp
    B[IV, 1] = ki
    # d2' = (th_cmd - d2) / t_out
    A[D2, X] = -kv * kp / G / t_out
    A[D2, V] = -kv / G / t_out
    A[D2, IV] = 1.0 / G / t_out
    A[D2, D2] = -1.0 / t_out
    B[D2, 0] = kv * kp / G / t_out
    B[D2, 1] = kv / G / t_out
    B[D2, 2] = 1.0 / G / t_out
    # drag feed-forward kd v_sp in the acceleration command
    B[D2, 1] += K_DRAG / G / t_out
    # tilt-rate feed-forward j/g through the outer delay: d3' = (j/g - d3) / t_out
    A[D3, D3] = -1.0 / t_out
    B[D3, 3] = 1.0 / G / t_out
    # attitude: q_sp = k_att (d2 - th) + d3; rate PI: tau = kp_r (q_sp - q) + Ir, delayed (d1)
    A[IR, D3] = ki_r
    A[D1, D3] = kp_r / t_in
    A[IR, D2] = ki_r * k_att
    A[IR, TH] = -ki_r * k_att
    A[IR, Q] = -ki_r
    A[D1, D2] = kp_r * k_att / t_in
    A[D1, TH] = -kp_r * k_att / t_in
    A[D1, Q] = -kp_r / t_in
    A[D1, IR] = 1.0 / t_in
    A[D1, D1] = -1.0 / t_in
    return A, B


def modes(A) -> tuple[np.ndarray, float]:
    ev = np.linalg.eigvals(A)
    damp = -ev.real / np.maximum(np.abs(ev), 1e-12)
    return ev, float(damp.min())


def smooth_step(t: float, t0: float, dur: float, dx: float) -> tuple[float, float, float, float]:
    """Position, velocity, acceleration and jerk of the mission's move (as `Waypoints`): the
    7th-order smooth step s^4 (35 - 84 s + 70 s^2 - 20 s^3), zero velocity, acceleration and
    jerk at both ends, so the tilt-rate feed-forward j/g starts and ends at zero."""
    s = min(max((t - t0) / dur, 0.0), 1.0)
    p = dx * s**4 * (35 - 84 * s + 70 * s * s - 20 * s**3)
    v = dx * 140 * s**3 * (1 - s) ** 3 / dur
    a = dx * 420 * s * s * (1 - s) ** 2 * (1 - 2 * s) / dur**2
    j = dx * 840 * s * (1 - s) * (5 * s * s - 5 * s + 1) / dur**3
    return p, v, a, j


# the hover model's lateral step: 1 m along x, starting at STEP_T0, over STEP_DUR, run to STEP_T_END
STEP_T0 = 3.0
STEP_DUR = 2.5
STEP_DX = 1.0
STEP_T_END = 8.0


def simulate_step(A, B, t0=STEP_T0, dur=STEP_DUR, dx=STEP_DX, t_end=STEP_T_END, dt=2e-4, d=0.0) -> dict[str, float]:
    """The hover model's 1 m step through the linear axis model (RK4), with an optional constant
    acceleration disturbance `d` (m/s^2) acting from t = 0."""
    x = np.zeros(A.shape[0])
    worst_err, peak = 0.0, 0.0
    t = 0.0
    dv = np.zeros(A.shape[0])
    dv[1] = d

    def f(tt, xx):
        return A @ xx + B @ np.array(smooth_step(tt, t0, dur, dx)) + dv

    while t < t_end - 1e-12:
        k1 = f(t, x)
        k2 = f(t + dt / 2, x + dt / 2 * k1)
        k3 = f(t + dt / 2, x + dt / 2 * k2)
        k4 = f(t + dt, x + dt * k3)
        x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt
        worst_err = max(worst_err, abs(x[0] - smooth_step(t, t0, dur, dx)[0]))
        peak = max(peak, x[0])
    return {"worst_err": worst_err, "overshoot": peak - dx, "x_end": float(x[0])}


A_AXIS, B_AXIS = axis_model()
EV_AXIS, DAMP_AXIS = modes(A_AXIS)
STEP = simulate_step(A_AXIS, B_AXIS)

# The IMU's accelerometer bias (ImuSensor.bias_a, body axes). The vertical part is estimated by
# the navigation filter; the horizontal part cannot be told from a tilt, so the vehicle really
# leans by about b/g and the position loop sees a constant acceleration disturbance of up to
# |b_h| (its direction in the world turns with the heading). The step with that disturbance in
# the worse sign bounds what the simulation can show.
ACC_BIAS = (0.05, -0.04, 0.08)
B_H = math.hypot(ACC_BIAS[0], ACC_BIAS[1])
_steps_b = [simulate_step(A_AXIS, B_AXIS, d=sg * B_H) for sg in (1.0, -1.0)]
STEP_BIAS = {
    "worst_err": max(r["worst_err"] for r in _steps_b),
    "overshoot": max(r["overshoot"] for r in _steps_b),
    "x_end_dev": max(abs(r["x_end"] - STEP_DX) for r in _steps_b),
}
# the flight model's two legs: LEG_DX along x from LEG_T0[0], then along y from LEG_T0[1]
LEG_DX = 1.5
LEG_DUR = 3.0
LEG_T0 = (2.0, 6.0)
_legs_b = [simulate_step(A_AXIS, B_AXIS, t0=LEG_T0[0], dur=LEG_DUR, dx=LEG_DX, t_end=LEG_T0[1], d=sg * B_H)
           for sg in (1.0, -1.0)]
LEG_BIAS = {
    "worst_err": max(r["worst_err"] for r in _legs_b),
    "overshoot": max(r["overshoot"] for r in _legs_b),
}

# the gyroscopic coupling without the feed-forward: two axes, J p' = tau_x - h q, J q' = tau_y + h p
W_NUT = H_ROTOR / math.sqrt(JX * JY)


def coupled_rate_modes(decouple: bool) -> tuple[np.ndarray, float]:
    """Attitude + rate loops of both tilt axes with the rotor momentum h, with or without the
    feed-forward. States: phi, theta, p, q, Ix, Iy (no delays; this is about the coupling)."""
    h = H_ROTOR
    hf = h if decouple else 0.0
    A = np.zeros((6, 6))
    PHI, TH, P, Qr, IX, IY = range(6)
    A[PHI, P] = 1.0
    A[TH, Qr] = 1.0
    # tau_x = kp (k_att (0 - phi) - p) + Ix + hf q ;  J p' = tau_x - h q
    A[P, PHI] = -KP_RATE * K_ATT / JX
    A[P, P] = -KP_RATE / JX
    A[P, IX] = 1.0 / JX
    A[P, Qr] = (hf - h) / JX
    A[Qr, TH] = -KP_RATE * K_ATT / JY
    A[Qr, Qr] = -KP_RATE / JY
    A[Qr, IY] = 1.0 / JY
    A[Qr, P] = (h - hf) / JY
    A[IX, PHI] = -KI_RATE * K_ATT
    A[IX, P] = -KI_RATE
    A[IY, TH] = -KI_RATE * K_ATT
    A[IY, Qr] = -KI_RATE
    return modes(A)


EV_COUPLED_OFF, DAMP_COUPLED_OFF = coupled_rate_modes(False)
EV_COUPLED_ON, DAMP_COUPLED_ON = coupled_rate_modes(True)

# rotor speed loop: Ja s + dQ/dw (+ bearing loss), PI
DQDW = 2 * K_Q * OMEGA0 + B_M
KP_ESC = 0.03
KI_ESC = 0.5
ACCEL_ESC = 260.0             # rad/s^2  the speed loop's reference acceleration limit


def esc_loop_margins(kp=KP_ESC, ki=KI_ESC) -> tuple[float, float]:
    """Crossover and phase margin of the rotor speed PI loop."""
    w = np.logspace(-1, 4, 200000)
    s = 1j * w
    L = (kp + ki / s) / (JA * s + DQDW)
    mag = np.abs(L)
    i = int(np.argmin(np.abs(mag - 1.0)))
    ph = np.degrees(np.angle(L))
    return float(w[i]), float(180.0 + ph[i])


W_ESC, PM_ESC = esc_loop_margins()


def butterworth2(fc: float, ts: float) -> tuple[list[float], list[float]]:
    """Second-order Butterworth low-pass (bilinear transform): b0 b1 b2 and a1 a2."""
    k = math.tan(math.pi * fc * ts)
    norm = 1.0 / (1.0 + math.sqrt(2.0) * k + k * k)
    b0 = k * k * norm
    return [b0, 2.0 * b0, b0], [2.0 * (k * k - 1.0) * norm, (1.0 - math.sqrt(2.0) * k + k * k) * norm]


BGC, AGC = butterworth2(80.0, 2e-3)
BAC, AAC = butterworth2(30.0, 2e-3)

# --------------------------------------------------------------------------- landing gear
K_CONTACT = 2.0e4             # N/m per foot (Hertz stiffness: k x (x/xref)^(1/2), xref = 1 mm)
# Damped feet (rubber pads): Hunt-Crossley damping F = Fk (1 + c xdot). The pads are sized for a
# coefficient of restitution e = 0.2 at the land-mode speed with the relation of Flores et al.
# (2011), c = 8 (1 - e) / (5 e v), which holds for low e too (Hunt and Crossley's 3 (1 - e)/(2 v)
# is a small-damping approximation); the impact simulation below checks it.
E_FEET = 0.2
Z_CONTACT = -Z_FOOT           # m  CoM height when the feet touch the ground
HOVER_Z = 1.32                # m  hover height of both models (CoM)
T_LAND = 10.0                 # s  the flight model's land mode starts here, from the hover height ...
V_LAND = 0.25                 # m/s ... and descends at this speed until touchdown
T_RAMP = 1.0                  # s  over which the land-mode speed is ramped in
# CoM height at which the land-mode descent (ramp: half of t_ramp at full speed) meets the ground
T_TO_CONTACT = T_RAMP + (HOVER_Z - Z_CONTACT - 0.5 * V_LAND * T_RAMP) / V_LAND
T_CONTACT = T_LAND + T_TO_CONTACT


def _descent_yaw_rate(vz: float) -> float:
    """Steady yaw rate in a steady vertical speed vz (body z): the fin torque balances Q0 again.

    Only the swirl changes (the mass flow through the disc is rho A (vc + v_i)); the rotor speed
    and thrust stay at the trim."""
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if fin_wrench((0, 0, mid, 0, 0, vz), T0, Q0, DELTA_FIN)[2] > Q0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


R_DESCENT = _descent_yaw_rate(-V_LAND)

# touchdown: four Hertz contacts F = k x (x/xref)^(1/2) per foot hit together at V_LAND with the
# thrust carrying the weight (a free impact). Without damping, (1/2) m v^2 = (2/5) K4 x^(5/2) with
# K4 = 4 k / sqrt(xref), so the peak force is K4 x^(3/2). The pads' damping adds a force
# proportional to the penetration rate, so the damped peak (`impact` below) is higher; a slightly
# tilted body (the feet do not all touch at once) lowers it.
C_CONTACT = 8 * (1 - E_FEET) / (5 * E_FEET * V_LAND)
K_HERTZ4 = 4 * K_CONTACT / math.sqrt(1.0e-3)
X_IMPACT = (5 * M * V_LAND**2 / (4 * K_HERTZ4)) ** 0.4
F_IMPACT = K_HERTZ4 * X_IMPACT**1.5


def impact(v: float, c: float, dt: float = 2.0e-7) -> tuple[float, float, float]:
    """Vertical touchdown of the rigid body on four Hunt-Crossley feet at speed v, the thrust
    carrying the weight: m x'' = -K4 x^(3/2) (1 + c x'). Returns the peak force, the
    coefficient of restitution and the contact duration."""
    x, xd, fmax, t = 0.0, v, 0.0, 0.0

    def acc(x, xd):
        return -K_HERTZ4 * max(x, 0.0) ** 1.5 * max(1.0 + c * xd, 0.0) / M

    while True:
        k1x, k1v = xd, acc(x, xd)
        k2x, k2v = xd + dt / 2 * k1v, acc(x + dt / 2 * k1x, xd + dt / 2 * k1v)
        k3x, k3v = xd + dt / 2 * k2v, acc(x + dt / 2 * k2x, xd + dt / 2 * k2v)
        k4x, k4v = xd + dt * k3v, acc(x + dt * k3x, xd + dt * k3v)
        x += dt / 6 * (k1x + 2 * k2x + 2 * k3x + k4x)
        xd += dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
        t += dt
        fmax = max(fmax, -M * acc(x, xd))
        if x <= 0.0:
            return fmax, -xd / v, t


F_IMPACT_D, E_IMPACT, T_IMPACT = impact(V_LAND, C_CONTACT)
# at rest on the four feet (rotor stopped): each Hertz contact carries m g / 4
X_STATIC = (M * G / K_HERTZ4) ** (2.0 / 3.0)
Z_REST = Z_CONTACT - X_STATIC

# on the ground the speed loop runs the rotor down at ACCEL_ESC; the fins still carry the drag
# torque, so the body feels the rotor's deceleration torque Ja * ACCEL_ESC. The feet's friction
# can hold mu * m g * r_foot once the thrust is gone.
MU_FEET = 0.8
TAU_RUNDOWN = JA * ACCEL_ESC
TAU_FRICTION = MU_FEET * M * G * math.hypot(FOOT_XY, FOOT_XY)

# Touchdown. In the descent the thrust carries the weight, so the rebound of the feet would float
# the body, and taking the thrust off means slowing the rotor. The fins carry the drag torque Q
# in any state, so the only unbalanced yaw torque on the body is the rotor's change of
# angular momentum: whatever speed the rotor loses while the feet do not hold the body goes into
# the body's yaw, Jz dr = -Ja dW (Ja/Jz = 0.109 rad/s per rad/s). What holds the body:
#  * two loaded feet a distance s apart hold a yaw torque mu s min(N_a, N_b) as a friction
#    couple (four equal feet: mu r_foot F_n in total);
#  * one loaded foot holds no torque. The body pivots about it, with the yaw inertia
#    Jz + m r_foot^2 instead of Jz (a factor K_PIVOT);
#  * feet in the air hold nothing.
# The drive therefore reads the foot loads (FootSensor, at its own 400 Hz) and never changes the
# rotor speed faster than a fraction GAMMA_FR of what the last samples hold:
#  * touchdown brake: on the first tick with a total load above F_TOUCH the drive caps the speed
#    at K_TD times its reference and slews down to the cap at up to ACCEL_TD (inside the torque
#    limit TAU_MIN_ESC), limited by the total load: Ja a <= K_MU_ESC r_foot (F - 4 f_min).
#    This brake does not wait for a second foot, because until it is done the thrust carries
#    the whole weight; on one foot it costs the pivot's share (R_PIVOT below);
#  * after the brake: only the load that two feet share counts (RotorEsc's pairing), and the
#    slew is at most ACCEL_ESC. In the air or on one foot the speed stays where it is;
#  * the mission's ground thrust fraction falls from 1 to 0 along the smooth step over
#    T_UNLOAD from its touchdown latch, and scales the drive's cap. The drive follows as the
#    feet take the weight m g (1 - x^2), x = w / w_touchdown, never above GAMMA_FR of the
#    friction the settled feet give.
# Until the weight is on the feet the vehicle still flies: the position and attitude loops keep
# the horizontal axes (the lean into a wind), only the vertical channel is frozen.
F_TOUCH = 2.0                 # N  total foot load that counts as touchdown (sensor, drive)
SIGMA_FOOT = 0.03             # N  white noise of one foot's load sample
F_MIN_FOOT = 0.1              # N  load below which the drive counts a foot as unloaded (3.3 sigma)
K_TD = 0.97                   # fraction of the rotor speed kept at touchdown
TAU_MIN_ESC = -1.2            # N m  braking torque limit of the drive (the drive's limit is 1.6 N m)
TAU_BRAKE_REACT = Q0 + B_M * OMEGA0 - TAU_MIN_ESC      # N m  yaw torque on the body at the braking limit
A_BRAKE_MAX = TAU_BRAKE_REACT / JA                     # rad/s^2  deceleration at the torque limit
ACCEL_TD = 4000.0             # rad/s^2  largest slew of the speed reference while braking
assert ACCEL_TD < A_BRAKE_MAX
T_TICK_ESC = 2.5e-3           # s  the drive's and the foot sensor's tick
T_TICK_MISSION = 20e-3        # s  the mission's tick
N_TOUCH_HOLD = round(T_TICK_MISSION / T_TICK_ESC)      # ticks the sensor holds its touch flag
R_FOOT = math.hypot(FOOT_XY, FOOT_XY)                  # m  foot radius from the body axis
GAMMA_FR = 0.5                # fraction of the feet's friction the drive counts on
K_MU_ESC = GAMMA_FR * MU_FEET
T_UNLOAD = 1.0                # s  the mission's ground thrust fraction falls to 0 over this time
T_SPIN = 2.0                  # s  motor off this long after `landed`
F_LAND = 0.5 * M * G          # N  sensed foot load that counts as landed (half the weight) ...
N_LAND = 5                    # ... for this many mission ticks in a row
K_GROUND = 1.0                # the attitude loop keeps its proportional authority on the ground
T_YAW_MEAN = 0.025            # s  lag of the yaw-rate read-out YawMean (about two revolutions)
K_PIVOT = JZ / (JZ + M * R_FOOT**2)                    # yaw rate of a body pivoting on one foot / free body
V_REB = E_FEET * V_LAND       # m/s  rebound at the pads' design restitution


def touchdown_flat(phase: float, dt: float = 1.0e-6) -> dict[str, float]:
    """The flat touchdown with the drive's sampled law: four equal Hunt-Crossley feet hit at
    V_LAND with the thrust carrying the weight, m x'' = m g (1 - xi^2) - F(x, x'), xi the rotor
    speed over its touchdown value. The drive samples F every T_TICK_ESC, first `phase` after
    the first contact, latches above F_TOUCH and slews xi down to K_TD at
    a = min(ACCEL_TD, K_MU_ESC R_FOOT (F_k - 4 F_MIN_FOOT) / Ja), held over the tick (the rotor
    follows its reference: ACCEL_TD is inside the torque limit).

    Returns the peak force, the latch time, the rotor speed lost while the reaction Ja a exceeds
    the feet's friction mu R_FOOT F(t) (rad/s), xi and the rebound speed at lift-off, and the
    contact duration."""
    x, xd, xi, t = 0.0, V_LAND, 1.0, 0.0
    a, t_next, latched, t_latch = 0.0, phase, False, float("nan")
    fmax, dw_unheld = 0.0, 0.0
    while True:
        f = K_HERTZ4 * max(x, 0.0) ** 1.5 * max(1.0 + C_CONTACT * xd, 0.0)
        if t >= t_next:
            t_next += T_TICK_ESC
            if not latched and f > F_TOUCH:
                latched, t_latch = True, t
            a = 0.0
            if latched and xi > K_TD:
                a = min(ACCEL_TD, K_MU_ESC * R_FOOT * max(f - 4.0 * F_MIN_FOOT, 0.0) / JA,
                        (xi - K_TD) * OMEGA0 / T_TICK_ESC)
        fmax = max(fmax, f)
        if a > 0.0:
            xi -= a * dt / OMEGA0
            dw_unheld += max(0.0, JA * a - MU_FEET * R_FOOT * f) / JA * dt
        acc = G * (1.0 - xi * xi) - f / M
        x += xd * dt + 0.5 * acc * dt * dt
        xd += acc * dt
        t += dt
        if x <= 0.0:
            return {"f_peak": fmax, "t_latch": t_latch, "dw_unheld": dw_unheld, "xi": xi, "v_reb": -xd, "t": t}


# The tick phase is not known, so the bounds take the worst of a scan over one tick. The hop
# uses the rebound of the scan or the pads' design restitution, whichever is larger, against
# the net downward acceleration g (1 - xi^2) the brake has reached at lift-off.
TD_SCAN = [touchdown_flat((k + 0.5) / 20.0 * T_TICK_ESC) for k in range(20)]
T_DETECT = max(r["t_latch"] for r in TD_SCAN)            # s  latest latch after the first contact
DW_UNHELD = max(r["dw_unheld"] for r in TD_SCAN)         # rad/s
R_LAND_FLAT = JA / JZ * DW_UNHELD                        # rad/s  yaw the flat brake can leave
XI_LIFT = max(r["xi"] for r in TD_SCAN)                  # rotor speed fraction at lift-off, worst
H_HOP = max(max(r["v_reb"], V_REB) ** 2 / (2.0 * G * (1.0 - r["xi"] ** 2)) for r in TD_SCAN)
T_HOP = max(2.0 * max(r["v_reb"], V_REB) / (G * (1.0 - r["xi"] ** 2)) for r in TD_SCAN)
F_SENSED_MAX = max(r["f_peak"] for r in TD_SCAN)         # N  (the sensor cannot read more than the true peak)
# one foot first (a leaning vehicle): the whole brake acts on a body pivoting about that foot,
# and so does the yaw rate it arrives with
R_PIVOT = JA * (1.0 - K_TD) * OMEGA0 / (JZ + M * R_FOOT**2)
# the once-per-revolution cyclic torque (amplitude up to A_MAX) shakes the body in yaw against
# the rotor: a ripple of A_MAX / (Jz w) in the yaw rate, with zero mean. YawMean, a first-order
# lag over T_YAW_MEAN, passes 1/sqrt(1 + (w T)^2) of it.
R_RIPPLE = A_MAX / (JZ * K_TD * OMEGA0)
R_RIPPLE_MEAN = R_RIPPLE / math.sqrt(1.0 + (K_TD * OMEGA0 * T_YAW_MEAN) ** 2)


def unload_time(dt: float = 1.0e-4) -> tuple[float, float, float]:
    """The unload on settled, equally loaded feet, from the mission's latch (t = 0, x = K_TD).

    The target is x = K_TD sqrt(1 - S(t / T_UNLOAD)); the drive follows at no more than
    ACCEL_ESC and no more than its own limit Ja a <= K_MU_ESC R_FOOT (m g (1 - x^2) - 4 f_min).
    The first T_IMPACT + T_HOP are skipped (the feet may be in the air: nothing happens).
    Returns the time at which the feet carry F_LAND (and the schedule has ended), the time the
    rotor reaches the end of the schedule's range, and the largest ratio of the rotor's
    deceleration torque to the feet's friction."""
    t, x, worst, t_land = 0.0, K_TD, 0.0, None
    x_idle = 90.0 / OMEGA0
    while x > x_idle + 1e-9 or t_land is None:
        t += dt
        s = min(t / T_UNLOAD, 1.0)
        target = max(K_TD * math.sqrt(max(1.0 - s**4 * (35 - 84 * s + 70 * s * s - 20 * s**3), 0.0)), x_idle)
        load = M * G * (1.0 - x * x)
        if t > T_IMPACT + T_HOP:
            a = min(ACCEL_ESC, K_MU_ESC * R_FOOT * max(load - 4.0 * F_MIN_FOOT, 0.0) / JA, max(x - target, 0.0) * OMEGA0 / dt)
            x -= a * dt / OMEGA0
            if a > 0.0:
                worst = max(worst, JA * a / (MU_FEET * R_FOOT * load))
        if t_land is None and s >= 1.0 and M * G * (1.0 - x * x) > F_LAND:
            t_land = t
    return t_land, t, worst


T_FEET_LAND, T_RUNDOWN, UNLOAD_RATIO = unload_time()
assert UNLOAD_RATIO <= GAMMA_FR + 1e-9, "the drive's own limit keeps the unload inside the feet's friction"
# `landed` at the latest: contact (as late as the zero-crossing check allows) + the drive's latch
# + one mission tick + the unload until the feet carry F_LAND + N_LAND ticks + one tick
T_LANDED_MAX = T_CONTACT + 0.03 + T_DETECT + T_TICK_MISSION + T_FEET_LAND + (N_LAND + 1) * T_TICK_MISSION


def lean(wind: float) -> float:
    """Tilt of the vehicle holding its position in a steady horizontal wind: drag / weight (the
    fins' and airframe's linear drag, the rotor disc and body drag), plus the lean the
    horizontal accelerometer bias causes."""
    drag = (C_FIN_X + C_LIN_AERO) * wind + 0.5 * RHO * (A_PROP * C_DD + A_BODY * C_DB) * wind * wind
    return math.atan2(drag, M * G) + B_H / G


def _descent_yaw_rate_wind(vz: float, wind: float) -> float:
    """As `_descent_yaw_rate`, with a horizontal wind (body axes, the lean neglected)."""
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if fin_wrench((0, 0, mid, 0, 0, vz), T0, Q0, DELTA_FIN, (wind, 0.0, 0.0))[2] > Q0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# The wind landing checks (1 m/s along x, and along y). The vehicle leans, so one foot touches
# first. Bounds:
#  * yaw rate (YawMean): what it arrives with (the descent yaw in that wind, with the 6 % of
#    the descent check), plus the brake on one foot, plus the ripple the read-out passes. A
#    foot alone does not stop the arrival yaw, so it stays in the bound;
#  * height: one foot on the ground at the lean raises the CoM by R_FOOT sin(lean); the hop is
#    added to that.
W_CHECK = 1.0
LEAN_W = lean(W_CHECK)
R_DESCENT_W = _descent_yaw_rate_wind(-V_LAND, W_CHECK)
R_LAND_WIND = 1.06 * R_DESCENT_W + R_PIVOT + R_RIPPLE_MEAN
Z_HOP_WIND = Z_CONTACT + R_FOOT * math.sin(LEAN_W) + H_HOP

DATA = {
    "g": G, "rho": RHO, "m": M, "m_rotor": M_ROTOR,
    "parts": [{"name": p[0], "m": p[1], "pos_build": list(p[2])} for p in PARTS],
    "z_com_build": Z_COM_B,
    "Jx": JX, "Jy": JY, "Jz": JZ, "Ja": JA,
    "z_rotor": Z_ROTOR, "z_fin": Z_FIN, "z_foot": Z_FOOT, "r_body": R_BODY, "h_body": H_BODY,
    "r_fin": R_FIN, "fin_span": FIN_SPAN, "fin_chord": FIN_CHORD, "S_fin": S_FIN, "r_prop": R_PROP,
    "kT": K_T, "kQ": K_Q, "k_thrust_cyc": K_THRUST_CYC,
    "k_wake": K_WAKE, "r_wake": R_WAKE, "cla_fin": CLA_FIN, "ar_eff": AR_EFF,
    "delta_fin": DELTA_FIN, "alpha_fin0": ALPHA_FIN0,
    "T0": T0, "F_down": F_DOWN, "omega0": OMEGA0, "Q0": Q0, "vi0": VI0, "wa0": WA0, "ut0": UT0,
    "h": H_ROTOR, "D_yaw": D_YAW, "tau_yaw": TAU_YAW, "dQ_cross_1": DQ_CROSS_1,
    "dQ_cross_1_45": DQ_CROSS_1_45, "My_fin_cross_1": MY_FIN_CROSS_1, "My_drag_1": MY_DRAG_1,
    "k_mot": K_MOT, "R_w": R_W, "L_w": L_W, "b_m": B_M, "K_cur": K_CUR, "I_aux": I_AUX,
    "I_mot0": I_MOT0, "V_mot0": V_MOT0, "P_shaft0": P_SHAFT0, "P_bat0": P_BAT0, "I_bat0": I_BAT0,
    "V_bus0": V_BUS0, "eta0": ETA0, "soc_mid": SOC_MID, "ocv_mid": OCV_MID, "I_bat_mid": I_BAT_MID,
    "V_bus_mid": V_BUS_MID, "P_bat_mid": P_BAT_MID,
    "kM": K_M, "kM_est": K_M_EST, "A_max": A_MAX, "M_max": M_MAX, "dOmega": D_OMEGA,
    "Kp_rate": KP_RATE, "Ki_rate": KI_RATE, "K_att": K_ATT,
    "c_fin_x": C_FIN_X, "M_fin_v": M_FIN_V, "k_drag": K_DRAG,
    "Kv_xy": KV_XY, "Ki_xy": KI_XY, "Kp_xy": KP_XY, "Kv_z": KV_Z, "Ki_z": KI_Z, "Kp_z": KP_Z,
    "ev_axis": [[float(x.real), float(x.imag)] for x in EV_AXIS], "damp_axis": DAMP_AXIS,
    "step": STEP, "acc_bias": list(ACC_BIAS), "b_h": B_H, "step_bias": STEP_BIAS, "leg_bias": LEG_BIAS, "w_nut": W_NUT, "f_nut": W_NUT / (2 * math.pi),
    "damp_coupled_off": DAMP_COUPLED_OFF, "damp_coupled_on": DAMP_COUPLED_ON,
    "Kp_esc": KP_ESC, "Ki_esc": KI_ESC, "w_esc": W_ESC, "pm_esc": PM_ESC,
    "z_contact": Z_CONTACT, "hover_z": HOVER_Z, "t_land": T_LAND, "v_land": V_LAND, "t_ramp": T_RAMP,
    "t_contact": T_CONTACT,
    "t_to_contact": T_TO_CONTACT, "k_contact": K_CONTACT, "c_contact": C_CONTACT, "e_feet": E_FEET,
    "r_descent": R_DESCENT, "x_impact": X_IMPACT, "f_impact": F_IMPACT,
    "f_impact_damped": F_IMPACT_D, "e_impact": E_IMPACT, "t_impact": T_IMPACT,
    "f_touch": F_TOUCH, "sigma_foot": SIGMA_FOOT, "f_min_foot": F_MIN_FOOT, "k_td": K_TD,
    "tau_min_esc": TAU_MIN_ESC, "tau_brake_react": TAU_BRAKE_REACT, "accel_td": ACCEL_TD,
    "r_foot": R_FOOT, "gamma_fr": GAMMA_FR, "k_mu_esc": K_MU_ESC, "k_pivot": K_PIVOT, "v_reb": V_REB,
    "t_detect": T_DETECT, "dw_unheld": DW_UNHELD, "r_land_flat": R_LAND_FLAT, "xi_lift": XI_LIFT,
    "h_hop": H_HOP, "t_hop": T_HOP, "f_sensed_max": F_SENSED_MAX, "r_pivot": R_PIVOT,
    "r_ripple": R_RIPPLE, "r_ripple_mean": R_RIPPLE_MEAN, "t_yaw_mean": T_YAW_MEAN,
    "t_unload": T_UNLOAD, "t_spin": T_SPIN, "f_land": F_LAND, "n_land": N_LAND,
    "t_feet_land": T_FEET_LAND, "t_rundown": T_RUNDOWN, "unload_ratio": UNLOAD_RATIO, "t_landed_max": T_LANDED_MAX,
    "w_check": W_CHECK, "lean_w": LEAN_W, "r_descent_w": R_DESCENT_W, "r_land_wind": R_LAND_WIND, "z_hop_wind": Z_HOP_WIND,
    "x_static": X_STATIC, "z_rest": Z_REST, "accel_esc": ACCEL_ESC, "mu_feet": MU_FEET, "tau_rundown": TAU_RUNDOWN, "tau_friction": TAU_FRICTION,
    "lp": {"bgc": BGC, "agc": AGC, "bac": BAC, "aac": AAC},
}


def main() -> int:
    deg = 180 / math.pi
    print("single-propeller drone - reference design")
    print("=" * 78)
    print(f"mass                 m  = {M:.3f} kg, CoM {Z_COM_B * 1000:.1f} mm above the body-tube centre")
    print(f"inertia (no spin)    J  = ({JX:.5f}, {JY:.5f}, {JZ:.5f}) kg m^2")
    print(f"rotor spin inertia   Ja = {JA:.3e} kg m^2 (prop rod + bell ring), h = Ja w0 = {H_ROTOR:.4f} N m s")
    print(f"positions from CoM   rotor {Z_ROTOR:+.4f}, fins {Z_FIN:+.4f}, feet {Z_FOOT:+.4f} m")
    print()
    print("slipstream and fins (momentum theory)")
    print(f"  fins {D_FIN:.3f} m below the rotor: wake speed {K_WAKE:.3f} v_i, wake radius {R_WAKE:.4f} m (fin tip {FIN_TIP})")
    print(f"  fin area {S_FIN * 1e4:.1f} cm^2 each, r_f = {R_FIN:.3f} m, AR_eff {AR_EFF:.2f}, CL_alpha {CLA_FIN:.3f}/rad")
    print(f"  hover: v_i = {VI0:.2f} m/s, w_a = {WA0:.2f} m/s, swirl u_t = Q/(mdot r_f) = {UT0:.2f} m/s")
    print(f"  trim incidence      delta = {DELTA_FIN * deg:.2f} deg, angle of attack {ALPHA_FIN0 * deg:.2f} deg")
    print(f"  fin download        {F_DOWN:.3f} N ({100 * F_DOWN / (M * G):.2f} % of the weight)")
    print()
    print("hover trim")
    print(f"  thrust              T0 = m g + download = {T0:.4f} N")
    print(f"  rotor speed         w0 = sqrt(T0/kT) = {OMEGA0:.2f} rad/s = {OMEGA0 * 30 / math.pi:.0f} rpm")
    print(f"  drag torque         Q0 = kQ w0^2 = {Q0:.4f} N m (= fin torque at trim)")
    print()
    print("passive yaw")
    print(f"  damping             D = {D_YAW:.5f} N m s/rad, tau = (Jz + Ja)/D = {TAU_YAW:.3f} s")
    print(f"  crossflow 1 m/s     yaw torque change {DQ_CROSS_1 * 1e3:+.3f} mN m along x, {DQ_CROSS_1_45 * 1e3:+.3f} mN m at 45 deg")
    print(f"  pitch moment 1 m/s  fins {MY_FIN_CROSS_1 * 1e3:+.2f} mN m, disc + body drag {MY_DRAG_1 * 1e3:+.2f} mN m")
    print()
    print("drive and battery")
    print(f"  motor current {I_MOT0:.2f} A, inverter voltage {V_MOT0:.2f} V, shaft {P_SHAFT0:.1f} W, motor efficiency {ETA0:.3f}")
    print(f"  pack: {I_BAT0:.3f} A at {V_BUS0:.3f} V = {P_BAT0:.2f} W at hover (full pack, settled RC)")
    print(f"        at {T_BAT_MID:g} s (charge {SOC_MID:.4f}, OCV {OCV_MID:.3f} V): {I_BAT_MID:.4f} A at {V_BUS_MID:.3f} V = {P_BAT_MID:.2f} W")
    print(f"  current loop {W_CURRENT / (2 * math.pi):.0f} Hz, K = {K_CUR:.4f} Ohm")
    print()
    print("cyclic actuation")
    print(f"  kM = {K_M} (plant), {K_M_EST} (allocation), A_max = {A_MAX} N m, M_max = {M_MAX:.3f} N m")
    print(f"  speed ripple at full cyclic {D_OMEGA:.2f} rad/s ({100 * D_OMEGA / OMEGA0:.2f} %)")
    print()
    print("control loops")
    print(f"  rate                Kp = {KP_RATE:.4f}, Ki = {KI_RATE:.4f} (crossover {W_RATE} rad/s), gyro feed-forward")
    print(f"  attitude K = {K_ATT}; velocity Kv = {KV_XY}, Ki = {KI_XY}; position Kp = {KP_XY}")
    print(f"  one axis, closed-loop modes {np.round(np.sort_complex(EV_AXIS), 3).tolist()}")
    print(f"                      minimum damping ratio {DAMP_AXIS:.3f}")
    print(f"  lateral derivatives: fin drag {C_FIN_X:.3f} N s/m (+ {C_LIN_AERO} airframe), fin pitch moment {M_FIN_V * 1e3:+.2f} mN m per m/s")
    print(f"  drag feed-forward    k_drag = {K_DRAG:.4f} 1/s")
    print(f"  {STEP_DX:g} m step ({STEP_DUR} s from t = {STEP_T0} s): worst tracking error {STEP['worst_err']:.4f} m, overshoot {STEP['overshoot'] * 100:.2f} cm")
    print(f"  with the horizontal accelerometer bias |b_h| = {B_H:.4f} m/s^2 as a disturbance (worse sign):")
    print(f"                      worst tracking error {STEP_BIAS['worst_err']:.4f} m, overshoot {STEP_BIAS['overshoot'] * 100:.2f} cm, "
          f"offset at {STEP_T_END:g} s {STEP_BIAS['x_end_dev'] * 100:.2f} cm")
    print(f"  flight legs ({LEG_DX} m in {LEG_DUR} s), with the bias: worst tracking error {LEG_BIAS['worst_err']:.4f} m, "
          f"overshoot {LEG_BIAS['overshoot'] * 100:.2f} cm")
    print(f"  gyroscopic coupling: free nutation h/sqrt(Jx Jy) = {W_NUT:.2f} rad/s ({W_NUT / (2 * math.pi):.3f} Hz)")
    print(f"  attitude+rate loops, both axes: min damping {DAMP_COUPLED_OFF:.3f} without feed-forward, {DAMP_COUPLED_ON:.3f} with")
    print(f"  rotor speed         Kp = {KP_ESC}, Ki = {KI_ESC}, crossover {W_ESC:.1f} rad/s, PM {PM_ESC:.1f} deg")
    print()
    print(f"landing: contact height {Z_CONTACT:.4f} m; land mode from {HOVER_Z} m at t = {T_LAND} s, {V_LAND} m/s "
          f"(ramped in over {T_RAMP} s): ground {T_TO_CONTACT:.3f} s later, t = {T_CONTACT:.3f} s")
    print(f"  steady yaw rate in the {V_LAND} m/s descent {R_DESCENT:+.3f} rad/s (fin swirl with the larger mass flow)")
    print(f"  touchdown at {V_LAND} m/s on four Hertz feet, undamped: peak force {F_IMPACT:.1f} N, penetration {X_IMPACT * 1e3:.2f} mm")
    print(f"  foot damping c = 8 (1 - e)/(5 e v) = {C_CONTACT:.2f} s/m for a restitution e = {E_FEET}")
    print(f"  impact simulation with that damping: peak force {F_IMPACT_D:.1f} N, restitution {E_IMPACT:.3f}")
    print(f"  at rest: static penetration {X_STATIC * 1e3:.3f} mm, CoM height {Z_REST:.5f} m")
    print(f"  run-down on the ground: rotor deceleration torque {TAU_RUNDOWN:.3f} N m, feet friction {TAU_FRICTION:.2f} N m")
    print(f"  foot load sensor: {1 / T_TICK_ESC:.0f} Hz, noise {SIGMA_FOOT} N per foot, touch above {F_TOUCH} N held {N_TOUCH_HOLD} ticks; "
          f"the drive counts a foot above {F_MIN_FOOT} N")
    print(f"  touchdown brake: to {K_TD} of the speed at up to {ACCEL_TD:.0f} rad/s^2 (torque limit allows {A_BRAKE_MAX:.0f}), "
          f"limited to {GAMMA_FR} of the friction the sampled load gives (k_mu = {K_MU_ESC}, r_foot = {R_FOOT:.4f} m)")
    print(f"  flat touchdown with the sampled law, tick phase scanned: latch at most {T_DETECT * 1e3:.2f} ms after the first contact, "
          f"sampled peak at most {F_SENSED_MAX:.1f} N")
    print(f"      rotor speed lost outside the feet's friction at most {DW_UNHELD:.2f} rad/s: yaw rate Ja/Jz x that = {R_LAND_FLAT:.3f} rad/s")
    print(f"      speed fraction at lift-off at most {XI_LIFT:.4f}; hop at most {H_HOP * 1e3:.2f} mm, {T_HOP * 1e3:.0f} ms "
          f"(rebound {V_REB:.3f} m/s at e = {E_FEET})")
    for r in TD_SCAN[::5]:
        print(f"        latch {r['t_latch'] * 1e3:5.2f} ms: lost unheld {r['dw_unheld']:.2f} rad/s, xi {r['xi']:.4f}, rebound {r['v_reb']:.4f} m/s, "
              f"contact {r['t'] * 1e3:.1f} ms")
    print(f"  one foot first: the body pivots, yaw inertia x {1 / K_PIVOT:.2f}; the brake leaves {R_PIVOT:.3f} rad/s")
    print(f"  cyclic ripple of the yaw rate at full cyclic {R_RIPPLE:.3f} rad/s; YawMean ({T_YAW_MEAN} s lag) passes {R_RIPPLE_MEAN:.3f}")
    print(f"  unload over {T_UNLOAD} s on settled feet: deceleration torque at most {UNLOAD_RATIO:.2f} of the friction; the feet carry "
          f"{F_LAND:.2f} N {T_FEET_LAND:.3f} s after the latch, idle after {T_RUNDOWN:.3f} s; landed by {T_LANDED_MAX:.3f} s")
    print(f"  wind {W_CHECK} m/s: lean {LEAN_W:.4f} rad, descent yaw {R_DESCENT_W:.3f} rad/s; yaw bound {R_LAND_WIND:.3f} rad/s, "
          f"height bound {Z_HOP_WIND:.5f} m (+{(Z_HOP_WIND - Z_CONTACT) * 1e3:.2f} mm)")
    out = HERE / "design.json"
    out.write_text(json.dumps(DATA, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
