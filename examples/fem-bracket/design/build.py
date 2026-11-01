# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the fem-bracket example: two models, the scene, expected checks.

An aluminium L-bracket (base plate 120 x 40 x 5 mm, upright 40 x 4 x 150 mm) as a FEM flexible
body (`ModalBody3D`), reduced from quadratic tetrahedra by Craig-Bampton with two interfaces:
A, the bolted area of the base plate, and B, the top face of the upright that carries a 0.5 kg
payload (a 40 mm steel cube).

    julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl examples/fem-bracket/design/bracket.fem.json
    uv run examples/fem-bracket/design/build.py

Models:

* `fem-bracket`: the bracket on a turntable (a servo-driven revolute joint) that indexes 90
  degrees and back; the tangential acceleration bends the upright in its thin direction and
  the payload rings at the first bracket mode afterwards. Gravity on.
* `bracket-ringdown`: the same bracket and payload clamped at A, no gravity, the payload
  given a velocity at t = 0. The ring-down frequencies are checked against the full finite
  element model with the payload attached (computed by the reduction tool, in the file's
  `validation.attached`).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = "fem-bracket"
RING = "bracket-ringdown"
MODAL_FILE = "data/bracket.modal.json"
MODAL = json.loads((ROOT / MODAL_FILE).read_text())
NM = MODAL["nm"]
ATT = MODAL["validation"]["attached"]

# payload: 0.5 kg steel cube, 40 mm, its centre 20 mm above interface B
M_PAY, A_PAY = 0.5, 0.04
J_PAY = M_PAY * A_PAY**2 / 6
COM_PAY = 0.02
# hub: steel disk r 80 mm, 20 mm thick, its centre on the joint axis
R_HUB, T_HUB, RHO_ST = 0.08, 0.02, 7850.0
M_HUB = RHO_ST * math.pi * R_HUB**2 * T_HUB
J_HUB = [M_HUB * (3 * R_HUB**2 + T_HUB**2) / 12] * 2 + [M_HUB * R_HUB**2 / 2]
# bracket interface A (in the part spec) sits on the hub top, on the axis
SEAT_Z = T_HUB / 2
# turntable servo: speed source through a stiff spring and damper on the joint drive
J_TABLE = J_HUB[2] + 0.0006 + M_PAY * 0.08**2
K_SERVO = 2000.0
D_SERVO = 2 * 0.7 * math.sqrt(K_SERVO * J_TABLE)
# index moves: +90 degrees at 0.2 s, back at 1.6 s
MOVE = dict(v_max=8.0, a_max=80.0, j_max=4000.0)
T_END = 3.0
ZETA = 0.01
# compliant table joint and clamp
KT, KR = 1.0e8, 1.0e5
K_CLAMP, B_CLAMP = 1.0e9, 1.0e3


def fmt(x: float) -> str:
    return repr(float(x))


def vec(xs) -> str:
    return "[" + ", ".join(fmt(x) for x in xs) + "]"


def node(nid, name, ref, x, y, params=None, constants=None, starts=None):
    return {
        "id": nid,
        "name": name,
        "block": {"ref": f"stdlib:{ref}"},
        "position": {"x": x, "y": y},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": constants or {},
        "starts": starts or {},
        "ui": {"showLabel": True, "color": None},
    }


def conn(cid, kind, a, ap, b, bp):
    return {"id": cid, "kind": kind, "from": {"node": a, "port": ap}, "to": {"node": b, "port": bp},
            "route": [], "label": None}


def pose(link, sig):
    return {"target": f"link:{link}", "property": "pose", "signal": [f"{sig}[{i}]" for i in range(1, 8)]}


def mode_shapes():
    return {"target": "visual:bracket_mesh", "property": "mode-shapes",
            "signal": [f"Bracket/eta[{i}]" for i in range(1, NM + 1)]}


def settings(t_end, points):
    return {"t_start": 0.0, "t_end": t_end, "solver": "Rodas5P", "reltol": 1e-07, "abstol": 1e-10,
            "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 10000}


def doc(name, nodes, conns, bindings, plots, t_end, points):
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "diagram": {"nodes": nodes, "connections": conns, "subsystemPorts": [], "annotations": []},
        "settings": settings(t_end, points),
        "plots": plots,
        "scene": {"file": f"scenes/{name}.sdf"},
        "bindings": bindings,
    }


def turntable() -> dict:
    s2 = math.sqrt(0.5)
    del s2
    nodes = [
        node("n1", "World", "multibond/GroundSpatial", 40, 300),
        node("n2", "Table", "spatial/Revolute3D", 220, 300,
             {"kt": fmt(KT), "kr": fmt(KR), "bt": fmt(2 * 0.05 * math.sqrt(KT * M_HUB)),
              "br": fmt(2 * 0.05 * math.sqrt(KR * J_HUB[0]))}),
        node("n3", "Hub", "spatial/RigidBody3D", 400, 300, {"m": fmt(M_HUB), "J": vec(J_HUB)}),
        node("n4", "Seat", "multibond/FixedTransform3DNeutral", 580, 300, {"z": fmt(SEAT_Z)}),
        node("n5", "Bracket", "spatial/ModalBody3D", 760, 300, {"zeta": fmt(ZETA)}, {"file": MODAL_FILE}),
        node("n6", "Clamp", "multibond/FixedTransform3DNeutral", 940, 300, {"z": fmt(COM_PAY)}),
        node("n7", "Payload", "spatial/RigidBody3D", 1120, 300, {"m": fmt(M_PAY), "J": vec([J_PAY] * 3)}),
        # servo
        node("n10", "MoveOut", "motion/SCurveProfile", 40, 20,
             {"q_start": "0.0", "q_end": fmt(math.pi / 2), "t_start": "0.2",
              "v_max": fmt(MOVE["v_max"]), "a_max": fmt(MOVE["a_max"]), "j_max": fmt(MOVE["j_max"])}),
        node("n11", "MoveBack", "motion/SCurveProfile", 40, 120,
             {"q_start": "0.0", "q_end": fmt(-math.pi / 2), "t_start": "1.6",
              "v_max": fmt(MOVE["v_max"]), "a_max": fmt(MOVE["a_max"]), "j_max": fmt(MOVE["j_max"])}),
        node("n16", "Moves", "continuous/Mux2", 130, 60),
        node("n12", "Speed", "continuous/Sum", 190, 60, {}, {"N": "2"}),
        node("n13", "Servo", "rotation/SpeedSource", 260, 60, {"w": "1.0"}),
        node("n14", "ServoSpring", "rotation/TorsionSpring", 360, 20, {"k": fmt(K_SERVO)}),
        node("n15", "ServoDamper", "rotation/RotationalDamper", 360, 120, {"d": fmt(D_SERVO)}),
        # poses
        node("n20", "Origin", "spatial/LocalPose3D", 220, 480),
        node("n21", "PHub", "multibond/ComposePose3D", 400, 480),
        node("n22", "SeatPose", "spatial/LocalPose3D", 580, 560, {"z": fmt(SEAT_Z)}),
        node("n23", "PBracketA", "multibond/ComposePose3D", 580, 480),
        node("n24", "ClampPose", "spatial/LocalPose3D", 940, 560, {"z": fmt(COM_PAY)}),
        node("n25", "PPayload", "multibond/ComposePose3D", 940, 480),
    ]
    conns = [
        conn("c1", "bond", "n1", "p", "n2", "parent"),
        conn("c2", "bond", "n2", "child", "n3", "p"),
        conn("c3", "bond", "n3", "p", "n4", "a"),
        conn("c4", "bond", "n4", "b", "n5", "A"),
        conn("c5", "bond", "n5", "B", "n6", "a"),
        conn("c6", "bond", "n6", "b", "n7", "p"),
        conn("c10", "signal", "n10", "v", "n16", "u1"),
        conn("c11", "signal", "n11", "v", "n16", "u2"),
        conn("c17", "signal", "n16", "y", "n12", "u"),
        conn("c12", "signal", "n12", "y", "n13", "u"),
        conn("c13", "wire", "n13", "a", "n14", "a"),
        conn("c14", "wire", "n13", "a", "n15", "a"),
        conn("c15", "wire", "n14", "b", "n2", "drive"),
        conn("c16", "wire", "n15", "b", "n2", "drive"),
        conn("c20", "signal", "n20", "g", "n21", "gp"),
        conn("c21", "signal", "n2", "pose", "n21", "gl"),
        conn("c22", "signal", "n21", "g", "n3", "g"),
        conn("c23", "signal", "n21", "g", "n23", "gp"),
        conn("c24", "signal", "n22", "g", "n23", "gl"),
        conn("c25", "signal", "n23", "g", "n5", "gA"),
        conn("c26", "signal", "n5", "poseB", "n25", "gp"),
        conn("c27", "signal", "n24", "g", "n25", "gl"),
        conn("c28", "signal", "n25", "g", "n7", "g"),
    ]
    bindings = [pose("hub", "PHub/g"), pose("bracket", "Bracket/pose"), pose("payload", "PPayload/g"), mode_shapes()]
    plots = [
        {"id": "p1", "title": "Table angle (rad) and speed (rad/s)", "signals": ["Table/qout", "Table/qdout"]},
        {"id": "p2", "title": "Modal coordinates (m)", "signals": [f"Bracket/eta[{i}]" for i in range(1, NM + 1)]},
        {"id": "p3", "title": "Payload twist (body frame)", "signals": [f"Payload/V[{i}]" for i in range(1, 7)]},
        {"id": "p4", "title": "Bracket energies (J)", "signals": ["Bracket/Ek", "Bracket/Ee", "Bracket/Eg"]},
    ]
    return doc(NAME, nodes, conns, bindings, plots, T_END, 6001)


def ringdown() -> dict:
    # the payload starts moving: 0.1 m/s along y (the upright's thin direction) and 0.05 m/s
    # along x, so both bending directions ring
    p0 = [0.0, 0.0, 0.0, 0.05 * M_PAY, 0.1 * M_PAY, 0.0]
    nodes = [
        node("n1", "Clamp", "multibond/CSpatial", 220, 300,
             {k: fmt(K_CLAMP) for k in ("krx", "kry", "krz", "kx", "ky", "kz")}),
        node("n2", "ClampDamping", "multibond/RSpatial", 220, 420,
             {k: fmt(B_CLAMP) for k in ("brx", "bry", "brz", "bx", "by", "bz")}),
        node("n3", "Bracket", "spatial/ModalBody3D", 400, 300, {"zeta": "0.0", "g0": "0.0"}, {"file": MODAL_FILE}),
        node("n4", "PayloadMount", "multibond/FixedTransform3DNeutral", 580, 300, {"z": fmt(COM_PAY)}),
        node("n5", "Payload", "spatial/RigidBody3D", 760, 300,
             {"m": fmt(M_PAY), "J": vec([J_PAY] * 3), "g0": "0.0"}, starts={"P": vec(p0)}),
        node("n20", "Origin", "spatial/LocalPose3D", 400, 480),
        node("n21", "PayloadPose", "spatial/LocalPose3D", 580, 560, {"z": fmt(COM_PAY)}),
        node("n22", "PPayload", "multibond/ComposePose3D", 760, 480),
    ]
    conns = [
        conn("c1", "bond", "n3", "A", "n1", "p"),
        conn("c2", "bond", "n3", "A", "n2", "p"),
        conn("c3", "bond", "n3", "B", "n4", "a"),
        conn("c4", "bond", "n4", "b", "n5", "p"),
        conn("c5", "signal", "n20", "g", "n3", "gA"),
        conn("c6", "signal", "n3", "poseB", "n22", "gp"),
        conn("c7", "signal", "n21", "g", "n22", "gl"),
        conn("c8", "signal", "n22", "g", "n5", "g"),
    ]
    bindings = [pose("bracket", "Bracket/pose"), pose("payload", "PPayload/g"), mode_shapes()]
    plots = [
        {"id": "p1", "title": "Modal coordinates (m)", "signals": [f"Bracket/eta[{i}]" for i in range(1, NM + 1)]},
        {"id": "p2", "title": "Payload velocity (m/s, body frame)", "signals": ["Payload/V[4]", "Payload/V[5]", "Payload/V[6]"]},
        {"id": "p3", "title": "Energy (J)", "signals": ["Bracket/Ek", "Bracket/Ee"]},
    ]
    return doc(RING, nodes, conns, bindings, plots, 1.0, 20001)


def scene(name: str, turntable_scene: bool) -> str:
    hub = f"""
    <link name="hub">
      <pose>0 0 0 0 0 0</pose>
      <visual name="hub_disk">
        <geometry><cylinder><radius>{R_HUB}</radius><length>{T_HUB}</length></cylinder></geometry>
        <material><diffuse>0.25 0.5 0.85 1</diffuse></material>
      </visual>
      <visual name="hub_mark">
        <pose>{-R_HUB + 0.012} 0 {T_HUB / 2 + 0.001} 0 0 0</pose>
        <geometry><box><size>0.02 0.01 0.002</size></box></geometry>
        <material><diffuse>0.95 0.95 0.95 1</diffuse></material>
      </visual>
    </link>
""" if turntable_scene else ""
    base = f"""
      <visual name="table_base">
        <pose>0 0 {-T_HUB / 2 - 0.03} 0 0 0</pose>
        <geometry><cylinder><radius>0.06</radius><length>0.04</length></cylinder></geometry>
        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>
      </visual>""" if turntable_scene else f"""
      <visual name="clamp_block">
        <pose>0.02 0 -0.01 0 0 0</pose>
        <geometry><box><size>0.05 0.05 0.02</size></box></geometry>
        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>
      </visual>"""
    a_z = SEAT_Z if turntable_scene else 0.0
    return f"""<?xml version="1.0"?>
<!--
  {name}: an aluminium L-bracket (a FEM flexible body, ModalBody3D) with a 0.5 kg payload.

  Z-up, metres. The bracket link follows Bracket/pose, the world pose of its reference frame
  (interface A, the bolted area of the base plate). Its visual `bracket_mesh` is the GLB the
  reduction wrote (meshes/bracket.glb, in that frame, one morph target per mode), deformed by a
  mode-shapes binding with Bracket/eta[1..{NM}]. The payload follows PPayload/g (interface B,
  deformed, composed with the 20 mm offset to the cube's centre).
-->
<sdf version="1.9">
  <model name="{name.replace('-', '_')}">
    <link name="frame">
      <pose>0 0 0 0 0 0</pose>{base}
      <visual name="floor">
        <pose>0 0 {-T_HUB / 2 - 0.055 if turntable_scene else -0.025} 0 0 0</pose>
        <geometry><box><size>0.6 0.6 0.01</size></box></geometry>
        <material><diffuse>0.55 0.57 0.6 1</diffuse></material>
      </visual>
    </link>
{hub}
    <link name="bracket">
      <pose>0 0 {a_z} 0 0 0</pose>
      <visual name="bracket_mesh">
        <geometry><mesh><uri>meshes/bracket.glb</uri></mesh></geometry>
      </visual>
    </link>

    <link name="payload">
      <pose>0.08 0 {a_z + 0.155 + COM_PAY} 0 0 0</pose>
      <visual name="payload_cube">
        <geometry><box><size>{A_PAY} {A_PAY} {A_PAY}</size></box></geometry>
        <material><diffuse>0.9 0.55 0.1 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""


def expected() -> dict:
    full = ATT["full_hz"]
    red = ATT["reduced_hz"]
    note = (f"full finite element model ({MODAL['mesh']['dofs']} dofs) clamped at A with the payload "
            f"at B: {full[0]:.4f} / {full[1]:.4f} Hz; reduced model {red[0]:.4f} / {red[1]:.4f} Hz")
    return {
        "project": NAME,
        "description": "An aluminium L-bracket as a FEM flexible body (ModalBody3D, Craig-Bampton 4 + 6 modes) carrying a 0.5 kg payload: on an indexing turntable, and clamped for a ring-down whose frequencies match the full finite element model with the payload attached.",
        "models": {
            NAME: {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "E108", "W201", "W202"]},
                    {"kind": "scene_bindings"},
                    {"kind": "final_value", "signal": "Table/qout", "t": T_END, "value": 0.0, "atol": 0.01,
                     "note": "the table is back at 0 after the two index moves"},
                    {"kind": "max_abs", "signal": "Table/qout", "from_t": 0.0, "to_t": T_END,
                     "value": math.pi / 2, "rtol": 0.02, "note": "the first move reaches 90 degrees"},
                    {"kind": "fft_peak", "signal": "Payload/V[1]", "from_t": 1.0, "to_t": 1.6,
                     "min_hz": 8.0, "max_hz": 40.0, "value": full[0], "rtol": 0.06,
                     "note": "the payload rings near the first clamped bracket mode after the move (the servo spring lowers it slightly); " + note},
                ]
            },
            RING: {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "E108", "W201", "W202"]},
                    {"kind": "scene_bindings"},
                    {"kind": "fft_peak", "signal": "Payload/V[5]", "from_t": 0.0, "to_t": 1.0,
                     "min_hz": 5.0, "max_hz": 25.0, "value": full[0], "rtol": 0.003, "note": note},
                    {"kind": "fft_peak", "signal": "Payload/V[4]", "from_t": 0.0, "to_t": 1.0,
                     "min_hz": 25.0, "max_hz": 60.0, "value": full[1], "rtol": 0.003, "note": note},
                ]
            },
        },
    }


def main() -> None:
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    (ROOT / "scenes").mkdir(parents=True, exist_ok=True)
    for name, d, turn in ((NAME, turntable(), True), (RING, ringdown(), False)):
        with open(ROOT / "models" / f"{name}.bgmodel.json", "w", newline="\n") as f:
            json.dump(d, f, indent=2)
            f.write("\n")
        with open(ROOT / "scenes" / f"{name}.sdf", "w", newline="\n") as f:
            f.write(scene(name, turn))
    with open(ROOT / "expected.json", "w", newline="\n") as f:
        json.dump(expected(), f, indent=2)
        f.write("\n")
    with open(ROOT / "bgsim.project.json", "w", newline="\n") as f:
        json.dump({"format": "bgsim.project", "language": "0.1.0", "name": NAME, "models": [NAME, RING],
                   "libraryDir": "library", "scenesDir": "scenes"}, f, indent=2)
        f.write("\n")
    print(f"bracket: nm {NM}, mass {MODAL['mass']:.4f} kg; payload {M_PAY} kg, J {J_PAY:.4e}")
    print(f"clamped with payload: full {ATT['full_hz']} Hz, reduced {ATT['reduced_hz']} Hz")
    print(f"hub m {M_HUB:.3f} kg, table inertia {J_TABLE:.4f}, servo k {K_SERVO}, d {D_SERVO:.3f}, "
          f"servo frequency {math.sqrt(K_SERVO / J_TABLE) / 2 / math.pi:.1f} Hz")


if __name__ == "__main__":
    main()
