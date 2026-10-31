# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the three `maglev` models and the two scenes from `design/design.json`.

    uv run examples/maglev/design/design.py        # first: the design numbers
    uv run examples/maglev/design/build_model.py

Models (examples/maglev/models):

* ``maglev-current-driven``      the MathWorks reproduction: current input, gain-scheduled PID
                                 with trim feedforward, prefilter, the 0.15 -> 0.1875 m step;
                                 a ``Statics`` subsystem finds the trim current by integral action
* ``maglev-open-loop-and-linear`` three released plants (growth rate = unstable pole) and the
                                 nonlinear plant next to its frozen linear model in a small and a
                                 large closed-loop step
* ``maglev-bondgraph``           the energy-consistent bond graph: amplifier MSe, coil R and the
                                 stdlib ``converters/Electromagnet`` IC-field, ball I + gravity Se,
                                 cascade control, IR sensor with noise and ADC, dashboard
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))

P_GRID = [g["p"] for g in DESIGN["gains"]]
KP = [g["Kp"] for g in DESIGN["gains"]]
KI = [g["Ki"] for g in DESIGN["gains"]]
KD = [g["Kd"] for g in DESIGN["gains"]]
C_TRIM = DESIGN["plant"]["c_trim"]
H_START = DESIGN["scenario"]["h_start"]


def vec(values) -> str:
    return "[" + ", ".join(repr(float(v)) for v in values) + "]"


def num(v: float) -> str:
    return repr(float(v))


# --------------------------------------------------------------------------- document helpers


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[dict] = []
        self.annotations: list[dict] = []
        self.ports: list[dict] = []
        self._ids: dict[str, str] = {}
        self._c = 0

    def node(self, name: str, block, x: float, y: float, params=None, starts=None, constants=None,
             rotation: float = 0) -> str:
        nid = f"n{len(self.nodes) + 1:02d}"
        if isinstance(block, str):
            if block in ("0", "1"):
                b = {"junction": block}
            else:
                b = {"ref": block}
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
        """Node names are resolved in `doc()`, so a connection may name a later node."""
        self._c += 1
        self.connections.append((f"c{self._c:02d}", kind, a, pa, b, pb))

    def _resolved(self) -> list[dict]:
        out = []
        for cid, kind, a, pa, b, pb in self.connections:
            frm = {"node": self._ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self._ids[b]}
            if pb is not None:
                to["port"] = pb
            out.append({"id": cid, "kind": kind, "from": frm, "to": to})
        return out

    def sig(self, a, pa, b, pb):
        self._conn("signal", a, pa, b, pb)

    def bond(self, a, pa, b, pb):
        self._conn("bond", a, pa, b, pb)

    def wire(self, a, pa, b, pb):
        self._conn("wire", a, pa, b, pb)

    def note(self, text: str, x, y, w, h, color: str | None = None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def doc(self) -> dict:
        return {"nodes": self.nodes, "connections": self._resolved(), "annotations": self.annotations}


def model_doc(name: str, comment: str, diagram: Diagram, settings: dict, plots: list, scene: str | None,
              bindings: list, parameters: list, dashboard: dict | None = None) -> dict:
    doc = {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": comment,
        "diagram": diagram.doc(),
        "settings": settings,
        "plots": plots,
        "scene": {"file": scene} if scene else None,
        "bindings": bindings,
        "parameters": parameters,
    }
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc


def settings(t_end: float, points: int, reltol: float = 1e-9, abstol: float = 1e-12, solver: str = "auto") -> dict:
    return {"t_start": 0.0, "t_end": t_end, "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 10000}


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value, "unit": unit, "description": description}


PLANT_GLOBALS = [
    g("m_b", "0.02", "kg", "Ball mass (MathWorks maglev)"),
    g("g0", "9.81", "m/s^2", "Gravitational acceleration"),
    g("alpha", "2.4832e-5", "H*m", "Force constant: F = alpha*i^2/h^2 (N*m^2/A^2)"),
    g("c_trim", "sqrt(m_b*g0/alpha)", "A/m", "Trim law i_bar = c_trim*h_bar: alpha*i_bar^2/h_bar^2 = m_b*g0"),
]
SCENARIO_GLOBALS = [
    g("h_start", "0.15", "m", "Gap at the start (levitating at rest)"),
    g("h_step", "0.1875", "m", "Setpoint after the step (+25 %)"),
    g("t_step", "0.2", "s", "Time of the setpoint step"),
    g("tau_pre", "0.1", "s", "Reference prefilter 1/(tau_pre*s + 1), the reference's 10/(s + 10)"),
    g("Tf", "0.001", "s", "Derivative filter time constant of the PID"),
]


def gain_tables(d: Diagram, x: float, y: float, h_source: tuple[str, str], prefix: str = "",
                gains: list | None = None) -> None:
    """Three Lookup1D blocks: the PID gains designed at 0.05/0.15/0.25 m over the measured gap
    (the current-driven design, or `gains`, e.g. the cascade's)."""
    if gains is None:
        kp, ki, kd = KP, KI, KD
    else:
        kp, ki, kd = ([gg[k] for gg in gains] for k in ("Kp", "Ki", "Kd"))
    for k, (name, table) in enumerate((("KpTab", kp), ("KiTab", ki), ("KdTab", kd))):
        d.node(prefix + name, "stdlib:continuous/Lookup1D", x, y + 100 * k,
               params={"x": vec(P_GRID), "table": vec(table)})
        d.sig(h_source[0], h_source[1], prefix + name, "u")


SOLVER_OPEN = "auto"
SCENE_CURRENT = "scenes/maglev.sdf"
SCENE_OPEN = "scenes/maglev-open-loop.sdf"


# --------------------------------------------------------------------------- model 1


def model_current_driven() -> dict:
    d = Diagram()
    d.node("Ref", "stdlib:sources/Step", 40, 60,
           params={"t_step": "t_step", "initial": "h_start", "final": "h_step"})
    d.node("Pre", "stdlib:continuous/FirstOrder", 240, 60, params={"k": "1.0", "tau": "tau_pre"},
           starts={"x": "h_start"})
    d.node("Ideal", "stdlib:continuous/TransferFunction", 440, -60,
           params={"num": "[0.0, 0.0, 900.0]", "den": "[1.0, 42.0, 900.0]"},
           starts={"x": vec([0.0, H_START / 900.0])})
    d.node("Trim", "stdlib:continuous/Gain", 440, 120, params={"k": "c_trim"})
    gain_tables(d, 440, 240, ("Ball", "h"))
    d.node("PID", "project:ScheduledPID", 680, 160, params={"Tf": "Tf"})
    d.node("Ball", "project:MaglevBall", 920, 160,
           params={"m": "m_b", "g": "g0", "alpha": "alpha"}, starts={"x": "h_start", "w": "0.0"})
    d.sig("Ref", "y", "Pre", "u")
    d.sig("Pre", "y", "Ideal", "u")
    d.sig("Pre", "y", "PID", "r")
    d.sig("Ball", "h", "PID", "y")
    d.sig("Ball", "h", "Trim", "u")
    d.sig("Trim", "y", "PID", "ff")
    d.sig("KpTab", "y", "PID", "Kp")
    d.sig("KiTab", "y", "PID", "Ki")
    d.sig("KdTab", "y", "PID", "Kd")
    d.sig("PID", "u", "Ball", "i")

    # Statics: three loops without feedforward hold the ball at 0.05, 0.15 and 0.25 m; their
    # integrators start 2 % short of the trim current and must find it.
    s = Diagram()
    s.node("Zero", "stdlib:sources/Constant", 40, 420, params={"value": "0.0"})
    for col, p in enumerate(P_GRID):
        tag = f"{int(round(p * 100)):02d}"
        x = 40 + 360 * col
        gp = DESIGN["gains"][col]
        s.node(f"R{tag}", "stdlib:sources/Constant", x, 40, params={"value": num(p)})
        s.node(f"Kp{tag}", "stdlib:sources/Constant", x, 120, params={"value": num(gp["Kp"])})
        s.node(f"Ki{tag}", "stdlib:sources/Constant", x, 200, params={"value": num(gp["Ki"])})
        s.node(f"Kd{tag}", "stdlib:sources/Constant", x, 280, params={"value": num(gp["Kd"])})
        s.node(f"PID{tag}", "project:ScheduledPID", x + 170, 120, params={"Tf": "Tf"},
               starts={"xi": f"0.98*c_trim*{num(p)}"})
        s.node(f"Ball{tag}", "project:MaglevBall", x + 170, 300,
               params={"m": "m_b", "g": "g0", "alpha": "alpha"}, starts={"x": num(p), "w": "0.0"})
        s.sig(f"R{tag}", "y", f"PID{tag}", "r")
        s.sig(f"Ball{tag}", "h", f"PID{tag}", "y")
        s.sig("Zero", "y", f"PID{tag}", "ff")
        s.sig(f"Kp{tag}", "y", f"PID{tag}", "Kp")
        s.sig(f"Ki{tag}", "y", f"PID{tag}", "Ki")
        s.sig(f"Kd{tag}", "y", f"PID{tag}", "Kd")
        s.sig(f"PID{tag}", "u", f"Ball{tag}", "i")
    s.note("**Statics.** No feedforward: each integrator starts 2 % below the trim current and "
           "finds the current that carries the ball, i = sqrt(m_b*g0/alpha)*h. The checks compare "
           "PID05/u, PID15/u and PID25/u at 1.4 s with 4.444, 13.333 and 22.222 A.",
           40, 500, 1000, 70, "green")
    d.node("Statics", {"subsystem": {"ports": [], "diagram": s.doc()}}, 920, 420)

    d.note("**Maglev, current-driven (MathWorks reproduction).** m*h'' = m*g - alpha*i^2/h^2 with "
           "the current as the input. The PID gains are designed at h = 0.05, 0.15 and 0.25 m "
           "(crossover 50 rad/s, phase margin 60 deg, Tf = 1 ms) and interpolated over the measured "
           "gap (KpTab, KiTab, KdTab). Trim feedforward c_trim*h, prefilter 10/(s + 10) on the "
           "0.15 -> 0.1875 m step at 0.2 s. Ideal is the reference behaviour 900/(s^2 + 42 s + 900) "
           "of the prefiltered setpoint, for comparison only.", 40, 580, 1100, 90)

    plots = [
        {"id": "p1", "title": "Gap h and setpoint", "signals": ["Ball/h", "Pre/y", "Ref/y", "Ideal/y"]},
        {"id": "p2", "title": "Coil current and trim current", "signals": ["PID/u", "Trim/y"]},
        {"id": "p3", "title": "Scheduled proportional gain", "signals": ["KpTab/y"]},
        {"id": "p4", "title": "Control error", "signals": ["PID/e"]},
        {"id": "p5", "title": "Statics: currents found by integral action",
         "signals": ["Statics/PID05/u", "Statics/PID15/u", "Statics/PID25/u"]},
    ]
    bindings = [
        {"target": "joint:gap", "property": "position", "signal": "Ball/h"},
        {"target": "joint:setpoint", "property": "position", "signal": "Ref/y"},
        {"target": "visual:coil_winding", "property": "color", "signal": "PID/u", "colormap": "heat",
         "range": [0.0, 30.0]},
    ]
    return model_doc(
        "maglev-current-driven",
        "Magnetic levitation after the MathWorks 'Maglev LPV model' examples: a 20 g steel ball below "
        "a coil, the current is the input. Gain-scheduled PID (designed at 0.05/0.15/0.25 m, "
        "interpolated over the measured gap) plus trim feedforward and a 10/(s+10) prefilter; "
        "0.15 -> 0.1875 m step at 0.2 s, 1.4 s.",
        d, settings(1.4, 2801), plots, SCENE_CURRENT, bindings, PLANT_GLOBALS + SCENARIO_GLOBALS)


# --------------------------------------------------------------------------- model 2


def model_open_loop() -> dict:
    d = Diagram()
    dh0 = DESIGN["model2"]["dh0"]
    # A: three released plants with the trim current of their gap.
    for col, p in enumerate(P_GRID):
        tag = f"{int(round(p * 100)):02d}"
        x = 40 + 300 * col
        d.node(f"I{tag}", "stdlib:continuous/Gain", x, 40, params={"k": "c_trim"})
        d.node(f"P{tag}", "stdlib:sources/Constant", x - 10, -60, params={"value": num(p)})
        d.node(f"Ball{tag}", "project:MaglevBall", x + 150, 40,
               params={"m": "m_b", "g": "g0", "alpha": "alpha"},
               starts={"x": f"{num(p)} + dh0", "w": "0.0"})
        d.node(f"Grow{tag}", "project:GrowthRate", x + 150, 180, params={"p": num(p)})
        d.sig(f"P{tag}", "y", f"I{tag}", "u")
        d.sig(f"I{tag}", "y", f"Ball{tag}", "i")
        d.sig(f"Ball{tag}", "h", f"Grow{tag}", "h")
        d.sig(f"Ball{tag}", "v", f"Grow{tag}", "v")
    d.note("**Open loop.** Each ball gets the trim current of its gap and starts dh0 = 10 nm below "
           "it, at rest. The deviation grows as dh0*cosh(s*t); Grow*/lambda = v/(h - p) tends to the "
           "unstable pole s = sqrt(2*g/p): 19.81, 11.44 and 8.86 1/s.", 960, -40, 420, 120, "green")

    # Frozen gains of the 0.15 m design (no scheduling: the comparison isolates the plant).
    g15 = DESIGN["gains"][1]
    d.node("Kp", "stdlib:sources/Constant", 40, 320, params={"value": num(g15["Kp"])})
    d.node("Ki", "stdlib:sources/Constant", 40, 400, params={"value": num(g15["Ki"])})
    d.node("Kd", "stdlib:sources/Constant", 40, 480, params={"value": num(g15["Kd"])})
    for row, (tag, h1) in enumerate((("S", DESIGN["model2"]["small"]["h1"]), ("L", DESIGN["model2"]["large"]["h1"]))):
        y = 600 + 420 * row
        d.node(f"Ref{tag}", "stdlib:sources/Step", 40, y,
               params={"t_step": "t_step", "initial": "h_start", "final": num(h1)})
        d.node(f"Pre{tag}", "stdlib:continuous/FirstOrder", 220, y, params={"k": "1.0", "tau": "tau_pre"},
               starts={"x": "h_start"})
        # nonlinear loop
        d.node(f"Trim{tag}", "stdlib:continuous/Gain", 400, y - 80, params={"k": "c_trim"})
        d.node(f"PID{tag}", "project:ScheduledPID", 600, y, params={"Tf": "Tf"})
        d.node(f"Ball{tag}", "project:MaglevBall", 820, y,
               params={"m": "m_b", "g": "g0", "alpha": "alpha"}, starts={"x": "h_start", "w": "0.0"})
        # frozen linear loop: dh'' = a0*dh - b0*di around (0.15 m, 13.33 A)
        d.node(f"TrimLin{tag}", "stdlib:continuous/Gain", 400, y + 180, params={"k": "c_trim"})
        d.node(f"PIDLin{tag}", "project:ScheduledPID", 600, y + 220, params={"Tf": "Tf"})
        d.node(f"Lin{tag}", "project:LinearBall", 820, y + 220,
               params={"p": "h_start", "m": "m_b", "g": "g0", "alpha": "alpha"},
               starts={"dh": "0.0", "dv": "0.0"})
        d.node(f"Diff{tag}", "project:Diff2", 1180, y + 60)
        for pid, meas, trim in ((f"PID{tag}", (f"Ball{tag}", "h"), f"Trim{tag}"),
                                (f"PIDLin{tag}", (f"Lin{tag}", "h"), f"TrimLin{tag}")):
            d.sig(f"Pre{tag}", "y", pid, "r")
            d.sig(meas[0], meas[1], pid, "y")
            d.sig(meas[0], meas[1], trim, "u")
            d.sig(trim, "y", pid, "ff")
            d.sig("Kp", "y", pid, "Kp")
            d.sig("Ki", "y", pid, "Ki")
            d.sig("Kd", "y", pid, "Kd")
        d.sig(f"Ref{tag}", "y", f"Pre{tag}", "u")
        d.sig(f"PID{tag}", "u", f"Ball{tag}", "i")
        d.sig(f"PIDLin{tag}", "u", f"Lin{tag}", "i")
        d.sig(f"Ball{tag}", "h", f"Diff{tag}", "u1")
        d.sig(f"Lin{tag}", "h", f"Diff{tag}", "u2")
    d.note("**Small step (0.15 -> 0.155 m).** The same frozen PID (0.15 m gains) and trim feedforward "
           "around the nonlinear ball (BallS) and around its linearisation at 0.15 m (LinS: "
           "A = [0 1; 2g/p 0], B = [0; -2 sqrt(g alpha/m)/p], C = [1 0] at p = 0.15 m, taking the "
           "absolute current and returning the absolute gap). DiffS = BallS/h - LinS/h stays below 0.5 % of the step.",
           1380, 600, 420, 150, "blue")
    d.note("**Large step (0.15 -> 0.21 m).** The controller now asks for a negative current; the "
           "real force alpha*i^2/h^2 still pulls (it does not care about the sign), the linear model "
           "pushes. The real ball can at best fall freely, so it lags the linear one: DiffL reaches "
           "18 % of the step.",
           1380, 1020, 420, 130, "pink")

    plots = [
        {"id": "p1", "title": "Open loop: gaps of the released balls", "signals": ["Ball05/h", "Ball15/h", "Ball25/h"]},
        {"id": "p2", "title": "Open loop: growth rate v/(h - p) [1/s]", "signals": ["Grow05/lambda", "Grow15/lambda", "Grow25/lambda"]},
        {"id": "p3", "title": "Small step: nonlinear vs frozen linear", "signals": ["BallS/h", "LinS/h", "PreS/y"]},
        {"id": "p4", "title": "Large step: nonlinear vs frozen linear", "signals": ["BallL/h", "LinL/h", "PreL/y"]},
        {"id": "p5", "title": "Gap difference nonlinear - linear", "signals": ["DiffS/y", "DiffL/y"]},
        {"id": "p6", "title": "Coil currents, large step", "signals": ["PIDL/u", "PIDLinL/u"]},
    ]
    bindings = []
    for p in P_GRID:
        tag = f"{int(round(p * 100)):02d}"
        bindings.append({"target": f"joint:gap{tag}", "property": "position", "signal": f"Ball{tag}/h"})
    return model_doc(
        "maglev-open-loop-and-linear",
        "Why the maglev needs control and what its LPV model means: three nonlinear balls released "
        "10 nm below their trim gaps 0.05/0.15/0.25 m (growth rate -> sqrt(2g/p)), and the nonlinear "
        "plant next to its frozen linear model at 0.15 m under the same closed loop, for a small "
        "(+5 mm) and a large (+60 mm) step.",
        d, settings(1.5, 3001, reltol=1e-10, abstol=1e-14, solver=SOLVER_OPEN), plots, SCENE_OPEN, bindings,
        PLANT_GLOBALS + [
            g("h_start", "0.15", "m", "Gap of the closed loops at the start"),
            g("t_step", "0.2", "s", "Time of the setpoint steps"),
            g("tau_pre", "0.1", "s", "Reference prefilter time constant"),
            g("Tf", "0.001", "s", "Derivative filter time constant"),
            g("dh0", num(dh0), "m", "Release offset of the open-loop balls below their trim gap"),
        ])


# --------------------------------------------------------------------------- model 3


def model_bondgraph() -> dict:
    m3 = DESIGN["model3"]
    sens = m3["sensor"]
    d = Diagram()
    # Electrical bond graph: amplifier (Sat + MSe), coil 1-junction, R, current detector,
    # power tap, electromagnet coil port.
    d.node("Ipi", "project:CurrentPI", 860, 40, params={"Kp": "Kp_i", "Ti": "Ti_i", "v_max": "V_max"},
           starts={"x": "R_coil*i_start/Kp_i"})
    d.node("Sat", "stdlib:continuous/Saturation", 1060, 40, params={"lower": "-V_max", "upper": "V_max"})
    d.node("Amp", "stdlib:bondgraph/MSe", 1240, 40, params={"gain": "1.0"})
    d.node("Jc", "1", 1240, 200)
    d.node("Rc", "stdlib:bondgraph/R", 1080, 200, params={"r": "R_coil"})
    d.node("Imeas", "stdlib:bondgraph/Df", 1440, 160)
    d.node("Jv", "0", 1240, 330)
    d.node("Vcoil", "stdlib:bondgraph/De", 1440, 330)
    d.node("Pel", "stdlib:continuous/Product", 1600, 250)
    d.node("EM", "stdlib:converters/Electromagnet", 1240, 470,
           params={"alpha": "alpha", "L_inf": "L_inf", "h0": "0.0"},
           starts={"i": "i_start", "h": "h_start"})
    d.node("Gnd", "stdlib:electrical/Ground", 1440, 420)
    d.node("Frame", "stdlib:translation/Fixed", 1440, 540)
    # Mechanical bond graph: ball 1-junction with gravity, mass, power tap, position sensor.
    d.node("Jf", "0", 1240, 620)
    d.node("Fmag", "stdlib:bondgraph/De", 1440, 620)
    d.node("Vball", "stdlib:bondgraph/Df", 1440, 860)
    d.node("Pmech", "stdlib:continuous/Product", 1600, 700)
    d.node("Jb", "1", 1240, 760)
    d.node("Grav", "stdlib:bondgraph/Se", 1440, 760, params={"e": "m_b*g0"})
    d.node("Ball", "stdlib:bondgraph/I", 1080, 760, params={"i": "m_b"})
    d.node("BallPos", "stdlib:converters/PositionSensor", 1240, 900, starts={"x": "h_start"})
    d.bond("Amp", "p", "Jc", None)
    d.bond("Jc", None, "Rc", "p")
    d.bond("Jc", None, "Imeas", "p")
    d.bond("Jc", None, "Jv", None)
    d.bond("Jv", None, "Vcoil", "p")
    d.bond("Jv", None, "EM", "p")
    d.wire("EM", "n", "Gnd", "p")
    d.wire("EM", "a", "Frame", "a")
    d.bond("Grav", "p", "Jb", None)
    d.bond("Jb", None, "Ball", "p")
    d.bond("Jb", None, "Jf", None)
    d.bond("Jf", None, "Fmag", "p")
    d.bond("Jf", None, "EM", "b")
    d.bond("Jb", None, "Vball", "p")
    d.bond("Jb", None, "BallPos", "a")
    d.sig("Ipi", "v", "Sat", "u")
    d.sig("Sat", "y", "Amp", "u")
    d.sig("Imeas", "y", "Ipi", "i")

    # IR sensor: zero at the start gap, gain, seeded noise, 16-bit ADC at 1 kHz, back to metres.
    # The sensor reads the deviation from h_start (its calibrated zero), so the ADC's held
    # output 0 before its first tick (t = 1 ms) already stands for the true start gap.
    s = Diagram()
    s.node("Zero", "project:Bias", 40, 40, params={"b": "-h_start"})
    s.node("Gain", "stdlib:continuous/Gain", 200, 40, params={"k": "k_s"})
    s.node("Noise", "stdlib:sources/Noise", 200, 160, params={"mean": "0.0", "std": num(sens["noise_std"]), "seed": "7"},
           constants={"sample_time": num(sens["t_sample"])})
    s.node("Add", "project:Add2", 380, 80)
    s.node("ADC", "stdlib:motion/ADC", 540, 80,
           params={"bits": str(sens["adc_bits"]), "u_min": num(sens["adc_range"][0]), "u_max": num(sens["adc_range"][1])},
           constants={"sample_period": num(sens["t_sample"])})
    s.node("Scale", "stdlib:continuous/Gain", 700, 80, params={"k": "1.0/k_s"})
    s.node("Back", "project:Bias", 860, 80, params={"b": "h_start"})
    s.sig("Zero", "y", "Gain", "u")
    s.sig("Gain", "y", "Add", "u1")
    s.sig("Noise", "y", "Add", "u2")
    s.sig("Add", "y", "ADC", "u")
    s.sig("ADC", "y", "Scale", "u")
    s.sig("Scale", "y", "Back", "u")
    s.ports = [
        {"name": "x", "kind": "signal", "direction": "input", "type": "Real", "size": [1], "unit": None,
         "node": s._ids["Zero"], "port": "u"},
        {"name": "y", "kind": "signal", "direction": "output", "type": "Real", "size": [1], "unit": None,
         "node": s._ids["Back"], "port": "y"},
    ]
    s.note("**IR sensor.** Zero at h_start, 30 V/m, white noise 0.3 mV rms (10 um) drawn every 1 ms from "
           "seed 7, 16-bit ADC over -5..5 V (lsb 5.1 um of gap), scaled back to metres.", 40, 260, 900, 60, "green")
    d.node("IR", {"subsystem": {"ports": s.ports, "diagram": s.doc()}}, 820, 960)
    d.sig("BallPos", "y", "IR", "x")

    # Outer loop: setpoint, prefilter, scheduled PID with trim feedforward -> current setpoint.
    d.node("Ref", "stdlib:sources/Step", 40, 40, params={"t_step": "t_step", "initial": "h_start", "final": "h_step"})
    d.node("Pre", "stdlib:continuous/FirstOrder", 220, 40, params={"k": "1.0", "tau": "tau_pre"},
           starts={"x": "h_start"})
    d.node("Trim", "stdlib:continuous/Gain", 420, 160, params={"k": "c_trim"})
    gain_tables(d, 420, 280, ("IR", "y"), gains=m3["gains"])
    d.node("PID", "project:ScheduledPID", 640, 40, params={"Tf": "Tf"})
    d.sig("Ref", "y", "Pre", "u")
    d.sig("Pre", "y", "PID", "r")
    d.sig("IR", "y", "PID", "y")
    d.sig("IR", "y", "Trim", "u")
    d.sig("Trim", "y", "PID", "ff")
    d.sig("KpTab", "y", "PID", "Kp")
    d.sig("KiTab", "y", "PID", "Ki")
    d.sig("KdTab", "y", "PID", "Kd")
    d.sig("PID", "u", "Ipi", "i_ref")

    # Energy bookkeeping of the field: integrated port powers.
    d.node("Eel", "stdlib:continuous/Integrator", 1780, 240)
    d.node("Emech", "stdlib:continuous/Integrator", 1780, 700)
    d.sig("Vcoil", "y", "Pel", "u1")
    d.sig("Imeas", "y", "Pel", "u2")
    d.sig("Pel", "y", "Eel", "u")
    d.sig("Fmag", "y", "Pmech", "u1")
    d.sig("Vball", "y", "Pmech", "u2")
    d.sig("Pmech", "y", "Emech", "u")

    d.note("**Maglev as a bond graph.** Electrical 1-junction Jc (coil current): amplifier MSe Amp "
           "(+-60 V rail in Sat), coil resistance Rc, current detector Imeas and the coil port of EM. "
           "EM is the two-port IC-field electromagnet: co-energy W' = L(h)*i^2/2 with "
           "L(h) = L_inf + 2*alpha/h, so its gap port carries F = alpha*i^2/h^2. Mechanical "
           "1-junction Jb (ball velocity, down positive): gravity Se Grav, ball mass I Ball, the "
           "armature port of EM and the position sensor. The detectors give the field's port powers: coil voltage Vcoil (De on the 0-junction Jv) times Imeas, attraction Fmag (De on Jf) times ball velocity Vball; "
           "EM/W - Eel/y - Emech/y stays at W(0).", 40, 1100, 1100, 110)
    d.note("**Cascade.** Outer: gain-scheduled PID on the IR measurement plus trim feedforward "
           "c_trim*h -> current setpoint; its gains are designed with the 1 kHz sample-and-hold, the inner "
           "loop and a 5 ms derivative filter in the phase budget. Inner: PI (Kp = L*1000 rad/s, Ti = L/R) -> voltage command.",
           40, 560, 640, 80, "blue")

    plots = [
        {"id": "p1", "title": "Gap h, measurement and setpoint", "signals": ["BallPos/y", "IR/Back/y", "Pre/y", "Ref/y"]},
        {"id": "p2", "title": "Coil current and its setpoint", "signals": ["EM/i", "PID/u", "Trim/y"]},
        {"id": "p3", "title": "Amplifier voltage (rail +-60 V)", "signals": ["Sat/y", "Ipi/v"]},
        {"id": "p4", "title": "Field energy terms [J]", "signals": ["EM/W", "Eel/y", "Emech/y"]},
        {"id": "p5", "title": "Field port powers [W]", "signals": ["Pel/y", "Pmech/y"]},
        {"id": "p6", "title": "Magnetic force and weight", "signals": ["EM/F", "Grav/p.e"]},
    ]
    bindings = [
        {"target": "joint:gap", "property": "position", "signal": "BallPos/y"},
        {"target": "joint:setpoint", "property": "position", "signal": "Ref/y"},
        {"target": "visual:coil_winding", "property": "color", "signal": "EM/i", "colormap": "heat",
         "range": [0.0, 30.0]},
    ]
    dashboard = {
        "autoRerun": True,
        "cards": [
            {"id": "d1", "kind": "text", "size": "2x1", "title": "Maglev",
             "options": {"markdown": True, "text": "Move the **setpoint** and the model runs again: the ball steps from 0.15 m to the new gap at 0.2 s. Keep it between 0.08 and 0.22 m; outside the LPV design range the gains are clamped at the end points."}},
            {"id": "d2", "kind": "slider", "size": "2x1", "title": "Setpoint after the step",
             "parameter": "global:h_step", "options": {"min": 0.08, "max": 0.22, "step": 0.0025, "decimals": 4, "unit": "m"}},
            {"id": "d3", "kind": "gauge", "size": "1x1", "title": "Gap h", "signals": ["BallPos/y"],
             "options": {"min": 0.0, "max": 0.3, "decimals": 4, "unit": "m",
                         "zones": [{"from": 0.0, "to": 0.05, "tone": "bad"}, {"from": 0.05, "to": 0.25, "tone": "good"},
                                   {"from": 0.25, "to": 0.3, "tone": "warn"}]}},
            {"id": "d4", "kind": "gauge", "size": "1x1", "title": "Coil current", "signals": ["EM/i"],
             "options": {"min": 0.0, "max": 30.0, "decimals": 2, "unit": "A",
                         "zones": [{"from": 0.0, "to": 25.0, "tone": "good"}, {"from": 25.0, "to": 30.0, "tone": "warn"}]}},
            {"id": "d5", "kind": "bar", "size": "1x1", "title": "Amplifier voltage", "signals": ["Sat/y"],
             "options": {"min": -60.0, "max": 60.0, "decimals": 1, "unit": "V", "orientation": "horizontal",
                         "zones": [{"from": -60.0, "to": -55.0, "tone": "warn"}, {"from": -55.0, "to": 55.0, "tone": "good"},
                                   {"from": 55.0, "to": 60.0, "tone": "warn"}]}},
            {"id": "d6", "kind": "value", "size": "1x1", "title": "Magnetic energy", "signals": ["EM/W"],
             "options": {"decimals": 3, "unit": "J", "sparkline": True}},
            {"id": "d7", "kind": "plot", "size": "4x2", "title": "Gap and setpoint", "signals": ["BallPos/y", "Pre/y", "Ref/y"]},
        ],
    }
    return model_doc(
        "maglev-bondgraph",
        "The maglev as an energy-consistent bond graph: amplifier MSe (+-60 V), coil R and the "
        "stdlib Electromagnet (two-port IC-field, L(h) = L_inf + 2 alpha/h, F = alpha i^2/h^2), "
        "ball I with gravity Se. Cascade: gain-scheduled position PID with trim feedforward -> "
        "current setpoint, PI current loop -> voltage. IR sensor with seeded noise and a 16-bit ADC.",
        d, settings(1.4, 2801, reltol=1e-9, abstol=1e-12), plots, SCENE_CURRENT, bindings,
        PLANT_GLOBALS + [gl for gl in SCENARIO_GLOBALS if gl["name"] != "Tf"] + [
            g("Tf", num(m3["Tf"]), "s", "Derivative filter of the PID: 5 ms for the sampled, noisy IR signal"),
            g("L_inf", num(m3["L_inf"]), "H", "Coil inductance at an infinite gap (assumed)"),
            g("R_coil", num(m3["R"]), "Ohm", "Coil resistance (assumed)"),
            g("V_max", num(m3["V_max"]), "V", "Amplifier rail"),
            g("w_i", num(m3["w_i"]), "rad/s", "Current-loop bandwidth"),
            g("L0", "L_inf + 2*alpha/h_start", "H", "Coil inductance at the start gap"),
            g("Kp_i", "L0*w_i", "V/A", "Current PI gain: the loop crosses over at w_i"),
            g("Ti_i", "L0/R_coil", "s", "Current PI integral time: the PI zero cancels the coil pole"),
            g("i_start", "c_trim*h_start", "A", "Trim current at the start gap"),
            g("k_s", num(sens["k_s"]), "V/m", "IR sensor gain"),
        ],
        dashboard,
    )


# --------------------------------------------------------------------------- scenes

BALL_R = 0.0125      # m, the ball's drawn radius (a 25 mm hollow steel ball of 20 g)
H_MAX = 0.30         # m, gap at the pedestal (MaglevBall h_max)
BASE_T = 0.02
PED_TOP = 0.075
Z_FACE = PED_TOP + 2 * BALL_R + H_MAX     # the magnet face, so the ball rests on the pedestal at h = h_max


def _vis(name, pose, geom, rgba):
    return (f'      <visual name="{name}">\n        <pose>{pose}</pose>\n'
            f'        <geometry>{geom}</geometry>\n'
            f'        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def _box(sx, sy, sz):
    return f"<box><size>{sx:.4f} {sy:.4f} {sz:.4f}</size></box>"


def _cyl(r, length):
    return f"<cylinder><radius>{r:.4f}</radius><length>{length:.4f}</length></cylinder>"


def _sphere(r):
    return f"<sphere><radius>{r:.4f}</radius></sphere>"


def rig(prefix: str, x0: float, with_sensor: bool, with_setpoint: bool, column: bool = True) -> tuple[str, str]:
    """Links and joints of one rig at x = x0 (the ball axis). Returns (links, joints)."""
    P = prefix
    L = []
    # Frame: column, arm, pedestal
    v = ""
    if column:
        cx = x0 - 0.17
        top = Z_FACE + 0.17
        v += _vis(f"{P}column", f"{cx:.4f} 0 {BASE_T + (top - BASE_T) / 2:.4f} 0 0 0", _box(0.04, 0.04, top - BASE_T), "0.72 0.74 0.78 1")
        v += _vis(f"{P}column_foot", f"{cx:.4f} 0 {BASE_T + 0.01:.4f} 0 0 0", _box(0.09, 0.09, 0.02), "0.30 0.32 0.36 1")
        v += _vis(f"{P}arm", f"{(cx + x0) / 2 - 0.01:.4f} 0 {Z_FACE + 0.15:.4f} 0 0 0", _box(x0 - cx + 0.06, 0.04, 0.03), "0.72 0.74 0.78 1")
    v += _vis(f"{P}pedestal", f"{x0:.4f} 0 {BASE_T + (PED_TOP - BASE_T) / 2:.4f} 0 0 0", _cyl(0.012, PED_TOP - BASE_T), "0.55 0.57 0.6 1")
    v += _vis(f"{P}pedestal_pad", f"{x0:.4f} 0 {PED_TOP - 0.003:.4f} 0 0 0", _cyl(0.02, 0.006), "0.12 0.12 0.13 1")
    # Electromagnet: iron core, pole face, flanges, copper body (bound) and winding ribs
    core_len = 0.13
    v += _vis(f"{P}core", f"{x0:.4f} 0 {Z_FACE + core_len / 2:.4f} 0 0 0", _cyl(0.022, core_len), "0.38 0.39 0.42 1")
    v += _vis(f"{P}pole_face", f"{x0:.4f} 0 {Z_FACE + 0.002:.4f} 0 0 0", _cyl(0.024, 0.004), "0.62 0.64 0.68 1")
    v += _vis(f"{P}flange_low", f"{x0:.4f} 0 {Z_FACE + 0.011:.4f} 0 0 0", _cyl(0.056, 0.006), "0.22 0.23 0.26 1")
    v += _vis(f"{P}flange_high", f"{x0:.4f} 0 {Z_FACE + 0.119:.4f} 0 0 0", _cyl(0.056, 0.006), "0.22 0.23 0.26 1")
    v += _vis(f"{P}coil_winding", f"{x0:.4f} 0 {Z_FACE + 0.065:.4f} 0 0 0", _cyl(0.047, 0.102), "0.78 0.45 0.2 1")
    n_ribs = 12
    for k in range(n_ribs):
        z = Z_FACE + 0.018 + k * (0.094 / (n_ribs - 1))
        v += _vis(f"{P}winding_rib{k + 1:02d}", f"{x0:.4f} 0 {z:.4f} 0 0 0", _cyl(0.0485, 0.0025), "0.55 0.3 0.12 1")
    v += _vis(f"{P}terminal_a", f"{x0 + 0.03:.4f} 0.045 {Z_FACE + 0.128:.4f} 0 0 0", _cyl(0.004, 0.016), "0.85 0.2 0.15 1")
    v += _vis(f"{P}terminal_b", f"{x0 - 0.03:.4f} 0.045 {Z_FACE + 0.128:.4f} 0 0 0", _cyl(0.004, 0.016), "0.15 0.15 0.18 1")
    if with_sensor:
        # IR light curtain: emitter and receiver heads on both sides, a faint sheet between them
        # over the measured range (gap 0.03 .. 0.27 m, ball centres).
        z_lo = Z_FACE - BALL_R - 0.27
        z_hi = Z_FACE - BALL_R - 0.03
        zc = (z_lo + z_hi) / 2
        hgt = z_hi - z_lo
        v += _vis(f"{P}ir_receiver", f"{x0 + 0.07:.4f} 0 {zc:.4f} 0 0 0", _box(0.018, 0.03, hgt + 0.02), "0.10 0.11 0.14 1")
        v += _vis(f"{P}ir_receiver_window", f"{x0 + 0.0605:.4f} 0 {zc:.4f} 0 0 0", _box(0.002, 0.016, hgt), "0.55 0.08 0.1 1")
        v += _vis(f"{P}ir_emitter", f"{x0 - 0.07:.4f} 0 {zc:.4f} 0 0 0", _box(0.018, 0.03, hgt + 0.02), "0.10 0.11 0.14 1")
        v += _vis(f"{P}ir_emitter_window", f"{x0 - 0.0605:.4f} 0 {zc:.4f} 0 0 0", _box(0.002, 0.016, hgt), "0.95 0.25 0.2 1")
        v += _vis(f"{P}ir_beam", f"{x0:.4f} 0 {zc:.4f} 0 0 0", _box(0.119, 0.003, hgt), "1.0 0.2 0.15 0.12")
        v += _vis(f"{P}ir_bracket", f"{x0:.4f} -0.03 {z_hi + 0.016:.4f} 0 0 0", _box(0.16, 0.012, 0.012), "0.30 0.32 0.36 1")
    L.append(f'    <link name="{P}rig">\n      <pose>0 0 0 0 0 0</pose>\n{v}    </link>\n')
    # The ball: link at h = 0 (ball top at the magnet face), the prismatic joint moves it down by h.
    ball = _vis(f"{P}ball_sphere", "0 0 0 0 0 0", _sphere(BALL_R), "0.80 0.83 0.88 1")
    ball += _vis(f"{P}ball_glint", f"{-0.004:.4f} {-0.004:.4f} {0.005:.4f} 0 0 0", _sphere(0.0035), "1 1 1 1")
    L.append(f'    <link name="{P}ball">\n      <pose>{x0:.4f} 0 {Z_FACE - BALL_R:.4f} 0 0 0</pose>\n{ball}    </link>\n')
    J = [f'    <joint name="{P}gap" type="prismatic">\n      <parent>{P}rig</parent>\n      <child>{P}ball</child>\n'
         f'      <axis><xyz>0 0 -1</xyz></axis>\n    </joint>\n']
    if with_setpoint:
        sp = _vis(f"{P}setpoint_disc", "0 0 0 0 0 0", _cyl(0.034, 0.0015), "0.15 0.85 0.45 0.28")
        sp += _vis(f"{P}setpoint_line", "0 0 0 0 0 0", _box(0.15, 0.0025, 0.0025), "0.1 0.9 0.45 1")
        sp += _vis(f"{P}setpoint_tick_l", "-0.078 0 0 0 0 0", _box(0.006, 0.006, 0.012), "0.1 0.9 0.45 1")
        sp += _vis(f"{P}setpoint_tick_r", "0.078 0 0 0 0 0", _box(0.006, 0.006, 0.012), "0.1 0.9 0.45 1")
        L.append(f'    <link name="{P}setpoint_marker">\n      <pose>{x0:.4f} 0 {Z_FACE - BALL_R:.4f} 0 0 0</pose>\n{sp}    </link>\n')
        J.append(f'    <joint name="{P}setpoint" type="prismatic">\n      <parent>{P}rig</parent>\n'
                 f'      <child>{P}setpoint_marker</child>\n      <axis><xyz>0 0 -1</xyz></axis>\n    </joint>\n')
    return "".join(L), "".join(J)


def scene_single() -> str:
    links, joints = rig("", 0.0, with_sensor=True, with_setpoint=True)
    base = _vis("base_plate", f"-0.06 0 {BASE_T / 2:.4f} 0 0 0", _box(0.36, 0.22, BASE_T), "0.20 0.22 0.27 1")
    base += _vis("base_label", f"0.06 0.085 {BASE_T + 0.0005:.4f} 0 0 0", _box(0.08, 0.02, 0.001), "0.85 0.6 0.15 1")
    for k, (bx, by) in enumerate(((-0.22, -0.09), (-0.22, 0.09), (0.1, -0.09), (0.1, 0.09))):
        base += _vis(f"foot{k + 1}", f"{bx:.4f} {by:.4f} -0.004 0 0 0", _cyl(0.012, 0.008), "0.1 0.1 0.1 1")
    return (
        '<?xml version="1.0"?>\n'
        "<!--\n"
        "  maglev: a tabletop magnetic levitation rig (Z-up, metres).\n"
        f"  The magnet face is at z = {Z_FACE:.4f}; the gap h runs from the face down to the top of the\n"
        f"  ball (radius {BALL_R} m), so the prismatic joint \"gap\" (axis -Z) carries h directly, and\n"
        f"  the ball lands on the pedestal at h = {H_MAX} m. \"setpoint\" moves the green marker to the\n"
        "  reference gap; the copper body \"coil_winding\" is coloured by the coil current. The IR light\n"
        "  curtain (emitter, receiver, faint beam) covers gaps from 0.03 to 0.27 m.\n"
        "  Written by examples/maglev/design/build_model.py.\n"
        "-->\n"
        '<sdf version="1.9">\n  <model name="maglev">\n'
        f'    <link name="base">\n      <pose>0 0 0 0 0 0</pose>\n{base}    </link>\n'
        f"{links}{joints}"
        "  </model>\n</sdf>\n"
    )


def scene_three() -> str:
    parts_l, parts_j = [], []
    for k, p in enumerate(P_GRID):
        tag = f"{int(round(p * 100)):02d}"
        links, joints = rig(f"r{tag}_", 0.17 * k, with_sensor=False, with_setpoint=False, column=False)
        parts_l.append(links)
        # the trim-gap marker of this rig (fixed)
        parts_l.append(
            f'    <link name="r{tag}_trim">\n      <pose>{0.17 * k:.4f} 0 {Z_FACE - BALL_R - p:.4f} 0 0 0</pose>\n'
            + _vis(f"r{tag}_trim_disc", "0 0 0 0 0 0", _cyl(0.03, 0.0015), "0.15 0.85 0.45 0.3")
            + "    </link>\n")
        parts_j.append(joints.replace('<joint name="r', '<joint name="r').replace(f'name="r{tag}_gap"', f'name="gap{tag}"'))
        parts_j.append(f'    <joint name="r{tag}_trim_fix" type="fixed">\n      <parent>r{tag}_rig</parent>\n      <child>r{tag}_trim</child>\n    </joint>\n')
    base = _vis("base_plate", f"0.17 0 {BASE_T / 2:.4f} 0 0 0", _box(0.52, 0.16, BASE_T), "0.20 0.22 0.27 1")
    base += _vis("beam", f"0.17 0 {Z_FACE + 0.15:.4f} 0 0 0", _box(0.52, 0.04, 0.03), "0.72 0.74 0.78 1")
    for k, x in enumerate((-0.07, 0.41)):
        base += _vis(f"post{k + 1}", f"{x:.4f} 0 {BASE_T + (Z_FACE + 0.165 - BASE_T) / 2:.4f} 0 0 0", _box(0.03, 0.03, Z_FACE + 0.165 - BASE_T), "0.72 0.74 0.78 1")
    for k in range(3):
        base += _vis(f"hanger{k + 1}", f"{0.17 * k:.4f} 0 {Z_FACE + 0.1375:.4f} 0 0 0", _cyl(0.008, 0.02), "0.5 0.52 0.56 1")
    return (
        '<?xml version="1.0"?>\n'
        "<!--\n"
        "  maglev-open-loop: three magnets on one beam, trimmed for gaps of 0.05, 0.15 and 0.25 m\n"
        "  (green discs). The joints gap05, gap15 and gap25 (axis -Z) carry the gaps of the three\n"
        "  released balls. Same geometry as scenes/maglev.sdf. Written by build_model.py.\n"
        "-->\n"
        '<sdf version="1.9">\n  <model name="maglev_open_loop">\n'
        f'    <link name="frame">\n      <pose>0 0 0 0 0 0</pose>\n{base}    </link>\n'
        + "".join(parts_l) + "".join(parts_j)
        + "".join(f'    <joint name="r{int(round(p * 100)):02d}_mount" type="fixed">\n      <parent>frame</parent>\n      <child>r{int(round(p * 100)):02d}_rig</child>\n    </joint>\n' for p in P_GRID)
        + "  </model>\n</sdf>\n"
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(EXAMPLE))


# --------------------------------------------------------------------------- checks

def expected() -> dict:
    """examples/maglev/expected.json: every number from design.json (scipy), so a check states
    'bgsim agrees with the independent design calculation'."""
    m1 = DESIGN["model1"]["nonlinear"]
    m2 = DESIGN["model2"]
    m3 = DESIGN["model3"]
    h0, h1 = H_START, DESIGN["scenario"]["h_step"]
    t_end, t_step = DESIGN["scenario"]["t_end"], DESIGN["scenario"]["t_step"]
    no_diag = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
               "note": "integral causality everywhere, no algebraic loop, no event storm"}

    def step(signal, m, rise, overshoot, settling, note):
        return {"kind": "step_response", "signal": signal, "from_t": t_step, "to_t": t_end, "step_t": t_step,
                "value": h1, "initial": h0, "max_rise_time": rise, "max_overshoot": overshoot,
                "max_settling_time": settling,
                "note": note + f" (scipy design: rise {m['rise']:.4f} s, overshoot {m['overshoot']:.2%}, "
                               f"settling {m['settling']:.4f} s)"}

    current = [
        {"kind": "scene_bindings"},
        no_diag,
        step("Ball/h", m1, 0.18, 0.005, 0.45, "the MathWorks scenario 0.15 -> 0.1875 m"),
        {"kind": "cursor_value", "signal": "Ball/h", "t": t_end, "value": m1["h_max"], "abs": 1e-8,
         "note": "the gap at 1.4 s equals the scipy simulation of the same loop"},
        {"kind": "max_abs", "signal": "PID/u", "value": m1["i_max"], "rtol": 1e-4,
         "note": "peak coil current (scipy)"},
        {"kind": "min_ge", "signal": "PID/u", "value": 0.5 * m1["i_min"],
         "note": f"the current stays positive (scipy minimum {m1['i_min']:.4f} A): the magnet only pulls"},
        {"kind": "min_ge", "signal": "Ball/h", "value": h0 - 1e-9, "note": "no undershoot below the start gap"},
        {"kind": "max_abs_le", "signal": "Ball/F_c", "value": 0.0,
         "note": "the ball never touches the magnet or the pedestal: it stays levitated"},
    ]
    for p in P_GRID:
        tag = f"{int(round(p * 100)):02d}"
        current.append({"kind": "cursor_value", "signal": f"Statics/PID{tag}/u", "t": t_end, "value": C_TRIM * p,
                        "rtol": 1e-6, "note": f"integral action finds the trim current sqrt(m g/alpha)*{p} m"})
        current.append({"kind": "cursor_value", "signal": f"Statics/Ball{tag}/h", "t": t_end, "value": p,
                        "rtol": 1e-6, "note": "and holds the gap"})

    open_loop = [{"kind": "scene_bindings"}, no_diag]
    for gr in m2["growth"]:
        tag = f"{int(round(gr['p'] * 100)):02d}"
        open_loop.append({"kind": "cursor_value", "signal": f"Grow{tag}/lambda", "t": gr["t_check"],
                          "value": gr["lambda_at_check"], "rtol": 1e-7,
                          "note": f"v/(h - p) of the released ball at p = {gr['p']} m (scipy, same equation)"})
        open_loop.append({"kind": "cursor_value", "signal": f"Grow{tag}/lambda", "t": gr["t_check"],
                          "value": gr["pole"], "rtol": 2e-4,
                          "note": f"= the LPV pole sqrt(2 g/p) = {gr['pole']:.4f} 1/s, up to tanh(7) and the "
                                  "nonlinearity of a 5.5 um deviation"})
    for tag, name in (("S", "small"), ("L", "large")):
        m = m2[name]
        span = abs(m["h1"] - h0)
        open_loop.append({"kind": "max_abs", "signal": f"Diff{tag}/y", "value": m["max_diff_over_step"] * span,
                          "rtol": 2e-3,
                          "note": f"nonlinear - frozen linear gap: {m['max_diff_over_step']:.2%} of the {name} step (scipy)"})
        open_loop.append({"kind": "cursor_value", "signal": f"Ball{tag}/h", "t": 1.5, "value": m["h1"], "abs": 1e-5,
                          "note": "both loops reach the setpoint"})
        open_loop.append({"kind": "cursor_value", "signal": f"Lin{tag}/h", "t": 1.5, "value": m["h1"], "abs": 1e-5})
    open_loop.append({"kind": "min_ge", "signal": "PIDL/u", "value": m2["large"]["nonlinear"]["i_min"] - 0.01,
                      "note": "the large step asks for a negative current"})
    open_loop.append({"kind": "max_abs", "signal": "PIDL/u", "value": m2["large"]["nonlinear"]["i_max"], "rtol": 1e-3,
                      "note": "peak current of the large step (scipy)"})

    nf = m3["noise_free"]
    bond_checks = [
        {"kind": "scene_bindings"},
        no_diag,
        step("BallPos/y", nf, 0.18, 0.01, 0.35,
             "cascade with the noisy, sampled IR sensor; the scipy design is continuous and noise-free"),
        {"kind": "invariant", "terms": [{"signal": "EM/W", "coeff": 1.0}, {"signal": "Eel/y", "coeff": -1.0},
                                        {"signal": "Emech/y", "coeff": -1.0}],
         "tol": 1e-7, "scale": m3["W0"],
         "note": "the IC-field stores exactly what flows in: W(t) - integral(v i) - integral(F dh/dt) = W(0)"},
        {"kind": "cursor_value", "signal": "EM/W", "t": 0.0, "value": m3["W0"], "rtol": 1e-9,
         "note": "W(0) = L(h0) i0^2 / 2"},
        {"kind": "max_abs_le", "signal": "Sat/y", "value": m3["V_max"], "note": "the amplifier rail"},
        {"kind": "min_ge", "signal": "EM/i", "value": 1.0, "note": "the coil current stays positive"},
        {"kind": "compare_signals", "signal": "EM/h", "signal_b": "BallPos/y", "max_abs": 1e-9,
         "note": "the field's gap state and the ball position sensor integrate the same velocity"},
        {"kind": "compare_signals", "signal": "EM/F", "signal_b": "Fmag/y", "max_abs": 1e-12,
         "note": "the effort detector on the 0-junction reads the field force"},
    ]
    ideal = [
        no_diag,
        {"kind": "cursor_value", "signal": "EM/W", "t": 0.0, "value": m3["W0"], "rtol": 1e-9},
        {"kind": "ratio", "signal": "EM/i", "signal_b": "EM/h", "t": 6.0, "value": C_TRIM, "rtol": 1e-6,
         "note": "the same statics as maglev-current-driven: i = sqrt(m g/alpha) h at rest"},
        {"kind": "final_value", "signal": "EM/F", "t": 6.0, "value": DESIGN["plant"]["m_b"] * DESIGN["plant"]["g"],
         "rtol": 1e-6, "note": "the field carries the weight"},
        {"kind": "final_value", "signal": "BallPos/y", "t": 6.0, "value": h1, "rtol": 1e-6},
        {"kind": "cursor_value", "signal": "BallPos/y", "t": t_end, "value": h1 + nf["final_error"], "abs": 2e-6,
         "note": "the slow integral tail at 1.4 s (scipy, continuous)"},
        step("BallPos/y", nf, 0.18, 0.005, 0.32, "ideal sensor (sampled at 1 kHz, no noise, 52-bit ADC)"),
        {"kind": "max_abs_le", "signal": "Sat/y", "value": m3["V_max"]},
    ]
    return {
        "project": "maglev",
        "description": "Maglev showcase (after the MathWorks 'maglev LPV model from batch linearization' "
                       "example). Numbers come from design/design.json, an independent scipy calculation.",
        "models": {
            "maglev-current-driven": {"checks": current},
            "maglev-open-loop-and-linear": {"checks": open_loop},
            "maglev-bondgraph": {"checks": bond_checks},
            "maglev-bondgraph-ideal-sensor": {
                "model": "maglev-bondgraph",
                "settings": {"t_end": 6.0, "output": {"points": 12001}},
                "overrides": [{"target": "IR/Noise/std", "value": 0.0}, {"target": "IR/ADC/bits", "value": 52}],
                "checks": ideal,
            },
        },
        "compare": [
            {"a": "maglev-current-driven", "b": "maglev-bondgraph-ideal-sensor", "signal_a": "Ball/h",
             "signal_b": "BallPos/y", "from_t": 0.0, "max_abs": 3e-3,
             "note": "the cascade (other PID, 1 kHz sensor, coil dynamics) tracks the current-driven loop within 3 mm (8 % of the step)"},
        ],
    }


def main() -> None:
    for doc in (model_current_driven(), model_open_loop(), model_bondgraph()):
        write(EXAMPLE / "models" / f"{doc['name']}.bgmodel.json", json.dumps(doc, indent=2) + "\n")
    write(EXAMPLE / "expected.json", json.dumps(expected(), indent=2) + "\n")
    write(EXAMPLE / SCENE_CURRENT, scene_single())
    write(EXAMPLE / SCENE_OPEN, scene_three())


if __name__ == "__main__":
    main()
