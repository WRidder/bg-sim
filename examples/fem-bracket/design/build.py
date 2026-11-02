# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
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

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = "fem-bracket"
RING = "bracket-ringdown"
MODAL_FILE = "data/bracket.modal.json"
MODAL = json.loads((ROOT / MODAL_FILE).read_text())
NM = MODAL["nm"]
ATT = MODAL["validation"]["attached"]
M_BRACKET = MODAL["mass"]
J_BRACKET_A = MODAL["inertia"][0][0]   # about interface A (x axis), for the weld damping

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
# compliant table joint
KT, KR = 1.0e8, 1.0e5
# (the clamp of the ring-down: about 10 000 times stiffer than the bracket at A, damped)
K_CLAMP_R, K_CLAMP_T, B_CLAMP_R, B_CLAMP_T = 1.0e6, 1.0e8, 2.0, 500.0
# welds: the bolted joints hub-bracket (A) and bracket-payload (B). Two bodies with their own
# momenta cannot be joined rigidly (derivative causality), so each joint is a stiff Revolute3D
# about z whose rotation is held by a stiff torsion spring: about 1000 times stiffer than the
# bracket at that interface.
KT_W, KR_W, KW = 1.0e8, 1.0e5, 1.0e5
# stress view range (Pa) and the material's allowable (6082-T6 aluminium, yield 250 MPa)
STRESS_RANGE = 20.0e6
YIELD = 250.0e6
STRESS = MODAL["stress"]


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
    # coloured by von Mises from the GLB's per-vertex stress table
    return {"target": "visual:bracket_mesh", "property": "mode-shapes",
            "signal": [f"Bracket/eta[{i}]" for i in range(1, NM + 1)],
            "stress": {"colormap": "heat", "range": [0.0, STRESS_RANGE]}}


def stress_plot(pid):
    return {"id": pid, "title": "Bracket von Mises stress (Pa): upright 30 mm, upright root, peak",
            "signals": ["Bracket/sigma_vm[1]", "Bracket/sigma_vm[2]", "Bracket/sigma_max"]}


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
        # the deflections are a fraction of a millimetre: the view opens at x100 (marked exaggerated)
        "scene": {"file": f"scenes/{name}.sdf", "exaggeration": 100},
        "bindings": bindings,
    }


def weld(prefix: str, x: int, y: int, mass: float, inertia: float) -> tuple[list, list]:
    """A stiff weld: Revolute3D `<prefix>` held about z by a torsion spring to a fixed shaft.
    Returns the nodes and the two wires; the caller connects parent, child and pose."""
    nodes = [
        node(prefix, prefix, "spatial/Revolute3D", x, y,
             {"kt": fmt(KT_W), "kr": fmt(KR_W), "bt": fmt(2 * 0.05 * math.sqrt(KT_W * mass)),
              "br": fmt(2 * 0.05 * math.sqrt(KR_W * inertia))}),
        node(f"{prefix}Ground", f"{prefix}Ground", "rotation/FixedShaft", x, y - 180),
        node(f"{prefix}Spring", f"{prefix}Spring", "rotation/TorsionSpring", x, y - 90, {"k": fmt(KW)}),
    ]
    conns = [
        conn(f"w{prefix}1", "wire", f"{prefix}Ground", "a", f"{prefix}Spring", "a"),
        conn(f"w{prefix}2", "wire", f"{prefix}Spring", "b", prefix, "drive"),
    ]
    return nodes, conns


def payload_chain(bracket: str, x0: int, y_pose: int) -> tuple[list, list]:
    """Bracket B -> WeldB -> Offset (20 mm up) -> Payload, and the payload's pose chain."""
    wn, wc = weld("WeldB", x0, 300, M_PAY, J_PAY)
    nodes = wn + [
        node("n6", "Offset", "multibond/FixedTransform3DNeutral", x0 + 180, 300, {"z": fmt(COM_PAY)}),
        node("n7", "Payload", "spatial/RigidBody3D", x0 + 360, 300,
             {"m": fmt(M_PAY), "J": vec([J_PAY] * 3)}),
        node("n26", "PWeldB", "multibond/ComposePose3D", x0, y_pose),
        node("n24", "OffsetPose", "spatial/LocalPose3D", x0 + 180, y_pose + 80, {"z": fmt(COM_PAY)}),
        node("n25", "PPayload", "multibond/ComposePose3D", x0 + 180, y_pose),
    ]
    conns = wc + [
        # bonds point into the body they load (joint.parent -> body, as in the library examples)
        conn("c5", "bond", "WeldB", "parent", bracket, "B"),
        conn("c5b", "bond", "WeldB", "child", "n6", "a"),
        conn("c6", "bond", "n6", "b", "n7", "p"),
        conn("c26", "signal", bracket, "poseB", "n26", "gp"),
        conn("c26b", "signal", "WeldB", "pose", "n26", "gl"),
        conn("c27", "signal", "n26", "g", "n25", "gp"),
        conn("c27b", "signal", "n24", "g", "n25", "gl"),
        conn("c28", "signal", "n25", "g", "n7", "g"),
    ]
    return nodes, conns


def turntable() -> dict:
    wa_nodes, wa_conns = weld("WeldA", 520, 300, M_BRACKET + M_PAY, J_BRACKET_A)
    pay_nodes, pay_conns = payload_chain("n5", 1000, 480)
    nodes = wa_nodes + pay_nodes + [
        node("n1", "World", "multibond/GroundSpatial", 40, 300),
        node("n2", "Table", "spatial/Revolute3D", 220, 300,
             {"kt": fmt(KT), "kr": fmt(KR), "bt": fmt(2 * 0.05 * math.sqrt(KT * M_HUB)),
              "br": fmt(2 * 0.05 * math.sqrt(KR * J_HUB[0]))}),
        node("n3", "Hub", "spatial/RigidBody3D", 400, 300, {"m": fmt(M_HUB), "J": vec(J_HUB)}),
        node("n4", "Seat", "multibond/FixedTransform3DNeutral", 670, 300, {"z": fmt(SEAT_Z)}),
        node("n5", "Bracket", "spatial/ModalBody3D", 820, 300, {"zeta": fmt(ZETA)}, {"file": MODAL_FILE}),
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
        node("n22", "SeatPose", "spatial/LocalPose3D", 670, 560, {"z": fmt(SEAT_Z)}),
        node("n27", "PWeldA", "multibond/ComposePose3D", 520, 480),
        node("n23", "PBracketA", "multibond/ComposePose3D", 670, 480),
    ]
    conns = wa_conns + pay_conns + [
        conn("c1", "bond", "n1", "p", "n2", "parent"),
        conn("c2", "bond", "n2", "child", "n3", "p"),
        conn("c3", "bond", "WeldA", "parent", "n3", "p"),
        conn("c4", "bond", "WeldA", "child", "n4", "a"),
        conn("c4b", "bond", "n4", "b", "n5", "A"),
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
        conn("c23", "signal", "n21", "g", "n27", "gp"),
        conn("c24", "signal", "WeldA", "pose", "n27", "gl"),
        conn("c24b", "signal", "n27", "g", "n23", "gp"),
        conn("c24c", "signal", "n22", "g", "n23", "gl"),
        conn("c25", "signal", "n23", "g", "n5", "gA"),
    ]
    bindings = [pose("hub", "PHub/g"), pose("bracket", "Bracket/pose"), pose("payload", "PPayload/g"), mode_shapes()]
    plots = [
        {"id": "p1", "title": "Table angle (rad) and speed (rad/s)", "signals": ["Table/qout", "Table/qdout"]},
        {"id": "p2", "title": "Modal coordinates (m)", "signals": [f"Bracket/eta[{i}]" for i in range(1, NM + 1)]},
        {"id": "p3", "title": "Payload twist (body frame)", "signals": [f"Payload/flow/y[{i}]" for i in range(1, 7)]},
        {"id": "p4", "title": "Bracket energies (J)", "signals": ["Bracket/Ek", "Bracket/Ee", "Bracket/Eg"]},
        stress_plot("p5"),
    ]
    return doc(NAME, nodes, conns, bindings, plots, T_END, 6001)


# the ring-down: the payload starts moving, 0.1 m/s along y (the upright's thin direction) and
# 0.05 m/s along x, so both bending directions ring
P0_RING = [0.0, 0.0, 0.0, 0.05 * M_PAY, 0.1 * M_PAY, 0.0]
# the stress checks compare the first swing (30 ms, past the first peak at a quarter period of
# 18.6 Hz): the reference is undamped, while the clamp and the welds damp the higher modes
# (171 Hz and up) that later beat with the first ones
T_FIRST = 0.03


def von_mises(s):
    s = np.asarray(s)
    return np.sqrt(0.5 * ((s[0] - s[1]) ** 2 + (s[1] - s[2]) ** 2 + (s[2] - s[0]) ** 2)
                   + 3.0 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2))


def ringdown_stress_reference(t_end=T_FIRST, n=601):
    """The ring-down's stress from the reduced model alone, by linear modal superposition (no
    BGSim): the bracket clamped at A, the payload rigid at B (its centre 20 mm above), the
    payload's initial momentum shared through the impulse T' p0. Returns the largest von Mises
    at the two hotspots and over all the stress points in [0, t_end], and the first two
    frequencies (Hz)."""
    mk = np.array(MODAL["modal_mass"])
    kk = np.array(MODAL["modal_stiffness"])
    ib = MODAL["interfaces"][1]
    PT, PR = np.array(ib["translation"]), np.array(ib["rotation"])     # B frame = R axes here
    r = np.array([0.0, 0.0, COM_PAY])
    rx = np.array([[0, -r[2], r[1]], [r[2], 0, -r[0]], [-r[1], r[0], 0]])
    T = np.vstack([PR, PT - rx @ PR])                                   # payload twist [w; v_com]
    M6 = np.diag([J_PAY] * 3 + [M_PAY] * 3)
    M = np.diag(mk) + T.T @ M6 @ T
    w2, phi = np.linalg.eig(np.linalg.solve(M, np.diag(kk)))
    w = np.sqrt(w2.real)
    phi = phi.real / np.sqrt(np.einsum("ik,ij,jk->k", phi.real, M, phi.real))
    qd0 = np.linalg.solve(M, T.T @ np.array(P0_RING))
    t = np.linspace(0.0, t_end, n)
    a = (phi.T @ M @ qd0) / w
    q = phi @ (a[:, None] * np.sin(w[:, None] * t[None, :]))           # nm x n
    vm = np.array([von_mises(np.array(p["sigma"]) @ q) for p in STRESS["points"]])
    return float(vm[0].max()), float(vm[1].max()), float(vm.max()), sorted(w / 2 / np.pi)[:2]


REF = ringdown_stress_reference()
# the hand estimate at the 30 mm hotspot: the payload swings at the first mode (y), its peak
# inertia force m w v acts 175 mm above the plate face; sigma_zz = M c / I of the upright
_F_HAND = M_PAY * 2 * math.pi * ATT["full_hz"][0] * 0.1
HAND = {"F": _F_HAND, "szz": _F_HAND * (0.175 - 0.03) * 0.002 / (0.04 * 0.004**3 / 12)}


def ringdown() -> dict:
    p0 = P0_RING
    pay_nodes, pay_conns = payload_chain("n3", 580, 480)
    for n in pay_nodes:
        if n["name"] == "Payload":
            n["params"]["g0"] = "0.0"
            n["starts"] = {"inertia/P": vec(p0)}
    nodes = pay_nodes + [
        node("n1", "Clamp", "multibond/CSpatial", 220, 300,
             {k: fmt(K_CLAMP_R if k.startswith("kr") else K_CLAMP_T) for k in ("krx", "kry", "krz", "kx", "ky", "kz")}),
        node("n2", "ClampDamping", "multibond/RSpatial", 220, 420,
             {k: fmt(B_CLAMP_R if k.startswith("br") else B_CLAMP_T) for k in ("brx", "bry", "brz", "bx", "by", "bz")}),
        node("n3", "Bracket", "spatial/ModalBody3D", 400, 300, {"zeta": "0.0", "g0": "0.0"}, {"file": MODAL_FILE}),
        node("n20", "Origin", "spatial/LocalPose3D", 400, 480),
    ]
    conns = pay_conns + [
        conn("c1", "bond", "n3", "A", "n1", "p"),
        conn("c2", "bond", "n3", "A", "n2", "p"),
        conn("c3", "signal", "n20", "g", "n3", "gA"),
    ]
    bindings = [pose("bracket", "Bracket/pose"), pose("payload", "PPayload/g"), mode_shapes()]
    plots = [
        {"id": "p1", "title": "Modal coordinates (m)", "signals": [f"Bracket/eta[{i}]" for i in range(1, NM + 1)]},
        {"id": "p2", "title": "Payload velocity (m/s, body frame)", "signals": ["Payload/flow/y[4]", "Payload/flow/y[5]", "Payload/flow/y[6]"]},
        {"id": "p3", "title": "Energy (J)", "signals": ["Bracket/Ek", "Bracket/Ee"]},
        stress_plot("p4"),
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
      <pose>0.1 0 {a_z + 0.155 + COM_PAY} 0 0 0</pose>
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
    note_s = (f"linear modal superposition of the reduced model with the payload rigid at B "
              f"(design/build.py, no BGSim), first {T_FIRST * 1e3:.0f} ms: max von Mises {REF[0] / 1e6:.3f} MPa at upright 30 mm, "
              f"{REF[1] / 1e6:.3f} MPa at the root, {REF[2] / 1e6:.3f} MPa over the stress points")
    note_hand = (f"beam theory: F = m w v = {HAND['F']:.2f} N at the payload centre, "
                 f"sigma_zz = F (0.175 - 0.03) c / I = {HAND['szz'] / 1e6:.2f} MPa")
    return {
        "project": NAME,
        "description": "An aluminium L-bracket as a FEM flexible body (ModalBody3D, Craig-Bampton 4 + 6 modes) carrying a 0.5 kg payload: on an indexing turntable, and clamped for a ring-down whose frequencies match the full finite element model with the payload attached.",
        "models": {
            NAME: {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "E108", "W201", "W202"]},
                    {"kind": "scene_bindings"},
                    {"kind": "final_value", "signal": "Table/qout", "t": T_END, "value": 0.0, "abs": 0.01,
                     "note": "the table is back at 0 after the two index moves"},
                    {"kind": "max_abs", "signal": "Table/qout", "from_t": 0.0, "to_t": T_END,
                     "value": math.pi / 2, "rtol": 0.02, "note": "the first move reaches 90 degrees"},
                    {"kind": "fft_peak", "signal": "Payload/flow/y[1]", "from_t": 1.0, "to_t": 1.6,
                     "min_hz": 8.0, "max_hz": 40.0, "value": full[0], "rtol": 0.06,
                     "note": "the payload rings near the first clamped bracket mode after the move (the servo spring lowers it slightly); " + note},
                    {"kind": "max_abs_le", "signal": "Bracket/sigma_max", "value": YIELD / 2,
                     "note": "the index moves keep the bracket below half the 6082-T6 yield strength (250 MPa)"},
                ]
            },
            RING: {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "E108", "W201", "W202"]},
                    {"kind": "scene_bindings"},
                    {"kind": "fft_peak", "signal": "Payload/flow/y[5]", "from_t": 0.0, "to_t": 1.0,
                     "min_hz": 5.0, "max_hz": 25.0, "value": full[0], "rtol": 0.003, "note": note},
                    {"kind": "fft_peak", "signal": "Payload/flow/y[4]", "from_t": 0.0, "to_t": 1.0,
                     "min_hz": 25.0, "max_hz": 60.0, "value": full[1], "rtol": 0.003, "note": note},
                    {"kind": "max_abs", "signal": "Bracket/sigma_vm[1]", "from_t": 0.0, "to_t": T_FIRST,
                     "value": REF[0], "rtol": 0.03, "note": note_s + "; " + note_hand},
                    {"kind": "max_abs", "signal": "Bracket/sigma_vm[2]", "from_t": 0.0, "to_t": T_FIRST,
                     "value": REF[1], "rtol": 0.03, "note": note_s},
                    {"kind": "max_abs", "signal": "Bracket/sigma_max", "from_t": 0.0, "to_t": T_FIRST,
                     "value": REF[2], "rtol": 0.03, "note": note_s + " (the peak sits at the upright's sharp root corner)"},
                    {"kind": "max_abs_le", "signal": "Bracket/sigma_max", "value": YIELD / 2,
                     "note": "the bracket stays below half the 6082-T6 yield strength (250 MPa)"},
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
    print(f"ring-down stress reference: upright 30 mm {REF[0] / 1e6:.4f} MPa, root {REF[1] / 1e6:.4f} MPa, "
          f"peak {REF[2] / 1e6:.4f} MPa; modes {REF[3][0]:.4f} / {REF[3][1]:.4f} Hz; "
          f"hand F {HAND['F']:.3f} N, sigma_zz {HAND['szz'] / 1e6:.4f} MPa")


if __name__ == "__main__":
    main()
