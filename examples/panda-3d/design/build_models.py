# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the model documents of `panda-3d`.

    uv run examples/panda-3d/design/build_models.py

* `panda-free`  the bare spatial multibond Panda (Gaz et al. 2019 parameters) released at rest
                under gravity with zero joint torque: the pure dynamics check against Pinocchio;
* `panda`       the two-layer model: the `Robot` subsystem (mechanics, seven elastic drives with
                rotor inertia, gear, Gaz friction and torque limit, encoders, rate and torque
                sensors) driven by the 1 kHz outer layer (Cartesian trajectory -> analytical IK
                -> PD + gravity feedforward);
* `panda-free-rigid`, `panda-rigid`  the same two models on the rigid joint `Revolute3DRigid`
                (hard held directions, reduced by `mtkcompile`'s index reduction to two
                states per joint; plan/MULTIBOND_PLAN.md section 5.7).

Every link of the arm is an instance of a library subsystem: `RevoluteLink3D` (compliant joint)
or `RevoluteLink3DRigid`, whose definitions (`library/*.bgsub.json`) this script writes from
`serial_link.py`.

Every number comes from `panda.py` (parameters, kinematics, drives) and `design.py` (gains,
waypoints, start state).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import design as dz
import panda as pz
import serial_link as sl
from diagram import Diagram, fmt, pose_params, vec

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
SCENE = {"file": "scenes/panda.sdf"}

# ------------------------------------------------------------------ the spatial chain

STAIR_X, STAIR_Y = 300, 300  # first column of the chain
STAIR_DX = 520  # column pitch per joint


def held_damping(k: float, i: int) -> tuple[float, float]:
    """(bt, br): 0.7 of critical for the distal mass and for a 0.3 kg m^2 reference inertia."""
    distal = float(pz.MASS[i:].sum())
    return 1.4 * math.sqrt(k * distal), 1.4 * math.sqrt(k * 0.3)


def add_chain(d: Diagram, q0, k_joint: float, qdd0=None, y0: int = STAIR_Y,
              rigid: bool = False) -> list[tuple[str, str]]:
    """World -> L1 -> L2 -> ... -> L7, instances of the library subsystem RevoluteLink3D (or
    RevoluteLink3DRigid), and the flange pose TCP = L7.g o LFlange.

    Link i (design/serial_link.py): T (L1: the base mount; else the offset from body i-1's
    principal centre-of-mass frame to joint i) -> J -> Link -> BJ <- B, and the pose band
    W_i = W_{i-1} o LN_i o J_i.pose, P_i = W_i o LC_i. Body i sits at its principal
    centre-of-mass frame (LC_i), so RigidBody3D gets the diagonal principal inertia. The held
    directions start on the deflections of the joint loads at the start (`qdd0`: the rigid-body
    acceleration there, None for rest). With `rigid` the joints are `Revolute3DRigid`: no
    held-direction parameters and no deflection starts.

    Returns the seven joint drive ports.
    """
    wrench = pz.joint_wrenches(q0, qdd0)
    bx = [STAIR_X + STAIR_DX * i for i in range(pz.NJ)]
    d.ref("world", "World", "stdlib:multibond/GroundSpatial", bx[0] - 160, y0 + 100)
    d.ref("mpose", "Base", "stdlib:spatial/LocalPose3D", bx[0] - 160, y0, params=pose_params(np.eye(4)))
    drives = []
    for i in range(pz.NJ):
        k = i + 1
        force, moment = wrench[i]
        if rigid:
            joint, starts = {"q0": fmt(q0[i])}, {}
        else:
            bt, br = held_damping(k_joint, i)
            joint = {"kt": fmt(k_joint), "kr": fmt(k_joint), "bt": fmt(bt), "br": fmt(br), "q0": fmt(q0[i])}
            starts = {"dth": vec(moment[:2] / k_joint), "dl": vec(force / k_joint)}
        # T: the mount for joint 1, else body i-1's centre-of-mass frame seen from joint i
        t_pose = np.linalg.inv(pz.joint_frame(0)) if i == 0 else np.linalg.inv(pz.joint_frame(i)) @ pz.com_frame(i - 1)
        jp, _ = pz.principal(i)
        params, pin_starts = sl.pins(
            pose_params(t_pose), joint, pose_params(pz.com_frame(i)),
            {"m": fmt(pz.MASS[i]), "J": vec(jp), "g0": fmt(pz.G0)},
            pose_params(pz.joint_frame(i)), pose_params(pz.com_frame(i)), starts,
        )  # fmt: skip
        d.ref(f"l{k}", f"L{k}", f"project:{sl.name(rigid)}", bx[i] + 80, y0, params=params, starts=pin_starts)
        if i == 0:
            d.connect("bond", ("world", "p"), ("l1", "parent"))
            d.connect("signal", ("mpose", "g"), ("l1", "gp"))
        else:
            d.connect("bond", (f"l{i}", "child"), (f"l{k}", "parent"))
            d.connect("signal", (f"l{i}", "g"), (f"l{k}", "gp"))
        drives.append((f"l{k}", "drive"))
    # flange (TCP of the bare arm): W7 o Tz(0.107)
    xf = bx[-1] + 360
    d.ref("lf", "LFlange", "stdlib:spatial/LocalPose3D", xf, y0 + 140,
          params=pose_params(pz.hom(np.eye(3), [0.0, 0.0, pz.D_FLANGE])))  # fmt: skip
    d.ref("tcp", "TCP", "stdlib:multibond/ComposePose3D", xf + 140, y0)
    d.connect("signal", ("l7", "g"), ("tcp", "gp"))
    d.connect("signal", ("lf", "g"), ("tcp", "gl"))
    return drives


def write_definitions() -> None:
    """library/RevoluteLink3D.bgsub.json and library/RevoluteLink3DRigid.bgsub.json."""
    for rigid in (False, True):
        definition = sl.definition(rigid)
        path = ROOT / "library" / f"{definition['name']}.bgsub.json"
        path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT.parent.parent)}")


def settings(solver: str, reltol: float, abstol: float, points: int, t_end: float) -> dict:
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


def joint_bindings(prefix: str) -> list[dict]:
    return [
        {"target": f"joint:panda_joint{k}", "property": "position", "signal": f"{prefix}L{k}/J/qout"}
        for k in range(1, 8)
    ]


def pose_binding(target: str, signal: str) -> dict:
    return {"target": target, "property": "pose", "signal": [f"{signal}[{n}]" for n in range(1, 8)]}


# ------------------------------------------------------------------ panda-free


RIGID_NOTE = (
    " Rigid variant: the seven joints are Revolute3DRigid (the held directions are hard velocity "
    "constraints with Lagrange-multiplier reactions, so the link inertias are derivative-causal, W201 "
    "by design), and mtkcompile's index reduction keeps q and qdot per joint as the states "
    "(plan/MULTIBOND_PLAN.md section 5.7)."
)


def build_free(rigid: bool = False) -> dict:
    d = Diagram()
    qdd0 = pz.forward_dynamics(dz.Q_FREE, np.zeros(pz.NJ), np.zeros(pz.NJ))
    drives = add_chain(d, dz.Q_FREE, dz.K_HELD, qdd0, rigid=rigid)
    for i, port in enumerate(drives):
        x = STAIR_X + STAIR_DX * i + 80
        d.ref(f"se{i + 1}", f"Free{i + 1}", "stdlib:bondgraph/Se", x - 120, STAIR_Y + 260, params={"e": "0.0"})
        d.connect("bond", (f"se{i + 1}", "p"), port)
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "panda-free-rigid" if rigid else "panda-free",
        "$comment": (
            "The bare Franka Emika Panda on the spatial multibond mechanics: seven compliant Revolute3D "
            "joints (held directions kt = kr = " + f"{dz.K_HELD:g}" + ") joined by the modified-DH joint "
            "offsets of franka_description, RigidBody3D links at their principal centre-of-mass frames "
            "with the physically feasible Gaz et al. 2019 masses, centres of mass and inertias. No drives, "
            "no friction: zero-torque Se on every joint. Released at rest from q0, the held "
            "directions on the deflections of the released motion's joint loads and swinging under gravity; compared with Pinocchio (design/validate.py)."
        ) + (RIGID_NOTE if rigid else ""),
        "diagram": d.document(),
        "settings": settings("Rodas5P", 1e-8, 1e-10, 1001, dz.T_FREE),
        "plots": [
            {"id": "p1", "title": "Joint angles (free swing)", "signals": [f"L{k}/J/qout" for k in range(1, 8)]},
            {"id": "p2", "title": "Joint rates", "signals": [f"L{k}/J/qdout" for k in range(1, 8)]},
            {"id": "p3", "title": "Flange position", "signals": ["TCP/g[5]", "TCP/g[6]", "TCP/g[7]"]},
        ],
        "scene": {"file": "scenes/panda-free.sdf"},
        "bindings": joint_bindings("") + [pose_binding("link:tcp_actual", "TCP/g")],
    }


# ------------------------------------------------------------------ panda (Robot + firmware)

DRIVE_Y = 760  # first row of the drive band inside Robot


def add_drives(d: Diagram, drives: list[tuple[str, str]], q0) -> None:
    """Per joint: torque limit -> motor (MSe, tau/N) -> rotor (I) -> gear (TF 1/N) -> elastic joint
    (0-junction: spring C + damper R on the relative rate; torque sensor De) -> link-side
    1-junction (Gaz friction R) -> Revolute3D drive. Sensors: encoder (Quantizer), rate, torque."""
    start = dz.drive_start(q0)
    bgear = dz.gear_damping()
    for i, port in enumerate(drives):
        k = i + 1
        x = STAIR_X + STAIR_DX * i
        y = DRIVE_Y
        n = float(pz.N_GEAR[i])
        d.ref(f"sat{k}", f"Limit{k}", "stdlib:continuous/Saturation", x - 160, y,
              params={"lower": fmt(-pz.TAU_MAX[i]), "upper": fmt(pz.TAU_MAX[i])})  # fmt: skip
        d.ref(f"mot{k}", f"Motor{k}", "stdlib:bondgraph/MSe", x - 40, y, params={"gain": fmt(1.0 / n)})
        d.junction(f"jm{k}", f"Rotor{k}J", "1", x + 60, y)
        d.ref(f"rot{k}", f"Rotor{k}", "project:RotorInertia", x + 60, y + 100, params={"i": fmt(pz.J_ROTOR[i])})
        d.ref(f"gear{k}", f"Gear{k}", "stdlib:bondgraph/TF", x + 160, y, params={"n": fmt(1.0 / n)})
        d.junction(f"s0{k}", f"Joint{k}0", "0", x + 260, y)
        d.junction(f"js{k}", f"Elastic{k}", "1", x + 260, y + 100)
        d.ref(f"cg{k}", f"Spring{k}", "stdlib:bondgraph/C", x + 200, y + 200,
              params={"c": fmt(1.0 / pz.K_GEAR[i])}, starts={"q": fmt(start["spring"][i])})  # fmt: skip
        d.ref(f"rg{k}", f"Damper{k}", "stdlib:bondgraph/R", x + 320, y + 200, params={"r": fmt(bgear[i])})
        d.ref(f"tq{k}", f"TauSense{k}", "stdlib:bondgraph/De", x + 260, y - 100)
        d.junction(f"jl{k}", f"Link{k}J", "1", x + 360, y)
        d.ref(f"fr{k}", f"Friction{k}", "project:GazFriction", x + 360, y + 100,
              params={"phi1": fmt(pz.PHI1[i]), "phi2": fmt(pz.PHI2[i]), "phi3": fmt(pz.PHI3[i])})  # fmt: skip
        d.ref(f"enc{k}", f"Encoder{k}", "stdlib:discrete/Quantizer", x + 120, y - 200,
              params={"resolution": fmt(pz.ENCODER_RES)}, constants={"sample_period": fmt(dz.TS)})  # fmt: skip
        d.connect("signal", (f"sat{k}", "y"), (f"mot{k}", "u"))
        d.connect("bond", (f"mot{k}", "p"), (f"jm{k}", None))
        d.connect("bond", (f"jm{k}", None), (f"rot{k}", "p"))
        d.connect("bond", (f"jm{k}", None), (f"gear{k}", "p1"))
        d.connect("bond", (f"gear{k}", "p2"), (f"s0{k}", None))
        d.connect("bond", (f"s0{k}", None), (f"js{k}", None))
        d.connect("bond", (f"js{k}", None), (f"cg{k}", "p"))
        d.connect("bond", (f"js{k}", None), (f"rg{k}", "p"))
        d.connect("bond", (f"s0{k}", None), (f"tq{k}", "p"))
        d.connect("bond", (f"s0{k}", None), (f"jl{k}", None))
        d.connect("bond", (f"jl{k}", None), (f"fr{k}", "p"))
        d.connect("bond", (f"jl{k}", None), port)
        d.connect("signal", (f"l{k}", "q"), (f"enc{k}", "u"))
        d.signal_port(f"tau{k}", "input", f"sat{k}", "u", "N*m")
        d.signal_port(f"q{k}", "output", f"enc{k}", "y", "rad")
        d.signal_port(f"dq{k}", "output", f"l{k}", "qd", "rad/s")
        d.signal_port(f"tauJ{k}", "output", f"tq{k}", "y", "N*m")


def build_robot(rigid: bool = False) -> dict:
    d = Diagram()
    drives = add_chain(d, pz.Q_READY, dz.K_HELD, rigid=rigid)
    add_drives(d, drives, pz.Q_READY)
    # the subsystem ports: inputs first, then the three sensor groups
    order = {"tau": 0, "q": 1, "dq": 2, "tauJ": 3}
    d.ports.sort(key=lambda p: (order[p["name"].rstrip("1234567")], p["name"]))
    return {"ports": d.ports, "diagram": d.document()}


def build_panda(rigid: bool = False) -> dict:
    d = Diagram()
    d.node("robot", "Robot", {"subsystem": build_robot(rigid)}, 900, 300)
    d.ref("clock", "Clock", "stdlib:sources/Time", 40, 120)
    d.ref("traj", "Traj", "project:PandaTrajectory", 160, 120)
    d.ref("ik", "IK", "project:PandaIK", 380, 160)
    d.ref("pd", "PD", "project:PandaPD", 620, 300)
    d.connect("signal", ("clock", "y"), ("traj", "tm"))
    d.connect("signal", ("traj", "g"), ("ik", "g"))
    for k in range(1, 8):
        if k <= 6:
            d.connect("signal", ("robot", f"q{k}"), ("ik", f"q{k}"))
        d.connect("signal", ("ik", f"qr{k}"), ("pd", f"qr{k}"))
        d.connect("signal", ("robot", f"q{k}"), ("pd", f"q{k}"))
        d.connect("signal", ("robot", f"dq{k}"), ("pd", f"dq{k}"))
        d.connect("signal", ("pd", f"u{k}"), ("robot", f"tau{k}"))
    joints = [f"Robot/L{k}/J/qout" for k in range(1, 8)]
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "panda-rigid" if rigid else "panda",
        "$comment": (
            "Franka Emika Panda, two layers. Robot (subsystem, signal ports only): the spatial multibond "
            "arm of panda-free (Gaz et al. 2019 feasible parameters) at the ready pose, and per joint a "
            "bond-graph drive: torque limit (87/12 N m), motor torque source tau/N, rotor inertia J_m (I), "
            "gear N = 100 (TF), elastic joint (C, R) with a torque sensor (De) on its 0-junction, Gaz "
            "friction (nonlinear R) on the link side, a 20-bit link-side encoder (Quantizer, 1 ms) and the "
            "joint rate; drive values other than the torque limits are assumptions (README). Firmware "
            "(1 kHz): PandaTrajectory (Cartesian flange waypoints, quintic rest-to-rest) -> PandaIK "
            "(He & Liu 2021 analytical IK, q7 fixed, branch from the measured q, holds the last solution "
            "and raises flag) -> PandaPD (PD + Gaz gravity and friction feedforward, torque limits)."
        ) + (RIGID_NOTE if rigid else ""),
        "diagram": d.document(),
        "settings": settings("Rodas5P", 1e-6, 1e-8, 1031, dz.T_END),
        "plots": [
            {"id": "p1", "title": "Joint angles", "signals": joints},
            {"id": "p2", "title": "Flange position: target and measured",
             "signals": ["Traj/px", "Traj/py", "Traj/pz", "Robot/TCP/g[5]", "Robot/TCP/g[6]", "Robot/TCP/g[7]"]},
            {"id": "p3", "title": "Measured joint torques tau_J", "signals": [f"Robot/TauSense{k}/y" for k in range(1, 8)]},
            {"id": "p4", "title": "Joint tracking errors", "signals": [f"PD/e{k}" for k in range(1, 8)]},
            {"id": "p5", "title": "Torque commands", "signals": [f"PD/u{k}" for k in range(1, 8)]},
            {"id": "p6", "title": "IK flag and segment", "signals": ["IK/flag", "Traj/segment"]},
        ],  # fmt: skip
        "scene": SCENE,
        "bindings": joint_bindings("Robot/")
        + [pose_binding("link:tcp_target", "Traj/g"), pose_binding("link:tcp_actual", "Robot/TCP/g")],
    }


# ------------------------------------------------------------------ main


def write(model: dict) -> None:
    path = MODELS / f"{model['name']}.bgmodel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT.parent.parent)}")


def main() -> None:
    write_definitions()
    write(build_free())
    write(build_panda())
    write(build_free(rigid=True))
    write(build_panda(rigid=True))


if __name__ == "__main__":
    main()
