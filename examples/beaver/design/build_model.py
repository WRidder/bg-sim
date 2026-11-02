# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the beaver models, scenes, generated blocks and expected.json from `design/design.json`.

    uv run examples/beaver/design/design.py        # first
    uv run examples/beaver/design/build_model.py

The airframe (a subsystem, `airframe()`) is the same in every model: the multibond rigid body on a
free joint, the air-data tap, the aerodynamic and propulsion coefficients, the wrench on the body
and the engine/propeller drivetrain as a rotational bond graph. The models differ in what flies it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path.insert(0, str(HERE))
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
SI = DESIGN["si"]
PT = DESIGN["point"]
DRV = DESIGN["drive"]
RAD = math.pi / 180.0
D2R = "57.29577951308232"


def num(v: float) -> str:
    return repr(float(v))


def vec(values) -> str:
    return "[" + ", ".join(repr(float(v)) for v in values) + "]"


def ex(v) -> str:
    """A number, or an expression over global parameters as it is."""
    return v if isinstance(v, str) else num(v)


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
        if isinstance(block, str):
            b = {"junction": block} if block in ("0", "1") else {"ref": block}
        else:
            b = block
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
        parent.node(name, {"subsystem": {"ports": self.ports, "diagram": self.doc()}}, x, y)
        return name


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value, "unit": unit, "description": description}


def settings(t_end: float, points: int, reltol=1e-9, abstol=1e-9) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 100000}


def model_doc(name, comment, d: Diagram, sett, plots, scene, bindings, parameters) -> dict:
    return {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
            "diagram": d.doc(), "settings": sett, "plots": plots,
            "scene": {"file": scene} if scene else None, "bindings": bindings, "parameters": parameters}


# --------------------------------------------------------------------------- generated blocks
AERO_TERMS = {  # coefficient -> [(parameter, regressor)] [FDC modbuild.m, REP Table C.3]
    "CX": [("CX0", "1.0"), ("CXa", "a"), ("CXa2", "a * a"), ("CXa3", "a * a * a"), ("CXq", "qh"), ("CXdr", "dr_r"),
            ("CXdf", "df_r"), ("CXadf", "a * df_r")],
    "CY": [("CY0", "1.0"), ("CYb", "beta"), ("CYp", "ph"), ("CYr", "rh"), ("CYda", "da_r"), ("CYdr", "dr_r"),
            ("CYdra", "dr_r * a")],
    "CZ": [("CZ0", "1.0"), ("CZa", "a"), ("CZa3", "a * a * a"), ("CZq", "qh"), ("CZde", "de_r"),
            ("CZdeb2", "de_r * beta * beta"), ("CZdf", "df_r"), ("CZadf", "a * df_r")],
    "Cl": [("Cl0", "1.0"), ("Clb", "beta"), ("Clp", "ph"), ("Clr", "rh"), ("Clda", "da_r"), ("Cldr", "dr_r"),
            ("Cldaa", "da_r * a")],
    "Cm": [("Cm0", "1.0"), ("Cma", "a"), ("Cma2", "a * a"), ("Cmq", "qh"), ("Cmde", "de_r"), ("Cmb2", "beta * beta"),
            ("Cmr", "rh"), ("Cmdf", "df_r")],
    "Cn": [("Cn0", "1.0"), ("Cnb", "beta"), ("Cnp", "ph"), ("Cnr", "rh"), ("Cnda", "da_r"), ("Cndr", "dr_r"),
            ("Cnq", "qh"), ("Cnb3", "beta * beta * beta")],
}


def aero_block() -> str:
    """library/BeaverAero.jl: the polynomial aerodynamic model, its coefficients as parameters."""
    A = DESIGN["aero"]
    L = ["@block BeaverAero begin",
         "    # Aerodynamic force and moment coefficients of the DHC-2 'Beaver' (generated by",
         "    # design/build_model.py from design/beaver_data.py). Polynomials identified from flight tests",
         "    # by Tjee & Mulder (TU Delft report LR-556, 1988), as in the FDC 1.4 toolbox [FDC modbuild.m,",
         "    # REP Table C.3]; body axes FRD, angles in rad, valid for 35-55 m/s in the normal flight",
         "    # envelope (no stall). With ph = p b/2V, qh = q c/V, rh = r b/2V:"]
    for c, terms in AERO_TERMS.items():
        L.append(f"    #   {c} = " + " + ".join(f"{p}" + ("" if r == "1.0" else f" {r}") for p, r in terms))
    L += ["    # The beta-dot term (CYbdot) is not here: BeaverWrench applies it the way FDC does.",
          "    @inputs begin",
          "        V::Real, [unit = \"m/s\"]",
          "        alpha::Real, [unit = \"rad\"]",
          "        beta::Real, [unit = \"rad\"]",
          "        p::Real, [unit = \"rad/s\"]",
          "        q::Real, [unit = \"rad/s\"]",
          "        r::Real, [unit = \"rad/s\"]",
          "        de::Real, [description = \"Elevator (deg), positive trailing edge down\"]",
          "        da::Real, [description = \"Ailerons (deg), da_right - da_left, positive rolls left\"]",
          "        dr::Real, [description = \"Rudder (deg), positive trailing edge left\"]",
          "        df::Real, [description = \"Flaps (deg), positive down\"]",
          "    end",
          "    @outputs begin"]
    for c in AERO_TERMS:
        L.append(f"        {c}::Real")
    L += ["    end", "    @parameters begin",
          f"        b::Real = {num(SI['b'])}, [unit = \"m\", description = \"Span\"]",
          f"        c::Real = {num(SI['c'])}, [unit = \"m\", description = \"Mean aerodynamic chord\"]"]
    for terms in AERO_TERMS.values():
        for p, _ in terms:
            L.append(f"        {p}::Real = {num(A[p])}")
    L += ["    end", "    @variables begin"]
    for v in ("a", "ph", "qh", "rh", "de_r", "da_r", "dr_r", "df_r"):
        L.append(f"        {v}::Real = 0.0")
    L += ["    end", "    @equations begin",
          "        a ~ alpha",
          "        ph ~ p * b / (2.0 * V)",
          "        qh ~ q * c / V",
          "        rh ~ r * b / (2.0 * V)",
          f"        de_r ~ de / {D2R}",
          f"        da_r ~ da / {D2R}",
          f"        dr_r ~ dr / {D2R}",
          f"        df_r ~ df / {D2R}"]
    for c, terms in AERO_TERMS.items():
        L.append(f"        {c} ~ " + " + ".join(p if r == "1.0" else f"{p} * {r}" for p, r in terms))
    L += ["    end", "end", ""]
    return "\n".join(L)


TRAIL_N = 12          # dots per trail
TRAIL_TS = 0.25       # s between dots (a trail of 3 s, 11 m apart at 45 m/s)


def trail_block() -> str:
    """library/BeaverTrail.jl: a shift register of past positions, sampled every TRAIL_TS (generated:
    the DSL has no arrays of discrete variables). The same block as the f16's F16Trail."""
    n, ts = TRAIL_N, TRAIL_TS
    L = ["@block BeaverTrail begin",
         "    # Scene helper (no physics, generated by design/build_model.py): the dots of a flight-path",
         f"    # trail, {n} past positions of an aircraft {ts:g} s apart, relative to the reference aircraft",
         "    # of the view (see BeaverView) plus a formation offset. Every tick stores the position in a",
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


# --------------------------------------------------------------------------- the airframe
PROP_VIS = 0.05       # the 3D propeller turns at 1/20 of the shaft speed (the true 30 rev/s would alias)

AIRFRAME_OUTPUTS = [  # (port name, node, node port, unit)
    ("V", "Air", "V", "m/s"), ("alpha_deg", "Air", "alpha_deg", None), ("beta_deg", "Air", "beta_deg", None),
    ("p_deg", "Air", "p_deg", None), ("q_deg", "Air", "q_deg", None), ("r_deg", "Air", "r_deg", None),
    ("phi_deg", "Air", "phi_deg", None), ("theta_deg", "Air", "theta_deg", None), ("psi_deg", "Air", "psi_deg", None),
    ("gamma_deg", "Air", "gamma_deg", None), ("H", "Air", "H", "m"), ("north", "Air", "north", "m"),
    ("east", "Air", "east", "m"), ("hdot", "Air", "hdot", "m/s"), ("vc", "Air", "vc", "m/s"),
    ("theta", "Air", "theta", "rad"), ("phi", "Air", "phi", "rad"), ("psi", "Air", "psi", "rad"),
    ("q", "Air", "q", "rad/s"), ("r", "Air", "r", "rad/s"), ("p", "Air", "p", "rad/s"), ("phidot", "Air", "phidot", "rad/s"),
    ("n_shaft", "Engine", "n_shaft", None), ("P", "Prop", "P", None), ("dpt", "Prop", "dpt", None), ("nz", "Forces", "nz", None),
    ("prop_angle", "PropAngle", "y", "rad"),
]


def airframe(start_pose: dict, start_P: list, wind: bool = False, drivetrain: str = "drivetrain") -> Diagram:
    """One Beaver: inputs de, da, dr, df (deg), pz (inch Hg), n (rpm); with wind also wn, we, wd."""
    d = Diagram()
    # ---- multibond rigid body on a free joint (principal axes) and the external wrench
    d.node("World", "stdlib:multibond/GroundSpatial", 40, 40)
    d.node("Free", "stdlib:spatial/Free3D", 220, 40, starts={k: ex(v) for k, v in start_pose.items()})
    d.node("Body", "stdlib:spatial/RigidBody3D", 420, 40,
           params={"m": num(SI["mass"]), "J": vec(SI["J_principal"]), "g0": num(SI["g0"])},
           starts={"inertia/P": vec(start_P)})
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
    d.note("**Airframe.** RigidBody3D on its principal axes (the product of inertia Jxz tilts them "
           f"{SI['eps'] / RAD:.2f} deg from the body x axis); the air and engine wrench (BeaverWrench) is a "
           "modulated source on the body, applied in the geometric body frame through the Mount.", 40, -60, 900, 50, "blue")
    # ---- air data
    d.node("Air", "project:BeaverAirData", 420, 300, params={"eps": num(SI["eps"])})
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
    for k, nm in enumerate(("de", "da", "dr", "df", "pz", "n")):
        d.node(f"{nm}In", "stdlib:continuous/Gain", 40, 520 + 60 * k, params={"k": "1.0"})
        d.port(nm, "input", f"{nm}In", "u")
    # ---- aerodynamics
    d.node("Aero", "project:BeaverAero", 700, 300)
    for p in ("V", "alpha", "beta", "p", "q", "r"):
        d.sig("Air", p, "Aero", p)
    for nm in ("de", "da", "dr", "df"):
        d.sig(f"{nm}In", "y", "Aero", nm)
    # ---- engine and propeller drivetrain: a rotational bond graph on the crank
    w0 = DRV["w0"]
    d.node("Engine", "project:BeaverEngine", 420, 640)
    d.node("EngineTorque", "stdlib:bondgraph/MSe", 620, 640, params={"gain": "1.0"})
    d.node("Crank", "1", 780, 640)
    d.node("Inertia", "stdlib:bondgraph/I", 780, 760, params={"i": num(DRV["J"])}, starts={"P": num(DRV["J"] * w0)})
    d.node("PropLoad", "stdlib:bondgraph/MSe", 940, 640, params={"gain": "-1.0"})
    d.node("Tacho", "stdlib:converters/SpeedSensor", 780, 540)
    d.bond("EngineTorque", "p", "Crank", None)
    d.bond("Crank", None, "Inertia", "p")
    d.bond("PropLoad", "p", "Crank", None)
    d.bond("Crank", None, "Tacho", "a")
    d.node("Governor", "project:PropGovernor", 940, 760,
           params={"Kp": num(DRV["Kp"]), "Ki": num(DRV["Ki"]), "D": num(DRV["D"])}, starts={"ci": num(DRV["Cq0"])})
    d.sig("pzIn", "y", "Engine", "pz")
    d.sig("nIn", "y", "Engine", "n_cmd")
    d.sig("Tacho", "y", "Engine", "w")
    d.sig("Air", "rho", "Engine", "rho")
    d.sig("Engine", "Te", "EngineTorque", "u")
    d.sig("Tacho", "y", "Governor", "w")
    d.sig("nIn", "y", "Governor", "n_cmd")
    d.sig("Air", "rho", "Governor", "rho")
    d.sig("Governor", "Q", "PropLoad", "u")
    d.node("PropVis", "stdlib:continuous/Gain", 1100, 540, params={"k": num(PROP_VIS)})
    d.node("PropAngle", "stdlib:continuous/Integrator", 1240, 540)
    d.sig("Tacho", "y", "PropVis", "u")
    d.sig("PropVis", "y", "PropAngle", "u")
    d.note("**Drivetrain (bond graph, our addition).** 1-junction Crank: engine torque P(pz, n, rho)/w (MSe), "
           f"crank + propeller inertia I = {DRV['J']:g} kg m^2, the propeller's torque -Q (MSe) from the governor of the "
           "constant-speed propeller, tachometer (SpeedSensor, which makes the bond graph rotational). Global `drivetrain`: 1 the thrust comes from the shaft power Q w, "
           "0 from the source's algebraic power at the commanded rpm (exact FDC).", 420, 860, 900, 60, "blue")
    # ---- propulsion coefficients (algebraic in dpt, as the source)
    d.node("Prop", "project:BeaverPropulsion", 1100, 640, params={"drivetrain": drivetrain})
    d.sig("Engine", "P_src", "Prop", "P_src")
    d.sig("Governor", "P_shaft", "Prop", "P_shaft")
    d.sig("Air", "rho", "Prop", "rho")
    d.sig("Air", "V", "Prop", "V")
    d.sig("Air", "alpha", "Prop", "alpha")
    # ---- the wrench
    d.node("Forces", "project:BeaverWrench", 1100, 300,
           params={"S": num(SI["S"]), "b": num(SI["b"]), "c": num(SI["c"]), "m": num(SI["mass"]),
                   "g0": num(SI["g0"]), "CYbdot": num(DESIGN["aero"]["CYbdot"])})
    for c in ("CXa", "CYa", "CZa", "Cla", "Cma", "Cna"):
        d.sig("Aero", c[:-1] if c.endswith("a") else c, "Forces", c)
    for c in ("CXp", "CYp", "CZp", "Clp", "Cmp", "Cnp"):
        d.sig("Prop", c, "Forces", c)
    for p in ("V", "alpha", "beta", "p", "r", "theta", "phi", "rho", "g"):
        d.sig("Air", p, "Forces", p)
    for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
        d.sig("Forces", p, "Wrench", p)
    for name, node, port, unit in AIRFRAME_OUTPUTS:
        d.port(name, "output", node, port, unit)
    d.port("pose", "output", "Air", "gB", None, size=7)
    return d


def trim_constants(d: Diagram, x: float, y: float) -> dict:
    """Constants at the trim point: de, da, dr, df (deg), pz, n. Returns {input: node}."""
    u0 = PT["u0"]
    vals = {"de": u0[0] / RAD, "da": u0[1] / RAD, "dr": u0[2] / RAD, "df": u0[3] / RAD, "n": u0[4], "pz": u0[5]}
    out = {}
    for k, (nm, v) in enumerate(vals.items()):
        node = f"Trim_{nm}"
        d.node(node, "stdlib:sources/Constant", x, y + 60 * k, params={"value": num(v)})
        out[nm] = node
    return out


# --------------------------------------------------------------------------- the 3D scene
FLOOR_PERIOD = 50.0
FLOOR_HALF = 300.0
VIEW_LIFT = 6.0
BOUNDS = 360.0         # m, invisible markers beyond the floor: the view's Fit centres on the framed aircraft
FLOOR_DEPTH = 150.0
SLOT = 25.0           # m between the aircraft of one model
PIVOTS = {  # hinge point and axis of each moving part (design/make_meshes.py PIVOTS)
    "elevator": ((-5.9, 0.0, 0.42), (0.0, 1.0, 0.0)),
    "aileron_l": ((-0.62, 4.25, 0.95), (0.0, 1.0, 0.0)),
    "aileron_r": ((-0.62, -4.25, 0.95), (0.0, 1.0, 0.0)),
    "flap_l": ((-0.62, 0.75, 0.95), (0.0, 1.0, 0.0)),
    "flap_r": ((-0.62, -0.75, 0.95), (0.0, 1.0, 0.0)),
    "rudder": ((-5.63, 0.0, 0.55), (0.0, 0.0, 1.0)),
    "prop": ((2.78, 0.0, 0.18), (1.0, 0.0, 0.0)),
}
# joint position = gain * signal: elevator, flaps trailing edge down = negative rotation about +y;
# ailerons: da = da_right - da_left, split half and half (right trailing edge down for da > 0);
# rudder: trailing edge left (positive dr) = negative rotation about +z.
SURFACE_GAINS = {"elevator": ("de", -RAD), "aileron_l": ("da", 0.5 * RAD), "aileron_r": ("da", -0.5 * RAD),
                 "flap_l": ("df", -RAD), "flap_r": ("df", -RAD), "rudder": ("dr", -RAD), "prop": ("prop", 1.0)}
TRAIL_RGBA = {"yellow": "1.0 0.9 0.4 1", "red": "1.0 0.55 0.5 1", "blue": "0.55 0.75 1.0 1",
              "white": "0.95 0.95 0.98 1", "green": "0.6 0.9 0.65 1", "orange": "1.0 0.7 0.4 1"}


def scene_sdf(name: str, aircraft: list[tuple[str, str]], dots: list[int], comment: str) -> str:
    """aircraft: (tag, paint scheme); the first one is the reference the view keeps framed."""
    L = ['<?xml version="1.0"?>', "<!--", comment, "-->", '<sdf version="1.9">', f'  <model name="{name}">',
         '    <link name="ground">', "      <pose>0 0 0 0 0 0</pose>",
         '      <visual name="floor">', "        <pose>0 0 -0.5 0 0 0</pose>",
         f"        <geometry><box><size>{2 * FLOOR_HALF:g} {2 * FLOOR_HALF:g} 1</size></box></geometry>",
         "        <material><diffuse>0.30 0.42 0.52 1</diffuse></material>", "      </visual>"]
    n = int(FLOOR_HALF // FLOOR_PERIOD)
    for k in range(-n, n + 1):
        c = k * FLOOR_PERIOD
        L += [f'      <visual name="stripe_x{k + n}">', f"        <pose>{c:g} 0 0.05 0 0 0</pose>",
              f"        <geometry><box><size>3 {2 * FLOOR_HALF:g} 0.1</size></box></geometry>",
              "        <material><diffuse>0.52 0.62 0.68 1</diffuse></material>", "      </visual>",
              f'      <visual name="stripe_y{k + n}">', f"        <pose>0 {c:g} 0.05 0 0 0</pose>",
              f"        <geometry><box><size>{2 * FLOOR_HALF:g} 3 0.1</size></box></geometry>",
              "        <material><diffuse>0.52 0.62 0.68 1</diffuse></material>", "      </visual>"]
    L.append("    </link>")
    L += ['    <link name="bounds">', "      <pose>0 0 0 0 0 0</pose>"]
    for k, sgn in enumerate((1, -1)):
        L += [f'      <visual name="bound_{k}">', f"        <pose>{sgn * BOUNDS:g} {sgn * BOUNDS:g} {VIEW_LIFT + sgn * BOUNDS:g} 0 0 0</pose>",
              "        <geometry><box><size>0.01 0.01 0.01</size></box></geometry>",
              "        <material><diffuse>0 0 0 0</diffuse></material>", "      </visual>"]
    L.append("    </link>")
    for tag, scheme in aircraft:
        L += [f'    <link name="ac_{tag}">', "      <pose>0 0 0 0 0 0</pose>",
              f'      <visual name="airframe_{tag}">', "        <pose>0 0 0 0 0 0</pose>",
              f"        <geometry><mesh><uri>meshes/beaver_body_{scheme}.glb</uri></mesh></geometry>", "      </visual>",
              "    </link>"]
        for part, ((x, y, z), (ax, ay, az)) in PIVOTS.items():
            L += [f'    <link name="{part}_{tag}">', f"      <pose>{x:g} {y:g} {z:g} 0 0 0</pose>",
                  f'      <visual name="{part}_vis_{tag}">', "        <pose>0 0 0 0 0 0</pose>",
                  f"        <geometry><mesh><uri>meshes/beaver_{part}.glb</uri></mesh></geometry>", "      </visual>",
                  "    </link>",
                  f'    <joint name="{part}_{tag}_hinge" type="revolute">', f"      <parent>ac_{tag}</parent>",
                  f"      <child>{part}_{tag}</child>", f"      <axis><xyz>{ax:g} {ay:g} {az:g}</xyz></axis>",
                  "    </joint>"]
        for k in dots:
            r = 0.45 - 0.015 * k
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
    "  (blocks BeaverView and BeaverTrail). Other aircraft fly in formation slots 25 m to the side. The floor\n"
    "  is a reference plane 150 m below the start altitude of the first aircraft; it follows climbs and\n"
    "  descents of up to 100 m and its 50 m stripes scroll with the ground track. The dots behind each\n"
    "  aircraft are its flight path over the last seconds. The control surfaces turn on their hinge lines\n"
    "  (links elevator_*, aileron_l_*, ..., joints *_hinge): elevator and flaps trailing edge down = a negative\n"
    "  rotation about the body y axis (left), the ailerons split da = da_right - da_left half and half, the\n"
    "  rudder's trailing edge left (positive dr) = a negative rotation about z. The propeller turns at 1/20\n"
    "  of the shaft speed (the true 30 rev/s would alias at the display rate). The floats are decoration:\n"
    "  the model has no water or ground contact.")


def view(d: Diagram, crafts: list[dict], z0, x: float, y: float, dots: list[int], reach: float = 100.0):
    """View and trail blocks; crafts: {lab, tag, dy, signals: {de, da, dr, df, prop}}. Returns bindings."""
    ref = crafts[0]["lab"]
    bindings = []
    for k, c in enumerate(crafts):
        lab, tag, dy = c["lab"], c["tag"], c["dy"]
        vnode, tnode = f"{lab}View", f"{lab}Trail"
        d.node(vnode, "project:BeaverView", x, y + 120 * k,
               params={"dy": num(dy), "dz": num(VIEW_LIFT), "depth": num(FLOOR_DEPTH + VIEW_LIFT),
                       "period": num(FLOOR_PERIOD), "z0": ex(z0), "reach": num(reach)})
        d.node(tnode, "project:BeaverTrail", x + 200, y + 120 * k, params={"dy": num(dy), "dz": num(VIEW_LIFT)})
        for nd in (vnode, tnode):
            d.sig(lab, "pose", nd, "g")
            d.sig(ref, "pose", nd, "g0")
        bindings.append({"target": f"link:ac_{tag}", "property": "pose", "signal": [f"{vnode}/pose[{i}]" for i in range(1, 8)]})
        for part, (key, gain) in SURFACE_GAINS.items():
            s = c["signals"].get(key)
            if s is not None:
                bindings.append({"target": f"joint:{part}_{tag}_hinge", "property": "position", "signal": s, "gain": gain})
        for j in dots:
            bindings.append({"target": f"link:trail_{tag}_{j}", "property": "pose",
                             "signal": [f"{tnode}/d{j}[{i}]" for i in range(1, 8)]})
    bindings.append({"target": "link:ground", "property": "pose", "signal": [f"{ref}View/ground[{i}]" for i in range(1, 8)]})
    return bindings


def write_scene(name: str, crafts: list[dict], dots: list[int], comment: str) -> str:
    path = EXAMPLE / "scenes" / f"{name}.sdf"
    path.parent.mkdir(exist_ok=True)
    path.write_text(scene_sdf(name, [(c["tag"], c["scheme"]) for c in crafts], dots, comment + "\n" + SCENE_NOTE),
                    encoding="utf-8", newline="\n")
    return f"scenes/{name}.sdf"


SCHEMES = ["yellow", "red", "blue", "white", "green", "orange"]
MULTI_DOTS = [2, 4, 6, 8, 10, 12]
# beaver-steps: six aircraft; fewer dots keep the 3D stream's signal list under the 8 KiB request line
STEPS_DOTS = [3, 6, 9, 12]
SIM_DOTS = list(range(1, TRAIL_N + 1))


def slots(n):
    """Formation offsets (m, +y west/left): 0, -25, +25, -50, +50, -75."""
    out = [0.0]
    k = 1
    while len(out) < n:
        out.append(-SLOT * k)
        if len(out) < n:
            out.append(SLOT * k)
        k += 1
    return out


# --------------------------------------------------------------------------- model 1: the modes
def model_modes():
    d = Diagram()
    rel = DESIGN["releases"]
    params = [g("drivetrain", "0.0", None, "Thrust from the drivetrain's shaft power (1), or the source's algebraic "
                "power at the prescribed rpm (0, exact FDC; the validation mode)")]
    trim = trim_constants(d, 40, 40)
    crafts = []
    for k, r in enumerate(rel):
        lab = r["label"]
        x, y = 400 + 340 * k, 40   # side by side: the airframe subsystem is tall
        airframe(r["start_pose"], r["start_P"]).subsystem(d, lab, x, y)
        for nm, node in trim.items():
            d.sig(node, "y", lab, nm)
        crafts.append({"lab": lab, "tag": lab.lower(), "scheme": SCHEMES[k], "dy": slots(len(rel))[k],
                       "signals": {"prop": f"{lab}/PropAngle/y"}})
    for lab in ("Roll", "Spiral"):
        k = [r["label"] for r in rel].index(lab)
        d.node(f"Grow{lab}", "project:GrowthRate", 400 + 340 * k + 220, 340)
        d.sig(lab, "phidot", f"Grow{lab}", "xdot")
        d.sig(lab, "phi", f"Grow{lab}", "x")
    d.note("**Modes.** Five Beavers at the FDC trim (45 m/s, 6000 ft, flaps up, 1800 rpm), each released on one "
           "eigenvector of the coupled linear model: phugoid (2 m/s of airspeed), short period (1 deg of alpha), "
           "Dutch roll (1 deg of sideslip), roll and spiral (2 deg of bank). GrowthRate reads the real modes as "
           "phidot/phi.", 40, -80, 900, 50, "blue")
    plots = [
        {"id": "p1", "title": "Phugoid: airspeed (m/s)", "signals": ["Phugoid/Air/V"]},
        {"id": "p2", "title": "Short period: angle of attack (deg)", "signals": ["ShortPeriod/Air/alpha_deg"]},
        {"id": "p3", "title": "Dutch roll: sideslip (deg)", "signals": ["DutchRoll/Air/beta_deg"]},
        {"id": "p4", "title": "Roll and spiral: bank (deg)", "signals": ["Roll/Air/phi_deg", "Spiral/Air/phi_deg"]},
        {"id": "p5", "title": "Growth rate phidot/phi (1/s)", "signals": ["GrowRoll/lambda", "GrowSpiral/lambda"]},
        {"id": "p6", "title": "Altitude (m)", "signals": [f"{r['label']}/Air/H" for r in rel]},
    ]
    bindings = view(d, crafts, PT["H"], 2160, 40, MULTI_DOTS)
    scene = write_scene("beaver-modes", crafts, MULTI_DOTS,
                        "  beaver-modes: Phugoid (yellow, framed), ShortPeriod (red), DutchRoll (blue), Roll (white), Spiral (green).")
    return model_doc("beaver-modes",
                     "The FDC 'Beaver' at its trim point (45 m/s, 6000 ft), five airframes each released on one mode. "
                     "Generated by design/build_model.py; see the README.",
                     d, settings(150.0, 1501), plots, scene, bindings, params)


# --------------------------------------------------------------------------- model 2: the steps
STEP_GLOBALS = {"Elevator": ("step_de", "deg", "Elevator block (deg, 1-3 s)"),
                "Aileron": ("step_da", "deg", "Aileron block (deg, 1-3 s)"),
                "Rudder": ("step_dr", "deg", "Rudder block (deg, 1-3 s)"),
                "Flap": ("step_df", "deg", "Flap ramp (deg in 3 s from 1 s)"),
                "Rpm": ("step_n", None, "Engine speed ramp (rpm in 4 s from 1 s)"),
                "Manifold": ("step_pz", None, "Manifold pressure ramp (inch Hg in 2 s from 1 s)")}


def model_steps():
    d = Diagram()
    steps = DESIGN["steps"]
    fast = num(DESIGN["fast"])
    params = [g("drivetrain", "0.0", None, "Thrust from the drivetrain's shaft power (1), or the source's algebraic "
                "power at the prescribed rpm (0, exact FDC; the validation mode)")]
    trim = trim_constants(d, 40, 40)
    crafts = []
    pose0, P0 = PT["start_pose"], PT["start_P"]
    for k, s in enumerate(steps):
        lab = s["label"]
        X, y = 300 + 560 * (k % 3), 40 + 900 * (k // 3)   # two rows of three: the airframe is tall
        gname, unit, desc = STEP_GLOBALS[lab]
        amp = s["amp"] / RAD if s["input"] in ("de", "da", "dr", "df") else s["amp"]
        params.append(g(gname, num(amp), unit, desc))
        airframe(pose0, P0).subsystem(d, lab, X + 400, y)
        idx = s["input"]
        base = trim[idx]
        if s["kind"] == "block":
            d.node(f"{lab}On", "stdlib:sources/Ramp", X, y,
                   params={"t_start": num(s["t0"]), "slope": f"{gname} / {fast}", "duration": fast})
            d.node(f"{lab}Off", "stdlib:sources/Ramp", X, y + 60,
                   params={"t_start": num(s["t0"] + s["dur"]), "slope": f"-{gname} / {fast}", "duration": fast})
        else:
            d.node(f"{lab}On", "stdlib:sources/Ramp", X, y,
                   params={"t_start": num(s["t0"]), "slope": f"{gname} / {num(s['dur'])}", "duration": num(s["dur"])})
            d.node(f"{lab}Off", "stdlib:sources/Constant", X, y + 60, params={"value": "0.0"})
        d.node(f"{lab}Mx", "stdlib:continuous/Mux3", X + 140, y + 30)
        d.node(f"{lab}Input", "stdlib:continuous/Sum", X + 260, y + 30, params={"signs": "[1.0, 1.0, 1.0]"}, constants={"N": 3})
        d.sig(base, "y", f"{lab}Mx", "u1")
        d.sig(f"{lab}On", "y", f"{lab}Mx", "u2")
        d.sig(f"{lab}Off", "y", f"{lab}Mx", "u3")
        d.sig(f"{lab}Mx", "y", f"{lab}Input", "u")
        for nm, node in trim.items():
            if nm == idx:
                d.sig(f"{lab}Input", "y", lab, nm)
            else:
                d.sig(node, "y", lab, nm)
        sigs = {nm: (f"{lab}Input/y" if nm == idx else f"{trim[nm]}/y") for nm in ("de", "da", "dr", "df")}
        sigs["prop"] = f"{lab}/PropAngle/y"
        crafts.append({"lab": lab, "tag": lab.lower(), "scheme": SCHEMES[k], "dy": slots(len(steps))[k], "signals": sigs})
    d.note("**Control steps.** Six Beavers at the FDC trim, each with one input as in the thesis' figures 5-2 to 5-7: "
           "3 deg blocks of elevator, ailerons and rudder (1-3 s), 3 deg of flap in 3 s, +200 rpm in 4 s and +2 inch Hg "
           "in 2 s.", 40, -80, 900, 50, "blue")
    labs = [s["label"] for s in steps]
    plots = [
        {"id": "p1", "title": "Airspeed (m/s)", "signals": [f"{l}/Air/V" for l in labs]},
        {"id": "p2", "title": "Angle of attack (deg)", "signals": [f"{l}/Air/alpha_deg" for l in labs]},
        {"id": "p3", "title": "Pitch angle (deg)", "signals": [f"{l}/Air/theta_deg" for l in labs]},
        {"id": "p4", "title": "Sideslip (deg)", "signals": [f"{l}/Air/beta_deg" for l in labs]},
        {"id": "p5", "title": "Bank (deg)", "signals": [f"{l}/Air/phi_deg" for l in labs]},
        {"id": "p6", "title": "Altitude (m)", "signals": [f"{l}/Air/H" for l in labs]},
        {"id": "p7", "title": "dpt and engine power (kW)", "signals": ["Manifold/Prop/dpt", "Rpm/Prop/dpt", "Manifold/Prop/P", "Rpm/Prop/P"]},
        {"id": "p8", "title": "Shaft speed (rpm)", "signals": ["Rpm/Engine/n_shaft", "Manifold/Engine/n_shaft"]},
    ]
    bindings = view(d, crafts, PT["H"], 2040, 40, STEPS_DOTS)
    scene = write_scene("beaver-steps", crafts, STEPS_DOTS,
                        "  beaver-steps: Elevator (yellow, framed), Aileron (red), Rudder (blue), Flap (white), Rpm (green), "
                        "Manifold (orange).")
    return model_doc("beaver-steps",
                     "Open-loop responses of the FDC 'Beaver' (45 m/s, 6000 ft) to the thesis' control inputs on each axis "
                     "and the engine. Generated by design/build_model.py; see the README.",
                     d, settings(DESIGN["t_steps"], int(DESIGN["t_steps"] * 20) + 1), plots, scene, bindings, params)


# --------------------------------------------------------------------------- model 3: beaver-sim
DEMO = DESIGN["demo_spec"]
SERVO = DESIGN["servo"]
PILOT = DESIGN["pilot"]
SIM_INPUTS = [  # (marker, start value, description)
    ("col_pitch", "0.0", "column pitch, -1 full forward .. +1 full aft"),
    ("col_roll", "0.0", "column roll (wheel), -1 full left .. +1 full right"),
    ("pedals", "0.0", "rudder pedals, -1 full left .. +1 full right"),
    ("flaps_deg", "0.0", "flaps (deg, 0 .. 20)"),
    ("elev_trim_deg", num(PT["de0"]), "elevator trim (deg of elevator)"),
    ("pz_inhg", num(PT["pz0"]), "manifold pressure (inch Hg)"),
    ("rpm", num(PT["n0"]), "propeller lever: governed engine speed (rpm)"),
    ("ap_pitch", "1.0", "autopilot pitch mode: 0 off, 1 pitch attitude hold, 2 altitude hold"),
    ("ap_roll", "1.0", "autopilot roll mode: 0 off, 1 roll attitude hold, 2 heading hold"),
    ("theta_ref_deg", num(PT["theta0"]), "pitch attitude reference (deg)"),
    ("phi_ref_deg", "0.0", "bank reference (deg)"),
    ("psi_ref_deg", "0.0", "heading reference (deg)"),
    ("h_ref_m", num(PT["H0"]), "altitude reference (m)"),
    ("wind_n", "0.0", "wind towards north (m/s)"),
    ("wind_e", "0.0", "wind towards east (m/s)"),
    ("wind_d", "0.0", "wind downwards (m/s)"),
]
SIM_OUTPUT_SOURCES = [  # (marker, node, port)
    ("north_m", "Beaver", "north"), ("east_m", "Beaver", "east"), ("alt_m", "Beaver", "H"),
    ("q_w", "PoseOut", "y1"), ("q_x", "PoseOut", "y2"), ("q_y", "PoseOut", "y3"), ("q_z", "PoseOut", "y4"),
    ("phi_deg", "Beaver", "phi_deg"), ("theta_deg", "Beaver", "theta_deg"), ("psi_deg", "Beaver", "psi_deg"),
    ("gamma_deg", "Beaver", "gamma_deg"), ("p_dps", "Beaver", "p_deg"), ("q_dps", "Beaver", "q_deg"),
    ("r_dps", "Beaver", "r_deg"), ("tas_mps", "Beaver", "V"), ("cas_mps", "Beaver", "vc"),
    ("alpha_deg", "Beaver", "alpha_deg"), ("beta_deg", "Beaver", "beta_deg"), ("vs_mps", "Beaver", "hdot"),
    ("nz_g", "Beaver", "nz"), ("elev_deg", "Controls", "de"), ("ail_deg", "Controls", "da"),
    ("rud_deg", "Controls", "dr"), ("flap_deg", "Controls", "df"), ("engine_rpm", "Beaver", "n_shaft"),
    ("power_kw", "Beaver", "P"), ("dpt", "Beaver", "dpt"), ("prop_angle", "Beaver", "prop_angle"),
]
FAST = 0.05


def sim_globals() -> list[dict]:
    D = DEMO
    out = [
        g("drivetrain", "1.0", None, "Engine/propeller drivetrain: 1 the thrust comes from the shaft power of the "
          "bond-graph drivetrain (crank inertia, constant-speed propeller), 0 the source's algebraic power at the "
          "commanded rpm (exact FDC)"),
        g("elev_trim", num(PT["de0"]), "deg", "Elevator trim (the trim of 45 m/s, 6000 ft)"),
        g("ail_trim", num(PT["da0"]), "deg", "Aileron offset that trims the propeller's roll (ours: the source has no trim tabs)"),
        g("rud_trim", num(PT["dr0"]), "deg", "Rudder offset that trims the propeller's yaw (ours)"),
        g("t_climb", num(D["t_climb"]), "s", "Demo: climb power and pitch-up at"),
        g("climb_pz", num(D["climb_pz"]), None, "Demo: climb manifold pressure (inch Hg)"),
        g("climb_rpm", num(D["climb_rpm"]), None, "Demo: climb rpm"),
        g("climb_dtheta", num(D["climb_dtheta"]), "deg", "Demo: pitch-up of the attitude hold for the climb"),
        g("t_turn", num(D["t_turn"]), "s", "Demo: heading hold engaged at"),
        g("turn_psi", num(D["turn_psi"]), "deg", "Demo: heading to turn to"),
        g("t_level", num(D["t_level"]), "s", "Demo: altitude hold engaged at"),
        g("level_dh", num(D["level_dh"]), "m", "Demo: altitude to level off at, above the start"),
        g("t_power", num(D["t_power"]), "s", "Demo: power back to the trim setting at"),
        g("ap_pitch_start", "1.0", None, "Autopilot pitch mode before t_level (0 off, 1 PAH)"),
        g("ap_pitch_level", "2.0", None, "Autopilot pitch mode from t_level (2 ALH)"),
        g("ap_roll_start", "1.0", None, "Autopilot roll mode before t_turn (0 off, 1 RAH)"),
        g("ap_roll_turn", "2.0", None, "Autopilot roll mode from t_turn (2 HH)"),
        g("flaps_set", "0.0", "deg", "Test input: flaps (ramped in 3 s from flaps_t)"),
        g("flaps_t", "10.0", "s", "Test input: flaps at"),
    ]
    for pre, desc in (("pitch", "column pitch"), ("roll", "column roll"), ("pedal", "pedals")):
        out += [g(f"{pre}_amp", "0.0", None, f"Test input: {desc} (-1 .. 1), held from {pre}_t for {pre}_dur"),
                g(f"{pre}_t", "10.0", "s", f"Test input: {desc} on at"),
                g(f"{pre}_dur", "2.0", "s", f"Test input: {desc} held for")]
    out += [g("wind_n0", "0.0", "m/s", "Wind towards north"), g("wind_e0", "0.0", "m/s", "Wind towards east"),
            g("wind_d0", "0.0", "m/s", "Wind downwards")]
    return out


def pulse(d: Diagram, axis: str, pre: str, x: float, y: float) -> str:
    """amp (ramp(t; t0) - ramp(t; t0 + dur)), 0.05 s edges: a held column or pedal."""
    fast = num(FAST)
    d.node(f"{axis}On", "stdlib:sources/Ramp", x, y, params={"t_start": f"{pre}_t", "slope": f"{pre}_amp / {fast}", "duration": fast})
    d.node(f"{axis}Off", "stdlib:sources/Ramp", x, y + 60,
           params={"t_start": f"{pre}_t + {pre}_dur", "slope": f"{pre}_amp / {fast}", "duration": fast})
    d.node(f"{axis}Mx", "stdlib:continuous/Mux2", x + 140, y + 30)
    d.node(f"{axis}Stim", "stdlib:continuous/Sum", x + 260, y + 30, params={"signs": "[1.0, -1.0]"})
    d.sig(f"{axis}On", "y", f"{axis}Mx", "u1")
    d.sig(f"{axis}Off", "y", f"{axis}Mx", "u2")
    d.sig(f"{axis}Mx", "y", f"{axis}Stim", "u")
    return f"{axis}Stim"


def up_down(d: Diagram, name: str, initial: str, delta: str, t_up: str, t_down: str | None, edge: str, x, y) -> str:
    """initial + delta (ramp(t; t_up, edge) - ramp(t; t_down, edge)) from two stdlib Ramps."""
    d.node(f"{name}Up", "stdlib:sources/Ramp", x, y,
           params={"t_start": t_up, "initial": initial, "slope": f"({delta}) / {edge}", "duration": edge})
    if t_down is None:
        return f"{name}Up"
    d.node(f"{name}Down", "stdlib:sources/Ramp", x, y + 60,
           params={"t_start": t_down, "slope": f"-({delta}) / {edge}", "duration": edge})
    d.node(f"{name}Mx", "stdlib:continuous/Mux2", x + 140, y + 30)
    d.node(f"{name}Stim", "stdlib:continuous/Sum", x + 260, y + 30, params={"signs": "[1.0, 1.0]"})
    d.sig(f"{name}Up", "y", f"{name}Mx", "u1")
    d.sig(f"{name}Down", "y", f"{name}Mx", "u2")
    d.sig(f"{name}Mx", "y", f"{name}Stim", "u")
    return f"{name}Stim"


def servo(d: Diagram, name: str, axis: str, x, y) -> str:
    k2, k1, k0 = SERVO["poly"][axis]
    d.node(name, "project:BeaverServo", x, y, params={"k2": num(k2), "k1": num(k1), "k0": num(k0), "tau": num(SERVO["tau"])})
    d.sig("Beaver", "V", name, "V")
    return name


def model_sim():
    d = Diagram()
    edge = num(DEMO["edge"])
    # ---- the demo and test stimulus (globals) into the export inputs
    src = {
        "col_pitch": pulse(d, "Pitch", "pitch", 40, 40),
        "col_roll": pulse(d, "Roll", "roll", 40, 180),
        "pedals": pulse(d, "Pedal", "pedal", 40, 320),
    }
    d.node("FlapStim", "stdlib:sources/Ramp", 40, 460,
           params={"t_start": "flaps_t", "slope": "flaps_set / 3.0", "duration": "3.0"})
    src["flaps_deg"] = "FlapStim"
    d.node("TrimStim", "stdlib:sources/Constant", 40, 520, params={"value": "elev_trim"})
    src["elev_trim_deg"] = "TrimStim"
    src["pz_inhg"] = up_down(d, "Pz", num(PT["pz0"]), f"climb_pz - {num(PT['pz0'])}", "t_climb", "t_power", edge, 40, 580)
    src["rpm"] = up_down(d, "Rpm", num(PT["n0"]), f"climb_rpm - {num(PT['n0'])}", "t_climb", "t_power", edge, 40, 720)
    d.node("ApPitchStim", "stdlib:sources/Step", 40, 860, params={"t_step": "t_level", "initial": "ap_pitch_start", "final": "ap_pitch_level"})
    d.node("ApRollStim", "stdlib:sources/Step", 40, 920, params={"t_step": "t_turn", "initial": "ap_roll_start", "final": "ap_roll_turn"})
    src["ap_pitch"], src["ap_roll"] = "ApPitchStim", "ApRollStim"
    src["theta_ref_deg"] = up_down(d, "ThetaRef", num(PT["theta0"]), "climb_dtheta", "t_climb", None, edge, 40, 980)
    for i, (nm, val) in enumerate((("phi_ref_deg", "0.0"), ("psi_ref_deg", "turn_psi"), ("h_ref_m", f"{num(PT['H0'])} + level_dh"),
                                   ("wind_n", "wind_n0"), ("wind_e", "wind_e0"), ("wind_d", "wind_d0"))):
        node = f"{nm}Stim"
        d.node(node, "stdlib:sources/Constant", 40, 1120 + 60 * i, params={"value": val})
        src[nm] = node
    for k, (marker, start, _) in enumerate(SIM_INPUTS):
        d.node(marker, "stdlib:converters/ExportInputPass", 420, 40 + 90 * k, params={"value": start})
        d.sig(src[marker], "y", marker, "u")
    d.note("**Inputs.** The ExportInputPass markers pass the demo and test stimulus (the globals) through in bg-sim; "
           "in the FMU the host drives them.", 40, -80, 700, 40, "blue")
    # ---- the airframe
    airframe(PT["start_pose"], PT["start_P"], wind=True).subsystem(d, "Beaver", 1500, 300)
    for nm, port in (("wind_n", "wn"), ("wind_e", "we"), ("wind_d", "wd")):
        d.sig(nm, "y", "Beaver", port)
    # ---- cockpit and servos
    d.node("Controls", "project:BeaverControls", 1200, 300,
           params={"ail_trim": "ail_trim", "rud_trim": "rud_trim", **{k: num(v) for k, v in PILOT.items()}})
    for marker, port in (("col_pitch", "col_pitch"), ("col_roll", "col_roll"), ("pedals", "pedals"), ("flaps_deg", "flaps"),
                         ("elev_trim_deg", "elev_trim"), ("pz_inhg", "pz_in"), ("rpm", "rpm_in")):
        d.sig(marker, "y", "Controls", port)
    for port, inp in (("de", "de"), ("da", "da"), ("dr", "dr"), ("df", "df"), ("pz", "pz"), ("n", "n")):
        d.sig("Controls", port, "Beaver", inp)
    # ---- the FDC autopilot
    for nm, gy in (("theta_ref_deg", 640), ("phi_ref_deg", 820), ("psi_ref_deg", 880)):
        d.node(f"{nm}Rad", "stdlib:continuous/Gain", 700, gy, params={"k": num(RAD)})
        d.sig(nm, "y", f"{nm}Rad", "u")
    d.node("PitchAP", "project:BeaverPitchAP", 900, 600,
           params={"theta0": num(PT["x0"][7]), "t_aw": num(SERVO["t_aw"]), "t_off": num(SERVO["t_off"])})
    d.sig("ap_pitch", "y", "PitchAP", "mode")
    for p in ("theta", "q", "r", "phi", "V", "H"):
        d.sig("Beaver", p, "PitchAP", p)
    d.sig("theta_ref_degRad", "y", "PitchAP", "theta_ref")
    d.sig("h_ref_m", "y", "PitchAP", "H_ref")
    d.node("RollAP", "project:BeaverRollAP", 900, 800, params={"t_aw": num(SERVO["t_aw"]), "t_off": num(SERVO["t_off"])})
    d.sig("ap_roll", "y", "RollAP", "mode")
    for p in ("phi", "r", "psi", "V"):
        d.sig("Beaver", p, "RollAP", p)
    d.sig("phi_ref_degRad", "y", "RollAP", "phi_ref")
    d.sig("psi_ref_degRad", "y", "RollAP", "psi_ref")
    servo(d, "ElevServo", "e", 1100, 600)
    servo(d, "AilServo", "a", 1100, 760)
    servo(d, "RudServo", "r", 1100, 860)
    d.sig("PitchAP", "de", "ElevServo", "u")
    d.sig("RollAP", "da", "AilServo", "u")
    d.sig("RollAP", "dr", "RudServo", "u")
    d.sig("ElevServo", "y", "Controls", "servo_e")
    d.sig("AilServo", "y", "Controls", "servo_a")
    d.sig("RudServo", "y", "Controls", "servo_r")
    d.note("**Autopilot (FDC 'Beaver', REP ch. 11).** Pitch: attitude hold (PAH) and altitude hold (ALH); roll: "
           "attitude hold (RAH), heading hold (HH) and the turn coordinator; gains scheduled on V. Servos (our fit of "
           "FDC's actuator models): 0.09 s lag with the speed-dependent cable gain.", 700, 1000, 800, 50, "blue")
    # ---- what the host reads
    d.node("PoseOut", "stdlib:continuous/Demux4", 1900, 300)
    d.node("PoseQ", "project:PoseQuat", 1800, 300)
    d.sig("Beaver", "pose", "PoseQ", "g")
    d.sig("PoseQ", "q", "PoseOut", "u")
    for k, (marker, node, port) in enumerate(SIM_OUTPUT_SOURCES):
        d.node(marker, "stdlib:converters/ExportOutput", 2150 + 200 * (k // 15), 40 + 60 * (k % 15))
        d.sig(node, port, marker, "u")
    # ---- 3D view
    crafts = [{"lab": "Beaver", "tag": "sim", "scheme": "yellow", "dy": 0.0,
               "signals": {"de": "Controls/de", "da": "Controls/da", "dr": "Controls/dr", "df": "Controls/df",
                           "prop": "Beaver/PropAngle/y"}}]
    bindings = view(d, crafts, PT["H0"], 1900, 1100, SIM_DOTS, reach=200.0)
    write_scene("beaver-sim", crafts, SIM_DOTS, "  beaver-sim: the flyable Beaver (yellow, framed).")
    plots = [
        {"id": "p1", "title": "Altitude (m) and reference", "signals": ["Beaver/Air/H", "h_ref_m/y"]},
        {"id": "p2", "title": "Heading and bank (deg)", "signals": ["Beaver/Air/psi_deg", "Beaver/Air/phi_deg", "psi_ref_deg/y"]},
        {"id": "p3", "title": "Pitch angle and reference (deg)", "signals": ["Beaver/Air/theta_deg", "theta_ref_deg/y"]},
        {"id": "p4", "title": "Airspeed (m/s)", "signals": ["Beaver/Air/V", "Beaver/Air/vc"]},
        {"id": "p5", "title": "Surfaces (deg)", "signals": ["Controls/de", "Controls/da", "Controls/dr"]},
        {"id": "p6", "title": "Engine: rpm and command", "signals": ["Beaver/Engine/n_shaft", "Controls/n"]},
        {"id": "p7", "title": "Power (kW) and manifold pressure (inch Hg)", "signals": ["Beaver/Prop/P", "Controls/pz"]},
        {"id": "p8", "title": "Sideslip (deg)", "signals": ["Beaver/Air/beta_deg"]},
    ]
    t_end = DEMO["t_end"]
    return model_doc(
        "beaver-sim",
        "The flyable DHC-2 Beaver: the FDC airframe with the engine/propeller drivetrain (switchable), the cockpit "
        "controls and the FDC autopilot (pitch/altitude hold, roll/heading hold, turn coordinator), with the FMU "
        "interface as export markers. The default run is the demo: a climb, a turn to 090 and a level-off. "
        "Generated by design/build_model.py; see the README.",
        d, settings(t_end, int(t_end * 20) + 1, reltol=1e-8, abstol=1e-8), plots, "scenes/beaver-sim.sdf", bindings,
        sim_globals())


POSEQUAT = """@block PoseQuat begin
    # The attitude quaternion (qw, qx, qy, qz) of a pose (qw, qx, qy, qz, x, y, z), normalised: the
    # FMU host of beaver-sim reads it (body FLU to the world x north, y west, z up).
    @inputs g::Vec{7}
    @outputs q::Vec{4}
    @variables s::Real = 1.0
    @equations begin
        s ~ sqrt(g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4])
        q[1] ~ g[1] / s
        q[2] ~ g[2] / s
        q[3] ~ g[3] / s
        q[4] ~ g[4] / s
    end
end
"""


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


def gauge(cid, title, sig, lo, hi, unit, zones, decimals=1):
    return {"id": cid, "kind": "gauge", "size": "1x1", "title": title, "signals": [sig],
            "options": {"min": lo, "max": hi, "decimals": decimals, "unit": unit, "zones": zones}}


DASHBOARDS = {
    "beaver-modes": {"autoRerun": True, "cards": [
        text("d1", "Modes", "Five Beavers at 45 m/s, 6000 ft, each released on one mode of the coupled linear model. "
             "Switch the **drivetrain** on to see how little the shaft dynamics change the modes."),
        slider("d2", "Drivetrain (1 on, 0 source)", "drivetrain", 0.0, 1.0, 1.0, 0),
        plot("d3", "Phugoid: airspeed (m/s)", ["Phugoid/Air/V"]),
        plot("d4", "Short period: alpha (deg)", ["ShortPeriod/Air/alpha_deg"]),
        plot("d5", "Dutch roll: sideslip (deg)", ["DutchRoll/Air/beta_deg"]),
        plot("d6", "Roll and spiral: bank (deg)", ["Roll/Air/phi_deg", "Spiral/Air/phi_deg"]),
    ]},
    "beaver-steps": {"autoRerun": True, "cards": [
        text("d1", "Control steps", "The thesis' inputs on each axis and the engine, from the 45 m/s, 6000 ft trim. "
             "Change the sizes; switch the drivetrain on to let the shaft lag the rpm command."),
        slider("d2", "Elevator block (deg)", "step_de", -5.0, 5.0, 0.5, 1, "deg"),
        slider("d3", "Aileron block (deg)", "step_da", -5.0, 5.0, 0.5, 1, "deg"),
        slider("d4", "Rudder block (deg)", "step_dr", -5.0, 5.0, 0.5, 1, "deg"),
        slider("d5", "Flaps (deg)", "step_df", 0.0, 10.0, 0.5, 1, "deg"),
        slider("d6", "Rpm change", "step_n", -300.0, 400.0, 10.0, 0),
        slider("d7", "Manifold pressure change (inch Hg)", "step_pz", -5.0, 5.0, 0.25, 2),
        slider("d8", "Drivetrain (1 on, 0 source)", "drivetrain", 0.0, 1.0, 1.0, 0),
        plot("d9", "Airspeed (m/s)", ["Elevator/Air/V", "Flap/Air/V", "Rpm/Air/V", "Manifold/Air/V"], "4x2"),
        plot("d10", "Bank (deg)", ["Aileron/Air/phi_deg", "Rudder/Air/phi_deg", "Flap/Air/phi_deg", "Manifold/Air/phi_deg"]),
        plot("d11", "Sideslip (deg)", ["Aileron/Air/beta_deg", "Rudder/Air/beta_deg"]),
    ]},
    "beaver-sim": {"autoRerun": True, "cards": [
        text("d1", "The flyable Beaver", "45 m/s at 6000 ft on the FDC autopilot. The demo: **climb** power and +4 deg "
             "at 5 s, **turn** to the heading at 30 s (heading hold), **level off** at the altitude (altitude hold) at "
             "70 s, cruise power at 85 s. Move the sliders, or switch the autopilot off (mode 0) and fly the test "
             "inputs.", "2x2"),
        slider("d2", "Climb manifold pressure (inch Hg)", "climb_pz", 18.0, 28.0, 0.5, 1),
        slider("d3", "Climb rpm", "climb_rpm", 1800.0, 2300.0, 50.0, 0),
        slider("d4", "Climb pitch-up (deg)", "climb_dtheta", 0.0, 8.0, 0.5, 1, "deg"),
        slider("d5", "Heading to turn to (deg)", "turn_psi", -180.0, 180.0, 5.0, 0, "deg"),
        slider("d6", "Level off above the start (m)", "level_dh", 0.0, 300.0, 10.0, 0, "m"),
        slider("d7", "Drivetrain (1 on, 0 source)", "drivetrain", 0.0, 1.0, 1.0, 0),
        slider("d8", "Pitch AP before the level-off (0 off, 1 PAH)", "ap_pitch_start", 0.0, 1.0, 1.0, 0),
        slider("d9", "Roll AP before the turn (0 off, 1 RAH)", "ap_roll_start", 0.0, 1.0, 1.0, 0),
        slider("d10", "Column pitch pulse (from 10 s, 2 s)", "pitch_amp", -0.3, 0.3, 0.01, 2),
        slider("d11", "Column roll pulse (from 10 s, 2 s)", "roll_amp", -0.3, 0.3, 0.01, 2),
        slider("d12", "Flaps (deg, from 10 s)", "flaps_set", 0.0, 20.0, 1.0, 0, "deg"),
        gauge("d13", "Airspeed", "Beaver/Air/V", 25.0, 65.0, "m/s",
              [{"from": 25.0, "to": 35.0, "tone": "bad"}, {"from": 35.0, "to": 55.0, "tone": "good"},
               {"from": 55.0, "to": 65.0, "tone": "bad"}]),
        gauge("d14", "Engine", "Beaver/Engine/n_shaft", 1500.0, 2400.0, "rpm",
              [{"from": 1500.0, "to": 2300.0, "tone": "good"}, {"from": 2300.0, "to": 2400.0, "tone": "bad"}], 0),
        plot("d15", "Altitude and reference (m)", ["Beaver/Air/H", "h_ref_m/y"], "4x2"),
        plot("d16", "Heading, bank (deg)", ["Beaver/Air/psi_deg", "Beaver/Air/phi_deg"]),
        plot("d17", "Pitch and reference (deg)", ["Beaver/Air/theta_deg", "theta_ref_deg/y"]),
        plot("d18", "Airspeed (m/s)", ["Beaver/Air/V"]),
        plot("d19", "Surfaces (deg)", ["Controls/de", "Controls/da", "Controls/dr"]),
    ]},
}


# --------------------------------------------------------------------------- expected.json
NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
           "note": "no algebraic loop, no causality conflict, no event storm"}


def _at(rec, key, t):
    ts = rec["t"]
    k = min(range(len(ts)), key=lambda i: abs(ts[i] - t))
    assert abs(ts[k] - t) < 1e-9, (t, ts[k])
    return rec[key][k]


def _cursor(signal, rec, key, t, tol, note=None, offset=0.0):
    c = {"kind": "cursor_value", "signal": signal, "t": t, "value": _at(rec, key, t) + offset, "abs": tol}
    if note:
        c["note"] = note
    return c


KEYS = [("V", "Air/V", 1e-4), ("alpha_deg", "Air/alpha_deg", 1e-4), ("beta_deg", "Air/beta_deg", 1e-4),
        ("p_deg", "Air/p_deg", 1e-4), ("q_deg", "Air/q_deg", 1e-4), ("r_deg", "Air/r_deg", 1e-4),
        ("phi_deg", "Air/phi_deg", 1e-4), ("theta_deg", "Air/theta_deg", 1e-4), ("H", "Air/H", 1e-3)]


def expected() -> dict:
    val = DESIGN["validation"]["6000ft"]
    modes = DESIGN["modes"]
    ref = "the scipy reference of the FDC model (design/beaver_ref.py, design/design.py)"
    # ---- modes
    rel = {r["label"]: r for r in DESIGN["releases"]}
    checks_m = [{"kind": "scene_bindings"}, NO_DIAG]
    for lab, r in rel.items():
        for t in (1.0, 5.0, 20.0, 60.0, 150.0):
            for key, sig, tol in KEYS:
                if key in ("V", "alpha_deg", "beta_deg", "phi_deg", "theta_deg"):
                    checks_m.append(_cursor(f"{lab}/{sig}", r["run"], key, t, tol, ref if (t == 1.0 and key == "V") else None))
    def damp(lab, sig, f, t, mode, zabs, wrtol):
        p = modes["props"][mode]
        return {"kind": "damping", "signal": f"{lab}/{sig}", "from_t": f, "to_t": t, "zeta": p["zeta"], "zeta_abs": zabs,
                "wn": p["wn"], "wn_rtol": wrtol,
                "note": f"{mode.replace('_', ' ')} of the coupled linear model: zeta {p['zeta']:.4f}, wn {p['wn']:.4f} rad/s "
                        f"(THESIS Table 5-3, decoupled: {DESIGN['validation']['6000ft']['thesis_modes'][mode]})"}
    checks_m += [damp("Phugoid", "Air/V", 0.0, 150.0, "phugoid", 0.003, 0.003),
                 damp("ShortPeriod", "Air/alpha_deg", 0.0, 3.0, "short_period", 0.005, 0.005),
                 damp("DutchRoll", "Air/beta_deg", 0.0, 12.0, "dutch_roll", 0.005, 0.005)]
    lr, ls = modes["coupled"]["roll"][0], modes["coupled"]["spiral"][0]
    checks_m += [
        {"kind": "cursor_value", "signal": "GrowRoll/lambda", "t": 0.3, "value": lr, "rtol": 2e-3,
         "note": f"roll mode: phidot/phi reads the eigenvalue {lr:.4f} 1/s (THESIS Table 5-3: -5.1351, decoupled)"},
        {"kind": "cursor_value", "signal": "GrowSpiral/lambda", "t": 1.0, "value": ls, "rtol": 2e-3,
         "note": f"spiral mode: phidot/phi reads the eigenvalue {ls:.5f} 1/s (THESIS: -0.04573, decoupled)"},
        _cursor("GrowSpiral/lambda", rel["Spiral"]["run"], "lambda_phi", 20.0, 1e-4,
                "later the slow spiral drifts from the linear rate (the release also excites the lightly damped "
                "phugoid through the nonlinear coupling); bg-sim follows the scipy reference"),
        _cursor("GrowSpiral/lambda", rel["Spiral"]["run"], "lambda_phi", 60.0, 1e-4),
    ]
    # ---- steps
    steps = {s["label"]: s for s in DESIGN["steps"]}
    tp = DESIGN["point"]
    checks_s = [{"kind": "scene_bindings"}, NO_DIAG,
                {"kind": "cursor_value", "signal": "Manifold/Air/V", "t": 0.9, "value": 45.0, "abs": 1e-6,
                 "note": "trimmed: the FDC trim (THESIS Table 5-1, data/cr4560.lin) holds the speed in bg-sim"},
                {"kind": "cursor_value", "signal": "Manifold/Air/alpha_deg", "t": 0.9, "value": tp["alpha0"], "abs": 1e-6},
                {"kind": "cursor_value", "signal": "Manifold/Air/beta_deg", "t": 0.9, "value": tp["beta0"], "abs": 1e-6},
                {"kind": "cursor_value", "signal": "Manifold/Air/H", "t": 0.9, "value": tp["H0"], "abs": 1e-5}]
    for lab, s in steps.items():
        for t in (2.0, 5.0, 10.0, 20.0, 40.0, 60.0):
            for key, sig, tol in KEYS:
                checks_s.append(_cursor(f"{lab}/{sig}", s["run"], key, t, tol,
                                        ref + ", exact source mode" if (t == 2.0 and key == "V") else None))
    # the drivetrain variant of the steps: the Rpm airframe with the shaft lag
    rd = DESIGN["rpm_step_drivetrain"]
    checks_sd = [NO_DIAG]
    for t in (2.0, 3.0, 5.0, 10.0, 30.0, 60.0):
        checks_sd.append(_cursor("Rpm/Engine/n_shaft", rd, "rpm", t, 1e-3,
                                 "drivetrain on: the governed shaft follows the rpm ramp with the designed "
                                 f"wn {DRV['wn']} rad/s, zeta {DRV['zeta']}" if t == 2.0 else None))
        for key, sig, tol in KEYS[:1] + KEYS[6:]:
            checks_sd.append(_cursor(f"Rpm/{sig}", rd, key, t, tol))
    # ---- sim
    dem = DESIGN["demo"]["drivetrain_on"]
    dsrc = DESIGN["demo"]["drivetrain_off"]
    H0 = tp["H0"]
    href = H0 + DEMO["level_dh"]
    sim_ref = "the closed-loop scipy reference (design/beaver_sim.py)"

    def demo_checks(rec, note):
        out = []
        for t in (10.0, 30.0, 50.0, 70.0, 90.0, 120.0, 150.0):
            out += [_cursor("Beaver/Air/H", rec, "H", t, 0.01, note if t == 10.0 else None),
                    _cursor("Beaver/Air/V", rec, "V", t, 1e-3), _cursor("Beaver/Air/phi_deg", rec, "phi_deg", t, 2e-3),
                    _cursor("Beaver/Air/theta_deg", rec, "theta_deg", t, 2e-3),
                    _cursor("Beaver/Air/psi_deg", rec, "psi_deg", t, 2e-3), _cursor("Beaver/Engine/n_shaft", rec, "rpm", t, 0.01)]
        return out
    checks_sim = [{"kind": "scene_bindings"}, NO_DIAG] + demo_checks(dem, sim_ref + ", drivetrain on") + [
        {"kind": "cursor_value", "signal": "Beaver/Air/H", "t": 150.0, "value": href, "abs": 1.0,
         "note": f"level-off: the altitude hold holds {DEMO['level_dh']:.0f} m above the start"},
        {"kind": "cursor_value", "signal": "Beaver/Air/psi_deg", "t": 150.0, "value": DEMO["turn_psi"], "abs": 0.5,
         "note": "the heading hold has turned the aircraft to 090"},
        {"kind": "max_abs_le", "signal": "Beaver/Air/phi_deg", "value": 31.0,
         "note": "the bank stays within the roll attitude hold's 30 deg limit"},
        {"kind": "min_ge", "signal": "Beaver/Air/V", "value": 38.0,
         "note": f"the speed stays inside the model's 35-55 m/s range (reference minimum {min(dem['V']):.1f} m/s)"},
        {"kind": "max_abs_le", "signal": "Beaver/Air/H", "value": href + 10.0,
         "note": f"altitude capture overshoot below 10 m (reference {max(dem['H']) - href:.1f} m)"},
        {"kind": "max_abs_le", "signal": "Beaver/Air/alpha_deg", "value": 13.0,
         "note": "no stall: alpha stays in the identified range"},
    ]
    export = {"inputs": {"col_pitch": {"min": -0.05, "max": 0.05}, "col_roll": {"min": -0.05, "max": 0.05},
                         "pedals": {"min": -0.05, "max": 0.05}, "flaps_deg": {"min": 0.0, "max": 3.0},
                         "elev_trim_deg": {"min": PT["de0"] - 0.5, "max": PT["de0"] + 0.5},
                         "pz_inhg": {"min": PT["pz0"] - 1.0, "max": PT["pz0"] + 1.0},
                         "rpm": {"min": 1750.0, "max": 1900.0},
                         "theta_ref_deg": {"min": PT["theta0"] - 2.0, "max": PT["theta0"] + 2.0},
                         "phi_ref_deg": {"min": -10.0, "max": 10.0}, "psi_ref_deg": {"min": -30.0, "max": 30.0},
                         "h_ref_m": {"min": H0 - 30.0, "max": H0 + 30.0},
                         "wind_n": {"min": -2.0, "max": 2.0}, "wind_e": {"min": -2.0, "max": 2.0},
                         "wind_d": {"min": -1.0, "max": 1.0}},
              "interface": {"inputs": [m for m, _, _ in SIM_INPUTS], "outputs": [m for m, _, _ in SIM_OUTPUT_SOURCES]},
              "note": "the FMU of beaver-sim; its own acceptance (tunables, the demo and manoeuvres against bg-sim) is "
                      "examples/export_beaver_check.py"}
    checks_src = [NO_DIAG] + demo_checks(dsrc, sim_ref + ", exact source mode (drivetrain 0)")
    return {"project": "beaver",
            "description": "DHC-2 'Beaver' (FDC 1.4, Rauw; Tjee & Mulder flight-test data): the modes and control steps at "
                           "the thesis' trim point, and the flyable beaver-sim with the drivetrain and the FDC autopilot. "
                           "Numbers come from design/design.json (an independent scipy implementation of the FDC model, "
                           "validated against the thesis' Tables 5-1 and 5-3 and FDC's linear models).",
            "models": {"beaver-modes": {"checks": checks_m},
                       "beaver-steps": {"checks": checks_s},
                       "beaver-steps-drivetrain": {"model": "beaver-steps", "overrides": {"global:drivetrain": 1.0},
                                                   "checks": checks_sd},
                       "beaver-sim": {"checks": checks_sim, "export": export},
                       "beaver-sim-source": {"model": "beaver-sim", "overrides": {"global:drivetrain": 0.0},
                                             "checks": checks_src}}}


def main() -> int:
    (EXAMPLE / "library" / "BeaverTrail.jl").write_text(trail_block(), encoding="utf-8", newline="\n")
    (EXAMPLE / "library" / "BeaverAero.jl").write_text(aero_block(), encoding="utf-8", newline="\n")
    (EXAMPLE / "library" / "PoseQuat.jl").write_text(POSEQUAT, encoding="utf-8", newline="\n")
    models = {"beaver-modes": model_modes(), "beaver-steps": model_steps(), "beaver-sim": model_sim()}
    (EXAMPLE / "models").mkdir(exist_ok=True)
    for name, doc in models.items():
        doc["dashboard"] = DASHBOARDS[name]
        path = EXAMPLE / "models" / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "beaver", "models": list(models),
            "libraryDir": "library", "scenesDir": "scenes"}
    (EXAMPLE / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    (EXAMPLE / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
