# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the hybrid-powersplit models and expected.json from `design/design.json`.

    uv run examples/hybrid-powersplit/design/design.py        # first
    uv run examples/hybrid-powersplit/design/build_model.py

The plant is one bond graph, the same in the three vehicle models: the engine (a modulated
effort source on its crankshaft inertia, plus its drag while unfired) through the transaxle
input damper onto the planet carrier; the planetary set as the classic bond-graph planetary
(the `Planetary` subsystem: one TF per shaft into the 0-junction of the internal mesh force, the
Willis equation being that junction's flow balance); MG1 on the sun and MG2 on the ring as
DC-equivalent machines (inverter MTF from the DC bus, stator R and L, stdlib EMConverter) with
their iron loss as R; the transaxle spin losses on the ring; the ring through the final drive,
the half shafts (C + R) and the tyre (stdlib Wheel converter) to the vehicle mass with
aerodynamic drag (MR), rolling resistance (MSe), grade (Se) and the friction brakes (MR on the
wheel); the NiMH battery (stdlib Battery, Thevenin model with an OCV table), the DC-link
capacitor and the 12 V auxiliary load (R) on the bus.
The controllers are signal blocks: the NEDC (Lookup1D over time), the driver (PI), the
EnergyManager (rule-based or ECMS) and the PowerSplitControl.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
D = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
VEH, PSD, ENG, MG, BAT, SPIN = D["vehicle"], D["psd"], D["engine"], D["mg"], D["battery"], D["spin"]
RPM = 2 * math.pi / 60


def num(v: float) -> str:
    return repr(float(v))


def vec(values) -> str:
    return "[" + ", ".join(repr(float(v)) for v in values) + "]"


def mat(rows) -> str:
    return "[" + "; ".join(" ".join(repr(float(v)) for v in r) for r in rows) + "]"


# --------------------------------------------------------------------------- document helpers
class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[tuple] = []
        self.annotations: list[dict] = []
        self.ports: list[dict] = []
        self.ids: dict[str, str] = {}

    def node(self, name, block, x, y, params=None, starts=None, constants=None) -> str:
        assert name not in self.ids, name
        nid = f"n{len(self.nodes) + 1:03d}"
        b = {"ref": block} if isinstance(block, str) else block
        self.nodes.append({
            "id": nid, "name": name, "block": b, "position": {"x": int(x), "y": int(y)}, "rotation": 0,
            "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self.ids[name] = nid
        return name

    def junction(self, name, kind, x, y) -> str:
        return self.node(name, {"junction": str(kind)}, x, y)

    def sig(self, a, pa, b, pb):
        self.connections.append(("signal", a, pa, b, pb))

    def bond(self, a, pa, b, pb):
        self.connections.append(("bond", a, pa, b, pb))

    def wire(self, a, pa, b, pb):
        self.connections.append(("wire", a, pa, b, pb))

    def note(self, text, x, y, w, h, color=None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def port(self, name, direction, node, port, unit=None, size=1):
        self.ports.append({"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
                           "unit": unit, "node": self.ids[node], "port": port})

    def power_port(self, name, domain, node, port=None):
        p = {"name": name, "kind": "power", "domain": domain, "size": [1], "node": self.ids[node]}
        if port is not None:
            p["port"] = port
        self.ports.append(p)

    def doc(self, prefix: str = "") -> dict:
        conns = []
        for k, (kind, a, pa, b, pb) in enumerate(self.connections):
            frm = {"node": self.ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self.ids[b]}
            if pb is not None:
                to["port"] = pb
            conns.append({"id": f"{prefix}c{k + 1:03d}", "kind": kind, "from": frm, "to": to})
        d = {"nodes": self.nodes, "connections": conns, "annotations": self.annotations}
        if self.ports:
            d["subsystemPorts"] = self.ports
        return d

    def subsystem(self, parent: "Diagram", name: str, x: float, y: float) -> str:
        parent.node(name, {"subsystem": {"ports": self.ports, "diagram": self.doc(name + "_")}}, x, y)
        return name


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value if isinstance(value, str) else num(value), "unit": unit,
            "description": description}


def settings(t_end: float, points: int, solver="Rodas5P", reltol=1e-6, abstol=1e-6) -> dict:
    return {"t_start": 0.0, "t_end": float(t_end), "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": 1000000}


def model_doc(name, comment, d: Diagram, sett, plots, parameters, dashboard) -> dict:
    return {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
            "diagram": d.doc(), "settings": sett, "plots": plots, "scene": None, "bindings": [],
            "parameters": parameters, "dashboard": dashboard}


# --------------------------------------------------------------------------- the planetary set
def planetary() -> Diagram:
    """The bond-graph planetary gear: one TF per shaft into the 0-junction `Mesh` whose effort is
    the tooth-normalised mesh force F (the mesh force times half the module; with the TF moduli in
    teeth, the shaft torques are Z F). The junction's flow balance is the Willis equation
    (Zs+Zr) w_c = Zs w_s + Zr w_r; its common effort gives the torque split
    T_s : T_r : T_c = Zs : Zr : (Zs+Zr)."""
    p = Diagram()
    p.node("TFc", "stdlib:bondgraph/TF", 60, 200, params={"n": "Zs + Zr"})
    p.junction("Mesh", 0, 300, 200)
    p.node("TFs", "stdlib:bondgraph/TF", 540, 80, params={"n": "Zs"})
    p.node("TFr", "stdlib:bondgraph/TF", 540, 320, params={"n": "Zr"})
    p.node("MeshForce", "stdlib:bondgraph/De", 300, 380)
    p.bond("TFc", "p2", "Mesh", None)
    p.bond("Mesh", None, "TFs", "p2")
    p.bond("Mesh", None, "TFr", "p2")
    p.bond("Mesh", None, "MeshForce", "p")
    p.power_port("carrier", "Rotation", "TFc", "p1")
    p.power_port("sun", "Rotation", "TFs", "p1")
    p.power_port("ring", "Rotation", "TFr", "p1")
    p.port("F", "output", "MeshForce", "y")
    p.note("**Planetary set (bond graph).** The 0-junction `Mesh` carries the tooth-normalised mesh force F. Its flow "
           "balance is the Willis equation (Zs+Zr) w_carrier = Zs w_sun + Zr w_ring; the TFs (moduli in teeth) give the "
           "torque split T_sun : T_ring : T_carrier = Zs : Zr : (Zs+Zr) = 30 : 78 : 108.", 40, -60, 640, 70, "blue")
    return p


# --------------------------------------------------------------------------- globals
def vehicle_globals(kind: str) -> list[dict]:
    out = [
        g("Zs", PSD["Zs"], None, "Sun gear teeth (THS-II: 30)"),
        g("Zr", PSD["Zr"], None, "Ring gear teeth (THS-II: 78)"),
        g("FD", PSD["FD"], None, "Ring (MG2) to axle reduction (ORNL: 4.113)"),
        g("m_veh", VEH["m"], "kg", "Vehicle mass with driver (Prius NHW20 curb 1310 kg + 75 kg)"),
        g("m_rot", VEH["m_rot"], "kg", "Equivalent mass of the four wheels' inertia, 4 J_w / r^2"),
        g("r_w", VEH["r_w"], "m", "Rolling radius (185/65 R15)"),
        g("Cd", VEH["Cd"], None, "Drag coefficient (Toyota: 0.26)"),
        g("A_front", VEH["A"], "m^2", "Frontal area"),
        g("rho_air", VEH["rho"], "kg/m^3", "Air density"),
        g("c_rr", VEH["c_rr"], None, "Rolling resistance coefficient"),
        g("grade_pct", 0.0, "%", "Road grade (positive uphill)"),
        g("J_e", PSD["J_e"], "kg*m^2", "Engine crankshaft and flywheel inertia"),
        g("J_sun", PSD["J_sun"], "kg*m^2", "Sun gear inertia"),
        g("J_mg1", PSD["J_mg1"], "kg*m^2", "MG1 rotor inertia"),
        g("J_ring", PSD["J_ring"], "kg*m^2", "Ring gear and counter drive gear inertia"),
        g("J_mg2", PSD["J_mg2"], "kg*m^2", "MG2 rotor inertia (ORNL rotor mass 10.2 kg)"),
        g("soc0", BAT["soc0"], None, "Initial battery state of charge"),
        g("P_aux", 250.0, "W", "12 V auxiliary load through the DC/DC converter (assumed)"),
    ]
    if kind == "cycle":
        out += [
            g("soc_ref", 0.6, None, "Target state of charge of the energy management (at standstill)"),
            g("eta_kin", 0.6, None, "Share of the kinetic energy the SOC target keeps room for (0: a fixed target)"),
            g("P_on_kW", 9.0, "kW", "Rule-based: engine start power"),
            g("P_min_kW", 9.0, "kW", "Rule-based: least engine power while it runs"),
            g("s0", 2.6, None, "ECMS: equivalence factor (fuel per electric energy, both as power)"),
            g("k_p", 1.0, None, "ECMS: SOC correction gain"),
        ]
    return out


# --------------------------------------------------------------------------- the plant
def plant(d: Diagram) -> None:
    """The vehicle bond graph (top-level nodes). Signal sources the controllers use:
    EngineSpeed/y, SunSpeed/y, RingSpeed/y, WheelSpeed/y, VehicleSpeed/y, BusVoltage/y, WOT/y,
    BatCurrent/y; inputs: Throttle/u1, Inv1/u, Inv2/u, Brakes/u."""
    X0, Y0 = 0, 0
    # ---- engine
    d.node("WOT", "stdlib:continuous/Lookup1D", X0 + 0, Y0 + 520,
           params={"x": vec(D["wot"]["w"]), "table": vec(D["wot"]["T"])}, constants={"N": len(D["wot"]["w"])})
    d.node("Throttle", "stdlib:continuous/Product", X0 + 0, Y0 + 400)
    d.node("EngineTorque", "stdlib:bondgraph/MSe", X0 + 0, Y0 + 300, params={"gain": "1.0"})
    d.junction("Engine", 1, X0 + 160, Y0 + 300)
    d.node("EngineInertia", "stdlib:bondgraph/I", X0 + 160, Y0 + 180, params={"i": "J_e"})
    d.node("EngineSpeed", "stdlib:converters/SpeedSensor", X0 + 160, Y0 + 420)
    d.junction("Damper", 0, X0 + 400, Y0 + 300)
    d.junction("DamperTwist", 1, X0 + 400, Y0 + 180)
    d.node("DamperK", "stdlib:bondgraph/C", X0 + 340, Y0 + 80, params={"c": num(1.0 / PSD["k_damper"])})
    d.node("DamperD", "stdlib:bondgraph/R", X0 + 460, Y0 + 80, params={"r": num(PSD["d_damper"])})
    d.junction("Carrier", 1, X0 + 520, Y0 + 300)
    d.node("CarrierSpeed", "stdlib:converters/SpeedSensor", X0 + 520, Y0 + 420)
    d.sig("EngineSpeed", "y", "WOT", "u")
    d.sig("WOT", "y", "Throttle", "u2")
    d.sig("Throttle", "y", "EngineTorque", "u")
    d.bond("EngineTorque", "p", "Engine", None)
    d.bond("Engine", None, "EngineInertia", "p")
    # friction and pumping drag while the engine turns unfired (fuel cut, or spun by MG1)
    d.node("EngineDrag", "stdlib:bondgraph/MSe", X0 + 0, Y0 + 60, params={"gain": "1.0"})
    d.bond("Engine", None, "EngineDrag", "p")
    d.sig("HCU", "T_drag", "EngineDrag", "u")
    d.bond("Engine", None, "EngineSpeed", "a")
    d.bond("Engine", None, "Damper", None)
    d.bond("Damper", None, "DamperTwist", None)
    d.bond("DamperTwist", None, "DamperK", "p")
    d.bond("DamperTwist", None, "DamperD", "p")
    d.bond("Damper", None, "Carrier", None)
    d.bond("Carrier", None, "CarrierSpeed", "a")
    # ---- planetary set
    planetary().subsystem(d, "Planetary", X0 + 680, Y0 + 300)
    d.bond("Carrier", None, "Planetary", "carrier")
    # ---- sun shaft + MG1
    d.junction("Sun", 1, X0 + 860, Y0 + 120)
    d.bond("Planetary", "sun", "Sun", None)
    d.node("SunInertia", "stdlib:bondgraph/I", X0 + 760, Y0 + 20, params={"i": "J_sun + J_mg1"})
    d.node("SunSpeed", "stdlib:converters/SpeedSensor", X0 + 960, Y0 + 20)
    d.node("Iron1", "stdlib:bondgraph/R", X0 + 860, Y0 + 220, params={"r": num(MG["b1"])})
    d.bond("Sun", None, "SunInertia", "p")
    d.bond("Sun", None, "SunSpeed", "a")
    d.bond("Sun", None, "Iron1", "p")
    machine(d, "1", X0 + 1000, Y0 - 120, "Sun", MG["k1"], MG["R1"])
    # ---- ring shaft + MG2
    d.junction("Ring", 1, X0 + 860, Y0 + 480)
    d.bond("Planetary", "ring", "Ring", None)
    d.node("RingInertia", "stdlib:bondgraph/I", X0 + 760, Y0 + 600, params={"i": "J_ring + J_mg2"})
    d.node("RingSpeed", "stdlib:converters/SpeedSensor", X0 + 860, Y0 + 620)
    d.node("Iron2", "stdlib:bondgraph/R", X0 + 960, Y0 + 620, params={"r": num(MG["b2"])})
    # transaxle spin loss T = c0 tanh(w_r / 2 rad/s) + c1 w_r (ORNL fit): the Coulomb part as an
    # MSe modulated by the smooth sign of the ring speed, the viscous part as an R. A stdlib
    # RotationalFriction would do the same, but its Stribeck term abs(w) is a kink that the ring
    # speed sits on while the half-shaft oscillation reverses it at launch (event chatter)
    d.node("SpinScale", "stdlib:continuous/Gain", X0 + 1180, Y0 + 720, params={"k": "0.5"})
    d.node("SpinSign", "stdlib:continuous/MathFunction", X0 + 1180, Y0 + 820, constants={"fn": 8})
    d.node("SpinLoss", "stdlib:bondgraph/MSe", X0 + 1060, Y0 + 620, params={"gain": num(SPIN["c0"])})
    d.node("SpinDrag", "stdlib:bondgraph/R", X0 + 1060, Y0 + 720, params={"r": num(SPIN["c1"])})
    d.bond("Ring", None, "RingInertia", "p")
    d.bond("Ring", None, "RingSpeed", "a")
    d.bond("Ring", None, "Iron2", "p")
    d.bond("Ring", None, "SpinLoss", "p")
    d.bond("Ring", None, "SpinDrag", "p")
    d.sig("RingSpeed", "y", "SpinScale", "u")
    d.sig("SpinScale", "y", "SpinSign", "u")
    d.sig("SpinSign", "y", "SpinLoss", "u")
    machine(d, "2", X0 + 1000, Y0 + 300, "Ring", MG["k2"], MG["R2"])
    # ---- driveline and vehicle
    d.node("FinalDrive", "stdlib:bondgraph/TF", X0 + 1200, Y0 + 480, params={"n": "1/FD"})
    d.junction("HalfShaft", 0, X0 + 1340, Y0 + 480)
    d.junction("ShaftTwist", 1, X0 + 1340, Y0 + 360)
    d.node("ShaftK", "stdlib:bondgraph/C", X0 + 1280, Y0 + 260, params={"c": num(1.0 / PSD["k_shaft"])})
    d.node("ShaftD", "stdlib:bondgraph/R", X0 + 1400, Y0 + 260, params={"r": num(PSD["d_shaft"])})
    d.junction("Wheel", 1, X0 + 1480, Y0 + 480)
    d.node("WheelSpeed", "stdlib:converters/SpeedSensor", X0 + 1480, Y0 + 600)
    d.node("Brakes", "stdlib:bondgraph/MR", X0 + 1480, Y0 + 360, params={"gain": "1.0"})
    d.node("Tyre", "stdlib:converters/Wheel", X0 + 1640, Y0 + 480, params={"r": "r_w"})
    d.node("ShaftTorque", "stdlib:bondgraph/De", X0 + 1240, Y0 + 600)
    d.junction("Vehicle", 1, X0 + 1860, Y0 + 480)
    d.node("VehicleMass", "stdlib:bondgraph/I", X0 + 1860, Y0 + 340, params={"i": "m_veh + m_rot"})
    d.node("VehicleSpeed", "stdlib:converters/VelocitySensor", X0 + 1980, Y0 + 340)
    d.node("Aero", "stdlib:bondgraph/MR", X0 + 1980, Y0 + 480, params={"gain": "0.5*rho_air*Cd*A_front"})
    # aero drag F = k sqrt(v^2 + v0^2) v (v0 = 0.1 m/s, smooth |v|) and rolling resistance
    # F = c_rr m g tanh(v / 0.05 m/s) (smooth sign), both without a kink at standstill, where
    # the NEDC holds the car for minutes
    d.node("SpeedSq", "stdlib:continuous/Polynomial", X0 + 2120, Y0 + 300, constants={"N": 3},
           params={"p": "[1.0, 0.0, 0.01]"})
    d.node("AbsV", "stdlib:continuous/MathFunction", X0 + 2120, Y0 + 400, constants={"fn": 12})
    d.node("RollScale", "stdlib:continuous/Gain", X0 + 2120, Y0 + 700, params={"k": "20.0"})
    d.node("RollSign", "stdlib:continuous/MathFunction", X0 + 1980, Y0 + 720, constants={"fn": 8})
    d.node("Rolling", "stdlib:bondgraph/MSe", X0 + 1980, Y0 + 600, params={"gain": "c_rr*m_veh*g_n"})
    d.node("Grade", "stdlib:bondgraph/Se", X0 + 1860, Y0 + 620, params={"e": "-m_veh*g_n*sin(atan(grade_pct/100))"})
    d.bond("Ring", None, "FinalDrive", "p1")
    d.bond("FinalDrive", "p2", "HalfShaft", None)
    d.bond("HalfShaft", None, "ShaftTwist", None)
    d.bond("ShaftTwist", None, "ShaftK", "p")
    d.bond("ShaftTwist", None, "ShaftD", "p")
    d.bond("HalfShaft", None, "Wheel", None)
    d.bond("Wheel", None, "WheelSpeed", "a")
    d.bond("Wheel", None, "Brakes", "p")
    d.bond("Wheel", None, "Tyre", "a")
    d.bond("Vehicle", None, "Tyre", "b")
    d.bond("HalfShaft", None, "ShaftTorque", "p")
    d.bond("Vehicle", None, "VehicleMass", "p")
    d.bond("Vehicle", None, "VehicleSpeed", "a")
    d.bond("Vehicle", None, "Aero", "p")
    d.bond("Vehicle", None, "Rolling", "p")
    d.bond("Grade", "p", "Vehicle", None)
    d.sig("VehicleSpeed", "y", "SpeedSq", "u")
    d.sig("SpeedSq", "y", "AbsV", "u")
    d.sig("AbsV", "y", "Aero", "u")
    d.sig("VehicleSpeed", "y", "RollScale", "u")
    d.sig("RollScale", "y", "RollSign", "u")
    d.sig("RollSign", "y", "Rolling", "u")
    # ---- battery and DC bus
    d.junction("Bus", 0, X0 + 1000, Y0 - 300)
    d.node("DCLink", "stdlib:bondgraph/C", X0 + 1000, Y0 - 420, params={"c": num(BAT["C_dc"])},
           starts={"q": f"{BAT['C_dc']!r}*interp_ocv0"})
    d.node("BusVoltage", "stdlib:bondgraph/De", X0 + 1120, Y0 - 420)
    d.junction("BatJ", 1, X0 + 740, Y0 - 300)
    d.node("BatCurrent", "stdlib:bondgraph/Df", X0 + 740, Y0 - 420)
    d.node("Battery", "stdlib:electrical/Battery", X0 + 600, Y0 - 300,
           params={"capacity": num(BAT["capacity"]), "soc_table": vec(BAT["ocv_soc"]), "ocv_table": vec(BAT["ocv_v"]),
                   "R0": num(BAT["R0"]), "R1": num(BAT["R1"]), "C1": num(BAT["C1"])},
           constants={"N": len(BAT["ocv_soc"])}, starts={"soc": "soc0"})
    d.node("Gnd", "stdlib:electrical/Ground", X0 + 600, Y0 - 180)
    d.bond("Battery", "p", "BatJ", None)
    d.wire("Battery", "n", "Gnd", "p")
    d.bond("BatJ", None, "BatCurrent", "p")
    d.bond("BatJ", None, "Bus", None)
    d.bond("Bus", None, "DCLink", "p")
    d.bond("Bus", None, "BusVoltage", "p")
    d.bond("Bus", None, "Inv1", "p2")
    d.bond("Bus", None, "Inv2", "p2")
    # 12 V auxiliaries through the DC/DC converter: a resistor drawing P_aux at the nominal bus voltage
    d.node("Aux", "stdlib:bondgraph/R", X0 + 1240, Y0 - 300, params={"r": f"{BAT['ocv_v'][4]!r}^2/P_aux"})
    d.bond("Bus", None, "Aux", "p")


def machine(d: Diagram, k: str, x: float, y: float, shaft: str, kt: float, Rs: float) -> None:
    """A DC-equivalent PM machine: the inverter (MTF from the DC bus, modulus from the controller:
    machine voltage = u x bus voltage) onto the stator 1-junction with the stator resistance (copper
    loss) and inductance (L = R tau_el: it gives the stator current integral causality, so the
    undeclared EMConverter needs no arbitrary choice), and the electromechanical gyrator
    EMConverter (torque constant k) onto the shaft."""
    d.node(f"Inv{k}", "stdlib:bondgraph/MTF", x, y)
    d.junction(f"Stator{k}", 1, x + 140, y)
    d.node(f"Rs{k}", "stdlib:bondgraph/R", x + 80, y - 100, params={"r": num(Rs)})
    d.node(f"Ls{k}", "stdlib:bondgraph/I", x + 200, y - 100, params={"i": num(Rs * MG["tau_el"])})
    d.node(f"MG{k}", "stdlib:converters/EMConverter", x + 280, y, params={"k": num(kt)})
    d.node(f"Gnd{k}", "stdlib:electrical/Ground", x + 280, y + 100)
    d.bond(f"Inv{k}", "p1", f"Stator{k}", None)
    d.bond(f"Stator{k}", None, f"Rs{k}", "p")
    d.bond(f"Stator{k}", None, f"Ls{k}", "p")
    d.bond(f"Stator{k}", None, f"MG{k}", "p")
    d.wire(f"MG{k}", "n", f"Gnd{k}", "p")
    d.bond(f"MG{k}", "shaft", shaft, None)


def ocv0_expr() -> str:
    """The initial bus voltage: the OCV at soc0 (piecewise-linear expression over globals)."""
    s, v = BAT["ocv_soc"], BAT["ocv_v"]
    expr = num(v[-1])
    for i in range(len(s) - 2, -1, -1):
        seg = f"({num(v[i])} + ({num(v[i + 1] - v[i])})*(soc0 - {num(s[i])})/{num(s[i + 1] - s[i])})"
        expr = f"ifelse(soc0 <= {num(s[i + 1])}, {seg}, {expr})"
    return expr


# --------------------------------------------------------------------------- controllers
def control(d: Diagram, ems: bool, strategy: int = 0, step_force: float | None = None) -> None:
    X, Y = 0, 1000
    if step_force is None:
        d.node("Clock", "stdlib:sources/Time", X + 0, Y + 0)
        d.node("Cycle", "stdlib:continuous/Lookup1D", X + 140, Y + 0,
               params={"x": vec(D["nedc"]["t"]), "table": vec([v / 3.6 for v in D["nedc"]["v_kmh"]])},
               constants={"N": len(D["nedc"]["t"])})
        d.node("DriverMux", "stdlib:continuous/Mux2", X + 300, Y + 0)
        d.node("DriverError", "stdlib:continuous/Sum", X + 440, Y + 0, params={"signs": "[1.0, -1.0]"})
        d.node("Driver", "stdlib:continuous/PIController", X + 580, Y + 0,
               params={"Kp": "4.0*(m_veh + m_rot)", "Ti": "2.0"})
        d.sig("Clock", "y", "Cycle", "u")
        d.sig("Cycle", "y", "DriverMux", "u1")
        d.sig("VehicleSpeed", "y", "DriverMux", "u2")
        d.sig("DriverMux", "y", "DriverError", "u")
        d.sig("DriverError", "y", "Driver", "e")
        demand = ("Driver", "u")
        d.note("**Driver.** NEDC speed (Lookup1D over time, generated from the cycle definition) and a PI speed "
               "tracker: the tractive force demand F_dem = Kp (e + int e / Ti).", X, Y - 90, 700, 50, "green")
    else:
        d.node("Demand", "stdlib:sources/Step", X + 580, Y + 0,
               params={"t_step": num(D["ev"]["t_step"]), "initial": "0.0", "final": num(step_force)})
        demand = ("Demand", "y")
        d.note("**EV launch.** A step of the tractive force demand (MG2 150 N*m at the ring); the engine is off: the "
               "energy manager is replaced by constants (on = 0, speed reference 0).", X, Y - 90, 700, 50, "green")
    psc = {"Zs": "Zs", "Zr": "Zr", "FD": "FD", "r_w": "r_w", "w_fire": num(ENG["n_fire"] * RPM),
           "f0": num(D["engine"]["f0"]), "f1": num(D["engine"]["f1"]), "f2": num(D["engine"]["f2"]),
           "T1_max": num(MG["T1_max"]), "T2_max": num(MG["T2_max"]), "P2_max": num(MG["P2_max"]),
           "P_dis": f"{BAT['P_dis']!r} - P_aux", "P_chg": f"{BAT['P_chg']!r} + P_aux",
           "k1": num(MG["k1"]), "R1": num(MG["R1"]), "k2": num(MG["k2"]), "R2": num(MG["R2"])}
    d.node("HCU", "project:PowerSplitControl", X + 1100, Y + 200, params=psc)
    if ems:
        fuel_g, tg = ecms_candidates()
        d.node("EMS", "project:EnergyManager", X + 760, Y + 200, params={
            "strategy": str(strategy), "Zs": "Zs", "Zr": "Zr", "FD": "FD", "r_w": "r_w", "LHV": num(ENG["LHV"]),
            "w_min": num(ENG["n_min"] * RPM), "w_max": num(ENG["n_max"] * RPM), "w1_max": num(MG["n1_max"] * RPM),
            "T2_max": num(MG["T2_max"]), "P2_max": num(MG["P2_max"]), "c1": num(MG["c1"]), "b1": num(MG["b1"]),
            "c2": num(MG["c2"]), "b2": num(MG["b2"]), "P_dis": f"{BAT['P_dis']!r} - P_aux", "P_chg": f"{BAT['P_chg']!r} + P_aux",
            "soc_ref": "soc_ref", "P_on": "1000*P_on_kW", "P_off": "0.55*1000*P_on_kW", "P_min": "1000*P_min_kW",
            "ool_P": vec(D["ool"]["P"]), "ool_w": vec(D["ool"]["w"]), "s0": "s0", "k_p": "k_p",
            "wg": vec(ECMS_W), "Tg_cand": mat(tg), "fuel_g": mat(fuel_g),
            "f0": num(D["engine"]["f0"]), "f1": num(D["engine"]["f1"]), "f2": num(D["engine"]["f2"]),
            "R_bat": num(BAT["R0"] + BAT["R1"]), "V_bat": num(BAT["ocv_v"][4]),
            "m_kin": "m_veh + m_rot", "E_bat": num(BAT["capacity"] * 3600.0 * BAT["ocv_v"][4]),
            "eta_kin": "eta_kin"},
            constants={"NO": len(D["ool"]["P"]), "NW": len(ECMS_W), "NT": len(ECMS_F)})
        d.sig(*demand, "EMS", "F_dem")
        d.sig("VehicleSpeed", "y", "EMS", "v")
        d.sig("RingSpeed", "y", "EMS", "w_r")
        d.sig("BMS", "y", "EMS", "soc")
        for p in ("on", "w_ref", "T_ref"):
            d.sig("EMS", p, "HCU", p)
    else:
        d.node("EngineOff", "stdlib:sources/Constant", X + 760, Y + 160, params={"value": "0.0"})
        for p in ("on", "w_ref", "T_ref"):
            d.sig("EngineOff", "y", "HCU", p)
    d.sig(*demand, "HCU", "F_dem")
    for p, src in (("w_e", "EngineSpeed"), ("w_s", "SunSpeed"), ("w_r", "RingSpeed"), ("w_w", "WheelSpeed"),
                   ("V", "BusVoltage")):
        d.sig(src, "y", "HCU", p)
    d.sig("WOT", "y", "HCU", "T_wot")
    d.sig("HCU", "thr", "Throttle", "u1")
    d.sig("HCU", "d1", "Inv1", "u")
    d.sig("HCU", "d2", "Inv2", "u")
    d.sig("HCU", "u_b", "Brakes", "u")
    # battery management: coulomb counting (BatCurrent is positive while discharging)
    d.node("BMS", "stdlib:continuous/Integrator", X + 760, Y + 420, starts={"x": "soc0"})
    d.node("BMSGain", "stdlib:continuous/Gain", X + 620, Y + 420,
           params={"k": num(-1.0 / (3600.0 * BAT["capacity"]))})
    d.sig("BatCurrent", "y", "BMSGain", "u")
    d.sig("BMSGain", "y", "BMS", "u")


ECMS_W = [n * RPM for n in (1000, 1150, 1300, 1450, 1600, 1800, 2000, 2250, 2500, 2800, 3100, 3400, 3800, 4200, 4600, 5000)]
ECMS_F = [0.15, 0.25, 0.35, 0.45, 0.55, 0.62, 0.68, 0.74, 0.8, 0.85, 0.9, 0.95]


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            return ys[i] + (ys[i + 1] - ys[i]) * (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[-1]


def _map(w, T):
    fm = D["fuel_map"]
    ws, ts, tab = fm["w"], fm["T"], fm["table"]
    col = [_interp(w, ws, row) for row in tab]
    return _interp(T, ts, col)


def ecms_candidates():
    tg, fuel = [], []
    for w in ECMS_W:
        Tw = _interp(w, D["wot"]["w"], D["wot"]["T"])
        row_t = [f * Tw for f in ECMS_F]
        tg.append(row_t)
        fuel.append([_map(w, T) for T in row_t])
    return fuel, tg


# --------------------------------------------------------------------------- meters
def meters(d: Diagram, x: float, y: float) -> None:
    """Trip computer: fuel, distance, engine on-time and the energy integrals (a subsystem)."""
    m = Diagram()
    ins = [("fuel_rate", "kg/s"), ("v", "m/s"), ("fire", None), ("P_eng", "W"), ("P_mg1", "W"), ("P_mg2", "W"),
           ("P_bat", "W"), ("P_wheel", "W"), ("T_b", "N*m"), ("w_w", "rad/s")]
    integ = {"fuel_rate": "Fuel", "v": "Distance", "fire": "OnTime", "P_eng": "EEng", "P_mg1": "EMG1",
             "P_mg2": "EMG2", "P_bat": "EBat", "P_wheel": "EWheel"}
    for k, (name, unit) in enumerate(ins):
        if name in integ:
            m.node(integ[name], "stdlib:continuous/Integrator", 200, 60 + 100 * k)
            m.port(name, "input", integ[name], "u", unit)
    m.node("BrakePower", "stdlib:continuous/Product", 200, 1060)
    m.node("EBrake", "stdlib:continuous/Integrator", 360, 1060)
    m.port("T_b", "input", "BrakePower", "u1", "N*m")
    m.port("w_w", "input", "BrakePower", "u2", "rad/s")
    m.sig("BrakePower", "y", "EBrake", "u")
    # braking energy the driver asks for at the ring; what the friction brakes do not take
    # (EBrake) MG2 recovers: the regenerative share is 1 - EBrake/EBrakeDemand
    m.node("EBrakeDemand", "stdlib:continuous/Integrator", 360, 1160)
    m.port("P_brk", "input", "EBrakeDemand", "u", "W")
    m.node("FrictionShare", "stdlib:continuous/Divide", 500, 1110)
    m.node("DemandFloor", "stdlib:sources/Constant", 360, 1260, params={"value": "1000.0"})
    m.node("DemandMax", "stdlib:continuous/Max", 500, 1210)
    m.node("RegenShare", "stdlib:continuous/Polynomial", 640, 1110, constants={"N": 2}, params={"p": "[-1.0, 1.0]"})
    m.sig("EBrakeDemand", "y", "DemandMax", "u1")
    m.sig("DemandFloor", "y", "DemandMax", "u2")
    m.sig("EBrake", "y", "FrictionShare", "u1")
    m.sig("DemandMax", "y", "FrictionShare", "u2")
    m.sig("FrictionShare", "y", "RegenShare", "u")
    # fuel per 100 km (distance floored at 100 m) and litres
    m.node("DistFloor", "stdlib:sources/Constant", 360, 260, params={"value": "100.0"})
    m.node("DistMax", "stdlib:continuous/Max", 500, 160)
    m.node("FuelPerM", "stdlib:continuous/Divide", 640, 60)
    m.node("L100km", "stdlib:continuous/Gain", 780, 60, params={"k": num(1.0e5 / ENG["rho_fuel"])})
    m.node("FuelL", "stdlib:continuous/Gain", 640, -40, params={"k": num(1.0 / ENG["rho_fuel"])})
    m.sig("Distance", "y", "DistMax", "u1")
    m.sig("DistFloor", "y", "DistMax", "u2")
    m.sig("Fuel", "y", "FuelPerM", "u1")
    m.sig("DistMax", "y", "FuelPerM", "u2")
    m.sig("FuelPerM", "y", "L100km", "u")
    m.sig("Fuel", "y", "FuelL", "u")
    m.note("**Trip computer.** Integrals of the fuel rate (kg), the speed (m), the firing flag (engine on-time, s) "
           "and the powers (J); L100km/y = fuel / distance / density x 1e5; RegenShare/y = 1 - friction brake "
           "energy / braking energy demand.", 40, -140, 700, 50, "blue")
    m.subsystem(d, "Meters", x, y)


def fuel_and_meters(d: Diagram) -> None:
    d.node("FuelMap", "stdlib:continuous/Lookup2D", 300, 640,
           params={"breaks": mat([D["fuel_map"]["w"], D["fuel_map"]["T"]]), "table": mat(D["fuel_map"]["table"])},
           constants={"N": len(D["fuel_map"]["w"])})
    d.node("FuelCut", "stdlib:continuous/Product", 440, 640)
    d.sig("EngineSpeed", "y", "FuelMap", "u")
    d.sig("HCU", "T_e", "FuelMap", "v")
    d.sig("FuelMap", "y", "FuelCut", "u1")
    d.sig("HCU", "fire", "FuelCut", "u2")
    # power readouts (W): torque x speed of each shaft, voltage x current of the battery
    for name, a, b, x, y in (("PEng", ("Throttle", "y"), ("EngineSpeed", "y"), 300, 760),
                             ("PMG1", ("HCU", "T_g"), ("SunSpeed", "y"), 440, 760),
                             ("PMG2", ("HCU", "T_m"), ("RingSpeed", "y"), 580, 760),
                             ("PBat", ("BusVoltage", "y"), ("BatCurrent", "y"), 720, 760),
                             ("PWheel", ("ShaftTorque", "y"), ("WheelSpeed", "y"), 860, 760)):
        d.node(name, "stdlib:continuous/Product", x, y)
        d.sig(*a, name, "u1")
        d.sig(*b, name, "u2")
    # display: the optimal operating line's torque at the present engine speed (for the XY plot)
    ow, oP = [], []
    for w, P in zip(D["ool"]["w"], D["ool"]["P"]):
        if ow and w <= ow[-1] + 1e-6:
            oP[-1] = max(oP[-1], P)      # the line runs up in torque at its lowest speed
        else:
            ow.append(w)
            oP.append(P)
    d.node("OOL", "stdlib:continuous/Lookup1D", 300, 880,
           params={"x": vec(ow), "table": vec([P / w for w, P in zip(ow, oP)])}, constants={"N": len(ow)})
    d.sig("EngineSpeed", "y", "OOL", "u")
    # the friction brake torque the modulated R actually applies, u_b w_w
    d.node("BrakeTorque", "stdlib:continuous/Product", 1000, 760)
    d.sig("HCU", "u_b", "BrakeTorque", "u1")
    d.sig("WheelSpeed", "y", "BrakeTorque", "u2")
    meters(d, 1500, 1200)
    for p, (src, sp) in {"fuel_rate": ("FuelCut", "y"), "v": ("VehicleSpeed", "y"), "fire": ("HCU", "fire"),
                         "P_eng": ("PEng", "y"), "P_mg1": ("PMG1", "y"), "P_mg2": ("PMG2", "y"),
                         "P_bat": ("PBat", "y"), "P_wheel": ("PWheel", "y"), "T_b": ("BrakeTorque", "y"),
                         "P_brk": ("HCU", "P_brk"), "w_w": ("WheelSpeed", "y")}.items():
        d.sig(src, sp, "Meters", p)


# --------------------------------------------------------------------------- models
def model_vehicle(name: str, kind: str, strategy: int = 0) -> dict:
    d = Diagram()
    plant(d)
    if kind == "ev":
        control(d, ems=False, step_force=D["ev"]["F_demand"])
    else:
        control(d, ems=True, strategy=strategy)
    fuel_and_meters(d)
    d.note("**Plant (bond graph).** Engine (MSe = throttle x WOT(w), plus the unfired drag MSe) on its inertia, the "
           "input damper (C, R) onto the carrier; the planetary set (subsystem); MG1 on the sun, MG2 on the ring: "
           "inverter MTF from the DC bus, stator R (copper loss) and L, EMConverter, iron loss R; spin losses on the "
           "ring; ring -> final drive TF -> half shafts (C, R) -> wheel (friction brake MR) -> tyre -> vehicle mass I "
           "with drag MR, rolling resistance MSe and grade Se. Battery (Thevenin, OCV table), DC-link C and the "
           "auxiliary load R on the bus.", -40, -620, 1100, 80, "blue")
    params = vehicle_globals("ev" if kind == "ev" else "cycle")
    params.append(g("interp_ocv0", ocv0_expr(), "V", "Open-circuit voltage at soc0 (the DC-link start voltage)"))
    if kind == "ev":
        sett = settings(10.0, 2001)
        plots = [
            {"id": "p1", "title": "Vehicle speed (m/s)", "signals": ["VehicleSpeed/y"]},
            {"id": "p2", "title": "Shaft speeds (rad/s): engine, sun (MG1), ring (MG2)",
             "signals": ["EngineSpeed/y", "SunSpeed/y", "RingSpeed/y"]},
            {"id": "p3", "title": "Machine torques (N*m)", "signals": ["HCU/T_m", "HCU/T_g"]},
            {"id": "p4", "title": "Battery power (W) and bus voltage (V)", "signals": ["PBat/y", "BusVoltage/y"]},
        ]
        comment = ("EV launch: MG2 alone accelerates the Prius from rest with 150 N*m while MG1 holds the engine at rest. "
                   "Generated by design/build_model.py; see the README.")
    else:
        sett = settings(D["nedc"]["t_end"], 2361, reltol=1e-5, abstol=1e-5)
        plots = [
            {"id": "p1", "title": "Speed: NEDC and vehicle (m/s)", "signals": ["Cycle/y", "VehicleSpeed/y"]},
            {"id": "p2", "title": "Power flow (W)", "signals": ["PEng/y", "PMG1/y", "PMG2/y", "PBat/y", "PWheel/y"]},
            {"id": "p3", "title": "Shaft speeds (rad/s): engine, sun (MG1), ring (MG2)",
             "signals": ["EngineSpeed/y", "SunSpeed/y", "RingSpeed/y"]},
            {"id": "p4", "title": "Battery state of charge", "signals": ["Battery/soc"]},
            {"id": "p5", "title": "Engine operating points (torque vs speed) on the WOT and optimal lines",
             "signals": ["HCU/T_e", "WOT/y", "OOL/y"], "x": "EngineSpeed/y"},
            {"id": "p6", "title": "Fuel (l) and L/100 km", "signals": ["Meters/FuelL/y", "Meters/L100km/y"]},
        ]
        comment = (f"NEDC with the {'rule-based' if strategy == 0 else 'ECMS'} energy management (EMS/strategy = "
                   f"{strategy}). Generated by design/build_model.py; see the README.")
    return model_doc(name, comment, d, sett, plots, params, dashboard(name, kind))


def model_kinematics() -> dict:
    k = D["kin"]
    d = Diagram()
    d.node("Engine", "stdlib:bondgraph/MSe", 0, 300, params={"gain": "1.0"})
    d.node("EngineStep", "stdlib:sources/Step", 0, 420, params={"t_step": "0.5", "initial": "0.0", "final": num(k["T_c"])})
    d.junction("Carrier", 1, 160, 300)
    d.node("CarrierSpeed", "stdlib:converters/SpeedSensor", 160, 420)
    d.node("PCarrier", "stdlib:continuous/Product", 300, 420)
    d.sig("EngineStep", "y", "Engine", "u")
    d.bond("Engine", "p", "Carrier", None)
    d.bond("Carrier", None, "CarrierSpeed", "a")
    d.sig("EngineStep", "y", "PCarrier", "u1")
    d.sig("CarrierSpeed", "y", "PCarrier", "u2")
    planetary().subsystem(d, "Planetary", 580, 300)
    d.bond("Carrier", None, "Planetary", "carrier")
    for shaft, y, J, b in (("Sun", 120, k["J_s"], k["b_s"]), ("Ring", 480, k["J_r"], k["b_r"])):
        d.node(f"{shaft}Torque", "stdlib:continuous/Gain", 760, y + 200, params={"k": "Z" + shaft[0].lower()})
        d.node(f"P{shaft}", "stdlib:continuous/Product", 900, y + 200)
        d.sig("Planetary", "F", f"{shaft}Torque", "u")
        d.sig(f"{shaft}Torque", "y", f"P{shaft}", "u1")
        d.sig(f"{shaft}Speed", "y", f"P{shaft}", "u2")
        d.junction(shaft, 1, 900, y)
        d.node(f"{shaft}Inertia", "stdlib:bondgraph/I", 1020, y - 80, params={"i": num(J)})
        d.node(f"{shaft}Load", "stdlib:bondgraph/R", 1020, y + 60, params={"r": num(b)})
        d.node(f"{shaft}Speed", "stdlib:converters/SpeedSensor", 900, y + 110)
        d.bond("Planetary", shaft.lower(), shaft, None)
        d.bond(shaft, None, f"{shaft}Inertia", "p")
        d.bond(shaft, None, f"{shaft}Load", "p")
        d.bond(shaft, None, f"{shaft}Speed", "a")
    # the same set with the stdlib PlanetaryGear (equation block) for comparison
    Y = 800
    d.node("Engine2", "stdlib:bondgraph/MSe", 0, Y + 300, params={"gain": "1.0"})
    d.junction("Carrier2", 1, 160, Y + 300)
    d.node("CarrierSpeed2", "stdlib:converters/SpeedSensor", 160, Y + 420)
    d.sig("EngineStep", "y", "Engine2", "u")
    d.bond("Engine2", "p", "Carrier2", None)
    d.bond("Carrier2", None, "CarrierSpeed2", "a")
    d.node("Gear", "stdlib:rotation/PlanetaryGear", 580, Y + 300, params={"ratio": "Zr/Zs"})
    d.bond("Gear", "carrier", "Carrier2", None)
    for shaft, y, J, b in (("Sun2", Y + 120, k["J_s"], k["b_s"]), ("Ring2", Y + 480, k["J_r"], k["b_r"])):
        d.junction(shaft, 1, 900, y)
        d.node(f"{shaft}Inertia", "stdlib:bondgraph/I", 1020, y - 80, params={"i": num(J)})
        d.node(f"{shaft}Load", "stdlib:bondgraph/R", 1020, y + 60, params={"r": num(b)})
        d.node(f"{shaft}Speed", "stdlib:converters/SpeedSensor", 900, y + 110)
        d.bond("Gear", shaft[:-1].lower(), shaft, None)
        d.bond(shaft, None, f"{shaft}Inertia", "p")
        d.bond(shaft, None, f"{shaft}Load", "p")
        d.bond(shaft, None, f"{shaft}Speed", "a")
    d.note("**Kinematics.** A 60 N*m torque step on the carrier (the engine) splits over the sun (MG1 side, viscous "
           "load 0.05 N*m*s/rad) and the ring (wheels side, 0.4 N*m*s/rad) as 30 : 78. Top: the bond-graph planetary "
           "(subsystem). Bottom: the same set with the stdlib PlanetaryGear block, for comparison.", 0, -40, 900, 60, "blue")
    params = [g("Zs", PSD["Zs"], None, "Sun gear teeth"), g("Zr", PSD["Zr"], None, "Ring gear teeth")]
    plots = [
        {"id": "p1", "title": "Speeds (rad/s): sun, carrier, ring", "signals": ["SunSpeed/y", "CarrierSpeed/y", "RingSpeed/y"]},
        {"id": "p2", "title": "Power (W): carrier in, sun and ring out", "signals": ["PCarrier/y", "PSun/y", "PRing/y"]},
        {"id": "p3", "title": "Mesh force (tooth-normalised, N*m)", "signals": ["Planetary/MeshForce/y"]},
        {"id": "p4", "title": "Bond graph vs stdlib PlanetaryGear: ring speed", "signals": ["RingSpeed/y", "Ring2Speed/y"]},
    ]
    return model_doc("hybrid-kinematics", "The THS-II planetary set alone: Willis equation, torque split and power flow. "
                     "Generated by design/build_model.py; see the README.", d, settings(10.0, 2001, reltol=1e-9, abstol=1e-9),
                     plots, params, dashboard("hybrid-kinematics", "kin"))


# --------------------------------------------------------------------------- dashboards
def slider(cid, title, param, lo, hi, step, decimals, unit=None, size="2x1"):
    o = {"min": lo, "max": hi, "step": step, "decimals": decimals}
    if unit:
        o["unit"] = unit
    return {"id": cid, "kind": "slider", "size": size, "title": title, "parameter": f"global:{param}", "options": o}


def text(cid, title, body, size="2x1"):
    return {"id": cid, "kind": "text", "size": size, "title": title, "options": {"markdown": True, "text": body}}


def plot(cid, title, signals, size="2x2", x=None):
    c = {"id": cid, "kind": "plot", "size": size, "title": title, "signals": signals}
    if x:
        c["x"] = x
    return c


def value(cid, title, sig, unit, decimals=1, sparkline=False):
    o = {"decimals": decimals, "unit": unit}
    if sparkline:
        o["sparkline"] = True
    return {"id": cid, "kind": "value", "size": "1x1", "title": title, "signals": [sig], "options": o}


def dashboard(name: str, kind: str) -> dict:
    if kind == "kin":
        return {"autoRerun": True, "cards": [
            text("d1", "Power split", "The carrier (engine) torque splits **30 : 78** over the sun and the ring, and the "
                 "speeds obey the Willis equation 108 w_c = 30 w_s + 78 w_r. Change the teeth and re-run.", "2x2"),
            slider("d2", "Sun teeth Zs", "Zs", 20, 50, 1, 0),
            slider("d3", "Ring teeth Zr", "Zr", 60, 100, 1, 0),
            plot("d4", "Speeds (rad/s): sun, carrier, ring", ["SunSpeed/y", "CarrierSpeed/y", "RingSpeed/y"], "4x2"),
            plot("d5", "Power (W): carrier, sun, ring", ["PCarrier/y", "PSun/y", "PRing/y"]),
            value("d6", "Mesh force", "Planetary/MeshForce/y", "N*m", 2),
        ]}
    if kind == "ev":
        return {"autoRerun": True, "cards": [
            text("d1", "EV launch", "MG2 alone pulls away with **150 N*m**; MG1 turns backwards (w_sun = -2.6 w_ring) and "
                 "holds the engine at rest. Change the mass or the grade and re-run.", "2x2"),
            slider("d2", "Vehicle mass (kg)", "m_veh", 1200, 1800, 10, 0, "kg"),
            slider("d3", "Grade (%)", "grade_pct", -5, 10, 0.5, 1, "%"),
            value("d4", "Speed", "VehicleSpeed/y", "m/s", 2, True),
            value("d5", "Battery power", "PBat/y", "W", 0, True),
            plot("d6", "Shaft speeds (rad/s)", ["EngineSpeed/y", "SunSpeed/y", "RingSpeed/y"], "4x2"),
            plot("d7", "Vehicle speed (m/s)", ["VehicleSpeed/y"]),
            plot("d8", "Battery: power (W), voltage (V)", ["PBat/y", "BusVoltage/y"]),
        ]}
    return {"autoRerun": False, "cards": [
        text("d1", "Power split on the NEDC", "The **energy manager** chooses when the engine runs and at which point; "
             "MG1 holds the engine speed through the sun gear, MG2 fills in the wheel torque and recovers the braking "
             "energy. Switch the strategy, change the target SOC or the ECMS equivalence factor, then **Run**.", "2x2"),
        {"id": "d2", "kind": "select", "size": "2x1", "title": "Energy management (0 rule-based, 1 ECMS)",
         "parameter": "EMS/strategy"},
        slider("d3", "Target SOC", "soc_ref", 0.45, 0.75, 0.01, 2),
        slider("d4", "ECMS equivalence factor s0", "s0", 1.5, 4.0, 0.05, 2),
        slider("d5", "Rule-based engine start (kW)", "P_on_kW", 3, 20, 0.5, 1, "kW"),
        value("d6", "Fuel (L/100 km)", "Meters/L100km/y", "L/100km", 2),
        value("d7", "Fuel used (l)", "Meters/FuelL/y", "l", 3),
        value("d8", "State of charge", "Battery/soc", "", 3, True),
        value("d9", "Engine on-time (s)", "Meters/OnTime/y", "s", 0),
        value("d10", "Engine power", "PEng/y", "W", 0, True),
        value("d11", "MG1 power", "PMG1/y", "W", 0, True),
        value("d12", "MG2 power", "PMG2/y", "W", 0, True),
        value("d13", "Battery power", "PBat/y", "W", 0, True),
        value("d14", "Wheel power", "PWheel/y", "W", 0, True),
        value("d21", "Regenerative share of braking", "Meters/RegenShare/y", "", 3),
        plot("d15", "Speed: NEDC and vehicle (m/s)", ["Cycle/y", "VehicleSpeed/y"], "4x2"),
        plot("d16", "Planetary speeds (rad/s): carrier (engine), sun (MG1), ring (MG2)",
             ["CarrierSpeed/y", "SunSpeed/y", "RingSpeed/y"], "4x2"),
        plot("d17", "Engine operating points: torque (N*m) vs speed (rad/s), with the WOT and optimal lines",
             ["HCU/T_e", "WOT/y", "OOL/y"], "2x2", x="EngineSpeed/y"),
        plot("d18", "Power flow (W)", ["PEng/y", "PMG1/y", "PMG2/y", "PBat/y"], "2x2"),
        plot("d19", "Battery state of charge", ["Battery/soc"], "2x2"),
        plot("d20", "Fuel (l)", ["Meters/FuelL/y"], "2x2"),
    ]}


# --------------------------------------------------------------------------- expected.json
NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206", "E901", "E006", "E102"],
           "note": "no derivative causality, no torn algebraic loop, no solver or unit error"}


def patch_library() -> None:
    """Write the ECMS candidate tables as the EnergyManager's parameter defaults."""
    fuel_g, tg = ecms_candidates()
    path = EXAMPLE / "library" / "EnergyManager.jl"
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"NW::Int = \d+", f"NW::Int = {len(ECMS_W)}", src, count=1)
    src = re.sub(r"NT::Int = \d+", f"NT::Int = {len(ECMS_F)}", src, count=1)
    src = re.sub(r"(wg::Vec\{NW\} = )\[[^\]]*\]", lambda m: m.group(1) + "[" + ", ".join(f"{w:.1f}" for w in ECMS_W) + "]",
                 src, count=1)
    src = re.sub(r"(Tg_cand::Mat\{NW,NT\} = )[^,\]]*\]|(Tg_cand::Mat\{NW,NT\} = )zeros\(12, 8\)",
                 lambda m: (m.group(1) or m.group(2)) + mat(tg), src, count=1)
    src = re.sub(r"(fuel_g::Mat\{NW,NT\} = )[^,\]]*\]|(fuel_g::Mat\{NW,NT\} = )zeros\(12, 8\)",
                 lambda m: (m.group(1) or m.group(2)) + mat(fuel_g), src, count=1)
    path.write_text(src, encoding="utf-8", newline="\n")


def main() -> int:
    (EXAMPLE / "models").mkdir(exist_ok=True)
    patch_library()
    models = {
        "hybrid-kinematics": model_kinematics(),
        "hybrid-ev-mode": model_vehicle("hybrid-ev-mode", "ev"),
        "hybrid-rule-based": model_vehicle("hybrid-rule-based", "cycle", 0),
        "hybrid-ecms": model_vehicle("hybrid-ecms", "cycle", 1),
    }
    for name, doc in models.items():
        path = EXAMPLE / "models" / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "hybrid-powersplit", "models": list(models),
            "libraryDir": "library", "scenesDir": "scenes"}
    (EXAMPLE / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    import expected_checks  # noqa: E402  (design/expected_checks.py)
    (EXAMPLE / "expected.json").write_text(json.dumps(expected_checks.expected(D, NO_DIAG), indent=2) + "\n",
                                           encoding="utf-8", newline="\n")
    print("wrote expected.json")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    sys.exit(main())
