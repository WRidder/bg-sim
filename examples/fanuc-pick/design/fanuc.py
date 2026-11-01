# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""The robot of the `fanuc-pick` example: kinematics, datasheet limits, FK and IK.

The user's cell has a FANUC **LR-10iA/10** (reach 1101 mm, payload 10 kg). No URDF, xacro or
mesh of that robot is published (not in `ros-industrial/fanuc`, not in `fanuc_experimental`,
not on GitHub; checked 2026-11-01), so the *geometry* (kinematics and meshes) is the closest
FANUC arm whose sources are all open: the **LR Mate 200iD/7L** (reach 911 mm, payload 7 kg;
the same enclosed, slim LR family, six axes, spherical wrist).

The arm is **kinematic**: it follows the planned joint trajectory exactly, and the plan is
checked against the **LR-10iA/10 datasheet limits** (the robot of the cell), so no arm
dynamics, drives or joint servos are modelled. Every number names its source:

* **Kinematics, meshes**: `fanuc_lrmate200id_support/urdf/lrmate200id7l_macro.xacro` of
  github.com/ros-industrial/fanuc (BSD-3-Clause, `noetic-devel` at
  d8f42bd73584b255df87098395512538882caea1, package version 0.6.0).
* **Rate limits and wrist load ratings**: LR-10iA/10 (FANUC catalogue RLR-10iA(E)-01, 2022.3):
  300, 230, 340, 500, 400, 800 deg/s; payload 10 kg; allowable wrist moment J4/J5/J6
  21/21/10 N m; allowable wrist inertia 0.77/0.77/0.28 kg m^2. The LR Mate 200iD/7L values
  (catalogue LRMateiD(E)-07, column 7L, equal to the URDF rates) are kept as `LR7L_*`.
* **Joint ranges**: J1 +-185 deg (LR-10iA/10 drawing); J4, J5, J6 +-190, +-125, +-360 (both
  robots); J2 the LR-10iA/10 total 235 deg split like the URDF (-96..139); J3 the URDF range
  -70..213 (narrower than the LR-10iA/10 total of 421 deg, which counts J3 FANUC-coupled).
* **Acceleration and jerk limits**: no FANUC datasheet publishes them. **Assumed**: the rate
  limit is reached in `T_ACC` (0.15 s for J1-J3, 0.10 s for J4-J6) and the acceleration
  limit in `T_JERK` = 0.05 s. Replace with the controller's settings when known.

URDF frames: link i is `link_i`; joint i sits at `JOINT_ORIGIN[i]` in link i-1 (no fixed
rotation in this URDF) and turns about `JOINT_AXIS[i]`; the flange is the `link_6` frame,
its x axis is the tool axis (the ROS `tool0` frame has its z along flange x).

    uv run examples/fanuc-pick/design/fanuc.py      # self checks (FK/IK round trip)
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
G0 = 9.81
NJ = 6

# ------------------------------------------------------------------ kinematics (URDF)
JOINT_ORIGIN = np.array([
    [0.0, 0.0, 0.330],
    [0.050, 0.0, 0.0],
    [0.0, 0.0, 0.440],
    [0.0, 0.0, 0.035],
    [0.420, 0.0, 0.0],
    [0.080, 0.0, 0.0],
])
JOINT_AXIS = np.array([
    [0.0, 0.0, 1.0],
    [0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0],
    [-1.0, 0.0, 0.0],
    [0.0, -1.0, 0.0],
    [-1.0, 0.0, 0.0],
])
A1, D1, A2, A3, D4, D6 = 0.050, 0.330, 0.440, 0.035, 0.420, 0.080
L3 = math.hypot(D4, A3)          # J3 -> wrist centre
PHI3 = math.atan2(A3, D4)        # its angle above the forearm axis

DEG = math.pi / 180.0
#: joint ranges used as constraints (see the module docstring)
Q_MIN = np.array([-185.0, -96.0, -70.0, -190.0, -125.0, -360.0]) * DEG
Q_MAX = np.array([185.0, 139.0, 213.0, 190.0, 125.0, 360.0]) * DEG
#: URDF ranges of the modelled geometry (LR Mate 200iD/7L)
URDF_Q_MIN = np.array([-170.0, -100.0, -70.0, -190.0, -125.0, -360.0]) * DEG
URDF_Q_MAX = np.array([170.0, 145.0, 213.0, 190.0, 125.0, 360.0]) * DEG

# FANUC LR-10iA/10 (catalogue RLR-10iA(E)-01): motion range (total), maximum speed, wrist ratings
LR10_RANGE_DEG = np.array([370.0, 235.0, 421.0, 380.0, 250.0, 720.0])
LR10_QD_MAX = np.array([300.0, 230.0, 340.0, 500.0, 400.0, 800.0]) * DEG
LR10_REACH, LR10_PAYLOAD, LR10_MASS = 1.101, 10.0, 46.0
LR10_M_WRIST = np.array([21.0, 21.0, 10.0])      # N m, allowable load moment J4, J5, J6
LR10_I_WRIST = np.array([0.77, 0.77, 0.28])      # kg m^2, allowable load inertia J4, J5, J6
# LR Mate 200iD/7L (catalogue LRMateiD(E)-07), the geometry of the model
LR7L_RANGE_DEG = np.array([340.0, 245.0, 430.0, 380.0, 250.0, 720.0])
LR7L_QD_MAX = np.array([370.0, 310.0, 410.0, 550.0, 545.0, 1000.0]) * DEG
LR7L_REACH, LR7L_PAYLOAD, LR7L_MASS = 0.911, 7.0, 27.0

#: the limits of the study: LR-10iA/10 rates, assumed acceleration and jerk
QD_MAX = LR10_QD_MAX
T_ACC = np.array([0.15, 0.15, 0.15, 0.10, 0.10, 0.10])
QDD_MAX = QD_MAX / T_ACC
T_JERK = 0.05
QDDD_MAX = QDD_MAX / T_JERK

# ================================================================== small SE(3) helpers
def rot_axis(axis, a: float) -> np.ndarray:
    """Rotation by `a` about the unit vector `axis` (Rodrigues)."""
    k = np.asarray(axis, dtype=float)
    k = k / np.linalg.norm(k)
    kx = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(a) * kx + (1.0 - math.cos(a)) * (kx @ kx)


def rotx(a: float) -> np.ndarray:
    return rot_axis([1, 0, 0], a)


def roty(a: float) -> np.ndarray:
    return rot_axis([0, 1, 0], a)


def rotz(a: float) -> np.ndarray:
    return rot_axis([0, 0, 1], a)


def hom(r: np.ndarray, p) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = r
    t[:3, 3] = p
    return t


def inv(t: np.ndarray) -> np.ndarray:
    return hom(t[:3, :3].T, -t[:3, :3].T @ t[:3, 3])


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
    w, x, y, z = np.asarray(q, dtype=float) / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def pose7(t: np.ndarray) -> list[float]:
    """The D-MB6 chart (qw, qx, qy, qz, x, y, z) of a homogeneous transform."""
    return [float(v) for v in (*quat_of(t[:3, :3]), *t[:3, 3])]


def axis_to_z(axis) -> np.ndarray:
    """A rotation R_a whose z column is `axis` (the bg-sim joint frame turns about its local z)."""
    a = np.asarray(axis, dtype=float)
    if np.allclose(a, [0, 0, 1]):
        return np.eye(3)
    if np.allclose(a, [0, 0, -1]):
        return rotx(math.pi)
    # z -> a: rotate about z x a
    k = np.cross([0.0, 0.0, 1.0], a)
    ang = math.acos(max(-1.0, min(1.0, a[2])))
    return rot_axis(k, ang)


# ================================================================== forward kinematics
def link_frames(q) -> list[np.ndarray]:
    """World poses of link_1..link_6 (the base_link at the world origin)."""
    t = np.eye(4)
    out = []
    for i in range(NJ):
        t = t @ hom(np.eye(3), JOINT_ORIGIN[i]) @ hom(rot_axis(JOINT_AXIS[i], q[i]), [0, 0, 0])
        out.append(t.copy())
    return out


def fk_flange(q) -> np.ndarray:
    return link_frames(q)[-1]


#: the gripper frame G at the flange: z_G = -x_flange (up when the tool points down)
R_FLANGE_G = roty(-math.pi / 2)   # G axes in the flange frame
R_G_FLANGE = R_FLANGE_G.T


def flange_down(x: float, y: float, z: float, yaw: float) -> np.ndarray:
    """Flange pose for the tool pointing straight down with the gripper frame turned by `yaw`."""
    return hom(rotz(yaw) @ R_G_FLANGE, [x, y, z])


# ================================================================== analytical IK
def wrap_near(a: float, ref: float) -> float:
    return a + 2 * math.pi * round((ref - a) / (2 * math.pi))


def ik(t_f: np.ndarray, q6_ref: float | None = None) -> np.ndarray:
    """Front, elbow-up, no-flip solution of the flange pose `t_f` (J4 near 0 for the tool down).

    Wrist centre `wc = p - D6 x_f`; `q1 = atan2(wc_y, wc_x)`; in the arm plane
    `r = |wc_xy| - A1`, `z = wc_z - D1`, `sin(q3 + phi) = (r^2 + z^2 - A2^2 - L3^2)/(2 A2 L3)`;
    `q2 = atan2(A r - B z, B r + A z)` with `A = A2 + L3 sin g`, `B = L3 cos g`, `g = q3 + phi`;
    the wrist is the X-Y-X Euler decomposition of `R03^T R_f = Rx(-q4) Ry(-q5) Rx(-q6)`.
    """
    r_f, p = t_f[:3, :3], t_f[:3, 3]
    wc = p - D6 * r_f[:, 0]
    q1 = math.atan2(wc[1], wc[0])
    rr = math.hypot(wc[0], wc[1]) - A1
    zz = wc[2] - D1
    s = (rr * rr + zz * zz - A2 * A2 - L3 * L3) / (2 * A2 * L3)
    if abs(s) > 1.0:
        raise ValueError("pose out of reach")
    g = math.asin(s)
    a_ = A2 + L3 * math.sin(g)
    b_ = L3 * math.cos(g)
    q2 = math.atan2(a_ * rr - b_ * zz, b_ * rr + a_ * zz)
    q3 = g - PHI3
    r03 = rotz(q1) @ roty(q2 - q3)
    m = r03.T @ r_f
    c5 = max(-1.0, min(1.0, m[0, 0]))
    if m[2, 0] <= 0.0:
        b = math.acos(c5)
        a = math.atan2(m[1, 0], -m[2, 0])
        c = math.atan2(m[0, 1], m[0, 2])
    else:
        b = -math.acos(c5)
        a = math.atan2(-m[1, 0], m[2, 0])
        c = math.atan2(-m[0, 1], -m[0, 2])
    q4, q5, q6 = -a, -b, -c
    if q6_ref is not None:
        q6 = wrap_near(q6, q6_ref)
    return np.array([q1, q2, q3, q4, q5, q6])


def ik_down(x: float, y: float, z: float, yaw: float) -> np.ndarray:
    """IK of `flange_down`, with q6 unwrapped next to its tool-down value yaw - q1."""
    q1 = math.atan2(y, x)
    return ik(flange_down(x, y, z, yaw), q6_ref=yaw - q1)


# ================================================================== self checks
def ik_roundtrip(n: int = 20000, seed: int = 3) -> dict:
    """FK -> IK -> FK over random reachable tool-down poses in front of the robot."""
    rng = np.random.default_rng(seed)
    worst_p = worst_r = worst_q = 0.0
    done = 0
    while done < n:
        x = rng.uniform(0.25, 0.75)
        y = rng.uniform(-0.55, 0.55)
        z = rng.uniform(0.15, 0.60)
        yaw = rng.uniform(-math.pi, math.pi)
        t = flange_down(x, y, z, yaw)
        try:
            q = ik_down(x, y, z, yaw)
        except ValueError:
            continue
        if np.any(q < Q_MIN) or np.any(q > Q_MAX):
            continue
        t2 = fk_flange(q)
        worst_p = max(worst_p, float(np.abs(t2[:3, 3] - t[:3, 3]).max()))
        worst_r = max(worst_r, float(np.abs(t2[:3, :3] - t[:3, :3]).max()))
        q2 = ik(t2, q6_ref=q[5])
        worst_q = max(worst_q, float(np.abs(q2 - q).max()))
        done += 1
    return {"n": n, "pos": worst_p, "rot": worst_r, "q": worst_q}


def fk_down(q) -> tuple[float, float, float, float]:
    """Flange position and gripper yaw of a tool-down configuration (q4 = 0, q5 = q2 - q3 - pi/2):
    the closed-form inverse of `ik_down`, used by the planner for the joint-space moves."""
    g = q[2] + PHI3
    a_ = A2 + L3 * math.sin(g)
    b_ = L3 * math.cos(g)
    rr = a_ * math.sin(q[1]) + b_ * math.cos(q[1])
    zz = a_ * math.cos(q[1]) - b_ * math.sin(q[1])
    return ((A1 + rr) * math.cos(q[0]), (A1 + rr) * math.sin(q[0]), zz + D1 - D6, q[0] + q[5])


def main() -> None:
    print("rate limits [deg/s]:", np.round(QD_MAX / DEG, 1))
    print("acc limits [rad/s^2] (assumed):", np.round(QDD_MAX, 1))
    print("jerk limits [rad/s^3] (assumed):", np.round(QDDD_MAX, 0))
    rt = ik_roundtrip(5000)
    print("IK round trip:", rt)
    q = ik_down(0.5, -0.3, 0.35, 0.2)
    print("q at (0.5, -0.3, 0.35, yaw 0.2):", np.round(q / DEG, 3))
    t = fk_flange(q)
    print("fk_down vs fk_flange:", np.round(np.array(fk_down(q)) - np.array([*t[:3, 3], 0.2]), 12))


if __name__ == "__main__":
    main()
