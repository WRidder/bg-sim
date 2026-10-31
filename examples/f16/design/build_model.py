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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path.insert(0, str(HERE))
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
SI = DESIGN["si"]
TABLES = DESIGN["tables"]


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


def airframe(xcg: str, start: dict, energy: bool = False) -> Diagram:
    """One F-16: inputs el, ail, rdr (deg) and thtl (0..1); xcg is a parameter expression."""
    d = Diagram()
    pose, P, power = start["start_pose"], start["start_P"], start["start_power"]
    # ---- multibond rigid body on a free joint (principal axes) and the external wrench
    d.node("World", "stdlib:multibond/GroundSpatial", 40, 40)
    d.node("Free", "stdlib:spatial/Free3D", 220, 40, starts={k: num(v) for k, v in pose.items()})
    d.node("Body", "stdlib:spatial/RigidBody3D", 420, 40,
           params={"m": num(SI["mass"]), "J": vec(SI["J_principal"]), "g0": num(SI["g0"])},
           starts={"inertia/P": vec(P)})
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
    d.node("Engine", "project:F16Engine", 620, 640, starts={"P": num(power)})
    d.sig("thtlIn", "y", "Engine", "thtl")
    d.sig("TIdle", "y", "Engine", "tidl")
    d.sig("TMil", "y", "Engine", "tmil")
    d.sig("TMax", "y", "Engine", "tmax")
    # ---- force build-up
    d.node("Forces", "project:F16Forces", 1100, 300,
           params={"S": num(SI["S"]), "b": num(SI["b"]), "cbar": num(SI["cbar"]), "xcg": xcg,
                   "xcgr": num(SI["xcgr"]), "he": num(SI["he"]), "m": num(SI["mass"]), "g0": num(SI["g0"])})
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
    for name, node, port, unit in AIRFRAME_OUTPUTS:
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
TRAIL_N = 12          # dots per trail (every bound signal id goes into the 3D stream URL: keep it short)
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


FLOOR_PERIOD = 50.0   # m, stripe spacing of the reference floor
FLOOR_HALF = 300.0    # m, half size of the floor patch
VIEW_LIFT = 8.0       # m, the framed aircraft flies this far above the viewer's 10 m grid at the origin
BOUNDS = 360.0        # m, the invisible markers that centre the view's Fit on the framed aircraft
FLOOR_DEPTH = 150.0   # m below the start altitude of the reference aircraft
STAB_PIVOT = (-5.0, 0.0, 0.05)
TRAIL_RGBA = {"grey": "0.95 0.95 0.98 1", "sand": "1.0 0.85 0.45 1", "blue": "0.55 0.75 1.0 1"}


def scene_sdf(name: str, aircraft: list[tuple[str, str]], comment: str) -> str:
    """aircraft: (tag, paint scheme); the first one is the reference the view keeps framed."""
    L = ['<?xml version="1.0"?>', "<!--", comment, "-->", '<sdf version="1.9">', f'  <model name="{name}">',
         '    <link name="ground">', "      <pose>0 0 0 0 0 0</pose>",
         '      <visual name="floor">', f"        <pose>0 0 -0.5 0 0 0</pose>",
         f"        <geometry><box><size>{2 * FLOOR_HALF:g} {2 * FLOOR_HALF:g} 1</size></box></geometry>",
         "        <material><diffuse>0.36 0.45 0.33 1</diffuse></material>", "      </visual>"]
    n = int(FLOOR_HALF // FLOOR_PERIOD)
    for k in range(-n, n + 1):
        c = k * FLOOR_PERIOD
        L += [f'      <visual name="stripe_x{k + n}">', f"        <pose>{c:g} 0 0.05 0 0 0</pose>",
              f"        <geometry><box><size>3 {2 * FLOOR_HALF:g} 0.1</size></box></geometry>",
              "        <material><diffuse>0.62 0.66 0.55 1</diffuse></material>", "      </visual>",
              f'      <visual name="stripe_y{k + n}">', f"        <pose>0 {c:g} 0.05 0 0 0</pose>",
              f"        <geometry><box><size>{2 * FLOOR_HALF:g} 3 0.1</size></box></geometry>",
              "        <material><diffuse>0.62 0.66 0.55 1</diffuse></material>", "      </visual>"]
    L.append("    </link>")
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
    "  an attitude reference), and its 50 m stripes scroll with the ground track. The dots behind each aircraft are its flight path over the last second. The\n"
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
    bindings.append({"target": "link:ground", "property": "pose", "signal": [f"{ref}View/ground[{i}]" for i in range(1, 8)]})
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


def actuator(el0: float) -> Diagram:
    """Stevens & Lewis's elevator servo from stdlib blocks: input limit +-25 deg, a 20.2 rad/s
    first-order lag, rate limit +-60 deg/s. Outputs the deflection y (deg) and its rate (deg/s)."""
    a = FBW["act"]
    s = Diagram()
    s.node("Travel", "stdlib:continuous/Saturation", 40, 40, params={"lower": num(-a["pos"]), "upper": num(a["pos"])})
    s.node("Mx", "stdlib:continuous/Mux2", 200, 40)
    s.node("Err", "stdlib:continuous/Sum", 340, 40, params={"signs": "[1.0, -1.0]"})
    s.node("Bandwidth", "stdlib:continuous/Gain", 480, 40, params={"k": num(a["w"])})
    s.node("RateLimit", "stdlib:continuous/Saturation", 620, 40, params={"lower": num(-a["rate"]), "upper": num(a["rate"])})
    s.node("Servo", "stdlib:continuous/Integrator", 760, 40, starts={"x": num(el0)})
    s.sig("Travel", "y", "Mx", "u1")
    s.sig("Servo", "y", "Mx", "u2")
    s.sig("Mx", "y", "Err", "u")
    s.sig("Err", "y", "Bandwidth", "u")
    s.sig("Bandwidth", "y", "RateLimit", "u")
    s.sig("RateLimit", "y", "Servo", "u")
    s.port("u", "input", "Travel", "u")
    s.port("y", "output", "Servo", "y")
    s.port("rate", "output", "RateLimit", "y")
    s.note(f"Elevator servo: {a['w']} rad/s lag, +-{a['pos']:g} deg, +-{a['rate']:g} deg/s (Stevens & Lewis).",
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
}


# --------------------------------------------------------------------------- expected.json
def _at(case, key, t):
    ts = case["t"]
    k = min(range(len(ts)), key=lambda i: abs(ts[i] - t))
    assert abs(ts[k] - t) < 1e-9, (t, ts[k])
    return case[key][k]


def _cursor(signal, case, key, t, tol, note=None):
    c = {"kind": "cursor_value", "signal": signal, "t": t, "value": _at(case, key, t), "abs": tol}
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
                           "PIO. Numbers come from design/design.json (an independent scipy implementation of the book's "
                           "F16 subroutine and of the same controllers).",
            "models": {"f16-open-loop": {"checks": checks_ol}, "f16-fbw": {"checks": checks_fbw},
                       "f16-envelope": {"checks": checks_env}, "f16-pio": {"checks": checks_pio}}}


def main() -> int:
    models = {"f16-open-loop": model_open_loop(), "f16-fbw": model_fbw(), "f16-envelope": model_envelope(),
              "f16-pio": model_pio()}
    (EXAMPLE / "library" / "F16Trail.jl").write_text(trail_block(), encoding="utf-8", newline="\n")
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
