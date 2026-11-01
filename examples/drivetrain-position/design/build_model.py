# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the three model documents of the `drivetrain-position` sample.

    drivetrain-position            the showcase: a 1 kHz firmware (LQR + Kalman + smooth trajectory)
    naive                          the same plant with a textbook motor-side PID
    drivetrain-position-open-loop  the plant alone, a voltage step and a load step (the plant ODE
                                   of design/design.py is compared with it)

All three share one plant, written as a bond graph (MSe, I, R, GY, TF, C and 0/1-junctions).
`design/design.py` repeats the plant numbers in its header and checks them against the model
documents, so a change in one place and not the other is caught.

    uv run examples/drivetrain-position/design/build_model.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# plant (also in design.py)
R_OHM, L_H, KT, J_M, R_D = 1.0, 1e-3, 0.1, 5e-5, 1e-4
GEAR, J1, J2 = 10.0, 1e-3, 2e-3
K_SHAFT, D_SHAFT = 1.2, 1e-3
T_STEP, R_STEP = 0.2, 1.0
T_DIST, TORQUE = 2.2, 0.2
T_END = 3.2
ENC_M, ENC_L = 6.283185307179586 / 4096, 6.283185307179586 / 16384

nodes: list[dict] = []
connections: list[dict] = []


def node(nid, name, block, x, y, params=None, constants=None, starts=None):
    nodes.append({
        "id": nid, "name": name, "block": block, "position": {"x": x, "y": y}, "rotation": 0,
        "flipX": False, "params": params or {}, "constants": constants or {}, "starts": starts or {},
        "ui": {"showLabel": True, "color": None},
    })


def ref(path):
    return {"ref": path}


def junction(kind):
    return {"junction": kind}


def bond(bid, a, b, port_a=None, port_b=None):
    def end(n, p):
        return {"node": n} if p is None else {"node": n, "port": p}

    connections.append({"id": bid, "kind": "bond", "from": end(a, port_a), "to": end(b, port_b),
                        "route": [], "label": None})


def signal(sid, a, port_a, b, port_b, label):
    connections.append({"id": sid, "kind": "signal", "from": {"node": a, "port": port_a},
                        "to": {"node": b, "port": port_b}, "route": [], "label": label})


def plant() -> None:
    node("n01", "V", ref("stdlib:bondgraph/MSe"), 100, 490, {"gain": "1.0"})
    node("n02", "Elec", junction("1"), 240, 490)
    node("n03", "R", ref("stdlib:bondgraph/R"), 170, 610, {"r": repr(R_OHM)})
    node("n04", "IL", ref("stdlib:bondgraph/I"), 310, 610, {"i": repr(L_H)})
    node("n05", "Current", ref("project:FlowSensor"), 240, 370)
    node("n06", "GY", ref("stdlib:bondgraph/GY"), 360, 490, {"r": repr(KT)})
    node("n07", "MotorJ", junction("1"), 480, 490)
    node("n08", "IJm", ref("stdlib:bondgraph/I"), 410, 610, {"i": repr(J_M)})
    node("n09", "Rd", ref("stdlib:bondgraph/R"), 550, 610, {"r": repr(R_D)})
    node("n10", "MotorSpeed", ref("project:FlowSensor"), 480, 370)
    node("n18", "TFa", ref("stdlib:bondgraph/TF"), 600, 490, {"n": "1.0"})
    node("n19", "TFb", ref("stdlib:bondgraph/TF"), 720, 490, {"n": repr(1.0 / GEAR)})
    node("n20", "WheelJ1", junction("1"), 840, 490)
    node("n21", "IW1", ref("stdlib:bondgraph/I"), 840, 610, {"i": repr(J1)})
    node("n22", "S1", junction("0"), 960, 490)
    node("n23", "Shaft", junction("1"), 960, 380)
    node("n24", "C", ref("stdlib:bondgraph/C"), 890, 300, {"c": repr(1.0 / K_SHAFT)})
    node("n25", "D", ref("stdlib:bondgraph/R"), 1030, 300, {"r": repr(D_SHAFT)})
    node("n38", "WheelJ2", junction("1"), 1080, 490)
    node("n39", "IW2", ref("stdlib:bondgraph/I"), 1080, 610, {"i": repr(J2)})
    node("n40", "Load", ref("stdlib:bondgraph/MSe"), 1200, 490, {"gain": "1.0"})
    node("n41", "LoadStep", ref("stdlib:sources/Step"), 1200, 370,
         {"t_step": repr(T_DIST), "initial": "0.0", "final": repr(-TORQUE)})
    # sensors: motor speed -> angle; load speed -> angle (kinematic integrators, the D28 exception)
    node("n11", "Theta", ref("stdlib:continuous/Integrator"), 480, 250, starts={"x": "0.0"})
    node("n50", "LoadSpeed", ref("project:FlowSensor"), 1080, 370)
    node("n51", "ThetaL", ref("stdlib:continuous/Integrator"), 1080, 250, starts={"x": "0.0"})
    bond("b01", "n01", "n02", "p", None)
    bond("b02", "n02", "n03", None, "p")
    bond("b03", "n02", "n04", None, "p")
    bond("b04", "n02", "n05", None, "p")
    bond("b05", "n02", "n06", None, "p1")
    bond("b06", "n06", "n07", "p2", None)
    bond("b07", "n07", "n08", None, "p")
    bond("b08", "n07", "n09", None, "p")
    bond("b09", "n07", "n10", None, "p")
    bond("b10", "n07", "n18", None, "p1")
    bond("b10b", "n18", "n19", "p2", "p1")
    bond("b10c", "n19", "n20", "p2", None)
    bond("b11", "n20", "n21", None, "p")
    bond("b12", "n20", "n22")
    bond("b13", "n23", "n22")
    bond("b14", "n23", "n24", None, "p")
    bond("b15", "n23", "n25", None, "p")
    bond("b16", "n22", "n38")
    bond("b17", "n38", "n39", None, "p")
    bond("b18", "n40", "n38", "p", None)
    bond("b19", "n38", "n50", None, "p")
    signal("s02", "n41", "y", "n40", "u", "load step")
    signal("s03", "n10", "y", "n11", "u", "motor speed")
    signal("s07", "n50", "y", "n51", "u", "load speed")


def sensors_encoders() -> None:
    node("n12", "Encoder", ref("stdlib:discrete/Quantizer"), 310, 250, {"resolution": repr(ENC_M)},
         {"sample_period": "1e-3"})
    node("n52", "EncoderL", ref("stdlib:discrete/Quantizer"), 910, 130, {"resolution": repr(ENC_L)},
         {"sample_period": "1e-3"})
    signal("s04", "n11", "y", "n12", "u", "motor angle")
    signal("s08", "n51", "y", "n52", "u", "load angle")


def common(name: str) -> dict:
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": name,
        "diagram": {"nodes": nodes, "connections": connections, "subsystemPorts": [], "annotations": []},
        "settings": {"t_start": 0.0, "t_end": T_END, "solver": "auto", "reltol": 1e-8, "abstol": 1e-10,
                     "max_step": None, "output": {"mode": "points", "points": int(round(T_END * 1000)) + 1},
                     "event_limit": 10000},
    }


SCENE = "scenes/drivetrain-position.sdf"
# the 3D view opens with the shaft twist drawn x10: 0.17-0.33 rad on a 0.7 m, 8 mm shaft turns the stripes by
# only 1.4-2.6 mm at true scale; x10 makes them wind visibly (README, "3D view")
SCENE_EXAGGERATION = 10
BINDINGS = [
    {"target": "joint:rotor_joint", "property": "position", "signal": "Theta/y"},
    {"target": "joint:wheel1_joint", "property": "position", "signal": "Theta/y", "gain": 0.1},
    {"target": "joint:wheel2_joint", "property": "position", "signal": "ThetaL/y"},
    # the shaft turns with wheel 1 (its link) and twists linearly towards wheel 2: the lumped spring's
    # twist distribution, theta(s) = s / L * C/q (C/q is the wheel-2 minus the wheel-1 angle)
    {"target": "visual:shaft_rod", "property": "deformation", "family": "torsion", "basis": "linear",
     "beam": {"axis": "+z", "length": 0.705}, "signal": ["C/q"]},
]

STRUCTURE = (
    "Plant (pure bond graph): MSe(V) -> 1-junction (R = 1 ohm, I = L = 1 mH) -> GY (k_t = 0.1) -> "
    "1-junction (rotor I = 5e-5, R_d) -> TF(1) * TF(0.1) = a 10:1 gear -> 1-junction (wheel 1, I = 1e-3) -> "
    "0-junction S1 with the shaft 1-junction (C = 1/1.2 N m/rad, R = 0.001) -> 1-junction (wheel 2, "
    "I = 2e-3) with the load MSe (-0.2 N m at 2.2 s). FlowSensors and kinematic integrators give the "
    "motor and load angles."
)


def showcase() -> dict:
    nodes.clear()
    connections.clear()
    plant()
    sensors_encoders()
    node("n42", "Ref", ref("stdlib:sources/Step"), 100, 130,
         {"t_step": repr(T_STEP), "initial": "0.0", "final": repr(R_STEP)})
    node("n43", "Ctrl", ref("project:PositionController"), 700, 130)
    signal("s05", "n12", "y", "n43", "theta_m", "motor encoder (12 bit)")
    signal("s09", "n52", "y", "n43", "theta_L", "load encoder (14 bit)")
    signal("s06", "n42", "y", "n43", "r_cmd", "1 rad at 0.2 s")
    signal("s01", "n43", "u", "n01", "u", "voltage")
    doc = common("drivetrain-position")
    doc["diagram"]["annotations"] = [{"id": "a1", "kind": "text", "x": 40, "y": 820, "w": 1500, "h": 110,
        "text": STRUCTURE + " Ctrl is the 1 kHz firmware: septic smoothstep trajectory, 5-state Kalman "
                "filter on the two encoders, model-inversion feedforward and LQR with integral action."}]
    doc["plots"] = [
        {"id": "p1", "title": "Load position", "signals": ["ThetaL/y", "Ctrl/r_traj", "Ref/y"]},
        {"id": "p2", "title": "Control voltage", "signals": ["V/p.e", "Ctrl/u"]},
        {"id": "p3", "title": "Shaft twist", "signals": ["C/q"]},
        {"id": "p4", "title": "Estimator", "signals": ["ThetaL/y", "Ctrl/theta_L_hat", "Ctrl/T_hat"]},
    ]
    doc["scene"] = {"file": SCENE, "exaggeration": SCENE_EXAGGERATION}
    doc["bindings"] = BINDINGS
    return doc


def naive() -> dict:
    nodes.clear()
    connections.clear()
    plant()
    node("n42", "Ref", ref("stdlib:sources/Step"), 100, 130,
         {"t_step": repr(T_STEP), "initial": "0.0", "final": repr(R_STEP)})
    node("n53", "ToMotor", ref("stdlib:continuous/Gain"), 310, 130, {"k": repr(GEAR)})
    node("n54", "PID", ref("project:PositionPID"), 700, 130)
    signal("s10", "n42", "y", "n53", "u", "1 rad at 0.2 s (load)")
    signal("s11", "n53", "y", "n54", "r", "motor reference n * r")
    signal("s12", "n11", "y", "n54", "y", "motor angle")
    signal("s01", "n54", "u", "n01", "u", "voltage")
    doc = common("naive")
    doc["diagram"]["annotations"] = [{"id": "a1", "kind": "text", "x": 40, "y": 820, "w": 1500, "h": 110,
        "text": STRUCTURE + " PID is the textbook controller: a rigid-body tuning of the motor-side "
                "position loop."}]
    doc["plots"] = [
        {"id": "p1", "title": "Load position", "signals": ["ThetaL/y", "Ref/y"]},
        {"id": "p2", "title": "Control voltage", "signals": ["V/p.e"]},
        {"id": "p3", "title": "Shaft twist", "signals": ["C/q"]},
    ]
    doc["scene"] = {"file": SCENE, "exaggeration": SCENE_EXAGGERATION}
    doc["bindings"] = BINDINGS
    return doc


def open_loop() -> dict:
    nodes.clear()
    connections.clear()
    plant()
    node("n42", "Vin", ref("stdlib:sources/Step"), 100, 250,
         {"t_step": "0.05", "initial": "0.0", "final": "2.0"})
    signal("s01", "n42", "y", "n01", "u", "2 V at 0.05 s")
    for n in nodes:
        if n["name"] == "LoadStep":
            n["params"]["t_step"] = "0.6"
    doc = common("drivetrain-position-open-loop")
    doc["settings"]["t_end"] = 1.0
    doc["settings"]["output"]["points"] = 1001
    doc["diagram"]["annotations"] = [{"id": "a1", "kind": "text", "x": 40, "y": 820, "w": 1500, "h": 110,
        "text": "Verification model: the plant alone, +2 V at 0.05 s and a -0.2 N m load step at 0.6 s. "
                "design/design.py integrates the same equations (5-state ODE with the 1 mH inductance) "
                "and expected.json compares the two."}]
    doc["plots"] = [{"id": "p1", "title": "Load position", "signals": ["ThetaL/y", "Theta/y"]}]
    doc["scene"] = {"file": SCENE, "exaggeration": SCENE_EXAGGERATION}
    doc["bindings"] = BINDINGS
    return doc


def main() -> None:
    for name, build in (("drivetrain-position", showcase), ("naive", naive),
                        ("drivetrain-position-open-loop", open_loop)):
        doc = build()
        path = ROOT / "models" / f"{name}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
