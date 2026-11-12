# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""The microduck body: kinematics and inertials (design/robot_data.json, extracted from the
microduck_rl MJCF by extract_mjcf.py), the STAND pose, the squat pose, the two robot models and their references.

    uv run examples/microduck/design/robot.py      # the design report (mass, stand height, statics)

Model structure (per body b with parent P, joint about the local z of b):

    BJ_P -> T_b (FixedTransform3DNeutral, P's centre of mass seen from the joint frame)
         -> b_joint (Revolute3D) -> L_b (FixedTransform3DNeutral, b's principal CoM frame) -> BJ_b
    BJ_b <- b (RigidBody3D, principal moments)
    XL330 instance (named after the joint): horn -> b_joint.drive, vbus <- Bus
    pose band: W_b = W_P o T_Pb o b_joint.pose, P_b = W_b o C_b -> b.g

The trunk floats: World -> Free3D -> TrunkCoM -> BJ_trunk_base. Each sole carries four
ContactPoint elements (Hunt-Crossley, Coulomb friction) on one ground ContactSurface.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from diagram import Diagram, fmt, pose_params, vec

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "robot_data.json").read_text(encoding="utf-8"))
BODIES = DATA["bodies"]
BY_NAME = {b["name"]: b for b in BODIES}
JOINTS = [b["joint"] for b in BODIES if "joint" in b]  # MJCF order: left leg, head, right leg

# microduck DEFAULT_POSITION = microduck_rl HOME_FRAME (duck-control/src/model.rs)
HOME = {
    "left_hip_yaw": 0.0, "left_hip_roll": -0.0873, "left_hip_pitch": -0.4579, "left_knee": -0.0049,
    "left_ankle": 0.4530, "neck_pitch": 0.3491, "head_pitch": 0.3491, "head_yaw": 0.0, "head_roll": 0.0,
    "right_hip_yaw": 0.0, "right_hip_roll": 0.0873, "right_hip_pitch": 0.4579, "right_knee": 0.0049,
    "right_ankle": -0.4530,
}
G0 = 9.81
K_HELD = 1.0e5  # N/m, N m/rad: the held directions of every Revolute3D (compliant joints)
CONTACT = {"k": 2.0e4, "xref": 1.0e-3, "c": 5.0, "mu": 1.0, "vs": 1.0e-3, "eps": 1.0e-6}  # mu: microduck_rl foot friction 1.0
R_BAT = 0.1  # Ohm, ASSUMED pack + wiring resistance (training: 0..0.2 V per N m of total torque)
C_BUS = 1.0e-3  # F, ASSUMED bus capacitance (gives the bus voltage a state)

# Squat pose (microduck-hang): the legs bend so that the trunk would drop SQUAT_DEPTH at constant attitude.
SQUAT_DEPTH = 0.015  # m
HANG_HEIGHT = 0.3  # m, trunk frame of the held robot (microduck-hang)
HANG_STEP = 0.2  # s, the leg goals step from HOME to the squat pose
HANG_T_END = 1.2  # s
STAND_T_END = 1.3  # s, the held HOME pose has tipped past 40 deg by then (no trunk/head contacts)


# ------------------------------------------------------------------ kinematics

def quat_rot(q) -> np.ndarray:
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def hom(r, p) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = r
    t[:3, 3] = p
    return t


def rz(q) -> np.ndarray:
    c, s = math.cos(q), math.sin(q)
    return hom(np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]]), np.zeros(3))


def parent_frame(b) -> np.ndarray:
    """T_Pb: body b's frame (= its joint frame at q = 0) in its parent's frame."""
    return hom(quat_rot(b["quat"]), b["pos"])


def principal(b) -> tuple[np.ndarray, np.ndarray]:
    """(moments, C_b): principal moments and the principal CoM frame in b's frame (right-handed)."""
    vals, vecs = np.linalg.eigh(np.array(b["inertia"]))
    if np.linalg.det(vecs) < 0:
        vecs[:, 2] = -vecs[:, 2]
    return vals, hom(vecs, b["com"])


def fk(q: dict, base=np.eye(4)) -> dict:
    """World frame of every body for joint angles q (trunk frame = base)."""
    out = {}
    for b in BODIES:
        if b["parent"] is None:
            out[b["name"]] = base
        else:
            out[b["name"]] = out[b["parent"]] @ parent_frame(b) @ rz(q[b["joint"]])
    return out


def contact_points(b) -> np.ndarray:
    return np.array(b["sole"]["points"])


def feet():
    return [b for b in BODIES if "sole" in b]


def stand_height(q=HOME) -> float:
    """Trunk-frame height that puts the lowest sole point on the ground (trunk level)."""
    frames = fk(q)
    zmin = min((frames[b["name"]] @ np.append(p, 1.0))[2] for b in feet() for p in contact_points(b))
    return -zmin


def com(q=HOME) -> np.ndarray:
    frames = fk(q)
    m = sum(b["mass"] for b in BODIES)
    return sum(b["mass"] * (frames[b["name"]] @ np.append(b["com"], 1.0))[:3] for b in BODIES) / m


def mass() -> float:
    return sum(b["mass"] for b in BODIES)


# ------------------------------------------------------------------ the squat

def leg_chain(side: str) -> list[str]:
    return [f"{side}_hip_pitch", f"{side}_knee", f"{side}_ankle"]


def squat_pose(depth: float) -> dict:
    """Joint angles that lower the trunk by `depth` with the feet flat and in place (numerical IK
    on hip pitch, knee, ankle of each leg; trunk attitude unchanged)."""
    q = dict(HOME)
    base = fk(HOME)
    for side, foot in (("left", "ankle_left"), ("right", "ankle_right")):
        target = base[foot].copy()
        target[2, 3] += depth  # the foot rises relative to a trunk that drops
        names = leg_chain(side)
        x = np.array([q[n] for n in names])
        for _ in range(60):
            qq = dict(q)
            qq.update(dict(zip(names, x)))
            f = fk(qq)[foot]
            err = np.concatenate([f[:3, 3] - target[:3, 3], 0.5 * _rotvec(f[:3, :3] @ target[:3, :3].T)])
            if np.linalg.norm(err) < 1e-12:
                break
            jac = np.zeros((6, 3))
            for k in range(3):
                dx = x.copy()
                dx[k] += 1e-7
                qd = dict(q)
                qd.update(dict(zip(names, dx)))
                fd = fk(qd)[foot]
                ed = np.concatenate([fd[:3, 3] - target[:3, 3], 0.5 * _rotvec(fd[:3, :3] @ target[:3, :3].T)])
                jac[:, k] = (ed - err) / 1e-7
            x = x - np.linalg.lstsq(jac, err, rcond=None)[0]
        q.update(dict(zip(names, x)))
    return q


def _rotvec(r) -> np.ndarray:
    return np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])


# ------------------------------------------------------------------ the model

def node_names(b) -> dict:
    """Nodes of body b, named after the joint that moves it (the trunk: `trunk`)."""
    k = b.get("joint", "trunk")
    return {"body": f"{k}_link", "bj": f"{k}_bj", "T": f"{k}_T", "L": f"{k}_L", "joint": f"{k}_joint",
            "LN": f"{k}_LN", "CA": f"{k}_CA", "W": f"{k}_W", "LC": f"{k}_LC", "P": f"{k}_P"}


LAYOUT = {  # columns per body, rows per branch
    "trunk_base": (0, 0),
    "yaw2roll": (1, -1), "hip_l": (2, -1), "upper_leg_left": (3, -1), "leg": (4, -1), "ankle_left": (5, -1),
    "neck": (1, 0), "neck_pitch": (2, 0), "yaw_roll_motion": (3, 0), "jaw_soft": (4, 0),
    "bearing_roll": (1, 1), "hip_l_2": (2, 1), "upper_leg_right": (3, 1), "leg_2": (4, 1), "ankle_right": (5, 1),
}
DX, DY = 900, 1300


def static_sink(m_total=None) -> float:
    """Penetration of each sole point when the eight carry the weight equally (Hertz law of
    ContactPoint: F = k x (x / xref)^(1/2)), m."""
    m_total = mass() if m_total is None else m_total
    f = m_total * G0 / 8
    return (f * math.sqrt(CONTACT["xref"]) / CONTACT["k"]) ** (2.0 / 3.0)


def add_contact(d: Diagram, n: dict, cb: np.ndarray, tag: str, pt, x, y, params: dict, prefix: str) -> str:
    """A ContactPoint at `pt` (body frame of the body whose nodes are `n`) on the ground plane."""
    r_c = np.linalg.inv(cb) @ np.append(pt, 1.0)  # point in the principal CoM frame
    local = np.eye(4)
    local[:3, 3] = r_c[:3]
    name = f"{prefix}{tag}"
    pose_name = "Sole" if prefix == "Foot" else f"{prefix}Pose"
    mount_name = "SoleMount" if prefix == "Foot" else f"{prefix}Mount"
    world_name = "SoleW" if prefix == "Foot" else f"{prefix}W"
    d.ref(f"{pose_name}{tag}", "stdlib:spatial/LocalPose3D", x, y, params=pose_params(local))
    d.ref(f"{world_name}{tag}", "stdlib:multibond/ComposePose3D", x + 120, y)
    d.ref(f"{mount_name}{tag}", "stdlib:multibond/FixedTransform3DNeutral", x + 240, y,
          params=pose_params(np.linalg.inv(local)))
    d.ref(name, "stdlib:contact/ContactPoint", x + 360, y, params=params)
    d.bond(n["bj"], None, f"{mount_name}{tag}", "b")
    d.bond(f"{mount_name}{tag}", "a", name, "p")
    d.sig(n["P"], "g", f"{world_name}{tag}", "gp")
    d.sig(f"{pose_name}{tag}", "g", f"{world_name}{tag}", "gl")
    d.sig(f"{world_name}{tag}", "g", name, "g")
    d.sig("Ground", "o", name, "o")
    d.sig("Ground", "fr", name, "fr")
    return name


# Bumpers (falls): the microduck_rl ground-contact model gives every collision geom other than the
# soles condim 1, a frictionless normal contact; the normal law here is the soles'.
BUMPER_CONTACT = {**CONTACT, "mu": 0.0}
BUMPER_TAGS = {"trunk_base": "Trunk", "jaw_soft": "Head", "leg": "ShinL", "leg_2": "ShinR"}


def build_robot(d: Diagram, goal_nodes: dict, q0=HOME, floating=True, policy=None) -> None:
    """The body, 14 servos and their supply; floating: the trunk is free and the soles touch the
    ground, otherwise the trunk is held at HANG_HEIGHT and there is no ground.

    policy: None for the XL330 robot (compliant Revolute3D joints, battery bus with resistance and
    capacitance, released 0.1 mm above the floor), or a dict for the robot a policy drives:
    rigid Revolute3DRigid joints that carry the servo armature, XL330Rigid servos whose gain is the
    signal `policy["kp"]` (node, port), an ideal supply at v_bat, the soles loaded at the start,
    and with `policy["bumpers"]` the trunk, head and shin bumper points.
    """
    from build_model import actuator, rigid_actuator

    d.ref("World", "stdlib:multibond/GroundSpatial", -600, 0)
    if floating:
        z0 = stand_height(q0) + (1.0e-4 if policy is None else -static_sink())
        d.ref("Free", "stdlib:spatial/Free3D", -440, 0, starts={"pz": z0})
        d.bond("World", "p", "Free", "parent")
        for k in range(1, 7):
            d.ref(f"FreeSe{k}", "stdlib:bondgraph/Se", -440, 120 + 60 * k, params={"e": 0.0})
            d.bond(f"FreeSe{k}", "p", "Free", f"drive{k}")
    else:
        d.ref("TrunkPose", "stdlib:spatial/LocalPose3D", -440, 120, params=pose_params(hom(np.eye(3), [0, 0, HANG_HEIGHT])))
    # ---- supply
    d.ref("Battery", "stdlib:bondgraph/Se", -600, -900, params={"e": "v_bat"})
    d.junction("BatJ", "1", -460, -900)
    d.ref("BatCurrent", "stdlib:bondgraph/Df", -420, -800)
    d.junction("Bus", "0", -320, -900)
    d.bond("Battery", "p", "BatJ")
    d.bond("BatJ", None, "BatCurrent", "p")
    d.bond("BatJ", None, "Bus")
    if policy is None:
        d.ref("Rbat", "stdlib:bondgraph/R", -500, -800, params={"r": "r_bat"})
        d.ref("Cbus", "stdlib:bondgraph/C", -320, -800, params={"c": C_BUS}, starts={"q": f"{C_BUS!r}*v_bat"})
        d.ref("BusVoltage", "stdlib:bondgraph/De", -240, -800)
        d.bond("BatJ", None, "Rbat", "p")
        d.bond("Bus", None, "Cbus", "p")
        d.bond("Bus", None, "BusVoltage", "p")
    # ---- ground
    if floating:
        d.ref("Ground", "stdlib:contact/ContactSurface", -600, 2400)
    world_pose = {}
    for b in BODIES:
        n = node_names(b)
        col, row = LAYOUT[b["name"]]
        x, y = col * DX, row * DY
        moments, cb = principal(b)
        d.junction(n["bj"], "1", x + 420, y)
        d.ref(n["L"], "stdlib:multibond/FixedTransform3DNeutral", x + 300, y, params=pose_params(cb))
        d.bond(n["L"], "b", n["bj"])
        if b["parent"] is None and not floating:  # held trunk: no body, the ground holds the frame
            d.bond("World", "p", n["L"], "a")
            world_pose[b["name"]] = ("TrunkPose", "g")
            continue
        d.ref(n["body"], "stdlib:spatial/RigidBody3D", x + 420, y + 120,
              params={"m": b["mass"], "J": vec(moments), "g0": G0})
        d.bond(n["body"], "p", n["bj"])
        d.ref(n["LC"], "stdlib:spatial/LocalPose3D", x + 300, y + 420, params=pose_params(cb))
        d.ref(n["P"], "stdlib:multibond/ComposePose3D", x + 420, y + 320)
        d.sig(n["LC"], "g", n["P"], "gl")
        d.sig(n["P"], "g", n["body"], "g")
        if policy is not None and policy.get("bumpers") and "bumpers" in b:
            for k, pt in enumerate(b["bumpers"], start=1):
                add_contact(d, n, cb, f"{BUMPER_TAGS[b['name']]}{k}", pt, x + 1100, y + 120 * k, BUMPER_CONTACT, "Bump")
        if b["parent"] is None:
            d.bond("Free", "child", n["L"], "a")
            d.sig("Free", "pose", n["P"], "gp")
            world_pose[b["name"]] = ("Free", "pose")
            continue
        p = BY_NAME[b["parent"]]
        assert b["axis"] == [0.0, 0.0, 1.0], b["name"]
        _, cp = principal(p)
        t_pb = parent_frame(b)
        joint = b["joint"]
        lo, hi = b["range"]
        d.ref(n["T"], "stdlib:multibond/FixedTransform3DNeutral", x - 60, y,
              params=pose_params(np.linalg.inv(t_pb) @ cp))
        if policy is not None:
            d.ref(n["joint"], "stdlib:spatial/Revolute3DRigid", x + 100, y,
                  params={"q0": q0[joint], "Ja": "armature"})
        else:
            d.ref(n["joint"], "stdlib:spatial/Revolute3D", x + 100, y,
                  params={"kt": K_HELD, "kr": K_HELD, "bt": 2 * math.sqrt(K_HELD * 0.05),
                          "br": 2 * math.sqrt(K_HELD * 2e-5), "q0": q0[joint]},
                  constants={"q_min": lo, "q_max": hi})
        d.bond(node_names(p)["bj"], None, n["T"], "b")
        d.bond(n["T"], "a", n["joint"], "parent")
        d.bond(n["joint"], "child", n["L"], "a")
        # pose band
        d.ref(n["LN"], "stdlib:spatial/LocalPose3D", x - 60, y + 420, params=pose_params(t_pb))
        d.ref(n["CA"], "stdlib:multibond/ComposePose3D", x - 60, y + 320)
        d.ref(n["W"], "stdlib:multibond/ComposePose3D", x + 100, y + 320)
        d.sig(*world_pose[p["name"]], n["CA"], "gp")
        d.sig(n["LN"], "g", n["CA"], "gl")
        d.sig(n["CA"], "g", n["W"], "gp")
        d.sig(n["joint"], "pose", n["W"], "gl")
        d.sig(n["W"], "g", n["P"], "gp")
        world_pose[b["name"]] = (n["W"], "g")
        # the actuator
        if policy is not None:
            rigid_actuator(d, joint, x + 100, y - 400, q0=q0[joint], ws=policy.get("ws"))
            d.sig(n["joint"], "qout", joint, "q")
            d.sig(*policy["kp"], joint, "kp")
        else:
            actuator(d, joint, x + 100, y - 400, q0=q0[joint])
        d.bond(joint, "horn", n["joint"], "drive")
        d.bond("Bus", None, joint, "vbus")
        d.sig(*goal_nodes[joint], joint, "q_goal")
        # the sole
        if "sole" in b and floating:
            side = "L" if "left" in b["name"] else "R"
            for k, pt in enumerate(contact_points(b), start=1):
                add_contact(d, n, cb, f"{side}{k}", pt, x + 600, y + 700 + 120 * k, CONTACT, "Foot")


def robot_globals(policy=False):
    from build_model import firmware_globals

    if policy:
        return firmware_globals(7.4)
    return firmware_globals(7.4) + [
        {"name": "r_bat", "value": fmt(R_BAT), "unit": "Ohm",
         "description": "Battery + wiring resistance (assumed; training randomises the sag 0..0.2 V per N m)"},
    ]


LEGS = ["left_hip_pitch", "left_knee", "left_ankle", "right_hip_pitch", "right_knee", "right_ankle"]


def stand_plots():
    return [
        {"id": "p1", "title": "Trunk attitude (quaternion) and height", "signals": ["Free/pose[1]", "Free/pose[2]", "Free/pose[3]", "Free/pose[4]", "Free/pose[7]"]},
        {"id": "p2", "title": "Leg joint angles (encoders)", "signals": [f"{j}/Encoder/y" for j in LEGS]},
        {"id": "p3", "title": "Leg motor currents", "signals": [f"{j}/Current/y" for j in LEGS]},
        {"id": "p4", "title": "Foot normal forces", "signals": [f"Foot{s}{k}/f_n" for s in "LR" for k in range(1, 5)]},
        {"id": "p5", "title": "Battery current and bus voltage", "signals": ["BatCurrent/y", "BusVoltage/y"]},
    ]


def hang_plots():
    return [
        {"id": "p1", "title": "Left leg: goals and encoders", "signals": [s for j in LEGS[:3] for s in (f"Goal_{j}/y", f"{j}/Encoder/y")]},
        {"id": "p2", "title": "Left leg motor currents", "signals": [f"{j}/Current/y" for j in LEGS[:3]]},
        {"id": "p3", "title": "Left leg PWM duty", "signals": [f"{j}/PwmLimit/y" for j in LEGS[:3]]},
        {"id": "p4", "title": "Left knee backlash (gear minus horn)", "signals": ["left_knee/Backlash/phi"]},
        {"id": "p5", "title": "Battery current and bus voltage", "signals": ["BatCurrent/y", "BusVoltage/y"]},
    ]


def microduck_stand() -> dict:
    from build_model import settings

    d = Diagram()
    goals = {}
    for k, j in enumerate(JOINTS):
        d.ref(f"Goal_{j}", "stdlib:sources/Constant", -1200, -1200 + 90 * k, params={"value": HOME[j]})
        goals[j] = (f"Goal_{j}", "y")
    build_robot(d, goals)
    d.note("**microduck holding HOME.** Released 0.1 mm above the floor at the STAND pose, the 14 servos "
           "hold the HOME goals at kp 200 with no policy. HOME is balanced only by a policy that keeps "
           "balancing it: the robot sags into its backlash and its P gains and tips forward, past 40 deg "
           "after about 1.1 s (the microduck design notes report the same in their simulation). Only the "
           "soles touch the ground, so the run ends before the head would.", -1200, -1500, 900, 160)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "microduck-stand",
        "$comment": "The microduck released at the STAND pose; the 14 XL330 servos hold the HOME goals (no policy).",
        "diagram": d.document(),
        "settings": settings(STAND_T_END, reltol=1e-5, abstol=1e-7, points=651),
        "parameters": robot_globals(),
        "plots": stand_plots(),
    }


def hang_goal_pose() -> dict:
    return squat_pose(SQUAT_DEPTH)


def microduck_hang() -> dict:
    from build_model import settings

    d = Diagram()
    low = hang_goal_pose()
    goals = {}
    for k, j in enumerate(JOINTS):
        if abs(low[j] - HOME[j]) < 1e-9:
            d.ref(f"Goal_{j}", "stdlib:sources/Constant", -1200, -1200 + 90 * k, params={"value": HOME[j]})
        else:
            d.ref(f"Goal_{j}", "stdlib:sources/Step", -1200, -1200 + 90 * k,
                  params={"t_step": HANG_STEP, "initial": HOME[j], "final": low[j]})
        goals[j] = (f"Goal_{j}", "y")
    build_robot(d, goals, floating=False)
    d.note("**microduck on a stand.** The trunk is held in the air; at 0.2 s the hip pitch, knee and ankle "
           "goals step from HOME to a 15 mm squat (the bring-up test of a real robot). Watch the 20 ms "
           "latency, the current limit during the move, the backlash taking up and the gravity sag at "
           "the end (design/robot.py hang_reference).", -1200, -1500, 900, 140)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "microduck-hang",
        "$comment": "The microduck held by the trunk; the legs step from HOME to a squat pose (design/robot.py).",
        "diagram": d.document(),
        "settings": settings(HANG_T_END, reltol=1e-5, abstol=1e-7, points=1201),
        "parameters": robot_globals(),
        "plots": hang_plots(),
    }


POLICY_T_END = 0.6  # s (HOME without a policy tips forward and passes 40 deg near 1 s)
POLICY_STEP = 0.3  # s, the scripted leg targets step from HOME to the squat pose (open-loop check)
KP_WALK = 200.0  # robotd gain while walking (DUCK robotd.toml, control.rs)
POLICY_WS = 0.02  # rad/s, friction regularisation of the policy robot (the benches: xl330.W_S, 2 mrad/s)
POLICY_KP_RANGE = (50.0, 400.0)  # the gain input's range (limp 50 .. twice the walking gain)
TRUNK_OUTPUTS = [("trunk_wx", "wx"), ("trunk_wy", "wy"), ("trunk_wz", "wz"),
                 ("trunk_qw", "qw"), ("trunk_qx", "qx"), ("trunk_qy", "qy"), ("trunk_qz", "qz"),
                 ("trunk_x", "x"), ("trunk_y", "y"), ("trunk_z", "z"),
                 ("gravity_x", "gx"), ("gravity_y", "gy"), ("gravity_z", "gz")]


def policy_target_pose() -> dict:
    """The scripted targets after POLICY_STEP: the squat of microduck-hang (legs only)."""
    return squat_pose(SQUAT_DEPTH)


def microduck_policy(bumpers=True) -> dict:
    """The microduck a walking policy drives, exported as an FMU for the browser demo.

    Inputs (ExportInputPass, so the model keeps its own scripted stimulus in simulation and the
    FMU takes the host's): `<joint>_target` (rad) for the 14 policy joints in the robot's order,
    and `kp` (the Position P Gain register of every servo). Outputs (ExportOutput):
    `<joint>_q`, `<joint>_qd`, the trunk sensors (TrunkSensors) and the summed sole normal forces.
    """
    from build_model import settings

    d = Diagram()
    low = policy_target_pose()
    goals = {}
    for k, j in enumerate(JOINTS):
        yy = -1500 + 90 * k
        if abs(low[j] - HOME[j]) < 1e-9:
            d.ref(f"Cmd_{j}", "stdlib:sources/Constant", -1500, yy, params={"value": HOME[j]})
        else:
            d.ref(f"Cmd_{j}", "stdlib:sources/Step", -1500, yy,
                  params={"t_step": POLICY_STEP, "initial": HOME[j], "final": low[j]})
        d.ref(f"{j}_target", "stdlib:converters/ExportInputPass", -1350, yy, params={"value": HOME[j]})
        d.sig(f"Cmd_{j}", "y", f"{j}_target", "u")
        goals[j] = (f"{j}_target", "y")
    d.ref("Gain", "stdlib:sources/Constant", -1500, -1700, params={"value": "kp_fw"})
    d.ref("kp", "stdlib:converters/ExportInputPass", -1350, -1700, params={"value": KP_WALK})
    d.sig("Gain", "y", "kp", "u")
    build_robot(d, goals, policy={"kp": ("kp", "y"), "bumpers": bumpers, "ws": POLICY_WS})
    # ---- outputs
    d.ref("Trunk", "project:TrunkSensors", -300, 300)
    d.sig("Free", "pose", "Trunk", "pose")
    d.sig("Free", "Vrelout", "Trunk", "V")
    for k, (name, port) in enumerate(TRUNK_OUTPUTS):
        d.ref(name, "stdlib:converters/ExportOutput", -150, 200 + 60 * k)
        d.sig("Trunk", port, name, "u")
    for k, j in enumerate(JOINTS):
        n = node_names(BY_NAME[[b["name"] for b in BODIES if b.get("joint") == j][0]])
        d.ref(f"{j}_q", "stdlib:converters/ExportOutput", -1100, -1500 + 90 * k)
        d.ref(f"{j}_qd", "stdlib:converters/ExportOutput", -1000, -1500 + 90 * k)
        d.sig(n["joint"], "qout", f"{j}_q", "u")
        d.sig(n["joint"], "qdout", f"{j}_qd", "u")
    for side, name in (("L", "left_foot_contact"), ("R", "right_foot_contact")):
        d.ref(f"Load{side}", "stdlib:continuous/Mux4", -300, 1200 + (0 if side == "L" else 200))
        d.ref(f"Sum{side}", "stdlib:continuous/Sum", -200, 1200 + (0 if side == "L" else 200),
              params={"signs": "[1.0, 1.0, 1.0, 1.0]"}, constants={"N": "4"})
        for k in range(1, 5):
            d.sig(f"Foot{side}{k}", "f_n", f"Load{side}", f"u{k}")
        d.sig(f"Load{side}", "y", f"Sum{side}", "u")
        d.ref(name, "stdlib:converters/ExportOutput", -100, 1200 + (0 if side == "L" else 200))
        d.sig(f"Sum{side}", "y", name, "u")
    d.note("**microduck for a policy.** 14 joint targets and the servo gain in (the export inputs), the "
           "joint angles and rates, the trunk's gyro, orientation, position and projected gravity and the "
           "sole loads out: what velstand.onnx reads and writes at 50 Hz. Rigid joints carry the servo "
           "armature (XL330Rigid: rigid gear, no backlash), the soles start loaded at HOME, the trunk, head "
           "and shins have bumper points. In simulation the targets hold HOME and step to a 15 mm squat at "
           "0.3 s (no policy: HOME tips forward, as in microduck-stand); the FMU takes them from the host.", -1500, -2000, 1000, 180)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "microduck-policy",
        "$comment": "The microduck with the policy interface (joint targets and gain in, sensors out), for the FMU export.",
        "diagram": d.document(),
        "settings": settings(POLICY_T_END, reltol=1e-5, abstol=1e-7, points=401),
        "parameters": robot_globals(policy=True),
        "plots": policy_plots(),
    }


def policy_plots():
    return [
        {"id": "p1", "title": "Trunk height and projected gravity", "signals": ["trunk_z/u", "gravity_x/u", "gravity_y/u", "gravity_z/u"]},
        {"id": "p2", "title": "Leg targets and joint angles", "signals": [s for j in LEGS[:3] for s in (f"{j}_target/y", f"{j}_q/u")]},
        {"id": "p3", "title": "Leg motor currents", "signals": [f"{j}/Current/y" for j in LEGS]},
        {"id": "p4", "title": "Sole loads", "signals": ["left_foot_contact/u", "right_foot_contact/u"]},
    ]


def p_stiffness(v=7.4, kp=None) -> float:
    """Static P stiffness of an XL330 at the horn, N m/rad (duty = gain * error, stall torque)."""
    import xl330 as xl

    kp = xl.KP_FW if kp is None else kp
    return kp * xl.ERROR_GAIN * v * xl.BAM["kt"] / xl.BAM["R"]


def gravity_torques(q: dict) -> dict:
    """Generalised gravity force -dU/dq_j of every joint, trunk held (finite differences)."""
    def u(qq):
        f = fk(qq)
        return sum(b["mass"] * G0 * (f[b["name"]] @ np.append(b["com"], 1.0))[2] for b in BODIES)
    out = {}
    for j in JOINTS:
        qp, qm = dict(q), dict(q)
        qp[j] += 1e-6
        qm[j] -= 1e-6
        out[j] = -(u(qp) - u(qm)) / 2e-6
    return out


def hang_reference(goal: dict) -> dict:
    """Quasi-static encoder angles of the held robot: K (goal - q) + tau_g(q) = 0, with the
    friction band +-F/K of the BAM budget at rest (F = fb + fs + (lfm + lfms) |tau|
    + (lfe + lfes) |tau|, the static load torque on both sides)."""
    import xl330 as xl

    k = p_stiffness()
    q = dict(goal)
    for _ in range(50):
        tg = gravity_torques(q)
        q = {j: goal[j] + tg[j] / k for j in JOINTS}
    tg = gravity_torques(q)
    b = xl.BAM
    out = {}
    for j in JOINTS:
        t = abs(tg[j])
        f = (b["friction_base"] + b["friction_stribeck"] + (b["load_friction_motor"] + b["load_friction_motor_stribeck"]
             + b["load_friction_external"] + b["load_friction_external_stribeck"]) * t)
        out[j] = {"q": q[j], "tau_g": tg[j], "band": f / k}
    return out


MODEL_BUILDERS = [microduck_stand, microduck_hang, microduck_policy]


def report() -> None:
    print(f"bodies {len(BODIES)}, joints {len(JOINTS)}, mass {mass():.4f} kg, weight {mass() * G0:.3f} N")
    print(f"stand height (trunk frame above ground) {stand_height():.5f} m")
    print("CoM at HOME (trunk frame)", np.round(com(), 5))
    for b in feet():
        f = fk(HOME)[b["name"]]
        pts = [(f @ np.append(p, 1.0))[:3] for p in contact_points(b)]
        print(b["name"], "sole points (trunk frame):", np.round(pts, 4).tolist())
    low = squat_pose(SQUAT_DEPTH)
    print("squat deltas", {j: round(low[j] - HOME[j], 4) for j in JOINTS if abs(low[j] - HOME[j]) > 1e-9})
    print(f"P stiffness at 7.4 V, kp 200: {p_stiffness():.4f} N m/rad")
    print("hang reference (held trunk, legs at the squat goals): encoder q, gravity torque, friction band")
    for j, r in hang_reference(low).items():
        print(f"  {j:16s} goal {low[j]:9.5f}  q {r['q']:9.5f}  sag {r['q'] - low[j]:9.5f}  tau_g {r['tau_g']:8.5f}  band +-{r['band']:.4f}")


if __name__ == "__main__":
    report()
