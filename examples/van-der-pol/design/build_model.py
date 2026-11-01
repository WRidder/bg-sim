# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the three `van-der-pol` models, the belt scene and `expected.json` from `design/design.json`.

    uv run examples/van-der-pol/design/design.py        # first: the reference numbers (scipy)
    uv run examples/van-der-pol/design/build_model.py

Models (examples/van-der-pol/models):

* ``vdp-tunnel-diode``  the electronic oscillator as a bond graph: parallel LC tank on a tunnel
                        diode (a nonlinear R, i = -a v + b v^3) on one 0-junction, its scaled states
                        next to the textbook equation in the circuit's seconds, energy bookkeeping,
                        cycle meter; the dashboard (mu, start amplitude, readouts, plots)
* ``vdp-belt``          the mechanical oscillator: a block on a spring rides a belt; the friction
                        contact is a nonlinear R (the cubic fit of the friction curve, and the full
                        Stribeck curve next to it); 3D scene
* ``vdp-textbook``      x'' - mu (1 - x^2) x' + x = 0 at mu = 0.1, 1, 5 and 20, each as a block
                        diagram and as an equation block
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
SCENE_BELT = "scenes/vdp-belt.sdf"


def num(v: float) -> str:
    return repr(float(v))


# --------------------------------------------------------------------------- document helpers


class Diagram:
    """One diagram level. `prefix` makes the node and connection ids unique in the whole model:
    the causality pass keys bonds by connection id, so two subsystems must not share one."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self.nodes: list[dict] = []
        self.connections: list = []
        self.annotations: list[dict] = []
        self._ids: dict[str, str] = {}
        self._c = 0

    def node(self, name: str, block, x: float, y: float, params=None, starts=None, constants=None,
             rotation: float = 0) -> str:
        nid = f"{self.prefix}n{len(self.nodes) + 1:02d}"
        if isinstance(block, str):
            b = {"junction": block} if block in ("0", "1") else {"ref": block}
        else:
            b = block
        self.nodes.append({
            "id": nid, "name": name, "block": b, "position": {"x": x, "y": y}, "rotation": rotation,
            "flipX": False, "params": params or {}, "constants": constants or {}, "starts": starts or {},
            "ui": {"showLabel": True, "color": None},
        })
        self._ids[name] = nid
        return nid

    def _conn(self, kind, a, pa, b, pb):
        self._c += 1
        self.connections.append((f"{self.prefix}c{self._c:02d}", kind, a, pa, b, pb))

    def sig(self, a, pa, b, pb):
        self._conn("signal", a, pa, b, pb)

    def bond(self, a, pa, b, pb):
        self._conn("bond", a, pa, b, pb)

    def note(self, text: str, x, y, w, h, color: str | None = None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def doc(self) -> dict:
        out = []
        for cid, kind, a, pa, b, pb in self.connections:
            frm = {"node": self._ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self._ids[b]}
            if pb is not None:
                to["port"] = pb
            out.append({"id": cid, "kind": kind, "from": frm, "to": to})
        return {"nodes": self.nodes, "connections": out, "annotations": self.annotations}

    def subsystem(self) -> dict:
        return {"subsystem": {"ports": [], "diagram": self.doc()}}


def model_doc(name, comment, diagram, settings, plots, parameters, scene=None, bindings=None, dashboard=None):
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": diagram.doc(), "settings": settings, "plots": plots,
        "scene": {"file": scene} if scene else None, "bindings": bindings or [], "parameters": parameters,
    }
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc


def settings(t_end: float, points: int, reltol: float = 1e-10, abstol: float = 1e-12) -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 20000}


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value, "unit": unit, "description": description}


SIDE_X0 = "ifelse(x0 > 0.0, 1.0, 0.0)"
AIRY3 = num(3.0 * DESIGN["airy"])

# --------------------------------------------------------------------------- 1. tunnel diode

CIRC = DESIGN["circuit"][DESIGN["circuit_default"]]
DIODE = DESIGN["diode"]


def model_tunnel_diode() -> dict:
    d = Diagram()
    # Bond graph: one 0-junction (the tank voltage v) with the capacitor branch, the inductor
    # branch, the diode and a voltage detector. The two 1-junctions carry the branch currents.
    d.node("Vm", "stdlib:bondgraph/De", 400, 60)
    d.node("J0", "0", 400, 240)
    d.node("Diode", "project:TunnelDiode", 640, 240, params={"a": "a", "b": "b"})
    d.node("Jc", "1", 240, 400)
    d.node("Cap", "stdlib:bondgraph/C", 120, 540, params={"c": "C"}, starts={"q": "C*v0"})
    d.node("Ic", "stdlib:bondgraph/Df", 340, 540)
    d.node("Jl", "1", 560, 400)
    d.node("Ind", "stdlib:bondgraph/I", 460, 540, params={"i": "L"}, starts={"P": "L*iL0"})
    d.node("Il", "stdlib:bondgraph/Df", 680, 540)
    d.bond("J0", None, "Vm", "p")
    d.bond("J0", None, "Diode", "p")
    d.bond("J0", None, "Jc", None)
    d.bond("Jc", None, "Cap", "p")
    d.bond("Jc", None, "Ic", "p")
    d.bond("J0", None, "Jl", None)
    d.bond("Jl", None, "Ind", "p")
    d.bond("Jl", None, "Il", "p")
    # Scaled states x = v/A and x' = i_C/(w0 C A), and the textbook equation in the circuit's seconds.
    d.node("Xc", "stdlib:continuous/Gain", 900, 60, params={"k": "1.0/A"})
    d.node("Yc", "stdlib:continuous/Gain", 900, 540, params={"k": "1.0/(w0*C*A)"})
    d.node("Ref", "project:VanDerPol", 900, 720, params={"mu": "mu", "w0": "w0"}, starts={"xs": "x0", "ys": "0.0"})
    d.sig("Vm", "y", "Xc", "u")
    d.sig("Ic", "y", "Yc", "u")
    # Energy bookkeeping: tank energy and the diode's absorbed power, split by sign.
    d.node("Split", "project:EnergySplit", 900, 240)
    d.node("Tank", "project:StoredEnergy", 900, 380, params={"c1": "C", "c2": "L"})
    d.sig("Diode", "P", "Split", "P")
    d.sig("Vm", "y", "Tank", "u1")
    d.sig("Il", "y", "Tank", "u2")
    # Cycle meter on the scaled states: period, frequency (MHz), amplitude, energy per cycle.
    d.node("Meter", "project:CycleMeter", 1160, 300, params={"w0": "w0", "f_scale": "1.0e-6"},
           starts={"side": SIDE_X0, "dside": "0.0"})
    d.sig("Xc", "y", "Meter", "u")
    d.sig("Yc", "y", "Meter", "du")
    d.sig("Split", "W_sup", "Meter", "w1")
    d.sig("Split", "W_abs", "Meter", "w2")
    d.node("Vpk", "stdlib:continuous/Gain", 1400, 300, params={"k": "1000.0*A"})
    d.sig("Meter", "amp", "Vpk", "u")
    # Readouts of the design: the two asymptotic periods and the component values for this mu.
    d.node("Tsmall", "stdlib:sources/Constant", 1400, 440, params={"value": "6.283185307179586*(1.0 + mu*mu/16.0)"})
    d.node("Trelax", "stdlib:sources/Constant", 1400, 540,
           params={"value": f"(3.0 - 2.0*log(2.0))*mu + {AIRY3}*mu^(-1.0/3.0)"})
    d.node("L_nH", "stdlib:sources/Constant", 1400, 640, params={"value": "L*1.0e9"})
    d.node("C_pF", "stdlib:sources/Constant", 1400, 740, params={"value": "C*1.0e12"})

    d.note("**Tunnel-diode oscillator.** One 0-junction carries the tank voltage v. Its branches: the "
           "capacitor C (1-junction Jc with the current detector Ic), the inductor L (1-junction Jl, Il), "
           "the tunnel diode (a nonlinear R, i = -a v + b v^3 about its bias point) and the voltage "
           "detector Vm. C v' = -i_L + a v - b v^3 and L i_L' = v.", 40, 640, 720, 90)
    d.note("**Van der Pol scaling.** tau = w0 t with w0 = 1/sqrt(L C), x = v/A with A = sqrt(a/(3 b)): "
           "x'' - mu (1 - x^2) x' + x = 0 with mu = a sqrt(L/C). Xc and Yc are the circuit's x and x'; Ref "
           "integrates the textbook equation in the circuit's seconds.", 40, 760, 720, 80, "blue")
    d.note("**Energy.** Tank/E = C v^2/2 + L i_L^2/2; Split integrates the diode power: W_sup while it "
           "supplies (|v| < sqrt(a/b)), W_abs while it dissipates. Tank/E + Split/W stays constant; on the "
           "limit cycle Meter/dw1 = Meter/dw2 (supplied = dissipated per cycle).", 860, 840, 700, 90, "green")

    plots = [
        {"id": "p1", "title": "Tank voltage v (V) and inductor current (A)", "signals": ["Vm/y", "Il/y"]},
        {"id": "p2", "title": "Scaled state x = v/A: circuit and textbook equation", "signals": ["Xc/y", "Ref/x"]},
        {"id": "p3", "title": "Scaled rate x' = i_C/(w0 C A): circuit and textbook equation", "signals": ["Yc/y", "Ref/y"]},
        {"id": "p4", "title": "Diode current (A) and absorbed power (W)", "signals": ["Diode/i", "Diode/P"]},
        {"id": "p5", "title": "Energy: tank, supplied and absorbed by the diode (J)",
         "signals": ["Tank/E", "Split/W_sup", "Split/W_abs", "Split/W"]},
        {"id": "p6", "title": "Cycle meter: frequency (MHz), scaled period and amplitude",
         "signals": ["Meter/f", "Meter/T_s", "Meter/amp"]},
        # XY plots: the phase portrait (x' against x, equal aspect: the small-mu cycle is a circle of
        # radius 2) and the diode's operating curve (its current against the tank voltage).
        {"id": "p7", "title": "Phase portrait: x' against x (circuit, scaled)", "signals": ["Yc/y"], "x": "Xc/y",
         "equalAspect": True},
        {"id": "p8", "title": "Textbook phase portrait: x' against x", "signals": ["Ref/y"], "x": "Ref/x",
         "equalAspect": True},
        {"id": "p9", "title": "Diode operating curve: current (A) against the tank voltage (V)",
         "signals": ["Diode/i"], "x": "Vm/y"},
    ]
    dashboard = {
        "autoRerun": True,
        "cards": [
            {"id": "d1", "kind": "text", "size": "2x1", "title": "Tunnel-diode Van der Pol oscillator",
             "options": {"markdown": True, "text":
                         "Change an input and the circuit runs again. **mu** = a sqrt(L/C) sets the tank impedance "
                         "sqrt(L/C) = mu/a at a fixed resonance of 10 MHz (L and C follow); **x0** is the start "
                         "voltage in units of A = 145 mV. Small mu: a 10 MHz sine of 2A = 290 mV. Large mu: "
                         "relaxation oscillations, slower than 10 MHz."}},
            {"id": "d2", "kind": "slider", "size": "2x1", "title": "mu (nonlinearity)", "parameter": "global:mu",
             "options": {"min": 0.05, "max": 10.0, "step": 0.05, "decimals": 2, "unit": ""}},
            {"id": "d3", "kind": "slider", "size": "2x1", "title": "Start voltage x0 = v(0)/A", "parameter": "global:x0",
             "options": {"min": 0.05, "max": 3.0, "step": 0.05, "decimals": 2, "unit": ""}},
            {"id": "d4", "kind": "value", "size": "1x1", "title": "Frequency", "signals": ["Meter/f"],
             "options": {"decimals": 2, "unit": "MHz"}},
            {"id": "d5", "kind": "value", "size": "1x1", "title": "Peak voltage", "signals": ["Vpk/y"],
             "options": {"decimals": 1, "unit": "mV"}},
            {"id": "d6", "kind": "value", "size": "1x1", "title": "Amplitude x (theory: 2)", "signals": ["Meter/amp"],
             "options": {"decimals": 4, "unit": ""}},
            {"id": "d7", "kind": "value", "size": "1x1", "title": "Period in tau", "signals": ["Meter/T_s"],
             "options": {"decimals": 4, "unit": ""}},
            {"id": "d8", "kind": "value", "size": "1x1", "title": "2 pi (1 + mu^2/16)", "signals": ["Tsmall/y"],
             "options": {"decimals": 4, "unit": ""}},
            {"id": "d9", "kind": "value", "size": "1x1", "title": "Relaxation estimate", "signals": ["Trelax/y"],
             "options": {"decimals": 4, "unit": ""}},
            {"id": "d10", "kind": "value", "size": "1x1", "title": "L", "signals": ["L_nH/y"],
             "options": {"decimals": 1, "unit": "nH"}},
            {"id": "d11", "kind": "value", "size": "1x1", "title": "C", "signals": ["C_pF/y"],
             "options": {"decimals": 1, "unit": "pF"}},
            {"id": "d15", "kind": "plot", "size": "2x2", "title": "Phase portrait x' against x",
             "signals": ["Yc/y"], "x": "Xc/y", "equalAspect": True},
            {"id": "d16", "kind": "plot", "size": "2x2", "title": "Diode current (A) against voltage (V)",
             "signals": ["Diode/i"], "x": "Vm/y"},
            {"id": "d12", "kind": "plot", "size": "4x2", "title": "Tank voltage (V)", "signals": ["Vm/y"]},
            {"id": "d13", "kind": "plot", "size": "4x2", "title": "Scaled x and x' (circuit and textbook)",
             "signals": ["Xc/y", "Yc/y", "Ref/x"]},
            {"id": "d14", "kind": "plot", "size": "4x2", "title": "Diode power (W): negative = supplies the tank",
             "signals": ["Diode/P"]},
        ],
    }
    c = CIRC
    parameters = [
        g("I_p", num(DIODE["I_p"]), "A", "Tunnel diode peak current (a 4.7 mA germanium diode, rounded)"),
        g("V_p", num(DIODE["V_p"]), "V", "Peak voltage"),
        g("I_v", num(DIODE["I_v"]), "A", "Valley current"),
        g("V_v", num(DIODE["V_v"]), "V", "Valley voltage"),
        g("V0", "0.5*(V_p + V_v)", "V", "Bias point: midpoint of the negative-resistance region (set by the DC supply)"),
        g("A", "0.5*(V_v - V_p)", "V", "Amplitude scale sqrt(a/(3 b)): half the peak-to-valley voltage"),
        g("a", "3.0*(I_p - I_v)/(4.0*A)", "A/V", "Negative conductance at the bias point (the diode is -1/a = -47 Ohm there)"),
        g("b", "a/(3.0*A*A)", "A/V^3", "Cubic coefficient: the fit's extrema sit at the peak and the valley"),
        g("f0", num(DESIGN["circuit"][DESIGN["circuit_default"]]["f0"]), "Hz", "Tank resonance 1/(2 pi sqrt(L C))"),
        g("w0", "6.283185307179586*f0", "rad/s", "Time scale of the Van der Pol form: tau = w0 t"),
        g("mu", num(c["mu"]), None, "Van der Pol parameter mu = a sqrt(L/C)"),
        g("Z0", "mu/a", "Ohm", "Tank characteristic impedance sqrt(L/C) that gives this mu"),
        g("L", "Z0/w0", "H", "Tank inductance"),
        g("C", "1.0/(Z0*w0)", "F", "Tank capacitance"),
        g("x0", num(DESIGN["x0"]), None, "Start voltage in units of A (x(0) = x0, x'(0) = 0)"),
        g("v0", "A*x0", "V", "Start voltage of the tank capacitor"),
        g("iL0", "a*v0 - b*v0^3", "A", "Start inductor current: the diode current, so the capacitor current is 0 (x'(0) = 0)"),
    ]
    return model_doc(
        "vdp-tunnel-diode",
        "Van der Pol's oscillator in electronics: a parallel LC tank on a tunnel diode biased in its negative-"
        "resistance region, as a bond graph (C, I and a nonlinear R on one 0-junction). mu = a sqrt(L/C), "
        "tau = t/sqrt(L C), x = v/A with A = sqrt(a/(3 b)). The textbook equation runs alongside in the circuit's "
        "seconds; the cycle meter and the energy split read the limit cycle.",
        d, settings(c["t_end"], 32001, reltol=1e-11, abstol=1e-22), plots, parameters, dashboard=dashboard)


# --------------------------------------------------------------------------- 2. belt

BELT = DESIGN["belt"]
BELT_PITCH = 0.04   # m, stripe pitch on the drawn belt


def belt_rig(prefix: str, friction: str, fparams: dict, energy: bool) -> Diagram:
    s = Diagram(prefix)
    # a port flow is positive into its element: the source that drives the junction carries -v_b
    s.node("Belt", "stdlib:bondgraph/Sf", 40, 220, params={"f": "-v_b"})
    s.node("Jb", "0", 240, 220)
    s.node("Fric", friction, 240, 60, params=fparams)
    s.node("Fm", "stdlib:bondgraph/De", 240, 400)
    s.node("Jm", "1", 480, 220)
    s.node("Mass", "stdlib:bondgraph/I", 480, 60, params={"i": "m"}, starts={"P": "m*xd0"})
    s.node("Spring", "stdlib:bondgraph/C", 680, 120, params={"c": "1.0/k"}, starts={"q": "x_s"})
    s.node("Vel", "stdlib:bondgraph/Df", 680, 300)
    s.node("Pos", "stdlib:converters/PositionSensor", 480, 400, starts={"x": "x_s"})
    s.bond("Belt", "p", "Jb", None)
    s.bond("Jb", None, "Fric", "p")
    s.bond("Jb", None, "Fm", "p")
    s.bond("Jb", None, "Jm", None)
    s.bond("Jm", None, "Mass", "p")
    s.bond("Jm", None, "Spring", "p")
    s.bond("Jm", None, "Vel", "p")
    s.bond("Jm", None, "Pos", "a")
    # Scaled Van der Pol states: x = x'/V, x' = x''/(w0 V) = (F - k x)/(m w0 V).
    s.node("Xm", "stdlib:continuous/Gain", 900, 300, params={"k": "1.0/V"})
    s.node("Ym", "project:Lin2", 900, 440, params={"k1": "1.0/(m*w0*V)", "k2": "-k/(m*w0*V)", "c": "0.0"})
    s.sig("Vel", "y", "Xm", "u")
    s.sig("Fm", "y", "Ym", "u1")
    s.sig("Pos", "y", "Ym", "u2")
    s.node("Meter", "project:CycleMeter", 1120, 260, params={"w0": "w0", "f_scale": "1.0"},
           starts={"side": SIDE_X0, "dside": "ifelse(mu*(x0 - x0^3/3.0) > 0.0, 1.0, 0.0)"})
    s.sig("Xm", "y", "Meter", "u")
    s.sig("Ym", "y", "Meter", "du")
    if energy:
        # Energy of the oscillation about the force balance x_s = F0/k, and the power the contact
        # takes out of it, -(F - F0) x'. The contact's own output dF = F - F0 has no cancellation
        # against F0, so the sign of the power is clean where it touches zero (x' = 0).
        s.node("Dev", "stdlib:continuous/Gain", 680, 560, params={"k": "-1.0"})
        s.node("Pc", "stdlib:continuous/Product", 900, 580)
        s.node("Split", "project:EnergySplit", 1120, 580)
        s.node("Store", "project:StoredEnergy", 1120, 440, params={"c1": "k", "c2": "m", "o1": "x_s"})
        s.sig("Fric", "dF", "Dev", "u")
        s.sig("Dev", "y", "Pc", "u1")
        s.sig("Vel", "y", "Pc", "u2")
        s.sig("Pc", "y", "Split", "P")
        s.sig("Pos", "y", "Store", "u1")
        s.sig("Vel", "y", "Store", "u2")
        s.sig("Split", "W_sup", "Meter", "w1")
        s.sig("Split", "W_abs", "Meter", "w2")
    else:
        s.node("Zero", "stdlib:sources/Constant", 900, 580, params={"value": "0.0"})
        s.sig("Zero", "y", "Meter", "w1")
        s.sig("Zero", "y", "Meter", "w2")
    s.note("**Belt drive.** Sf Belt imposes the belt speed v_b on the 0-junction Jb, whose effort is the "
           "friction force F. The slip w = v_b - x' goes to the friction contact Fric (a nonlinear R, "
           "F = F(w)); the rest drives the block's 1-junction Jm: mass m (I), spring k (C), velocity "
           "detector Vel and position sensor Pos.", 40, 680, 760, 90)
    return s


def model_belt() -> dict:
    b = BELT
    # The rig with the cubic fit on the root diagram, the full-curve rig as a subsystem beside it.
    d = belt_rig("", "project:BeltFriction", {"F0": "F0", "alpha": "alpha", "beta": "beta", "v_b": "v_b"}, True)
    d.node("Stribeck", belt_rig("str_", "project:StribeckFriction",
                                {"F_n": "F_n", "mu_c": "mu_c", "mu_s": "mu_s", "v_s": "v_s", "sigma": "sigma",
                                 "v_eps": "v_eps"}, False).subsystem(), 1340, 60)
    d.node("Ref", "project:VanDerPol", 1340, 420, params={"mu": "mu", "w0": "w0"},
           starts={"xs": "x0", "ys": "mu*(x0 - x0^3/3.0)"})
    d.node("RefV", "stdlib:continuous/Gain", 1340, 580, params={"k": "V"})
    d.sig("Ref", "x", "RefV", "u")
    d.node("BeltPhase", "stdlib:sources/Sawtooth", 1340, 240,
           params={"amplitude": num(BELT_PITCH), "period": f"{num(BELT_PITCH)}/v_b", "offset": "0.0", "t_start": "0.0"})
    d.note("**Belt-driven Van der Pol oscillator.** This diagram: the friction curve's third-order fit about the belt "
           "speed, F = F0 - alpha (w - v_b) + beta (w - v_b)^3, which makes the block obey Rayleigh's equation "
           "m x'' - alpha x' + beta x'^3 + k (x - x_s) = 0; its velocity obeys Van der Pol with mu = alpha/sqrt(k m), "
           "tau = sqrt(k/m) t, x_vdp = x'/V, V = sqrt(alpha/(3 beta)). Stribeck: the same rig on the full curve. "
           "Ref: the textbook equation in the rig's seconds (RefV = V x, in m/s).", 40, 790, 1000, 90)
    d.note("**Why the viscous term.** alpha = alpha_f - sigma: the Stribeck drop alone (alpha_f = 51.5 N s/m) "
           "would grow the velocity swing to the belt speed, and the block would stick (stick-slip, not Van der "
           "Pol). The viscous friction sigma = 46.5 N s/m keeps the net slope small: mu = 0.5, peak slip "
           "variation 62 % of v_b.", 840, 680, 560, 100, "blue")
    plots = [
        {"id": "p1", "title": "Block velocity (m/s): cubic fit, Stribeck curve, textbook V x",
         "signals": ["Vel/y", "Stribeck/Vel/y", "RefV/y"]},
        {"id": "p2", "title": "Block position (m)", "signals": ["Pos/y", "Stribeck/Pos/y"]},
        {"id": "p3", "title": "Scaled states x, x' of the cubic rig and the textbook equation",
         "signals": ["Xm/y", "Ref/x", "Ym/y", "Ref/y"]},
        {"id": "p4", "title": "Friction force (N) and slip (m/s)",
         "signals": ["Fric/F", "Stribeck/Fric/F", "Fric/w", "Stribeck/Fric/w"]},
        {"id": "p5", "title": "Oscillation energy, supplied and absorbed by the contact (J)",
         "signals": ["Store/E", "Split/W_sup", "Split/W_abs"]},
        {"id": "p6", "title": "Cycle meters: period (s) and velocity amplitude (scaled)",
         "signals": ["Meter/T", "Stribeck/Meter/T", "Meter/amp", "Stribeck/Meter/amp"]},
        # XY plots: the scaled phase portrait, and the friction force against the slip (the part of the
        # friction curve the cycle sweeps: the falling, negative-slope branch that feeds the oscillation).
        {"id": "p7", "title": "Phase portrait of the cubic rig: x' against x (scaled)", "signals": ["Ym/y"],
         "x": "Xm/y", "equalAspect": True},
        {"id": "p8", "title": "Friction force (N) against slip (m/s), cubic rig",
         "signals": ["Fric/F"], "x": "Fric/w"},
    ]
    n_coils = 8
    bindings = [{"target": "joint:block", "property": "position", "signal": "Pos/y"},
                {"target": "joint:belt", "property": "position", "signal": "BeltPhase/y"},
                {"target": "visual:block_body", "property": "color", "signal": "Fric/w", "colormap": "heat",
                 "range": [0.0, 2.0 * b["v_b"]]}]
    for k in range(1, n_coils + 1):
        bindings.append({"target": f"joint:coil{k}", "property": "position", "signal": "Pos/y",
                         "gain": k / (n_coils + 1)})
    parameters = [
        g("m", num(b["m"]), "kg", "Block mass"),
        g("k", num(b["k"]), "N/m", "Spring stiffness"),
        g("F_n", num(b["F_n"]), "N", "Normal force on the belt (the block's weight and a spring-loaded pressure pad)"),
        g("mu_c", num(b["mu_c"]), None, "Coulomb (kinetic) friction coefficient"),
        g("mu_s", num(b["mu_s"]), None, "Static friction coefficient"),
        g("v_s", num(b["v_s"]), "m/s", "Stribeck velocity of the Gaussian drop exp(-(w/v_s)^2)"),
        g("v_eps", num(b["v_eps"]), "m/s", "Smooth-sign velocity of the Stribeck block"),
        g("v_b", "v_s/sqrt(2.0)", "m/s", "Belt speed: the inflection point of the Stribeck drop"),
        g("w0", "sqrt(k/m)", "rad/s", "Time scale of the Van der Pol form: tau = w0 t"),
        g("mu", num(b["mu"]), None, "Van der Pol parameter mu = alpha/sqrt(k m) (chosen; sets sigma)"),
        g("alpha_f", "F_n*(mu_s - mu_c)*sqrt(2.0)*exp(-0.5)/v_s", "N*s/m", "Falling slope of the Stribeck drop at v_b"),
        g("alpha", "mu*sqrt(k*m)", "N*s/m", "Net falling slope of the friction curve at v_b"),
        g("sigma", "alpha_f - alpha", "N*s/m", "Viscous friction coefficient"),
        g("beta", "F_n*(mu_s - mu_c)*4.0*sqrt(2.0)*exp(-0.5)/(6.0*v_s^3)", "N*s^3/m^3", "Cubic coefficient F'''(v_b)/6"),
        g("F0", "F_n*(mu_c + (mu_s - mu_c)*exp(-0.5)) + sigma*v_b", "N", "Friction force at the belt speed"),
        g("x_s", "F0/k", "m", "Spring stretch at the force balance F0 = k x_s"),
        g("V", "sqrt(alpha/(3.0*beta))", "m/s", "Velocity scale: x_vdp = x'/V"),
        g("x0", num(DESIGN["x0"]), None, "Start velocity in units of V (the block starts at x_s)"),
        g("xd0", "V*x0", "m/s", "Start velocity of the block"),
    ]
    return model_doc(
        "vdp-belt",
        "Van der Pol's oscillator in mechanics: a block on a spring rides a belt; the falling friction-velocity "
        "curve about the belt speed is a negative damper. the curve's Taylor fit (Rayleigh's equation, "
        "exactly Van der Pol in the velocity); Stribeck: the full curve. Ref: the textbook equation in seconds.",
        d, settings(b["t_end"], 8001, reltol=1e-11, abstol=1e-13), plots, parameters, scene=SCENE_BELT,
        bindings=bindings)


# --------------------------------------------------------------------------- 3. textbook

TEXT_MUS = [("Mu01", "mu_1", 0.1), ("Mu1", "mu_2", 1.0), ("Mu5", "mu_3", 5.0), ("Mu20", "mu_4", 20.0)]


def textbook_rig(prefix: str, mu_name: str) -> Diagram:
    s = Diagram(prefix)
    s.node("Sq", "stdlib:continuous/Polynomial", 40, 200, params={"p": "[-1.0, 0.0, 1.0]"}, constants={"N": "3"})
    s.node("Prod", "stdlib:continuous/Product", 220, 200)
    s.node("Mu", "stdlib:continuous/Gain", 400, 200, params={"k": mu_name})
    s.node("Acc", "project:Lin2", 580, 200, params={"k1": "1.0", "k2": "-1.0", "c": "0.0"})
    s.node("Y", "stdlib:continuous/Integrator", 760, 200, starts={"x": "y0"})
    s.node("X", "stdlib:continuous/Integrator", 940, 200, starts={"x": "x0"})
    s.sig("X", "y", "Sq", "u")
    s.sig("Sq", "y", "Prod", "u1")
    s.sig("Y", "y", "Prod", "u2")
    s.sig("Prod", "y", "Mu", "u")
    s.sig("Mu", "y", "Acc", "u1")
    s.sig("X", "y", "Acc", "u2")
    s.sig("Acc", "y", "Y", "u")
    s.sig("Y", "y", "X", "u")
    s.node("Eq", "project:VanDerPol", 400, 380, params={"mu": mu_name, "w0": "1.0"}, starts={"xs": "x0", "ys": "y0"})
    s.node("Zero", "stdlib:sources/Constant", 760, 480, params={"value": "0.0"})
    s.node("Meter", "project:CycleMeter", 940, 380, params={"w0": "1.0", "f_scale": "1.0"},
           starts={"side": SIDE_X0, "dside": "ifelse(y0 > 0.0, 1.0, 0.0)"})
    s.sig("X", "y", "Meter", "u")
    s.sig("Y", "y", "Meter", "du")
    s.sig("Zero", "y", "Meter", "w1")
    s.sig("Zero", "y", "Meter", "w2")
    s.note("**Block diagram** of x'' = mu (1 - x^2) x' - x: Sq = 1 - x^2, times x' (Prod), times mu, minus x, "
           "integrated twice (Y gives x', X gives x). **Eq** is the same equation as an equation block; the cycle "
           "Meter reads the block diagram's period T_s and amplitude.", 40, 560, 900, 70)
    return s


def model_textbook() -> dict:
    d = Diagram()
    for k, (name, mu_name, _mu) in enumerate(TEXT_MUS):
        d.node(name, textbook_rig(name.lower() + "_", mu_name).subsystem(), 80 + 240 * k, 80)
    d.note("**Van der Pol, x'' - mu (1 - x^2) x' + x = 0**, from x = 0.5, x' = 0, in tau (the run time). "
           "Four subsystems at mu = 0.1, 1, 5 and 20; open one for its block diagram and equation block. "
           "Small mu: a near-sine of amplitude 2 and period 2 pi (1 + mu^2/16). Large mu: relaxation "
           "oscillations, slow drifts along the branches |x| > 1 and fast jumps, period about "
           "(3 - 2 ln 2) mu + 7.014 mu^(-1/3).", 40, 220, 940, 110)
    plots = [
        {"id": "p1", "title": "x(tau) at mu = 0.1, 1, 5, 20",
         "signals": ["Mu01/X/y", "Mu1/X/y", "Mu5/X/y", "Mu20/X/y"]},
        {"id": "p2", "title": "x'(tau) at mu = 0.1, 1, 5 (mu = 20 peaks at 27)",
         "signals": ["Mu01/Y/y", "Mu1/Y/y", "Mu5/Y/y"]},
        {"id": "p3", "title": "x'(tau) at mu = 20", "signals": ["Mu20/Y/y"]},
        {"id": "p4", "title": "Block diagram against the equation block (mu = 5)", "signals": ["Mu5/X/y", "Mu5/Eq/x"]},
        {"id": "p5", "title": "Measured period T_s", "signals": ["Mu01/Meter/T_s", "Mu1/Meter/T_s", "Mu5/Meter/T_s",
                                                                 "Mu20/Meter/T_s"]},
        {"id": "p6", "title": "Measured amplitude", "signals": ["Mu01/Meter/amp", "Mu1/Meter/amp", "Mu5/Meter/amp",
                                                                "Mu20/Meter/amp"]},
        # XY plots: the phase portraits, from x = 0.5 out to the limit cycle.
        {"id": "p7", "title": "Phase portrait at mu = 1: x' against x", "signals": ["Mu1/Y/y"], "x": "Mu1/X/y",
         "equalAspect": True},
        {"id": "p8", "title": "Phase portrait at mu = 5 (relaxation): x' against x", "signals": ["Mu5/Y/y"],
         "x": "Mu5/X/y"},
    ]
    parameters = [g(mu_name, num(mu), None, f"mu of subsystem {name}") for name, mu_name, mu in TEXT_MUS] + [
        g("x0", num(DESIGN["x0"]), None, "Start value x(0)"),
        g("y0", num(DESIGN["y0"]), None, "Start rate x'(0)"),
    ]
    return model_doc(
        "vdp-textbook",
        "The textbook Van der Pol equation x'' - mu (1 - x^2) x' + x = 0 at mu = 0.1, 1, 5 and 20, each as a block "
        "diagram and as an equation block, from x = 0.5, x' = 0; time is tau.",
        d, settings(DESIGN["tau_end"], 20001, reltol=1e-11, abstol=1e-12), plots, parameters)


# --------------------------------------------------------------------------- scene


def _vis(name, pose, geom, rgba):
    return (f'      <visual name="{name}">\n        <pose>{pose}</pose>\n'
            f'        <geometry>{geom}</geometry>\n'
            f'        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def _box(sx, sy, sz):
    return f"<box><size>{sx:.4f} {sy:.4f} {sz:.4f}</size></box>"


def _cyl(r, length):
    return f"<cylinder><radius>{r:.4f}</radius><length>{length:.4f}</length></cylinder>"


def scene_belt() -> str:
    """Z up, metres. x is the block's position: 0 is the unstretched spring, the block sits at x_s."""
    n_coils = 8
    L0 = 0.08            # drawn spring length at x = 0 (wall face to block face)
    bw = 0.05            # block edge
    belt_top = 0.06
    x_wall = -L0
    x_lo, x_hi = -0.12, 0.42
    base = _vis("table", f"{(x_lo + x_hi) / 2:.4f} 0 0.005 0 0 0", _box(x_hi - x_lo + 0.12, 0.2, 0.01), "0.28 0.30 0.34 1")
    base += _vis("wall", f"{x_wall - 0.01:.4f} 0 {belt_top + 0.06:.4f} 0 0 0", _box(0.02, 0.12, 0.12), "0.62 0.64 0.68 1")
    base += _vis("wall_foot", f"{x_wall - 0.01:.4f} 0 {(belt_top + 0.0) / 2 + 0.005:.4f} 0 0 0",
                 _box(0.02, 0.12, belt_top), "0.50 0.52 0.56 1")
    span = x_hi - x_lo
    base += _vis("belt_top", f"{(x_lo + x_hi) / 2:.4f} 0 {belt_top - 0.004:.4f} 0 0 0", _box(span, 0.08, 0.008), "0.10 0.10 0.11 1")
    base += _vis("belt_bottom", f"{(x_lo + x_hi) / 2:.4f} 0 0.026 0 0 0", _box(span, 0.08, 0.008), "0.10 0.10 0.11 1")
    for name, x in (("pulley_left", x_lo), ("pulley_right", x_hi)):
        base += _vis(name, f"{x:.4f} 0 0.043 1.5708 0 0", _cyl(0.017, 0.086), "0.70 0.72 0.76 1")
        base += _vis(name + "_hub", f"{x:.4f} 0.046 0.043 1.5708 0 0", _cyl(0.006, 0.01), "0.85 0.6 0.15 1")
    base += _vis("pad_bracket", f"{0.19 + bw / 2:.4f} 0 {belt_top + bw + 0.045:.4f} 0 0 0", _box(0.012, 0.11, 0.012), "0.55 0.57 0.6 1")
    base += _vis("pad_post_a", f"{0.19 + bw / 2:.4f} 0.05 {belt_top + bw / 2 + 0.02:.4f} 0 0 0", _box(0.012, 0.01, bw + 0.05), "0.55 0.57 0.6 1")
    links = [f'    <link name="rig">\n      <pose>0 0 0 0 0 0</pose>\n{base}    </link>\n']
    joints = []
    # belt stripes: a link that moves by the belt phase (a sawtooth over one stripe pitch)
    stripes = ""
    n_str = int(round((x_hi - x_lo) / BELT_PITCH))
    for j in range(n_str):
        x = x_lo + 0.01 + j * BELT_PITCH
        if x + BELT_PITCH > x_hi:
            break
        stripes += _vis(f"stripe{j + 1:02d}", f"{x:.4f} 0 {belt_top + 0.0005:.4f} 0 0 0", _box(0.006, 0.078, 0.001), "0.85 0.6 0.15 1")
    links.append(f'    <link name="belt_marks">\n      <pose>0 0 0 0 0 0</pose>\n{stripes}    </link>\n')
    joints.append('    <joint name="belt" type="prismatic">\n      <parent>rig</parent>\n      <child>belt_marks</child>\n'
                  '      <axis><xyz>1 0 0</xyz></axis>\n    </joint>\n')
    # the block: its left face is at x (joint position)
    blk = _vis("block_body", f"{bw / 2:.4f} 0 {belt_top + bw / 2:.4f} 0 0 0", _box(bw, bw, bw), "0.25 0.45 0.80 1")
    blk += _vis("block_pad", f"{bw / 2:.4f} 0 {belt_top + bw + 0.004:.4f} 0 0 0", _box(0.03, 0.03, 0.008), "0.12 0.12 0.13 1")
    blk += _vis("block_hook", f"{-0.004:.4f} 0 {belt_top + bw / 2:.4f} 0 1.5708 0", _cyl(0.006, 0.008), "0.8 0.8 0.82 1")
    links.append(f'    <link name="block_link">\n      <pose>0 0 0 0 0 0</pose>\n{blk}    </link>\n')
    joints.append('    <joint name="block" type="prismatic">\n      <parent>rig</parent>\n      <child>block_link</child>\n'
                  '      <axis><xyz>1 0 0</xyz></axis>\n    </joint>\n')
    # spring coils: coil k sits at the fraction k/(n+1) between the wall and the block
    for k in range(1, n_coils + 1):
        x_rest = x_wall + k / (n_coils + 1) * L0
        coil = _vis(f"coil{k}_ring", f"0 0 {belt_top + bw / 2:.4f} 0 1.5708 0", _cyl(0.014, 0.003), "0.80 0.82 0.85 1")
        links.append(f'    <link name="coil{k}_link">\n      <pose>{x_rest:.4f} 0 0 0 0 0</pose>\n{coil}    </link>\n')
        joints.append(f'    <joint name="coil{k}" type="prismatic">\n      <parent>rig</parent>\n      <child>coil{k}_link</child>\n'
                      '      <axis><xyz>1 0 0</xyz></axis>\n    </joint>\n')
    return (
        '<?xml version="1.0"?>\n'
        "<!--\n"
        "  vdp-belt: a block on a spring rides a belt (Z up, metres). The prismatic joint \"block\" (axis +X) is\n"
        f"  the block position x, 0 at the unstretched spring (the block's left face {L0} m from the wall); it\n"
        f"  oscillates about x_s = {BELT['x_s']:.4f} m by +-4.5 mm. The joints coil1..coil{n_coils} move the spring's rings by\n"
        "  k/(n+1) of x; \"belt\" moves the belt's stripes by the belt phase (a sawtooth over one stripe pitch).\n"
        "  The block is coloured by the slip velocity. Written by examples/van-der-pol/design/build_model.py.\n"
        "-->\n"
        '<sdf version="1.9">\n  <model name="vdp_belt">\n'
        + "".join(links) + "".join(joints)
        + "  </model>\n</sdf>\n"
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(EXAMPLE))


# --------------------------------------------------------------------------- checks

NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
           "note": "integral causality on every store, no algebraic loop, no event storm"}


def circuit_checks(c: dict, full: bool) -> list:
    lc = DESIGN["cycles"][f"{c['mu']:g}"]
    checks = [
        NO_DIAG,
        {"kind": "period", "signal": "Vm/y", "direction": "up", "n": c["n_last"], "value": c["period"], "rtol": 1e-6,
         "note": f"last full cycle of the tank voltage: {c['freq'] / 1e6:.6f} MHz (scipy, the circuit in SI units)"},
        {"kind": "cursor_value", "signal": "Meter/T_s", "t": c["t_end"], "value": lc["period"], "rtol": 1e-7,
         "note": "the cycle meter's scaled period w0 T equals the textbook limit cycle's period (scipy shooting)"},
        {"kind": "cursor_value", "signal": "Meter/f", "t": c["t_end"], "value": c["freq_cycle"] * 1e-6, "rtol": 1e-7,
         "note": "frequency in MHz = f0 2 pi / T(mu)"},
        {"kind": "cursor_value", "signal": "Meter/amp", "t": c["t_end"], "value": lc["amplitude"], "rtol": 1e-7,
         "note": "amplitude of x = v/A on the limit cycle (scipy shooting); averaging theory: 2"},
        {"kind": "cursor_value", "signal": "Vpk/y", "t": c["t_end"], "value": c["v_amp_cycle"] * 1e3, "rtol": 1e-7,
         "note": "peak voltage deviation A x_max in mV"},
        {"kind": "compare_signals", "signal": "Xc/y", "signal_b": "Ref/x", "max_abs": 1e-6,
         "note": f"the circuit's scaled voltage is the textbook x (scipy: {c['scaled_vs_textbook_x']:.1e})"},
        {"kind": "compare_signals", "signal": "Yc/y", "signal_b": "Ref/y", "max_abs": 1e-6,
         "note": f"the circuit's scaled capacitor current is the textbook x' (scipy: {c['scaled_vs_textbook_y']:.1e})"},
        {"kind": "invariant", "terms": [{"signal": "Tank/E", "coeff": 1.0}, {"signal": "Split/W", "coeff": 1.0}],
         "tol": 1e-7, "scale": c["E_tank0"] + c["E_sup_cycle"],
         "note": "energy bookkeeping: the tank loses exactly what the diode absorbs, C v^2/2 + L i^2/2 + int v i_D dt = const"},
        {"kind": "cursor_value", "signal": "Meter/dw1", "t": c["t_end"], "value": c["E_sup_cycle"], "rtol": 1e-6,
         "note": "energy the diode supplies per cycle, while |v| < sqrt(a/b) (scipy)"},
        {"kind": "cursor_value", "signal": "Meter/dw2", "t": c["t_end"], "value": c["E_abs_cycle"], "rtol": 1e-6,
         "note": "energy it dissipates per cycle, at the outer part |v| > sqrt(a/b): the same, so the net is 0"},
    ]
    if full:
        checks.append({"kind": "cursor_value", "signal": "Meter/T_s", "t": c["t_end"], "value": 2 * math.pi * (1 + c["mu"] ** 2 / 16),
                       "rtol": 3e-3, "note": "the small-mu estimate 2 pi (1 + mu^2/16) holds to 0.19 % even at mu = 1"})
        checks.append({"kind": "min_ge", "signal": "Split/W_sup", "value": 0.0})
    return checks


def expected() -> dict:
    tb = DESIGN["textbook"]
    text_checks = [NO_DIAG]
    for name, _mu_name, mu in TEXT_MUS:
        r = tb[f"{mu:g}"]
        lc = r["cycle"]
        text_checks += [
            {"kind": "compare_signals", "signal": f"{name}/X/y", "signal_b": f"{name}/Eq/x", "max_abs": 1e-6,
             "note": f"mu = {mu:g}: the block diagram and the equation block agree"},
            {"kind": "compare_signals", "signal": f"{name}/Y/y", "signal_b": f"{name}/Eq/y",
             "max_abs": 1e-6 * max(1.0, lc["y_peak"])},
            {"kind": "period", "signal": f"{name}/X/y", "direction": "up", "n": r["n_last"], "value": lc["period"],
             "rtol": 1e-6, "note": f"mu = {mu:g}: the limit-cycle period {lc['period']:.8f} (scipy shooting)"},
            {"kind": "cursor_value", "signal": f"{name}/Meter/T_s", "t": DESIGN["tau_end"], "value": lc["period"],
             "rtol": 1e-7, "note": "the event-based cycle meter"},
            {"kind": "cursor_value", "signal": f"{name}/Meter/amp", "t": DESIGN["tau_end"], "value": lc["amplitude"],
             "rtol": 1e-7, "note": f"limit-cycle amplitude {lc['amplitude']:.7f} (averaging theory: 2)"},
            {"kind": "max_abs", "signal": f"{name}/X/y", "from_t": DESIGN["tau_end"] / 2, "value": lc["amplitude"],
             "abs": 1e-4, "note": "the sampled peak of x on the second half of the run"},
            {"kind": "cursor_value", "signal": f"{name}/X/y", "t": DESIGN["tau_end"], "value": r["x_end"], "abs": 1e-5,
             "note": "x at the end of the run (scipy from the same start)"},
        ]
        if mu <= 1.0:
            text_checks.append({"kind": "cursor_value", "signal": f"{name}/Meter/T_s", "t": DESIGN["tau_end"],
                                "value": r["T_small"], "rtol": max(2.0 * abs(r["err_small"]), 1e-7),
                                "note": f"small-mu theory 2 pi (1 + mu^2/16) = {r['T_small']:.6f}, "
                                        f"{r['err_small']:+.2e} relative"})
            text_checks.append({"kind": "cursor_value", "signal": f"{name}/Meter/amp", "t": DESIGN["tau_end"],
                                "value": 2.0, "rtol": max(2.0 * abs(lc['amplitude'] / 2 - 1), 1e-6),
                                "note": "averaging theory: amplitude 2"})
        else:
            text_checks.append({"kind": "cursor_value", "signal": f"{name}/Meter/T_s", "t": DESIGN["tau_end"],
                                "value": r["T_relax"], "rtol": 2.0 * abs(r["err_relax"]),
                                "note": f"relaxation theory (3 - 2 ln 2) mu + 7.014 mu^(-1/3) = {r['T_relax']:.4f}, "
                                        f"{r['err_relax']:+.2%} (the error falls with mu)"})
    b = BELT
    cu, st = b["cubic"], b["stribeck"]
    lcm = DESIGN["cycles"][f"{b['mu']:g}"]
    belt_checks = [
        {"kind": "scene_bindings"},
        NO_DIAG,
        {"kind": "compare_signals", "signal": "Xm/y", "signal_b": "Ref/x", "max_abs": 1e-6,
         "note": f"the block velocity x'/V is the textbook x (scipy: {cu['scaled_vs_textbook_x']:.1e})"},
        {"kind": "compare_signals", "signal": "Ym/y", "signal_b": "Ref/y", "max_abs": 1e-6,
         "note": f"and the scaled acceleration x''/(w0 V) is the textbook x' (scipy: {cu['scaled_vs_textbook_y']:.1e})"},
        {"kind": "period", "signal": "Vel/y", "direction": "up", "n": cu["n_last"], "value": cu["period"],
         "rtol": 1e-6, "note": f"cubic fit: {cu['period']:.6f} s = T(0.5)/w0 (scipy, the rig in SI units)"},
        {"kind": "cursor_value", "signal": "Meter/T_s", "t": b["t_end"], "value": lcm["period"], "rtol": 1e-7,
         "note": "scaled period = the textbook limit cycle at mu = 0.5"},
        {"kind": "cursor_value", "signal": "Meter/amp", "t": b["t_end"], "value": lcm["amplitude"], "rtol": 1e-7,
         "note": f"velocity amplitude {lcm['amplitude']:.6f} V = {b['xd_amp_cycle']:.6f} m/s"},
        {"kind": "period", "signal": "Stribeck/Vel/y", "direction": "up", "n": st["n_last"], "value": st["period"],
         "rtol": 1e-6, "note": f"full Stribeck curve: {st['period']:.6f} s ({st['period'] / cu['period'] - 1:+.3%} vs the cubic fit, scipy)"},
        {"kind": "cursor_value", "signal": "Stribeck/Meter/amp", "t": b["t_end"], "value": st["xd_amp"] / b["V"], "rtol": 1e-6,
         "note": f"full curve: velocity amplitude {st['xd_amp']:.6f} m/s ({st['xd_amp'] / cu['xd_amp'] - 1:+.2%} vs the cubic fit)"},
        {"kind": "min_ge", "signal": "Stribeck/Fric/w", "value": 0.9 * st["slip_min"],
         "note": f"the slip stays positive (scipy minimum {st['slip_min']:.5f} m/s): the block never sticks"},
        {"kind": "min_ge", "signal": "Fric/w", "value": 0.9 * cu["slip_min"]},
        {"kind": "invariant", "terms": [{"signal": "Store/E", "coeff": 1.0}, {"signal": "Split/W", "coeff": 1.0}],
         "tol": 1e-7, "scale": 0.5 * b["m"] * b["xd0"] ** 2 + b["E_sup_cycle"],
         "note": "oscillation energy m x'^2/2 + k (x - x_s)^2/2 changes by exactly the contact's work -int (F - F0) x' dt"},
        {"kind": "cursor_value", "signal": "Meter/dw1", "t": b["t_end"], "value": b["E_sup_cycle"], "rtol": 1e-6,
         "note": "energy the contact feeds the oscillation per cycle (small |x'|, the falling branch)"},
        {"kind": "cursor_value", "signal": "Meter/dw2", "t": b["t_end"], "value": b["E_abs_cycle"], "rtol": 1e-6,
         "note": "energy it takes back per cycle (large |x'|): equal, the net is 0"},
        {"kind": "max_abs", "signal": "Pos/y", "from_t": b["t_end"] / 2, "value": cu["x_max"], "rtol": 1e-6,
         "note": f"the block swings between {cu['x_min']:.5f} and {cu['x_max']:.5f} m"},
    ]
    models = {
        "vdp-tunnel-diode": {"checks": circuit_checks(CIRC, True)},
        "vdp-belt": {"checks": belt_checks},
        "vdp-textbook": {"checks": text_checks},
    }
    for k, c in DESIGN["circuit"].items():
        if k == DESIGN["circuit_default"]:
            continue
        models[f"vdp-tunnel-diode-mu{k.replace('.', 'p')}"] = {
            "model": "vdp-tunnel-diode", "overrides": [{"target": "global:mu", "value": c["mu"]}],
            "checks": circuit_checks(c, False) + [
                {"kind": "cursor_value", "signal": "L_nH/y", "t": 0.0, "value": c["L"] * 1e9, "rtol": 1e-9,
                 "note": f"the dashboard's mu = {c['mu']:g} gives L = {c['L'] * 1e9:.2f} nH"},
                {"kind": "cursor_value", "signal": "C_pF/y", "t": 0.0, "value": c["C"] * 1e12, "rtol": 1e-9,
                 "note": f"and C = {c['C'] * 1e12:.2f} pF"},
            ]}
    return {
        "project": "van-der-pol",
        "description": "The Van der Pol oscillator as a tunnel-diode LC oscillator, a belt-driven mass-spring and the "
                       "textbook equation. Numbers come from design/design.json, an independent scipy calculation.",
        "models": models,
    }


def main() -> None:
    for doc in (model_tunnel_diode(), model_belt(), model_textbook()):
        write(EXAMPLE / "models" / f"{doc['name']}.bgmodel.json", json.dumps(doc, indent=2) + "\n")
    write(EXAMPLE / "expected.json", json.dumps(expected(), indent=2) + "\n")
    write(EXAMPLE / SCENE_BELT, scene_belt())


if __name__ == "__main__":
    main()
