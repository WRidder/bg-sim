# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Writes the models, the 3D scene and expected.json of the excavator example.

    uv run examples/excavator/design/design.py        # reference numbers -> design.json
    uv run examples/excavator/design/build_model.py   # models/*.bgmodel.json, scenes/, expected.json

Models (one mechanism, three set-ups):

* ``excavator-kinematics``: the front without gravity, every cylinder replaced by a stiff
  length servo; the cylinder-length set points move the joints through the linkage, and the
  bucket tip is checked against a scipy forward kinematics of the set lengths.
* ``excavator-lift``: the full load-sensing hydraulics holding a 1.5 t payload, ringing at the
  boom's hydraulic natural frequency after a pressure sag, then a boom lift at half joystick.
* ``excavator-dig-cycle``: a scripted joystick dig cycle (penetrate, curl, lift, dump,
  return) into soil with the earthmoving-equation cutting force and the bucket fill.
* ``excavator-no-ls``: the same dig cycle with a fixed-displacement pump and the relief as the
  only pressure control (a constant-pressure system), to compare the energy.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import exc_geom as G  # noqa: E402

DES = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
CYL = DES["cylinders"]
HYD = DES["hydraulics"]
BODIES = DES["bodies"]
SOIL = DES["soil"]
NAMES = ("boom", "arm", "bucket")
CAP = {"boom": "Boom", "arm": "Arm", "bucket": "Bucket"}
G0 = 9.81
NL = chr(10)


def num(x: float) -> str:
    text = repr(float(x))
    return text[:-2] if text.endswith(".0") and "e" not in text else text


def vec(xs) -> str:
    return "[" + ", ".join(num(x) for x in xs) + "]"


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.notes: list[dict] = []

    def node(self, name: str, ref: str, x: float, y: float, params: dict | None = None,
             starts: dict | None = None, constants: dict | None = None, rotation: int = 0,
             flip: bool = False) -> str:
        self.nodes.append({
            "id": name, "name": name, "block": {"ref": ref},
            "position": {"x": x, "y": y}, "rotation": rotation, "flipX": flip,
            "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
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

    def bond(self, a, pa, b, pb) -> None:
        self.conn("bond", a, pa, b, pb)

    def wire(self, a, pa, b, pb) -> None:
        self.conn("wire", a, pa, b, pb)

    def sig(self, a, pa, b, pb) -> None:
        self.conn("signal", a, pa, b, pb)

    def note(self, text: str, x: float, y: float, w: float, h: float, color: str = "yellow") -> None:
        self.notes.append({"id": f"note{len(self.notes) + 1}", "kind": "text", "text": text,
                           "x": x, "y": y, "w": w, "h": h, "color": color})


# --------------------------------------------------------------------------- mechanism
PIVOT = {"kt": "k_pin", "bt": "b_pin"}
STOP = {"kL": "k_stop", "bL": "b_stop", "delta": "0.002"}


def mechanism(d: Diagram, q0, bucket: dict, g0: str) -> None:
    """Ground, three limited revolute joints, the three bodies on their 1-junctions and the
    composed world poses (joint frames, centres of mass, cylinder pins, the bucket tip)."""
    L1, L2 = G.L1, G.L2
    bb, ba = BODIES["boom"], BODIES["arm"]
    X = 1500
    d.node("Ground", "stdlib:multibond/GroundPlanar", X, 60)
    # boom
    d.node("Joint1", "stdlib:planar/Revolute2DLimit", X, 180,
           {"rx": "0.0", "ry": "0.0", **PIVOT, "lower": num(CYL["boom"]["q_lower"]),
            "upper": num(CYL["boom"]["q_upper"]), **STOP, "q0": num(q0[0])}, {"d": "[0.0, 0.0]"})
    d.node("Link1", "stdlib:planar/FixedJoint2D", X, 300, {"x": num(bb["c"][0]), "y": num(bb["c"][1]), "theta": "0.0"})
    d.junction("BodyJ1", "1", X, 420)
    d.node("Boom", "stdlib:planar/RigidBody2D", X + 160, 420, {"m": "m_boom", "J": "J_boom", "g0": g0})
    d.bond("Ground", "p", "Joint1", "parent")
    d.bond("Joint1", "child", "Link1", "parent")
    d.bond("Link1", "child", "BodyJ1", None)
    d.bond("Boom", "p", "BodyJ1", None)
    # arm (joint 2 at C, in the boom's centre-of-mass frame)
    d.node("Joint2", "stdlib:planar/Revolute2DLimit", X, 560,
           {"rx": num(L1 - bb["c"][0]), "ry": num(-bb["c"][1]), **PIVOT, "lower": num(CYL["arm"]["q_lower"]),
            "upper": num(CYL["arm"]["q_upper"]), **STOP, "q0": num(q0[1])}, {"d": "[0.0, 0.0]"})
    d.node("Link2", "stdlib:planar/FixedJoint2D", X, 680, {"x": num(ba["c"][0]), "y": num(ba["c"][1]), "theta": "0.0"})
    d.junction("BodyJ2", "1", X, 800)
    d.node("Arm", "stdlib:planar/RigidBody2D", X + 160, 800, {"m": "m_arm", "J": "J_arm", "g0": g0})
    d.bond("Joint2", "parent", "BodyJ1", None)
    d.bond("Joint2", "child", "Link2", "parent")
    d.bond("Link2", "child", "BodyJ2", None)
    d.bond("Arm", "p", "BodyJ2", None)
    # bucket (joint 3 at Q, in the arm's centre-of-mass frame)
    d.node("Joint3", "stdlib:planar/Revolute2DLimit", X, 940,
           {"rx": num(L2 - ba["c"][0]), "ry": num(-ba["c"][1]), **PIVOT, "lower": num(CYL["bucket"]["q_lower"]),
            "upper": num(CYL["bucket"]["q_upper"]), **STOP, "q0": num(q0[2])}, {"d": "[0.0, 0.0]"})
    d.node("Link3", "stdlib:planar/FixedJoint2D", X, 1060, {"x": "cx_bucket", "y": "cy_bucket", "theta": "0.0"})
    d.junction("BodyJ3", "1", X, 1180)
    d.node("Bucket", "stdlib:planar/RigidBody2D", X + 160, 1180, {"m": "m_bucket", "J": "J_bucket", "g0": g0})
    d.bond("Joint3", "parent", "BodyJ2", None)
    d.bond("Joint3", "child", "Link3", "parent")
    d.bond("Link3", "child", "BodyJ3", None)
    d.bond("Bucket", "p", "BodyJ3", None)

    # ---- poses (world): joint frames O/C/Q, centres of mass, pins, tip
    P = 1900
    lp = "stdlib:planar/LocalPose2D"
    cp = "stdlib:multibond/ComposePose2D"
    jp = "stdlib:planar/JointPose2D"

    def local(name, x, y, xx, yy, theta="0.0"):
        d.node(name, lp, xx, yy, {"x": x, "y": y, "theta": theta})

    def compose(name, gp, gl, xx, yy, gp_port="g", gl_port="g"):
        d.node(name, cp, xx, yy)
        d.sig(gp, gp_port, name, "gp")
        d.sig(gl, gl_port, name, "gl")

    d.node("PoseO", jp, P, 180, {"rx": "0.0", "ry": "0.0", "theta0": "0.0"})
    d.sig("Joint1", "qout", "PoseO", "q")
    local("CoM1", num(bb["c"][0]), num(bb["c"][1]), P, 300)
    compose("PoseB1", "PoseO", "CoM1", P + 160, 300)
    d.sig("PoseB1", "g", "Boom", "g")
    d.node("PoseCrel", jp, P, 560, {"rx": num(L1 - bb["c"][0]), "ry": num(-bb["c"][1]), "theta0": "0.0"})
    d.sig("Joint2", "qout", "PoseCrel", "q")
    compose("PoseC", "PoseB1", "PoseCrel", P + 160, 560)
    local("CoM2", num(ba["c"][0]), num(ba["c"][1]), P, 680)
    compose("PoseB2", "PoseC", "CoM2", P + 160, 680)
    d.sig("PoseB2", "g", "Arm", "g")
    d.node("PoseQrel", jp, P, 940, {"rx": num(L2 - ba["c"][0]), "ry": num(-ba["c"][1]), "theta0": "0.0"})
    d.sig("Joint3", "qout", "PoseQrel", "q")
    compose("PoseQ", "PoseB2", "PoseQrel", P + 160, 940)
    local("CoM3", "cx_bucket", "cy_bucket", P, 1060)
    compose("PoseB3", "PoseQ", "CoM3", P + 160, 1060)
    d.sig("PoseB3", "g", "Bucket", "g")
    local("TipOffset", num(G.L3), "0.0", P, 1180)
    compose("PoseTip", "PoseQ", "TipOffset", P + 160, 1180)

    # ---- cylinder pins and the bucket four-bar
    Q = 2300
    g = G.GEOM
    local("PinA1", num(g["A1"][0]), num(g["A1"][1]), Q, 180)
    local("LocB1", num(g["B1"][0]), num(g["B1"][1]), Q, 260)
    compose("PinB1", "PoseO", "LocB1", Q + 160, 260)
    local("LocA2", num(g["A2"][0]), num(g["A2"][1]), Q, 400)
    compose("PinA2", "PoseO", "LocA2", Q + 160, 400)
    local("LocB2", num(g["B2"][0]), num(g["B2"][1]), Q, 480)
    compose("PinB2", "PoseC", "LocB2", Q + 160, 480)
    local("LocA3", num(g["A3"][0]), num(g["A3"][1]), Q, 640)
    compose("PinA3", "PoseC", "LocA3", Q + 160, 640)
    local("LocR", num(g["R"][0]), num(g["R"][1]), Q, 720)
    compose("PinR", "PoseC", "LocR", Q + 160, 720)
    d.node("Linkage", "project:BucketLinkage2D", Q, 840,
           {"Qx": num(L2), "Rx": num(g["R"][0]), "Ry": num(g["R"][1]), "Px": num(g["P"][0]), "Py": num(g["P"][1]),
            "lr": num(g["lr"]), "lc": num(g["lc"]), "branch": num(G.FOUR_BAR_BRANCH)})
    d.sig("Joint3", "qout", "Linkage", "q")
    compose("PinJ", "PoseC", "Linkage", Q + 160, 840, gl_port="gJ")
    compose("PinP", "PoseC", "Linkage", Q + 160, 920, gl_port="gP")
    for name, gA, gB, gJ, y in (("boom", "PinA1", "PinB1", "PoseO", 180), ("arm", "PinA2", "PinB2", "PoseC", 400),
                                ("bucket", "PinA3", "PinJ", "PinR", 640)):
        c = CYL[name]
        m = CAP[name] + "Mount"
        lb = c["L_closed"] - 0.12
        d.node(m, "project:CylinderMount2D", Q + 360, y,
               {"L0": num(c["L_closed"]), "lb": num(round(lb, 3)), "lr": num(round(c["stroke"] + 0.2, 3))})
        d.sig(gA, "g", m, "gA")
        d.sig(gB, "g", m, "gB")
        d.sig(gJ, "g", m, "gJ")


def drive_chain(d: Diagram, name: str, x: float, y: float) -> str:
    """Rod 1-junction -> rack-and-pinion (a unit domain bridge) -> modulated transformer(s)
    -> joint drive. Returns the rod junction."""
    C = CAP[name]
    rod = d.junction(f"{C}Rod", "1", x, y)
    d.node(f"{C}RP", "stdlib:converters/RackAndPinion", x + 120, y, {"r": "1.0"})
    d.bond(f"{C}RP", "b", rod, None)
    joint = {"boom": "Joint1", "arm": "Joint2", "bucket": "Joint3"}[name]
    if name != "bucket":
        d.node(f"{C}Lever", "stdlib:bondgraph/MTF", x + 240, y)
        d.bond(f"{C}RP", "a", f"{C}Lever", "p2")
        d.bond(f"{C}Lever", "p1", joint, "drive")
        d.sig(f"{C}Mount", "r", f"{C}Lever", "u")
    else:
        d.node("BucketLever", "stdlib:bondgraph/MTF", x + 240, y)
        d.node("FourBar", "stdlib:bondgraph/MTF", x + 360, y)
        d.bond("BucketRP", "a", "BucketLever", "p2")
        d.bond("BucketLever", "p1", "FourBar", "p2")
        d.bond("FourBar", "p1", joint, "drive")
        d.sig("BucketMount", "r", "BucketLever", "u")
        d.sig("Linkage", "k", "FourBar", "u")
    return rod


# --------------------------------------------------------------------------- hydraulics
def cylinder(d: Diagram, name: str, rod: str, x: float, y: float, start: dict) -> str:
    C = CAP[name]
    c = CYL[name]
    cyl = d.node(f"{C}Cyl", "stdlib:converters/HydraulicCylinder", x, y,
                 {"Ap": num(c["Ap"]), "Ar": num(c["Ar"]), "V0A": num(c["V0"]), "V0B": num(c["V0"]),
                  "beta": "beta", "stroke": num(c["stroke"])},
                 {"x": num(start["x"]), "pA": start["pA"], "pB": start["pB"]})
    d.bond(rod, None, cyl, "rod")
    d.node(f"{C}Fric", "stdlib:translation/Friction", x + 120, y + 100,
           {"Fs": num(c["Fc"]), "Fc": num(c["Fc"]), "Fv": num(c["Fv"]), "v_s": "0.01", "v_eps": "0.005"})
    d.node(f"{C}Barrel", "stdlib:translation/Fixed", x + 240, y + 100)
    d.bond(rod, None, f"{C}Fric", "a")
    d.wire(f"{C}Fric", "b", f"{C}Barrel", "a")
    return cyl


PUMP_LINE = ("Vpump", "a")
TANK = ("Tank", "a")
LS_LINE = ("Vls", "a")


def section(d: Diagram, name: str, cyl: str, x: float, y: float, cmd: tuple[str, str], ls: bool) -> None:
    """One pre-compensated LS valve section: compensator + meter-in (PCFC on |spool|) into
    the section volume, the directional spool (4/3) to the cylinder chambers, anti-cavitation
    checks from the tank, and the LS edge of the spool with its shuttle (a check valve) into
    the common LS line. The circuit is wired (connection sets): every node is one volume (a
    Volume block or a cylinder chamber) that the valves around it are wired to."""
    C = CAP[name]
    a_sp = HYD["A_spool"][name]
    rho = num(HYD["rho"])
    d.node(f"{C}Spool", "stdlib:continuous/FirstOrder", x, y, {"k": "1.0", "tau": "tau_spool"})
    d.sig(cmd[0], cmd[1], f"{C}Spool", "u")
    d.node(f"{C}Abs", "stdlib:continuous/Abs", x + 120, y - 60)
    d.sig(f"{C}Spool", "y", f"{C}Abs", "u")
    d.node(f"{C}Comp", "stdlib:hydraulic/PressureCompensatedFlowControl", x + 240, y - 60,
           {"Q_nom": num(HYD["Q_nom"][name]), "dp_c": "dp_c", "p_tr": "1.0e5"})
    d.sig(f"{C}Abs", "y", f"{C}Comp", "u")
    d.wire(*PUMP_LINE, f"{C}Comp", "a")
    d.node(f"{C}Vin", "stdlib:hydraulic/Volume", x + 360, y - 160, {"V": num(HYD["V_sec"]), "beta": "beta"},
           {"p": "1.0e5"})
    d.wire(f"{C}Comp", "b", f"{C}Vin", "a")
    d.node(f"{C}Valve", "stdlib:hydraulic/DirectionalValve43", x + 480, y,
           {"A_max": num(a_sp), "A_leak": "1.0e-10", "lap": "0.0", "Cd": "0.62", "rho": rho, "p_tr": "1.0e5"})
    d.sig(f"{C}Spool", "y", f"{C}Valve", "u")
    d.wire(f"{C}Vin", "a", f"{C}Valve", "P")
    d.wire(f"{C}Valve", "T", *TANK)
    d.wire(f"{C}Valve", "A", cyl, "A")
    d.wire(f"{C}Valve", "B", cyl, "B")
    for k, port in enumerate(("A", "B")):
        d.node(f"{C}MakeUp{port}", "stdlib:hydraulic/CheckValve", x + 620, y - 160 + 320 * k,
               {"p_crack": "3.0e4", "dp_open": "1.0e5", "A_max": "2.0e-4", "A_leak": "1.0e-11", "rho": rho})
        d.wire(*TANK, f"{C}MakeUp{port}", "a")
        d.wire(f"{C}MakeUp{port}", "b", cyl, port)
    # readouts: chamber pressures -> cylinder force -> joint torque -> power
    c = CYL[name]
    for k, port in enumerate(("A", "B")):
        d.node(f"{C}p{port}", "stdlib:converters/PressureSensor", x + 760, y - 60 + 120 * k)
        d.wire(cyl, port, f"{C}p{port}", "a")
    d.node(f"{C}pAB", "stdlib:continuous/Mux2", x + 820, y)
    d.sig(f"{C}pA", "y", f"{C}pAB", "u1")
    d.sig(f"{C}pB", "y", f"{C}pAB", "u2")
    d.node(f"{C}Force", "stdlib:continuous/Sum", x + 900, y, {"signs": vec([c["Ap"], -c["Ar"]])}, constants={"N": 2})
    d.sig(f"{C}pAB", "y", f"{C}Force", "u")
    d.node(f"{C}Torque", "stdlib:continuous/Product", x + 1000, y)
    d.sig(f"{C}Force", "y", f"{C}Torque", "u1")
    d.sig(f"{C}Mount", "r", f"{C}Torque", "u2")
    d.node(f"{C}Power", "stdlib:continuous/Product", x + 1120, y)
    d.sig(f"{C}Torque", "y", f"{C}Power", "u1")
    d.sig({"boom": "Joint1", "arm": "Joint2", "bucket": "Joint3"}[name], "qdout", f"{C}Power", "u2")
    if not ls:
        return
    # LS edge of the spool: P = the section's LS chamber, A/B the work ports, T the tank
    d.node(f"{C}LSEdge", "stdlib:hydraulic/DirectionalValve43", x + 480, y + 160,
           {"A_max": "A_ls", "A_leak": "1.0e-10", "lap": "0.0", "Cd": "0.62", "rho": rho, "p_tr": "1.0e5"})
    d.sig(f"{C}Spool", "y", f"{C}LSEdge", "u")
    d.node(f"{C}Vls", "stdlib:hydraulic/Volume", x + 240, y + 160, {"V": num(HYD["V_ls_sec"]), "beta": "beta"},
           {"p": "1.0e5"})
    d.wire(f"{C}Vls", "a", f"{C}LSEdge", "P")
    d.wire(f"{C}LSEdge", "T", *TANK)
    d.wire(f"{C}LSEdge", "A", cyl, "A")
    d.wire(f"{C}LSEdge", "B", cyl, "B")
    d.node(f"{C}Shuttle", "stdlib:hydraulic/CheckValve", x + 360, y + 260,
           {"p_crack": "0.0", "dp_open": "1.0e5", "A_max": "2.0e-6", "A_leak": "1.0e-12", "rho": rho})
    d.wire(f"{C}Vls", "a", f"{C}Shuttle", "a")
    d.wire(f"{C}Shuttle", "b", *LS_LINE)


A_BLEED = 2.2e-7     # LS bleed orifice, m^2 (about 1.4 l/min at 150 bar)


def supply(d: Diagram, ls: bool, x: float, y: float) -> None:
    """Engine (constant speed), the LS pump, the pump line, the main relief, the LS line with
    its bleed, the tank, and the energy meters. Without LS (``ls = False``) the pump's LS port
    is on the tank, so the same regulator holds the pump pressure at p_tank + dp_ls: a
    constant-pressure system."""
    rho = num(HYD["rho"])
    d.node("EngineSpeed", "stdlib:sources/Constant", x, y, {"value": "1.0"})
    d.node("Engine", "stdlib:rotation/SpeedSource", x + 120, y, {"w": "w_engine"})
    d.sig("EngineSpeed", "y", "Engine", "u")
    d.node("Tank", "stdlib:hydraulic/Tank", x + 240, y + 380, {"p": num(HYD["p_tank"])})
    d.node("Pump", "stdlib:converters/LoadSensingPump", x + 300, y,
           {"D": num(HYD["D_pump"]), "eta_v": num(HYD["eta_v"]), "eta_m": num(HYD["eta_m"]),
            "p_nom": num(HYD["p_nom"]), "w_nom": "w_engine", "dp_ls": "dp_ls", "dp_reg": num(HYD["dp_reg"]),
            "p_cut": num(HYD["p_cut"]), "T_max": "P_max/w_engine"})
    d.wire("Engine", "a", "Pump", "shaft")
    d.wire(*TANK, "Pump", "a")
    d.node("Vpump", "stdlib:hydraulic/Volume", x + 480, y - 120, {"V": num(HYD["V_pump"]), "beta": "beta"},
           {"p": num(HYD["p_tank"] + HYD["dp_ls"]) if ls else num(HYD["p_tank"] + 2.8e7)})
    d.wire("Pump", "b", *PUMP_LINE)
    d.node("Relief", "stdlib:hydraulic/PressureReliefValve", x + 600, y + 120,
           {"p_set": "p_relief", "dp_reg": "1.0e6", "A_max": "1.5e-4", "A_leak": "1.0e-11", "rho": rho})
    d.wire(*PUMP_LINE, "Relief", "a")
    d.wire("Relief", "b", *TANK)
    if ls:
        d.node("Vls", "stdlib:hydraulic/Volume", x + 180, y + 160, {"V": num(HYD["V_ls"]), "beta": "beta"},
               {"p": "1.0e5"})
        d.wire(*LS_LINE, "Pump", "ls")
        # LS bleed: a fixed orifice to the tank (the check-valve law held fully open by a
        # negative cracking pressure, so the orifice is regularised at zero flow)
        d.node("Bleed", "stdlib:hydraulic/CheckValve", x + 300, y + 260,
               {"p_crack": "-1.0e8", "dp_open": "1.0e5", "A_max": num(A_BLEED), "A_leak": num(A_BLEED), "rho": rho})
        d.wire(*LS_LINE, "Bleed", "a")
        d.wire("Bleed", "b", *TANK)
    else:
        d.wire(*TANK, "Pump", "ls")
    # energy meters: engine (shaft) energy, net cylinder work and their ratio
    d.node("Pmux", "stdlib:continuous/Mux3", x, y + 520)
    for k, name in enumerate(NAMES):
        d.sig(f"{CAP[name]}Power", "y", "Pmux", f"u{k + 1}")
    d.node("Pcyl", "stdlib:continuous/Sum", x + 120, y + 520, {"signs": "[1.0, 1.0, 1.0]"}, constants={"N": 3})
    d.sig("Pmux", "y", "Pcyl", "u")
    d.node("Ein", "stdlib:continuous/Integrator", x + 240, y + 460, {}, {"x": "1.0"})
    d.sig("Pump", "P_in", "Ein", "u")
    d.node("Ecyl", "stdlib:continuous/Integrator", x + 240, y + 580)
    d.sig("Pcyl", "y", "Ecyl", "u")
    d.node("Eff", "stdlib:continuous/Divide", x + 360, y + 520)
    d.sig("Ecyl", "y", "Eff", "u1")
    d.sig("Ein", "y", "Eff", "u2")


# --------------------------------------------------------------------------- globals
def globals_table(kind: str) -> list[dict]:
    b = BODIES["bucket"]
    p = DES["payload"]
    rows = [
        ("m_boom", num(BODIES["boom"]["m"]), "kg", "Boom mass (with its share of the cylinders)"),
        ("J_boom", num(BODIES["boom"]["J"]), "kg*m^2", "Boom inertia about its centre of mass"),
        ("m_arm", num(BODIES["arm"]["m"]), "kg", "Arm (stick) mass"),
        ("J_arm", num(BODIES["arm"]["J"]), "kg*m^2", "Arm inertia about its centre of mass"),
        ("m_bkt", num(b["m"]), "kg", "Bucket mass (with its linkage)"),
        ("J_bkt", num(b["J"]), "kg*m^2", "Bucket inertia about its centre of mass"),
        ("m_pay", num(p["m"]) if kind == "lift" else "0", "kg", "Payload rigidly carried in the bucket (lift model)"),
        ("m_bucket", "m_bkt + m_pay", "kg", "Bucket plus payload"),
        ("cx_bucket", f"(m_bkt*{num(b['c'][0])} + m_pay*{num(p['c'][0])})/m_bucket", "m", "Centre of mass x in the bucket frame"),
        ("cy_bucket", f"(m_bkt*{num(b['c'][1])} + m_pay*{num(p['c'][1])})/m_bucket", "m", "Centre of mass y in the bucket frame"),
        ("J_bucket", f"J_bkt + {num(p['J'])}*m_pay/{num(p['m'])} + m_bkt*m_pay/m_bucket*"
                     f"({num(b['c'][0] - p['c'][0])}^2 + {num(b['c'][1] - p['c'][1])}^2)", "kg*m^2",
         "Bucket plus payload inertia about their common centre of mass"),
        ("k_pin", "1.0e9", "N/m", "Pin (pivot) translational stiffness"),
        ("b_pin", "1.0e6", "N*s/m", "Pin translational damping"),
        ("k_stop", "2.0e7", "N*m/rad", "End-stop stiffness at the joints (the cylinder end stops)"),
        ("b_stop", "2.0e6", "N*m*s/rad", "End-stop damping"),
    ]
    if kind == "kin":
        rows += [
            ("k_servo", num(DES["kinematics"]["k_servo"]), "N/m", "Stiffness of the length servos that replace the cylinders"),
            ("d_servo", num(DES["kinematics"]["d_servo"]), "N*s/m", "Damping of the length servos"),
        ]
    else:
        rows += [
            ("beta", num(HYD["beta"]), "Pa", "Effective bulk modulus of the oil (with hoses)"),
            ("w_engine", num(HYD["w_engine"]), "rad/s", "Engine speed (1800 rpm, constant)"),
            ("dp_ls", num(HYD["dp_ls"]) if kind != "nols" else "2.8e7", "Pa",
             "LS margin of the pump regulator" if kind != "nols" else "Pump pressure setting above the tank (the LS port is on the tank)"),
            ("P_max", num(HYD["P_max"]), "W", "Pump power limit (torque limiter at the engine speed)"),
            ("p_relief", num(HYD["p_relief"]), "Pa", "Main relief valve setting"),
            ("dp_c", num(HYD["dp_c"]), "Pa", "Compensator setting of the valve sections"),
            ("tau_spool", num(HYD["tau_spool"]), "s", "Spool (pilot) time constant"),
            ("A_ls", num(HYD["A_ls"]), "m^2", "LS edge of each spool"),
        ]
    if kind == "lift":
        rows += [("u_lift", num(DES["lift"]["u_lift"]), "1", "Boom joystick during the lift (1 = full)")]
    if kind in ("dig", "nols"):
        rows += [
            ("u_scale", "1.0", "1", "Scale of every joystick command of the dig cycle"),
            ("c_soil", num(SOIL["c"]), "Pa", "Soil cohesion (1.5e4 loam, 5e4 stiff clay)"),
            ("gamma_soil", num(SOIL["gamma"]), "N/m^3", "Soil unit weight"),
        ]
    return [{"name": n, "value": v, "unit": u, "description": t} for n, v, u, t in rows]


# --------------------------------------------------------------------------- models
def settings(t_end: float, points_per_s: int = 100, reltol: float = 1e-6, abstol: float = 1e-6) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "FBDF", "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(round(t_end * points_per_s)) + 1},
            "event_limit": 10000}


def kinematics_model() -> dict:
    k = DES["kinematics"]
    d = Diagram()
    mechanism(d, k["q0"], BODIES["bucket"], "0.0")
    dt = 0.5
    n = int(round(k["t_end"] / dt)) + 1
    for i, name in enumerate(NAMES):
        C = CAP[name]
        y = 180 + 400 * i
        rod = drive_chain(d, name, 900, y)
        vals = []
        for j in range(n):
            t = j * dt
            v = 0.0
            for t0, t1, dL in k["moves"]:
                if t0 - 1e-9 <= t < t1 - 1e-9:
                    v += dL[i] / (t1 - t0)
            vals.append(v)
        d.node(f"{C}Rate", "stdlib:sources/TimeTable", 300, y,
               {"t_start": "0.0", "sample_time": num(dt), "values": vec(vals), "method": "0"}, constants={"N": n})
        d.node(f"{C}Servo", "stdlib:translation/SpringDamper", 700, y + 100, {"k": "k_servo", "d": "d_servo"})
        d.node(f"{C}Drive", "stdlib:translation/VelocitySource", 500, y + 100, {"v": "1.0"})
        d.sig(f"{C}Rate", "y", f"{C}Drive", "u")
        d.bond(rod, None, f"{C}Servo", "a")
        d.wire(f"{C}Servo", "b", f"{C}Drive", "a")
        # the set length (integral of the rate) for the plots
        d.node(f"{C}SetL", "stdlib:continuous/Integrator", 500, y - 80, {}, {"x": num(k["L0"][i])})
        d.sig(f"{C}Rate", "y", f"{C}SetL", "u")
    return {"diagram": d, "globals": globals_table("kin"), "settings": settings(k["t_end"], 100, 1e-8, 1e-9)}


def hydraulic_model(kind: str) -> dict:
    """kind: lift | dig | nols"""
    d = Diagram()
    if kind == "lift":
        L = DES["lift"]
        q0, starts = L["q0"], dict(L["starts"])
        s = dict(starts["boom"])
        s["pA"] = num(L["sag"] * s["pA"])
        starts = {**starts, "boom": s}
    else:
        q0, starts = DES["dig"]["q0"], DES["dig"]["starts"]
    mechanism(d, q0, BODIES["bucket"], num(G0))
    supply(d, kind != "nols", -900, 1500)
    cmds = joystick(d, kind)
    for i, name in enumerate(NAMES):
        y = 180 + 400 * i
        rod = drive_chain(d, name, 1100, y)
        st = starts[name]
        st = {"x": st["x"], "pA": num(st["pA"]) if not isinstance(st["pA"], str) else st["pA"],
              "pB": num(st["pB"]) if not isinstance(st["pB"], str) else st["pB"]}
        cyl = cylinder(d, name, rod, 950, y, st)
        section(d, name, cyl, 300, y + 1600, cmds[name], kind != "nols")
    if kind in ("dig", "nols"):
        soil(d)
    t_end = DES["lift"]["t_end"] if kind == "lift" else DIG_T_END
    return {"diagram": d, "globals": globals_table(kind), "settings": settings(t_end, 100, 1e-6, 1e-6)}


# --------------------------------------------------------------------------- joystick
DIG_DT = 0.25
DIG_RAMP = 0.25
#: dig cycle phases: (name, t_start, t_end, (boom, arm, bucket) joystick), + = cylinder out
#: (boom up, arm in, bucket curl). The levels follow from the cylinder strokes of each phase
#: at the regulated speed u*Q_nom/A (plan_cycle in the README); the joystick ramps over
#: DIG_RAMP between phases.
DIG_PHASES = [
    ("penetrate", 0.5, 2.0, (-0.15, 0.0, 0.25)),
    ("drag", 2.0, 5.0, (-0.03, 0.5, 0.22)),
    ("curl", 5.0, 6.5, (0.13, 0.33, 0.38)),
    ("lift", 6.5, 9.5, (0.9, -0.06, 0.0)),
    ("arm out", 9.5, 11.0, (0.15, -0.65, 0.0)),
    ("dump", 11.0, 12.8, (0.0, 0.0, -0.85)),
    ("return", 12.8, 15.3, (-0.17, 0.02, 0.38)),
]
DIG_T_END = 16.5


def _phase_points(phases) -> list[tuple]:
    pts = [(0.0, 0.0, 0.0, 0.0)]
    last = (0.0, 0.0, 0.0)
    for _, t0, t1, v in phases:
        if pts[-1][0] < t0 - 1e-9:
            pts.append((t0, *last))
        pts.append((t0 + DIG_RAMP, *v))
        pts.append((t1, *v))
        last = v
    pts.append((pts[-1][0] + DIG_RAMP, 0.0, 0.0, 0.0))
    pts.append((DIG_T_END, 0.0, 0.0, 0.0))
    return pts


DIG_SCRIPT = _phase_points(DIG_PHASES)


def table(points, col: int, dt: float, t_end: float) -> list[float]:
    out = []
    n = int(round(t_end / dt)) + 1
    for j in range(n):
        t = j * dt
        for (ta, *va), (tb, *vb) in zip(points, points[1:]):
            if ta - 1e-9 <= t <= tb + 1e-9:
                f = 0.0 if tb == ta else (t - ta) / (tb - ta)
                out.append(va[col] + f * (vb[col] - va[col]))
                break
        else:
            out.append(points[-1][1 + col])
    return out


def joystick(d: Diagram, kind: str) -> dict:
    out = {}
    if kind == "lift":
        t0, t1 = DES["lift"]["t_lift"]
        n = int(round(DES["lift"]["t_end"] / 0.5)) + 1
        vals = [1.0 if t0 - 1e-9 <= 0.5 * j < t1 - 1e-9 else 0.0 for j in range(n)]
        d.node("LiftStick", "stdlib:sources/TimeTable", 60, 1700,
               {"t_start": "0.0", "sample_time": "0.5", "values": vec(vals), "method": "0"}, constants={"N": n})
        d.node("LiftCmd", "stdlib:continuous/Gain", 180, 1700, {"k": "u_lift"})
        d.sig("LiftStick", "y", "LiftCmd", "u")
        d.node("Neutral", "stdlib:sources/Constant", 60, 300, {"value": "0.0"})
        return {"boom": ("LiftCmd", "y"), "arm": ("Neutral", "y"), "bucket": ("Neutral", "y")}
    for i, name in enumerate(NAMES):
        C = CAP[name]
        vals = table(DIG_SCRIPT, i, DIG_DT, DIG_T_END)
        d.node(f"{C}Stick", "stdlib:sources/TimeTable", 60, 1700 + 400 * i,
               {"t_start": "0.0", "sample_time": num(DIG_DT), "values": vec(vals), "method": "1"},
               constants={"N": len(vals)})
        d.node(f"{C}Cmd", "stdlib:continuous/Gain", 180, 1700 + 400 * i, {"k": "u_scale"})
        d.sig(f"{C}Stick", "y", f"{C}Cmd", "u")
        out[name] = (f"{C}Cmd", "y")
    return out


def soil(d: Diagram) -> None:
    b = BODIES["bucket"]
    p = DES["payload"]
    d.node("Soil", "project:SoilCutting2D", 1700, 1300,
           {"rtx": f"{num(G.L3)} - cx_bucket", "rty": "-cy_bucket",
            "rsx": f"{num(p['c'][0])} - cx_bucket", "rsy": f"{num(p['c'][1])} - cy_bucket",
            "y_s": num(G.Y_GROUND), "w": num(SOIL["w"]), "gamma": "gamma_soil", "c": "c_soil",
            "N_g": num(SOIL["N_gamma"]), "N_c": num(SOIL["N_c"]), "rho_s": num(SOIL["rho"]),
            "swell": num(SOIL["swell"]), "V_max": num(SOIL["V_max"]), "tau_dump": "0.6", "c_dump": "0.3",
            "g0": num(G0), "v_eps": "0.02", "d_eps": "0.01"}, {"V": "0.0"})
    d.bond("Soil", "p", "BodyJ3", None)
    d.sig("PoseB3", "g", "Soil", "g")
    del b


# --------------------------------------------------------------------------- documents
def bindings(kind: str) -> list[dict]:
    import scene as S
    out = [
        {"target": "joint:boom_joint", "property": "position", "signal": "Joint1/qout"},
        {"target": "joint:arm_joint", "property": "position", "signal": "Joint2/qout"},
        {"target": "joint:bucket_joint", "property": "position", "signal": "Joint3/qout"},
    ]
    pins = {"boom": ("PinA1", "PinB1"), "arm": ("PinA2", "PinB2"), "bucket": ("PinA3", "PinJ")}
    for name, vis in S.CYL_VISUALS.items():
        a, b = pins[name]
        m = CAP[name] + "Mount"
        for barrel, rod, y in vis:
            out.append({"target": f"visual:{barrel}", "property": "segment", "plane": "xz", "depth": y,
                        "signal": [f"{a}/g[2]", f"{a}/g[3]", f"{m}/pb[1]", f"{m}/pb[2]"]})
            out.append({"target": f"visual:{rod}", "property": "segment", "plane": "xz", "depth": y,
                        "signal": [f"{m}/pr[1]", f"{m}/pr[2]", f"{b}/g[2]", f"{b}/g[3]"]})
    for name, y in S.LINK_VISUALS:
        a, b = ("PinR", "PinJ") if name.startswith("rocker") else ("PinJ", "PinP")
        out.append({"target": f"visual:{name}", "property": "segment", "plane": "xz", "depth": y,
                    "signal": [f"{a}/g[2]", f"{a}/g[3]", f"{b}/g[2]", f"{b}/g[3]"]})
    if kind in ("dig", "nols"):
        out.append({"target": "visual:soil_load", "property": "scale.z", "signal": "Soil/fillr"})
    elif kind == "kin":
        out.append({"target": "visual:soil_load", "property": "scale.z", "signal": "Empty/y"})
    return out


def plots(kind: str) -> list[dict]:
    if kind == "kin":
        return [
            {"id": "p1", "title": "Cylinder lengths: set point and pin-to-pin [m]",
             "signals": ["BoomSetL/y", "BoomMount/L", "ArmSetL/y", "ArmMount/L", "BucketSetL/y", "BucketMount/L"]},
            {"id": "p2", "title": "Bucket tip path [m]", "signals": ["PoseTip/g[3]"], "x": "PoseTip/g[2]",
             "equalAspect": True},
            {"id": "p3", "title": "Joint angles [rad]", "signals": ["Joint1/qout", "Joint2/qout", "Joint3/qout"]},
            {"id": "p4", "title": "Moment arms dL/dq [m] and four-bar ratio k",
             "signals": ["BoomMount/r", "ArmMount/r", "BucketMount/r", "Linkage/k"]},
        ]
    common = [
        {"id": "p2", "title": "Pump line, LS line and LS margin [Pa]", "signals": ["Vpump/p", "Pump/margin"]
         + (["Vls/p"] if kind != "nols" else [])},
        {"id": "p3", "title": "Cylinder cap-side pressures [Pa]", "signals": ["BoomCyl/pA", "ArmCyl/pA", "BucketCyl/pA"]},
        {"id": "p4", "title": "Cylinder forces [N] (extending positive)", "signals": ["BoomForce/y", "ArmForce/y", "BucketForce/y"]},
        {"id": "p5", "title": "Pump displacement and flow", "signals": ["Pump/xd", "Pump/Q"]},
        {"id": "p6", "title": "Power [W]: engine shaft, pump hydraulic, cylinders",
         "signals": ["Pump/P_in", "Pump/P_out", "Pcyl/y"]},
        {"id": "p7", "title": "Energy [J] and ratio cylinder work / engine energy",
         "signals": ["Ein/y", "Ecyl/y", "Eff/y"]},
    ]
    if kind == "lift":
        return [{"id": "p1", "title": "Boom cylinder pressures [Pa]", "signals": ["BoomCyl/pA", "BoomCyl/pB"]},
                {"id": "p8", "title": "Boom: rod extension [m] and joint angle [rad]",
                 "signals": ["BoomCyl/x", "Joint1/qout"]},
                {"id": "p9", "title": "Boom section: compensator flow [m^3/s]", "signals": ["BoomComp/Q"]}] + common
    return [
        {"id": "p1", "title": "Bucket tip path [m]", "signals": ["PoseTip/g[3]"], "x": "PoseTip/g[2]", "equalAspect": True},
        {"id": "p8", "title": "Joystick (spool) commands", "signals": ["BoomSpool/y", "ArmSpool/y", "BucketSpool/y"]},
        {"id": "p9", "title": "Soil: cutting force [N]", "signals": ["Soil/Fcut"]},
        {"id": "p10", "title": "Soil: cutting depth [m] and bucket fill", "signals": ["Soil/depth", "Soil/fillr"]},
    ] + common


def dashboard(kind: str) -> dict:
    gauge_margin = {"id": "margin", "kind": "gauge", "size": "2x2", "title": "LS margin (pump - LS line) [Pa]",
                    "signals": ["Pump/margin"],
                    "options": {"min": 0, "max": 5.0e6, "decimals": 0, "unit": "Pa",
                                "zones": [{"from": 0, "to": 2.0e6, "tone": "warn"}, {"from": 2.0e6, "to": 3.0e6, "tone": "good"},
                                          {"from": 3.0e6, "to": 5.0e6, "tone": "warn"}]}}
    if kind == "kin":
        return {"autoRerun": False, "cards": [
            {"id": "tip", "kind": "plot", "size": "2x2", "title": "Bucket tip path [m]", "signals": ["PoseTip/g[3]"],
             "x": "PoseTip/g[2]", "equalAspect": True},
            {"id": "len", "kind": "plot", "size": "2x2", "title": "Cylinder lengths [m]",
             "signals": ["BoomMount/L", "ArmMount/L", "BucketMount/L"]},
            {"id": "k", "kind": "value", "size": "1x1", "title": "Four-bar ratio k", "signals": ["Linkage/k"],
             "options": {"decimals": 3, "sparkline": True}},
            {"id": "mu", "kind": "value", "size": "1x1", "title": "Transmission angle [rad]", "signals": ["Linkage/mu"],
             "options": {"decimals": 3, "sparkline": True}},
            {"id": "ks", "kind": "slider", "size": "2x1", "title": "Servo stiffness", "parameter": "global:k_servo",
             "options": {"min": 1.0e7, "max": 1.0e9, "step": 1.0e7, "unit": "N/m"}},
        ]}
    if kind == "lift":
        return {"autoRerun": False, "cards": [
            {"id": "pboom", "kind": "plot", "size": "2x2", "title": "Boom cylinder pressures [Pa]",
             "signals": ["BoomCyl/pA", "BoomCyl/pB"]},
            gauge_margin,
            {"id": "force", "kind": "value", "size": "1x1", "title": "Boom cylinder force", "signals": ["BoomForce/y"],
             "options": {"decimals": 0, "unit": "N", "sparkline": True}},
            {"id": "eff", "kind": "value", "size": "1x1", "title": "Cylinder work / engine energy", "signals": ["Eff/y"],
             "options": {"decimals": 3, "sparkline": True}},
            {"id": "pay", "kind": "slider", "size": "2x1", "title": "Payload", "parameter": "global:m_pay",
             "options": {"min": 0, "max": 2500, "step": 100, "decimals": 0, "unit": "kg"}},
            {"id": "ul", "kind": "slider", "size": "2x1", "title": "Boom joystick during the lift",
             "parameter": "global:u_lift", "options": {"min": 0.1, "max": 1.0, "step": 0.05, "decimals": 2}},
            {"id": "dpls", "kind": "slider", "size": "2x1", "title": "LS margin setting", "parameter": "global:dp_ls",
             "options": {"min": 1.0e6, "max": 4.0e6, "step": 1.0e5, "unit": "Pa"}},
            {"id": "beta", "kind": "slider", "size": "2x1", "title": "Oil bulk modulus", "parameter": "global:beta",
             "options": {"min": 5.0e8, "max": 1.8e9, "step": 5.0e7, "unit": "Pa"}},
        ]}
    cards = [
        {"id": "tip", "kind": "plot", "size": "2x2", "title": "Bucket tip path [m]", "signals": ["PoseTip/g[3]"],
         "x": "PoseTip/g[2]", "equalAspect": True},
        {"id": "press", "kind": "plot", "size": "2x2", "title": "Pump and cap-side pressures [Pa]",
         "signals": ["Vpump/p", "BoomCyl/pA", "ArmCyl/pA", "BucketCyl/pA"]},
        gauge_margin,
        {"id": "force", "kind": "plot", "size": "2x2", "title": "Cylinder forces [N] and soil cutting force",
         "signals": ["BoomForce/y", "ArmForce/y", "BucketForce/y", "Soil/Fcut"]},
        {"id": "fill", "kind": "value", "size": "1x1", "title": "Bucket fill", "signals": ["Soil/fillr"],
         "options": {"decimals": 2, "sparkline": True}},
        {"id": "eff", "kind": "value", "size": "1x1", "title": "Cylinder work / engine energy", "signals": ["Eff/y"],
         "options": {"decimals": 3, "sparkline": True}},
        {"id": "ein", "kind": "value", "size": "1x1", "title": "Engine energy", "signals": ["Ein/y"],
         "options": {"decimals": 0, "unit": "J", "sparkline": True}},
        {"id": "pin", "kind": "value", "size": "1x1", "title": "Engine (shaft) power", "signals": ["Pump/P_in"],
         "options": {"decimals": 0, "unit": "W", "sparkline": True}},
        {"id": "us", "kind": "slider", "size": "2x1", "title": "Joystick scale (operator speed)",
         "parameter": "global:u_scale", "options": {"min": 0.5, "max": 1.2, "step": 0.05, "decimals": 2}},
        {"id": "coh", "kind": "slider", "size": "2x1", "title": "Soil cohesion (1.5e4 loam, 5e4 stiff clay)",
         "parameter": "global:c_soil", "options": {"min": 0, "max": 6.0e4, "step": 5.0e3, "unit": "Pa"}},
    ]
    if kind == "dig":
        cards.append({"id": "dpls", "kind": "slider", "size": "2x1", "title": "LS margin setting",
                      "parameter": "global:dp_ls", "options": {"min": 1.0e6, "max": 4.0e6, "step": 1.0e5, "unit": "Pa"}})
    else:
        cards[2] = {"id": "ppump", "kind": "value", "size": "1x1", "title": "Pump pressure", "signals": ["Vpump/p"],
                    "options": {"decimals": 0, "unit": "Pa", "sparkline": True}}
    return {"autoRerun": False, "cards": cards}


def model_document(name: str, comment: str, kind: str, built: dict) -> dict:
    d: Diagram = built["diagram"]
    if kind == "kin":
        d.node("Empty", "stdlib:sources/Constant", 300, 1500, {"value": "0.0"})
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": comment,
        "diagram": {"nodes": d.nodes, "connections": d.conns, "annotations": d.notes},
        "settings": built["settings"],
        "parameters": built["globals"],
        "plots": plots(kind),
        "scene": {"file": "scenes/excavator.sdf"},
        "bindings": bindings(kind),
        "dashboard": dashboard(kind),
    }


MODELS = {
    "excavator-kinematics": ("kin", "The excavator front without gravity: every cylinder is a stiff length servo, and the "
                             "set lengths move the boom, arm and bucket through the linkage (bucket four-bar "
                             "included). The bucket tip is checked against a scipy forward kinematics.",
                             kinematics_model),
    "excavator-lift": ("lift", "Load-sensing hydraulics holding a 1.5 t payload: the boom rings at its hydraulic natural "
                       "frequency after a pressure sag, then lifts at half joystick with the pump holding its "
                       "LS margin.", lambda: hydraulic_model("lift")),
    "excavator-dig-cycle": ("dig", "A scripted joystick dig cycle (penetrate, drag, curl, lift, dump, return) into loam, "
                            "with a load-sensing pump, pre-compensated valve sections and the fundamental "
                            "earthmoving equation at the bucket teeth.", lambda: hydraulic_model("dig")),
    "excavator-no-ls": ("nols", "The same dig cycle without load sensing: the pump's LS port is on the tank, so the "
                        "pump holds 281 bar whenever it delivers (a constant-pressure system), and the valves "
                        "throttle the difference.", lambda: hydraulic_model("nols")),
}


NO_DIAG = {"kind": "no_diagnostics", "codes": ["E901", "E101", "E102", "E103", "E106", "W201", "W202", "W206"],
           "note": "no solver failure, no connection or causality error, no derivative causality, no algebraic loop "
                   "(every valve sits between two volumes) and no event-limit stop"}


def expected() -> dict:
    k = DES["kinematics"]
    L = DES["lift"]
    kin = [{"kind": "scene_bindings"}, NO_DIAG]
    for h in k["holds"][1:]:
        t = h["t"]
        for j, axis in ((2, "x"), (3, "y")):
            kin.append({"kind": "cursor_value", "signal": f"PoseTip/g[{j}]", "t": t, "value": round(h["tip"][j - 2], 6),
                        "abs": 1e-4, "note": f"bucket tip {axis} at the hold t = {t} s: scipy forward kinematics of the "
                        "three set lengths (brentq on each cylinder length, the bucket through the four-bar), design.py"})
        for i, name in enumerate(NAMES):
            kin.append({"kind": "cursor_value", "signal": f"Joint{i + 1}/qout", "t": t, "value": round(h["q"][i], 7),
                        "abs": 1e-5, "note": f"{name} joint angle whose cylinder length is the set length (design.py)"})
            kin.append({"kind": "cursor_value", "signal": f"{CAP[name]}Mount/L", "t": t, "value": round(h["L"][i], 7),
                        "abs": 1e-5, "note": f"{name} pin-to-pin length = the set length L0 + integral of the rate profile"})
        fb = G.four_bar(h["q"][2])
        cy = G.cylinders(*h["q"])
        kin.append({"kind": "cursor_value", "signal": "Linkage/k", "t": t, "value": round(fb["k"], 7), "abs": 1e-5,
                    "note": "four-bar velocity ratio dphi/dq3 at the hold (exc_geom.four_bar, circle intersection)"})
        kin.append({"kind": "cursor_value", "signal": "BucketMount/r", "t": t, "value": round(cy["r_rocker"], 7),
                    "abs": 1e-5, "note": "moment arm of the bucket cylinder about the rocker pivot (exc_geom.cylinders)"})
    st = L["starts"]
    lift = [
        {"kind": "scene_bindings"}, NO_DIAG,
        {"kind": "cursor_value", "signal": "BoomForce/y", "t": 2.9, "value": round(L["F"][0], 1), "rtol": 0.012,
         "note": "static boom cylinder force (pA Ap - pB Ar) holding the front with 1.5 t: moment balance about the boom "
                 "foot divided by the moment arm dL/dq1 (design.static_forces, 275.2 kN). Tolerance: the Coulomb band "
                 "of the cylinder friction, 3 kN = 1.1 %"},
        {"kind": "cursor_value", "signal": "ArmForce/y", "t": 2.9, "value": round(L["F"][1], 1), "abs": 2500.0,
         "note": "static arm cylinder force (10.4 kN), within its Coulomb friction band (2 kN)"},
        {"kind": "cursor_value", "signal": "BucketForce/y", "t": 2.9, "value": round(L["F"][2], 1), "abs": 2000.0,
         "note": "static bucket cylinder force through the four-bar (81.1 kN), within its Coulomb friction band (1.5 kN)"},
        {"kind": "fft_peak", "signal": "BoomCyl/pA", "from_t": 0.0, "to_t": 2.8, "value": round(L["f_boom_mode"], 4),
         "rtol": 0.03, "min_hz": 1.0, "max_hz": 6.0,
         "note": "after the 15 % cap-pressure sag the front rings at its lowest hydraulic mode: eig(M^-1 K) of the 3-DOF "
                 "chain (mass matrix from the body Jacobians, K = diag(beta (Ap^2/VA + Ar^2/VB) r^2), all valves closed), "
                 f"{L['f_boom_mode']:.3f} Hz. The single-DOF estimate sqrt(beta A^2 (1/V1 + 1/V2)/m_eq) with the arm and "
                 f"bucket locked gives {L['f_h']:.3f} Hz"},
        {"kind": "cursor_value", "signal": "Pump/margin", "t": 2.9, "value": round(HYD["dp_ls"] + HYD["dp_reg"], 1),
         "abs": 2.0e4, "note": "stand-by: no section open, the pump destrokes until only the leakage flows and the "
                               "margin sits at the top of the regulation range, dp_ls + dp_reg = 2.7 MPa"},
        {"kind": "min_ge", "signal": "Pump/margin", "from_t": 3.6, "to_t": 6.0, "value": HYD["dp_ls"],
         "note": "LS margin during the boom lift: the static LS regulator holds pump - LS line between dp_ls ..."},
        {"kind": "max_abs_le", "signal": "Pump/margin", "from_t": 3.6, "to_t": 6.0, "value": HYD["dp_ls"] + HYD["dp_reg"],
         "note": "... and dp_ls + dp_reg (2.5 to 2.7 MPa)"},
        {"kind": "cursor_value", "signal": "BoomComp/Q", "t": 5.0, "value": round(L["u_lift"] * HYD["Q_nom"]["boom"], 8),
         "rtol": 0.05, "note": "flow regulation: the pre-compensated section passes u Q_nom = 150 l/min regardless of the "
                               "load; the compensator's smooth saturation (dp a little above dp_c = 1 MPa) keeps it 3 % "
                               "below the nominal"},
        {"kind": "energy_ledger", "tol": 1e-6, "note": "port-power ledger closes (Tellegen) through the wired hydraulics, "
                                                        "the modulated transformers and the planar bodies"},
    ]
    dig = [
        {"kind": "scene_bindings"}, NO_DIAG,
        {"kind": "min_ge", "signal": "Pump/margin", "from_t": 0.5, "to_t": DIG_T_END, "value": 2.0e6,
         "note": "the LS margin stays within 0.5 MPa of the 2.5 MPa setting through the whole cycle (it dips while the "
                 "LS line follows a step in load pressure) ..."},
        {"kind": "max_abs_le", "signal": "Pump/margin", "from_t": 0.5, "to_t": DIG_T_END, "value": 3.2e6, "note": "... and above"},
        {"kind": "max_abs_le", "signal": "Relief/Q", "value": 1.0e-6,
         "note": "the main relief never opens: the LS pump never delivers more than the sections take"},
        {"kind": "min_ge", "signal": "Soil/fillr", "from_t": 6.5, "to_t": 7.0, "value": 0.6,
         "note": "the bucket is filled (above 60 % of its heaped capacity) after the curl"},
        {"kind": "max_abs_le", "signal": "Soil/fillr", "from_t": 15.5, "to_t": DIG_T_END, "value": 0.05,
         "note": "and empty after the dump"},
        {"kind": "max_abs_le", "signal": "Soil/depth", "value": 0.6, "note": "the teeth cut at most 0.6 m deep"},
        {"kind": "energy_ledger", "tol": 1e-6, "note": "port-power ledger closes (Tellegen)"},
    ]
    nols = [
        NO_DIAG,
        {"kind": "min_ge", "signal": "Vpump/p", "from_t": 0.5, "to_t": DIG_T_END, "value": 1.9e7,
         "note": "constant-pressure system: the pump line stays near 281 bar except while all sections draw together"},
        {"kind": "min_ge", "signal": "Ein/y", "from_t": DIG_T_END - 0.01, "to_t": DIG_T_END, "value": 1.2e6,
         "note": "the cycle costs more than 1.2 MJ at the engine (the LS system: below 0.7 MJ, see excavator-dig-cycle)"},
    ]
    dig.append({"kind": "max_abs_le", "signal": "Ein/y", "from_t": DIG_T_END - 0.01, "to_t": DIG_T_END, "value": 7.0e5,
                "note": "the LS cycle costs less than 0.7 MJ at the engine (the constant-pressure system: above 1.2 MJ)"})
    return {
        "project": "excavator",
        "description": "The front of a 20-t hydraulic excavator (boom 5.7 m, arm 2.9 m, bucket 1.5 m) on planar multibond "
                       "mechanics with the real cylinder linkage (bucket four-bar included), driven by a load-sensing "
                       "pump and pre-compensated valve sections, digging loam with the fundamental earthmoving equation. "
                       "design/design.py computes the references: forward kinematics from the cylinder lengths, static "
                       "cylinder forces, the hydraulic modes, the earthmoving factors.",
        "models": {
            "excavator-kinematics": {"checks": kin},
            "excavator-lift": {"checks": lift},
            "excavator-dig-cycle": {"checks": dig},
            "excavator-no-ls": {"checks": nols},
        },
    }


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline=NL)


def main() -> None:
    import scene
    (ROOT / "scenes").mkdir(exist_ok=True)
    _write(ROOT / "scenes" / "excavator.sdf", scene.scene_sdf())
    out_dir = ROOT / "models"
    out_dir.mkdir(exist_ok=True)
    for name, (kind, comment, fn) in MODELS.items():
        doc = model_document(name, comment, kind, fn())
        _write(out_dir / f"{name}.bgmodel.json", json.dumps(doc, indent=1) + NL)
        print("wrote", name)
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "excavator", "models": list(MODELS),
            "libraryDir": "library", "scenesDir": "scenes"}
    _write(ROOT / "bgsim.project.json", json.dumps(proj, indent=2) + NL)
    _write(ROOT / "expected.json", json.dumps(expected(), indent=2) + NL)


if __name__ == "__main__":
    main()
