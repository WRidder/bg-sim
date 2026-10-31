# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.11"]
# ///
"""Generate the model documents and the 3D scene of the `gripper` example from `design.py`.

    uv run examples/gripper/design/build_model.py

writes `models/ball-gripper.bgmodel.json`, `models/block-gripper.bgmodel.json` and
`scenes/gripper.sdf`. The diagrams are plain node/connection lists, so they are generated: the
contact elements, their mounts and their carrier wiring repeat a lot.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design as d  # noqa: E402

ROOT = HERE.parent

# The table top (world x, y of its centre and half-widths, m): the contact face and the 3D view
# share it, so a dropped part rolls off the drawn edge.
TABLE_TOP = (-0.03, 0.2, 0.23, 0.38)
TABLE_FACE = {"ox": TABLE_TOP[0], "oy": TABLE_TOP[1], "w1": TABLE_TOP[2], "w2": TABLE_TOP[3]}


def fmt(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(fmt(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return f"{v}.0"
    r = f"{v:.10g}"
    if "e" not in r and "." not in r:
        r += ".0"
    return r


class Doc:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self._n = 0
        self._c = 0

    def node(self, name, ref, x, y, params=None, starts=None, color=None) -> str:
        self._n += 1
        nid = f"n{self._n:02d}"
        self.nodes.append({
            "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": x, "y": y},
            "rotation": 0, "flipX": False,
            "params": {k: fmt(v) for k, v in (params or {}).items()},
            "constants": {},
            "starts": {k: fmt(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": color},
        })
        return nid

    def conn(self, kind, a, ap, b, bp, label=None) -> None:
        self._c += 1
        self.conns.append({"id": f"{kind[0]}{self._c:02d}", "kind": kind, "from": {"node": a, "port": ap},
                           "to": {"node": b, "port": bp}, "route": [], "label": label})

    def sig(self, a, ap, b, bp, label=None):
        self.conn("signal", a, ap, b, bp, label)

    def bond(self, a, ap, b, bp):
        self.conn("bond", a, ap, b, bp)

    def wire(self, a, ap, b, bp):
        self.conn("wire", a, ap, b, bp)


def contact_params(c: dict, **geom) -> dict:
    p = {k: c[k] for k in ("k", "xref", "c", "mu", "vs", "eps", "feps")}
    p.update(geom)
    return p


def drive_train(doc: Doc, x0: float, y0: float, F_set: float, ctrl_extra: dict | None = None) -> tuple[str, str, str, str]:
    """Motor (current loop) -> gearhead -> lead screw -> wedge hook -> jaw node (both jaws).

    Returns (jaw-node anchor block, position sensor, velocity sensor, controller)."""
    ctrl = doc.node("Ctrl", "project:GripController", x0, y0 + 160,
                    params={**d.CTRL, "F_set": F_set, "k_t": d.K_T, "G": d.G_IDEAL, "eta": d.ETA, "I_max": d.I_MAX,
                            **(ctrl_extra or {})})
    motor = doc.node("Motor", "stdlib:drives/CurrentControlledDrive", x0 + 200, y0,
                     params={"k_t": d.K_T, "J_m": d.J_M, "b_m": d.B_M}, color="#5b8def")
    gear = doc.node("Gearhead", "stdlib:rotation/IdealGear", x0 + 380, y0, params={"n": d.N_GEAR})
    screw = doc.node("Spindle", "project:LeadScrew", x0 + 560, y0,
                     params={"lead": d.LEAD, "eta": d.ETA, "eta_back": d.ETA_BACK, "w_eps": d.W_EPS})
    wedge = doc.node("Wedge", "project:WedgeHook", x0 + 740, y0, params={"i_w": d.I_W})
    guide = doc.node("Guides", "project:JawGuides", x0 + 920, y0 - 120, params=d.GUIDE)
    gnd = doc.node("Frame", "stdlib:translation/Fixed", x0 + 1100, y0 - 120)
    xs = doc.node("JawPos", "stdlib:converters/PositionSensor", x0 + 920, y0 + 120)
    vs = doc.node("JawVel", "stdlib:converters/VelocitySensor", x0 + 740, y0 + 160)
    doc.sig(ctrl, "i_ref", motor, "i_ref")
    doc.wire(motor, "shaft", gear, "a")
    doc.wire(gear, "b", screw, "a")
    doc.wire(screw, "b", wedge, "a")
    doc.wire(wedge, "b", guide, "a")
    doc.wire(guide, "b", gnd, "a")
    doc.wire(wedge, "b", xs, "a")
    doc.wire(wedge, "b", vs, "a")
    doc.sig(xs, "y", ctrl, "x")
    doc.sig(vs, "y", ctrl, "v")
    return wedge, xs, vs, ctrl


def carriage(doc: Doc, x0: float, y0: float, z0: float) -> str:
    prof = {}
    for i, (name, spec) in enumerate((("Lift", d.LIFT), ("Transfer", d.TRANSFER), ("Lower", d.LOWER),
                                      ("Retreat", d.RETREAT))):
        prof[name] = doc.node(name, "stdlib:motion/SCurveProfile", x0, y0 + 110 * i,
                              params={"q_start": 0.0, **spec})
    car = doc.node("Carriage", "project:Carriage", x0 + 220, y0 + 160, params={"x0": 0.0, "y0": 0.0, "z0": z0})
    for p, pre in (("Transfer", "y"), ("Lift", "z1"), ("Lower", "z2"), ("Retreat", "z3")):
        doc.sig(prof[p], "q", car, f"{pre}q")
        doc.sig(prof[p], "v", car, f"{pre}v")
        doc.sig(prof[p], "a", car, f"{pre}a")
    return car


def common_settings(t_end: float) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "Rodas5P", "reltol": 1e-6, "abstol": 1e-9,
            "max_step": None, "output": {"mode": "points", "points": int(round(t_end * 1000)) + 1},
            "event_limit": 100000}


# ----------------------------------------------------------------------------- ball model
def build_ball() -> dict:
    doc = Doc()
    R = d.BALL_R
    jaw, xs, vs, ctrl = drive_train(doc, 40, 140, d.F_SIZED)
    car = carriage(doc, 40, 520, d.BALL_Z0)
    body = doc.node("Ball", "stdlib:spatial/RigidBody3D", 900, 620,
                    params={"m": d.BALL_M, "J": [d.BALL_J] * 3, "g0": d.G0},
                    starts={"inertia/P": [0.0] * 6}, color="#9aa4b1")
    pose = doc.node("BallPose", "stdlib:multibond/PoseIntegrator3D", 900, 780,
                    starts={"qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "px": 0.0, "py": 0.0, "pz": d.BALL_Z0})
    doc.sig(body, "V", pose, "tw")
    doc.sig(pose, "g", body, "g")
    jaws = {}
    for side, sx, y in (("A", 1.0, 480), ("B", -1.0, 620)):
        m = doc.node(f"Mount{side}", "stdlib:multibond/FixedTransform3DNeutral", 1100, y)
        c = doc.node(f"Jaw{side}", "stdlib:contact/MovingPlaneContact", 1300, y,
                     params=contact_params(d.PAD, r=R, ox=sx * (R + d.GAP), oy=0.0, oz=0.0,
                                           nx=-sx, ny=0.0, nz=0.0, tx=0.0, ty=1.0, tz=0.0,
                                           ax=-sx, ay=0.0, az=0.0, w1=d.PAD_W, w2=d.PAD_W, we=d.PAD_WE),
                     color="#e0a030")
        doc.bond(body, "p", m, "b")
        doc.bond(m, "a", c, "p")
        doc.wire(jaw, "b", c, "j")
        doc.sig(pose, "g", c, "g")
        doc.sig(car, "pc", c, "pc")
        doc.sig(car, "vc", c, "vc")
        doc.sig(xs, "y", c, "xs")
        jaws[side] = c
    # the table (one fixed face under the source and the target)
    tm = doc.node("MountT", "stdlib:multibond/FixedTransform3DNeutral", 1100, 780)
    tc = doc.node("Table", "stdlib:contact/MovingPlaneContact", 1300, 780,
                  params=contact_params(d.TABLE, r=R, **TABLE_FACE, oz=0.0, nx=0.0, ny=0.0, nz=1.0,
                                        tx=1.0, ty=0.0, tz=0.0, ax=0.0, ay=0.0, az=1.0))
    tcar = doc.node("TableFrame", "project:StaticCarrier", 1100, 900)
    tgnd = doc.node("TableFixed", "stdlib:translation/Fixed", 1500, 860)
    doc.bond(body, "p", tm, "b")
    doc.bond(tm, "a", tc, "p")
    doc.wire(tc, "j", tgnd, "a")
    doc.sig(pose, "g", tc, "g")
    doc.sig(tcar, "pc", tc, "pc")
    doc.sig(tcar, "vc", tc, "vc")
    doc.sig(tcar, "xs", tc, "xs")
    mon = doc.node("Grip", "project:GripMonitor", 1560, 560,
                   params={"m": d.BALL_M, "mu": d.MU, "S": d.S_SAFETY, "g0": d.G0, "d_hold": 0.002, "s_th": d.SLIP_S_TH,
                           "Fg0": 2.0}, color="#3fae6a")
    doc.sig(pose, "g", mon, "g")
    doc.sig(car, "pc", mon, "pc")
    doc.sig(car, "ac", mon, "ac")
    for side in ("A", "B"):
        doc.sig(jaws[side], "F", mon, f"F{side}")
        doc.sig(jaws[side], "f_n", mon, f"fn{side}")
        doc.sig(jaws[side], "slip", mon, f"slip{side}")
    doc.sig(ctrl, "cmd", mon, "cmd")

    plots = [
        {"id": "p1", "title": "Grip force per jaw vs required force (N): S = 1 and with the safety factor S = 2",
         "signals": ["Grip/F_grip", "Grip/F_req", "Grip/F_reqS", "Ctrl/F_cmd"]},
        {"id": "p2", "title": "Friction the jaws deliver vs what the ball needs, m|a - g| (N)",
         "signals": ["Grip/demand", "Grip/need", "Grip/cap"]},
        {"id": "p3", "title": "Ball position relative to the jaws (m) and slip distance",
         "signals": ["Grip/dy", "Grip/dz", "Grip/slipd"]},
        {"id": "p4", "title": "Slip speed at the jaws (m/s)", "signals": ["JawA/slip", "JawB/slip", "Grip/slipv"]},
        {"id": "p5", "title": "Motor current (A) and grip current limit", "signals": ["Motor/isense/y", "Ctrl/I_grip", "Ctrl/I_lim"]},
        {"id": "p6", "title": "Carriage acceleration (m/s^2): horizontal and vertical",
         "signals": ["Carriage/a_h", "Carriage/a_v"]},
        {"id": "p7", "title": "Jaw travel (m) and closing speed (m/s)", "signals": ["JawPos/y", "JawVel/y", "Ctrl/v_ref"]},
        {"id": "p8", "title": "Contact forces (N): jaws and table", "signals": ["JawA/f_n", "JawB/f_n", "Table/f_n"]},
    ]
    bindings = [
        {"target": "link:ball", "property": "pose",
         "signal": [f"BallPose/g[{i}]" for i in range(1, 8)]},
        {"target": "link:gripper", "property": "pose",
         "signal": [f"Carriage/pose[{i}]" for i in range(1, 8)]},
        {"target": "joint:slide_a", "property": "position", "signal": "JawPos/y", "gain": 1.0, "offset": 0.0},
        {"target": "joint:slide_b", "property": "position", "signal": "JawPos/y", "gain": 1.0, "offset": 0.0},
        {"target": "visual:pad_a", "property": "color", "signal": "JawA/util", "colormap": "coolwarm",
         "range": [0.0, 1.0]},
        {"target": "visual:pad_b", "property": "color", "signal": "JawB/util", "colormap": "coolwarm",
         "range": [0.0, 1.0]},
        {"target": "visual:led", "property": "color", "signal": "Grip/holds", "colormap": "coolwarm",
         "range": [1.0, 0.0]},
    ]
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "ball-gripper",
        "$comment": "Parallel-jaw gripper holding a steel ball during a fast pick-and-place move. Generated by design/build_model.py from design/design.py; see the README.",
        "diagram": {"nodes": doc.nodes, "connections": doc.conns, "subsystemPorts": [], "annotations": []},
        "settings": common_settings(d.T_END),
        "plots": plots,
        "scene": {"file": "scenes/gripper.sdf"},
        "bindings": bindings,
        "dashboard": ball_dashboard(),
    }


def ball_dashboard() -> dict:
    """Sliders for the grip-force setting, the transfer acceleration and the closing speed at the
    part; the holds light, the time of the first slip (alarm zone), the grip force at the slip,
    the grip current, and the force and friction plots."""
    return {
        "autoRerun": True,
        "cards": [
            {"id": "holds", "kind": "indicator", "size": "1x1", "title": "Ball holds",
             "signals": ["Grip/holds"], "options": {"threshold": 0.5, "onWhen": "above"}},
            {"id": "tslip", "kind": "value", "size": "1x1", "title": "First slip at (0: none)",
             "signals": ["Grip/t_slip"], "options": {"decimals": 3, "unit": "s",
                                                     "zones": [{"from": 0, "to": 1e-6, "tone": "good"},
                                                               {"from": 1e-6, "to": 1000, "tone": "bad"}]}},
            {"id": "fslip", "kind": "value", "size": "1x1", "title": "Grip force at the slip (0: none)",
             "signals": ["Grip/F_slip"], "options": {"decimals": 1, "unit": "N"}},
            {"id": "igrip", "kind": "value", "size": "1x1", "title": "Grip current",
             "signals": ["Ctrl/I_grip"], "options": {"decimals": 3, "unit": "A"}},
            {"id": "fset", "kind": "slider", "size": "2x1", "title": "Grip-force setting per jaw (N)",
             "parameter": "Ctrl/F_set", "options": {"min": 4, "max": 100, "step": 1, "decimals": 0, "unit": "N"}},
            {"id": "atr", "kind": "slider", "size": "2x1", "title": "Transfer acceleration (m/s²)",
             "parameter": "Transfer/a_max", "options": {"min": 2, "max": 40, "step": 1, "decimals": 0, "unit": "m/s²"}},
            {"id": "vgrip", "kind": "slider", "size": "2x1", "title": "Closing speed at the part (m/s)",
             "parameter": "Ctrl/v_grip", "options": {"min": 0.002, "max": 0.03, "step": 0.001, "decimals": 3,
                                                     "unit": "m/s"}},
            {"id": "intro", "kind": "text", "size": "2x1", "title": "Grip force sizing",
             "options": {"markdown": True, "text": (
                 f"Required per jaw: **F = m·sqrt((g + a_v)² + a_h²) / (2μ)**, with S = {d.S_SAFETY:g}. "
                 f"Sized setting {d.F_SIZED} N. Lower the setting or raise the transfer acceleration: "
                 "the ball slips in the jaws (at 8 N it falls out in the transfer), the light goes out "
                 "and the first-slip time shows an alarm.")}},
            {"id": "force", "kind": "plot", "size": "4x2", "title": "Grip force vs requirement (N)",
             "signals": ["Grip/F_grip", "Grip/F_req", "Grip/F_reqS", "Ctrl/F_cmd"]},
            {"id": "fric", "kind": "plot", "size": "4x2", "title": "Friction demand vs capacity (N)",
             "signals": ["Grip/demand", "Grip/need", "Grip/cap"]},
        ],
    }


# ----------------------------------------------------------------------------- block model
def build_block() -> dict:
    """The aluminium block, gripped BLOCK_E above its centre of mass: four point contacts per
    flat pad (at +-PAD_PT in y and z around the grip line) and four on the table (the bottom
    corners). Sized with the tilting moment (BLOCK_F_SIZED); the dashboard and the checks also
    run it at the force-only size, where the transfer swings the block in the grip."""
    doc = Doc()
    hx, hy, hz = (s / 2 for s in d.BLOCK)
    e, pt = d.BLOCK_E, d.PAD_PT
    jaw, xs, vs, ctrl = drive_train(doc, 40, 140, d.BLOCK_F_SIZED, d.BLOCK_CTRL)
    car = carriage(doc, 40, 520, d.BLOCK_Z0 + e)
    body = doc.node("Block", "stdlib:spatial/RigidBody3D", 900, 620,
                    params={"m": d.BLOCK_M, "J": list(d.BLOCK_J), "g0": d.G0},
                    starts={"inertia/P": [0.0] * 6}, color="#9aa4b1")
    pose = doc.node("BlockPose", "stdlib:multibond/PoseIntegrator3D", 900, 780,
                    starts={"qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "px": 0.0, "py": 0.0, "pz": d.BLOCK_Z0})
    doc.sig(body, "V", pose, "tw")
    doc.sig(pose, "g", body, "g")

    def point_contact(name, off, x, y, params, carrier, slide):
        """A MovingPlaneContact at the body point `off` (CoM frame): local pose, composed world
        pose, the neutral mount (child = body at -off in the point frame) and the contact."""
        loc = doc.node(f"L{name}", "stdlib:spatial/LocalPose3D", x - 400, y,
                       params={"x": off[0], "y": off[1], "z": off[2]})
        comp = doc.node(f"G{name}", "stdlib:multibond/ComposePose3D", x - 200, y)
        mnt = doc.node(f"M{name}", "stdlib:multibond/FixedTransform3DNeutral", x - 200, y + 60,
                       params={"x": -off[0], "y": -off[1], "z": -off[2]})
        c = doc.node(name, "stdlib:contact/MovingPlaneContact", x, y, params=params, color="#e0a030")
        doc.sig(pose, "g", comp, "gp")
        doc.sig(loc, "g", comp, "gl")
        doc.sig(comp, "g", c, "g")
        doc.bond(body, "p", mnt, "b")
        doc.bond(mnt, "a", c, "p")
        doc.sig(carrier, "pc", c, "pc")
        doc.sig(carrier, "vc", c, "vc")
        if slide is None:
            doc.sig(xs, "y", c, "xs")
            doc.wire(jaw, "b", c, "j")
        else:
            doc.sig(carrier, "xs", c, "xs")
            doc.wire(c, "j", slide, "a")
        return c

    pads = {}
    for side, sx, y0 in (("A", 1.0, 60), ("B", -1.0, 660)):
        params = contact_params(d.PAD_BLOCK, r=0.0, ox=sx * (hx + d.GAP), oy=0.0, oz=0.0,
                                nx=-sx, ny=0.0, nz=0.0, tx=0.0, ty=1.0, tz=0.0,
                                ax=-sx, ay=0.0, az=0.0, w1=d.PAD_W, w2=d.PAD_W, we=d.PAD_WE)
        cs = []
        for k, (py, pz) in enumerate(((-pt, -pt), (pt, -pt), (pt, pt), (-pt, pt)), start=1):
            cs.append(point_contact(f"Jaw{side}{k}", (sx * hx, py, e + pz), 1700, y0 + 140 * (k - 1), params, car, None))
        s = doc.node(f"Pad{side}", "project:PadSum", 1950, y0 + 200,
                     params={"mu": d.PAD_BLOCK["mu"], "nx": -sx, "ny": 0.0, "nz": 0.0})
        for k, c in enumerate(cs, start=1):
            doc.sig(c, "F", s, f"F{k}")
            doc.sig(c, "f_n", s, f"fn{k}")
            doc.sig(c, "slip", s, f"s{k}")
            doc.sig(c, "util", s, f"u{k}")
        pads[side] = s
    tcar = doc.node("TableFrame", "project:StaticCarrier", 1300, 1300)
    tgnd = doc.node("TableFixed", "stdlib:translation/Fixed", 1900, 1300)
    tparams = contact_params(d.TABLE, r=0.0, **TABLE_FACE, oz=0.0, nx=0.0, ny=0.0, nz=1.0,
                             tx=1.0, ty=0.0, tz=0.0, ax=0.0, ay=0.0, az=1.0)
    tables = []
    for k, (px, py) in enumerate(((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)), start=1):
        tables.append(point_contact(f"Table{k}", (px, py, -hz), 1700, 1260 + 140 * (k - 1), tparams, tcar, tgnd))
    mon = doc.node("Grip", "project:GripMonitor", 2200, 560,
                   params={"m": d.BLOCK_M, "mu": d.PAD_BLOCK["mu"], "S": d.S_SAFETY, "g0": d.G0, "d_hold": 0.002,
                           "s_th": d.SLIP_S_TH, "Fg0": 2.0, "ez": e, "kM": e / d.PAD_R}, color="#3fae6a")
    doc.sig(pose, "g", mon, "g")
    doc.sig(car, "pc", mon, "pc")
    doc.sig(car, "ac", mon, "ac")
    for side in ("A", "B"):
        doc.sig(pads[side], "F", mon, f"F{side}")
        doc.sig(pads[side], "f_n", mon, f"fn{side}")
        doc.sig(pads[side], "slip", mon, f"slip{side}")
    doc.sig(ctrl, "cmd", mon, "cmd")

    plots = [
        {"id": "p1", "title": "Grip force per jaw vs required force with the tilting moment (N): S = 1 and S = 2",
         "signals": ["Grip/F_grip", "Grip/F_req", "Grip/F_reqS", "Ctrl/F_cmd"]},
        {"id": "p2", "title": "Block tilt in the grip (rad) and slip distance of its centre of mass (m)",
         "signals": ["Grip/tilt", "Grip/slipd"]},
        {"id": "p3", "title": "Pad friction utilisation |F_t|/(mu f_n)", "signals": ["PadA/util", "PadB/util"]},
        {"id": "p4", "title": "Point contact normal forces, jaw A (N): the moment shifts load between top and bottom",
         "signals": ["JawA1/f_n", "JawA2/f_n", "JawA3/f_n", "JawA4/f_n"]},
        {"id": "p5", "title": "Carriage acceleration (m/s^2): horizontal and vertical",
         "signals": ["Carriage/a_h", "Carriage/a_v"]},
        {"id": "p6", "title": "Motor current (A) and grip current limit", "signals": ["Motor/isense/y", "Ctrl/I_grip", "Ctrl/I_lim"]},
    ]
    bindings = [
        {"target": "link:part", "property": "pose", "signal": [f"BlockPose/g[{i}]" for i in range(1, 8)]},
        {"target": "link:gripper", "property": "pose", "signal": [f"Carriage/pose[{i}]" for i in range(1, 8)]},
        {"target": "joint:slide_a", "property": "position", "signal": "JawPos/y", "gain": 1.0, "offset": 0.0},
        {"target": "joint:slide_b", "property": "position", "signal": "JawPos/y", "gain": 1.0, "offset": 0.0},
        {"target": "visual:pad_a", "property": "color", "signal": "PadA/util", "colormap": "coolwarm",
         "range": [0.0, 1.0]},
        {"target": "visual:pad_b", "property": "color", "signal": "PadB/util", "colormap": "coolwarm",
         "range": [0.0, 1.0]},
        {"target": "visual:led", "property": "color", "signal": "Grip/holds", "colormap": "coolwarm",
         "range": [1.0, 0.0]},
    ]
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "block-gripper",
        "$comment": "The parallel-jaw gripper holding an aluminium block above its centre of mass: the tilting moment of the transfer. Generated by design/build_model.py from design/design.py; see the README.",
        "diagram": {"nodes": doc.nodes, "connections": doc.conns, "subsystemPorts": [], "annotations": []},
        "settings": common_settings(d.T_END),
        "plots": plots,
        "scene": {"file": "scenes/gripper-block.sdf"},
        "bindings": bindings,
    }


# ----------------------------------------------------------------------------- 3D scene
def _visual(name, geometry, pose, rgba):
    x, y, z, roll, pitch, yaw = pose
    return (
        f'      <visual name="{name}">\n'
        f'        <pose>{x:.5g} {y:.5g} {z:.5g} {roll:.7g} {pitch:.7g} {yaw:.7g}</pose>\n'
        f'        <geometry>{geometry}</geometry>\n'
        f'        <material><diffuse>{rgba}</diffuse></material>\n'
        f'      </visual>\n'
    )


def _box(sx, sy, sz):
    return f"<box><size>{sx:.5g} {sy:.5g} {sz:.5g}</size></box>"


def _cyl(r, h):
    return f"<cylinder><radius>{r:.5g}</radius><length>{h:.5g}</length></cylinder>"


def _sph(r):
    return f"<sphere><radius>{r:.5g}</radius></sphere>"


def build_scene(part: str = "ball") -> str:
    R = d.BALL_R
    half = R if part == "ball" else d.BLOCK[0] / 2
    o = half + d.GAP                   # jaw face at the open position (carriage frame)
    H = math.pi / 2
    out = ['''<?xml version="1.0"?>
<!--
  gripper: a parallel-jaw gripper on a pick-and-place carriage, moving a part (PART) from the
  source (y = 0) to the target (y = 0.4 m). Generated by design/build_model.py from design/design.py.

  Z-up, metres. The table top is z = 0. Link "gripper" is the carriage: its origin is the gripping
  point between the jaw faces, its pose is bound to Carriage/pose (it only translates). The jaws
  "jaw_a" (at +x, closing towards -x) and "jaw_b" (at -x, closing towards +x) are children of the
  gripper on the prismatic joints "slide_a"/"slide_b", bound to the jaw closing travel JawPos/y
  (0 = open). The jaw pads
  "pad_a"/"pad_b" are coloured by the friction utilisation |F_t|/(mu f_n) (blue: far from slipping,
  red: sliding); the status light "led" by Grip/holds. Link "LINK" is bound to the part pose.
-->
<sdf version="1.9">
  <model name="gripper">
    <link name="world_fixed">
      <pose>0 0 0 0 0 0</pose>
''']
    out[0] = out[0].replace("PART", "a 50 mm steel ball" if part == "ball" else "a 40 x 40 x 80 mm aluminium block")
    out[0] = out[0].replace("LINK", "ball" if part == "ball" else "part")
    # table, source and target fixtures
    cx, cy, hx, hy = TABLE_TOP
    out.append(_visual("table_top", _box(2 * hx, 2 * hy, 0.025), (cx, cy, -0.0125, 0, 0, 0), "0.66 0.68 0.7 1"))
    out.append(_visual("table_frame", _box(2 * hx - 0.04, 2 * hy - 0.04, 0.04), (cx, cy, -0.045, 0, 0, 0),
                       "0.3 0.32 0.36 1"))
    for i, yy in enumerate((0.0, 0.4)):
        tag = "source" if i == 0 else "target"
        rgba = "0.2 0.5 0.85 1" if i == 0 else "0.2 0.68 0.4 1"
        out.append(_visual(f"{tag}_plate", _box(0.11, 0.11, 0.002), (0, yy, 0.001, 0, 0, 0), rgba))
        out.append(_visual(f"{tag}_ring", _cyl(0.031, 0.0025), (0, yy, 0.0013, 0, 0, 0), "0.92 0.92 0.9 1"))
        out.append(_visual(f"{tag}_dot", _cyl(0.026, 0.003), (0, yy, 0.0015, 0, 0, 0), rgba))
    # gantry: two posts and a beam along y above the move
    z_grip = d.BALL_Z0 if part == "ball" else d.BLOCK_Z0 + d.BLOCK_E
    zb = z_grip + d.LIFT["q_end"] + 0.24
    frame = "0.5 0.53 0.58 1"          # anodised aluminium profile: readable on light and dark
    out.append(_visual("post_a", _box(0.03, 0.03, zb + 0.04), (-0.2, -0.16, (zb - 0.04) / 2, 0, 0, 0), frame))
    out.append(_visual("post_b", _box(0.03, 0.03, zb + 0.04), (-0.2, 0.56, (zb - 0.04) / 2, 0, 0, 0), frame))
    out.append(_visual("beam", _box(0.04, 0.75, 0.04), (-0.18, 0.2, zb, 0, 0, 0), frame))
    out.append(_visual("rail", _box(0.01, 0.72, 0.012), (-0.155, 0.2, zb + 0.008, 0, 0, 0), "0.85 0.6 0.2 1"))
    out.append("    </link>\n")
    # the carriage + gripper body (origin = gripping point)
    out.append('\n    <link name="gripper">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_visual("slide", _box(0.07, 0.07, 0.03), (-0.11, 0, 0.26, 0, 0, 0), "0.3 0.32 0.36 1"))
    out.append(_visual("z_column", _box(0.03, 0.05, 0.22), (-0.09, 0, 0.16, 0, 0, 0), "0.75 0.77 0.8 1"))
    out.append(_visual("flange", _cyl(0.035, 0.012), (0.0, 0, 0.124, 0, 0, 0), "0.62 0.64 0.67 1"))
    out.append(_visual("flange_arm", _box(0.09, 0.03, 0.012), (-0.045, 0, 0.124, 0, 0, 0), "0.62 0.64 0.67 1"))
    out.append(_visual("housing", _box(0.15, 0.056, 0.07), (0, 0, 0.083, 0, 0, 0), "0.2 0.33 0.55 1"))
    out.append(_visual("housing_cap", _box(0.152, 0.058, 0.008), (0, 0, 0.12, 0, 0, 0), "0.14 0.15 0.17 1"))
    out.append(_visual("motor_can", _cyl(0.016, 0.05), (0.0, 0.0, 0.143, 0, 0, 0), "0.14 0.15 0.17 1"))
    out.append(_visual("guide", _box(0.15, 0.03, 0.012), (0, 0, 0.042, 0, 0, 0), "0.78 0.8 0.84 1"))
    out.append(_visual("label_strip", _box(0.09, 0.001, 0.012), (0, -0.0285, 0.09, 0, 0, 0), "0.9 0.9 0.92 1"))
    out.append(_visual("led", _sph(0.006), (0.058, -0.029, 0.1, 0, 0, 0), "0.3 0.9 0.4 1"))
    out.append("    </link>\n")
    for side, sx in (("a", 1.0), ("b", -1.0)):
        out.append(f'\n    <link name="jaw_{side}">\n      <pose>0 0 0 0 0 0</pose>\n')
        # carriage block on the guide, finger down to the pad; face at x = sx * o at travel 0
        out.append(_visual(f"carriage_{side}", _box(0.03, 0.04, 0.02), (sx * (o + 0.018), 0, 0.03, 0, 0, 0), "0.78 0.8 0.84 1"))
        out.append(_visual(f"finger_{side}", _box(0.012, 0.016, 0.05), (sx * (o + 0.013), 0, 0.006, 0, 0, 0), "0.7 0.72 0.75 1"))
        out.append(_visual(f"pad_{side}", _box(0.007, 2 * d.PAD_W, 2 * d.PAD_W), (sx * (o + 0.0035), 0, 0, 0, 0, 0), "0.2 0.4 0.85 1"))
        out.append("    </link>\n")
    if part == "ball":
        out.append('\n    <link name="ball">\n      <pose>0 0 0 0 0 0</pose>\n')
        out.append(_visual("sphere", _sph(R), (0, 0, 0, 0, 0, 0), "0.82 0.84 0.88 1"))
        out.append(_visual("mark", _cyl(R * 1.002, 0.002), (0, 0, 0, H, 0, 0), "0.35 0.37 0.4 1"))
    else:
        bx, by, bz = d.BLOCK
        out.append('\n    <link name="part">\n      <pose>0 0 0 0 0 0</pose>\n')
        out.append(_visual("block", _box(bx, by, bz), (0, 0, 0, 0, 0, 0), "0.9 0.48 0.2 1"))
        # anodised orange; a dark band at the grip line and a dark mark at the centre of mass show the tilt
        out.append(_visual("grip_band", _box(bx * 1.004, by * 1.004, 0.003), (0, 0, d.BLOCK_E, 0, 0, 0),
                           "0.3 0.32 0.36 1"))
        out.append(_visual("com_mark", _cyl(0.006, bx * 1.01), (0, 0, 0, 0, H, 0), "0.15 0.16 0.18 1"))
    out.append("    </link>\n")
    for side, sx in (("a", 1.0), ("b", -1.0)):
        out.append(
            f'\n    <joint name="slide_{side}" type="prismatic">\n      <parent>gripper</parent>\n'
            f'      <child>jaw_{side}</child>\n      <axis><xyz>{-sx:.0f} 0 0</xyz></axis>\n    </joint>\n')
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


def main() -> int:
    models = ROOT / "models"
    models.mkdir(exist_ok=True)
    (ROOT / "scenes").mkdir(exist_ok=True)
    for name, doc in (("ball-gripper", build_ball()), ("block-gripper", build_block())):
        path = models / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path} ({len(doc['diagram']['nodes'])} nodes, {len(doc['diagram']['connections'])} connections)")
    for name, part in (("gripper.sdf", "ball"), ("gripper-block.sdf", "block")):
        sdf = ROOT / "scenes" / name
        sdf.write_text(build_scene(part), encoding="utf-8", newline="\n")
        print(f"wrote {sdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
