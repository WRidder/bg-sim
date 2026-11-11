# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the rocket models, scenes and expected.json from design/data.py and design/design.json.

    uv run examples/rocket/design/design.py        # reference numbers (once, or after a data change)
    uv run examples/rocket/design/build_model.py   # models/*.bgmodel.json, scenes/*.sdf, expected.json

Both vehicles are the same 3D bond graph: a `Free3D` joint from the ground to the vehicle's
1-junction `Body`, on which sit the modulated inertia `Inertia` (project `VariableInertia3D`), the
gyroscopic `Coriolis`, the twist tap `Twist` and three wrench sources (thrust, gravity, drag). The
mass leaving the vehicle (propellant and jettisoned stages) takes its momentum with it through six
`MR` elements on the joint's drive axes (a 1-junction per drive port), modulated by `Seq` (`FlightSequence`).
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
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
TAU_JET = 0.2
QV = (math.cos(math.radians(-45.0)), 0.0, math.sin(math.radians(-45.0)), 0.0)   # body x up: -90 deg about y


def fmt(x: float) -> str:
    return repr(float(x))


def vec(xs) -> str:
    return "[" + ", ".join(fmt(x) if not isinstance(x, str) else x for x in xs) + "]"


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.ann: list[dict] = []

    def node(self, name, ref, x, y, params=None, starts=None, constants=None) -> str:
        nid = f"n{len(self.nodes) + 1:02d}"
        block = {"junction": ref[9:]} if ref.startswith("junction:") else {"ref": ref}
        self.nodes.append({
            "id": nid, "name": name, "block": block, "position": {"x": x, "y": y},
            "rotation": 0, "flipX": False,
            "params": {k: (v if isinstance(v, str) else fmt(v)) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: (v if isinstance(v, str) else fmt(v)) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        return nid

    def bond(self, a, ap, b, bp):
        c = {"id": f"b{len(self.conns) + 1:03d}", "kind": "bond", "from": {"node": a}, "to": {"node": b},
             "route": [], "label": None}
        if ap:
            c["from"]["port"] = ap
        if bp:
            c["to"]["port"] = bp
        self.conns.append(c)

    def sig(self, a, ap, b, bp, label=None):
        self.conns.append({"id": f"s{len(self.conns) + 1:03d}", "kind": "signal", "from": {"node": a, "port": ap},
                           "to": {"node": b, "port": bp}, "route": [], "label": label})

    def note(self, text, x, y, w=420, h=60):
        self.ann.append({"id": f"a{len(self.ann) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h})


def glob(name, value, unit, description):
    return {"name": name, "value": str(value), "unit": unit, "description": description}


def vehicle(dg: Diagram, *, m0: str, v0: str, seq_params: dict, seq_consts: dict, drag_tab: tuple, S: str,
            omega: str, tvc: dict | None) -> dict:
    """The shared bond graph and signal chain. Returns the node ids."""
    n = {}
    atm = d.atmosphere_table()
    # ---------------------------------------------------------------- bond graph (3D, multibond)
    n["World"] = dg.node("World", "stdlib:multibond/GroundSpatial", 40, 300)
    n["Free"] = dg.node("Free", "stdlib:spatial/Free3D", 240, 300, starts={"qw": QV[0], "qy": QV[2]})
    n["Body"] = dg.node("Body", "junction:1", 520, 300)
    n["Inertia"] = dg.node("Inertia", "project:VariableInertia3D", 760, 180,
                           starts={"P": f"[0.0, 0.0, 0.0, 0.0, 0.0, -({m0})*({v0})]"})
    n["Coriolis"] = dg.node("Coriolis", "stdlib:multibond/CoriolisSpatial", 760, 280)
    n["Twist"] = dg.node("Twist", "stdlib:multibond/DfSpatial", 760, 380)
    n["ThrustW"] = dg.node("ThrustW", "stdlib:multibond/ExternalWrenchSpatial", 520, 520)
    n["GravityW"] = dg.node("GravityW", "stdlib:multibond/ExternalWrenchSpatial", 660, 560)
    n["DragW"] = dg.node("DragW", "stdlib:multibond/ExternalWrenchSpatial", 800, 520)
    dg.bond(n["World"], "p", n["Free"], "parent")
    dg.bond(n["Free"], "child", n["Body"], None)
    for k in ("Inertia", "Coriolis", "Twist"):
        dg.bond(n["Body"], None, n[k], "p")
    for k in ("ThrustW", "GravityW", "DragW"):
        dg.bond(n[k], "p", n["Body"], None)
    dg.sig(n["Inertia"], "Pm", n["Coriolis"], "P", "momentum")
    # the momentum that leaves with the exhaust and the dropped stages: MR on each joint drive axis
    # (a 1-junction per drive port: a drive and an MR are both `in`)
    outs = []
    for k in range(1, 7):
        axis = dg.node(f"Axis{k}", "junction:1", 120, 440 + 60 * k)
        nid = dg.node(f"Out{k}", "stdlib:bondgraph/MR", 240, 440 + 60 * k)
        dg.bond(axis, None, n["Free"], f"drive{k}")
        dg.bond(axis, None, nid, "p")
        outs.append(nid)
    dg.note("Body: 1-junction of the vehicle. Inertia = modulated spatial I (m(t), J(t)); "
            "Out1..6 = MR on the joint's drive axes (1-junctions Axis1..6), r = -dm/dt and -dJ/dt: the leaving mass takes its momentum with it.", 400, 80, 520, 60)

    # ---------------------------------------------------------------- mass budget and engines
    n["Seq"] = dg.node("Seq", "project:FlightSequence", 40, 820, params=seq_params, constants=seq_consts)
    dg.sig(n["Seq"], "m", n["Inertia"], "m")
    dg.sig(n["Seq"], "J", n["Inertia"], "J")
    for k, port in enumerate(("r_ang1", "r_ang2", "r_ang3", "r_lin", "r_lin", "r_lin")):
        dg.sig(n["Seq"], port, outs[k], "u")
    n["Air"] = dg.node("Air", "project:AirData3D", 1000, 300, params={"R": d.RE, "omega": omega})
    dg.sig(n["Free"], "pose", n["Air"], "g", "pose")
    dg.sig(n["Twist"], "y", n["Air"], "V", "twist")
    n["Atm"] = dg.node("Atm", "project:Atmosphere1976", 1000, 460, constants={"N": len(atm["h"])},
                       params={"h_tab": vec(atm["h"]), "T_tab": vec(atm["T"]), "lnp_tab": vec(atm["lnp"]),
                               "lnrho_tab": vec(atm["lnrho"]), "scale": "ambient_scale"})
    dg.sig(n["Air"], "h", n["Atm"], "h")
    n["Engine"] = dg.node("Engine", "project:RocketEngine3D", 280, 820)
    for port in ("mdot", "c", "ae", "l"):
        dg.sig(n["Seq"], port, n["Engine"], port)
    dg.sig(n["Atm"], "p", n["Engine"], "pa")
    for port in ("tx", "ty", "tz", "fx", "fy", "fz"):
        dg.sig(n["Engine"], port, n["ThrustW"], port)
    n["Gravity"] = dg.node("Gravity", "project:CentralGravity3D", 520, 700,
                           params={"mu": d.MU, "R": d.RE, "scale": "gravity_scale"})
    dg.sig(n["Free"], "pose", n["Gravity"], "g")
    dg.sig(n["Seq"], "m", n["Gravity"], "m")
    for port in ("tx", "ty", "tz", "fx", "fy", "fz"):
        dg.sig(n["Gravity"], port, n["GravityW"], port)
    n["Drag"] = dg.node("Drag", "project:AxialDrag3D", 1000, 600, constants={"N": len(drag_tab[0])},
                        params={"S": S, "mach_tab": vec(drag_tab[0]), "cd_tab": vec(drag_tab[1]), "scale": "drag_scale"})
    dg.sig(n["Air"], "va", n["Drag"], "va")
    dg.sig(n["Atm"], "rho", n["Drag"], "rho")
    dg.sig(n["Atm"], "a", n["Drag"], "a")
    for port in ("tx", "ty", "tz", "fx", "fy", "fz"):
        dg.sig(n["Drag"], port, n["DragW"], port)
    n["Status"] = dg.node("Status", "project:FlightStatus", 280, 1000)
    dg.sig(n["Seq"], "m", n["Status"], "m")
    dg.sig(n["Engine"], "T", n["Status"], "T")
    for a, b in (("fx", "fex"), ("fz", "fez")):
        dg.sig(n["Engine"], a, n["Status"], b)
    for a, b in (("fx", "fax"), ("fy", "fay"), ("fz", "faz")):
        dg.sig(n["Drag"], a, n["Status"], b)
    # ---------------------------------------------------------------- attitude
    if tvc is None:
        n["Gimbal"] = dg.node("Gimbal", "stdlib:sources/Constant", 40, 1000, params={"value": 0.0})
        dg.sig(n["Gimbal"], "y", n["Engine"], "delta")
    else:
        n["Clock"] = dg.node("Clock", "stdlib:sources/Time", 40, 1120)
        n["Pitch"] = dg.node("Pitch", "stdlib:continuous/Lookup1D", 200, 1120, constants={"N": len(tvc["t"])},
                             params={"x": vec(tvc["t"]), "table": vec(tvc["deg"])})
        n["AP"] = dg.node("AP", "project:PitchAutopilot", 420, 1120,
                          params={"wn": "ap_wn", "zeta": "ap_zeta", "delta_max": tvc["delta_max"]})
        dg.sig(n["Clock"], "y", n["Pitch"], "u")
        dg.sig(n["Pitch"], "y", n["AP"], "theta_cmd", "pitch program (deg)")
        dg.sig(n["Air"], "theta", n["AP"], "theta")
        dg.sig(n["Twist"], "y", n["AP"], "V")
        dg.sig(n["Seq"], "J", n["AP"], "J")
        dg.sig(n["Engine"], "T", n["AP"], "T")
        dg.sig(n["Seq"], "l", n["AP"], "l")
        dg.sig(n["AP"], "delta", n["Engine"], "delta")
    return n


def settings(t_end: float, points: int) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": 1e-8, "abstol": 1e-8, "max_step": None,
            "output": {"mode": "points", "points": points}, "event_limit": 100000}


# ============================================================================================ V-2
def v2_model() -> dict:
    dg = Diagram()
    seq = {
        "t_ph": "[0.0, t_burn]", "mdot_ph": "[mdot, 0.0]",
        "c_ph": "[T_vac_t * 1000 * g_n / mdot, T_vac_t * 1000 * g_n / mdot]",
        "ae_ph": "[(T_vac_t - T_sl_t) * 1000 * g_n / 101325, (T_vac_t - T_sl_t) * 1000 * g_n / 101325]",
        "tau": d.TAU_ENGINE, "t_j": "[1.0e9]", "dm_j": "[0.0]", "tau_j": TAU_JET,
        "rgp": vec([d.V2["rg_pitch"]] * 2), "rgr": vec([d.V2["rg_roll"]] * 2), "lg": vec([d.V2["l_gimbal"]] * 2),
    }
    starts = {"m_s": "m0", "mdot_s": "mdot", "rgp2": d.V2["rg_pitch"] ** 2, "rgr2": d.V2["rg_roll"] ** 2}
    n = vehicle(dg, m0="m0", v0="0.0", seq_params=seq, seq_consts={"np": 2, "nj": 1},
                drag_tab=(d.V2_CD_MACH, d.V2_CD), S=fmt(d.V2["S"]), omega="0.0", tvc=None)
    dg.nodes[[x["id"] for x in dg.nodes].index(n["Seq"])]["starts"] = {k: (v if isinstance(v, str) else fmt(v)) for k, v in starts.items()}
    view = dg.node("View", "project:RocketView", 1240, 300,
                   params={"T_ref": "[250000.0, 1.0, 1.0]", "t_on": "[0.0, 1.0e9, 1.0e9]", "t_off": "[1.0e9, 1.0e9, 1.0e9]"})
    dg.sig(n["Free"], "pose", view, "g")
    dg.sig(n["Engine"], "T", view, "T")
    dg.note("V-2 (A4), vertical launch: 12.5 t, 25 t sea-level thrust rising to 29 t in vacuum, 65 s burn. "
            "US76 atmosphere, Mach-dependent drag, inverse-square gravity over a round, non-rotating Earth.",
            40, 0, 900, 60)
    params = [
        glob("m0", d.V2["m0"], "kg", "Launch mass (V-2 rocket, Wikipedia: 12,500 kg)"),
        glob("mdot", d.V2["mdot"], "kg/s", "Propellant flow (55 kg/s alcohol + 68 kg/s LOX)"),
        glob("t_burn", d.V2["t_burn"], "s", "Burn time (up to 65 s)"),
        glob("T_sl_t", 25.0, "1", "Sea-level thrust in tonnes-force (25 t)"),
        glob("T_vac_t", 29.0, "1", "Vacuum thrust in tonnes-force (29 t)"),
        glob("drag_scale", 1.0, "1", "Drag multiplier (0: no drag)"),
        glob("gravity_scale", 1.0, "1", "Gravity multiplier (0: no gravity)"),
        glob("ambient_scale", 1.0, "1", "Atmosphere multiplier on p and rho (0: vacuum)"),
    ]
    plots = [
        {"id": "p1", "title": "Altitude (km)", "signals": ["Air/h_km"]},
        {"id": "p2", "title": "Speed (m/s) and ideal velocity gain (m/s)", "signals": ["Air/speed", "Status/dv"]},
        {"id": "p3", "title": "Thrust (N) and drag (N)", "signals": ["Engine/T", "Drag/D"]},
        {"id": "p4", "title": "Mass (kg)", "signals": ["Seq/m"]},
        {"id": "p5", "title": "Mach number and dynamic pressure (Pa)", "signals": ["Drag/mach", "Drag/qbar"]},
        {"id": "p6", "title": "Sensed acceleration (g)", "signals": ["Status/acc_g"]},
        {"id": "p7", "title": "Ambient pressure (Pa)", "signals": ["Atm/p"]},
    ]
    bindings = [
        {"target": "link:v2", "property": "pose", "signal": [f"View/gv[{k}]" for k in range(1, 8)]},
        {"target": "link:ground", "property": "pose", "signal": [f"View/ground[{k}]" for k in range(1, 8)]},
        {"target": "visual:plume", "property": "scale.z", "signal": "View/plume[1]", "gain": 1.0},
    ]
    dash = {"autoRerun": True, "cards": [
        text("d1", "V-2 vertical shot", "Change the burn time, the thrust or the launch mass and press **Run**. "
             "**Vacuum**: set drag, gravity and atmosphere to 0 and the burnout speed is Tsiolkovsky's "
             "c ln(m0/mf).", "2x1"),
        slider("d2", "Burn time", "t_burn", 40.0, 70.0, 1.0, 0, "s"),
        slider("d3", "Launch mass", "m0", 11000.0, 14000.0, 100.0, 0, "kg"),
        slider("d4", "Vacuum thrust (t)", "T_vac_t", 25.0, 33.0, 0.5, 1),
        slider("d5", "Drag multiplier", "drag_scale", 0.0, 2.0, 0.1, 1),
        slider("d6", "Gravity multiplier", "gravity_scale", 0.0, 1.0, 1.0, 0),
        slider("d7", "Atmosphere multiplier", "ambient_scale", 0.0, 1.0, 1.0, 0),
        value("d8", "Altitude", "Air/h_km", 1, "km"),
        value("d9", "Speed", "Air/speed", 0, "m/s"),
        value("d10", "Mach", "Drag/mach", 2, ""),
        plot("d11", "Altitude (km)", ["Air/h_km"], "2x2"),
        plot("d12", "Speed and ideal velocity gain (m/s)", ["Air/speed", "Status/dv"], "2x2"),
        plot("d13", "Dynamic pressure (Pa)", ["Drag/qbar"], "2x2"),
    ]}
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "rocket-v2",
        "$comment": "A V-2 (A4) launched vertically: a variable-mass 3D bond graph. Generated by design/build_model.py.",
        "diagram": {"nodes": dg.nodes, "connections": dg.conns, "subsystemPorts": [], "annotations": dg.ann},
        "settings": settings(400.0, 4001),
        "plots": plots, "scene": {"file": "scenes/rocket-v2.sdf"}, "bindings": bindings,
        "parameters": params, "dashboard": dash,
    }


# ======================================================================================= Saturn V
def saturn_model() -> dict:
    dg = Diagram()
    s = d.sv_schedule()
    ph = s["phases"]
    jt = s["jettisons"]
    cf = s["configs"]
    seq = {
        "t_ph": vec([p[0] for p in ph]), "mdot_ph": vec([p[1] for p in ph]),
        "c_ph": vec([p[2] for p in ph]), "ae_ph": vec([p[3] for p in ph]), "tau": d.TAU_ENGINE,
        "t_j": vec([j[0] for j in jt]), "dm_j": vec([j[1] for j in jt]), "tau_j": TAU_JET,
        "rgp": vec([c[1] for c in cf]), "rgr": vec([c[2] for c in cf]), "lg": vec([c[3] for c in cf]),
    }
    starts = {"m_s": s["m0"], "mdot_s": ph[0][1], "rgp2": cf[0][1] ** 2, "rgr2": cf[0][2] ** 2}
    pitch = {"t": DESIGN["pitch_t"],
             "deg": [f"90.0 - tilt * {90.0 - v!r}" for v in DESIGN["pitch_deg"]],
             "delta_max": d.SV_DELTA_MAX}
    n = vehicle(dg, m0=fmt(s["m0"]), v0=fmt(d.V0_PLANE), seq_params=seq,
                seq_consts={"np": len(ph), "nj": len(jt)}, drag_tab=(d.SV_CD_MACH, d.SV_CD), S=fmt(d.S_SV),
                omega=fmt(d.V0_PLANE / d.RE), tvc=pitch)
    dg.nodes[[x["id"] for x in dg.nodes].index(n["Seq"])]["starts"] = {k: fmt(v) for k, v in starts.items()}
    view = dg.node("View", "project:RocketView", 1240, 300,
                   params={"T_ref": vec([34.0e6, 5.0e6, 0.9e6]),
                           "t_on": vec([0.0, d.T_SII_START, d.T_SIVB_START]),
                           "t_off": vec([d.T_SEP1, d.T_SEP2, 1.0e9]),
                           "R": d.RE, "omega": fmt(d.V0_PLANE / d.RE)})
    dg.sig(n["Free"], "pose", view, "g")
    dg.sig(n["Engine"], "T", view, "T")
    for k, (name, t_sep, dv) in enumerate((("SpentSIC", d.T_SEP1, 8.0), ("SpentIS", d.T_IS, 2.0),
                                           ("SpentLET", d.T_LET, -40.0), ("SpentSII", d.T_SEP2, 5.0))):
        nid = dg.node(name, "project:SpentStage", 1240, 460 + 120 * k,
                      params={"t_sep": t_sep, "dv_sep": dv, "mu": d.MU, "R": d.RE})
        dg.sig(n["Free"], "pose", nid, "g")
        dg.sig(n["Twist"], "y", nid, "V")
    dg.note("Saturn V AS-506 (Apollo 11) to parking orbit: S-IC, S-II and the first S-IVB burn, staging as "
            "mass flows through the outflow MRs, pitch program flown by thrust vector control.", 40, 0, 900, 60)
    params = [
        glob("tilt", 1.0, "1", "Scale of the pitch program's tilt from the vertical (1: the fitted AS-506 program)"),
        glob("ap_wn", d.SV_WN, "rad/s", "Attitude loop natural frequency"),
        glob("ap_zeta", d.SV_ZETA, "1", "Attitude loop damping ratio"),
        glob("drag_scale", 1.0, "1", "Drag multiplier (0: no drag)"),
        glob("gravity_scale", 1.0, "1", "Gravity multiplier (0: no gravity)"),
        glob("ambient_scale", 1.0, "1", "Atmosphere multiplier on p and rho (0: vacuum)"),
    ]
    plots = [
        {"id": "p1", "title": "Altitude (km) and surface range (km)", "signals": ["Air/h_km", "Air/s_km"]},
        {"id": "p2", "title": "Space-fixed and Earth-fixed speed (m/s)", "signals": ["Air/speed", "Air/v_rel"]},
        {"id": "p3", "title": "Pitch: command, attitude and flight-path angle (deg)",
         "signals": ["Pitch/y", "Air/theta_deg", "Air/fpa_deg"]},
        {"id": "p4", "title": "Mass (kg)", "signals": ["Seq/m"]},
        {"id": "p5", "title": "Thrust (N)", "signals": ["Engine/T"]},
        {"id": "p6", "title": "Sensed acceleration (g)", "signals": ["Status/acc_g"]},
        {"id": "p7", "title": "Mach number", "signals": ["Drag/mach"]},
        {"id": "p8", "title": "Dynamic pressure (Pa)", "signals": ["Drag/qbar"]},
        {"id": "p9", "title": "Gimbal angle and attitude error (deg)", "signals": ["AP/delta_deg", "AP/err_deg"]},
        {"id": "p10", "title": "Distance of the jettisoned parts (m)",
         "signals": ["SpentSIC/dist", "SpentIS/dist", "SpentLET/dist", "SpentSII/dist"]},
        {"id": "p11", "title": "Trajectory: altitude (km) over surface range (km)", "signals": ["Air/h_km"], "x": "Air/s_km"},
    ]
    pose = lambda blk: [f"{blk}[{k}]" for k in range(1, 8)]  # noqa: E731
    bindings = [
        {"target": "link:upper", "property": "pose", "signal": pose("View/gv")},
        {"target": "link:sic", "property": "pose", "signal": pose("SpentSIC/pose")},
        {"target": "link:interstage", "property": "pose", "signal": pose("SpentIS/pose")},
        {"target": "link:let", "property": "pose", "signal": pose("SpentLET/pose")},
        {"target": "link:sii", "property": "pose", "signal": pose("SpentSII/pose")},
        {"target": "link:ground", "property": "pose", "signal": pose("View/ground")},
        {"target": "visual:plume_sic", "property": "scale.z", "signal": "View/plume[1]", "gain": 1.0},
        {"target": "visual:plume_sii", "property": "scale.z", "signal": "View/plume[2]", "gain": 1.0},
        {"target": "visual:plume_sivb", "property": "scale.z", "signal": "View/plume[3]", "gain": 1.0},
    ]
    dash = {"autoRerun": False, "cards": [
        text("d1", "Saturn V to orbit", "Apollo 11's ascent: S-IC, S-II and the first S-IVB burn to the 191 km parking "
             "orbit. Scale the **tilt** of the pitch program and press **Run** (about half a minute): a steeper "
             "or flatter ascent misses the orbit.", "2x1"),
        slider("d2", "Tilt of the pitch program", "tilt", 0.8, 1.2, 0.01, 2),
        slider("d3", "Drag multiplier", "drag_scale", 0.0, 3.0, 0.1, 1),
        slider("d4", "Attitude loop wn", "ap_wn", 0.3, 3.0, 0.1, 1, "rad/s"),
        value("d5", "Altitude", "Air/h_km", 1, "km"),
        value("d6", "Space-fixed speed", "Air/speed", 0, "m/s"),
        value("d7", "Flight-path angle", "Air/fpa_deg", 2, "deg"),
        value("d8", "Mass", "Seq/m", 0, "kg"),
        plot("d9", "Altitude and range (km)", ["Air/h_km", "Air/s_km"], "2x2"),
        plot("d10", "Speed (m/s)", ["Air/speed", "Air/v_rel"], "2x2"),
        plot("d11", "Sensed acceleration (g)", ["Status/acc_g"], "2x2"),
        plot("d12", "Pitch command, attitude, flight-path angle (deg)", ["Pitch/y", "Air/theta_deg", "Air/fpa_deg"], "2x2"),
    ]}
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "rocket-saturn-v",
        "$comment": "Saturn V AS-506 ascent to parking orbit: a variable-mass 3D bond graph with staging. Generated by design/build_model.py.",
        "diagram": {"nodes": dg.nodes, "connections": dg.conns, "subsystemPorts": [], "annotations": dg.ann},
        "settings": settings(712.0, 7121),
        "plots": plots, "scene": {"file": "scenes/rocket-saturn-v.sdf"}, "bindings": bindings,
        "parameters": params, "dashboard": dash,
    }


# ------------------------------------------------------------------------------------- dashboard
def slider(cid, title, param, lo, hi, step, decimals, unit=None, size="1x1"):
    o = {"min": lo, "max": hi, "step": step, "decimals": decimals}
    if unit:
        o["unit"] = unit
    return {"id": cid, "kind": "slider", "size": size, "title": title, "parameter": f"global:{param}", "options": o}


def text(cid, title, body, size="2x1"):
    return {"id": cid, "kind": "text", "size": size, "title": title, "options": {"markdown": True, "text": body}}


def value(cid, title, signal, decimals, unit):
    return {"id": cid, "kind": "value", "size": "1x1", "title": title, "signals": [signal],
            "options": {"decimals": decimals, "unit": unit, "sparkline": True}}


def plot(cid, title, signals, size="2x2"):
    return {"id": cid, "kind": "plot", "size": size, "title": title, "signals": signals}


# ------------------------------------------------------------------------------------- scenes
def _vis(name, geom, pose, rgba):
    x, y, z, r, p, yw = pose
    return (f'      <visual name="{name}">\n        <pose>{x:.5g} {y:.5g} {z:.5g} {r:.7g} {p:.7g} {yw:.7g}</pose>\n'
            f'        <geometry>{geom}</geometry>\n        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def _box(a, b, c):
    return f"<box><size>{a:.5g} {b:.5g} {c:.5g}</size></box>"


def _cyl(r, h):
    return f"<cylinder><radius>{r:.5g}</radius><length>{h:.5g}</length></cylinder>"


def _xcyl(name, r, x0, x1, rgba):
    """A cylinder along the link's x axis from x0 to x1."""
    return _vis(name, _cyl(r, x1 - x0), ((x0 + x1) / 2, 0, 0, 0, math.pi / 2, 0), rgba)


WHITE, BLACK, GREY, ORANGE = "0.93 0.93 0.92 1", "0.08 0.08 0.09 1", "0.55 0.56 0.58 1", "1.0 0.55 0.1 0.85"


def _ground(size, tower_h, tower_x) -> str:
    out = '    <link name="ground">\n      <pose>0 0 0 0 0 0</pose>\n'
    out += _vis("field", _box(size, size, 1.0), (0, 0, -0.5 - 3.0, 0, 0, 0), "0.36 0.45 0.33 1")
    out += _vis("pad", _box(tower_h * 0.6, tower_h * 0.6, 3.0), (0, 0, -1.5, 0, 0, 0), "0.6 0.6 0.6 1")
    if tower_h > 0:
        out += _vis("tower", _box(tower_h * 0.12, tower_h * 0.12, tower_h), (tower_x, 0, tower_h / 2, 0, 0, 0),
                    "0.7 0.2 0.15 1")
    out += "    </link>\n"
    return out


def v2_scene() -> str:
    r = d.V2["d"] / 2
    out = ['<?xml version="1.0"?>\n<!--\n  rocket-v2: the V-2 on a vertical launch. Generated by design/build_model.py.\n'
           '  Z-up, metres. The view keeps the rocket at the origin and moves the world (block RocketView): the\n'
           '  link "v2" turns with the vehicle attitude (its x axis is the rocket axis, nose at +x; the link origin\n'
           '  is the vehicle centre of mass drawn at the tail), the link "ground" (field and launch table) falls\n'
           '  away below. The plume visual stretches with the thrust (scale.z, 1 at 25 t).\n-->\n'
           '<sdf version="1.9">\n  <model name="rocket-v2">\n']
    out.append(_ground(300.0, 0.0, 0.0))
    out.append('    <link name="v2">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_xcyl("tail", r * 0.9, 0.0, 1.6, BLACK))
    out.append(_xcyl("body_low", r, 1.6, 6.0, WHITE))
    out.append(_xcyl("body_band", r * 1.01, 6.0, 7.2, BLACK))
    out.append(_xcyl("body_up", r, 7.2, 9.5, WHITE))
    out.append(_xcyl("nose1", r * 0.8, 9.5, 11.3, WHITE))
    out.append(_xcyl("nose2", r * 0.55, 11.3, 12.8, WHITE))
    out.append(_xcyl("nose3", r * 0.28, 12.8, 14.0, BLACK))
    for k in range(4):
        ang = k * math.pi / 2
        out.append(_vis(f"fin{k + 1}", _box(3.0, 0.08, 1.8),
                        (1.5, 1.3 * math.cos(ang), 1.3 * math.sin(ang), ang, 0, 0), BLACK if k % 2 else WHITE))
    out.append(_xcyl("nozzle", 0.37, -0.6, 0.0, GREY))
    out.append(_vis("plume", _cyl(0.45, 14.0), (-7.6, 0, 0, 0, math.pi / 2, 0), ORANGE))
    out.append("    </link>\n  </model>\n</sdf>\n")
    return "".join(out)


def saturn_scene() -> str:
    out = ['<?xml version="1.0"?>\n<!--\n  rocket-saturn-v: the Saturn V of Apollo 11. Generated by design/build_model.py.\n'
           '  Z-up, metres. The view keeps the vehicle at the origin and moves the world (block RocketView). Every\n'
           '  part that separates is its own link: "sic" (first stage), "interstage" (S-II aft interstage ring),\n'
           '  "let" (launch escape tower), "sii" (second stage with the S-II/S-IVB interstage); "upper" is the\n'
           '  S-IVB, instrument unit, adapter and Apollo spacecraft. Until its separation a part rides at its place\n'
           '  in the stack (the link poses equal the vehicle attitude, the visuals sit along the link x axis from\n'
           '  the S-IC base); after it the block SpentStage flies it ballistically. Approximate shapes, true\n'
           '  lengths and diameters within a few metres. The plumes stretch with the thrust of their stage.\n-->\n'
           '<sdf version="1.9">\n  <model name="rocket-saturn-v">\n']
    out.append(_ground(1500.0, 120.0, -25.0))
    R1, R3 = 5.03, 3.3
    out.append('    <link name="sic">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_xcyl("sic_body", R1, 0.0, 42.1, WHITE))
    out.append(_xcyl("sic_band1", R1 * 1.005, 6.0, 9.0, BLACK))
    out.append(_xcyl("sic_band2", R1 * 1.005, 33.0, 37.0, BLACK))
    for k in range(4):
        ang = math.pi / 4 + k * math.pi / 2
        out.append(_vis(f"sic_fin{k + 1}", _box(6.0, 0.3, 4.0),
                        (1.0, 6.2 * math.cos(ang), 6.2 * math.sin(ang), ang, 0, 0), BLACK))
    for k, (yy, zz) in enumerate(((0, 0), (3.0, 3.0), (-3.0, 3.0), (-3.0, -3.0), (3.0, -3.0))):
        out.append(_vis(f"f1_{k + 1}", _cyl(1.85, 5.8), (-2.9, yy, zz, 0, math.pi / 2, 0), BLACK))
    out.append(_vis("plume_sic", _cyl(7.5, 70.0), (-40.0, 0, 0, 0, math.pi / 2, 0), ORANGE))
    out.append("    </link>\n")
    out.append('    <link name="interstage">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_xcyl("is_ring", R1, 42.1, 47.6, "0.85 0.85 0.84 1"))
    out.append("    </link>\n")
    out.append('    <link name="sii">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_xcyl("sii_body", R1, 47.6, 67.0, WHITE))
    out.append(_xcyl("sii_band", R1 * 1.005, 64.0, 67.0, BLACK))
    out.append(_xcyl("sii_sivb_is", 4.2, 67.0, 72.0, WHITE))
    for k, (yy, zz) in enumerate(((0, 0), (2.6, 2.6), (-2.6, 2.6), (-2.6, -2.6), (2.6, -2.6))):
        out.append(_vis(f"j2_{k + 1}", _cyl(0.98, 3.4), (45.9, yy, zz, 0, math.pi / 2, 0), BLACK))
    out.append(_vis("plume_sii", _cyl(5.0, 40.0), (24.0, 0, 0, 0, math.pi / 2, 0), "0.75 0.8 1.0 0.6"))
    out.append("    </link>\n")
    out.append('    <link name="upper">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_xcyl("sivb_body", R3, 72.0, 88.0, WHITE))
    out.append(_xcyl("sivb_band", R3 * 1.01, 72.0, 75.0, BLACK))
    out.append(_xcyl("iu", R3, 88.0, 88.9, "0.75 0.75 0.75 1"))
    out.append(_xcyl("sla1", 3.0, 88.9, 93.0, WHITE))
    out.append(_xcyl("sla2", 2.4, 93.0, 97.4, WHITE))
    out.append(_xcyl("sm", 1.95, 97.4, 100.4, "0.8 0.82 0.85 1"))
    out.append(_xcyl("cm1", 1.7, 100.4, 101.6, "0.85 0.85 0.86 1"))
    out.append(_xcyl("cm2", 1.1, 101.6, 102.8, "0.85 0.85 0.86 1"))
    out.append(_xcyl("cm3", 0.5, 102.8, 103.6, "0.85 0.85 0.86 1"))
    out.append(_vis("j2_sivb", _cyl(0.98, 3.4), (70.3, 0, 0, 0, math.pi / 2, 0), BLACK))
    out.append(_vis("plume_sivb", _cyl(2.5, 25.0), (56.0, 0, 0, 0, math.pi / 2, 0), "0.75 0.8 1.0 0.6"))
    out.append("    </link>\n")
    out.append('    <link name="let">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_xcyl("let_cover", 1.75, 103.0, 103.7, "0.95 0.95 0.95 1"))
    out.append(_xcyl("let_tower", 0.6, 103.7, 107.6, "0.75 0.2 0.15 1"))
    out.append(_xcyl("let_motor", 0.33, 107.6, 113.0, "0.95 0.95 0.95 1"))
    out.append(_xcyl("let_tip", 0.15, 113.0, 113.6, "0.75 0.2 0.15 1"))
    out.append("    </link>\n  </model>\n</sdf>\n")
    return "".join(out)


# ------------------------------------------------------------------------------------ expected
NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206", "E901"],
           "note": "no derivative causality, no algebraic loop warning, no event storm and no solver failure"}


def cv(signal, t, value, note, rtol=None, abs_=None):
    c = {"kind": "cursor_value", "signal": signal, "t": float(t), "value": float(value), "note": note}
    if rtol is not None:
        c["rtol"] = rtol
    if abs_ is not None:
        c["abs"] = abs_
    return c


def expected() -> dict:
    ref2, vac2 = DESIGN["v2"], DESIGN["v2_vacuum"]
    v2 = [
        {"kind": "scene_bindings"}, NO_DIAG,
        cv("Air/speed", d.V2["t_burn"], ref2["v_burnout"], "burnout speed of the scipy reference "
           "(design/reference.py, the same equations integrated as a planar point mass with DOP853)", rtol=1e-4),
        cv("Air/h", d.V2["t_burn"], ref2["h_burnout"], "burnout altitude, scipy reference", rtol=1e-4),
        {"kind": "max_abs", "signal": "Air/h", "value": ref2["apogee"], "rtol": 1e-4,
         "note": "apogee of the scipy reference"},
        {"kind": "zero_crossing", "signal": "Air/fpa", "n": 1, "direction": "down", "value": ref2["t_apogee"],
         "abs": 0.2, "note": "time of apogee (the flight-path angle turns from +90 to -90 deg), scipy reference "
                             "on a 0.1 s output grid"},
        {"kind": "zero_crossing", "signal": "Drag/mach", "level": 1.0, "n": 1, "direction": "up",
         "value": ref2["mach1_t"], "abs": 0.02, "note": "Mach 1, scipy reference"},
        {"kind": "max_abs", "signal": "Drag/qbar", "from_t": 0.0, "to_t": 150.0, "value": ref2["maxq"], "rtol": 2e-3,
         "note": "max Q on the way up, scipy reference (0.1 s grid: the peak is sampled, hence 2e-3)"},
        cv("Seq/m", d.V2["t_burn"], ref2["m_burnout"], "mass at burnout: m0 - mdot t_burn = 4505 kg (the flow lag "
           "starts the decay only at t_burn)", rtol=1e-6),
        cv("Air/speed", d.V2["t_burn"], d.V2_PUB["v_burnout"], "PUBLISHED: burnout speed 'about 5,000 ft/s "
           "(1,500 m/s)' (Wikipedia, V-2 sounding rocket). Different payloads and loads flew; the model gives "
           f"{ref2['v_burnout']:.0f} m/s (5 % low). Loose tolerance 10 %.", rtol=0.10),
        {"kind": "max_abs", "signal": "Air/h", "value": d.V2_PUB["apogee_design"], "rtol": 0.15,
         "note": "PUBLISHED: White Sands design profile 'about 100 miles (160 km) high' (Wikipedia, V-2 sounding "
                 f"rocket). The model reaches {ref2['apogee'] / 1000:.1f} km (11 % low: the drag table and the "
                 "propellant load are estimates). Loose tolerance 15 %."},
        {"kind": "max_abs_le", "signal": "Air/h", "value": d.V2_PUB["apogee_max"],
         "note": "PUBLISHED: never above the 206 km maximum for a vertical launch (Wikipedia, V-2 rocket)"},
    ]
    v2_vacuum = [
        cv("Air/speed", vac2["t"], vac2["dv"], "TSIOLKOVSKY: without gravity, drag and atmosphere the speed is "
           f"c_vac ln(m0/mf) = {d.V2['c_vac']:.2f} m/s * ln(12500/{vac2['m_f']:.2f}) (mf includes the "
           "lagged thrust decay mdot tau). Exact: tests the variable-mass bond graph (MI + outflow MR).", rtol=1e-6),
        cv("Status/dv", vac2["t"], vac2["dv"], "ideal velocity gain = Tsiolkovsky in vacuum", rtol=1e-6),
        cv("Seq/m", vac2["t"], vac2["m_f"], "final mass m0 - mdot (t_burn + tau (1 - exp(-15/tau)))", rtol=1e-8),
    ]
    sv = DESIGN["saturn"]
    ev = d.SV_EVENTS
    svc = [{"kind": "scene_bindings"}, NO_DIAG]
    # --- against the scipy reference (same equations): tight
    for name, e in ev.items():
        r = sv["events"][name]
        svc.append(cv("Air/speed", e["t"], r["speed"], f"{name}: space-fixed speed, scipy reference", rtol=2e-4))
        svc.append(cv("Air/h", e["t"], r["h"], f"{name}: altitude, scipy reference", abs_=30.0))
        svc.append(cv("Seq/m", e["t"], r["m"], f"{name}: mass, scipy reference (the cutoffs sit on the events: 1e-4 allows the sampling of the flow step)", rtol=1e-4))
    svc.append({"kind": "zero_crossing", "signal": "Drag/mach", "level": 1.0, "n": 1, "direction": "up",
                "value": sv["mach1_t"], "abs": 0.05, "note": "Mach 1, scipy reference"})
    svc.append({"kind": "max_abs", "signal": "Drag/qbar", "from_t": 0.0, "to_t": 200.0, "value": sv["maxq"],
                "rtol": 2e-3, "note": "max Q, scipy reference (0.1 s grid)"})
    # --- against the AS-506 flight evaluation report (published): honest tolerances
    for name, e in ev.items():
        r = sv["events"][name]
        dv = (r["speed"] - e["v"]) / e["v"] * 100
        svc.append(cv("Air/speed", e["t"], e["v"], f"PUBLISHED (validation): {name} space-fixed velocity "
                      f"{e['v']} m/s, AS-506 report Table 4-2. Model {r['speed']:.1f} m/s ({dv:+.1f} %). Not fitted: "
                      "set by the thrust, flow and mass data. The planar model omits the 126 m/s cross-plane part "
                      "of the pad's eastward speed (0.1 % of the speed at S-IC CECO).", rtol=0.025))
        dh = (r["h"] - e["h"]) / 1000
        svc.append(cv("Air/h", e["t"], e["h"], f"PUBLISHED (fitted): {name} altitude {e['h'] / 1000} km, AS-506 "
                      f"Table 4-2. The pitch program is fitted to it (design.py). Model {dh:+.1f} km.", abs_=3000.0))
        svc.append(cv("Air/fpa_deg", e["t"], e["fpa"], f"PUBLISHED (fitted): {name} space-fixed flight-path angle "
                      f"{e['fpa']} deg, AS-506 Table 4-2; pitch program fitted. Model {r['fpa']:.2f} deg.", abs_=1.0))
        svc.append(cv("Air/s", e["t"], e["s"], f"PUBLISHED (fitted): {name} surface range {e['s'] / 1000} km, "
                      f"AS-506 Table 4-2; pitch program fitted. Model {r['s'] / 1000:.1f} km.", rtol=0.03))
    svc += [
        {"kind": "zero_crossing", "signal": "Drag/mach", "level": 1.0, "n": 1, "direction": "up",
         "value": d.SV_MACH1["t"], "abs": 3.0, "note": f"PUBLISHED (validation): Mach 1 at {d.SV_MACH1['t']} s, AS-506 "
         f"Table 4-1. Model {sv['mach1_t']:.1f} s. Depends on the S-IC thrust at low altitude and the altitude profile."},
        {"kind": "max_abs", "signal": "Drag/qbar", "from_t": 0.0, "to_t": 200.0, "value": d.SV_MAXQ["q"], "rtol": 0.15,
         "note": f"PUBLISHED (validation): max Q 3.52 N/cm^2 = 35.2 kPa at {d.SV_MAXQ['t']} s and 13.6 km, AS-506 "
         f"Table 4-1. Model {sv['maxq'] / 1000:.1f} kPa at {sv['maxq_t']:.1f} s. The report's Q is computed with "
         "the measured winds and the day's atmosphere; the model has the US76 standard and no wind. Tolerance 15 %."},
        cv("Status/acc", 161.5, d.SV_ACC_OECO, f"PUBLISHED (validation): S-IC maximum acceleration 38.61 m/s^2 at "
           f"161.7 s, AS-506 Table 4-1. Model {sv['acc_oeco']:.2f}. Thrust from the F-1 Isp (Table 5-1) and the "
           "mass history (Table 20-1).", rtol=0.02),
        cv("Status/acc", 460.5, d.SV_ACC_SII, f"PUBLISHED (validation): S-II maximum acceleration 17.84 m/s^2 at "
           f"460.70 s, AS-506 Table 4-1. Model {sv['acc_sii']:.2f}.", rtol=0.03),
        cv("Status/acc", 699.3, d.SV_ACC_SIVB, f"PUBLISHED (validation): S-IVB first burn maximum acceleration "
           f"6.73 m/s^2 at 699.41 s, AS-506 Table 4-1. Model {sv['acc_sivb']:.2f}.", rtol=0.03),
        cv("Seq/m", d.T_OECO, d.M_OECO, f"PUBLISHED (validation): mass at S-IC OECO 827,292 kg, AS-506 Table 20-1. "
           f"Model {sv['m_oeco']:.0f} kg.", rtol=0.005),
        cv("Seq/m", d.T_SII_OECO, d.M_SII_OECO, f"PUBLISHED (validation): mass at S-II OECO 213,888 kg, AS-506 "
           f"Table 20-3. Model {sv['m_sii_oeco']:.0f} kg: the S-II flow from the published thrust levels and "
           "specific impulse burns about 2 t more than the mass history shows.", rtol=0.02),
        cv("Seq/m", d.T_SIVB_ECO, d.M_SIVB_ECO, f"PUBLISHED (validation): mass at S-IVB first cutoff 135,182 kg, "
           f"AS-506 Table 20-5. Model {sv['m_sivb_eco']:.0f} kg (carries the S-II deficit: the drop at S-II/S-IVB "
           "separation is the published difference).", rtol=0.03),
        cv("Air/speed", d.T_INSERT, d.SV_V_INSERT, f"PUBLISHED (validation): insertion velocity 7793.1 m/s at "
           f"709.33 s, AS-506 Table 4-5. Model {sv['v_insert']:.1f} m/s.", rtol=0.01),
    ]
    sv_vac = DESIGN["saturn_vacuum"]
    s = d.sv_schedule()
    ph = s["phases"]
    tau = d.TAU_ENGINE
    m160 = (s["m0"] - ph[0][1] * d.T_CECO - ph[1][1] * (160.0 - d.T_CECO)
            - (ph[0][1] - ph[1][1]) * tau * (1.0 - math.exp(-(160.0 - d.T_CECO) / tau)))
    dv160 = d.F1_C_VAC * math.log(s["m0"] / m160)
    vac = [
        cv("Status/dv", 160.0, dv160, f"TSIOLKOVSKY (analytic): S-IC in vacuum, c_vac ln(m0/m(160 s)) = "
           f"{d.F1_C_VAC:.2f} m/s * ln({s['m0']:.0f}/{m160:.0f}); m(160 s) is the schedule's mass (flow steps "
           "with the first-order lag), no jettison before 160 s.", rtol=1e-6),
        cv("Seq/m", 160.0, m160, "S-IC mass at 160 s, analytic from the schedule", rtol=1e-8),
        cv("Status/dv", 460.0, sv_vac["dv_460"], "ideal velocity gain in vacuum through the S-II burn, scipy "
           "quadrature (piecewise Tsiolkovsky across the jettisons)", rtol=1e-5),
        cv("Status/dv", 699.0, sv_vac["dv_699"], "ideal velocity gain in vacuum through the S-IVB burn, scipy",
           rtol=1e-5),
    ]
    return {
        "project": "rocket",
        "description": "Variable-mass launch vehicles as 3D bond graphs: a V-2 vertical shot and the Saturn V AS-506 "
                       "ascent to parking orbit. Checks against an independent scipy integration (tight), Tsiolkovsky "
                       "(exact, in vacuum) and published data (V-2: Wikipedia; Saturn V: the AS-506 flight evaluation "
                       "report MPR-SAT-FE-69-9), with the tolerances and fitted quantities named in each note.",
        "models": {
            "rocket-v2": {"checks": v2},
            "rocket-v2-vacuum": {"model": "rocket-v2", "settings": {"t_end": 80.0, "output": {"points": 801}},
                                 "overrides": [{"target": "global:drag_scale", "value": 0.0},
                                               {"target": "global:gravity_scale", "value": 0.0},
                                               {"target": "global:ambient_scale", "value": 0.0}],
                                 "checks": v2_vacuum},
            "rocket-saturn-v": {"checks": svc, "run_timeout": 900},
            "rocket-saturn-v-vacuum": {"model": "rocket-saturn-v",
                                       "overrides": [{"target": "global:drag_scale", "value": 0.0},
                                                     {"target": "global:gravity_scale", "value": 0.0},
                                                     {"target": "global:ambient_scale", "value": 0.0}],
                                       "checks": vac, "run_timeout": 900},
        },
    }


def main() -> int:
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "scenes").mkdir(exist_ok=True)
    for model, scene, sdf in ((v2_model(), "rocket-v2", v2_scene()), (saturn_model(), "rocket-saturn-v", saturn_scene())):
        path = ROOT / "models" / f"{model['name']}.bgmodel.json"
        path.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path} ({len(model['diagram']['nodes'])} nodes)")
        (ROOT / "scenes" / f"{scene}.sdf").write_text(sdf, encoding="utf-8", newline="\n")
    (ROOT / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
