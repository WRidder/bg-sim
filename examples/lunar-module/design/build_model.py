# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the lunar-module models, scenes and expected.json from design/data.py and design/design.json.

    uv run examples/lunar-module/design/design.py        # reference numbers (once, or after a data change)
    uv run examples/lunar-module/design/build_model.py   # models/*.bgmodel.json, scenes/*.sdf, expected.json

All three models share one 3D bond graph: a `Free3D` joint from the ground to the vehicle's
1-junction `Body`, on which sit the modulated inertia `Inertia` (project `VariableInertia3D`), the
gyroscopic `Coriolis`, the twist tap `Twist` and three wrench sources (engine, RCS torques,
gravity). The propellant leaving the vehicle takes its momentum with it through six `MR` elements
on the joint's drive ports, modulated by `Tank` (`PropellantTank`). The descent and hover models
add the landing gear: four `ContactPoint`s on the lunar sphere (`LunarSurface3D`), mounted at the
footpads through `FixedTransform3DNeutral`s.
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
DES = DESIGN["descent"]
ASC = DESIGN["ascent"]
G_SURF = d.MU / d.RM ** 2
C_DPS = d.DPS_ISP * d.G0
C_APS = d.APS_ISP * d.G0
M_EMPTY_DPS = d.M_PDI - d.PROP_PDI + d.PROP_UNUSABLE
M_EMPTY_APS = d.M_LIFTOFF - d.APS_PROP
Q_UP = (0.0, math.sqrt(0.5), 0.0, math.sqrt(0.5))   # body x up, body z downrange (windows forward)


def fmt(x: float) -> str:
    return repr(float(x))


def vec(xs) -> str:
    return "[" + ", ".join(fmt(x) if not isinstance(x, str) else x for x in xs) + "]"


def rotm(q):
    w, x, y, z = q
    s = w * w + x * x + y * y + z * z
    return [[(w * w + x * x - y * y - z * z) / s, 2 * (x * y - w * z) / s, 2 * (x * z + w * y) / s],
            [2 * (x * y + w * z) / s, (w * w - x * x + y * y - z * z) / s, 2 * (y * z - w * x) / s],
            [2 * (x * z - w * y) / s, 2 * (y * z + w * x) / s, (w * w - x * x - y * y + z * z) / s]]


def body_momentum(q, m, v):
    R = rotm(q)
    vb = [sum(R[k][i] * v[k] for k in range(3)) for i in range(3)]
    return [0.0, 0.0, 0.0] + [m * x for x in vb]


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.ann: list[dict] = []
        self.ids: dict[str, str] = {}

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
        self.ids[name] = nid
        return nid

    def bond(self, a, ap, b, bp):
        c = {"id": f"b{len(self.conns) + 1:03d}", "kind": "bond", "from": {"node": self.ids[a]},
             "to": {"node": self.ids[b]}, "route": [], "label": None}
        if ap:
            c["from"]["port"] = ap
        if bp:
            c["to"]["port"] = bp
        self.conns.append(c)

    def sig(self, a, ap, b, bp, label=None):
        self.conns.append({"id": f"s{len(self.conns) + 1:03d}", "kind": "signal",
                           "from": {"node": self.ids[a], "port": ap}, "to": {"node": self.ids[b], "port": bp},
                           "route": [], "label": label})

    def note(self, text, x, y, w=420, h=60):
        self.ann.append({"id": f"a{len(self.ann) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h})


def glob(name, value, unit, description):
    return {"name": name, "value": str(value), "unit": unit, "description": description}


WRENCH = ("tx", "ty", "tz", "fx", "fy", "fz")
PADS = [("Pad1", (-d.D_CG, d.TREAD, 0.0)), ("Pad2", (-d.D_CG, -d.TREAD, 0.0)),
        ("Pad3", (-d.D_CG, 0.0, d.TREAD)), ("Pad4", (-d.D_CG, 0.0, -d.TREAD))]


def vehicle(dg: Diagram, *, q0, p0, P0, tank: dict, engine_T0, c_eng, gear: bool) -> None:
    """The shared 3D bond graph (the variable-mass body) and its taps."""
    # ---------------------------------------------------------------- bond graph (3D, multibond)
    dg.node("World", "stdlib:multibond/GroundSpatial", 40, 300)
    dg.node("Free", "stdlib:spatial/Free3D", 240, 300,
            starts={"qw": q0[0], "qx": q0[1], "qy": q0[2], "qz": q0[3], "px": p0[0], "py": p0[1], "pz": p0[2]})
    dg.node("Body", "junction:1", 520, 300)
    dg.node("Inertia", "project:VariableInertia3D", 760, 160, starts={"P": vec(P0)})
    dg.node("Coriolis", "stdlib:multibond/CoriolisSpatial", 760, 250)
    dg.node("Twist", "stdlib:multibond/DfSpatial", 760, 340)
    dg.node("ThrustW", "stdlib:multibond/ExternalWrenchSpatial", 420, 520)
    dg.node("RcsW", "stdlib:multibond/ExternalWrenchSpatial", 560, 560)
    dg.node("GravityW", "stdlib:multibond/ExternalWrenchSpatial", 700, 520)
    dg.bond("World", "p", "Free", "parent")
    dg.bond("Body", None, "Free", "child")
    for k in ("Inertia", "Coriolis", "Twist", "ThrustW", "RcsW", "GravityW"):
        dg.bond("Body", None, k, "p")
    dg.sig("Inertia", "Pm", "Coriolis", "P", "momentum")
    for k in range(1, 7):
        dg.node(f"Out{k}", "stdlib:bondgraph/MR", 240, 420 + 60 * k)
        dg.bond("Free", f"drive{k}", f"Out{k}", "p")
    dg.note("Body: 1-junction of the lunar module. Inertia = modulated spatial I (m(t), J(m)); Out1..6 = MR, "
            "r = -dm/dt and -dJ/dt: the propellant that leaves takes its momentum with it.", 400, 60, 560, 60)
    # ---------------------------------------------------------------- mass, engine, gravity
    dg.node("Tank", "project:PropellantTank", 40, 860, params=tank["params"], starts={"m_s": tank["m0"]})
    dg.sig("Tank", "m", "Inertia", "m")
    dg.sig("Tank", "J", "Inertia", "J")
    for k, port in enumerate(("r_ang1", "r_ang2", "r_ang3", "r_lin", "r_lin", "r_lin")):
        dg.sig("Tank", port, f"Out{k + 1}", "u")
    dg.node("Engine", "project:Engine3D", 300, 860, params={"c": c_eng, "tau": tank["tau"]}, starts={"Tf": engine_T0})
    dg.sig("Engine", "mdot", "Tank", "mdot")
    for port in WRENCH:
        dg.sig("Engine", port, "ThrustW", port)
    dg.node("Gravity", "project:CentralGravity3D", 560, 700, params={"mu": d.MU, "R": d.RM, "scale": "gravity_scale"})
    dg.sig("Free", "pose", "Gravity", "g")
    dg.sig("Tank", "m", "Gravity", "m")
    for port in WRENCH:
        dg.sig("Gravity", port, "GravityW", port)
    dg.node("State", "project:LMState", 1000, 300, params={"R": d.RM, "d_cg": d.D_CG, "tread": d.TREAD})
    dg.sig("Free", "pose", "State", "g", "pose")
    dg.sig("Twist", "y", "State", "V", "twist")
    dg.node("Status", "project:PropulsionStatus", 560, 1000,
            params={"g_moon": G_SURF, "c": c_eng, "prop0": tank["prop0"]})
    dg.sig("Tank", "m", "Status", "m")
    dg.sig("Engine", "T", "Status", "T")
    dg.sig("Tank", "prop", "Status", "prop")
    # ---------------------------------------------------------------- attitude (RCS)
    dg.node("Att", "project:AttitudeControl", 820, 700,
            params={"wn": "att_wn", "zeta": d.ATT_ZETA, "tau_max": d.RCS_TORQUE})
    dg.sig("Free", "pose", "Att", "g")
    dg.sig("Twist", "y", "Att", "V")
    dg.sig("Tank", "J", "Att", "J")
    for port in WRENCH:
        dg.sig("Att", port, "RcsW", port)
    dg.node("View", "project:LMView", 1240, 300, params={"R": d.RM, "T_ref": d.DPS_FTP})
    dg.sig("Free", "pose", "View", "g")
    dg.sig("Engine", "T", "View", "T")
    if gear:
        landing_gear(dg)


def landing_gear(dg: Diagram) -> None:
    x0, y0 = 1000, 1200
    for k, (name, b) in enumerate(PADS):
        y = y0 + 150 * k
        dg.node(f"{name}At", "stdlib:spatial/LocalPose3D", x0, y, params={"x": b[0], "y": b[1], "z": b[2]})
        dg.node(f"{name}Pose", "stdlib:multibond/ComposePose3D", x0 + 180, y)
        dg.sig("Free", "pose", f"{name}Pose", "gp")
        dg.sig(f"{name}At", "g", f"{name}Pose", "gl")
        dg.node(f"{name}Surf", "project:LunarSurface3D", x0 + 360, y, params={"R": d.RM})
        dg.sig(f"{name}Pose", "g", f"{name}Surf", "g")
        dg.node(name, "stdlib:contact/ContactPoint", x0 + 540, y, params=d.GEAR_CONTACT)
        dg.sig(f"{name}Pose", "g", name, "g")
        dg.sig(f"{name}Surf", "o", name, "o")
        dg.sig(f"{name}Surf", "fr", name, "fr")
        dg.node(f"{name}Mount", "stdlib:multibond/FixedTransform3DNeutral", x0 + 720, y,
                params={"x": -b[0], "y": -b[1], "z": -b[2]})
        dg.bond(f"{name}Mount", "b", "Body", None)   # b at the from end: b.f = -twist (ContactPoint convention)
        dg.bond(f"{name}Mount", "a", name, "p")
    dg.note("Landing gear: four footpads (167.57 in from the X axis, TN D-6850), each a ContactPoint (Hunt-Crossley "
            "normal force for pad, strut and soil; Coulomb friction mu = 0.4) on the lunar sphere below it "
            "(LunarSurface3D), mounted at its pad through a FixedTransform3DNeutral.", x0, y0 - 100, 700, 60)


def settings(t_end: float, points: int, reltol=1e-8) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": reltol, "abstol": 1e-8, "max_step": None,
            "output": {"mode": "points", "points": points}, "event_limit": 100000}


def descent_tank() -> dict:
    return {"m0": d.M_PDI, "prop0": d.PROP_PDI - d.PROP_UNUSABLE, "tau": d.TAU_ENGINE,
            "params": {"m_a": d.M_PDI, "J_a": vec(d.J_PDI), "m_b": d.M_LANDING, "J_b": vec(d.J_LANDING),
                       "m_empty": M_EMPTY_DPS}}


def descent_guidance(dg: Diagram, *, t_hg, t_p66) -> None:
    t63, t64 = DES["tgt63"], DES["tgt64"]
    cfg = DESIGN["descent_cfg"]
    dg.node("Guid", "project:DescentGuidance", 1000, 560,
            params={"mu": d.MU, "R": d.RM, "gscale": "gravity_scale", "t_hg": t_hg, "t_p66": t_p66,
                    "r63": vec(t63["r"]), "v63": vec(t63["v"]), "a63": vec(t63["a"]), "T63": t63["T"],
                    "r64": vec(t64["r"]), "v64": vec(t64["v"]), "a64": vec(t64["a"]), "T64": cfg["t64_end"],
                    "tau_v": d.TAU_V, "tau_h": d.TAU_H, "ah_max": d.A_H_MAX})
    dg.sig("Free", "pose", "Guid", "g")
    dg.sig("Twist", "y", "Guid", "V")
    dg.sig("Tank", "m", "Guid", "m")
    dg.sig("Guid", "u", "Att", "u", "thrust direction")
    dg.node("Throttle", "project:DpsThrottle", 300, 700,
            params={"T_rated": d.DPS_RATED, "T_ftp": d.DPS_FTP, "lo": d.DPS_MIN, "hi": d.DPS_MAX,
                    "recover": d.DPS_RECOVER, "t_trim": d.T_TRIM if t_hg > 0 else -1.0},
            starts={"ftp": 1.0 if t_hg > 0 else 0.0})
    dg.sig("Guid", "T_req", "Throttle", "T_req")
    dg.sig("State", "h_pad", "Throttle", "h_pad")
    dg.sig("Tank", "prop", "Throttle", "prop")
    dg.sig("Throttle", "T_cmd", "Engine", "T_cmd")


# ===================================================================================== descent
def descent_model() -> dict:
    dg = Diagram()
    s = d.pdi_state(DESIGN["descent_cfg"]["range_pdi"])
    q0 = DES["q0"]
    vehicle(dg, q0=q0, p0=s["p"], P0=body_momentum(q0, d.M_PDI, s["v"]), tank=descent_tank(),
            engine_T0=d.DPS_MIN * d.DPS_RATED, c_eng=C_DPS, gear=True)
    descent_guidance(dg, t_hg=d.T_HG, t_p66=d.T_P66)
    # windows down -> up (the yaw manoeuvre about the thrust axis, MR table 5-I)
    dg.node("Clock", "stdlib:sources/Time", 40, 1120)
    dg.node("Windows", "stdlib:continuous/Lookup1D", 220, 1120, constants={"N": 2},
            params={"x": vec([d.T_YAW_START, d.T_YAW_END]), "table": vec([math.pi, 0.0])})
    dg.sig("Clock", "y", "Windows", "u")
    dg.sig("Windows", "y", "Att", "phi", "windows angle")
    # P66 pilot model from Aldrin's callouts: descent rate and forward speed over altitude
    dg.node("PilotRate", "stdlib:continuous/Lookup1D", 1240, 560, constants={"N": len(d.P66_H)},
            params={"x": vec(d.P66_H), "table": vec([f"{r!r} * 0.3048 * rate_scale" for r in d.P66_RATE])})
    dg.node("PilotFwd", "stdlib:continuous/Lookup1D", 1240, 660, constants={"N": len(d.P66_FWD_H)},
            params={"x": vec(d.P66_FWD_H), "table": vec([v * d.FT for v in d.P66_FWD])})
    dg.sig("State", "h_ft", "PilotRate", "u")
    dg.sig("State", "h_ft", "PilotFwd", "u")
    dg.sig("PilotRate", "y", "Guid", "rate_cmd", "descent rate")
    dg.sig("PilotFwd", "y", "Guid", "fwd_cmd", "forward speed")
    dg.note("Apollo 11 powered descent, PDI to touchdown: braking (P63) and approach (P64) on Apollo's quadratic "
            "guidance, the landing phase (P66) on a pilot model built from Aldrin's callouts; the descent engine's "
            "throttle logic (trim, fixed throttle position, throttle recovery at 57 %); RCS attitude control; "
            "touchdown on four footpads.", 40, -40, 960, 60)
    params = [
        glob("gravity_scale", 1.0, "1", "Gravity multiplier (guidance and dynamics)"),
        glob("rate_scale", 1.0, "1", "Scale on the P66 descent rates of the pilot model (1: Aldrin's callouts)"),
        glob("att_wn", d.ATT_WN, "rad/s", "Attitude loop natural frequency"),
    ]
    plots = [
        {"id": "p1", "title": "Altitude (ft)", "signals": ["State/h_ft"]},
        {"id": "p2", "title": "Horizontal and vertical velocity (ft/s)", "signals": ["State/vh_fps", "State/rdot_fps"]},
        {"id": "p3", "title": "Throttle (fraction of rated thrust)", "signals": ["Throttle/throttle"]},
        {"id": "p4", "title": "Mass (kg) and usable propellant (kg)", "signals": ["Tank/m", "Tank/prop"]},
        {"id": "p5", "title": "Tilt of the thrust axis from vertical (deg)", "signals": ["State/tilt_deg"]},
        {"id": "p6", "title": "Velocity gained (ft/s)", "signals": ["Status/dv_fps"]},
        {"id": "p7", "title": "Footpad loads (N)", "signals": ["Pad1/f_n", "Pad2/f_n", "Pad3/f_n", "Pad4/f_n"]},
        {"id": "p8", "title": "Trajectory: altitude (km) over range (km)", "signals": ["State/h_km"], "x": "State/s_km"},
        {"id": "p9", "title": "Hover time left (s)", "signals": ["Status/hover_left"]},
    ]
    dash = {"autoRerun": False, "cards": [
        text("d1", "Eagle, PDI to touchdown", "Apollo 11's powered descent from 15 km and 1,695 m/s to the Sea of "
             "Tranquility. Press **Run** (about a minute). Scale the descent rates of the landing phase and watch the "
             "propellant left at touchdown.", "2x1"),
        slider("d2", "P66 descent-rate scale", "rate_scale", 0.5, 2.0, 0.05, 2),
        slider("d3", "Attitude loop wn", "att_wn", 0.3, 2.0, 0.1, 1, "rad/s"),
        value("d4", "Altitude", "State/h_ft", 0, "ft"),
        value("d5", "Usable propellant", "Tank/prop", 0, "kg"),
        value("d6", "Hover time left", "Status/hover_left", 0, "s"),
        value("d7", "Throttle", "Throttle/throttle", 2, ""),
        plot("d8", "Altitude (ft)", ["State/h_ft"], "2x2"),
        plot("d9", "Velocity (ft/s)", ["State/vh_fps", "State/rdot_fps"], "2x2"),
        plot("d10", "Throttle", ["Throttle/throttle"], "2x2"),
    ]}
    return model_doc("lm-descent", "Apollo 11 lunar module powered descent, PDI to touchdown, on a variable-mass 3D "
                     "bond graph with landing gear. Generated by design/build_model.py.", dg, settings(775.0, 7751),
                     plots, "scenes/lm-descent.sdf", descent_bindings(), params, dash)


def descent_bindings():
    pose = lambda blk: [f"{blk}[{k}]" for k in range(1, 8)]  # noqa: E731
    return [
        {"target": "link:lm", "property": "pose", "signal": pose("View/gv")},
        {"target": "link:ground", "property": "pose", "signal": pose("View/ground")},
        {"target": "link:site", "property": "pose", "signal": pose("View/site")},
        {"target": "visual:plume", "property": "scale.z", "signal": "View/plume", "gain": 1.0},
    ]


# ====================================================================================== hover
def hover_model() -> dict:
    dg = Diagram()
    h0 = "h0_ft * 0.3048"
    m0 = f"{M_EMPTY_DPS!r} + prop_start"
    g_h0 = f"{d.MU!r} / (({d.RM!r} + {h0}) * ({d.RM!r} + {h0}))"
    tank = descent_tank()
    tank["m0"] = m0
    tank["prop0"] = "prop_start"
    vehicle(dg, q0=Q_UP, p0=[0.0, 0.0, h0], P0=[0.0] * 6, tank=tank, engine_T0=f"({m0}) * {g_h0}", c_eng=C_DPS,
            gear=True)
    descent_guidance(dg, t_hg=-2.0, t_p66=-1.0)
    dg.node("Windows", "stdlib:sources/Constant", 220, 1120, params={"value": 0.0})
    dg.sig("Windows", "y", "Att", "phi", "windows angle")
    dg.node("RateCmd", "stdlib:continuous/Lookup1D", 1240, 560, constants={"N": 3},
            params={"x": vec([d.H_REF / d.FT, 100.0, 1.0e5]), "table": "[td_fps * 0.3048, rod_fps * 0.3048, rod_fps * 0.3048]"})
    dg.node("Clock", "stdlib:sources/Time", 1060, 660)
    dg.node("FwdCmd", "stdlib:continuous/Lookup1D", 1240, 660, constants={"N": 3},
            params={"x": "[0.0, t_fwd, t_fwd + 4.0]", "table": "[fwd_fps * 0.3048, fwd_fps * 0.3048, 0.0]"})
    dg.sig("State", "h_ft", "RateCmd", "u")
    dg.sig("Clock", "y", "FwdCmd", "u")
    dg.sig("RateCmd", "y", "Guid", "rate_cmd", "descent rate")
    dg.sig("FwdCmd", "y", "Guid", "fwd_cmd", "forward speed")
    dg.note("Landing phase (P66, rate of descent) by hand: start in a hover, set the descent rate above and below "
            "100 ft and a forward translation on the dashboard, and land before the propellant runs out.",
            40, -40, 960, 60)
    params = [
        glob("h0_ft", 400.0, "1", "Start altitude in ft (the guidance reference, 6.4 ft above the pads)"),
        glob("prop_start", round(DES["samples"]["617"]["m"] - M_EMPTY_DPS, 1), "kg",
             "Usable propellant at the start (Apollo 11 at P66 entry, 102:43:22, from the descent model: about 1 t)"),
        glob("rod_fps", 3.5, "1", "Commanded descent rate above 100 ft, ft/s"),
        glob("td_fps", 1.7, "1", "Commanded descent rate at the pads' touchdown, ft/s (ramps from 100 ft)"),
        glob("fwd_fps", 20.0, "1", "Forward speed while translating, ft/s"),
        glob("t_fwd", 30.0, "s", "Translation time (then the forward speed is nulled)"),
        glob("gravity_scale", 1.0, "1", "Gravity multiplier"),
        glob("att_wn", d.ATT_WN, "rad/s", "Attitude loop natural frequency"),
    ]
    plots = [
        {"id": "p1", "title": "Altitude (ft)", "signals": ["State/h_ft"]},
        {"id": "p2", "title": "Vertical and horizontal velocity (ft/s)", "signals": ["State/rdot_fps", "State/vh_fps"]},
        {"id": "p3", "title": "Usable propellant (kg)", "signals": ["Tank/prop"]},
        {"id": "p4", "title": "Hover time left (s)", "signals": ["Status/hover_left"]},
        {"id": "p5", "title": "Footpad loads (N)", "signals": ["Pad1/f_n", "Pad2/f_n", "Pad3/f_n", "Pad4/f_n"]},
        {"id": "p6", "title": "Thrust-to-weight ratio", "signals": ["Status/tw"]},
    ]
    dash = {"autoRerun": True, "cards": [
        text("d1", "Land Eagle", "You have Armstrong's propellant at P66 entry. Set the **descent rate** and a "
             "**forward translation** (to clear the boulders), then watch the **hover time left**. Hover too long "
             "and the engine quits.", "2x1"),
        slider("d2", "Descent rate above 100 ft", "rod_fps", 0.0, 15.0, 0.5, 1, "ft/s"),
        slider("d3", "Descent rate at touchdown", "td_fps", 0.0, 6.0, 0.1, 1, "ft/s"),
        slider("d4", "Forward speed", "fwd_fps", 0.0, 60.0, 1.0, 0, "ft/s"),
        slider("d5", "Translation time", "t_fwd", 5.0, 120.0, 5.0, 0, "s"),
        slider("d6", "Usable propellant at the start", "prop_start", 100.0, 1500.0, 10.0, 0, "kg"),
        value("d7", "Altitude", "State/h_ft", 0, "ft"),
        value("d8", "Hover time left", "Status/hover_left", 0, "s"),
        value("d9", "Descent rate", "State/rdot_fps", 1, "ft/s"),
        plot("d10", "Altitude (ft)", ["State/h_ft"], "2x2"),
        plot("d11", "Hover time left (s)", ["Status/hover_left"], "2x2"),
        plot("d12", "Footpad loads (N)", ["Pad1/f_n", "Pad2/f_n", "Pad3/f_n", "Pad4/f_n"], "2x2"),
    ]}
    return model_doc("lm-hover", "The lunar module's landing phase (P66) flown from the dashboard: descent rate, "
                     "forward translation and the propellant margin. Generated by design/build_model.py.", dg,
                     settings(200.0, 2001), plots, "scenes/lm-descent.sdf", descent_bindings(), params, dash)


# ===================================================================================== ascent
def ascent_model() -> dict:
    dg = Diagram()
    tank = {"m0": d.M_LIFTOFF, "prop0": d.APS_PROP, "tau": d.TAU_APS,
            "params": {"m_a": d.M_LIFTOFF, "J_a": vec(d.J_LIFTOFF), "m_b": d.M_INSERTION, "J_b": vec(d.J_INSERTION),
                       "m_empty": M_EMPTY_APS}}
    vehicle(dg, q0=Q_UP, p0=[0.0, 0.0, d.H_ASC0], P0=[0.0] * 6, tank=tank, engine_T0=d.APS_THRUST, c_eng=C_APS,
            gear=False)
    dg.node("Guid", "project:AscentGuidance", 1000, 560,
            params={"mu": d.MU, "R": d.RM, "gscale": "gravity_scale", "T_aps": d.APS_THRUST, "c": C_APS,
                    "h_T": d.ASC_H_T, "rdot_T": d.ASC_RDOT_T, "vh_T": d.ASC_VH_T, "vrise": d.ASC_VRISE_RATE,
                    "steer": "steer", "tgo_min": 1.0, "t_tail": d.TAU_APS})
    dg.sig("Free", "pose", "Guid", "g")
    dg.sig("Twist", "y", "Guid", "V")
    dg.sig("Tank", "m", "Guid", "m")
    dg.sig("Engine", "T", "Guid", "T")
    dg.sig("Tank", "prop", "Guid", "prop")
    dg.sig("Guid", "u", "Att", "u", "thrust direction")
    dg.sig("Guid", "T_cmd", "Engine", "T_cmd")
    dg.node("Windows", "stdlib:sources/Constant", 220, 1120, params={"value": 0.0})
    dg.sig("Windows", "y", "Att", "phi", "windows angle")
    dg.node("Orbit", "project:OrbitElements", 1240, 460, params={"mu": d.MU, "R": d.RM})
    dg.sig("Free", "pose", "Orbit", "g")
    dg.sig("Twist", "y", "Orbit", "V")
    dg.note("Apollo 11 ascent from Tranquility Base to orbit insertion: the ascent stage lifts off the descent stage "
            "(which stays behind), rises vertically, pitches over and flies Apollo's linear guidance to 60,000 ft, "
            "5,535 ft/s; the ascent engine is cut on the target velocity.", 40, -40, 960, 60)
    params = [
        glob("gravity_scale", 1.0, "1", "Gravity multiplier (guidance and dynamics; 0 with steer = 0: Tsiolkovsky)"),
        glob("steer", 1.0, "1", "1: pitch-over and insertion guidance; 0: hold the vertical rise until the tanks run dry"),
        glob("att_wn", d.ATT_WN, "rad/s", "Attitude loop natural frequency"),
    ]
    plots = [
        {"id": "p1", "title": "Altitude (ft)", "signals": ["State/h_ft"]},
        {"id": "p2", "title": "Horizontal and radial velocity (ft/s)", "signals": ["State/vh_fps", "State/rdot_fps"]},
        {"id": "p3", "title": "Mass (kg)", "signals": ["Tank/m"]},
        {"id": "p4", "title": "Tilt of the thrust axis from vertical (deg)", "signals": ["State/tilt_deg"]},
        {"id": "p5", "title": "Orbit: apolune and perilune (km)", "signals": ["Orbit/apolune_km", "Orbit/perilune_km"]},
        {"id": "p6", "title": "Velocity gained (ft/s)", "signals": ["Status/dv_fps"]},
        {"id": "p7", "title": "Trajectory: altitude (km) over range (km)", "signals": ["State/h_km"], "x": "State/s_km"},
    ]
    dash = {"autoRerun": True, "cards": [
        text("d1", "Eagle to orbit", "Lift-off from Tranquility Base: vertical rise, pitch-over, insertion into the "
             "9 by 45 n mi orbit after about 7 min 15 s. Set **steer** and **gravity** to 0 and the speed is "
             "Tsiolkovsky's c ln(m0/m).", "2x1"),
        slider("d2", "Steer (pitch-over)", "steer", 0.0, 1.0, 1.0, 0),
        slider("d3", "Gravity multiplier", "gravity_scale", 0.0, 1.0, 1.0, 0),
        value("d4", "Altitude", "State/h_ft", 0, "ft"),
        value("d5", "Horizontal velocity", "State/vh_fps", 0, "ft/s"),
        value("d6", "Perilune", "Orbit/perilune_km", 1, "km"),
        value("d7", "Apolune", "Orbit/apolune_km", 1, "km"),
        plot("d8", "Altitude (ft)", ["State/h_ft"], "2x2"),
        plot("d9", "Velocity (ft/s)", ["State/vh_fps", "State/rdot_fps"], "2x2"),
        plot("d10", "Tilt from vertical (deg)", ["State/tilt_deg"], "2x2"),
    ]}
    return model_doc("lm-ascent", "Apollo 11 lunar module ascent stage from lift-off to orbit insertion on a "
                     "variable-mass 3D bond graph. Generated by design/build_model.py.", dg, settings(460.0, 4601),
                     plots, "scenes/lm-ascent.sdf", [
                         {"target": "link:lm", "property": "pose", "signal": [f"View/gv[{k}]" for k in range(1, 8)]},
                         {"target": "link:ground", "property": "pose", "signal": [f"View/ground[{k}]" for k in range(1, 8)]},
                         {"target": "link:site", "property": "pose", "signal": [f"View/site[{k}]" for k in range(1, 8)]},
                         {"target": "visual:plume", "property": "scale.z", "signal": "View/plume", "gain": 1.0},
                     ], params, dash)


def model_doc(name, comment, dg, sett, plots, scene, bindings, params, dash) -> dict:
    return {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
            "diagram": {"nodes": dg.nodes, "connections": dg.conns, "subsystemPorts": [], "annotations": dg.ann},
            "settings": sett, "plots": plots, "scene": {"file": scene}, "bindings": bindings,
            "parameters": params, "dashboard": dash}


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
def _rpy_of(R):
    """Fixed-axis roll-pitch-yaw (SDF) of a rotation matrix."""
    pitch = math.asin(max(-1.0, min(1.0, -R[2][0])))
    roll = math.atan2(R[2][1], R[2][2])
    yaw = math.atan2(R[1][0], R[0][0])
    return roll, pitch, yaw


def _align_z(dv):
    """Rotation taking e_z to the unit vector dv."""
    n = math.sqrt(sum(x * x for x in dv))
    z = [x / n for x in dv]
    a = [1.0, 0.0, 0.0] if abs(z[0]) < 0.9 else [0.0, 1.0, 0.0]
    x = [a[1] * z[2] - a[2] * z[1], a[2] * z[0] - a[0] * z[2], a[0] * z[1] - a[1] * z[0]]
    nx = math.sqrt(sum(c * c for c in x))
    x = [c / nx for c in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    return [[x[0], y[0], z[0]], [x[1], y[1], z[1]], [x[2], y[2], z[2]]]


def _vis(name, geom, pose, rgba):
    x, y, z, r, p, yw = pose
    return (f'      <visual name="{name}">\n        <pose>{x:.5g} {y:.5g} {z:.5g} {r:.7g} {p:.7g} {yw:.7g}</pose>\n'
            f'        <geometry>{geom}</geometry>\n        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def _box(a, b, c):
    return f"<box><size>{a:.5g} {b:.5g} {c:.5g}</size></box>"


def _cyl(r, h):
    return f"<cylinder><radius>{r:.5g}</radius><length>{h:.5g}</length></cylinder>"


def _rod(name, p0, p1, r, rgba):
    """A cylinder from point p0 to p1."""
    mid = [(a + b) / 2 for a, b in zip(p0, p1)]
    dv = [b - a for a, b in zip(p0, p1)]
    length = math.sqrt(sum(c * c for c in dv))
    return _vis(name, _cyl(r, length), (*mid, *_rpy_of(_align_z(dv))), rgba)


GOLD, FOIL, GREY, DARK, SILVER = "0.83 0.64 0.22 1", "0.70 0.55 0.25 1", "0.62 0.62 0.62 1", "0.12 0.12 0.13 1", "0.80 0.80 0.82 1"
PLUME = "1.0 0.85 0.55 0.35"
LUNAR = "0.52 0.51 0.49 1"


def descent_stage_visuals(frame) -> str:
    """The descent stage: octagonal body, engine bell, four legs with footpads and three probes.
    `frame(h, a, b)` maps a height above the pad soles and two lateral coordinates (along body y,
    body z) to the link frame; it returns (x, y, z) and the rpy that turns e_z into the up axis."""
    out = []
    w = 4.22                      # across the flats (Wikipedia: 4.22 m without the gear)
    a = w * (math.sqrt(2) - 1)    # side of the regular octagon
    h0, h1 = 0.95, 2.6            # bottom and top of the stage above the pads [est]
    for k, ang in enumerate((0.0, 45.0, 90.0, 135.0)):
        out.append(frame.box(f"ds_body{k + 1}", (h0 + h1) / 2, 0.0, 0.0, (h1 - h0, w, a), math.radians(ang),
                             GOLD if k % 2 == 0 else FOIL))
    out.append(frame.box("ds_deck", h1 + 0.03, 0.0, 0.0, (0.06, w * 0.9, w * 0.9), 0.0, "0.75 0.75 0.74 1"))
    out.append(frame.cyl("dps_throat", h0 - 0.15, 0.0, 0.0, 0.35, 0.3, DARK))
    out.append(frame.cyl("dps_bell", h0 - 0.65, 0.0, 0.0, 0.75, 0.75, DARK))
    for k, (_, b) in enumerate(PADS):
        lat = (b[1], b[2])
        un = (lat[0] / d.TREAD, lat[1] / d.TREAD)
        pad = (0.12, d.TREAD * un[0], d.TREAD * un[1])
        top = (2.25, 2.1 * un[0], 2.1 * un[1])
        mid = (1.15, 2.6 * un[0], 2.6 * un[1])
        out.append(frame.cyl(f"pad{k + 1}", 0.06, pad[1], pad[2], d.PAD_D / 2, 0.12, SILVER))
        out.append(frame.rod(f"strut{k + 1}", pad, top, 0.09, GOLD))
        out.append(frame.rod(f"brace{k + 1}", (0.55, d.TREAD * 0.86 * un[0], d.TREAD * 0.86 * un[1]), mid, 0.05, SILVER))
        if b[2] <= 0.0 or abs(b[1]) > 0:    # no probe on the forward (+Z) leg (TN D-6850)
            if not (b[2] > 0):
                out.append(frame.rod(f"probe{k + 1}", (0.0, pad[1], pad[2]), (-d.PROBE, pad[1], pad[2]), 0.015, DARK))
    return "".join(out)


def ascent_stage_visuals(frame) -> str:
    """The ascent stage on the descent stage's deck (heights above the pad soles)."""
    out = []
    b0 = 2.66
    out.append(frame.box("as_cabin", b0 + 1.2, 0.0, 0.35, (2.35, 2.9, 2.4), 0.0, SILVER))
    out.append(frame.box("as_aft", b0 + 1.35, 0.0, -1.55, (2.2, 1.6, 1.9), 0.0, "0.66 0.66 0.68 1"))
    out.append(frame.box("as_front", b0 + 1.0, 0.0, 1.85, (1.4, 1.2, 0.3), 0.0, "0.86 0.86 0.86 1"))
    out.append(frame.box("window_l", b0 + 1.95, -0.6, 1.79, (0.55, 0.06, 0.08), 0.0, DARK))
    out.append(frame.box("window_r", b0 + 1.95, 0.6, 1.79, (0.55, 0.06, 0.08), 0.0, DARK))
    out.append(frame.box("hatch", b0 + 0.55, 0.0, 2.02, (0.8, 0.8, 0.05), 0.0, "0.45 0.45 0.47 1"))
    out.append(frame.cyl("tunnel", b0 + 2.65, 0.0, 0.2, 0.42, 0.5, SILVER))
    out.append(frame.cyl("rr_dish", b0 + 2.6, 0.0, 1.3, 0.3, 0.05, "0.9 0.9 0.9 1"))
    out.append(frame.rod("sband", (b0 + 2.4, -1.0, -0.6), (b0 + 3.1, -1.3, -0.9), 0.03, SILVER))
    for k, (yy, zz) in enumerate(((1.45, 1.45), (-1.45, 1.45), (1.45, -1.45), (-1.45, -1.45))):
        out.append(frame.box(f"rcs_quad{k + 1}", b0 + 1.6, yy * 0.85, zz * 0.85, (0.35, 0.35, 0.35), 0.0, "0.55 0.55 0.57 1"))
    return "".join(out)


class BodyFrame:
    """Visuals in the vehicle link: link x = up (thrust axis), origin at the CoM `cg` above the
    pad soles (heights h are measured from the pad soles)."""

    def __init__(self, cg):
        self.cg = cg

    def _p(self, h, a, b):
        return (h - self.cg, a, b)

    def box(self, name, h, a, b, size, rot, rgba):
        # box size (height, along y, along z) -> SDF box (x, y, z) turned by `rot` about x
        return _vis(name, _box(*size), (*self._p(h, a, b), rot, 0.0, 0.0), rgba)

    def cyl(self, name, h, a, b, r, length, rgba):
        return _vis(name, _cyl(r, length), (*self._p(h, a, b), 0.0, math.pi / 2, 0.0), rgba)

    def rod(self, name, p0, p1, r, rgba):
        return _rod(name, self._p(*p0), self._p(*p1), r, rgba)


class SiteFrame:
    """Visuals in the site link (z up, origin on the surface): body x -> z, body y -> x, body z -> y."""

    def _p(self, h, a, b):
        return (a, b, h)

    def box(self, name, h, a, b, size, rot, rgba):
        return _vis(name, _box(size[1], size[2], size[0]), (*self._p(h, a, b), 0.0, 0.0, rot), rgba)

    def cyl(self, name, h, a, b, r, length, rgba):
        return _vis(name, _cyl(r, length), (*self._p(h, a, b), 0.0, 0.0, 0.0), rgba)

    def rod(self, name, p0, p1, r, rgba):
        return _rod(name, self._p(*p0), self._p(*p1), r, rgba)


def _ground_link(size) -> str:
    out = '    <link name="ground">\n      <pose>0 0 0 0 0 0</pose>\n'
    out += _vis("regolith", _box(size, size, 2.0), (0, 0, -1.0, 0, 0, 0), LUNAR)
    return out + "    </link>\n"


# Craters around the landing point (metres from the touchdown point, x downrange = west): West
# crater (about 180 m across), which Armstrong overflew about 400 m before touchdown, its boulder
# field, and Little West crater about 60 m behind the LM (ALSJ maps); the rest are made up.
CRATERS = [(-400.0, 0.0, 90.0), (-60.0, 5.0, 15.0), (55.0, -40.0, 6.0), (-15.0, 70.0, 4.0),
           (-150.0, -120.0, 10.0), (120.0, 90.0, 8.0), (-260.0, 160.0, 25.0), (180.0, -170.0, 18.0)]
GROUND = 1100.0   # side of the surface patch below the vehicle [m]; it holds every crater, so the view fits on the vehicle


def _site_craters(dx: float) -> str:
    """Craters and boulders in the site link; `dx` is the touchdown point's x in that link."""
    out = []
    for k, (x, y, r) in enumerate(CRATERS):
        out.append(_vis(f"crater{k + 1}_rim", _cyl(r * 1.15, 0.06), (x + dx, y, 0.03, 0, 0, 0), "0.60 0.59 0.57 1"))
        out.append(_vis(f"crater{k + 1}", _cyl(r, 0.08), (x + dx, y, 0.04, 0, 0, 0), "0.40 0.40 0.39 1"))
    for k in range(12):
        ang = math.radians(-60.0 + 10.0 * k)
        rr = 100.0 + 6.0 * (k % 4)
        out.append(_vis(f"boulder{k + 1}", _box(1.5 + k % 3, 1.2 + k % 2, 1.0 + 0.3 * (k % 3)),
                        (-400.0 + dx + rr * math.cos(ang), rr * math.sin(ang), 0.4, 0, 0, 0.3 * k), "0.45 0.44 0.42 1"))
    return "".join(out)


def descent_scene() -> str:
    head = ('<?xml version="1.0"?>\n<!--\n  lm-descent / lm-hover: the Apollo 11 lunar module (Eagle). Generated by '
            'design/build_model.py.\n  Z-up, metres. The view keeps the vehicle at the origin and moves the world '
            '(block LMView):\n  the link "lm" turns with the vehicle (its x axis is the thrust axis, the link origin '
            'the centre\n  of mass 1.95 m above the footpad soles); "ground" is a patch of the lunar surface tangent '
            'to the\n  sphere below the vehicle; "site" carries the craters and boulders around the landing site '
            '(the\n  world origin). The plume stretches with the thrust (scale.z, 1 at the fixed throttle position).\n'
            '  Approximate shapes; the tread radius (4.26 m), pad size and probe length are the published ones.\n-->\n'
            '<sdf version="1.9">\n  <model name="lm-descent">\n')
    out = [head, _ground_link(GROUND)]
    out.append('    <link name="site">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_site_craters(DES["td"]["s"]))
    out.append("    </link>\n")
    out.append('    <link name="lm">\n      <pose>0 0 0 0 0 0</pose>\n')
    f = BodyFrame(d.D_CG)
    out.append(descent_stage_visuals(f))
    out.append(ascent_stage_visuals(f))
    out.append(_vis("plume", _cyl(0.9, 12.0), (0.3 - 6.0 - d.D_CG, 0, 0, 0, math.pi / 2, 0), PLUME))
    out.append("    </link>\n  </model>\n</sdf>\n")
    return "".join(out)


def ascent_scene() -> str:
    head = ('<?xml version="1.0"?>\n<!--\n  lm-ascent: the ascent stage leaves the descent stage. Generated by '
            'design/build_model.py.\n  Z-up, metres. The view keeps the ascent stage at the origin and moves the world '
            '(block LMView):\n  "lm" is the ascent stage (link x = thrust axis, origin at its centre of mass, 4.3 m '
            'above the\n  surface at lift-off); "site" carries the descent stage left at Tranquility Base and the '
            'craters;\n  "ground" is the surface patch below the vehicle. The plume stretches with the thrust.\n-->\n'
            '<sdf version="1.9">\n  <model name="lm-ascent">\n')
    out = [head, _ground_link(GROUND)]
    out.append('    <link name="site">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_site_craters(0.0))
    out.append(descent_stage_visuals(SiteFrame()))
    out.append("    </link>\n")
    out.append('    <link name="lm">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(ascent_stage_visuals(BodyFrame(d.H_ASC0)))
    out.append(_vis("aps_bell", _cyl(0.45, 0.5), (2.5 - d.H_ASC0, 0, 0, 0, math.pi / 2, 0), DARK))
    out.append(_vis("plume", _cyl(0.5, 6.0), (2.25 - 3.0 - d.H_ASC0, 0, 0, 0, math.pi / 2, 0), PLUME))
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
    td = DES["td"]
    t_td = DES["touchdown"]
    smp = DES["samples"]
    dsc = [{"kind": "scene_bindings"}, NO_DIAG]
    # ---- scipy reference (design/reference.py): the same equations, integrated independently
    for key in ("100", "258", "384", "507", "596", "650", "740"):
        r = smp[key]
        dsc.append(cv("State/h", r["t"], r["h"], f"altitude at {key} s, scipy reference (design/reference.py: the same "
                      "equations as a 6-DOF rigid body with DOP853 at rtol 1e-10)", rtol=2e-4, abs_=0.5))
        dsc.append(cv("State/speed", r["t"], r["speed"], f"inertial speed at {key} s, scipy reference", rtol=2e-4, abs_=0.05))
        dsc.append(cv("Tank/m", r["t"], r["m"], f"mass at {key} s, scipy reference", rtol=2e-5))
    dsc += [
        {"kind": "zero_crossing", "signal": "Throttle/throttle", "level": 0.75, "n": 1, "direction": "down",
         "value": DES["throttle_recovery"], "abs": 0.05, "note": "throttle recovery (the engine leaves the fixed "
         "throttle position), scipy reference"},
        {"kind": "zero_crossing", "signal": "State/h_pad", "n": 1, "direction": "down", "value": t_td, "abs": 0.1,
         "note": "touchdown (the lowest footpad reaches the surface), scipy reference"},
        cv("Tank/m", t_td - 0.05, td["m"], "mass at touchdown, scipy reference", rtol=5e-5),
        # ---- published (Apollo 11): fitted
        {"kind": "zero_crossing", "signal": "Throttle/throttle", "level": 0.75, "n": 1, "direction": "down",
         "value": d.T_THROTTLE_RECOVERY, "abs": 2.0, "note": "PUBLISHED (FITTED): throttle recovery 386 s after "
         "ignition (MR 5.3). The PDI range to the landing site is fitted to it (design.py): "
         f"{DESIGN['descent_cfg']['range_pdi'] / 1000:.1f} km against the published 'approximately 260 n mi' "
         f"({d.RANGE_PDI_PUB / 1000:.0f} km)."},
        cv("State/h_ft", d.T_HG, d.H_HG / d.FT, f"PUBLISHED (FITTED): high gate at 7,129 ft (MR 5.3) at P64 entry "
           f"102:41:32 (507 s). The braking-phase target is fitted to it. Model {smp['507']['h'] / d.FT:.0f} ft.", abs_=120.0),
        cv("State/rdot_fps", d.T_HG, d.HDOT_HG / d.FT, "PUBLISHED (FITTED): descent rate 125 ft/s at high gate "
           f"(MR 5.3). Model {smp['507']['rdot'] / d.FT:.1f} ft/s.", abs_=5.0),
    ]
    for tc, alt, rate, _ in d.CALLOUTS[:4]:
        dsc.append(cv("State/h_ft", tc, alt, f"PUBLISHED (FITTED): Aldrin's callout '{alt} feet' at {tc:.0f} s "
                      "(ALSJ). The approach-phase (P64) target is fitted to the four callouts at 596 .. 611 s.",
                      abs_=60.0))
    # ---- published: independent comparisons
    for name, tt, v, hd, h in d.PREMISSION[2:6]:
        k = f"{tt:g}"
        r = smp[k] if k in smp else None
        if r is None:
            continue
        dsc.append(cv("State/speed", tt, v * d.FT, f"PUBLISHED (validation, premission): inertial velocity {v} ft/s at "
                      f"'{name}' ({tt:.0f} s), TN D-6846 table I. Model {r['speed'] / d.FT:.0f} ft/s. The braking "
                      "phase flies at the fixed throttle position, so the speed is set by the thrust and the mass.",
                      rtol=0.04))
        dsc.append(cv("State/h_ft", tt, h, f"PUBLISHED (validation, premission): altitude {h} ft at '{name}' "
                      f"({tt:.0f} s), TN D-6846 table I. Model {r['h'] / d.FT:.0f} ft. Apollo 11 flew lower than "
                      "the premission profile (MR 5.2: a 2,800 ft altitude difference at radar lock-on); "
                      "tolerance 15 %.", rtol=0.15))
    for tc, alt, rate, fwd in d.CALLOUTS[4:]:
        dsc.append(cv("State/h_ft", tc, alt, f"PUBLISHED (validation): Aldrin's callout '{alt} feet' at {tc:.0f} s "
                      "(ALSJ). The P66 pilot model holds his called descent rates as a function of altitude, so the "
                      "time at each altitude is an output (integrated rates). Tolerance 35 ft.", abs_=35.0))
    dsc += [
        {"kind": "zero_crossing", "signal": "State/h_pad", "n": 1, "direction": "down", "value": d.T_LANDING, "abs": 8.0,
         "note": f"PUBLISHED (validation): landing at 102:45:39.9, {d.T_LANDING:.1f} s after ignition (MR 5.4). "
                 f"Model {t_td:.1f} s: the end of the landing phase follows from the P66 entry state and the "
                 "pilot model's rates."},
        cv("Tank/m", t_td - 0.05, d.M_PDI - d.DPS_PDI, f"PUBLISHED (validation): propellant burned in the powered "
           f"descent 17,146 lb (SP-2000-4029: 17,414 lb DPS total less the 268 lb DOI burn), so {d.M_PDI - d.DPS_PDI:.0f} "
           f"kg at engine cutoff. Model {td['m']:.0f} kg: it burns {(d.DPS_PDI - (d.M_PDI - td['m'])):.0f} kg "
           "less (0.7 %), with the published Isp of 305 s. The 43 kg of RCS propellant are not modelled.", rtol=0.01),
        cv("Tank/prop", t_td - 0.05, d.DPS_USABLE_LEFT, f"PUBLISHED (validation): usable DPS propellant at cutoff "
           f"674 lb = {d.DPS_USABLE_LEFT:.0f} kg (SP-2000-4029). Model {td['prop_left'] - d.PROP_UNUSABLE:.0f} kg: the "
           "small difference of two large numbers (0.7 % of the burn); tolerance 25 %.", rtol=0.25),
        cv("Status/dv_fps", d.T_HG, d.PREMISSION[6][4] if False else 5375.0, "PUBLISHED (validation, premission): "
           "velocity gained to high gate 5,375 ft/s (TN D-6846 table I). Model "
           f"{smp['507']['dv'] / d.FT:.0f} ft/s.", rtol=0.02),
        cv("Status/dv_fps", 606.0, 6176.0, "PUBLISHED (validation, premission): velocity gained to low gate 6,176 ft/s "
           "(TN D-6846 table I). Model " f"{smp['606']['dv'] / d.FT:.0f} ft/s.", rtol=0.02),
        cv("Status/dv_fps", t_td - 0.05, d.DV_PDI / d.FT, f"PUBLISHED (validation): 'a velocity change of "
           f"approximately 6775 ft/sec' (MR 9.8; the premission nominal to touchdown is also 6,775). Model "
           f"{td['dv'] / d.FT:.0f} ft/s: Armstrong's longer landing phase (140 s instead of 104 s nominal) costs "
           "about 2 ft/s of velocity per second of hover; tolerance 5 %.", rtol=0.05),
        cv("State/rdot_fps", t_td - 0.05, -d.TD_VZ / d.FT, "PUBLISHED (set, not independent): touchdown 1.7 ft/s "
           "vertical (MR 5.4); the pilot model's last breakpoint is that rate.", abs_=0.5),
        {"kind": "max_abs_le", "signal": "State/rdot_fps", "from_t": t_td - 3.0, "to_t": 775.0, "value": 7.0,
         "note": "PUBLISHED (design limit): the landing gear's touchdown envelope allows 7 ft/s vertical with 4 ft/s "
                 "horizontal (up to 10 ft/s vertical at less horizontal speed), TN D-6850"},
        {"kind": "max_abs_le", "signal": "State/vh_fps", "from_t": t_td - 3.0, "to_t": 775.0, "value": 4.0,
         "note": "PUBLISHED (design limit): horizontal touchdown velocity at most 4 ft/s, TN D-6850"},
    ]
    for name, _ in PADS:
        dsc.append({"kind": "max_abs_le", "signal": f"{name}/f_n", "value": d.STRUT_CRUSH_HIGH,
                    "note": "PUBLISHED (flight, indicative): no primary-strut stroking was recorded on Apollo 11 "
                            "(TN D-6850 table V), so no strut reached its 4,500 lb honeycomb cartridge, let alone the "
                            "9,500 lb one behind it (TN D-6850 fig. 6). The model's struts are rigid and a pad's force "
                            "is shared in reality by the primary and two secondary struts, so the check is against "
                            "the 9,500 lb level; the model's peak (forward pad, as the LM rocks onto it from a 4.5 deg "
                            "tilt) is about 10 % above 4,500 lb"})
    for name in ("Pad1", "Pad3"):
        dsc.append(cv(f"{name}/delta", 774.0, d.PAD_PEN, "PUBLISHED (FITTED): the footpads penetrated the surface "
                      "2.5 to 3.5 in (MR 5.4); the contact stiffness is chosen so that a pad settles 3 in under a "
                      "quarter of the landing weight. Tolerance 0.75 in.", abs_=0.75 * 0.0254))
    w_td = td["m"] * d.MU / (d.RM + d.D_CG) ** 2
    dsc.append({"kind": "compare_signals", "signal": "Pad1/f_n", "signal_b": "Pad2/f_n", "from_t": 770.0, "to_t": 775.0,
                "max_abs": 0.05 * w_td / 4, "note": "at rest the two side pads carry the same load (within 5 %)"})
    dsc.append(cv("Pad3/f_n", 774.0, w_td / 4, "at rest on level ground each pad carries a quarter of the lunar weight "
                  "m g(R + h) / 4 (statics; m from the scipy reference at touchdown)", rtol=1e-3))
    # ---------------------------------------------------------------------------- ascent
    asm = ASC["samples"]
    cut = ASC["cut"]
    asc = [{"kind": "scene_bindings"}, NO_DIAG]
    for key in ("20", "120", "300", "430"):
        r = asm[key]
        asc.append(cv("State/h", r["t"], r["h"], f"altitude at {key} s, scipy reference", rtol=2e-4, abs_=0.5))
        asc.append(cv("State/speed", r["t"], r["speed"], f"speed at {key} s, scipy reference", rtol=2e-4))
        asc.append(cv("Tank/m", r["t"], r["m"], f"mass at {key} s, scipy reference", rtol=1e-6))
    asc += [
        {"kind": "zero_crossing", "signal": "Guid/T_cmd", "level": d.APS_THRUST / 2, "n": 1, "direction": "down",
         "value": ASC["cutoff"], "abs": 0.1, "note": "engine cutoff on the target velocity, scipy reference"},
        {"kind": "zero_crossing", "signal": "State/rdot_fps", "level": 40.0, "n": 1, "direction": "up",
         "value": ASC["pitchover"], "abs": 0.05, "note": "end of the vertical rise (radial rate 40 ft/s), scipy reference"},
        cv("Orbit/apolune_km", 450.0, ASC["after"]["apolune"] / 1000, "apolune after insertion and the thrust tail-off, scipy reference", rtol=1e-3),
        cv("Orbit/perilune_km", 450.0, ASC["after"]["perilune"] / 1000, "perilune after insertion and the thrust tail-off, scipy reference", rtol=5e-3),
        # published
        {"kind": "zero_crossing", "signal": "Guid/T_cmd", "level": d.APS_THRUST / 2, "n": 1, "direction": "down",
         "value": d.ASC_BURN, "abs": 6.0, "note": f"PUBLISHED (validation): ascent burn 434.88 s (MR table 9.6-V; TN "
         f"D-6846: insertion at 7:15 against 7:18 premission). Model {ASC['cutoff']:.1f} s with the predicted thrust "
         "and Isp of MR table 9.9-I; the report puts the 3 s difference down to a slightly higher thrust-to-weight "
         "ratio in flight."},
        {"kind": "zero_crossing", "signal": "State/rdot_fps", "level": 40.0, "n": 1, "direction": "up", "value": d.ASC_T_VRISE,
         "abs": 3.0, "note": f"PUBLISHED (validation): the vertical rise ends about 10 s after lift-off (TN D-6846 "
         f"table V). Model {ASC['pitchover']:.1f} s (the guidance switch; the report's 10 s includes the autopilot lag)."},
        cv("Tank/m", 450.0, d.M_INSERTION, f"PUBLISHED (validation): ascent stage at orbit insertion 5,928.6 lb = "
           f"{d.M_INSERTION:.0f} kg (MR appendix A). Model {ASC['after']['m']:.0f} kg; the 69 lb of RCS propellant are not "
           "modelled.", rtol=0.02),
        cv("Status/dv_fps", 450.0, d.ASC_DV / d.FT, f"PUBLISHED (validation): ascent velocity change 6,070.1 ft/s "
           f"(MR table 7-V). Model {ASC['after']['dv'] / d.FT:.0f} ft/s.", rtol=0.02),
        cv("State/h_ft", 450.0, d.ASC_INS["h"] / d.FT, "PUBLISHED (target): insertion altitude 60,300 ft "
           "(postflight, TN D-6846 table V); the guidance targets 60,000 ft, so this checks that it gets there "
           f"(model {cut['h'] / d.FT:.0f} ft at cutoff; 450 s is 12 s into the coast).", rtol=0.02),
        cv("State/vh_fps", 450.0, d.ASC_INS["vh"] / d.FT, "PUBLISHED (target): down-range velocity at insertion "
           "5,537 ft/s (postflight); the engine is cut at the 5,534.9 ft/s target.", rtol=0.003),
        cv("Orbit/apolune_km", 450.0, d.ASC_ORBIT_RAW[0] / 1000, "PUBLISHED (validation): orbit of the ascent burn "
           "48.0 by 9.1 n mi (MR table 7-V); apolune 88.9 km. Model "
           f"{ASC['after']['apolune'] / 1000:.1f} km. Heights above the mean radius; Apollo quoted heights above the landing-site "
           "radius (1.8 km less). Tolerance 3 km.", abs_=3.0),
        cv("Orbit/perilune_km", 450.0, d.ASC_ORBIT_RAW[1] / 1000, "PUBLISHED (validation): perilune 9.1 n mi = 16.9 km "
           f"(MR table 7-V). Model {ASC['after']['perilune'] / 1000:.1f} km. Tolerance 3 km.", abs_=3.0),
    ]
    av = DESIGN["ascent_vacuum"]
    m300 = d.M_LIFTOFF - d.APS_THRUST / C_APS * 300.0
    dv300 = C_APS * math.log(d.M_LIFTOFF / m300)
    vac = [
        cv("State/speed", 300.0, dv300, f"TSIOLKOVSKY (analytic): no gravity, thrust held vertical, so the speed is "
           f"c ln(m0/m) = {C_APS:.2f} m/s * ln({d.M_LIFTOFF:.1f}/{m300:.2f}); the engine burns at full thrust from "
           "t = 0, m(t) = m0 - T t / c. Tests the variable-mass bond graph (MI + outflow MR).", rtol=1e-6),
        cv("Tank/m", 300.0, m300, "mass at 300 s, m0 - T t / c (analytic)", rtol=1e-9),
        cv("State/speed", 300.0, av["speed"], "scipy reference in vacuum", rtol=1e-6),
    ]
    # ---------------------------------------------------------------------------- hover
    hov = [{"kind": "scene_bindings"}, NO_DIAG,
           {"kind": "max_abs_le", "signal": "State/rdot_fps", "from_t": 100.0, "to_t": 200.0, "value": 7.0,
            "note": "the default flight lands within the gear's vertical design limit, 7 ft/s (TN D-6850)"},
           {"kind": "min_ge", "signal": "Tank/prop", "value": 0.0, "note": "the default flight lands with propellant left"}]
    # hover hold: rate 0 at 100 ft until the propellant runs out: analytic depletion time and fall
    h0 = 100.0 * d.FT
    g_h = d.MU / (d.RM + h0) ** 2
    prop = 300.0
    m0 = M_EMPTY_DPS + prop
    t_dep = C_DPS / g_h * math.log(m0 / M_EMPTY_DPS)
    hold = [
        cv("Status/tw", 30.0, g_h / G_SURF, "hover: thrust equals the weight at 100 ft, T/(m g_surface) = "
           "(R/(R+h))^2 (analytic)", rtol=1e-6),
        cv("State/h_ft", 60.0, 100.0, "hover: the altitude is held (a rate loop, no altitude hold: it drifts by the thrust lag at the start)", abs_=0.5),
        {"kind": "zero_crossing", "signal": "Tank/prop", "level": 0.0, "n": 1, "direction": "down", "value": t_dep,
         "abs": 0.01,
         "note": f"ROCKET EQUATION (analytic): in a hover T = m g, so m(t) = m0 exp(-g t / c) and the usable "
                 f"propellant ({prop:.0f} kg) is gone at t = (c/g) ln(m0/m_empty) = {t_dep:.3f} s"},
        cv("State/rdot_fps", t_dep + 3.0, -g_h * (3.0 - d.TAU_ENGINE) / d.FT, "free fall after the engine quits: "
           "the lagged thrust T0 exp(-t/tau) with T0 = m g still gives g tau of velocity, so 3 s later "
           "rdot = -g (3 s - tau) (analytic)", rtol=1e-3),
    ]
    return {
        "project": "lunar-module",
        "description": "The Apollo 11 lunar module (Eagle) on a variable-mass 3D bond graph: powered descent from PDI "
                       "to touchdown on the landing gear, the landing phase flown from the dashboard, and the ascent "
                       "to orbit. Checks against an independent scipy integration of the same equations (tight), "
                       "analytic rocket-equation cases (exact), and the Apollo 11 Mission Report, Apollo by the "
                       "Numbers, TN D-6846/D-6850 and the ALSJ transcript (honest tolerances; each note says whether "
                       "the quantity was fitted).",
        "models": {
            "lm-descent": {"checks": dsc, "run_timeout": 1200},
            "lm-ascent": {"checks": asc, "run_timeout": 900},
            "lm-ascent-vacuum": {"model": "lm-ascent", "settings": {"t_end": 300.0, "output": {"points": 601}},
                                 "overrides": [{"target": "global:gravity_scale", "value": 0.0},
                                               {"target": "global:steer", "value": 0.0}],
                                 "checks": vac, "run_timeout": 900},
            "lm-hover": {"checks": hov, "run_timeout": 900},
            "lm-hover-hold": {"model": "lm-hover", "settings": {"t_end": 120.0, "output": {"points": 1201}},
                              "overrides": [{"target": "global:h0_ft", "value": 100.0},
                                            {"target": "global:rod_fps", "value": 0.0},
                                            {"target": "global:td_fps", "value": 0.0},
                                            {"target": "global:fwd_fps", "value": 0.0},
                                            {"target": "global:prop_start", "value": prop}],
                              "checks": hold, "run_timeout": 900},
        },
    }


def main() -> int:
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "scenes").mkdir(exist_ok=True)
    for model in (descent_model(), ascent_model(), hover_model()):
        path = ROOT / "models" / f"{model['name']}.bgmodel.json"
        path.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path} ({len(model['diagram']['nodes'])} nodes)")
    (ROOT / "scenes" / "lm-descent.sdf").write_text(descent_scene(), encoding="utf-8", newline="\n")
    (ROOT / "scenes" / "lm-ascent.sdf").write_text(ascent_scene(), encoding="utf-8", newline="\n")
    (ROOT / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "lunar-module",
            "models": ["lm-descent", "lm-hover", "lm-ascent"], "libraryDir": "library", "scenesDir": "scenes"}
    (ROOT / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json, scenes, bgsim.project.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
