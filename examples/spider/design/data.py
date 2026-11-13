"""Design data of the T8X spider-robot example.

All numbers are SI. Tags:

``[pub]`` published, ``[est]`` engineering estimate from the published photographs and
dimensions, ``[ds]`` servo datasheet, ``[der]`` derived in ``design/design.py``.

Published (accessed 2026-11-12):

* eight legs, 26 servos: three in each leg and two in the abdomen (Robugtix T8X product and
  store pages; the T8X servos are "Robugtix servo motors" with no published rating);
* Wi-Fi web-app controller and the proprietary Bigfoot inverse-kinematics/gait engine;
* walk command 0..200 mm/s, stop at 100, so 100 mm/s per 100 counts (tutorial #2);
* walk-turn command 0..200 deg/s, stop at 100 (tutorial #2);
* 2.2 lb (1.0 kg) for the T8, the same mechanism as the T8X (Open Electronics);
* the original T8 used 26 Hitec HS-35HD servos on a 4.8 V NiMH pack (New Atlas, 2013);
* 20..60 min on one battery charge (FAQ).

The leg lengths, body size and inertia are ``[est]``: the photographs show a body about
0.20 m long and a leg span about 0.42 m, with a short coxa, a long femur and a longer tibia.

Servo. The HS-35HD of the original T8 is rated 11 oz-in = 0.078 N m at 4.8 V, 0.10 s/60 deg
(Hitec datasheet as listed by ServoDatabase and the retailers). That is below what this
model's [est] 1.02 kg robot needs: 0.10 N m at the femur standing on eight feet and about
0.25 N m in the four-foot phase of the tetrapod (design.json). The model therefore uses the
next Hitec class that carries the load, the HS-82MG [ds]: 3.4 kg cm = 0.333 N m and
0.10 s/60 deg at 6.0 V (2.8 kg cm and 0.12 s/60 deg at 4.8 V), 19 g. It is a substitute
for the unpublished T8X servo, not a T8X datum. The servo is an analog P loop driving a DC
motor: full duty (stall torque) beyond a small position error, and the motor's back-EMF line
from stall to the no-load speed; there is no derivative term.
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------- body [est]
M_BODY = 0.46                # kg, frame, battery, electronics (without the legs)
J_BODY = [0.00115, 0.00205, 0.00295]  # kg m^2, x (roll), y (pitch), z (yaw), without the legs
G0 = 9.80665                 # m/s^2

# --------------------------------------------------------------------------- leg geometry [est]
A_COXA = 0.045               # m, coxa (yaw) link
B_FEMUR = 0.110              # m, femur
C_TIBIA = 0.140              # m, tibia
H_STAND = 0.110              # m, commanded body origin height above the foot points

# Hip position in the body frame and the direction of the hip x axis (the leg plane).
# Legs 1..4 are the left side front to rear, 5..8 the right side front to rear.
HIPS = [
    (0.072, 0.032, 0.0, math.radians(35.0)),
    (0.024, 0.040, 0.0, math.radians(65.0)),
    (-0.024, 0.040, 0.0, math.radians(115.0)),
    (-0.072, 0.032, 0.0, math.radians(145.0)),
    (0.072, -0.032, 0.0, math.radians(-35.0)),
    (0.024, -0.040, 0.0, math.radians(-65.0)),
    (-0.024, -0.040, 0.0, math.radians(-115.0)),
    (-0.072, -0.032, 0.0, math.radians(-145.0)),
]

# Nominal foot point in the body frame: 0.16 m from the hip along the hip x axis, on the
# ground (z = -H_STAND relative to the body origin).
FOOT_R = 0.160
FOOT = [
    (h[0] + FOOT_R * math.cos(h[3]), h[1] + FOOT_R * math.sin(h[3]), -H_STAND)
    for h in HIPS
]
NX = [p[0] for p in FOOT]
NY = [p[1] for p in FOOT]

# Alternating tetrapod: L1, L3, R2, R4 in phase A, the other four half a cycle later.
PHASE_OFF = [0.0, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 0.0]

# Link masses (servo included) and principal inertias about the link centres (x along the
# link, z the joint axis of the femur and tibia, vertical for the coxa) [est]. The centre of
# each link is at its middle.
M_COXA, M_FEMUR, M_TIBIA = 0.015, 0.030, 0.025
J_COXA = [1.5e-6, 2.5e-6, 2.5e-6]
J_FEMUR = [2.5e-5, 3.0e-5, 3.0e-5]
J_TIBIA = [4.0e-5, 5.0e-5, 5.0e-5]

M_LEG = M_COXA + M_FEMUR + M_TIBIA
M_TOTAL = M_BODY + 8.0 * M_LEG

# --------------------------------------------------------------------------- gait [est]
T_GAIT = 0.8                 # s, one leg cycle
DUTY = 0.70                  # stance fraction of the command profile (the foot is commanded
                             # on the ground for DUTY*T_GAIT and in the air for the rest)
LIFT = 0.035                 # m, swing apex of the commanded foot
V_WALK = 0.10                # m/s, the forward command used by spider-walk
V_CRAB = 0.06                # m/s, the lateral command
W_TURN = math.radians(20.0)  # rad/s, the yaw-rate command (the T8X tutorial uses 25 deg/s)
RAMP_T = 0.8                 # s, the gait's command ramp-in time constant
K_ATT = 1.0                  # roll/pitch foot correction (see design.py: roll stiffness x2)
TAU_ATT = 0.1                # s, attitude filter of the correction (see design.py)

# --------------------------------------------------------------------------- servo
# Hitec HS-82MG at 6.0 V [ds]: 3.4 kg cm stall, 0.10 s/60 deg no-load.
TAU_STALL = 3.4e-2 * G0               # N m, 0.333
W_NOLOAD = (math.pi / 3.0) / 0.10     # rad/s, 10.47
B_EMF = TAU_STALL / W_NOLOAD          # N m s/rad, slope of the torque-speed line, 0.0318
THETA_SAT = math.radians(1.0)         # rad, position error that gives full duty [est]
KP_SERVO = TAU_STALL / THETA_SAT      # N m/rad, 19.1
KD_SERVO = 0.0                        # N m s/rad, an analog servo has no derivative term
KP = [KP_SERVO] * 3
KD = [KD_SERVO] * 3
TAU_MAX = [TAU_STALL] * 3
W_NL = [W_NOLOAD] * 3
TAU_S = 0.012                # s, command filter (50 Hz servo frame) [est]
B_JOINT = [0.005, 0.005, 0.005]       # N m s/rad, gear-train viscous friction [est]
# The joint inertias are derived from the link masses in design.py (joint_inertias); the
# rotor inertia of the HS-82MG is not published and is not included.

# --------------------------------------------------------------------------- contact [est]
# Rubber foot pad on a lab floor. 1.5 kN/m at the 1 mm reference gives about 1.5 N at a
# standing foot (the robot weighs 10 N on eight feet); Hunt-Crossley damping c = 3 s/m
# and mu = 0.8 hold the stance without a visible creep.
CONTACT = {"k": 1500.0, "xref": 1.0e-3, "c": 3.0, "mu": 0.8, "vs": 0.01,
           "bt": 0.0, "eps": 1.0e-5, "feps": 1.0e-6}

# --------------------------------------------------------------------------- IK / FK
REACH_BAND = 0.02            # m, the IK `reach` falls from 1 to 0 over this band at either limit


def leg_ik(foot, hip, yaw, a=A_COXA, b=B_FEMUR, c=C_TIBIA, margin=1.0e-4, band=REACH_BAND):
    """Analytic IK of one leg (the equations of library/SpiderLegIK.jl).

    Returns (q1, q2, q3, reach, rho). ``foot`` and ``hip`` are 3-vectors in the body frame,
    ``yaw`` is the hip x direction. The chain is coxa yaw about body z, then the planar
    femur/tibia chain in the radial-z plane; q2 is positive up and q3 negative bends the
    tibia down. ``reach`` is 1 inside the annulus and falls to 0 within ``band`` of either
    the outer (straight leg) or the inner (folded leg) limit.
    """
    dx = math.cos(yaw) * (foot[0] - hip[0]) + math.sin(yaw) * (foot[1] - hip[1])
    dy = -math.sin(yaw) * (foot[0] - hip[0]) + math.cos(yaw) * (foot[1] - hip[1])
    rho = math.hypot(dx, dy)
    q1 = math.atan2(dy, dx)
    x = rho - a
    z = foot[2] - hip[2]
    d = math.hypot(x, z)
    dmin = abs(b - c) + margin
    dmax = b + c - margin
    dc = min(max(d, dmin), dmax)
    xs, zs = x * dc / max(d, 1e-9), z * dc / max(d, 1e-9)
    ck = min(max((dc * dc - b * b - c * c) / (2.0 * b * c), -1.0), 1.0)
    q3 = -math.acos(ck)
    q2 = math.atan2(zs, xs) - math.atan2(c * math.sin(q3), b + c * math.cos(q3))
    reach = min(max(min(dmax - d, d - dmin) / band, 0.0), 1.0)
    return q1, q2, q3, reach, rho


def leg_fk(q1, q2, q3, hip, yaw, a=A_COXA, b=B_FEMUR, c=C_TIBIA):
    """Foot point in the body frame from the three joint angles (the inverse of leg_ik)."""
    r = a + b * math.cos(q2) + c * math.cos(q2 + q3)
    z = hip[2] + b * math.sin(q2) + c * math.sin(q2 + q3)
    x = hip[0] + r * math.cos(yaw + q1)
    y = hip[1] + r * math.sin(yaw + q1)
    return x, y, z


Q0 = [leg_ik(FOOT[i], HIPS[i][:3], HIPS[i][3])[:3] for i in range(8)]


def leg_summary():
    """Rows for the README: hip, foot, joint angles and the foot's reach margin."""
    rows = []
    for i in range(8):
        q1, q2, q3, reach, rho = leg_ik(FOOT[i], HIPS[i][:3], HIPS[i][3])
        rows.append((i + 1, HIPS[i], FOOT[i], math.degrees(q1), math.degrees(q2),
                     math.degrees(q3), reach))
    return rows


if __name__ == "__main__":
    print(f"mass {M_TOTAL:.3f} kg, weight {M_TOTAL * G0:.3f} N")
    print(f"static foot load {M_TOTAL * G0 / 8:.4f} N")
    print(f"servo: stall {TAU_STALL:.4f} N m, no-load {W_NOLOAD:.3f} rad/s, "
          f"back-EMF {B_EMF:.4f} N m s/rad, kp {KP_SERVO:.2f} N m/rad")
    for row in leg_summary():
        i, h, f, q1, q2, q3, reach = row
        print(f"leg {i}: hip ({h[0]:+.3f},{h[1]:+.3f}) foot ({f[0]:+.3f},{f[1]:+.3f}) "
              f"q1 {q1:+7.2f} q2 {q2:+7.2f} q3 {q3:+8.2f} deg  reach {reach:.3f}")
