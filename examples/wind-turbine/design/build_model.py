# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate the wind-turbine models, the scene and expected.json from `design/design.json`.

    uv run examples/wind-turbine/design/design.py        # first (BEM tables, tower mode, steady states)
    uv run examples/wind-turbine/design/build_model.py

Every model has the same plant, built by `plant()`: the NREL 5 MW turbine as a rotational and a
translational bond graph. The rotor 1-junction carries the rotor inertia and the aerodynamic torque
(an MSe), a 0-junction the low-speed shaft (its twist rate on a 1-junction with the shaft's C and
R), the gearbox is a TF of 97, the generator 1-junction carries the generator inertia and the
generator torque (an MSe that takes the converter's torque). The tower's first fore-aft mode is a
1-junction with the modal I, C and R and the thrust (an MSe). `RotorAero` (the aerodynamic law) and
two stdlib Lookup2D blocks (the BEM tables) drive the two aerodynamic sources from the rotor speed,
the nacelle velocity, the wind and the pitch. The models differ in the wind and in the controller
(the baseline controller of the report, or a fixed pitch and torque).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
TAB = DESIGN["tables"]
CTRL = DESIGN["ctrl"]
TW = DESIGN["tower"]
DT = DESIGN["drivetrain"]
STEADY = {s["v"]: s for s in DESIGN["steady"]}
OL = DESIGN["open_loop"]
RPM = 2.0 * math.pi / 60.0
DEG = math.pi / 180.0

R_TIP = 63.0
RHO = 1.225
GEAR = 97.0
J_ROTOR = 38_759_228.0
J_GEN = 534.116
K_SHAFT = 867_637_000.0
C_SHAFT = 6_215_000.0
ETA = 0.944


def num(v: float) -> str:
    return repr(float(v))


def vec(values) -> str:
    return "[" + ", ".join(v if isinstance(v, str) else repr(float(v)) for v in values) + "]"


def mat(rows) -> str:
    return "[" + "; ".join(" ".join(repr(float(v)) for v in row) for row in rows) + "]"


# --------------------------------------------------------------------------- document helpers
class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[tuple] = []
        self.annotations: list[dict] = []
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

    def sig(self, a, pa, b, pb, label=None):
        self.connections.append(("signal", a, pa, b, pb, label))

    def bond(self, a, pa, b, pb, label=None):
        self.connections.append(("bond", a, pa, b, pb, label))

    def note(self, text, x, y, w, h, color=None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def doc(self) -> dict:
        conns = []
        for k, (kind, a, pa, b, pb, label) in enumerate(self.connections):
            frm = {"node": self.ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self.ids[b]}
            if pb is not None:
                to["port"] = pb
            c = {"id": f"c{k + 1:03d}", "kind": kind, "from": frm, "to": to}
            if label:
                c["label"] = label
            conns.append(c)
        return {"nodes": self.nodes, "connections": conns, "annotations": self.annotations}


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value if isinstance(value, str) else num(value), "unit": unit,
            "description": description}


def settings(t_end: float, points: int, reltol=1e-7, abstol=1e-7, max_step=None) -> dict:
    return {"t_start": 0.0, "t_end": float(t_end), "solver": "auto", "reltol": reltol, "abstol": abstol,
            "max_step": max_step, "output": {"mode": "points", "points": int(points)}, "event_limit": 200000}


# --------------------------------------------------------------------------- the plant
def plant_globals(st: dict, x0: float | None = None) -> list[dict]:
    """The turbine's globals and its start state (`st`: a steady state of design.json)."""
    pitch = st["pitch"]
    return [
        g("rho", RHO, "kg/m^3", "Air density (the report's 1.225 kg/m^3)"),
        g("R", R_TIP, "m", "Rotor radius (126 m diameter)"),
        g("J_rotor", J_ROTOR, "kg*m^2", "Rotor inertia about the low-speed shaft (hub and 3 blades)"),
        g("J_gen", J_GEN, "kg*m^2", "Generator inertia about the high-speed shaft"),
        g("N_gear", GEAR, None, "Gearbox ratio (high-speed / low-speed shaft speed)"),
        g("k_shaft", K_SHAFT, "N*m/rad", "Drivetrain torsional stiffness, low-speed shaft equivalent"),
        g("c_shaft", C_SHAFT, "N*m*s/rad", "Drivetrain torsional damping, low-speed shaft equivalent"),
        g("m_tower", TW["m_gen"], "kg", "Modal mass of the first fore-aft tower mode (tower top deflection, design/tower.py)"),
        g("k_tower", TW["k_gen"], "N/m", "Modal stiffness of the first fore-aft tower mode"),
        g("c_tower", "2*0.01*sqrt(k_tower*m_tower)", "N*s/m", "Modal damping: 1 % of critical (the report's structural damping)"),
        g("eta_gen", ETA, None, "Generator efficiency (electrical power = eta_gen * mechanical power)"),
        g("tau_act", 0.05, "s", "Time constant of the pitch actuator and of the converter's torque loop"),
        g("rpm0", st["rpm_rotor"], "rpm", f"Start: rotor speed (the steady state at {st['v']:g} m/s, design/design.py)"),
        g("pitch0", st["pitch_deg"], "deg", "Start: blade pitch"),
        g("tq0", st["t_gen"], "N*m", "Start: generator torque"),
        g("x0", st["x_tower"] if x0 is None else x0, "m", "Start: tower-top fore-aft deflection"),
    ]


def plant(d: Diagram) -> None:
    """The bond graph, the aerodynamics and the measurements; inputs `Wind/u`, `Converter/u` (generator
    torque command) and the pitch on `Aero/beta` (wired by the caller)."""
    # ---- aerodynamics
    d.node("Aero", "project:RotorAero", 560, 120, params={"R": "R", "rho": "rho"})
    breaks = mat([TAB["tsr"], TAB["pitch_deg"]])
    n = len(TAB["tsr"])
    d.node("Cp", "stdlib:continuous/Lookup2D", 820, 60, params={"breaks": breaks, "table": mat(TAB["cp"])},
           constants={"N": n})
    d.node("Ct", "stdlib:continuous/Lookup2D", 820, 180, params={"breaks": breaks, "table": mat(TAB["ct"])},
           constants={"N": n})
    for t in ("Cp", "Ct"):
        d.sig("Aero", "lambda", t, "u")
        d.sig("Aero", "beta_deg", t, "v")
    d.sig("Cp", "y", "Aero", "cp")
    d.sig("Ct", "y", "Aero", "ct")
    d.sig("Wind", "y", "Aero", "v")
    d.note("**Aerodynamics.** RotorAero: tip-speed ratio lambda = Omega R / v_rel with v_rel = v - xdot (the nacelle's "
           "velocity gives the aerodynamic damping of the tower), the BEM tables Cp(lambda, beta) and Ct(lambda, beta) "
           "(two Lookup2D, from the report's blade and airfoil data, design/bem.py), the torque Ta = 1/2 rho pi R^2 Cp v^3 / "
           "Omega and the thrust T = 1/2 rho pi R^2 Ct v^2.", 520, -60, 520, 90, "blue")
    # ---- drivetrain bond graph (rotation)
    y = 420
    d.node("AeroTorque", "stdlib:bondgraph/MSe", 560, y)
    d.sig("Aero", "torque", "AeroTorque", "u")
    d.junction("Rotor", 1, 760, y)
    d.bond("AeroTorque", "p", "Rotor", None)
    d.node("RotorInertia", "stdlib:bondgraph/I", 760, y + 130, params={"i": "J_rotor"},
           starts={"P": "J_rotor*rpm0*pi/30"})
    d.bond("Rotor", None, "RotorInertia", "p")
    d.node("RotorSpeed", "stdlib:converters/SpeedSensor", 760, y - 120)
    d.bond("Rotor", None, "RotorSpeed", "a")
    d.sig("RotorSpeed", "y", "Aero", "w")
    d.junction("Shaft", 0, 960, y)
    d.bond("Rotor", None, "Shaft", None)
    d.junction("Twist", 1, 960, y + 130)
    d.bond("Shaft", None, "Twist", None)
    d.node("ShaftC", "stdlib:bondgraph/C", 880, y + 250, params={"c": "1/k_shaft"},
           starts={"q": "N_gear*tq0/k_shaft"})
    d.node("ShaftR", "stdlib:bondgraph/R", 1040, y + 250, params={"r": "c_shaft"})
    d.bond("Twist", None, "ShaftC", "p")
    d.bond("Twist", None, "ShaftR", "p")
    d.node("Gearbox", "stdlib:bondgraph/TF", 1160, y, params={"n": "N_gear"})
    d.bond("Shaft", None, "Gearbox", "p1")
    d.junction("Gen", 1, 1360, y)
    d.bond("Gearbox", "p2", "Gen", None)
    d.node("GenInertia", "stdlib:bondgraph/I", 1360, y + 130, params={"i": "J_gen"},
           starts={"P": "J_gen*N_gear*rpm0*pi/30"})
    d.bond("Gen", None, "GenInertia", "p")
    # The generator absorbs the converter torque: an effort source at the tail of the Gen
    # junction (its declared `out`) with gain -1, so it opposes the rotation.
    d.node("Generator", "stdlib:bondgraph/MSe", 1560, y, params={"gain": "-1.0"})
    d.bond("Generator", "p", "Gen", None)
    d.node("GenSpeed", "stdlib:converters/SpeedSensor", 1360, y - 120)
    d.bond("Gen", None, "GenSpeed", "a")
    d.note("**Drivetrain (rotation).** Rotor 1-junction: rotor inertia and aerodynamic torque. Shaft 0-junction: the "
           "shaft torque; its twist rate (Twist 1-junction) loads the shaft's C (1/k) and R (c), both low-speed-shaft "
           "equivalents. Gearbox TF 97. Gen 1-junction: generator inertia and the generator (an MSe absorbing the "
           "converter's torque).", 560, y + 340, 620, 70, "blue")
    # ---- tower bond graph (translation)
    y = 900
    d.node("Thrust", "stdlib:bondgraph/MSe", 560, y)
    d.sig("Aero", "thrust", "Thrust", "u")
    d.junction("Nacelle", 1, 760, y)
    d.bond("Thrust", "p", "Nacelle", None)
    d.node("TowerMass", "stdlib:bondgraph/I", 640, y + 130, params={"i": "m_tower"}, starts={"P": "0.0"})
    d.node("TowerSpring", "stdlib:bondgraph/C", 760, y + 130, params={"c": "1/k_tower"}, starts={"q": "x0"})
    d.node("TowerDamper", "stdlib:bondgraph/R", 880, y + 130, params={"r": "c_tower"})
    for e in ("TowerMass", "TowerSpring", "TowerDamper"):
        d.bond("Nacelle", None, e, "p")
    d.node("NacelleVel", "stdlib:converters/VelocitySensor", 960, y)
    d.bond("Nacelle", None, "NacelleVel", "a")
    d.sig("NacelleVel", "y", "Aero", "xdot")
    d.note("**Tower (translation).** The first fore-aft mode as one degree of freedom, the tower-top deflection: modal "
           "mass, stiffness and 1 % damping from a finite-element model of the report's tower with the rotor and "
           "nacelle on top (design/tower.py, 0.322 Hz). The thrust drives it; its velocity feeds back into the wind the "
           "rotor sees.", 520, y + 240, 520, 70, "blue")
    # ---- measurements
    d.node("RotorRPM", "stdlib:continuous/Gain", 1000, 180, params={"k": num(1.0 / RPM)})
    d.sig("RotorSpeed", "y", "RotorRPM", "u")
    d.node("GenRPM", "stdlib:continuous/Gain", 1600, 200, params={"k": num(1.0 / RPM)})
    d.sig("GenSpeed", "y", "GenRPM", "u")
    d.node("RotorAngle", "stdlib:continuous/Integrator", 1000, 260)
    d.sig("RotorSpeed", "y", "RotorAngle", "u")
    d.node("MechPower", "stdlib:continuous/Product", 1780, 520)
    d.sig("Converter", "y", "MechPower", "u1")
    d.sig("GenSpeed", "y", "MechPower", "u2")
    d.node("ElecPower", "stdlib:continuous/Gain", 1960, 520, params={"k": "eta_gen*1e-6"})
    d.sig("MechPower", "y", "ElecPower", "u")
    # the scene's tower tilt: the nacelle velocity integrated (the same displacement as TowerSpring/q)
    d.node("TowerX", "stdlib:continuous/Integrator", 1140, 900, starts={"x": "x0"})
    d.sig("NacelleVel", "y", "TowerX", "u")
    d.node("TowerTilt", "stdlib:continuous/Gain", 1140, 1000, params={"k": num(EXAG / TOWER_H)})
    d.sig("TowerX", "y", "TowerTilt", "u")
    d.node("ThrustkN", "stdlib:continuous/Gain", 760, 1150, params={"k": "1e-3"})
    d.sig("Aero", "thrust", "ThrustkN", "u")
    # ---- the converter: the generator torque follows the command with a lag and the torque-rate limit
    d.node("Converter", "project:RateLimitedLag", 1560, 300, params={"tau": "tau_act", "rate": num(CTRL["vs_maxrat"])},
           starts={"x": "tq0"})
    d.sig("Converter", "y", "Generator", "u")
    d.note("**Generator.** The converter (RateLimitedLag: a 50 ms lag and the report's 15 kN m/s torque-rate limit) "
           "sets the generator torque. ElecPower = eta_gen x torque x speed, in MW.", 1700, 600, 420, 60, "blue")


def controller(d: Diagram) -> None:
    """The baseline controller of the report (chapter 7): the generator-speed filter, the torque law and the
    gain-scheduled pitch PI, the pitch actuator."""
    c = CTRL
    d.node("SpeedFilter", "stdlib:continuous/FirstOrder", 1760, 120,
           params={"tau": num(1.0 / (2.0 * math.pi * c["corner_hz"]))}, starts={"x": "N_gear*rpm0*pi/30"})
    d.sig("GenSpeed", "y", "SpeedFilter", "u")
    d.node("Torque", "project:VSTorque", 1960, 120, params={"k2": "k2"})
    d.sig("SpeedFilter", "y", "Torque", "w")
    d.sig("Torque", "tq", "Converter", "u")
    d.node("PitchCtrl", "project:PitchPI", 1960, 300, params={"kp": "kp", "ki": "ki"},
           starts={"xi": "pitch0*pi/180*(1 + pitch0*pi/180/0.1099965)/ki"})
    d.sig("SpeedFilter", "y", "PitchCtrl", "w")
    d.node("PitchAct", "project:RateLimitedLag", 2160, 300,
           params={"tau": "tau_act", "rate": num(c["pc_maxrat"])}, starts={"x": "pitch0*pi/180"})
    d.sig("PitchCtrl", "beta_cmd", "PitchAct", "u")
    d.sig("PitchAct", "y", "PitchCtrl", "beta")
    d.sig("PitchAct", "y", "Torque", "beta")
    d.sig("PitchAct", "y", "Aero", "beta")
    d.note("**Baseline controller** (report chapter 7). SpeedFilter: the generator speed through a 0.25 Hz low-pass. "
           "Torque (VSTorque): regions 1.5, 2 (k2 w^2, 0.0255764 N m/rpm^2), 2.5 and 3 (constant power). PitchCtrl "
           "(PitchPI): the collective-pitch PI to 1173.7 rpm, gain-scheduled by 1/(1 + beta/6.3 deg). PitchAct: the "
           "pitch actuator, 8 deg/s.", 1740, -60, 560, 90, "blue")


def controller_globals() -> list[dict]:
    return [
        g("k2", CTRL["vs_rgn2k"], "N*m*s^2/rad^2", "Region-2 torque gain (0.0255764 N m/rpm^2)"),
        g("kp", CTRL["pc_kp"], "s", "Pitch PI proportional gain at zero pitch"),
        g("ki", CTRL["pc_ki"], None, "Pitch PI integral gain at zero pitch"),
    ]


# --------------------------------------------------------------------------- wind inputs
def wind_pass(d: Diagram, x=380, y=120) -> None:
    d.node("Wind", "stdlib:continuous/Gain", x, y, params={"k": "1.0"})


def iec_sigma(v: str) -> str:
    """IEC 61400-1 normal turbulence, class B (I_ref 0.14): sigma = I_ref (0.75 v + 5.6)."""
    return f"0.14*(0.75*{v} + 5.6)"


# --------------------------------------------------------------------------- the scene
TOWER_H = 87.6
HUB_DZ = 2.4
OVERHANG = 5.0
EXAG = 20.0       # the tower's fore-aft motion is drawn 20 x larger


def cyl(name, pose, radius, length, rgba, rpy=(0.0, 0.0, 0.0)) -> list[str]:
    return [f'      <visual name="{name}">',
            f"        <pose>{pose[0]:g} {pose[1]:g} {pose[2]:g} {rpy[0]:g} {rpy[1]:g} {rpy[2]:g}</pose>",
            f"        <geometry><cylinder><radius>{radius:g}</radius><length>{length:g}</length></cylinder></geometry>",
            f"        <material><diffuse>{rgba}</diffuse></material>", "      </visual>"]


def box(name, pose, size, rgba, rpy=(0.0, 0.0, 0.0)) -> list[str]:
    return [f'      <visual name="{name}">',
            f"        <pose>{pose[0]:g} {pose[1]:g} {pose[2]:g} {rpy[0]:g} {rpy[1]:g} {rpy[2]:g}</pose>",
            f"        <geometry><box><size>{size[0]:g} {size[1]:g} {size[2]:g}</size></box></geometry>",
            f"        <material><diffuse>{rgba}</diffuse></material>", "      </visual>"]


def sphere(name, pose, radius, rgba) -> list[str]:
    return [f'      <visual name="{name}">', f"        <pose>{pose[0]:g} {pose[1]:g} {pose[2]:g} 0 0 0</pose>",
            f"        <geometry><sphere><radius>{radius:g}</radius></sphere></geometry>",
            f"        <material><diffuse>{rgba}</diffuse></material>", "      </visual>"]


def scene() -> str:
    """The turbine in a field, wind from -x (blowing towards +x): the rotor faces the wind (upwind of the tower)."""
    white = "0.92 0.93 0.95 1"
    L = ['<?xml version="1.0"?>', "<!--",
         "  wind-turbine: the NREL 5 MW reference turbine, built from simple solids at full scale (metres, Z up).",
         "  The wind blows towards +x; the nacelle is yawed into it, so the rotor (hub 5 m upwind of the tower axis, 90 m",
         "  above the ground) faces -x. Links and joints:",
         "    tower    revolute tower_tilt about +y at the ground: the first fore-aft mode drawn as a rigid tilt of the",
         f"             tower, angle = {EXAG:g} x TowerSpring/q / {TOWER_H:g} m, so the nacelle moves {EXAG:g} x its real",
         "             deflection (0.2 to 0.7 m in operation);",
         "    nacelle  fixed on the tower top;",
         "    rotor    revolute rotor_spin about -x (the hub, three blades with the root at the hub and a 63 m tip",
         "             radius), angle = RotorAngle/y: the rotor turns at its real speed, 12.1 rpm at rated;",
         "    wind     the arrow upwind of the rotor, its shaft length scaled by the wind speed (scale.x = Wind/y / 10).",
         "-->", '<sdf version="1.9">', '  <model name="wind-turbine">']
    # ground
    L += ['    <link name="ground">', "      <pose>0 0 0 0 0 0</pose>"]
    L += box("ground_plane", (0.0, 0.0, -0.25), (220.0, 220.0, 0.5), "0.42 0.55 0.36 1")
    L += cyl("foundation", (0.0, 0.0, 0.25), 6.0, 0.5, "0.6 0.6 0.6 1")
    L.append("    </link>")
    # tower (tapered: five sections)
    L += ['    <link name="tower">', "      <pose>0 0 0 0 0 0</pose>"]
    nseg = 6
    for k in range(nseg):
        z0, z1 = TOWER_H * k / nseg, TOWER_H * (k + 1) / nseg
        zm = 0.5 * (z0 + z1)
        dia = 6.0 + (3.87 - 6.0) * zm / TOWER_H
        L += cyl(f"tower_{k}", (0.0, 0.0, zm), dia / 2.0, z1 - z0 + 0.05, white)
    L.append("    </link>")
    L += ['    <joint name="tower_tilt" type="revolute">', "      <parent>ground</parent>", "      <child>tower</child>",
          "      <axis><xyz>0 1 0</xyz></axis>", "    </joint>"]
    # nacelle on the tower top
    L += ['    <link name="nacelle">', f"      <pose>0 0 {TOWER_H:g} 0 0 0</pose>"]
    L += box("nacelle_body", (1.6, 0.0, 1.9), (14.0, 4.2, 3.8), white)
    L += box("nacelle_stripe", (1.6, 0.0, 3.85), (12.0, 2.0, 0.12), "0.15 0.35 0.65 1")
    L += cyl("yaw_bearing", (0.0, 0.0, 0.0), 1.95, 0.4, "0.5 0.5 0.52 1")
    L += cyl("main_shaft", (-OVERHANG / 2 - 0.3, 0.0, HUB_DZ), 0.6, 2.2, "0.45 0.45 0.48 1", (0.0, math.pi / 2, 0.0))
    L.append("    </link>")
    L += ['    <joint name="nacelle_mount" type="fixed">', "      <parent>tower</parent>", "      <child>nacelle</child>",
          "    </joint>"]
    # rotor
    L += ['    <link name="rotor">', f"      <pose>{-OVERHANG:g} 0 {TOWER_H + HUB_DZ:g} 0 0 0</pose>"]
    L += sphere("hub", (0.0, 0.0, 0.0), 1.8, white)
    L += cyl("spinner", (-1.4, 0.0, 0.0), 1.4, 1.6, white, (0.0, math.pi / 2, 0.0))
    for b in range(3):
        a = 2.0 * math.pi * b / 3.0
        # blade b: along the direction (0, sin a, cos a) in the rotor plane, root at r = 1.5 m, tip at 63 m;
        # three tapered pieces (root cylinder, inner and outer blade) approximating the chord distribution
        for name, r0, r1, chord, th in (("root", 1.5, 8.0, 3.6, 3.4), ("inner", 8.0, 30.0, 4.4, 1.2),
                                         ("outer", 30.0, 63.0, 2.8, 0.6)):
            rm = 0.5 * (r0 + r1)
            pos = (0.0, rm * math.sin(a), rm * math.cos(a))
            if name == "root":
                L += cyl(f"blade{b + 1}_{name}", pos, chord / 2.0, r1 - r0, white, (-a, 0.0, 0.0))
            else:
                L += box(f"blade{b + 1}_{name}", pos, (th, chord, r1 - r0), white, (-a, 0.0, 0.0))
        tip = (0.0, 61.0 * math.sin(a), 61.0 * math.cos(a))
        L += box(f"blade{b + 1}_tip", tip, (0.62, 2.0, 4.0), "0.85 0.2 0.15 1", (-a, 0.0, 0.0))
    L.append("    </link>")
    L += ['    <joint name="rotor_spin" type="revolute">', "      <parent>nacelle</parent>", "      <child>rotor</child>",
          "      <axis><xyz>-1 0 0</xyz></axis>", "    </joint>"]
    # wind arrow: upwind of the rotor at hub height, blowing towards +x
    L += ['    <link name="wind">', f"      <pose>-80 0 {TOWER_H + HUB_DZ:g} 0 0 0</pose>"]
    L += cyl("wind_shaft", (0.0, 0.0, 0.0), 0.9, 20.0, "0.25 0.6 0.95 1", (0.0, math.pi / 2, 0.0))
    L += cyl("wind_head", (13.0, 0.0, 0.0), 2.4, 6.0, "0.25 0.6 0.95 1", (0.0, math.pi / 2, 0.0))
    L.append("    </link>")
    L += ["  </model>", "</sdf>", ""]
    return "\n".join(L)


def bindings(pitch="PitchAct/y") -> list[dict]:
    return [
        {"target": "joint:tower_tilt", "property": "position", "signal": "TowerTilt/y"},
        {"target": "joint:rotor_spin", "property": "position", "signal": "RotorAngle/y"},
        {"target": "visual:wind_shaft", "property": "scale.z", "signal": "Wind/y", "gain": 0.1},
        {"target": "visual:wind_shaft", "property": "color", "signal": "Wind/y", "colormap": "viridis", "range": [3.0, 25.0]},
        {"target": "visual:blade1_tip", "property": "color", "signal": pitch, "colormap": "heat",
         "range": [0.0, 0.45]},
    ]


# --------------------------------------------------------------------------- dashboards
def slider(cid, title, param, lo, hi, step, decimals, unit=None, size="2x1"):
    o = {"min": lo, "max": hi, "step": step, "decimals": decimals}
    if unit:
        o["unit"] = unit
    return {"id": cid, "kind": "slider", "size": size, "title": title, "parameter": f"global:{param}", "options": o}


def text(cid, title, body, size="2x1"):
    return {"id": cid, "kind": "text", "size": size, "title": title, "options": {"markdown": True, "text": body}}


def plot(cid, title, signals, size="2x2", x=None):
    p = {"id": cid, "kind": "plot", "size": size, "title": title, "signals": signals}
    if x:
        p["x"] = x
    return p


def gauge(cid, title, sig, lo, hi, unit, zones, decimals=0):
    return {"id": cid, "kind": "gauge", "size": "1x1", "title": title, "signals": [sig],
            "options": {"min": lo, "max": hi, "decimals": decimals, "unit": unit, "zones": zones}}


def readouts(prefix="r"):
    return [
        gauge(f"{prefix}1", "Electrical power", "ElecPower/y", 0.0, 6.0, "MW",
              [{"from": 0.0, "to": 5.05, "tone": "good"}, {"from": 5.05, "to": 5.5, "tone": "warn"},
               {"from": 5.5, "to": 6.0, "tone": "bad"}], 2),
        gauge(f"{prefix}2", "Rotor speed", "RotorRPM/y", 0.0, 15.0, "rpm",
              [{"from": 0.0, "to": 12.5, "tone": "good"}, {"from": 12.5, "to": 13.5, "tone": "warn"},
               {"from": 13.5, "to": 15.0, "tone": "bad"}], 2),
        gauge(f"{prefix}3", "Blade pitch", "Aero/beta_deg", 0.0, 30.0, "deg", [{"from": 0.0, "to": 30.0, "tone": "good"}], 1),
        gauge(f"{prefix}4", "Generator torque", "Converter/y", 0.0, 50000.0, "N m",
              [{"from": 0.0, "to": 43100.0, "tone": "good"}, {"from": 43100.0, "to": 50000.0, "tone": "warn"}], 0),
    ]


MAIN_PLOTS = [
    {"id": "p1", "title": "Wind and relative wind (m/s)", "signals": ["Wind/y", "Aero/v_rel"]},
    {"id": "p2", "title": "Electrical power (MW)", "signals": ["ElecPower/y"]},
    {"id": "p3", "title": "Rotor speed (rpm)", "signals": ["RotorRPM/y"]},
    {"id": "p4", "title": "Pitch (deg)", "signals": ["Aero/beta_deg"]},
    {"id": "p5", "title": "Generator torque (N m)", "signals": ["Converter/y", "Torque/tq"]},
    {"id": "p6", "title": "Thrust (kN) and tower-top deflection (m)", "signals": ["ThrustkN/y", "TowerSpring/q"]},
    {"id": "p7", "title": "Shaft twist (rad)", "signals": ["ShaftC/q"]},
]


# --------------------------------------------------------------------------- models
def closed_loop(wind_builder, name, comment, t_end, points, wind_globals, start_v, dash, extra_plots=(),
                max_step=None, x0=None) -> dict:
    d = Diagram()
    wind_pass(d)
    plant(d)
    controller(d)
    wind_builder(d)
    plots = MAIN_PLOTS + list(extra_plots)
    params = plant_globals(STEADY[start_v], x0) + controller_globals() + wind_globals
    return {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
            "diagram": d.doc(), "settings": settings(t_end, points, max_step=max_step), "plots": plots,
            "scene": {"file": "scenes/wind-turbine.sdf"}, "bindings": bindings(), "parameters": params,
            "dashboard": dash}


def wind_ramp(d: Diagram) -> None:
    d.node("WindRamp", "stdlib:sources/Ramp", 120, 120,
           params={"t_start": "t_ramp", "initial": "v_start", "slope": "(v_end - v_start)/ramp_time",
                   "duration": "ramp_time"})
    d.sig("WindRamp", "y", "Wind", "u")
    d.note("**Wind.** A slow ramp from v_start to v_end: the turbine follows its quasi-steady power curve.",
           40, 20, 300, 60, "green")


def model_steady() -> dict:
    v0, v1, t0, tr = 4.0, 25.0, 60.0, 1050.0
    wg = [g("v_start", v0, "m/s", "Wind before the ramp"), g("v_end", v1, "m/s", "Wind after the ramp"),
          g("t_ramp", t0, "s", "Start of the ramp"), g("ramp_time", tr, "s", "Duration of the ramp (0.02 m/s per s)")]
    dash = {"autoRerun": False, "cards": [
        text("d1", "Power curve", "The wind ramps slowly from **v_start** to **v_end**. Below rated (11.3 m/s) the "
             "torque law holds the optimal tip-speed ratio; above it the pitch holds 5 MW and 12.1 rpm. Set "
             "**v_end = v_start** for one steady operating point.", "2x2"),
        slider("d2", "Wind before the ramp", "v_start", 3.0, 25.0, 0.5, 1, "m/s"),
        slider("d3", "Wind after the ramp", "v_end", 3.0, 25.0, 0.5, 1, "m/s"),
        *readouts(),
        plot("d4", "Power curve: electrical power (MW) over the wind (m/s)", ["ElecPower/y"], "4x2", x="Wind/y"),
        plot("d5", "Rotor speed (rpm) and pitch (deg)", ["RotorRPM/y", "Aero/beta_deg"], "4x2"),
        plot("d6", "Thrust (kN)", ["ThrustkN/y"]),
        plot("d7", "Tip-speed ratio and Cp", ["Aero/lambda", "Cp/y"]),
    ]}
    extra = [{"id": "p8", "title": "Power curve (MW over m/s)", "signals": ["ElecPower/y"], "x": "Wind/y"},
             {"id": "p9", "title": "Pitch over the wind (deg over m/s)", "signals": ["Aero/beta_deg"], "x": "Wind/y"}]
    return closed_loop(wind_ramp, "wind-turbine-steady",
                       "NREL 5 MW turbine with the baseline controller on a slow wind ramp (the power curve). Generated by "
                       "design/build_model.py.", t0 + tr + 60.0, 6001, wg, v0, dash, extra)


STEP_PATTERN = ["v_low", "v_low + 0.25*(v_high - v_low)", "v_low + 0.5*(v_high - v_low)", "v_high",
                "v_low + 0.5*(v_high - v_low)", "v_low + 0.25*(v_high - v_low)", "v_low"]


def wind_steps(d: Diagram) -> None:
    d.node("WindSteps", "stdlib:sources/TimeTable", 120, 120,
           params={"t_start": "0.0", "sample_time": "t_hold", "values": vec(STEP_PATTERN), "method": "0"},
           constants={"N": len(STEP_PATTERN)})
    d.sig("WindSteps", "y", "Wind", "u")
    d.note("**Wind.** Steps every t_hold seconds: v_low, a quarter, half way, v_high and back.", 40, 20, 300, 60, "green")


def model_step() -> dict:
    wg = [g("v_low", 10.0, "m/s", "Lowest wind of the step sequence"), g("v_high", 18.0, "m/s", "Highest wind"),
          g("t_hold", 60.0, "s", "Time between two steps")]
    dash = {"autoRerun": False, "cards": [
        text("d1", "Wind steps across rated", "The wind steps from **v_low** to **v_high** and back (10, 12, 14, 18, "
             "14, 12, 10 m/s). Watch the torque law hand over to the pitch PI at rated, the overshoot of rotor speed "
             "after each step and the tower swaying with the thrust.", "2x2"),
        slider("d2", "Lowest wind", "v_low", 4.0, 14.0, 0.5, 1, "m/s"),
        slider("d3", "Highest wind", "v_high", 8.0, 25.0, 0.5, 1, "m/s"),
        slider("d4", "Pitch PI gain kp", "kp", 0.005, 0.05, 0.001, 4, "s"),
        *readouts(),
        plot("d5", "Wind (m/s) and power (MW)", ["Wind/y", "ElecPower/y"], "4x2"),
        plot("d6", "Rotor speed (rpm)", ["RotorRPM/y"]),
        plot("d7", "Pitch (deg)", ["Aero/beta_deg"]),
        plot("d8", "Tower-top deflection (m)", ["TowerSpring/q"]),
        plot("d9", "Control region", ["Torque/region"]),
    ]}
    return closed_loop(wind_steps, "wind-turbine-step",
                       "NREL 5 MW turbine with the baseline controller: wind steps across rated. Generated by "
                       "design/build_model.py.", 7 * 60.0, 8401, wg, 10.0, dash,
                       [{"id": "p8", "title": "Control region", "signals": ["Torque/region"]}])


def wind_gust(d: Diagram) -> None:
    d.node("WindMean", "stdlib:sources/Constant", 40, 60, params={"value": "v_hub"})
    d.node("Gust", "project:GustEOG", 40, 180, params={"t0": "t_gust", "v_gust": "v_gust", "T": "10.5"})
    d.node("WindMux", "stdlib:continuous/Mux2", 200, 120)
    d.node("WindSum", "stdlib:continuous/Sum", 290, 120, params={"signs": "[1.0, 1.0]"})
    d.sig("WindMean", "y", "WindMux", "u1")
    d.sig("Gust", "dv", "WindMux", "u2")
    d.sig("WindMux", "y", "WindSum", "u")
    d.sig("WindSum", "y", "Wind", "u")
    d.note("**Wind.** The IEC 61400-1 extreme operating gust (10.5 s) on the mean wind v_hub, the gust magnitude of "
           "class IB for this rotor.", 20, -60, 330, 60, "green")


def model_gust() -> dict:
    vh = 12.0
    wg = [g("v_hub", vh, "m/s", "Mean hub-height wind"),
          g("v_gust", f"3.3*{iec_sigma('v_hub')}/(1 + 0.1*2*R/42)", "m/s",
            "Gust magnitude, IEC 61400-1 class IB: 3.3 sigma1 / (1 + 0.1 D / Lambda1), Lambda1 = 42 m"),
          g("t_gust", 20.0, "s", "Start of the gust")]
    dash = {"autoRerun": True, "cards": [
        text("d1", "Extreme operating gust", "The IEC gust on **v_hub**: a dip, a rise of about 4 m/s within 5 s and a "
             "second dip. Near rated the dip drops the turbine into region 2.5; the rise overspeeds the rotor until the "
             "pitch catches up at 8 deg/s.", "2x2"),
        slider("d2", "Mean wind", "v_hub", 8.0, 24.0, 0.5, 1, "m/s"),
        slider("d3", "Gust start", "t_gust", 5.0, 40.0, 1.0, 0, "s"),
        *readouts(),
        plot("d4", "Wind (m/s)", ["Wind/y", "Aero/v_rel"], "4x2"),
        plot("d5", "Rotor speed (rpm)", ["RotorRPM/y"]),
        plot("d6", "Pitch (deg) and its command", ["Aero/beta_deg", "PitchCmdDeg/y"]),
        plot("d7", "Power (MW)", ["ElecPower/y"]),
        plot("d8", "Thrust (kN)", ["ThrustkN/y"]),
    ]}
    doc = closed_loop(wind_gust, "wind-turbine-gust",
                      "NREL 5 MW turbine with the baseline controller through an IEC extreme operating gust. Generated by "
                      "design/build_model.py.", 60.0, 6001, wg, vh, dash,
                      [{"id": "p8", "title": "Pitch command (deg)", "signals": ["PitchCmdDeg/y"]}])
    return doc


def wind_turbulent(d: Diagram) -> None:
    d.node("WindMean", "stdlib:sources/Constant", 40, 40, params={"value": "v_mean"})
    d.node("WhiteNoise", "stdlib:sources/BandLimitedWhiteNoise", 40, 160,
           params={"noise_power": "2*tau_turb*sigma_turb^2", "seed": "seed"}, constants={"sample_time": "0.25"})
    d.node("Turbulence", "stdlib:continuous/FirstOrder", 160, 220, params={"k": "1.0", "tau": "tau_turb"},
           starts={"x": "0.0"})
    d.sig("WhiteNoise", "y", "Turbulence", "u")
    d.node("WindMux", "stdlib:continuous/Mux2", 230, 120)
    d.node("WindSum", "stdlib:continuous/Sum", 300, 120, params={"signs": "[1.0, 1.0]"})
    d.sig("WindMean", "y", "WindMux", "u1")
    d.sig("Turbulence", "y", "WindMux", "u2")
    d.sig("WindMux", "y", "WindSum", "u")
    d.sig("WindSum", "y", "Wind", "u")
    d.note("**Turbulence.** Seeded band-limited white noise through a first-order filter (an Ornstein-Uhlenbeck "
           "process): standard deviation sigma_turb (IEC 61400-1 class B), time constant L/v with the Kaimal length "
           "scale L = 340.2 m, so its spectrum has the Kaimal level below 0.01 Hz and falls as f^-2 above "
           "(Kaimal: f^-5/3). One point, no rotor averaging.", 0, -80, 380, 90, "green")


def model_turbulent() -> dict:
    wg = [g("v_mean", 18.0, "m/s", "Mean hub-height wind"),
          g("sigma_turb", iec_sigma("v_mean"), "m/s", "Turbulence standard deviation, IEC 61400-1 class B (I_ref 0.14)"),
          g("tau_turb", "340.2/v_mean", "s", "Time constant of the turbulence filter: L/v, Kaimal L_u = 8.1 x 42 m"),
          g("seed", "7", None, "Seed of the noise")]
    dash = {"autoRerun": False, "cards": [
        text("d1", "Turbulent wind at 18 m/s", "Seeded turbulence (**sigma** from IEC class B) on **v_mean**. The pitch "
             "works continuously to hold 5 MW at 12.1 rpm; the tower sways with the thrust at its 0.32 Hz mode and "
             "the shaft rings at 2.2 Hz. Change the global **seed** for another realisation.", "2x2"),
        slider("d2", "Mean wind", "v_mean", 12.0, 24.0, 0.5, 1, "m/s"),
        *readouts(),
        plot("d4", "Wind (m/s)", ["Wind/y"], "4x2"),
        plot("d5", "Pitch (deg)", ["Aero/beta_deg"]),
        plot("d6", "Power (MW) and rotor speed (rpm)", ["ElecPower/y", "RotorRPM/y"]),
        plot("d7", "Tower-top deflection (m)", ["TowerSpring/q"]),
        plot("d8", "Shaft torque (twist, rad)", ["ShaftC/q"]),
    ]}
    return closed_loop(wind_turbulent, "wind-turbine-turbulent",
                       "NREL 5 MW turbine with the baseline controller in turbulent wind at 18 m/s. Generated by "
                       "design/build_model.py.", 600.0, 24001, wg, 18.0, dash)


def model_open_loop() -> dict:
    op = OL["operating_point"]
    d = Diagram()
    wind_pass(d)
    plant(d)
    d.node("WindConst", "stdlib:sources/Constant", 120, 120, params={"value": "v_ol"})
    d.sig("WindConst", "y", "Wind", "u")
    d.node("PitchFixed", "stdlib:sources/Constant", 2160, 300, params={"value": "pitch0*pi/180"})
    d.sig("PitchFixed", "y", "Aero", "beta")
    d.node("TorqueCmd", "stdlib:sources/Step", 1360, 200,
           params={"t_step": "t_step", "initial": "tq0", "final": "tq0*(1 + dtq)"})
    d.sig("TorqueCmd", "y", "Converter", "u")
    d.note("**Open loop.** Constant wind, fixed pitch and a fixed generator torque (the region-2 steady state at v_ol). "
           "The tower starts undeflected and rings down about its static deflection under the thrust (aerodynamic "
           "damping); at t_step the generator torque steps by dtq, which rings the drivetrain's torsion mode, and the "
           "rotor settles at a lower speed.", 1300, -60, 560, 90, "green")
    wg = [g("v_ol", op["v"], "m/s", "Constant wind"), g("t_step", 120.0, "s", "Time of the generator-torque step"),
          g("dtq", 0.05, None, "Relative generator-torque step")]
    params = plant_globals(op, 0.0) + wg
    dash = {"autoRerun": True, "cards": [
        text("d1", "Open loop: the aerodynamics", "Fixed pitch and generator torque at **v_ol**. The tower is released "
             "undeflected and rings at 0.32 Hz, damped mostly by the rotor's aerodynamics; at **t_step** the torque "
             "steps by **dtq** and the shaft rings at 2.22 Hz.", "2x2"),
        slider("d2", "Wind", "v_ol", 4.0, 11.0, 0.5, 1, "m/s"),
        slider("d3", "Torque step", "dtq", -0.2, 0.2, 0.01, 2),
        *readouts(),
        plot("d4", "Tower-top deflection (m)", ["TowerSpring/q"], "4x2"),
        plot("d5", "Shaft twist (rad)", ["ShaftC/q"]),
        plot("d6", "Rotor speed (rpm)", ["RotorRPM/y"]),
        plot("d7", "Tip-speed ratio and Cp", ["Aero/lambda", "Cp/y"]),
    ]}
    plots = [p for p in MAIN_PLOTS if p["id"] != "p5"] + [
        {"id": "p5", "title": "Generator torque (N m)", "signals": ["Converter/y", "TorqueCmd/y"]},
        {"id": "p8", "title": "Tip-speed ratio and Cp", "signals": ["Aero/lambda", "Cp/y"]}]
    return {"format": "bgsim.model", "language": "0.1.0", "name": "wind-turbine-open-loop",
            "$comment": "NREL 5 MW turbine in open loop (fixed pitch and generator torque): the tower and drivetrain modes. "
                        "Generated by design/build_model.py.",
            "diagram": d.doc(), "settings": settings(320.0, 32001), "plots": plots,
            "scene": {"file": "scenes/wind-turbine.sdf"}, "bindings": bindings("PitchFixed/y"), "parameters": params,
            "dashboard": dash}


def add_pitch_cmd(doc: dict) -> None:
    """The pitch command in degrees (a readout of the gust model)."""
    nodes = doc["diagram"]["nodes"]
    ids = {n["name"]: n["id"] for n in nodes}
    nid = f"n{len(nodes) + 1:03d}"
    nodes.append({"id": nid, "name": "PitchCmdDeg", "block": {"ref": "stdlib:continuous/Gain"},
                  "position": {"x": 2160, "y": 400}, "rotation": 0, "flipX": False, "params": {"k": num(1.0 / DEG)},
                  "constants": {}, "starts": {}, "ui": {"showLabel": True, "color": None}})
    conns = doc["diagram"]["connections"]
    conns.append({"id": f"c{len(conns) + 1:03d}", "kind": "signal", "from": {"node": ids["PitchCtrl"], "port": "beta_cmd"},
                  "to": {"node": nid, "port": "u"}})


# --------------------------------------------------------------------------- expected.json
NO_DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E106", "W206"],
           "note": "no algebraic loop, no causality conflict, no event storm"}


def ledger(tol=1e-4) -> dict:
    """The port-power ledger with the stored energy of the five storage elements."""
    return {"kind": "energy_ledger", "tol": tol,
            "stored": [{"coeff": 0.5 / J_ROTOR, "signal": "RotorInertia/P", "pow": 2},
                       {"coeff": 0.5 / J_GEN, "signal": "GenInertia/P", "pow": 2},
                       {"coeff": 0.5 / TW["m_gen"], "signal": "TowerMass/P", "pow": 2},
                       {"coeff": 0.5 * K_SHAFT, "signal": "ShaftC/q", "pow": 2},
                       {"coeff": 0.5 * TW["k_gen"], "signal": "TowerSpring/q", "pow": 2}],
            "note": "every bond's two ports carry opposite power (Tellegen); the kinetic and elastic energy of the two "
                    "inertias, the tower mass, the shaft and the tower spring changes by the work of the sources "
                    "(aerodynamic torque, thrust, generator) minus the shaft and tower damping; the balances integrate "
                    "the port powers with the trapezoid rule on the output grid, so their accuracy is set by how many "
                    "samples per period of the 2.2 Hz shaft oscillation the model records (tol 1e-3 for the step and "
                    "turbulent runs, 20 to 40 samples per second)"}


def steady_scenarios() -> dict:
    """One closed-loop run per wind speed, from a start 3 % below the design steady state: the final values against
    design/design.py (the same controller law and tables in numpy) and the region-3 pitch against Table 7-1."""
    out = {}
    for v in (5.0, 8.0, 10.0, 11.0, 12.0, 14.0, 18.0, 25.0):
        s = STEADY[v]
        t_end = 400.0 if v < 9.0 else 250.0
        start = {"global:v_start": v, "global:v_end": v, "global:rpm0": 0.97 * s["rpm_rotor"],
                 "global:pitch0": max(s["pitch_deg"] - 1.0, 0.0), "global:tq0": s["t_gen"],
                 "global:x0": s["x_tower"]}
        rep = s.get("pitch_deg_report")
        chk = [NO_DIAG,
               {"kind": "final_value", "t": t_end, "signal": "RotorRPM/y", "value": s["rpm_rotor"], "rtol": 2e-3,
                "note": f"steady state at {v:g} m/s, region {s['region']} (design/design.py)"},
               {"kind": "final_value", "t": t_end, "signal": "Converter/y", "value": s["t_gen"], "rtol": 4e-3,
                "note": "generator torque"},
               {"kind": "final_value", "t": t_end, "signal": "ElecPower/y", "value": s["p_elec"] * 1e-6, "rtol": 4e-3,
                "note": "electrical power (MW) = 0.944 x torque x speed"},
               {"kind": "final_value", "t": t_end, "signal": "Aero/thrust", "value": s["thrust"], "rtol": 5e-3, "note": "rotor thrust"},
               {"kind": "final_value", "t": t_end, "signal": "TowerSpring/q", "value": s["x_tower"], "rtol": 5e-3,
                "note": "tower-top deflection = thrust / k_tower"}]
        if s["region"] == "3":
            chk.append({"kind": "final_value", "t": t_end, "signal": "Aero/beta_deg", "value": s["pitch_deg"], "abs": 0.03,
                        "note": "pitch (design/design.py with the BEM tables)"})
            chk.append({"kind": "final_value", "t": t_end, "signal": "ElecPower/y", "value": 5.0, "rtol": 1e-3,
                        "note": "rated power: 5 MW electrical (5.29661 MW mechanical x 0.944)"})
            if rep is not None:
                tol = 0.15 if v <= 20.0 else 0.6
                chk.append({"kind": "final_value", "t": t_end, "signal": "Aero/beta_deg", "value": rep, "abs": tol,
                            "note": f"NREL/TP-500-38060 Table 7-1: {rep:.2f} deg at {v:g} m/s (FAST with flexible "
                                    "blades, the tower and the tilted, coned rotor; the BEM tables here are rigid; "
                                    "wider above 20 m/s, where the pitch is 0.25-0.5 deg lower)"})
        else:
            chk.append({"kind": "max_abs_le", "signal": "Aero/beta_deg", "from_t": t_end - 50.0, "value": 0.01,
                        "note": "below rated the pitch stays at fine pitch (the integrator is clamped at 0)"})
        out[f"wind-turbine-steady-{v:g}ms"] = {
            "model": "wind-turbine-steady", "settings": {"t_end": t_end, "output": {"points": int(t_end * 4) + 1}},
            "overrides": start, "checks": chk}
    return out


def expected() -> dict:
    steady_main = [{"kind": "scene_bindings"}, NO_DIAG]
    # the ramp: quasi-steady, read where the wind passes 8, 14 and 20 m/s (0.02 m/s per s: the lag is small)
    for v, tol_rpm, tol_p in ((8.0, 0.02, 0.05), (14.0, 0.01, 0.01), (20.0, 0.01, 0.01)):
        t = 60.0 + (v - 4.0) / 0.02
        s = STEADY[v]
        steady_main.append({"kind": "cursor_value", "signal": "RotorRPM/y", "t": t, "value": s["rpm_rotor"],
                            "rtol": tol_rpm, "note": f"ramp at {v:g} m/s: quasi-steady rotor speed (design/design.py); below rated the "
                                    "rotor lags the ramp by about 1.5 %, as its inertia must be spun up"})
        steady_main.append({"kind": "cursor_value", "signal": "ElecPower/y", "t": t, "value": s["p_elec"] * 1e-6,
                            "rtol": tol_p, "note": "quasi-steady electrical power (below rated about 4 % under the steady value: the "
                                    "speed lag, cubed in K w^2 times w)"})
    steady_main.append({"kind": "cursor_value", "signal": "Aero/beta_deg", "t": 60.0 + 16.0 / 0.02,
                        "value": STEADY[20.0]["pitch_deg"], "abs": 0.3, "note": "pitch at 20 m/s on the ramp"})
    steady_main.append({"kind": "max_abs_le", "signal": "ElecPower/y", "value": 5.05,
                        "note": "the power never exceeds rated by more than 1 % on the ramp"})
    steady_main.append(ledger(1e-4))
    s10, s18 = STEADY[10.0], STEADY[18.0]
    step = [{"kind": "scene_bindings"}, NO_DIAG,
            {"kind": "cursor_value", "signal": "RotorRPM/y", "t": 59.0, "value": s10["rpm_rotor"], "rtol": 2e-3,
             "note": "10 m/s, region 2 (design/design.py)"},
            {"kind": "cursor_value", "signal": "Aero/beta_deg", "t": 239.0, "value": s18["pitch_deg"], "abs": 0.1,
             "note": "18 m/s, the pitch of design/design.py; Table 7-1: 14.92 deg"},
            {"kind": "cursor_value", "signal": "ElecPower/y", "t": 239.0, "value": 5.0, "rtol": 2e-3,
             "note": "rated power at 18 m/s"},
            {"kind": "cursor_value", "signal": "RotorRPM/y", "t": 419.0, "value": s10["rpm_rotor"], "rtol": 2e-3,
             "note": "back at 10 m/s: the same region-2 state"},
            {"kind": "max_abs_le", "signal": "RotorRPM/y", "value": 12.1 * 1.15,
             "note": "the rotor overspeeds by less than 15 % after the 4 m/s step to 18 m/s"},
            {"kind": "max_abs_le", "signal": "Aero/beta_deg", "value": 20.0, "note": "pitch stays below 20 deg"},
            ledger(1e-3)]
    gust = [{"kind": "scene_bindings"}, NO_DIAG,
            {"kind": "cursor_value", "signal": "RotorRPM/y", "t": 19.0, "value": STEADY[12.0]["rpm_rotor"], "rtol": 2e-3,
             "note": "12 m/s steady state before the gust"},
            {"kind": "max_abs_le", "signal": "RotorRPM/y", "value": 12.1 * 1.15,
             "note": "the gust overspeeds the rotor by less than 15 %"},
            {"kind": "min_ge", "signal": "RotorRPM/y", "value": 11.0, "note": "and the dip does not stall it"},
            {"kind": "max_abs", "signal": "Wind/y", "value": 12.0 + 0.74 * 3.3 * 0.14 * (0.75 * 12.0 + 5.6) / 1.3,
             "rtol": 1e-4, "note": "EOG peak: v_hub + 0.74 v_gust"},
            {"kind": "cursor_value", "signal": "RotorRPM/y", "t": 59.5, "value": STEADY[12.0]["rpm_rotor"], "rtol": 5e-3,
             "note": "recovered 30 s after the gust"},
            ledger(1e-4)]
    turb = [{"kind": "scene_bindings"}, NO_DIAG,
            {"kind": "fft_peak", "signal": "TowerSpring/q", "from_t": 100.0, "to_t": 600.0, "min_hz": 0.2,
             "max_hz": 0.6, "highpass_hz": 0.1, "value": TW["f1_hz"], "rtol": 0.06,
             "note": f"tower fore-aft mode: {TW['f1_hz']:.4f} Hz (design/tower.py; report Table 9-1: 0.3240 Hz FAST, 0.3195 "
                     "Hz ADAMS); one periodogram, the peak anywhere in the half-power band (5 % damping in operation)"},
            {"kind": "fft_peak", "signal": "ShaftC/q", "from_t": 100.0, "to_t": 600.0, "min_hz": 1.5, "max_hz": 3.5,
             "highpass_hz": 1.0, "value": DT["f_hz"], "rtol": 0.06,
             "note": f"drivetrain torsion: {DT['f_hz']:.4f} Hz, two-inertia formula sqrt(k (1/J_r + 1/(N^2 J_g))); the "
                     "peak of one periodogram of a random response lies anywhere in the resonance's half-power band "
                     "(+-zeta f_n, 5 %), hence 6 %"},
            {"kind": "max_abs_le", "signal": "RotorRPM/y", "from_t": 50.0, "value": 12.1 * 1.15,
             "note": "the rotor speed stays within 15 % of rated"},
            {"kind": "min_ge", "signal": "RotorRPM/y", "from_t": 50.0, "value": 12.1 * 0.85,
             "note": "and above 85 % (region 3 throughout)"},
            {"kind": "max_abs_le", "signal": "ElecPower/y", "from_t": 50.0, "value": 5.6,
             "note": "constant-power torque law: the power follows the speed within about 10 %"},
            ledger(1e-3)]
    olm = OL["modes"]
    op = OL["operating_point"]
    ol_after = OL["after_step"]
    ol = [{"kind": "scene_bindings"}, NO_DIAG,
          {"kind": "damping", "signal": "TowerSpring/q", "from_t": 0.5, "to_t": 40.0, "zeta": olm["tower"]["zeta"],
           "zeta_abs": 0.005, "wn": olm["tower"]["wn"], "wn_rtol": 0.01, "min_wn": 1.0, "max_wn": 4.0,
           "note": f"tower ring-down: wn {olm['tower']['wn']:.4f} rad/s ({olm['tower']['f_hz']:.4f} Hz), zeta "
                   f"{olm['tower']['zeta']:.4f} = 1 % structural + aerodynamic damping (linearised plant, design/design.py)"},
          {"kind": "damping", "signal": "ShaftC/q", "from_t": 120.08, "to_t": 124.0, "offset": "linear",
           "zeta": olm["drivetrain"]["zeta"], "zeta_abs": 0.005, "wn": olm["drivetrain"]["wn"], "wn_rtol": 0.01,
           "min_wn": 8.0, "max_wn": 25.0,
           "note": f"drivetrain torsion after the torque step: wn {olm['drivetrain']['wn']:.4f} rad/s; the two-inertia "
                   f"formula gives {DT['wn']:.4f} rad/s ({DT['f_hz']:.4f} Hz) and zeta {DT['zeta']:.4f}"},
          {"kind": "cursor_value", "signal": "TowerSpring/q", "t": 119.0, "value": op["x_tower"], "rtol": 2e-3,
           "note": "the tower settles at thrust / k_tower"},
          {"kind": "cursor_value", "signal": "Aero/lambda", "t": 119.0, "value": op["lambda"], "rtol": 2e-4,
           "note": "the operating point of design/design.py (region 2 at 8 m/s)"},
          {"kind": "cursor_value", "signal": "Cp/y", "t": 119.0, "value": op["cp"], "rtol": 1e-4,
           "note": "Cp at the operating point"},
          {"kind": "final_value", "t": 320.0, "signal": "RotorRPM/y", "value": ol_after["rpm_rotor"], "rtol": 2e-3,
           "note": "after the 5 % torque step the rotor slows until the aerodynamic torque matches (design/design.py)"},
          {"kind": "final_value", "t": 320.0, "signal": "Aero/lambda", "value": ol_after["lambda"], "rtol": 2e-3,
           "note": "the new tip-speed ratio"},
          ledger(1e-5)]
    return {"project": "wind-turbine",
            "description": "NREL 5 MW reference wind turbine (NREL/TP-500-38060): rotational and translational bond "
                           "graph with BEM Cp/Ct tables and the baseline controller. Numbers come from design/design.json "
                           "(BEM, tower finite elements, the controller law in numpy) and from the report's Table 7-1.",
            "models": {"wind-turbine-steady": {"checks": steady_main}, **steady_scenarios(),
                       "wind-turbine-step": {"checks": step}, "wind-turbine-gust": {"checks": gust},
                       "wind-turbine-turbulent": {"checks": turb}, "wind-turbine-open-loop": {"checks": ol}}}


def main() -> int:
    (EXAMPLE / "scenes").mkdir(exist_ok=True)
    (EXAMPLE / "models").mkdir(exist_ok=True)
    (EXAMPLE / "scenes" / "wind-turbine.sdf").write_text(scene(), encoding="utf-8", newline="\n")
    gust = model_gust()
    add_pitch_cmd(gust)
    docs = [model_steady(), model_step(), gust, model_turbulent(), model_open_loop()]
    for doc in docs:
        path = EXAMPLE / "models" / f"{doc['name']}.bgmodel.json"
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("wrote", path.relative_to(EXAMPLE))
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "wind-turbine", "models": [d["name"] for d in docs],
            "libraryDir": "library", "scenesDir": "scenes"}
    (EXAMPLE / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    (EXAMPLE / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
