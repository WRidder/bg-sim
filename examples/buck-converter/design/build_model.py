# /// script
# requires-python = ">=3.11"
# ///
"""Write the two `buck-converter` models from `design/design.json`.

The power stage is a bond graph in textbook form:

    MSe(Vin) -> PowerSensor Pin -> 1-junction IN (Df: input current)
             -> MTF SW (modulus = duty, p2 on the input side, p1 = d*Vin on the switch side)
             -> 1-junction LJ (I: L, R: R_L, Df: inductor current)
             -> 0-junction OUT (C, De: output voltage)
             -> 1-junction IO (Df: output current) -> 0-junction LOAD (R: R_load, MSf: the
                load-current step).

The input power is the stdlib `PowerSensor` next to the effort source; the output power is
the product `Vout*Iout` (a `PowerSensor` between OUT and LOAD would leave the load
resistor's causality free, an algebraic loop W202, because the sensor declares none).

The ideal switch is the modulated transformer `SW`: it conserves power, so the input
current is `d*i_L` and the input power `Vin*d*i_L`.  The controller is the stdlib `PID`
block plus the duty feed-forward `Vref/Vin`; one model drives the switch with
`PWMAverage` (the averaged plant), the other with `PWM` at `f_sw` (the switched plant).
L, C, the load resistance, the reference and the switching frequency are model-level
global parameters.

Run it with ``uv run examples/buck-converter/design/build_model.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))


def node(node_id, name, ref, x, y, params=None):
    block = {"junction": ref} if ref in {"0", "1"} else {"ref": ref}
    return {
        "id": node_id,
        "name": name,
        "block": block,
        "position": {"x": x, "y": y},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": {},
        "starts": {},
        "ui": {"showLabel": True, "color": None},
    }


def point(x, y):
    return {"x": x, "y": y}


def bond(conn_id, frm, to, from_port=None, to_port=None, label=None):
    f = {"node": frm}
    t = {"node": to}
    if from_port is not None:
        f["port"] = from_port
    if to_port is not None:
        t["port"] = to_port
    return {"id": conn_id, "kind": "bond", "from": f, "to": t, "route": [], "label": label}


def wire(conn_id, frm, to, from_port, to_port, label=None, route=None):
    return {
        "id": conn_id,
        "kind": "signal",
        "from": {"node": frm, "port": from_port},
        "to": {"node": to, "port": to_port},
        "route": route or [],
        "label": label,
    }


def num(value: float) -> str:
    return f"{value:.10g}"


def globals_(p: dict) -> list[dict]:
    return [
        {"name": "L", "value": num(p["L"]), "unit": "H", "description": "Inductance of the output filter"},
        {"name": "C", "value": num(p["C"]), "unit": "F", "description": "Output capacitance"},
        {"name": "R_load", "value": num(p["R_load"]), "unit": "Ohm",
         "description": "Load resistance (1 A at 5 V); the 1 A load step comes on top of it"},
        {"name": "V_ref", "value": num(p["Vref"]), "unit": "V", "description": "Output voltage set point"},
        {"name": "f_sw", "value": num(p["f_sw"]), "unit": "Hz",
         "description": "Switching frequency of the PWM carrier (the averaged model has no carrier and ignores it)"},
    ]


# Layout (node origins on the 20 px grid; a 40 px bond-graph element and a 60 px block at the
# same origin share their centre).  Power row at y = 100, controller row at y = 380.
X = {"Vin": 0, "Supply": 140, "Pin": 280, "IN": 420, "SW": 560, "LJ": 700, "OUT": 880,
     "IO": 1020, "LOAD": 1160}
Y_POWER, Y_UP, Y_DOWN, Y_CTRL = 100, -40, 240, 380
# Wire lanes (the centre of a node is its origin + 30).
LANE_FEEDBACK = 500


def build(name: str, switched: bool) -> dict:
    p = DESIGN["plant"]
    c = DESIGN["controller"]
    nodes = [
        # power stage, left to right
        node("n01", "Vin", "stdlib:sources/Step", X["Vin"], Y_POWER,
             {"t_step": num(p["t_line"]), "initial": num(p["Vin"]), "final": num(p["Vin_step"])}),
        node("n02", "Supply", "stdlib:bondgraph/MSe", X["Supply"], Y_POWER, {"gain": "1.0"}),
        node("n03", "Pin", "stdlib:converters/PowerSensor", X["Pin"], Y_POWER),
        node("n04", "IN", "1", X["IN"], Y_POWER),
        node("n05", "Iin", "stdlib:bondgraph/Df", X["IN"], Y_UP),
        node("n06", "SW", "stdlib:bondgraph/MTF", X["SW"], Y_POWER),
        node("n07", "LJ", "1", X["LJ"], Y_POWER),
        node("n08", "L", "stdlib:bondgraph/I", X["LJ"], Y_UP, {"i": "L"}),
        node("n09", "RL", "stdlib:bondgraph/R", X["LJ"], Y_DOWN, {"r": num(p["R_L"])}),
        node("n10", "IL", "stdlib:bondgraph/Df", X["LJ"] + 80, Y_DOWN),
        node("n11", "OUT", "0", X["OUT"], Y_POWER),
        node("n12", "C", "stdlib:bondgraph/C", X["OUT"], Y_UP, {"c": "C"}),
        node("n13", "Vout", "stdlib:bondgraph/De", X["OUT"], Y_DOWN),
        node("n14", "IO", "1", X["IO"], Y_POWER),
        node("n19", "Iout", "stdlib:bondgraph/Df", X["IO"], Y_DOWN),
        node("n21", "Pout", "stdlib:continuous/Product", X["IO"], Y_CTRL),
        node("n15", "LOAD", "0", X["LOAD"], Y_POWER),
        node("n16", "Rload", "stdlib:bondgraph/R", X["LOAD"], Y_UP, {"r": "R_load"}),
        # The load step draws current out of the node: the source is drawn into the junction
        # (out), so a negative gain makes it a sink of LoadStep amperes.
        node("n17", "Iload", "stdlib:bondgraph/MSf", X["LOAD"], Y_DOWN, {"gain": "-1.0"}),
        node("n18", "LoadStep", "stdlib:sources/Step", X["LOAD"], Y_CTRL,
             {"t_step": num(p["t_load"]), "initial": "0.0", "final": num(p["I_load_step"])}),
        # modulator, next to the switch
        node("n20", "PWM", "stdlib:motion/PWM" if switched else "stdlib:motion/PWMAverage",
             X["SW"], Y_DOWN,
             ({"frequency": "f_sw", "high": "1.0", "low": "0.0", "t_start": "0.0"}
              if switched else {"high": "1.0", "low": "0.0"})),
        # controller row, left to right
        node("n30", "Vref", "stdlib:sources/Constant", -140, Y_CTRL, {"value": "V_ref"}),
        node("n31", "VrefFilt", "stdlib:continuous/FirstOrder", 0, Y_CTRL,
             {"k": "1.0", "tau": num(c["tau_filter"])}),
        node("n32", "Err", "project:Diff2", 140, Y_CTRL),
        node("n33", "PID1", "stdlib:continuous/PID", 280, Y_CTRL,
             {"Kp": num(c["Kp"]), "Ti": f"{c['Ti']:.10f}", "Td": num(c["Td"]),
              "N": num(c["N"]), "lower": "-1.0", "upper": "1.0"}),
        node("n34", "DutySum", "project:Add2", 420, Y_CTRL),
        node("n35", "DutySat", "stdlib:continuous/Saturation", 560, Y_CTRL,
             {"lower": "0.0", "upper": "1.0"}),
        node("n36", "FF", "stdlib:continuous/Divide", 420, Y_DOWN),
    ]
    # Port y of a 60 px block with two connected inputs on its left edge: 10 + 40/3 and 10 + 80/3.
    ff_upper = Y_DOWN + 10 + 40 / 3
    ff_lower = Y_DOWN + 10 + 80 / 3
    connections = [
        # power bonds: sources point at their junction, elements are pointed at,
        # the two-ports (PowerSensor, MTF) pass the power through
        bond("b01", "n02", "n03", "p", "a"),
        bond("b02", "n03", "n04", "b", None),
        bond("b03", "n04", "n05", None, "p"),
        bond("b04", "n04", "n06", None, "p2"),
        bond("b05", "n06", "n07", "p1", None),
        bond("b06", "n07", "n08", None, "p"),
        bond("b07", "n07", "n09", None, "p"),
        bond("b08", "n07", "n10", None, "p"),
        bond("b09", "n07", "n11", None, None),
        bond("b10", "n11", "n12", None, "p"),
        bond("b11", "n11", "n13", None, "p"),
        bond("b12", "n11", "n14", None, None),
        bond("b13", "n14", "n19", None, "p"),
        bond("b16", "n14", "n15", None, None),
        bond("b14", "n15", "n16", None, "p"),
        bond("b15", "n17", "n15", "p", None),
        # signals
        wire("s01", "n01", "n02", "y", "u"),
        wire("s02", "n01", "n36", "y", "u2", None,
             [point(80, Y_POWER + 30), point(80, ff_upper)]),
        wire("s03", "n30", "n31", "y", "u"),
        wire("s04", "n31", "n32", "y", "u1"),
        wire("s05", "n31", "n36", "y", "u1", None,
             [point(110, Y_CTRL + 30), point(110, ff_lower)]),
        wire("s06", "n32", "n33", "y", "u"),
        wire("s07", "n33", "n34", "y", "u2"),
        wire("s08", "n36", "n34", "y", "u1"),
        wire("s09", "n34", "n35", "y", "u"),
        wire("s10", "n35", "n20", "y", "u"),
        wire("s11", "n20", "n06", "y", "u", "duty"),
        wire("s12", "n13", "n32", "y", "u2", "output voltage",
             [point(X["OUT"] + 70, Y_DOWN + 30), point(X["OUT"] + 70, LANE_FEEDBACK),
              point(170, LANE_FEEDBACK)]),
        wire("s14", "n13", "n21", "y", "u1", None,
             [point(X["OUT"] + 70, Y_DOWN + 30), point(X["OUT"] + 70, Y_CTRL + 30)]),
        wire("s15", "n19", "n21", "y", "u2"),
        wire("s13", "n18", "n17", "y", "u"),
    ]
    plots = [
        {"id": "p1", "title": "Output voltage", "signals": ["Vout/y", "VrefFilt/y"]},
        {"id": "p2", "title": "Inductor and input current", "signals": ["IL/y", "Iin/y"]},
        {"id": "p3", "title": "Duty cycle", "signals": ["DutySat/y"]},
        {"id": "p4", "title": "Input and output power", "signals": ["Pin/y", "Pout/y"]},
        {"id": "p5", "title": "Controller effort", "signals": ["PID1/y", "FF/y"]},
    ]
    cards = [
        {"id": "vref", "kind": "slider", "size": "2x1", "title": "Output set point",
         "parameter": "global:V_ref",
         "options": {"min": 2.0, "max": 10.0, "step": 0.5, "decimals": 1, "unit": "V"}},
        {"id": "rload", "kind": "slider", "size": "2x1", "title": "Load resistance",
         "parameter": "global:R_load",
         "options": {"min": 2.0, "max": 20.0, "step": 0.5, "decimals": 1, "unit": "Ohm"}},
        {"id": "td", "kind": "slider", "size": "2x1", "title": "PID1 derivative gain Td",
         "parameter": "PID1/Td",
         "options": {"min": 0.0001, "max": 0.0004, "step": 0.00005, "decimals": 5, "unit": "s"}},
    ]
    if switched:
        cards.append(
            {"id": "fsw", "kind": "slider", "size": "2x1", "title": "Switching frequency",
             "parameter": "global:f_sw",
             "options": {"min": 10000.0, "max": 50000.0, "step": 5000.0, "decimals": 0, "unit": "Hz"}})
    cards += [
        {"id": "vout", "kind": "value", "size": "1x1", "title": "Output voltage", "signals": ["Vout/y"],
         "options": {"decimals": 3, "unit": "V", "sparkline": True}},
        {"id": "il", "kind": "value", "size": "1x1", "title": "Inductor current", "signals": ["IL/y"],
         "options": {"decimals": 3, "unit": "A", "sparkline": True}},
        {"id": "pin", "kind": "value", "size": "1x1", "title": "Input power", "signals": ["Pin/y"],
         "options": {"decimals": 2, "unit": "W", "sparkline": True}},
        {"id": "pout", "kind": "value", "size": "1x1", "title": "Output power", "signals": ["Pout/y"],
         "options": {"decimals": 2, "unit": "W", "sparkline": True}},
        {"id": "vplot", "kind": "plot", "size": "2x1", "title": "Output voltage and reference",
         "signals": ["Vout/y", "VrefFilt/y"]},
        {"id": "iplot", "kind": "plot", "size": "2x1", "title": "Inductor and input current",
         "signals": ["IL/y", "Iin/y"]},
    ]
    description = "Switched buck converter" if switched else "Averaged buck converter"
    doc = {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": (
            f"{description} (synchronous, continuous conduction): MSe(Vin) -> 1-junction IN "
            f"(input current) -> MTF SW with modulus d ({'PWM at f_sw' if switched else 'PWMAverage'}) "
            f"-> 1-junction LJ with I(L) and R(R_L = {p['R_L']} Ohm) -> 0-junction OUT with C "
            f"-> 1-junction IO (output current) -> 0-junction LOAD with R(R_load) and a "
            f"{p['I_load_step']} A load-current step at {p['t_load']} s; Vin {p['Vin']} -> "
            f"{p['Vin_step']} V at {p['t_line']} s. Pin is a power sensor on the input bond, "
            f"Pout = Vout*Iout. The controller is the stdlib PID "
            f"(Kp {c['Kp']}, integral gain Kp/Ti^2 = {c['Ki']} 1/s, derivative gain Td = {c['Td']} s, "
            f"N {c['N']}) on the filtered error, plus the duty feed-forward Vref/Vin, clamped to 0..1."
        ),
        "parameters": globals_(p),
        "diagram": {
            "nodes": nodes,
            "connections": connections,
            "subsystemPorts": [],
            "annotations": [
                {"id": "a1", "kind": "text",
                 "text": ("Synchronous buck in continuous conduction (ideal switch, no diode, no ESR, "
                          "no switch resistance). Power stage: MSe(Vin) -> Pin -> 1-junction IN "
                          "(Iin) -> MTF SW, modulus = duty -> 1-junction LJ with I(L), R(RL) and IL "
                          "-> 0-junction OUT with C and Vout -> 1-junction IO with Iout -> 0-junction "
                          "LOAD with R(Rload) and the load step Iload; Pout = Vout*Iout. Controller: Vref -> VrefFilt -> Err -> "
                          "PID1, plus the feed-forward FF = VrefFilt/Vin, clamped by DutySat."),
                 "x": -140, "y": 560, "w": 1360, "h": 70},
            ],
        },
        "settings": {
            "t_start": 0.0,
            "t_end": p["t_end"],
            "solver": "auto",
            "reltol": 1e-8,
            "abstol": 1e-10,
            "max_step": 1e-6 if switched else 1e-5,
            "output": {"mode": "points", "points": 10001},
            "event_limit": 100000 if switched else 10000,
        },
        "plots": plots,
        "dashboard": {"autoRerun": not switched, "cards": cards},
        "scene": {"file": "scenes/buck-converter.sdf"},
        "bindings": [
            {"target": "visual:vout_bar", "property": "color", "signal": "Vout/y",
             "colormap": "coolwarm", "range": [0.0, 5.0]},
            {"target": "visual:il_bar", "property": "color", "signal": "IL/y",
             "colormap": "coolwarm", "range": [0.0, 2.5]},
        ],
    }
    return doc


def main() -> None:
    project = {
        "format": "bgsim.project",
        "language": "0.1.0",
        "name": "buck-converter",
        "models": ["buck-averaged", "buck-switched"],
        "libraryDir": "library",
        "scenesDir": "scenes",
    }
    (ROOT / "bgsim.project.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name, switched in (("buck-averaged", False), ("buck-switched", True)):
        path = ROOT / "models" / f"{name}.bgmodel.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(build(name, switched), indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
