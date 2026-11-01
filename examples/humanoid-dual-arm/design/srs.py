# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""The stacked 7-DOF SRS arm of the humanoid torso: kinematics and the reference IK.

Every kinematic number of `humanoid-dual-arm` lives here. The source is the interactive page
`humanoid_dual_arm_srs.html` (a kinematic demo, read as a specification only): its joint chain,
offsets, limits, home posture, grasp and IK constants. This file re-implements the page's
forward kinematics and its damped-least-squares IK with a null-space pull **the way the page
does** (`ik_page`: finite-difference Jacobian of one degree, angles in degrees, 8 iterations per
call, the same damping, gains and clamps), so the numbers it prints are independent of bg-sim.

Page frame (used by every function here): x right (the robot's left), y up, z forward (the
robot faces +z), metres. The page's +x arm is the robot's **left** arm (`s = +1`), the -x arm
its right arm (`s = -1`). bg-sim's world is Z-up: `world_of_page` maps page (x, y, z) to bg-sim
(X, Y, Z) = (z, x, y + Z0), so the robot faces +X and its left arm is on +Y.

Joint i turns about the page axis `AX[i]` of the current frame by `c_i q_i` with `c_i = -1` for
the pitch joints (both arms) and `c_i = s` otherwise, which makes the right arm the mirror
image of the left one. After the rotation the frame moves by `OFF[i]` (in its own frame).

    uv run examples/humanoid-dual-arm/design/srs.py      # the design report and self checks
"""

from __future__ import annotations

import math

import numpy as np

D = math.pi / 180.0
NJ = 7

# ------------------------------------------------------------------ the page's chain
#: offsets after each joint, in the joint's own frame [m] (page `REAL`)
OFF_REAL = np.array(
    [
        [0.0, -0.06, 0.025],
        [0.0, -0.06, -0.025],
        [0.0, -0.26, 0.0],
        [0.0, -0.04, 0.02],
        [0.0, -0.20, -0.02],
        [0.0, -0.04, 0.02],
        [0.0, -0.09, 0.0],
    ]
)
#: the ideal SRS: shoulder and wrist offsets zero, the same total link lengths (page `IDEAL`)
OFF_IDEAL = np.array(
    [
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, -0.38, 0.0],
        [0.0, -0.28, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, -0.09, 0.0],
    ]
)
NAMES = ["Shoulder pitch", "Shoulder roll", "Shoulder yaw", "Elbow pitch", "Forearm yaw", "Wrist pitch", "Wrist roll"]
AX = ["x", "z", "y", "x", "y", "x", "z"]
PITCH = [True, False, False, True, False, True, False]
LO = np.array([-60.0, -20.0, -90.0, 0.0, -90.0, -60.0, -90.0])  # [deg]
HI = np.array([180.0, 120.0, 90.0, 140.0, 90.0, 60.0, 90.0])  # [deg]
HOME = np.array([25.0, 12.0, 0.0, 70.0, 0.0, 0.0, 0.0])  # [deg]
SHOULDER_X = 0.2  # shoulder base at (s 0.2, 0.25, 0) [m]
SHOULDER_Y = 0.25
LOCK = 4  # the 6-DOF variant locks J5 (forearm yaw, index 4) at zero

# ------------------------------------------------------------------ the page's IK constants
RW = 0.3  # orientation weight [m/rad]
LAM_STEP = 1e-5  # damping of the task step (units of the per-degree Jacobian)
LAM_NULL = 1e-9  # damping of the null-space projection
K_NULL = 0.1  # null-space pull toward home, per iteration
STEP_MAX = 8.0  # step clamp per iteration [deg]
ITERS = 8  # iterations per call (one animation frame)
FD_STEP = 1.0  # finite-difference step of the Jacobian [deg]
HOLD_MM = 2.0  # "holds pose": under 2 mm and 2 deg
HOLD_DEG = 2.0

# ------------------------------------------------------------------ the shared object
HB = 0.14  # half length of the box along its x: the hands grasp at +-HB [m]
BOX = np.array([0.28, 0.10, 0.10])  # box size [m] (page: half extents 0.14, 0.05, 0.05)
OBJ_DEFAULT = (np.array([0.0, -0.1, 0.4]), np.array([0.0, 0.0, 0.0]))  # p [m], (roll, pitch, yaw) [deg]
BIAS_RANGE = (-40.0, 40.0)  # elbow bias slider [deg]

# ------------------------------------------------------------------ bg-sim world
Z0 = 1.0  # the page origin sits 1 m above the floor in the bg-sim world
P_WORLD = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])  # bg-sim = P page


def rot(ax: str, t: float) -> np.ndarray:
    c, s = math.cos(t), math.sin(t)
    if ax == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)
    if ax == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def hom(r: np.ndarray, p) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = r
    t[:3, 3] = p
    return t


def tr(p) -> np.ndarray:
    return hom(np.eye(3), p)


def sign(i: int, s: int) -> int:
    """c_i: the pitch joints turn by -q on both arms, the others by s q (mirror)."""
    return -1 if PITCH[i] else s


def base(s: int) -> np.ndarray:
    return tr([s * SHOULDER_X, SHOULDER_Y, 0.0])


def fk(q_deg, s: int, ideal: bool = False, frames: bool = False):
    """The page's `fk`: the hand frame (4x4, page frame); with `frames` also the joint origins
    and the world rotation axes (unit, the direction of +q)."""
    off = OFF_IDEAL if ideal else OFF_REAL
    r = np.eye(3)
    p = np.array([s * SHOULDER_X, SHOULDER_Y, 0.0])
    origins, axes = [], []
    for i in range(NJ):
        k = "xyz".index(AX[i])
        if frames:
            origins.append(p.copy())
            axes.append(sign(i, s) * r[:, k].copy())
        r = r @ rot(AX[i], sign(i, s) * q_deg[i] * D)
        p = p + r @ off[i]
    t = hom(r, p)
    if frames:
        return t, np.array(origins), np.array(axes)
    return t


def obj_rotation(rpy_deg) -> np.ndarray:
    """The page's object rotation R = Ry(yaw) Rx(pitch) Rz(roll) (page frame)."""
    r, p, y = (v * D for v in rpy_deg)
    return rot("y", y) @ rot("x", p) @ rot("z", r)


def grasp(s: int) -> np.ndarray:
    """Hand frame in the object frame: at (s HB, 0, 0) with columns (0, s, 0), (0, 0, -1), (-s, 0, 0)."""
    r = np.array([[0.0, s, 0.0], [0.0, 0.0, -1.0], [-s, 0.0, 0.0]]).T
    return hom(r, [s * HB, 0.0, 0.0])


def hand_target(p, rpy_deg, s: int) -> tuple[np.ndarray, np.ndarray]:
    """Target position and the three target columns of hand s for the object pose."""
    t = hom(obj_rotation(rpy_deg), p) @ grasp(s)
    return t[:3, 3], t[:3, :3]


def err(t: np.ndarray, tp, tr_cols) -> np.ndarray:
    """The page's `err`: target minus current, position [m] and 0.5 RW sum c_i x t_i."""
    e = np.zeros(6)
    e[:3] = tp - t[:3, 3]
    o = np.zeros(3)
    for i in range(3):
        o += np.cross(t[:3, i], tr_cols[:, i])
    e[3:] = 0.5 * o * RW
    return e


def jac_analytic(q_deg, s, ideal, tp, tr_cols) -> np.ndarray:
    """d(current)/dq per degree, the exact derivative of `-err` (the bg-sim block uses this)."""
    t, o, u = fk(q_deg, s, ideal, frames=True)
    p = t[:3, 3]
    jm = np.zeros((6, NJ))
    for k in range(NJ):
        jm[:3, k] = np.cross(u[k], p - o[k]) * D
        g = np.zeros(3)
        for i in range(3):
            g += np.cross(np.cross(u[k], t[:3, i]), tr_cols[:, i])
        jm[3:, k] = -0.5 * RW * g * D
    return jm


def ik_step(q, s, ideal, tp, tr_cols, lock, home, jac="page", step_max=STEP_MAX, scale=False):
    """One iteration of the page's `ik6` loop (in degrees). Returns the new q.

    The page clamps each joint's step to +-STEP_MAX; with `scale` the whole step is scaled down
    instead (the bg-sim block: a rate limit that keeps the direction). Both leave the fixed
    points unchanged."""
    act = [k for k in range(NJ) if k != lock]
    e0 = err(fk(q, s, ideal), tp, tr_cols)
    if jac == "page":
        jm = np.zeros((6, NJ))
        for k in act:
            qq = q.copy()
            qq[k] += FD_STEP
            jm[:, k] = e0 - err(fk(qq, s, ideal), tp, tr_cols)
    else:
        jm = jac_analytic(q, s, ideal, tp, tr_cols)
        if lock >= 0:
            jm[:, lock] = 0.0
    aa = jm @ jm.T
    y = np.linalg.solve(aa + LAM_STEP * np.eye(6), e0)
    z = np.array([K_NULL * (home[k] - q[k]) if k in act else 0.0 for k in range(NJ)])
    u = np.linalg.solve(aa + LAM_NULL * np.eye(6), jm @ z)
    q = q.copy()
    d = z + jm.T @ (y - u)
    if scale:
        dm = float(np.max(np.abs(d)))
        if dm > step_max:
            d = d * (step_max / dm)
    for k in act:
        dk = d[k] if scale else max(-step_max, min(step_max, d[k]))
        q[k] = max(LO[k], min(HI[k], q[k] + dk))
    return q


def home_of(s: int, bias: float) -> np.ndarray:
    """The page's home posture with the elbow bias added to shoulder yaw (mirrored by s)."""
    h = HOME.copy()
    h[2] += s * bias
    return h


def residual(q, s, ideal, tp, tr_cols, lock) -> dict:
    """The page's readout: position error [mm], orientation error [deg], nearest limit [%]."""
    e = err(fk(q, s, ideal), tp, tr_cols)
    pe = float(np.linalg.norm(e[:3]) * 1000.0)
    oe = float(math.asin(min(1.0, np.linalg.norm(e[3:]) / RW)) / D)
    act = [k for k in range(NJ) if k != lock]
    fr = [min(q[k] - LO[k], HI[k] - q[k]) / (HI[k] - LO[k]) for k in act]
    j = int(np.argmin(fr))
    return {"pe_mm": pe, "oe_deg": oe, "limit_pct": 100.0 * float(fr[j]), "limit_joint": act[j] + 1,
            "holds": pe < HOLD_MM and oe < HOLD_DEG}  # fmt: skip


def solve(p, rpy, s, ideal=False, lock=-1, bias=0.0, q0=None, frames=2000, jac="page", step_max=STEP_MAX,
          tol=1e-11):  # fmt: skip
    """Run the page's per-frame IK (8 iterations each) from `q0` (home) until a frame moves no
    joint by more than `tol` degrees (the page runs it every animation frame, so this is the
    pose it settles on), at most `frames` frames."""
    tp, tc = hand_target(np.asarray(p, float), rpy, s)
    q = (HOME if q0 is None else np.asarray(q0, float)).copy()
    if lock >= 0:
        q[lock] = 0.0
    home = home_of(s, bias)
    for _ in range(frames):
        q_prev = q
        for _ in range(ITERS):
            q = ik_step(q, s, ideal, tp, tc, lock, home, jac, step_max)
        if np.max(np.abs(q - q_prev)) < tol:
            break
    return q, residual(q, s, ideal, tp, tc, lock)


# ------------------------------------------------------------------ bg-sim world helpers


def world_of_page(t: np.ndarray) -> np.ndarray:
    """A page-frame homogeneous transform in the bg-sim world."""
    w = np.eye(4)
    w[:3, :3] = P_WORLD @ t[:3, :3] @ P_WORLD.T
    w[:3, 3] = P_WORLD @ t[:3, 3] + [0.0, 0.0, Z0]
    return w


def point_world(p) -> np.ndarray:
    return P_WORLD @ np.asarray(p, float) + [0.0, 0.0, Z0]


def quat(r: np.ndarray) -> np.ndarray:
    """(w, x, y, z) of a rotation matrix, w >= 0."""
    from scipy.spatial.transform import Rotation

    x, y, z, w = Rotation.from_matrix(r).as_quat()
    qq = np.array([w, x, y, z])
    return qq if qq[0] >= 0 else -qq


def pose7(t: np.ndarray) -> np.ndarray:
    return np.concatenate([quat(t[:3, :3]), t[:3, 3]])


def elbow(q, s, ideal=False) -> np.ndarray:
    """The elbow (J4 origin) in the page frame."""
    _, o, _ = fk(q, s, ideal, frames=True)
    return o[3]


# ------------------------------------------------------------------ report


def report() -> None:
    p, rpy = OBJ_DEFAULT
    print("humanoid-dual-arm: page reference IK at the default object pose", p, rpy)
    for lock, label in ((-1, "7-DOF"), (LOCK, "6-DOF (J5 locked)")):
        for ideal in (False, True):
            for s in (1, -1):
                q, r = solve(p, rpy, s, ideal, lock)
                qa, ra = solve(p, rpy, s, ideal, lock, jac="analytic")
                print(f"  {label:18s} {'ideal ' if ideal else 'stacked'} s={s:+d}: q = {np.round(q, 3)}")
                print(f"      page  {r}")
                print(f"      exact {ra}  |dq| = {np.max(np.abs(q - qa)):.3g} deg")
    # elbow bias
    for bias in (0.0, 30.0, -30.0):
        q, r = solve(p, rpy, 1, bias=bias)
        print(f"  bias {bias:+.0f}: elbow {np.round(elbow(q, 1) * 1000, 1)} mm, {r['pe_mm']:.3g} mm {r['oe_deg']:.3g} deg")


if __name__ == "__main__":
    report()
