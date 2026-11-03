"""Parameters of the ball-and-plate lab rig (one definition, imported by every design script).

Sources (see the README, "Parameters and sources"):

* Servos: Quanser SRV02 rotary servo base in the high-gear configuration, "SRV02 User Manual",
  Document Number 700, Revision 2.3, Table 5 (system specifications): R_m, L_m, k_t, k_m, K_g,
  J_eq (high gear, no load), B_eq (high gear), the 4096 count/rev encoder.
* Plate and camera: the Quanser 2 DOF Ball Balancer product page (two SRV02 units on the sides of a
  plate on a 2 DOF gimbal, an overhead camera of 640 x 480 pixels at 30 frames per second).
  Our plate is 0.35 m square instead of Quanser's 0.275 m.
* Linkage: the crank/push-rod geometry of the 2 DOF Ball Balancer and of the SRV02 ball-and-beam,
  sin(alpha) = (r_arm / L) sin(theta) (A. H. Sidi et al., "Enhanced Ball Trajectory Tracking Using
  Visual Servoing with 2-DOF Ball on Plate Balancing System", JESA 57(2), 2024, eq. 8, CC BY 4.0).
* Ball: a 1 inch (25.4 mm) chrome-steel bearing ball (AISI 52100, density 7810 kg/m^3), a solid
  sphere, J = 2/5 m r^2.
* Plate material: 6 mm cast acrylic (PMMA, density 1190 kg/m^3).

Assumed (no published value for this rig): the linkage stiffness and damping, the rolling
resistance of the steel ball on acrylic, the contact stiffness (softened 50 times from Hertz for
the solver), the friction coefficient, the voltage dead band, the camera noise and the plate
height above the base.
"""

from __future__ import annotations

import math

G0 = 9.81

# ---- ball: 1 inch chrome-steel ball, solid sphere
R_BALL = 0.0127                                   # m
RHO_STEEL = 7810.0                                # kg/m^3 (AISI 52100)
M_BALL = RHO_STEEL * 4.0 / 3.0 * math.pi * R_BALL**3   # 0.06701 kg
J_FACTOR = 0.4                                    # solid sphere (2/3 for a thin shell)
J_BALL = J_FACTOR * M_BALL * R_BALL**2
K_ROLL = 1.0 / (1.0 + J_FACTOR)                   # 5/7: x'' = K_ROLL g sin(alpha)

# ---- plate: 0.35 m square, 6 mm acrylic, centre of mass on the gimbal centre
A_PLATE = 0.35                                    # side, m
T_PLATE = 0.006                                   # thickness, m
RHO_PMMA = 1190.0
M_PLATE = RHO_PMMA * A_PLATE * A_PLATE * T_PLATE  # 0.8747 kg
J_PLATE_XY = M_PLATE * (A_PLATE**2 + T_PLATE**2) / 12.0
J_PLATE_Z = M_PLATE * (2 * A_PLATE**2) / 12.0
H_PIVOT = 0.16                                    # gimbal centre above the base, m
Z_SURF = T_PLATE / 2                              # top surface in the plate frame
H_BALL = Z_SURF + R_BALL                          # ball centre above the pivot plane (plate frame)
W_FACE = A_PLATE / 2                              # half width of the face

# ---- servos: Quanser SRV02, high gear (User Manual rev 2.3, Table 5)
R_M = 2.6                                         # ohm
L_M = 0.18e-3                                     # H
K_T = 7.68e-3                                     # N m/A
K_M = 7.68e-3                                     # V s/rad
K_G = 70.0                                        # 14 x 5
J_EQ = 2.08e-3                                    # kg m^2, high gear, no load (rotor reflected)
B_EQ = 0.015                                      # N m s/rad, high gear
ENC_CPR = 4096                                    # counts/rev (SRV02-E)
V_MAX = 10.0                                      # V: the +-10 V analog output of the DAQ
V_DEAD = 0.05                                     # V: dead band of the drive (assumed)
THETA_MAX = math.radians(60.0)                    # servo travel (soft limit of the command)

# ---- linkage: crank r_arm on the servo, push rod to the plate edge at L from the gimbal centre
R_ARM = 0.0254                                    # m
L_ROD_X = 0.16                                    # m, attachment of the rod on the plate
RHO_LINK = R_ARM / L_ROD_X                        # sin(alpha) = RHO sin(theta)
L_ROD = 0.10                                      # push-rod length (scene only), m
K_LINK = 5000.0                                   # N m/rad at the plate axis (assumed)
B_LINK = 1.3                                      # N m s/rad (assumed: zeta ~ 0.1 against the plate)

# ---- contact (RollingSphere)
K_C, XREF_C = 1.0e5, 1.0e-4                       # 1e7 N/m^1.5 (Hertz steel/PMMA: about 5e8)
C_C = 20.0                                        # Hunt-Crossley damping, s/m
MU_C = 0.4                                        # steel on acrylic
VS_C = 1.0e-3                                     # m/s
CRR = 2.0e-3                                      # rolling resistance coefficient (assumed)
DELTA0 = (M_BALL * G0 * math.sqrt(XREF_C) / K_C) ** (2.0 / 3.0)   # static penetration on a level plate

# ---- camera
CAM_RATE = 30.0                                   # frames per second (Quanser 2DBB camera)
CAM_T = round(1.0 / CAM_RATE, 9)                 # s, whole nanoseconds (a discrete clock period must be)
CAM_DELAY = 1                                     # frames of processing latency
CAM_PIX = 0.40 / 640                              # m per pixel (0.40 m field of view over 640 px)
CAM_NOISE = 0.3e-3                                # m, centroid noise (std)

# ---- servo firmware
SERVO_RATE = 500.0
SERVO_T = 1.0 / SERVO_RATE

# ---- plant numbers of the linear design
GAIN_V = K_T * K_G / R_M                          # torque per volt at the output, N m/V
B_EMF = K_T * K_M * K_G**2 / R_M                  # back-EMF damping at the output, N m s/rad
J_SERVO = J_EQ + RHO_LINK**2 * J_PLATE_XY         # servo inertia with the plate reflected
B_SERVO = B_EMF + B_EQ
K_BB = K_ROLL * G0 * RHO_LINK                     # x'' per servo angle (small angles), m/s^2/rad


def summary() -> dict:
    return {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float))}
