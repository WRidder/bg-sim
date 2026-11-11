# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Write the model documents of `humanoid-dual-arm`.

    uv run examples/humanoid-dual-arm/design/build_models.py

* `humanoid-ik`    the firmware alone (kinematic, seconds per run): the object trajectory and four
                   ArmIK blocks, the stacked pair and the ideal-SRS pair, drawn in 3D from the IK
                   solutions. The dashboard mirrors the interactive page.
* `humanoid-hold`  the torso with both stacked 7-DOF arms as a spatial multibond model: links with
                   mass and inertia, compliant Revolute3D joints, one bond-graph drive per joint
                   (motor, rotor inertia, elastic gear, joint friction, torque sensor), the shared
                   box held by two stiff grasp springs (Revolute3D welds), and the 1 kHz firmware
                   (trajectory -> IK -> PID servo per arm).

Every number comes from `srs.py` (kinematics, IK) and `humanoid.py` (task, dynamics, drives).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import humanoid as dz
import srs
from diagram import Diagram, fmt, mat, pose_params, vec

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
SCENE = {"file": "scenes/humanoid.sdf"}
SIDES = (("L", 1, "left"), ("R", -1, "right"))

# ------------------------------------------------------------------ the firmware layer


def add_firmware(d: Diagram, x0: int = -1400, y0: int = 400) -> None:
    """Traj -> IKL, IKR (stacked) and IdealL, IdealR (ideal SRS beside the robot)."""
    d.ref("traj", "Traj", "project:ObjectTrajectory", x0, y0 + 600)
    for row, (key, name, s, ideal) in enumerate(
        (("ikl", "IKL", 1, False), ("ikr", "IKR", -1, False), ("idl", "IdealL", 1, True), ("idr", "IdealR", -1, True))
    ):
        q0 = dz.Q_START_IDEAL if ideal else dz.Q_START
        params = {"s": fmt(s), "q0": vec(q0)}
        if ideal:
            params["off"] = mat(srs.OFF_IDEAL)
        # the outputs hold the start posture until the first tick (t = Ts), so the plots, the
        # servos and the 3D view start where the arms are
        starts = {f"qr{k}": fmt(q0[k - 1] * srs.D) for k in range(1, 8)}
        starts.update({f"e{c}": fmt(v) for c, v in zip("xyz", srs.elbow(q0, s, ideal))})
        d.ref(key, name, "project:ArmIK", x0 + 320, y0 + 300 * row, params=params, starts=starts)
        d.connect("signal", ("traj", "obj"), (key, "obj"))


def settings(t_end: float, points: int, solver: str = "Rodas5P", reltol: float = 1e-6, abstol: float = 1e-8) -> dict:
    return {
        "t_start": 0.0,
        "t_end": t_end,
        "solver": solver,
        "reltol": reltol,
        "abstol": abstol,
        "max_step": None,
        "output": {"mode": "points", "points": points},
        "event_limit": 10000,
    }


def pose_binding(target: str, signal: str) -> dict:
    return {"target": target, "property": "pose", "signal": [f"{signal}[{n}]" for n in range(1, 8)]}


def joint_bindings(prefix: str, signal) -> list[dict]:
    return [
        {"target": f"joint:{prefix}_joint{k}", "property": "position", "signal": signal(k)}
        for k in range(1, 8)
    ]


# ------------------------------------------------------------------ dashboard


def slider(cid, title, param, lo, hi, step, dec, unit, value=None) -> dict:
    card = {"id": cid, "kind": "slider", "size": "1x1", "title": title, "parameter": param,
            "options": {"min": lo, "max": hi, "step": step, "decimals": dec, "unit": unit}}  # fmt: skip
    if value is not None:
        card["value"] = value
    return card


def value(cid, title, signal, dec, unit, zones=None) -> dict:
    opts = {"decimals": dec, "unit": unit, "sparkline": True}
    if zones:
        opts["zones"] = zones
    return {"id": cid, "kind": "value", "size": "1x1", "title": title, "signals": [signal], "options": opts}


ERR_ZONES_MM = [{"from": 0.0, "to": 2.0, "tone": "good"}, {"from": 2.0, "to": 1000.0, "tone": "bad"}]
ERR_ZONES_DEG = [{"from": 0.0, "to": 2.0, "tone": "good"}, {"from": 2.0, "to": 180.0, "tone": "bad"}]
LIM_ZONES = [{"from": 0.0, "to": 5.0, "tone": "bad"}, {"from": 5.0, "to": 15.0, "tone": "warn"},
             {"from": 15.0, "to": 100.0, "tone": "good"}]  # fmt: skip

REDUNDANCY_TEXT = (
    "**Redundancy.** A rigid grasp fixes the full pose of each hand (3 position + 3 orientation), so two hands "
    "on one object give **12 constraints**. Two 7-DOF arms have **14 joints: 2 left over**, one self-motion "
    "per arm (the elbow swings about the shoulder-wrist line while the hand stays put). Two 6-DOF arms "
    "(J5 locked) have **12 joints for 12 constraints: no slack**, so the object pose fixes both postures, "
    "the elbow bias does nothing, and at the default pose the arms run into J3 and J6 limits and miss the "
    "grasp by about 3.5 mm and 3.3 deg."
)


def input_cards() -> list[dict]:
    return [
        slider("x", "Object x (right)", "Traj/x", -0.4, 0.4, 0.01, 2, "m"),
        slider("y", "Object y (up)", "Traj/y", -0.5, 0.3, 0.01, 2, "m"),
        slider("z", "Object z (forward)", "Traj/z", 0.05, 0.7, 0.01, 2, "m"),
        slider("roll", "Object roll", "Traj/roll", -60.0, 60.0, 1.0, 0, "deg"),
        slider("pitch", "Object pitch", "Traj/pitch", -60.0, 60.0, 1.0, 0, "deg"),
        slider("yaw", "Object yaw", "Traj/yaw", -60.0, 60.0, 1.0, 0, "deg"),
        slider("bias", "Elbow bias", "Traj/bias", -40.0, 40.0, 1.0, 0, "deg"),
        {"id": "dof6", "kind": "toggle", "size": "1x1", "title": "6-DOF arms (lock J5)", "parameter": "Traj/dof6"},
    ]


def ik_readouts() -> list[dict]:
    cards = []
    for key, label in (("IKL", "Stacked left"), ("IKR", "Stacked right"), ("IdealL", "Ideal left")):
        cards += [
            value(f"{key}_pe", f"{label}: position error", f"{key}/pe", 2, "mm", ERR_ZONES_MM),
            value(f"{key}_oe", f"{label}: orientation error", f"{key}/oe", 2, "deg", ERR_ZONES_DEG),
            value(f"{key}_lim", f"{label}: nearest limit", f"{key}/lim", 0, "%", LIM_ZONES),
        ]
    return cards


def joint_plot(cid, title, key, prefix="") -> dict:
    return {"id": cid, "kind": "plot", "size": "2x2", "title": title, "signals": [f"{prefix}{key}/q{k}" for k in range(1, 8)]}


# ------------------------------------------------------------------ humanoid-ik


def build_ik() -> dict:
    d = Diagram()
    add_firmware(d, x0=100, y0=100)
    plots = [
        {"id": "p1", "title": "Stacked left arm: joint angles [deg]", "signals": [f"IKL/q{k}" for k in range(1, 8)]},
        {"id": "p2", "title": "Stacked right arm: joint angles [deg]", "signals": [f"IKR/q{k}" for k in range(1, 8)]},
        {"id": "p3", "title": "Hand pose error of the IK solution (stacked)", "signals": ["IKL/pe", "IKL/oe", "IKR/pe", "IKR/oe"]},
        {"id": "p4", "title": "Nearest joint limit [%]", "signals": ["IKL/lim", "IKR/lim", "IdealL/lim", "IdealR/lim"]},
        {"id": "p5", "title": "Ideal SRS: joint angles [deg]", "signals": [f"IdealL/q{k}" for k in range(1, 8)]},
        {"id": "p6", "title": "Object (page frame) and elbow bias", "signals": ["Traj/px", "Traj/py", "Traj/pz", "Traj/elbow_bias"]},
    ]
    cards = [{"id": "t", "kind": "text", "size": "2x1", "title": "Two 7-DOF SRS arms on one object",
              "options": {"markdown": True, "text": REDUNDANCY_TEXT}}]  # fmt: skip
    cards += input_cards()
    cards += [
        {"id": "held", "kind": "indicator", "size": "1x1", "title": "Stacked left holds the pose", "signals": ["IKL/held"],
         "options": {"threshold": 0.5, "onWhen": "above"}},
    ]  # fmt: skip
    cards += ik_readouts()
    cards += [
        joint_plot("qL", "Stacked left: joint angles [deg]", "IKL"),
        joint_plot("qR", "Stacked right: joint angles [deg]", "IKR"),
        {"id": "err", "kind": "plot", "size": "2x2", "title": "IK hand pose error (mm, deg)", "signals": ["IKL/pe", "IKL/oe", "IdealL/pe", "IdealL/oe"]},
        {"id": "lim", "kind": "plot", "size": "2x2", "title": "Nearest joint limit [%]", "signals": ["IKL/lim", "IdealL/lim"]},
    ]  # fmt: skip
    bindings = joint_bindings("L", lambda k: f"IKL/qr{k}") + joint_bindings("R", lambda k: f"IKR/qr{k}")
    bindings += joint_bindings("GL", lambda k: f"IdealL/qr{k}") + joint_bindings("GR", lambda k: f"IdealR/qr{k}")
    bindings += [pose_binding("link:box", "Traj/g"), pose_binding("link:box_target", "Traj/g"),
                 pose_binding("link:ghost_box", "Traj/gi")]  # fmt: skip
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "humanoid-ik",
        "$comment": (
            "The firmware of humanoid-hold alone, kinematic: ObjectTrajectory (start pose, quintic move to the "
            "dashboard pose, elbow-bias ramp, the 6-DOF switch) drives four ArmIK blocks at 1 kHz: the stacked "
            "7-DOF SRS arms (shoulder and wrist offsets) and an ideal SRS pair (zero offsets, the same link "
            "lengths) beside them. Each IK is the interactive page's damped least squares with a null-space pull "
            "toward home, one iteration per tick. The 3D view draws the IK solutions."
        ),
        "diagram": d.document(),
        "settings": settings(dz.T_END, 1301, solver="Tsit5"),
        "plots": plots,
        "scene": SCENE,
        "bindings": bindings,
        "dashboard": {"autoRerun": True, "cards": cards},
    }


# ------------------------------------------------------------------ humanoid-hold: the arms

X0 = 400  # first joint column
DX = 520  # column pitch per joint
ROWS = {"L": 300, "R": 2700}  # chain row per arm; the pose band is 450 below, the drives 900 below


def add_arm(d: Diagram, p: str, s: int) -> None:
    """World -> Mount -> J1 -> Link1 -> BJ1 -> B1, T2 -> J2 -> ... -> B7, the pose band and the
    seven drives of arm p (L/R)."""
    f = dz.chain_frames(s)
    y0 = ROWS[p]
    band = y0 + 450
    yd = y0 + 900
    tau0 = dz.statics(dz.Q_START, s, dz.HAND_LOAD)
    bgear = dz.gear_damping()
    d.ref(f"world{p}", f"World{p}", "stdlib:multibond/GroundSpatial", X0 - 260, y0)
    d.ref(f"mount{p}", f"Mount{p}", "stdlib:multibond/FixedTransform3DNeutral", X0 - 120, y0,
          params=pose_params(np.linalg.inv(f["LN"][0])))  # fmt: skip
    d.connect("bond", (f"world{p}", "p"), (f"mount{p}", "b"))
    d.ref(f"base{p}", f"Base{p}", "stdlib:spatial/LocalPose3D", X0 - 260, band, params=pose_params(np.eye(4)))
    prev = f"base{p}"
    for i in range(srs.NJ):
        k = i + 1
        x = X0 + DX * i
        bt, br = dz.held_damping(dz.K_HELD, i)
        d.ref(f"j{p}{k}", f"{p}J{k}", "stdlib:spatial/Revolute3D", x + 80, y0,
              params={"kt": fmt(dz.K_HELD), "kr": fmt(dz.K_HELD), "bt": fmt(bt), "br": fmt(br),
                      "q0": fmt(dz.Q_START[i] * srs.D)})  # fmt: skip
        d.ref(f"link{p}{k}", f"{p}Link{k}", "stdlib:multibond/FixedTransform3DNeutral", x + 200, y0, params=pose_params(f["LC"][i]))
        d.junction(f"bj{p}{k}", f"{p}BJ{k}", "1", x + 320, y0 + 10)
        d.ref(f"b{p}{k}", f"{p}B{k}", "stdlib:spatial/RigidBody3D", x + 310, y0 + 110,
              params={"m": fmt(dz.LINK_MASS[i]), "J": vec(dz.link_inertia(i)), "g0": fmt(dz.G0)})  # fmt: skip
        if i == 0:
            d.connect("bond", (f"mount{p}", "a"), (f"j{p}1", "parent"))
        else:
            t_pose = np.linalg.inv(f["LN"][i]) @ f["LC"][i - 1]
            d.ref(f"t{p}{k}", f"{p}T{k}", "stdlib:multibond/FixedTransform3DNeutral", x - 40, y0, params=pose_params(t_pose))
            d.connect("bond", (f"t{p}{k}", "a"), (f"j{p}{k}", "parent"))
            d.connect("bond", (f"bj{p}{k - 1}", None), (f"t{p}{k}", "b"))
        d.connect("bond", (f"j{p}{k}", "child"), (f"link{p}{k}", "a"))
        d.connect("bond", (f"link{p}{k}", "b"), (f"bj{p}{k}", None))
        d.connect("bond", (f"b{p}{k}", "p"), (f"bj{p}{k}", None))
        # pose band: W_k = W_{k-1} o LN_k o J_k.pose ; body P_k = W_k o LC_k
        d.ref(f"ln{p}{k}", f"{p}LN{k}", "stdlib:spatial/LocalPose3D", x - 40, band + 100, params=pose_params(f["LN"][i]))
        d.ref(f"ca{p}{k}", f"{p}CA{k}", "stdlib:multibond/ComposePose3D", x - 40, band)
        d.ref(f"w{p}{k}", f"{p}W{k}", "stdlib:multibond/ComposePose3D", x + 80, band)
        d.ref(f"lc{p}{k}", f"{p}LC{k}", "stdlib:spatial/LocalPose3D", x + 310, band + 220, params=pose_params(f["LC"][i]))
        d.ref(f"pb{p}{k}", f"{p}P{k}", "stdlib:multibond/ComposePose3D", x + 310, band + 110)
        d.connect("signal", (prev, "g"), (f"ca{p}{k}", "gp"))
        d.connect("signal", (f"ln{p}{k}", "g"), (f"ca{p}{k}", "gl"))
        d.connect("signal", (f"ca{p}{k}", "g"), (f"w{p}{k}", "gp"))
        d.connect("signal", (f"j{p}{k}", "pose"), (f"w{p}{k}", "gl"))
        d.connect("signal", (f"w{p}{k}", "g"), (f"pb{p}{k}", "gp"))
        d.connect("signal", (f"lc{p}{k}", "g"), (f"pb{p}{k}", "gl"))
        d.connect("signal", (f"pb{p}{k}", "g"), (f"b{p}{k}", "g"))
        prev = f"w{p}{k}"
        # drive: Motor (MSe) -> 1 [Rotor: I] -> 0 [TauSense: De] -> 1 [Spring: C, Damper: R]
        #                                         -> 1 [Friction: R] -> J.drive
        d.ref(f"mot{p}{k}", f"{p}Motor{k}", "stdlib:bondgraph/MSe", x - 40, yd, params={"gain": "1.0"})
        d.junction(f"jm{p}{k}", f"{p}Rotor{k}J", "1", x + 60, yd)
        d.ref(f"rot{p}{k}", f"{p}Rotor{k}", "stdlib:bondgraph/I", x + 60, yd + 100, params={"i": fmt(dz.J_ROTOR[i])})
        d.junction(f"s0{p}{k}", f"{p}Gear{k}0", "0", x + 180, yd)
        d.junction(f"js{p}{k}", f"{p}Elastic{k}", "1", x + 180, yd + 100)
        d.ref(f"cg{p}{k}", f"{p}Spring{k}", "stdlib:bondgraph/C", x + 120, yd + 200,
              params={"c": fmt(1.0 / dz.K_GEAR[i])}, starts={"q": fmt(tau0[i] / dz.K_GEAR[i])})  # fmt: skip
        d.ref(f"rg{p}{k}", f"{p}Damper{k}", "stdlib:bondgraph/R", x + 240, yd + 200, params={"r": fmt(bgear[i])})
        d.ref(f"tq{p}{k}", f"{p}TauSense{k}", "stdlib:bondgraph/De", x + 180, yd - 100)
        d.junction(f"jl{p}{k}", f"{p}Link{k}J", "1", x + 300, yd)
        d.ref(f"fr{p}{k}", f"{p}Friction{k}", "stdlib:bondgraph/R", x + 300, yd + 100, params={"r": fmt(dz.B_JOINT)})
        d.connect("bond", (f"mot{p}{k}", "p"), (f"jm{p}{k}", None))
        d.connect("bond", (f"jm{p}{k}", None), (f"rot{p}{k}", "p"))
        d.connect("bond", (f"jm{p}{k}", None), (f"s0{p}{k}", None))
        d.connect("bond", (f"s0{p}{k}", None), (f"js{p}{k}", None))
        d.connect("bond", (f"js{p}{k}", None), (f"cg{p}{k}", "p"))
        d.connect("bond", (f"js{p}{k}", None), (f"rg{p}{k}", "p"))
        d.connect("bond", (f"s0{p}{k}", None), (f"tq{p}{k}", "p"))
        d.connect("bond", (f"s0{p}{k}", None), (f"jl{p}{k}", None))
        d.connect("bond", (f"jl{p}{k}", None), (f"fr{p}{k}", "p"))
        d.connect("bond", (f"jl{p}{k}", None), (f"j{p}{k}", "drive"))
    # the hand frame: Hand = W7 o LH
    xh = X0 + DX * 7
    d.ref(f"lh{p}", f"{p}LH", "stdlib:spatial/LocalPose3D", xh, band + 100, params=pose_params(f["LH"]))
    d.ref(f"hand{p}", f"{p}Hand", "stdlib:multibond/ComposePose3D", xh + 120, band)
    d.connect("signal", (f"w{p}7", "g"), (f"hand{p}", "gp"))
    d.connect("signal", (f"lh{p}", "g"), (f"hand{p}", "gl"))


def add_grasp(d: Diagram, p: str, s: int) -> None:
    """Hand p -> Tip (body 7 seen from the hand frame) -> Weld (Revolute3D, axis held by a
    torsion spring) -> Grip (the box frame seen from the hand) -> BoxJ."""
    f = dz.chain_frames(s)
    y0 = ROWS[p]
    xw = X0 + DX * 7 + 300
    yw = y0 + (600 if p == "L" else -600)
    g = dz.GRASP
    bt = 1.4 * np.sqrt(g["kt"] * 0.5 * dz.BOX_MASS)
    br = 1.4 * np.sqrt(g["kr"] * 0.01)
    tip = np.linalg.inv(f["LH"]) @ f["LC"][6]
    d.ref(f"tip{p}", f"{p}Tip", "stdlib:multibond/FixedTransform3DNeutral", xw - 120, y0, params=pose_params(tip))
    d.ref(f"weld{p}", f"{p}Weld", "stdlib:spatial/Revolute3D", xw, yw,
          params={"kt": fmt(g["kt"]), "kr": fmt(g["kr"]), "bt": fmt(bt), "br": fmt(br), "q0": "0.0"})  # fmt: skip
    d.ref(f"grip{p}", f"{p}Grip", "stdlib:multibond/FixedTransform3DNeutral", xw + 140, yw,
          params=pose_params(np.linalg.inv(srs.grasp(s))))  # fmt: skip
    d.junction(f"wj{p}", f"{p}WeldJ", "1", xw, yw + 120)
    d.ref(f"wc{p}", f"{p}WeldSpring", "stdlib:bondgraph/C", xw - 60, yw + 220, params={"c": fmt(1.0 / g["kq"])})
    d.ref(f"wr{p}", f"{p}WeldDamper", "stdlib:bondgraph/R", xw + 60, yw + 220, params={"r": fmt(br)})
    d.connect("bond", (f"bj{p}7", None), (f"tip{p}", "b"))
    d.connect("bond", (f"tip{p}", "a"), (f"weld{p}", "parent"))
    d.connect("bond", (f"weld{p}", "child"), (f"grip{p}", "a"))
    d.connect("bond", (f"grip{p}", "b"), ("boxj", None))
    d.connect("bond", (f"wj{p}", None), (f"weld{p}", "drive"))
    d.connect("bond", (f"wj{p}", None), (f"wc{p}", "p"))
    d.connect("bond", (f"wj{p}", None), (f"wr{p}", "p"))
    d.ref(f"gl{p}", f"{p}GraspLoad", "project:GraspLoad", xw + 300, yw + 120,
          params={"kt": fmt(g["kt"]), "kr": fmt(g["kr"]), "kq": fmt(g["kq"])})  # fmt: skip
    d.connect("signal", (f"weld{p}", "dlin"), (f"gl{p}", "dl"))
    d.connect("signal", (f"weld{p}", "dang"), (f"gl{p}", "dth"))
    d.connect("signal", (f"weld{p}", "qout"), (f"gl{p}", "q"))


def add_box(d: Diagram) -> None:
    """The box (RigidBody3D) on its 1-junction; its pose is composed through the left grasp:
    Box = LHand o LWeld.pose o inv(G_left)."""
    xb = X0 + DX * 7 + 700
    yb = (ROWS["L"] + ROWS["R"]) // 2
    d.junction("boxj", "BoxJ", "1", xb, yb)
    d.ref("box", "Box", "stdlib:spatial/RigidBody3D", xb, yb + 110,
          params={"m": fmt(dz.BOX_MASS), "J": vec(dz.box_inertia()), "g0": fmt(dz.G0)})  # fmt: skip
    d.connect("bond", ("box", "p"), ("boxj", None))
    d.ref("lgrip_pose", "LGripPose", "stdlib:multibond/ComposePose3D", xb - 250, yb - 200)
    d.ref("lginv", "LGraspInv", "stdlib:spatial/LocalPose3D", xb - 250, yb - 80, params=pose_params(np.linalg.inv(srs.grasp(1))))
    d.ref("boxpose", "BoxPose", "stdlib:multibond/ComposePose3D", xb - 100, yb - 140)
    d.connect("signal", ("handL", "g"), ("lgrip_pose", "gp"))
    d.connect("signal", ("weldL", "pose"), ("lgrip_pose", "gl"))
    d.connect("signal", ("lgrip_pose", "g"), ("boxpose", "gp"))
    d.connect("signal", ("lginv", "g"), ("boxpose", "gl"))
    d.connect("signal", ("boxpose", "g"), ("box", "g"))


def add_hold_firmware(d: Diagram) -> None:
    add_firmware(d, x0=-1500, y0=900)
    for p, s, _ in SIDES:
        key = f"servo{p}"
        tau0 = dz.statics(dz.Q_START, s, dz.HAND_LOAD)
        d.ref(key, f"Servo{p}", "project:ArmServo", -700, ROWS[p] + 900,
              params={"tau0": vec(tau0), "qp0": vec(dz.Q_START * srs.D)},
              starts={f"u{k}": fmt(tau0[k - 1]) for k in range(1, 8)})  # fmt: skip
        ik = f"ik{p.lower()}"
        for k in range(1, 8):
            d.connect("signal", (ik, f"qr{k}"), (key, f"qr{k}"))
            d.connect("signal", (f"j{p}{k}", "qout"), (key, f"q{k}"))
            d.connect("signal", (f"j{p}{k}", "qdout"), (key, f"dq{k}"))
            d.connect("signal", (key, f"u{k}"), (f"mot{p}{k}", "u"))
    # readouts: the object and each hand against the commanded poses
    yb = (ROWS["L"] + ROWS["R"]) // 2
    xb = X0 + DX * 7 + 1000
    d.ref("boxerr", "BoxError", "project:PoseError", xb, yb - 300)
    d.connect("signal", ("boxpose", "g"), ("boxerr", "g"))
    d.connect("signal", ("traj", "g"), ("boxerr", "gr"))
    for p, s, _ in SIDES:
        y = yb + (200 if p == "L" else 400)
        d.ref(f"gs{p}", f"{p}GraspFrame", "stdlib:spatial/LocalPose3D", xb - 150, y + 80, params=pose_params(srs.grasp(s)))
        d.ref(f"ht{p}", f"{p}HandTarget", "stdlib:multibond/ComposePose3D", xb, y)
        d.ref(f"he{p}", f"{p}HandError", "project:PoseError", xb + 150, y)
        d.connect("signal", ("traj", "g"), (f"ht{p}", "gp"))
        d.connect("signal", (f"gs{p}", "g"), (f"ht{p}", "gl"))
        d.connect("signal", (f"hand{p}", "g"), (f"he{p}", "g"))
        d.connect("signal", (f"ht{p}", "g"), (f"he{p}", "gr"))


def build_hold() -> dict:
    d = Diagram()
    for p, s, _ in SIDES:
        add_arm(d, p, s)
    add_box(d)
    for p, s, _ in SIDES:
        add_grasp(d, p, s)
    add_hold_firmware(d)
    plots = [
        {"id": "p1", "title": "Left arm: joint angles [rad]", "signals": [f"LJ{k}/qout" for k in range(1, 8)]},
        {"id": "p2", "title": "Right arm: joint angles [rad]", "signals": [f"RJ{k}/qout" for k in range(1, 8)]},
        {"id": "p3", "title": "Object pose error (simulated vs commanded)", "signals": ["BoxError/e_mm", "BoxError/e_deg"]},
        {"id": "p4", "title": "Hand pose errors (simulated vs grasp target)",
         "signals": ["LHandError/e_mm", "LHandError/e_deg", "RHandError/e_mm", "RHandError/e_deg"]},
        {"id": "p5", "title": "IK solution errors and nearest limit", "signals": ["IKL/pe", "IKL/oe", "IKL/lim"]},
        {"id": "p6", "title": "Grasp loads", "signals": ["LGraspLoad/F", "RGraspLoad/F", "LGraspLoad/M", "RGraspLoad/M"]},
        {"id": "p7", "title": "Left elbow position (world)", "signals": ["LW4/g[5]", "LW4/g[6]", "LW4/g[7]"]},
        {"id": "p8", "title": "Left joint torques (sensors) [N m]", "signals": [f"LTauSense{k}/y" for k in range(1, 8)]},
    ]  # fmt: skip
    cards = [{"id": "t", "kind": "text", "size": "2x1", "title": "Bimanual hold, dynamic",
              "options": {"markdown": True, "text": REDUNDANCY_TEXT + " Here the arms are a multibody "
                          "model on joint servos and the box hangs on two stiff grasp springs: what the IK "
                          "cannot match becomes grasp load."}}]  # fmt: skip
    cards += input_cards()
    cards += [
        value("box_mm", "Object position error (sim)", "BoxError/e_mm", 2, "mm", ERR_ZONES_MM),
        value("box_deg", "Object orientation error (sim)", "BoxError/e_deg", 2, "deg", ERR_ZONES_DEG),
        value("L_mm", "Left hand error (sim)", "LHandError/e_mm", 2, "mm", ERR_ZONES_MM),
        value("L_deg", "Left hand error (sim)", "LHandError/e_deg", 2, "deg", ERR_ZONES_DEG),
        value("R_mm", "Right hand error (sim)", "RHandError/e_mm", 2, "mm", ERR_ZONES_MM),
        value("R_deg", "Right hand error (sim)", "RHandError/e_deg", 2, "deg", ERR_ZONES_DEG),
        value("IKL_pe", "Left IK solution: position error", "IKL/pe", 2, "mm", ERR_ZONES_MM),
        value("IKL_oe", "Left IK solution: orientation error", "IKL/oe", 2, "deg", ERR_ZONES_DEG),
        value("IKL_lim", "Left: nearest joint limit", "IKL/lim", 0, "%", LIM_ZONES),
        value("IKR_lim", "Right: nearest joint limit", "IKR/lim", 0, "%", LIM_ZONES),
        value("F", "Left grasp force", "LGraspLoad/F", 1, "N"),
        value("M", "Left grasp moment", "LGraspLoad/M", 2, "N*m"),
        {"id": "qL", "kind": "plot", "size": "2x2", "title": "Left arm: joint angles [rad]", "signals": [f"LJ{k}/qout" for k in range(1, 8)]},
        {"id": "qR", "kind": "plot", "size": "2x2", "title": "Right arm: joint angles [rad]", "signals": [f"RJ{k}/qout" for k in range(1, 8)]},
        {"id": "eb", "kind": "plot", "size": "2x2", "title": "Object error (mm, deg) and elbow bias [deg]", "signals": ["BoxError/e_mm", "BoxError/e_deg", "Traj/elbow_bias"]},
        {"id": "el", "kind": "plot", "size": "2x2", "title": "Left elbow position (world, m)", "signals": ["LW4/g[5]", "LW4/g[6]", "LW4/g[7]"]},
    ]  # fmt: skip
    bindings = joint_bindings("L", lambda k: f"LJ{k}/qout") + joint_bindings("R", lambda k: f"RJ{k}/qout")
    bindings += joint_bindings("GL", lambda k: f"IdealL/qr{k}") + joint_bindings("GR", lambda k: f"IdealR/qr{k}")
    bindings += [pose_binding("link:box", "BoxPose/g"), pose_binding("link:box_target", "Traj/g"),
                 pose_binding("link:ghost_box", "Traj/gi")]  # fmt: skip
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "humanoid-hold",
        "$comment": (
            "Humanoid torso with two stacked 7-DOF SRS arms (shoulder pitch-roll-yaw, elbow, forearm yaw, wrist "
            "pitch-roll, shoulder and wrist axis offsets) holding one box with both hands. Plant: spatial multibond "
            "chains (compliant Revolute3D joints, RigidBody3D links with illustrative masses), per joint a "
            "bond-graph drive (motor torque MSe, reflected rotor inertia I, elastic gear C/R with a torque sensor "
            "De, joint friction R), the box on two stiff grasp springs (Revolute3D welds with a torsion spring on "
            "the axis). Firmware at 1 kHz: ObjectTrajectory -> ArmIK per arm (damped least squares with a "
            "null-space pull toward home plus the elbow bias; J5 locked with Traj/dof6) -> ArmServo (PID). The "
            "ideal-SRS pair (IdealL/IdealR) is kinematic and drawn beside the robot."
        ),
        "diagram": d.document(),
        "settings": settings(dz.T_END, 1301, solver="FBDF", reltol=1e-4, abstol=1e-6),
        "plots": plots,
        "scene": SCENE,
        "bindings": bindings,
        "dashboard": {"autoRerun": False, "cards": cards},
    }


def write(model: dict) -> None:
    path = MODELS / f"{model['name']}.bgmodel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT.parent.parent)}")


def main() -> None:
    write(build_ik())
    write(build_hold())


if __name__ == "__main__":
    main()
