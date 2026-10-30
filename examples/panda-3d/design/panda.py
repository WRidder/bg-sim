# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""The Franka Emika Panda: kinematics, Gaz et al. 2019 dynamics, drives and the analytical IK.

Every number of the `panda-3d` example lives here, with its source:

* **Kinematics** (modified DH, Craig convention) as published by Franka Robotics
  (https://frankaemika.github.io/docs/control_parameters.html) and in the official
  `franka_description` URDF (`robots/common/franka_arm.xacro` of `frankaemika/franka_ros`,
  Apache-2.0): link frame i is the URDF `panda_link<i>` frame. `check_urdf()` verifies that the
  URDF joint origins and the DH table give the same forward kinematics.
* **Dynamics**: C. Gaz, M. Cognetti, A. Oliva, P. Robuffo Giordano, A. De Luca, "Dynamic
  Identification of the Franka Emika Panda Robot With Retrieval of Feasible Parameters Using
  Penalty-Based Optimization", IEEE RA-L 4(4), 2019, the physically feasible set `p^` as
  printed in Tables VIII and IX of the authors' supplementary material (revised Oct 15 2019,
  `pdf/` of github.com/marcocognetti/FrankaEmikaPandaDynModel): masses, centres of mass in the
  link frame, inertia tensors about the centre of mass in link-frame axes. `c1z` is a "don't
  care" in the paper (it does not enter the dynamics); we use -0.04762 m, the value of the
  official `franka_description/robots/common/inertial.yaml`, which places it inside link 1.
  The friction model is Table I of the same supplementary:
  `tau_f = phi1 / (1 + exp(-phi2 (qd + phi3))) - phi1 / (1 + exp(-phi2 phi3))`.
* **Drives**: the joint torque limits are Franka's (`joint_limits.yaml`: 87 N m for joints 1-4,
  12 N m for 5-7). Gear ratio, rotor inertia, joint (gear) stiffness and damping are **assumed**
  (Franka publishes none of them; see `DRIVE_NOTE`).
* **IK**: the case-consistent geometric solver of Y. He and S. Liu, "Analytical Inverse
  Kinematics for Franka Emika Panda - a Geometrical Solver for 7-DOF Manipulators with
  Unconventional Design", ICCMA 2021 (github.com/ffall007/franka_analytical_ik, Apache-2.0),
  re-derived here for the flange frame (no hand): q7 is the redundancy parameter.

    uv run examples/panda-3d/design/panda.py      # prints the design report and the self checks
"""

from __future__ import annotations

import math

import numpy as np

G0 = 9.81  # gravity [m/s^2] (Pinocchio's default too)
NJ = 7

# ------------------------------------------------------------------ kinematics (Franka, modified DH)
# row i (joint i): a_{i-1} [m], d_i [m], alpha_{i-1} [rad];  T_{i-1,i} = Rx(alpha) Tx(a) Rz(q) Tz(d)
DH = [
    (0.0, 0.333, 0.0),
    (0.0, 0.0, -math.pi / 2),
    (0.0, 0.316, math.pi / 2),
    (0.0825, 0.0, math.pi / 2),
    (-0.0825, 0.384, -math.pi / 2),
    (0.0, 0.0, math.pi / 2),
    (0.088, 0.0, math.pi / 2),
]
D_FLANGE = 0.107  # flange (panda_link8) along z7 [m]

# URDF joint origins of franka_arm.xacro (rpy, xyz), for check_urdf()
URDF_JOINTS = [
    ((0.0, 0.0, 0.0), (0.0, 0.0, 0.333)),
    ((-math.pi / 2, 0.0, 0.0), (0.0, 0.0, 0.0)),
    ((math.pi / 2, 0.0, 0.0), (0.0, -0.316, 0.0)),
    ((math.pi / 2, 0.0, 0.0), (0.0825, 0.0, 0.0)),
    ((-math.pi / 2, 0.0, 0.0), (-0.0825, 0.384, 0.0)),
    ((math.pi / 2, 0.0, 0.0), (0.0, 0.0, 0.0)),
    ((math.pi / 2, 0.0, 0.0), (0.088, 0.0, 0.0)),
]

Q_MIN = np.array([-2.8973, -1.7628, -2.8973, -3.0718, -2.8973, -0.0175, -2.8973])
Q_MAX = np.array([2.8973, 1.7628, 2.8973, -0.0698, 2.8973, 3.7525, 2.8973])
QD_MAX = np.array([2.1750, 2.1750, 2.1750, 2.1750, 2.6100, 2.6100, 2.6100])
TAU_MAX = np.array([87.0, 87.0, 87.0, 87.0, 12.0, 12.0, 12.0])

# ------------------------------------------------------------------ Gaz et al. 2019, feasible p^
MASS = np.array([4.970684, 0.646926, 3.228604, 3.587895, 1.225946, 1.666555, 7.35522e-01])
COM = np.array(
    [
        [3.875e-03, 2.081e-03, -0.04762],  # c1z: "don't care" (*); franka_description value
        [-3.141e-03, -2.872e-02, 3.495e-03],
        [2.7518e-02, 3.9252e-02, -6.6502e-02],
        [-5.317e-02, 1.04419e-01, 2.7454e-02],
        [-1.1953e-02, 4.1065e-02, -3.8437e-02],
        [6.0149e-02, -1.4117e-02, -1.0517e-02],
        [1.0517e-02, -4.252e-03, 6.1597e-02],
    ]
)
# Ixx, Ixy, Ixz, Iyy, Iyz, Izz about the centre of mass, link-frame axes [kg m^2]
INERTIA6 = np.array(
    [
        [7.0337e-01, -1.3900e-04, 6.7720e-03, 7.0661e-01, 1.9169e-02, 9.1170e-03],
        [7.9620e-03, -3.9250e-03, 1.0254e-02, 2.8110e-02, 7.0400e-04, 2.5995e-02],
        [3.7242e-02, -4.7610e-03, -1.1396e-02, 3.6155e-02, -1.2805e-02, 1.0830e-02],
        [2.5853e-02, 7.7960e-03, -1.3320e-03, 1.9552e-02, 8.6410e-03, 2.8323e-02],
        [3.5549e-02, -2.1170e-03, -4.0370e-03, 2.9474e-02, 2.2900e-04, 8.6270e-03],
        [1.9640e-03, 1.0900e-04, -1.1580e-03, 4.3540e-03, 3.4100e-04, 5.4330e-03],
        [1.2516e-02, -4.2800e-04, -1.1960e-03, 1.0027e-02, -7.4100e-04, 4.8150e-03],
    ]
)
# friction, Table I of the supplementary
PHI1 = np.array([5.4615e-01, 0.87224, 6.4068e-01, 1.2794e00, 8.3904e-01, 3.0301e-01, 5.6489e-01])
PHI2 = np.array([5.1181e00, 9.0657e00, 1.0136e01, 5.5903e00, 8.3469e00, 1.7133e01, 1.0336e01])
PHI3 = np.array([3.9533e-02, 2.5882e-02, -4.6070e-02, 3.6194e-02, 2.6226e-02, -2.1047e-02, 3.5526e-03])

# ------------------------------------------------------------------ drives (assumptions)
N_GEAR = np.array([100.0] * 7)  # gear ratio (motor rate / link rate)
J_ROTOR = np.array([5.0e-5] * 4 + [1.0e-5] * 3)  # rotor inertia, motor side [kg m^2]
K_GEAR = np.array([1.0e4] * 4 + [5.0e3] * 3)  # joint (gear + torque sensor) stiffness [N m/rad]
ZETA_GEAR = 0.2  # damping ratio of the rotor-on-spring mode (link held)
DRIVE_NOTE = (
    "Franka publishes no gear ratio, rotor inertia or joint stiffness. Assumed: N = 100 "
    "(harmonic drive), rotor J_m = 5e-5 kg m^2 (joints 1-4) and 1e-5 kg m^2 (5-7), i.e. "
    "reflected N^2 J_m = 0.5 and 0.1 kg m^2, joint stiffness 1e4 and 5e3 N m/rad, rotor-mode "
    "damping ratio 0.2."
)
ENCODER_BITS = 20  # link-side absolute encoder (assumed), counts per revolution 2^20
ENCODER_RES = 2 * math.pi / 2**ENCODER_BITS

# ------------------------------------------------------------------ poses of the example
Q_READY = np.array([0.0, -math.pi / 4, 0.0, -3 * math.pi / 4, 0.0, math.pi / 2, math.pi / 4])


# ================================================================== small SE(3) helpers
def rotx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rotz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rpy(r: float, p: float, y: float) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def hom(r: np.ndarray, p) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = r
    t[:3, 3] = p
    return t


def quat_of(r: np.ndarray) -> np.ndarray:
    """Unit quaternion (w, x, y, z) of a rotation matrix, w >= 0."""
    tr = np.trace(r)
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = [0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s]
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = [(r[2, 1] - r[1, 2]) / s, 0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s]
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = [(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = [(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s]
    q = np.array(q)
    q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def rot_of_quat(q) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def pose7(t: np.ndarray) -> list[float]:
    """The D-MB6 chart (qw, qx, qy, qz, x, y, z) of a homogeneous transform."""
    return [*quat_of(t[:3, :3]), *t[:3, 3]]


# ================================================================== kinematics
def joint_frame(i: int) -> np.ndarray:
    """LN_i: the joint-i frame (before the rotation q_i) in link frame i-1 (i = 0..6)."""
    a, d, alpha = DH[i]
    return hom(rotx(alpha), [0.0, 0.0, 0.0]) @ hom(np.eye(3), [a, 0.0, 0.0]) @ hom(np.eye(3), [0.0, 0.0, d])


def link_frames(q) -> list[np.ndarray]:
    """World poses of link frames 1..7 and of the flange (8 entries)."""
    t = np.eye(4)
    out = []
    for i in range(NJ):
        t = t @ joint_frame(i) @ hom(rotz(q[i]), [0.0, 0.0, 0.0])
        out.append(t.copy())
    out.append(t @ hom(np.eye(3), [0.0, 0.0, D_FLANGE]))
    return out


def fk_flange(q) -> np.ndarray:
    return link_frames(q)[-1]


def check_urdf() -> float:
    """Largest FK difference (m or rotation-matrix entry) between the DH table and the URDF origins."""
    rng = np.random.default_rng(1)
    worst = 0.0
    for _ in range(200):
        q = rng.uniform(Q_MIN, Q_MAX)
        t = np.eye(4)
        for i, (r, p) in enumerate(URDF_JOINTS):
            t = t @ hom(rpy(*r), p) @ hom(rotz(q[i]), [0, 0, 0])
        t = t @ hom(np.eye(3), [0, 0, D_FLANGE])
        worst = max(worst, float(np.abs(t - fk_flange(q)).max()))
    return worst


def inertia_matrix(i: int) -> np.ndarray:
    xx, xy, xz, yy, yz, zz = INERTIA6[i]
    return np.array([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]])


def principal(i: int) -> tuple[np.ndarray, np.ndarray]:
    """(J, R): principal moments and the rotation whose columns are the principal axes (det +1)."""
    w, v = np.linalg.eigh(inertia_matrix(i))
    if np.linalg.det(v) < 0:
        v[:, 2] = -v[:, 2]
    return w, v


def com_frame(i: int) -> np.ndarray:
    """LC_i: the principal centre-of-mass frame of body i in link frame i."""
    _, r = principal(i)
    return hom(r, COM[i])


# ================================================================== dynamics (recursive Newton-Euler)
def rnea_wrenches(q, qd, qdd, g0: float = G0) -> tuple[np.ndarray, list[np.ndarray], list[np.ndarray]]:
    """Newton-Euler (Craig): joint torques and, per joint i, the force f_i and the moment n_i
    (about the joint origin) that link i-1 exerts on link i, both in link frame i."""
    frames = [joint_frame(i) @ hom(rotz(q[i]), [0, 0, 0]) for i in range(NJ)]
    w = np.zeros(3)
    wd = np.zeros(3)
    a = np.array([0.0, 0.0, g0])  # base acceleration = -gravity
    f_list, n_list, r_list, p_list = [], [], [], []
    z = np.array([0.0, 0.0, 1.0])
    for i in range(NJ):
        r = frames[i][:3, :3]  # R_{i-1,i}
        p = frames[i][:3, 3]  # origin of i in i-1
        rt = r.T
        w_new = rt @ w + qd[i] * z
        wd_new = rt @ wd + np.cross(rt @ w, qd[i] * z) + qdd[i] * z
        a_new = rt @ (a + np.cross(wd, p) + np.cross(w, np.cross(w, p)))
        w, wd, a = w_new, wd_new, a_new
        c = COM[i]
        ac = a + np.cross(wd, c) + np.cross(w, np.cross(w, c))
        ic = inertia_matrix(i)
        f_list.append(MASS[i] * ac)
        n_list.append(ic @ wd + np.cross(w, ic @ w))
        r_list.append(r)
        p_list.append(p)
    tau = np.zeros(NJ)
    fs: list[np.ndarray] = [np.zeros(3)] * NJ
    ns: list[np.ndarray] = [np.zeros(3)] * NJ
    f = np.zeros(3)
    n = np.zeros(3)
    for i in reversed(range(NJ)):
        if i + 1 < NJ:
            r_next, p_next = r_list[i + 1], p_list[i + 1]
            f_child, n_child = r_next @ f, r_next @ n + np.cross(p_next, r_next @ f)
        else:
            f_child, n_child = np.zeros(3), np.zeros(3)
        f = f_list[i] + f_child
        n = n_list[i] + n_child + np.cross(COM[i], f_list[i])
        fs[i], ns[i] = f.copy(), n.copy()
        tau[i] = n[2]
    return tau, fs, ns


def rnea(q, qd, qdd, g0: float = G0) -> np.ndarray:
    """Joint torques of the rigid arm (no friction, no drives): M qdd + c + g."""
    return rnea_wrenches(q, qd, qdd, g0)[0]


def gravity(q) -> np.ndarray:
    return rnea(q, np.zeros(NJ), np.zeros(NJ))


def mass_matrix(q) -> np.ndarray:
    m = np.zeros((NJ, NJ))
    for j in range(NJ):
        e = np.zeros(NJ)
        e[j] = 1.0
        m[:, j] = rnea(q, np.zeros(NJ), e, g0=0.0)
    return m


def friction(qd) -> np.ndarray:
    qd = np.asarray(qd, dtype=float)
    return PHI1 / (1 + np.exp(-PHI2 * (qd + PHI3))) - PHI1 / (1 + np.exp(-PHI2 * PHI3))


def joint_wrenches(q, qdd=None, g0: float = G0) -> list[tuple[np.ndarray, np.ndarray]]:
    """The load each joint's held directions carry, in link frame i: (force, moment about the
    joint origin) that the distal arm exerts on its parent through joint i (minus the
    Newton-Euler joint reaction). At rest (`qdd = None`) it is the weight of everything distal;
    for an arm released with zero torque pass its rigid-body acceleration, so the compliant
    joints start on the deflections of that motion instead of ringing (start of `panda-free`)."""
    qdd = np.zeros(NJ) if qdd is None else np.asarray(qdd, dtype=float)
    _, fs, ns = rnea_wrenches(q, np.zeros(NJ), qdd, g0)
    return [(-fs[i], -ns[i]) for i in range(NJ)]


def forward_dynamics(q, qd, tau) -> np.ndarray:
    return np.linalg.solve(mass_matrix(q), np.asarray(tau) - rnea(q, qd, np.zeros(NJ)))


# ================================================================== analytical IK (He & Liu, flange frame)
D1, D3, D5, A4, A7 = 0.333, 0.316, 0.384, 0.0825, 0.088
LL24 = A4 * A4 + D3 * D3
LL46 = A4 * A4 + D5 * D5
L24 = math.sqrt(LL24)
L46 = math.sqrt(LL46)
TH_H46 = math.atan(D5 / A4)
TH_342 = math.atan(D3 / A4)
TH_46H = math.atan(A4 / D5)


def ik_flange(t_f: np.ndarray, q7: float, q_actual) -> tuple[np.ndarray | None, int]:
    """Case-consistent IK for the flange pose `t_f` with the redundancy parameter q7.

    Returns (q, code): code 0 = solved; 1 = unreachable (triangle inequality); 2..8 = joint
    limit of joint code-1 violated; 9 = q7 out of range. The solution branch (shoulder sign of
    q2 and the q6 case) is taken from `q_actual`, so a continuous path keeps its branch.
    """
    if q7 <= Q_MIN[6] or q7 >= Q_MAX[6]:
        return None, 9
    q = np.zeros(7)
    q[6] = q7
    # branch of the current configuration
    fr = link_frames(q_actual)
    p2a = np.array([0.0, 0.0, D1])
    o4 = fr[3][:3, 3]
    pha = o4 - A4 * fr[3][:3, 0]  # the point H of the paper: O4 minus a4 along x4
    p6a = fr[5][:3, 3]
    z6a = fr[5][:3, 2]
    case6_0 = float(np.cross(pha - p6a, p2a - p6a) @ z6a) <= 0.0
    case1_1 = q_actual[1] < 0.0

    r_f = t_f[:3, :3]
    z_f = r_f[:, 2]
    p_7 = t_f[:3, 3] - D_FLANGE * z_f
    x_6 = r_f @ np.array([math.cos(q7), -math.sin(q7), 0.0])
    x_6 /= np.linalg.norm(x_6)
    p_6 = p_7 - A7 * x_6
    v26 = p_6 - p2a
    ll26 = float(v26 @ v26)
    l26 = math.sqrt(ll26)
    if L24 + L46 < l26 or L24 + l26 < L46 or l26 + L46 < L24:
        return None, 1
    th246 = math.acos((LL24 + LL46 - ll26) / 2 / L24 / L46)
    q[3] = th246 + TH_H46 + TH_342 - 2 * math.pi
    if q[3] <= Q_MIN[3] or q[3] >= Q_MAX[3]:
        return None, 5
    th462 = math.acos((ll26 + LL46 - LL24) / 2 / l26 / L46)
    th26h = TH_46H + th462
    d26 = -l26 * math.cos(th26h)
    z6 = np.cross(z_f, x_6)
    y6 = np.cross(z6, x_6)
    r6 = np.column_stack([x_6, y6 / np.linalg.norm(y6), z6 / np.linalg.norm(z6)])
    v662 = r6.T @ (-v26)
    phi6 = math.atan2(v662[1], v662[0])
    theta6 = math.asin(d26 / math.hypot(v662[0], v662[1]))
    q[5] = (math.pi - theta6 - phi6) if case6_0 else (theta6 - phi6)
    if q[5] <= Q_MIN[5]:
        q[5] += 2 * math.pi
    elif q[5] >= Q_MAX[5]:
        q[5] -= 2 * math.pi
    if q[5] <= Q_MIN[5] or q[5] >= Q_MAX[5]:
        return None, 7
    th_p26 = 1.5 * math.pi - th462 - th246 - TH_342
    th_p = math.pi - th_p26 - th26h
    lp6 = l26 * math.sin(th_p26) / math.sin(th_p)
    z5 = r6 @ np.array([math.sin(q[5]), math.cos(q[5]), 0.0])
    v2p = p_6 - lp6 * z5 - p2a
    l2p = float(np.linalg.norm(v2p))
    if math.hypot(v2p[0], v2p[1]) < 1e-9 * l2p:  # shoulder singularity: keep q1
        q[0] = q_actual[0]
        q[1] = 0.0
    else:
        q[0] = math.atan2(v2p[1], v2p[0])
        q[1] = math.acos(v2p[2] / l2p)
        if case1_1:
            q[0] = q[0] + math.pi if q[0] < 0 else q[0] - math.pi
            q[1] = -q[1]
    if q[0] <= Q_MIN[0] or q[0] >= Q_MAX[0]:
        return None, 2
    if q[1] <= Q_MIN[1] or q[1] >= Q_MAX[1]:
        return None, 3
    z3 = v2p / l2p
    y3 = -np.cross(v26, v2p)
    y3 /= np.linalg.norm(y3)
    x3 = np.cross(y3, z3)
    c1, s1 = math.cos(q[0]), math.sin(q[0])
    c2, s2 = math.cos(q[1]), math.sin(q[1])
    r1 = np.array([[c1, -s1, 0], [s1, c1, 0], [0, 0, 1.0]])
    r12 = np.array([[c2, -s2, 0], [0, 0, 1.0], [-s2, -c2, 0]])
    x23 = (r1 @ r12).T @ x3
    q[2] = math.atan2(x23[2], x23[0])
    if q[2] <= Q_MIN[2] or q[2] >= Q_MAX[2]:
        return None, 4
    vh4 = p2a + D3 * z3 + A4 * x3 - p_6 + D5 * z5
    c6, s6 = math.cos(q[5]), math.sin(q[5])
    r56 = np.array([[c6, -s6, 0], [0, 0, -1.0], [s6, c6, 0]])
    r5 = r6 @ r56.T
    v5h4 = r5.T @ vh4
    q[4] = -math.atan2(v5h4[1], v5h4[0])
    if q[4] <= Q_MIN[4] or q[4] >= Q_MAX[4]:
        return None, 6
    return q, 0


Q4_PRACTICAL = -0.5  # the solver's elbow family: theta246 = acos(...) <= pi gives q4 <= -0.467 rad


def ik_roundtrip(n: int = 20000, seed: int = 7, q4_max: float = Q4_PRACTICAL) -> dict:
    """FK -> IK round trip at random joint vectors inside the limits (q7 and the branch from q).

    He & Liu's solver returns the elbow family with q4 <= -0.467 rad (the 2-4-6 triangle is not
    folded through); a pose reached with a more stretched elbow (q4 in (-0.467, -0.0698)) is
    reported as a joint-limit failure of another joint. `q4_max` limits the samples to the
    solver's family; pass `Q_MAX[3]` to sample the whole range and count the failures.
    """
    rng = np.random.default_rng(seed)
    margin = 0.05
    lo, hi = Q_MIN + margin, Q_MAX - margin
    hi[3] = min(hi[3], q4_max)
    worst_q = worst_p = worst_r = 0.0
    solved = 0
    failed = {}
    for _ in range(n):
        q = rng.uniform(lo, hi)
        t = fk_flange(q)
        sol, code = ik_flange(t, q[6], q)
        if sol is None:
            failed[code] = failed.get(code, 0) + 1
            continue
        solved += 1
        t2 = fk_flange(sol)
        worst_p = max(worst_p, float(np.linalg.norm(t2[:3, 3] - t[:3, 3])))
        worst_r = max(worst_r, float(np.abs(t2[:3, :3] - t[:3, :3]).max()))
        worst_q = max(worst_q, float(np.abs(sol - q).max()))
    return {"n": n, "q4_max": float(hi[3]), "solved": solved, "failed": failed, "max_pos_err": worst_p,
            "max_rot_err": worst_r, "max_q_err": worst_q}  # fmt: skip


# ================================================================== report
def main() -> None:
    np.set_printoptions(precision=6, suppress=True, linewidth=120)
    print(f"URDF origins vs modified DH, max FK difference over 200 poses: {check_urdf():.3e}")
    print("ready pose flange:", fk_flange(Q_READY)[:3, 3])
    print("G(ready) =", gravity(Q_READY))
    print("M(ready) diag =", np.diag(mass_matrix(Q_READY)))
    for i in range(NJ):
        j, r = principal(i)
        print(f"link {i + 1}: m = {MASS[i]:.6f}, J principal = {j}, min triangle margin = "
              f"{min(j[0] + j[1] - j[2], j[1] + j[2] - j[0], j[0] + j[2] - j[1]):.3e}")  # fmt: skip
    print("IK round trip:", ik_roundtrip())


if __name__ == "__main__":
    main()
