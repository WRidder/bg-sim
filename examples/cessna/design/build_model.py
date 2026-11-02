# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the cessna models, scenes and expected.json from `design/design.json`.

    uv run examples/cessna/design/design.py        # first
    uv run examples/cessna/design/build_model.py

The airframe (a subsystem, `airframe()`) is the same in both models: the multibond rigid body on a
free joint, the air data, the c172p tables as stdlib Lookup1D blocks, the aerodynamic build-up as
a modulated wrench source, and the power train as a rotational bond graph (engine torque source,
crankshaft + propeller rotor, propeller load) whose thrust acts on the airframe at the hub.
cessna-sim adds the landing gear: per leg the tyre-runway contact (a modulated transformer on the
airframe's multibond) with the strut spring and damper, the rolling resistance and brake, and the
tyre's side force as bond-graph elements on its three bonds.
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
TABLES = DESIGN["tables"]
COEF = DESIGN["coef"]
OL = DESIGN["open_loop"]
SIMD = DESIGN["sim"]
KT = 0.514444444
RAD = math.pi / 180.0


def num(v: float) -> str:
    return repr(float(v))


def vec(values) -> str:
    return "[" + ", ".join(repr(float(v)) for v in values) + "]"


def ex(v) -> str:
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

    def node(self, name, block, x, y, params=None, starts=None, constants=None) -> str:
        assert name not in self.ids, name
        nid = f"n{len(self.nodes) + 1:03d}"
        b = {"ref": block} if isinstance(block, str) else block
        self.nodes.append({
            "id": nid, "name": name, "block": b, "position": {"x": int(x), "y": int(y)}, "rotation": 0,
            "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self.ids[name] = nid
        return name

    def junction(self, name, kind, x, y) -> str:
        return self.node(name, {"junction": str(kind)}, x, y)

    def sig(self, a, pa, b, pb):
        self.connections.append(("signal", a, pa, b, pb))

    def bond(self, a, pa, b, pb):
        self.connections.append(("bond", a, pa, b, pb))

    def note(self, text, x, y, w, h, color=None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def port(self, name, direction, node, port, unit=None, size=1):
        self.ports.append({"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
                           "unit": unit, "node": self.ids[node], "port": port})

    def doc(self, prefix: str = "") -> dict:
        conns = []
        for k, (kind, a, pa, b, pb) in enumerate(self.connections):
            frm = {"node": self.ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self.ids[b]}
            if pb is not None:
                to["port"] = pb
            conns.append({"id": f"{prefix}c{k + 1:03d}", "kind": kind, "from": frm, "to": to})
        d = {"nodes": self.nodes, "connections": conns, "annotations": self.annotations}
        if self.ports:
            d["subsystemPorts"] = self.ports
        return d

    def subsystem(self, parent: "Diagram", name: str, x: float, y: float) -> str:
        parent.node(name, {"subsystem": {"ports": self.ports, "diagram": self.doc(name + "_")}}, x, y)
        return name


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value if isinstance(value, str) else num(value), "unit": unit,
            "description": description}


def settings(t_end: float, points: int, solver="auto", reltol=1e-8, abstol=1e-8) -> dict:
    return {"t_start": 0.0, "t_end": float(t_end), "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": 100000}


def model_doc(name, comment, d: Diagram, sett, plots, scene, bindings, parameters, dashboard=None) -> dict:
    doc = {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
           "diagram": d.doc(), "settings": sett, "plots": plots,
           "scene": {"file": scene} if scene else None, "bindings": bindings, "parameters": parameters}
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc


def lookup1d(d: Diagram, name, tab, x, y):
    return d.node(name, "stdlib:continuous/Lookup1D", x, y, params={"x": vec(tab["x"]), "table": vec(tab["y"])},
                  constants={"N": len(tab["x"])})


# --------------------------------------------------------------------------- the airframe
INPUTS = ("yoke_pitch", "yoke_roll", "pedals", "trim", "throttle", "mixture", "flaps", "brake_l", "brake_r")
LOOKUPS = [  # (Lookup1D node / table name, argument (AirData or Flaps output), C172Aero input)
    ("KCDGE", ("Air", "hb"), "kcd"), ("KCLGE", ("Air", "hb"), "kcl"),
    ("CDDF", ("Flaps", "flap"), "cddf"), ("CLDF", ("Flaps", "flap"), "cldf"), ("CMDF", ("Flaps", "flap"), "cmdf"),
    ("CLB", ("Air", "beta"), "clb"), ("CNB", ("Air", "beta"), "cnb"),
    ("CLWBH0", ("Air", "alpha"), "clwbh0"), ("CLWBH1", ("Air", "alpha"), "clwbh1"),
    ("CDWBH0", ("Air", "alpha"), "cdwbh0"), ("CDWBH1", ("Air", "alpha"), "cdwbh1"),
    ("CDWBH2", ("Air", "alpha"), "cdwbh2"), ("CDWBH3", ("Air", "alpha"), "cdwbh3"),
    ("CYB0", ("Air", "beta"), "cyb0"), ("CYB30", ("Air", "beta"), "cyb30"),
    ("CYP0", ("Air", "alpha"), "cyp0"), ("CYP30", ("Air", "alpha"), "cyp30"),
    ("CYR0", ("Air", "alpha"), "cyr0"), ("CYR30", ("Air", "alpha"), "cyr30"),
    ("CLR0", ("Air", "alpha"), "clr0"), ("CLR30", ("Air", "alpha"), "clr30"),
]
OUTPUTS = [  # (subsystem port, node, node port, unit)
    ("alpha_deg", "Air", "alpha_deg", None), ("beta_deg", "Air", "beta_deg", None), ("vt", "Air", "vt", "m/s"),
    ("cas", "Air", "cas", "m/s"), ("h", "Air", "h", "m"), ("phi", "Air", "phi", "rad"), ("theta", "Air", "theta", "rad"),
    ("psi", "Air", "psi", "rad"), ("p", "Air", "p", "rad/s"), ("q", "Air", "q", "rad/s"), ("r", "Air", "r", "rad/s"),
    ("hdot", "Air", "hdot", "m/s"), ("x", "Air", "x", "m"), ("y", "Air", "y", "m"), ("gamma", "Air", "gamma", "rad"),
    ("u", "Air", "u", "m/s"), ("v", "Air", "v", "m/s"), ("w", "Air", "w", "m/s"), ("gs", "Air", "gs", "m/s"),
    ("engine_rpm", "Engine", "n_rpm", None), ("hp", "Engine", "hp", None), ("map_inhg", "Engine", "map_inhg", None),
    ("ff_gph", "Engine", "ff_gph", None), ("thrust", "Prop", "thrust", "N"), ("flap", "Flaps", "flap", None),
    ("de_deg", "Ctl", "de_deg", None), ("da_deg", "Ctl", "da_deg", None), ("dr_deg", "Ctl", "dr_deg", None),
    ("steer", "Ctl", "steer", "rad"), ("prop_angle", "PropAngle", "y", None), ("fy_aero", "Aero", "fy", "N"),
    ("CL", "Aero", "CL", None), ("stall", "Stall", "y", None),
]
GEAR_OUTPUTS = [(f"fn_{leg}", f"Contact_{leg}", "fn", "N") for leg in ("nose", "left", "right")] + \
               [(f"delta_{leg}", f"Contact_{leg}", "delta", "m") for leg in ("nose", "left", "right")]


def airframe(start: dict, gear: bool, wind: bool) -> Diagram:
    """One Cessna 172P. `start`: pose (7), P (6), h_rotor, MAP, xad, flap, strut (3) as numbers or
    expressions over global parameters."""
    d = Diagram()
    J = SI["J"]
    # ---- multibond rigid body on a free joint (body = principal axes: the products of inertia are neglected)
    d.node("World", "stdlib:multibond/GroundSpatial", 40, 40)
    pose = start["pose"]
    d.node("Free", "stdlib:spatial/Free3D", 220, 40, starts=dict(zip(("qw", "qx", "qy", "qz", "px", "py", "pz"), map(ex, pose))))
    d.node("Body", "stdlib:spatial/RigidBody3D", 420, 40, params={"m": num(SI["mass"]), "J": vec(J), "g0": num(SI["g0"])},
           starts={"inertia/P": exvec(start["P"])})
    d.bond("World", "p", "Free", "parent")
    d.bond("Free", "child", "Body", "p")
    for k in range(1, 7):
        d.node(f"Se{k}", "stdlib:bondgraph/Se", 220, 160 + 40 * k, params={"e": "0.0"})
        d.bond(f"Se{k}", "p", "Free", f"drive{k}")
    d.sig("Free", "pose", "Body", "g")
    d.note("**Airframe.** RigidBody3D at the centre of gravity of the POH gross loading (2400 lb, station 45.6 in), "
           f"body axes x forward, y left, z up; Jxx, Jyy, Jzz = {J[0]:.0f}, {J[1]:.0f}, {J[2]:.0f} kg m^2 (the product "
           f"Jxz {SI['Jxz']:.1f} kg m^2 is neglected). Gravity is inside RigidBody3D.", 40, -60, 900, 50, "blue")
    # ---- air data
    ra = SI["r_aero"]
    d.node("Air", "project:C172AirData", 420, 300,
           params={"vf": num(SI["smoothing"]["V_FLOOR"]), "b": num(SI["b"]), "cbar": num(SI["cbar"]),
                   "rax": num(ra[0]), "ray": num(ra[1]), "raz": num(ra[2]), "ground_z": "0.0"})
    d.sig("Free", "pose", "Air", "g")
    d.sig("Body", "V", "Air", "V")
    if wind:
        for nm in ("wn", "we", "wd"):
            d.port(nm, "input", "Air", nm, "m/s")
    else:
        d.node("Calm", "stdlib:sources/Constant", 220, 300, params={"value": "0.0"})
        for nm in ("wn", "we", "wd"):
            d.sig("Calm", "y", "Air", nm)
    # ---- the pilot's controls (pass-through gains, so each input can fan out)
    for k, nm in enumerate(INPUTS):
        d.node(f"{nm}In", "stdlib:continuous/Gain", 40, 560 + 60 * k, params={"k": "1.0"})
        d.port(nm, "input", f"{nm}In", "u")
    d.node("Ctl", "project:C172Controls", 220, 560, params={"ks": num(SI["smoothing"]["CMD_SMOOTH"])})
    for nm in ("yoke_pitch", "yoke_roll", "pedals", "trim"):
        d.sig(f"{nm}In", "y", "Ctl", nm)
    d.node("Flaps", "project:FlapActuator", 220, 760, params={"k": num(SI["smoothing"]["FLAP_GAIN"])},
           starts={"x": ex(start["flap"])})
    d.sig("flapsIn", "y", "Flaps", "cmd")
    # ---- alpha-dot and the stall flag
    d.node("AlphaDot", "stdlib:continuous/FilteredDerivative", 620, 220, params={"Tf": num(SI["smoothing"]["TF_ALPHADOT"])},
           starts={"x": ex(start["xad"])})
    d.sig("Air", "alpha", "AlphaDot", "u")
    d.node("Stall", "project:StallHysteresis", 620, 280, params={"hi": "0.36", "lo": "0.09", "k": "50.0"})
    d.sig("Air", "alpha", "Stall", "u")
    # ---- tables
    x0, y0 = 800, 300
    for k, (nm, src, _) in enumerate(LOOKUPS):
        lookup1d(d, nm, TABLES[nm], x0 + 160 * (k // 11), y0 + 60 * (k % 11))
        d.sig(src[0], src[1], nm, "u")
    # ---- aerodynamics: a modulated wrench source on the airframe
    d.node("Aero", "project:C172Aero", 1200, 300,
           params={"S": num(SI["S"]), "b": num(SI["b"]), "cbar": num(SI["cbar"]), "rax": num(ra[0]), "ray": num(ra[1]),
                   "raz": num(ra[2]), "eps": num(SI["smoothing"]["EPS_ABS"]), **{k: num(v) for k, v in COEF.items()}})
    for p in ("u", "alpha", "beta", "p", "q", "r", "qbar", "rho", "bi2v", "ci2v"):
        d.sig("Air", p, "Aero", p)
    d.sig("AlphaDot", "y", "Aero", "alphadot")
    for p in ("de", "da", "dr"):
        d.sig("Ctl", p, "Aero", p)
    d.sig("Flaps", "flap", "Aero", "flap")
    d.sig("Stall", "y", "Aero", "hyst")
    for nm, _, port in LOOKUPS:
        d.sig(nm, "y", "Aero", port)
    d.node("AeroWrench", "stdlib:multibond/ExternalWrenchSpatial", 1400, 40)
    for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
        d.sig("Aero", p, "AeroWrench", p)
    d.bond("AeroWrench", "p", "Body", "p")
    # ---- power train: the rotational bond graph
    e = SI["engine"]
    rp = SI["r_prop"]
    d.node("RotorMount", "stdlib:multibond/FixedTransform3DNeutral", 620, 820,
           params={"qw": num(math.cos(-math.pi / 4)), "qx": "0.0", "qy": num(math.sin(-math.pi / 4)), "qz": "0.0",
                   "x": num(-(-rp[2])), "y": num(-rp[1]), "z": num(-rp[0])})
    d.node("Rotor", "stdlib:spatial/Rotor3D", 820, 820, params={"Ja": num(SI["prop_J"])}, starts={"h": ex(start["h_rotor"])})
    d.bond("Body", "p", "RotorMount", "b")
    d.bond("RotorMount", "a", "Rotor", "p")
    d.junction("Crank", 1, 1000, 900)
    d.bond("Crank", None, "Rotor", "drive")
    d.node("Engine", "project:PistonEngine", 1200, 820,
           params={"displacement": num(e["displacement"]), "stroke_in": num(e["stroke_in"]), "cr": num(e["cr"]),
                   "VE": num(e["VE"]), "R_air": num(e["R_air"]), "isfc": num(e["isfc"]), "fric_hp": num(e["fric_hp"]),
                   "fmep_dyn": num(e["fmep_dyn"]), "fmep_static": num(e["fmep_static"]), "cycles": num(e["cycles"]),
                   "peak_mps": num(e["peak_mps"]), "z_airbox": num(e["z_airbox"]), "z_thr": num(e["z_thr"]),
                   "lag": num(e["lag"]), "mps_floor": num(SI["smoothing"]["MPS_FLOOR"]),
                   "w_floor": num(SI["smoothing"]["W_FLOOR"]),
                   "fa_tab": vec(TABLES["MIXTURE_EFFICIENCY"]["x"]), "me_tab": vec(TABLES["MIXTURE_EFFICIENCY"]["y"])},
           starts={"MAP": ex(start["MAP"])}, constants={"NM": len(TABLES["MIXTURE_EFFICIENCY"]["x"])})
    d.bond("Crank", None, "Engine", "p")
    d.sig("throttleIn", "y", "Engine", "throttle")
    d.sig("mixtureIn", "y", "Engine", "mixture")
    for p in ("pa", "p_tot", "T"):
        d.sig("Air", p, "Engine", p)
    d.node("Prop", "project:Propeller", 1200, 960,
           params={"D": num(SI["prop_D"]), "ry": num(rp[1]), "rz": num(rp[2]),
                   "n_floor": num(SI["smoothing"]["N_FLOOR"]),
                   "j_ct": vec(TABLES["C_THRUST"]["x"]), "ct_tab": vec(TABLES["C_THRUST"]["y"]),
                   "j_cp": vec(TABLES["C_POWER"]["x"]), "cp_tab": vec(TABLES["C_POWER"]["y"])},
           constants={"NT": len(TABLES["C_THRUST"]["x"]), "NP": len(TABLES["C_POWER"]["x"])})
    d.bond("Crank", None, "Prop", "p")
    for p in ("u", "rho", "a"):
        d.sig("Air", p, "Prop", p)
    d.sig("Prop", "vi", "Aero", "vi")
    d.node("PropWrench", "stdlib:multibond/ExternalWrenchSpatial", 1400, 960)
    for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
        d.sig("Prop", p, "PropWrench", p)
    d.bond("PropWrench", "p", "Body", "p")
    d.node("PropAngle", "stdlib:continuous/Integrator", 1000, 1040)
    d.sig("Rotor", "w_rel", "PropAngle", "u")
    d.note("**Power train (rotational bond graph).** The crankshaft 1-junction: the engine (PistonEngine, a torque "
           "source modulated by the throttle, the mixture and the manifold pressure), the crankshaft + propeller "
           "inertia (Rotor3D: the axial momentum, spinning about body x, on the airframe through RotorMount, so its "
           "torque reaction and gyroscopic moment act on the airframe) and the propeller (an R: torque over the "
           "shaft speed and the airspeed). The thrust and the propeller's aerodynamic torque act on the airframe at "
           "the hub (PropWrench).", 620, 1100, 900, 60, "blue")
    # ---- landing gear
    if gear:
        d.node("NoSteer", "stdlib:sources/Constant", 1600, 1200, params={"value": "0.0"})
        d.node("NoBrake", "stdlib:sources/Constant", 1600, 1260, params={"value": "0.0"})
        for k, leg in enumerate(("nose", "left", "right")):
            gl = SI["gear"][leg]
            r = gl["r"]
            x, y = 1600 + 900 * k, 1400
            d.node(f"Mount_{leg}", "stdlib:multibond/FixedTransform3DNeutral", x, y,
                   params={"x": num(-r[0]), "y": num(-r[1]), "z": num(-r[2])})
            d.bond("Body", "p", f"Mount_{leg}", "b")
            d.node(f"Contact_{leg}", "project:GearContact", x + 200, y,
                   params={"rx": num(r[0]), "ry": num(r[1]), "rz": num(r[2]), "ground_z": "0.0"})
            d.bond(f"Mount_{leg}", "a", f"Contact_{leg}", "p")
            d.sig("Free", "pose", f"Contact_{leg}", "g")
            d.sig("Ctl" if leg == "nose" else "NoSteer", "steer" if leg == "nose" else "y", f"Contact_{leg}", "steer")
            # normal: strut spring C and damper R on a 1-junction
            d.junction(f"N_{leg}", 1, x + 400, y - 100)
            d.bond(f"N_{leg}", None, f"Contact_{leg}", "n")
            d.node(f"Spring_{leg}", "project:StrutSpring", x + 600, y - 160,
                   params={"k": num(gl["k"]), "eps": num(SI["smoothing"]["GEAR_EPS"])}, starts={"q": ex(start["strut"][k])})
            d.node(f"Damper_{leg}", "project:StrutDamper", x + 600, y - 80,
                   params={"b": num(gl["b"]), "feps": num(SI["smoothing"]["GEAR_FEPS"])})
            d.bond(f"N_{leg}", None, f"Spring_{leg}", "j")
            d.bond(f"N_{leg}", None, f"Damper_{leg}", "j")
            d.sig(f"Spring_{leg}", "Fk", f"Damper_{leg}", "Fk")
            d.sig(f"Spring_{leg}", "sig", f"Damper_{leg}", "sig")
            # rolling: rolling resistance and the brake
            d.junction(f"X_{leg}", 1, x + 400, y)
            d.bond(f"X_{leg}", None, f"Contact_{leg}", "x")
            d.node(f"Roll_{leg}", "project:WheelFriction", x + 600, y,
                   params={"mu_r": num(gl["mu_r"]), "mu_s": num(gl["mu_s"]), "vs": num(SI["smoothing"]["V_ROLL"])})
            d.bond(f"X_{leg}", None, f"Roll_{leg}", "j")
            d.sig(f"Contact_{leg}", "fn", f"Roll_{leg}", "fn")
            d.sig({"nose": "NoBrake", "left": "brake_lIn", "right": "brake_rIn"}[leg], "y", f"Roll_{leg}", "brake")
            # lateral: the tyre's cornering force
            d.junction(f"Y_{leg}", 1, x + 400, y + 100)
            d.bond(f"Y_{leg}", None, f"Contact_{leg}", "y")
            d.node(f"Side_{leg}", "project:WheelSide", x + 600, y + 100,
                   params={"mu_s": num(gl["mu_s"]), "vs": num(SI["smoothing"]["V_SIDE"])})
            d.bond(f"Y_{leg}", None, f"Side_{leg}", "j")
            d.sig(f"Contact_{leg}", "fn", f"Side_{leg}", "fn")
            d.sig(f"Contact_{leg}", "vx", f"Side_{leg}", "vx")
        d.note("**Landing gear (bond graph per leg).** GearContact is the tyre-runway contact: a modulated transformer "
               "from the airframe's multibond (through Mount, at the contact point) to three translational bonds: the "
               "runway normal with the strut spring (C) and damper (R) on a 1-junction, the rolling direction with the "
               "rolling resistance and the brake (R), and the side direction with the tyre's cornering force (R). The "
               "nose wheel steers 10 deg with the pedals; the toe brakes act on the main wheels.", 1600, 1050, 1200, 60, "blue")
    for name, node, port, unit in OUTPUTS + (GEAR_OUTPUTS if gear else []):
        d.port(name, "output", node, port, unit)
    d.port("pose", "output", "Free", "pose", None, size=7)
    return d


def numeric_start(st: dict) -> dict:
    return {"pose": st["pose"], "P": st["P"], "h_rotor": st["h_rotor"], "MAP": st["MAP"], "xad": st["xad"],
            "flap": st["flap"], "strut": st["strut"]}


# --------------------------------------------------------------------------- scenes
VIEW_LIFT = 4.0
FLOOR_DEPTH = 40.0     # m: the open-loop reference floor below the start altitude (the phugoid moves +-10 m)
FLOOR_PERIOD = 50.0    # m, stripe spacing of the reference floor (the period of the scrolling pattern)
FLOOR_HALF = 400.0     # m, half size of the floor patch (a whole number of periods)
STRIPE_W = 3.0         # m, stripe width
TRAIL_RGBA = "1.0 0.85 0.45 1"
PIVOTS = {   # make_meshes.PIVOTS: (hinge point, axis), body frame
    "aileron_l": ((-0.63, 4.09, 0.66), (0.0, 1.0, 0.0)), "aileron_r": ((-0.63, -4.09, 0.66), (0.0, 1.0, 0.0)),
    "flap_l": ((-0.59, 1.785, 0.63), (0.0, 1.0, 0.0)), "flap_r": ((-0.59, -1.785, 0.63), (0.0, 1.0, 0.0)),
    "elevator": ((-5.20, 0.0, 0.10), (0.0, 1.0, 0.0)), "rudder": ((-5.55, 0.0, 0.10), (-0.074, 0.0, 0.997)),
    "propeller": ((2.116, 0.0, -0.226), (1.0, 0.0, 0.0)), "nosewheel": ((1.331, 0.0, -1.217), (0.0, 0.0, 1.0)),
}


def check_pivots():
    sys.path.insert(0, str(HERE))
    import make_meshes  # noqa: PLC0415  (needs trimesh only when run; here just the constants)
    for k, (p, a) in PIVOTS.items():
        q, b = make_meshes.PIVOTS[k]
        assert all(abs(u - v) < 1e-3 for u, v in zip(p, q)) and all(abs(u - v) < 1e-3 for u, v in zip(a, b)), (k, p, q)


def aircraft_links(tag: str) -> list[str]:
    L = [f'    <link name="ac_{tag}">', "      <pose>0 0 0 0 0 0</pose>",
         f'      <visual name="airframe_{tag}">', "        <pose>0 0 0 0 0 0</pose>",
         "        <geometry><mesh><uri>meshes/c172_body.glb</uri></mesh></geometry>", "      </visual>", "    </link>"]
    for name, ((x, y, z), (ax, ay, az)) in PIVOTS.items():
        # the link and its joint need different names (one namespace per model in SDF)
        L += [f'    <link name="{name}_part_{tag}">', f"      <pose>{x:g} {y:g} {z:g} 0 0 0</pose>",
              f'      <visual name="{name}_vis_{tag}">', "        <pose>0 0 0 0 0 0</pose>",
              f"        <geometry><mesh><uri>meshes/c172_{name}.glb</uri></mesh></geometry>", "      </visual>",
              "    </link>",
              f'    <joint name="{name}_{tag}" type="revolute">', f"      <parent>ac_{tag}</parent>",
              f"      <child>{name}_part_{tag}</child>", f"      <axis><xyz>{ax:g} {ay:g} {az:g}</xyz></axis>", "    </joint>"]
    return L


def box(name, pose, size, rgba) -> list[str]:
    return [f'      <visual name="{name}">', f"        <pose>{pose[0]:g} {pose[1]:g} {pose[2]:g} 0 0 {pose[3] if len(pose) > 3 else 0:g}</pose>",
            f"        <geometry><box><size>{size[0]:g} {size[1]:g} {size[2]:g}</size></box></geometry>",
            f"        <material><diffuse>{rgba}</diffuse></material>", "      </visual>"]


RUNWAY = {"x0": -30.0, "length": 1200.0, "width": 30.0}   # runway 36: from x0 northwards, centre line y = 0


def airfield() -> list[str]:
    """The airfield link: grass, runway 36/18 with its markings, a taxiway and the apron with a
    hangar and a tower (world frame, the runway surface at z = 0)."""
    x0, ln, w = RUNWAY["x0"], RUNWAY["length"], RUNWAY["width"]
    L = ['    <link name="field">', "      <pose>0 0 0 0 0 0</pose>"]
    L += box("grass", (x0 + ln / 2, 0.0, -0.55), (ln + 1600.0, 1600.0, 1.0), "0.36 0.47 0.30 1")
    L += box("runway", (x0 + ln / 2, 0.0, -0.04), (ln, w, 0.1), "0.30 0.30 0.32 1")
    for k in range(int((ln - 120.0) // 50.0)):
        L += box(f"centreline_{k}", (x0 + 60.0 + 50.0 * k + 15.0, 0.0, 0.02), (30.0, 0.9, 0.02), "0.95 0.95 0.95 1")
    for end, xs in (("s", x0 + 6.0), ("n", x0 + ln - 6.0)):
        for j in range(8):
            yy = -w / 2 + 3.0 + j * (w - 6.0) / 7.0
            L += box(f"threshold_{end}{j}", (xs, yy, 0.02), (8.0, 1.6, 0.02), "0.95 0.95 0.95 1")
    for sgn, side in ((1.0, "w"), (-1.0, "e")):
        L += box(f"edge_{side}", (x0 + ln / 2, sgn * (w / 2 - 0.6), 0.02), (ln, 0.5, 0.02), "0.95 0.95 0.95 1")
    L += box("taxiway", (x0 + ln / 2, -75.0, -0.045), (ln - 100.0, 15.0, 0.1), "0.33 0.33 0.34 1")
    for k, xx in enumerate((x0 + 80.0, x0 + ln - 80.0)):
        L += box(f"link_{k}", (xx, -37.5, -0.045), (15.0, 60.0, 0.1), "0.33 0.33 0.34 1")
    L += box("apron", (x0 + 300.0, -125.0, -0.045), (160.0, 85.0, 0.1), "0.38 0.38 0.39 1")
    L += box("hangar", (x0 + 260.0, -185.0, 6.0), (40.0, 30.0, 12.0), "0.70 0.72 0.74 1")
    L += box("hangar_roof", (x0 + 260.0, -185.0, 12.3), (41.0, 31.0, 0.6), "0.55 0.25 0.20 1")
    L += box("tower", (x0 + 350.0, -175.0, 9.0), (6.0, 6.0, 18.0), "0.85 0.85 0.82 1")
    L += box("tower_cab", (x0 + 350.0, -175.0, 19.5), (8.0, 8.0, 3.0), "0.35 0.50 0.60 1")
    L += box("windsock_mast", (x0 + 120.0, 30.0, 3.0), (0.2, 0.2, 6.0), "0.8 0.8 0.8 1")
    L += box("windsock", (x0 + 120.0, 31.2, 5.6), (0.6, 2.4, 0.6), "0.95 0.45 0.10 1")
    L.append("    </link>")
    return L


SCENE_NOTE = (
    "  Generated by design/build_model.py. Z-up, metres; x north, y west. The view keeps the aircraft framed by moving\n"
    "  the world instead of the camera (block C172View): the aircraft stays at the origin, lifted 4 m, and the airfield\n"
    "  (link field: runway 36 from x = -30 m, 1200 m long, the taxiway and apron to the east) moves under it. The moving\n"
    "  parts turn on revolute joints about their hinge lines (meshes from design/make_meshes.py): ailerons, flaps,\n"
    "  elevator and rudder with the surface angles (gain -pi/180: positive JSBSim deflections are trailing edge down,\n"
    "  and trailing edge left for the rudder; the right aileron moves the other way, gain +pi/180), the propeller with\n"
    "  the crankshaft angle (shown at 1/25 of the real speed, which a display could not show), the nose wheel with\n"
    "  the steering angle.")


def sim_scene() -> str:
    L = ['<?xml version="1.0"?>', "<!--", "  cessna-sim: the flyable Cessna 172P on its airfield.", SCENE_NOTE, "-->",
         '<sdf version="1.9">', '  <model name="cessna-sim">']
    L += airfield()
    L += aircraft_links("sim")
    L += ["  </model>", "</sdf>", ""]
    return "\n".join(L)


OL_TAGS = ("sp", "ph", "dr", "ro", "sl")
OL_LABELS = {"short_period": "SP", "phugoid": "Ph", "dutch_roll": "DR", "roll": "Ro", "spiral": "Sl"}
OL_OFFSETS = [0.0, 30.0, -30.0, 60.0, -60.0]


def ol_scene() -> str:
    L = ['<?xml version="1.0"?>', "<!--",
         "  cessna-open-loop: five Cessnas released from the trim at 100 KTAS, 5000 ft, each on one mode: SP (short period,\n"
         "  framed), Ph (phugoid), DR (dutch roll), Ro (roll), Sl (spiral), in formation slots 30 m apart. A striped floor 40 m\n"
         "  below the start altitude follows the framed aircraft (C172View): link floor stays under it, and the 50 m\n"
         "  stripes (links stripes_x, stripes_y) scroll with the ground track, each set along its own axis, wrapped into\n"
         "  one stripe spacing (the bindings declare that period, so the view interpolates across a wrap the short way).",
         SCENE_NOTE, "-->", '<sdf version="1.9">', '  <model name="cessna-open-loop">', '    <link name="floor">', "      <pose>0 0 0 0 0 0</pose>"]
    # the stripes sit half a period off the centre and shift by at most half a period either way, so they cover
    # the floor from edge to edge and their ends stay put; the floor is one stripe width larger than the pattern
    n = int(round(FLOOR_HALF / FLOOR_PERIOD))
    side = 2 * FLOOR_HALF + STRIPE_W
    L += box("floor", (0.0, 0.0, -0.5), (side, side, 1.0), "0.36 0.45 0.33 1")
    L.append("    </link>")
    for axis in "xy":
        L += [f'    <link name="stripes_{axis}">', "      <pose>0 0 0 0 0 0</pose>"]
        for k in range(-n, n):
            c = (k + 0.5) * FLOOR_PERIOD
            at, size = (((c, 0.0, 0.05), (STRIPE_W, 2 * FLOOR_HALF, 0.1)) if axis == "x"
                        else ((0.0, c, 0.05), (2 * FLOOR_HALF, STRIPE_W, 0.1)))
            L += box(f"stripe_{axis}{k + n}", at, size, "0.62 0.66 0.55 1")
        L.append("    </link>")
    for tag in OL_TAGS:
        L += aircraft_links(tag)
    L += ["  </model>", "</sdf>", ""]
    return "\n".join(L)


def surface_bindings(tag: str, sub: str) -> list[dict]:
    """Bindings of the moving parts of aircraft `tag` (signals of subsystem `sub`)."""
    return [
        {"target": f"joint:aileron_l_{tag}", "property": "position", "signal": f"{sub}/Ctl/da_deg", "gain": -RAD},
        {"target": f"joint:aileron_r_{tag}", "property": "position", "signal": f"{sub}/Ctl/da_deg", "gain": RAD},
        {"target": f"joint:flap_l_{tag}", "property": "position", "signal": f"{sub}/Flaps/flap", "gain": -RAD},
        {"target": f"joint:flap_r_{tag}", "property": "position", "signal": f"{sub}/Flaps/flap", "gain": -RAD},
        {"target": f"joint:elevator_{tag}", "property": "position", "signal": f"{sub}/Ctl/de_deg", "gain": -RAD},
        {"target": f"joint:rudder_{tag}", "property": "position", "signal": f"{sub}/Ctl/dr_deg", "gain": -RAD},
        {"target": f"joint:propeller_{tag}", "property": "position", "signal": f"{sub}/PropAngle/y", "gain": 0.04},
        {"target": f"joint:nosewheel_{tag}", "property": "position", "signal": f"{sub}/Ctl/steer", "gain": -1.0},
    ]


def view(d: Diagram, subs: list[str], tags: list[str], offsets: list[float], z0, x, y, field: bool):
    bindings = []
    ref = subs[0]
    for k, (sub, tag, dy) in enumerate(zip(subs, tags, offsets)):
        vnode = f"{sub}View"
        d.node(vnode, "project:C172View", x, y + 120 * k,
               params={"dy": num(dy), "dz": num(VIEW_LIFT), "z0": ex(z0), "depth": num(FLOOR_DEPTH + VIEW_LIFT),
                       "period": num(FLOOR_PERIOD)})
        d.sig(sub, "pose", vnode, "g")
        d.sig(ref, "pose", vnode, "g0")
        bindings.append({"target": f"link:ac_{tag}", "property": "pose", "signal": [f"{vnode}/pose[{i}]" for i in range(1, 8)]})
        bindings += surface_bindings(tag, sub)
    if field:
        bindings.append({"target": "link:field", "property": "pose", "signal": [f"{ref}View/field[{i}]" for i in range(1, 8)]})
    else:
        bindings.append({"target": "link:floor", "property": "pose", "signal": [f"{ref}View/ground[{i}]" for i in range(1, 8)]})
        for axis, period in (("x", [FLOOR_PERIOD, 0.0, 0.0]), ("y", [0.0, FLOOR_PERIOD, 0.0])):
            bindings.append({"target": f"link:stripes_{axis}", "property": "pose",
                             "signal": [f"{ref}View/stripes_{axis}[{i}]" for i in range(1, 8)], "period": period})
    return bindings


# --------------------------------------------------------------------------- model 1: open loop
def hold_controls(d: Diagram, sub: str, ctl: dict, x: float, y: float):
    for k, nm in enumerate(INPUTS):
        val = {"flaps": ctl["flaps"], "brake_l": 0.0, "brake_r": 0.0}.get(nm, ctl.get(nm, 0.0))
        d.node(f"{sub}_{nm}", "stdlib:sources/Constant", x, y + 50 * k, params={"value": num(val)})
        d.sig(f"{sub}_{nm}", "y", sub, nm)


def model_open_loop():
    d = Diagram()
    subs = []
    for k, (mode, lab) in enumerate(OL_LABELS.items()):
        st = OL["modes"][mode]["start"]
        sub = airframe(numeric_start(st), gear=False, wind=False)
        y = 40 + 600 * k
        sub.subsystem(d, lab, 500, y)
        hold_controls(d, lab, st["controls"], 100, y)
        subs.append(lab)
        if mode in ("roll", "spiral"):
            d.node(f"Rate{lab}", "project:ModeRate", 800, y)
            for p in ("phi", "theta", "p", "q", "r"):
                d.sig(lab, p, f"Rate{lab}", p)
    tr = OL["trim"]
    d.note(f"**Open loop.** Five Cessnas trimmed at 100 KTAS, 5000 ft (alpha {tr['alpha'] / RAD:.2f} deg, throttle "
           f"{tr['throttle']:.3f}, {tr['rpm']:.0f} rpm, elevator {tr['de'] / RAD:.2f} deg, mixture leaned for best power), "
           "each released on one eigenvector of the linearised model (design/c172_lin.py): SP short period (1 deg of alpha), "
           "Ph phugoid (2 m/s), DR dutch roll (1 deg of sideslip), Ro roll (2 deg of bank), Sl spiral (5 deg). The controls are "
           "held at the trim.", 40, -100, 1000, 60, "blue")
    plots = [
        {"id": "p1", "title": "Short period: angle of attack (deg)", "signals": ["SP/Air/alpha_deg"]},
        {"id": "p2", "title": "Phugoid: airspeed (m/s) and altitude (m)", "signals": ["Ph/Air/vt", "Ph/Air/h"]},
        {"id": "p3", "title": "Dutch roll: sideslip (deg)", "signals": ["DR/Air/beta_deg"]},
        {"id": "p4", "title": "Roll and spiral: bank (rad)", "signals": ["Ro/Air/phi", "Sl/Air/phi"]},
        {"id": "p5", "title": "Mode rates (d phi/dt)/phi (1/s)", "signals": ["RateRo/lambda", "RateSl/lambda"]},
        {"id": "p6", "title": "Engine (rpm)", "signals": ["Ph/Engine/n_rpm", "SP/Engine/n_rpm"]},
    ]
    bindings = view(d, subs, list(OL_TAGS), OL_OFFSETS, OL["modes"]["short_period"]["start"]["pose"][6], 1100, 40, field=False)
    (EXAMPLE / "scenes" / "cessna-open-loop.sdf").write_text(ol_scene(), encoding="utf-8", newline="\n")
    return model_doc(
        "cessna-open-loop",
        "Open loop at 100 KTAS, 5000 ft: the five rigid-body modes of the c172p, one aircraft per mode. Generated by "
        "design/build_model.py; see the README.",
        d, settings(120.0, 2401), plots, "scenes/cessna-open-loop.sdf", bindings,
        [g("t_end", "120.0", "s", "Run length")])


# --------------------------------------------------------------------------- model 2: cessna-sim
SIM_INPUTS = [  # (marker, global (start value), description)
    ("yoke_pitch", "yoke", "yoke pitch, -1 full forward .. +1 full aft"),
    ("yoke_roll", "roll", "yoke roll, -1 full left .. +1 full right"),
    ("pedals", "ped", "rudder pedals, -1 full left .. +1 full right (the nose wheel steers with them)"),
    ("throttle", "thr", "throttle, 0 idle .. 1 full"),
    ("mixture", "mixture0", "mixture, 0 cut-off .. 1 full rich"),
    ("flaps", "flaps", "flap lever detent 0 .. 3 (0, 10, 20, 30 deg)"),
    ("trim", "trim0", "elevator trim, -1 nose down .. +1 nose up"),
    ("brake_l", "brake_l0", "left toe brake 0 .. 1"),
    ("brake_r", "brake_r0", "right toe brake 0 .. 1"),
    ("ap_roll_mode", "ap_roll_mode", "autopilot roll: 0 off, 1 wing leveller, 2 heading hold"),
    ("ap_alt_mode", "ap_alt_mode", "autopilot pitch: 0 off, 1 altitude hold"),
    ("ap_hdg_deg", "ap_hdg", "autopilot heading (deg)"),
    ("ap_alt_m", "ap_alt", "autopilot altitude (m)"),
    ("wind_n", "wind_n", "wind towards north (m/s)"),
    ("wind_e", "wind_e", "wind towards east (m/s)"),
    ("wind_d", "wind_d", "wind downwards (m/s)"),
]
SIM_OUTPUT_SOURCES = [  # (marker, node, port)
    ("north_m", "Status", "north_m"), ("east_m", "Status", "east_m"), ("alt_m", "Status", "alt_m"),
    ("q_w", "Status", "q_w"), ("q_x", "Status", "q_x"), ("q_y", "Status", "q_y"), ("q_z", "Status", "q_z"),
    ("phi_deg", "Status", "phi_deg"), ("theta_deg", "Status", "theta_deg"), ("psi_deg", "Status", "psi_deg"),
    ("kias", "Status", "kias"), ("ktas", "Status", "ktas"), ("vs_fpm", "Status", "vs_fpm"),
    ("alt_ft", "Status", "alt_ft"), ("agl_ft", "Status", "agl_ft"), ("turn_dps", "Status", "turn_dps"),
    ("slip", "Status", "slip"), ("on_ground", "Status", "on_ground"),
    ("alpha_deg", "C172", "alpha_deg"), ("beta_deg", "C172", "beta_deg"), ("gs_mps", "C172", "gs"),
    ("rpm", "C172", "engine_rpm"), ("hp", "C172", "hp"), ("map_inhg", "C172", "map_inhg"), ("ff_gph", "C172", "ff_gph"),
    ("thrust_n", "C172", "thrust"), ("flap_deg", "C172", "flap"), ("elevator_deg", "C172", "de_deg"),
    ("aileron_deg", "C172", "da_deg"), ("rudder_deg", "C172", "dr_deg"), ("steer_rad", "C172", "steer"),
    ("prop_angle", "C172", "prop_angle"), ("stall_flag", "C172", "stall"),
    ("fn_nose", "C172", "fn_nose"), ("fn_left", "C172", "fn_left"), ("fn_right", "C172", "fn_right"),
    ("ap_pitch", "AP", "ap_pitch"), ("ap_roll", "AP", "ap_roll"),
]
START_NAMES = ["qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
               "hrot0", "map0", "xad0", "flap0", "qn0", "ql0", "qr0"]


def start_values(st: dict) -> list[float]:
    return list(st["pose"]) + list(st["P"]) + [st["h_rotor"], st["MAP"], st["xad"], st["flap"]] + list(st["strut"])


def sim_globals() -> list[dict]:
    rw = SIMD["runway"]["start"]
    dp = SIMD["demo"]["params"]
    out = []
    for nm, v in zip(START_NAMES, start_values(rw)):
        out.append(g(nm, v, None, "Start state (set together by design/design.py: the runway start at rest, engine at idle, "
                                  "flaps 10). Pose, body momentum [J w; m v], crankshaft momentum, manifold pressure, "
                                  "alpha filter, flap angle, strut compressions" if nm == "qw0" else "Start state"))
    out += [
        g("demo", 1.0, None, "1: the demo pilot flies (takeoff, climb, turn); 0: the controls hold the *_hold values"),
        g("vr_kt", dp["vr"] / KT, None, "Demo: rotation speed (KCAS)"),
        g("turn_hdg", dp["psi_turn"] / RAD, None, "Demo: heading of the turn (deg)"),
        g("turn_t", dp["t_turn"], "s", "Demo: start of the turn"),
        g("flaps_up_m", dp["h_flaps_up"], "m", "Demo: flaps up above this height"),
        g("yoke_hold", 0.0, None, "Held yoke pitch (demo = 0)"), g("roll_hold", 0.0, None, "Held yoke roll"),
        g("ped_hold", 0.0, None, "Held pedals"), g("thr_hold", 0.0, None, "Held throttle"),
        g("flaps_hold", 0.0, None, "Held flap detent"),
        g("mixture0", 1.0, None, "Mixture"), g("trim0", 0.0, None, "Elevator trim"),
        g("brake_l0", 0.0, None, "Left brake"), g("brake_r0", 0.0, None, "Right brake"),
        g("ap_roll_mode", 0.0, None, "Autopilot roll: 0 off, 1 wing leveller, 2 heading hold"),
        g("ap_alt_mode", 0.0, None, "Autopilot pitch: 0 off, 1 altitude hold"),
        g("ap_hdg", 0.0, None, "Autopilot heading (deg)"), g("ap_alt", 300.0, "m", "Autopilot altitude"),
        g("wind_n", 0.0, "m/s", "Wind towards north"), g("wind_e", 0.0, "m/s", "Wind towards east"),
        g("wind_d", 0.0, "m/s", "Wind downwards"),
    ]
    return out


def model_sim():
    d = Diagram()
    dp = SIMD["demo"]["params"]
    rw = SIMD["runway"]
    sub = airframe({"pose": START_NAMES[0:7], "P": START_NAMES[7:13], "h_rotor": "hrot0", "MAP": "map0", "xad": "xad0",
                    "flap": "flap0", "strut": ["qn0", "ql0", "qr0"]}, gear=True, wind=True)
    sub.subsystem(d, "C172", 1500, 300)
    # ---- the demo pilot (the bg-sim stimulus; the FMU host replaces it) and the export inputs
    d.node("Demo", "project:DemoPilot", 300, 40, params={
        **{k: num(dp[k]) for k in ("t_thr", "t_thr_ramp", "dv_rot", "theta_rot", "h_air", "theta_climb", "kv", "v_lift",
                                   "v_climb", "dvdh", "k_theta", "k_q", "psi_turn", "k_psi", "phi_max", "k_phi", "k_p",
                                   "k_ped_psi", "k_ped_r", "k_ped_y", "k_yd")},
        "vr": f"vr_kt * {num(KT)}", "t_turn": "turn_t", "psi_turn": f"turn_hdg * {num(RAD)}", "h_flaps_up": "flaps_up_m",
        "h_cg0": num(rw["h_cg"]), "on": "demo", "yoke_hold": "yoke_hold", "roll_hold": "roll_hold", "ped_hold": "ped_hold",
        "thr_hold": "thr_hold", "flaps_hold": "flaps_hold"})
    for p, src in (("cas", "cas"), ("theta", "theta"), ("q", "q"), ("phi", "phi"), ("p", "p"), ("psi", "psi"), ("r", "r"),
                   ("h", "h"), ("y", "y")):
        d.sig("C172", src, "Demo", p)
    demo_out = {"yoke_pitch": "yoke_pitch", "yoke_roll": "yoke_roll", "pedals": "pedals", "throttle": "throttle",
                "flaps": "flaps"}
    gdefault = {p["name"]: p["value"] for p in sim_globals()}
    for k, (marker, gname, _) in enumerate(SIM_INPUTS):
        # the FMU's start value of the input (a number: the host's default)
        d.node(marker, "stdlib:converters/ExportInputPass", 700, 40 + 90 * k,
               params={"value": ("1.0" if marker == "flaps" else "0.0") if marker in demo_out else gdefault[gname]})
        if marker in demo_out:
            d.sig("Demo", demo_out[marker], marker, "u")
        else:
            d.node(f"{marker}Src", "stdlib:sources/Constant", 520, 40 + 90 * k, params={"value": gname})
            d.sig(f"{marker}Src", "y", marker, "u")
    d.note("**Inputs.** The ExportInputPass markers pass the demo pilot (or the globals) through in bg-sim; in the FMU the "
           "host drives them: yoke, pedals, throttle, mixture, flaps, trim, toe brakes, the autopilot's modes and "
           "references, and the wind.", 300, -80, 700, 50, "blue")
    # ---- autopilot (adds to the yoke)
    d.node("AP", "project:C172Autopilot", 1100, 40)
    d.sig("yoke_pitch", "y", "AP", "yoke_pitch_in")
    d.sig("yoke_roll", "y", "AP", "yoke_roll_in")
    d.sig("ap_roll_mode", "y", "AP", "roll_mode")
    d.sig("ap_alt_mode", "y", "AP", "alt_mode")
    d.sig("ap_hdg_deg", "y", "AP", "hdg_ref")
    d.sig("ap_alt_m", "y", "AP", "alt_ref")
    for p in ("phi", "psi", "p", "q", "h", "hdot"):
        d.sig("C172", p, "AP", p)
    d.sig("AP", "yoke_pitch", "C172", "yoke_pitch")
    d.sig("AP", "yoke_roll", "C172", "yoke_roll")
    for marker in ("pedals", "throttle", "mixture", "flaps", "trim", "brake_l", "brake_r"):
        d.sig(marker, "y", "C172", marker)
    for marker, port in (("wind_n", "wn"), ("wind_e", "we"), ("wind_d", "wd")):
        d.sig(marker, "y", "C172", port)
    # ---- what the host reads
    d.node("Status", "project:C172Status", 1900, 300, params={"h_cg0": num(rw["h_cg"]), "mass": num(SI["mass"])})
    d.sig("C172", "pose", "Status", "g")
    for p, src in (("cas", "cas"), ("vt", "vt"), ("hdot", "hdot"), ("phi", "phi"), ("theta", "theta"), ("psi", "psi"),
                   ("q", "q"), ("r", "r"), ("fy", "fy_aero"), ("fn_nose", "fn_nose"), ("fn_left", "fn_left"),
                   ("fn_right", "fn_right")):
        d.sig("C172", src, "Status", p)
    for k, (marker, node, port) in enumerate(SIM_OUTPUT_SOURCES):
        d.node(marker, "stdlib:converters/ExportOutput", 2150 + 200 * (k // 20), 40 + 60 * (k % 20))
        d.sig(node, port, marker, "u")
    bindings = view(d, ["C172"], ["sim"], [0.0], "z0", 1900, 1400, field=True)
    (EXAMPLE / "scenes" / "cessna-sim.sdf").write_text(sim_scene(), encoding="utf-8", newline="\n")
    plots = [
        {"id": "p1", "title": "Altitude (m) and ground track x (m)", "signals": ["C172/Air/h", "C172/Air/x"]},
        {"id": "p2", "title": "Airspeed (KIAS)", "signals": ["Status/kias"]},
        {"id": "p3", "title": "Attitude (deg)", "signals": ["Status/phi_deg", "Status/theta_deg", "Status/psi_deg"]},
        {"id": "p4", "title": "Wheel loads (N)", "signals": ["C172/Contact_nose/fn", "C172/Contact_left/fn", "C172/Contact_right/fn"]},
        {"id": "p5", "title": "Controls", "signals": ["AP/yoke_pitch", "AP/yoke_roll", "pedals/y", "throttle/y"]},
        {"id": "p6", "title": "Engine (rpm) and flaps (deg)", "signals": ["C172/Engine/n_rpm", "C172/Flaps/flap"]},
    ]
    return model_doc(
        "cessna-sim",
        "The flyable Cessna 172P: the c172p airframe with its landing gear on the runway, the power train, the flaps and an "
        "optional autopilot, with the FMU interface of the cessna-sim host as export markers. The default run is the demo: "
        "takeoff from runway 36, climb and a turn to the east. Generated by design/build_model.py; see the README.",
        d, settings(SIMD["demo"]["t_end"], int(SIMD["demo"]["t_end"] * 10) + 1, reltol=1e-7, abstol=1e-7),
        plots, "scenes/cessna-sim.sdf", bindings, sim_globals())


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


def gauge(cid, title, sig, lo, hi, unit, zones, decimals=0):
    return {"id": cid, "kind": "gauge", "size": "1x1", "title": title, "signals": [sig],
            "options": {"min": lo, "max": hi, "decimals": decimals, "unit": unit, "zones": zones}}


DASHBOARDS = {
    "cessna-open-loop": {"autoRerun": False, "cards": [
        text("d1", "Rigid-body modes", "Five Cessnas trimmed at 100 KTAS, 5000 ft, each released on one eigenvector: "
             "the **short period** (1.3 s, well damped), the **phugoid** (25 s, lightly damped), the **dutch roll** (3 s), "
             "the **roll** subsidence (0.18 s) and the slow, stable **spiral**.", "2x2"),
        plot("d2", "Short period: alpha (deg)", ["SP/Air/alpha_deg"]),
        plot("d3", "Phugoid: airspeed (m/s)", ["Ph/Air/vt"]),
        plot("d4", "Dutch roll: sideslip (deg)", ["DR/Air/beta_deg"]),
        plot("d5", "Roll and spiral: bank (rad)", ["Ro/Air/phi", "Sl/Air/phi"]),
        plot("d6", "Mode rates (1/s)", ["RateRo/lambda", "RateSl/lambda"]),
    ]},
    "cessna-sim": {"autoRerun": True, "cards": [
        text("d1", "Takeoff, climb and turn", "The demo pilot opens the throttle on runway 36, rotates at the **rotation "
             "speed**, climbs at 75 KIAS, raises the flaps and turns to the **turn heading**. Change them, add **wind**, "
             "or switch the demo off and let the autopilot hold a heading and an altitude.", "2x2"),
        slider("d2", "Rotation speed (KCAS)", "vr_kt", 40.0, 60.0, 1.0, 0, "kt"),
        slider("d3", "Turn heading (deg)", "turn_hdg", -180.0, 180.0, 5.0, 0, "deg"),
        slider("d4", "Turn start (s)", "turn_t", 40.0, 110.0, 1.0, 0, "s"),
        slider("d5", "Flaps up above (m)", "flaps_up_m", 5.0, 200.0, 5.0, 0, "m"),
        slider("d6", "Wind towards north (m/s; negative: headwind)", "wind_n", -10.0, 10.0, 0.5, 1, "m/s"),
        slider("d7", "Wind towards east (m/s)", "wind_e", -8.0, 8.0, 0.5, 1, "m/s"),
        gauge("d8", "Airspeed", "Status/kias", 0.0, 160.0, "kt",
              [{"from": 0.0, "to": 48.0, "tone": "bad"}, {"from": 48.0, "to": 129.0, "tone": "good"},
               {"from": 129.0, "to": 160.0, "tone": "warn"}]),
        gauge("d9", "Engine", "C172/Engine/n_rpm", 0.0, 3000.0, "rpm",
              [{"from": 0.0, "to": 2100.0, "tone": "good"}, {"from": 2100.0, "to": 2700.0, "tone": "good"},
               {"from": 2700.0, "to": 3000.0, "tone": "bad"}]),
        plot("d10", "Altitude (m)", ["C172/Air/h"], "4x2"),
        plot("d11", "Airspeed (KIAS)", ["Status/kias"]),
        plot("d12", "Attitude (deg)", ["Status/phi_deg", "Status/theta_deg", "Status/psi_deg"]),
        plot("d13", "Wheel loads (N)", ["C172/Contact_nose/fn", "C172/Contact_left/fn", "C172/Contact_right/fn"]),
        plot("d14", "Controls", ["AP/yoke_pitch", "AP/yoke_roll", "pedals/y", "throttle/y"]),
    ]},
}


# --------------------------------------------------------------------------- expected.json
def _at(rec, key, t):
    ts = rec["t"]
    k = min(range(len(ts)), key=lambda i: abs(ts[i] - t))
    assert abs(ts[k] - t) < 1e-6, (t, ts[k])
    return rec[key][k]


def _cursor(signal, rec, key, t, tol, note=None, scale=1.0, rel=False):
    c = {"kind": "cursor_value", "signal": signal, "t": t, "value": _at(rec, key, t) * scale}
    c["rtol" if rel else "abs"] = tol
    if note:
        c["note"] = note
    return c


NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
           "note": "no algebraic loop, no causality conflict, no event storm"}


def expected_open_loop() -> list:
    m = OL["modes"]
    tr = OL["trim"]
    ref = "the scipy simulation of the reference model (design/c172_ref.py, design/design.py)"
    chk = [{"kind": "scene_bindings"}, NO_DIAG,
           {"kind": "cursor_value", "signal": "SP/Air/vt", "t": 0.0, "value": m["short_period"]["run"]["vt"][0], "abs": 1e-3,
            "note": f"trim at 100 KTAS, 5000 ft: alpha {tr['alpha'] / RAD:.3f} deg, throttle {tr['throttle']:.4f}, {tr['rpm']:.0f} rpm"}]

    def damp(name, sig, lab, t0, t1, zeta_abs, wn_rtol):
        mm = m[name]
        return {"kind": "damping", "signal": f"{lab}/Air/{sig}", "from_t": t0, "to_t": t1, "offset": "linear",
                "zeta": mm["zeta"], "zeta_abs": zeta_abs, "wn": mm["wn"], "wn_rtol": wn_rtol,
                "note": f"{name.replace('_', ' ')}: the linearised mode zeta {mm['zeta']:.3f}, wn {mm['wn']:.3f} rad/s "
                        f"(period {mm.get('period', 0):.2f} s)"}
    chk += [damp("short_period", "alpha_deg", "SP", 0.0, 3.0, 0.03, 0.03),
            damp("phugoid", "vt", "Ph", 0.0, 120.0, 0.01, 0.01),
            damp("dutch_roll", "beta_deg", "DR", 0.0, 12.0, 0.02, 0.02)]
    for lab, mode, t in (("Ro", "roll", 0.3), ("Sl", "spiral", 0.0)):
        mm = m[mode]
        chk.append({"kind": "cursor_value", "signal": f"Rate{lab}/lambda", "t": t, "value": mm["re"], "rtol": 0.03,
                    "note": f"{mode}: released on its eigenvector, (d phi/dt)/phi reads the eigenvalue {mm['re']:.4f} 1/s "
                            f"(time constant {mm['tau']:.2f} s)"})
    chk.append(_cursor("RateSl/lambda", m["spiral"]["run"], "lambda", 20.0, 2e-4,
                       "spiral at 20 s: the slow phugoid it excites modulates the rate (the scipy run)"))
    for lab, mode, sig, key, ts, tol in (("SP", "short_period", "alpha_deg", "alpha_deg", (0.5, 1.0, 2.0), 2e-3),
                                         ("Ph", "phugoid", "vt", "vt", (10.0, 30.0, 60.0), 5e-3),
                                         ("DR", "dutch_roll", "beta_deg", "beta_deg", (1.0, 2.0, 4.0), 2e-3),
                                         ("Ro", "roll", "phi", "phi_deg", (0.2, 0.5), 2e-5),
                                         ("Sl", "spiral", "phi", "phi_deg", (10.0, 60.0), 2e-4)):
        for k, t in enumerate(ts):
            scale = RAD if sig == "phi" else 1.0
            chk.append(_cursor(f"{lab}/Air/{sig}", m[mode]["run"], key, t, tol, ref if k == 0 else None, scale=scale))
    return chk


def sim_entry(name: str, t_end: float, overrides: dict, checks: list) -> dict:
    return {"model": "cessna-sim", "settings": {"t_end": t_end, "output": {"points": int(round(t_end * 10)) + 1}},
            "overrides": {f"global:{k}": v for k, v in overrides.items()}, "checks": checks}


def trimmed_overrides(rec: dict) -> dict:
    st = rec["start"]
    c = st["controls"]
    o = dict(zip(START_NAMES, start_values(st)))
    o.update({"demo": 0.0, "yoke_hold": c["yoke_pitch"], "roll_hold": c["yoke_roll"], "ped_hold": c["pedals"],
              "thr_hold": c["throttle"], "flaps_hold": c["flaps"], "mixture0": c["mixture"]})
    return o


def expected_sim() -> dict:
    demo = SIMD["demo"]
    run = demo["run"]
    ms = demo["milestones"]
    ref = "the scipy run of the reference model with the same demo pilot (design/demo.py)"
    poh_p = DESIGN["poh"]["performance"]
    perf = DESIGN["performance"]["calibrated"]
    checks = [{"kind": "scene_bindings"}, NO_DIAG,
              {"kind": "cursor_value", "signal": "C172/Air/h", "t": 0.0, "value": SIMD["runway"]["h_cg"], "abs": 1e-4,
               "note": "the runway start is the static equilibrium on the gear (CG 1.25 m above the runway)"},
              {"kind": "max_abs_le", "signal": "C172/Air/h", "to_t": 14.0, "value": SIMD["runway"]["h_cg"] + 0.05,
               "note": "the take-off roll: on the runway until rotation (45 KCAS at about 15 s)"},
              {"kind": "zero_crossing", "signal": "Status/agl_ft", "direction": "up", "level": 50.0, "n": 1,
               "value": ms["t_50ft"], "abs": 1.0,
               "note": f"{ref}: 50 ft above the runway at {ms['t_50ft']:.1f} s, {ms['x_50ft'] / 0.3048:.0f} ft from brake "
                       f"release (POH Fig. 5-5: {poh_p['takeoff_50ft_ft'][0]:.0f} ft, flown by the demo pilot rather "
                       f"than the POH's short-field technique; see the README)"},
              {"kind": "max_abs_le", "signal": "Status/phi_deg", "value": 22.0,
               "note": "the turn: the demo pilot banks at most 20 deg"}]
    for t, tol in ((20.0, 0.3), (40.0, 0.5), (60.0, 1.0), (90.0, 2.0), (120.0, 3.0)):
        checks.append(_cursor("C172/Air/h", run, "h", t, tol, ref if t == 20.0 else None))
    for t in (20.0, 60.0, 100.0):
        checks.append(_cursor("Status/kias", run, "cas", t, 0.5, None, scale=1.0 / KT))
    checks.append(_cursor("C172/Air/psi", run, "psi", 120.0, 0.02, "the turn to the east (90 deg)"))
    checks.append(_cursor("C172/Air/x", run, "x", 15.0, 2.0, "the ground roll: distance from brake release"))
    export = {"inputs": {"yoke_pitch": {"min": -0.1, "max": 0.1}, "yoke_roll": {"min": -0.1, "max": 0.1},
                         "pedals": {"min": -0.1, "max": 0.1}, "throttle": {"min": 0.0, "max": 0.3},
                         "brake_l": {"min": 0.0, "max": 0.5}, "brake_r": {"min": 0.0, "max": 0.5},
                         "wind_n": {"min": -2.0, "max": 2.0}, "wind_e": {"min": -2.0, "max": 2.0}},
              "interface": {"inputs": [m for m, _, _ in SIM_INPUTS], "outputs": [m for m, _, _ in SIM_OUTPUT_SOURCES]},
              "note": "the FMU of apps/cessna-sim; its own acceptance is examples/export_cessna_check.py"}
    out = {"cessna-sim": {"checks": checks, "export": export}}
    # ---- the autopilot: heading and altitude hold from a trimmed 95 KCAS at 1000 m
    ap = SIMD["ap"]
    o = trimmed_overrides(ap)
    o.update({"ap_roll_mode": 2.0, "ap_alt_mode": 1.0, "ap_hdg": ap["hdg_ref_deg"], "ap_alt": ap["alt_ref"]})
    r = ap["run"]
    ch = [_cursor("C172/Air/psi", r, "psi", 60.0, 0.01, f"heading hold: 60 deg after a 60 deg turn ({ref.replace('demo pilot', 'autopilot')})"),
          {"kind": "max_abs_le", "signal": "Status/phi_deg", "value": 21.0, "note": "the bank is limited to 20 deg"},
          {"kind": "min_ge", "signal": "C172/Air/h", "value": ap["alt_ref"] - 15.0, "note": "altitude hold through the turn: within 15 m"},
          {"kind": "max_abs_le", "signal": "C172/Air/h", "value": ap["alt_ref"] + 15.0}]
    for t in (10.0, 20.0, 40.0):
        ch.append(_cursor("C172/Air/psi", r, "psi", t, 0.01))
        ch.append(_cursor("C172/Air/h", r, "h", t, 0.3))
    out["cessna-sim-autopilot"] = sim_entry("ap", ap["t_end"], o, ch)
    # ---- POH points: best-rate climb (full throttle) and full throttle at 8000 ft
    cl = SIMD["climb"]
    roc = cl["trim"]["vt"] * math.sin(cl["trim"]["gamma"]) / 0.3048 * 60.0
    kc = cl["trim"]["cas"] / KT
    ch = [{"kind": "cursor_value", "signal": "Status/vs_fpm", "t": 10.0, "value": _at(cl["run"], "hdot", 10.0) / 0.3048 * 60.0,
           "abs": 5.0, "note": f"trimmed full-throttle climb at 300 m, at the model's best-rate speed {kc:.0f} KCAS: "
                               f"{roc:.0f} ft/min (POH Fig. 5-6: {poh_p['roc_sl_fpm'][0]:.0f} ft/min at sea level, "
                               f"76 KIAS; see the README)"},
          {"kind": "cursor_value", "signal": "Status/vs_fpm", "t": 10.0, "value": poh_p["roc_sl_fpm"][0], "rtol": 0.05,
           "note": "POH best rate of climb (sea level, 15 C), within 5 % (the propeller tables are fitted to it, "
                   "c172_data.PROP_FIT)"},
          _cursor("Status/kias", cl["run"], "cas", 15.0, 0.3, None, scale=1.0 / KT)]
    out["cessna-sim-climb"] = sim_entry("climb", cl["t_end"], trimmed_overrides(cl), ch)
    cr = SIMD["cruise"]
    ch = [{"kind": "cursor_value", "signal": "Status/ktas", "t": 15.0, "value": cr["trim"]["vt"] / KT, "abs": 0.3,
           "note": f"full throttle (mixture leaned for best power) at 8000 ft: {cr['trim']['vt'] / KT:.1f} KTAS, "
                   f"{cr['trim']['rpm']:.0f} rpm, {cr['trim']['hp']:.0f} hp"},
          {"kind": "cursor_value", "signal": "Status/ktas", "t": 15.0, "value": poh_p["cruise75_8000_ktas"][0], "rtol": 0.06,
           "note": "POH: 120 KTAS at 75 % power, 8000 ft (the model makes "
                   f"{perf['vmax_8000']['hp'] / 160 * 100:.0f} % at full throttle there), within 6 %"},
          {"kind": "max_abs_le", "signal": "Status/vs_fpm", "from_t": 1.0, "value": 30.0, "note": "level: trimmed"}]
    out["cessna-sim-cruise"] = sim_entry("cruise", cr["t_end"], trimmed_overrides(cr), ch)
    return out


def expected() -> dict:
    return {"project": "cessna",
            "description": "Cessna 172P (JSBSim c172p data, the propeller fitted to the POH): the open-loop rigid-body modes and the flyable cessna-sim with "
                           "its landing gear and power train as bond graphs. Numbers come from design/design.json (an "
                           "independent scipy implementation of the same physics).",
            "models": {"cessna-open-loop": {"checks": expected_open_loop()}, **expected_sim()}}


def main() -> int:
    (EXAMPLE / "scenes").mkdir(exist_ok=True)
    (EXAMPLE / "models").mkdir(exist_ok=True)
    models = {"cessna-open-loop": model_open_loop(), "cessna-sim": model_sim()}
    for name, doc in models.items():
        doc["dashboard"] = DASHBOARDS[name]
        path = EXAMPLE / "models" / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "cessna", "models": list(models),
            "libraryDir": "library", "scenesDir": "scenes"}
    (EXAMPLE / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    (EXAMPLE / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
