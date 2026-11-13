# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the T8X spider-robot example: models, scene and expected.json.

The two models are the same plant (a 6-DOF body and eight reduced three-joint legs, 24
servo coordinates) with different commands:

    spider-stand   all eight feet planted, the gait held still; starts in the static
                   equilibrium of design.json (the static and IK model)
    spider-walk    the alternating tetrapod gait and a scripted forward / turn / crab command
                   (the locomotion model)

Each leg (IK, reduced three-joint leg, wrench on the body) is drawn once as the library
subsystem `library/SpiderLegUnit.bgsub.json`, also written here; both models use eight
instances `Leg1`..`Leg8` that pin only the hip position, the hip yaw and the foot friction.

The derived plant data (joint inertias, the composite body, the equilibrium start) and the
check references come from design/design.json: run design.py first.

Run:  uv run examples/spider/design/build_model.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as d  # noqa: E402

ROOT = HERE.parent
MODELS = ROOT / "models"
DES = json.loads((HERE / "design.json").read_text(encoding="utf-8"))

CONTACT = d.CONTACT
T_END = 16.0
T_STAND = 4.0


def fmt(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return "true" if x else "false"
    return repr(float(x))


def vec(xs) -> str:
    return "[" + ", ".join(fmt(x) for x in xs) + "]"


# Footprints on the canvas (web/src/editor/geometry.ts), with 20 px for the name below.
COMPACT, LETTER = 60, 40


def card_height(rows: int) -> int:
    """A subsystem card: 34 px header, 26 px per port row, 18 px footer, at least 86 px."""
    return max(86, 34 + 26 * rows + 18)


class Diagram:
    """Nodes keyed by name (the node id is the name), connections, exposed ports and notes."""

    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.ann: list[dict] = []
        self.ports: list[dict] = []
        self.boxes: list[tuple[str, float, float, float, float]] = []

    def node(self, name, ref, x, y, params=None, starts=None, constants=None,
             size=(COMPACT, COMPACT + 20)) -> str:
        assert all(n["id"] != name for n in self.nodes), name
        self.nodes.append({
            "id": name, "name": name, "block": {"ref": ref}, "position": {"x": x, "y": y},
            "rotation": 0, "flipX": False,
            "params": {k: fmt(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: fmt(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self.boxes.append((name, x, y, size[0], size[1]))
        return name

    def letter(self, name, ref, x, y, params=None):
        return self.node(name, ref, x, y, params, size=(LETTER, LETTER + 20))

    def card(self, name, ref, x, y, rows, params=None, starts=None):
        """An instance of a library subsystem, drawn as a card 164 px wide."""
        return self.node(name, ref, x, y, params, starts, size=(164, card_height(rows) + 20))

    def _conn(self, kind, a, ap, b, bp, label=None):
        c = {"id": f"{kind[0]}{len(self.conns) + 1:03d}", "kind": kind,
             "from": {"node": a}, "to": {"node": b}, "route": [], "label": label}
        if ap:
            c["from"]["port"] = ap
        if bp:
            c["to"]["port"] = bp
        self.conns.append(c)

    def bond(self, a, ap, b, bp):
        self._conn("bond", a, ap, b, bp)

    def sig(self, a, ap, b, bp, label=None):
        self._conn("signal", a, ap, b, bp, label)

    def in_port(self, name, node, port, size, unit=None):
        self.ports.append({"name": name, "kind": "signal", "direction": "input", "type": "Real",
                           "size": [size], "unit": unit, "node": node, "port": port})

    def out_port(self, name, node, port, size=1, unit=None):
        self.ports.append({"name": name, "kind": "signal", "direction": "output", "type": "Real",
                           "size": [size], "unit": unit, "node": node, "port": port})

    def power_port(self, name, domain, node, port, size):
        self.ports.append({"name": name, "kind": "power", "domain": domain, "size": [size],
                           "node": node, "port": port})

    def note(self, text, x, y, w=420, h=70, color="yellow"):
        self.ann.append({"id": f"a{len(self.ann) + 1}", "kind": "text", "text": text,
                         "x": x, "y": y, "w": w, "h": h, "color": color})
        self.boxes.append((f"note a{len(self.ann)}", x, y, w, h))

    def check_layout(self, label: str) -> None:
        """No two nodes (with their names) or notes may overlap."""
        gap = 10
        for i, (na, xa, ya, wa, ha) in enumerate(self.boxes):
            for nb, xb, yb, wb, hb in self.boxes[i + 1:]:
                if xa < xb + wb + gap and xb < xa + wa + gap and ya < yb + hb + gap and yb < ya + ha + gap:
                    raise SystemExit(f"{label}: {na} overlaps {nb}")

    def diagram(self) -> dict:
        return {"nodes": self.nodes, "connections": self.conns, "subsystemPorts": [],
                "annotations": self.ann}


def glob(name, value, unit, description):
    return {"name": name, "value": str(value), "unit": unit, "description": description}


GLOBALS = [
    glob("vx_cmd", d.V_WALK, "m/s", "Forward walk command"),
    glob("vy_cmd", d.V_CRAB, "m/s", "Crab (left) walk command"),
    glob("wz_cmd", math.degrees(d.W_TURN), "deg/s", "Walk-turn yaw-rate command"),
    glob("h_stand", d.H_STAND, "m", "Commanded body height (the start pose is built for 0.110 m)"),
    glob("gait_T", d.T_GAIT, "s", "Gait cycle time"),
    glob("gait_lift", d.LIFT, "m", "Swing apex height"),
    glob("mu_foot", CONTACT["mu"], "1", "Foot-pad friction coefficient"),
    glob("roll0", 0, "deg", "Initial body roll (a perturbed start)"),
]


# ----------------------------------------------------------------------------- the leg unit
# library/SpiderLegUnit.bgsub.json: one leg, drawn once. The eight legs differ only in where
# the hip sits on the body (hx, hy and the hip yaw); the foot friction is pinned so the model
# global `mu_foot` reaches every foot. Everything else, including the joint angles of the
# equilibrium start, is the same for every leg.
LEG_UNIT = "SpiderLegUnit"
LEG_ROWS = 3                       # foot, g, V on the left; p and f_n on the right
LEG_PINS = ["IK/hx", "IK/hy", "IK/yaw", "Joints/hx", "Joints/hy", "Joints/yaw", "Joints/mu"]


def leg_pins(k: int) -> dict:
    """The pinned values of leg k: its hip position and hip yaw, for the IK and the leg, and
    the foot friction from the global `mu_foot`."""
    hx, hy, _hz, yaw = d.HIPS[k - 1]
    hip = {"hx": fmt(hx), "hy": fmt(hy), "yaw": fmt(yaw)}
    pins = {f"{node}/{key}": value for node in ("IK", "Joints") for key, value in hip.items()}
    pins["Joints/mu"] = "mu_foot"
    return pins


def leg_definition() -> dict:
    """One leg unit: IK -> reduced three-joint leg -> external wrench on the body.

    Ports: the foot target `foot` (body frame) from the gait, the body pose `g` and twist `V`,
    the body bond `p` (the wrench at the body centre of mass) and the foot normal force `f_n`.
    """
    hx, hy, hz, yaw = d.HIPS[0]
    assert all(h[2] == hz for h in d.HIPS), "every hip at the same height (hz is not pinned)"
    q0 = d.Q0[0]
    # The analytic IK gives every leg the same nominal joint angles (the foot is straight out
    # along the hip x axis); the eight solutions differ only in rounding.
    assert all(abs(a - b) < 1e-12 for q in d.Q0 for a, b in zip(q, q0)), d.Q0
    # The equilibrium start: the joints deflected under the static load, the servo filter at
    # the IK command (design.json, stance_static).
    qs = DES["stand"]["q_static"]
    s = Diagram()
    common = {"hx": fmt(hx), "hy": fmt(hy), "hz": fmt(hz), "yaw": fmt(yaw),
              "a": d.A_COXA, "b": d.B_FEMUR, "c": d.C_TIBIA}
    s.node("IK", "project:SpiderLegIK", 0, 0, params={**common, "band": d.REACH_BAND})
    s.node("Joints", "project:SpiderLeg", 180, 0,
           params={**common, "m_c": d.M_COXA, "m_f": d.M_FEMUR, "m_t": d.M_TIBIA,
                   "I": vec(DES["joint_inertias"]),
                   "b_joint": vec(d.B_JOINT), "g0": d.G0,
                   "kp": vec(d.KP), "kd": vec(d.KD),
                   "tau_max": vec(d.TAU_MAX), "w_nl": vec(d.W_NL),
                   "tau_s": d.TAU_S, "kc": CONTACT["k"], "xref": CONTACT["xref"],
                   "cc": CONTACT["c"], "mu": CONTACT["mu"], "vs": CONTACT["vs"],
                   "bt": CONTACT["bt"], "eps": CONTACT["eps"],
                   "feps": CONTACT["feps"], "gz": "0.0"},
           starts={"q1s": fmt(qs[0]), "q2s": fmt(qs[1]), "q3s": fmt(qs[2]),
                   "qf1s": fmt(q0[0]), "qf2s": fmt(q0[1]), "qf3s": fmt(q0[2])})
    s.node("Wrench", "stdlib:multibond/ExternalWrenchSpatial", 360, 0)
    s.sig("IK", "qcmd", "Joints", "qcmd")
    for pout in ("tx", "ty", "tz", "fx", "fy", "fz"):
        s.sig("Joints", pout, "Wrench", pout)
    s.in_port("foot", "IK", "p", 3, unit="m")
    s.in_port("g", "Joints", "g", 7)
    s.in_port("V", "Joints", "V", 6)
    s.power_port("p", "Spatial", "Wrench", "p", 6)
    s.out_port("f_n", "Joints", "f_n", unit="N")
    s.check_layout(LEG_UNIT)
    return {
        "format": "bgsim.subsystem", "name": LEG_UNIT,
        "description": ("One leg of the T8X spider: the analytic leg IK (`IK`), the reduced "
                        "three-joint leg with its servos, weight and foot contact (`Joints`) "
                        "and the wrench it puts on the body (`Wrench`). Inputs: the foot "
                        "target `foot` in the body frame, the body pose `g` and twist `V`; "
                        "`p` bonds to the body and `f_n` is the foot normal force. An instance "
                        "pins its hip (IK/hx, IK/hy, IK/yaw and the same three on Joints) and "
                        "the foot friction Joints/mu. "
                        "Generated by design/build_model.py."),
        "ports": s.ports,
        "diagram": s.diagram(),
        "pins": {"params": LEG_PINS, "starts": []},
    }


# ----------------------------------------------------------------------------- the model
LEG_X0, LEG_DX, LEG_Y0, LEG_DY = 900, 200, 40, 200


def plant(dg: Diagram, stand: bool) -> None:
    dg.node("World", "stdlib:multibond/GroundSpatial", 40, 40)
    # The start is the static equilibrium of design.json (built for H_STAND), rolled by the
    # global roll0 about the body x axis.
    dg.node("Free", "stdlib:spatial/Free3D", 200, 40,
            starts={"qw": "cos(roll0*pi/360)", "qx": "sin(roll0*pi/360)", "qy": "0.0", "qz": "0.0",
                    "px": "0.0", "py": "0.0", "pz": fmt(DES["stand"]["body_height"])})
    # The body block carries the whole robot with the legs locked in the nominal stance.
    comp = DES["composite_body"]
    dg.node("Body", "stdlib:spatial/RigidBody3D", 380, 40,
            params={"m": comp["m"], "J": vec(comp["J_origin_diag"]), "g0": d.G0})
    dg.bond("World", "p", "Free", "parent")
    dg.bond("Free", "child", "Body", "p")
    dg.sig("Free", "pose", "Body", "g")
    for k in range(1, 7):
        dg.letter(f"FreeSe{k}", "stdlib:bondgraph/Se", 40 + 60 * (k - 1), 200,
                  params={"e": "0.0"})
        dg.bond(f"FreeSe{k}", "p", "Free", f"drive{k}")

    dg.note("**Plant.** The body is a full 6-DOF `Free3D` + `RigidBody3D` bond graph that "
            "carries the whole robot's mass and inertia with the legs locked in the stance. "
            "The eight legs `Leg1`..`Leg8` are instances of one library subsystem, "
            "`SpiderLegUnit`: the leg IK, the reduced three-joint leg (`SpiderLeg`: servo "
            "angle dynamics, link gravity, foot contact) and its wrench on the body. The leg "
            "is quasi-static and signal-coupled: the body feels it only through the contact "
            "force at the foot and the moment of the link weights; the servo reactions and "
            "the inertia of a swinging leg do not reach the body (see the README).", 40, -120,
            1800, 90, "blue")

    # gait / outer loop
    dg.node("Gait", "project:SpiderGait", 720, 300,
            params={"T_gait": "gait_T", "duty": d.DUTY, "lift": "gait_lift",
                    "h_stand": "h_stand", "nx": vec(d.NX), "ny": vec(d.NY),
                    "off": vec(d.PHASE_OFF), "k_att": d.K_ATT, "tau_att": d.TAU_ATT,
                    "ramp_t": d.RAMP_T,
                    "z_unload": 0.0 if stand else DES["gait"]["z_unload"]})
    dg.sig("Free", "pose", "Gait", "g")
    dg.sig("Body", "V", "Gait", "V")
    if stand:
        dg.node("ZeroCmd", "stdlib:sources/Constant", 540, 300, params={"value": "0.0"})
        for p in ("vx_cmd", "vy_cmd", "wz_cmd"):
            dg.sig("ZeroCmd", "y", "Gait", p)
    else:
        # 0..16 s in 2 s samples, linear between them: march in place (0..2 s), ramp up to
        # forward (2..4), forward with a turn ramped in and out (4..10, the turn peaks at
        # 6..8), slow forward plus crab left (10..12, blended in from 8 and out by 14),
        # forward (14..16).
        tables = {
            "vx_cmd": "[0.0, 0.0, vx_cmd, vx_cmd, vx_cmd, 0.3*vx_cmd, 0.3*vx_cmd, vx_cmd, vx_cmd]",
            "vy_cmd": "[0.0, 0.0, 0.0, 0.0, 0.0, vy_cmd, vy_cmd, 0.0, 0.0]",
            "wz_cmd": "[0.0, 0.0, 0.0, wz_cmd*pi/180.0, wz_cmd*pi/180.0, 0.0, 0.0, 0.0, 0.0]",
        }
        for j, (p, values) in enumerate(tables.items()):
            dg.node(f"{p}Tab", "stdlib:sources/TimeTable", 540, 200 + 100 * j,
                    constants={"N": 9},
                    params={"t_start": "0.0", "sample_time": "2.0", "method": "1",
                            "values": values})
            dg.sig(f"{p}Tab", "y", "Gait", p)

    # measurement block (created before the legs so each leg can feed its foot force)
    dg.node("Status", "project:SpiderStatus", LEG_X0 + 4 * LEG_DX + 60, 160)
    dg.sig("Free", "pose", "Status", "g")
    dg.sig("Body", "V", "Status", "V")

    # legs: eight instances of the leg unit, left side 1..4 on top, right side 5..8 below
    for k in range(1, 9):
        leg = f"Leg{k}"
        dg.card(leg, f"project:{LEG_UNIT}", LEG_X0 + LEG_DX * ((k - 1) % 4),
                LEG_Y0 + LEG_DY * ((k - 1) // 4), LEG_ROWS, params=leg_pins(k))
        dg.sig("Gait", f"foot{k}", leg, "foot")
        dg.sig("Free", "pose", leg, "g")
        dg.sig("Body", "V", leg, "V")
        dg.bond(leg, "p", "Body", "p")
        dg.sig(leg, "f_n", "Status", f"f{k}")

    dg.note("**Gait and control.** `Gait` is the T8X Bigfoot-style layer: an alternating "
            "tetrapod with a constant-speed stance (70 % of the cycle) and a Hermite swing, "
            "and a filtered roll/pitch correction of the foot targets (the height loop is off). "
            "Inside each leg, `IK` turns the body-frame foot target into three joint "
            "commands and `Joints` adds the servo (HS-82MG class: P loop, stall torque, "
            "back-EMF), the link weights, the contact force and the wrench on the body. "
            "`IK` and `Joints` use the same "
            "kinematic chain as the 3D scene.", 40, 520, 1800, 90, "green")


def settings(t_end: float, points: int) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "Rodas5P", "reltol": 1e-6,
            "abstol": 1e-8, "max_step": None, "output": {"mode": "points", "points": points},
            "event_limit": 100000}


def dashboard(stand: bool) -> dict:
    cards = [
        {"id": "intro", "kind": "text", "size": "2x1", "title": "T8X spider robot",
         "options": {"markdown": True, "text":
                     "An eight-legged **T8X-class** spider: 24 joint servos, an alternating "
                     "tetrapod gait, foot contact and a filtered attitude correction."}},
        {"id": "h", "kind": "value", "size": "1x1", "title": "Body height", "signals": ["Status/height"],
         "options": {"decimals": 3, "unit": "m"}},
        {"id": "load", "kind": "value", "size": "1x1", "title": "Ground load", "signals": ["Status/load"],
         "options": {"decimals": 1, "unit": "N"}},
        {"id": "contact", "kind": "value", "size": "1x1", "title": "Feet down", "signals": ["Status/contact"],
         "options": {"decimals": 1, "unit": ""}},
        {"id": "speed", "kind": "value", "size": "1x1", "title": "Body speed", "signals": ["Status/speed"],
         "options": {"decimals": 2, "unit": "m/s"}},
    ]
    if stand:
        cards += [
            {"id": "hs", "kind": "slider", "size": "1x1", "title": "Stand height",
             "parameter": "global:h_stand", "options": {"min": 0.08, "max": 0.14, "step": 0.005,
                                                        "decimals": 3, "unit": "m"}},
        ]
    else:
        cards += [
            {"id": "vx", "kind": "slider", "size": "1x1", "title": "Forward speed",
             "parameter": "global:vx_cmd", "options": {"min": 0.02, "max": 0.18, "step": 0.01,
                                                       "decimals": 2, "unit": "m/s"}},
            {"id": "wz", "kind": "slider", "size": "1x1", "title": "Turn rate",
             "parameter": "global:wz_cmd", "options": {"min": -30.0, "max": 30.0, "step": 5.0,
                                                       "decimals": 0, "unit": "deg/s"}},
            {"id": "T", "kind": "number", "size": "1x1", "title": "Gait period",
             "parameter": "global:gait_T", "options": {"decimals": 2, "unit": "s"}},
        ]
    return {"autoRerun": False, "cards": cards}


def model(name: str, stand: bool) -> dict:
    dg = Diagram()
    plant(dg, stand)
    dg.check_layout(name)
    plots = [
        {"id": "p1", "title": "Body height (m)",
         "signals": ["Status/height"]},
        {"id": "p2", "title": "Body x/y position and yaw",
         "signals": ["Status/x", "Status/y", "Status/yaw_deg"]},
        {"id": "p3", "title": "Ground load and number of feet down",
         "signals": ["Status/load", "Status/contact"]},
        {"id": "p4", "title": "Body forward speed, speed and yaw rate",
         "signals": ["Status/v_fwd", "Status/speed", "Status/wb"]},
        {"id": "p5", "title": "Foot normal forces (N)",
         "signals": [f"Leg{k}/Joints/f_n" for k in range(1, 9)]},
        {"id": "p6", "title": "Leg 1 joint angles (rad)",
         "signals": ["Leg1/Joints/q1", "Leg1/Joints/q2", "Leg1/Joints/q3"]},
        {"id": "p7", "title": "Leg 1 IK reach and foot height",
         "signals": ["Leg1/IK/reach", "Leg1/Joints/pfoot[3]"]},
        {"id": "p8", "title": "Leg 1 servo torques (N m)",
         "signals": ["Leg1/Joints/tau1", "Leg1/Joints/tau2", "Leg1/Joints/tau3"]},
    ]
    t_end = T_STAND if stand else T_END
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name,
        "$comment": ("T8X-class eight-legged spider robot: a 6-DOF body and eight instances of "
                     "the leg subsystem SpiderLegUnit (analytic IK, reduced three-joint leg with "
                     "servos, link gravity and a ContactPoint-law foot contact, wrench on the "
                     "body), an alternating tetrapod gait and a filtered attitude correction. "
                     "Generated by design/build_model.py; see the README and model docs."),
        "diagram": dg.diagram(),
        "settings": settings(t_end, int(t_end * 50) + 1),
        "plots": plots,
        "parameters": [dict(g) for g in GLOBALS],
        "dashboard": dashboard(stand),
    }
    doc["scene"] = {"file": "scenes/spider.sdf"}
    doc["bindings"] = scene_bindings()
    if stand:
        for g in doc["parameters"]:
            if g["name"] == "vx_cmd":
                g["value"] = "0.0"
            if g["name"] == "vy_cmd":
                g["value"] = "0.0"
            if g["name"] == "wz_cmd":
                g["value"] = "0.0"
            if g["name"] == "gait_lift":
                g["value"] = "0.0"
    return doc


def scene_bindings() -> list[dict]:
    out = [{"target": "link:body", "property": "pose",
            "signal": [f"Free/pose[{k}]" for k in range(1, 8)]}]
    for k in range(1, 9):
        for j, nm in enumerate(("coxa", "femur", "tibia"), start=1):
            out.append({"target": f"joint:leg{k}_{nm}_joint", "property": "position",
                        "signal": f"Leg{k}/Joints/q{j}"})
    return out


def build_scene() -> str:
    """SDF of the spider: body at the origin, eight three-link legs, a floor.

    Link poses are the rest poses (all joints at zero). Every joint frame is its child link
    frame and the axis is the child z, the chain the model's IK and leg blocks use (hip yaw,
    coxa yaw, Rx90, femur, tibia). The floor covers the commanded walk path (design.json)
    plus the leg span.
    """
    def pose_xyz_rpy(x, y, z, yaw):
        return f"{x:.9g} {y:.9g} {z:.9g} 0 0 {yaw:.9g}"

    (x0, x1), (y0, y1) = DES["floor"]["x"], DES["floor"]["y"]
    cx, cy0, sx, sy0 = 0.5 * (x0 + x1), 0.5 * (y0 + y1), x1 - x0, y1 - y0
    out = [f'''<?xml version="1.0"?>
<!--
  spider: a T8X-class eight-legged robot, x forward, y left, z up, metres. The body mesh
  carries the cephalothorax, the abdomen, the eyes and the eight hip bosses. Each leg is
  three links (coxa, femur, tibia) whose joints are bound to the model's joint angles; the
  foot pad is part of the tibia. The floor slab covers the commanded walk path of
  spider-walk plus the leg span, with a dark rim on all four sides. The meshes are written
  by design/make_meshes.py; this file by design/build_model.py.
-->
<sdf version="1.9">
  <model name="spider">
    <link name="floor">
      <pose>0 0 0 0 0 0</pose>
      <visual name="floor_slab">
        <pose>{cx:.4f} {cy0:.4f} -0.012 0 0 0</pose>
        <geometry><box><size>{sx:.4f} {sy0:.4f} 0.024</size></box></geometry>
        <material><diffuse>0.50 0.52 0.55 1</diffuse></material>
      </visual>
      <visual name="floor_edge_n">
        <pose>{cx:.4f} {y1 + 0.01:.4f} -0.010 0 0 0</pose>
        <geometry><box><size>{sx + 0.04:.4f} 0.02 0.028</size></box></geometry>
        <material><diffuse>0.18 0.22 0.28 1</diffuse></material>
      </visual>
      <visual name="floor_edge_s">
        <pose>{cx:.4f} {y0 - 0.01:.4f} -0.010 0 0 0</pose>
        <geometry><box><size>{sx + 0.04:.4f} 0.02 0.028</size></box></geometry>
        <material><diffuse>0.18 0.22 0.28 1</diffuse></material>
      </visual>
      <visual name="floor_edge_e">
        <pose>{x1 + 0.01:.4f} {cy0:.4f} -0.010 0 0 0</pose>
        <geometry><box><size>0.02 {sy0:.4f} 0.028</size></box></geometry>
        <material><diffuse>0.18 0.22 0.28 1</diffuse></material>
      </visual>
      <visual name="floor_edge_w">
        <pose>{x0 - 0.01:.4f} {cy0:.4f} -0.010 0 0 0</pose>
        <geometry><box><size>0.02 {sy0:.4f} 0.028</size></box></geometry>
        <material><diffuse>0.18 0.22 0.28 1</diffuse></material>
      </visual>
    </link>
    <link name="body">
      <pose>0 0 {d.H_STAND:.3f} 0 0 0</pose>
      <visual name="body_mesh">
        <geometry><mesh><uri>meshes/spider_body.glb</uri></mesh></geometry>
      </visual>
    </link>
''']
    for k, (hx, hy, hz, yaw) in enumerate(d.HIPS, start=1):
        cy, sy = math.cos(yaw), math.sin(yaw)
        out.append(
            f'    <link name="leg{k}_coxa">\n'
            f'      <pose>{pose_xyz_rpy(hx, hy, d.H_STAND + hz, yaw)}</pose>\n'
            f'      <visual name="leg{k}_coxa_mesh">\n'
            f'        <geometry><mesh><uri>meshes/spider_coxa.glb</uri></mesh></geometry>\n'
            f'      </visual>\n'
            f'    </link>\n')
        # femur rest frame = coxa frame + T(a,0,0) Rx90
        fx = hx + d.A_COXA * cy
        fy = hy + d.A_COXA * sy
        out.append(
            f'    <link name="leg{k}_femur">\n'
            f'      <pose>{fx:.9g} {fy:.9g} {d.H_STAND + hz:.9g} 1.570796327 0 {yaw:.9g}</pose>\n'
            f'      <visual name="leg{k}_femur_mesh">\n'
            f'        <geometry><mesh><uri>meshes/spider_femur.glb</uri></mesh></geometry>\n'
            f'      </visual>\n'
            f'    </link>\n')
        # tibia rest frame = femur frame + T(b,0,0), same orientation
        tx = fx + d.B_FEMUR * cy
        ty = fy + d.B_FEMUR * sy
        out.append(
            f'    <link name="leg{k}_tibia">\n'
            f'      <pose>{tx:.9g} {ty:.9g} {d.H_STAND + hz:.9g} 1.570796327 0 {yaw:.9g}</pose>\n'
            f'      <visual name="leg{k}_tibia_mesh">\n'
            f'        <geometry><mesh><uri>meshes/spider_tibia.glb</uri></mesh></geometry>\n'
            f'      </visual>\n'
            f'    </link>\n')
        out.append(
            f'    <joint name="leg{k}_coxa_joint" type="revolute">\n'
            f'      <parent>body</parent>\n      <child>leg{k}_coxa</child>\n'
            f'      <axis><xyz>0 0 1</xyz><limit><lower>-1.2</lower><upper>1.2</upper></limit></axis>\n'
            f'    </joint>\n'
            f'    <joint name="leg{k}_femur_joint" type="revolute">\n'
            f'      <parent>leg{k}_coxa</parent>\n      <child>leg{k}_femur</child>\n'
            f'      <axis><xyz>0 0 1</xyz><limit><lower>-1.5</lower><upper>1.8</upper></limit></axis>\n'
            f'    </joint>\n'
            f'    <joint name="leg{k}_tibia_joint" type="revolute">\n'
            f'      <parent>leg{k}_femur</parent>\n      <child>leg{k}_tibia</child>\n'
            f'      <axis><xyz>0 0 1</xyz><limit><lower>-2.5</lower><upper>0.2</upper></limit></axis>\n'
            f'    </joint>\n')
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


def expected() -> dict:
    """The checks. Every reference is from design/data.py or design/design.json (derived
    without running the model); the tolerances carry their reason in the note."""
    w = d.M_TOTAL * d.G0
    st, four, gait, path = DES["stand"], DES["four_foot"], DES["gait"], DES["walk_path"]
    deg = math.degrees
    diag = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206", "W218"],
            "note": "no algebraic loop, causality conflict, event storm or unpinned instance key"}
    stand = [diag, {"kind": "scene_bindings"}]
    # the IK of every leg (each has its own hip yaw) against the Python IK of data.py
    for k in range(1, 9):
        for j in range(3):
            stand.append({"kind": "cursor_value", "signal": f"Leg{k}/IK/q{j + 1}", "t": 0.0,
                          "value": d.Q0[k - 1][j], "abs": 1e-9,
                          **({"note": "Julia IK block against the Python IK of data.py, all eight hips"}
                             if k == 1 and j == 0 else {})})
        stand.append({"kind": "cursor_value", "signal": f"Leg{k}/IK/reach", "t": 0.0, "value": 1.0,
                      "abs": 1e-9, **({"note": "the nominal foot is inside the workspace"} if k == 1 else {})})
    stand += [
        {"kind": "max_abs", "signal": "Status/load", "from_t": 0.0, "to_t": T_STAND, "value": w,
         "rtol": 0.01, "note": "starts in the static equilibrium (design.json): the load never "
                               "overshoots the 10.003 N weight by more than 1 %"},
        {"kind": "cursor_value", "signal": "Status/load", "t": 3.0, "value": w, "rtol": 1e-3,
         "note": "the eight foot forces carry the whole 1.020 kg weight (body + legs)"},
        {"kind": "cursor_value", "signal": "Status/height", "t": 3.0, "value": st["body_height"],
         "abs": 5e-4, "note": f"h_stand minus the static sag: {DES['static_contact_penetration'] * 1e3:.3f} mm "
                              f"contact penetration + {st['servo_sag'] * 1e3:.3f} mm servo compliance (design.json)"},
        {"kind": "cursor_value", "signal": "Leg1/Joints/pfoot[3]", "t": 3.0,
         "value": -DES["static_contact_penetration"], "abs": 5e-5,
         "note": "the foot sinks by the Hertz penetration of W/8"},
    ]
    for k in range(1, 9):
        for j in range(3):
            stand.append({"kind": "cursor_value", "signal": f"Leg{k}/Joints/tau{j + 1}", "t": 3.0,
                          "value": st["tau_static"][j], "abs": 3e-3,
                          **({"note": "standing servo torques: link-centre gravity Jacobian and "
                                      "the foot load W/8 through the leg Jacobian (design.json); "
                                      "3e-3 N m covers the residual foot friction"}
                             if k == 1 and j == 0 else {})})
    for j in (1, 2):
        stand.append({"kind": "cursor_value", "signal": f"Leg1/Joints/q{j + 1}", "t": 3.0,
                      "value": st["q_static"][j], "abs": 2e-4,
                      **({"note": "the joint deflects by tau/kp from the IK command (design.json)"}
                         if j == 1 else {})})
    roll = DES["roll"]["by_k_att"][f"{d.K_ATT:g}"]
    m_roll = 0.3
    roll_moment = [
        diag,
        {"kind": "cursor_value", "signal": "Status/roll_deg", "t": 2.5,
         "value": deg(m_roll / roll["k_roll"]), "rtol": 0.1,
         "note": f"static roll under a {m_roll} N m roll moment: M / K_roll with "
                 f"K_roll = (1 + k_att) k_foot sum(y^2) = {roll['k_roll']:.1f} N m/rad "
                 "(design.json; the old sign of the attitude loop gives K_roll = 0). 10 % covers "
                 "the Hertz nonlinearity and the creep of the feet"},
    ]
    roll_start = [
        diag,
        {"kind": "max_abs_le", "signal": "Status/roll_deg", "from_t": 1.0, "to_t": 3.0, "value": 0.05,
         "note": f"from a 1 deg roll start the roll is below 5 % of the start after 1 s: the "
                 f"linear roll model decays at {roll['sigma']:.1f} 1/s (design.json); with the old "
                 "sign of the attitude loop the roll stiffness is zero and the tilt stays"},
    ]

    sag_mid = 0.5 * (st["sag"] + four["sag"])
    sag_half = 0.5 * (four["sag"] - st["sag"])
    walk = [
        diag,
        {"kind": "scene_bindings"},
        {"kind": "cursor_value", "signal": "Status/x", "t": T_END, "value": path["x16"],
         "abs": 0.05 * path["length16"],
         "note": f"the integrated command path (design.json): x = {path['x16']:.3f} m; 5 % of the "
                 f"{path['length16']:.2f} m path for slip and servo compliance"},
        {"kind": "cursor_value", "signal": "Status/y", "t": T_END, "value": path["y16"],
         "abs": 0.05 * path["length16"], "note": f"y = {path['y16']:.3f} m, same tolerance"},
        {"kind": "cursor_value", "signal": "Status/yaw_deg", "t": T_END, "value": path["yaw16_deg"],
         "abs": 0.05 * path["yaw16_deg"], "note": "the integrated yaw-rate command, 5 %"},
        {"kind": "mean_value", "signal": "Status/v_fwd", "from_t": 14.4, "to_t": 16.0,
         "value": path["mean_vx_14p4_16"], "rtol": 0.05,
         "note": "two straight cycles at the 0.10 m/s command: the stance foot moves at exactly "
                 "the command, so the body does too; 5 % for slip"},
        {"kind": "ripple", "signal": "Status/v_fwd", "from_t": 14.4, "to_t": 16.0, "measure": "pp",
         "value": 0.3 * d.V_WALK,
         "note": "the constant-velocity stance implies a constant body speed; 0.3 v peak to peak "
                 "allows for the servo compliance at the 8/4-foot hand-over (the old sinusoidal "
                 "stance swung between 0.004 and 0.19 m/s)"},
        {"kind": "mean_value", "signal": "Status/contact", "from_t": 14.4, "to_t": 16.0,
         "value": gait["mean_feet_down"], "abs": 0.3,
         "note": "8 x the 0.70 stance fraction: the hand-over ramps put touchdown and liftoff at "
                 "zero load (design.json, z_unload); 0.3 for the tanh gate of the count, which "
                 "reaches 1 only above about 0.15 N"},
        {"kind": "min_ge", "signal": "Status/contact", "from_t": 4.0, "to_t": 16.0, "value": 3.8,
         "note": "the profile always keeps one group of four feet loaded"},
        {"kind": "max_abs", "signal": "Leg1/Joints/pfoot[3]", "from_t": 14.4, "to_t": 16.0,
         "value": gait["apex_world"], "abs": 1.5e-3,
         "note": f"swing apex {gait['apex_world'] * 1e3:.1f} mm: the commanded "
                 f"{gait['apex_command'] * 1e3:.1f} mm on the body at its four-foot height, the "
                 "unloaded leg sagging under its weight (design.json); 1.5 mm for the "
                 f"{gait['apex_filter_drop'] * 1e3:.2f} mm of the command filter, the servo lag "
                 "and the body bounce"},
        {"kind": "max_abs", "signal": "Leg5/Joints/pfoot[3]", "from_t": 14.4, "to_t": 16.0,
         "value": gait["apex_world"], "abs": 1.5e-3},
        {"kind": "mean_value", "signal": "Status/height", "from_t": 14.4, "to_t": 16.0,
         "value": d.H_STAND - sag_mid, "abs": sag_half + 5e-4,
         "note": "no height loop (k_h = 0): the body rides between the eight-foot and the "
                 "four-foot static sag (design.json)"},
        {"kind": "mean_value", "signal": "Status/load", "from_t": 14.4, "to_t": 16.0, "value": w,
         "rtol": 0.02, "note": "over whole gait cycles the floor carries the weight (vertical "
                               "momentum balance); 2 % for the sampling of the load ripple"},
        {"kind": "min_ge", "signal": "Status/load", "from_t": 2.0, "to_t": 16.0, "value": 0.5 * w,
         "note": "the hand-over ramps keep at least half the weight on the floor at every instant"},
        {"kind": "max_abs_le", "signal": "Status/roll_deg", "value": 3.0},
        {"kind": "max_abs_le", "signal": "Status/pitch_deg", "value": 3.0},
        {"kind": "max_abs_le", "signal": "Leg1/Joints/q1", "value": 1.2},
        {"kind": "max_abs_le", "signal": "Leg1/Joints/q2", "value": 1.8},
        {"kind": "max_abs_le", "signal": "Leg1/Joints/q3", "value": 2.6},
    ]
    for k in range(1, 9):
        walk.append({"kind": "min_ge", "signal": f"Leg{k}/IK/reach", "from_t": 0.0, "to_t": T_END,
                     "value": 0.9, **({"note": "the gait stays inside every leg's workspace"} if k == 1 else {})})
    for k in range(1, 9):
        for j in range(3):
            walk.append({"kind": "max_abs_le", "signal": f"Leg{k}/Joints/tau{j + 1}",
                         "value": d.TAU_STALL,
                         **({"note": f"every servo stays within the HS-82MG stall torque "
                                     f"{d.TAU_STALL:.3f} N m (6.0 V datasheet)"} if k == 1 and j == 0 else {})})
    return {
        "project": "spider",
        "description": ("T8X spider robot: 6-DOF body, eight reduced three-joint legs (library "
                        "subsystem SpiderLegUnit) with servos, foot contact, an alternating "
                        "tetrapod gait and analytic IK. References from design/data.py and "
                        "design/design.json."),
        "models": {
            "spider-stand": {"checks": stand},
            "spider-stand-roll-moment": {
                "model": "spider-stand", "settings": {"t_end": 3.0, "output": {"points": 151}},
                "overrides": [{"target": "FreeSe1/e", "value": m_roll}], "checks": roll_moment},
            "spider-stand-roll-start": {
                "model": "spider-stand", "settings": {"t_end": 3.0, "output": {"points": 301}},
                "overrides": [{"target": "global:roll0", "value": 1.0}], "checks": roll_start},
            "spider-walk": {"checks": walk},
        },
    }


def main() -> int:
    unit = ROOT / "library" / f"{LEG_UNIT}.bgsub.json"
    unit.write_text(json.dumps(leg_definition(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {unit}")
    for name, stand in (("spider-stand", True), ("spider-walk", False)):
        doc = model(name, stand)
        path = MODELS / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path} ({len(doc['diagram']['nodes'])} nodes)")
    scene = ROOT / "scenes" / "spider.sdf"
    scene.write_text(build_scene(), encoding="utf-8", newline="\n")
    print(f"wrote {scene}")
    (ROOT / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n",
                                        encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
