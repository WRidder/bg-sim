# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the AIM-9X example: models, scene and expected.json.

The three models are the same plant with different loops closed:

    aim9x-airframe   aeroelastic-free 6-DOF body, motor and canards, open loop (a fin doublet)
    aim9x-control    the same body under the roll + acceleration autopilot and TVC
    aim9x-intercept  the full weapon: target, imaging seeker, proportional navigation,
                     autopilot, servos and proximity fuze

Run:  uv run examples/aim9x/design/build_model.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as d

ROOT = HERE.parent
MODELS = ROOT / "models"


def fmt(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return "true" if x else "false"
    return repr(float(x))


def vec(xs) -> str:
    return "[" + ", ".join(fmt(x) for x in xs) + "]"


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.ann: list[dict] = []

    def node(self, name, ref, x, y, params=None, starts=None, constants=None) -> str:
        nid = f"n{len(self.nodes) + 1:03d}"
        block = {"junction": ref[9:]} if ref.startswith("junction:") else {"ref": ref}
        self.nodes.append({
            "id": nid, "name": name, "block": block, "position": {"x": x, "y": y},
            "rotation": 0, "flipX": False,
            "params": {k: fmt(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: fmt(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        return nid

    def bond(self, a, ap, b, bp):
        c = {"id": f"b{len(self.conns) + 1:03d}", "kind": "bond",
             "from": {"node": a}, "to": {"node": b}, "route": [], "label": None}
        if ap:
            c["from"]["port"] = ap
        if bp:
            c["to"]["port"] = bp
        self.conns.append(c)

    def sig(self, a, ap, b, bp, label=None):
        self.conns.append({"id": f"s{len(self.conns) + 1:03d}", "kind": "signal",
                           "from": {"node": a, "port": ap}, "to": {"node": b, "port": bp},
                           "route": [], "label": label})

    def note(self, text, x, y, w=420, h=70, color="yellow"):
        self.ann.append({"id": f"a{len(self.ann) + 1}", "kind": "text", "text": text,
                         "x": x, "y": y, "w": w, "h": h, "color": color})


def glob(name, value, unit, description):
    return {"name": name, "value": str(value), "unit": unit, "description": description}


GLOBALS = [
    glob("vt0", d.V_M0, "m/s", "Launch speed (the carrier aircraft's speed)"),
    glob("h0", d.P_M0[2], "m", "Launch altitude"),
    glob("mx0", d.P_M0[0], "m", "Launch position, north"),
    glob("my0", d.P_M0[1], "m", "Launch position, west"),
    glob("alpha0", d.ALPHA0, "deg", "Launch angle of attack"),
    glob("tvc_on", 1.0, "1", "Thrust-vector control (1 on, 0 off)"),
    glob("nav_N", d.N_PN, "1", "Proportional-navigation constant"),
    glob("a_max_g", d.A_MAX / d.G0, "g", "Guidance acceleration limit"),
    glob("tgt_x", d.P_T0[0], "m", "Target start, north"),
    glob("tgt_y", d.P_T0[1], "m", "Target start, west"),
    glob("tgt_z", d.P_T0[2], "m", "Target start altitude"),
    glob("tgt_v", d.V_T0, "m/s", "Target speed"),
    glob("tgt_psi", d.PSI_T0, "deg", "Target initial heading (from north towards west)"),
    glob("turn_rate", math.degrees(d.TURN_RATE), "deg/s", "Target turn rate"),
    glob("turn_t", d.T_TURN, "s", "Target turn start"),
    glob("dp_amp", 0.2, "deg", "Airframe model: pitch-canard doublet amplitude"),
    glob("dy_amp", 0.1, "deg", "Airframe model: yaw-canard doublet amplitude"),
    glob("dr_amp", 0.0, "deg", "Airframe model: roll-canard doublet amplitude"),
]


# --------------------------------------------------------------------------- graph parts
def _servo(dg: Diagram, name: str, x: float, y: float) -> dict:
    # The F-16 example's proven servo: a position limit before the lag, a first-order lag at
    # servo_w0, a rate limit on the error, and an integrating output (so the deflection is a
    # state and cannot feed an algebraic loop).
    tr = dg.node(f"{name}Travel", "stdlib:continuous/Saturation", x, y,
                 params={"lower": -d.FIN_MAX, "upper": d.FIN_MAX})
    mx = dg.node(f"{name}Mx", "stdlib:continuous/Mux2", x + 150, y)
    err = dg.node(f"{name}Err", "stdlib:continuous/Sum", x + 300, y, params={"signs": "[1.0, -1.0]"})
    bw = dg.node(f"{name}Bw", "stdlib:continuous/Gain", x + 450, y, params={"k": d.SERVO_W0})
    rl = dg.node(f"{name}Rate", "stdlib:continuous/Saturation", x + 600, y,
                 params={"lower": -d.FIN_RATE, "upper": d.FIN_RATE})
    sv = dg.node(f"{name}", "stdlib:continuous/Integrator", x + 750, y,
                 params={"lower": -d.FIN_MAX, "upper": d.FIN_MAX})
    dg.sig(tr, "y", mx, "u1")
    dg.sig(sv, "y", mx, "u2")
    dg.sig(mx, "y", err, "u")
    dg.sig(err, "y", bw, "u")
    dg.sig(bw, "y", rl, "u")
    dg.sig(rl, "y", sv, "u")
    return {"travel": tr, "rate": rl, "servo": sv}


def plant(dg: Diagram, n: dict, tvc_from_ap: bool) -> None:
    """The 3D bond graph, air data, atmosphere, aero and motor. Shared by all three models."""
    n["World"] = dg.node("World", "stdlib:multibond/GroundSpatial", 40, 340)
    n["Free"] = dg.node("Free", "stdlib:spatial/Free3D", 220, 340,
                        starts={"qw": "cos(alpha0*pi/360)", "qy": "-sin(alpha0*pi/360)",
                                "px": "mx0", "py": "my0", "pz": "h0"})
    n["Body"] = dg.node("Body", "junction:1", 430, 340)
    n["Inertia"] = dg.node(
        "Inertia", "project:VariableInertia3D", 650, 200,
        starts={"P": "[" + ", ".join([
            "0.0", "0.0", "0.0",
            f"{d.MASS_0}*vt0*cos(alpha0*pi/180)", "0.0",
            f"-{d.MASS_0}*vt0*sin(alpha0*pi/180)"]) + "]"})
    n["Coriolis"] = dg.node("Coriolis", "stdlib:multibond/CoriolisSpatial", 650, 320)
    n["Twist"] = dg.node("Twist", "stdlib:multibond/DfSpatial", 650, 440)
    n["AeroW"] = dg.node("AeroW", "stdlib:multibond/ExternalWrenchSpatial", 430, 560)
    n["ThrustW"] = dg.node("ThrustW", "stdlib:multibond/ExternalWrenchSpatial", 430, 680)
    n["WeightW"] = dg.node("WeightW", "stdlib:multibond/ExternalWrenchSpatial", 430, 800)
    n["Weight"] = dg.node("Weight", "project:MissileWeight", 220, 800)
    n["Motor"] = dg.node("Motor", "project:MissileMotor", 860, 680)
    dg.bond(n["World"], "p", n["Free"], "parent")
    dg.bond(n["Free"], "child", n["Body"], None)
    for key in ("Inertia", "Coriolis", "Twist"):
        dg.bond(n["Body"], None, n[key], "p")
    for key in ("AeroW", "ThrustW", "WeightW"):
        dg.bond(n[key], "p", n["Body"], None)
    dg.sig(n["Inertia"], "Pm", n["Coriolis"], "P", "momentum")
    # the propellant leaving through the six twist components
    for k in range(1, 7):
        axis = dg.node(f"Axis{k}", "junction:1", 120, 940 + 55 * k)
        out = dg.node(f"Out{k}", "stdlib:bondgraph/MR", 250, 940 + 55 * k)
        dg.bond(axis, None, n["Free"], f"drive{k}")
        dg.bond(axis, None, out, "p")
        n[f"Out{k}"] = out
    dg.sig(n["Motor"], "m", n["Inertia"], "m")
    dg.sig(n["Motor"], "J", n["Inertia"], "J")
    for k in range(1, 4):
        dg.sig(n["Motor"], f"r_ang{k}", n[f"Out{k}"], "u")
    for k in range(4, 7):
        dg.sig(n["Motor"], "r_lin", n[f"Out{k}"], "u")
    for port in ("tx", "ty", "tz", "fx", "fy_out", "fz_out"):
        dst = {"fy_out": "fy", "fz_out": "fz"}.get(port, port)
        dg.sig(n["Motor"], port, n["ThrustW"], dst)
    dg.sig(n["Free"], "pose", n["Weight"], "g")
    dg.sig(n["Motor"], "m", n["Weight"], "m")
    for port in ("tx", "ty", "tz", "fx", "fy", "fz"):
        dg.sig(n["Weight"], port, n["WeightW"], port)

    # atmosphere and air data
    n["ISA"] = dg.node("ISA", "project:ISA1976", 860, 40)
    n["Air"] = dg.node("Air", "project:MissileAirData", 1060, 160)
    dg.sig(n["Free"], "pose", n["Air"], "g")
    dg.sig(n["Twist"], "y", n["Air"], "V", "twist")
    dg.sig(n["Air"], "h", n["ISA"], "h")
    dg.sig(n["ISA"], "rho", n["Air"], "rho")
    dg.sig(n["ISA"], "a", n["Air"], "a")
    dg.sig(n["ISA"], "p", n["Motor"], "pa")

    # coefficients against Mach
    n["CNa"] = dg.node("CNa", "stdlib:continuous/Lookup1D", 860, 260,
                       constants={"N": len(d.MACH_TAB)},
                       params={"x": vec(d.MACH_TAB), "table": vec(d.CN_ALPHA_TAB)})
    n["CD0"] = dg.node("CD0", "stdlib:continuous/Lookup1D", 860, 360,
                       constants={"N": len(d.MACH_TAB)},
                       params={"x": vec(d.MACH_TAB), "table": vec(d.CD0_TAB)})
    dg.sig(n["Air"], "mach", n["CNa"], "u")
    dg.sig(n["Air"], "mach", n["CD0"], "u")

    # aero build-up and its wrench
    n["Aero"] = dg.node("Aero", "project:MissileAero", 1260, 460)
    dg.sig(n["Air"], "va", n["Aero"], "va")
    dg.sig(n["Air"], "alpha", n["Aero"], "alpha")
    dg.sig(n["Air"], "beta", n["Aero"], "beta")
    dg.sig(n["Air"], "q_up", n["Aero"], "q_up")
    dg.sig(n["Air"], "r_right", n["Aero"], "r_right")
    dg.sig(n["Air"], "p", n["Aero"], "p")
    dg.sig(n["Air"], "qbar", n["Aero"], "qbar")
    dg.sig(n["Air"], "vt", n["Aero"], "vt")
    dg.sig(n["Motor"], "m", n["Aero"], "m")
    dg.sig(n["CNa"], "y", n["Aero"], "cna")
    dg.sig(n["CD0"], "y", n["Aero"], "cd0")
    for port in ("tx", "ty", "tz", "fx", "fy", "fz"):
        dg.sig(n["Aero"], port, n["AeroW"], port)

    # the four canard servos
    for k in range(1, 5):
        n[f"Fin{k}"] = _servo(dg, f"Fin{k}", 1960, 80 + 130 * (k - 1))
        dg.sig(n[f"Fin{k}"]["servo"], "y", n["Aero"], f"d{k}")

    # TVC command, zero unless an autopilot drives it
    if not tvc_from_ap:
        n["Tvc0"] = dg.node("Tvc0", "stdlib:sources/Constant", 1760, 700, params={"value": 0.0})
        dg.sig(n["Tvc0"], "y", n["Motor"], "tvc_p")
        dg.sig(n["Tvc0"], "y", n["Motor"], "tvc_y")

    # the 3D view: the missile at the origin, its attitude and the plume
    n["View"] = dg.node("View", "project:MissileSoloView", 1960, 260)
    dg.sig(n["Free"], "pose", n["View"], "g")
    dg.sig(n["Motor"], "T", n["View"], "T")


def mixer(dg: Diagram, n: dict) -> None:
    n["Mixer"] = dg.node("Mixer", "project:FinMixer", 1760, 340)
    for k in range(1, 5):
        dg.sig(n["Mixer"], f"d{k}", n[f"Fin{k}"]["travel"], "u")


def autopilot(dg: Diagram, n: dict) -> None:
    n["AP"] = dg.node("AP", "project:MissileAutopilot", 1480, 340)
    dg.sig(n["Air"], "qbar", n["AP"], "qbar")
    dg.sig(n["Air"], "vt", n["AP"], "vt")
    dg.sig(n["Air"], "p", n["AP"], "p")
    dg.sig(n["Air"], "q_up", n["AP"], "q_up")
    dg.sig(n["Air"], "r_right", n["AP"], "r_right")
    dg.sig(n["Air"], "phi", n["AP"], "phi")
    dg.sig(n["Aero"], "a_z", n["AP"], "a_z")
    dg.sig(n["Aero"], "a_y", n["AP"], "a_y")
    dg.sig(n["Motor"], "T", n["AP"], "T")
    dg.sig(n["Motor"], "m", n["AP"], "m")
    dg.sig(n["AP"], "dp", n["Mixer"], "dp")
    dg.sig(n["AP"], "dy", n["Mixer"], "dy")
    dg.sig(n["AP"], "dr", n["Mixer"], "dr")
    dg.sig(n["AP"], "tvc_p", n["Motor"], "tvc_p")
    dg.sig(n["AP"], "tvc_y", n["Motor"], "tvc_y")
    n["RollCmd"] = dg.node("RollCmd", "stdlib:sources/Constant", 1260, 700, params={"value": 0.0})
    dg.sig(n["RollCmd"], "y", n["AP"], "roll_cmd")
    n["TvcOn"] = dg.node("TvcOn", "stdlib:sources/Constant", 1260, 800, params={"value": "tvc_on"})
    dg.sig(n["TvcOn"], "y", n["AP"], "tvc_on")


def seeker_chain(dg: Diagram, n: dict, with_target: bool) -> None:
    n["Seeker"] = dg.node("Seeker", "project:MissileSeeker", 1480, 80)
    dg.sig(n["Free"], "pose", n["Seeker"], "gm")
    dg.sig(n["Twist"], "y", n["Seeker"], "Vm")
    if with_target:
        n["Target"] = dg.node("Target", "project:TargetMotion", 1060, 80,
                              params={"v0": "tgt_v", "turn_rate": "turn_rate*pi/180", "t_turn": "turn_t"},
                              starts={"ps": "[tgt_x, tgt_y, tgt_z]", "psis": "tgt_psi*pi/180"})
    dg.sig(n["Target"], "pose", n["Seeker"], "gt")
    dg.sig(n["Target"], "vw_out", n["Seeker"], "Vt")
    dg.sig(n["Target"], "ir", n["Seeker"], "I_t")
    dg.sig(n["Air"], "pos", n["Target"], "pm")
    n["SeekerOn"] = dg.node("SeekerOn", "stdlib:sources/Constant", 1260, 180, params={"value": 1.0})
    dg.sig(n["SeekerOn"], "y", n["Seeker"], "seeker_on")
    n["Guide"] = dg.node("Guide", "project:ProNav", 1660, 80,
                         params={"N": "nav_N", "a_max": f"a_max_g*{d.G0}"})
    dg.sig(n["Seeker"], "los_pitch", n["Guide"], "los_pitch")
    dg.sig(n["Seeker"], "los_yaw", n["Guide"], "los_yaw")
    dg.sig(n["Seeker"], "range", n["Guide"], "range")
    dg.sig(n["Seeker"], "range_rate", n["Guide"], "range_rate")
    dg.sig(n["Air"], "gz_body", n["Guide"], "gz_body")
    dg.sig(n["Air"], "qbar", n["Guide"], "qbar")
    dg.sig(n["Motor"], "m", n["Guide"], "m")
    dg.sig(n["Guide"], "a_z_cmd", n["AP"], "a_z_cmd")
    dg.sig(n["Guide"], "a_y_cmd", n["AP"], "a_y_cmd")


def status(dg: Diagram, n: dict) -> None:
    n["Status"] = dg.node("Status", "project:MissileStatus", 1760, 520,
                          params={"fuze_radius": d.FUZE_RADIUS, "kill_radius": d.KILL_RADIUS})
    dg.sig(n["Free"], "pose", n["Status"], "g")
    dg.sig(n["Twist"], "y", n["Status"], "V")
    dg.sig(n["Air"], "alpha_deg", n["Status"], "alpha_deg")
    dg.sig(n["Air"], "beta_deg", n["Status"], "beta_deg")
    dg.sig(n["Air"], "qbar", n["Status"], "qbar")
    dg.sig(n["Air"], "mach", n["Status"], "mach")
    dg.sig(n["Air"], "vt", n["Status"], "vt")
    dg.sig(n["Aero"], "n_z", n["Status"], "n_z")
    dg.sig(n["Aero"], "n_y", n["Status"], "n_y")
    dg.sig(n["Motor"], "m", n["Status"], "m")
    dg.sig(n["Seeker"], "range", n["Status"], "range")
    dg.sig(n["Seeker"], "range_rate", n["Status"], "range_rate")
    dg.sig(n["Seeker"], "lock", n["Status"], "lock")
    n["Stop"] = dg.node("Stop", "stdlib:sources/StopSimulation", 1960, 520,
                        params={"threshold": 0.5})
    dg.sig(n["Status"], "fuze", n["Stop"], "u")


def model(name: str, kind: str) -> dict:
    dg = Diagram()
    n: dict = {}
    plant(dg, n, tvc_from_ap=(kind != "airframe"))
    mixer(dg, n)
    if kind in ("control", "intercept"):
        autopilot(dg, n)
    if kind == "airframe":
        # open-loop canard doublets
        for k, (amp, t0) in enumerate((("dp_amp", 0.531), ("dy_amp", 4.037), ("dr_amp", 6.049)), start=1):
            cmd = dg.node(f"Cmd{k}", "stdlib:sources/TimeTable", 1480, 620 + 90 * k,
                          constants={"N": 8},
                          params={"t_start": t0, "sample_time": 0.2137, "method": "1",
                                  "values": f"[0.0, 0.0, {amp}, {amp}, 0.0, 0.0, 0.0, 0.0]"})
            n[f"Cmd{k}"] = cmd
        dg.sig(n["Cmd1"], "y", n["Mixer"], "dp")
        dg.sig(n["Cmd2"], "y", n["Mixer"], "dy")
        dg.sig(n["Cmd3"], "y", n["Mixer"], "dr")
    elif kind == "control":
        az = dg.node("AzCmd", "stdlib:sources/TimeTable", 1260, 620, constants={"N": 12},
                     params={"t_start": 0.531, "sample_time": 0.2137, "method": "1",
                             "values": "[0.0, 0.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0, 0.0, 0.0]"})
        ay = dg.node("AyCmd", "stdlib:sources/TimeTable", 1260, 720, constants={"N": 12},
                     params={"t_start": 3.037, "sample_time": 0.2137, "method": "1",
                             "values": "[0.0, 0.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 0.0, 0.0]"})
        dg.sig(az, "y", n["AP"], "a_z_cmd")
        dg.sig(ay, "y", n["AP"], "a_y_cmd")
        n["AzCmd"], n["AyCmd"] = az, ay
    else:
        seeker_chain(dg, n, True)
        status(dg, n)

    if kind == "intercept":
        plots = [
            {"id": "p1", "title": "Range to target and closest approach (m)",
             "signals": ["Seeker/range", "Status/min_range"]},
            {"id": "p2", "title": "Line-of-sight rates (rad/s)",
             "signals": ["Seeker/los_pitch", "Seeker/los_yaw"]},
            {"id": "p3", "title": "Commanded and achieved acceleration (g)",
             "signals": ["Guide/a_z_cmd", "Aero/n_z", "Aero/n_y"]},
            {"id": "p4", "title": "Angle of attack, sideslip and roll (deg)",
             "signals": ["Air/alpha_deg", "Air/beta_deg", "Air/phi_deg"]},
            {"id": "p5", "title": "Canard deflections (deg)",
             "signals": ["Fin1/y", "Fin2/y", "Fin3/y", "Fin4/y"]},
            {"id": "p6", "title": "Speed, Mach and dynamic pressure",
             "signals": ["Air/vt", "Air/mach", "Air/qbar"]},
        ]
    elif kind == "control":
        plots = [
            {"id": "p1", "title": "Commanded and achieved acceleration (g)",
             "signals": ["AP/a_z_cmd_out", "Aero/n_z", "Aero/n_y"]},
            {"id": "p2", "title": "Canard deflections (deg)",
             "signals": ["Fin1/y", "Fin2/y", "Fin3/y", "Fin4/y"]},
            {"id": "p3", "title": "Angle of attack, sideslip and roll (deg)",
             "signals": ["Air/alpha_deg", "Air/beta_deg", "Air/phi_deg"]},
            {"id": "p4", "title": "Speed, Mach and thrust",
             "signals": ["Air/vt", "Air/mach", "Motor/T"]},
        ]
    else:
        plots = [
            {"id": "p1", "title": "Angle of attack and sideslip (deg)",
             "signals": ["Air/alpha_deg", "Air/beta_deg"]},
            {"id": "p2", "title": "Body rates (deg/s)",
             "signals": ["Air/q_deg", "Air/r_deg", "Air/p_deg"]},
            {"id": "p3", "title": "Canard deflections (deg)",
             "signals": ["Fin1/y", "Fin2/y", "Fin3/y", "Fin4/y"]},
            {"id": "p4", "title": "Speed, Mach and thrust",
             "signals": ["Air/vt", "Air/mach", "Motor/T"]},
        ]
    t_end = 10.0 if kind == "intercept" else 8.0
    params = [dict(g) for g in GLOBALS]
    if kind == "intercept":
        start = {"vt0": d.V_M0, "h0": d.P_M0[2], "alpha0": d.ALPHA0}
    else:
        start = {"vt0": d.V_TEST, "h0": d.H_TEST, "alpha0": 2.0}
    for g in params:
        if g["name"] in start:
            g["value"] = str(start[g["name"]])
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name,
        "$comment": ("AIM-9X Sidewinder: 6-DOF multibond airframe with variable mass, canards and "
                     "two-axis thrust vector control, imaging IR seeker and proportional navigation. "
                     "Generated by design/build_model.py; see the README and the model docs."),
        "diagram": {"nodes": dg.nodes, "connections": dg.conns,
                    "subsystemPorts": [], "annotations": dg.ann},
        "settings": {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": 1e-6,
                     "abstol": 1e-8, "max_step": None,
                     "output": {"mode": "points", "points": int(t_end * 100) + 1},
                     "event_limit": 100000},
        "plots": plots,
        "parameters": params,
        "dashboard": dashboard(kind),
    }
    doc["scene"] = {"file": "scenes/aim9x.sdf"}
    doc["bindings"] = scene_bindings()
    return doc


def scene_bindings() -> list[dict]:
    """Bindings of the missile scene: the attitude, the four canards and the motor plume."""
    out = [
        {"target": "link:missile", "property": "pose",
         "signal": [f"View/m_pose[{k}]" for k in range(1, 8)]},
        {"target": "visual:plume", "property": "scale.x", "signal": "View/plume"},
        {"target": "visual:plume_glow", "property": "visible", "signal": "View/plume"},
    ]
    for k in range(1, 5):
        out.append({"target": f"joint:canard{k}_hinge", "property": "position",
                    "signal": f"Fin{k}/y", "gain": math.pi / 180.0})
    return out


def build_scene() -> str:
    """The SDF of the missile view: the missile at the origin, a cloud deck below and a faint
    reference grid for scale. Generated by design/build_model.py; the meshes are written by
    design/make_meshes.py."""
    out = ['''<?xml version="1.0"?>
<!--
  aim9x: the AIM-9X at the origin, x forward, y left, z up, metres. The body, the fixed tail
  fins and the seeker window are one mesh; the four canards are separate links on their hinge
  axes (joints canard1..4) and turn with Fin1..4/y. The nozzle plume scales with the motor
  thrust. A cloud deck and a faint 16 m reference grid give the scene depth and scale. The
  meshes are written by design/make_meshes.py.
-->
<sdf version="1.9">
  <model name="aim9x">
    <link name="missile">
      <pose>0 0 0 0 0 0</pose>
      <visual name="body">
        <geometry><mesh><uri>meshes/aim9x_missile.glb</uri></mesh></geometry>
      </visual>
      <visual name="plume_glow">
        <pose>-1.50 0 0 0 0 0</pose>
        <geometry><sphere><radius>0.085</radius></sphere></geometry>
        <material><diffuse>1 0.85 0.35 1</diffuse></material>
      </visual>
      <visual name="plume">
        <pose>-1.02 0 0 0 0 0</pose>
        <geometry><mesh><uri>meshes/aim9x_plume.glb</uri></mesh></geometry>
      </visual>
    </link>
''']
    for k, phi in enumerate((45.0, 135.0, 225.0, 315.0), start=1):
        rad = math.radians(phi)
        roll = math.radians(phi - 90.0)
        out.append(
            f'    <link name="canard{k}">\n'
            f'      <pose>1.12 {0.0635 * math.cos(rad):.6g} {0.0635 * math.sin(rad):.6g} {roll:.6g} 0 0</pose>\n'
            f'      <visual name="canard{k}_fin">\n'
            f'        <geometry><mesh><uri>meshes/aim9x_canard.glb</uri></mesh></geometry>\n'
            f'      </visual>\n'
            f'    </link>\n')
    for k in range(1, 5):
        out.append(
            f'    <joint name="canard{k}_hinge" type="revolute">\n'
            f'      <parent>missile</parent>\n      <child>canard{k}</child>\n'
            f'      <axis><xyz>0 0 1</xyz></axis>\n    </joint>\n')
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


def dashboard(kind: str) -> dict:
    cards = [
        {"id": "intro", "kind": "text", "size": "2x1", "title": "AIM-9X Sidewinder",
         "options": {"markdown": True, "text":
                     "A six-degree-of-freedom AIM-9X with **variable mass**, canards, **two-axis "
                     "thrust-vector control**, an imaging IR seeker and **proportional navigation**."}},
        {"id": "v", "kind": "value", "size": "1x1", "title": "Speed", "signals": ["Air/vt"],
         "options": {"decimals": 0, "unit": "m/s"}},
        {"id": "g", "kind": "value", "size": "1x1", "title": "Normal acceleration", "signals": ["Aero/n_z"],
         "options": {"decimals": 1, "unit": "g"}},
    ]
    if kind == "intercept":
        cards += [
            {"id": "r", "kind": "value", "size": "1x1", "title": "Range", "signals": ["Seeker/range"],
             "options": {"decimals": 0, "unit": "m"}},
            {"id": "lock", "kind": "indicator", "size": "1x1", "title": "Seeker lock",
             "signals": ["Seeker/lock"], "options": {"threshold": 0.5}},
            {"id": "n", "kind": "number", "size": "1x1", "title": "PN constant",
             "parameter": "global:nav_N", "options": {"decimals": 1, "unit": ""}},
        ]
    else:
        cards += [
            {"id": "tvc", "kind": "slider", "size": "1x1", "title": "TVC", "parameter": "global:tvc_on",
             "options": {"min": 0.0, "max": 1.0, "step": 1.0, "decimals": 0, "unit": ""}},
            {"id": "dp", "kind": "number", "size": "1x1", "title": "Pitch command",
             "parameter": "global:dp_amp", "options": {"decimals": 1, "unit": "deg"}},
        ]
    return {"autoRerun": False, "cards": cards}


def main() -> int:
    out = {}
    for name, kind in (("aim9x-airframe", "airframe"), ("aim9x-control", "control"),
                       ("aim9x-intercept", "intercept")):
        doc = model(name, kind)
        path = MODELS / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
        out[name] = doc
        print(f"wrote {path} ({len(doc['diagram']['nodes'])} nodes)")
    scene = ROOT / "scenes" / "aim9x.sdf"
    scene.write_text(build_scene(), encoding="utf-8", newline="\n")
    print(f"wrote {scene}")
    (ROOT / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    return 0


def expected() -> dict:
    design = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    air, mot, mode, seek = design["airframe"], design["motor"], design["mode_fit"], design["seeker"]
    no_diag = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
               "note": "no algebraic loop, no causality conflict, no event storm"}
    thrust = {"kind": "cursor_value", "signal": "Motor/T", "t": 1.0, "value": mot["thrust_1"],
              "rtol": 0.001, "note": "mdot c_vac - p_a A_e at 1 s (design/design.py)"}
    mass = {"kind": "cursor_value", "signal": "Motor/m", "t": 4.0, "value": mot["m_f"],
            "abs": 0.02, "note": "m0 minus the area of the flow profile (design/design.py)"}
    airframe = [
        no_diag,
        {"kind": "scene_bindings"},
        {"kind": "cursor_value", "signal": "Aero/CN", "t": 0.0, "value": air["cn"], "abs": 1e-6,
         "note": "cna alpha + CN3 alpha^3 at alpha0 = 2 deg (design/design.py)"},
        {"kind": "cursor_value", "signal": "Aero/n_z", "t": 0.0, "value": air["nz"], "rtol": 1e-4,
         "note": "qbar S CN / (m g0) at the start (design/design.py)"},
        {"kind": "cursor_value", "signal": "Air/qbar", "t": 0.0, "value": air["qbar"], "rtol": 1e-6,
         "note": "0.5 rho v^2 at 3000 m, 600 m/s (design/design.py)"},
        thrust, mass,
        {"kind": "damping", "signal": "Air/alpha_deg", "from_t": 1.2, "to_t": 3.8,
         "offset": "constant", "zeta": mode["zeta"], "zeta_abs": 0.06,
         "wn": mode["wn"], "wn_rtol": 0.2,
         "note": "short period after the 0.2 deg pitch doublet; the linearised mode is "
                 f"{mode['zeta']:.3f} at {mode['wn']:.2f} rad/s (design/design.py)"},
        {"kind": "max_abs_le", "signal": "Air/alpha_deg", "value": 20.0,
         "note": "the 0.2 deg doublet keeps the airframe in the linear range"},
        {"kind": "max_abs_le", "signal": "Fin1/y", "value": 25.0},
        {"kind": "max_abs_le", "signal": "Fin4/y", "value": 25.0},
    ]
    control = [
        no_diag,
        {"kind": "scene_bindings"},
        {"kind": "max_abs_le", "signal": "AP/dp", "value": 16.0001,
         "note": "virtual pitch command limit"},
        {"kind": "max_abs_le", "signal": "AP/dy", "value": 16.0001},
        {"kind": "max_abs_le", "signal": "AP/dr", "value": 12.0001},
        {"kind": "max_abs_le", "signal": "Air/alpha_deg", "value": 10.0,
         "note": "the 40 m/s^2 command stays well inside the 30 deg command limit"},
        {"kind": "max_abs_le", "signal": "Air/beta_deg", "value": 5.0},
        {"kind": "max_abs_le", "signal": "Air/phi_deg", "value": 2.0,
         "note": "the roll loop holds wings level"},
        {"kind": "max_abs_le", "signal": "Fin1/y", "value": 25.0},
        {"kind": "max_abs_le", "signal": "Fin4/y", "value": 25.0},
        {"kind": "max_abs_le", "signal": "AP/tvc_p", "value": 0.140,
         "note": "TVC gimbal inside its 8 deg stop"},
        {"kind": "max_abs_le", "signal": "AP/tvc_y", "value": 0.140},
        {"kind": "max_abs_le", "signal": "Aero/n_z", "value": 10.0},
        {"kind": "min_ge", "signal": "Aero/n_z", "from_t": 1.5, "to_t": 2.0, "value": 0.3,
         "note": "the acceleration command builds load factor"},
        thrust, mass,
    ]
    intercept = [
        no_diag,
        {"kind": "scene_bindings"},
        {"kind": "cursor_value", "signal": "Seeker/range", "t": 0.0, "value": seek["range"],
         "abs": 1.0, "note": "Euclidean launch range (design/design.py)"},
        {"kind": "cursor_value", "signal": "Seeker/ir_target", "t": 0.0, "value": seek["ir"],
         "rtol": 0.01, "note": "I r^-2 exp(-k r) with the rear-aspect intensity (design/design.py)"},
        {"kind": "ratio", "signal": "Guide/pn_gain", "signal_b": "Guide/vc_out", "t": 0.5,
         "value": 4.0, "rtol": 1e-6, "note": "pn_gain = N V_c: the PN law's gain"},
        {"kind": "max_abs_le", "signal": "Air/alpha_deg", "value": 30.0},
        {"kind": "max_abs_le", "signal": "Air/beta_deg", "value": 20.0},
        {"kind": "max_abs_le", "signal": "Fin1/y", "value": 25.0},
        {"kind": "max_abs_le", "signal": "Fin4/y", "value": 25.0},
        {"kind": "final_value", "signal": "Status/min_range", "t": 3.29, "value": 18.0, "abs": 5.0,
         "note": "closest approach at the fuze event; the unfuzed trajectory passes inside 13 m"},
        {"kind": "max_abs_le", "signal": "Status/fuze", "value": 1.0,
         "note": "the proximity fuze fires"},
        {"kind": "max_abs_le", "signal": "Status/hit", "value": 1.0,
         "note": "the target is inside the warhead's lethal radius"},
        {"kind": "cursor_value", "signal": "Motor/T", "t": 1.0, "value": mot["thrust_1_launch"],
         "rtol": 0.001, "note": "mdot c_vac - p_a A_e at 6040 m (design/design.py)"},
    ]
    return {"project": "aim9x",
            "description": "AIM-9X Sidewinder: open-loop airframe, rate-command autopilot with TVC, and the full "
                           "seeker / proportional-navigation intercept. Analytic reference values from "
                           "design/design.py.",
            "models": {"aim9x-airframe": {"checks": airframe},
                       "aim9x-control": {"checks": control},
                       "aim9x-intercept": {"checks": intercept}}}


if __name__ == "__main__":
    sys.exit(main())
