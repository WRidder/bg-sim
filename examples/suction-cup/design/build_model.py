# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Writes the models of the suction-cup example (``models/*.bgmodel.json``) and its scenes.

One plant, several scenarios: a tool (``CupTool``, prescribed motion) carries one bellows
suction cup (``stdlib:contact/SuctionCup`` with the nonlinear bellows on) that holds a small box
(``RigidBody3D``) picked from a table. The excitation is chosen by the global ``motion``; every
scenario is the same diagram with other global values, except ``linear-vs-nonlinear``, which adds
a second cup with the nonlinear terms off and its own box next to the first. The four table contacts
under each box are instances (``Floor1`` to ``Floor4``, ``FloorL1`` to ``FloorL4``) of the library
subsystem ``library/ContactFoot.bgsub.json``, which this script also writes.

Run it with ``uv run examples/suction-cup/design/build_model.py``.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import params as P  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
#: cup mounts (x, y) in the tool frame, per variant
MOUNTS = {"single": [(0.0, 0.0)], "compare": [(0.0, -0.09), (0.0, 0.09)]}
#: instance-name suffix per cup (cup 1 the nonlinear cup, cup 2 the linear one)
SUFFIX = {1: "", 2: "L"}


def num(x: float) -> str:
    text = repr(float(x))
    return text[:-2] if text.endswith(".0") and "e" not in text else text


def scurve_time(dist: float, v: float, a: float, j: float) -> float:
    """Duration of the stdlib SCurveProfile move (the block's formulas)."""
    a_v = min(a, math.sqrt(v * j))
    dist_v = v * (a_v / j + v / a_v)
    if dist >= dist_v:
        a_peak, v_peak = a_v, v
    else:
        a_peak = min(a, (dist * j * j / 2.0) ** (1.0 / 3.0))
        tj = a_peak / j
        v_peak = a_peak * (math.sqrt(tj * tj + 4.0 * dist / a_peak) - tj) / 2.0
    t_acc = a_peak / j + v_peak / a_peak
    t_cruise = max(dist / v - t_acc, 0.0) if dist >= dist_v else 0.0
    return 2.0 * t_acc + t_cruise


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.notes: list[dict] = []

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
        self.conns.append({"id": f"c{len(self.conns) + 1:03d}", "kind": kind, "from": src, "to": dst})

    def note(self, text: str, x: float, y: float, w: float, h: float, color: str = "yellow") -> None:
        self.notes.append({"id": f"note{len(self.notes) + 1}", "kind": "text", "text": text,
                           "x": x, "y": y, "w": w, "h": h, "color": color})


# ---------------------------------------------------------------- timing (fixed lift profile)
M = P.MOTION
D_PRESS = 0.003       # m   the lower presses the box this far onto the table before the release
H_RET = 0.05          # m   retract after the release
T_LIFT = scurve_time(M["H_lift"], M["v_lift"], M["a_lift"], M["j_lift"])
T_LOW = scurve_time(M["H_lift"] + D_PRESS, M["v_lift"], M["a_lift"], M["j_lift"])
T_RET = scurve_time(H_RET, M["v_lift"], M["a_lift"], M["j_lift"])


def globals_table(overrides: dict | None = None) -> list[dict]:
    """The global parameters (name, value expression, unit, description)."""
    b, c, v = P.BOX, P.CUP, P.VACUUM
    rows = [
        # payload
        ("m_p", num(b["m_p"]), "kg", "Payload (box) mass"),
        ("L_p", num(b["L_p"]), "m", "Box length (x)"),
        ("W_p", num(b["W_p"]), "m", "Box width (y)"),
        ("H_p", num(b["H_p"]), "m", "Box height"),
        ("cx", num(b["cx"]), "m", "Centre of mass offset from the box centre, x"),
        ("cy", num(b["cy"]), "m", "Centre of mass offset, y"),
        ("cz", num(b["cz"]), "m", "Centre of mass offset, z (up)"),
        # cup
        ("L0", num(c["L0"]), "m", "Cup rest length (mount to lip)"),
        ("A_eff", num(c["A_eff"]), "m^2", "Effective suction area"),
        ("D_lip", num(c["D_lip"]), "m", "Lip diameter"),
        ("k_ax", num(c["k_ax"]), "N/m", "Bellows axial stiffness"),
        ("d_ax", num(c["d_ax"]), "N*s/m", "Bellows axial damping"),
        ("k_lat", num(c["k_lat"]), "N/m", "Bellows lateral stiffness"),
        ("d_lat", num(c["d_lat"]), "N*s/m", "Bellows lateral damping"),
        ("k_tilt", num(c["k_tilt"]), "N*m/rad", "Bellows bending stiffness"),
        ("k_tor", num(c["k_tor"]), "N*m/rad", "Bellows torsional stiffness"),
        ("d_rot", num(c["d_rot"]), "N*m*s/rad", "Bellows rotational damping"),
        ("mu", num(c["mu"]), "1", "Lip friction coefficient"),
        ("V_cup", num(c["V_cup"]), "m^3", "Cup chamber and hose volume"),
        ("A_lip0", num(c["A_lip0"]), "m^2", "Sealed-lip leak area"),
        ("F_min", num(c["F_min"]), "N", "Residual friction capacity of a free lip"),
        ("s_bot", num(c["s_bot"]), "m", "Compression stroke before the folds bottom (estimate)"),
        ("k_bot", num(c["k_bot"]), "N/m", "Bottoming stiffness scale (estimate)"),
        ("n_bot", num(c["n_bot"]), "1", "Bottoming exponent"),
        ("x_bot", num(c["x_bot"]), "m", "Reference over-stroke of the bottoming law"),
        ("A_fold", num(c["A_fold"]), "m^2", "Folded bellows annulus: vacuum lift stroke A_fold*dp/k_ax (estimate)"),
        ("c_vac", num(c["c_vac"]), "1", "Lateral/tilt stiffness rise with vacuum, 1 + c_vac*dp/p_atm (estimate)"),
        ("c_ext", num(c["c_ext"]), "1", "Lateral/tilt stiffness fall with extension, exp(-c_ext*ext/L0) (estimate)"),
        # vacuum
        ("dp_max", num(v["dp_max"]), "Pa", "Ejector end vacuum (the vacuum level)"),
        ("Q_max", num(v["Q_max"]), "m^3/s", "Ejector suction flow at zero vacuum (free air)"),
        ("G_rel", num(v["G_rel"]), "m^3/(s*Pa)", "Release (vent) conductance"),
        ("perm", num(v["perm"]), "m/(s*Pa)", "Air permeance of the box surface"),
        # motion
        ("motion", num(M["motion"]), "1", "Excitation: 1 hold, 2 vertical bounce, 3 horizontal steps, 4 tilt swing, 5 lateral chirp"),
        ("amp", "1", "1", "Amplitude scale of every excitation"),
        ("fsc", "1", "1", "Frequency scale of the chirps and the fast swing"),
        ("H_lift", num(M["H_lift"]), "m", "Lift height"),
        ("A_st", num(M["A_st"]), "m", "Bounce: quick step down"),
        ("T_st", num(M["T_st"]), "s", "Bounce: step duration"),
        ("T_ring", num(M["T_ring"]), "s", "Bounce: free ring-down before the chirp"),
        ("A_z", num(M["A_z"]), "m", "Bounce: vertical chirp amplitude (end)"),
        ("f0_z", num(M["f0_z"]), "Hz", "Bounce: chirp start frequency"),
        ("f1_z", num(M["f1_z"]), "Hz", "Bounce: chirp end frequency"),
        ("T_cz", num(M["T_cz"]), "s", "Bounce: chirp duration"),
        ("a_s", num(M["a_s"]), "m/s^2", "Steps: largest acceleration (moves at a_s/3, 2a_s/3, a_s)"),
        ("T_p", num(M["T_p"]), "s", "Steps: acceleration pulse duration"),
        ("T_c", num(M["T_c"]), "s", "Steps: coast and pause"),
        ("tau_s", num(M["tau_s"]), "s", "Steps: edge time scale"),
        ("th_A", num(M["th_A"]), "deg", "Swing: quasi-static tilt"),
        ("T_sw", num(M["T_sw"]), "s", "Swing: tilt time each way"),
        ("T_h", num(M["T_h"]), "s", "Swing: hold at th_A"),
        ("th_B", num(M["th_B"]), "deg", "Swing: amplitude of the fast swing"),
        ("f_sw", num(M["f_sw"]), "Hz", "Swing: frequency of the fast swing"),
        ("N_sw", num(M["N_sw"]), "1", "Swing: cycles of the fast swing"),
        ("A_x", num(M["A_x"]), "m", "Chirp: lateral amplitude (end)"),
        ("f0_x", num(M["f0_x"]), "Hz", "Chirp: start frequency"),
        ("f1_x", num(M["f1_x"]), "Hz", "Chirp: end frequency"),
        ("T_cx", num(M["T_cx"]), "s", "Chirp: duration"),
        ("a0", num(M["a0"]), "1", "Chirps: start amplitude share"),
        ("T_env", num(M["T_env"]), "s", "Chirps: fade-in and fade-out"),
        ("w_lp", num(M["w_lp"]), "rad/s", "Transmissibility demodulator low-pass"),
        # timeline
        ("t_lift", num(M["t_lift"]), "s", "Lift start (the vacuum is on from t = 0)"),
        ("t_x0", f"t_lift + {num(round(T_LIFT + 0.2, 4))}", "s", "Start of the excitation"),
        ("T_exc",
         "1*max(0, 1 - abs(motion - 1)) + (T_ring + T_cz + 0.6)*max(0, 1 - abs(motion - 2))"
         " + (6*T_p + 6*T_c + 0.3)*max(0, 1 - abs(motion - 3))"
         " + (2*T_sw + T_h + 0.8 + N_sw/(fsc*f_sw))*max(0, 1 - abs(motion - 4))"
         " + (T_cx + 0.6)*max(0, 1 - abs(motion - 5))",
         "s", "Length of the excitation window (per motion)"),
        ("t_low", "t_x0 + T_exc + 0.2", "s", "Lower start (place)"),
        ("t_rel", f"t_low + {num(round(T_LOW + 0.1, 4))}", "s", "Vacuum off (release)"),
        ("t_ret", "t_rel + 0.25", "s", "Retract start"),
        # derived
        ("pen0", "(m_p*9.81/4*sqrt(1e-3)/2e5)^(2/3)", "m", "Rest penetration of the box corners in the table"),
        ("z0", "H_p - pen0 + L0", "m", "Start height of the cup mount (lip on the box top)"),
        ("Jx", "m_p*(W_p^2 + H_p^2)/12", "kg*m^2", "Box inertia about x"),
        ("Jy", "m_p*(L_p^2 + H_p^2)/12", "kg*m^2", "Box inertia about y"),
        ("Jz", "m_p*(L_p^2 + W_p^2)/12", "kg*m^2", "Box inertia about z"),
    ]
    overrides = overrides or {}
    unknown = set(overrides) - {r[0] for r in rows}
    if unknown:
        raise KeyError(f"unknown globals {sorted(unknown)}")
    return [{"name": n, "value": str(overrides.get(n, val)), "unit": u, "description": d} for n, val, u, d in rows]


def t_end_of(gv: dict) -> float:
    """The run length for the motion of a scenario (the same formulas as the globals)."""
    m = round(float(gv["motion"]))
    f = lambda k: float(gv[k])  # noqa: E731
    t_exc = {1: 1.0, 2: f("T_ring") + f("T_cz") + 0.6, 3: 6 * f("T_p") + 6 * f("T_c") + 0.3,
             4: 2 * f("T_sw") + f("T_h") + 0.8 + f("N_sw") / (f("fsc") * f("f_sw")), 5: f("T_cx") + 0.6}[m]
    t_x0 = float(gv["t_lift"]) + T_LIFT + 0.2
    return round(t_x0 + t_exc + 0.2 + T_LOW + 0.1 + 0.25 + T_RET + 0.35, 2)


def cup_params(linear: bool) -> dict:
    p = {"L0": "L0", "A_eff": "A_eff", "D_lip": "D_lip", "k_ax": "k_ax", "d_ax": "d_ax", "k_lat": "k_lat",
         "d_lat": "d_lat", "k_tilt": "k_tilt", "k_tor": "k_tor", "d_rot": "d_rot", "mu": "mu", "V": "V_cup",
         "perm": "perm", "A_lip0": "A_lip0", "F_min": "F_min", "p_atm": num(P.P_ATM)}
    p.update({k: k for k in P.CUP_NL})
    if linear:
        p.update({k: num(v) for k, v in P.LINEAR_OFF.items()})
    return p


def foot_definition() -> dict:
    """library/ContactFoot.bgsub.json: one table contact of the box. The mount carries the body's
    bond to the corner, the local offset gives the corner pose; the contact point presses on the
    table (a ContactSurface outside the instance, fed in through o and fr)."""
    fl = P.FLOOR
    nodes = [
        ("Local", "stdlib:spatial/LocalPose3D", 0, 0, {"x": "0", "y": "0", "z": "0"}),
        ("Compose", "stdlib:multibond/ComposePose3D", 160, 0, {}),
        ("Mount", "stdlib:multibond/FixedTransform3DNeutral", 0, 160, {"x": "0", "y": "0", "z": "0"}),
        ("Contact", "stdlib:contact/ContactPoint", 320, 40,
         {"k": num(fl["k"]), "xref": num(fl["xref"]), "c": num(fl["c"]), "mu": num(fl["mu"]), "vs": num(fl["vs"])}),
    ]
    conns = [("bond", "Mount", "a", "Contact", "p"), ("signal", "Local", "g", "Compose", "gl"),
             ("signal", "Compose", "g", "Contact", "g")]

    def sig(name, direction, size, unit, node, port):
        return {"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
                "unit": unit, "node": node, "port": port}

    return {
        "format": "bgsim.subsystem", "name": "ContactFoot",
        "description": ("One contact foot: a fixed mount from the body to the contact point and a compliant "
                        "Hunt-Crossley ContactPoint on a ContactSurface outside the instance (o, fr). Pin the "
                        "point with Local/x, Local/y, Local/z (body frame) and the mount with Mount/x, Mount/y, "
                        "Mount/z (the negated offsets). Generated by design/build_model.py."),
        "ports": [
            {"name": "p", "kind": "power", "domain": "Spatial", "size": [6], "node": "Mount", "port": "b"},
            sig("pose", "input", 7, None, "Compose", "gp"),
            sig("o", "input", 3, "m", "Contact", "o"),
            sig("fr", "input", 9, "1", "Contact", "fr"),
            sig("f_n", "output", 1, "N", "Contact", "f_n"),
            sig("Pd", "output", 1, "W", "Contact", "Pd"),
        ],
        "diagram": {
            "nodes": [{"id": n, "name": n, "block": {"ref": ref}, "position": {"x": x, "y": y}, "rotation": 0,
                       "flipX": False, "params": p, "constants": {}, "starts": {},
                       "ui": {"showLabel": True, "color": None}} for n, ref, x, y, p in nodes],
            "connections": [{"id": f"foot_{kind[0]}{k:03d}", "kind": kind, "from": {"node": a, "port": pa},
                             "to": {"node": b, "port": pb}, "route": [], "label": None}
                            for k, (kind, a, pa, b, pb) in enumerate(conns, start=1)],
            "subsystemPorts": [], "annotations": [],
        },
        "pins": {"params": ["Local/x", "Local/y", "Local/z", "Mount/x", "Mount/y", "Mount/z"], "starts": []},
    }


def build(variant: str = "single") -> Diagram:
    d = Diagram()
    mounts = MOUNTS[variant]
    # ---------------------------------------------------------------- tool motion (left)
    sc = "stdlib:motion/SCurveProfile"
    lift = dict(q_start="0", v_max=num(M["v_lift"]), a_max=num(M["a_lift"]), j_max=num(M["j_lift"]))
    d.node("Lift", sc, 40, 60, {**lift, "q_end": "H_lift", "t_start": "t_lift"})
    d.node("Lower", sc, 40, 200, {**lift, "q_end": f"-(H_lift + {num(D_PRESS)})", "t_start": "t_low"})
    d.node("Retract", sc, 40, 340, {**lift, "q_end": num(H_RET), "t_start": "t_ret"})
    d.node("Tool", "project:CupTool", 260, 200, {
        "motion": "motion", "t_x0": "t_x0",
        "A_st": "amp*A_st", "T_st": "T_st", "T_ring": "T_ring",
        "A_z": "amp*A_z", "f0_z": "fsc*f0_z", "f1_z": "fsc*f1_z", "T_cz": "T_cz",
        "a_s": "amp*a_s", "T_p": "T_p", "T_c": "T_c", "tau_s": "tau_s",
        "th_A": "amp*th_A", "T_sw": "T_sw", "T_h": "T_h", "th_B": "amp*th_B", "f_sw": "fsc*f_sw", "N_sw": "N_sw",
        "A_x": "amp*A_x", "f0_x": "fsc*f0_x", "f1_x": "fsc*f1_x", "T_cx": "T_cx",
        "a0": "a0", "T_env": "T_env",
    }, {"z": "z0"})
    for k, src in enumerate(["Lift", "Lower", "Retract"], start=1):
        d.conn("signal", src, "v", "Tool", f"zv{k}")
        d.conn("signal", src, "a", "Tool", f"za{k}")
    d.node("Grip", "stdlib:multibond/SfSpatial", 460, 200)
    d.junction("TJ", "1", 560, 300)
    d.conn("signal", "Tool", "tw", "Grip", "u")
    d.conn("bond", "Grip", "p", "TJ", None)
    d.node("Valve", "stdlib:sources/Step", 460, 520, {"t_step": "t_rel", "initial": "1", "final": "0"})
    d.node("Table", "stdlib:contact/ContactSurface", 1400, 980, {})

    for n, (mx, my) in enumerate(mounts, start=1):
        s = SUFFIX[n]
        y0 = 80 + 900 * (n - 1)
        # ------------------------------------------------------------ cup and its vacuum
        d.node(f"GMount{s}", "stdlib:multibond/FixedTransform3DNeutral", 660, y0,
               {"x": num(-mx), "y": num(-my), "z": "0"})
        d.node(f"Cup{s}", "stdlib:contact/SuctionCup", 820, y0, cup_params(linear=(n == 2)), {"rz": "-L0"})
        d.node(f"PMount{s}", "stdlib:multibond/FixedTransform3DNeutral", 980, y0,
               {"x": "cx", "y": "cy", "z": "-(H_p/2 - cz)"})
        d.node(f"Gen{s}", "stdlib:contact/VacuumGenerator", 820, y0 + 180,
               {"dp_max": "dp_max", "Q_max": "Q_max", "n": "1", "G_rel": "G_rel"})
        d.conn("bond", "TJ", None, f"GMount{s}", "b")
        d.conn("bond", f"GMount{s}", "a", f"Cup{s}", "a")
        d.conn("wire", f"Gen{s}", "a", f"Cup{s}", "vac")
        d.conn("signal", "Valve", "y", f"Gen{s}", "u")
        # ------------------------------------------------------------ payload
        d.node(f"Box{s}", "stdlib:spatial/RigidBody3D", 1160, y0 + 60,
               {"m": "m_p", "J": "[Jx, Jy, Jz]", "g0": num(P.G0)},
               {"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
        d.node(f"Pose{s}", "stdlib:multibond/PoseIntegrator3D", 1160, y0 + 220, {},
               {"qw": "1", "qx": "0", "qy": "0", "qz": "0",
                "px": f"{num(mx)} + cx", "py": f"{num(my)} + cy", "pz": "H_p/2 + cz - pen0"})
        d.conn("signal", f"Box{s}", "V", f"Pose{s}", "tw")
        d.conn("signal", f"Pose{s}", "g", f"Box{s}", "g")
        d.conn("bond", f"Box{s}", "p", f"PMount{s}", "b")
        d.conn("bond", f"PMount{s}", "a", f"Cup{s}", "b")
        # table contact under the four bottom corners (instances of library/ContactFoot)
        for k, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)], start=1):
            cxe, cye, cze = f"{sx}*L_p/2 - cx", f"{sy}*W_p/2 - cy", "-H_p/2 - cz"
            foot = f"Floor{s}{k}"
            d.node(foot, "project:ContactFoot", 1400 + 200 * ((k - 1) % 2), y0 + 340 + 200 * ((k - 1) // 2),
                   {"Local/x": cxe, "Local/y": cye, "Local/z": cze,
                    "Mount/x": f"-({cxe})", "Mount/y": f"-({cye})", "Mount/z": f"-({cze})"})
            d.conn("bond", f"Box{s}", "p", foot, "p")
            d.conn("signal", f"Pose{s}", "g", foot, "pose")
            d.conn("signal", "Table", "o", foot, "o")
            d.conn("signal", "Table", "fr", foot, "fr")
        # ------------------------------------------------------------ monitor (and the drawn cup)
        d.node(f"Mon{s}", "project:CupMonitor", 1160, y0 + 380, {
            "mx": num(mx), "my": num(my), "bx": "-cx", "by": "-cy", "bz": "H_p/2 - cz", "L0": "L0", "t_rel": "t_rel"})
        d.conn("signal", "Tool", "g", f"Mon{s}", "gt")
        d.conn("signal", f"Pose{s}", "g", f"Mon{s}", "gp")
        d.conn("signal", f"Cup{s}", "sealed", f"Mon{s}", "sealed")
        for sig in ("ext", "T"):
            d.conn("signal", f"Cup{s}", sig, f"Mon{s}", sig)
        # ------------------------------------------------------------ transmissibility (lateral chirp)
        d.node(f"Trans{s}", "project:Transmissibility", 1160, y0 + 560, {"w_lp": "w_lp"})
        d.conn("signal", f"Pose{s}", "g", f"Trans{s}", "gp")
        d.conn("signal", "Tool", "xc", f"Trans{s}", "xc")
        d.conn("signal", "Tool", "sp", f"Trans{s}", "sp")
        d.conn("signal", "Tool", "cp", f"Trans{s}", "cp")
        d.conn("signal", "Tool", "A", f"Trans{s}", "A")
        d.conn("signal", "Tool", "f", f"Trans{s}", "f")
        d.conn("signal", "Tool", "g", f"Trans{s}", "gt")
    d.note("One bellows suction cup (nonlinear bellows) on a tool with a prescribed motion holds a box. "
           "motion: 1 hold, 2 vertical bounce, 3 horizontal steps, 4 tilt swing, 5 lateral chirp. "
           "Mon draws the cup in 3D and latches a drop; Trans demodulates the lateral chirp.",
           40, 520, 360, 120)
    return d


def plots(variant: str) -> list[dict]:
    out = [
        {"id": "p1", "title": "Cup utilisation U (1 = pull-off, peel or slip)", "signals": ["Cup/U"]},
        {"id": "p2", "title": "Axial: bellows force Fs, transmitted T, holding force Fcap [N]", "signals": ["Cup/Fs", "Cup/T", "Cup/Fcap"]},
        {"id": "p3", "title": "Force-stroke while sealed: transmitted force T [N] against ext [m]", "signals": ["Mon/T_c"], "x": "Mon/ext_c"},
        {"id": "p4", "title": "Lateral force Flx [N] against the bellows deflection ex [m]", "signals": ["Cup/Flx"], "x": "Cup/ex"},
        {"id": "p5", "title": "Deflections: axial ext, lateral ex [m], lip gap h [m]", "signals": ["Cup/ext", "Cup/ex", "Cup/h"]},
        {"id": "p6", "title": "Vacuum [Pa]", "signals": ["Cup/dp", "Gen/dp"]},
        {"id": "p7", "title": "Tool: tilt [deg], payload tilt relative to the tool [deg]", "signals": ["Tool/theta", "Mon/sway"]},
        {"id": "p8", "title": "Transmissibility (lateral chirp) against the frequency [Hz]", "signals": ["Trans/TR"], "x": "Trans/fl"},
        {"id": "p9", "title": "Nonlinear terms: bottoming push F_bot [N], side stiffness factor kf", "signals": ["Cup/F_bot", "Cup/kf"]},
        {"id": "p10", "title": "Grip status", "signals": ["Cup/sealed", "Mon/held"]},
    ]
    if variant == "compare":
        out = [
            {"id": "p1", "title": "Utilisation U: nonlinear cup (Cup) and linear cup (CupL)", "signals": ["Cup/U", "CupL/U"]},
            {"id": "p2", "title": "Nonlinear cup: transmitted force T [N] against its ext [m], while sealed", "signals": ["Mon/T_c"], "x": "Mon/ext_c"},
            {"id": "p3", "title": "Linear cup: transmitted force T [N] against its ext [m], while sealed", "signals": ["MonL/T_c"], "x": "MonL/ext_c"},
            {"id": "p4", "title": "Axial extension ext [m]", "signals": ["Cup/ext", "CupL/ext"]},
            {"id": "p5", "title": "Lip gap h [m]", "signals": ["Cup/h", "CupL/h"]},
            {"id": "p6", "title": "Vacuum [Pa]", "signals": ["Cup/dp", "CupL/dp"]},
            {"id": "p7", "title": "Bottoming push F_bot [N] and side stiffness factor kf (nonlinear cup)", "signals": ["Cup/F_bot", "Cup/kf"]},
            {"id": "p8", "title": "Grip status", "signals": ["Cup/sealed", "CupL/sealed", "Mon/held", "MonL/held"]},
        ]
    return out


def bindings(variant: str) -> list[dict]:
    out = [{"target": "link:tool", "property": "pose", "signal": [f"Tool/g[{k}]" for k in range(1, 8)]}]
    for n in range(1, len(MOUNTS[variant]) + 1):
        s = SUFFIX[n]
        out.append({"target": f"link:box_{n}", "property": "pose",
                    "signal": [f"Pose{s}/{c}" for c in ("qw", "qx", "qy", "qz", "px", "py", "pz")]})
        for vis, sig in (("bellows", "bel"), ("ring1", "ring1"), ("ring2", "ring2"), ("lip", "lip")):
            out.append({"target": f"visual:{vis}_{n}", "property": "segment",
                        "signal": [f"Mon{s}/{sig}[{k}]" for k in range(1, 7)]})
        out.append({"target": f"visual:lip_{n}", "property": "color", "signal": f"Cup{s}/U",
                    "colormap": "coolwarm", "range": [0.0, 1.0]})
        out.append({"target": f"visual:bellows_{n}", "property": "color", "signal": f"Cup{s}/dp",
                    "colormap": "viridis", "range": [0.0, 60000.0]})
    return out


def dashboard(variant: str) -> dict:
    gauge_zones = [{"from": 0, "to": 0.5, "tone": "good"}, {"from": 0.5, "to": 1.0, "tone": "warn"},
                   {"from": 1.0, "to": 1.2, "tone": "bad"}]
    sliders = [
        {"id": "mass", "kind": "slider", "size": "2x1", "title": "Payload mass", "parameter": "global:m_p",
         "options": {"min": 0.1, "max": 3.0, "step": 0.05, "decimals": 2, "unit": "kg"}},
        {"id": "cx", "kind": "slider", "size": "2x1", "title": "Centre of mass offset x", "parameter": "global:cx",
         "options": {"min": -0.05, "max": 0.05, "step": 0.005, "decimals": 3, "unit": "m"}},
        {"id": "vac", "kind": "slider", "size": "2x1", "title": "Vacuum level (ejector end vacuum)", "parameter": "global:dp_max",
         "options": {"min": 20000, "max": 80000, "step": 2500, "decimals": 0, "unit": "Pa"}},
        {"id": "amp", "kind": "slider", "size": "2x1", "title": "Motion amplitude (scale)", "parameter": "global:amp",
         "options": {"min": 0.25, "max": 2.0, "step": 0.05, "decimals": 2, "unit": ""}},
        {"id": "fsc", "kind": "slider", "size": "2x1", "title": "Motion frequency (scale)", "parameter": "global:fsc",
         "options": {"min": 0.5, "max": 2.0, "step": 0.05, "decimals": 2, "unit": ""}},
    ]
    if variant == "compare":
        return {"autoRerun": False, "cards": [
            {"id": "fs", "kind": "plot", "size": "2x2", "title": "Force-stroke while sealed: T [N] against ext [m] (nonlinear)",
             "signals": ["Mon/T_c"], "x": "Mon/ext_c"},
            {"id": "fsl", "kind": "plot", "size": "2x2", "title": "Force-stroke while sealed: T [N] against ext [m] (linear)",
             "signals": ["MonL/T_c"], "x": "MonL/ext_c"},
            {"id": "ext", "kind": "plot", "size": "2x2", "title": "Axial extension ext [m]: nonlinear, linear",
             "signals": ["Cup/ext", "CupL/ext"]},
            {"id": "u", "kind": "plot", "size": "2x2", "title": "Utilisation U: nonlinear, linear", "signals": ["Cup/U", "CupL/U"]},
            {"id": "un", "kind": "gauge", "size": "1x1", "title": "U nonlinear", "signals": ["Cup/U"],
             "options": {"min": 0, "max": 1.2, "decimals": 2, "zones": gauge_zones}},
            {"id": "ul", "kind": "gauge", "size": "1x1", "title": "U linear", "signals": ["CupL/U"],
             "options": {"min": 0, "max": 1.2, "decimals": 2, "zones": gauge_zones}},
            {"id": "hn", "kind": "indicator", "size": "1x1", "title": "Nonlinear cup holds", "signals": ["Mon/held"],
             "options": {"threshold": 0.5, "onWhen": "above"}},
            {"id": "hl", "kind": "indicator", "size": "1x1", "title": "Linear cup holds", "signals": ["MonL/held"],
             "options": {"threshold": 0.5, "onWhen": "above"}},
            *sliders,
        ]}
    return {"autoRerun": False, "cards": [
        {"id": "fs", "kind": "plot", "size": "2x2", "title": "Force-stroke while sealed: transmitted force T [N] against ext [m]",
         "signals": ["Mon/T_c"], "x": "Mon/ext_c"},
        {"id": "lat", "kind": "plot", "size": "2x2", "title": "Lateral force Flx [N] against the deflection ex [m]",
         "signals": ["Cup/Flx"], "x": "Cup/ex"},
        {"id": "ut", "kind": "plot", "size": "2x2", "title": "Utilisation U over time (1 = pull-off, peel or slip)", "signals": ["Cup/U"]},
        {"id": "tr", "kind": "plot", "size": "2x2", "title": "Transmissibility against the chirp frequency [Hz] (motion 5)",
         "signals": ["Trans/TR"], "x": "Trans/fl"},
        {"id": "u", "kind": "gauge", "size": "1x1", "title": "Utilisation U", "signals": ["Cup/U"],
         "options": {"min": 0, "max": 1.2, "decimals": 2, "zones": gauge_zones}},
        {"id": "held", "kind": "indicator", "size": "1x1", "title": "Payload held", "signals": ["Mon/held"],
         "options": {"threshold": 0.5, "onWhen": "above"}},
        {"id": "h", "kind": "value", "size": "1x1", "title": "Lip gap h", "signals": ["Cup/h"],
         "options": {"decimals": 5, "sparkline": True, "unit": "m"}},
        {"id": "dp", "kind": "value", "size": "1x1", "title": "Vacuum", "signals": ["Cup/dp"],
         "options": {"decimals": 0, "sparkline": True, "unit": "Pa"}},
        {"id": "ext", "kind": "value", "size": "1x1", "title": "Axial extension", "signals": ["Cup/ext"],
         "options": {"decimals": 5, "sparkline": True, "unit": "m"}},
        {"id": "ex", "kind": "value", "size": "1x1", "title": "Lateral deflection", "signals": ["Cup/ex"],
         "options": {"decimals": 5, "sparkline": True, "unit": "m"}},
        {"id": "sway", "kind": "value", "size": "1x1", "title": "Tilt of the box (to the tool)", "signals": ["Mon/sway"],
         "options": {"decimals": 2, "sparkline": True, "unit": "deg"}},
        {"id": "fcap", "kind": "value", "size": "1x1", "title": "Holding capacity", "signals": ["Cup/Fcap"],
         "options": {"decimals": 1, "sparkline": True, "unit": "N"}},
        *sliders,
    ]}


#: name -> (comment, global overrides, variant)
SCENARIOS = {
    "hold-release": (
        "Static hold: the vacuum builds up on the box resting on the table, the bellows contracts under the "
        "vacuum (lift stroke) and lifts the box off the table; lift, hold, lower and release.",
        {"motion": "1"}, "single"),
    "bounce": (
        "Vertical bounce: a quick 4 mm step down rings the axial spring-mass mode, then a vertical chirp "
        "(3 to 20 Hz, amplitude rising to 1.7 mm) passes the resonance; the folds bottom on compression.",
        {"motion": "2"}, "single"),
    "steps": (
        "Horizontal acceleration steps (1.5, 3 and 4.5 m/s^2): the box sways and tilts, the bellows shears, the "
        "lip load rises on one side; the cup holds.", {"motion": "3"}, "single"),
    "swing": (
        "Tool tilt: a slow swing to 30 degrees and back (the cup carries the box sideways: shear and moment), "
        "then a fast +-10 degree swing at 1.5 Hz.", {"motion": "4"}, "single"),
    "chirp": (
        "Lateral chirp 1.5 to 20 Hz with 0.4 mm amplitude: the lateral/tilt resonance of the box on the cup, "
        "with the transmissibility from the tool to the box.", {"motion": "5"}, "single"),
    "overload": (
        "Overload: a 0.8 kg box on the horizontal steps up to 9 m/s^2: the lip peels on one side, the gap "
        "opens a leak, the seal is lost and the box falls.", {"motion": "3", "m_p": "0.8", "a_s": "9"}, "single"),
    "linear-vs-nonlinear": (
        "The nonlinear cup (left, blue box) next to the same cup with the nonlinear bellows off (right, sand "
        "box) on the vertical bounce: the lift stroke, the bottoming and the stiffer, safer hold.",
        {"motion": "2"}, "compare"),
}


def model_document(name: str, comment: str, overrides: dict, variant: str) -> dict:
    d = build(variant)
    g = globals_table(overrides)
    gv = {row["name"]: row["value"] for row in g}
    t_end = t_end_of(gv)
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": comment,
        "diagram": {"nodes": d.nodes, "connections": d.conns, "annotations": d.notes},
        "settings": {
            "t_start": 0.0, "t_end": t_end, "solver": "FBDF", "reltol": 1e-6, "abstol": 1e-8,
            "max_step": None, "output": {"mode": "points", "points": int(round(t_end * 500)) + 1},
            "event_limit": 20000,
        },
        "parameters": g,
        "plots": plots(variant),
        "scene": {"file": f"scenes/{'suction-cup-compare' if variant == 'compare' else 'suction-cup'}.sdf"},
        "bindings": bindings(variant),
        "dashboard": dashboard(variant),
    }


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline=NL)


def main() -> None:
    import scene
    (ROOT / "scenes").mkdir(exist_ok=True)
    _write(ROOT / "scenes" / "suction-cup.sdf", scene.scene_sdf(MOUNTS["single"]))
    _write(ROOT / "scenes" / "suction-cup-compare.sdf", scene.scene_sdf(MOUNTS["compare"]))
    _write(ROOT / "library" / "ContactFoot.bgsub.json", json.dumps(foot_definition(), indent=2) + NL)
    out_dir = ROOT / "models"
    out_dir.mkdir(exist_ok=True)
    for name, (comment, overrides, variant) in SCENARIOS.items():
        doc = model_document(name, comment, overrides, variant)
        out = out_dir / f"{name}.bgmodel.json"
        _write(out, json.dumps(doc, indent=2) + NL)
        print("wrote", out, "t_end", doc["settings"]["t_end"])
    proj = ROOT / "bgsim.project.json"
    _write(proj, json.dumps({"format": "bgsim.project", "language": "0.1.0", "name": "suction-cup",
                             "models": list(SCENARIOS), "libraryDir": "library", "scenesDir": "scenes"},
                            indent=2) + NL)


if __name__ == "__main__":
    main()
