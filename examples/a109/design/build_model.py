# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the a109 models, scenes and expected.json from `design/design.json`.

    uv run examples/a109/design/design.py        # first
    uv run examples/a109/design/build_model.py

The airframe (a subsystem, `airframe()`; in a109-open-loop instances of the library subsystem
`library/HeliAirframe.bgsub.json`) is the same in every model: the multibond rigid body on a
free joint with one modulated wrench source per component at its own point (main rotor, fuselage,
tail rotor, tailplane, fin), the drivetrain as a rotational bond graph (rotor inertia, mast
0-junction coupled to the airframe yaw through ShaftAxis, gearbox junction with the engine, the
losses and the tail-rotor gear), the governor, and the air-data tap. The models differ in what
flies it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
SI = DESIGN["si"]
RAD = math.pi / 180.0
D2R = "57.29577951308232"


def num(v: float) -> str:
    return repr(float(v))


def vec(values) -> str:
    return "[" + ", ".join(repr(float(v)) for v in values) + "]"


def ex(v) -> str:
    """A number, or an expression over global parameters as it is."""
    return v if isinstance(v, str) else num(v)


def exvec(values) -> str:
    return "[" + ", ".join(ex(v) for v in values) + "]"


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
        if isinstance(block, dict):
            b = block
        elif block in ("0", "1"):
            b = {"junction": block}
        else:
            b = {"ref": block}
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
        # Connection ids carry the subsystem's name: the compiler names the virtual (e, f) pair
        # of a junction-to-junction bond after the bare connection id (not scoped by the
        # subsystem path), so two copies of the airframe with the same ids would share those
        # variables (E103). Unique ids per copy keep them apart.
        diagram = self.doc()
        for c in diagram["connections"]:
            c["id"] = f"{name}_{c['id']}"
        parent.node(name, {"subsystem": {"ports": self.ports, "diagram": diagram}}, x, y)
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
AIRFRAME_OUTPUTS = [  # (port name, node, node port)
    ("u", "Air", "u"), ("v", "Air", "v"), ("w", "Air", "w"), ("p", "Air", "p"), ("q", "Air", "q"), ("r", "Air", "r"),
    ("p_deg", "Air", "p_deg"), ("q_deg", "Air", "q_deg"), ("r_deg", "Air", "r_deg"),
    ("phi", "Air", "phi"), ("theta", "Air", "theta"), ("psi", "Air", "psi"),
    ("phi_deg", "Air", "phi_deg"), ("theta_deg", "Air", "theta_deg"), ("psi_deg", "Air", "psi_deg"),
    ("h", "Air", "h"), ("hdot", "Air", "hdot"), ("vt", "Air", "vt"), ("kts", "Air", "kts"), ("beta_deg", "Air", "beta_deg"),
    ("ui", "Air", "ui"), ("vi", "Air", "vi"), ("wi", "Air", "wi"), ("gs", "Air", "gs"), ("x", "Air", "x"), ("y", "Air", "y"),
    ("a1", "MR", "a1_deg"), ("b1", "MR", "b1_deg"), ("om", "OmRotor", "y"), ("nr", "Gov", "nr"),
    ("power_hp", "Gov", "power_hp"), ("thrust", "MR", "T"),
]

COMPONENTS = [  # (name, block, position key, outputs that drive the wrench)
    ("MR", "project:MainRotor", "HUB", ("tx", "ty", "tz", "fx", "fy", "fz")),
    ("Fus", "project:Fuselage", "FUS", ("tx", "ty", "tz", "fx", "fy", "fz")),
    ("TR", "project:TailRotor", "TR", ("fy",)),
    ("HT", "project:Tailplane", "HT", ("fz",)),
    ("VT", "project:Fin", "VT", ("fy",)),
]


# The landing gear of a109-sim (ours; the report has no gear): the tyre contact points of the
# tricycle gear in the body frame (x forward, y left, z up, from the CG), the bottoms of the
# scene's wheels (nose wheel 1.9 m ahead, main wheels 0.8 m behind and 0.95 m to each side, the
# wheel centres 1.12 m below the CG, radius 0.2 m).
GEAR = {"nose": (1.9, 0.0, -1.32), "left": (-0.8, 0.95, -1.32), "right": (-0.8, -0.95, -1.32)}
# ContactPoint (Hunt-Crossley, Hertz exponent 3/2): tyre plus strut. k xref = 8.4 kN at the
# reference deflection xref = 4 cm (about a main wheel's static load); c damps about 0.3 of
# critical in heave. The friction (mu 0.7, regularised over vs = 2 cm/s) holds the parked
# helicopter: the wheels are braked and the nose wheel locked, so the gear acts as a skid on the
# pad (it creeps at a fraction of vs under the rotor's torque). eps = 1 mm: the smooth positive
# part of the penetration, eps^2/(2 (r - d)), loses its digits in contact when eps << d (the
# integrator then sees noise); 1 mm keeps it exact to ~1e-12 and leaves ~1e-6 N at 0.5 m.
GEAR_CONTACT = {"k": 2.1e5, "xref": 0.04, "c": 1.5, "mu": 0.7, "vs": 0.02, "bt": 0.0, "eps": 1e-3, "feps": 1e-6}
WOW_LOAD = 0.2       # fraction of the weight on the gear at which weight-on-wheels is complete


def airframe(start: dict, rpm_mode="rpm_mode", ge="0.0", engine=False, wind=False, smooth="0.0", gear=False) -> Diagram:
    """One A109: inputs th0, B1, A1, thtr (deg; and `on`, the engines, with engine=True; wn, we, wd
    with wind=True). `start` holds the pose, momentum, flapping, rotor speed and governor
    integrator start values (numbers or expressions over globals). gear=True adds the landing
    gear: three ContactPoints on a ContactSurface (the ground, z = 0) and the outputs fn_nose,
    fn_left, fn_right (the wheel loads), gear_load (their sum) and wow (weight on wheels, 0 .. 1)."""
    d = Diagram()
    q_bp = SI["q_bp"]
    pose, P = start["pose"], start["P"]
    # ---- multibond rigid body on a free joint (principal axes)
    d.node("World", "stdlib:multibond/GroundSpatial", 40, 40)
    d.node("Free", "stdlib:spatial/Free3D", 220, 40, starts={k: ex(v) for k, v in pose.items()})
    d.node("Body", "stdlib:spatial/RigidBody3D", 420, 40,
           params={"m": num(SI["m"]), "J": vec(SI["J_principal"]), "g0": num(SI["g0"])},
           starts={"inertia/P": exvec(P)})
    d.bond("World", "p", "Free", "parent")
    d.bond("Free", "child", "Body", "p")
    for k in range(1, 7):
        d.node(f"Se{k}", "stdlib:bondgraph/Se", 220, 160 + 40 * k, params={"e": "0.0"})
        d.bond(f"Se{k}", "p", "Free", f"drive{k}")
    d.sig("Free", "pose", "Body", "g")
    d.note("**Airframe.** RigidBody3D on its principal axes (the report's Ixz tilts them "
           f"{SI['eps'] * 180 / math.pi:.2f} deg from the body x axis). Each component is a modulated wrench "
           "source at its own point: ExternalWrenchSpatial bonded through a FixedTransform3DNeutral that "
           "carries the offset, so the bond graph forms r x F.", 40, -60, 900, 50, "blue")
    # ---- air data
    d.node("Air", "project:HeliAirData", 420, 360,
           params={"eps": num(SI["eps"]), "rho0": num(SI["rho0"]), "h_hub": num(SI["H"]["HUB"])})
    d.sig("Free", "pose", "Air", "gP")
    d.sig("Body", "V", "Air", "VP")
    if wind:
        for nm in ("wn", "we", "wd"):
            d.port(nm, "input", "Air", nm, "m/s")
    else:
        d.node("Calm", "stdlib:sources/Constant", 220, 360, params={"value": "0.0"})
        for nm in ("wn", "we", "wd"):
            d.sig("Calm", "y", "Air", nm)
    # ---- control inputs (deg -> rad)
    for k, nm in enumerate(("th0", "B1", "A1", "thtr")):
        d.node(f"{nm}In", "stdlib:continuous/Gain", 40, 600 + 60 * k, params={"k": num(RAD)})
        d.port(nm, "input", f"{nm}In", "u")
    # ---- the components and their wrenches
    mr, tr, fus, ht, vt = SI["mr"], SI["tr"], SI["fus"], SI["ht"], SI["vt"]
    d.node("MR", "project:MainRotor", 700, 300, params={**{k: num(v) for k, v in mr.items()}, "rpm_mode": rpm_mode,
                                                        "ge": ge, "smooth": smooth},
           starts={"a1": ex(start["a1"]), "b1": ex(start["b1"])})
    d.node("Power", "project:RotorPower", 900, 300, params={k: num(v) for k, v in SI["power"].items()})
    d.node("Fus", "project:Fuselage", 700, 500, params={k: num(v) for k, v in fus.items()})
    d.node("TR", "project:TailRotor", 700, 700, params={**{k: num(v) for k, v in tr.items()}, "rpm_mode": rpm_mode})
    d.node("HT", "project:Tailplane", 700, 900, params={**{k: num(v) for k, v in ht.items()}, "smooth": smooth})
    d.node("VT", "project:Fin", 700, 1050, params={**{k: num(v) for k, v in vt.items()}, "smooth": smooth})
    for nm, port in (("u", "u"), ("v", "v"), ("w", "w"), ("p", "p"), ("q", "q"), ("rho", "rho"), ("hgt", "hgt")):
        d.sig("Air", nm, "MR", port)
    d.sig("th0In", "y", "MR", "th0")
    d.sig("B1In", "y", "MR", "B1")
    d.sig("A1In", "y", "MR", "A1")
    for nm in ("u", "v", "w", "rho"):
        d.sig("Air", nm, "Fus", nm)
    d.sig("MR", "vi", "Fus", "vi")
    for nm in ("u", "v", "w", "p", "q", "r", "rho"):
        d.sig("Air", nm, "TR", nm)
    d.sig("thtrIn", "y", "TR", "thtr")
    for nm in ("u", "v", "w", "q", "rho"):
        d.sig("Air", nm, "HT", nm)
    d.sig("MR", "vi", "HT", "vi")
    for nm in ("u", "v", "r", "rho"):
        d.sig("Air", nm, "VT", nm)
    d.sig("TR", "vi", "VT", "vi_tr")
    d.sig("MR", "T", "Power", "T")
    d.sig("MR", "vi_eff", "Power", "vi")
    d.sig("MR", "om_a", "Power", "om")
    d.sig("Air", "u", "Power", "u")
    d.sig("Air", "v", "Power", "v")
    d.sig("Air", "hdot", "Power", "hdot")
    d.sig("Air", "rho", "Power", "rho")
    d.sig("Fus", "p_para", "Power", "p_para")
    d.node("Zero", "stdlib:sources/Constant", 900, 1200, params={"value": "0.0"})
    for k, (name, _, key, outs) in enumerate(COMPONENTS):
        pos = SI["pos"][key]
        wn, mn = f"W{name}", f"M{name}"
        d.node(wn, "stdlib:multibond/ExternalWrenchSpatial", 1150, 100 + 200 * k)
        # the mount: the principal frame P (child, b) seen from the component frame (parent, a),
        # which is the body frame B moved to the component point: offset -r (B axes)
        d.node(mn, "stdlib:multibond/FixedTransform3DNeutral", 1350, 100 + 200 * k,
               params={"qw": num(q_bp[0]), "qx": num(q_bp[1]), "qy": num(q_bp[2]), "qz": num(q_bp[3]),
                       "x": num(-pos[0]), "y": num(-pos[1]), "z": num(-pos[2])})
        d.bond(wn, "p", mn, "a")
        d.bond(mn, "b", "Body", "p")
        for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
            if p in outs:
                d.sig(name, p, wn, p)
            else:
                d.sig("Zero", "y", wn, p)
    d.note("**Components** (modulated sources): the report's main rotor (flapping, thrust/inflow), fuselage, "
           "tail rotor, tailplane and fin, in SI. Their forces act at the hub, the fuselage point, the "
           "tail-rotor hub, the tailplane and the fin.", 700, 200, 600, 50, "blue")
    # ---- drivetrain: the rotational bond graph (ours)
    dr = SI["drive"]
    x0, y0 = 1700, 300
    d.node("MShaft", "stdlib:multibond/FixedTransform3DNeutral", x0, y0,
           params={"qw": num(q_bp[0]), "qx": num(q_bp[1]), "qy": num(q_bp[2]), "qz": num(q_bp[3])})
    d.node("Shaft", "project:ShaftAxis", x0, y0 + 120, params={"kx": "0.0", "ky": "0.0", "kz": "1.0"})
    d.bond("Body", "p", "MShaft", "b")
    d.bond("MShaft", "a", "Shaft", "p")
    d.node("Mast", "0", x0 + 200, y0 + 240)
    d.node("RotorJ", "1", x0 + 400, y0 + 240)
    d.node("Rotor", "stdlib:bondgraph/I", x0 + 600, y0 + 160, params={"i": num(dr["J"])},
           starts={"P": ex(start["om_P"]) if "om_P" in start else num(dr["J"] * start["om"])})
    d.node("AeroLoad", "stdlib:bondgraph/MSe", x0 + 600, y0 + 320, params={"gain": "-1.0"})
    d.node("OmRotor", "stdlib:bondgraph/Df", x0 + 600, y0 + 400)
    d.node("GearJ", "1", x0, y0 + 400)
    d.node("Engine", "stdlib:bondgraph/MSe", x0 - 200, y0 + 400, params={"gain": "1.0"})
    d.node("Loss", "stdlib:bondgraph/MSe", x0 - 200, y0 + 480, params={"gain": "-1.0"})
    d.node("OmGear", "stdlib:bondgraph/Df", x0 - 200, y0 + 560)
    d.node("TRGear", "stdlib:bondgraph/TF", x0, y0 + 560, params={"n": num(dr["n_tr"])})
    d.node("TRJ", "1", x0, y0 + 680)
    d.node("TRLoad", "stdlib:bondgraph/MSe", x0 + 200, y0 + 680, params={"gain": "-1.0"})
    d.node("OmTR", "stdlib:bondgraph/Df", x0 + 200, y0 + 760)
    d.bond("GearJ", None, "Mast", None)
    d.bond("Mast", None, "RotorJ", None)
    d.bond("Shaft", "s", "Mast", None)
    d.bond("RotorJ", None, "Rotor", "p")
    d.bond("AeroLoad", "p", "RotorJ", None)
    d.bond("RotorJ", None, "OmRotor", "p")
    d.bond("Engine", "p", "GearJ", None)
    d.bond("Loss", "p", "GearJ", None)
    d.bond("GearJ", None, "OmGear", "p")
    d.bond("GearJ", None, "TRGear", "p1")
    d.bond("TRGear", "p2", "TRJ", None)
    d.bond("TRLoad", "p", "TRJ", None)
    d.bond("TRJ", None, "OmTR", "p")
    d.sig("Power", "torque", "AeroLoad", "u")
    d.sig("TR", "torque", "TRLoad", "u")
    d.sig("OmRotor", "y", "MR", "om")
    d.sig("OmTR", "y", "TR", "om")
    d.node("PLoss", "stdlib:sources/Constant", x0 - 500, y0 + 480, params={"value": num(dr["p_loss"])})
    d.node("LossDiv", "stdlib:continuous/Divide", x0 - 350, y0 + 480)
    d.sig("PLoss", "y", "LossDiv", "u1")
    d.sig("OmGear", "y", "LossDiv", "u2")
    d.sig("LossDiv", "y", "Loss", "u")
    d.node("Gov", "project:Governor", x0 - 350, y0 + 300,
           params={"om_ref": num(dr["om0"]), "Kp": num(dr["Kp"]), "Ki": num(dr["Ki"]), "p_max": num(dr["p_max"])},
           starts={"xi": ex(start["xi"])})
    d.sig("OmGear", "y", "Gov", "om")
    d.sig("Gov", "q", "Engine", "u")
    if engine:
        d.port("on", "input", "Gov", "on")
    else:
        d.node("EngOn", "stdlib:sources/Constant", x0 - 500, y0 + 300, params={"value": "1.0"})
        d.sig("EngOn", "y", "Gov", "on")
    d.note("**Drivetrain** (rotational bond graph, ours): the rotor inertia on its 1-junction with the "
           "aerodynamic torque; the mast 0-junction (common torque) whose flows make rotor speed = gearbox "
           "speed + airframe yaw rate (ShaftAxis, the reaction torque on the airframe); the gearbox "
           "1-junction with the engine torque (Governor), the transmission losses and the tail-rotor gear "
           "(TF) to the tail-rotor junction and its torque.", x0 - 500, y0 - 120, 900, 70, "blue")
    if gear:
        x0, y0 = 1150, 1300
        d.node("Ground", "stdlib:contact/ContactSurface", x0 - 300, y0 + 500)
        d.node("GearMux", "stdlib:continuous/Mux3", x0 + 500, y0 + 500)
        d.node("GearLoad", "stdlib:continuous/Sum", x0 + 650, y0 + 500, params={"signs": "[1.0, 1.0, 1.0]"},
               constants={"N": 3})
        for k, (leg, r) in enumerate(GEAR.items()):
            y = y0 + 160 * k
            d.node(f"Wheel_{leg}", "stdlib:spatial/LocalPose3D", x0 - 300, y,
                   params={"x": num(r[0]), "y": num(r[1]), "z": num(r[2])})
            d.node(f"WheelPose_{leg}", "stdlib:multibond/ComposePose3D", x0 - 100, y)
            d.sig("Air", "gB", f"WheelPose_{leg}", "gp")
            d.sig(f"Wheel_{leg}", "g", f"WheelPose_{leg}", "gl")
            d.node(f"Tyre_{leg}", "stdlib:contact/ContactPoint", x0 + 100, y,
                   params={name: num(v) for name, v in GEAR_CONTACT.items()})
            d.sig(f"WheelPose_{leg}", "g", f"Tyre_{leg}", "g")
            d.sig("Ground", "o", f"Tyre_{leg}", "o")
            d.sig("Ground", "fr", f"Tyre_{leg}", "fr")
            d.node(f"MTyre_{leg}", "stdlib:multibond/FixedTransform3DNeutral", x0 + 300, y,
                   params={"qw": num(q_bp[0]), "qx": num(q_bp[1]), "qy": num(q_bp[2]), "qz": num(q_bp[3]),
                           "x": num(-r[0]), "y": num(-r[1]), "z": num(-r[2])})
            d.bond("Body", "p", f"MTyre_{leg}", "b")
            d.bond(f"MTyre_{leg}", "a", f"Tyre_{leg}", "p")
            d.sig(f"Tyre_{leg}", "f_n", "GearMux", f"u{k + 1}")
        d.sig("GearMux", "y", "GearLoad", "u")
        d.node("WowGain", "stdlib:continuous/Gain", x0 + 800, y0 + 500,
               params={"k": num(1.0 / (WOW_LOAD * SI["m"] * SI["g0"]))})
        d.node("Wow", "stdlib:continuous/Saturation", x0 + 950, y0 + 500, params={"lower": "0.0", "upper": "1.0"})
        d.sig("GearLoad", "y", "WowGain", "u")
        d.sig("WowGain", "y", "Wow", "u")
        d.note("**Landing gear** (a109-sim, ours). Each wheel is a ContactPoint (Hunt-Crossley normal force, "
               "regularised Coulomb friction: braked wheels) on the ground plane (ContactSurface, z = 0), mounted at "
               "its point through a FixedTransform3DNeutral like the component sources; LocalPose3D and ComposePose3D "
               "give its pose. Weight on wheels: the gear load over a fifth of the weight, saturated to 0 .. 1 "
               "(the SCAS fades out on the ground).", x0 - 300, y0 - 120, 900, 60, "blue")
    for name, node, port in AIRFRAME_OUTPUTS:
        d.port(name, "output", node, port)
    if gear:
        for leg in GEAR:
            d.port(f"fn_{leg}", "output", f"Tyre_{leg}", "f_n", "N")
        d.port("gear_load", "output", "GearLoad", "y", "N")
        d.port("wow", "output", "Wow", "y")
    d.port("pose", "output", "Air", "gB", None, size=7)
    d.port("a1r", "output", "MR", "a1r")
    d.port("b1r", "output", "MR", "b1r")
    return d


# --------------------------------------------------------------------------- the library airframe
# a109-open-loop flies instances of library/HeliAirframe.bgsub.json: airframe() in calm air without the
# gear, laid out on its own (AIRFRAME_LAYOUT). a109-sim keeps its inline airframe (gear, wind, engines).
AIRFRAME = "HeliAirframe"
AIRFRAME_POSE = ("qw", "qx", "qy", "qz", "px", "py", "pz")
AIRFRAME_PINS = {"params": ["MR/rpm_mode", "TR/rpm_mode"],
                 "starts": [f"Free/{k}" for k in AIRFRAME_POSE] + ["Body/inertia/P", "MR/a1", "MR/b1", "Rotor/P", "Gov/xi"]}
_DX, _DY = 1760, 300   # the drivetrain's origin (MShaft), the relative layout of airframe()
AIRFRAME_LAYOUT = {  # node -> (x, y) inside the definition
    "th0In": (0, 300), "B1In": (0, 400), "A1In": (0, 500), "thtrIn": (0, 600),
    "World": (200, 0), "Free": (360, 0), "Body": (520, 0),
    **{f"Se{k}": (180 + 60 * k, 140) for k in range(1, 7)},
    "Calm": (200, 300), "Air": (360, 300),
    "MR": (600, 300), "Fus": (600, 460), "TR": (600, 620), "HT": (600, 780), "VT": (600, 940),
    "Power": (780, 300), "Zero": (780, 1100),
    **{f"W{c[0]}": (960, 300 + 160 * k) for k, c in enumerate(COMPONENTS)},
    **{f"M{c[0]}": (1120, 300 + 160 * k) for k, c in enumerate(COMPONENTS)},
    **{n: (_DX + dx, _DY + dy) for n, (dx, dy) in {
        "MShaft": (0, 0), "Shaft": (0, 120), "Mast": (200, 240), "RotorJ": (400, 240), "Rotor": (600, 160),
        "AeroLoad": (600, 320), "OmRotor": (600, 400), "GearJ": (0, 400), "Engine": (-200, 400), "Loss": (-200, 480),
        "OmGear": (-200, 560), "TRGear": (0, 560), "TRJ": (0, 680), "TRLoad": (200, 680), "OmTR": (200, 760),
        "PLoss": (-500, 480), "LossDiv": (-350, 480), "Gov": (-350, 300), "EngOn": (-500, 300)}.items()},
}
AIRFRAME_NOTES = [(0, -100), (600, 200), (_DX - 500, _DY - 120)]   # airframe, components, drivetrain


def _box(node: dict) -> tuple[float, float, float, float]:
    """The node's footprint in the editor with its name below: junctions and bond-graph letters 40 px,
    other blocks a 60 px square."""
    b = node["block"]
    small = "junction" in b or b.get("ref", "").startswith("stdlib:bondgraph/")
    s = 40 if small else 60
    return node["position"]["x"], node["position"]["y"], s, s + 20


def check_layout(nodes: list[dict], notes: list[dict], label: str, gap: float = 10.0) -> None:
    boxes = [(n["name"], *_box(n)) for n in nodes] + [(f"note {a['id']}", a["x"], a["y"], a["w"], a["h"]) for a in notes]
    for i, (na, xa, ya, wa, ha) in enumerate(boxes):
        for nb, xb, yb, wb, hb in boxes[i + 1:]:
            if xa < xb + wb + gap and xb < xa + wa + gap and ya < yb + hb + gap and yb < ya + ha + gap:
                raise SystemExit(f"{label}: {na} overlaps {nb}")


def _airframe_start(st: dict) -> dict:
    return {"pose": st["pose"], "P": st["P"], "a1": st["a1"], "b1": st["b1"], "om": st["om"], "xi": st["xi"]}


AIRFRAME_START = _airframe_start(DESIGN["open_loop"][0]["start"])   # the hover trim


def _pinned_starts(start: dict) -> dict:
    """The pinned start values of airframe(start), as airframe() writes them."""
    out = {f"Free/{k}": ex(start["pose"][k]) for k in AIRFRAME_POSE}
    out["Body/inertia/P"] = exvec(start["P"])
    out["MR/a1"], out["MR/b1"] = ex(start["a1"]), ex(start["b1"])
    out["Rotor/P"] = num(SI["drive"]["J"] * start["om"])
    out["Gov/xi"] = ex(start["xi"])
    return out


def airframe_definition() -> dict:
    """library/HeliAirframe.bgsub.json: airframe() in calm air at the hover trim; the global `rpm_mode`
    of the model reaches it through the pinned MR/rpm_mode and TR/rpm_mode (default 1, the drivetrain's)."""
    assert set(AIRFRAME_START["pose"]) == set(AIRFRAME_POSE)
    d = airframe(AIRFRAME_START, rpm_mode="1.0")
    doc = d.doc()
    for n in doc["nodes"]:
        x, y = AIRFRAME_LAYOUT[n["name"]]
        n["position"] = {"x": x, "y": y}
    assert len(AIRFRAME_LAYOUT) == len(doc["nodes"])
    for a, (x, y) in zip(doc["annotations"], AIRFRAME_NOTES, strict=True):
        a["x"], a["y"] = x, y
    check_layout(doc["nodes"], doc["annotations"], AIRFRAME)
    ports = doc.pop("subsystemPorts")
    return {"format": "bgsim.subsystem", "name": AIRFRAME,
            "description": ("One A109 in calm air (Heffley & Mnich, NASA CR-177476): the rigid body on a free joint with "
                            "a wrench source per component (main rotor, fuselage, tail rotor, tailplane, fin), the "
                            "drivetrain as a rotational bond graph, the governor and the air data. Inputs th0, B1, A1, "
                            "thtr (deg). Pin the start state with Free/qw .. Free/pz, Body/inertia/P, MR/a1, MR/b1, "
                            "Rotor/P and Gov/xi (default: the hover trim) and the rotor speed the aerodynamics see with "
                            "MR/rpm_mode and TR/rpm_mode (1 the drivetrain's, 0 the nominal). Generated by "
                            "design/build_model.py."),
            "ports": ports, "diagram": doc, "pins": AIRFRAME_PINS}


def airframe_instance(parent: Diagram, name: str, x: float, y: float, start: dict) -> str:
    """An instance of the library airframe: it sets the start values where they differ from the definition's."""
    own, base = _pinned_starts(start), _pinned_starts(AIRFRAME_START)
    starts = {k: v for k, v in own.items() if v != base[k]}
    parent.node(name, f"project:{AIRFRAME}", x, y, params={"MR/rpm_mode": "rpm_mode", "TR/rpm_mode": "rpm_mode"},
                starts=starts)
    return name


# --------------------------------------------------------------------------- the 3D view
VIEW_LIFT = 6.0       # m, the framed helicopter flies this far above the viewer's grid at the origin
FLOOR_PERIOD = 10.0   # m, stripe spacing of the floor (the period of the scrolling pattern)
FLOOR_HALF = 60.0    # m, half size of the floor patch (a whole number of periods)
STRIPE_W = 1.0       # m, stripe width
BOUNDS = 70.0        # m, the invisible markers (beyond the floor) that centre the view's Fit on the framed helicopter
PAINT = {"red": "0.72 0.12 0.12 1", "white": "0.92 0.92 0.94 1", "blue": "0.16 0.32 0.62 1",
         "yellow": "0.93 0.74 0.18 1", "grey": "0.55 0.57 0.6 1"}


def heli_visuals(tag: str, paint: str) -> list[str]:
    """The airframe of one A109 from simple solids, in the body frame (x forward, y left, z up,
    origin at the CG): cabin, nose, tail cone, boom, engine fairing, fin, tailplane, mast and the
    retractable tricycle gear (shown down). Dimensions follow the report's stations and the TCDS
    (length 10.7 m over the fuselage, hub 1.52 m above the CG, tail rotor 6.56 m aft)."""
    body = PAINT[paint]
    dark = "0.15 0.16 0.18 1"
    glass = "0.35 0.5 0.62 0.85"
    V = []

    def vis(name, pose, geom, color):
        V.extend([f'      <visual name="{name}_{tag}">', f"        <pose>{pose}</pose>",
                  f"        <geometry>{geom}</geometry>", f"        <material><diffuse>{color}</diffuse></material>",
                  "      </visual>"])
    cyl_x = "0 1.5708 0"     # a cylinder along x
    vis("cabin", f"0.35 0 0.05 {cyl_x}", "<cylinder><radius>0.82</radius><length>3.2</length></cylinder>", body)
    vis("nose", "2.0 0 -0.05 0 0 0", "<sphere><radius>0.78</radius></sphere>", body)
    vis("windscreen", "2.25 0 0.35 0 0 0", "<sphere><radius>0.55</radius></sphere>", glass)
    vis("aft", "-1.25 0 0.0 0 0 0", "<sphere><radius>0.8</radius></sphere>", body)
    vis("cone", f"-2.4 0 0.25 {cyl_x}", "<cylinder><radius>0.42</radius><length>1.8</length></cylinder>", body)
    vis("boom", f"-4.6 0 0.45 {cyl_x}", "<cylinder><radius>0.2</radius><length>3.4</length></cylinder>", body)
    vis("fairing", "-0.2 0 0.95 0 0 0", "<box><size>2.6 1.1 0.45</size></box>", body)
    vis("mast", f"0.02 0 1.25 0 {SI['mr']['IS']:.4f} 0", "<cylinder><radius>0.1</radius><length>0.6</length></cylinder>", dark)
    vis("fin", "-6.2 0 1.0 0 -0.45 0", "<box><size>0.9 0.06 1.3</size></box>", body)
    vis("ventral", "-6.25 0 0.0 0 0.45 0", "<box><size>0.6 0.06 0.6</size></box>", body)
    vis("stab", "-5.0 0 0.45 0 0 0", "<box><size>0.6 2.6 0.05</size></box>", body)
    vis("stripe", f"0.35 0 -0.2 {cyl_x}", "<cylinder><radius>0.83</radius><length>0.5</length></cylinder>", "0.95 0.95 0.95 1")
    # tricycle gear, down: nose wheel and two main wheels
    for nm, (x, y) in (("nosegear", (1.9, 0.0)), ("maingear_l", (-0.8, 0.95)), ("maingear_r", (-0.8, -0.95))):
        vis(nm + "_strut", f"{x} {y} -0.85 0 0 0", "<box><size>0.08 0.08 0.5</size></box>", dark)
        vis(nm + "_wheel", f"{x} {y} -1.12 1.5708 0 0", "<cylinder><radius>0.2</radius><length>0.14</length></cylinder>", dark)
    return V


def rotor_visuals(tag: str, at=(0.0, 0.0, 0.0)) -> list[str]:
    """Main rotor link (frame: the tip-path plane at the hub, z its normal): 4 blades, hub and a
    faint disc; tail rotor link (frame: the tail-rotor hub, y the axis): 2 blades and a faint disc."""
    R, Rt = SI["mr"]["R"], SI["tr"]["R"]
    blade = "0.12 0.12 0.13 1"
    hx, hz = SI["pos"]["HUB"][0], SI["pos"]["HUB"][2]
    tx, tz = SI["pos"]["TR"][0], SI["pos"]["TR"][2]
    L = [f'    <link name="rotor_{tag}">',
         f"      <pose>{at[0] + hx:.4f} {at[1]:.4f} {at[2] + hz:.4f} 0 {SI['mr']['IS']:.4f} 0</pose>"]
    for k in range(4):
        a = k * math.pi / 2
        cx, cy = 0.5 * R * math.cos(a), 0.5 * R * math.sin(a)
        L += [f'      <visual name="blade{k}_{tag}">', f"        <pose>{cx:.4f} {cy:.4f} 0.05 0 0 {a:.5f}</pose>",
              f"        <geometry><box><size>{R:.3f} 0.34 0.03</size></box></geometry>",
              f"        <material><diffuse>{blade}</diffuse></material>", "      </visual>"]
    L += [f'      <visual name="hub_{tag}">', "        <pose>0 0 0.05 0 0 0</pose>",
          "        <geometry><cylinder><radius>0.28</radius><length>0.22</length></cylinder></geometry>",
          "        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>", "      </visual>",
          f'      <visual name="disc_{tag}">', "        <pose>0 0 0.05 0 0 0</pose>",
          f"        <geometry><cylinder><radius>{R:.3f}</radius><length>0.01</length></cylinder></geometry>",
          "        <material><diffuse>0.8 0.85 0.9 0.12</diffuse></material>", "      </visual>", "    </link>",
          f'    <link name="tailrotor_{tag}">', f"      <pose>{at[0] + tx:.4f} {at[1] + 0.25:.4f} {at[2] + tz:.4f} 0 0 0</pose>"]
    for k in range(2):
        a = k * math.pi
        cx, cz = 0.5 * Rt * math.cos(a), 0.5 * Rt * math.sin(a)
        L += [f'      <visual name="trblade{k}_{tag}">', f"        <pose>{cx:.4f} 0 {cz:.4f} 0 {-a:.5f} 0</pose>",
              f"        <geometry><box><size>{Rt:.3f} 0.03 0.16</size></box></geometry>",
              f"        <material><diffuse>{blade}</diffuse></material>", "      </visual>"]
    L += [f'      <visual name="trdisc_{tag}">', "        <pose>0 0 0 1.5708 0 0</pose>",
          f"        <geometry><cylinder><radius>{Rt:.3f}</radius><length>0.01</length></cylinder></geometry>",
          "        <material><diffuse>0.8 0.85 0.9 0.15</diffuse></material>", "      </visual>", "    </link>"]
    return L


def floor_links(ground_z: float) -> list[str]:
    """The floor: link `ground` (the floor, which stays under the framed helicopter) and the links
    `stripes_x` (stripes across x, lines of constant x) and `stripes_y`. Each stripe set scrolls along
    its own axis only, by at most half a period either way (HeliView), so the stripes stay on the floor
    and their ends do not move; the stripes sit half a period off the centre, so the shifted sets cover
    the floor from edge to edge. The floor is one stripe width larger than the pattern."""
    n = int(round(FLOOR_HALF / FLOOR_PERIOD))
    side = 2 * FLOOR_HALF + STRIPE_W
    L = ['    <link name="ground">', f"      <pose>0 0 {ground_z:g} 0 0 0</pose>",
         '      <visual name="floor">', "        <pose>0 0 -0.5 0 0 0</pose>",
         f"        <geometry><box><size>{side:g} {side:g} 1</size></box></geometry>",
         "        <material><diffuse>0.36 0.45 0.33 1</diffuse></material>", "      </visual>", "    </link>"]
    for axis in "xy":
        L += [f'    <link name="stripes_{axis}">', f"      <pose>0 0 {ground_z:g} 0 0 0</pose>"]
        for k in range(-n, n):
            c = (k + 0.5) * FLOOR_PERIOD
            at, size = ((f"{c:g} 0", f"{STRIPE_W:g} {2 * FLOOR_HALF:g}") if axis == "x"
                        else (f"0 {c:g}", f"{2 * FLOOR_HALF:g} {STRIPE_W:g}"))
            L += [f'      <visual name="stripe_{axis}{k + n}">', f"        <pose>{at} 0.02 0 0 0</pose>",
                  f"        <geometry><box><size>{size} 0.04</size></box></geometry>",
                  "        <material><diffuse>0.62 0.66 0.55 1</diffuse></material>", "      </visual>"]
        L.append("    </link>")
    return L


def scene_sdf(name: str, helis: list[tuple[str, str]], comment: str, slots=None, ground_z=0.0) -> str:
    """helis: (tag, paint); the first is the reference the view keeps framed."""
    L = ['<?xml version="1.0"?>', "<!--", comment, "-->", '<sdf version="1.9">', f'  <model name="{name}">',
         *floor_links(ground_z)]
    L += ['    <link name="bounds">', "      <pose>0 0 0 0 0 0</pose>"]
    for k, sgn in enumerate((1, -1)):
        L += [f'      <visual name="bound_{k}">', f"        <pose>{sgn * BOUNDS:g} {sgn * BOUNDS:g} {VIEW_LIFT + sgn * BOUNDS:g} 0 0 0</pose>",
              "        <geometry><box><size>0.01 0.01 0.01</size></box></geometry>",
              "        <material><diffuse>0 0 0 0</diffuse></material>", "      </visual>"]
    L.append("    </link>")
    # the link poses before a run: the start of the view (each helicopter in its slot, VIEW_LIFT up)
    for k, (tag, paint) in enumerate(helis):
        dx, dy = (slots or [(0.0, 0.0)] * len(helis))[k]
        at = (dx, dy, VIEW_LIFT)
        L += [f'    <link name="heli_{tag}">', f"      <pose>{dx:g} {dy:g} {VIEW_LIFT:g} 0 0 0</pose>"] + heli_visuals(tag, paint) + ["    </link>"]
        L += rotor_visuals(tag, at)
    L += ["  </model>", "</sdf>", ""]
    return "\n".join(L)


SCENE_NOTE = (
    "  Generated by design/build_model.py. Z-up, metres; x north, y west. The view keeps the first helicopter\n"
    "  framed by moving the world instead of the camera (block HeliView): every pose is relative to that\n"
    "  helicopter's position, the others fly in formation slots beside it, and a helicopter in steady forward\n"
    "  flight is shown relative to its trimmed path. The floor (link ground) stays under the framed helicopter;\n"
    "  its 10 m stripes (links stripes_x, stripes_y) scroll with the ground track, each set along its own axis,\n"
    "  wrapped into one stripe spacing (the bindings declare that period, so the view interpolates across a wrap\n"
    "  the short way). The airframe is built from simple solids (cabin, nose,\n"
    "  tail cone, boom, fin, tailplane, engine fairing, tricycle gear). The main rotor (link rotor_*) sits at\n"
    "  the hub, tilted with the shaft (6.3 deg forward) and with the flapping a1, b1; the blades and the tail\n"
    "  rotor (link tailrotor_*) turn at a tenth of their real speed, so they do not strobe in a video.")


def view(d: Diagram, labs: list[str], slots: list[tuple[float, float]], drifts: list[float], z_floor, x, y):
    """HeliView blocks for the helicopters `labs` (the first is the reference); returns bindings."""
    ref = labs[0]
    bindings = []
    dr = SI["drive"]
    for k, (lab, (dx, dy), vx) in enumerate(zip(labs, slots, drifts)):
        tag = lab.lower()
        vn = f"{lab}View"
        d.node(vn, "project:HeliView", x, y + 140 * k,
               params={"dx": num(dx), "dy": num(dy), "dz": num(VIEW_LIFT), "vx": num(vx), "z_floor": ex(z_floor),
                       "period": num(FLOOR_PERIOD), "hub_x": num(SI["pos"]["HUB"][0]), "hub_z": num(SI["pos"]["HUB"][2]),
                       "IS": num(SI["mr"]["IS"]), "tr_x": num(SI["pos"]["TR"][0]), "tr_y": "0.25",
                       "tr_z": num(SI["pos"]["TR"][2]), "n_tr": num(dr["n_tr"]), "spin": "0.1"})
        d.sig(lab, "pose", vn, "g")
        d.sig(ref, "pose", vn, "g0")
        d.sig(lab, "a1r", vn, "a1")
        d.sig(lab, "b1r", vn, "b1")
        d.sig(lab, "om", vn, "om")
        bindings.append({"target": f"link:heli_{tag}", "property": "pose", "signal": [f"{vn}/pose[{i}]" for i in range(1, 8)]})
        bindings.append({"target": f"link:rotor_{tag}", "property": "pose", "signal": [f"{vn}/disc[{i}]" for i in range(1, 8)]})
        bindings.append({"target": f"link:tailrotor_{tag}", "property": "pose", "signal": [f"{vn}/tail[{i}]" for i in range(1, 8)]})
    bindings.append({"target": "link:ground", "property": "pose", "signal": [f"{ref}View/ground[{i}]" for i in range(1, 8)]})
    # the stripe offsets wrap with the stripe spacing: the period tells the view to interpolate across a wrap the short way
    for axis, period in (("x", [FLOOR_PERIOD, 0.0, 0.0]), ("y", [0.0, FLOOR_PERIOD, 0.0])):
        bindings.append({"target": f"link:stripes_{axis}", "property": "pose",
                         "signal": [f"{ref}View/stripes_{axis}[{i}]" for i in range(1, 8)], "period": period})
    return bindings


def write_scene(name: str, helis, comment: str, slots=None, ground_z=0.0):
    path = EXAMPLE / "scenes" / f"{name}.sdf"
    path.parent.mkdir(exist_ok=True)
    path.write_text(scene_sdf(name, helis, comment + "\n" + SCENE_NOTE, slots, ground_z), encoding="utf-8", newline="\n")
    return f"scenes/{name}.sdf"


# --------------------------------------------------------------------------- model 1: open loop
OL = DESIGN["open_loop"]
AXIS_INPUT = {"coll": "th0", "lon": "B1", "lat": "A1", "ped": "thtr"}
OL_SLOTS = [(0.0, 0.0), (0.0, -16.0), (0.0, 16.0), (-16.0, 0.0)]
OL_PAINT = ["red", "white", "blue", "yellow"]


def model_open_loop():
    d = Diagram()
    params = [g("rpm_mode", "1.0", None, "Rotor speed the aerodynamics see: 1 the drivetrain's (bond graph), "
                "0 the nominal 385 rpm (the report's constant-RPM model)")]
    for k, a in enumerate(OL):
        lab = a["label"]
        x0, y = 40 + 440 * k, 40   # side by side: the airframe is tall
        st = a["start"]
        airframe_instance(d, lab, x0 + 200, y, _airframe_start(st))
        for j, nm in enumerate(("th0", "B1", "A1", "thtr")):
            c0 = st["ctrl_deg"][j]
            node = f"{lab}{nm}"
            if a["axis"] and AXIS_INPUT[a["axis"]] == nm:
                if a["t_off"] is None:
                    d.node(node, "stdlib:sources/Step", x0, y + 90 * j,
                           params={"t_step": num(a["t_on"]), "initial": num(c0), "final": num(c0 + a["amp"])})
                else:
                    d.node(node, "stdlib:sources/Trapezoid", x0, y + 90 * j,
                           params={"amplitude": num(a["amp"]), "rising": "0.0", "width": num(a["t_off"] - a["t_on"]),
                                   "falling": "0.0", "period": "1000.0", "n_periods": "1", "offset": num(c0),
                                   "t_start": num(a["t_on"])})
            else:
                d.node(node, "stdlib:sources/Constant", x0, y + 90 * j, params={"value": num(c0)})
            d.sig(node, "y", lab, nm)
    labs = [a["label"] for a in OL]
    drifts = [a["kt"] * 0.5144444444444445 for a in OL]
    plots = [
        {"id": "p1", "title": "Pitch and roll attitude (deg)", "signals": [f"{l}/Air/theta_deg" for l in labs] + [f"{l}/Air/phi_deg" for l in labs]},
        {"id": "p2", "title": "Body rates p, q, r (deg/s)", "signals": [f"{l}/Air/{k}_deg" for l in labs for k in ("p", "q", "r")]},
        {"id": "p3", "title": "Heading (deg)", "signals": [f"{l}/Air/psi_deg" for l in labs]},
        {"id": "p4", "title": "Rotor speed (percent)", "signals": [f"{l}/Gov/nr" for l in labs]},
        {"id": "p5", "title": "Flapping a1, b1 (deg)", "signals": [f"{l}/MR/a1_deg" for l in labs] + [f"{l}/MR/b1_deg" for l in labs]},
        {"id": "p6", "title": "Height (m)", "signals": [f"{l}/Air/h" for l in labs]},
    ]
    bindings = view(d, labs, OL_SLOTS, drifts, -30.0, 1840, 40)
    scene = write_scene("a109-open-loop", list(zip([l.lower() for l in labs], OL_PAINT)),
                        "  a109-open-loop: Hover (red, framed), Coll (white, right), Lon (blue, left), Fwd (yellow, behind).\n"
                        "  The floor is a reference plane 30 m below the start height (sea level).",
                        OL_SLOTS, -30.0 + VIEW_LIFT)
    return model_doc(
        "a109-open-loop",
        "Four A109s (Heffley & Mnich, NASA CR-177476, Appendix D), open loop: the hover trim released, a collective "
        "step and a longitudinal cyclic pulse in hover, and a pedal pulse at 100 kt. Generated by design/build_model.py; "
        "see the README.",
        d, settings(15.0, 1501), plots, scene, bindings, params)


# --------------------------------------------------------------------------- model 2: the flyable a109-sim
SIM = DESIGN["sim"]
RIG = DESIGN["a109"]["rig"]
SIM_INPUTS = [  # (marker, DemoPilot output, start value, description)
    ("collective", "coll", SIM["hover_sticks"][0], "collective lever, 0 full down .. 1 full up"),
    ("cyclic_lon", "lon", 0.0, "longitudinal cyclic, -1 full aft .. +1 full forward"),
    ("cyclic_lat", "lat", 0.0, "lateral cyclic, -1 full left .. +1 full right"),
    ("pedals", "ped", 0.0, "pedals, -1 full left .. +1 full right"),
]
SIM_WIND = [("wind_n", "wn", "wind towards north (m/s)"), ("wind_e", "we", "wind towards east (m/s)"),
            ("wind_d", "wd", "wind downwards (m/s)")]
SIM_OUTPUT_SOURCES = [  # (marker, node, port)
    ("north_m", "Heli", "x"), ("east_m", "East", "y"), ("alt_m", "Heli", "h"),
    ("phi_deg", "Heli", "phi_deg"), ("theta_deg", "Heli", "theta_deg"), ("psi_deg", "Heli", "psi_deg"),
    ("p_dps", "Heli", "p_deg"), ("q_dps", "Heli", "q_deg"), ("r_dps", "Heli", "r_deg"),
    ("u_mps", "Heli", "ui"), ("v_mps", "Heli", "vi"), ("w_mps", "Heli", "wi"), ("vs_mps", "Heli", "hdot"),
    ("tas_mps", "Heli", "vt"), ("kts", "Heli", "kts"), ("beta_deg", "Heli", "beta_deg"),
    ("rotor_pct", "Heli", "nr"), ("power_hp", "Heli", "power_hp"), ("thrust_n", "Heli", "thrust"),
    ("a1_deg", "Heli", "a1"), ("b1_deg", "Heli", "b1"),
    ("theta0_deg", "Rig", "th0"), ("B1_deg", "Scas", "B1"), ("A1_deg", "Scas", "A1"), ("theta_tr_deg", "Scas", "thtr"),
    ("fn_nose", "Heli", "fn_nose"), ("fn_left", "Heli", "fn_left"), ("fn_right", "Heli", "fn_right"),
    ("wow", "Heli", "wow"),
]
# the SCAS switch: an input marker after the global `scas` (in bg-sim the global, in the FMU the host's switch)
SIM_SWITCH = ("scas", "SCAS switch, 1 on (engaged in the air), 0 off (the rigging's angles direct)")
# The start state (globals, so that an FMU host can set them before initialisation: the hover at
# 15 m of design/heli_sim.py by default, or the helicopter parked on its gear): the pose of the
# principal frame (Free3D), the body momentum in it (angular, then linear), the flapping (rad),
# the rotor's angular momentum (N m s) and the governor's integrator (N m).
SIM_START = ("qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
             "a10", "b10", "Lrot0", "xi0")
SIM_GLOBALS = [
    ("scas", "1.0", "1: SCAS on (attitude command / hold, yaw-rate command, turn coordination); 0: sticks direct"),
    ("demo", "1.0", "1: the demonstration pilot flies the schedule; 0: hold the hover sticks"),
    ("smooth", "1.0", "1: the report's hard switches (fin and tailplane stall, wake edge, dihedral magnification) "
     "blended over a narrow band (ours, keeps the closed loop from chattering); 0: the report's switches"),
    ("coll_off", "0.0", "collective offset added from t_inp (fraction of travel)"),
    ("lon_off", "0.0", "longitudinal cyclic offset added from t_inp (-1 .. 1, + forward)"),
    ("lat_off", "0.0", "lateral cyclic offset added from t_inp (-1 .. 1, + right)"),
    ("ped_off", "0.0", "pedal offset added from t_inp (-1 .. 1, + right)"),
    ("t_inp", "1.0", "time the stick offsets start (s)"),
]


def sim_start_globals() -> list[dict]:
    """The start-state globals at the hover of design/heli_sim.py (SIM_START)."""
    st = SIM["start"]
    pose, P = st["pose"], st["P"]
    vals = [pose["qw"], pose["qx"], pose["qy"], pose["qz"], pose["px"], pose["py"], pose["pz"], *P,
            st["a1"], st["b1"], SI["drive"]["J"] * st["om"], st["xi"]]
    desc = ["start pose: quaternion of the principal frame (w)", "start pose quaternion (x)", "start pose quaternion (y)",
            "start pose quaternion (z)", "start position north (m)", "start position west (m)", "start height of the CG (m)",
            "start angular momentum, principal x (N m s)", "start angular momentum, principal y (N m s)",
            "start angular momentum, principal z (N m s)", "start linear momentum, principal x (kg m/s)",
            "start linear momentum, principal y (kg m/s)", "start linear momentum, principal z (kg m/s)",
            "start longitudinal flapping a1 (rad)", "start lateral flapping b1 (rad)",
            "start angular momentum of the rotor and drivetrain (N m s)", "start governor integrator (N m)"]
    return [g(n, num(v), None, dsc) for n, v, dsc in zip(SIM_START, vals, desc)]


def lookup1d(d: Diagram, name, xs, ys, x, y):
    return d.node(name, "stdlib:continuous/Lookup1D", x, y, params={"x": vec(xs), "table": vec(ys)},
                  constants={"N": len(xs)})


def model_sim():
    d = Diagram()
    pose_keys = ("qw", "qx", "qy", "qz", "px", "py", "pz")
    start = {"pose": dict(zip(pose_keys, SIM_START[:7])), "P": list(SIM_START[7:13]), "a1": "a10", "b1": "b10",
             "om_P": "Lrot0", "xi": "xi0"}
    airframe(start, rpm_mode="1.0", ge="1.0", wind=True, smooth="smooth", gear=True).subsystem(d, "Heli", 1500, 300)
    # ---- the schedule of the demonstration (time -> speed, height, bank)
    sched = SIM["schedule"]
    d.node("Clock", "stdlib:sources/Time", 40, 40)
    for k, (nm, col) in enumerate((("UCmd", 1), ("HCmd", 2), ("PhTurn", 3))):
        lookup1d(d, nm, [r[0] for r in sched], [r[col] for r in sched], 200, 40 + 70 * k)
        d.sig("Clock", "y", nm, "u")
    # ---- trim feedforward over the forward airspeed
    ff = SIM["ff"]
    for k, key in enumerate(("theta", "phi", "coll", "B1", "A1", "thtr")):
        nm = f"FF_{key}"
        lookup1d(d, nm, ff["u"], ff[key], 700, 700 + 70 * k)
        d.sig("Heli", "u", nm, "u")
    d.note("**Schedule and feedforward.** UCmd, HCmd and PhTurn give the demonstration's forward speed, "
           "height and bank over time; the FF_* tables the trim attitude, collective and control angles "
           "over the forward airspeed (the trim sweep of design/heli_sim.py at 15 m).", 40, -60, 700, 40, "blue")
    # ---- the demonstration pilot and the export inputs
    pil = SIM["pilot"]
    hs = SIM["hover_sticks"]
    d.node("Pilot", "project:DemoPilot", 400, 40, params={
        "demo": "demo", "scas": "scas", "Ku": num(pil["Ku"]), "Kv": num(pil["Kv"]), "Kh": num(pil["Kh"]),
        "Khd": num(pil["Khd"]), "k_th_stick": num(SIM["stick"]["theta"]), "k_ph_stick": num(SIM["stick"]["phi"]),
        "v_tc1": num(SIM["v_tc"][0]), "v_tc2": num(SIM["v_tc"][1]), "a_coll": num(RIG["coll"]["a"]),
        "b_coll": num(RIG["coll"]["b"]), "coll_h": num(hs[0]), "lon_h": num(hs[1]), "lat_h": num(hs[2]),
        "ped_h": num(hs[3]), "coll_off": "coll_off", "lon_off": "lon_off", "lat_off": "lat_off",
        "ped_off": "ped_off", "t_inp": "t_inp"})
    d.sig("UCmd", "y", "Pilot", "u_cmd")
    d.sig("HCmd", "y", "Pilot", "h_cmd")
    d.sig("PhTurn", "y", "Pilot", "ph_turn")
    for p in ("u", "v", "h", "hdot"):
        d.sig("Heli", p, "Pilot", p)
    d.sig("FF_coll", "y", "Pilot", "coll_ff")
    for k, (marker, port, start_v, _) in enumerate(SIM_INPUTS):
        d.node(marker, "stdlib:converters/ExportInputPass", 650, 40 + 110 * k, params={"value": num(start_v)})
        d.sig("Pilot", port, marker, "u")
    d.node("Calm", "stdlib:sources/Constant", 400, 500, params={"value": "0.0"})
    for k, (marker, port, _) in enumerate(SIM_WIND):
        d.node(marker, "stdlib:converters/ExportInputPass", 650, 500 + 110 * k, params={"value": "0.0"})
        d.sig("Calm", "y", marker, "u")
        d.sig(marker, "y", "Heli", port)
    d.note("**Pilot and inputs.** DemoPilot flies the schedule by stick (speed by pitch attitude, height by "
           "collective, the turn by bank); the ExportInputPass markers pass its sticks and a calm wind through "
           "in bg-sim, in the FMU the host drives them.", 400, -60, 700, 40, "blue")
    # ---- rigging and SCAS
    d.node("Rig", "project:Rigging", 900, 40, params={
        **{f"a_{ax}": num(RIG[ax]["a"]) for ax in ("coll", "lon", "lat", "ped")},
        **{f"b_{ax}": num(RIG[ax]["b"]) for ax in ("coll", "lon", "lat", "ped")}})
    for marker, port in (("collective", "coll"), ("cyclic_lon", "lon"), ("cyclic_lat", "lat"), ("pedals", "ped")):
        d.sig(marker, "y", "Rig", port)
    gains = SIM["gains"]
    d.node("Scas", "project:Scas", 1150, 40, params={
        "k_th_stick": num(SIM["stick"]["theta"]), "k_ph_stick": num(SIM["stick"]["phi"]),
        "k_r_stick": num(SIM["stick"]["r"]), "v_tc1": num(SIM["v_tc"][0]), "v_tc2": num(SIM["v_tc"][1]),
        "g0": num(SI["g0"]), **{k: num(v) for k, v in gains.items()}})
    for marker, port in (("cyclic_lon", "lon"), ("cyclic_lat", "lat"), ("pedals", "ped")):
        d.sig(marker, "y", "Scas", port)
    d.node("ScasSw", "stdlib:sources/Constant", 900, 520, params={"value": "scas"})
    d.node(SIM_SWITCH[0], "stdlib:converters/ExportInputPass", 1000, 520, params={"value": "1.0"})
    d.sig("ScasSw", "y", SIM_SWITCH[0], "u")
    d.sig(SIM_SWITCH[0], "y", "Scas", "on")
    d.sig("Heli", "wow", "Scas", "wow")
    for src, port in (("u", "u"), ("theta_deg", "theta"), ("phi_deg", "phi"), ("p_deg", "p"), ("q_deg", "q"),
                      ("r_deg", "r")):
        d.sig("Heli", src, "Scas", port)
    for key, port in (("theta", "th_ff"), ("phi", "ph_ff"), ("B1", "B1_ff"), ("A1", "A1_ff"), ("thtr", "tr_ff")):
        d.sig(f"FF_{key}", "y", "Scas", port)
    d.sig("Rig", "B1", "Scas", "B1d")
    d.sig("Rig", "A1", "Scas", "A1d")
    d.sig("Rig", "thtr", "Scas", "trd")
    d.sig("Rig", "th0", "Heli", "th0")
    d.sig("Scas", "B1", "Heli", "B1")
    d.sig("Scas", "A1", "Heli", "A1")
    d.sig("Scas", "thtr", "Heli", "thtr")
    d.note("**Rigging and SCAS.** Rigging maps the sticks to the blade angles with the percent-of-travel fits; "
           "the SCAS (switch `scas`) holds the attitude, commands the yaw rate and coordinates the turn, or "
           "passes the rigging's angles.", 900, -60, 600, 40, "blue")
    # ---- what the host reads
    d.node("East", "stdlib:continuous/Gain", 1900, 40, params={"k": "-1.0"})
    d.sig("Heli", "y", "East", "u")
    for k, (marker, node, port) in enumerate(SIM_OUTPUT_SOURCES):
        d.node(marker, "stdlib:converters/ExportOutput", 2150 + 200 * (k // 15), 40 + 60 * (k % 15))
        d.sig(node, port, marker, "u")
    bindings = view(d, ["Heli"], [(0.0, 0.0)], [0.0], 0.0, 1900, 900)
    scene = write_scene("a109-sim", [("heli", "red")],
                        "  a109-sim: the flyable A109 (red, framed). The floor is the ground (sea level); the wheels\n"
                        "  touch it 1.32 m below the CG (the gear's ContactPoints).", [(0.0, 0.0)], -SIM["alt"] + VIEW_LIFT)
    plots = [
        {"id": "p1", "title": "Forward speed and command (m/s)", "signals": ["Heli/Air/u", "UCmd/y"]},
        {"id": "p2", "title": "Height and command (m)", "signals": ["Heli/Air/h", "HCmd/y"]},
        {"id": "p3", "title": "Attitude (deg)", "signals": ["Heli/Air/phi_deg", "Heli/Air/theta_deg", "Scas/ph_cmd", "Scas/th_cmd"]},
        {"id": "p4", "title": "Heading (deg) and yaw rate (deg/s)", "signals": ["Heli/Air/psi_deg", "Heli/Air/r_deg", "Scas/r_cmd"]},
        {"id": "p5", "title": "Sticks", "signals": [f"{m}/y" for m, *_ in SIM_INPUTS]},
        {"id": "p6", "title": "Blade angles (deg)", "signals": ["Rig/th0", "Scas/B1", "Scas/A1", "Scas/thtr"]},
        {"id": "p7", "title": "Rotor speed (percent) and power (hp)", "signals": ["Heli/Gov/nr", "Heli/Gov/power_hp"]},
        {"id": "p8", "title": "Wheel loads (N)", "signals": ["Heli/Tyre_nose/f_n", "Heli/Tyre_left/f_n", "Heli/Tyre_right/f_n"]},
    ]
    params = [g(n, v, None, desc) for n, v, desc in SIM_GLOBALS] + sim_start_globals()
    return model_doc(
        "a109-sim",
        "The flyable A109: Heffley & Mnich's model with the drivetrain bond graph, ground effect, a switchable SCAS "
        "and the demonstration pilot (hover, transition and climb, a coordinated 20 deg bank turn, deceleration to "
        "hover), with the FMU interface as export markers. Generated by design/build_model.py; see the README.",
        d, settings(SIM["t_end"], int(round(SIM["t_end"] / 0.05)) + 1), plots, scene, bindings, params)


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


DASHBOARDS = {
    "a109-open-loop": {"autoRerun": True, "cards": [
        text("d1", "Open loop", "Four A109s released from trim. **Hover** stays put; **Coll** (+0.5 deg collective) "
             "climbs and yaws right as the main-rotor torque grows; **Lon** (a cyclic pulse) starts the unstable "
             "hover phugoid; **Fwd** (a pedal pulse at 100 kt) shows the Dutch roll. Switch the rotor speed the "
             "aerodynamics see between the drivetrain's and the report's constant 385 rpm."),
        slider("d2", "Rotor speed: drivetrain (1) or constant (0)", "rpm_mode", 0.0, 1.0, 1.0, 0),
        plot("d3", "Heading (deg)", ["Hover/Air/psi_deg", "Coll/Air/psi_deg", "Lon/Air/psi_deg", "Fwd/Air/psi_deg"], "4x2"),
        plot("d4", "Pitch attitude (deg)", ["Hover/Air/theta_deg", "Coll/Air/theta_deg", "Lon/Air/theta_deg"]),
        plot("d5", "Roll attitude (deg)", ["Hover/Air/phi_deg", "Coll/Air/phi_deg", "Fwd/Air/phi_deg"]),
        plot("d6", "Rotor speed (percent)", ["Coll/Gov/nr", "Fwd/Gov/nr"]),
        plot("d7", "Height (m)", ["Hover/Air/h", "Coll/Air/h", "Lon/Air/h"]),
    ]},
    "a109-sim": {"autoRerun": True, "cards": [
        text("d1", "The flyable A109", "The demonstration pilot hovers at 15 m, accelerates and climbs to 70 kt, flies a "
             "coordinated 20 deg bank turn, decelerates and hovers again. Turn the **demo** off to hover hands-off, "
             "add stick offsets from 1 s, or switch the **SCAS** off and watch the bare helicopter diverge.", "2x2"),
        slider("d2", "Demonstration pilot (1 on, 0 hover sticks)", "demo", 0.0, 1.0, 1.0, 0),
        slider("d3", "SCAS (1 on, 0 direct)", "scas", 0.0, 1.0, 1.0, 0),
        slider("d4", "Collective offset (fraction)", "coll_off", -0.2, 0.2, 0.01, 2),
        slider("d5", "Longitudinal cyclic offset", "lon_off", -0.5, 0.5, 0.01, 2),
        slider("d6", "Lateral cyclic offset", "lat_off", -0.5, 0.5, 0.01, 2),
        slider("d7", "Pedal offset", "ped_off", -0.5, 0.5, 0.01, 2),
        plot("d8", "Forward speed and command (m/s)", ["Heli/Air/u", "UCmd/y"], "4x2"),
        plot("d9", "Height and command (m)", ["Heli/Air/h", "HCmd/y"]),
        plot("d10", "Attitude (deg)", ["Heli/Air/phi_deg", "Heli/Air/theta_deg"]),
        plot("d11", "Heading (deg)", ["Heli/Air/psi_deg"]),
        plot("d12", "Sticks", ["collective/y", "cyclic_lon/y", "cyclic_lat/y", "pedals/y"]),
        plot("d13", "Rotor speed (percent) and power (hp)", ["Heli/Gov/nr", "Heli/Gov/power_hp"]),
    ]},
}


# --------------------------------------------------------------------------- expected.json
NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
           "note": "no algebraic loop, no causality conflict, no event storm"}
OL_SIGNAL = {"om": "OmRotor/y", "a1_deg": "MR/a1_deg", "b1_deg": "MR/b1_deg", "nr": "Gov/nr", "power_hp": "Gov/power_hp"}
SIM_SIGNAL = {"u": "Heli/Air/u", "v": "Heli/Air/v", "h": "Heli/Air/h", "phi_deg": "Heli/Air/phi_deg",
              "theta_deg": "Heli/Air/theta_deg", "psi_deg": "Heli/Air/psi_deg", "r_deg": "Heli/Air/r_deg",
              "nr": "Heli/Gov/nr", "power_hp": "Heli/Gov/power_hp", "coll": "collective/y", "lon": "cyclic_lon/y",
              "B1": "Scas/B1", "thtr": "Scas/thtr"}


def _wrap(signal, value):
    """HeliAirData wraps the heading to (-180, 180]; the references integrate it."""
    return (value + 180.0) % 360.0 - 180.0 if signal.endswith("psi_deg") else value


def _cur(signal, value, t, tol, note=None):
    value = _wrap(signal, value)
    c = {"kind": "cursor_value", "signal": signal, "t": float(t), "value": value, "abs": tol}
    if note:
        c["note"] = note
    return c


def _ol_cursors(case, keys, times, tol, note=None):
    out = []
    for t in times:
        for k in keys:
            sig = f"{case['label']}/{OL_SIGNAL.get(k, 'Air/' + k)}"
            out.append(_cur(sig, case["at"][k][str(t)], t, tol[k] if isinstance(tol, dict) else tol, note))
            note = None
    return out


def expected() -> dict:
    ol = {a["label"]: a for a in OL}
    ref = "the scipy SI model (design/heli_si.py, LSODA 1e-10) of the same airframe and drivetrain"
    tol = {"theta_deg": 1e-3, "phi_deg": 1e-3, "psi_deg": 2e-3, "p_deg": 2e-3, "q_deg": 2e-3, "r_deg": 2e-3,
           "u": 1e-3, "v": 1e-3, "w": 1e-3, "h": 1e-3, "a1_deg": 1e-3, "b1_deg": 1e-3, "nr": 1e-3, "power_hp": 0.05,
           "om": 1e-4}
    hov, coll, lon, fwd = ol["Hover"], ol["Coll"], ol["Lon"], ol["Fwd"]
    checks_ol = [{"kind": "scene_bindings"}, NO_DIAG]
    checks_ol += _ol_cursors(hov, ("theta_deg", "phi_deg", "a1_deg", "b1_deg", "nr", "power_hp"), (10.0,), tol,
                             "the hover trim holds: attitude, flapping, rotor speed and the 640 hp of the power method")
    checks_ol += _ol_cursors(coll, ("r_deg", "psi_deg", "h", "w", "nr", "power_hp", "om"), (1.5, 3.0, 5.0, 10.0), tol,
                             ref + ": the collective step climbs, the main-rotor torque yaws the nose right and the rotor droops")
    checks_ol += _ol_cursors(coll, ("p_deg", "q_deg", "phi_deg", "theta_deg"), (3.0, 5.0, 10.0), tol,
                             "and the cyclic cross-coupling rolls and pitches it")
    checks_ol += _ol_cursors(lon, ("q_deg", "theta_deg", "u", "a1_deg"), (1.5, 3.0, 5.0, 7.0, 10.0), tol,
                             "the cyclic pulse starts the unstable hover phugoid")
    checks_ol += _ol_cursors(fwd, ("r_deg", "v", "p_deg", "phi_deg", "psi_deg"), (1.5, 2.0, 3.0, 5.0, 7.0, 10.0), tol,
                             "the pedal pulse at 100 kt")
    hm = DESIGN["modes"]["rpm1_0"][0]
    wn = math.hypot(hm[0], hm[1])
    checks_ol.append({"kind": "damping", "signal": "Lon/Air/theta_deg", "from_t": 1.5, "to_t": 10.0, "offset": "constant",
                      "zeta": -hm[0] / wn, "zeta_abs": 0.08, "wn": wn, "wn_rtol": 0.15, "min_wn": 0.2, "max_wn": 2.0,
                      "note": f"the hover phugoid of the linearised scipy model ({hm[0]:+.3f} +- {hm[1]:.3f}j 1/s; the report "
                              "publishes no eigenvalues, so the reference is scipy)"})
    # constant rotor speed (the report's model): the same collective step
    c0 = DESIGN["open_loop_rpm0"][0]
    checks_rpm0 = [NO_DIAG] + _ol_cursors(c0, ("r_deg", "psi_deg", "h", "power_hp"), (1.5, 3.0, 5.0, 10.0), tol,
                                          "rpm_mode = 0: the aerodynamics see the nominal 385 rpm (the report's model)")
    psi0, psi1 = c0["at"]["psi_deg"]["10.0"], coll["at"]["psi_deg"]["10.0"]
    checks_rpm0.append(_cur("Coll/Air/psi_deg", psi0, 10.0, abs(psi1 - psi0) / 2,
                            f"the rotor-speed droop matters: heading {psi0:.1f} deg here against {psi1:.1f} deg with "
                            "the drivetrain's speed (the tolerance is half the difference)"))
    # ---- the flyable model
    stol = {"u": 0.02, "v": 0.02, "h": 0.05, "phi_deg": 0.05, "theta_deg": 0.05, "psi_deg": 0.2, "r_deg": 0.05,
            "nr": 0.01, "power_hp": 0.5, "coll": 1e-3, "lon": 2e-3, "B1": 0.01, "thtr": 0.02}
    sref = "the scipy closed loop (design/heli_sim.py: rigging, SCAS, demonstration pilot on heli_si.py)"
    checks_sim = [{"kind": "scene_bindings"}, NO_DIAG]
    for k, t in enumerate(DESIGN_SIM_TIMES):
        for key in ("u", "h", "phi_deg", "theta_deg", "psi_deg", "nr", "coll", "B1"):
            checks_sim.append(_cur(SIM_SIGNAL[key], SIM["at"][key][str(t)], t, stol[key],
                                   sref if (k == 0 and key == "u") else None))
    checks_sim += [
        {"kind": "min_ge", "signal": "Heli/Air/h", "value": 10.0, "note": "never below 10 m"},
        {"kind": "max_abs", "signal": "Heli/Air/u", "value": SIM["max_abs"]["u"], "rtol": 2e-3,
         "note": f"the transition to {SIM['max_abs']['u']:.1f} m/s ({SIM['max_abs']['u'] / 0.5144444:.0f} kt)"},
        {"kind": "max_abs", "signal": "Heli/Air/phi_deg", "value": SIM["max_abs"]["phi_deg"], "rtol": 5e-3,
         "note": "the coordinated 20 deg bank turn"},
        {"kind": "max_abs_le", "signal": "Heli/Gov/power_hp", "value": 740.0, "note": "within the 740 hp take-off power"},
    ]
    entries = {"a109-open-loop": {"checks": checks_ol},
               "a109-open-loop-rpm0": {"model": "a109-open-loop", "overrides": {"global:rpm_mode": 0.0},
                                       "checks": checks_rpm0}}
    export = {"inputs": {"collective": {"min": SIM["hover_sticks"][0] - 0.02, "max": SIM["hover_sticks"][0] + 0.02},
                         "cyclic_lon": {"min": -0.05, "max": 0.05}, "cyclic_lat": {"min": -0.05, "max": 0.05},
                         "pedals": {"min": -0.05, "max": 0.05}, "wind_n": {"min": -2.0, "max": 2.0},
                         "wind_e": {"min": -2.0, "max": 2.0}, "wind_d": {"min": -1.0, "max": 1.0},
                         SIM_SWITCH[0]: {"min": 1.0, "max": 1.0}},
              "interface": {"inputs": [m for m, *_ in SIM_INPUTS] + [m for m, *_ in SIM_WIND] + [SIM_SWITCH[0]],
                            "outputs": [m for m, *_ in SIM_OUTPUT_SOURCES]},
              "note": "the FMU interface of a109-sim: the host flies the sticks (the DemoPilot is then bypassed by the markers)"}
    entries["a109-sim"] = {"checks": checks_sim, "export": export}
    for lab, case in SIM["cases"].items():
        ov = {"global:demo": 0.0, "global:scas": case["scas"], "global:t_inp": case["offsets"]["t"]}
        for key, gname in (("coll", "coll_off"), ("lon", "lon_off"), ("lat", "lat_off"), ("ped", "ped_off")):
            if key in case["offsets"]:
                ov[f"global:{gname}"] = case["offsets"][key]
        ov = {k: v for k, v in ov.items() if not (k == "global:scas" and v == 1.0) and not (k == "global:t_inp" and v == 1.0)}
        cks = [NO_DIAG]
        first = True
        for t in case["at"]["u"]:
            for key in ("u", "theta_deg", "phi_deg", "psi_deg", "h"):
                tl = stol[key] if lab == "hold" else 5 * stol[key]
                cks.append(_cur(SIM_SIGNAL[key], case["at"][key][t], float(t), tl, case["desc"] if first else None))
                first = False
        t_end = case["t_end"]
        entries[f"a109-sim-{lab}"] = {"model": "a109-sim",
                                      "settings": {"t_end": t_end, "output": {"points": int(round(t_end / 0.05)) + 1}},
                                      "overrides": ov, "checks": cks}
    entries.update(ground_cases())
    return {"project": "a109",
            "description": "Agusta A109 (Heffley & Mnich, NASA CR-177476, Appendix D): open loop with the drivetrain bond "
                           "graph and the constant-RPM switch, and the flyable a109-sim (SCAS, demonstration pilot, FMU "
                           "markers). Numbers come from design/design.json (an independent scipy implementation).",
            "models": entries}


DESIGN_SIM_TIMES = [float(t) for t in SIM["at"]["u"]]


def parked_start() -> dict:
    """Overrides of the start globals: the helicopter parked on its gear, level, heading north. The
    CG height is the gear's (1.32 m) less the static deflection of a wheel under a third of the
    weight (the contact law k x (x/xref)^(1/2)); the rotor at 100 %; the governor's integrator at
    a rough flat-pitch torque (the governor settles it within a second)."""
    weight = SI["m"] * SI["g0"]
    k, xref = GEAR_CONTACT["k"], GEAR_CONTACT["xref"]
    delta = (weight / 3.0 * math.sqrt(xref) / k) ** (2.0 / 3.0)
    q = SI["q_bp"]      # the principal frame of a level body (B = P turned by eps)
    return {"global:qw0": q[0], "global:qx0": q[1], "global:qy0": q[2], "global:qz0": q[3],
            "global:z0": -GEAR["nose"][2] - delta, "global:a10": 0.0, "global:b10": 0.0, "global:xi0": 6000.0}


def ground_cases() -> dict:
    """a109-sim on its landing gear (demo = 0, from the parked start): collective full down, it
    stays parked; the hover collective + 3 %, it lifts off and the SCAS takes over."""
    weight = SI["m"] * SI["g0"]
    th0, ph0 = SIM["ff"]["theta"][0], SIM["ff"]["phi"][0]
    base = {"global:demo": 0.0, "global:t_inp": 0.0, **parked_start()}
    parked = [
        NO_DIAG,
        {"kind": "min_ge", "signal": "Heli/Air/h", "value": 1.25,
         "note": "parked, collective full down: the CG stays at the gear's height less the tyre deflection (1.28 m)"},
        {"kind": "max_abs_le", "signal": "Heli/Air/h", "value": 1.30},
        {"kind": "max_abs_le", "signal": "Heli/Air/theta_deg", "value": 0.5,
         "note": "level on its three wheels (all three contact points 1.32 m below the CG)"},
        {"kind": "max_abs_le", "signal": "Heli/Air/phi_deg", "value": 0.5},
        {"kind": "max_abs_le", "signal": "Heli/Air/u", "from_t": 1.0, "value": 0.02,
         "note": "the tyres' friction holds it against the flat-pitch rotor and the tail rotor (no brakes)"},
        {"kind": "max_abs_le", "signal": "Heli/Air/v", "from_t": 1.0, "value": 0.02},
        {"kind": "max_abs_le", "signal": "Heli/Air/r_deg", "from_t": 1.0, "value": 0.3,
         "note": "the regularised friction creeps under the rotor's torque: about 0.13 deg/s"},
        {"kind": "min_ge", "signal": "Heli/GearLoad/y", "from_t": 1.0, "value": 0.95 * weight,
         "note": f"the gear carries the weight ({weight:.0f} N; the flat-pitch rotor pushes down a little)"},
        {"kind": "min_ge", "signal": "Heli/Wow/y", "value": 0.999, "note": "weight on wheels: the SCAS is out"},
        _cur("Heli/Gov/nr", 100.0, 10.0, 0.01, "the governor holds 100 % at flat pitch"),
    ]
    liftoff = [
        NO_DIAG,
        {"kind": "max_abs_le", "signal": "Heli/Wow/y", "from_t": 1.0, "value": 1e-3,
         "note": "the hover collective + 3 %: it lifts off within half a second; weight off wheels, the SCAS engages"},
        {"kind": "min_ge", "signal": "Heli/Air/h", "from_t": 10.0, "value": 15.0, "note": "and climbs"},
        _cur("Heli/Air/theta_deg", th0, 20.0, 0.1, "the SCAS holds the hover attitude of its feedforward table "
             "(design/heli_sim.py's trim at 15 m)"),
        _cur("Heli/Air/phi_deg", ph0, 20.0, 0.1),
        _cur("Heli/Gov/nr", 100.0, 20.0, 0.05),
    ]
    return {
        "a109-sim-parked": {"model": "a109-sim", "settings": {"t_end": 10.0, "output": {"points": 201}},
                            "overrides": {**base, "global:coll_off": -SIM["hover_sticks"][0]}, "checks": parked},
        "a109-sim-liftoff": {"model": "a109-sim", "settings": {"t_end": 20.0, "output": {"points": 401}},
                             "overrides": {**base, "global:coll_off": 0.03}, "checks": liftoff},
    }


def main() -> int:
    (EXAMPLE / "library" / f"{AIRFRAME}.bgsub.json").write_text(json.dumps(airframe_definition(), indent=1) + "\n",
                                                                  encoding="utf-8", newline="\n")
    models = {"a109-open-loop": model_open_loop(), "a109-sim": model_sim()}
    (EXAMPLE / "expected.json").write_text(json.dumps(expected(), indent=1) + "\n", encoding="utf-8", newline="\n")
    for name, doc in models.items():
        if name in DASHBOARDS:
            doc["dashboard"] = DASHBOARDS[name]
        path = EXAMPLE / "models" / f"{name}.bgmodel.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "a109", "models": list(models),
            "libraryDir": "library", "scenesDir": "scenes"}
    (EXAMPLE / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
