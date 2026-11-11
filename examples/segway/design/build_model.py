# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Writes the models of the `segway` example (``models/*.bgmodel.json``): ``balance``, ``open-loop``,
``top-speed`` and ``figure-eight``. Run ``design.py`` first (it writes ``design.json``, the gains); the
scene is ``build_scene.py`` and ``expected.json`` is ``build_expected.py``.

All four models are the same 3D bond graph (stdlib multibond/spatial elements, no equation block for
the mechanics):

* the body is a floating ``RigidBody3D`` (pose from a ``PoseIntegrator3D``), centre of mass at
  its frame origin, x forward, y left, z up;
* each wheel is a ``RigidBody3D`` hanging on a ``Revolute3D`` axle joint (axis = body y, via a
  ``FixedTransform3DNeutral`` mount) with its pose composed from the body pose and the joint pose,
  and it rolls on the ground through a ``RollingDisk`` contact (compliant, friction cone: the
  no-slip rolling constraint is not imposed, it is the friction force);
* each motor is an ``MSe`` torque source on the axle joint (current loop, torque constant and gear
  ratio folded into the torque command): the joint carries the reaction, so the motor torque acts
  on the body exactly as on a real vehicle;
* the pitch push is an ``ExternalWrenchSpatial`` on the body.

    uv run examples/segway/design/build_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design as d  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
D = d.D
DES = json.loads((ROOT / "design" / "design.json").read_text(encoding="utf-8")) if (ROOT / "design" / "design.json").exists() else None

# ground contact (tyre as a stiff Hertz-type spring with damping and Coulomb friction)
K_C, XREF, C_C, MU, VS = 5.0e5, 1.0e-3, 1.0, 0.9, 1.0e-3
W_WHEEL = (D["m_b"] / 2 + D["m_w"]) * D["g"]                   # static load of one wheel
DELTA0 = (W_WHEEL * np.sqrt(XREF) / K_C) ** (2.0 / 3.0)         # its static penetration
S2 = float(np.sqrt(0.5))


def num(x) -> str:
    return repr(float(x))


class Diagram:
    def __init__(self):
        self.nodes, self.conns = [], []
        self._ids = {}

    def node(self, name, ref, x, y, params=None, starts=None):
        nid = f"n{len(self.nodes) + 1:02d}"
        self._ids[name] = nid
        self.nodes.append({
            "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": int(x), "y": int(y)},
            "rotation": 0, "flipX": False, "params": params or {}, "constants": {}, "starts": starts or {},
            "ui": {"showLabel": True, "color": None},
        })

    def _c(self, kind, a, pa, b, pb):
        self.conns.append({"id": f"c{len(self.conns) + 1:03d}", "kind": kind,
                           "from": {"node": self._ids[a], "port": pa}, "to": {"node": self._ids[b], "port": pb},
                           "label": None})

    def bond(self, a, pa, b, pb):
        self._c("bond", a, pa, b, pb)

    def wire(self, a, pa, b, pb):
        self._c("wire", a, pa, b, pb)

    def sig(self, a, pa, b, pb):
        self._c("signal", a, pa, b, pb)


# ------------------------------------------------------------------ global parameters
def global_parameters(overrides=None):
    P = D
    g = [
        ("g0", P["g"], "m/s^2", "Gravitational acceleration"),
        ("m_b", P["m_b"], "kg", "Body mass: rider plus platform, frame and batteries"),
        ("l", P["l"], "m", "Height of the body's centre of mass above the axle"),
        ("J_bx", P["J_bx"], "kg*m^2", "Body roll inertia about its centre of mass"),
        ("J_by", P["J_by"], "kg*m^2", "Body pitch inertia about its centre of mass"),
        ("J_bz", P["J_bz"], "kg*m^2", "Body yaw inertia about its centre of mass"),
        ("r", P["r"], "m", "Wheel radius"),
        ("m_w", P["m_w"], "kg", "Mass of one wheel"),
        ("J_wa", P["J_wa"], "kg*m^2", "Wheel inertia about its axle"),
        ("J_wt", P["J_wt"], "kg*m^2", "Wheel inertia about a diameter"),
        ("b", P["b"], "m", "Distance between the wheel centres"),
        ("n", P["n"], "1", "Gear ratio, motor : wheel"),
        ("k_t", P["k_t"], "N*m/A", "Motor torque constant"),
        ("R_w", P["R"], "Ohm", "Motor winding resistance"),
        ("J_m", P["J_m"], "kg*m^2", "Motor rotor inertia"),
        ("tau_max", P["tau_max"], "N*m", "Torque limit per wheel"),
        ("U_bus", P["U_max"], "V", "Battery bus voltage"),
    ]
    out = [{"name": n, "value": num(v), "unit": u, "description": t} for n, v, u, t in g]
    return out


def gains_globals(kind, zero=False):
    K = [0.0] * 4 if zero else DES["K"]
    out = [
        {"name": "K_xi", "value": num(K[0]), "unit": "N*m/m", "description": "LQR gain on the integral of the speed error"},
        {"name": "K_v", "value": num(K[1]), "unit": "N*m*s/m", "description": "LQR gain on the speed error"},
        {"name": "K_th", "value": num(K[2]), "unit": "N*m/rad", "description": "LQR gain on the body pitch"},
        {"name": "K_w", "value": num(K[3]), "unit": "N*m*s/rad", "description": "LQR gain on the pitch rate"},
        {"name": "kp_psi", "value": num(0.0 if zero else DES["yaw"]["kp"]), "unit": "N*m/rad", "description": "Heading gain"},
        {"name": "kd_psi", "value": num(0.0 if zero else DES["yaw"]["kd"]), "unit": "N*m*s/rad", "description": "Yaw-rate gain"},
    ]
    return out


# ------------------------------------------------------------------ the vehicle
def vehicle(name, comment, theta0, plan, t_end, points, plots, dashboard, scene, push=True, start=(0.0, 0.0),
            extra_globals=(), ramp=None, open_loop=False):
    """The 3D transporter model; ``plan`` is 'ramp' (balance run) or 'eight' (figure of eight)."""
    D_ = Diagram()
    X0, Y0 = start
    # --- body, pose and gravity
    pz = D["r"] - DELTA0 + D["l"] * np.cos(theta0)
    D_.node("Body", "stdlib:spatial/RigidBody3D", 600, 300, params={"m": "m_b", "J": "[J_bx, J_by, J_bz]", "g0": "g0"})
    D_.node("Pose", "stdlib:multibond/PoseIntegrator3D", 600, 460,
            starts={"qw": num(np.cos(theta0 / 2)), "qx": "0.0", "qy": num(np.sin(theta0 / 2)), "qz": "0.0",
                    "px": num(X0 + D["l"] * np.sin(theta0)), "py": num(Y0), "pz": num(pz)})
    D_.sig("Body", "V", "Pose", "tw")
    D_.sig("Pose", "g", "Body", "g")
    D_.node("Ground", "stdlib:contact/ContactSurface", 200, 300)
    # --- two wheels: side +y (left, 'L') and -y (right, 'R')
    for side, sgn, y0 in (("L", +1, 0), ("R", -1, 480)):
        ys = "b/2" if sgn > 0 else "-b/2"
        # mount: pose of the body in the joint frame (joint z = body y): Rx(+90), position (0, -l, -y_j)
        D_.node(f"Mount{side}", "stdlib:multibond/FixedTransform3DNeutral", 820, 140 + y0,
                params={"qw": num(S2), "qx": num(S2), "qy": "0.0", "qz": "0.0",
                        "x": "0.0", "y": "-l", "z": "-(b/2)" if sgn > 0 else "b/2"})
        D_.node(f"Axle{side}", "stdlib:spatial/Revolute3D", 1020, 140 + y0, params={"br": "200.0", "bt": "4000.0",
                                                                                   "kr": "1.0e6", "kt": "1.0e6"})
        D_.node(f"Wheel{side}", "stdlib:spatial/RigidBody3D", 1220, 140 + y0,
                params={"m": "m_w", "J": "[J_wt, J_wt, J_wa]", "g0": "g0"})
        D_.node(f"Tyre{side}", "stdlib:contact/RollingDisk", 1420, 140 + y0,
                params={"radius": "r", "k": num(K_C), "xref": num(XREF), "c": num(C_C), "mu": num(MU), "vs": num(VS)})
        D_.bond("Body", "p", f"Mount{side}", "b")
        D_.bond(f"Mount{side}", "a", f"Axle{side}", "parent")
        D_.bond(f"Axle{side}", "child", f"Wheel{side}", "p")
        D_.bond(f"Wheel{side}", "p", f"Tyre{side}", "p")
        D_.sig("Ground", "o", f"Tyre{side}", "o")
        D_.sig("Ground", "fr", f"Tyre{side}", "fr")
        # poses: wheel = body pose o mount o joint pose
        D_.node(f"Local{side}", "stdlib:spatial/LocalPose3D", 820, 260 + y0,
                params={"qw": num(S2), "qx": num(-S2), "qy": "0.0", "qz": "0.0", "x": "0.0", "y": ys, "z": "-l"})
        D_.node(f"PoseA{side}", "stdlib:multibond/ComposePose3D", 1020, 260 + y0)
        D_.node(f"PoseW{side}", "stdlib:multibond/ComposePose3D", 1220, 260 + y0)
        D_.sig("Pose", "g", f"PoseA{side}", "gp")
        D_.sig(f"Local{side}", "g", f"PoseA{side}", "gl")
        D_.sig(f"PoseA{side}", "g", f"PoseW{side}", "gp")
        D_.sig(f"Axle{side}", "pose", f"PoseW{side}", "gl")
        D_.sig(f"PoseW{side}", "g", f"Wheel{side}", "g")
        D_.sig(f"PoseW{side}", "g", f"Tyre{side}", "g")
        # motor: an ideal torque source on the axle joint (current loop and gear folded in:
        # wheel torque = n k_t i); the joint carries the reaction on the body
        D_.node(f"Motor{side}", "stdlib:bondgraph/MSe", 1020, 20 + y0)
        D_.bond(f"Motor{side}", "p", f"Axle{side}", "drive")
    # --- sensing, plan and control
    D_.node("Sense", "project:SegwaySense", 600, 640, params={"l": "l"})
    D_.sig("Pose", "g", "Sense", "g")
    D_.sig("Body", "V", "Sense", "V")
    if plan == "ramp":
        D_.node("VRef", "stdlib:sources/Ramp", 200, 760,
                params={"t_start": num(ramp[0]), "slope": "v_slope", "duration": num(ramp[2])})
        D_.node("PsiRef", "stdlib:sources/Constant", 200, 860, params={"value": "0.0"})
        vref = ("VRef", "y")
        psiref = ("PsiRef", "y")
    else:
        D_.node("Plan", "project:SegwayPlan", 200, 760, params={"v_cruise": "v_cruise", "t_loop": "t_loop"})
        vref = ("Plan", "v_ref")
        psiref = ("Plan", "psi_ref")
    D_.node("Ctrl", "project:SegwayCtrl", 600, 800, params={
        "K_xi": "K_xi", "K_v": "K_v", "K_th": "K_th", "K_w": "K_w", "kp_psi": "kp_psi", "kd_psi": "kd_psi",
        "tau_max": "tau_max", "r": "r", "n": "n", "k_t": "k_t", "R": "R_w"})
    D_.sig("Sense", "theta", "Ctrl", "theta")
    D_.sig("Sense", "w", "Ctrl", "w")
    D_.sig("AxleL", "qdout", "Ctrl", "qd_l")
    D_.sig("AxleR", "qdout", "Ctrl", "qd_r")
    D_.sig("Sense", "heading", "Ctrl", "psi")
    D_.sig("Sense", "wz", "Ctrl", "wz")
    D_.sig(*vref, "Ctrl", "v_ref")
    D_.sig(*psiref, "Ctrl", "psi_ref")
    D_.sig("Ctrl", "tau_l", "MotorL", "u")
    D_.sig("Ctrl", "tau_r", "MotorR", "u")
    # --- a push on the body (force along the body x axis at the centre of mass)
    if push:
        D_.node("Push", "stdlib:multibond/ExternalWrenchSpatial", 400, 140)
        D_.node("PushPulse", "stdlib:sources/Pulse", 200, 140,
                params={"amplitude": "push_F", "period": "1000.0", "duty": num(d.PUSH_W / 1000.0), "t_start": "push_t0"})
        D_.node("Zero", "stdlib:sources/Constant", 200, 220, params={"value": "0.0"})
        D_.bond("Push", "p", "Body", "p")
        D_.sig("PushPulse", "y", "Push", "fx")
        for k in ("tx", "ty", "tz", "fy", "fz"):
            D_.sig("Zero", "y", "Push", k)
    # --- globals of this model
    gl = global_parameters() + gains_globals(plan, zero=open_loop)
    if plan == "ramp":
        gl += [{"name": "v_slope", "value": num(ramp[1]), "unit": "m/s^2", "description": "Acceleration of the speed set-point ramp"}]
    else:
        gl += [{"name": "v_cruise", "value": "1.5", "unit": "m/s", "description": "Cruise speed of the figure of eight"},
               {"name": "t_loop", "value": "11.0", "unit": "s", "description": "Duration of one circle"}]
    if push:
        gl += [{"name": "push_F", "value": num(d.PUSH_F), "unit": "N", "description": "Force of the push on the body"},
               {"name": "push_t0", "value": num(d.PUSH_T0), "unit": "s", "description": "Time of the push"}]
    gl += list(extra_globals)
    model = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": {"nodes": D_.nodes, "connections": D_.conns, "subsystemPorts": [], "annotations": []},
        "settings": {"t_start": 0.0, "t_end": float(t_end), "solver": "Rodas5P", "reltol": 1e-7, "abstol": 1e-9,
                     "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": 10000},
        "plots": plots,
        "parameters": gl,
        "scene": {"file": scene},
        "bindings": [
            {"target": "link:body", "property": "pose",
             "signal": ["Pose/qw", "Pose/qx", "Pose/qy", "Pose/qz", "Pose/px", "Pose/py", "Pose/pz"]},
            {"target": "link:wheel_l", "property": "pose", "signal": [f"PoseWL/g[{i}]" for i in range(1, 8)]},
            {"target": "link:wheel_r", "property": "pose", "signal": [f"PoseWR/g[{i}]" for i in range(1, 8)]},
        ],
    }
    if dashboard:
        model["dashboard"] = dashboard
    return model


# ------------------------------------------------------------------ plots, dashboards
def plots_balance():
    return [
        {"id": "pitch", "title": "Body pitch (rad)", "signals": ["Sense/theta"]},
        {"id": "speed", "title": "Speed and set-point (m/s)", "signals": ["Ctrl/v", "VRef/y"]},
        {"id": "torque", "title": "Wheel torque commands (N m)", "signals": ["Ctrl/tau_l", "Ctrl/tau_r"]},
        {"id": "voltage", "title": "Voltage the motors need (V)", "signals": ["Ctrl/vreq_l", "Ctrl/vreq_r"]},
        {"id": "current", "title": "Motor current references (A)", "signals": ["Ctrl/i_l", "Ctrl/i_r"]},
        {"id": "wheels", "title": "Contact force of each wheel (N)", "signals": ["TyreL/f_n", "TyreR/f_n"]},
    ]


def plots_eight():
    return [
        {"id": "path", "title": "Path of the axle (y against x, m)", "signals": ["Sense/ya", "Sense/xa"]},
        {"id": "heading", "title": "Heading and set-point (rad)", "signals": ["Sense/heading", "Plan/psi_ref"]},
        {"id": "speed", "title": "Speed and set-point (m/s)", "signals": ["Ctrl/v", "Plan/v_ref"]},
        {"id": "pitch", "title": "Body pitch (rad)", "signals": ["Sense/theta"]},
        {"id": "torque", "title": "Wheel torque commands (N m)", "signals": ["Ctrl/tau_l", "Ctrl/tau_r"]},
        {"id": "voltage", "title": "Voltage the motors need (V)", "signals": ["Ctrl/vreq_l", "Ctrl/vreq_r"]},
    ]


def plots_open():
    return [
        {"id": "pitch", "title": "Body pitch (rad)", "signals": ["Sense/theta"]},
        {"id": "rate", "title": "Pitch rate (rad/s)", "signals": ["Sense/w"]},
        {"id": "speed", "title": "Axle speed (m/s)", "signals": ["Ctrl/v"]},
    ]


def dashboard_open():
    return {
        "autoRerun": False,
        "cards": [
            {"id": "mass", "kind": "slider", "size": "2x1", "title": "Body mass (rider)", "parameter": "global:m_b",
             "options": {"min": 70, "max": 140, "step": 5, "decimals": 0, "unit": "kg"}},
            {"id": "height", "kind": "slider", "size": "2x1", "title": "Centre of mass height", "parameter": "global:l",
             "options": {"min": 0.3, "max": 0.8, "step": 0.02, "decimals": 2, "unit": "m"}},
            {"id": "pitch", "kind": "value", "size": "1x1", "title": "Pitch", "signals": ["Sense/theta"],
             "options": {"decimals": 3, "unit": "rad", "sparkline": True}},
            {"id": "plot_pitch", "kind": "plot", "size": "2x1", "title": "Body pitch", "signals": ["Sense/theta"]},
        ],
    }


def dashboard_balance(push=True):
    dash = _dashboard_balance()
    if not push:
        dash["cards"] = [c for c in dash["cards"] if c["id"] != "push"]
    return dash


def _dashboard_balance():
    return {
        "autoRerun": False,
        "cards": [
            {"id": "push", "kind": "slider", "size": "2x1", "title": "Push force", "parameter": "global:push_F",
             "options": {"min": 0, "max": 400, "step": 10, "decimals": 0, "unit": "N"}},
            {"id": "mass", "kind": "slider", "size": "2x1", "title": "Body mass (rider)", "parameter": "global:m_b",
             "options": {"min": 70, "max": 140, "step": 5, "decimals": 0, "unit": "kg"}},
            {"id": "pitch", "kind": "gauge", "size": "1x1", "title": "Pitch", "signals": ["Sense/theta"],
             "options": {"min": -0.2, "max": 0.2, "decimals": 3, "unit": "rad",
                         "zones": [{"from": -0.2, "to": -0.12, "tone": "bad"}, {"from": -0.12, "to": 0.12, "tone": "good"},
                                   {"from": 0.12, "to": 0.2, "tone": "bad"}]}},
            {"id": "v", "kind": "value", "size": "1x1", "title": "Speed", "signals": ["Ctrl/v"],
             "options": {"decimals": 2, "unit": "m/s", "sparkline": True}},
            {"id": "tau", "kind": "value", "size": "1x1", "title": "Wheel torque", "signals": ["Ctrl/tau_l"],
             "options": {"decimals": 1, "unit": "N m", "sparkline": True}},
            {"id": "volt", "kind": "value", "size": "1x1", "title": "Voltage needed", "signals": ["Ctrl/vreq_l"],
             "options": {"decimals": 1, "unit": "V", "sparkline": True}},
            {"id": "plot_speed", "kind": "plot", "size": "2x1", "title": "Speed and set-point", "signals": ["Ctrl/v", "VRef/y"]},
            {"id": "plot_pitch", "kind": "plot", "size": "2x1", "title": "Body pitch", "signals": ["Sense/theta"]},
        ],
    }


def dashboard_eight():
    return {
        "autoRerun": False,
        "cards": [
            {"id": "speed", "kind": "slider", "size": "2x1", "title": "Cruise speed", "parameter": "global:v_cruise",
             "options": {"min": 0.5, "max": 2.5, "step": 0.1, "decimals": 1, "unit": "m/s"}},
            {"id": "loop", "kind": "slider", "size": "2x1", "title": "Time of one circle", "parameter": "global:t_loop",
             "options": {"min": 7, "max": 16, "step": 0.5, "decimals": 1, "unit": "s"}},
            {"id": "v", "kind": "value", "size": "1x1", "title": "Speed", "signals": ["Ctrl/v"],
             "options": {"decimals": 2, "unit": "m/s", "sparkline": True}},
            {"id": "yaw", "kind": "value", "size": "1x1", "title": "Yaw rate", "signals": ["Sense/wz"],
             "options": {"decimals": 2, "unit": "rad/s", "sparkline": True}},
            {"id": "volt", "kind": "value", "size": "1x1", "title": "Voltage needed", "signals": ["Ctrl/vreq_l"],
             "options": {"decimals": 1, "unit": "V", "sparkline": True}},
            {"id": "pitch", "kind": "value", "size": "1x1", "title": "Pitch", "signals": ["Sense/theta"],
             "options": {"decimals": 3, "unit": "rad", "sparkline": True}},
            {"id": "path", "kind": "plot", "size": "2x2", "title": "Path of the axle", "signals": ["Sense/ya"], "x": "Sense/xa"},
            {"id": "heading", "kind": "plot", "size": "2x1", "title": "Heading and set-point", "signals": ["Sense/heading", "Plan/psi_ref"]},
        ],
    }


def write(name, model):
    MODELS.mkdir(parents=True, exist_ok=True)
    path = MODELS / f"{name}.bgmodel.json"
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT))


def main(only=None):
    todo = {}
    todo["balance"] = lambda: vehicle(
        "balance", "A rider on the transporter, released 0.03 rad (1.7 deg) off upright. The LQR holds it up, follows a "
        "1.5 m/s speed set-point (ramped from t = 3 s) and rejects a 150 N push at the centre of mass at t = 9 s.",
        d.THETA0, "ramp", d.T_END, 1401, plots_balance(), dashboard_balance(), "scenes/segway.sdf",
        ramp=(d.T_RAMP0, d.V_STEP / d.T_RAMP, d.T_RAMP))
    todo["top-speed"] = lambda: vehicle(
        "top-speed", "Accelerating to the published top speed of the Segway i2 (20 km/h) on a slow ramp, then holding it: the "
        "body leans forward about 5.5 degrees while it accelerates, and the voltage the motors need (mostly back-EMF) rises "
        "to 67 V at top speed, just inside the 72 V bus.",
        0.0, "ramp", d.TOP["t_end"], 1701, plots_balance(), dashboard_balance(push=False), "scenes/segway-run.sdf", push=False,
        ramp=(d.TOP["t_ramp0"], d.TOP["v_step"] / d.TOP["t_ramp"], d.TOP["t_ramp"]))
    todo["figure-eight"] = lambda: vehicle(
        "figure-eight", "The transporter drives a figure of eight at 1.5 m/s: the heading set-point turns +2 pi in 11 s and "
        "then back. Differential wheel torque steers; the pitch loop is the same as in `balance`.",
        0.0, "eight", 28.0, 1401, plots_eight(), dashboard_eight(), "scenes/segway-eight.sdf", push=False, start=d.EIGHT_START)
    todo["open-loop"] = lambda: vehicle(
        "open-loop", "No control: the transporter is released 0.002 rad off upright with free wheels and falls over. "
        "The tilt grows with the unstable pole of the linearised plant (+5.23 1/s).",
        d.OPEN["theta0"], "ramp", d.OPEN["t_end"], 501, plots_open(), dashboard_open(), "scenes/segway-close.sdf", push=False,
        ramp=(0.0, 0.0, 1.0), open_loop=True)
    for k in list(todo):
        if only and k not in only:
            del todo[k]
    for k, f in todo.items():
        write(k, f())


if __name__ == "__main__":
    main(sys.argv[1:] or None)
