"""Design data of the AIM-9X Sidewinder example.

Everything the models, the reference simulation and the checks use. Values are SI. The tags say
where a number comes from:

``[pub]`` published, ``[der]`` derived from published numbers, ``[est]`` engineering estimate
(the source is given in the comment).

Published data (Wikipedia, *AIM-9 Sidewinder*, accessed 2026-11-12, and the sources it cites):

* mass 85.3 kg (188 lb), length 3.02 m (9 ft 11 in), diameter 0.127 m (5 in), span 0.2794 m (11 in)
* warhead 9.4 kg (20.8 lb)
* maximum speed Mach 2.5+, range 1.0 to 35.4 km
* Mk. 36 solid rocket motor, imaging infrared 128 x 128 FPA seeker, 90 deg off-boresight,
  two-axis thrust-vector control that augments the canards, 60 g turn capability

The motor's thrust and burn time are not public. They are derived from the published mass,
speed and range, and tagged ``[est]`` where that is the case. All aerodynamic coefficients are
engineering estimates of a slender cruciform missile; they are small and readable, and the
example is about the *control* of the airframe, not about matching a wind-tunnel table.
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------- vehicle [pub]/[est]
MASS_0 = 85.3                 # kg, launch mass [pub]
MASS_DRY = 64.3               # kg, after the motor [est: 21 kg propellant, 24.6 % of the launch mass]
LENGTH = 3.02                 # m [pub]
DIAMETER = 0.127              # m [pub]
SPAN = 0.2794                 # m [pub]
WARHEAD = 9.4                 # kg [pub]

S_REF = math.pi * DIAMETER**2 / 4.0       # m^2, body cross-section
B_REF = SPAN                              # m, roll reference length

# The body is a slender cylinder; the mass is concentrated near the middle.
J_0 = [0.80, 55.0, 55.0]       # kg m^2, launch: roll, pitch, yaw [est]
J_DRY = [0.55, 42.0, 42.0]     # kg m^2, burnout [est]

X_CG = 1.52                    # m from the nose [est: mid-body]
X_CANARD = 1.10                # m ahead of the CG (0.38 m from the nose) [est]
X_TAIL = 1.33                  # m behind the CG [est]
FIN_AREA = 0.020               # m^2, total canard planform area (four fins) [est]
FIN_RADIUS = DIAMETER / 2.0    # m, canard root radius from the body axis
FIN_CN_DELTA = 2.0             # 1/rad, canard normal-force slope [est]
FIN_MAX = 25.0                 # deg, canard deflection limit [est]
FIN_RATE = 200.0               # deg/s, canard actuator rate [est]
SERVO_W0 = 30.0                # rad/s, actuator natural frequency [est]
SERVO_ZETA = 0.7               # 1, actuator damping ratio [est]

TVC_ARM = 1.30                 # m, centre of mass to the nozzle gimbal [est]
TVC_MAX = 8.0                  # deg, two-axis TVC gimbal limit [est]
TVC_RATE = 200.0               # deg/s [est]

# --------------------------------------------------------------------------- motor [est]
T_IGNITION = 0.10              # s, ignition delay after launch [est]
T_BURN = 2.40                  # s, boost duration [est]
MDOT = (MASS_0 - MASS_DRY) / T_BURN   # kg/s, 8.75 kg/s
ISP_VAC = 235.0                # s, vacuum specific impulse [est]
C_VAC = ISP_VAC * 9.80665      # m/s, vacuum effective exhaust velocity
EXIT_AREA = 0.0060             # m^2, nozzle exit area [est: 0.087 m exit diameter]
# The thrust tail-off is a 0.15 s linear ramp; the ignition ramp is 0.05 s.
TAU_IGN = 0.05                 # s
TAU_TAIL = 0.15                # s

# --------------------------------------------------------------------------- atmosphere (US 1976)
G0 = 9.80665                   # m/s^2
R_AIR = 287.05287              # J/(kg K)
GAMMA_AIR = 1.4
P0 = 101325.0                  # Pa
T0 = 288.15                    # K
LAPSE = 0.0065                 # K/m
H_TROP = 11000.0               # m
T_TROP = 216.65                # K
P_TROP = 22632.06              # Pa
RHO0 = 1.225                   # kg/m^3

# --------------------------------------------------------------------------- aerodynamics [est]
# Normal-force slope against Mach. The slender body plus the tail fins.
MACH_TAB = [0.0, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
CN_ALPHA_TAB = [2.6, 2.6, 2.8, 3.2, 3.4, 3.2, 3.0, 2.8, 2.7]   # 1/rad
CD0_TAB = [0.18, 0.18, 0.21, 0.36, 0.38, 0.32, 0.26, 0.23, 0.22]  # zero-lift drag
CN3 = 80.0                     # 1/rad^2, the vortex lift of the slender body
CN_MAX = 12.0                  # 1, table clamp
K_INDUCED = 0.10               # 1, induced drag factor: CD = CD0 + k CN^2
CM_RATIO = -0.80               # 1, Cm = CM_RATIO CN: a small static margin (0.15 d)
CN_RATIO = 0.80               # 1, Cn = CN_RATIO CN_beta: weathercock stability
CM_Q = -1500.0                 # 1/rad, pitch damping (Cm_q)
CN_R = -1200.0                 # 1/rad, yaw damping (Cn_r)
CL_P = -0.50                   # 1/rad, roll damping (Cl_p)
ALPHA_MAX = 40.0               # deg, beyond this the tables hold (no departure model)

# --------------------------------------------------------------------------- autopilot [est]
A_MAX = 60.0 * G0              # m/s^2, the published 60 g turn capability
N_PN = 4.0                     # 1, proportional-navigation constant
VC_MIN = 120.0                 # m/s, floor of the closing speed in the PN law
GRAVITY_COMP = 1.0             # 1, add the gravity component to the acceleration command
QBAR_REF = 150000.0            # Pa, gain-scheduling reference dynamic pressure
K_PHI = 6.0                    # 1/s, roll-angle loop
K_P_ROLL = 2.2                 # deg per rad/s, roll-rate loop
K_I_ROLL = 8.0                 # deg per rad, roll integrator
P_CMD_MAX = 250.0              # deg/s
K_Q = 28.0                     # deg per rad/s, pitch/yaw rate loop
K_A = 0.55                     # deg per m/s^2, acceleration loop
K_I = 0.35                     # deg per (m/s^2 s), acceleration integrator
DP_MAX = 16.0                  # deg, virtual pitch command limit
DY_MAX = 16.0                  # deg, virtual yaw command limit
DR_MAX = 12.0                  # deg, virtual roll command limit
TVC_GAIN = 0.35                # 1, share of the acceleration error given to the TVC
TVC_MIN_T = 1000.0             # N, thrust floor in the TVC allocation

# --------------------------------------------------------------------------- seeker [est]
FOV = math.radians(90.0)       # rad, full field of view (90 deg off-boresight claimed)
GIMBAL_MAX = math.radians(60.0)
SEEKER_TAU = 0.020             # s, gimbal lag
SEEKER_RATE = math.radians(180.0)   # rad/s, gimbal rate limit
LOS_RATE_TAU = 0.030           # s, LOS-rate filter
IR_ZERO_RANGE = 10.0           # m, the 1/r^2 singularity floor
IR_ATTEN = 1.0e-4              # 1/m, atmospheric attenuation exp(-k r)
IR_MIN = 0.02                  # W/m^2, detection threshold
IR_TARGET = 1.0e6              # W/sr, target intensity at the nose [est]
IR_REAR_FACTOR = 0.65          # 1, rear-aspect increase of the target intensity
FLARE_I = 4.0e6                # W/sr, flare intensity at release [est]
FLARE_TAU = 2.5                # s, flare decay
FLARE_RATIO = 1.5              # 1, a flare brighter than this times the target competes
IRCCM_RATIO = 1.0              # 1, IRCCM on: ignore a source that grows this fast (simplified)

# --------------------------------------------------------------------------- fuze and warhead [est]
FUZE_RADIUS = 15.0              # m, the proximity fuze triggers inside this range
KILL_RADIUS = 20.0              # m, the continuous-rod warhead's lethal radius

# --------------------------------------------------------------------------- scenarios
# The nominal start is a launch from a fighter at 6 km, 250 m/s (Mach 0.75).
P_M0 = [0.0, 0.0, 6040.0]      # m
V_M0 = 400.0                   # m/s
ALPHA0 = 0.0                   # deg, the missile leaves the rail aligned with the aircraft
T_END = 30.0

# The target: a fighter crossing from the right, turning into the missile.
P_T0 = [2000.0, 0.0, 6000.0]  # m, world (north, west, up)
V_T0 = 150.0                     # m/s
PSI_T0 = 0.0                    # deg, heading (from +x towards +y: west)
GAMMA_T0 = 0.0                   # deg
TURN_RATE = math.radians(0.0)    # rad/s, about 1.5 g at 220 m/s
T_TURN = 3.5                     # s
T_FLARE = 6.0                    # s, the target releases a flare
FLARE_SEP = 60.0                 # m behind the target
FLARE_DROP = 30.0                # m below

# The airframe and control models start fast and high, where the missile has authority.
H_TEST = 3000.0
V_TEST = 600.0
T_END_AIRFRAME = 8.0
T_END_CONTROL = 8.0


def atmosphere(h: float) -> tuple[float, float, float, float]:
    """US Standard Atmosphere 1976 (troposphere and lower stratosphere).

    Returns temperature (K), pressure (Pa), density (kg/m^3) and speed of sound (m/s).
    """
    h = min(max(h, -1000.0), 20000.0)
    if h < H_TROP:
        temp = T0 - LAPSE * h
        pres = P0 * (temp / T0) ** (G0 / (R_AIR * LAPSE))
    else:
        temp = T_TROP
        pres = P_TROP * math.exp(-G0 * (h - H_TROP) / (R_AIR * T_TROP))
    rho = pres / (R_AIR * temp)
    sound = math.sqrt(GAMMA_AIR * R_AIR * temp)
    return temp, pres, rho, sound


def cn_alpha(mach: float) -> float:
    return _interp(mach, MACH_TAB, CN_ALPHA_TAB)


def cd0(mach: float) -> float:
    return _interp(mach, MACH_TAB, CD0_TAB)


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for k in range(len(xs) - 1):
        if x <= xs[k + 1]:
            f = (x - xs[k]) / (xs[k + 1] - xs[k])
            return ys[k] + f * (ys[k + 1] - ys[k])
    return ys[-1]


def motor(t: float) -> tuple[float, float, float, float]:
    """Propellant flow, mass and inertia at time *t* (the same law as `MissileMotor`).

    Returns ``mdot`` (kg/s), ``m`` (kg), ``J`` (3) and ``dm`` (kg/s, the flow that leaves).
    """
    if t < T_IGNITION:
        flow = 0.0
    else:
        rise = min(max((t - T_IGNITION) / TAU_IGN, 0.0), 1.0)
        fall = min(max((T_IGNITION + T_BURN - t) / TAU_TAIL, 0.0), 1.0)
        flow = MDOT * rise * fall
    burned = MDOT * (t - T_IGNITION) if t > T_IGNITION else 0.0
    m = max(MASS_0 - burned, MASS_DRY)
    f = (m - MASS_DRY) / (MASS_0 - MASS_DRY)
    J = [J_DRY[k] + f * (J_0[k] - J_DRY[k]) for k in range(3)]
    return flow, m, J, flow


def thrust(t: float, pa: float, mdot: float) -> float:
    """Vacuum thrust minus the ambient-pressure correction, with the flow gate."""
    if mdot <= 0.0:
        return 0.0
    gate = min(max(mdot / MDOT, 0.0), 1.0)
    return max(mdot * C_VAC - pa * EXIT_AREA * gate, 0.0)


# --------------------------------------------------------------------------- scenarios as dicts
def scenario(name: str) -> dict:
    if name == "airframe":
        return {
            "name": name, "t_end": T_END_AIRFRAME, "p0": [0.0, 0.0, H_TEST], "v0": V_TEST,
            "alpha0": 2.0, "motor": True, "guidance": False, "target": False,
        }
    if name == "control":
        return {
            "name": name, "t_end": T_END_CONTROL, "p0": [0.0, 0.0, H_TEST], "v0": V_TEST,
            "alpha0": 2.0, "motor": True, "guidance": False, "target": False,
        }
    if name == "intercept":
        return {
            "name": name, "t_end": T_END, "p0": P_M0, "v0": V_M0, "alpha0": 0.0,
            "motor": True, "guidance": True, "target": True,
        }
    raise ValueError(name)
