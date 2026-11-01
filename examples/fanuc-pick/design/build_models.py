# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the models of the fanuc-pick example (`models/*.bgmodel.json`, `bgsim.project.json`).

    uv run examples/fanuc-pick/design/build_models.py

One plant per parcel kind, every scenario the same diagram with other global values (the worker
compiles each structure once):

* `box`      a carton as one rigid body (size, mass, adjustable centre of mass);
* `sphere`   a carton shell with a loose sphere inside (`SphereInBox`);
* `cylinder` a carton shell with a loose cylinder inside (`CylinderInBox`).

The arm is kinematic (it follows the planner exactly, within the LR-10iA/10 datasheet limits
that the planner reports): `PickPlanner` -> `ToolMotion` (the gripper frame's twist) -> five
zones of `Prismatic3DLimit` rod + `PneumaticCylinder` + `SuctionCup` + `VacuumGenerator` ->
the parcel (`RigidBody3D` + `PoseIntegrator3D`, four `ContactPoint` corners on the support plane).
The joint angles drive the robot meshes of the scene.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import params as P  # noqa: E402
import planner  # noqa: E402

ROOT = HERE.parent
NL = "\n"
G0 = P.G0


def num(x: float) -> str:
    text = repr(float(x))
    return text[:-2] if text.endswith(".0") and "e" not in text else text


class Diagram:
    def __init__(self, prefix: str = "fp") -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.notes: list[dict] = []
        self.prefix = prefix

    def node(self, name: str, ref: str, x: float, y: float, params: dict | None = None,
             starts: dict | None = None) -> str:
        self.nodes.append({
            "id": name, "name": name, "block": {"ref": ref},
            "position": {"x": x, "y": y}, "rotation": 0, "flipX": False,
            "params": params or {}, "constants": {}, "starts": starts or {},
        })
        return name

    def junction(self, name: str, kind: str, x: float, y: float) -> str:
        self.nodes.append({"id": name, "name": name, "block": {"junction": kind},
                           "position": {"x": x, "y": y}, "rotation": 0, "flipX": False,
                           "params": {}, "constants": {}, "starts": {}})
        return name

    def conn(self, kind: str, a: str, pa: str | None, b: str, pb: str | None) -> None:
        src = {"node": a} if pa is None else {"node": a, "port": pa}
        dst = {"node": b} if pb is None else {"node": b, "port": pb}
        self.conns.append({"id": f"{self.prefix}{len(self.conns) + 1:03d}", "kind": kind, "from": src, "to": dst})

    def note(self, text: str, x: float, y: float, w: float, h: float, color: str = "yellow") -> None:
        self.notes.append({"id": f"note{len(self.notes) + 1}", "kind": "text", "text": text,
                           "x": x, "y": y, "w": w, "h": h, "color": color})


# ------------------------------------------------------------------ geometry expressions
def zone_xy(k: int) -> tuple[str, str]:
    """Cup k centre in the gripper frame (expressions of the globals)."""
    dx, dy = P.ZONE_DIRS[k]
    if dx == 0.0 and dy == 0.0:
        return "0", "0"
    cx = f"{num(dx)}*cos(lay_deg*deg) - {num(dy)}*sin(lay_deg*deg)"
    cy = f"{num(dx)}*sin(lay_deg*deg) + {num(dy)}*cos(lay_deg*deg)"
    return f"r_p*({cx})", f"r_p*({cy})"


def point_mount(k: int) -> dict:
    """FixedTransform3DNeutral params: the parcel body frame (centre of mass) seen from the cup-k
    point frame on the top face (yaw psig against the parcel, so it starts aligned with the cup)."""
    xg, yg = zone_xy(k)
    c, s = "cos(psig_deg*deg)", "sin(psig_deg*deg)"
    return {
        "qw": "cos(psig_deg*deg/2)", "qx": "0", "qy": "0", "qz": "-sin(psig_deg*deg/2)",
        "x": f"-(({xg}) + {c}*(gx - cx) + {s}*(gy - cy))",
        "y": f"-(({yg}) - {s}*(gx - cx) + {c}*(gy - cy))",
        "z": "-(H_p/2 - cz)",
    }


# ------------------------------------------------------------------ the diagram
def build(kind: str) -> Diagram:
    """kind: box | sphere | cylinder."""
    d = Diagram()
    loose = kind != "box"
    # ---------------------------------------------------------------- planner and tool motion
    d.node("Planner", "project:PickPlanner", 80, 200, {n: n for n in planner.PLANNER_PARAMS})
    d.node("Tool", "project:ToolMotion", 360, 200)
    for s in ("V", "Vd", "tk"):
        d.conn("signal", "Planner", s, "Tool", s)
    d.junction("TJ", "1", 520, 200)
    d.conn("bond", "Tool", "p", "TJ", None)
    d.note("Kinematic arm: the LR-10iA/10 follows the planned joint trajectory exactly (no arm dynamics). "
           "PickPlanner checks the datasheet limits (util_*); ToolMotion prescribes the gripper frame's twist.",
           40, 40, 520, 90)

    # ---------------------------------------------------------------- five zones
    for i in range(P.N_ZONES):
        k = i + 1
        x0, y0 = 700, 80 + 260 * i
        xg, yg = zone_xy(i)
        zj = "h_base + L_cyl + rod0"
        d.node(f"JM{k}", "stdlib:multibond/FixedTransform3DNeutral", x0, y0,
               {"qw": "0", "qx": "1", "qy": "0", "qz": "0", "x": f"-({xg})", "y": yg, "z": f"-({zj})"})
        d.node(f"Rod{k}", "stdlib:spatial/Prismatic3DLimit", x0 + 160, y0,
               {"kr": "kr_rod", "br": "br_rod", "kt": "kt_rod", "bt": "bt_rod", "q0": "q_r0",
                "lower": "0", "upper": "stroke", "kL": "k_stop", "bL": "b_stop", "delta": "1e-4"})
        d.node(f"Cyl{k}", "project:PneumaticCylinder", x0 + 160, y0 + 120,
               {"F_ext": "F_ext", "F_ret": "F_ret", "v_ext": "v_ext", "v_ret": "v_ret"})
        d.node(f"RM{k}", "stdlib:multibond/FixedTransform3DNeutral", x0 + 320, y0)
        d.junction(f"RJ{k}", "1", x0 + 440, y0)
        d.node(f"RodBody{k}", "stdlib:spatial/RigidBody3D", x0 + 440, y0 + 100,
               {"m": "m_rod", "J": "[J_rod, J_rod, J_rod/4]", "g0": num(G0)},
               {"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
        d.node(f"LJ{k}", "stdlib:spatial/LocalPose3D", x0, y0 + 160,
               {"qw": "0", "qx": "1", "qy": "0", "qz": "0", "x": xg, "y": yg, "z": f"-({zj})"})
        d.node(f"CJ{k}", "stdlib:multibond/ComposePose3D", x0 + 160, y0 + 200)
        d.node(f"CR{k}", "stdlib:multibond/ComposePose3D", x0 + 320, y0 + 200)
        d.node(f"CM{k}", "stdlib:multibond/FixedTransform3DNeutral", x0 + 560, y0,
               {"qw": "0", "qx": "1", "qy": "0", "qz": "0"})
        d.node(f"Cup{k}", "stdlib:contact/SuctionCup", x0 + 700, y0, {
            "L0": "L0", "A_eff": "A_eff", "D_lip": "D_lip", "k_ax": "k_ax", "d_ax": "d_ax", "k_lat": "k_lat",
            "d_lat": "d_lat", "k_tilt": "k_tilt", "k_tor": "k_tor", "d_rot": "d_rot", "mu": "mu", "V": "V_cup",
            "perm": "perm", "A_lip0": "A_lip0", "F_min": "F_min", "p_atm": num(P.P_ATM)},
            {"rz": "rz0"})
        d.node(f"Gen{k}", "stdlib:contact/VacuumGenerator", x0 + 700, y0 + 140,
               {"dp_max": "dp_max", "Q_max": "Q_max", "n": "1", "G_rel": "G_rel"})
        d.node(f"PM{k}", "stdlib:multibond/FixedTransform3DNeutral", x0 + 860, y0, point_mount(i))
        # bonds: gripper -> joint -> rod -> cup -> parcel. A port at the tail of a bond sees minus
        # the bond flow: the joint mounts bond FROM their b port INTO the body junction (as the
        # bodies themselves and panda-3d's link transforms do), so the joints get positive twists;
        # the cup mounts bond from the junction (as suction-gripper), so the cups get negative ones.
        d.conn("bond", f"JM{k}", "b", "TJ", None)
        d.conn("bond", f"JM{k}", "a", f"Rod{k}", "parent")
        d.conn("bond", f"Rod{k}", "child", f"RM{k}", "a")
        d.conn("bond", f"RM{k}", "b", f"RJ{k}", None)
        d.conn("bond", f"RodBody{k}", "p", f"RJ{k}", None)
        d.junction(f"ZJ{k}", "1", x0 + 160, y0 + 60)
        d.conn("bond", f"Cyl{k}", "p", f"ZJ{k}", None)
        d.conn("bond", f"ZJ{k}", None, f"Rod{k}", "drive")
        d.conn("bond", f"RJ{k}", None, f"CM{k}", "b")
        d.conn("bond", f"CM{k}", "a", f"Cup{k}", "a")
        d.conn("bond", "Parcel", "p", f"PM{k}", "b")
        d.conn("bond", f"PM{k}", "a", f"Cup{k}", "b")
        d.conn("wire", f"Gen{k}", "a", f"Cup{k}", "vac")
        # signals: valves, rod pose
        d.conn("signal", "Planner", f"ue{k}", f"Cyl{k}", "u")
        d.conn("signal", "Planner", f"uv{k}", f"Gen{k}", "u")
        d.conn("signal", "Planner", "gref", f"CJ{k}", "gp")
        d.conn("signal", f"LJ{k}", "g", f"CJ{k}", "gl")
        d.conn("signal", f"CJ{k}", "g", f"CR{k}", "gp")
        d.conn("signal", f"Rod{k}", "pose", f"CR{k}", "gl")
        d.conn("signal", f"CR{k}", "g", f"RodBody{k}", "g")

    # ---------------------------------------------------------------- the parcel (or the carton shell)
    xp, yp = 1800, 300
    if loose:
        mass, jj = "m_shell", "[Jsx, Jsy, Jsz]"
    else:
        mass, jj = "m_p", "[Jpx, Jpy, Jpz]"
    d.node("Parcel", "stdlib:spatial/RigidBody3D", xp, yp, {"m": mass, "J": jj, "g0": num(G0)},
           {"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
    c, s = "cos(psip_deg*deg)", "sin(psip_deg*deg)"
    d.node("Pose", "stdlib:multibond/PoseIntegrator3D", xp, yp + 160, {},
           {"qw": "cos(psip_deg*deg/2)", "qx": "0", "qy": "0", "qz": "sin(psip_deg*deg/2)",
            "px": f"xp + {c}*cx - {s}*cy", "py": f"yp + {s}*cx + {c}*cy", "pz": "z_s + H_p/2 + cz - pen0"})
    d.conn("signal", "Parcel", "V", "Pose", "tw")
    d.conn("signal", "Pose", "g", "Parcel", "g")
    # the carton centre (for the scene): the centre of mass shifted by -c
    d.node("BoxOff", "stdlib:spatial/LocalPose3D", xp + 160, yp + 160, {"x": "-cx", "y": "-cy", "z": "-cz"})
    d.node("BoxPose", "stdlib:multibond/ComposePose3D", xp + 300, yp + 160)
    d.conn("signal", "Pose", "g", "BoxPose", "gp")
    d.conn("signal", "BoxOff", "g", "BoxPose", "gl")
    # support plane (conveyor and place table) under the four bottom corners
    d.node("Support", "stdlib:contact/ContactSurface", xp + 200, yp + 720, {"oz": "z_s"})
    fl = P.FLOOR
    for k, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)], start=1):
        cxe, cye, cze = f"{sx}*L_p/2 - cx", f"{sy}*W_p/2 - cy", "-H_p/2 - cz"
        y = yp + 300 + 110 * (k - 1)
        d.node(f"FMount{k}", "stdlib:multibond/FixedTransform3DNeutral", xp, y,
               {"x": f"-({cxe})", "y": f"-({cye})", "z": f"-({cze})"})
        d.node(f"FLocal{k}", "stdlib:spatial/LocalPose3D", xp + 140, y + 40, {"x": cxe, "y": cye, "z": cze})
        d.node(f"FPose{k}", "stdlib:multibond/ComposePose3D", xp + 280, y + 40)
        d.node(f"Floor{k}", "stdlib:contact/ContactPoint", xp + 420, y,
               {"k": num(fl["k"]), "xref": num(fl["xref"]), "c": num(fl["c"]), "mu": num(fl["mu"]), "vs": num(fl["vs"])})
        d.conn("bond", "Parcel", "p", f"FMount{k}", "b")
        d.conn("bond", f"FMount{k}", "a", f"Floor{k}", "p")
        d.conn("signal", "Pose", "g", f"FPose{k}", "gp")
        d.conn("signal", f"FLocal{k}", "g", f"FPose{k}", "gl")
        d.conn("signal", f"FPose{k}", "g", f"Floor{k}", "g")
        d.conn("signal", "Support", "o", f"Floor{k}", "o")
        d.conn("signal", "Support", "fr", f"Floor{k}", "fr")

    # ---------------------------------------------------------------- loose content
    if loose:
        xc, yc = 2200, 300
        if kind == "sphere":
            d.node("Content", "stdlib:spatial/RigidBody3D", xc, yc,
                   {"m": "m_s", "J": "[0.4*m_s*r_s^2, 0.4*m_s*r_s^2, 0.4*m_s*r_s^2]", "g0": num(G0)},
                   {"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
            q = {"qw": "cos(psip_deg*deg/2)", "qx": "0", "qy": "0", "qz": "sin(psip_deg*deg/2)"}
            zc = "z_s + wall + r_s - pen_c - pen0"
            geom = {"r": "r_s"}
            ref = "project:SphereInBox"
        else:
            d.node("Content", "stdlib:spatial/RigidBody3D", xc, yc,
                   {"m": "m_c", "J": "[m_c*(3*r_c^2 + l_c^2)/12, m_c*(3*r_c^2 + l_c^2)/12, m_c*r_c^2/2]", "g0": num(G0)},
                   {"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
            h = num(math.sqrt(0.5))
            q = {"qw": f"{h}*cos(psip_deg*deg/2)", "qx": f"-{h}*sin(psip_deg*deg/2)",
                 "qy": f"{h}*cos(psip_deg*deg/2)", "qz": f"{h}*sin(psip_deg*deg/2)"}
            zc = "z_s + wall + r_c - pen_c - pen0"
            geom = {"r": "r_c", "l": "l_c"}
            ref = "project:CylinderInBox"
        d.node("ContentPose", "stdlib:multibond/PoseIntegrator3D", xc, yc + 160, {},
               {**q, "px": "xp", "py": "yp", "pz": zc})
        d.conn("signal", "Content", "V", "ContentPose", "tw")
        d.conn("signal", "ContentPose", "g", "Content", "g")
        d.node("Walls", ref, xc - 200, yc + 40, {
            **geom, "hx": "L_p/2 - wall", "hy": "W_p/2 - wall", "hz": "H_p/2 - wall",
            "k": "k_w", "xref": num(P.CONTENT_CONTACT["xref_w"]), "c": "c_w", "mu": "mu_w",
            "vs": num(P.CONTENT_CONTACT["vs_w"])})
        d.node("WA", "stdlib:multibond/FixedTransform3DNeutral", xc - 360, yc)
        d.node("WB", "stdlib:multibond/FixedTransform3DNeutral", xc - 40, yc)
        d.conn("bond", "Parcel", "p", "WA", "b")
        d.conn("bond", "WA", "a", "Walls", "a")
        d.conn("bond", "Content", "p", "WB", "b")
        d.conn("bond", "WB", "a", "Walls", "b")
        d.conn("signal", "Pose", "g", "Walls", "gb")
        d.conn("signal", "ContentPose", "g", "Walls", "gc")

    # ---------------------------------------------------------------- monitor
    d.node("Monitor", "project:PickMonitor", 1500, 1400, {"d_drop": "0.02", "M_req": "M_req"})
    for k in range(1, P.N_ZONES + 1):
        d.conn("signal", f"Cup{k}", "U", "Monitor", f"U{k}")
    d.conn("signal", "Planner", "act", "Monitor", "act")
    d.conn("signal", "Planner", "held", "Monitor", "held")
    d.conn("signal", "Pose", "g", "Monitor", "gp")
    d.conn("signal", "Planner", "gref", "Monitor", "gt")
    return d


# ------------------------------------------------------------------ globals, plots, bindings, dashboard
def extra_rows(kind: str) -> list[tuple[str, str, str, str]]:
    """Rows that depend on the plant kind (contents, start penetrations)."""
    cc = P.CONTENT_CONTACT
    rows = []
    if kind != "box":
        rows.append(("Jsx", "m_shell/(W_p*H_p + L_p*H_p + L_p*W_p)*(W_p*H_p*(W_p^2 + H_p^2)/12 + L_p*H_p*(H_p^2/12 + W_p^2/4) + L_p*W_p*(W_p^2/12 + H_p^2/4))",
                     "kg*m^2", "Carton shell inertia about x (thin walls)"))
        rows.append(("Jsy", "m_shell/(W_p*H_p + L_p*H_p + L_p*W_p)*(L_p*H_p*(L_p^2 + H_p^2)/12 + W_p*H_p*(H_p^2/12 + L_p^2/4) + L_p*W_p*(L_p^2/12 + H_p^2/4))",
                     "kg*m^2", "Carton shell inertia about y (thin walls)"))
        rows.append(("Jsz", "m_shell/(W_p*H_p + L_p*H_p + L_p*W_p)*(L_p*W_p*(L_p^2 + W_p^2)/12 + W_p*H_p*(W_p^2/12 + L_p^2/4) + L_p*H_p*(L_p^2/12 + W_p^2/4))",
                     "kg*m^2", "Carton shell inertia about z (thin walls)"))
        m_c = P.SPHERE["m_s"] if kind == "sphere" else P.CYLINDER["m_c"] / 2.0
        pen_c = (m_c * G0 * math.sqrt(cc["xref_w"]) / cc["k_w"]) ** (2.0 / 3.0)
        rows.append(("pen_c", num(round(pen_c, 9)), "m", "Rest penetration of the content in the carton floor"))
    return rows


def globals_table(kind: str, overrides: dict | None = None) -> list[dict]:
    rows = P.global_rows() + extra_rows(kind)
    overrides = dict(overrides or {})
    out = [{"name": n, "value": str(overrides.get(n, v)), "unit": u, "description": desc} for n, v, u, desc in rows]
    unknown = set(overrides) - {r[0] for r in rows}
    if unknown:
        raise KeyError(f"unknown globals {sorted(unknown)}")
    return out


def kind_overrides(kind: str) -> dict:
    """Globals a plant kind sets: the load seen by the wrist and the rest penetration."""
    if kind == "box":
        return {}
    m_in = P.SPHERE["m_s"] if kind == "sphere" else P.CYLINDER["m_c"]
    m_tot = P.SHELL["m_shell"] + m_in
    var = "m_s" if kind == "sphere" else "m_c"
    # A loose content ends against a wall (the soft bellows let the carton tilt, the content
    # rolls or slides downhill): a static CoM shift the five 4 cm pitch cups cannot carry at a
    # safety factor of 2 even at a crawl, so the loose cases ask a margin of 0.3 (factor 1.4).
    return {"m_p": f"m_shell + {var}", "pen0": num(round(P.rest_penetration(m_tot), 9)), "M_req": "0.3"}


def plots(kind: str) -> list[dict]:
    z = range(1, P.N_ZONES + 1)
    out = [
        {"id": "u", "title": "Cup utilisation U (1 = pull-off, peel or slip)", "signals": [f"Cup{k}/U" for k in z]},
        {"id": "margin", "title": "Holding margin per zone and in total (1 - peak U while carried)",
         "signals": [f"Monitor/margin{k}" for k in z] + ["Monitor/M_tot"]},
        {"id": "force", "title": "Axial cup force T [N] (pull > 0)", "signals": [f"Cup{k}/T" for k in z]},
        {"id": "shear", "title": "Lateral cup force [N]", "signals": [f"Cup{k}/F_lat" for k in z]},
        {"id": "vac", "title": "Vacuum per zone [Pa]", "signals": [f"Cup{k}/dp" for k in z]},
        {"id": "stroke", "title": "Cylinder strokes [m] (0 retracted)", "signals": [f"Rod{k}/qout" for k in z]},
        {"id": "joints", "title": "Joint angles [rad] (the arm follows the plan exactly)", "signals": [f"Planner/qr[{j}]" for j in range(1, 7)]},
        {"id": "jrate", "title": "Joint rates [rad/s]", "signals": [f"Planner/qdr[{j}]" for j in range(1, 7)]},
        {"id": "util", "title": "Use of the LR-10iA/10 limits [%] (running maxima)",
         "signals": ["Planner/util_v", "Planner/util_a", "Planner/util_j", "Planner/util_r", "Planner/util_M", "Planner/util_I"]},
        {"id": "xy", "title": "Gripper path, top view [m]", "signals": ["Planner/gref[6]"], "x": "Planner/gref[5]", "equalAspect": True},
        {"id": "xz", "title": "Gripper height against x [m]", "signals": ["Planner/gref[7]"], "x": "Planner/gref[5]", "equalAspect": True},
        {"id": "sep", "title": "Parcel drop detection: displacement from the gripper [m] and held flag",
         "signals": ["Monitor/sep", "Monitor/held_ok", "Planner/held"]},
        {"id": "wrench", "title": "Wrench of the gripper load on the flange (gripper frame) [N, N m]",
         "signals": [f"Tool/W[{k}]" for k in range(1, 7)]},
    ]
    if kind != "box":
        out.append({"id": "content", "title": "Content position in the carton [m]",
                    "signals": [f"Walls/pos[{k}]" for k in (1, 2, 3)]})
        out.append({"id": "contentxy", "title": "Content in the carton, top view [m]",
                    "signals": ["Walls/pos[2]"], "x": "Walls/pos[1]", "equalAspect": True})
        out.append({"id": "wallforce", "title": "Content wall force [N]", "signals": ["Walls/Fmag", "Walls/Fn"]})
    return out


def bindings(kind: str) -> list[dict]:
    out = [{"target": f"joint:joint_{j}", "property": "position", "signal": f"Planner/qr[{j}]"} for j in range(1, 7)]
    out.append({"target": "link:parcel", "property": "pose", "signal": [f"BoxPose/g[{k}]" for k in range(1, 8)]})
    out.append({"target": "link:com", "property": "pose", "signal": [f"Pose/g[{k}]" for k in range(1, 8)]})
    for k in range(1, P.N_ZONES + 1):
        out.append({"target": f"joint:rod_{k}", "property": "position", "signal": f"Rod{k}/qout"})
        out.append({"target": f"visual:bellows_{k}", "property": "color", "signal": f"Cup{k}/U",
                    "colormap": "coolwarm", "range": [0.0, 1.0]})
        out.append({"target": f"visual:lip_{k}", "property": "color", "signal": f"Cup{k}/dp",
                    "colormap": "viridis", "range": [0.0, 60000.0]})
    if kind != "box":
        out.append({"target": "link:content", "property": "pose", "signal": [f"ContentPose/g[{k}]" for k in range(1, 8)]})
    return out


def dashboard(kind: str) -> dict:
    cards = [
        {"id": "u", "kind": "plot", "size": "2x2", "title": "Cup utilisation U (1 = pull-off, peel or slip)",
         "signals": [f"Cup{k}/U" for k in range(1, 6)]},
        {"id": "xy", "kind": "plot", "size": "2x2", "title": "Gripper path, top view [m]",
         "signals": ["Planner/gref[6]"], "x": "Planner/gref[5]", "equalAspect": True},
        {"id": "tcyc", "kind": "value", "size": "1x1", "title": "Cycle time", "signals": ["Planner/T_cyc"],
         "options": {"decimals": 3, "unit": "s"}},
        {"id": "margin", "kind": "gauge", "size": "1x1", "title": "Holding margin (min over zones)",
         "signals": ["Monitor/M_tot"],
         "options": {"min": -0.5, "max": 1.0, "decimals": 2, "unit": "",
                     "zones": [{"from": -0.5, "to": 0.0, "tone": "bad"}, {"from": 0.0, "to": 0.5, "tone": "warn"},
                               {"from": 0.5, "to": 1.0, "tone": "good"}]}},
        {"id": "held", "kind": "indicator", "size": "1x1", "title": "Parcel held", "signals": ["Monitor/held_ok"],
         "options": {"threshold": 0.5, "onWhen": "above"}},
        {"id": "umax", "kind": "gauge", "size": "1x1", "title": "Peak use of the robot limits", "signals": ["Planner/util_max"],
         "options": {"min": 0, "max": 120, "decimals": 0, "unit": "%",
                     "zones": [{"from": 0, "to": 90, "tone": "good"}, {"from": 90, "to": 100, "tone": "warn"},
                               {"from": 100, "to": 120, "tone": "bad"}]}},
        {"id": "margins", "kind": "plot", "size": "2x2", "title": "Holding margin per zone",
         "signals": [f"Monitor/margin{k}" for k in range(1, 6)]},
        {"id": "util", "kind": "plot", "size": "2x2", "title": "Joint rate / acc / jerk, wrist moment [% of limit]",
         "signals": ["Planner/util_v", "Planner/util_a", "Planner/util_j", "Planner/util_M"]},
        {"id": "family", "kind": "slider", "size": "2x1",
         "title": "Family: 1 joint PTP, 2 Cartesian, 3 Cartesian blended, 4 joint blended",
         "parameter": "global:family", "options": {"min": 1, "max": 4, "step": 1, "decimals": 0, "unit": ""}},
        {"id": "kv", "kind": "slider", "size": "2x1", "title": "Joint moves: share of the rate limits", "parameter": "global:kv",
         "options": {"min": 0.2, "max": 1.0, "step": 0.05, "decimals": 2, "unit": ""}},
        {"id": "ka", "kind": "slider", "size": "2x1", "title": "Joint moves: share of the acc/jerk limits", "parameter": "global:ka",
         "options": {"min": 0.2, "max": 1.0, "step": 0.05, "decimals": 2, "unit": ""}},
        {"id": "vc", "kind": "slider", "size": "2x1", "title": "Cartesian speed", "parameter": "global:v_c",
         "options": {"min": 0.2, "max": 3.0, "step": 0.1, "decimals": 1, "unit": "m/s"}},
        {"id": "ac", "kind": "slider", "size": "2x1", "title": "Cartesian acceleration", "parameter": "global:a_c",
         "options": {"min": 1, "max": 30, "step": 0.5, "decimals": 1, "unit": "m/s^2"}},
        {"id": "lam", "kind": "slider", "size": "2x1", "title": "Jerk phase share (0 trapezoid, 1 S-curve)",
         "parameter": "global:lam", "options": {"min": 0.1, "max": 1.0, "step": 0.05, "decimals": 2, "unit": ""}},
        {"id": "rb", "kind": "slider", "size": "2x1", "title": "Blend distance", "parameter": "global:r_b",
         "options": {"min": 0, "max": 0.08, "step": 0.005, "decimals": 3, "unit": "m"}},
        {"id": "hlift", "kind": "slider", "size": "2x1", "title": "Lift height", "parameter": "global:H_lift",
         "options": {"min": 0.02, "max": 0.2, "step": 0.01, "decimals": 2, "unit": "m"}},
        {"id": "text", "kind": "slider", "size": "2x1", "title": "Cylinder extension lead before the pick",
         "parameter": "global:t_ext", "options": {"min": 0, "max": 0.4, "step": 0.01, "decimals": 2, "unit": "s"}},
        {"id": "tseal", "kind": "slider", "size": "2x1", "title": "Vacuum wait at the pick",
         "parameter": "global:T_seal", "options": {"min": 0, "max": 0.3, "step": 0.01, "decimals": 2, "unit": "s"}},
        {"id": "cx", "kind": "slider", "size": "2x1", "title": "Centre of mass offset x", "parameter": "global:cx",
         "options": {"min": -0.1, "max": 0.1, "step": 0.005, "decimals": 3, "unit": "m"}},
        {"id": "cy", "kind": "slider", "size": "2x1", "title": "Centre of mass offset y", "parameter": "global:cy",
         "options": {"min": -0.06, "max": 0.06, "step": 0.005, "decimals": 3, "unit": "m"}},
        {"id": "psip", "kind": "slider", "size": "2x1", "title": "Pick yaw of the parcel", "parameter": "global:psip_deg",
         "options": {"min": -90, "max": 90, "step": 15, "decimals": 0, "unit": "deg"}},
        {"id": "psiq", "kind": "slider", "size": "2x1", "title": "Place yaw of the parcel", "parameter": "global:psiq_deg",
         "options": {"min": -90, "max": 180, "step": 15, "decimals": 0, "unit": "deg"}},
    ]
    if kind != "box":
        cards.insert(2, {"id": "content", "kind": "plot", "size": "2x2", "title": "Content in the carton, top view [m]",
                         "signals": ["Walls/pos[2]"], "x": "Walls/pos[1]", "equalAspect": True})
    return {"autoRerun": False, "cards": cards}


# ------------------------------------------------------------------ scenarios
#: name -> (kind, comment, overrides)
SCENARIOS: dict[str, tuple[str, str, dict]] = {
    "pick-place": ("box", "Pick a 1.5 kg carton (300 x 200 x 120 mm) from the conveyor and place it turned by 90 deg, "
                   "five cups, Cartesian blended motion (family 3) at the default limits.", {}),
    "offset-com": ("box", "The same pick with the centre of mass 60 mm off the box centre along its length and 30 mm "
                   "across: the outer cups on the light side carry the moment.", {"cx": "0.06", "cy": "0.03"}),
    "loose-sphere": ("sphere", "A carton shell (0.6 kg) with a loose 0.5 kg ball (80 mm) inside: it rolls against the "
                     "walls during the transfer and its reaction loads the cups.", {}),
    "loose-cylinder": ("cylinder", "A carton shell (0.6 kg) with a loose 0.5 kg bottle (cylinder 70 x 120 mm) lying inside: it "
                       "slides and tips against the walls during the transfer.", {}),
    "too-aggressive": ("box", "A trajectory the robot can drive but the gripper cannot hold: joint blended motion "
                       "(family 4) at 80 % of every joint rate, acceleration and jerk limit (83 % of the robot limits "
                       "in all): the cups peel at the start of the transfer and the carton drops.",
                       {"family": "4", "kv": "0.8", "ka": "0.8"}),
    "static-hold": ("box", "Validation: the offset-CoM carton carried slowly (Cartesian with stops at 0.1 m/s): in the "
                    "cruise the parcel hangs still and the cup forces match the hand calculation of design/reference.py "
                    "(a rigid plate on five bellows: axial springs, tilt springs and the CoM below the lip plane).",
                    {"family": "2", "v_c": "0.1", "w_c": "0.25", "a_c": "0.5", "al_c": "1.25", "j_c": "5",
                     "jw_c": "12.5", "cx": "0.06", "cy": "0.03"}),
}


def model_document(name: str, kind: str, comment: str, overrides: dict) -> dict:
    d = build(kind)
    ov = {**kind_overrides(kind), **overrides}
    g = globals_table(kind, ov)
    gv = P.eval_globals(P.global_rows() + extra_rows(kind), ov)
    ref = planner.reference(gv, t_end=0.0)
    t_end = round(ref["tl"]["tF"] + P.T_END_PAD, 3)
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": comment,
        "diagram": {"nodes": d.nodes, "connections": d.conns, "annotations": d.notes},
        "settings": {
            "t_start": 0.0, "t_end": t_end, "solver": "Rodas5P", "reltol": 1e-6, "abstol": 1e-8,
            "max_step": None, "output": {"mode": "points", "points": int(round(t_end * 500)) + 1},
            "event_limit": 20000,
        },
        "parameters": g,
        "plots": plots(kind),
        "scene": {"file": f"scenes/fanuc-pick-{kind}.sdf"},
        "bindings": bindings(kind),
        "dashboard": dashboard(kind),
    }


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + NL, encoding="utf-8", newline=NL)
    print("wrote", path.relative_to(ROOT))


def all_scenarios() -> dict:
    """The built-in scenarios plus the optimum models of design/optimize.py (results.json)."""
    out = dict(SCENARIOS)
    res = HERE / "results.json"
    if res.exists():
        data = json.loads(res.read_text(encoding="utf-8"))
        for case in data.get("cases", []):
            best = case.get("best")
            if best and case.get("model"):
                out[case["model"]] = (case["kind"], best["comment"], best["globals"])
    return out


def main(argv: list[str]) -> int:
    only = set(argv)
    scen = all_scenarios()
    for name, (kind, comment, ov) in scen.items():
        if only and name not in only:
            continue
        _write(ROOT / "models" / f"{name}.bgmodel.json", model_document(name, kind, comment, ov))
    _write(ROOT / "bgsim.project.json", {
        "format": "bgsim.project", "language": "0.1.0", "name": "fanuc-pick",
        "models": list(scen), "libraryDir": "library", "scenesDir": "scenes"})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
