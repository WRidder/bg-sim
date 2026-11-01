# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""The task, the dynamics and the drives of `humanoid-dual-arm`, and the Python twin of the
in-model firmware.

The kinematics and the page's IK are in `srs.py`. Everything here is a **design choice** of
this example (the page is kinematic only): the scenario timing, the start pose, the link
masses and inertias, the drives and the servo gains. The masses and inertias are
**illustrative**: a 7 kg arm of solid cylinders, not a particular robot.

    uv run examples/humanoid-dual-arm/design/humanoid.py      # the design report and self checks
"""

from __future__ import annotations

import math

import numpy as np

import srs

G0 = 9.81
TS = 0.001  # firmware period [s]
BIAS = 30.0  # commanded elbow bias of the scenario [deg]
GHOST_DY = -1.0  # the ideal-SRS pair is drawn 1 m to the robot's right (world y)
TIMING = {"settle": 1.5, "move": 1.5, "dwell": 1.0, "bias": 1.5, "hold": 1.0}
T_END = sum(TIMING.values())
#: the start pose of the object: the stacked 6-DOF arms (J5 locked) hold it exactly, so both
#: variants start from one posture (design/explore: a grid of poses in front of the torso)
OBJ_START = (np.array([0.0, -0.20, 0.35]), np.array([0.0, 0.0, 0.0]))
#: check instants: end of the dwell at the commanded pose, end of the run (bias applied)
T_HOLD = TIMING["settle"] + TIMING["move"] + TIMING["dwell"] - 0.05
T_BIAS = T_END - 0.05

# ------------------------------------------------------------------ start postures


def start_posture(ideal: bool) -> np.ndarray:
    """The 6-DOF (J5 locked) solution of the start pose [deg]; both sides are mirror images,
    so one posture serves both arms."""
    p, r = OBJ_START
    q, res = srs.solve(p, r, 1, ideal=ideal, lock=srs.LOCK, jac="analytic", tol=1e-12, frames=4000)
    assert res["holds"], res
    return q


# ------------------------------------------------------------------ link masses (illustrative)
#: link k sits between joint k and joint k+1 (link 7: the hand): mass [kg], cylinder radius [m]
LINK_MASS = np.array([1.0, 1.0, 2.0, 0.8, 1.2, 0.4, 0.6])
LINK_RADIUS = np.array([0.045, 0.045, 0.04, 0.04, 0.035, 0.03, 0.03])
LINK_MIN_LEN = 0.05  # compact housings count as 5 cm cylinders
BOX_MASS = 1.5  # the shared object [kg]

# ------------------------------------------------------------------ drives and grasp (assumed)
K_HELD = 1.0e6  # held directions of the compliant joints [N/m, N m/rad]
J_ROTOR = np.array([0.2, 0.2, 0.2, 0.2, 0.05, 0.05, 0.05])  # reflected rotor inertia [kg m^2]
K_GEAR = np.array([1.0e4, 1.0e4, 1.0e4, 1.0e4, 2.0e3, 2.0e3, 2.0e3])  # gear stiffness [N m/rad]
ZETA_GEAR = 0.3
B_JOINT = 0.5  # viscous joint friction, link side [N m s/rad]
U_MAX = np.array([80.0, 80.0, 80.0, 80.0, 20.0, 20.0, 20.0])  # torque limits [N m]
WN = np.array([20.0, 20.0, 20.0, 20.0, 25.0, 25.0, 25.0])  # servo bandwidth [rad/s]
ZETA_SERVO = 0.8
GRASP = {"kt": 1.0e5, "kr": 1.0e3, "kq": 1.0e3}  # grasp stiffness [N/m, N m/rad]


def link_body(k: int) -> tuple[np.ndarray, np.ndarray, float]:
    """(centre of mass in the page link frame k, principal frame rotation, length) of link k:
    a cylinder along the offset after joint k, centred on it."""
    off = srs.OFF_REAL[k]
    length = float(np.linalg.norm(off))
    axis = off / length
    # principal frame: z along the cylinder
    ref = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = np.cross(ref, axis)
    x /= np.linalg.norm(x)
    y = np.cross(axis, x)
    return off / 2.0, np.column_stack([x, y, axis]), max(length, LINK_MIN_LEN)


def link_inertia(k: int) -> np.ndarray:
    """Principal moments (x, y, z = cylinder axis) of link k [kg m^2]."""
    _, _, length = link_body(k)
    m, r = LINK_MASS[k], LINK_RADIUS[k]
    it = m * (3 * r * r + length * length) / 12.0
    return np.array([it, it, 0.5 * m * r * r])


def box_inertia() -> np.ndarray:
    a, b, c = srs.BOX
    m = BOX_MASS
    return np.array([m * (b * b + c * c), m * (a * a + c * c), m * (a * a + b * b)]) / 12.0


# ------------------------------------------------------------------ the bg-sim chain frames


def r_pre(u: np.ndarray) -> np.ndarray:
    """A rotation whose z is the unit axis u (one of +-x, +-y, +-z)."""
    k = int(np.argmax(np.abs(u)))
    sgn = float(np.sign(u[k]))
    if k == 2:
        return np.eye(3) if sgn > 0 else srs.rot("x", math.pi)
    if k == 0:
        return srs.rot("y", sgn * math.pi / 2)
    return srs.rot("x", -sgn * math.pi / 2)


def joint_axis(i: int, s: int) -> np.ndarray:
    e = np.eye(3)["xyz".index(srs.AX[i])]
    return srs.sign(i, s) * e


def pw() -> np.ndarray:
    """The page frame in the world."""
    return srs.hom(srs.P_WORLD, [0.0, 0.0, srs.Z0])


def chain_frames(s: int, ideal: bool = False, dy: float = 0.0) -> dict:
    """The fixed transforms of the bg-sim chain of arm s (4x4, see build_models.py):

    LN[0]  the J1 parent frame in the world; LN[i] (i >= 1) the J(i+1) parent frame in the
           J(i) child frame; LC[i] the link-(i+1) principal CoM frame in the J(i+1) child frame;
           LH the hand frame in the J7 child frame. A joint's child frame turns about its z by q.
    """
    off = srs.OFF_IDEAL if ideal else srs.OFF_REAL
    rp = [srs.hom(r_pre(joint_axis(i, s)), [0, 0, 0]) for i in range(srs.NJ)]
    base = srs.hom(np.eye(3), [0.0, dy, 0.0]) @ pw() @ srs.tr([s * srs.SHOULDER_X, srs.SHOULDER_Y, 0.0])
    ln = [base @ rp[0]]
    for i in range(1, srs.NJ):
        ln.append(rp[i - 1].T @ srs.tr(off[i - 1]) @ rp[i])
    lc = []
    for i in range(srs.NJ):
        com, rprin, _ = link_body(i)
        lc.append(rp[i].T @ srs.hom(rprin, com))
    lh = rp[6].T @ srs.tr(off[6])
    return {"LN": ln, "LC": lc, "LH": lh}


def rz(q: float) -> np.ndarray:
    return srs.hom(srs.rot("z", q), [0, 0, 0])


def chain_fk(q_deg, s: int, ideal: bool = False, dy: float = 0.0) -> dict:
    """World frames of the bg-sim chain: the joint child frames W[i], bodies P[i], the hand."""
    f = chain_frames(s, ideal, dy)
    w = np.eye(4)
    ws, ps = [], []
    for i in range(srs.NJ):
        w = w @ f["LN"][i] @ rz(q_deg[i] * srs.D)
        ws.append(w)
        ps.append(w @ f["LC"][i])
    return {"W": ws, "P": ps, "hand": ws[-1] @ f["LH"]}


def grasp_world(s: int) -> np.ndarray:
    return srs.grasp(s)


def object_pose_world(p, rpy) -> np.ndarray:
    """The commanded object pose in the world (D-MB6 chart): the twin of ObjectTrajectory.g."""
    return srs.pose7(pw() @ srs.hom(srs.obj_rotation(rpy), p))


# ------------------------------------------------------------------ statics and servo gains


def statics(q_deg, s: int, hand_force_page) -> np.ndarray:
    """Holding torques (along +q) of arm s at rest at q under gravity and a force on the hand
    origin (page frame) [N m]."""
    t, o, u = srs.fk(q_deg, s, frames=True)
    f = chain_fk(q_deg, s)
    inv = np.linalg.inv(pw())
    coms = [(inv @ p)[:3, 3] for p in f["P"]]
    g = np.array([0.0, -G0, 0.0])
    tau = np.zeros(srs.NJ)
    for k in range(srs.NJ):
        m = np.zeros(3)
        for j in range(k, srs.NJ):
            m += np.cross(coms[j] - o[k], LINK_MASS[j] * g)
        m += np.cross(t[:3, 3] - o[k], hand_force_page)
        tau[k] = -u[k] @ m
    return tau


def joint_inertia(q_deg, s: int) -> np.ndarray:
    """Diagonal of the arm's mass matrix (plus half the box at the hand) at q [kg m^2]."""
    t, o, u = srs.fk(q_deg, s, frames=True)
    f = chain_fk(q_deg, s)
    inv = np.linalg.inv(pw())
    b = np.zeros(srs.NJ)
    for k in range(srs.NJ):
        for j in range(k, srs.NJ):
            pj = inv @ f["P"][j]
            r = pj[:3, 3] - o[k]
            ib = pj[:3, :3] @ np.diag(link_inertia(j)) @ pj[:3, :3].T
            b[k] += LINK_MASS[j] * float(np.sum(np.cross(u[k], r) ** 2)) + u[k] @ ib @ u[k]
        b[k] += 0.5 * BOX_MASS * float(np.sum(np.cross(u[k], t[:3, 3] - o[k]) ** 2))
    return b


Q_START = start_posture(False)
Q_START_IDEAL = start_posture(True)
HAND_LOAD = np.array([0.0, -0.5 * BOX_MASS * G0, 0.0])  # the box on each hand at rest (symmetric)
TAU_START = statics(Q_START, 1, HAND_LOAD)  # the same on the mirrored right arm


def servo_gains() -> dict:
    b = J_ROTOR + joint_inertia(Q_START, 1)
    kp = b * WN**2
    kd = 2 * ZETA_SERVO * b * WN
    ki = kp * WN / 5.0
    return {"B": b, "Kp": np.round(kp, 3), "Kd": np.round(kd, 3), "Ki": np.round(ki, 3), "umax": U_MAX,
            "imax": np.round(U_MAX / np.round(ki, 3), 6)}  # fmt: skip


SERVO = servo_gains()


def gear_damping() -> np.ndarray:
    return 2 * ZETA_GEAR * np.sqrt(K_GEAR * J_ROTOR)


def held_damping(k_held: float, i: int) -> tuple[float, float]:
    """(bt, br) of joint i: 0.7 of critical for the distal mass (half the box) and 0.05 kg m^2."""
    distal = float(LINK_MASS[i:].sum()) + 0.5 * BOX_MASS
    return 1.4 * math.sqrt(k_held * distal), 1.4 * math.sqrt(k_held * 0.05)


# ------------------------------------------------------------------ the firmware twin


def quintic(tau: float) -> float:
    tau = min(1.0, max(0.0, tau))
    return tau**3 * (10.0 - 15.0 * tau + 6.0 * tau * tau)


def trajectory(t: float, p1=None, r1=None, bias=BIAS, dof6=False) -> np.ndarray:
    """The twin of ObjectTrajectory.obj at time t."""
    p0, r0 = OBJ_START
    p1 = srs.OBJ_DEFAULT[0] if p1 is None else np.asarray(p1, float)
    r1 = srs.OBJ_DEFAULT[1] if r1 is None else np.asarray(r1, float)
    T = TIMING
    s = quintic((t - T["settle"]) / T["move"])
    tc = T["settle"] + T["move"] + T["dwell"]
    sb = quintic((t - tc) / T["bias"])
    return np.array([*(p0 + (p1 - p0) * s), *(r0 + (r1 - r0) * s), bias * sb, 1.0 if dof6 else 0.0])


def twin(dof6=False, bias=BIAS, p1=None, r1=None, t_end=T_END, every=1) -> dict:
    """Run the in-model firmware (ObjectTrajectory + four ArmIK) tick by tick in Python.

    Returns per instance (`L`, `R`, `IL`, `IR`) the arrays of the joint solution [deg] and the
    readouts after each tick (the block's outputs), with the tick times."""
    arms = {"L": (1, False), "R": (-1, False), "IL": (1, True), "IR": (-1, True)}
    q = {k: (Q_START_IDEAL if ideal else Q_START).copy() for k, (_, ideal) in arms.items()}
    out = {k: {"q": [], "pe": [], "oe": [], "lim": [], "elbow": []} for k in arms}
    times = []
    n = int(round(t_end / TS))
    for i in range(1, n + 1):
        t = i * TS
        obj = trajectory(t, p1, r1, bias, dof6)
        lock = srs.LOCK if obj[7] > 0.5 else -1
        for k, (s, ideal) in arms.items():
            tp, tc = srs.hand_target(obj[:3], obj[3:6], s)
            qk = q[k]
            if lock >= 0:
                qk[lock] = 0.0
            res = srs.residual(qk, s, ideal, tp, tc, lock)
            el = srs.elbow(qk, s, ideal)
            qk = srs.ik_step(qk, s, ideal, tp, tc, lock, srs.home_of(s, obj[6]), jac="analytic", step_max=DMAX, scale=True)
            q[k] = qk
            if i % every == 0:
                out[k]["q"].append(qk.copy())
                out[k]["pe"].append(res["pe_mm"])
                out[k]["oe"].append(res["oe_deg"])
                # the block reads the nearest limit after its step, the errors before it
                out[k]["lim"].append(srs.residual(qk, s, ideal, tp, tc, lock)["limit_pct"])
                out[k]["elbow"].append(el)
        if i % every == 0:
            times.append(t)
    for k in out:
        for key in out[k]:
            out[k][key] = np.array(out[k][key])
    out["t"] = np.array(times)
    return out


DMAX = 0.05  # ArmIK largest joint step per tick [deg] (50 deg/s)


# ------------------------------------------------------------------ report and self checks


def self_checks() -> None:
    rng = np.random.default_rng(1)
    worst = 0.0
    for _ in range(200):
        q = rng.uniform(srs.LO, srs.HI)
        for s in (1, -1):
            for ideal in (False, True):
                a = chain_fk(q, s, ideal)["hand"]
                b = pw() @ srs.fk(q, s, ideal)
                worst = max(worst, float(np.max(np.abs(a - b))))
    print(f"  chain frames vs the page FK, 800 random poses: {worst:.2e}")
    assert worst < 1e-12
    # elbow = J4 origin = W[3] origin
    q = Q_START
    a = chain_fk(q, 1)["W"][3][:3, 3]
    b = srs.point_world(srs.elbow(q, 1))
    assert np.max(np.abs(a - b)) < 1e-12
    # analytic Jacobian vs a central difference of err
    p, r = srs.OBJ_DEFAULT
    tp, tc = srs.hand_target(p, r, 1)
    j = srs.jac_analytic(q, 1, False, tp, tc)
    jn = np.zeros_like(j)
    for k in range(7):
        dq = np.zeros(7)
        dq[k] = 1e-6
        jn[:, k] = -(srs.err(srs.fk(q + dq, 1), tp, tc) - srs.err(srs.fk(q - dq, 1), tp, tc)) / 2e-6
    print(f"  analytic Jacobian vs central difference: {np.max(np.abs(j - jn)):.2e}")
    assert np.max(np.abs(j - jn)) < 1e-8
    # object pose world vs the trajectory quaternion formula
    g = object_pose_world(np.array([0.1, -0.05, 0.4]), np.array([10.0, -20.0, 30.0]))
    print(f"  object pose (world) for rpy (10, -20, 30): {np.round(g, 6)}")


def report() -> None:
    print("humanoid-dual-arm design")
    print(f"  start pose {OBJ_START[0]} rpy {OBJ_START[1]}")
    print(f"  start posture (stacked, J5 = 0): {np.round(Q_START, 4)} deg")
    print(f"  start posture (ideal,   J5 = 0): {np.round(Q_START_IDEAL, 4)} deg")
    print(f"  arm mass {LINK_MASS.sum():.2f} kg, box {BOX_MASS} kg, box inertia {box_inertia()}")
    print(f"  holding torques at the start: {np.round(TAU_START, 3)} N m")
    for k in ("B", "Kp", "Kd", "Ki", "imax"):
        print(f"  servo {k}: {SERVO[k]}")
    print(f"  gear damping {np.round(gear_damping(), 3)}")
    self_checks()


if __name__ == "__main__":
    report()
