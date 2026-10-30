"""Physical data of the Robird example (X5.15): geometry, masses, aerodynamics, drive.

Sources: T = van der Grinten, Folkertsma, Nijenhuis, Stramigioli, "The bird is the word" (2015) and its
appendix; A = assumed (public Robird figures: about 0.7 kg, about 1.1 m span; or an engineering guess,
flagged). The thesis gives the model STRUCTURE and ranges but not the fitted numbers of its tables.
Imported by build_model.py and design.py (no side effects).
"""

from __future__ import annotations

import math

import numpy as np

G = 9.81
RHO = 1.2

# --------------------------------------------------------------------------- bodies (all A unless noted)
M_FUS = 0.55            # kg  fuselage + battery + motor + electronics + fixed tail frame     (A, total 0.70 kg)
J_FUS = [0.0012, 0.0060, 0.0065]   # kg m^2  roll, pitch, yaw principal moments (x fwd, y left, z up)   (A)
WING_ROOT = (0.02, 0.05, 0.02)     # m  wing root hinge (x fwd of CoM, |y|, z)    (A; thesis: wing about 50 cm)
L1, L2 = 0.20, 0.30     # m  inner (arm) and outer (hand) wing segment span; wing length 0.50 m    (T: about 50 cm; split A)
C1 = (0.160, 0.145)     # m  inner chord root/tip                                              (A)
C2 = (0.145, 0.100)     # m  outer chord root/tip                                              (A)
M1, M2 = 0.035, 0.030   # kg per segment                                                          (A)
NS = 3                  # strips per segment (modified strip theory, thesis III-E)
XEA = 0.10              # torsion axis at 10 % chord from the leading edge, centre of pressure at 25 %  (A)
M_FLAP = 0.006          # kg tail flap
TAIL_X = -0.33          # m hinge of the tail flaps behind the CoM                               (A)
TAIL_Y = 0.075
FLAP_SPAN, FLAP_CHORD = 0.15, 0.13   # m all-moving tail halves                                  (A)
RUD_X, RUD_Z = -0.30, 0.03
RUD_SPAN, RUD_CHORD = 0.09, 0.13     # m all-moving fin                                         (A)

# --------------------------------------------------------------------------- aerodynamics (thesis III-E form)
LA, LB = 4.4, 0.25      # C_L = La alpha + Lb   (T: affine; numbers A)
DA, DB = 0.2, 0.04      # C_D = Db + Da |alpha| (T: affine in alpha; numbers A, Da set so that induced drag at alpha = 0.25 is about 0.05)
AMAX = 0.45             # rad  stall smoothing
CDA_FUS = (0.0030, 0.0300, 0.0200)   # m^2 drag areas x y z   (A)
CDR_FUS = (0.002, 0.01, 0.01)        # N m s/rad  rotational damping of the fuselage  (A)
LA_TAIL, LB_TAIL, DA_TAIL, DB_TAIL = 3.2, 0.0, 0.5, 0.03   # low aspect ratio tail     (A)

# --------------------------------------------------------------------------- aeroelastic wing joints
K_SWEEP = 40.0          # N m/rad  held sweep rotation (about the vertical wing axis)
K_PIVOT = 2.0e4         # N/m  pivot translations
B_PIVOT = 25.0
B_SWEEP = 0.2
KP_TORS = (0.60, 0.50)  # N m/rad  torsion (aeroelastic pitch) stiffness inner / outer joint   (A, ~ G J / L of a foam+carbon wing)
BP_TORS = (0.010, 0.008)
K_BEND2 = 12.0          # N m/rad  bending of the outer segment against the inner one: E I / L, E I = 2.4 N m^2 (carbon rods, thesis eq 15)  (A)
B_BEND2 = 0.06
K_BEND1 = 0.0
INCIDENCE = 0.12       # rad rigging incidence of the wing roots (A)
THETA_ROD, PS_ROD = 0.30, 0.80   # rear-rod pitch amplitude / phase lag (thesis: rear rod lags the front rod; numbers A)
DIHEDRAL = 0.05         # rad mean flap angle (dihedral)

# --------------------------------------------------------------------------- flapping drive
N_GEAR = 28.0
PHI_FLAP = 0.50         # rad amplitude (T: flapping 2..4 Hz; amplitude A)
H2, PH2 = 0.06, 0.8
K_MOTOR = 0.0125        # N m/A and V s/rad
R_W, L_W = 0.15, 1.0e-4
J_M = 4.0e-6            # kg m^2 rotor
B_M = 1.0e-5
V_BAT = 22.2            # V 6S pack
K_SHAFT, D_SHAFT = 120.0, 0.5   # N m/rad crank-to-wing compliance (keeps the multibond joint rate integral)
F_MIN, F_MAX = 2.0, 4.5

# --------------------------------------------------------------------------- tail servos
SERVO = dict(Tsv=0.04, Kp=1.5, Kd=0.01, tau_max=0.3, dmax=0.6)
FLAP_LIM = 0.5          # rad usable deflection

# --------------------------------------------------------------------------- helpers
def rotmat_from_cols(x, y, z):
    return np.array([x, y, z], dtype=float).T


def quat_from_matrix(R):
    R = np.asarray(R, dtype=float)
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = [(R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s]
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = [(R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = [(R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s]
    q = np.array(q)
    return q / np.linalg.norm(q) * (1 if q[0] >= 0 else -1)


def matrix_from_quat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1.0, 0], [-s, 0, c]])


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0, 0], [0, c, -s], [0, s, c]])


# --------------------------------------------------------------------------- derived wing geometry
def segment_strips(length, chord_root, chord_tip, ns=NS):
    """Strip centres along the span (from the segment root), widths, areas and chords of one segment."""
    w = length / ns
    rs = [w * (i + 0.5) for i in range(ns)]
    ch = [chord_root + (chord_tip - chord_root) * r / length for r in rs]
    return rs, [w * c for c in ch], ch


def wing_area():
    a1 = sum(segment_strips(L1, *C1)[1])
    a2 = sum(segment_strips(L2, *C2)[1])
    return a1 + a2


def inertia_plate(m, span, chord):
    """Principal moments (about chord axis z_j... ) in joint-frame order (x_j span, y_j normal, z_j chord)."""
    return [m * chord**2 / 12 + 1e-6, m * (span**2 + chord**2) / 12, m * span**2 / 12]


M_TOTAL = M_FUS + 2 * (M1 + M2) + 3 * M_FLAP
