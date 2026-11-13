# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the `maglev-train` models, the scene and expected.json from `design/design.json`.

    uv run examples/maglev-train/design/design.py        # first: the design numbers
    uv run examples/maglev-train/design/build_model.py

Models (examples/maglev-train/models):

* ``maglev-module``   one EMS levitation module carrying a quarter of a car: lift-off from the skids,
                      gap regulation at 10 mm, a guideway step and a payload step
* ``maglev-vehicle``  a car section on two levitation modules, running on a guideway of flexible spans
                      with an LSM and a speed profile (3D multibond car body, heave and pitch); its two
                      modules ModF and ModR are instances of the library subsystem LevitationModule
                      (library/LevitationModule.bgsub.json, also written here)
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))


def num(v: float) -> str:
    return repr(float(v))


# --------------------------------------------------------------------------- document helpers


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[tuple] = []
        self.annotations: list[dict] = []
        self.ports: list[dict] = []
        self._ids: dict[str, str] = {}
        self._c = 0

    def node(self, name: str, block, x: float, y: float, params=None, starts=None, constants=None,
             rotation: float = 0) -> str:
        nid = f"n{len(self.nodes) + 1:02d}"
        if isinstance(block, str):
            b = {"junction": block} if block in ("0", "1") else {"ref": block}
        else:
            b = block
        self.nodes.append({
            "id": nid, "name": name, "block": b, "position": {"x": x, "y": y}, "rotation": rotation,
            "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self._ids[name] = nid
        return nid

    def _conn(self, kind, a, pa, b, pb):
        self._c += 1
        self.connections.append((f"c{self._c:02d}", kind, a, pa, b, pb))

    def _resolved(self) -> list[dict]:
        out = []
        for cid, kind, a, pa, b, pb in self.connections:
            frm = {"node": self._ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self._ids[b]}
            if pb is not None:
                to["port"] = pb
            out.append({"id": cid, "kind": kind, "from": frm, "to": to})
        return out

    def sig(self, a, pa, b, pb):
        self._conn("signal", a, pa, b, pb)

    def bond(self, a, pa, b, pb):
        self._conn("bond", a, pa, b, pb)

    def wire(self, a, pa, b, pb):
        self._conn("wire", a, pa, b, pb)

    def note(self, text: str, x, y, w, h, color: str | None = None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def signal_port(self, name, direction, node, port, unit=None):
        self.ports.append({"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [1],
                           "unit": unit, "node": self._ids[node], "port": port})

    def power_port(self, name, domain, node, port=None, size=1):
        p = {"name": name, "kind": "power", "domain": domain, "size": [size], "node": self._ids[node]}
        if port is not None:
            p["port"] = port
        self.ports.append(p)

    def doc(self) -> dict:
        return {"nodes": self.nodes, "connections": self._resolved(), "annotations": self.annotations}


def model_doc(name, comment, diagram, settings, plots, scene, bindings, parameters, dashboard=None) -> dict:
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": diagram.doc(), "settings": settings, "plots": plots,
        "scene": {"file": scene} if scene else None, "bindings": bindings, "parameters": parameters,
    }
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc


def settings(t_end: float, points: int, reltol: float = 1e-8, abstol: float = 1e-10, solver: str = "auto") -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 10000}


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value, "unit": unit, "description": description}


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# --------------------------------------------------------------------------- the levitation module


def module_globals(d: dict) -> list[dict]:
    """Globals of one levitation module (d = design.json entry of the module)."""
    a = d["a"]
    return [
        g("g0", "9.81", "m/s^2", "Gravitational acceleration"),
        g("h_nom", num(d["h0"]), "m", "Nominal gap (Transrapid: 10 mm)"),
        g("h_skid", num(d["h_skid"]), "m", "Gap while the module rests on its skids (estimate)"),
        g("h_stop", num(d["h_stop"]), "m", "Touch-down stop: the pole face would hit the rail below this gap (estimate)"),
        g("m_b", num(d["m_b"]), "kg", "Levitation chassis (bogie) mass"),
        g("k_s", num(d["k_s"]), "N/m", "Secondary suspension stiffness"),
        g("c_s", num(d["c_s"]), "N*s/m", "Secondary suspension damping"),
        g("alpha", num(d["alpha"]), "H*m", "Magnet force constant: F = alpha*i^2/h^2 (= mu0 N^2 A_pole/4)"),
        g("L_inf", num(d["L_inf"]), "H", "Coil leakage inductance; L(h) = L_inf + 2 alpha/h"),
        g("R_coil", num(d["R"]), "Ohm", "Coil resistance"),
        g("V_max", num(d["V_max"]), "V", "Chopper voltage limit"),
        g("k_c", num(d["k_c"]), "N/m", "Skid and stop contact stiffness"),
        g("d_c", num(d["d_c"]), "N*s/m", "Skid and stop contact damping"),
        g("h_rest", "h_skid + (m_b + m_c)*g0/k_c", "m", "Gap at rest: the skids carry the weight on the contact stiffness"),
        g("c_trim", "sqrt((m_b + m_c)*g0/alpha)", "A/m", "Trim law i = c_trim*h that carries the weight at any gap"),
        g("e_spring", "m_c*g0/k_s", "m", "Static stretch of the secondary spring under the body weight"),
        g("Tf", num(d["Tf"]), "s", "Derivative filter of the gap controller"),
        g("a1", num(d["a"][0]), "V/m", "Gap feedback gain (LQR design)"),
        g("a2", num(d["a"][1]), "V*s/m", "Gap-rate feedback gain (LQR design)"),
        g("a3", num(d["a"][2]), "V/A", "Current feedback gain (LQR design)"),
        g("a4", num(d["a"][3]), "V/(m*s)", "Gap-error integral gain (LQR design)"),
    ]


def add_module(dg: Diagram, ox: float, oy: float, with_body_port: bool = True, ports: bool = False,
               trim: bool = False) -> None:
    """One levitation module as a bond graph into `dg` (flat or inside a subsystem).

    Electrical side: chopper MSe `Amp` on the coil 1-junction `Jc` with the coil resistance, a
    current detector and the coil port of the stdlib `converters/Electromagnet` `EM` (an IC-field
    with L(h) = L_inf + 2 alpha/h). Mechanical side (velocities positive upward): bogie 1-junction
    `Jb` with the chassis mass, its weight, the armature port of EM, the secondary suspension `Sus`
    towards the body junction `Jq` and the skid contact `Skid` towards the guideway junction `Jr`.
    `Jr` carries the guideway velocity (flow source `Rail`) and the stator port of EM. The gap is
    read by a position sensor on the 0-junction `Jg` between `Jb` and `Jr`.
    """
    X, Y = ox, oy
    # controller and electrical side
    dg.node("Ctl", "project:GapController", X + 40, Y + 40,
            params={"a1": "a1", "a2": "a2", "a3": "a3", "a4": "a4", "Tf": "Tf", "R": "R_coil",
                    "c_trim": "c_trim", "v_max": "V_max"},
            starts={"xf": "h_nom" if trim else "h_rest"})
    dg.node("Amp", "stdlib:bondgraph/MSe", X + 260, Y + 40, params={"gain": "1.0"})
    dg.node("Jc", "1", X + 260, Y + 180)
    dg.node("Rc", "stdlib:bondgraph/R", X + 100, Y + 180, params={"r": "R_coil"})
    dg.node("Imeas", "stdlib:bondgraph/Df", X + 100, Y + 280)
    dg.node("Jv", "0", X + 260, Y + 260)
    dg.node("Vcoil", "stdlib:bondgraph/De", X + 100, Y + 380)
    dg.node("EM", "stdlib:converters/Electromagnet", X + 260, Y + 400,
            params={"alpha": "alpha", "L_inf": "L_inf", "h0": "0.0"},
            starts={"i": "c_trim*h_nom", "h": "h_nom + dh0"} if trim else {"i": "0.0", "h": "h_rest"})
    dg.node("Gnd", "stdlib:electrical/Ground", X + 440, Y + 280)
    # mechanical side
    dg.node("Rail", "stdlib:bondgraph/MSf", X + 40, Y + 600, params={"gain": "1.0"})
    dg.node("Jr", "1", X + 260, Y + 600)
    dg.node("Skid", "stdlib:translation/HardStop", X + 260, Y + 760,
            params={"lower": "h_stop", "upper": "h_skid", "k": "k_c", "d": "d_c"},
            starts={"x": "h_nom + dh0" if trim else "h_rest"})
    dg.node("Jb", "1", X + 480, Y + 480)
    dg.node("Chassis", "stdlib:bondgraph/I", X + 640, Y + 400, params={"i": "m_b"})
    dg.node("Weight", "stdlib:bondgraph/Se", X + 640, Y + 480, params={"e": "-m_b*g0"})
    dg.node("Jg", "0", X + 380, Y + 540)
    dg.node("GapRate", "stdlib:bondgraph/Df", X + 380, Y + 680)
    dg.node("Gap", "stdlib:continuous/Integrator", X + 540, Y + 680, starts={"x": "h_nom + dh0" if trim else "h_rest"})
    dg.node("Sus", "stdlib:translation/SpringDamper", X + 700, Y + 600, params={"k": "k_s", "d": "c_s"},
            starts={"x": "e_spring"})
    if with_body_port:
        dg.node("Jq", "1", X + 900, Y + 600)
    # electrical bonds
    dg.bond("Amp", "p", "Jc", None)
    dg.bond("Jc", None, "Rc", "p")
    dg.bond("Jc", None, "Imeas", "p")
    dg.bond("Jc", None, "Jv", None)
    dg.bond("Jv", None, "Vcoil", "p")
    dg.bond("Jv", None, "EM", "p")
    dg.wire("EM", "n", "Gnd", "p")
    # mechanical bonds
    dg.bond("Rail", "p", "Jr", None)
    dg.bond("Jb", None, "EM", "a")
    dg.bond("Jr", None, "EM", "b")
    dg.bond("Jr", None, "Skid", "a")
    dg.bond("Jb", None, "Skid", "b")
    dg.bond("Jb", None, "Chassis", "p")
    dg.bond("Weight", "p", "Jb", None)
    dg.bond("Jb", None, "Sus", "a")
    if with_body_port:
        dg.bond("Jq", None, "Sus", "b")
    dg.bond("Jr", None, "Jg", None)
    dg.bond("Jg", None, "Jb", None)
    dg.bond("Jg", None, "GapRate", "p")
    dg.sig("GapRate", "y", "Gap", "u")
    dg.node("Err", "project:Bias", X + 700, Y + 680, params={"b": "-h_nom"})
    dg.sig("Gap", "y", "Err", "u")
    # control
    dg.sig("Gap", "y", "Ctl", "h")
    dg.sig("Imeas", "y", "Ctl", "i")
    dg.sig("Ctl", "v", "Amp", "u")
    if ports:
        dg.power_port("body", "Translation", "Sus", "b")
        dg.signal_port("h_ref", "input", "Ctl", "h_ref", "m")
        dg.signal_port("v_rail", "input", "Rail", "u", "m/s")
        dg.signal_port("gap", "output", "Gap", "y", "m")
        dg.signal_port("i", "output", "Imeas", "y", "A")
        dg.signal_port("v", "output", "Ctl", "v", "V")


# --------------------------------------------------------------------------- scenes

E_VEH = 100.0     # exaggeration of gap, heave and pitch in the train scene
E_MOD = 20.0      # exaggeration of the gap and the suspension travel in the module scene


def _vis(name, pose, geom, rgba) -> str:
    return (f'      <visual name="{name}">\n        <pose>{pose}</pose>\n'
            f'        <geometry>{geom}</geometry>\n'
            f'        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def _box(sx, sy, sz) -> str:
    return f"<box><size>{sx:.4f} {sy:.4f} {sz:.4f}</size></box>"


def _cyl(r, length) -> str:
    return f"<cylinder><radius>{r:.4f}</radius><length>{length:.4f}</length></cylinder>"


def _link(name, pose, visuals) -> str:
    return f'    <link name="{name}">\n      <pose>{pose}</pose>\n{visuals}    </link>\n'


def _joint(name, kind, parent, child, axis) -> str:
    return (f'    <joint name="{name}" type="{kind}">\n      <parent>{parent}</parent>\n      <child>{child}</child>\n'
            f'      <axis><xyz>{axis}</xyz></axis>\n    </joint>\n')


# Train scene (Z up, X forward, metres). Guideway: pillars every span with a T-shaped beam (top slab and two
# side flanges whose underside is the rail), car with skirts and levitation arms below the flanges.
Z_RAIL = 3.9          # underside of the flange (the rail)
Z_FLOOR = 5.05        # car floor
Z_COM = 6.0           # height of the car's centre of mass (pose of the heave and pitch links)
GAP_PAD_H = 0.12


def scene_train(d: dict, v: dict) -> str:
    L = v["L_span"]
    Lc, Wc = v["L_car"], 3.7
    xm = v["x_m"]
    beam_len = 5.5 * L
    world = _vis("ground", "0 0 -0.05 0 0 0", _box(beam_len, 40.0, 0.1), "0.28 0.40 0.24 1")
    track = ""
    for k in range(-3, 4):
        track += _vis(f"pillar_{k + 3}", f"{k * L:.4f} 0 {(Z_RAIL - 0.05) / 2:.4f} 0 0 0",
                      _box(1.0, 1.6, Z_RAIL - 0.05), "0.72 0.72 0.70 1")
        track += _vis(f"cap_{k + 3}", f"{k * L:.4f} 0 {Z_RAIL - 0.12:.4f} 0 0 0", _box(1.4, 2.4, 0.24), "0.60 0.60 0.58 1")
    track += _vis("beam", f"0 0 {Z_RAIL + 0.55:.4f} 0 0 0", _box(beam_len, 2.2, 1.1), "0.78 0.78 0.76 1")
    for sgn, nm in ((1, "l"), (-1, "r")):
        track += _vis(f"flange_{nm}", f"0 {sgn * 1.45:.4f} {Z_RAIL + 0.05:.4f} 0 0 0", _box(beam_len, 0.8, 0.1),
                      "0.45 0.46 0.50 1")
        track += _vis(f"stator_{nm}", f"0 {sgn * 1.45:.4f} {Z_RAIL - 0.04:.4f} 0 0 0", _box(beam_len, 0.7, 0.08),
                      "0.25 0.30 0.55 1")
    # car body: cabin, nose wedges, glass, windows, stripe, skirts and arms (positions relative to the CoM)
    body = ""
    zc = Z_FLOOR + 1.275 - Z_COM
    body += _vis("cabin", f"0 0 {zc:.4f} 0 0 0", _box(Lc - 6.0, Wc, 2.55), "0.92 0.93 0.95 1")
    for sgn, nm in ((1, "f"), (-1, "r")):
        body += _vis(f"nose_{nm}", f"{sgn * (Lc / 2 - 3.0):.4f} 0 {zc - 0.35:.4f} 0 0 0", _box(6.0, Wc - 0.2, 1.85),
                     "0.92 0.93 0.95 1")
        body += _vis(f"nose_top_{nm}", f"{sgn * (Lc / 2 - 3.6):.4f} 0 {zc + 0.95:.4f} 0 {-sgn * 0.25:.4f} 0",
                     _box(5.2, Wc - 0.4, 0.25), "0.88 0.90 0.93 1")
        body += _vis(f"glass_{nm}", f"{sgn * (Lc / 2 - 1.6):.4f} 0 {zc + 0.55:.4f} 0 {-sgn * 0.5:.4f} 0",
                     _box(0.15, Wc - 0.9, 0.9), "0.10 0.14 0.22 1")
    for sgn, nm in ((1, "l"), (-1, "r")):
        body += _vis(f"windows_{nm}", f"0 {sgn * (Wc / 2 + 0.005):.4f} {zc + 0.35:.4f} 0 0 0",
                     _box(Lc - 8.0, 0.02, 0.7), "0.12 0.17 0.28 1")
        body += _vis(f"stripe_{nm}", f"0 {sgn * (Wc / 2 + 0.005):.4f} {zc - 0.5:.4f} 0 0 0",
                     _box(Lc - 2.0, 0.02, 0.25), "0.10 0.35 0.65 1")
        body += _vis(f"skirt_{nm}", f"0 {sgn * 2.15:.4f} {(Z_RAIL - 0.5 + Z_FLOOR) / 2 - Z_COM:.4f} 0 0 0",
                     _box(Lc - 4.0, 0.5, Z_FLOOR - (Z_RAIL - 0.5)), "0.60 0.64 0.70 1")
        body += _vis(f"arm_{nm}", f"0 {sgn * 1.5:.4f} {Z_RAIL - 0.5 + 0.15 - Z_COM:.4f} 0 0 0",
                     _box(Lc - 4.0, 0.9, 0.3), "0.50 0.54 0.60 1")
    links = _link("world", "0 0 0 0 0 0", world)
    links += _link("track", "0 0 0 0 0 0", track)
    links += _link("lift", f"0 0 {Z_COM} 0 0 0", "")
    links += _link("car", f"0 0 {Z_COM} 0 0 0", body)
    joints = _joint("scroll", "prismatic", "world", "track", "1 0 0")
    joints += _joint("heave", "prismatic", "world", "lift", "0 0 1")
    joints += _joint("pitch", "revolute", "lift", "car", "0 1 0")
    for tag, x in (("f", xm), ("r", -xm)):
        pad = ""
        for sgn, nm in ((1, "l"), (-1, "r")):
            pad += _vis(f"pad_{tag}_{nm}", f"0 {sgn * 1.5:.4f} {-GAP_PAD_H / 2:.4f} 0 0 0", _box(5.0, 0.7, GAP_PAD_H),
                        "0.35 0.36 0.40 1")
            pad += _vis(f"coil_{tag}_{nm}", f"0 {sgn * 1.5:.4f} {-GAP_PAD_H - 0.06:.4f} 0 0 0", _box(4.6, 0.8, 0.12),
                        "0.78 0.45 0.20 1")
        links += _link(f"bogie_{tag}", f"{x} 0 {Z_RAIL} 0 0 0", pad)
        joints += _joint(f"gap_{tag}", "prismatic", "world", f"bogie_{tag}", "0 0 -1")
    return (
        '<?xml version="1.0"?>\n<!--\n'
        "  maglev-train: a Transrapid-style car on a T-shaped guideway (Z up, X forward, metres).\n"
        "  The pillars (every span) scroll under the car with the joint \"scroll\" (position -s mod span), so the\n"
        "  car stays near the origin. The joints \"heave\" and \"pitch\" and the pads' \"gap_f\" and \"gap_r\" are bound with\n"
        f"  a gain of {E_VEH:g}: deviations from the nominal levitated state are exaggerated {E_VEH:g} times (the nominal\n"
        "  gap of 10 mm itself stays true to scale). The copper coils are coloured by the coil current.\n"
        "  Written by examples/maglev-train/design/build_model.py.\n-->\n"
        '<sdf version="1.9">\n  <model name="maglev-train">\n'
        f"{links}{joints}"
        "  </model>\n</sdf>\n"
    )


def scene_module(d: dict) -> str:
    """Side view of one module: rail, magnet pad on the bogie, body hanging on the secondary suspension."""
    rig = _vis("ground", "0 0 -0.05 0 0 0", _box(6.0, 3.0, 0.1), "0.28 0.40 0.24 1")
    for sgn in (1, -1):
        rig += _vis(f"pillar_{sgn}", f"{sgn * 1.4:.4f} 0 1.0 0 0 0", _box(0.4, 0.8, 2.0), "0.72 0.72 0.70 1")
    rig += _vis("beam", "0 0 2.3 0 0 0", _box(3.6, 1.0, 0.6), "0.78 0.78 0.76 1")
    rig += _vis("rail", "0 0 1.97 0 0 0", _box(3.0, 1.2, 0.06), "0.25 0.30 0.55 1")
    for sgn in (1, -1):
        rig += _vis(f"skid_{sgn}", f"{sgn * 0.9:.4f} 0 {1.94 - (E_MOD * d['h_skid'] + (1 - E_MOD) * d['h0']) - 0.02:.4f} 0 0 0",
                    _box(0.25, 0.9, 0.04), "0.85 0.6 0.15 1")
    bogie = _vis("pad", "0 0 -0.08 0 0 0", _box(1.3, 0.8, 0.16), "0.35 0.36 0.40 1")
    bogie += _vis("coil", "0 0 -0.2 0 0 0", _box(1.1, 0.9, 0.12), "0.78 0.45 0.20 1")
    bogie += _vis("frame", "0 0 -0.34 0 0 0", _box(1.5, 0.6, 0.2), "0.50 0.54 0.60 1")
    bogie += _vis("spring", "0.45 0 -0.62 0 0 0", _cyl(0.05, 0.4), "0.85 0.85 0.2 1")
    bogie += _vis("damper", "-0.45 0 -0.62 0 0 0", _cyl(0.04, 0.4), "0.3 0.3 0.3 1")
    body = _vis("body", "0 0 -1.12 0 0 0", _box(1.6, 1.0, 0.6), "0.92 0.93 0.95 1")
    body += _vis("window", "0 0.51 -1.07 0 0 0", _box(1.2, 0.02, 0.25), "0.12 0.17 0.28 1")
    links = _link("rig", "0 0 0 0 0 0", rig)
    links += _link("bogie", "0 0 1.94 0 0 0", bogie)
    links += _link("body", "0 0 1.94 0 0 0", body)
    joints = _joint("gap", "prismatic", "rig", "bogie", "0 0 -1")
    joints += _joint("suspension", "prismatic", "bogie", "body", "0 0 -1")
    return (
        '<?xml version="1.0"?>\n<!--\n'
        "  maglev-module: one levitation module (Z up, metres, side view). The magnet pad hangs below the rail;\n"
        f"  the joint \"gap\" carries the gap with a gain of {E_MOD:g} (deviations from the nominal 10 mm exaggerated {E_MOD:g} times),\n"
        "  the joint \"suspension\" carries the stretch of the secondary spring, also exaggerated. The coil is\n"
        "  coloured by the current.\n  Written by examples/maglev-train/design/build_model.py.\n-->\n"
        '<sdf version="1.9">\n  <model name="maglev-module">\n'
        f"{links}{joints}"
        "  </model>\n</sdf>\n"
    )


# --------------------------------------------------------------------------- model 1: one module


def model_module() -> dict:
    m = DESIGN["module"]
    sc = DESIGN["scenario"]
    dg = Diagram()
    add_module(dg, 700, 0)
    # body share on Jq: mass, weight and a payload step
    dg.node("Body", "stdlib:bondgraph/I", 1700, 560, params={"i": "m_c"})
    dg.node("BodyWeight", "stdlib:bondgraph/Se", 1700, 640, params={"e": "-m_c*g0"})
    dg.node("Load", "stdlib:bondgraph/MSe", 1700, 720, params={"gain": "-1.0"})
    dg.node("LoadStep", "stdlib:sources/Step", 1500, 720,
            params={"t_step": "t_load", "initial": "0.0", "final": "dm_load*g0"})
    dg.bond("Jq", None, "Body", "p")
    dg.bond("BodyWeight", "p", "Jq", None)
    dg.bond("Load", "p", "Jq", None)
    dg.sig("LoadStep", "y", "Load", "u")
    # reference: step from the skid gap to the nominal gap, prefiltered
    dg.node("RefStep", "stdlib:sources/Step", 40, 40,
            params={"t_step": "t_ref", "initial": "h_skid", "final": "h_nom"})
    dg.node("RefLag", "stdlib:continuous/FirstOrder", 240, 40, params={"k": "1.0", "tau": "tau_ref"},
            starts={"x": "h_skid"})
    dg.sig("RefStep", "y", "RefLag", "u")
    dg.sig("RefLag", "y", "Ctl", "h_ref")
    # guideway step: smoothed by 1/(1 + s/w)^2, as a velocity
    dg.node("RailStep", "stdlib:sources/Step", 40, 640,
            params={"t_step": "t_rail", "initial": "0.0", "final": "-dz_rail"})
    dg.node("RailVel", "stdlib:continuous/TransferFunction", 240, 640,
            params={"num": "[w_rail*w_rail, 0.0]", "den": "[1.0, 2.0*w_rail, w_rail*w_rail]"},
            constants={"n": "2", "m": "1"})
    dg.sig("RailStep", "y", "RailVel", "u")
    dg.sig("RailVel", "y", "Rail", "u")
    # monitors: body position by integrating the body flow
    dg.node("BodyV", "stdlib:bondgraph/Df", 1900, 560)
    dg.bond("Jq", None, "BodyV", "p")
    dg.note("**Levitation module.** Left: chopper (MSe) driving the coil 1-junction Jc with the coil "
            "resistance, a current detector and the coil port of EM, the electromagnet IC-field "
            "(L(h) = L_inf + 2 alpha/h, F = alpha i^2/h^2). Right: the bogie 1-junction Jb (chassis mass, "
            "weight, EM armature, skid contact and the secondary suspension Sus) and the body junction Jq. "
            "Velocities are positive upward. The guideway moves with the flow source Rail on Jr.",
            40, 900, 1500, 90)
    plots = [
        {"id": "p1", "title": "Gap and reference [m]", "signals": ["Gap/y", "RefLag/y"]},
        {"id": "p2", "title": "Coil current [A]", "signals": ["EM/i", "Ctl/i_ff"]},
        {"id": "p3", "title": "Chopper voltage [V]", "signals": ["Ctl/v"]},
        {"id": "p4", "title": "Magnet force and total weight [N]", "signals": ["EM/F"]},
    ]
    params = module_globals(m) + [
        g("m_c", num(m["m_c"]), "kg", "Body mass carried by the module (a quarter of the car body)"),
        g("t_ref", num(sc["t_ref"]), "s", "Time the gap reference steps from the skid gap to the nominal gap"),
        g("tau_ref", num(sc["tau_ref"]), "s", "Reference prefilter time constant"),
        g("t_rail", num(sc["t_rail"]), "s", "Time of the guideway step"),
        g("dz_rail", num(sc["dz_rail"]), "m", "Guideway step: the rail sinks towards the vehicle by this much (the gap closes)"),
        g("w_rail", num(sc["w_rail"]), "rad/s", "Smoothing of the guideway step 1/(1 + s/w)^2"),
        g("t_load", num(sc["t_load"]), "s", "Time of the payload step"),
        g("dm_load", num(sc["dm_load"]), "kg", "Payload added to the body share"),
    ]
    bindings = [
        {"target": "joint:gap", "property": "position", "signal": "Gap/y", "gain": E_MOD, "offset": (1 - E_MOD) * m["h0"]},
        {"target": "joint:suspension", "property": "position", "signal": "Sus/x", "gain": 5.0, "offset": -5.0 * m["e0"]},
        {"target": "visual:coil", "property": "color", "signal": "EM/i", "colormap": "heat", "range": [0.0, 250.0]},
    ]
    gap_zones = [{"from": 0.0, "to": 0.006, "tone": "bad"}, {"from": 0.006, "to": 0.008, "tone": "warn"},
                 {"from": 0.008, "to": 0.013, "tone": "good"}, {"from": 0.013, "to": 0.02, "tone": "warn"}]
    dashboard = {
        "autoRerun": True,
        "cards": [
            {"id": "d1", "kind": "text", "size": "2x1", "title": "Levitation module",
             "options": {"markdown": True, "text":
                 "A quarter of a car on one EMS magnet. At 0.1 s the gap reference drops from the skid gap to **10 mm**; "
                 "at 2 s the guideway sinks 1 mm; at 4 s a payload is added. Change an input and the model runs again."}},
            {"id": "d2", "kind": "slider", "size": "1x1", "title": "Nominal gap", "parameter": "global:h_nom",
             "options": {"min": 0.008, "max": 0.014, "step": 0.0005, "decimals": 4, "unit": "m"}},
            {"id": "d3", "kind": "gauge", "size": "1x1", "title": "Gap", "signals": ["Gap/y"],
             "options": {"min": 0.0, "max": 0.02, "decimals": 4, "unit": "m", "zones": gap_zones}},
            {"id": "d4", "kind": "slider", "size": "2x1", "title": "Guideway step (+ = rail sinks, gap closes)",
             "parameter": "global:dz_rail", "options": {"min": -0.003, "max": 0.003, "step": 0.0002, "decimals": 4, "unit": "m"}},
            {"id": "d5", "kind": "slider", "size": "2x1", "title": "Payload step", "parameter": "global:dm_load",
             "options": {"min": 0.0, "max": 4000.0, "step": 100.0, "decimals": 0, "unit": "kg"}},
            {"id": "d6", "kind": "gauge", "size": "1x1", "title": "Coil current", "signals": ["EM/i"],
             "options": {"min": 0.0, "max": 400.0, "decimals": 1, "unit": "A",
                         "zones": [{"from": 0.0, "to": 300.0, "tone": "good"}, {"from": 300.0, "to": 400.0, "tone": "warn"}]}},
            {"id": "d7", "kind": "bar", "size": "1x1", "title": "Chopper voltage", "signals": ["Ctl/v"],
             "options": {"min": -800.0, "max": 800.0, "decimals": 0, "unit": "V", "orientation": "horizontal",
                         "zones": [{"from": -800.0, "to": -700.0, "tone": "warn"}, {"from": -700.0, "to": 700.0, "tone": "good"},
                                   {"from": 700.0, "to": 800.0, "tone": "warn"}]}},
            {"id": "d8", "kind": "plot", "size": "4x2", "title": "Gap and reference", "signals": ["Gap/y", "RefLag/y"]},
            {"id": "d9", "kind": "plot", "size": "4x2", "title": "Coil current and chopper voltage", "signals": ["EM/i", "Ctl/v"]},
        ],
    }
    return model_doc("maglev-module", "One EMS levitation module carrying a quarter of a car.", dg,
                     settings(sc["t_end"], 8001), plots, "scenes/maglev-module.sdf", bindings, params, dashboard)


# --------------------------------------------------------------------------- model 2: the vehicle


def module_definition() -> dict:
    """library/LevitationModule.bgsub.json: one levitation module behind the ports `body` (the
    secondary suspension's top), `h_ref`, `v_rail`, `gap`, `i` and `v`. The vehicle holds two
    instances, ModF and ModR; nothing is pinned, the values are the globals the module reads."""
    sd = Diagram()
    add_module(sd, 0, 0, with_body_port=False, ports=True)
    return {
        "format": "bgsim.subsystem", "name": "LevitationModule",
        "description": ("One EMS levitation module: chopper and coil (stdlib Electromagnet), chassis on its "
                        "skids, secondary suspension to the body port, gap sensor and the GapController. Reads "
                        "the module globals (a1..a4, Tf, R_coil, c_trim, V_max, alpha, L_inf, m_b, k_s, c_s, "
                        "h_nom, h_rest, h_stop, h_skid, k_c, d_c, e_spring, g0). Generated by "
                        "design/build_model.py."),
        "ports": sd.ports, "diagram": sd.doc(), "pins": {"params": [], "starts": []},
    }


def model_open_loop() -> dict:
    """The module without feedback, released 10 nm from its trim gap: the gap deviation grows with the unstable pole."""
    m = DESIGN["module"]
    ol = DESIGN["open_loop"]
    dg = Diagram()
    add_module(dg, 700, 0, trim=True)
    dg.node("Body", "stdlib:bondgraph/I", 1700, 560, params={"i": "m_c"})
    dg.node("BodyWeight", "stdlib:bondgraph/Se", 1700, 640, params={"e": "-m_c*g0"})
    dg.bond("Jq", None, "Body", "p")
    dg.bond("BodyWeight", "p", "Jq", None)
    dg.node("RefHold", "stdlib:sources/Constant", 40, 40, params={"value": "h_nom"})
    dg.sig("RefHold", "y", "Ctl", "h_ref")
    dg.node("RailHold", "stdlib:sources/Constant", 40, 640, params={"value": "0.0"})
    dg.sig("RailHold", "y", "Rail", "u")
    dg.node("Growth", "stdlib:continuous/Divide", 1400, 900)
    dg.sig("GapRate", "y", "Growth", "u1")
    dg.sig("Err", "y", "Growth", "u2")
    dg.note("**Open loop.** The controller gains are zero, so the chopper only holds the trim voltage R*i_trim. "
            "The module starts at its trim state with the gap 10 nm too large. The gap deviation then grows "
            "as exp(p t) with the unstable pole p of the linearisation; Growth/y = (dh/dt)/(h - h_nom) tends to p.",
            40, 900, 1200, 70)
    params = module_globals(m) + [
        g("m_c", num(m["m_c"]), "kg", "Body mass carried by the module (a quarter of the car body)"),
        g("dh0", num(ol["dh0"]), "m", "Initial gap offset from the trim gap"),
    ]
    for gl in params:
        if gl["name"] in ("a1", "a2", "a3"):
            gl["value"] = "0.0"
        if gl["name"] == "a4":
            gl["value"] = "1.0e-6"
    plots = [
        {"id": "p1", "title": "Gap deviation from the trim gap [m]", "signals": ["Err/y"]},
        {"id": "p2", "title": "Growth rate (dh/dt)/(h - h_nom) [1/s]", "signals": ["Growth/y"]},
    ]
    st = settings(0.3, 3001, reltol=1e-10, abstol=1e-13)
    return model_doc("maglev-module-open-loop", "The levitation module without feedback.", dg, st, plots, None, [], params)


def model_vehicle() -> dict:
    m = DESIGN["vehicle"]
    v = DESIGN["veh"]
    dg = Diagram()
    # ---- 3D car body: floating base, rigid body with gravity, the drive ports of the joint
    dg.node("World", "stdlib:multibond/GroundSpatial", 40, 40)
    dg.node("Free", "stdlib:spatial/Free3D", 240, 40)
    dg.node("Body", "stdlib:spatial/RigidBody3D", 480, 40,
            params={"m": "m_body", "J": "[J_roll, J_pitch, J_yaw]", "g0": "g0"})
    dg.bond("World", "p", "Free", "parent")
    dg.bond("Free", "child", "Body", "p")
    dg.sig("Free", "pose", "Body", "g")
    # ---- along the track (drive4): LSM thrust, aerodynamic drag
    dg.node("Jx", "1", 240, 240)
    dg.node("Lsm", "stdlib:bondgraph/MSe", 40, 240, params={"gain": "1.0"})
    dg.node("LsmLag", "stdlib:continuous/FirstOrder", 40, 340, params={"k": "1.0", "tau": "tau_lsm"})
    dg.node("Drag", "stdlib:bondgraph/MR", 240, 340, params={"gain": "1.0"})
    dg.node("DragK", "stdlib:continuous/Gain", 60, 440, params={"k": "k_aero"})
    dg.node("Speed", "stdlib:bondgraph/Df", 440, 240)
    dg.node("SpeedAbs", "stdlib:continuous/Abs", 240, 440)
    dg.bond("Jx", None, "Free", "drive4")
    dg.bond("Lsm", "p", "Jx", None)
    dg.bond("Jx", None, "Drag", "p")
    dg.bond("Jx", None, "Speed", "p")
    dg.sig("LsmLag", "y", "Lsm", "u")
    dg.sig("Speed", "y", "SpeedAbs", "u")
    dg.sig("SpeedAbs", "y", "DragK", "u")
    dg.sig("DragK", "y", "Drag", "u")
    dg.node("Profile", "stdlib:motion/TrapezoidalProfile", 40, 560,
            params={"q_start": "0.0", "q_end": "q_end", "t_start": "t_go", "v_max": "v_cruise", "a_max": "a_acc"})
    dg.node("LsmCtl", "project:LsmController", 240, 560,
            params={"m": "m_body", "k_aero": "k_aero", "Kp": "Kp_v", "Ti": "Ti_v", "F_max": "F_max"})
    dg.sig("Profile", "v", "LsmCtl", "v_ref")
    dg.sig("Profile", "a", "LsmCtl", "a_ref")
    dg.sig("Speed", "y", "LsmCtl", "v")
    dg.sig("LsmCtl", "F_cmd", "LsmLag", "u")
    # ---- guidance (lateral, roll, yaw): stiff spring-dampers on drive5, drive1, drive3
    for name, port, kp, cp, y in (("Lat", "drive5", "k_guide", "c_guide", 760), ("Roll", "drive1", "kr_guide", "cr_guide", 860),
                                   ("Yaw", "drive3", "kr_guide", "cr_guide", 960)):
        dg.node(f"J{name}", "1", 240, y)
        dg.node(f"K{name}", "stdlib:bondgraph/C", 400, y - 30, params={"c": f"1.0/{kp}"})
        dg.node(f"D{name}", "stdlib:bondgraph/R", 400, y + 30, params={"r": cp})
        dg.bond(f"J{name}", None, "Free", port)
        dg.bond(f"J{name}", None, f"K{name}", "p")
        dg.bond(f"J{name}", None, f"D{name}", "p")
    # ---- heave (drive6) and pitch (drive2) junctions and the lever to the two modules
    dg.node("Jz", "1", 760, 240)
    dg.node("Jt", "1", 760, 520)
    dg.bond("Jz", None, "Free", "drive6")
    dg.bond("Jt", None, "Free", "drive2")
    dg.node("AccZ", "stdlib:continuous/FilteredDerivative", 1100, 140, params={"Tf": "0.005"})
    dg.node("HeaveV", "stdlib:bondgraph/Df", 960, 240)
    dg.node("PitchRate", "stdlib:bondgraph/Df", 960, 520)
    dg.sig("HeaveV", "y", "AccZ", "u")
    dg.bond("Jz", None, "HeaveV", "p")
    dg.bond("Jt", None, "PitchRate", "p")
    # pose taps: track coordinate and pitch quaternion component
    dg.node("PoseX", "stdlib:continuous/Select", 480, 160, constants={"N": "7", "index": "5"})
    dg.node("PoseQy", "stdlib:continuous/Select", 480, 220, constants={"N": "7", "index": "3"})
    dg.node("PoseZ", "stdlib:continuous/Select", 480, 280, constants={"N": "7", "index": "7"})
    for n in ("PoseX", "PoseQy", "PoseZ"):
        dg.sig("Free", "pose", n, "u")
    dg.node("R31", "stdlib:continuous/Gain", 700, 220, params={"k": "-2.0"})
    dg.sig("PoseQy", "y", "R31", "u")
    # reference gap: step from the skid gap to the nominal gap, prefiltered
    dg.node("RefStep", "stdlib:sources/Step", 40, 1100,
            params={"t_step": "t_ref", "initial": "h_skid", "final": "h_nom"})
    dg.node("RefLag", "stdlib:continuous/FirstOrder", 240, 1100, params={"k": "1.0", "tau": "tau_ref"},
            starts={"x": "h_skid"})
    dg.sig("RefStep", "y", "RefLag", "u")
    for tag, sign, X in (("F", 1, 1200), ("R", -1, 1200)):
        y0 = 40 if tag == "F" else 760
        dg.node(f"Mod{tag}", "project:LevitationModule", X, y0)
        # kinematic lever: the module point moves with v_z - x*w_y (z up); a 0-junction adds the heave velocity
        # and the pinion flow (radius x_m, from the pitch rate); the module sees it as a downward velocity.
        # Both rack-and-pinion terminals are `in` (the junctions bond into them); the rear module sits behind
        # the centre of mass (x = -x_m), so a -1 transformer turns the pitch rate round before its pinion.
        dg.node(f"Lever{tag}", "stdlib:converters/RackAndPinion", 960, y0 + 120, params={"r": "x_m"})
        dg.node(f"Z{tag}", "0", 1100, y0 + 100)
        dg.bond("Jz", None, f"Z{tag}", None)
        if tag == "F":
            dg.bond("Jt", None, f"Lever{tag}", "a")
        else:
            dg.node(f"Flip{tag}", "stdlib:bondgraph/TF", 860, y0 + 120, params={"n": "-1.0"})
            dg.bond("Jt", None, f"Flip{tag}", "p1")
            dg.bond(f"Flip{tag}", "p2", f"Lever{tag}", "a")
        dg.bond(f"Z{tag}", None, f"Lever{tag}", "b")
        # the forward speed has a vertical component in the world when the car is pitched: R31 = -2 q_y
        dg.node(f"Climb{tag}", "stdlib:bondgraph/MTF", 960, y0 + 200)
        dg.bond("Jx", None, f"Climb{tag}", "p1")
        dg.bond(f"Climb{tag}", "p2", f"Z{tag}", None)
        dg.sig("R31", "y", f"Climb{tag}", "u")
        dg.bond(f"Z{tag}", None, f"Mod{tag}", "body")
        dg.sig("RefLag", "y", f"Mod{tag}", "h_ref")
        # guideway under the module: track coordinate = body x (+ or - x_m for the front or rear module)
        dg.node(f"Gw{tag}", "project:Guideway", 700, y0 + 100,
                params={"L_span": "L_span", "A_sag": "A_sag", "s_b": "s_bump", "A_b": "A_bump",
                        "lam_b": "lam_bump", "x_off": "x_m" if tag == "F" else "-x_m"})
        dg.sig("PoseX", "y", f"Gw{tag}", "s")
        dg.sig("Speed", "y", f"Gw{tag}", "v")
        dg.sig(f"Gw{tag}", "w", f"Mod{tag}", "v_rail")
    plots = [
        {"id": "p1", "title": "Speed and reference [m/s]", "signals": ["Speed/y", "Profile/v"]},
        {"id": "p2", "title": "Front and rear gap [m]", "signals": ["ModF/Gap/y", "ModR/Gap/y"]},
        {"id": "p3", "title": "Coil currents [A]", "signals": ["ModF/EM/i", "ModR/EM/i"]},
        {"id": "p4", "title": "LSM thrust and aerodynamic drag [N]", "signals": ["Lsm/p.e", "Drag/p.e"]},
        {"id": "p5", "title": "Body heave [m], vertical acceleration [m/s^2] and pitch rate [rad/s]",
         "signals": ["Free/pz", "AccZ/y", "PitchRate/y"]},
        {"id": "p6", "title": "Guideway deflection under the two modules [m]", "signals": ["GwF/z", "GwR/z"]},
        {"id": "p7", "title": "Track position [m]", "signals": ["Free/px", "Profile/q"]},
    ]
    params = module_globals(m) + [
        g("m_c", num(m["m_c"]), "kg", "Body mass carried by one module (half the car body)"),
        g("m_body", "2*m_c", "kg", "Car body mass"),
        g("J_roll", num(DESIGN["veh"]["J"][0]), "kg*m^2", "Roll inertia of the car body (homogeneous box)"),
        g("J_pitch", num(DESIGN["veh"]["J"][1]), "kg*m^2", "Pitch inertia of the car body"),
        g("J_yaw", num(DESIGN["veh"]["J"][2]), "kg*m^2", "Yaw inertia of the car body"),
        g("x_m", num(v["x_m"]), "m", "Module position from the centre of mass (front +, rear -)"),
        g("k_guide", num(v["k_guide"]), "N/m", "Lateral guidance stiffness"),
        g("c_guide", num(v["c_guide"]), "N*s/m", "Lateral guidance damping"),
        g("kr_guide", num(v["kr_guide"]), "N*m/rad", "Roll and yaw guidance stiffness"),
        g("cr_guide", num(v["cr_guide"]), "N*m*s/rad", "Roll and yaw guidance damping"),
        g("k_aero", num(v["k_aero"]), "N*s^2/m^2", "0.5*rho*Cd*A"),
        g("v_cruise", num(v["v_cruise"]), "m/s", "Cruise speed (430 km/h)"),
        g("a_acc", num(v["a_acc"]), "m/s^2", "Acceleration and braking"),
        g("t_go", num(v["t_go"]), "s", "Time the speed profile starts"),
        g("T_cruise", num(v["T_cruise"]), "s", "Duration of the cruise phase"),
        g("q_end", "v_cruise*v_cruise/a_acc + v_cruise*T_cruise", "m", "Distance of the move: accelerate, cruise for T_cruise, brake"),
        g("tau_lsm", num(v["tau_lsm"]), "s", "Thrust response of the long stator"),
        g("F_max", num(v["F_max"]), "N", "Thrust limit"),
        g("Kp_v", num(v["Kp_v"]), "N*s/m", "Speed controller gain"),
        g("Ti_v", num(v["Ti_v"]), "s", "Speed controller integral time"),
        g("L_span", num(v["L_span"]), "m", "Span length"),
        g("A_sag", num(v["A_sag"]), "m", "Sag at mid-span"),
        g("s_bump", num(v["s_bump"]), "m", "Track position of the bump"),
        g("A_bump", num(v["A_bump"]), "m", "Bump height"),
        g("lam_bump", num(v["lam_bump"]), "m", "Bump length"),
        g("t_ref", "0.1", "s", "Time the gap reference steps to the nominal gap"),
        g("tau_ref", "0.15", "s", "Reference prefilter"),
    ]
    pz_nom = m["h_rest"] - m["h0"]
    bindings = [
        {"target": "joint:scroll", "property": "position", "signal": "GwF/ph", "gain": -1.0, "offset": 0.0},
        {"target": "joint:heave", "property": "position", "signal": "Free/pz", "gain": E_VEH, "offset": (1 - E_VEH) * pz_nom},
        {"target": "joint:pitch", "property": "position", "signal": "Free/qy", "gain": 2 * E_VEH, "offset": 0.0},
        {"target": "joint:gap_f", "property": "position", "signal": "ModF/Gap/y", "gain": E_VEH, "offset": (1 - E_VEH) * m["h0"]},
        {"target": "joint:gap_r", "property": "position", "signal": "ModR/Gap/y", "gain": E_VEH, "offset": (1 - E_VEH) * m["h0"]},
    ]
    for tag in ("f", "r"):
        for nm in ("l", "r"):
            bindings.append({"target": f"visual:coil_{tag}_{nm}", "property": "color", "signal": f"Mod{tag.upper()}/EM/i",
                             "colormap": "heat", "range": [0.0, 250.0]})
    gap_zones = [{"from": 0.0, "to": 0.006, "tone": "bad"}, {"from": 0.006, "to": 0.008, "tone": "warn"},
                 {"from": 0.008, "to": 0.013, "tone": "good"}, {"from": 0.013, "to": 0.02, "tone": "warn"}]
    dashboard = {
        "autoRerun": True,
        "cards": [
            {"id": "d1", "kind": "text", "size": "2x1", "title": "Maglev car",
             "options": {"markdown": True, "text":
                 "A 53 t car section on two EMS modules: lift-off at 0.1 s, then the long stator accelerates it to 430 km/h, "
                 "it cruises and brakes. The guideway sags between its pillars and has one 2 mm bump at 8.5 km. "
                 "The 3D view exaggerates gap, heave and pitch 100 times."}},
            {"id": "d2", "kind": "slider", "size": "2x1", "title": "Cruise speed", "parameter": "global:v_cruise",
             "options": {"min": 30.0, "max": 119.5, "step": 5.0, "decimals": 1, "unit": "m/s"}},
            {"id": "d3", "kind": "value", "size": "1x1", "title": "Speed", "signals": ["Speed/y"],
             "options": {"decimals": 1, "unit": "m/s", "sparkline": True}},
            {"id": "d4", "kind": "slider", "size": "2x1", "title": "Guideway sag at mid-span", "parameter": "global:A_sag",
             "options": {"min": 0.0, "max": 0.008, "step": 0.0005, "decimals": 4, "unit": "m"}},
            {"id": "d5", "kind": "slider", "size": "2x1", "title": "Bump height", "parameter": "global:A_bump",
             "options": {"min": 0.0, "max": 0.006, "step": 0.0005, "decimals": 4, "unit": "m"}},
            {"id": "d6", "kind": "gauge", "size": "1x1", "title": "Front gap", "signals": ["ModF/Gap/y"],
             "options": {"min": 0.0, "max": 0.02, "decimals": 4, "unit": "m", "zones": gap_zones}},
            {"id": "d7", "kind": "gauge", "size": "1x1", "title": "Body acceleration", "signals": ["AccZ/y"],
             "options": {"min": -1.0, "max": 1.0, "decimals": 3, "unit": "m/s^2",
                         "zones": [{"from": -0.3, "to": 0.3, "tone": "good"}, {"from": -0.6, "to": -0.3, "tone": "warn"},
                                   {"from": 0.3, "to": 0.6, "tone": "warn"}]}},
            {"id": "d8", "kind": "plot", "size": "4x2", "title": "Speed and reference", "signals": ["Speed/y", "Profile/v"]},
            {"id": "d9", "kind": "plot", "size": "4x2", "title": "Front and rear gap", "signals": ["ModF/Gap/y", "ModR/Gap/y"]},
            {"id": "d10", "kind": "plot", "size": "4x2", "title": "Body vertical acceleration and pitch rate",
             "signals": ["AccZ/y", "PitchRate/y"]},
        ],
    }
    return model_doc("maglev-vehicle", "A car section on two EMS modules.", dg,
                     settings(v["t_end"], 13501), plots, "scenes/maglev-train.sdf", bindings, params, dashboard)


# --------------------------------------------------------------------------- expected.json

NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
           "note": "integral causality everywhere, no algebraic loop, no event storm"}


def expected() -> dict:
    """Acceptance checks. Every number comes from design.json (analytic trim, linearisation, scipy simulations)."""
    m = DESIGN["module"]
    v2 = DESIGN["vehicle"]
    veh = DESIGN["veh"]
    ref = DESIGN["ref_module"]
    rv = DESIGN["ref_vehicle"]
    ol = DESIGN["open_loop"]
    sc = DESIGN["scenario"]
    h0 = m["h0"]
    W1 = m["W"]
    W1_loaded = W1 + sc["dm_load"] * 9.81

    module = [
        {"kind": "scene_bindings"},
        NO_DIAG,
        {"kind": "cursor_value", "signal": "EM/i", "t": 1.9, "value": ref["i_trim"], "rtol": 2e-3,
         "note": "trim current i = c_trim*h0 = sqrt((m_b + m_c) g/alpha)*h0 (analytic): the integral action finds it. "
                 "1.4 s after lift-off the secondary-suspension mode (-1.8 +- 6.1j 1/s) has not quite decayed: 0.12 % left"},
        {"kind": "cursor_value", "signal": "EM/F", "t": 1.9, "value": W1, "rtol": 2e-3,
         "note": "the magnet carries the whole module weight (m_b + m_c) g (analytic)"},
        {"kind": "cursor_value", "signal": "Gap/y", "t": 1.9, "value": h0, "abs": 8e-6,
         "note": "gap error below 8 um (0.08 %) before the guideway step: the decaying body mode again"},
        {"kind": "cursor_value", "signal": "EM/i", "t": 7.9, "value": ref["i_loaded"], "rtol": 6e-4,
         "note": "after the payload step the trim current rises with sqrt(weight): c_trim*h0*sqrt((W + dm g)/W) (analytic)"},
        {"kind": "cursor_value", "signal": "EM/F", "t": 7.9, "value": W1_loaded, "rtol": 6e-4,
         "note": "magnet force = weight with the payload (analytic)"},
        {"kind": "cursor_value", "signal": "Err/y", "t": 7.9, "value": ref["h_final"] - h0, "abs": 1.5e-6,
         "note": "gap error 6 s after the payload step: the slow integral tail of the scipy design simulation"},
        {"kind": "max_abs_le", "signal": "Err/y", "from_t": 1.8, "to_t": 1.99, "value": 2e-5,
         "note": "gap error before the guideway step stays below 20 um (0.2 %)"},
        {"kind": "max_abs", "signal": "Err/y", "from_t": sc["t_rail"], "to_t": sc["t_rail"] + 1.0,
         "value": ref["rail_dev_max"], "rtol": 0.03,
         "note": "peak gap deviation after the 1 mm guideway step (scipy nonlinear simulation of the same loop)"},
        {"kind": "max_abs", "signal": "Err/y", "from_t": sc["t_load"], "to_t": sc["t_load"] + 1.0,
         "value": ref["load_dev_max"], "rtol": 0.03,
         "note": "peak gap deviation after the payload step (scipy)"},
        {"kind": "max_abs", "signal": "EM/i", "value": ref["i_lift_max"], "rtol": 3e-3,
         "note": "peak coil current of the lift-off (scipy)"},
        {"kind": "max_abs_le", "signal": "EM/i", "value": 300.0,
         "note": "coil current within twice the trim current (design limit of this model, estimate)"},
        {"kind": "max_abs_le", "signal": "Ctl/v", "value": m["V_max"] * (1 + 1e-9), "note": "chopper rail"},
        {"kind": "max_abs_le", "signal": "Vcoil/y", "value": m["V_max"] * (1 + 1e-9),
         "note": "coil terminal voltage within the rail"},
        {"kind": "max_abs", "signal": "Skid/a.e", "from_t": 1.5, "value": 0.0, "abs": 1e-6,
         "note": "after lift-off the skids and the touch-down stop carry nothing"},
        {"kind": "compare_signals", "signal": "EM/h", "signal_b": "Gap/y", "max_abs": 1e-9,
         "note": "the field's gap state and the sensor integrate the same relative velocity"},
    ]
    for smp in ref["samples"]:
        module.append({"kind": "cursor_value", "signal": "Gap/y", "t": smp["t"], "value": smp["h"], "abs": 4e-5,
                       "note": "gap of the scipy nonlinear simulation of the same loop (lift-off, guideway step, payload step)"})
        module.append({"kind": "cursor_value", "signal": "EM/i", "t": smp["t"], "value": smp["i"], "rtol": 4e-3, "abs": 0.5,
                       "note": "coil current of the scipy simulation"})

    open_loop = [
        NO_DIAG,
        {"kind": "cursor_value", "signal": "Growth/y", "t": ol["t_check"], "value": ol["pole"], "rtol": 5e-3,
         "note": f"growth rate of the open-loop gap deviation = the unstable pole {ol['pole']:.4f} 1/s of the "
                 "5-state linearisation (module, secondary suspension and coil; scipy eigenvalue), up to the "
                 "excitation of the stable modes and the nonlinearity of a 30 um deviation"},
        {"kind": "cursor_value", "signal": "Growth/y", "t": 0.1, "value": ol["pole"], "rtol": 5e-3},
    ]

    # bgsim records every ~18 ms; the check interpolates linearly between samples, which alone costs up to
    # 1e-5 m on a 0.25 mm, 5 Hz gap oscillation (h'' = 0.25 m/s^2)
    tol_gap, tol_i = 2e-5, 2.5e-3
    vehicle = [
        {"kind": "scene_bindings"},
        NO_DIAG,
        {"kind": "cursor_value", "signal": "ModF/EM/i", "t": 3.0, "value": v2["c_trim"] * h0, "rtol": 6e-4,
         "note": "trim current c_trim*h0 of each module at rest, levitated (analytic)"},
        {"kind": "cursor_value", "signal": "ModF/EM/F", "t": 3.0, "value": v2["W"], "rtol": 6e-4,
         "note": "each module carries half the car body and its own chassis, (m_body/2 + m_b) g (analytic)"},
        {"kind": "cursor_value", "signal": "ModR/EM/F", "t": 3.0, "value": v2["W"], "rtol": 6e-4},
        {"kind": "cursor_value", "signal": "Free/pz", "t": 3.9, "value": v2["h_rest"] - h0, "abs": 3e-5,
         "note": "the car body has risen from its rest on the skids (gap h_rest) to the nominal gap (analytic)"},
        {"kind": "cursor_value", "signal": "ModF/Gap/y", "t": 3.0, "value": h0, "abs": 3e-6},
        {"kind": "cursor_value", "signal": "Speed/y", "t": 60.0, "value": veh["a_acc"] * (60.0 - veh["t_go"]), "rtol": 2e-4,
         "note": "constant acceleration a_acc from t_go: v = a (t - t_go) (analytic)"},
        {"kind": "cursor_value", "signal": "Speed/y", "t": 148.0, "value": veh["v_cruise"], "rtol": 1e-4,
         "note": "cruise speed 430 km/h"},
        {"kind": "ratio", "signal": "Lsm/p.e", "signal_b": "Drag/p.e", "t": 148.0, "value": 1.0, "rtol": 3e-3,
         "note": "at cruise the LSM thrust balances the aerodynamic drag"},
        {"kind": "cursor_value", "signal": "Drag/p.e", "t": 148.0, "value": veh["k_aero"] * veh["v_cruise"] ** 2, "rtol": 1e-3,
         "note": "drag force 0.5 rho Cd A v^2 at 430 km/h (analytic)"},
        {"kind": "cursor_value", "signal": "Drag/p.P", "t": veh["t_go"] + 400.0 / 3.6 / veh["a_acc"], "value": 3.53e6, "rtol": 0.04,
         "note": "published: aerodynamic drag needs about 3.53 MW at 400 km/h (Wikipedia 'Transrapid'); the model, with the same Cd and "
                 "area, gives 3.42 MW. Not an independent check of Cd and the area, only of the drag law and the units."},
        {"kind": "cursor_value", "signal": "Free/px", "t": veh["t_end"] - 0.05, "value": veh["q_end"], "rtol": 2e-4,
         "note": "the car has covered the distance of the speed profile"},
        {"kind": "max_abs_le", "signal": "Lsm/p.e", "value": veh["F_max"] * (1 + 1e-9), "note": "LSM thrust limit"},
        {"kind": "max_abs_le", "signal": "ModF/Ctl/v", "value": v2["V_max"] * (1 + 1e-9), "note": "chopper rail"},
        {"kind": "max_abs_le", "signal": "ModR/Ctl/v", "value": v2["V_max"] * (1 + 1e-9)},
        {"kind": "max_abs_le", "signal": "ModF/EM/i", "value": 600.0, "note": "coil current within twice the trim current of a 2-chassis module (estimate)"},
        {"kind": "min_ge", "signal": "ModF/Gap/y", "from_t": 2.0, "value": 8.0e-3,
         "note": "the gap stays above 8 mm once the car has lifted off (never near the 4 mm touch-down stop)"},
        {"kind": "min_ge", "signal": "ModR/Gap/y", "from_t": 2.0, "value": 8.0e-3},
        {"kind": "max_abs_le", "signal": "ModF/Gap/y", "from_t": 2.0, "value": 1.2e-2},
        {"kind": "max_abs", "signal": "ModF/Skid/a.e", "from_t": 2.0, "value": 0.0, "abs": 1e-6,
         "note": "the skids carry nothing during the whole run"},
        {"kind": "max_abs", "signal": "Free/py", "value": 0.0, "abs": 1e-9,
         "note": "lateral, roll and yaw motion are not excited: the symmetric 3D body only heaves, pitches and travels"},
        {"kind": "max_abs", "signal": "Free/qx", "value": 0.0, "abs": 1e-9},
        {"kind": "max_abs", "signal": "Free/qz", "value": 0.0, "abs": 1e-9},
        {"kind": "cursor_value", "signal": "Free/s", "t": veh["t_end"] - 0.05, "value": 1.0, "abs": 1e-6,
         "note": "the pose quaternion stays a unit quaternion"},
        {"kind": "compare_signals", "signal": "ModF/EM/h", "signal_b": "ModF/Gap/y", "max_abs": 1e-9,
         "note": "the field's gap state and the sensor integrate the same relative velocity"},
        {"kind": "max_abs_le", "signal": "AccZ/y", "from_t": 10.0, "value": 0.5,
         "note": "body acceleration below 0.5 m/s^2 over sag and bump (a ride-comfort bound: ISO 2631-1 puts 0.315 to "
                 "0.63 m/s^2 weighted rms at 'a little uncomfortable'; this is a peak bound on an unweighted signal)"},
        {"kind": "max_abs", "signal": "ModF/Err/y", "from_t": rv["t_bump"] - 0.5, "to_t": rv["t_bump"] + 3.0,
         "value": rv["bump_gap_dev_max_front"], "rtol": 0.15,
         "note": "peak front gap deviation while the car crosses the bump (scipy planar simulation of the same car, sampled "
                 "every 5 ms; bgsim records about every 18 ms, so its sampled peak of this 30 ms feature is up to 10 % lower)"},
        {"kind": "max_abs", "signal": "ModR/Err/y", "from_t": rv["t_bump"] - 0.5, "to_t": rv["t_bump"] + 3.0,
         "value": rv["bump_gap_dev_max_rear"], "rtol": 0.15},
        {"kind": "max_abs", "signal": "Free/qy", "from_t": rv["t_bump"] - 0.5, "to_t": rv["t_bump"] + 3.0,
         "value": rv["bump_pitch_max"], "rtol": 0.05,
         "note": "peak pitch (q_y = theta/2) while crossing the bump (scipy)"},
    ]
    for smp in rv["samples"]:
        t = smp["t"]
        vehicle.append({"kind": "cursor_value", "signal": "Free/px", "t": t, "value": smp["px"], "abs": 0.01,
                        "note": "scipy planar simulation of the same car (heave, pitch, two modules, LSM, guideway)"})
        vehicle.append({"kind": "cursor_value", "signal": "Speed/y", "t": t, "value": smp["v"], "abs": 1e-3})
        vehicle.append({"kind": "cursor_value", "signal": "ModF/Gap/y", "t": t, "value": smp["h_f"], "abs": tol_gap})
        vehicle.append({"kind": "cursor_value", "signal": "ModR/Gap/y", "t": t, "value": smp["h_r"], "abs": tol_gap})
        vehicle.append({"kind": "cursor_value", "signal": "ModF/EM/i", "t": t, "value": smp["i_f"], "rtol": tol_i, "abs": 0.01,
                        "note": "linear interpolation between the recorded samples is part of the tolerance"})
        vehicle.append({"kind": "cursor_value", "signal": "Free/pz", "t": t, "value": smp["pz"], "abs": 1e-5})
        vehicle.append({"kind": "cursor_value", "signal": "Free/qy", "t": t, "value": smp["qy"], "abs": 1e-6})

    return {
        "project": "maglev-train",
        "description": "EMS maglev train. Analytic trim and weight balance, the open-loop pole from the linearisation, "
                       "and nonlinear scipy simulations of the same equations (design/design.py) are the references; "
                       "no published test data of a Transrapid levitation loop could be found to compare with.",
        "models": {
            "maglev-module": {"checks": module},
            "maglev-module-open-loop": {"checks": open_loop},
            "maglev-vehicle": {"checks": vehicle},
        },
    }


def main() -> None:
    write(EXAMPLE / "library" / "LevitationModule.bgsub.json", json.dumps(module_definition(), indent=2) + "\n")
    for doc in (model_module(), model_open_loop(), model_vehicle()):
        write(EXAMPLE / "models" / f"{doc['name']}.bgmodel.json", json.dumps(doc, indent=2) + "\n")
    write(EXAMPLE / "expected.json", json.dumps(expected(), indent=2) + "\n")
    write(EXAMPLE / "scenes" / "maglev-module.sdf", scene_module(DESIGN["module"]))
    write(EXAMPLE / "scenes" / "maglev-train.sdf", scene_train(DESIGN["vehicle"], DESIGN["veh"]))


if __name__ == "__main__":
    main()
