# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the f16 models, scenes and expected.json from `design/design.json`.

    uv run examples/f16/design/design.py        # first
    uv run examples/f16/design/build_model.py

The airframe (a subsystem, `airframe()`) is the same in every model: the multibond rigid body on a
free joint, the air-data tap, the NASA tables as stdlib Lookup1D/Lookup2D blocks, the force build-up
and the engine. The models differ in what flies it.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path.insert(0, str(HERE))
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
GEAR = json.loads((HERE / "gear.json").read_text(encoding="utf-8"))    # design/gear.py
SI = DESIGN["si"]
TABLES = DESIGN["tables"]
# The gear's bond-graph elements are the Cessna's, unchanged. A project library belongs to one
# project and a project is copied whole from its example, so main() copies these files here on
# every build: the Cessna's library stays their one source.
CESSNA_BLOCKS = ("GearContact", "StrutSpring", "StrutDamper", "WheelFriction", "WheelSide")


def num(v: float) -> str:
    return repr(float(v))


def vec(values) -> str:
    return "[" + ", ".join(repr(float(v)) for v in values) + "]"


def mat(rows) -> str:
    return "[" + "; ".join(" ".join(repr(float(v)) for v in row) for row in rows) + "]"


# --------------------------------------------------------------------------- document helpers
class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[tuple] = []
        self.annotations: list[dict] = []
        self.ports: list[dict] = []
        self.ids: dict[str, str] = {}
        self._c = 0

    def node(self, name, block, x, y, params=None, starts=None, constants=None) -> str:
        nid = f"n{len(self.nodes) + 1:02d}"
        b = {"ref": block} if isinstance(block, str) else block
        self.nodes.append({
            "id": nid, "name": name, "block": b, "position": {"x": x, "y": y}, "rotation": 0,
            "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self.ids[name] = nid
        return name

    def _conn(self, kind, a, pa, b, pb):
        self._c += 1
        self.connections.append((f"c{self._c:03d}", kind, a, pa, b, pb))

    def sig(self, a, pa, b, pb):
        self._conn("signal", a, pa, b, pb)

    def bond(self, a, pa, b, pb):
        self._conn("bond", a, pa, b, pb)

    def junction(self, name, kind, x, y):
        return self.node(name, {"junction": str(kind)}, x, y)

    def note(self, text, x, y, w, h, color=None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def port(self, name, direction, node, port, unit=None, size=1):
        self.ports.append({"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
                           "unit": unit, "node": self.ids[node], "port": port})

    def doc(self) -> dict:
        conns = []
        for cid, kind, a, pa, b, pb in self.connections:
            frm = {"node": self.ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self.ids[b]}
            if pb is not None:
                to["port"] = pb
            conns.append({"id": cid, "kind": kind, "from": frm, "to": to})
        d = {"nodes": self.nodes, "connections": conns, "annotations": self.annotations}
        if self.ports:
            d["subsystemPorts"] = self.ports
        return d

    def subsystem(self, parent: "Diagram", name: str, x: float, y: float) -> str:
        parent.node(name, {"subsystem": {"ports": self.ports, "diagram": self.doc()}}, x, y)
        return name


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value, "unit": unit, "description": description}


def settings(t_end: float, points: int, reltol=1e-8, abstol=1e-8) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 100000}


def model_doc(name, comment, d: Diagram, sett, plots, scene, bindings, parameters, dashboard=None) -> dict:
    doc = {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
           "diagram": d.doc(), "settings": sett, "plots": plots,
           "scene": {"file": scene} if scene else None, "bindings": bindings, "parameters": parameters}
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc


# --------------------------------------------------------------------------- the airframe
def lookup2d(d: Diagram, name, tab, x, y):
    n = len(tab["x"])
    assert len(tab["y"]) == n and len(tab["table"]) == n
    return d.node(name, "stdlib:continuous/Lookup2D", x, y,
                  params={"breaks": mat([tab["x"], tab["y"]]), "table": mat(tab["table"])}, constants={"N": n})


def lookup1d(d: Diagram, name, xs, ys, x, y):
    return d.node(name, "stdlib:continuous/Lookup1D", x, y, params={"x": vec(xs), "table": vec(ys)},
                  constants={"N": len(xs)})


AIRFRAME_OUTPUTS = [  # (port name, node, node port, unit)
    ("alpha", "Air", "alpha_deg", None), ("q", "Air", "q_deg", None), ("nz", "Forces", "nz", None),
    ("vt", "Air", "vt", "m/s"), ("qbar", "Air", "qbar", "Pa"), ("mach", "Air", "mach", None),
    ("theta", "Air", "theta", "rad"), ("phi", "Air", "phi", "rad"), ("h", "Air", "h", "m"),
    ("theta_deg", "Air", "theta_deg", None), ("gamma", "Air", "gamma", "rad"),
]


def ex(v) -> str:
    """A number, or an expression over global parameters as it is."""
    return v if isinstance(v, str) else num(v)


def exvec(values) -> str:
    return "[" + ", ".join(ex(v) for v in values) + "]"


SIM_OUTPUTS = [  # the f16-sim airframe's extra ports: (port name, node, node port, unit)
    ("beta", "Air", "beta_deg", None), ("p", "Air", "p_deg", None), ("r", "Air", "r_deg", None),
    ("psi", "Air", "psi", "rad"), ("ny", "Forces", "ny", None), ("pa", "Air", "pa", "Pa"),
    ("hdot", "Air", "hdot", "m/s"), ("ui", "Air", "ui", "m/s"), ("vi", "Air", "vi", "m/s"),
    ("wi", "Air", "wi", "m/s"), ("pow", "Engine", "pow", None), ("thrust", "Engine", "thrust", "N"),
]


def landing_gear(d: Diagram, xcg: str, st: dict) -> None:
    """Three legs on the airframe, as the Cessna's (`GearContact`, `StrutSpring`, `StrutDamper`,
    `WheelFriction`, `WheelSide`), plus what the Cessna's fixed gear does not have: the retraction
    (an MSf in series with the strut, through a 0-junction), nose steering and the gear's drag.
    `st` holds the start expressions: `gear` (position), `strut` (leg -> compression)."""
    x0, y0 = 1600, 1400
    d.node("GearCmdIn", "stdlib:continuous/Gain", x0 - 400, y0 - 300, params={"k": "1.0"})
    d.port("gear_cmd", "input", "GearCmdIn", "u")
    for nm in ("brake_l", "brake_r", "pedal"):
        d.node(f"{nm}In", "stdlib:continuous/Gain", x0 - 400, y0 - 240 + 60 * ("brake_l", "brake_r", "pedal").index(nm),
               params={"k": "1.0"})
        d.port(nm, "input", f"{nm}In", "u")
    d.node("GearAct", "project:GearActuator", x0 - 200, y0 - 300,
           params={"t_gear": num(GEAR["t_gear"]), "L": num(GEAR["l_retract"])}, starts={"x": ex(st["gear"])})
    d.sig("GearCmdIn", "y", "GearAct", "cmd")
    lookup1d(d, "SteerMax", GEAR["steer_v"], GEAR["steer_deg"], x0 - 400, y0 - 60)
    d.sig("Air", "ui", "SteerMax", "u")
    d.node("Logic", "project:GearLogic", x0 - 200, y0 - 120,
           params={"f0": num(GEAR["f0_wow"]), "f1": num(GEAR["f1_wow"])})
    d.sig("pedalIn", "y", "Logic", "pedal")
    d.sig("SteerMax", "y", "Logic", "steer_max")
    d.sig("Logic", "w", "GearAct", "w")
    d.node("NoSteer", "stdlib:sources/Constant", x0 - 200, y0 + 40, params={"value": "0.0"})
    d.node("NoBrake", "stdlib:sources/Constant", x0 - 200, y0 + 100, params={"value": "0.0"})
    q_bp = SI["q_bp"]
    legs = GEAR["legs"]
    for k, leg in enumerate(("nose", "left", "right")):
        gl = legs[leg]
        x, y = x0 + 1000 * k, y0
        rx = f"({num(gl['rx'])} + ({xcg} - {num(SI['xcgr'])}) * {num(SI['cbar'])})"
        d.node(f"Mount_{leg}", "stdlib:multibond/FixedTransform3DNeutral", x, y,
               params={"qw": num(q_bp[0]), "qx": num(q_bp[1]), "qy": num(q_bp[2]), "qz": num(q_bp[3]),
                       "x": f"-{rx}", "y": num(-gl["ry"]), "z": num(-gl["rz"])})
        d.bond("Body", "p", f"Mount_{leg}", "b")
        d.node(f"Contact_{leg}", "project:GearContact", x + 200, y,
               params={"rx": rx, "ry": num(gl["ry"]), "rz": num(gl["rz"]), "ground_z": "0.0"})
        d.bond(f"Mount_{leg}", "a", f"Contact_{leg}", "p")
        d.sig("Air", "gB", f"Contact_{leg}", "g")
        d.sig("Logic" if leg == "nose" else "NoSteer", "steer" if leg == "nose" else "y", f"Contact_{leg}", "steer")
        # normal direction: the contact's 1-junction, the 0-junction of the retraction, the strut's 1-junction
        d.junction(f"N_{leg}", 1, x + 400, y - 200)
        d.bond(f"N_{leg}", None, f"Contact_{leg}", "n")
        d.junction(f"Lift_{leg}", 0, x + 520, y - 200)
        d.bond(f"N_{leg}", None, f"Lift_{leg}", None)
        d.node(f"Retract_{leg}", "stdlib:bondgraph/MSf", x + 520, y - 320)
        d.bond(f"Lift_{leg}", None, f"Retract_{leg}", "p")
        d.sig("GearAct", "lift_rate", f"Retract_{leg}", "u")
        d.junction(f"Strut_{leg}", 1, x + 640, y - 200)
        d.bond(f"Lift_{leg}", None, f"Strut_{leg}", None)
        d.node(f"Spring_{leg}", "project:StrutSpring", x + 800, y - 260,
               params={"k": num(gl["k"]), "eps": num(GEAR["gear_eps"])}, starts={"q": ex(st["strut"][leg])})
        d.node(f"Damper_{leg}", "project:StrutDamper", x + 800, y - 160,
               params={"b": num(gl["b"]), "feps": num(GEAR["gear_feps"])})
        d.bond(f"Strut_{leg}", None, f"Spring_{leg}", "j")
        d.bond(f"Strut_{leg}", None, f"Damper_{leg}", "j")
        d.sig(f"Spring_{leg}", "Fk", f"Damper_{leg}", "Fk")
        d.sig(f"Spring_{leg}", "sig", f"Damper_{leg}", "sig")
        # rolling: rolling resistance and the brake
        d.junction(f"X_{leg}", 1, x + 400, y)
        d.bond(f"X_{leg}", None, f"Contact_{leg}", "x")
        d.node(f"Roll_{leg}", "project:WheelFriction", x + 800, y,
               params={"mu_r": num(GEAR["mu_r"]), "mu_s": num(GEAR["mu_brake"]), "vs": num(GEAR["v_roll"])})
        d.bond(f"X_{leg}", None, f"Roll_{leg}", "j")
        d.sig(f"Contact_{leg}", "fn", f"Roll_{leg}", "fn")
        d.sig({"nose": "NoBrake", "left": "brake_lIn", "right": "brake_rIn"}[leg], "y", f"Roll_{leg}", "brake")
        # lateral: the tyre's cornering force
        d.junction(f"Y_{leg}", 1, x + 400, y + 120)
        d.bond(f"Y_{leg}", None, f"Contact_{leg}", "y")
        d.node(f"Side_{leg}", "project:WheelSide", x + 800, y + 120,
               params={"mu_s": num(GEAR["mu_s"]), "vs": num(GEAR["v_side"])})
        d.bond(f"Y_{leg}", None, f"Side_{leg}", "j")
        d.sig(f"Contact_{leg}", "fn", f"Side_{leg}", "fn")
        d.sig(f"Contact_{leg}", "vx", f"Side_{leg}", "vx")
        d.port(f"fn_{leg}", "output", f"Contact_{leg}", "fn", "N")
        d.port(f"q_{leg}", "output", f"Spring_{leg}", "compression", "m")
    d.sig("Spring_left", "Fk", "Logic", "Fk_left")
    d.sig("Spring_right", "Fk", "Logic", "Fk_right")
    # the gear's drag: a wrench in the geometric body frame, through its own mount
    d.node("GearDrag", "project:GearDrag", 1100, 40 - 300,
           params={"cd": num(GEAR["cd_gear"]), "S": num(SI["S"]), "z_arm": num(GEAR["z_drag"])})
    d.sig("GearAct", "pos", "GearDrag", "pos")
    d.sig("Air", "qbar", "GearDrag", "qbar")
    d.sig("Air", "alpha_deg", "GearDrag", "alpha")
    d.sig("Air", "beta_deg", "GearDrag", "beta")
    d.node("GearDragMount", "stdlib:multibond/FixedTransform3DNeutral", 620, -260,
           params={"qw": num(q_bp[0]), "qx": num(q_bp[1]), "qy": num(q_bp[2]), "qz": num(q_bp[3])})
    d.node("GearWrench", "stdlib:multibond/ExternalWrenchSpatial", 820, -260)
    d.bond("GearWrench", "p", "GearDragMount", "a")
    d.bond("GearDragMount", "b", "Body", "p")
    for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
        d.sig("GearDrag", p, "GearWrench", p)
    d.port("gear_pos", "output", "GearAct", "pos")
    d.port("w", "output", "Logic", "w")
    d.port("steer", "output", "Logic", "steer", "rad")
    d.note("**Landing gear (one bond graph per leg, as the Cessna's).** GearContact is the tyre-runway contact: a "
           "modulated transformer from the airframe's multibond to three translational bonds. Normal: the strut spring "
           "(C) and damper (R) on a 1-junction, in series with the retraction (an MSf on a 0-junction, the rate at which "
           "the contact point rises). Rolling: rolling resistance and brake (R). Side: the tyre's cornering force (R). "
           "GearLogic: weight on wheels and nose steering; GearActuator: the 5 s traverse with its ground interlock.",
           x0, y0 - 420, 1400, 60, "blue")


def airframe(xcg: str, start: dict, energy: bool = False, wind: bool = False, mass=None, J=None,
             extra_outputs: bool = False, gear: dict | None = None) -> Diagram:
    """One F-16: inputs el, ail, rdr (deg) and thtl (0..1); xcg is a parameter expression.

    The start values (pose, momentum, power) and the mass and inertia may be numbers or expressions over
    global parameters (the f16-sim model). With wind, the subsystem has the inputs wn, we, wd
    (m/s, north-east-down); without, the air is calm. `gear` adds the landing gear (`landing_gear`)."""
    d = Diagram()
    pose, P, power = start["start_pose"], start["start_P"], start["start_power"]
    mass = SI["mass"] if mass is None else mass
    J = SI["J_principal"] if J is None else J
    # ---- multibond rigid body on a free joint (principal axes) and the external wrench
    d.node("World", "stdlib:multibond/GroundSpatial", 40, 40)
    d.node("Free", "stdlib:spatial/Free3D", 220, 40, starts={k: ex(v) for k, v in pose.items()})
    d.node("Body", "stdlib:spatial/RigidBody3D", 420, 40,
           params={"m": ex(mass), "J": exvec(J), "g0": num(SI["g0"])},
           starts={"inertia/P": exvec(P)})
    q_bp = SI["q_bp"]
    d.node("Mount", "stdlib:multibond/FixedTransform3DNeutral", 620, 40,
           params={"qw": num(q_bp[0]), "qx": num(q_bp[1]), "qy": num(q_bp[2]), "qz": num(q_bp[3])})
    d.node("Wrench", "stdlib:multibond/ExternalWrenchSpatial", 820, 40)
    d.bond("World", "p", "Free", "parent")
    d.bond("Free", "child", "Body", "p")
    d.bond("Wrench", "p", "Mount", "a")
    d.bond("Mount", "b", "Body", "p")
    for k in range(1, 7):
        d.node(f"Se{k}", "stdlib:bondgraph/Se", 220, 160 + 40 * k, params={"e": "0.0"})
        d.bond(f"Se{k}", "p", "Free", f"drive{k}")
    d.sig("Free", "pose", "Body", "g")
    d.note("**Airframe.** RigidBody3D on its principal axes (the book's Jxz tilts them "
           f"{SI['eps'] * 57.29578:.2f} deg from the body x axis); the wrench is applied in the geometric "
           "body frame through the Mount (FixedTransform3DNeutral).", 40, -60, 900, 50, "blue")
    # ---- air data
    d.node("Air", "project:F16AirData", 420, 300,
           params={"eps": num(SI["eps"]), "rho0": num(SI["rho0"]), "klapse": num(SI["klapse"]),
                   "h_trop": num(SI["h_trop"]), "a_gas": num(SI["a_gas"])})
    d.sig("Free", "pose", "Air", "gP")
    d.sig("Body", "V", "Air", "VP")
    if wind:
        for nm in ("wn", "we", "wd"):
            d.port(nm, "input", "Air", nm, "m/s")
    else:
        d.node("Calm", "stdlib:sources/Constant", 220, 300, params={"value": "0.0"})
        for nm in ("wn", "we", "wd"):
            d.sig("Calm", "y", "Air", nm)
    # ---- inputs (pass-through gains so each input can fan out)
    for k, nm in enumerate(("el", "ail", "rdr", "thtl")):
        d.node(f"{nm}In", "stdlib:continuous/Gain", 40, 520 + 60 * k, params={"k": "1.0"})
        d.port(nm, "input", f"{nm}In", "u")
    # ---- tables
    x0, y0 = 700, 300
    lookup2d(d, "CX", TABLES["CX"], x0, y0)
    lookup2d(d, "CM", TABLES["CM"], x0, y0 + 80)
    lookup2d(d, "CL", TABLES["CL"], x0, y0 + 160)
    lookup2d(d, "CN", TABLES["CN"], x0, y0 + 240)
    for k, nm in enumerate(("DLDA", "DLDR", "DNDA", "DNDR")):
        lookup2d(d, nm, TABLES[nm], x0, y0 + 320 + 80 * k)
    lookup1d(d, "CZ", TABLES["CZ"]["x"], TABLES["CZ"]["table"], x0, y0 + 640)
    damp = TABLES["DAMP"]
    for k, nm in enumerate(damp["names"]):
        lookup1d(d, nm, damp["x"], damp["tables"][k], x0 + 200, y0 + 80 * k)
    for nm in ("CX", "CM"):
        d.sig("Air", "alpha_deg", nm, "u")
        d.sig("elIn", "y", nm, "v")
    for nm in ("CL", "CN", "DLDA", "DLDR", "DNDA", "DNDR"):
        d.sig("Air", "alpha_deg", nm, "u")
        d.sig("Air", "beta_deg", nm, "v")
    d.sig("Air", "alpha_deg", "CZ", "u")
    for nm in damp["names"]:
        d.sig("Air", "alpha_deg", nm, "u")
    # ---- engine
    for k, nm in enumerate(("TIdle", "TMil", "TMax")):
        lookup2d(d, nm, TABLES[{"TIdle": "T_IDLE", "TMil": "T_MIL", "TMax": "T_MAX"}[nm]], 420, 560 + 80 * k)
        d.sig("Air", "h", nm, "u")
        d.sig("Air", "mach", nm, "v")
    d.node("Engine", "project:F16Engine", 620, 640, starts={"P": ex(power)})
    d.sig("thtlIn", "y", "Engine", "thtl")
    d.sig("TIdle", "y", "Engine", "tidl")
    d.sig("TMil", "y", "Engine", "tmil")
    d.sig("TMax", "y", "Engine", "tmax")
    # ---- force build-up
    d.node("Forces", "project:F16Forces", 1100, 300,
           params={"S": num(SI["S"]), "b": num(SI["b"]), "cbar": num(SI["cbar"]), "xcg": xcg,
                   "xcgr": num(SI["xcgr"]), "he": num(SI["he"]), "m": ex(mass), "g0": num(SI["g0"])})
    for p in ("vt", "alpha_deg", "beta_deg", "p", "q", "r", "qbar"):
        d.sig("Air", p, "Forces", p)
    d.sig("elIn", "y", "Forces", "el")
    d.sig("ailIn", "y", "Forces", "ail")
    d.sig("rdrIn", "y", "Forces", "rdr")
    d.sig("Engine", "thrust", "Forces", "thrust")
    for nm, port in (("CX", "cx0"), ("CZ", "cz0"), ("CM", "cm0"), ("CL", "cl0"), ("CN", "cn0"),
                     ("DLDA", "dlda"), ("DLDR", "dldr"), ("DNDA", "dnda"), ("DNDR", "dndr")):
        d.sig(nm, "y", "Forces", port)
    for nm in damp["names"]:
        d.sig(nm, "y", "Forces", nm.lower())
    for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
        d.sig("Forces", p, "Wrench", p)
    if energy:
        d.node("Energy", "project:F16Energy", 1100, 40,
               params={"J": vec(SI["J_principal"]), "m": num(SI["mass"]), "g0": num(SI["g0"])})
        d.sig("Free", "pose", "Energy", "gP")
        d.sig("Body", "V", "Energy", "VP")
        d.node("Work", "stdlib:continuous/Integrator", 1300, 40)
        d.sig("Forces", "P_ext", "Work", "u")
    if gear is not None:
        landing_gear(d, xcg, gear)
    for name, node, port, unit in AIRFRAME_OUTPUTS + (SIM_OUTPUTS if extra_outputs else []):
        d.port(name, "output", node, port, unit)
    d.port("pose", "output", "Air", "gB", None, size=7)
    return d


def pose_signals(prefix: str) -> list[str]:
    return [f"{prefix}/Air/gB[{k}]" for k in range(1, 8)]


# --------------------------------------------------------------------------- model 1: open loop
def model_open_loop():
    d = Diagram()
    ol = DESIGN["scenarios"]["open_loop"]
    params = [g("t_end", "15.0", "s", "Run length")]
    for k, a in enumerate(ol):
        lab = a["label"]
        y = 40 + 320 * k
        params.append(g(f"xcg_{lab[1:]}", num(a["xcg"]), None, f"CG of {lab}, fraction of the mean chord"))
        sub = airframe(f"xcg_{lab[1:]}", a, energy=(lab == "A30"))
        sub.subsystem(d, lab, 400, y)
        d.node(f"El{lab}", "stdlib:sources/Constant", 100, y, params={"value": num(a["el"])})
        d.node(f"Thr{lab}", "stdlib:sources/Constant", 100, y + 60, params={"value": num(a["throttle"])})
        d.node(f"Zero{lab}", "stdlib:sources/Constant", 100, y + 120, params={"value": "0.0"})
        d.sig(f"El{lab}", "y", lab, "el")
        d.sig(f"Thr{lab}", "y", lab, "thtl")
        d.sig(f"Zero{lab}", "y", lab, "ail")
        d.sig(f"Zero{lab}", "y", lab, "rdr")
        d.node(f"Grow{lab}", "project:GrowthRate", 700, y, params={"theta0": num(a["theta0"])})
        d.sig(lab, "theta", f"Grow{lab}", "theta")
        d.node(f"Q{lab}", "stdlib:continuous/Gain", 600, y + 80, params={"k": num(3.141592653589793 / 180.0)})
        d.sig(lab, "q", f"Q{lab}", "u")
        d.sig(f"Q{lab}", "y", f"Grow{lab}", "q")
    plots = [
        {"id": "p1", "title": "Angle of attack (deg)", "signals": [f"{a['label']}/Air/alpha_deg" for a in ol]},
        {"id": "p2", "title": "Pitch rate (deg/s)", "signals": [f"{a['label']}/Air/q_deg" for a in ol]},
        {"id": "p3", "title": "Pitch angle (deg)", "signals": [f"{a['label']}/Air/theta_deg" for a in ol]},
        {"id": "p4", "title": "Growth rate q/(theta - theta0) (1/s)", "signals": [f"Grow{a['label']}/lambda" for a in ol]},
        {"id": "p5", "title": "Airspeed (m/s) and altitude (m)",
         "signals": [f"{a['label']}/Air/vt" for a in ol] + [f"{a['label']}/Air/h" for a in ol]},
    ]
    labs = [a["label"] for a in ol]
    bindings = view(d, labs, [0.0, -30.0, 30.0], [f"El{l}/y" for l in labs], ol[0]["start_pose"]["pz"], 1000, 40)
    scene = write_scene("f16-open-loop", list(zip([l.lower() for l in labs], ("grey", "sand", "blue"))),
                        "  f16-open-loop: the three CG positions, A30 (grey, framed), A35 (sand, right) and A38 (blue, left).")
    return model_doc(
        "f16-open-loop",
        "Open loop at the book's trim point (502 ft/s, sea level) for xcg = 0.30, 0.35 and 0.38, each released on "
        "its own mode. Generated by design/build_model.py; see the README.",
        d, settings(15.0, 1501), plots, scene, bindings, params)


# --------------------------------------------------------------------------- the 3D view helpers
TRAIL_N = 12          # dots per trail (the 3D stream takes any number of ids; 12 keep the scene light)
TRAIL_TS = 0.08       # s between dots (a trail of about one second)


def trail_block() -> str:
    """library/F16Trail.jl: a shift register of past positions, sampled every TRAIL_TS (generated:
    the DSL has no arrays of discrete variables)."""
    n, ts = TRAIL_N, TRAIL_TS
    L = ["@block F16Trail begin",
         "    # Scene helper (no physics, generated by design/build_model.py): the dots of a flight-path",
         f"    # trail, {n} past positions of an aircraft {ts:g} s apart, relative to the reference aircraft",
         "    # of the view (see F16View) plus a formation offset. Every tick stores the position in a",
         "    # shift register r1..r" + str(n + 1) + "; between ticks dot k interpolates linearly between the stored",
         "    # samples around t - k*Ts, so the dots glide along the path instead of hopping. Until the",
         "    # register has filled, a dot sits on the aircraft.",
         "    @inputs begin",
         "        g::Vec{7}, [description = \"Pose of the aircraft (qw, qx, qy, qz, x, y, z)\"]",
         "        g0::Vec{7}, [description = \"Pose of the reference aircraft of the view\"]",
         "    end",
         "    @outputs begin"]
    for k in range(1, n + 1):
        L.append(f"        d{k}::Vec{{7}}, [description = \"Pose of dot {k} ({k * ts:g} s back)\"]")
    L += ["    end",
          "    @parameters begin",
          "        dx::Real = 0.0, [unit = \"m\", description = \"Formation offset, x\"]",
          "        dy::Real = 0.0, [unit = \"m\", description = \"Formation offset, y\"]",
          "        dz::Real = 0.0, [unit = \"m\", description = \"Formation offset, z\"]",
          "    end",
          "    @variables begin"]
    for j in range(1, n + 2):
        for c in "xyz":
            L.append(f"        r{j}{c}::Real = 0.0, [unit = \"m\"]")
    L += ["        nfill::Real = 0.0, [description = \"Samples stored so far\"]",
          "        tk::Real = 0.0, [unit = \"s\", description = \"Time of the last tick\"]",
          "        frac::Real = 0.0, [description = \"(t - tk)/Ts\"]",
          "    end",
          f"    @discrete Ts = {ts!r} begin"]
    for j in range(n + 1, 1, -1):
        for c in "xyz":
            L.append(f"        r{j}{c} = r{j - 1}{c}")
    for i, c in enumerate("xyz"):
        L.append(f"        r1{c} = g[{5 + i}]")
    L += [f"        nfill = min(nfill + 1.0, {float(n + 1)!r})",
          "        tk = t",
          "    end",
          "    @equations begin",
          f"        frac ~ (t - tk) / {ts!r}"]
    for k in range(1, n + 1):
        L += [f"        d{k}[1] ~ 1.0", f"        d{k}[2] ~ 0.0", f"        d{k}[3] ~ 0.0", f"        d{k}[4] ~ 0.0"]
        for i, (c, off) in enumerate(zip("xyz", ("dx", "dy", "dz"))):
            L.append(f"        d{k}[{5 + i}] ~ ifelse(nfill > {k + 0.5!r}, r{k + 1}{c} + frac * (r{k}{c} - r{k + 1}{c}), "
                     f"g[{5 + i}]) - g0[{5 + i}] + {off}")
    L += ["    end", "end", ""]
    return "\n".join(L)


FLOOR_PERIOD = 50.0   # m, stripe spacing of the reference floor (the period of the scrolling pattern)
FLOOR_HALF = 300.0    # m, half size of the floor patch (a whole number of periods)
STRIPE_W = 3.0        # m, stripe width
VIEW_LIFT = 8.0       # m, the framed aircraft flies this far above the viewer's 10 m grid at the origin
BOUNDS = 360.0        # m, the invisible markers that centre the view's Fit on the framed aircraft
FLOOR_DEPTH = 150.0   # m below the start altitude of the reference aircraft
STAB_PIVOT = (-5.0, 0.0, 0.05)
TRAIL_RGBA = {"grey": "0.95 0.95 0.98 1", "sand": "1.0 0.85 0.45 1", "blue": "0.55 0.75 1.0 1"}


def floor_links() -> list[str]:
    """The reference floor: link `ground` (the floor, which stays under the framed aircraft) and the
    links `stripes_x` (stripes across x, lines of constant x) and `stripes_y`. Each stripe set scrolls
    along its own axis only, by at most half a period either way (F16View), so the stripes stay on the
    floor and their ends do not move; the stripes sit half a period off the centre, so the shifted
    sets cover the floor from edge to edge. The floor is one stripe width larger than the pattern."""
    n = int(round(FLOOR_HALF / FLOOR_PERIOD))
    side = 2 * FLOOR_HALF + STRIPE_W
    L = ['    <link name="ground">', "      <pose>0 0 0 0 0 0</pose>",
         '      <visual name="floor">', "        <pose>0 0 -0.5 0 0 0</pose>",
         f"        <geometry><box><size>{side:g} {side:g} 1</size></box></geometry>",
         "        <material><diffuse>0.36 0.45 0.33 1</diffuse></material>", "      </visual>", "    </link>"]
    for axis in "xy":
        L += [f'    <link name="stripes_{axis}">', "      <pose>0 0 0 0 0 0</pose>"]
        for k in range(-n, n):
            c = (k + 0.5) * FLOOR_PERIOD
            at, size = ((f"{c:g} 0", f"{STRIPE_W:g} {2 * FLOOR_HALF:g}") if axis == "x"
                        else (f"0 {c:g}", f"{2 * FLOOR_HALF:g} {STRIPE_W:g}"))
            L += [f'      <visual name="stripe_{axis}{k + n}">', f"        <pose>{at} 0.05 0 0 0</pose>",
                  f"        <geometry><box><size>{size} 0.1</size></box></geometry>",
                  "        <material><diffuse>0.62 0.66 0.55 1</diffuse></material>", "      </visual>"]
        L.append("    </link>")
    return L


def floor_bindings(view: str) -> list[dict]:
    """The floor and its two stripe sets; the stripe offsets wrap with the stripe spacing (`period`)."""
    return [{"target": "link:ground", "property": "pose", "signal": [f"{view}/ground[{i}]" for i in range(1, 8)]},
            {"target": "link:stripes_x", "property": "pose", "signal": [f"{view}/stripes_x[{i}]" for i in range(1, 8)],
             "period": [FLOOR_PERIOD, 0.0, 0.0]},
            {"target": "link:stripes_y", "property": "pose", "signal": [f"{view}/stripes_y[{i}]" for i in range(1, 8)],
             "period": [0.0, FLOOR_PERIOD, 0.0]}]


def scene_sdf(name: str, aircraft: list[tuple[str, str]], comment: str) -> str:
    """aircraft: (tag, paint scheme); the first one is the reference the view keeps framed."""
    L = ['<?xml version="1.0"?>', "<!--", comment, "-->", '<sdf version="1.9">', f'  <model name="{name}">',
         *floor_links()]
    # Two invisible specks at opposite corners: the viewer's Fit frames the bounding box of everything
    # shown, and these make it symmetric about the framed aircraft (the origin), so Fit centres on it and
    # zooming in afterwards keeps it in the middle.
    L += ['    <link name="bounds">', "      <pose>0 0 0 0 0 0</pose>"]
    for k, sgn in enumerate((1, -1)):
        L += [f'      <visual name="bound_{k}">', f"        <pose>{sgn * BOUNDS:g} {sgn * BOUNDS:g} {VIEW_LIFT + sgn * BOUNDS:g} 0 0 0</pose>",
              "        <geometry><box><size>0.01 0.01 0.01</size></box></geometry>",
              "        <material><diffuse>0 0 0 0</diffuse></material>", "      </visual>"]
    L.append("    </link>")
    for tag, scheme in aircraft:
        L += [f'    <link name="ac_{tag}">', "      <pose>0 0 0 0 0 0</pose>",
              f'      <visual name="airframe_{tag}">', "        <pose>0 0 0 0 0 0</pose>",
              f"        <geometry><mesh><uri>meshes/f16_body_{scheme}.glb</uri></mesh></geometry>", "      </visual>",
              "    </link>",
              f'    <link name="stabilator_{tag}">', f"      <pose>{STAB_PIVOT[0]:g} {STAB_PIVOT[1]:g} {STAB_PIVOT[2]:g} 0 0 0</pose>",
              f'      <visual name="stabilators_{tag}">', "        <pose>0 0 0 0 0 0</pose>",
              f"        <geometry><mesh><uri>meshes/f16_stab_{scheme}.glb</uri></mesh></geometry>", "      </visual>",
              "    </link>",
              f'    <joint name="stab_{tag}" type="revolute">', f"      <parent>ac_{tag}</parent>",
              f"      <child>stabilator_{tag}</child>", "      <axis><xyz>0 1 0</xyz></axis>", "    </joint>"]
        for k in range(1, TRAIL_N + 1):
            r = 0.6 - 0.02 * k      # unfilled dots sit at the CG, hidden in the fuselage
            L += [f'    <link name="trail_{tag}_{k}">', "      <pose>0 0 0 0 0 0</pose>",
                  f'      <visual name="dot_{tag}_{k}">', "        <pose>0 0 0 0 0 0</pose>",
                  f"        <geometry><sphere><radius>{r:.3f}</radius></sphere></geometry>",
                  f"        <material><diffuse>{TRAIL_RGBA[scheme]}</diffuse></material>", "      </visual>",
                  "    </link>"]
    L += ["  </model>", "</sdf>", ""]
    return "\n".join(L)


SCENE_NOTE = (
    "  Generated by design/build_model.py. Z-up, metres; x north, y west. The view keeps the first aircraft\n"
    "  framed by moving the world instead of the camera: every pose is relative to that aircraft's position\n"
    "  (blocks F16View and F16Trail). The other aircraft fly in formation slots 30 m to the side, so that\n"
    "  aircraft that start together do not overlap. The floor is a reference plane 150 m below the start\n"
    "  altitude of the first aircraft: it follows climbs and descents of up to 100 m (then it stays in view as\n"
    "  an attitude reference), and its 50 m stripes (links stripes_x, stripes_y) scroll with the ground track, each\n"
    "  set along its own axis, wrapped into one stripe spacing (the bindings declare that period, so the view\n"
    "  interpolates across a wrap the short way). The dots behind each aircraft are its flight path over the last second. The\n"
    "  stabilators (links stabilator_*, revolute joints stab_*) turn with the servo deflection: positive\n"
    "  elevator is trailing edge down, a negative rotation about the body y axis (left), hence gain -pi/180.")


def view(d: Diagram, labs: list[str], offsets: list[float], stab_signals: list[str], z0: float, x: float, y: float):
    """View and trail blocks for the aircraft `labs` (the first is the reference); returns bindings."""
    ref = labs[0]
    bindings = []
    for k, (lab, dy) in enumerate(zip(labs, offsets)):
        tag = lab.lower()
        vnode, tnode = f"{lab}View", f"{lab}Trail"
        d.node(vnode, "project:F16View", x, y + 120 * k,
               params={"dy": num(dy), "dz": num(VIEW_LIFT), "depth": num(FLOOR_DEPTH + VIEW_LIFT),
                       "period": num(FLOOR_PERIOD), "z0": num(z0)})
        d.node(tnode, "project:F16Trail", x + 200, y + 120 * k, params={"dy": num(dy), "dz": num(VIEW_LIFT)})
        for nd in (vnode, tnode):
            d.sig(lab, "pose", nd, "g")
            d.sig(ref, "pose", nd, "g0")
        bindings.append({"target": f"link:ac_{tag}", "property": "pose", "signal": [f"{vnode}/pose[{i}]" for i in range(1, 8)]})
        bindings.append({"target": f"joint:stab_{tag}", "property": "position", "signal": stab_signals[k],
                         "gain": -3.141592653589793 / 180.0})
        for j in range(1, TRAIL_N + 1):
            bindings.append({"target": f"link:trail_{tag}_{j}", "property": "pose",
                             "signal": [f"{tnode}/d{j}[{i}]" for i in range(1, 8)]})
    bindings += floor_bindings(f"{ref}View")
    return bindings


def write_scene(name: str, aircraft, comment: str):
    path = EXAMPLE / "scenes" / f"{name}.sdf"
    path.parent.mkdir(exist_ok=True)
    path.write_text(scene_sdf(name, aircraft, comment + "\n" + SCENE_NOTE), encoding="utf-8", newline="\n")
    return f"scenes/{name}.sdf"


# --------------------------------------------------------------------------- flight control
FBW = DESIGN["fbw"]
SC = DESIGN["scenarios"]


def transpose(rows):
    return [list(col) for col in zip(*rows)]


def actuator(el0, a: dict | None = None, label: str = "Elevator") -> Diagram:
    """Stevens & Lewis's servo from stdlib blocks (default the elevator: input limit +-25 deg, a
    20.2 rad/s first-order lag, rate limit +-60 deg/s). Outputs the deflection y (deg) and its
    rate (deg/s). el0 is the start deflection (a number or a global expression)."""
    a = FBW["act"] if a is None else a
    s = Diagram()
    s.node("Travel", "stdlib:continuous/Saturation", 40, 40, params={"lower": num(-a["pos"]), "upper": num(a["pos"])})
    s.node("Mx", "stdlib:continuous/Mux2", 200, 40)
    s.node("Err", "stdlib:continuous/Sum", 340, 40, params={"signs": "[1.0, -1.0]"})
    s.node("Bandwidth", "stdlib:continuous/Gain", 480, 40, params={"k": num(a["w"])})
    s.node("RateLimit", "stdlib:continuous/Saturation", 620, 40, params={"lower": num(-a["rate"]), "upper": num(a["rate"])})
    s.node("Servo", "stdlib:continuous/Integrator", 760, 40, starts={"x": ex(el0)})
    s.sig("Travel", "y", "Mx", "u1")
    s.sig("Servo", "y", "Mx", "u2")
    s.sig("Mx", "y", "Err", "u")
    s.sig("Err", "y", "Bandwidth", "u")
    s.sig("Bandwidth", "y", "RateLimit", "u")
    s.sig("RateLimit", "y", "Servo", "u")
    s.port("u", "input", "Travel", "u")
    s.port("y", "output", "Servo", "y")
    s.port("rate", "output", "RateLimit", "y")
    s.note(f"{label} servo: {a['w']} rad/s lag, +-{a['pos']:g} deg, +-{a['rate']:g} deg/s (Stevens & Lewis).",
           40, -40, 700, 30, "blue")
    return s


def rate_comp(el0: float, comp: dict) -> Diagram:
    """Phase-compensated rate limiter: y' = clamp(du_f/dt + k (u - y), +-rate). The output turns
    round as soon as the command does (the derivative term); the slow k-feedback pulls it back
    onto the command. A plain rate limiter only turns round when the command crosses the output."""
    s = Diagram()
    s.node("In", "stdlib:continuous/Gain", 40, 40, params={"k": "1.0"})
    s.node("Deriv", "stdlib:continuous/FilteredDerivative", 200, 0, params={"Tf": num(comp["tf"])}, starts={"x": num(el0)})
    s.node("Mx1", "stdlib:continuous/Mux2", 200, 100)
    s.node("Err", "stdlib:continuous/Sum", 340, 100, params={"signs": "[1.0, -1.0]"})
    s.node("Pull", "stdlib:continuous/Gain", 480, 100, params={"k": "comp_k"})
    s.node("Mx2", "stdlib:continuous/Mux2", 620, 40)
    s.node("Add", "stdlib:continuous/Sum", 760, 40, params={"signs": "[1.0, 1.0]"})
    s.node("RateLimit", "stdlib:continuous/Saturation", 900, 40, params={"lower": num(-comp["rate"]), "upper": num(comp["rate"])})
    s.node("Out", "stdlib:continuous/Integrator", 1040, 40, starts={"x": num(el0)})
    s.sig("In", "y", "Deriv", "u")
    s.sig("In", "y", "Mx1", "u1")
    s.sig("Out", "y", "Mx1", "u2")
    s.sig("Mx1", "y", "Err", "u")
    s.sig("Err", "y", "Pull", "u")
    s.sig("Deriv", "y", "Mx2", "u1")
    s.sig("Pull", "y", "Mx2", "u2")
    s.sig("Mx2", "y", "Add", "u")
    s.sig("Add", "y", "RateLimit", "u")
    s.sig("RateLimit", "y", "Out", "u")
    s.port("u", "input", "In", "u")
    s.port("y", "output", "Out", "y")
    s.note("Phase-compensated rate limiter: y' = clamp(du/dt + k (u - y), +-60 deg/s).", 40, -60, 700, 30, "blue")
    return s


def pilot(theta0_deg: float, pio: dict) -> Diagram:
    """The aggressive pilot: a pure gain on the attitude error, seen with a 0.25 s delay
    (perception and neuromuscular lag), stick limited to +-1."""
    s = Diagram()
    s.node("In", "stdlib:continuous/Gain", 40, 120, params={"k": "1.0"})
    s.node("Delay", "stdlib:continuous/TransportDelay", 200, 120, params={"initial": num(theta0_deg)},
           constants={"delay_time": num(pio["pilot"]["delay"]), "sample_period": "0.001"})
    s.node("Target", "stdlib:sources/Ramp", 200, 20,
           params={"t_start": "1.0", "initial": num(theta0_deg), "slope": f"pio_amp / {num(SC['fast'])}",
                   "duration": num(SC["fast"])})
    s.node("Mx", "stdlib:continuous/Mux2", 360, 60)
    s.node("Err", "stdlib:continuous/Sum", 500, 60, params={"signs": "[1.0, -1.0]"})
    s.node("Gain", "stdlib:continuous/Gain", 640, 60, params={"k": f"pilot_gain / {num(SC['pio']['q_per_stick'])}"})
    s.node("Stick", "stdlib:continuous/Saturation", 780, 60, params={"lower": "-1.0", "upper": "1.0"})
    s.sig("In", "y", "Delay", "u")
    s.sig("Target", "y", "Mx", "u1")
    s.sig("Delay", "y", "Mx", "u2")
    s.sig("Mx", "y", "Err", "u")
    s.sig("Err", "y", "Gain", "u")
    s.sig("Gain", "y", "Stick", "u")
    s.port("theta", "input", "In", "u")
    s.port("stick", "output", "Stick", "y")
    s.note("Pilot: stick = clamp(K/40 (theta_target - theta(t - 0.25 s)), +-1); K in 1/s.", 40, -40, 700, 30, "blue")
    return s


def gains(d: Diagram, lab: str, x: float, y: float, frozen: dict | None):
    """Ka, Kq, Ki: three stdlib Lookup2D over (qbar in Pa, Mach), or constants."""
    out = {}
    for k, nm in enumerate(("Ka", "Kq", "Ki")):
        node = f"{lab}{nm}"
        if frozen is None:
            lookup2d(d, node, {"x": FBW["qbar_pa"], "y": FBW["mach"], "table": transpose(FBW[nm])}, x, y + 70 * k)
            d.sig(lab, "qbar", node, "u")
            d.sig(lab, "mach", node, "v")
        else:
            d.node(node, "stdlib:sources/Constant", x, y + 70 * k, params={"value": num(frozen[nm])})
        out[nm] = node
    return out


def flight_control(d: Diagram, lab: str, case: dict, xcg: str, x: float, y: float, q_cmd: tuple,
                   frozen=None, comp=None, throttle=None):
    """One F-16 with its fly-by-wire law, servo (and rate-limit compensation)."""
    sub = airframe(xcg, case)
    sub.subsystem(d, lab, x + 700, y)
    d.node(f"{lab}Zero", "stdlib:sources/Constant", x + 500, y + 200, params={"value": "0.0"})
    d.sig(f"{lab}Zero", "y", lab, "ail")
    d.sig(f"{lab}Zero", "y", lab, "rdr")
    if throttle is None:
        d.node(f"{lab}Thr", "stdlib:sources/Constant", x + 500, y + 260, params={"value": num(case["throttle0"])})
    else:
        tr = SC["throttle_ramp"]
        d.node(f"{lab}Thr", "stdlib:sources/Ramp", x + 500, y + 260,
               params={"t_start": num(throttle[0]), "initial": num(case["throttle0"]),
                       "slope": num((throttle[1] - case["throttle0"]) / tr), "duration": num(tr)})
    d.sig(f"{lab}Thr", "y", lab, "thtl")
    gn = gains(d, lab, x, y + 120, frozen)
    law = f"{lab}Law"
    d.node(law, "project:PitchFBW", x + 200, y, params={"kff": num(FBW["kff"]), "u_max": num(FBW["act"]["pos"]),
                                                      "t_aw": num(FBW["t_aw"])}, starts={"xi": num(case["xi0"])})
    d.sig(lab, "alpha", law, "alpha")
    d.sig(lab, "q", law, "q")
    d.sig(q_cmd[0], q_cmd[1], law, "q_cmd")
    d.sig(f"{lab}Zero", "y", law, "w")
    d.sig(f"{lab}Zero", "y", law, "u_ground")
    for nm, node in gn.items():
        d.sig(node, "y", law, nm)
    src = (law, "u")
    if comp is not None:
        rate_comp(case["el0"], comp).subsystem(d, f"{lab}Comp", x + 350, y + 80)
        d.sig(law, "u", f"{lab}Comp", "u")
        src = (f"{lab}Comp", "y")
    actuator(case["el0"]).subsystem(d, f"{lab}Act", x + 500, y)
    d.sig(src[0], src[1], f"{lab}Act", "u")
    d.sig(f"{lab}Act", "y", lab, "el")
    return law


def g_command(d: Diagram, lab: str, x: float, y: float, stick: tuple, limiter: str, rate_mode: bool):
    node = f"{lab}Cmd"
    lim = FBW["limiter"]
    d.node(node, "project:GCommand", x, y, params={
        "g0": num(SI["g0"]), "nz_per_stick": num(FBW["nz_per_stick"]), "q_per_stick": num(SC["pio"]["q_per_stick"]),
        "rate_mode": "1.0" if rate_mode else "0.0", "limiter": limiter, "alpha_max": num(lim["alpha_max"]),
        "nz_max": num(lim["nz_max"]), "k_alim": num(lim["k_alim"]), "k_glim": num(lim["k_glim"])})
    d.sig(stick[0], stick[1], node, "stick")
    for p in ("vt", "alpha", "nz", "gamma", "phi"):
        d.sig(lab, p, node, p)
    return node


def cl_settings(t_end: float):
    return settings(t_end, int(round(t_end * 100)) + 1, reltol=1e-7, abstol=1e-7)


def model_fbw():
    sc = SC["fbw"]
    d = Diagram()
    t0, t1, a = sc["step"]
    params = [g("q_step", num(a), None, "Pitch-rate command step (deg/s)"),
              g("xcg", "0.38", None, "Centre of gravity, fraction of the mean chord (the law is designed for 0.38)")]
    fast = num(SC["fast"])
    d.node("StepOn", "stdlib:sources/Ramp", 40, 40, params={"t_start": num(t0), "slope": f"q_step / {fast}", "duration": fast})
    d.node("StepOff", "stdlib:sources/Ramp", 40, 110, params={"t_start": num(t1), "slope": f"q_step / {fast}", "duration": fast})
    d.node("QMx", "stdlib:continuous/Mux2", 180, 70)
    d.node("QCmd", "stdlib:continuous/Sum", 300, 70, params={"signs": "[1.0, -1.0]"})
    d.sig("StepOn", "y", "QMx", "u1")
    d.sig("StepOff", "y", "QMx", "u2")
    d.sig("QMx", "y", "QCmd", "u")
    for k, case in enumerate(sc["cases"]):
        flight_control(d, case["label"], case, "xcg", 400, 40 + 420 * k, ("QCmd", "y"), frozen=case["frozen"])
    labs = [c["label"] for c in sc["cases"]]
    plots = [
        {"id": "p1", "title": "Pitch rate and command (deg/s)", "signals": ["QCmd/y"] + [f"{l}/Air/q_deg" for l in labs]},
        {"id": "p2", "title": "Angle of attack (deg)", "signals": [f"{l}/Air/alpha_deg" for l in labs]},
        {"id": "p3", "title": "Stabilator (deg)", "signals": [f"{l}Act/Servo/y" for l in labs]},
        {"id": "p4", "title": "Stabilator rate (deg/s)", "signals": [f"{l}Act/RateLimit/y" for l in labs]},
        {"id": "p5", "title": "Load factor (g)", "signals": [f"{l}/Forces/nz" for l in labs]},
        {"id": "p6", "title": "Scheduled gains Ka, Kq, Ki", "signals": [f"{labs[0]}{n}/y" for n in ("Ka", "Kq", "Ki")]},
    ]
    bindings = view(d, labs, [0.0, -30.0], [f"{l}Act/Servo/y" for l in labs], sc["cases"][0]["start_pose"]["pz"],
                    1500, 40)
    scene = write_scene("f16-fbw", list(zip([l.lower() for l in labs], ('grey', 'sand'))), "  f16-fbw: Sched (grey, framed) and Frozen (sand, right).")
    return model_doc(
        "f16-fbw",
        "Gain-scheduled pitch-rate fly-by-wire on the unstable (xcg 0.38) F-16 at 400 ft/s, 25000 ft: the scheduled "
        "law against the same law with the gains of a 1000 ft/s, 2000 ft point frozen. Generated by design/build_model.py.",
        d, cl_settings(sc["t_end"]), plots, scene, bindings, params)


def model_envelope():
    sc = SC["envelope"]
    d = Diagram()
    t_r, d_r = sc["ramp"]
    params = [g("stick", "1.0", None, "Stick pulled (1 = full aft, ramped in over 0.5 s from 1 s)"),
              g("limiter", "1.0", None, "Envelope protection of the 'Protected' aircraft: 1 on, 0 off")]
    d.node("Stick", "stdlib:sources/Ramp", 40, 40,
           params={"t_start": num(t_r), "slope": f"stick / {num(d_r)}", "duration": num(d_r)})
    for k, case in enumerate(sc["cases"]):
        lab = case["label"]
        y = 40 + 420 * k
        cmd = g_command(d, lab, 200, y, ("Stick", "y"), "limiter" if case["limiter"] else "0.0", False)
        flight_control(d, lab, case, "0.38", 400, y, (cmd, "q_cmd"), throttle=(t_r, 1.0))
    labs = [c["label"] for c in sc["cases"]]
    plots = [
        {"id": "p1", "title": "Angle of attack (deg)", "signals": [f"{l}/Air/alpha_deg" for l in labs]},
        {"id": "p2", "title": "Load factor (g)", "signals": [f"{l}/Forces/nz" for l in labs]},
        {"id": "p3", "title": "Pitch rate and command (deg/s)",
         "signals": [f"{l}/Air/q_deg" for l in labs] + [f"{l}Cmd/q_cmd" for l in labs]},
        {"id": "p4", "title": "Stabilator (deg) and rate (deg/s)",
         "signals": [f"{l}Act/Servo/y" for l in labs] + [f"{l}Act/RateLimit/y" for l in labs]},
        {"id": "p5", "title": "Airspeed (m/s)", "signals": [f"{l}/Air/vt" for l in labs]},
        {"id": "p6", "title": "Altitude (m)", "signals": [f"{l}/Air/h" for l in labs]},
    ]
    bindings = view(d, labs, [0.0, -30.0], [f"{l}Act/Servo/y" for l in labs], sc["cases"][0]["start_pose"]["pz"],
                    1500, 40)
    scene = write_scene("f16-envelope", list(zip([l.lower() for l in labs], ('grey', 'sand'))), "  f16-envelope: Protected (grey, framed) and Unprotected (sand, right).")
    return model_doc(
        "f16-envelope",
        "Envelope protection: full aft stick at 900 ft/s, 5000 ft with the alpha/g limiter on and off. "
        "Generated by design/build_model.py.",
        d, cl_settings(sc["t_end"]), plots, scene, bindings, params)


def model_pio():
    sc = SC["pio"]
    d = Diagram()
    p = sc["pilot"]
    params = [g("pilot_gain", num(p["gain_per_s"]), "1/s", "Pilot gain: pitch rate asked per degree of attitude error"),
              g("pio_amp", num(p["amp"]), None, "Attitude change the pilot is asked to capture (deg)"),
              g("comp_k", num(sc["comp"]["k"]), "1/s", "Pull-back gain of the phase-compensated rate limiter")]
    for k, case in enumerate(sc["cases"]):
        lab = case["label"]
        y = 40 + 420 * k
        pilot(case["theta0"] * 57.29577951308232, sc).subsystem(d, f"{lab}Pilot", 40, y)
        d.sig(lab, "theta_deg", f"{lab}Pilot", "theta")
        cmd = g_command(d, lab, 200, y, (f"{lab}Pilot", "stick"), "1.0", True)
        flight_control(d, lab, case, "0.38", 400, y, (cmd, "q_cmd"), comp=sc["comp"] if case["label"] == "Comp" else None)
    labs = [c["label"] for c in sc["cases"]]
    plots = [
        {"id": "p1", "title": "Pitch angle and target (deg)",
         "signals": [f"{l}/Air/theta_deg" for l in labs] + [f"{labs[0]}Pilot/Target/y"]},
        {"id": "p2", "title": "Stabilator rate (deg/s)", "signals": [f"{l}Act/RateLimit/y" for l in labs]},
        {"id": "p3", "title": "Stabilator command and deflection (deg)",
         "signals": [f"{l}Law/u" for l in labs] + [f"{l}Act/Servo/y" for l in labs]},
        {"id": "p4", "title": "Pilot stick", "signals": [f"{l}Pilot/Stick/y" for l in labs]},
        {"id": "p5", "title": "Angle of attack (deg) and load factor (g)",
         "signals": [f"{l}/Air/alpha_deg" for l in labs] + [f"{l}/Forces/nz" for l in labs]},
    ]
    bindings = view(d, labs, [0.0, -30.0], [f"{l}Act/Servo/y" for l in labs], sc["cases"][0]["start_pose"]["pz"],
                    1500, 40)
    scene = write_scene("f16-pio", list(zip([l.lower() for l in labs], ('sand', 'grey'))), "  f16-pio: Plain (sand, framed) and Comp (grey, right).")
    return model_doc(
        "f16-pio",
        "Pilot-induced oscillation: an aggressive pilot (gain, 0.25 s delay) captures a 7 deg pitch change through a "
        "rate-limited stabilator, with a plain rate limit and with a phase-compensated one. Generated by design/build_model.py.",
        d, cl_settings(sc["t_end"]), plots, scene, bindings, params)


# --------------------------------------------------------------------------- model 5: f16-sim
LAT = DESIGN["lat"]
SIMD = DESIGN["sim"]
RAD = 3.141592653589793 / 180.0
D2R = "57.29577951308232"

# The FMU interface of f16-sim: the export markers' names are the FMI names.
SIM_INPUTS = [  # (marker, start value, description)
    ("stick_pitch", "0.0", "pitch stick, -1 full forward .. +1 full aft"),
    ("stick_roll", "0.0", "roll stick, -1 full left .. +1 full right"),
    ("pedals", "0.0", "pedals, -1 full left .. +1 full right"),
    ("throttle", num(SIMD["trim"]["thtl0"]), "throttle, 0 idle .. 0.77 military .. 1 full afterburner"),
    ("wind_n", "0.0", "wind towards north (m/s)"),
    ("wind_e", "0.0", "wind towards east (m/s)"),
    ("wind_d", "0.0", "wind downwards (m/s)"),
    ("gear_cmd", "0.0", "gear handle, 0 up .. 1 down"),
    ("brake_l", "0.0", "left toe brake, 0 .. 1"),
    ("brake_r", "0.0", "right toe brake, 0 .. 1"),
]
SIM_OUTPUT_SOURCES = [  # (marker, node, port)
    ("north_m", "Status", "north"), ("east_m", "Status", "east"), ("alt_m", "F16", "h"),
    ("q_w", "Status", "q_w"), ("q_x", "Status", "q_x"), ("q_y", "Status", "q_y"), ("q_z", "Status", "q_z"),
    ("phi_deg", "Status", "phi_deg"), ("theta_deg", "Status", "theta_deg"), ("psi_deg", "Status", "psi_deg"),
    ("gamma_deg", "Status", "gamma_deg"),
    ("p_dps", "F16", "p"), ("q_dps", "F16", "q"), ("r_dps", "F16", "r"),
    ("u_mps", "F16", "ui"), ("v_mps", "F16", "vi"), ("w_mps", "F16", "wi"), ("vs_mps", "F16", "hdot"),
    ("tas_mps", "F16", "vt"), ("cas_mps", "Status", "cas"), ("mach", "F16", "mach"), ("qbar_pa", "F16", "qbar"),
    ("alpha_deg", "F16", "alpha"), ("beta_deg", "F16", "beta"), ("nz_g", "Status", "nz_total"), ("ny_g", "F16", "ny"),
    ("stab_deg", "StabAct", "y"), ("ail_deg", "AilAct", "y"), ("rdr_deg", "RdrAct", "y"),
    ("power_pct", "F16", "pow"), ("thrust_n", "F16", "thrust"),
    ("p_lim_dps", "LatLaw", "p_lim"), ("nz_cmd_g", "PitchCmd", "nz_cmd"), ("limiter_active", "PitchCmd", "lim_active"),
    ("departed", "Status", "departed"), ("ground_contact", "Status", "ground"),
    ("fn_nose", "F16", "fn_nose"), ("fn_left", "F16", "fn_left"), ("fn_right", "F16", "fn_right"),
    ("on_ground", "Status", "on_ground"), ("steer_rad", "F16", "steer"), ("gear_pos", "F16", "gear_pos"),
]
# Stimulus globals (the model's own test input; the FMU host replaces it)
SIM_STIM = [  # (axis, global prefix, marker, description)
    ("Pitch", "pitch", "stick_pitch", "pitch stick"),
    ("Roll", "roll", "stick_roll", "roll stick"),
    ("Pedal", "pedal", "pedals", "pedals"),
    ("Kick", "kick", None, "rudder kick (deg, added after the law)"),
]
SIM_SWITCHES = [
    ("limiter", "Pitch: alpha/g limiter (1 on, 0 off)"),
    ("turn_comp", "Pitch: turn compensation, holds the altitude in a bank with the stick centred (1 on, 0 off)"),
    ("roll_law", "Roll: roll-rate law (1 on, 0 off: no aileron)"),
    ("yaw_damper", "Yaw: yaw damper (1 on, 0 off)"),
    ("beta_hold", "Yaw: sideslip command and hold (1 on, 0 off)"),
    ("ari", "Yaw: aileron-rudder interconnect (1 on, 0 off)"),
    ("vv_roll", "Roll about the velocity vector (1), or about the body x axis (0)"),
]


def sim_globals() -> list[dict]:
    tr = SIMD["trim"]
    turn = SIMD["turn"]["spec"]
    out = [
        g("vt0", num(tr["vt0"]), "m/s", "Trim airspeed (500 ft/s). The trim globals vt0, h0, alpha0, el0 and thtl0 "
          "go together: change them with a trim (design/simscen.py, or the f16-sim host)"),
        g("h0", num(tr["h0"]), "m", "Trim altitude (10 000 ft)"),
        g("alpha0", num(tr["alpha0"]), "deg", "Trim angle of attack"),
        g("el0", num(tr["el0"]), "deg", "Trim stabilator"),
        g("thtl0", num(tr["thtl0"]), None, "Trim throttle"),
        g("xcg", num(SIMD["xcg"]), None, "Centre of gravity, fraction of the mean chord"),
        g("mass", num(SI["mass"]), "kg", "Mass (the inertia scales with it)"),
        g("gamma0", "0.0", "deg", "Start flight-path angle: the pitch is alpha0 + gamma0 (0: level, or on the runway)"),
        g("gear0", "0.0", None, "Start gear position, 0 up .. 1 down"),
        g("north0", "0.0", "m", "Start position, north"),
        g("east0", "0.0", "m", "Start position, east"),
    ]
    for axis, pre, _, desc in SIM_STIM:
        amp = {"Roll": turn.get("roll_amp", 0.0)}.get(axis, 0.0)
        unit = "deg" if axis == "Kick" else None
        out.append(g(f"{pre}_amp", num(amp), unit, f"Test input: {desc}, held from {pre}_t for {pre}_dur"))
        out.append(g(f"{pre}_t", "1.0", "s", f"Test input: {desc} on at"))
        out.append(g(f"{pre}_dur", num(turn.get(f"{pre}_dur", 0.3 if axis == 'Kick' else 1.0)), "s",
                     f"Test input: {desc} held for"))
    out.append(g("throttle_set", num(turn["throttle_set"]), None, "Test input: throttle from throttle_t on"))
    out.append(g("throttle_t", "1.0", "s", "Test input: throttle change at"))
    out.append(g("throttle2_d", "0.0", None, "Test input: a second throttle change (added)"))
    out.append(g("throttle2_t", "1.0", "s", "Test input: second throttle change at"))
    out.append(g("gear_set", "0.0", None, "Test input: gear handle from gear_t on, 0 up .. 1 down"))
    out.append(g("gear_t", "1.0", "s", "Test input: gear handle moves at"))
    out.append(g("brake_set", "0.0", None, "Test input: both toe brakes from brake_t on, 0 .. 1"))
    out.append(g("brake_t", "1.0", "s", "Test input: brakes on at"))
    for name, desc in SIM_SWITCHES:
        out.append(g(name, "1.0", None, desc))
    return out


def stim_pulse(d: Diagram, axis: str, pre: str, x: float, y: float) -> str:
    """amp (ramp(t; t0) - ramp(t; t0 + dur)), 0.05 s edges: a held stick, pedal or kick."""
    fast = num(SIMD["fast"])
    d.node(f"{axis}On", "stdlib:sources/Ramp", x, y,
           params={"t_start": f"{pre}_t", "slope": f"{pre}_amp / {fast}", "duration": fast})
    d.node(f"{axis}Off", "stdlib:sources/Ramp", x, y + 60,
           params={"t_start": f"{pre}_t + {pre}_dur", "slope": f"{pre}_amp / {fast}", "duration": fast})
    d.node(f"{axis}Mx", "stdlib:continuous/Mux2", x + 140, y + 30)
    d.node(f"{axis}Stim", "stdlib:continuous/Sum", x + 260, y + 30, params={"signs": "[1.0, -1.0]"})
    d.sig(f"{axis}On", "y", f"{axis}Mx", "u1")
    d.sig(f"{axis}Off", "y", f"{axis}Mx", "u2")
    d.sig(f"{axis}Mx", "y", f"{axis}Stim", "u")
    return f"{axis}Stim"


def sim_airframe() -> Diagram:
    eps = num(SI["eps"])
    a0 = f"alpha0 / {D2R}"
    pitch = f"(alpha0 + gamma0) / {D2R}"
    start = {"start_pose": {"qw": f"cos(({eps} - ({pitch})) / 2.0)", "qx": "0.0", "qy": f"sin(({eps} - ({pitch})) / 2.0)",
                            "qz": "0.0", "px": "north0", "py": "-east0", "pz": "h0"},
             "start_P": ["0.0", "0.0", "0.0", f"mass * vt0 * cos({a0} - {eps})", "0.0",
                         f"-(mass * vt0 * sin({a0} - {eps}))"],
             "start_power": "64.94 * thtl0"}
    J = [f"{num(j)} * mass / {num(SI['mass'])}" for j in SI["J_principal"]]
    # A strut's start: the contact point's geometric penetration (GearContact.delta), less what the
    # retraction has lifted it.
    strut = {}
    for leg, gl in GEAR["legs"].items():
        rx = f"({num(gl['rx'])} + (xcg - {num(SI['xcgr'])}) * {num(SI['cbar'])})"
        strut[leg] = (f"-(h0 + sin({pitch}) * {rx} + cos({pitch}) * {num(gl['rz'])}) "
                      f"- {num(GEAR['l_retract'])} * (1.0 - gear0)")
    return airframe("xcg", start, wind=True, mass="mass", J=J, extra_outputs=True,
                    gear={"gear": "gear0", "strut": strut})


def model_sim():
    d = Diagram()
    lim = FBW["limiter"]
    # ---- test stimulus (globals) and the export inputs
    src = {}
    for k, (axis, pre, marker, _) in enumerate(SIM_STIM):
        src[axis] = stim_pulse(d, axis, pre, 40, 40 + 160 * k)
    d.node("ThrStim", "stdlib:sources/Ramp", 40, 700,
           params={"t_start": "throttle_t", "initial": "thtl0",
                   "slope": f"(throttle_set - thtl0) / {num(SIMD['throttle_ramp'])}",
                   "duration": num(SIMD["throttle_ramp"])})
    d.node("Thr2Stim", "stdlib:sources/Ramp", 40, 840,
           params={"t_start": "throttle2_t", "slope": f"throttle2_d / {num(SIMD['throttle_ramp'])}",
                   "duration": num(SIMD["throttle_ramp"])})
    d.node("ThrMx", "stdlib:continuous/Mux2", 180, 760)
    d.node("ThrSum", "stdlib:continuous/Sum", 300, 760, params={"signs": "[1.0, 1.0]"})
    d.sig("ThrStim", "y", "ThrMx", "u1")
    d.sig("Thr2Stim", "y", "ThrMx", "u2")
    d.sig("ThrMx", "y", "ThrSum", "u")
    fast = num(SIMD["fast"])
    d.node("GearStim", "stdlib:sources/Ramp", 40, 920,
           params={"t_start": "gear_t", "initial": "gear0", "slope": f"(gear_set - gear0) / {fast}", "duration": fast})
    d.node("BrakeStim", "stdlib:sources/Ramp", 40, 1000, params={"t_start": "brake_t", "slope": f"brake_set / {fast}",
                                                                 "duration": fast})
    d.node("Calm", "stdlib:sources/Constant", 40, 780, params={"value": "0.0"})
    for k, (marker, start, _) in enumerate(SIM_INPUTS):
        d.node(marker, "stdlib:converters/ExportInputPass", 420, 40 + 110 * k, params={"value": start})
    d.sig(src["Pitch"], "y", "stick_pitch", "u")
    d.sig(src["Roll"], "y", "stick_roll", "u")
    d.sig(src["Pedal"], "y", "pedals", "u")
    d.sig("ThrSum", "y", "throttle", "u")
    for nm in ("wind_n", "wind_e", "wind_d"):
        d.sig("Calm", "y", nm, "u")
    d.sig("GearStim", "y", "gear_cmd", "u")
    d.sig("BrakeStim", "y", "brake_l", "u")
    d.sig("BrakeStim", "y", "brake_r", "u")
    d.note("**Inputs.** The ExportInputPass markers pass the test stimulus (globals *_amp, *_t, *_dur, "
           "throttle_set) through in bg-sim; in the FMU the host drives them.", 40, -60, 700, 40, "blue")
    # ---- the airframe
    sim_airframe().subsystem(d, "F16", 1500, 300)
    d.sig("throttle", "y", "F16", "thtl")
    for nm, port in (("wind_n", "wn"), ("wind_e", "we"), ("wind_d", "wd"), ("gear_cmd", "gear_cmd"),
                     ("brake_l", "brake_l"), ("brake_r", "brake_r"), ("pedals", "pedal")):
        d.sig(nm, "y", "F16", port)
    # ---- pitch: g-command with turn compensation, scheduled pitch-rate law, stabilator servo
    d.node("PitchCmd", "project:PitchCommand", 700, 40, params={
        "g0": num(SI["g0"]), "nz_pull": num(DESIGN["sim_law"]["nz_pull"]), "nz_push": num(DESIGN["sim_law"]["nz_push"]),
        "limiter": "limiter", "turn_comp": "turn_comp", "alpha_max": num(lim["alpha_max"]), "nz_max": num(lim["nz_max"]),
        "nz_min": num(DESIGN["sim_law"]["nz_min"]), "k_alim": num(lim["k_alim"]), "k_glim": num(lim["k_glim"]),
        "k_nzc": num(DESIGN["sim_law"]["k_nzc"]), "nzc_lim": num(DESIGN["sim_law"]["nzc_lim"])})
    d.sig("stick_pitch", "y", "PitchCmd", "stick")
    for p in ("vt", "alpha", "nz", "gamma", "phi", "theta"):
        d.sig("F16", p, "PitchCmd", p)
    for k, nm in enumerate(("Ka", "Kq", "Ki")):
        lookup2d(d, nm, {"x": FBW["qbar_pa"], "y": FBW["mach"], "table": transpose(FBW[nm])}, 700, 200 + 70 * k)
        d.sig("F16", "qbar", nm, "u")
        d.sig("F16", "mach", nm, "v")
    d.node("PitchLaw", "project:PitchFBW", 900, 40,
           params={"alpha_ref": "alpha0", "kff": num(FBW["kff"]), "u_max": num(FBW["act"]["pos"]), "t_aw": num(FBW["t_aw"])},
           starts={"xi": "el0"})
    d.sig("F16", "alpha", "PitchLaw", "alpha")
    d.sig("F16", "q", "PitchLaw", "q")
    d.sig("PitchCmd", "q_cmd", "PitchLaw", "q_cmd")
    for nm in ("Ka", "Kq", "Ki"):
        d.sig(nm, "y", "PitchLaw", nm)
    d.sig("F16", "w", "PitchLaw", "w")
    d.node("StickDirect", "stdlib:continuous/Gain", 700, -40, params={"k": num(-FBW["act"]["pos"])})
    d.sig("stick_pitch", "y", "StickDirect", "u")
    d.sig("StickDirect", "y", "PitchLaw", "u_ground")
    act = LAT["act"]
    actuator("el0", act["el"], "Stabilator").subsystem(d, "StabAct", 1100, 40)
    d.sig("PitchLaw", "y", "StabAct", "u")
    d.sig("StabAct", "y", "F16", "el")
    # ---- roll and yaw: scheduled lateral law, ARI over alpha, aileron and rudder servos
    d.node("LatLaw", "project:LateralFBW", 900, 500, params={
        "p_max": num(LAT["p_max"]), "qbar_full": num(LAT["qbar_full"]), "fq_min": num(LAT["fq_min"]),
        "kn": num(LAT["kn"]), "fn_min": num(LAT["fn_min"]), "beta_per_pedal": num(LAT["beta_per_pedal"]),
        "kff": num(LAT["kff_p"]), "tau_wo": num(LAT["tau_wo"]), "ail_max": num(act["ail"]["pos"]),
        "rdr_max": num(act["rdr"]["pos"]), "t_aw": num(FBW["t_aw"]), "roll_law": "roll_law",
        "yaw_damper": "yaw_damper", "beta_hold": "beta_hold", "ari": "ari", "vv_roll": "vv_roll"})
    d.sig("stick_roll", "y", "LatLaw", "stick")
    d.sig("pedals", "y", "LatLaw", "pedal")
    d.sig("F16", "w", "LatLaw", "w")
    for p in ("alpha", "beta", "p", "r", "nz", "qbar"):
        d.sig("F16", p, "LatLaw", p)
    for k, nm in enumerate(("Kp", "Kip", "Kr", "Kb", "Kib")):
        lookup2d(d, nm, {"x": LAT["qbar_pa"], "y": LAT["mach"], "table": transpose(LAT[nm])}, 700, 500 + 70 * k)
        d.sig("F16", "qbar", nm, "u")
        d.sig("F16", "mach", nm, "v")
        d.sig(nm, "y", "LatLaw", nm)
    lookup1d(d, "Kari", LAT["ari_alpha"], LAT["ari"], 700, 870)
    d.sig("F16", "alpha", "Kari", "u")
    d.sig("Kari", "y", "LatLaw", "Kari")
    actuator(0.0, act["ail"], "Aileron").subsystem(d, "AilAct", 1100, 500)
    d.sig("LatLaw", "ail", "AilAct", "u")
    d.sig("AilAct", "y", "F16", "ail")
    d.node("RdrMx", "stdlib:continuous/Mux2", 1000, 640)
    d.node("RdrSum", "stdlib:continuous/Sum", 1060, 640, params={"signs": "[1.0, 1.0]"})
    d.sig("LatLaw", "rdr", "RdrMx", "u1")
    d.sig(src["Kick"], "y", "RdrMx", "u2")
    d.sig("RdrMx", "y", "RdrSum", "u")
    actuator(0.0, act["rdr"], "Rudder").subsystem(d, "RdrAct", 1100, 640)
    d.sig("RdrSum", "y", "RdrAct", "u")
    d.sig("RdrAct", "y", "F16", "rdr")
    d.note("**Three-axis fly-by-wire.** Pitch: g-command with turn compensation and the alpha/g limiter "
           "(PitchCommand, PitchFBW, Ka/Kq/Ki over qbar and Mach). Roll and yaw: LateralFBW with Kp/Kip/Kr/Kb/Kib "
           "over qbar and Mach and the ARI gain Kari over alpha. Servos: stabilator +-25 deg 60 deg/s, ailerons "
           "+-21.5 deg 80 deg/s, rudder +-30 deg 120 deg/s, all 20.2 rad/s.", 700, -60, 700, 50, "blue")
    # ---- what the host reads
    d.node("Status", "project:F16Status", 1900, 300, params={"mass": "mass", "g0": num(SI["g0"]),
                                                             "stroke": num(GEAR["stroke_max"])})
    d.sig("F16", "pose", "Status", "gB")
    for p in ("phi", "theta", "psi", "gamma", "mach", "pa", "alpha", "beta", "h", "nz", "fn_nose", "fn_left", "fn_right",
              "q_nose"):
        d.sig("F16", p, "Status", p)
    d.sig("F16", "q_left", "Status", "q_left")
    d.sig("F16", "q_right", "Status", "q_right")
    for k, (marker, node, port) in enumerate(SIM_OUTPUT_SOURCES):
        d.node(marker, "stdlib:converters/ExportOutput", 2150 + 200 * (k // 18), 40 + 60 * (k % 18))
        d.sig(node, port, marker, "u")
    # ---- 3D view
    bindings = sim_view(d, 1900, 900)
    plots = [
        {"id": "p1", "title": "Attitude (deg)", "signals": ["Status/phi_deg", "Status/theta_deg", "Status/psi_deg"]},
        {"id": "p2", "title": "Angle of attack and sideslip (deg)", "signals": ["F16/Air/alpha_deg", "F16/Air/beta_deg"]},
        {"id": "p3", "title": "Load factor (g)", "signals": ["F16/Forces/nz", "F16/Forces/ny", "PitchCmd/nz_cmd"]},
        {"id": "p4", "title": "Stability-axis roll rate, command and limit (deg/s)",
         "signals": ["LatLaw/ps", "LatLaw/p_cmd", "LatLaw/p_lim"]},
        {"id": "p5", "title": "Surfaces (deg)", "signals": ["StabAct/Servo/y", "AilAct/Servo/y", "RdrAct/Servo/y"]},
        {"id": "p6", "title": "Airspeed (m/s) and altitude (m)", "signals": ["F16/Air/vt", "F16/Air/h"]},
        {"id": "p7", "title": "Throttle and power (percent)", "signals": ["throttle/y", "F16/Engine/pow"]},
        {"id": "p8", "title": "Wheel loads (N)", "signals": ["F16/Contact_nose/fn", "F16/Contact_left/fn", "F16/Contact_right/fn"]},
        {"id": "p9", "title": "Gear position, weight on wheels", "signals": ["F16/GearAct/pos", "F16/Logic/w"]},
    ]
    turn = SIMD["turn"]
    return model_doc(
        "f16-sim",
        "The flyable F-16: three-axis fly-by-wire (pitch g-command with turn compensation and limiter, roll-rate "
        "command about the velocity vector, yaw damper, ARI, sideslip command) on the Stevens & Lewis airframe, "
        "trimmed at 500 ft/s, 10 000 ft, with the FMU interface of the f16-sim host as export markers. "
        "Generated by design/build_model.py; see the README.",
        d, cl_settings(turn["t_end"]), plots, "scenes/f16-sim.sdf", bindings, sim_globals())


SIM_PIVOTS = {  # body frame (x forward, y left, z up): the hinge point and axis of each surface
    "flap_l": ((-2.419, 1.25, 0.0), (0.153, 0.988, 0.0)),
    "flap_r": ((-2.419, -1.25, 0.0), (-0.153, 0.988, 0.0)),
    "rudder": ((-5.75, 0.0, 0.9), (-0.0797, 0.0, 0.9968)),
}


def sim_scene_sdf() -> str:
    """One aircraft with moving stabilators, flaperons (the ailerons) and rudder."""
    tag, scheme = "sim", "grey"
    base = scene_sdf("f16-sim", [(tag, scheme)], "  f16-sim: the flyable F-16 (grey, framed).\n" + SCENE_NOTE + "\n" + SIM_SCENE_NOTE)
    base = base.replace(f"meshes/f16_body_{scheme}.glb", "meshes/f16sim_body.glb")
    extra = []
    for name, ((x, y, z), (ax, ay, az)) in SIM_PIVOTS.items():
        extra += [f'    <link name="{name}_{tag}">', f"      <pose>{x:g} {y:g} {z:g} 0 0 0</pose>",
                  f'      <visual name="{name}_vis_{tag}">', "        <pose>0 0 0 0 0 0</pose>",
                  f"        <geometry><mesh><uri>meshes/f16sim_{name}.glb</uri></mesh></geometry>", "      </visual>",
                  "    </link>",
                  f'    <joint name="{name}_{tag}_hinge" type="revolute">', f"      <parent>ac_{tag}</parent>",
                  f"      <child>{name}_{tag}</child>", f"      <axis><xyz>{ax:g} {ay:g} {az:g}</xyz></axis>",
                  "    </joint>"]
    return base.replace("  </model>", "\n".join(extra) + "\n  </model>")


SIM_SCENE_NOTE = (
    "  The flaperons (the ailerons) and the rudder turn on their hinge lines (links flap_l_sim, flap_r_sim,\n"
    "  rudder_sim; a positive rotation lifts the trailing edge of a flaperon and moves the rudder's to the\n"
    "  right). A positive aileron rolls left: right trailing edge down, left up, hence gains -pi/180 (right)\n"
    "  and +pi/180 (left); a positive rudder yaws left: trailing edge left, gain -pi/180.")


def sim_view(d: Diagram, x: float, y: float):
    lab, tag = "F16", "sim"
    bindings = view(d, [lab], [0.0], ["StabAct/Servo/y"], SIMD["trim"]["h0"], x, y)
    # the floor of the view follows the trim altitude global
    d.nodes[[n["name"] for n in d.nodes].index(f"{lab}View")]["params"]["z0"] = "h0"
    for b in bindings:
        b["target"] = b["target"].replace("_f16", f"_{tag}")
    bindings += [
        {"target": f"joint:flap_l_{tag}_hinge", "property": "position", "signal": "AilAct/Servo/y", "gain": RAD},
        {"target": f"joint:flap_r_{tag}_hinge", "property": "position", "signal": "AilAct/Servo/y", "gain": -RAD},
        {"target": f"joint:rudder_{tag}_hinge", "property": "position", "signal": "RdrAct/Servo/y", "gain": -RAD},
    ]
    path = EXAMPLE / "scenes" / "f16-sim.sdf"
    path.write_text(sim_scene_sdf(), encoding="utf-8", newline="\n")
    return bindings


# --------------------------------------------------------------------------- dashboards
def slider(cid, title, param, lo, hi, step, decimals, unit=None, size="2x1"):
    o = {"min": lo, "max": hi, "step": step, "decimals": decimals}
    if unit:
        o["unit"] = unit
    return {"id": cid, "kind": "slider", "size": size, "title": title, "parameter": f"global:{param}", "options": o}


def text(cid, title, body, size="2x1"):
    return {"id": cid, "kind": "text", "size": size, "title": title, "options": {"markdown": True, "text": body}}


def plot(cid, title, signals, size="2x2"):
    return {"id": cid, "kind": "plot", "size": size, "title": title, "signals": signals}


def gauge_alpha(cid, sig):
    return {"id": cid, "kind": "gauge", "size": "1x1", "title": "Angle of attack", "signals": [sig],
            "options": {"min": -10.0, "max": 40.0, "decimals": 1, "unit": "deg",
                        "zones": [{"from": -10.0, "to": 25.0, "tone": "good"}, {"from": 25.0, "to": 40.0, "tone": "bad"}]}}


def gauge_nz(cid, sig):
    return {"id": cid, "kind": "gauge", "size": "1x1", "title": "Load factor", "signals": [sig],
            "options": {"min": -3.0, "max": 12.0, "decimals": 2, "unit": "g",
                        "zones": [{"from": -3.0, "to": 9.0, "tone": "good"}, {"from": 9.0, "to": 12.0, "tone": "bad"}]}}


DASHBOARDS = {
    "f16-open-loop": {"autoRerun": True, "cards": [
        text("d1", "Open loop", "Three F-16s trimmed at 502 ft/s at sea level, released on their own mode. Move the **CG of A38** "
             "forward of 0.35 and its short period becomes stable; aft of it the airframe diverges."),
        slider("d2", "CG of A38 (fraction of the mean chord)", "xcg_38", 0.25, 0.45, 0.005, 3),
        plot("d3", "Angle of attack (deg)", ["A30/Air/alpha_deg", "A35/Air/alpha_deg", "A38/Air/alpha_deg"], "4x2"),
        plot("d4", "Growth rate q/(theta - theta0) (1/s)", ["GrowA35/lambda", "GrowA38/lambda"]),
        plot("d5", "Altitude (m)", ["A30/Air/h", "A35/Air/h", "A38/Air/h"]),
    ]},
    "f16-fbw": {"autoRerun": True, "cards": [
        text("d1", "Gain-scheduled FBW", "400 ft/s at 25 000 ft, CG 0.38 (unstable). **Sched** reads its gains from the "
             "(qbar, Mach) tables; **Frozen** keeps the gains of a 1000 ft/s, 2000 ft point. Change the step or the CG."),
        slider("d2", "Pitch-rate step (deg/s)", "q_step", -10.0, 10.0, 0.5, 1, "deg/s"),
        slider("d3", "CG (fraction of the mean chord)", "xcg", 0.30, 0.42, 0.005, 3),
        plot("d4", "Pitch rate and command (deg/s)", ["QCmd/y", "Sched/Air/q_deg", "Frozen/Air/q_deg"], "4x2"),
        plot("d5", "Stabilator (deg)", ["SchedAct/Servo/y", "FrozenAct/Servo/y"]),
        plot("d6", "Stabilator rate (deg/s)", ["SchedAct/RateLimit/y", "FrozenAct/RateLimit/y"]),
        plot("d7", "Angle of attack (deg)", ["Sched/Air/alpha_deg", "Frozen/Air/alpha_deg"]),
        plot("d8", "Airspeed (m/s) and altitude (m)", ["Sched/Air/vt", "Sched/Air/h"]),
    ]},
    "f16-envelope": {"autoRerun": True, "cards": [
        text("d1", "Envelope protection", "Full aft stick at 900 ft/s, 5000 ft. The stick asks for 11 g. **Protected** "
             "holds alpha below 25 deg and nz below 9 g; **Unprotected** over-stresses and then departs."),
        slider("d2", "Stick (1 = full aft)", "stick", 0.0, 1.0, 0.05, 2),
        slider("d3", "Limiter of 'Protected' (1 on, 0 off)", "limiter", 0.0, 1.0, 1.0, 0),
        gauge_alpha("d4", "Protected/Air/alpha_deg"), gauge_nz("d5", "Protected/Forces/nz"),
        gauge_alpha("d6", "Unprotected/Air/alpha_deg"), gauge_nz("d7", "Unprotected/Forces/nz"),
        plot("d8", "Angle of attack (deg)", ["Protected/Air/alpha_deg", "Unprotected/Air/alpha_deg"]),
        plot("d9", "Load factor (g)", ["Protected/Forces/nz", "Unprotected/Forces/nz"]),
        plot("d10", "Pitch rate (deg/s)", ["Protected/Air/q_deg", "Unprotected/Air/q_deg", "ProtectedCmd/q_cmd"]),
        plot("d11", "Stabilator (deg) and rate (deg/s)", ["ProtectedAct/Servo/y", "ProtectedAct/RateLimit/y",
                                                           "UnprotectedAct/Servo/y", "UnprotectedAct/RateLimit/y"]),
        plot("d12", "Airspeed (m/s)", ["Protected/Air/vt", "Unprotected/Air/vt"]),
        plot("d13", "Altitude (m)", ["Protected/Air/h", "Unprotected/Air/h"]),
    ]},
    "f16-pio": {"autoRerun": True, "cards": [
        text("d1", "Pilot-induced oscillation", "An aggressive pilot captures a pitch-attitude change. **Plain**: the "
             "stabilator hits its 60 deg/s rate limit and the loop oscillates. **Comp**: the phase-compensated rate "
             "limiter removes the lag and the oscillation dies out."),
        slider("d2", "Pilot gain (1/s)", "pilot_gain", 0.5, 5.0, 0.1, 1, "1/s"),
        slider("d3", "Attitude change (deg)", "pio_amp", 1.0, 12.0, 0.5, 1, "deg"),
        slider("d4", "Compensator pull-back k (1/s)", "comp_k", 0.1, 10.0, 0.1, 1, "1/s"),
        plot("d5", "Pitch angle and target (deg)", ["Plain/Air/theta_deg", "Comp/Air/theta_deg", "PlainPilot/Target/y"], "4x2"),
        plot("d6", "Stabilator rate (deg/s)", ["PlainAct/RateLimit/y", "CompAct/RateLimit/y"]),
        plot("d7", "Stabilator command and deflection (deg)", ["PlainLaw/u", "PlainAct/Servo/y", "CompLaw/u", "CompAct/Servo/y"]),
        plot("d8", "Angle of attack (deg)", ["Plain/Air/alpha_deg", "Comp/Air/alpha_deg"]),
        plot("d9", "Pilot stick", ["PlainPilot/Stick/y", "CompPilot/Stick/y"]),
    ]},
    "f16-sim": {"autoRerun": True, "cards": [
        text("d1", "Three-axis fly-by-wire", "500 ft/s at 10 000 ft. The default input is a **coordinated 60 deg bank turn**: "
             "a roll-stick pulse banks the aircraft, the turn compensation pulls the 2 g and the yaw law keeps the "
             "sideslip near zero. Move the sticks, the pedals and the throttle, or switch parts of the law off.", "2x2"),
        slider("d2", "Roll stick (pulse from 1 s)", "roll_amp", -1.0, 1.0, 0.01, 2),
        slider("d3", "Roll pulse length (s)", "roll_dur", 0.0, 10.0, 0.1, 1, "s"),
        slider("d4", "Pitch stick (pulse from 1 s)", "pitch_amp", -1.0, 1.0, 0.01, 2),
        slider("d5", "Pedals (pulse from 1 s)", "pedal_amp", -1.0, 1.0, 0.05, 2),
        slider("d6", "Throttle (from 1 s)", "throttle_set", 0.0, 1.0, 0.01, 2),
        slider("d7", "Alpha/g limiter (1 on, 0 off)", "limiter", 0.0, 1.0, 1.0, 0),
        slider("d8", "Roll about the velocity vector (1) or the body axis (0)", "vv_roll", 0.0, 1.0, 1.0, 0),
        slider("d9", "Yaw damper (1 on, 0 off)", "yaw_damper", 0.0, 1.0, 1.0, 0),
        gauge_alpha("d10", "F16/Air/alpha_deg"), gauge_nz("d11", "F16/Forces/nz"),
        plot("d12", "Attitude (deg)", ["Status/phi_deg", "Status/theta_deg", "Status/psi_deg"], "4x2"),
        plot("d13", "Angle of attack and sideslip (deg)", ["F16/Air/alpha_deg", "F16/Air/beta_deg"]),
        plot("d14", "Load factor and command (g)", ["F16/Forces/nz", "PitchCmd/nz_cmd"]),
        plot("d15", "Stability-axis roll rate, command and limit (deg/s)", ["LatLaw/ps", "LatLaw/p_cmd", "LatLaw/p_lim"]),
        plot("d16", "Surfaces (deg)", ["StabAct/Servo/y", "AilAct/Servo/y", "RdrAct/Servo/y"]),
        plot("d17", "Airspeed (m/s) and altitude (m)", ["F16/Air/vt", "F16/Air/h"]),
        slider("d18", "Gear handle (from 1 s; 0 up, 1 down)", "gear_set", 0.0, 1.0, 1.0, 0),
        slider("d19", "Toe brakes (from 1 s)", "brake_set", 0.0, 1.0, 0.05, 2),
        plot("d20", "Wheel loads (N)", ["F16/Contact_nose/fn", "F16/Contact_left/fn", "F16/Contact_right/fn"]),
        plot("d21", "Gear position, weight on wheels", ["F16/GearAct/pos", "F16/Logic/w"]),
    ]},
}


# --------------------------------------------------------------------------- expected.json
def _at(case, key, t):
    ts = case["t"]
    k = min(range(len(ts)), key=lambda i: abs(ts[i] - t))
    assert abs(ts[k] - t) < 1e-9, (t, ts[k])
    return case[key][k]


def _cursor(signal, case, key, t, tol, note=None):
    value = _at(case, key, t)
    if signal == "Status/phi_deg":   # F16Status wraps the bank to (-180, 180]; the references integrate it
        value = (value + 180.0) % 360.0 - 180.0
    c = {"kind": "cursor_value", "signal": signal, "t": t, "value": value, "abs": tol}
    if note:
        c["note"] = note
    return c


NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
           "note": "no algebraic loop, no causality conflict, no event storm"}


def expected() -> dict:
    ol = {a["label"]: a for a in SC["open_loop"]}
    book = DESIGN["trims"]
    checks_ol = [{"kind": "scene_bindings"}, NO_DIAG]
    for lab, a in ol.items():
        for t in (1.0, 3.0, 5.0):
            checks_ol.append(_cursor(f"{lab}/Air/alpha_deg", a, "alpha_deg", t, 1e-4,
                                     "the scipy simulation of the book's F16 subroutine (design/scenarios.py)" if t == 1.0 else None))
            checks_ol.append(_cursor(f"{lab}/Air/q_deg", a, "q_deg", t, 1e-4))
    a38, a35, a30 = ol["A38"], ol["A35"], ol["A30"]
    checks_ol += [
        {"kind": "cursor_value", "signal": "A38/Air/vt", "t": 0.5, "value": _at(a38, "vt", 0.5), "abs": 1e-4,
         "note": f"book trim (Table 3.6-3, xcg 0.38: alpha {book['0.38']['alpha']:.5f} rad, throttle {book['0.38']['throttle']:.4f}, "
                 f"elevator {book['0.38']['el']:.4f} deg) holds the speed in bg-sim"},
        {"kind": "cursor_value", "signal": "A38/Forces/nz", "t": 0.0, "value": 1.0, "abs": 3e-3,
         "note": "trimmed: 1 g (the start is 1e-4 rad of alpha off trim, along the unstable mode)"},
        {"kind": "cursor_value", "signal": "GrowA38/lambda", "t": 1.0, "value": a38["lambda"][0], "rtol": 1e-3,
         "note": "q/(theta - theta0) of the airframe released on its unstable mode reads the linear eigenvalue (xcg 0.38: +0.657 1/s)"},
        {"kind": "cursor_value", "signal": "GrowA35/lambda", "t": 3.0, "value": a35["lambda"][0], "rtol": 2e-3,
         "note": "xcg 0.35 has a slow unstable real pole too (+0.102 1/s, 6-state linearisation)"},
        {"kind": "max_abs", "signal": "A30/Air/q_deg", "from_t": 8.0, "to_t": 15.0,
         "value": max(abs(v) for t, v in zip(a30["t"], a30["q_deg"]) if t >= 8.0 - 1e-9), "rtol": 0.02,
         "note": "xcg 0.30: the short period (-1.204 +- 1.492j) has died out; the phugoid is left"},
        {"kind": "invariant", "tol": 1e-7,
         "terms": [{"signal": "A30/Energy/E", "coeff": 1.0}, {"signal": "A30/Work/y", "coeff": -1.0}],
         "note": "energy ledger: kinetic + potential energy minus the work of the aerodynamic and engine wrench is constant"},
    ]
    # ---- fbw
    sc = SC["fbw"]
    sched, frozen = sc["cases"]
    checks_fbw = [{"kind": "scene_bindings"}, NO_DIAG,
                  {"kind": "step_response", "signal": "Sched/Air/q_deg", "from_t": 1.0, "to_t": 4.0, "step_t": 1.0,
                   "value": sc["step"][2], "initial": 0.0, "max_rise_time": 0.4, "max_overshoot": 0.15,
                   "settle": 0.05, "max_settling_time": 1.0,
                   "note": "the scheduled law at the low-qbar corner: rise 0.21 s, overshoot 7 %, within 5 % after 0.55 s "
                           "(the last 2 % take the integrator 2.4 s)"}]
    for t in (1.2, 1.5, 2.0, 3.0, 5.0):
        for case in (sched, frozen):
            lab = case["label"]
            checks_fbw.append(_cursor(f"{lab}/Air/q_deg", case, "q", t, 2e-3,
                                      "nonlinear scipy reference (design/closedloop.py)" if t == 1.2 else None))
            checks_fbw.append(_cursor(f"{lab}/Air/alpha_deg", case, "alpha", t, 2e-3))
    checks_fbw.append({"kind": "max_abs", "signal": "Frozen/Air/q_deg", "from_t": 1.0, "to_t": 4.0,
                       "value": max(frozen["q"]), "rtol": 2e-3,
                       "note": "the high-qbar gains, frozen, are too weak here: slow rise and about 40 % overshoot"})
    # ---- envelope
    sc = SC["envelope"]
    pro, unp = sc["cases"]
    lim = FBW["limiter"]
    checks_env = [{"kind": "scene_bindings"}, NO_DIAG,
                  {"kind": "max_abs_le", "signal": "Protected/Air/alpha_deg", "value": lim["alpha_max"],
                   "note": "the alpha limiter holds alpha below 25 deg"},
                  {"kind": "max_abs_le", "signal": "Protected/Forces/nz", "value": lim["nz_max"],
                   "note": "the g limiter holds nz below 9 g, although the stick asks for 11 g"},
                  {"kind": "max_abs", "signal": "Unprotected/Forces/nz", "value": max(unp["nz"]), "rtol": 5e-3,
                   "note": "without the limiter: over 10 g"},
                  {"kind": "max_abs", "signal": "Unprotected/Air/alpha_deg", "value": max(unp["alpha"]), "rtol": 5e-3,
                   "note": "and the low-speed end of the loop departs to beyond 80 deg alpha (tables clamped beyond 45 deg)"}]
    for t in (2.0, 4.0, 8.0, 12.0):
        for case in (pro, unp):
            lab = case["label"]
            checks_env.append(_cursor(f"{lab}/Air/alpha_deg", case, "alpha", t, 0.05))
            checks_env.append(_cursor(f"{lab}/Forces/nz", case, "nz", t, 0.02))
    # ---- pio
    sc = SC["pio"]
    plain, comp = sc["cases"]
    checks_pio = [{"kind": "scene_bindings"}, NO_DIAG,
                  {"kind": "max_abs", "signal": "PlainAct/RateLimit/y", "from_t": 6.0, "to_t": 10.0, "value": 60.0, "rtol": 1e-6,
                   "note": "plain: the stabilator is still rate-limited (60 deg/s) after 6 s: a limit cycle"},
                  {"kind": "max_abs_le", "signal": "CompAct/RateLimit/y", "from_t": 6.0, "to_t": 10.0, "value": 10.0,
                   "note": "compensated: the oscillation has died out"},
                  {"kind": "ripple", "signal": "Comp/Air/theta_deg", "from_t": 8.0, "to_t": 10.0, "measure": "pp", "value": 0.5,
                   "note": f"compensated: theta error peak-to-peak 8..10 s {comp['theta_err_pp']['8-10']:.2f} deg"},
                  {"kind": "max_abs", "signal": "Plain/Air/theta_deg", "from_t": 6.0, "to_t": 10.0,
                   "value": max(v for t, v in zip(plain["t"], plain["theta"]) if t >= 6.0 - 1e-9), "rtol": 0.02,
                   "note": "plain: theta still swings +-20 deg about the 11 deg target after 6 s "
                           f"(peak-to-peak per 2 s: {', '.join(f'{v:.0f}' for v in plain['theta_err_pp'].values())} deg)"}]
    for t in (1.5, 2.0, 3.0, 4.0):
        for case in (plain, comp):
            lab = case["label"]
            checks_pio.append(_cursor(f"{lab}/Air/theta_deg", case, "theta", t, 0.1))
    return {"project": "f16",
            "description": "F-16 (Stevens & Lewis, NASA TP-1538 data): open loop, gain-scheduled FBW, envelope protection, "
                           "PIO and the flyable three-axis f16-sim. Numbers come from design/design.json (an independent scipy implementation of the book's "
                           "F16 subroutine and of the same controllers).",
            "models": {"f16-open-loop": {"checks": checks_ol}, "f16-fbw": {"checks": checks_fbw},
                       "f16-envelope": {"checks": checks_env}, "f16-pio": {"checks": checks_pio},
                       **expected_sim()}}


def sim_overrides(name: str) -> dict:
    """The global overrides that turn the f16-sim model (whose defaults are the turn) into scenario `name`."""
    rec = SIMD[name]
    spec = rec["spec"]
    model = {gl["name"]: float(gl["value"]) for gl in sim_globals()}
    trim = SIMD["trim_hialpha"] if rec["point"] != SIMD["point"] else SIMD["trim"]
    want = {}
    for gname in model:
        if gname in ("vt0", "h0", "alpha0", "el0", "thtl0"):
            want[gname] = float(trim[gname])
        elif gname in spec:
            want[gname] = float(spec[gname])
        elif gname == "throttle_set":
            want[gname] = float(trim["thtl0"])
        elif gname == "roll_amp":
            want[gname] = 0.0
        else:
            want[gname] = model[gname]
    return {f"global:{k}": v for k, v in want.items() if abs(v - model[k]) > 1e-12}


def sim_entry(name: str, checks: list) -> dict:
    rec = SIMD[name]
    t_end = rec["t_end"]
    return {"model": "f16-sim", "settings": {"t_end": t_end, "output": {"points": int(round(t_end * 100)) + 1}},
            "overrides": sim_overrides(name), "checks": checks}


def gear_overrides(rec: dict) -> dict:
    """The f16-sim globals of a scenario of design/gear.py, against the model's defaults (the turn)."""
    model = {gl["name"]: float(gl["value"]) for gl in sim_globals()}
    want = {**model, "roll_amp": 0.0, "throttle_set": rec["spec"]["thtl0"]}
    want.update({k: float(v) for k, v in rec["spec"].items() if k in model})
    return {f"global:{k}": v for k, v in want.items() if abs(v - model[k]) > 1e-12}


def gear_entry(name: str, checks: list) -> dict:
    rec = GEAR["scenarios"][name]
    t_end = rec["spec"]["t_end"]
    return {"model": "f16-sim", "settings": {"t_end": t_end, "output": {"points": int(round(t_end * 100)) + 1}},
            "overrides": gear_overrides(rec), "checks": checks}


def expected_gear() -> dict:
    """The gear scenarios of design/gear.py (an independent pitch-plane reference)."""
    st = GEAR["static"]
    ref = "the planar scipy reference with the book's coefficients (design/gear.py)"
    w = GEAR["weight"]
    sc = {k: {**v, **v["series"]} for k, v in GEAR["scenarios"].items()}
    rest, taxi, to, ld = sc["rest"], sc["taxi"], sc["takeoff"], sc["landing"]
    h = "F16/Air/h"
    checks_rest = [
        NO_DIAG,
        _cursor(h, rest, "h", 5.0, 0.002, ref + f": at rest, idle, brakes set. Without thrust the analytic rest is "
                f"h = {st['h']:.4f} m, nose {st['fn']['nose'] / 1e3:.2f} kN ({100 * st['nose_share']:.1f} %), "
                f"mains {st['fn']['left'] / 1e3:.2f} kN each; the idle thrust against the brakes shifts a little to the nose"),
        _cursor("Status/theta_deg", rest, "theta", 5.0, 0.02),
        _cursor("F16/Contact_nose/fn", rest, "fn_nose", 5.0, 0.01 * w, "nose wheel load"),
        _cursor("F16/Contact_left/fn", rest, "fn_left", 5.0, 0.005 * w, "main wheel load"),
        _cursor("F16/Contact_right/fn", rest, "fn_left", 5.0, 0.005 * w, "symmetric"),
        {"kind": "max_abs", "signal": "Status/on_ground", "from_t": 1.0, "value": 1.0, "rtol": 1e-9},
        {"kind": "cursor_value", "signal": "Status/nz_total", "t": 5.0, "value": 1.0, "abs": 0.01,
         "note": "nz_g reads 1 g on the ramp"},
        {"kind": "cursor_value", "signal": "Status/departed", "t": 5.0, "value": 0.0, "abs": 1e-9},
        {"kind": "cursor_value", "signal": "Status/ground", "t": 5.0, "value": 0.0, "abs": 1e-9,
         "note": "ground_contact stays 0 on the wheels"}]
    checks_taxi = [
        NO_DIAG,
        {"kind": "max_abs", "signal": "F16/Air/ui", "value": max(taxi["vx"]), "rtol": 0.01,
         "note": ref + ": the speed when the brakes come on"},
        {"kind": "final_value", "signal": "F16/Air/x", "t": 30.0, "value": taxi["x"][-1], "abs": 3.0,
         "note": "where it stops (reference): the taxi and the stop together"},
        {"kind": "cursor_value", "signal": "F16/Air/ui", "t": 30.0, "value": taxi["vx"][-1], "abs": 0.05,
         "note": "stopped: idle thrust against the brakes creeps at the tanh regularisation speed"}]
    for t in (10.0, 16.0, 18.0):
        checks_taxi.append(_cursor("F16/Air/ui", taxi, "vx", t, 0.1))
    checks_to = [
        NO_DIAG,
        {"kind": "max_abs_le", "signal": "Status/theta_deg", "value": max(to["theta"]) + 1.0},
        {"kind": "final_value", "signal": "F16/GearAct/pos", "t": 26.0, "value": 0.0, "abs": 1e-3,
         "note": "gear up: 5 s traverse (JSBSim f16.xml), then the loop's tail"},
        {"kind": "max_abs_le", "signal": "F16/Contact_left/fn", "from_t": 16.0, "value": 1.0, "note": "airborne"}]
    for t in (5.0, 10.0, 12.0):
        checks_to.append(_cursor("F16/Air/ui", to, "vx", t, 0.1, ref if t == 5.0 else None))
        checks_to.append(_cursor("F16/Air/x", to, "x", t, 0.5))
    for t in (13.0, 14.0, 15.0, 20.0):
        checks_to.append(_cursor("Status/theta_deg", to, "theta", t, 0.5))
        checks_to.append(_cursor(h, to, "h", t, 1.0))
    td = ld["t_first_contact"]
    checks_ld = [
        NO_DIAG,
        {"kind": "max_abs", "signal": "F16/Contact_left/fn", "value": ld["max_fn_left"], "rtol": 0.05,
         "note": ref + f": no flare, {GEAR['touchdown_sink']:.2f} m/s of sink at the wheels: the peak main-wheel load"},
        {"kind": "max_abs", "signal": "F16/Contact_nose/fn", "value": ld["max_fn_nose"], "rtol": 0.1,
         "note": "the nose comes down by itself"},
        {"kind": "cursor_value", "signal": "F16/Air/hdot", "t": td, "value": -GEAR["touchdown_sink"], "abs": 0.1,
         "note": "the sink rate at touchdown"},
        {"kind": "max_abs_le", "signal": "F16/Air/hdot", "value": GEAR["sink_limit"],
         "note": "below the 10 ft/s limit of the gear (secondary source, README), all the way down"},
        {"kind": "max_abs_le", "signal": "F16/Spring_left/compression", "from_t": td, "value": GEAR["stroke_max"]},
        {"kind": "max_abs_le", "signal": "Status/ground", "value": 1e-9, "note": "no crash: ground_contact stays 0"},
        {"kind": "final_value", "signal": "F16/Air/x", "t": ld["spec"]["t_end"], "value": ld["end"]["x"], "abs": 10.0,
         "note": "where it stops"}]
    for t in (5.0, 10.0):
        checks_ld.append(_cursor(h, ld, "h", t, 0.3))
    for t in (td + 1.0, td + 3.0, td + 6.0):
        t = round(t, 1)
        checks_ld.append(_cursor("Status/theta_deg", ld, "theta", t, 0.3))
        checks_ld.append(_cursor("F16/Air/ui", ld, "vx", t, 0.3))
    # nose-wheel steering: the kinematic turn of a tricycle
    stc = GEAR["steer"]
    checks_st = [NO_DIAG,
                 {"kind": "cursor_value", "signal": "F16/Air/r_deg", "t": stc["t"], "value": stc["r_dps"],
                  "abs": 0.15 * abs(stc["r_dps"]),
                  "note": f"{stc['v']:.0f} m/s, pedal {stc['pedal']}: the kinematic yaw rate V tan(steer)/wheelbase "
                          f"= {abs(stc['r_dps']):.2f} deg/s (a slipping tyre gives a little less)"}]
    steer_doc = {"model": "f16-sim", "settings": {"t_end": stc["t_end"], "output": {"points": 1001}},
                 "overrides": stc["overrides"], "checks": checks_st}
    return {"f16-sim-rest": gear_entry("rest", checks_rest), "f16-sim-taxi": gear_entry("taxi", checks_taxi),
            "f16-sim-takeoff": gear_entry("takeoff", checks_to), "f16-sim-landing": gear_entry("landing", checks_ld),
            "f16-sim-steer": steer_doc}


def expected_sim() -> dict:
    """f16-sim: the turn (the model's defaults) and the scenarios of design/simscen.py as overrides."""
    turn = SIMD["turn"]
    h0 = SIMD["trim"]["h0"]
    ref = "the nonlinear three-axis scipy reference (design/sim3.py, design/simscen.py)"
    checks_turn = [{"kind": "scene_bindings"}, NO_DIAG,
                   _cursor("Status/phi_deg", turn, "phi", 4.0, 0.3, ref + ": 60 deg bank after a 1 s roll-stick pulse"),
                   _cursor("Status/phi_deg", turn, "phi", 30.0, 0.5),
                   _cursor("F16/Forces/nz", turn, "nz", 10.0, 0.01, "the turn compensation pulls the 2 g of a level 60 deg turn"),
                   _cursor("F16/Air/h", turn, "h", 10.0, 1.0), _cursor("F16/Air/h", turn, "h", 30.0, 2.0),
                   _cursor("F16/Air/vt", turn, "vt", 30.0, 0.5),
                   {"kind": "max_abs_le", "signal": "F16/Air/beta_deg", "value": 1.0,
                    "note": f"coordinated: |beta| stays below 1 deg (reference {turn['max_abs_beta']:.2f} deg)"},
                   {"kind": "min_ge", "signal": "F16/Air/h", "value": h0 - 80.0,
                    "note": f"altitude within 80 m in a 30 s 60 deg turn with the stick centred (reference: {turn['h_dev']:.0f} m)"},
                   {"kind": "max_abs_le", "signal": "F16/Air/h", "value": h0 + 80.0}]
    for t in (1.5, 2.0, 3.0):
        checks_turn.append(_cursor("LatLaw/ps", turn, "ps", t, 0.2))
    rs = SIMD["roll_step"]
    p_ss = _at(rs, "p_cmd", 1.2)
    checks_rs = [{"kind": "step_response", "signal": "LatLaw/ps", "from_t": 1.0, "to_t": 2.0, "step_t": 1.0,
                  "value": p_ss, "initial": 0.0, "max_rise_time": 0.6, "max_overshoot": 0.1, "settle": 0.05,
                  "max_settling_time": 1.0,
                  "note": f"roll-rate step: the stability-axis roll rate follows the {p_ss:.1f} deg/s command of a quarter stick"}]
    for t in (1.2, 1.5, 2.0, 3.0, 4.0):
        checks_rs.append(_cursor("LatLaw/ps", rs, "ps", t, 0.2, ref if t == 1.2 else None))
        checks_rs.append(_cursor("Status/phi_deg", rs, "phi", t, 0.2))
    fr = SIMD["full_roll"]
    checks_fr = [{"kind": "max_abs_le", "signal": "LatLaw/ps", "value": 1.03 * fr["max_p_lim"],
                  "note": f"full stick: the roll rate stays at the limit ({fr['max_p_lim']:.0f} deg/s from nz and qbar)"},
                 {"kind": "max_abs", "signal": "LatLaw/ps", "value": fr["max_ps"], "rtol": 0.01},
                 {"kind": "max_abs_le", "signal": "F16/Air/beta_deg", "value": 2.0,
                  "note": f"full-stick roll: |beta| below 2 deg (reference {fr['max_abs_beta']:.2f})"},
                 {"kind": "max_abs_le", "signal": "AilAct/Servo/y", "value": 21.5 + 1e-6},
                 {"kind": "max_abs_le", "signal": "RdrAct/Servo/y", "value": 30.0 + 1e-6},
                 {"kind": "max_abs_le", "signal": "F16/Air/alpha_deg", "value": 25.0}]
    for t in (1.5, 2.0, 3.0, 5.0):
        checks_fr.append(_cursor("Status/phi_deg", fr, "phi", t, 0.5))
    modes = SIMD["modes"]
    win = {"from_t": 2.0, "to_t": 12.0, "offset": "linear"}

    def damp(mode, zeta_abs, wn_rtol, note):
        m = modes[mode]
        return {"kind": "damping", "signal": "F16/Air/beta_deg", **win, "zeta": m["zeta"], "zeta_abs": zeta_abs,
                "wn": m["wn"], "wn_rtol": wn_rtol, "note": note}
    checks_do = [damp("open_loop", 0.01, 0.02,
                      f"dutch roll of the airframe after a 5 deg rudder kick: the linearised mode zeta {modes['open_loop']['zeta']:.3f}, "
                      f"wn {modes['open_loop']['wn']:.2f} rad/s (design/simscen.py)")]
    checks_dy = [damp("yaw_damper", 0.03, 0.05,
                      f"with the yaw damper alone: zeta {modes['yaw_damper']['zeta']:.3f}, wn {modes['yaw_damper']['wn']:.2f} rad/s")]
    for case, chk in (("dutch_open", checks_do), ("dutch_yd", checks_dy)):
        for t in (2.0, 4.0, 8.0):
            chk.append(_cursor("F16/Air/beta_deg", SIMD[case], "beta", t, 0.02))
    df = SIMD["dutch_full"]
    checks_df = [{"kind": "max_abs_le", "signal": "F16/Air/beta_deg", "from_t": 4.0, "value": 0.1,
                  "note": f"the full law (zeta {modes['full']['zeta']:.2f}): the kick has died out after 3 s"}]
    for t in (1.5, 2.0, 3.0):
        checks_df.append(_cursor("F16/Air/beta_deg", df, "beta", t, 0.02))
    hv, hb = SIMD["hialpha_vv"], SIMD["hialpha_body"]
    checks_hv = [{"kind": "max_abs_le", "signal": "F16/Air/beta_deg", "value": 1.2 * hv["max_abs_beta"],
                  "note": f"260 ft/s, alpha {SIMD['trim_hialpha']['alpha0']:.1f} deg, full stick: rolling about the velocity "
                          f"vector keeps |beta| at {hv['max_abs_beta']:.1f} deg"}]
    checks_hb = [{"kind": "max_abs", "signal": "F16/Air/beta_deg", "value": hb["max_abs_beta"], "rtol": 0.05,
                  "note": f"the same roll about the body axis (no ARI): |beta| {hb['max_abs_beta']:.1f} deg, alpha trades into sideslip"}]
    for t in (2.0, 3.0):
        checks_hv.append(_cursor("Status/phi_deg", hv, "phi", t, 0.5))
        checks_hb.append(_cursor("Status/phi_deg", hb, "phi", t, 0.5))
    pl = SIMD["pull"]
    checks_pl = [{"kind": "max_abs_le", "signal": "F16/Air/alpha_deg", "value": 27.0,
                  "note": f"full aft stick: the limiter holds alpha near 25 deg (reference peak {pl['max_alpha']:.1f} deg)"},
                 {"kind": "max_abs_le", "signal": "F16/Forces/nz", "value": 9.0},
                 {"kind": "max_abs", "signal": "PitchCmd/lim_active", "value": 1.0, "rtol": 1e-9,
                  "note": "the HUD's limit flag comes on"}]
    for t in (1.5, 2.0, 3.0):
        checks_pl.append(_cursor("F16/Air/alpha_deg", pl, "alpha", t, 0.1))
    # The X-EX1 export sweep (examples/export_checks.py) drives the inputs with steps, a ramp, a
    # chirp and a PRBS within these ranges: small ones, so 30 s of it stays in the envelope.
    export = {"inputs": {"stick_pitch": {"min": -0.1, "max": 0.1}, "stick_roll": {"min": -0.1, "max": 0.1},
                         "pedals": {"min": -0.1, "max": 0.1}, "throttle": {"min": 0.1, "max": 0.5},
                         "wind_n": {"min": -2.0, "max": 2.0}, "wind_e": {"min": -2.0, "max": 2.0},
                         "wind_d": {"min": -2.0, "max": 2.0}, "gear_cmd": {"min": 0.0, "max": 0.0},
                         "brake_l": {"min": 0.0, "max": 1.0}, "brake_r": {"min": 0.0, "max": 1.0}},
              "interface": {"inputs": [m for m, _, _ in SIM_INPUTS],
                            "outputs": [m for m, _, _ in SIM_OUTPUT_SOURCES]},
              "note": "the FMU of apps/f16-sim; its own acceptance (the host's settings and tunables, four "
                      "manoeuvres) is examples/export_f16_check.py"}
    checks_turn.append({"kind": "max_abs_le", "signal": "F16/Contact_nose/fn", "value": 1.0,
                        "note": "gear up: the retracted legs carry nothing (the strut's smooth contact leaves a few mN)"})
    return {**expected_gear(),
            "f16-sim": {"checks": checks_turn, "export": export},
            "f16-sim-roll-step": sim_entry("roll_step", checks_rs),
            "f16-sim-full-roll": sim_entry("full_roll", checks_fr),
            "f16-sim-dutch-open": sim_entry("dutch_open", checks_do),
            "f16-sim-dutch-yaw-damper": sim_entry("dutch_yd", checks_dy),
            "f16-sim-dutch-full": sim_entry("dutch_full", checks_df),
            "f16-sim-hialpha-vv": sim_entry("hialpha_vv", checks_hv),
            "f16-sim-hialpha-body": sim_entry("hialpha_body", checks_hb),
            "f16-sim-pull": sim_entry("pull", checks_pl)}


def main() -> int:
    models = {"f16-open-loop": model_open_loop(), "f16-fbw": model_fbw(), "f16-envelope": model_envelope(),
              "f16-pio": model_pio(), "f16-sim": model_sim()}
    (EXAMPLE / "library" / "F16Trail.jl").write_text(trail_block(), encoding="utf-8", newline="\n")
    for block in CESSNA_BLOCKS:
        shutil.copyfile(EXAMPLE.parent / "cessna" / "library" / f"{block}.jl", EXAMPLE / "library" / f"{block}.jl")
    for name, doc in models.items():
        doc["dashboard"] = DASHBOARDS[name]
        path = EXAMPLE / "models" / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "f16", "models": list(models),
            "libraryDir": "library", "scenesDir": "scenes"}
    (EXAMPLE / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    (EXAMPLE / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
