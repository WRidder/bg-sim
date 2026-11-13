# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Generate the single-propeller-drone models, the leg and motor subsystems and the 3D scene.

The vehicle is a **swashplateless** mono-rotor: one motor, no servos. The motor torque is
modulated once per revolution; the rotor accelerates and decelerates within each turn, the
lag-pitch hinges turn that into a cyclic blade pitch, and the hub moment tilts the vehicle. So
roll and pitch are actuated by the same motor that makes the thrust. Throttle is rotor speed.
There is no yaw actuator: the four fins in the slipstream carry the motor reaction and damp the
yaw rate.

Two models are written from the same diagram:

* `single-propeller-drone` - released in hover at 1.32 m (a hand launch: no take-off), a
  +1.5 m x leg, a +1.5 m y leg, then the land mode (a steady 0.25 m/s descent until the feet
  carry weight), touchdown detection and the motor run-down (20 s);
* `single-propeller-drone-hover` - released in hover with a 0.8 rad/s yaw kick and a 0.3 rad/s
  roll kick, then a 1 m lateral step from 3 s (8 s): the control and passive-yaw test.

`library/Leg.bgsub.json` (one landing leg: mount, contact point and its ground plane) and
`library/Motor.bgsub.json` (the battery, inverter and motor bond graph) are written here too;
each model uses four `Leg` instances and one `Motor` instance. Every number comes from
`design.py`.

    uv run examples/single-propeller-drone/design/build_model.py
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
HOVER_Z = d.HOVER_Z
T_END_FLIGHT = 20.0
T_END_HOVER = d.STEP_T_END
YAW_KICK = 0.8                 # rad/s, hover model
ROLL_KICK = 0.3                # rad/s, hover model
CONTACT = {"k": d.K_CONTACT, "xref": 1.0e-3, "c": round(d.C_CONTACT, 4), "mu": d.MU_FEET, "vs": 1.0e-3, "bt": 0.0, "eps": 1.0e-6, "feps": 1.0e-6}


def num(v: float) -> str:
    return f"{float(v):.10g}"


def vec(values) -> str:
    return "[" + ", ".join(num(v) for v in values) + "]"


# ----------------------------------------------------------------------------- document helpers
COMPACT, LETTER, JUNCTION = 60, 40, 40


class Diagram:
    """Nodes keyed by name (the node id is the name), connections and exposed ports."""

    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[tuple] = []
        self.ports: list[dict] = []
        self.boxes: list[tuple[str, float, float, float, float]] = []

    def node(self, name, block, x, y, params=None, starts=None, constants=None, size=(COMPACT, COMPACT + 20)):
        assert all(n["id"] != name for n in self.nodes), name
        b = {"ref": block} if isinstance(block, str) else block
        self.nodes.append({
            "id": name, "name": name, "block": b, "position": {"x": int(x), "y": int(y)},
            "rotation": 0, "flipX": False,
            "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self.boxes.append((name, x, y, size[0], size[1]))
        return name

    def letter(self, name, ref, x, y, params=None, starts=None):
        return self.node(name, ref, x, y, params, starts, size=(LETTER, LETTER + 20))

    def junction(self, name, kind, x, y):
        return self.node(name, {"junction": str(kind)}, x, y, size=(JUNCTION, JUNCTION))

    def card(self, name, block, x, y, rows, params=None, starts=None):
        """A subsystem drawn as a card (164 px wide, 34 + 26 rows + 18 tall)."""
        return self.node(name, block, x, y, params, starts, size=(164, max(86, 34 + 26 * rows + 18) + 20))

    def sig(self, a, pa, b, pb):
        self.connections.append(("signal", a, pa, b, pb))

    def bond(self, a, pa, b, pb):
        self.connections.append(("bond", a, pa, b, pb))

    def wire(self, a, pa, b, pb):
        self.connections.append(("wire", a, pa, b, pb))

    def in_port(self, name, node, port, unit=None, size=1):
        self.ports.append({"name": name, "kind": "signal", "direction": "input", "type": "Real",
                           "size": [size], "unit": unit, "node": node, "port": port})

    def out_port(self, name, node, port, unit=None, size=1):
        self.ports.append({"name": name, "kind": "signal", "direction": "output", "type": "Real",
                           "size": [size], "unit": unit, "node": node, "port": port})

    def power_port(self, name, domain, node, port, size=1):
        self.ports.append({"name": name, "kind": "power", "domain": domain, "size": [size],
                           "node": node, "port": port})

    def check_layout(self, label: str) -> None:
        """No two nodes (with their labels) may overlap."""
        gap = 10
        for i, (na, xa, ya, wa, ha) in enumerate(self.boxes):
            for nb, xb, yb, wb, hb in self.boxes[i + 1:]:
                if xa < xb + wb + gap and xb < xa + wa + gap and ya < yb + hb + gap and yb < ya + ha + gap:
                    raise SystemExit(f"{label}: {na} overlaps {nb}")

    def doc(self, prefix: str = "") -> dict:
        conns = []
        for k, (kind, a, pa, b, pb) in enumerate(self.connections):
            frm = {"node": a}
            if pa is not None:
                frm["port"] = pa
            to = {"node": b}
            if pb is not None:
                to["port"] = pb
            conns.append({"id": f"{prefix}{kind[0]}{k + 1:03d}", "kind": kind, "from": frm, "to": to,
                          "route": [], "label": None})
        return {"nodes": self.nodes, "connections": conns, "subsystemPorts": self.ports if prefix else [],
                "annotations": []}


# ----------------------------------------------------------------------------- the leg subsystem
LEG_ROWS = 2


def leg_definition() -> dict:
    """library/Leg.bgsub.json: one landing leg. The mount carries the body pose to the foot
    point; the contact point presses on its own ground plane (z = 0, mu = 0.8)."""
    s = Diagram()
    s.node("Local", "stdlib:spatial/LocalPose3D", 0, 0, params={"x": 0.0, "y": 0.0, "z": num(d.Z_FOOT)})
    s.node("Compose", "stdlib:multibond/ComposePose3D", 140, 0)
    s.node("Surface", "stdlib:contact/ContactSurface", 140, 120)
    s.node("Mount", "stdlib:multibond/FixedTransform3DNeutral", 0, 240,
           params={"x": 0.0, "y": 0.0, "z": num(-d.Z_FOOT)})
    s.node("Contact", "stdlib:contact/ContactPoint", 280, 240, params=CONTACT)
    s.bond("Mount", "a", "Contact", "p")
    s.sig("Local", "g", "Compose", "gl")
    s.sig("Compose", "g", "Contact", "g")
    s.sig("Surface", "o", "Contact", "o")
    s.sig("Surface", "fr", "Contact", "fr")
    s.power_port("p", "Spatial", "Mount", "b", size=6)
    s.in_port("pose", "Compose", "gp", size=7)
    s.out_port("f_n", "Contact", "f_n", unit="N")
    s.check_layout("Leg")
    diagram = s.doc("leg_")
    ports = diagram["subsystemPorts"]
    diagram["subsystemPorts"] = []
    return {
        "format": "bgsim.subsystem", "name": "Leg",
        "description": ("One landing leg of the single-propeller drone: a fixed mount from the body to the foot "
                        "point, a compliant Hunt-Crossley contact point and its ground plane. Pin the foot "
                        "position with Local/x, Local/y, Local/z and the mount with Mount/x, Mount/y, Mount/z "
                        "(the negated offsets). Generated by design/build_model.py."),
        "ports": ports,
        "diagram": diagram,
        "pins": {"params": ["Local/x", "Local/y", "Local/z", "Mount/x", "Mount/y", "Mount/z"], "starts": []},
    }


# ----------------------------------------------------------------------------- the motor subsystem
MOTOR_ROWS = 5


def motor_definition() -> dict:
    """library/Motor.bgsub.json: the electrical side as a bond graph: the 6S pack (stdlib Battery)
    on a 1-junction with its current detector, the DC bus (0-junction) with the bus-voltage
    detector and the avionics draw, the inverter as an MTF with the duty as modulus, the winding
    (1-junction: R, L, current detector) and the stdlib EMConverter to the shaft. Both models use
    it with the same values, so it pins nothing."""
    s = Diagram()
    s.node("Bat", "stdlib:electrical/Battery", 0, 120,
           params={"capacity": d.BAT_CAP, "soc_table": vec(d.BAT_SOC), "ocv_table": vec(d.BAT_OCV),
                   "R0": d.BAT_R0, "R1": d.BAT_R1, "C1": d.BAT_C1},
           # the RC branch settled at the hover current: Battery's p.f is the charging current,
           # -I_BAT0 in hover, so v1 = R1 p.f = -I_BAT0 R1
           starts={"soc": "1.0", "v1": num(-d.I_BAT0 * d.BAT_R1)})
    s.node("GndB", "stdlib:electrical/Ground", 0, 260)
    s.junction("BatJ", 1, 160, 130)
    s.letter("BatI", "stdlib:bondgraph/Df", 160, 240)
    s.node("Ibat", "stdlib:continuous/Gain", 160, 360, params={"k": -1.0})
    s.junction("Bus", 0, 300, 130)
    s.letter("BusV", "stdlib:bondgraph/De", 300, 240)
    s.letter("Aux", "stdlib:bondgraph/Sf", 300, 0, params={"f": num(-d.I_AUX)})
    s.node("Pbat", "stdlib:continuous/Product", 300, 360)
    s.letter("Inv", "stdlib:bondgraph/MTF", 440, 130)
    s.junction("Stator", 1, 580, 130)
    s.letter("Rw", "stdlib:bondgraph/R", 580, 0, params={"r": d.R_W})
    s.letter("Lw", "stdlib:bondgraph/I", 720, 0, params={"i": d.L_W}, starts={"P": num(d.L_W * d.I_MOT0)})
    s.letter("Imot", "stdlib:bondgraph/Df", 580, 240)
    s.node("EM", "stdlib:converters/EMConverter", 720, 120, params={"k": d.K_MOT})
    s.node("GndM", "stdlib:electrical/Ground", 720, 260)
    s.bond("BatJ", None, "Bat", "p")
    s.wire("Bat", "n", "GndB", "p")
    s.bond("BatJ", None, "BatI", "p")
    s.bond("Bus", None, "BatJ", None)
    s.bond("Bus", None, "BusV", "p")
    s.bond("Aux", "p", "Bus", None)
    s.bond("Bus", None, "Inv", "p2")
    s.bond("Inv", "p1", "Stator", None)
    s.bond("Stator", None, "Rw", "p")
    s.bond("Stator", None, "Lw", "p")
    s.bond("Stator", None, "Imot", "p")
    s.bond("Stator", None, "EM", "n")
    s.wire("EM", "p", "GndM", "p")
    s.sig("BatI", "y", "Ibat", "u")
    s.sig("BusV", "y", "Pbat", "u1")
    s.sig("Ibat", "y", "Pbat", "u2")
    s.in_port("duty", "Inv", "u")
    s.power_port("shaft", "Rotation", "EM", "shaft")
    s.out_port("v_bus", "BusV", "y", unit="V")
    s.out_port("i_bat", "Ibat", "y", unit="A")
    s.out_port("p_bat", "Pbat", "y", unit="W")
    s.out_port("i_m", "Imot", "y", unit="A")
    s.check_layout("Motor")
    diagram = s.doc("motor_")
    ports = diagram["subsystemPorts"]
    diagram["subsystemPorts"] = []
    return {
        "format": "bgsim.subsystem", "name": "Motor",
        "description": ("The drive of the single-propeller drone as a bond graph: the 6S pack (stdlib Battery with "
                        "its OCV table and RC branch, started settled at the hover current), the DC bus with the "
                        "avionics draw, the inverter MTF (modulus = duty), the winding R and I and the EM converter "
                        "to the shaft. Outputs the bus voltage, pack current and power and the motor current. "
                        "Pins nothing. Generated by design/build_model.py."),
        "ports": ports,
        "diagram": diagram,
        "pins": {"params": [], "starts": []},
    }


# ----------------------------------------------------------------------------- the model
def build(name: str, hover: bool) -> dict:
    D = Diagram()
    trim_iv = d.T0 / (d.M * 0.99) - d.G
    r0 = YAW_KICK if hover else 0.0
    p0 = ROLL_KICK if hover else 0.0

    # ------------------------------------------------------------ airframe (multibond)
    D.node("World", "stdlib:multibond/GroundSpatial", 40, 300)
    D.node("Free", "stdlib:spatial/Free3D", 220, 300, starts={"pz": HOVER_Z})
    D.node("Body", "stdlib:spatial/RigidBody3D", 400, 300,
           params={"m": d.M, "J": vec([d.JX, d.JY, d.JZ]), "g0": d.G},
           starts={"inertia/P": vec([d.JX * p0, 0.0, d.JZ * r0, 0.0, 0.0, 0.0])})
    D.bond("World", "p", "Free", "parent")
    D.bond("Free", "child", "Body", "p")
    for k in range(1, 7):
        D.letter(f"FreeSe{k}", "stdlib:bondgraph/Se", 20 + 100 * ((k - 1) % 3), 440 + 100 * ((k - 1) // 3),
                 params={"e": "0.0"})
        D.bond(f"FreeSe{k}", "p", "Free", f"drive{k}")
    D.sig("Free", "pose", "Body", "g")
    D.node("WrenchAero", "stdlib:multibond/ExternalWrenchSpatial", 400, 440)
    D.node("WrenchFins", "stdlib:multibond/ExternalWrenchSpatial", 400, 560)
    D.bond("WrenchAero", "p", "Body", "p")
    D.bond("WrenchFins", "p", "Body", "p")

    # ------------------------------------------------------------ landing gear (four Leg instances)
    for k, (fx, fy) in enumerate(d.feet, start=1):
        D.card(f"Leg{k}", "project:Leg", 40 + 200 * (k - 1), 700, LEG_ROWS,
               params={"Local/x": num(fx), "Local/y": num(fy), "Local/z": num(d.Z_FOOT),
                       "Mount/x": num(-fx), "Mount/y": num(-fy), "Mount/z": num(-d.Z_FOOT)})
        D.bond("Body", "p", f"Leg{k}", "p")
        D.sig("Free", "pose", f"Leg{k}", "pose")
    D.node("LegMux", "stdlib:continuous/Mux4", 860, 700)
    for k in range(1, 5):
        D.sig(f"Leg{k}", "f_n", "LegMux", f"u{k}")

    # ------------------------------------------------------------ rotor, shaft and motor
    D.node("Rotor", "project:PropRotor", 580, 300,
           params={"Ja": d.JA, "kT": d.K_T, "kQ": d.K_Q, "kM": "cyclic_gain", "k_thrust": d.K_THRUST_CYC},
           starts={"h_s": num(d.JA * (d.OMEGA0 + r0))})
    D.bond("Body", "p", "Rotor", "p")
    D.junction("Shaft", 1, 590, 160)
    D.letter("Bearing", "stdlib:bondgraph/R", 720, 40, params={"r": d.B_M})
    D.bond("Shaft", None, "Rotor", "motor")
    D.bond("Shaft", None, "Bearing", "p")
    D.card("Motor", "project:Motor", 700, 140, MOTOR_ROWS)
    D.bond("Shaft", None, "Motor", "shaft")
    D.node("Psi", "stdlib:continuous/Integrator", 580, 40, starts={"x": 0.0})
    D.sig("Rotor", "w", "Psi", "u")
    D.sig("Psi", "y", "Rotor", "psi")

    # ------------------------------------------------------------ aerodynamics (imposed wrenches)
    wind = "[wind_x, wind_y, 0.0]"
    D.node("Aero", "project:AeroWrench", 580, 440,
           params={"m": d.M, "rho": d.RHO, "wind": wind, "Adisc": d.A_PROP, "Cdd": d.C_DD, "zd": d.Z_ROTOR,
                   "Ab": d.A_BODY, "Cdb": d.C_DB, "zb": d.Z_BODY_DRAG, "clin": 0.08})
    D.node("Fins", "project:FinSet", 580, 560,
           params={"m": d.M, "rho": d.RHO, "A": d.A_PROP, "kw": d.K_WAKE, "wind": wind, "S": d.S_FIN,
                   "rf": d.R_FIN, "zf": d.Z_FIN, "delta": d.DELTA_FIN, "cla": d.CLA_FIN, "cdn": d.CDN_FIN,
                   "cf": d.CF_FIN, "cr": d.CR_FIN})
    D.node("AddF", "project:AddVec3", 760, 560)
    for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
        D.sig("Aero", p, "WrenchAero", p)
        D.sig("Fins", p, "WrenchFins", p)
    D.sig("Rotor", "T", "Aero", "T")
    D.sig("Rotor", "Mx", "Aero", "Mx")
    D.sig("Rotor", "My", "Aero", "My")
    D.sig("Body", "V", "Aero", "V")
    D.sig("Free", "pose", "Aero", "pose")
    D.sig("LegMux", "y", "Aero", "leg")
    D.sig("Body", "V", "Fins", "V")
    D.sig("Free", "pose", "Fins", "pose")
    D.sig("Rotor", "T", "Fins", "T")
    D.sig("Rotor", "Q", "Fins", "Q")
    D.sig("Aero", "fs", "AddF", "a")
    D.sig("Fins", "fs_fin", "AddF", "b")

    # ------------------------------------------------------------ truth and sensors
    D.node("Truth", "project:Truth", 760, 440)
    D.sig("Free", "pose", "Truth", "pose")
    D.sig("Body", "V", "Truth", "V")
    D.node("Imu", "project:ImuSensor", 940, 560,
           params={"bgc": vec(d.BGC), "agc": vec(d.AGC), "bac": vec(d.BAC), "aac": vec(d.AAC),
                   "bias_a": vec(list(d.ACC_BIAS))})
    D.sig("Truth", "wb", "Imu", "w")
    D.sig("AddF", "y", "Imu", "f")
    D.node("Mocap", "project:Mocap", 940, 440, starts={"pm": vec([0.0, 0.0, HOVER_Z])})
    D.sig("Truth", "p", "Mocap", "p")
    D.sig("Truth", "vw", "Mocap", "v")
    D.node("Beacon", "project:IrBeacon", 940, 320)
    D.sig("Truth", "yaw", "Beacon", "yaw")
    D.node("Nav", "project:NavFilter", 1120, 440, params={"g0": d.G},
           starts={"ps": vec([0.0, 0.0, HOVER_Z]), "p": vec([0.0, 0.0, HOVER_Z])})
    D.sig("Imu", "gyro_f", "Nav", "gyro")
    D.sig("Imu", "acc_f", "Nav", "acc")
    D.sig("Mocap", "pm", "Nav", "pm")
    D.sig("Mocap", "vm", "Nav", "vm")
    D.sig("Beacon", "psim", "Nav", "psim")
    D.sig("Mocap", "n", "Nav", "n")

    # ------------------------------------------------------------ mission and controller
    D.node("Clock", "stdlib:sources/Time", 940, 40)
    p_start = [0.0, 0.0, HOVER_Z]
    if hover:
        mpar = {"ts": f"[{num(d.STEP_T0)}, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0]",
                "dur": f"[{num(d.STEP_DUR)}, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]",
                "dx": f"[{num(d.STEP_DX)}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]",
                "dy": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]",
                "dz": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]",
                "t_arm": 0.0, "t_disarm": 99.0, "t_land": 99.0}
    else:
        L, T = num(d.LEG_DX), d.LEG_T0
        mpar = {"ts": f"[{num(T[0])}, {num(T[1])}, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0]",
                "dur": f"[{num(d.LEG_DUR)}, {num(d.LEG_DUR)}, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]",
                "dx": f"[{L}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]",
                "dy": f"[0.0, {L}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]",
                "dz": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]",
                "t_arm": 0.0, "t_disarm": 99.0, "t_land": num(d.T_LAND)}
    mpar.update({"p0": vec(p_start), "f_touch": num(d.F_TOUCH), "t_spin": 2.0,
                 "t_hold": num(d.T_HOLD), "t_unload": num(d.T_UNLOAD), "thr0": num(d.K_TD**2), "v_land": num(d.V_LAND), "t_ramp": num(d.T_RAMP)})
    D.node("Mission", "project:Waypoints", 1120, 40, params=mpar,
           starts={"p_sp": vec(p_start), "armed": "1.0", "motor": "1.0"})
    D.sig("Clock", "y", "Mission", "tm")
    # the touchdown latch reads the peak hold, so an impact between two 50 Hz ticks is kept
    D.sig("Aero", "fc_max", "Mission", "fc")

    D.node("Pos", "project:PosCtrl", 1300, 40,
           params={"m_nom": num(d.M * 0.99), "g0": d.G, "Kp_xy": d.KP_XY, "Kv_xy": d.KV_XY, "Ki_xy": d.KI_XY,
                   "Kd_xy": 0.0, "k_drag": num(d.K_DRAG), "Kp_z": d.KP_Z, "Kv_z": d.KV_Z, "Ki_z": d.KI_Z, "Kd_z": 0.0,
                   "tilt_max": "tilt_limit", "F_max": 25.0},
           starts={"F": num(d.T0), "iv": vec([0.0, 0.0, trim_iv])})
    for p in ("p", "v", "q"):
        D.sig("Nav", p, "Pos", p)
    D.sig("Nav", "yaw", "Pos", "psi")
    for p in ("p_sp", "v_sp", "a_sp", "j_sp", "armed", "contact", "thr"):
        D.sig("Mission", p, "Pos", p)
    D.node("Att", "project:AttCtrl", 1480, 40, params={"K_rp": d.K_ATT, "w_max_rp": 2.2})
    D.sig("Nav", "q", "Att", "q")
    D.sig("Pos", "qd", "Att", "qd")
    D.sig("Pos", "w_ff", "Att", "w_ff")
    D.node("Rate", "project:RateCtrl", 1480, 180,
           params={"Kp": num(d.KP_RATE), "Ki": num(d.KI_RATE), "Ja": d.JA, "k_gyro": 1.0,
                   "tau_max": f"{d.K_M_EST} * cyclic_limit", "i_max": 0.05})
    D.sig("Att", "w_sp", "Rate", "w_sp")
    D.sig("Nav", "w", "Rate", "w")
    D.sig("Rotor", "w", "Rate", "w_rot")
    D.sig("Mission", "armed", "Rate", "armed")
    D.sig("Mission", "contact", "Rate", "ground")
    D.node("Alloc", "project:Alloc", 1300, 180,
           params={"kT": d.K_T, "kM": d.K_M_EST, "A_max": "cyclic_limit", "w_max": 720.0, "T_max": 25.0},
           starts={"w_cmd": num(d.OMEGA0)})
    D.sig("Pos", "F", "Alloc", "F")
    D.sig("Rate", "tau", "Alloc", "tau")
    D.sig("Mission", "armed", "Alloc", "armed")
    D.node("Esc", "project:RotorEsc", 1120, 180,
           params={"Kp": d.KP_ESC, "Ki": d.KI_ESC, "accel_max": d.ACCEL_ESC, "kQ": d.K_Q, "b_m": d.B_M, "Ja": d.JA,
                   "tau_min": num(d.TAU_MIN_ESC), "f_touch": num(d.F_TOUCH), "k_td": num(d.K_TD),
                   "accel_td": num(d.ACCEL_TD)},
           starts={"tau": num(d.Q0 + d.B_M * d.OMEGA0), "w_ref": num(d.OMEGA0), "wr": num(d.OMEGA0),
                   "first": "1.0", "v_bus_s": num(d.V_BUS0)})
    D.sig("Alloc", "w_cmd", "Esc", "w_cmd")
    D.sig("Rotor", "w", "Esc", "w")
    D.sig("Mission", "motor", "Esc", "armed")
    D.sig("Alloc", "cyc_amp", "Esc", "cyc_amp")
    D.sig("Motor", "v_bus", "Esc", "v_bus")
    D.sig("Aero", "fc_max", "Esc", "fc")
    D.node("Drive", "project:CyclicDrive", 940, 180,
           params={"k_t": d.K_MOT, "R_w": d.R_W, "K_c": num(d.K_CUR), "tau_max": 1.6})
    D.sig("Esc", "tau", "Drive", "tau_base")
    D.sig("Alloc", "cyc_x", "Drive", "cyc_x")
    D.sig("Alloc", "cyc_y", "Drive", "cyc_y")
    D.sig("Psi", "y", "Drive", "psi")
    D.sig("Mission", "motor", "Drive", "arm")
    D.sig("Rotor", "w", "Drive", "w")
    D.sig("Motor", "i_m", "Drive", "i")
    D.sig("Esc", "v_bus_s", "Drive", "v_bus")
    D.sig("Drive", "duty", "Motor", "duty")

    D.node("Err", "project:EstError", 1300, 440)
    D.sig("Nav", "p", "Err", "phat")
    D.sig("Nav", "v", "Err", "vhat")
    D.sig("Nav", "q", "Err", "qhat")
    D.sig("Truth", "p", "Err", "p")
    D.sig("Truth", "vw", "Err", "v")
    D.sig("Truth", "q", "Err", "q")
    D.sig("Mission", "p_sp", "Err", "p_sp")
    D.check_layout(name)

    plots = [
        {"id": "p1", "title": "Position and set-point (m)",
         "signals": ["Truth/x", "Truth/y", "Truth/z", "Mission/p_sp[1]", "Mission/p_sp[2]", "Mission/p_sp[3]"]},
        {"id": "p2", "title": "Attitude (rad): roll, pitch, yaw",
         "signals": ["Truth/roll", "Truth/pitch", "Truth/yaw"]},
        {"id": "p3", "title": "Rotor speed (rad/s) and thrust (N)", "signals": ["Rotor/w", "Rotor/T"]},
        {"id": "p4", "title": "Swashplateless actuation: moment request (N m) and cyclic torque components (N m)",
         "signals": ["Rate/tau[1]", "Rate/tau[2]", "Alloc/cyc_x", "Alloc/cyc_y", "Alloc/cyc_amp"]},
        {"id": "p5", "title": "Yaw: rotor drag, fin torque (N m) and yaw rate (rad/s)",
         "signals": ["Rotor/Q", "Fins/Qz", "Truth/wb[3]"]},
        {"id": "p6", "title": "Battery: bus voltage (V), pack current and motor current (A)",
         "signals": ["Motor/BusV/y", "Motor/Ibat/y", "Motor/Imot/y"]},
        {"id": "p7", "title": "Navigation filter errors", "signals": ["Err/pos", "Err/vel", "Err/att"]},
        {"id": "p8", "title": "Tracking error: distance to the set-point (m)", "signals": ["Err/track"]},
        {"id": "p9", "title": "Landing-gear normal force and its peak hold (N), touchdown and flight mode",
         "signals": ["Aero/fc", "Aero/fc_max", "Esc/td", "Mission/contact", "Mission/thr", "Mission/armed",
                     "Mission/motor", "Mission/landed"]},
    ]
    bindings = [
        {"target": "link:body", "property": "pose",
         "signal": ["Truth/q[1]", "Truth/q[2]", "Truth/q[3]", "Truth/q[4]", "Truth/x", "Truth/y", "Truth/z"]},
        {"target": "joint:rotor", "property": "position", "signal": "Psi/y", "gain": 1.0, "offset": 0.0},
    ]
    t_end = T_END_HOVER if hover else T_END_FLIGHT
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": name,
        "$comment": ("Single-propeller swashplateless drone: one motor, a once-per-revolution torque for "
                     "roll/pitch, rotor speed for thrust, no yaw actuator (fins only). Generated by "
                     "design/build_model.py from design/design.py."),
        "diagram": D.doc(),
        "settings": {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": 1e-5, "abstol": 1e-7,
                     "max_step": None, "output": {"mode": "points", "points": int(round(t_end * 100)) + 1},
                     "event_limit": 200000},
        "plots": plots,
        "scene": {"file": "scenes/single-propeller-drone.sdf"},
        "bindings": bindings,
        "parameters": GLOBALS,
        "dashboard": dashboard(hover),
    }


def glob(name, value, unit, description):
    return {"name": name, "value": value, "unit": unit, "description": description}


GLOBALS = [
    glob("wind_x", "0.0", "m/s", "Steady wind, world x"),
    glob("wind_y", "0.0", "m/s", "Steady wind, world y"),
    glob("cyclic_gain", str(d.K_M), "N*m/(N*m)",
         f"Plant: mean hub moment per N m of cyclic torque (the allocation assumes {d.K_M_EST})"),
    glob("cyclic_limit", str(d.A_MAX), "N*m", "Cyclic torque amplitude limit of the allocation"),
    glob("tilt_limit", str(d.TILT_MAX), "rad", "Thrust-vector tilt limit of the position controller"),
]


def dashboard(hover: bool) -> dict:
    def slider(cid, title, param, lo, hi, step, decimals, unit):
        return {"id": cid, "kind": "slider", "size": "1x1", "title": title, "parameter": f"global:{param}",
                "options": {"min": lo, "max": hi, "step": step, "decimals": decimals, "unit": unit}}

    def value(cid, title, signal, decimals, unit):
        return {"id": cid, "kind": "value", "size": "1x1", "title": title, "signals": [signal],
                "options": {"decimals": decimals, "unit": unit, "sparkline": True}}

    return {"autoRerun": False, "cards": [
        {"id": "intro", "kind": "text", "size": "2x1", "title": "Single propeller, no servos", "options": {"markdown": True, "text":
            "One motor makes the thrust **and** the roll/pitch moments: the motor torque is modulated "
            "once per revolution, the rotor speeds up and slows down within each turn, and the lag-pitch "
            "hinges turn that into a cyclic blade pitch. **Yaw has no actuator**; the fins carry the motor "
            "reaction and damp the yaw rate. `cyclic_gain` is the plant's gain; the controller keeps "
            "assuming 0.25. Press **Run** after a change."}},
        slider("wx", "Wind x", "wind_x", -3.0, 3.0, 0.1, 1, "m/s"),
        slider("wy", "Wind y", "wind_y", -3.0, 3.0, 0.1, 1, "m/s"),
        slider("km", "Cyclic gain (plant)", "cyclic_gain", 0.10, 0.40, 0.01, 2, "N m/N m"),
        slider("am", "Cyclic limit", "cyclic_limit", 0.2, 1.0, 0.05, 2, "N m"),
        value("alt", "Altitude", "Truth/z", 3, "m"),
        {"id": "tilt", "kind": "gauge", "size": "1x1", "title": "Tilt", "signals": ["Truth/tilt"],
         "options": {"min": 0.0, "max": 0.4, "decimals": 3, "unit": "rad",
                     "zones": [{"from": 0.0, "to": 0.2, "tone": "good"},
                               {"from": 0.2, "to": 0.3, "tone": "warn"},
                               {"from": 0.3, "to": 0.4, "tone": "bad"}]}},
        {"id": "rotor", "kind": "gauge", "size": "1x1", "title": "Rotor speed", "signals": ["Rotor/w"],
         "options": {"min": 0.0, "max": 720.0, "decimals": 0, "unit": "rad/s",
                     "zones": [{"from": 0.0, "to": 640.0, "tone": "good"},
                               {"from": 640.0, "to": 700.0, "tone": "warn"},
                               {"from": 700.0, "to": 720.0, "tone": "bad"}]}},
        value("yawrate", "Yaw rate", "Truth/wb[3]", 3, "rad/s"),
        value("track", "Distance to set-point", "Err/track", 3, "m"),
        {"id": "plot_pos", "kind": "plot", "size": "4x2", "title": "Position and set-point (m)",
         "signals": ["Truth/x", "Truth/y", "Truth/z", "Mission/p_sp[1]", "Mission/p_sp[2]", "Mission/p_sp[3]"]},
        {"id": "plot_cyc", "kind": "plot", "size": "4x2", "title": "Moment request and cyclic torque (N m)",
         "signals": ["Rate/tau[1]", "Rate/tau[2]", "Alloc/cyc_amp"]},
        {"id": "plot_yaw", "kind": "plot", "size": "4x2", "title": "Yaw: rate (rad/s) and torque (N m)",
         "signals": ["Truth/wb[3]", "Rotor/Q", "Fins/Qz"]},
    ]}


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


def build_scene() -> str:
    """The scene from the same numbers as the model: body tube, fins, feet and rotor are where
    design.py puts them (body frame at the CoM)."""
    out = []
    out.append('''<?xml version="1.0"?>
<!--
  single-propeller-drone: a swashplateless mono-rotor. One motor on top of a finned body tube; no
  servos. The four red fins sit in the rotor slipstream (inside the contracted wake) at their
  trim incidence and carry the motor reaction. The body link is the airframe frame at the centre
  of mass (x forward, y left, z up); its pose is bound to the seven pose signals. The propeller
  link turns about body z on joint "rotor", bound to the rotor azimuth. Every dimension comes from
  design/design.py (generated by design/build_model.py).

  Z-up, metres.
-->
<sdf version="1.9">
  <model name="single_propeller_drone">
    <link name="ground">
      <pose>0 0 0 0 0 0</pose>
''')
    out.append(_visual("floor", _box(4.0, 4.0, 0.02), (0.75, 0.75, -0.01, 0, 0, 0), "0.62 0.64 0.66 1"))
    out.append(_visual("pad", _cyl(0.30, 0.006), (0.0, 0.0, 0.003, 0, 0, 0), "0.2 0.6 0.3 1"))
    out.append(_visual("pad_land", _cyl(0.30, 0.006), (1.5, 1.5, 0.003, 0, 0, 0), "0.9 0.75 0.2 1"))
    out.append("    </link>\n\n    <link name=\"body\">\n      <pose>0 0 0 0 0 0</pose>\n")
    zb = d.Z_BODY_C
    out.append(_visual("fuselage", _cyl(d.R_BODY, d.H_BODY), (0, 0, zb, 0, 0, 0), "0.72 0.12 0.10 1"))
    out.append(_visual("nose", _box(0.03, 0.04, 0.03), (d.R_BODY, 0, zb + 0.06, 0, 0, 0), "0.12 0.12 0.14 1"))
    out.append(_visual("beacon", _cyl(0.015, 0.012), (0.0, 0.0, zb + d.H_BODY / 2 + 0.006, 0, 0, 0), "0.05 0.05 0.05 1"))
    out.append(_visual("mount", _cyl(0.012, d.Z_STATOR - (zb + d.H_BODY / 2)),
                       (0, 0, 0.5 * (d.Z_STATOR + zb + d.H_BODY / 2), 0, 0, 0), "0.3 0.3 0.32 1"))
    for k in range(4):
        phi = k * math.pi / 2
        rx, ry = d.R_FIN * math.cos(phi), d.R_FIN * math.sin(phi)
        # a plate: span along e_r, chord along z, thickness along e_t; turned by the incidence
        # about the span axis. The viewer composes Rz(yaw) Ry(pitch) Rx(roll), so a roll of -delta
        # puts the plate normal at cos(delta) e_t - sin(delta) e_z, FinSet's normal
        out.append(_visual(f"fin_{k + 1}", _box(d.FIN_SPAN, 0.004, d.FIN_CHORD),
                           (rx, ry, d.Z_FIN, -d.DELTA_FIN, 0, phi), "0.78 0.10 0.08 1"))
    zbot = zb - d.H_BODY / 2
    for k, (fx, fy) in enumerate(d.feet, start=1):
        strut = math.sqrt(fx * fx + fy * fy + (zbot - d.Z_FOOT - d.FOOT_R) ** 2)
        tilt = math.atan2(math.hypot(fx, fy), zbot - d.Z_FOOT - d.FOOT_R)
        out.append(_visual(f"strut_{k}", _cyl(0.004, strut),
                           (fx / 2, fy / 2, 0.5 * (zbot + d.Z_FOOT + d.FOOT_R), tilt, 0, math.atan2(fy, fx) + math.pi / 2),
                           "0.1 0.1 0.1 1"))
        # the contact point is the sphere's lowest point
        out.append(_visual(f"foot_{k}", f"<sphere><radius>{d.FOOT_R:.5g}</radius></sphere>",
                           (fx, fy, d.Z_FOOT + d.FOOT_R, 0, 0, 0), "0.08 0.08 0.08 1"))
    out.append(_visual("motor", _cyl(0.025, 0.03), (0.0, 0.0, d.Z_STATOR, 0, 0, 0), "0.55 0.55 0.58 1"))
    out.append(_visual("motor_bell", _cyl(d.R_BELL, 0.014), (0.0, 0.0, d.Z_ROTOR - 0.012, 0, 0, 0), "0.25 0.25 0.27 1"))
    out.append("    </link>\n")
    out.append(f'\n    <link name="propeller">\n      <pose>0 0 {d.Z_ROTOR:.5g} 0 0 0</pose>\n')
    out.append(_visual("hub", _cyl(0.014, 0.012), (0, 0, 0.0, 0, 0, 0), "0.1 0.1 0.1 1"))
    out.append(_visual("blades", _box(2 * d.R_PROP, 0.020, 0.0035), (0, 0, 0.0, 0, 0, 0), "0.08 0.08 0.09 1"))
    out.append(_visual("tip_a", _box(0.04, 0.021, 0.004), (d.R_PROP - 0.02, 0, 0.0, 0, 0, 0), "0.95 0.45 0.05 1"))
    out.append(_visual("tip_b", _box(0.04, 0.021, 0.004), (-(d.R_PROP - 0.02), 0, 0.0, 0, 0, 0), "0.2 0.2 0.22 1"))
    out.append("    </link>\n")
    out.append('\n    <joint name="rotor" type="continuous">\n      <parent>body</parent>\n'
               '      <child>propeller</child>\n      <axis><xyz>0 0 1</xyz></axis>\n    </joint>\n')
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


def write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    write_json(ROOT / "library" / "Leg.bgsub.json", leg_definition())
    write_json(ROOT / "library" / "Motor.bgsub.json", motor_definition())
    flight = build("single-propeller-drone", hover=False)
    write_json(ROOT / "models" / "single-propeller-drone.bgmodel.json", flight)
    hover = build("single-propeller-drone-hover", hover=True)
    hover["$comment"] = (f"The same vehicle released in hover at {HOVER_Z} m with a {YAW_KICK} rad/s yaw kick and a "
                         f"{ROLL_KICK} rad/s roll kick, then a {d.STEP_DX:g} m lateral step from {d.STEP_T0:g} s, {T_END_HOVER:g} s: the control and passive-yaw "
                         "test. Generated by design/build_model.py.")
    write_json(ROOT / "models" / "single-propeller-drone-hover.bgmodel.json", hover)
    (ROOT / "scenes" / "single-propeller-drone.sdf").write_text(build_scene(), encoding="utf-8", newline="\n")
    n = len(flight["diagram"]["nodes"])
    print(f"wrote Leg.bgsub.json, Motor.bgsub.json, two models ({n} top-level nodes) and the scene")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
