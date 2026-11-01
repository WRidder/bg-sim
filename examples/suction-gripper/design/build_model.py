# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Writes the models of the suction-gripper example (``models/*.bgmodel.json``).

One plant, several scenarios: every scenario is the same diagram with other values of the global
parameters (so the worker compiles the plant once and reuses it for every scenario), except
``separate-generators``, which gives every cup its own vacuum generator.

Run it with ``uv run examples/suction-gripper/design/build_model.py``.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import params as P  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
N_CUPS = len(P.CUPS)


def num(x: float) -> str:
    text = repr(float(x))
    return text[:-2] if text.endswith(".0") and "e" not in text else text


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.notes: list[dict] = []

    def node(self, name: str, ref: str, x: float, y: float, params: dict | None = None,
             starts: dict | None = None, rotation: int = 0, flip: bool = False) -> str:
        self.nodes.append({
            "id": name, "name": name, "block": {"ref": ref},
            "position": {"x": x, "y": y}, "rotation": rotation, "flipX": flip,
            "params": params or {}, "constants": {}, "starts": starts or {},
        })
        return name

    def junction(self, name: str, kind: str, x: float, y: float) -> str:
        self.nodes.append({"id": name, "name": name, "block": {"junction": kind},
                           "position": {"x": x, "y": y}, "rotation": 0, "flipX": False,
                           "params": {}, "constants": {}, "starts": {}})
        return name

    def conn(self, kind: str, a: str, pa: str, b: str, pb: str) -> None:
        src = {"node": a} if pa is None else {"node": a, "port": pa}
        dst = {"node": b} if pb is None else {"node": b, "port": pb}
        self.conns.append({"id": f"c{len(self.conns) + 1:03d}", "kind": kind, "from": src, "to": dst})

    def note(self, text: str, x: float, y: float, w: float, h: float, color: str = "yellow") -> None:
        self.notes.append({"id": f"note{len(self.notes) + 1}", "kind": "text", "text": text,
                           "x": x, "y": y, "w": w, "h": h, "color": color})


def globals_table(overrides: dict | None = None) -> list[dict]:
    """The global parameters (name, value expression, unit, description)."""
    m, c, s = P.MOTION, P.CUP, P.SUPPLY
    t_lift_dur = P.scurve_time(m["H_lift"], m["v_lift"], m["a_lift"], m["j_lift"])
    t_low_dur = P.scurve_time(m["H_lift"] + m["d_press"], m["v_lift"], m["a_lift"], m["j_lift"])
    load = P.PARCEL["m_p"] * P.G0 / 4.0
    rows = [
        # parcel
        ("m_p", num(P.PARCEL["m_p"]), "kg", "Parcel mass"),
        ("L_p", num(P.PARCEL["L_p"]), "m", "Parcel length (along the gripper x)"),
        ("W_p", num(P.PARCEL["W_p"]), "m", "Parcel width (along the gripper y)"),
        ("H_p", num(P.PARCEL["H_p"]), "m", "Parcel height"),
        ("cx", num(P.PARCEL["cx"]), "m", "Centre of mass offset from the box centre, x"),
        ("cy", num(P.PARCEL["cy"]), "m", "Centre of mass offset, y"),
        ("cz", num(P.PARCEL["cz"]), "m", "Centre of mass offset, z (up)"),
        ("perm", num(P.PERM["cardboard"]), "m/(s*Pa)", "Air permeance of the parcel (0 sealed, 4e-7 cardboard, 2e-6 porous)"),
        # cups
        ("px", num(P.PX), "m", "Half spacing of the outer cup columns (gripper x)"),
        ("py", num(P.PY), "m", "Half spacing of the cup rows (gripper y)"),
        ("L0", num(c["L0"]), "m", "Cup rest length (mount to lip)"),
        ("A_eff", num(c["A_eff"]), "m^2", "Effective suction area per cup"),
        ("D_lip", num(c["D_lip"]), "m", "Lip diameter"),
        ("k_ax", num(c["k_ax"]), "N/m", "Bellows axial stiffness"),
        ("d_ax", num(c["d_ax"]), "N*s/m", "Bellows axial damping"),
        ("k_lat", num(c["k_lat"]), "N/m", "Bellows lateral stiffness"),
        ("d_lat", num(c["d_lat"]), "N*s/m", "Bellows lateral damping"),
        ("k_tilt", num(c["k_tilt"]), "N*m/rad", "Bellows bending stiffness"),
        ("mu", num(c["mu"]), "1", "Lip friction coefficient"),
        ("V_cup", num(c["V_cup"]), "m^3", "Cup chamber volume"),
        ("A_lip0", num(c["A_lip0"]), "m^2", "Sealed-lip leak area per cup (surface roughness)"),
        ("A_edge", "0", "m^2", "Extra leak area of cup 1 (a cup over the parcel edge or a damaged lip)"),
        ("s_bot", num(c["s_bot"]), "m", "Bellows compression stroke before the folds bottom (estimate)"),
        ("k_bot", num(c["k_bot"]), "N/m", "Bottoming stiffness scale (estimate)"),
        ("n_bot", num(c["n_bot"]), "1", "Bottoming exponent"),
        ("x_bot", num(c["x_bot"]), "m", "Reference over-stroke of the bottoming law"),
        ("A_fold", num(c["A_fold"]), "m^2", "Folded bellows annulus: vacuum lift stroke A_fold*dp/k_ax (estimate)"),
        ("c_vac", num(c["c_vac"]), "1", "Lateral/tilt stiffness rise with vacuum, 1 + c_vac*dp/p_atm (estimate)"),
        ("c_ext", num(c["c_ext"]), "1", "Lateral/tilt stiffness fall with extension, exp(-c_ext*ext/L0) (estimate)"),
        # supply
        ("dp_max", num(s["dp_max"]), "Pa", "Generator maximum vacuum"),
        ("Q_max", num(s["Q_max"]), "m^3/s", "Generator maximum suction flow (free air)"),
        ("n_gen", num(s["n_gen"]), "1", "Generator curve exponent (1 ejector, 3 pump-like)"),
        ("V_man", num(s["V_man"]), "m^3", "Manifold volume"),
        ("A_line", num(s["A_line"]), "m^2", "Line area per cup"),
        ("r_rev", num(s["r_rev"]), "1", "Reverse area fraction of the cup line (1 = no check valve)"),
        ("dp_close", num(s["dp_close"]), "Pa", "Closing pressure drop of the per-cup flow valves (1e9 = none)"),
        # motion
        ("L_move", num(m["L_move"]), "m", "Transfer length"),
        ("H_lift", num(m["H_lift"]), "m", "Lift height"),
        ("T_move", num(m["T_move"]), "s", "Transfer time"),
        ("kind", num(m["kind"]), "1", "Transfer profile: 1 trapezoidal, 2 S-curve, 3 polynomial 3-4-5, 4 cycloidal"),
        ("lam", num(m["lam"]), "1", "S-curve jerk phase / acceleration phase (0 < lam <= 0.5)"),
        ("psi_deg", "0", "deg", "Yaw of the cup pattern relative to the path"),
        ("k_tilt_g", num(m["k_tilt"]), "1", "Tilt gain (0 = level, 1 = cup axes along the specific force)"),
        ("th_max_deg", num(math.degrees(m["th_max"])), "deg", "Largest gripper tilt"),
        ("w_tilt", num(m["w_tilt"]), "rad/s", "Bandwidth of the tilt servo"),
        ("t_lead", "2/w_tilt", "s", "Preview of the tilt command (the servo lag)"),
        ("t_lift", num(m["t_lift"]), "s", "Lift start (the vacuum is switched on at t = 0)"),
        ("t_x0", num(m["t_lift"] + t_lift_dur + m["dwell"]), "s", "Transfer start"),
        ("t_low", f"t_x0 + T_move + {num(m['dwell'])}", "s", "Lower start"),
        ("t_rel", f"t_low + {num(t_low_dur + 0.1)}", "s", "Vacuum off (release)"),
        ("t_ret", "t_rel + 0.15", "s", "Retract start"),
        # derived
        ("z0", f"H_p/2 + cz - {num(P.rest_penetration(load))}", "m", "Start height of the parcel centre of mass (resting on the table)"),
        ("tcp_z", "-(L0 + H_p/2) + cz", "m", "TCP (parcel centre of mass) z in the gripper frame"),
        ("Jx", "m_p*(W_p^2 + H_p^2)/12", "kg*m^2", "Parcel inertia about x"),
        ("Jy", "m_p*(L_p^2 + H_p^2)/12", "kg*m^2", "Parcel inertia about y"),
        ("Jz", "m_p*(L_p^2 + W_p^2)/12", "kg*m^2", "Parcel inertia about z"),
        ("v_tr", "1.5*L_move/T_move", "m/s", "Trapezoid / S-curve cruise velocity"),
        ("a_tr", "4.5*L_move/T_move^2", "m/s^2", "Trapezoid acceleration"),
        ("a_sc", "v_tr/((1 - lam)*T_move/3)", "m/s^2", "S-curve peak acceleration"),
        ("j_sc", "a_sc/(lam*T_move/3)", "m/s^3", "S-curve jerk"),
    ]
    overrides = overrides or {}
    out = []
    for name, value, unit, desc in rows:
        out.append({"name": name, "value": str(overrides.get(name, value)), "unit": unit,
                    "description": desc})
    unknown = set(overrides) - {r[0] for r in rows}
    if unknown:
        raise KeyError(f"unknown globals {sorted(unknown)}")
    return out


def build(variant: str = "manifold") -> dict:
    d = Diagram()
    m = P.MOTION
    # ---------------------------------------------------------------- motion (left column)
    sc = "stdlib:motion/SCurveProfile"
    lift = dict(q_start="0", v_max=num(m["v_lift"]), a_max=num(m["a_lift"]), j_max=num(m["j_lift"]))
    d.node("Lift", sc, 60, 60, {**lift, "q_end": "H_lift", "t_start": "t_lift"})
    d.node("Lower", sc, 60, 180, {**lift, "q_end": f"-(H_lift + {num(m['d_press'])})", "t_start": "t_low"})
    d.node("Retract", sc, 60, 300, {**lift, "q_end": f"{num(m['H_ret'] + m['d_press'])}", "t_start": "t_ret"})
    d.node("Trap", "stdlib:motion/TrapezoidalProfile", 60, 440,
           {"q_start": "0", "q_end": "L_move", "t_start": "t_x0", "v_max": "v_tr", "a_max": "a_tr"})
    d.node("SCurve", sc, 60, 560,
           {"q_start": "0", "q_end": "L_move", "t_start": "t_x0", "v_max": "v_tr", "a_max": "a_sc", "j_max": "j_sc"})
    d.node("Poly", "stdlib:motion/PolynomialProfile", 60, 680,
           {"q_start": "0", "q_end": "L_move", "t_start": "t_x0", "duration": "T_move"})
    d.node("Cyclo", "stdlib:motion/CycloidalProfile", 60, 800,
           {"q_start": "0", "q_end": "L_move", "t_start": "t_x0", "duration": "T_move"})
    d.node("Profile", "project:ProfileSelect", 260, 600, {"kind": "kind"})
    # the same four profiles started t_lead earlier: the previewed acceleration for the tilt
    pv = {"q_start": "0", "q_end": "L_move", "t_start": "t_x0 - t_lead"}
    d.node("PvTrap", "stdlib:motion/TrapezoidalProfile", 60, 940, {**pv, "v_max": "v_tr", "a_max": "a_tr"})
    d.node("PvSCurve", sc, 60, 1060, {**pv, "v_max": "v_tr", "a_max": "a_sc", "j_max": "j_sc"})
    d.node("PvPoly", "stdlib:motion/PolynomialProfile", 60, 1180, {**pv, "duration": "T_move"})
    d.node("PvCyclo", "stdlib:motion/CycloidalProfile", 60, 1300, {**pv, "duration": "T_move"})
    d.node("Preview", "project:ProfileSelect", 260, 1100, {"kind": "kind"})
    for sel, prefix in (("Profile", ""), ("Preview", "Pv")):
        for i, src in enumerate(["Trap", "SCurve", "Poly", "Cyclo"], start=1):
            for o in ("q", "v", "a"):
                d.conn("signal", prefix + src, o, sel, f"{o}{i}")
            if i > 1:
                d.conn("signal", prefix + src, "jerk", sel, f"j{i}")
    d.node("Path", "project:GripperPath", 440, 300, {
        "x0": "0", "z0": "z0", "psi": "psi_deg*deg", "k_tilt": "k_tilt_g", "th_max": "th_max_deg*deg",
        "tx": "cx", "ty": "cy", "tz": "tcp_z", "g0": num(P.G0), "w_f": "w_tilt",
    })
    d.conn("signal", "Preview", "a", "Path", "ap")
    for o, i in (("q", "xq"), ("v", "xv"), ("a", "xa"), ("jerk", "xj")):
        d.conn("signal", "Profile", o, "Path", i)
    for k, src in enumerate(["Lift", "Lower", "Retract"], start=1):
        for o in ("q", "v", "a"):
            d.conn("signal", src, o, "Path", f"z{o}{k}")
    d.node("Grip", "stdlib:multibond/SfSpatial", 640, 300)
    d.junction("GJ", "1", 720, 400)
    d.conn("signal", "Path", "tw", "Grip", "u")
    d.conn("bond", "Grip", "p", "GJ", None)

    # ---------------------------------------------------------------- parcel (right)
    xp = 1340
    d.node("Parcel", "stdlib:spatial/RigidBody3D", xp, 420,
           {"m": "m_p", "J": "[Jx, Jy, Jz]", "g0": num(P.G0)},
           {"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
    d.node("Pose", "stdlib:multibond/PoseIntegrator3D", xp, 560, {},
           {"qw": "cos(psi_deg*deg/2)", "qx": "0", "qy": "0", "qz": "sin(psi_deg*deg/2)",
            "px": "0", "py": "0", "pz": "z0"})
    d.conn("signal", "Parcel", "V", "Pose", "tw")
    d.conn("signal", "Pose", "g", "Parcel", "g")
    # table contact under the four bottom corners
    d.node("Table", "stdlib:contact/ContactSurface", 1560, 980, {})
    fl = P.FLOOR
    corners = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    for k, (sx, sy) in enumerate(corners, start=1):
        cxe, cye, cze = f"{sx}*L_p/2 - cx", f"{sy}*W_p/2 - cy", "-H_p/2 - cz"
        y = 680 + 110 * (k - 1)
        d.node(f"FMount{k}", "stdlib:multibond/FixedTransform3DNeutral", 1560, y,
               {"x": f"-({cxe})", "y": f"-({cye})", "z": f"-({cze})"})
        d.node(f"FLocal{k}", "stdlib:spatial/LocalPose3D", 1700, y + 40, {"x": cxe, "y": cye, "z": cze})
        d.node(f"FPose{k}", "stdlib:multibond/ComposePose3D", 1840, y + 40)
        d.node(f"Floor{k}", "stdlib:contact/ContactPoint", 1980, y,
               {"k": num(fl["k"]), "xref": num(fl["xref"]), "c": num(fl["c"]), "mu": num(fl["mu"]), "vs": num(fl["vs"])})
        d.conn("bond", "Parcel", "p", f"FMount{k}", "b")
        d.conn("bond", f"FMount{k}", "a", f"Floor{k}", "p")
        d.conn("signal", "Pose", "g", f"FPose{k}", "gp")
        d.conn("signal", f"FLocal{k}", "g", f"FPose{k}", "gl")
        d.conn("signal", f"FPose{k}", "g", f"Floor{k}", "g")
        d.conn("signal", "Table", "o", f"Floor{k}", "o")
        d.conn("signal", "Table", "fr", f"Floor{k}", "fr")

    # ---------------------------------------------------------------- cups
    sx = {0: "-px", 1: "-px", 2: "0", 3: "0", 4: "px", 5: "px"}
    sy = {0: "py", 1: "-py", 2: "py", 3: "-py", 4: "py", 5: "-py"}
    cup_params = {
        "L0": "L0", "A_eff": "A_eff", "D_lip": "D_lip", "k_ax": "k_ax", "d_ax": "d_ax",
        "k_lat": "k_lat", "d_lat": "d_lat", "k_tilt": "k_tilt", "mu": "mu", "V": "V_cup",
        "perm": "perm", "A_lip0": "A_lip0",
        **{k: k for k in P.CUP_NL},
    }
    for i in range(N_CUPS):
        n = i + 1
        y = 80 + 140 * i
        xs, ys = sx[i], sy[i]
        d.node(f"GMount{n}", "stdlib:multibond/FixedTransform3DNeutral", 820, y,
               {"x": f"-({xs})", "y": f"-({ys})", "z": "0"})
        params = dict(cup_params)
        if n == 1:
            params["A_lip0"] = "A_lip0 + A_edge"
        d.node(f"Cup{n}", "stdlib:contact/SuctionCup", 980, y, params, {"rz": "-L0"})
        d.node(f"PMount{n}", "stdlib:multibond/FixedTransform3DNeutral", 1160, y,
               {"x": f"-({xs} - cx)", "y": f"-({ys} - cy)", "z": "-(H_p/2 - cz)"})
        d.conn("bond", "GJ", None, f"GMount{n}", "b")
        d.conn("bond", f"GMount{n}", "a", f"Cup{n}", "a")
        d.conn("bond", "Parcel", "p", f"PMount{n}", "b")
        d.conn("bond", f"PMount{n}", "a", f"Cup{n}", "b")

    # ---------------------------------------------------------------- vacuum supply
    valve = {"A_line": "A_line", "r_rev": "r_rev", "dp_close": "dp_close"}
    gen = {"dp_max": "dp_max", "Q_max": "Q_max", "n": "n_gen"}
    d.node("Valve", "stdlib:sources/Step", 600, 1000, {"t_step": "t_rel", "initial": "1", "final": "0"})
    if variant == "separate":
        for i in range(N_CUPS):
            n = i + 1
            x = 760 + 130 * i
            d.node(f"Gen{n}", "stdlib:contact/VacuumGenerator", x, 1150,
                   {**gen, "Q_max": f"Q_max/{N_CUPS}"})
            d.node(f"Man{n}", "stdlib:hydraulic/Volume", x, 1260,
                   {"V": f"V_man/{N_CUPS}", "beta": num(P.P_ATM)})
            d.node(f"Line{n}", "project:CupValve", x, 1040, valve)
            d.conn("signal", "Valve", "y", f"Gen{n}", "u")
            d.conn("wire", f"Gen{n}", "a", f"Man{n}", "a")
            d.conn("wire", f"Line{n}", "a", f"Man{n}", "a")
            d.conn("wire", f"Line{n}", "b", f"Cup{n}", "vac")
    else:
        d.node("Gen", "stdlib:contact/VacuumGenerator", 760, 1150, gen)
        d.node("Manifold", "stdlib:hydraulic/Volume", 980, 1260, {"V": "V_man", "beta": num(P.P_ATM)})
        d.conn("signal", "Valve", "y", "Gen", "u")
        d.conn("wire", "Gen", "a", "Manifold", "a")
        for i in range(N_CUPS):
            n = i + 1
            d.node(f"Line{n}", "project:CupValve", 760 + 130 * i, 1040, valve)
            d.conn("wire", f"Line{n}", "a", "Manifold", "a")
            d.conn("wire", f"Line{n}", "b", f"Cup{n}", "vac")

    # ---------------------------------------------------------------- monitor
    d.node("Monitor", "project:GripMonitor", 1340, 1120,
           {"tx": "cx", "ty": "cy", "tz": "tcp_z", "t_rel": "t_rel"})
    d.conn("signal", "Pose", "g", "Monitor", "gp")
    d.conn("signal", "Path", "g", "Monitor", "gg")
    for i in range(N_CUPS):
        d.conn("signal", f"Cup{i + 1}", "sealed", "Monitor", f"s{i + 1}")
    return {"diagram": d}


def model_document(name: str, comment: str, overrides: dict | None = None, variant: str = "manifold",
                   t_end: float | None = None) -> dict:
    built = build(variant)
    d: Diagram = built["diagram"]
    g = globals_table(overrides)
    gv = {row["name"]: row["value"] for row in g}
    if t_end is None:
        t_end = 3.6 + (float(gv["T_move"]) - 1.2)
    doc = {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": comment,
        "diagram": {"nodes": d.nodes, "connections": d.conns, "annotations": d.notes},
        "settings": {
            "t_start": 0.0, "t_end": round(t_end, 3), "solver": "FBDF", "reltol": 1e-6, "abstol": 1e-8,
            "max_step": None, "output": {"mode": "points", "points": int(round(t_end * 500)) + 1},
            "event_limit": 20000,
        },
        "parameters": g,
        "plots": plots() if variant != "separate" else
        [{**p, "signals": [x.replace("Gen/", "Gen1/") for x in p["signals"]]} for p in plots()],
        "scene": {"file": "scenes/suction-gripper.sdf"},
        "bindings": bindings(),
    }
    return doc


def plots() -> list[dict]:
    cups = range(1, N_CUPS + 1)
    return [
        {"id": "p1", "title": "Cup utilisation U (1 = pull-off, peel or slip)", "signals": [f"Cup{n}/U" for n in cups]},
        {"id": "p2", "title": "Axial cup force T and holding force Fcap [N]", "signals": [f"Cup{n}/T" for n in cups] + ["Cup1/Fcap", "Cup5/Fcap"]},
        {"id": "p3", "title": "Lateral (shear) cup force [N]", "signals": [f"Cup{n}/F_lat" for n in cups]},
        {"id": "p4", "title": "Vacuum level per cup [Pa]", "signals": [f"Cup{n}/dp" for n in cups] + ["Gen/dp"]},
        {"id": "p5", "title": "Air flows [m^3/s]: generator, lines, leaks", "signals": ["Gen/Q", "Line1/Q", "Line5/Q", "Cup1/Q_leak", "Cup1/Q_por", "Cup5/Q_leak"]},
        {"id": "p6", "title": "Lip lift h [m]", "signals": [f"Cup{n}/h" for n in cups]},
        {"id": "p7", "title": "Parcel sway relative to the gripper [rad]", "signals": ["Monitor/sway_x", "Monitor/sway_y", "Path/theta"]},
        {"id": "p8", "title": "Path acceleration [m/s^2] and jerk [m/s^3]", "signals": ["Path/ax", "Path/az", "Path/jerk"]},
        {"id": "p9", "title": "Grip status", "signals": ["Monitor/held", "Monitor/n_lost", "Monitor/sep"]},
    ]


def bindings() -> list[dict]:
    out = [
        {"target": "link:parcel", "property": "pose", "signal": [f"Pose/{c}" for c in ("qw", "qx", "qy", "qz", "px", "py", "pz")]},
        {"target": "link:gripper", "property": "pose", "signal": [f"Path/g[{k}]" for k in range(1, 8)]},
        {"target": "link:zaxis", "property": "pose", "signal": [f"Path/gfl[{k}]" for k in range(1, 8)]},
        {"target": "link:carriage", "property": "pose", "signal": [f"Path/gcar[{k}]" for k in range(1, 8)]},
    ]
    for n in range(1, N_CUPS + 1):
        out.append({"target": f"visual:bellows_{n}", "property": "color", "signal": f"Cup{n}/U",
                    "colormap": "coolwarm", "range": [0.0, 1.0]})
        out.append({"target": f"visual:lip_{n}", "property": "color", "signal": f"Cup{n}/dp",
                    "colormap": "viridis", "range": [0.0, 60000.0]})
    return out


def dashboard() -> dict:
    """Inputs: profile, move time, yaw, tilt, porosity, generator; outputs: holds, lost cups, U."""
    return {
        "autoRerun": False,
        "cards": [
            {"id": "umax", "kind": "plot", "size": "2x2", "title": "Cup utilisation U (1 = pull-off, peel or slip)",
             "signals": [f"Cup{n}/U" for n in range(1, N_CUPS + 1)]},
            {"id": "vac", "kind": "plot", "size": "2x2", "title": "Cup vacuum [Pa] and generator flow",
             "signals": ["Cup1/dp", "Cup5/dp", "Gen/dp"]},
            {"id": "held", "kind": "indicator", "size": "1x1", "title": "Parcel held", "signals": ["Monitor/held"],
             "options": {"threshold": 0.5, "onWhen": "above"}},
            {"id": "lost", "kind": "value", "size": "1x1", "title": "Cups lost", "signals": ["Monitor/n_lost"],
             "options": {"decimals": 0, "sparkline": True}},
            {"id": "kind", "kind": "slider", "size": "2x1", "title": "Profile: 1 trapezoid, 2 S-curve, 3 polynomial, 4 cycloidal",
             "parameter": "global:kind", "options": {"min": 1, "max": 4, "step": 1, "decimals": 0, "unit": ""}},
            {"id": "tmove", "kind": "slider", "size": "2x1", "title": "Transfer time", "parameter": "global:T_move",
             "options": {"min": 0.5, "max": 3.0, "step": 0.05, "decimals": 2, "unit": "s"}},
            {"id": "yaw", "kind": "slider", "size": "2x1", "title": "Yaw of the cup pattern", "parameter": "global:psi_deg",
             "options": {"min": 0, "max": 90, "step": 15, "decimals": 0, "unit": "deg"}},
            {"id": "tilt", "kind": "slider", "size": "2x1", "title": "Tilt gain (waiter's tray)", "parameter": "global:k_tilt_g",
             "options": {"min": 0, "max": 1, "step": 0.25, "decimals": 2, "unit": ""}},
            {"id": "u5", "kind": "gauge", "size": "2x2", "title": "Utilisation, front cup 5", "signals": ["Cup5/U"],
             "options": {"min": 0, "max": 1.2, "decimals": 2,
                         "zones": [{"from": 0, "to": 0.5, "tone": "good"}, {"from": 0.5, "to": 1.0, "tone": "warn"},
                                   {"from": 1.0, "to": 1.2, "tone": "bad"}]}},
            {"id": "perm", "kind": "slider", "size": "2x1", "title": "Parcel permeance (0 sealed, 4e-7 cardboard, 2e-6 porous)",
             "parameter": "global:perm", "options": {"min": 0, "max": 2.0e-6, "step": 1.0e-7, "unit": "m/(s*Pa)"}},
            {"id": "qmax", "kind": "slider", "size": "2x1", "title": "Generator flow Q_max (1e-3 = 60 l/min)",
             "parameter": "global:Q_max", "options": {"min": 2.0e-4, "max": 1.5e-3, "step": 5.0e-5, "unit": "m^3/s"}},
        ],
    }


#: name -> (comment, global overrides, variant)
SCENARIOS = {
    "transfer": ("Pick, lift, transfer (1 m in 1.75 s, S-curve) and place a 10 kg cardboard carton with a six-cup bellows "
                 "gripper: the shortest S-curve move in which every cup keeps a holding margin of 2 (U <= 0.5).", {}, "manifold"),
    "aggressive-trapezoid": ("The transfer in 0.74 s with a trapezoidal profile (8.2 m/s^2, infinite jerk): the step in "
                             "acceleration rings the bellows, the cups peel at the deceleration and the parcel drops.",
                             {"kind": "1", "T_move": "0.74"}, "manifold"),
    "aggressive-scurve": ("The same 0.74 s transfer with the S-curve: a higher peak acceleration (11.7 m/s^2) but a finite "
                          "jerk; no cup loses its seal and the parcel arrives.", {"kind": "2", "T_move": "0.74"}, "manifold"),
    "tilt-tray": ("A cycloidal transfer in 1.25 s (4.0 m/s^2) with the gripper tilted along the specific force (waiter's "
                  "tray, previewed tilt servo): U stays below 0.5, the same move held level reaches 0.62.",
                  {"kind": "4", "T_move": "1.25", "k_tilt_g": "1"}, "manifold"),
    "porous-undersized": ("A porous parcel (permeance 2e-6 m/(s*Pa)) on a 36 l/min generator: the leak through the material "
                          "holds the vacuum at 21.6 kPa, and a 1.1 s move (5.3 m/s^2) tears the parcel off; the 60 l/min "
                          "generator (29 kPa) carries it.",
                          {"perm": "2e-6", "Q_max": "6e-4", "T_move": "1.1"}, "manifold"),
    "edge-leak": ("Cup 1 sits over the parcel edge (20 mm^2 extra leak): through the common manifold the leak pulls every "
                  "cup down to 17 kPa and the parcel is lost at the lift.", {"A_edge": "2e-5"}, "manifold"),
    "edge-leak-valves": ("The same edge leak with per-cup flow valves (closing above 8 kPa line drop): the leaking cup is "
                         "shut off, the other five keep 49 kPa and carry the parcel.",
                         {"A_edge": "2e-5", "dp_close": "8000"}, "manifold"),
    "separate-generators": ("The same edge leak with one 10 l/min generator per cup: the leaking cup is lost, the five others "
                            "keep their own vacuum.", {"A_edge": "2e-5"}, "separate"),
}


NL = chr(10)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline=NL)


def main() -> None:
    import scene
    (ROOT / "scenes").mkdir(exist_ok=True)
    _write(ROOT / "scenes" / "suction-gripper.sdf", scene.scene_sdf())
    out_dir = ROOT / "models"
    out_dir.mkdir(exist_ok=True)
    for name, (comment, overrides, variant) in SCENARIOS.items():
        doc = model_document(name, comment, overrides, variant)
        if variant == "manifold":
            doc["dashboard"] = dashboard()
        out = out_dir / f"{name}.bgmodel.json"
        _write(out, json.dumps(doc, indent=2) + NL)
        print("wrote", out)
    proj = ROOT / "bgsim.project.json"
    pj = json.loads(proj.read_text(encoding="utf-8"))
    pj["models"] = list(SCENARIOS)
    _write(proj, json.dumps(pj, indent=2) + NL)


if __name__ == "__main__":
    main()
