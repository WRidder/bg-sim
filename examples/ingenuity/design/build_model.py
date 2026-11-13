# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Generate the models, the 3D scene and `expected.json` of the `ingenuity` example from `design.py`.

The four landing-gear feet (`Foot1..4`) are instances of the library subsystem
`library/ContactFoot.bgsub.json`, which this script writes too.

    uv run examples/ingenuity/design/build_model.py

Models (all generated, never hand-edited):

* ``ingenuity``             demonstration flight on Mars: take off, climb to 3 m, fly 5 m east, turn 90 deg,
                            land; dashboard with wind, density and rotor speed.
* ``ingenuity-flight-one``  replica of Flight One (19 April 2021): climb at 1 m/s to 3 m, hover, turn 96 deg,
                            descend at 1 m/s, land; checked against the published flight figures.
* ``ingenuity-rotor-stand`` the coaxial rotor on a fixed stand in the JPL 25-ft Space Simulator (CO2, 0.0175
                            kg/m^3, 2600 rpm): thrust sweep against the measured hover performance and cyclic
                            steps against the measured hub torques.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design as DS  # noqa: E402
import ingenuity_data as D  # noqa: E402
import rotor_ref as RR  # noqa: E402

ROOT = HERE.parent


def num(v: float) -> str:
    return repr(float(v))


def vec(v) -> str:
    return "[" + ", ".join(num(x) for x in v) + "]"


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[tuple] = []
        self.annotations: list[dict] = []
        self.ids: dict[str, str] = {}

    def node(self, name, block, x, y, params=None, starts=None, constants=None) -> str:
        assert name not in self.ids, name
        nid = f"n{len(self.nodes) + 1:03d}"
        b = {"junction": block} if block in ("0", "1") else {"ref": block}
        self.nodes.append({
            "id": nid, "name": name, "block": b, "position": {"x": int(x), "y": int(y)}, "rotation": 0,
            "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self.ids[name] = nid
        return name

    def sig(self, a, pa, b, pb):
        self.connections.append(("signal", a, pa, b, pb))

    def bond(self, a, pa, b, pb=None):
        self.connections.append(("bond", a, pa, b, pb))

    def note(self, text, x, y, w, h, color=None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def doc(self) -> dict:
        conns = []
        for k, (kind, a, pa, b, pb) in enumerate(self.connections):
            frm = {"node": self.ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self.ids[b]}
            if pb is not None:
                to["port"] = pb
            conns.append({"id": f"c{k + 1:03d}", "kind": kind, "from": frm, "to": to, "route": [], "label": None})
        return {"nodes": self.nodes, "connections": conns, "subsystemPorts": [], "annotations": self.annotations}


def glob(name, value, unit, description):
    return {"name": name, "value": value if isinstance(value, str) else num(value), "unit": unit,
            "description": description}


def settings(t_end: float, per_s: int = 100) -> dict:
    return {"t_start": 0.0, "t_end": float(t_end), "solver": "auto", "reltol": 1e-5, "abstol": 1e-7,
            "max_step": None, "output": {"mode": "points", "points": int(t_end * per_s) + 1}, "event_limit": 1000000}


# ----------------------------------------------------------------------------- shared pieces
DES = DS.build()
DES["comparisons"] = DS.comparisons(DES)
MP = DES["mass"]
ZCG = MP["z_cg"]
BL = DES["blade"]
NS = len(BL["y"])
SERVO_W0 = 2.0 * math.pi * D.SERVO_BW_HZ
ROTORS = (("U", "upper", DS.SPIN_UPPER, MP["z_upper"]), ("L", "lower", DS.SPIN_LOWER, MP["z_lower"]))
FEET = [(sx * MP["foot"][0], sy * MP["foot"][1]) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
STAND_SUPPLY_V = 25.2     # the stand runs on a supply at the pack's full-charge voltage [EST]
CONTACT = {"k": 20000.0, "xref": 1.0e-3, "c": 5.0, "mu": 0.8, "vs": 1.0e-3, "eps": 1.0e-6}


def aero_params(spin: float) -> dict:
    p = DES["polar"]
    return {"rho": "rho", "spin": num(spin), "nb": num(D.NB), "R": num(D.RADIUS), "a": num(D.CL_ALPHA),
            "alpha0": num(math.radians(D.ALPHA_0_DEG)), "kappa": num(D.KAPPA), "d0": num(p["d0"]), "d2": num(p["d2"]),
            "clm": num(p["clm"]), "edge": num(D.EDGEWISE_GAIN), "k_q": num(DES["k_q"]),
            "y": vec(BL["y"]), "c": vec(BL["c"]), "tw": vec(BL["tw"]), "lf": vec(BL["lf"]), "wd": vec(BL["wd"])}


def propulsion(d: Diagram, carrier: str | None, x0: float, y0: float, stand: bool = False) -> None:
    """Two motor/rotor chains as bond graphs, the rotor aerodynamics and (in flight) the hub wrenches."""
    m = DES["motor"]
    d.node("RpmSet", "stdlib:sources/Constant", x0 - 200, y0 + 380, params={"value": "rpm_set * pi / 30"})
    for k, (tag, label, spin, z) in enumerate(ROTORS):
        x, y = x0, y0 + 760 * k
        # electrical side: MSe (winding voltage) -- 1 -- R (winding + drive losses), Df (current), GY (k_t)
        d.node(f"Supply{tag}", "stdlib:bondgraph/MSe", x, y + 120)
        d.node(f"Elec{tag}", "1", x + 140, y + 120)
        d.node(f"Rw{tag}", "stdlib:bondgraph/R", x + 140, y + 240, params={"r": num(m["R_w"])})
        d.node(f"Amp{tag}", "stdlib:bondgraph/Df", x + 140, y)
        d.node(f"Motor{tag}", "stdlib:bondgraph/GY", x + 300, y + 120, params={"r": num(m["k_t"])})
        d.bond(f"Supply{tag}", "p", f"Elec{tag}")
        d.bond(f"Elec{tag}", None, f"Rw{tag}", "p")
        d.bond(f"Elec{tag}", None, f"Amp{tag}", "p")
        d.bond(f"Elec{tag}", None, f"Motor{tag}", "p1")
        # mechanical side: 1-junction at the rotor speed relative to the airframe
        d.node(f"Shaft{tag}", "1", x + 460, y + 120)
        d.node(f"Rotor{tag}", "stdlib:spatial/Rotor3D", x + 620, y + 120, params={"Ja": num(MP["Ja"])},
               starts={"h": f"{num(spin * MP['Ja'])} * rpm_set * pi / 30"})
        d.node(f"Aero{tag}", "project:RotorBEMT", x + 460, y + 300, params=aero_params(spin), constants={"NS": NS})
        d.bond(f"Motor{tag}", "p2", f"Shaft{tag}")
        d.bond(f"Shaft{tag}", None, f"Rotor{tag}", "drive")
        d.bond(f"Shaft{tag}", None, f"Aero{tag}", "shaft")
        if stand:
            d.node(f"Stand{tag}", "stdlib:multibond/GroundSpatial", x + 620, y - 120)
            d.node(f"StandMount{tag}", "stdlib:multibond/FixedTransform3DNeutral", x + 780, y - 120)
            d.bond(f"Stand{tag}", "p", f"StandMount{tag}", "b")
            d.bond(f"StandMount{tag}", "a", f"Rotor{tag}", "p")
        else:
            d.bond(carrier, "p", f"Rotor{tag}", "p")
            # hub wrench: thrust, H-force and hub moments at the hub, through the mount's lever arm
            d.node(f"Hub{tag}", "stdlib:multibond/FixedTransform3DNeutral", x + 780, y + 300,
                   params={"x": "0.0", "y": "0.0", "z": num(-(z - ZCG))})
            d.node(f"HubWrench{tag}", "stdlib:multibond/ExternalWrenchSpatial", x + 640, y + 300)
            # sources point at the body: wrench -> mount.a, mount.b -> body
            d.bond(f"HubWrench{tag}", "p", f"Hub{tag}", "a")
            d.bond(f"Hub{tag}", "b", carrier, "p")
            for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
                d.sig(f"Aero{tag}", p, f"HubWrench{tag}", p)
        # rotor-speed governor
        d.node(f"Gov{tag}", "project:RotorGovernor", x - 160, y + 120,
               params={"spin": num(spin), "k_e": num(m["k_t"]), "Kp": num(m["Kp"]), "Ki": num(m["Ki"]),
                       "u_max": num(STAND_SUPPLY_V if stand else D.BATTERY_V)})
        d.sig(f"Rotor{tag}", "w_rel", f"Gov{tag}", "w")
        d.sig(f"Amp{tag}", "y", f"Gov{tag}", "i")
        d.sig("RpmSet", "y", f"Gov{tag}", "wset")
        d.sig(f"Gov{tag}", "u", f"Supply{tag}", "u")
        # swashplate servos (second order, 12 Hz, 85 % damping: Grip et al. 2018)
        for j, ch in enumerate(("Coll", "CycX", "CycY")):
            d.node(f"{ch}{tag}", "stdlib:continuous/SecondOrder", x + 200, y + 360 + 70 * j,
                   params={"k": "1.0", "w0": num(SERVO_W0), "zeta": num(D.SERVO_ZETA)},
                   starts={"x1": num(DES["th_idle"]) if ch == "Coll" else "0.0"})
        d.sig(f"Coll{tag}", "y", f"Aero{tag}", "theta")
        d.sig(f"CycX{tag}", "y", f"Aero{tag}", "cx")
        d.sig(f"CycY{tag}", "y", f"Aero{tag}", "cy")
        # rotor angle for the 3D view
        d.node(f"Angle{tag}", "stdlib:continuous/Integrator", x + 780, y + 120)
        d.sig(f"Rotor{tag}", "w_rel", f"Angle{tag}", "u")
    d.sig("AeroU", "v0", "AeroL", "vext")
    d.node("NoWake", "stdlib:sources/Constant", x0 + 300, y0 + 700, params={"value": "0.0"})
    d.sig("NoWake", "y", "AeroU", "vext")
    d.node("Telem", "project:Telemetry", x0 + 1000, y0 + 380, params={"rho": "rho", "R": num(D.RADIUS)})
    for p, src in (("Tu", ("AeroU", "T")), ("Tl", ("AeroL", "T")), ("Pu", ("AeroU", "P")), ("Pl", ("AeroL", "P")),
                   ("Pu_el", ("GovU", "P_el")), ("Pl_el", ("GovL", "P_el")), ("th_u", ("CollU", "y")),
                   ("th_l", ("CollL", "y")), ("cx", ("CycXL", "y")), ("cy", ("CycYL", "y")), ("speed_rpm", ("AeroL", "speed_rpm"))):
        d.sig(src[0], src[1], "Telem", p)
    d.note("**Propulsion (bond graph, one chain per rotor).** Electrical 1-junction: the winding voltage (MSe, "
           "set by the rotor-speed governor), the winding and drive losses (R), a current detector (Df) and the "
           "motor gyrator (GY, k_t). Shaft 1-junction at the rotor speed relative to the airframe: the motor, "
           "the rotor's axial momentum (Rotor3D, bonded to the airframe body: its torque reaction and gyroscopic "
           "moment act on the airframe) and the blade-element/momentum aerodynamics (RotorBEMT, a nonlinear R). "
           "The thrust, H-force and hub moments act on the airframe at the hub (Hub mount + HubWrench). The lower "
           "rotor sees the upper rotor's uniform inflow (AeroU.v0 -> AeroL.vext).", x0 - 200, y0 - 200, 1100, 90,
           "blue")


def airframe(d: Diagram) -> None:
    d.node("World", "stdlib:multibond/GroundSpatial", 40, 420)
    d.node("Free", "stdlib:spatial/Free3D", 220, 420, starts={"pz": num(ZCG)})
    d.node("Body", "stdlib:spatial/RigidBody3D", 420, 420,
           params={"m": num(MP["m"]), "J": vec(MP["J"]), "g0": num(D.G_MARS)},
           starts={"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
    d.bond("World", "p", "Free", "parent")
    d.bond("Free", "child", "Body", "p")
    for k in range(1, 7):
        d.node(f"FreeSe{k}", "stdlib:bondgraph/Se", 220, 560 + 50 * k, params={"e": "0.0"})
        d.bond(f"FreeSe{k}", "p", "Free", f"drive{k}")
    d.sig("Free", "pose", "Body", "g")
    # airframe drag at the fuselage centre
    d.node("Air", "project:AirDrag", 620, 560, params={"rho": "rho", "wind": "[wind_e, wind_n, 0.0]", "CdA": num(D.DRAG_AREA)})
    d.sig("Free", "pose", "Air", "pose")
    d.sig("Body", "V", "Air", "V")
    d.node("DragMount", "stdlib:multibond/FixedTransform3DNeutral", 620, 760,
           params={"x": "0.0", "y": "0.0", "z": num(-(MP["z_fuse"] - ZCG))})
    d.node("DragWrench", "stdlib:multibond/ExternalWrenchSpatial", 800, 760)
    d.node("Zero", "stdlib:sources/Constant", 800, 860, params={"value": "0.0"})
    d.bond("DragWrench", "p", "DragMount", "a")
    d.bond("DragMount", "b", "Body", "p")
    for p in ("tx", "ty", "tz"):
        d.sig("Zero", "y", "DragWrench", p)
    for p in ("fx", "fy", "fz"):
        d.sig("Air", p, "DragWrench", p)
    # landing gear: four feet (ContactFoot instances), compliant Hunt-Crossley contacts with friction on the
    # Mars ground plane
    d.node("Ground", "stdlib:contact/ContactSurface", 40, 1100)
    for k, (fx, fy) in enumerate(FEET, start=1):
        d.node(f"Foot{k}", "project:ContactFoot", 220 + 200 * ((k - 1) % 2), 1100 + 200 * ((k - 1) // 2),
               params={"Local/x": num(fx), "Local/y": num(fy), "Local/z": num(-ZCG),
                       "Mount/x": num(-fx), "Mount/y": num(-fy), "Mount/z": num(ZCG)})
        d.bond("Body", "p", f"Foot{k}", "p")
        d.sig("Free", "pose", f"Foot{k}", "pose")
        d.sig("Ground", "o", f"Foot{k}", "o")
        d.sig("Ground", "fr", f"Foot{k}", "fr")
    d.node("Nav", "project:Nav", 620, 300, params={"z_rest": num(ZCG)})
    d.sig("Free", "pose", "Nav", "pose")
    d.sig("Body", "V", "Nav", "V")
    d.note("**Airframe (3D multibond).** World -> Free3D (6 DOF, quaternion pose) -> RigidBody3D (mass, apparent "
           "roll/pitch inertia, Mars gravity). Everything that acts on the airframe is bonded to the body's "
           "1-junction: the rotors (Rotor3D), the hub wrenches and the drag wrench through fixed mounts at the hub "
           "and fuselage centre, and the four landing-gear contacts through mounts at the feet.", 20, 200, 760, 70,
           "blue")


def controller(d: Diagram, plan: dict) -> None:
    g = DES["gains"]
    h = DES["hover"]
    d.node("Clock", "stdlib:sources/Time", 1500, -200)
    d.node("Plan", "project:FlightPlan", 1700, -200, params=plan)
    d.sig("Clock", "y", "Plan", "tm")
    d.node("Ctrl", "project:FlightControl", 1900, -200, params={
        "m": num(MP["m"]), "g0": num(D.G_MARS), "Ixx": num(MP["J"][0]), "Iyy": num(MP["J"][1]), "Izz": num(MP["J"][2]),
        "th_hover": num(h["th_s"]), "th_a_trim": num(h["th_a"]), "th_idle": num(DES["th_idle"]),
        "Z_th": num(DES["Z_th"]), "N_th": num(DES["N_th"]), "k_c": num(DES["k_c"]),
        "Kp_z": num(g["heave"][0]), "Kd_z": num(g["heave"][1]), "Ki_z": num(g["heave"][2]),
        "Kp_psi": num(g["yaw"][0]), "Kd_psi": num(g["yaw"][1]), "Ki_psi": num(g["yaw"][2]),
        "Kp_att": num(g["att"][0]), "Kd_att": num(g["att"][1]), "Ki_att": num(g["att"][2]),
        "Kp_xy": num(g["pos"][0]), "Kd_xy": num(g["pos"][1]), "Ki_xy": num(g["pos"][2]),
        "th_min": num(math.radians(D.COLL_MIN_DEG)), "th_max": num(math.radians(D.COLL_MAX_DEG)),
        "cyc_max": num(math.radians(D.CYC_MAX_DEG))})
    for p in ("p_sp", "v_sp", "a_sp", "psi_sp", "psi_rate", "mode"):
        d.sig("Plan", p, "Ctrl", p)
    for p in ("p", "vw", "wb", "roll", "pitch", "yaw"):
        d.sig("Nav", p, "Ctrl", p)
    d.sig("Ctrl", "th_u", "CollU", "u")
    d.sig("Ctrl", "th_l", "CollL", "u")
    for tag in ("U", "L"):
        d.sig("Ctrl", "cx", f"CycX{tag}", "u")
        d.sig("Ctrl", "cy", f"CycY{tag}", "u")
    d.note("**Flight software.** FlightPlan (waypoint moves, climb and descent at 1 m/s) -> FlightControl (500 Hz: "
           "heave and yaw by symmetric and antisymmetric collective, inner roll/pitch on cyclic, outer horizontal "
           "position; Grip et al. 2018). Nav reads the pose: the navigation estimate is taken as perfect.",
           1500, -360, 700, 70, "blue")


def air_va(d: Diagram) -> None:
    for tag in ("U", "L"):
        d.sig("Air", "va", f"Aero{tag}", "va")
        d.sig("Air", "wb", f"Aero{tag}", "wb")


# ----------------------------------------------------------------------------- flight plans
# the demonstration flight: climb to `alt` at 1 m/s peak, 5 m east in 8 s (1.17 m/s peak), turn 90 deg,
# descend at 1 m/s peak and land (the set-point ends 5 cm below the rest height: the gear takes the weight)
DEMO = {
    "moves": [(1.0, "1.875 * alt", "0.0", 0.0, "alt", 0.0),
              (9.0, 8.0, "dist", 0.0, "0.0", 0.0),
              (17.5, 3.0, "0.0", 0.0, "0.0", math.pi / 2),
              (21.5, "1.875 * (alt + 0.05)", "0.0", 0.0, "-(alt + 0.05)", 0.0)],
    "t_takeoff": 1.0, "t_cut": "21.5 + 1.875 * (alt + 0.05) + 0.3", "t_end": 30.0,
}
# Flight One, 19 April 2021: climb to 3 m, hover, turn 96 deg, descend at 1 m/s; 39.1 s in the air (NASA)
FLIGHT1 = {
    "moves": [(1.0, 5.625, "0.0", 0.0, "3.0", 0.0),
              (12.0, 6.0, "0.0", 0.0, "0.0", math.radians(96.0)),
              (35.7, 5.71875, "0.0", 0.0, "-3.05", 0.0)],
    "t_takeoff": 1.0, "t_cut": "41.7", "t_end": 44.0,
}


def plan_from(spec) -> dict:
    moves = [(m[0], m[1], m[2], m[3], m[4], m[5]) for m in spec["moves"]]
    W = 8
    moves = moves + [(99.0, 1.0, "0.0", 0.0, "0.0", 0.0)] * (W - len(moves))
    def col(i, numeric=True):
        return "[" + ", ".join(num(m[i]) if not isinstance(m[i], str) else m[i] for m in moves) + "]"
    return {"p0": f"[0.0, 0.0, {num(ZCG)}]", "ts": col(0), "dur": col(1), "dx": col(2), "dy": col(3),
            "dz": col(4), "dpsi": col(5), "t_takeoff": num(spec["t_takeoff"]), "t_cut": spec["t_cut"]}


# ----------------------------------------------------------------------------- the flight models
def flight_globals(wind_e: float = 0.0, wind_n: float = 0.0) -> list[dict]:
    return [
        glob("rho", D.RHO_FLIGHT1, "kg/m^3", "Air density (Flight One: 0.0165; design range 0.014-0.02)"),
        glob("rpm_set", D.RPM_FLIGHT1, "1/min", "Rotor speed set point (flights 1-13: 2537 rpm; later 2700)"),
        glob("wind_e", wind_e, "m/s", "Wind towards the east (world +x)"),
        glob("wind_n", wind_n, "m/s", "Wind towards the north (world +y)"),
    ]


# Flight One's wind: 4-6 m/s from the east/south-east, gusting to 8 (NASA21). The replica flies in a steady
# 5 m/s from the east-south-east (bearing 112.5 deg), i.e. blowing towards the west-north-west.
WIND1 = 5.0
WIND1_E, WIND1_N = -WIND1 * math.sin(math.radians(112.5)), -WIND1 * math.cos(math.radians(112.5))

FLIGHT_PLOTS = [
    {"id": "p1", "title": "Altitude above the take-off rest and set-point (m)", "signals": ["Nav/alt", "Plan/alt_sp"]},
    {"id": "p2", "title": "Position east / north (m)", "signals": ["Nav/x", "Nav/y", "Plan/p_sp[1]", "Plan/p_sp[2]"]},
    {"id": "p3", "title": "Heading (deg)", "signals": ["Nav/yaw_deg"]},
    {"id": "p4", "title": "Collective, upper and lower rotor (deg)", "signals": ["Telem/coll_u_deg", "Telem/coll_l_deg"]},
    {"id": "p5", "title": "Electrical and shaft power of the rotors (W)", "signals": ["Telem/P_el", "Telem/P_shaft"]},
    {"id": "p6", "title": "Thrust: upper, lower, total (N)", "signals": ["AeroU/T", "AeroL/T", "Telem/T"]},
    {"id": "p7", "title": "Rotor speed (rpm)", "signals": ["GovU/speed_rpm", "GovL/speed_rpm"]},
    {"id": "p8", "title": "Roll and pitch (rad) with the inner-loop set-points",
     "signals": ["Nav/roll", "Nav/pitch", "Ctrl/roll_d", "Ctrl/pitch_d"]},
    {"id": "p9", "title": "Cyclic amplitude (deg)", "signals": ["Telem/cyc_deg"]},
    {"id": "p10", "title": "Landing-gear normal forces (N)", "signals": [f"Foot{k}/Contact/f_n" for k in range(1, 5)]},
]


def bindings() -> list[dict]:
    b = [{"target": "link:body", "property": "pose",
          "signal": ["Nav/q[1]", "Nav/q[2]", "Nav/q[3]", "Nav/q[4]", "Nav/x", "Nav/y", "Nav/z"]}]
    # the rotors turn at about 42 rev/s: shown at 1/40 of the true angle so the counter-rotation is visible
    for tag, label, spin, _ in ROTORS:
        b.append({"target": f"joint:rotor_{label}", "property": "position", "signal": f"Angle{tag}/y",
                  "gain": SPIN_DISPLAY, "offset": 0.0})
    return b


SPIN_DISPLAY = 0.025


# ----------------------------------------------------------------------------- the library subsystem
def contact_foot_definition() -> dict:
    """library/ContactFoot.bgsub.json: one landing-gear foot. The local pose and the mount carry the body
    to the foot point; the compliant contact point presses on the ground plane given at `o`/`fr`."""
    def node(name, ref, x, y, params=None):
        return {"id": name, "name": name, "block": {"ref": ref}, "position": {"x": x, "y": y}, "rotation": 0,
                "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()}, "constants": {},
                "starts": {}, "ui": {"showLabel": True, "color": None}}

    def conn(k, kind, a, pa, b, pb):
        return {"id": f"contactfoot_{kind[0]}{k:03d}", "kind": kind, "from": {"node": a, "port": pa},
                "to": {"node": b, "port": pb}, "route": [], "label": None}

    def port(name, direction, node_, p, unit=None, size=1):
        return {"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
                "unit": unit, "node": node_, "port": p}

    return {
        "format": "bgsim.subsystem", "name": "ContactFoot",
        "description": ("One landing-gear foot: the foot point in the body frame (Local), its world pose (Compose), the "
                        "fixed mount from the body to the foot (Mount) and a compliant Hertz contact point with friction "
                        "(Contact) on the ground plane given at o and fr. Pin the foot position with Local/x, Local/y, "
                        "Local/z and the mount with Mount/x, Mount/y, Mount/z (the negated offsets). Generated by "
                        "design/build_model.py."),
        "ports": [{"name": "p", "kind": "power", "domain": "Spatial", "size": [6], "node": "Mount", "port": "b"},
                  port("pose", "input", "Compose", "gp", size=7),
                  port("o", "input", "Contact", "o", unit="m", size=3),
                  port("fr", "input", "Contact", "fr", unit="1", size=9),
                  port("f_n", "output", "Contact", "f_n", unit="N")],
        "diagram": {
            "nodes": [node("Local", "stdlib:spatial/LocalPose3D", 0, 0, {"x": "0.0", "y": "0.0", "z": num(-ZCG)}),
                      node("Compose", "stdlib:multibond/ComposePose3D", 160, 0),
                      node("Mount", "stdlib:multibond/FixedTransform3DNeutral", 0, 180,
                           {"x": "0.0", "y": "0.0", "z": num(ZCG)}),
                      node("Contact", "stdlib:contact/ContactPoint", 320, 120, CONTACT)],
            "connections": [conn(1, "bond", "Mount", "a", "Contact", "p"),
                            conn(2, "signal", "Local", "g", "Compose", "gl"),
                            conn(3, "signal", "Compose", "g", "Contact", "g")],
            "subsystemPorts": [], "annotations": []},
        "pins": {"params": ["Local/x", "Local/y", "Local/z", "Mount/x", "Mount/y", "Mount/z"], "starts": []},
    }


def flight_model(name: str, comment: str, spec: dict, globals_: list[dict], dashboard: dict | None) -> dict:
    d = Diagram()
    airframe(d)
    propulsion(d, "Body", 1100, 300)
    air_va(d)
    controller(d, plan_from(spec))
    doc = {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
           "diagram": d.doc(), "settings": settings(spec["t_end"]), "plots": FLIGHT_PLOTS,
           "scene": {"file": "scenes/ingenuity.sdf"}, "bindings": bindings(), "parameters": globals_}
    if dashboard:
        doc["dashboard"] = dashboard
    return doc


def slider(cid, title, param, lo, hi, step, decimals, unit):
    return {"id": cid, "kind": "slider", "size": "1x1", "title": title, "parameter": f"global:{param}",
            "options": {"min": lo, "max": hi, "step": step, "decimals": decimals, "unit": unit}}


def value(cid, title, signal, decimals, unit):
    return {"id": cid, "kind": "value", "size": "1x1", "title": title, "signals": [signal],
            "options": {"decimals": decimals, "unit": unit, "sparkline": True}}


def text(cid, title, body):
    return {"id": cid, "kind": "text", "size": "2x1", "title": title, "options": {"markdown": True, "text": body}}


def plot(cid, title, signals):
    return {"id": cid, "kind": "plot", "size": "4x2", "title": title, "signals": signals}


def flight_one_dashboard() -> dict:
    return {"autoRerun": False, "cards": [
        text("intro", "Flight One, 19 April 2021",
             "Climb to 3 m, hover, turn 96 deg, descend and land in a 5 m/s east-south-east wind. Published: "
             "**210 W** rotor power, collectives **8.2 / 9.2 deg** (upper / lower). Change the wind and press **Run**."),
        slider("wind_e", "Wind towards east", "wind_e", -8.0, 8.0, 0.5, 1, "m/s"),
        slider("wind_n", "Wind towards north", "wind_n", -8.0, 8.0, 0.5, 1, "m/s"),
        value("pel", "Rotor electrical power", "Telem/P_el", 0, "W"),
        value("cu", "Upper collective", "Telem/coll_u_deg", 2, "deg"),
        value("cl", "Lower collective", "Telem/coll_l_deg", 2, "deg"),
        value("hdg", "Heading", "Nav/yaw_deg", 1, "deg"),
        plot("plot_alt", "Altitude and set-point (m)", ["Nav/alt", "Plan/alt_sp"]),
        plot("plot_pow", "Rotor power: electrical and shaft (W)", ["Telem/P_el", "Telem/P_shaft"]),
    ]}


def stand_dashboard() -> dict:
    return {"autoRerun": False, "cards": [
        text("intro", "JPL rotor test",
             "The coaxial rotor on a stand: a thrust sweep, then 5 deg cyclic steps on the lower rotor. "
             "Compare `Telem/CP` with the measured points in `design/jpl_hover_test.json`."),
        slider("rho", "Chamber density", "rho", 0.012, 0.020, 0.0005, 4, "kg/m^3"),
        slider("rpm", "Rotor speed", "rpm_set", 2400.0, 2800.0, 10.0, 0, "rpm"),
        value("ct", "Thrust coefficient", "Telem/CT", 4, ""),
        value("cp", "Power coefficient", "Telem/CP", 5, ""),
        value("pel", "Electrical power", "Telem/P_el", 0, "W"),
        plot("plot_ct", "Thrust and power coefficient", ["Telem/CT", "Telem/CP"]),
        plot("plot_m", "Lower-rotor hub moments (N m)", ["AeroL/tx", "AeroL/ty"]),
    ]}


def demo_dashboard() -> dict:
    return {"autoRerun": False, "cards": [
        {"id": "intro", "kind": "text", "size": "2x1", "title": "Ingenuity on Mars", "options": {"markdown": True, "text":
            "Take off, climb to the hover altitude, fly east, turn and land. Change the **air density**, the "
            "**rotor speed** or the **wind** and press **Run** (the 30 s flight takes a minute or two)."}},
        slider("rho", "Air density", "rho", 0.012, 0.020, 0.0005, 4, "kg/m^3"),
        slider("rpm", "Rotor speed", "rpm_set", 2400.0, 2800.0, 10.0, 0, "rpm"),
        slider("wind_e", "Wind towards east", "wind_e", -6.0, 6.0, 0.5, 1, "m/s"),
        slider("wind_n", "Wind towards north", "wind_n", -6.0, 6.0, 0.5, 1, "m/s"),
        slider("alt", "Hover altitude", "alt", 1.0, 4.0, 0.25, 2, "m"),
        slider("dist", "Distance east", "dist", 0.0, 10.0, 0.5, 1, "m"),
        value("alt_v", "Altitude", "Nav/alt", 2, "m"),
        value("pel", "Rotor electrical power", "Telem/P_el", 0, "W"),
        {"id": "coll", "kind": "gauge", "size": "1x1", "title": "Lower collective (limit 17.5 deg)",
         "signals": ["Telem/coll_l_deg"],
         "options": {"min": -4.5, "max": 17.5, "decimals": 1, "unit": "deg",
                     "zones": [{"from": -4.5, "to": 13.0, "tone": "good"}, {"from": 13.0, "to": 15.5, "tone": "warn"},
                               {"from": 15.5, "to": 17.5, "tone": "bad"}]}},
        value("cyc", "Cyclic", "Telem/cyc_deg", 2, "deg"),
        {"id": "plot_alt", "kind": "plot", "size": "4x2", "title": "Altitude and set-point (m)",
         "signals": ["Nav/alt", "Plan/alt_sp"]},
        {"id": "plot_pow", "kind": "plot", "size": "4x2", "title": "Rotor power: electrical and shaft (W)",
         "signals": ["Telem/P_el", "Telem/P_shaft"]},
        {"id": "plot_coll", "kind": "plot", "size": "4x2", "title": "Collective upper / lower (deg)",
         "signals": ["Telem/coll_u_deg", "Telem/coll_l_deg"]},
    ]}


# ----------------------------------------------------------------------------- the rotor stand
STAND_RPM = D.RPM_JPL
STAND_CT = [0.0084, 0.0115, 0.0148, 0.0178, 0.0206, 0.0237]
STAND_DT = 2.5
T_CYC = len(STAND_CT) * STAND_DT + 1.0          # cyclic steps after the sweep, at the design thrust


def stand_model() -> dict:
    d = Diagram()
    propulsion(d, None, 400, 200, stand=True)
    d.node("StillU", "stdlib:sources/Constant", 60, 1000, params={"value": "0.0"})
    d.node("StillVec", "stdlib:continuous/Mux3", 220, 1050)
    for k in (1, 2, 3):
        d.sig("StillU", "y", "StillVec", f"u{k}")
    for tag in ("U", "L"):
        d.sig("StillVec", "y", f"Aero{tag}", "va")
        d.sig("StillVec", "y", f"Aero{tag}", "wb")
    cts = STAND_CT + [0.0178, 0.0178]
    t_ct = [STAND_DT * k for k in range(len(STAND_CT))] + [STAND_DT * len(STAND_CT), 99.0]
    d.node("Clock", "stdlib:sources/Time", 60, 40)
    d.node("Stand", "project:StandControl", 220, 40, params={
        "rho": "rho", "omega": "rpm_set * pi / 30", "R": num(D.RADIUS), "t_ct": vec(t_ct), "ct": vec(cts),
        "th0": vec([math.radians(v) for v in (3.0, 5.5, 8.0, 10.5, 12.5, 15.0, 10.5, 10.5)]), "k_track": "1.0",
        "t_cyc": num(T_CYC), "cyc": num(math.radians(5.0))})
    d.sig("Clock", "y", "Stand", "tm")
    d.sig("Telem", "T", "Stand", "T")
    d.sig("AeroU", "Q", "Stand", "Qu")
    d.sig("AeroL", "Q", "Stand", "Ql")
    d.sig("Stand", "th_u", "CollU", "u")
    d.sig("Stand", "th_l", "CollL", "u")
    d.sig("Stand", "cx_l", "CycXL", "u")
    d.sig("Stand", "cy_l", "CycYL", "u")
    d.sig("StillU", "y", "CycXU", "u")
    d.sig("StillU", "y", "CycYU", "u")
    d.note("**Rotor stand (JPL 25-ft Space Simulator).** The coaxial rotor on a fixed stand in CO2 at 0.0175 kg/m^3 "
           "and 2600 rpm (Koning et al. 2019). StandControl steps the thrust coefficient through the measured "
           "range (a PI on the symmetric collective), trims the pair torque-free (differential collective), then "
           "applies 5 deg cyclic steps on the lower rotor, the system-identification sequence of Grip et al. "
           "(2017) Fig. 15.", 20, -120, 900, 70, "blue")
    t_end = T_CYC + 22.0
    plots = [
        {"id": "p1", "title": "Thrust coefficient and target", "signals": ["Telem/CT", "Stand/ct_sp"]},
        {"id": "p2", "title": "Power coefficient", "signals": ["Telem/CP"]},
        {"id": "p3", "title": "Collective upper / lower (deg)", "signals": ["Telem/coll_u_deg", "Telem/coll_l_deg"]},
        {"id": "p4", "title": "Lower-rotor hub moments (N m): roll (x) and pitch (y)", "signals": ["AeroL/tx", "AeroL/ty"]},
        {"id": "p5", "title": "Shaft and electrical power (W)", "signals": ["Telem/P_shaft", "Telem/P_el"]},
        {"id": "p6", "title": "Rotor speed (rpm)", "signals": ["GovU/speed_rpm", "GovL/speed_rpm"]},
    ]
    globals_ = [glob("rho", D.RHO_JPL, "kg/m^3", "Chamber CO2 density (JPL test: 0.0175)"),
                glob("rpm_set", STAND_RPM, "1/min", "Rotor speed (JPL test: 2600 rpm)")]
    return {"format": "bgsim.model", "language": "0.1.0", "name": "ingenuity-rotor-stand",
            "$comment": "Ingenuity's coaxial rotor on a fixed stand at the JPL Space Simulator test conditions. Generated by design/build_model.py.",
            "diagram": d.doc(), "settings": settings(t_end), "plots": plots, "scene": None, "bindings": [],
            "parameters": globals_, "dashboard": stand_dashboard()}


# ----------------------------------------------------------------------------- 3D scene
def _visual(name, geometry, pose, rgba):
    x, y, z, roll, pitch, yaw = pose
    return (f'      <visual name="{name}">\n        <pose>{x:.5g} {y:.5g} {z:.5g} {roll:.7g} {pitch:.7g} {yaw:.7g}</pose>\n'
            f'        <geometry>{geometry}</geometry>\n        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def _box(sx, sy, sz):
    return f"<box><size>{sx:.5g} {sy:.5g} {sz:.5g}</size></box>"


def _cyl(r, h):
    return f"<cylinder><radius>{r:.5g}</radius><length>{h:.5g}</length></cylinder>"


def _sphere(r):
    return f"<sphere><radius>{r:.5g}</radius></sphere>"


def _rod(name, a, b, r, rgba):
    a, b = np.array(a, float), np.array(b, float)
    c = 0.5 * (a + b)
    v = b - a
    L = float(np.linalg.norm(v))
    yaw = math.atan2(v[1], v[0])
    pitch = math.atan2(math.hypot(v[0], v[1]), v[2])      # cylinder axis is z: tilt it by pitch about y, then yaw
    return _visual(name, _cyl(r, L), (c[0], c[1], c[2], 0.0, pitch, yaw), rgba)


def build_scene() -> str:
    rng = np.random.default_rng(2021)
    out = ['''<?xml version="1.0"?>
<!--
  ingenuity: NASA's Mars Helicopter on Jezero-coloured ground. Generated by design/build_model.py from the
  published dimensions (JPL press kit: fuselage 13.6 x 19.5 x 16.3 cm, legs 0.384 m, 13 cm ground clearance,
  1.21 m coaxial rotors 0.103 m apart, 0.49 m overall height) and the estimates of design/design.py.

  Z-up, metres; x east, y north. The link "body" is the airframe frame at the centre of mass, bound to the
  pose signals of the model. The links "rotor_upper_link" and "rotor_lower_link" turn about the mast on the
  continuous joints "rotor_upper" and "rotor_lower", bound to the integrated rotor angles at 1/40 of the true
  rate (about 42 rev/s would only flicker on screen); one blade tip of each rotor is orange. The blue-black
  solar panel sits on the non-rotating mast above the upper rotor. The white pad marks the take-off point,
  the yellow one the point 5 m east.
-->
<sdf version="1.9">
  <model name="ingenuity">
    <link name="ground">
      <pose>0 0 0 0 0 0</pose>
''']
    out.append(_visual("mars_ground", _box(9.0, 7.0, 0.04), (2.5, 0.0, -0.02, 0, 0, 0), "0.69 0.40 0.24 1"))
    out.append(_visual("pad_takeoff", _cyl(0.45, 0.004), (0.0, 0.0, 0.002, 0, 0, 0), "0.85 0.82 0.78 1"))
    out.append(_visual("pad_target", _cyl(0.45, 0.004), (5.0, 0.0, 0.002, 0, 0, 0), "0.88 0.72 0.25 1"))
    k = 0
    while k < 24:
        r = float(rng.uniform(0.02, 0.12))
        x, y = float(rng.uniform(-1.8, 6.8)), float(rng.uniform(-3.3, 3.3))
        if min(math.hypot(x, y), math.hypot(x - 5.0, y)) < 0.9:
            continue
        k += 1
        shade = float(rng.uniform(0.32, 0.48))
        out.append(_visual(f"rock_{k}", _sphere(r), (x, y, 0.35 * r, 0, 0, 0), f"{shade + 0.1:.2f} {shade * 0.75:.2f} {shade * 0.55:.2f} 1"))
    out.append(_visual("ridge", _box(9.0, 0.5, 0.25), (2.5, 3.25, 0.0, 0.1, 0, 0.0), "0.58 0.34 0.21 1"))
    out.append("    </link>\n\n    <link name=\"body\">\n      <pose>0 0 0 0 0 0</pose>\n")
    zf = MP["z_fuse"] - ZCG
    ztop = MP["z_top"] - ZCG
    out.append(_visual("fuselage", _box(D.FUSE_X, D.FUSE_Y, D.FUSE_Z), (0, 0, zf, 0, 0, 0), "0.80 0.78 0.72 1"))
    out.append(_visual("fuselage_band", _box(D.FUSE_X + 0.004, D.FUSE_Y + 0.004, 0.03), (0, 0, zf - 0.04, 0, 0, 0), "0.78 0.55 0.20 1"))
    out.append(_visual("nav_camera", _cyl(0.012, 0.02), (0.02, 0.0, zf - D.FUSE_Z / 2 - 0.008, 0, 0, 0), "0.1 0.1 0.12 1"))
    out.append(_visual("color_camera", _box(0.02, 0.025, 0.02), (D.FUSE_X / 2 + 0.008, 0.0, zf - 0.03, 0, 0, 0), "0.12 0.12 0.14 1"))
    out.append(_visual("antenna", _cyl(0.004, 0.06), (-0.04, 0.06, ztop + 0.03, 0, 0, 0), "0.85 0.85 0.85 1"))
    zs = MP["z_solar"] - ZCG
    out.append(_rod("mast", (0, 0, ztop), (0, 0, zs), 0.011, "0.75 0.76 0.78 1"))
    for tag, label, spin, z in ROTORS:
        out.append(_visual(f"hub_{label}", _cyl(0.03, 0.04), (0, 0, z - ZCG, 0, 0, 0), "0.55 0.56 0.6 1"))
        out.append(_visual(f"swashplate_{label}", _cyl(0.045, 0.008), (0, 0, z - ZCG - 0.03, 0, 0, 0), "0.3 0.3 0.32 1"))
    out.append(_visual("motor_housing", _cyl(0.035, 0.05), (0, 0, 0.5 * (MP["z_lower"] + MP["z_upper"]) - ZCG, 0, 0, 0), "0.22 0.22 0.24 1"))
    out.append(_visual("solar_panel", _box(0.40, 0.165, 0.008), (0, 0, zs, 0, 0, 0), "0.07 0.09 0.20 1"))
    out.append(_visual("solar_frame", _box(0.412, 0.177, 0.005), (0, 0, zs - 0.006, 0, 0, 0), "0.7 0.7 0.72 1"))
    for k in range(1, 5):
        out.append(_visual(f"solar_cell_line_{k}", _box(0.004, 0.16, 0.0085), (-0.24 + 0.096 * k, 0, zs + 0.0005, 0, 0, 0), "0.25 0.27 0.35 1"))
    cx, cy = MP["corner"]
    for k, (fx, fy) in enumerate(FEET, start=1):
        sx, sy = np.sign(fx), np.sign(fy)
        out.append(_rod(f"leg_{k}", (sx * cx, sy * cy, ztop - 0.005), (fx, fy, -ZCG + 0.012), 0.006, "0.12 0.12 0.13 1"))
        out.append(_rod(f"flexure_{k}", (sx * cx, sy * cy, ztop - 0.005), (sx * cx * 1.25, sy * cy * 1.25, ztop - 0.03), 0.009, "0.6 0.6 0.62 1"))
        out.append(_visual(f"foot_{k}", _cyl(0.025, 0.012), (fx, fy, -ZCG + 0.006, 0, 0, 0), "0.15 0.15 0.16 1"))
    out.append("    </link>\n")
    R = D.RADIUS
    for tag, label, spin, z in ROTORS:
        out.append(f'\n    <link name="rotor_{label}_link">\n      <pose>0 0 {z - ZCG:.5g} 0 0 0</pose>\n')
        # two blades: tapered planform from the published chord distribution, slight twist look by two boxes
        for side in (1, -1):
            r0, r1 = 0.06, 0.40
            out.append(_visual(f"blade_{label}_{'a' if side > 0 else 'b'}_root", _box(r1 - r0, 0.11, 0.006),
                               (side * 0.5 * (r0 + r1), 0, 0, side * 0.12, 0, 0), "0.86 0.84 0.78 1"))
            out.append(_visual(f"blade_{label}_{'a' if side > 0 else 'b'}_tip", _box(R - r1, 0.07, 0.005),
                               (side * 0.5 * (r1 + R), 0, 0, side * 0.05, 0, 0), "0.86 0.84 0.78 1"))
        out.append(_visual(f"tip_mark_{label}", _box(0.06, 0.071, 0.0055), (R - 0.04, 0, 0, 0.05, 0, 0), "1.0 0.45 0.05 1"))
        out.append("    </link>\n")
    for tag, label, spin, z in ROTORS:
        out.append(f'\n    <joint name="rotor_{label}" type="continuous">\n      <parent>body</parent>\n'
                   f'      <child>rotor_{label}_link</child>\n      <axis><xyz>0 0 1</xyz></axis>\n    </joint>\n')
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


# ----------------------------------------------------------------------------- write
def write(name: str, doc: dict) -> None:
    p = ROOT / "models" / f"{name}.bgmodel.json"
    p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {p}")


# ----------------------------------------------------------------------------- expected.json
# measured on the real worker (README): the lift-off instant of Flight One (2 cm above the rest height)
MEAS_F1_UP = 1.48


def ck(kind, signal=None, note=None, **kw) -> dict:
    c = {"kind": kind}
    if signal is not None:
        c["signal"] = signal
    c.update(kw)
    if note:
        c["note"] = note
    return c


def expected() -> dict:
    val = json.loads((HERE / "validation_data.json").read_text(encoding="utf-8"))
    jpl = json.loads((HERE / "jpl_hover_test.json").read_text(encoding="utf-8"))
    f1 = val["flight_one"]
    W = MP["m"] * D.G_MARS
    h = DES["hover"]
    # statics on the gear: the rotors idle at the collective that lifts 10 % of the weight (design.py), the
    # four feet share the rest; Hertz contact f = k x sqrt(x / xref) gives the compression
    f_foot = 0.9 * W / 4.0
    x_foot = (f_foot / CONTACT["k"] * math.sqrt(CONTACT["xref"])) ** (2.0 / 3.0)
    diag = ck("no_diagnostics", codes=["W201", "W202", "E106", "E901"])
    common = [ck("scene_bindings"), diag]
    p_peak = val["battery"]["peak_power_W"]
    demo = [
        ck("cursor_value", "Foot1/Contact/f_n", t=0.5, value=f_foot, rtol=0.01,
           note=f"on the ground at idle collective: each foot carries (W - 0.1 W)/4 = {f_foot:.4f} N "
                "(W = 1.8 kg x 3.71 m/s^2, published; the idle collective makes 10 % of the weight, design.py)"),
        ck("cursor_value", "Nav/alt", t=0.5, value=-x_foot, abs=2e-5,
           note=f"Hertz compression of the feet under that load: x = (f sqrt(xref) / k)^(2/3) = {x_foot * 1e3:.4f} mm"),
        ck("cursor_value", "Telem/T", t=8.5, value=W, rtol=0.002,
           note=f"hover: the total thrust equals the Mars weight m g = 1.8 x 3.71 = {W:.3f} N (published mass and gravity)"),
        ck("cursor_value", "GovL/speed_rpm", t=8.5, value=D.RPM_FLIGHT1, rtol=0.002,
           note="the governor holds the published set point of flights 1-13, 2537 rpm"),
        ck("cursor_value", "Telem/P_el", t=8.5, value=h["P_el"], rtol=0.01,
           note=f"hover electrical rotor power against the independent numpy BEMT trim of design/rotor_ref.py "
                f"({h['P_el']:.1f} W = shaft {h['P_shaft']:.1f} W / 0.78); published Flight One: about 210 W"),
        ck("cursor_value", "Telem/coll_u_deg", t=8.5, value=h["theta_u_deg"], abs=0.05,
           note="upper collective against the numpy trim (thrust = weight, torque balance of the coaxial pair)"),
        ck("cursor_value", "Telem/coll_l_deg", t=8.5, value=h["theta_l_deg"], abs=0.05,
           note="lower collective against the numpy trim"),
        ck("cursor_value", "Nav/alt", t=8.5, value=3.0, abs=0.01, note="hover altitude 3 m reached (set-point)"),
        ck("cursor_value", "Nav/x", t=17.4, value=5.0, abs=0.02, note="5 m east reached at the end of the 8 s move"),
        ck("cursor_value", "Nav/yaw_deg", t=21.4, value=90.0, abs=1.5,
           note="the 90 deg turn is complete (the real vehicle held its heading within 1.5 deg, NASA21)"),
        ck("cursor_value", "Nav/x", t=30.0, value=5.0, abs=0.05, note="landed on the target pad 5 m east"),
        ck("cursor_value", "Nav/alt", t=30.0, value=-x_foot, abs=5e-4, note="landed: back at the rest height on the gear"),
        ck("max_abs_le", "Nav/tilt_deg", value=10.0, note="the tilt stays inside the 10 deg set-point limit of the outer loop"),
        ck("max_abs_le", "Telem/coll_l_deg", value=D.COLL_MAX_DEG,
           note="collective inside the published -4.5..17.5 deg range (Bal18)"),
        ck("max_abs_le", "Telem/P_el", value=p_peak, note="rotor power below the published 510 W battery peak (Bal18, NASA21)"),
    ] + common
    flight1 = [
        ck("cursor_value", "Telem/T", t=25.0, value=W, rtol=0.005, note=f"hover thrust = Mars weight {W:.3f} N"),
        ck("cursor_value", "GovL/speed_rpm", t=25.0, value=f1["rotor_rpm"], rtol=0.002, note="published 2537 rpm"),
        ck("cursor_value", "Telem/P_el", t=25.0, value=f1["hover_rotor_electrical_power_W"], rtol=0.10,
           note=f"published Flight One hover rotor power 'about 210 W' (NASA21, design/validation_data.json); model "
                f"{h['P_el']:.0f} W. Tolerance 10 %: the published figure is rounded and the 78 % drive efficiency "
                "(Kon18) is one number for all loads"),
        ck("cursor_value", "Telem/coll_u_deg", t=25.0, value=f1["collective_upper_deg"], abs=0.8,
           note=f"published Flight One upper collective 8.2 deg (NASA21); model {h['theta_u_deg']:.2f} deg. JPL's own "
                "pre-flight model predicted 9.0 deg, 0.8 deg above the flight value; the model sits between the two. "
                "Tolerance 0.8 deg, the size of that published model error"),
        ck("cursor_value", "Telem/coll_l_deg", t=25.0, value=f1["collective_lower_deg"], abs=0.8,
           note=f"published Flight One lower collective 9.2 deg (NASA21); model {h['theta_l_deg']:.2f} deg "
                "(JPL pre-flight prediction 9.9 deg)"),
        ck("cursor_value", "Nav/alt", t=25.0, value=f1["hover_altitude_m"], abs=0.01, note="published hover altitude 3 m"),
        ck("compare_signals", "Nav/alt", signal_b="Plan/alt_sp", from_t=9.0, to_t=34.0, max_abs=f1["altitude_hold_m"],
           note="published altitude hold 'within about 1 cm' (NASA21); the model's navigation is perfect, so it "
                "meets this bound easily"),
        ck("cursor_value", "Nav/yaw_deg", t=25.0, value=f1["planned_turn_deg"], abs=f1["heading_hold_deg"],
           note="the planned 96 deg turn, held within the published 1.5 deg"),
        ck("max_abs_le", "Nav/x", from_t=9.0, to_t=34.0, value=f1["position_variation_m"],
           note="published horizontal position variations of about 25 cm in the gusty wind (NASA21): a bound only; "
                "the model flies a steady wind with perfect navigation"),
        ck("max_abs_le", "Nav/y", from_t=9.0, to_t=34.0, value=f1["position_variation_m"]),
        ck("max_abs_le", "Telem/cyc_deg", from_t=9.0, to_t=34.0, value=3.5,
           note="published: cyclic 'generally below 3 deg' in 4-6 m/s winds (NASA21). The model needs 3.3 deg in a "
                "steady 5 m/s wind (Pitt-Peters edgewise moment x 2.5, Grip17), slightly above the published figure; "
                "bound 3.5 deg"),
        ck("max_abs_le", "Telem/P_el", value=p_peak, note="below the 510 W battery peak (Bal18)"),
        ck("zero_crossing", "Nav/alt", n=1, direction="up", level=0.02, value=MEAS_F1_UP, abs=0.1,
           note="lift-off (2 cm above the rest height) shortly after the take-off command at 1 s (measured)"),
        ck("zero_crossing", "Nav/alt", n=1, direction="down", level=0.02, value=MEAS_F1_UP + f1["duration_s"], abs=0.5,
           note="touchdown 39.1 s after lift-off, the published flight time. The flight plan is laid out to that "
                "duration, so this checks the plan and the landing, not the physics"),
        ck("cursor_value", "Nav/alt", t=FLIGHT1["t_end"], value=0.0, abs=2e-3, note="landed and resting on the gear"),
    ] + common
    # rotor stand: C_P on the thrust plateaus against the measured points (linear interpolation)
    stand = []
    for k, ct in enumerate(STAND_CT):
        t = STAND_DT * (k + 1) - 0.1
        cp = float(np.interp(ct, jpl["CT"], jpl["CP"]))
        stand.append(ck("cursor_value", "Telem/CP", t=t, value=cp, rtol=0.06,
                        note=f"JPL hover test (Kon19 Fig. 25, digitised) at C_T = {ct}: C_P = {cp:.6f}. A FIT CHECK, "
                             "not an independent one: the profile-drag polar is fitted to these points (rms 2.8 %, "
                             "max 4.7 %); 6 % covers the fit and the digitising"))
    stand.append(ck("cursor_value", "Telem/CT", t=STAND_DT * 4 - 0.1, value=STAND_CT[3], abs=2e-4,
                    note="the stand controller holds the thrust-coefficient target"))
    stand.append(ck("cursor_value", "GovL/speed_rpm", t=10.0, value=D.RPM_JPL, rtol=0.002,
                    note="published test speed 2600 rpm"))
    ref = val["cyclic_torque_steps"]["mean_Nm"]
    for sig, t0 in (("AeroL/ty", T_CYC), ("AeroL/tx", T_CYC + 12.0)):
        stand.append(ck("cursor_value", sig, t=t0 + 2.5, value=ref, rtol=0.2,
                        note=f"5 deg cyclic step on the lower rotor: measured hub torque about 0.55 N m (Grip17 "
                             f"Fig. 15, digitised 0.53-0.57). The quasi-steady model gives "
                             f"{DES['comparisons']['cyclic_5deg_torque']:.3f} N m, 15 % high: it has no "
                             "first-harmonic inflow, which opposes the cyclic moment. Tolerance 20 %"))
    stand.append(diag)
    return {"project": "ingenuity",
            "description": "NASA's Ingenuity Mars Helicopter: 3D multibond airframe, coaxial BEMT rotors fitted to "
                           "the JPL hover test, flight control after Grip et al. 2018. Reference values: published "
                           "flight and test data (design/validation_data.json, design/jpl_hover_test.json) and the "
                           "independent numpy BEMT trim of design/rotor_ref.py. Generated by design/build_model.py.",
            "models": {"ingenuity": {"run_timeout": 900, "checks": demo},
                       "ingenuity-flight-one": {"run_timeout": 900, "checks": flight1},
                       "ingenuity-rotor-stand": {"run_timeout": 600, "checks": stand}}}


def main() -> int:
    foot = ROOT / "library" / "ContactFoot.bgsub.json"
    foot.write_text(json.dumps(contact_foot_definition(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {foot}")
    demo_globals = flight_globals() + [glob("alt", 3.0, "m", "Hover altitude of the flight plan"),
                                     glob("dist", 5.0, "m", "Distance flown east")]
    write("ingenuity", flight_model(
        "ingenuity", "NASA's Ingenuity Mars Helicopter: a demonstration flight (take off, 3 m hover, 5 m east, turn, "
        "land). Generated by design/build_model.py; see the README.", DEMO, demo_globals, demo_dashboard()))
    write("ingenuity-flight-one", flight_model(
        "ingenuity-flight-one", "Replica of Ingenuity's Flight One (19 April 2021, density 0.0165 kg/m^3, 2537 rpm). "
        "Generated by design/build_model.py.", FLIGHT1, flight_globals(WIND1_E, WIND1_N), flight_one_dashboard()))
    write("ingenuity-rotor-stand", stand_model())
    sdf = ROOT / "scenes" / "ingenuity.sdf"
    sdf.write_text(build_scene(), encoding="utf-8", newline="\n")
    print(f"wrote {sdf}")
    (ROOT / "design" / "design.json").write_text(json.dumps(DES, indent=2) + "\n", encoding="utf-8", newline="\n")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "ingenuity",
            "models": ["ingenuity", "ingenuity-flight-one", "ingenuity-rotor-stand"],
            "libraryDir": "library", "scenesDir": "scenes"}
    (ROOT / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
