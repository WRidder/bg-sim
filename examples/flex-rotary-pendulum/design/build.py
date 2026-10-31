# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the flex-rotary-pendulum example: two models, a scene and the checks.

A Furuta (rotary) pendulum whose pendulum rod is a FlexibleBeam3D (two bending modes per
plane, clamped-free at the pivot): a horizontal arm turns about the vertical axis on a motor
bearing, and the rod hangs from a pivot at the arm tip that swings in the plane perpendicular
to the arm. The rod is released from 90 degrees with the motor free; at t = 3 s a motor
torque pulse kicks the arm. Model `flex-rotary-pendulum-rigid` is the same rig with the rod
as a RigidBody3D of the same mass and inertia, the reference of the swing.

    uv run examples/flex-rotary-pendulum/design/build.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = "flex-rotary-pendulum"
RIGID = NAME + "-rigid"

S2 = math.sqrt(0.5)
# arm (aluminium bar 20 x 10 mm, 0.2 m from the motor axis to the pivot)
ARM_L, ARM_W, ARM_H = 0.2, 0.02, 0.01
ARM_M = 2700.0 * ARM_L * ARM_W * ARM_H
ARM_J = (ARM_M * (ARM_W**2 + ARM_H**2) / 12, ARM_M * (ARM_L**2 + ARM_H**2) / 12, ARM_M * (ARM_L**2 + ARM_W**2) / 12)
# rod (aluminium, d = 5 mm, 0.5 m)
ROD_L, ROD_D, RHO, E, NU = 0.5, 0.005, 2700.0, 70.0e9, 0.33
ROD_M = RHO * math.pi * ROD_D**2 / 4 * ROD_L
ROD_I = math.pi * ROD_D**4 / 64
NB = 2  # bending modes per plane
ZETA = 0.01
Q0 = math.pi / 2  # release angle of the pendulum
T_KICK, T_PULSE, TAU = 3.0, 0.05, 0.4
T_END = 6.0
KT, KR = 1.0e7, 1.0e5


def fmt(x: float) -> str:
    return repr(float(x))


def vec(v) -> str:
    return "[" + ", ".join(fmt(x) for x in v) + "]"


def node(nid, name, ref, x, y, params=None, constants=None):
    return {
        "id": nid,
        "name": name,
        "block": {"ref": f"stdlib:{ref}"},
        "position": {"x": x, "y": y},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": constants or {},
        "starts": {},
        "ui": {"showLabel": True, "color": None},
    }


def conn(cid, kind, a, ap, b, bp):
    return {"id": cid, "kind": kind, "from": {"node": a, "port": ap}, "to": {"node": b, "port": bp},
            "route": [], "label": None}


def pose_params(q, p):
    return {"qw": fmt(q[0]), "qx": fmt(q[1]), "qy": fmt(q[2]), "qz": fmt(q[3]),
            "x": fmt(p[0]), "y": fmt(p[1]), "z": fmt(p[2])}


def joint_params(m, extra=None):
    out = {"kt": fmt(KT), "kr": fmt(KR), "bt": fmt(2 * 0.05 * math.sqrt(KT * m)), "br": fmt(2 * 0.05 * math.sqrt(KR * 1e-3))}
    out.update(extra or {})
    return out


def model(flexible: bool) -> dict:
    QY90 = (S2, 0.0, S2, 0.0)
    QYM90 = (S2, 0.0, -S2, 0.0)
    nodes = [
        node("n1", "World", "multibond/GroundSpatial", 40, 300),
        node("n2", "Motor", "spatial/Revolute3D", 220, 300, joint_params(ARM_M)),
        node("n3", "ArmLink", "multibond/FixedTransform3DNeutral", 400, 300, pose_params((1, 0, 0, 0), (ARM_L / 2, 0, 0))),
        node("n4", "Arm", "spatial/RigidBody3D", 580, 300, {"m": fmt(ARM_M), "J": vec(ARM_J)}),
        # pivot frame in the arm centre-of-mass frame: Ry(90) (z along the arm), at the tip; the
        # mount carries its inverse (the body on `b`, the joint on `a`)
        node("n5", "PivotMount", "multibond/FixedTransform3DNeutral", 760, 300, pose_params(QYM90, (0, 0, -ARM_L / 2))),
        node("n6", "Pivot", "spatial/Revolute3D", 940, 300, joint_params(ROD_M, {"q0": fmt(Q0)})),
        node("n9", "Ground", "rotation/FixedShaft", 40, 120),
        node("n10", "Kick", "rotation/TorqueSource", 220, 120, {"T": fmt(TAU)}),
        node("n11", "Pulse", "sources/Pulse", 220, 20,
             {"amplitude": "1.0", "period": "1000.0", "duty": fmt(T_PULSE / 1000.0), "t_start": fmt(T_KICK)}),
        node("n12", "PivotFree", "bondgraph/Se", 940, 120, {"e": "0.0"}),
        node("n20", "Origin", "spatial/LocalPose3D", 220, 480),
        node("n21", "PMotor", "multibond/ComposePose3D", 400, 480),
        node("n22", "ArmCoM", "spatial/LocalPose3D", 400, 560, pose_params((1, 0, 0, 0), (ARM_L / 2, 0, 0))),
        node("n23", "PArm", "multibond/ComposePose3D", 580, 480),
        node("n24", "PivotFrame", "spatial/LocalPose3D", 760, 560, pose_params(QY90, (ARM_L, 0, 0))),
        node("n25", "PPivotFrame", "multibond/ComposePose3D", 760, 480),
        node("n26", "PRod", "multibond/ComposePose3D", 940, 480),
    ]
    conns = [
        conn("c1", "bond", "n1", "p", "n2", "parent"),
        conn("c2", "bond", "n2", "child", "n3", "a"),
        conn("c3", "bond", "n3", "b", "n4", "p"),
        conn("c4", "bond", "n4", "p", "n5", "b"),
        conn("c5", "bond", "n5", "a", "n6", "parent"),
        conn("c8", "wire", "n9", "a", "n10", "a"),
        conn("c9", "wire", "n10", "b", "n2", "drive"),
        conn("c10", "signal", "n11", "y", "n10", "u"),
        conn("c11", "bond", "n12", "p", "n6", "drive"),
        conn("c20", "signal", "n20", "g", "n21", "gp"),
        conn("c21", "signal", "n2", "pose", "n21", "gl"),
        conn("c22", "signal", "n21", "g", "n23", "gp"),
        conn("c23", "signal", "n22", "g", "n23", "gl"),
        conn("c24", "signal", "n23", "g", "n4", "g"),
        conn("c25", "signal", "n21", "g", "n25", "gp"),
        conn("c26", "signal", "n24", "g", "n25", "gl"),
        conn("c27", "signal", "n25", "g", "n26", "gp"),
        conn("c28", "signal", "n6", "pose", "n26", "gl"),
    ]
    if flexible:
        nodes.append(node("n7", "Rod", "spatial/FlexibleBeam3D", 1120, 300,
                          {"L": fmt(ROD_L), "d": fmt(ROD_D), "E": fmt(E), "nu": fmt(NU), "rho": fmt(RHO),
                           "zeta_y": fmt(ZETA), "zeta_z": fmt(ZETA)},
                          {"ny": str(NB), "nz": str(NB), "nt": "0"}))
        conns += [
            conn("c6", "bond", "n6", "child", "n7", "A"),
            conn("c29", "signal", "n26", "g", "n7", "gA"),
        ]
        rod_pose = "Rod/pose"
    else:
        # the same rod as a rigid body: centre of mass at L/2 along the pivot child x
        j_ax = ROD_M * ROD_D**2 / 8
        j_tr = ROD_M * ROD_L**2 / 12 + ROD_M * ROD_D**2 / 16
        nodes += [
            node("n7", "RodLink", "multibond/FixedTransform3DNeutral", 1120, 300, pose_params((1, 0, 0, 0), (ROD_L / 2, 0, 0))),
            node("n8", "Rod", "spatial/RigidBody3D", 1300, 300, {"m": fmt(ROD_M), "J": vec((j_ax, j_tr, j_tr))}),
            node("n27", "RodCoM", "spatial/LocalPose3D", 1120, 560, pose_params((1, 0, 0, 0), (ROD_L / 2, 0, 0))),
            node("n28", "PRodCoM", "multibond/ComposePose3D", 1120, 480),
        ]
        conns += [
            conn("c6", "bond", "n6", "child", "n7", "a"),
            conn("c7", "bond", "n7", "b", "n8", "p"),
            conn("c29", "signal", "n26", "g", "n28", "gp"),
            conn("c30", "signal", "n27", "g", "n28", "gl"),
            conn("c31", "signal", "n28", "g", "n8", "g"),
        ]
        rod_pose = "PRod/g"

    def pose(link, sig):
        return {"target": f"link:{link}", "property": "pose", "signal": [f"{sig}[{i}]" for i in range(1, 8)]}

    bindings = [pose("arm", "PArm/g"), pose("rod", rod_pose)]
    plots = [
        {"id": "p1", "title": "Pendulum angle and arm angle (rad)", "signals": ["Pivot/qout", "Motor/qout"]},
    ]
    if flexible:
        for fam, ax in (("bending-y", "y"), ("bending-z", "z")):
            bindings.append({
                "target": "visual:rod_bar",
                "property": "deformation",
                "family": fam,
                "basis": "clamped-free",
                "beam": {"axis": "+z", "y": "+y", "length": ROD_L},
                "signal": [f"Rod/eta_{ax}[{i}]" for i in range(1, NB + 1)],
            })
        plots += [
            {"id": "p2", "title": "Bending in the swing plane, eta_y (m)", "signals": [f"Rod/eta_y[{i}]" for i in range(1, NB + 1)]},
            {"id": "p3", "title": "Bending across the swing plane, eta_z (m)", "signals": [f"Rod/eta_z[{i}]" for i in range(1, NB + 1)]},
            {"id": "p4", "title": "Rod energy: kinetic, strain, gravity (J)", "signals": ["Rod/Ek", "Rod/Ee", "Rod/Eg"]},
        ]
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": NAME if flexible else RIGID,
        "diagram": {"nodes": nodes, "connections": conns, "subsystemPorts": [], "annotations": []},
        "settings": {
            "t_start": 0.0,
            "t_end": T_END,
            "solver": "Rodas5P",
            "reltol": 1e-08,
            "abstol": 1e-10,
            "max_step": None,
            "output": {"mode": "points", "points": 6001},
            "event_limit": 10000,
        },
        "plots": plots,
        "scene": {"file": f"scenes/{NAME}.sdf"},
        "bindings": bindings,
    }


def scene() -> str:
    rod_r = 0.006  # drawn thicker than the 5 mm rod
    return f"""<?xml version="1.0"?>
<!--
  flex-rotary-pendulum: a Furuta pendulum with a flexible rod.

  Z-up, metres, the world frame of the model. The motor axis is world z through the origin;
  the arm runs along its local x to the pivot at x = {ARM_L:g} m; the pivot axis is the arm
  axis and the rod hangs along the pivot frame's local x (world -z at rest).

    arm   PArm/g     the arm's centre-of-mass frame
    rod   Rod/pose   the rod's reference frame: end A at the pivot, x along the rod
                     (rigid model: PRod/g, the same frame)

  The rod visual `rod_bar` (beam axis = the cylinder's +z, beam y = +y) is deformed by
  Rod/eta_y[1..{NB}] (bending in the swing plane) and Rod/eta_z[1..{NB}] (across it),
  clamped-free basis. The scene starts at the release pose (pendulum at 90 degrees).
-->
<sdf version="1.9">
  <model name="flex_rotary_pendulum">
    <link name="base">
      <pose>0 0 0 0 0 0</pose>
      <visual name="motor_housing">
        <pose>0 0 -0.06 0 0 0</pose>
        <geometry><cylinder><radius>0.035</radius><length>0.1</length></cylinder></geometry>
        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>
      </visual>
      <visual name="column">
        <pose>0 0 -0.36 0 0 0</pose>
        <geometry><cylinder><radius>0.02</radius><length>0.5</length></cylinder></geometry>
        <material><diffuse>0.45 0.47 0.5 1</diffuse></material>
      </visual>
      <visual name="floor">
        <pose>0 0 -0.62 0 0 0</pose>
        <geometry><box><size>1.4 1.4 0.02</size></box></geometry>
        <material><diffuse>0.55 0.57 0.6 1</diffuse></material>
      </visual>
    </link>

    <link name="arm">
      <pose>{ARM_L / 2} 0 0 0 0 0</pose>
      <visual name="arm_bar">
        <geometry><box><size>{ARM_L + 0.02} {ARM_W} {ARM_H}</size></box></geometry>
        <material><diffuse>0.25 0.5 0.85 1</diffuse></material>
      </visual>
      <visual name="pivot_hub">
        <pose>{ARM_L / 2} 0 0 0 1.570796 0</pose>
        <geometry><cylinder><radius>0.012</radius><length>0.03</length></cylinder></geometry>
        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>
      </visual>
    </link>

    <link name="rod">
      <!-- released at 90 degrees: the rod points along world -y... the pose binding sets it -->
      <pose>{ARM_L} 0 0 0 1.570796 0</pose>
      <visual name="rod_bar">
        <pose>{ROD_L / 2} 0 0 0 1.570796 0</pose>
        <geometry><cylinder><radius>{rod_r}</radius><length>{ROD_L}</length></cylinder></geometry>
        <material><diffuse>0.9 0.55 0.1 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""


def expected() -> dict:
    return {
        "project": NAME,
        "description": "Furuta pendulum with a flexible rod (FlexibleBeam3D, 2 + 2 bending modes): power continuity of the whole graph, a visible bending, and the swing against the rigid-rod model.",
        "models": {
            NAME: {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "W201", "W202"]},
                    {"kind": "scene_bindings"},
                    {"kind": "energy_ledger", "tol": 1e-6},
                    {"kind": "max_abs", "signal": "Rod/eta_y[1]", "from_t": 0.0, "to_t": T_END, "value": 1e-3,
                     "rtol": 0.9, "note": "a bending of the order of a millimetre (modal coordinate)"},
                ]
            },
            RIGID: {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "W202"]},
                    {"kind": "scene_bindings"},
                ]
            },
        },
        "compare": [
            {"a": NAME, "b": RIGID, "signal_a": "Pivot/qout", "signal_b": "Pivot/qout",
             "from_t": 0.0, "to_t": 1.5, "max_abs": 0.05,
             "note": "the flexible rod swings like the rigid one (same mass and inertia) over the first swings"},
        ],
    }


def main() -> None:
    for d in ("models", "scenes"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    for flexible in (True, False):
        m = model(flexible)
        with open(ROOT / "models" / f"{m['name']}.bgmodel.json", "w", newline="\n") as f:
            json.dump(m, f, indent=2)
            f.write("\n")
    with open(ROOT / "scenes" / f"{NAME}.sdf", "w", newline="\n") as f:
        f.write(scene())
    with open(ROOT / "expected.json", "w", newline="\n") as f:
        json.dump(expected(), f, indent=2)
        f.write("\n")
    with open(ROOT / "bgsim.project.json", "w", newline="\n") as f:
        json.dump({"format": "bgsim.project", "language": "0.1.0", "name": NAME, "models": [NAME, RIGID],
                   "libraryDir": "library", "scenesDir": "scenes"}, f, indent=2)
        f.write("\n")
    lam = 1.87510407
    f1 = lam**2 / (2 * math.pi) * math.sqrt(E * ROD_I / (RHO * math.pi * ROD_D**2 / 4 * ROD_L**4))
    print(f"arm m {ARM_M:.4f} kg, rod m {ROD_M:.4f} kg, rod clamped-free f1 {f1:.3f} Hz")


if __name__ == "__main__":
    main()
