# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Write the fem-gantry example: the models, the scenes, the expected checks.

An H-gantry: two parallel X axes (ironcore linear motors on profile-rail guides) carry the ends
of an aluminium box crossbeam, 1400 x 60 x 100 mm, a FEM flexible body (`ModalBody3D`) reduced
by Craig-Bampton with two interfaces (A: the end bracket on the X1 carriage, B: the end
bracket on the X2 carriage) and a rail on its front wall along which a Y carriage with a tool
runs (the moving interface E and the slide S of ModalBody3D).

    julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl examples/fem-gantry/design/beam.fem.json
    uv run examples/fem-gantry/design/build.py

Models:

* `fem-gantry`: point-to-point X moves of 0.5 m out and back. Each X axis has its own servo
  drive (`library/AxisServo.jl`: P position loop, PI velocity loop with acceleration
  feedforward, an optional notch, a current loop); both follow one jerk-limited reference,
  plain or input-shaped (ZV, ZVD; the global `shaping`). The Y carriage holds its position
  `y_c` on the rail with its own servo. The beam is welded to X1 and pivots on X2 (the usual
  fixed/floating pair that keeps the two X axes from fighting each other). Gravity is off: in
  this linear model the weight only adds a constant sag, which `gantry-static` checks.
* `gantry-static`: the beam alone clamped at both ends with the Y carriage at mid-span, under
  1 g along x (the inertia load of a 9.81 m/s^2 X move): the deflection and the stresses
  against beam theory.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = "fem-gantry"
STATIC = "gantry-static"
MODAL_FILE = "data/beam.modal.json"
MODAL = json.loads((ROOT / MODAL_FILE).read_text(encoding="utf-8"))
SPEC = json.loads((HERE / "beam.fem.json").read_text(encoding="utf-8"))
NM = MODAL["nm"]
M_BEAM = MODAL["mass"]
RAIL = MODAL["rail"]
RAIL_X0, RAIL_Y0 = RAIL["start"][0], RAIL["start"][1]     # rail start in R (front wall, 110 mm from A)
RAIL_L = RAIL["length"]
L_AB = MODAL["interfaces"][1]["position"][1]                # A to B along the beam (R frame), 1.32 m
STRESS = MODAL["stress"]

# --- material and section (beam theory for the README and the checks) ----------------------
E_AL, NU_AL, RHO_AL = SPEC["material"]["E"], SPEC["material"]["nu"], SPEC["material"]["rho"]
G_AL = E_AL / (2 * (1 + NU_AL))
_OUT, _IN = SPEC["geometry"]["cut"][0]["box"], SPEC["geometry"]["cut"][1]["box"]
# the cross-section (x, z) of the box: outer 60 x 100 mm, the inner hole offset to the back
# (front wall 10 mm, the rail seat; the other walls 4 mm)
BX, BZ = _OUT["size"][0], _OUT["size"][2]
HX, HZ = _IN["size"][0], _IN["size"][2]
HX0 = _IN["corner"][0] + HX / 2                              # hole centre x (-3 mm)
A_SEC = BX * BZ - HX * HZ
XC = (-HX * HZ * HX0) / A_SEC                                # centroid x (front-heavy, +7.2 mm)
I_Z = (BZ * BX**3 / 12 + BX * BZ * XC**2) - (HZ * HX**3 / 12 + HX * HZ * (HX0 - XC) ** 2)   # x-bending
I_X = BX * BZ**3 / 12 - HX * HZ**3 / 12                     # z-bending
T_FRONT, T_BACK = BX / 2 - (HX0 + HX / 2), (HX0 - HX / 2) + BX / 2   # 10 mm, 4 mm
T_TB = (BZ - HZ) / 2                                         # top and bottom walls, 4 mm
MPL = RHO_AL * A_SEC                                         # kg/m
# closed thin-walled section (Bredt): the enclosed mid-line area and the torsion constant
B_M, H_M = BX - (T_FRONT + T_BACK) / 2, BZ - T_TB              # mid-line width and height
A_M = B_M * H_M
J_T = 4 * A_M**2 / (H_M / T_FRONT + H_M / T_BACK + 2 * B_M / T_TB)
# shear areas: x-bending is carried by the top and bottom walls, z-bending by the front and back
AS_X = 2 * T_TB * BX
AS_Z = (T_FRONT + T_BACK) * HZ
# the clamped ends: the interface regions are rigid (RBE2 over every surface node of the
# first and last 80 mm), so the elastic span runs between them
A_END = SPEC["interfaces"][0]["select"]["box"]["max"][1]                 # 0.08
B_START = SPEC["interfaces"][1]["select"]["box"]["min"][1]               # 1.32
L_PART = _OUT["size"][1]                                                 # 1.40
L_SPAN = B_START - A_END                                                 # 1.24 m, clamped-clamped
L_CANT = L_PART - A_END                                                  # 1.32 m, clamped at A only
M_CAP = RHO_AL * BX * BZ * _IN["corner"][1]                              # 10 mm end cap

# --- machine ----------------------------------------------------------------------------
# heights (world z): the X carriages' centres of mass, the beam axis (= R, interface A)
ZX, ZB = 0.50, 0.60
# X carriage: ironcore forcer (2.5 kg), carriage plate and two size-20 guide blocks (3 kg),
# the end bracket (1.5 kg); 200 x 160 x 80 mm
M_XC = 7.0
J_XC = [M_XC / 12 * (0.16**2 + 0.08**2), M_XC / 12 * (0.20**2 + 0.08**2), M_XC / 12 * (0.20**2 + 0.16**2)]
# X guide (two size-20 blocks, preload class medium): 4e8 N/m across, 1.5e6 N*m/rad about
# every axis (the yaw of two blocks 120 mm apart dominates)
KT_X, KR_X = 4.0e8, 1.5e6
# the bolted end brackets: a stiff joint about z (the A end) and the pivot of the floating
# B end; both are Revolute3D held as stiff as the guide in the other five directions
KT_W, KR_W, KW = 4.0e8, 1.5e6, 1.0e6
D_PIVOT = 1.0                                     # bearing friction of the B pivot, N*m*s/rad
# Y carriage: carriage plate, Z axis (a ball-screw slide with its motor) and the process head (a
# small spindle or dispensing head): 12 kg, about 160 x 300 x 180 mm (forward, down, along the
# beam), its centre of mass 80 mm in front of and 100 mm below the rail line
M_YC = 12.0
CX, CY = 0.08, 0.10
YC_BOX = (0.16, 0.30, 0.18)
J_YC = [M_YC / 12 * (YC_BOX[1] ** 2 + YC_BOX[2] ** 2), M_YC / 12 * (YC_BOX[0] ** 2 + YC_BOX[2] ** 2),
        M_YC / 12 * (YC_BOX[0] ** 2 + YC_BOX[1] ** 2)]
# the tool point, from the carriage's centre of mass (rail frame: x forward, y down): 350 mm
# below the rail line, at the end of the Z axis
TX, TY = 0.02, 0.25
# Y guide on the rail (two size-15 blocks) and the slide coupling (the Y carriage rides on the
# moving rail frame E through a Prismatic3D whose axis is held by a stiff drive spring)
KT_Y, KR_Y = 3.0e8, 1.0e6
KD_Y = 2.0e8
MS = 0.05                                         # slider mass of the rail coordinate s
# the servos (per axis): P position, PI velocity, acceleration feedforward, current loop
FP_X, FV_X, FI = 15.0, 60.0, 1000.0
FP_Y, FV_Y = 10.0, 40.0
# the optional notch of the X velocity loops: at the first lightly damped beam mode of the closed
# loop: the carriage rocking on the twisting beam, 167 Hz with the guides' compliance (192 Hz in the
# rigid-joint design/reference.py); a full notch there, f_n / 2 wide
F_NOTCH = 167.0
M_X = M_XC + (M_BEAM + M_YC + MS) / 2             # the mass each X drive is tuned for
M_Y = M_YC + MS
ZETA = 0.01                                       # modal damping of the aluminium beam
# stress: the allowable for 10^8 move cycles of an extruded EN AW-6063 T6 beam (fatigue of
# the parent material, EN 1999-1-3 detail category 71 extrapolated past 10^8 cycles, rounded
# down), against a yield strength of 170 MPa
SIGMA_ALLOW = 40.0e6
YIELD = 170.0e6
STRESS_RANGE = 2.0e6
# the moves
DX = 0.5
T1, T2 = 0.1, 1.0
T_END = 1.8
MOVE = dict(a_max=10.0, v_max=1.0, j_max=5000.0)
# the tool's settling band
BAND = 10.0e-6

# the tool point at rest (world); the rail frame E: x forward, y down (-z), z along the beam
TOOL0 = [RAIL_X0 + CX + TX, None, ZB - CY - TY]


def fmt(x: float) -> str:
    return repr(float(x))


def vec(xs) -> str:
    return "[" + ", ".join(fmt(x) for x in xs) + "]"


def node(nid, ref, x, y, params=None, constants=None, starts=None, name=None):
    full = ref if ":" in ref else f"stdlib:{ref}"
    return {
        "id": nid,
        "name": name or nid,
        "block": {"ref": full},
        "position": {"x": x, "y": y},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": constants or {},
        "starts": starts or {},
        "ui": {"showLabel": True, "color": None},
    }


def conn(cid, kind, a, ap, b, bp):
    return {"id": cid, "kind": kind, "from": {"node": a, "port": ap}, "to": {"node": b, "port": bp},
            "route": [], "label": None}


class Diagram:
    def __init__(self):
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.count = 0

    def add(self, *args, **kw):
        n = node(*args, **kw)
        self.nodes.append(n)
        return n["id"]

    def link(self, kind, a, ap, b, bp):
        self.count += 1
        self.conns.append(conn(f"c{self.count}", kind, a, ap, b, bp))

    def bond(self, a, ap, b, bp):
        self.link("bond", a, ap, b, bp)

    def wire(self, a, ap, b, bp):
        self.link("wire", a, ap, b, bp)

    def signal(self, a, ap, b, bp):
        self.link("signal", a, ap, b, bp)


Q_ZX = [math.cos(math.pi / 4), 0.0, math.sin(math.pi / 4), 0.0]      # joint z -> world x
Q_XZ = [math.cos(math.pi / 4), 0.0, -math.sin(math.pi / 4), 0.0]     # and back


def quat(q) -> dict:
    return {"qw": fmt(q[0]), "qx": fmt(q[1]), "qy": fmt(q[2]), "qz": fmt(q[3])}


def damping(k: float, m: float, zeta: float = 0.05) -> float:
    return 2 * zeta * math.sqrt(k * m)


def x_axis(d: Diagram, tag: str, y: float, px: int, py: int, kf: str) -> str:
    """Ground -> mount (joint z along world x) -> Prismatic3D -> turn back -> X carriage, the
    linear motor on the joint drive, the servo, the pose chain. Returns the carriage id."""
    d.add(f"World{tag}", "multibond/GroundSpatial", px, py)
    # The mount carries the inverse of the joint frame's world pose and has the ground on its
    # child side b: the transform computes a.f from b.f and b.e from a.e, so with the ground
    # (a flow source) on b every equation stays explicit. With the ground on a, the six flows
    # and efforts of each axis would be a linear algebraic loop (24 algebraic unknowns, a DAE).
    d.add(f"{tag}Mount", "multibond/FixedTransform3DNeutral", px + 120, py, {**quat(Q_XZ), "x": fmt(ZX), "y": fmt(-y)})
    d.add(tag, "spatial/Prismatic3D", px + 240, py,
          {"kt": fmt(KT_X), "kr": fmt(KR_X), "bt": fmt(damping(KT_X, M_XC)), "br": fmt(damping(KR_X, J_XC[2]))})
    d.add(f"{tag}Turn", "multibond/FixedTransform3DNeutral", px + 360, py, quat(Q_XZ))
    d.add(f"{tag}Car", "spatial/RigidBody3D", px + 480, py, {"m": fmt(M_XC), "J": vec(J_XC), "g0": "0.0"})
    d.bond(f"World{tag}", "p", f"{tag}Mount", "b")
    d.bond(f"{tag}Mount", "a", tag, "parent")
    d.bond(tag, "child", f"{tag}Turn", "a")
    d.bond(f"{tag}Turn", "b", f"{tag}Car", "p")
    # motor and servo
    d.add(f"{tag}Motor", "translation/ForceSource", px + 240, py - 120, {"F": "1.0"})
    d.add(f"{tag}Stator", "translation/Fixed", px + 120, py - 120)
    # the forcer pushes the carriage (port b on the drive) against the stator (port a): a
    # positive F moves the axis to +q
    d.wire(f"{tag}Motor", "b", tag, "drive")
    d.wire(f"{tag}Motor", "a", f"{tag}Stator", "a")
    d.add(f"{tag}Servo", "project:AxisServo", px + 240, py - 240,
          {"M": "M_x", "fp": "fp_x", "fv": "fv_x", "kff": "1.0", "fi": "f_i", "kf": kf,
           "fn": "f_n", "bn": "b_n", "dn": "notch"})
    d.signal("Ref", "q", f"{tag}Servo", "x_ref")
    d.signal("Ref", "v", f"{tag}Servo", "v_ref")
    d.signal("Ref", "a", f"{tag}Servo", "a_ref")
    d.signal(tag, "qout", f"{tag}Servo", "x")
    d.signal(tag, "qdout", f"{tag}Servo", "v")
    d.signal(f"{tag}Servo", "F", f"{tag}Motor", "u")
    # poses: mount, joint, turn -> the carriage
    d.add(f"P{tag}Mount", "spatial/LocalPose3D", px + 120, py + 120, {**quat(Q_ZX), "y": fmt(y), "z": fmt(ZX)})
    d.add(f"P{tag}J", "multibond/ComposePose3D", px + 240, py + 120)
    d.add(f"P{tag}Turn", "spatial/LocalPose3D", px + 360, py + 200, quat(Q_XZ))
    d.add(f"P{tag}Car", "multibond/ComposePose3D", px + 480, py + 120)
    d.signal(f"P{tag}Mount", "g", f"P{tag}J", "gp")
    d.signal(tag, "pose", f"P{tag}J", "gl")
    d.signal(f"P{tag}J", "g", f"P{tag}Car", "gp")
    d.signal(f"P{tag}Turn", "g", f"P{tag}Car", "gl")
    d.signal(f"P{tag}Car", "g", f"{tag}Car", "g")
    return f"{tag}Car"


def end_joint(d: Diagram, tag: str, car: str, port: str, px: int, py: int, weld: bool) -> str:
    """The end bracket: a Revolute3D about z at the carriage's centre of mass (held by a stiff
    torsion spring for the weld at A, free but for bearing friction for the pivot at B) and
    the offset up to the beam axis. Returns the id of the joint's world pose."""
    d.add(tag, "spatial/Revolute3D", px, py,
          {"kt": fmt(KT_W), "kr": fmt(KR_W), "bt": fmt(damping(KT_W, M_XC)), "br": fmt(damping(KR_W, J_XC[2]))})
    d.add(f"{tag}Ground", "rotation/FixedShaft", px, py - 180)
    if weld:
        d.add(f"{tag}Spring", "rotation/TorsionSpring", px, py - 90, {"k": fmt(KW)})
        d.add(f"{tag}Damper", "rotation/RotationalDamper", px + 90, py - 90, {"d": fmt(damping(KW, 1.0))})
        d.wire(f"{tag}Ground", "a", f"{tag}Spring", "a")
        d.wire(f"{tag}Spring", "b", tag, "drive")
        d.wire(f"{tag}Ground", "a", f"{tag}Damper", "a")
        d.wire(f"{tag}Damper", "b", tag, "drive")
    else:
        d.add(f"{tag}Friction", "rotation/RotationalDamper", px, py - 90, {"d": fmt(D_PIVOT)})
        d.wire(f"{tag}Ground", "a", f"{tag}Friction", "a")
        d.wire(f"{tag}Friction", "b", tag, "drive")
    d.add(f"{tag}Bracket", "multibond/FixedTransform3DNeutral", px + 120, py, {"z": fmt(ZB - ZX)})
    d.bond(tag, "parent", car, "p")
    d.bond(tag, "child", f"{tag}Bracket", "a")
    d.bond(f"{tag}Bracket", "b", "Beam", port)
    d.add(f"P{tag}", "multibond/ComposePose3D", px, py + 120)
    d.add(f"P{tag}Offset", "spatial/LocalPose3D", px + 120, py + 200, {"z": fmt(ZB - ZX)})
    d.add(f"P{tag}Beam", "multibond/ComposePose3D", px + 120, py + 120)
    d.signal(f"P{car}", "g", f"P{tag}", "gp")
    d.signal(tag, "pose", f"P{tag}", "gl")
    d.signal(f"P{tag}", "g", f"P{tag}Beam", "gp")
    d.signal(f"P{tag}Offset", "g", f"P{tag}Beam", "gl")
    return f"P{tag}Beam"


def y_carriage(d: Diagram, px: int, py: int, servo: bool) -> None:
    """The Y carriage on the moving rail frame E: Prismatic3D (its axis = the rail, held by a
    stiff drive spring) -> offset to the centre of mass -> RigidBody3D; the Y motor acts on the
    slide S (rail coordinate s), held by the Y servo at y_c; the pose chain to the tool."""
    d.add("YGuide", "spatial/Prismatic3D", px, py,
          {"kt": fmt(KT_Y), "kr": fmt(KR_Y), "bt": fmt(damping(KT_Y, M_YC)), "br": fmt(damping(KR_Y, J_YC[0]))})
    d.add("YOffset", "multibond/FixedTransform3DNeutral", px + 120, py, {"x": fmt(CX), "y": fmt(CY)})
    d.add("YCar", "spatial/RigidBody3D", px + 240, py,
          {"m": fmt(M_YC), "J": vec(J_YC), "g0": "g_y" if not servo else "0.0"})
    d.bond("YGuide", "parent", "Beam", "E")
    d.bond("YGuide", "child", "YOffset", "a")
    d.bond("YOffset", "b", "YCar", "p")
    d.add("YCoupling", "translation/Fixed", px - 120, py - 120)
    d.add("YCouplingSpring", "translation/Spring", px, py - 120, {"k": fmt(KD_Y)})
    d.add("YCouplingDamper", "translation/Damper", px + 120, py - 120, {"d": fmt(damping(KD_Y, M_YC, 0.3))})
    d.wire("YCoupling", "a", "YCouplingSpring", "a")
    d.wire("YCouplingSpring", "b", "YGuide", "drive")
    d.wire("YCoupling", "a", "YCouplingDamper", "a")
    d.wire("YCouplingDamper", "b", "YGuide", "drive")
    d.add("YMotor", "translation/ForceSource", px - 120, py - 240, {"F": "1.0"})
    d.add("YStator", "translation/Fixed", px - 240, py - 240)
    d.bond("YMotor", "b", "Beam", "S")          # b on the slide: a positive F moves the carriage to +s
    d.wire("YMotor", "a", "YStator", "a")
    if servo:
        d.add("YRef", "sources/Constant", px - 360, py - 400, {"value": "y_c"})
        d.add("Zero", "sources/Constant", px - 360, py - 320, {"value": "0.0"})
        d.add("YServo", "project:AxisServo", px - 120, py - 360,
              {"M": fmt(M_Y), "fp": fmt(FP_Y), "fv": fmt(FV_Y), "kff": "1.0", "fi": "f_i"})
        d.signal("YRef", "y", "YServo", "x_ref")
        d.signal("Zero", "y", "YServo", "v_ref")
        d.signal("Zero", "y", "YServo", "a_ref")
        d.signal("Beam", "s", "YServo", "x")
        d.signal("Beam", "sd", "YServo", "v")
        d.signal("YServo", "F", "YMotor", "u")
    else:
        # the static model: the slide held by a stiff, damped spring (no force along the rail)
        d.add("YRef", "sources/Constant", px - 360, py - 320, {"value": "0.0"})
        d.signal("YRef", "y", "YMotor", "u")
    d.add("PYJ", "multibond/ComposePose3D", px, py + 120)
    d.add("PYOffset", "spatial/LocalPose3D", px + 120, py + 200, {"x": fmt(CX), "y": fmt(CY)})
    d.add("PYCar", "multibond/ComposePose3D", px + 240, py + 120)
    d.add("PToolOffset", "spatial/LocalPose3D", px + 360, py + 200, {"x": fmt(TX), "y": fmt(TY)})
    d.add("PTool", "multibond/ComposePose3D", px + 360, py + 120)
    d.signal("Beam", "poseE", "PYJ", "gp")
    d.signal("YGuide", "pose", "PYJ", "gl")
    d.signal("PYJ", "g", "PYCar", "gp")
    d.signal("PYOffset", "g", "PYCar", "gl")
    d.signal("PYCar", "g", "YCar", "g")
    d.signal("PYCar", "g", "PTool", "gp")
    d.signal("PToolOffset", "g", "PTool", "gl")


def reference(d: Diagram, px: int, py: int) -> None:
    """Six SCurveProfile moves (three shaper impulses for the move out, three for the move
    back) summed into the X reference."""
    for k, (sign, t0) in enumerate((("", "t1"), ("-", "t2"))):
        for j in range(3):
            pid = f"{'Out' if k == 0 else 'Back'}{j}"
            w = f"(w{j} + 1e-9)"
            d.add(pid, "motion/SCurveProfile", px, py + 100 * (3 * k + j),
                  {"q_start": "0.0", "q_end": f"{sign}dX*w{j}", "t_start": f"{t0} + d{j}",
                   "v_max": f"v_max*{w}", "a_max": f"a_max*{w}", "j_max": f"j_max*{w}"})
    d.add("Ref", "project:MoveSum", px + 200, py + 250)
    for i, pid in enumerate(["Out0", "Out1", "Out2", "Back0", "Back1", "Back2"], start=1):
        for p in ("q", "v", "a"):
            d.signal(pid, p, "Ref", f"{p}{i}")


def glob(name, value, unit, description):
    return {"name": name, "value": value if isinstance(value, str) else fmt(value), "unit": unit,
            "description": description}


def globals_main(f_s: float, zeta_s: float) -> list[dict]:
    return [
        glob("Pi", math.pi, None, "pi (a global expression cannot use the built-in constant)"),
        glob("dX", DX, "m", "Length of the X move (out at t1, back at t2)"),
        glob("t1", T1, "s", "Start of the move out"),
        glob("t2", T2, "s", "Start of the move back"),
        glob("a_max", MOVE["a_max"], "m/s^2", "Largest acceleration of the X move"),
        glob("v_max", MOVE["v_max"], "m/s", "Largest speed of the X move"),
        glob("j_max", MOVE["j_max"], "m/s^3", "Jerk of the X move"),
        glob("shaping", 0.0, None, "Input shaper: 0 none, 1 ZV (two impulses), 2 ZVD (three impulses)"),
        glob("f_s", f_s, "Hz", "Frequency the shaper (and the notch) cancel: the dominant tool vibration after a plain move"),
        glob("zeta_s", zeta_s, None, "Damping ratio the shaper assumes (of the same mode)"),
        glob("Kz", "exp(-zeta_s*Pi/sqrt(1 - zeta_s^2))", None, "Shaper: the decay of the mode over half a damped period"),
        glob("Td", "1/(f_s*sqrt(1 - zeta_s^2))", "s", "Shaper: the damped period"),
        glob("w0", "(shaping - 1)*(shaping - 2)/2 - shaping*(shaping - 2)/(1 + Kz) + shaping*(shaping - 1)/2/(1 + Kz)^2", None,
             "Shaper: the first impulse (1, ZV 1/(1+K), ZVD 1/(1+K)^2; the Lagrange polynomial through shaping = 0, 1, 2)"),
        glob("w1", "-shaping*(shaping - 2)*Kz/(1 + Kz) + shaping*(shaping - 1)*Kz/(1 + Kz)^2", None,
             "Shaper: the second impulse at Td/2 (0, ZV K/(1+K), ZVD 2K/(1+K)^2)"),
        glob("w2", "shaping*(shaping - 1)/2*Kz^2/(1 + Kz)^2", None, "Shaper: the third impulse at Td (ZVD K^2/(1+K)^2)"),
        glob("d0", 0.0, "s", "Shaper: the time of the first impulse"),
        glob("d1", "Td/2", "s", "Shaper: the time of the second impulse"),
        glob("d2", "Td", "s", "Shaper: the time of the third impulse"),
        glob("notch", 1.0, None, "Notch depth in both X velocity loops at f_n: 1 off, 0 a full notch"),
        glob("f_n", F_NOTCH, "Hz", "Notch centre frequency: the first lightly damped beam mode in the X loops"),
        glob("b_n", "f_n/2", "Hz", "Notch width"),
        glob("y_c", RAIL_L / 2, "m", f"Y carriage position on the rail (0 to {RAIL_L} m; {RAIL_L / 2} is mid-span)"),
        glob("kf2", 1.0, None, "Force constant of the X2 motor relative to the one its drive assumes (racking: 0.9 is 10 % weak)"),
        glob("M_x", M_X, "kg", "The mass each X drive's gains are tuned for: an X carriage and half of the beam and Y carriage"),
        glob("fp_x", FP_X, "Hz", "X position loop bandwidth"),
        glob("fv_x", FV_X, "Hz", "X velocity loop bandwidth"),
        glob("f_i", FI, "Hz", "Current loop bandwidth of every drive"),
        glob("zeta", ZETA, None, "Modal damping ratio of the beam"),
    ]


def mode_shapes():
    return {"target": "visual:beam_mesh", "property": "mode-shapes",
            "signal": [f"Beam/eta[{i}]" for i in range(1, NM + 1)],
            "stress": {"colormap": "heat", "range": [0.0, STRESS_RANGE]}}


def pose(link, sig):
    return {"target": f"link:{link}", "property": "pose", "signal": [f"{sig}[{i}]" for i in range(1, 8)]}


def settings(t_end, points):
    return {"t_start": 0.0, "t_end": t_end, "solver": "Rodas5P", "reltol": 1e-06, "abstol": 1e-09,
            "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 10000}


def gantry(f_s: float, zeta_s: float) -> dict:
    d = Diagram()
    reference(d, 40, 40)
    x1 = x_axis(d, "X1", 0.0, 400, 900, "1.0")
    x2 = x_axis(d, "X2", L_AB, 400, 1500, "kf2")
    d.add("Beam", "spatial/ModalBody3D", 1500, 1200,
          {"zeta": "zeta", "g0": "0.0", "ms": fmt(MS), "s0": "y_c"}, {"file": MODAL_FILE, "stiffening": 0})
    pa = end_joint(d, "WeldA", x1, "A", 1100, 900, True)
    end_joint(d, "PivotB", x2, "B", 1100, 1500, False)
    d.signal(pa, "g", "Beam", "gA")
    y_carriage(d, 1900, 1200, True)
    d.add("Mon", "project:GantryMonitor", 2400, 700,
          {"x0": fmt(TOOL0[0]), "y0": f"{fmt(RAIL_Y0)} + y_c", "z0": fmt(TOOL0[2]), "band": fmt(BAND),
           "sigma_allow": fmt(SIGMA_ALLOW)})
    d.signal("PTool", "g", "Mon", "g")
    d.signal("Ref", "q", "Mon", "x_ref")
    d.signal("Ref", "v", "Mon", "v_ref")
    d.signal("X1", "qout", "Mon", "x1")
    d.signal("X2", "qout", "Mon", "x2")
    d.signal("Beam", "sigma_max", "Mon", "sigma")
    bindings = [pose("x1car", "PX1Car/g"), pose("x2car", "PX2Car/g"), pose("beam", "Beam/pose"),
                pose("ycar", "PYCar/g"), pose("tool", "PTool/g"), mode_shapes()]
    plots = [
        {"id": "p1", "title": "Tool error (um): x, y, z", "signals": ["Mon/ex", "Mon/ey", "Mon/ez"]},
        {"id": "p2", "title": "X reference and axes (m)", "signals": ["Ref/q", "X1/qout", "X2/qout"]},
        {"id": "p3", "title": "Racking X1 - X2 (um)", "signals": ["Mon/rack"]},
        {"id": "p4", "title": "Motor forces (N)", "signals": ["X1Servo/F", "X2Servo/F", "YServo/F"]},
        {"id": "p5", "title": "Beam von Mises stress (Pa): hotspots and peak",
         "signals": ["Beam/sigma_vm[1]", "Beam/sigma_vm[2]", "Beam/sigma_vm[3]", "Beam/sigma_max"]},
        {"id": "p6", "title": "Modal coordinates (m)", "signals": [f"Beam/eta[{i}]" for i in range(1, NM + 1)]},
        {"id": "p7", "title": "Settling time of the last move (s)", "signals": ["Mon/settle"]},
    ]
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": NAME,
        "parameters": globals_main(f_s, zeta_s),
        "diagram": {"nodes": d.nodes, "connections": d.conns, "subsystemPorts": [], "annotations": []},
        "settings": settings(T_END, 3601),
        "plots": plots,
        # the deflections are tens of micrometres: the view opens at x100 (marked exaggerated)
        "scene": {"file": f"scenes/{NAME}.sdf", "exaggeration": 100},
        "bindings": bindings,
        "dashboard": dashboard(f_s),
    }


def card(cid, kind, size, title, **kw):
    c = {"id": cid, "kind": kind, "size": size, "title": title}
    c.update(kw)
    return c


def dashboard(f_s: float) -> dict:
    text = (
        "An **H-gantry**: two linear-motor X axes carry a 1.4 m aluminium box beam (a FEM flexible "
        "body) with a Y carriage and a tool. Pick the **acceleration**, the **input shaper** "
        "(0 none, 1 ZV, 2 ZVD) or the **notch**, where the **Y carriage** sits and how much "
        "weaker the **X2 motor** is, press **Run**, then open the **3D View**: the beam is "
        f"coloured by von Mises stress (0 to {STRESS_RANGE / 1e6:.0f} MPa) and its deflection drawn x100.\n\n"
        f"The shaper cancels f_s = {f_s:.1f} Hz, the tool's ringing after a plain move; the notch "
        f"sits in both X velocity loops at {F_NOTCH:.0f} Hz, the first lightly damped beam mode. "
        f"Settling: the tool within +-{BAND * 1e6:.0f} um."
    )
    return {
        "autoRerun": False,
        "cards": [
            card("intro", "text", "2x2", "Gantry moves, shaping and stress", options={"markdown": True, "text": text}),
            card("a_max", "slider", "1x1", "Acceleration", parameter="global:a_max",
                 options={"min": 2.0, "max": 30.0, "step": 1.0, "decimals": 0, "unit": "m/s²"}),
            card("j_max", "slider", "1x1", "Jerk", parameter="global:j_max",
                 options={"min": 200.0, "max": 20000.0, "step": 100.0, "decimals": 0, "unit": "m/s³"}),
            card("shaping", "slider", "1x1", "Shaper: 0 none, 1 ZV, 2 ZVD", parameter="global:shaping",
                 options={"min": 0.0, "max": 2.0, "step": 1.0, "decimals": 0, "unit": ""}),
            card("notch", "slider", "1x1", "Notch depth (1 off, 0 full)", parameter="global:notch",
                 options={"min": 0.0, "max": 1.0, "step": 0.1, "decimals": 1, "unit": ""}),
            card("y_c", "slider", "1x1", "Y carriage on the rail", parameter="global:y_c",
                 options={"min": 0.0, "max": RAIL_L, "step": 0.05, "decimals": 2, "unit": "m"}),
            card("kf2", "slider", "1x1", "X2 motor force constant", parameter="global:kf2",
                 options={"min": 0.8, "max": 1.2, "step": 0.01, "decimals": 2, "unit": ""}),
            card("settle", "value", "1x1", "Settling time (last move)", signals=["Mon/settle"],
                 options={"decimals": 3, "unit": "s", "sparkline": True}),
            card("stress", "gauge", "1x1", "Peak stress / allowable", signals=["Mon/util"],
                 options={"min": 0.0, "max": 100.0, "decimals": 2, "unit": "%",
                          "zones": [{"from": 0.0, "to": 60.0, "tone": "good"},
                                    {"from": 60.0, "to": 90.0, "tone": "warn"},
                                    {"from": 90.0, "to": 100.0, "tone": "bad"}]}),
            card("sigma", "value", "1x1", f"Peak von Mises (allowable {SIGMA_ALLOW / 1e6:.0f} MPa)",
                 signals=["Mon/sigma_MPa"], options={"decimals": 3, "unit": "MPa", "sparkline": True}),
            card("rack", "value", "1x1", "Racking X1 - X2", signals=["Mon/rack"],
                 options={"decimals": 1, "unit": "um", "sparkline": True}),
            card("tool", "plot", "4x2", "Tool error (um)", signals=["Mon/ex", "Mon/ey", "Mon/ez"]),
            card("axes", "plot", "2x2", "X reference and the two axes (m)", signals=["Ref/q", "X1/qout", "X2/qout"]),
            card("forces", "plot", "2x2", "Motor forces (N)", signals=["X1Servo/F", "X2Servo/F"]),
        ],
    }


# --- the static model -------------------------------------------------------------------
# the beam rotated by -90 degrees about y: its x axis points up, so gravity pulls along -x
Q_STATIC = [math.cos(-math.pi / 4), 0.0, math.sin(-math.pi / 4), 0.0]
K_CLAMP_R, K_CLAMP_T = 1.0e9, 1.0e11


def static_model() -> dict:
    d = Diagram()
    d.add("Beam", "spatial/ModalBody3D", 600, 300,
          {"zeta": "0.3", "g0": "9.81", "ms": fmt(MS), "s0": fmt(RAIL_L / 2)}, {"file": MODAL_FILE, "stiffening": 0})
    for port, x in (("A", 300), ("B", 900)):
        d.add(f"Clamp{port}", "multibond/CSpatial", x, 200,
              {k: fmt(K_CLAMP_R if k.startswith("kr") else K_CLAMP_T) for k in ("krx", "kry", "krz", "kx", "ky", "kz")})
        d.add(f"Clamp{port}Damping", "multibond/RSpatial", x, 400,
              {k: fmt(2 * 0.7 * math.sqrt((K_CLAMP_R * 0.01) if k.startswith("br") else (K_CLAMP_T * M_BEAM)))
               for k in ("brx", "bry", "brz", "bx", "by", "bz")})
        d.bond("Beam", port, f"Clamp{port}", "p")
        d.bond("Beam", port, f"Clamp{port}Damping", "p")
    d.add("Origin", "spatial/LocalPose3D", 300, 600, {**quat(Q_STATIC), "z": "0.0"})
    d.signal("Origin", "g", "Beam", "gA")
    y_carriage(d, 1000, 300, False)
    for n in d.nodes:
        if n["id"] == "YCar":
            n["params"]["g0"] = "g_y"
    # hold the slide: a stiff spring and damper from the Y motor's place on S to ground
    d.nodes = [n for n in d.nodes if n["id"] not in ("YMotor", "YStator", "YRef")]
    d.conns = [c for c in d.conns if c["from"]["node"] not in ("YMotor", "YRef") and c["to"]["node"] not in ("YMotor", "YStator")]
    d.add("SlideGround", "translation/Fixed", 700, 0)
    d.add("SlideSpring", "translation/Spring", 820, 0, {"k": "1.0e5"})
    d.add("SlideDamper", "translation/Damper", 820, 100, {"d": fmt(damping(1.0e5, M_YC, 0.7))})
    d.wire("SlideGround", "a", "SlideSpring", "a")
    d.wire("SlideGround", "a", "SlideDamper", "a")
    d.bond("SlideSpring", "b", "Beam", "S")
    d.bond("SlideDamper", "b", "Beam", "S")
    bindings = [pose("beam", "Beam/pose"), pose("ycar", "PYCar/g"), pose("tool", "PTool/g"), mode_shapes()]
    plots = [
        {"id": "p1", "title": "Rail frame under the carriage, world z (m): the beam's x deflection + 0.03",
         "signals": ["Beam/poseE[7]"]},
        {"id": "p2", "title": "Beam von Mises stress (Pa): hotspots and peak",
         "signals": ["Beam/sigma_vm[1]", "Beam/sigma_vm[2]", "Beam/sigma_vm[3]", "Beam/sigma_max"]},
        {"id": "p3", "title": "Modal coordinates (m)", "signals": [f"Beam/eta[{i}]" for i in range(1, NM + 1)]},
    ]
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": STATIC,
        "parameters": [glob("g_y", 9.81, "m/s^2", "Gravity on the Y carriage (0: the beam's own weight only)")],
        "diagram": {"nodes": d.nodes, "connections": d.conns, "subsystemPorts": [], "annotations": []},
        "settings": settings(0.5, 501),
        "plots": plots,
        "scene": {"file": f"scenes/{STATIC}.sdf", "exaggeration": 1000},
        "bindings": bindings,
    }


# --- beam theory --------------------------------------------------------------------------
def cantilever_hz(EI: float, kGA: float, n: int = 2) -> list[float]:
    """The first bending frequencies of the beam clamped at the end of interface A, free at the
    far end with the 10 mm end cap as a tip mass: Euler-Bernoulli with a tip mass (the
    characteristic equation), then a Timoshenko shear correction (1/f^2 = 1/f_b^2 + 1/f_s^2,
    f_s the shear-beam frequency of the same mode)."""
    L, m = L_CANT, MPL * L_CANT
    r = M_CAP / m
    f = lambda b: 1 + math.cos(b) * math.cosh(b) + r * b * (math.cos(b) * math.sinh(b) - math.sin(b) * math.cosh(b))
    roots, b = [], 0.5
    while len(roots) < n:
        if f(b) * f(b + 0.01) < 0:
            roots.append(brentq(f, b, b + 0.01))
        b += 0.01
    out = []
    for k, beta in enumerate(roots):
        fb = beta**2 / (2 * math.pi) * math.sqrt(EI / (MPL * L**4))
        fs = (2 * k + 1) / (4 * L) * math.sqrt(kGA / MPL)
        out.append(1 / math.sqrt(1 / fb**2 + 1 / fs**2))
    return out


def hand_static(carriage: bool = True) -> dict:
    """The beam clamped at both ends of its elastic span (1.24 m), 1 g along x: its own weight
    and the Y carriage at mid-span. Deflection with shear (Timoshenko), the bending stress at
    the hotspots with the torsion shear of the carriage's offset weight."""
    g = 9.81
    L, EI, kGA = L_SPAN, E_AL * I_Z, G_AL * AS_X
    P, w = (M_YC * g if carriage else 0.0), MPL * g
    defl = P * L**3 / (192 * EI) + w * L**4 / (384 * EI) + P * L / (4 * kGA) + w * L**2 / (8 * kGA)
    out = {"P": P, "w": w, "defl": defl, "EI": EI}
    # the hotspots: x from the clamp along the span, the fibre distance from the centroid, the
    # wall thickness (torsion shear q / t of the carriage's offset weight, half to each end)
    T = P * CY
    q = T / 2 / (2 * A_M)
    for k, p in enumerate(STRESS["points"][:3]):
        pos = SPEC["stress"]["hotspots"][k]["position"]
        x = pos[1] - A_END
        M = P * (4 * min(x, L - x) - L) / 8 + w * (6 * L * x - L**2 - 6 * x**2) / 12
        c = pos[0] - XC
        t = T_FRONT if pos[0] > 0 else T_BACK
        sig = abs(M * c / I_Z)
        tau = q / t
        out[p["name"]] = {"x": x, "M": M, "sigma": sig, "tau": tau, "vm": math.sqrt(sig**2 + 3 * tau**2)}
    return out


HAND = hand_static()
HAND_W = hand_static(carriage=False)


def scene_text(name: str, static: bool) -> str:
    beam = f"""
    <link name="beam">
      <pose>0 0 {ZB if not static else 0.0} 0 {0 if not static else -math.pi / 2} 0</pose>
      <visual name="beam_mesh">
        <geometry><mesh><uri>meshes/beam.glb</uri></mesh></geometry>
      </visual>
    </link>"""
    ycar = f"""
    <link name="ycar">
      <pose>{RAIL_X0 + CX} {RAIL_Y0 + RAIL_L / 2} {ZB - CY} {-math.pi / 2} 0 0</pose>
      <visual name="ycar_body">
        <geometry><box><size>{YC_BOX[0]} {YC_BOX[1]} {YC_BOX[2]}</size></box></geometry>
        <material><diffuse>0.25 0.5 0.85 1</diffuse></material>
      </visual>
    </link>
    <link name="tool">
      <pose>{TOOL0[0]} {RAIL_Y0 + RAIL_L / 2} {TOOL0[2]} {-math.pi / 2} 0 0</pose>
      <visual name="tool_tip">
        <geometry><sphere><radius>0.012</radius></sphere></geometry>
        <material><diffuse>0.95 0.3 0.1 1</diffuse></material>
      </visual>
    </link>"""
    machine = "" if static else f"""
    <link name="frame">
      <pose>0 0 0 0 0 0</pose>
      <visual name="x1_rail">
        <pose>0.3 0 {ZX - 0.06} 0 0 0</pose>
        <geometry><box><size>1.4 0.06 0.04</size></box></geometry>
        <material><diffuse>0.3 0.3 0.33 1</diffuse></material>
      </visual>
      <visual name="x2_rail">
        <pose>0.3 {L_AB} {ZX - 0.06} 0 0 0</pose>
        <geometry><box><size>1.4 0.06 0.04</size></box></geometry>
        <material><diffuse>0.3 0.3 0.33 1</diffuse></material>
      </visual>
      <visual name="table">
        <pose>0.3 {L_AB / 2} 0.22 0 0 0</pose>
        <geometry><box><size>1.4 1.2 0.04</size></box></geometry>
        <material><diffuse>0.55 0.57 0.6 1</diffuse></material>
      </visual>
    </link>
    <link name="x1car">
      <pose>0 0 {ZX} 0 0 0</pose>
      <visual name="x1car_body">
        <geometry><box><size>0.2 0.16 0.08</size></box></geometry>
        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>
      </visual>
      <visual name="x1_bracket">
        <pose>0 0 0.05 0 0 0</pose>
        <geometry><box><size>0.08 0.1 0.03</size></box></geometry>
        <material><diffuse>0.9 0.55 0.1 1</diffuse></material>
      </visual>
    </link>
    <link name="x2car">
      <pose>0 {L_AB} {ZX} 0 0 0</pose>
      <visual name="x2car_body">
        <geometry><box><size>0.2 0.16 0.08</size></box></geometry>
        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>
      </visual>
      <visual name="x2_pivot">
        <pose>0 0 0.05 0 0 0</pose>
        <geometry><cylinder><radius>0.03</radius><length>0.03</length></cylinder></geometry>
        <material><diffuse>0.9 0.55 0.1 1</diffuse></material>
      </visual>
    </link>"""
    what = ("the beam clamped at both ends under 1 g along its x axis, the view rotated so that x points up"
            if static else "an H-gantry: two X axes, the FEM crossbeam, the Y carriage and its tool")
    return f"""<?xml version="1.0"?>
<!--
  {name}: {what}.

  Z-up, metres. The beam link follows Beam/pose, the world pose of its reference frame
  (interface A, on the beam axis at the A end bracket). Its visual `beam_mesh` is the GLB the
  reduction wrote (meshes/beam.glb, in that frame, one morph target per mode), deformed by a
  mode-shapes binding with Beam/eta[1..{NM}] and coloured by von Mises stress. The Y carriage
  follows PYCar/g (the deformed rail frame E composed with the guide and the offset to its
  centre of mass), the tool PTool/g.
-->
<sdf version="1.9">
  <model name="{name.replace('-', '_')}">{machine}{beam}{ycar}
  </model>
</sdf>
"""


T_HOLD = T2 - 0.01                                  # just before the move back


def scenario_checks(name: str, r: dict, label: str, off_centre: bool = False) -> list[dict]:
    """The checks of one run of the gantry against the scipy reference (design/reference.py,
    scenario `name`): the moves arrive, the tool's residual vibration, its peak error, the
    racking, the motor forces, the settling time and the beam's stress.

    off_centre: the Y carriage near the A end. The reference holds the carriage rigidly at the
    rail point; BGSim's compliant guide and drive let it rock on the beam's local twist (the
    167 Hz mode), which matters more there: the peak tool error is checked to 8 % (6 %), the
    hotspot stresses next to the carriage to 20 % (15 %), and the settling time, with a
    residual of only five times the band, to 15 ms (12 ms) (README, "Shaping, the notch and racking")."""
    src = f"design/reference.py, scenario {name}"
    rt_peak, rt_vm, abs_settle = (0.08, 0.20, 0.015) if off_centre else (0.06, 0.15, 0.012)
    out = [
        {"kind": "final_value", "signal": "X1/qout", "t": T_HOLD, "value": DX, "abs": 2e-6,
         "note": f"{label}: X1 reaches the 0.5 m target (the integral action leaves no error)"},
        {"kind": "final_value", "signal": "X2/qout", "t": T_HOLD, "value": DX, "abs": 2e-6, "note": "X2 too"},
        {"kind": "final_value", "signal": "X1/qout", "t": T_END, "value": 0.0, "abs": 2e-6, "note": "and both are back at 0"},
        {"kind": "max_abs", "signal": "Mon/ex", "from_t": 0.0, "to_t": T_HOLD, "value": r["peak"] * 1e6, "rtol": rt_peak,
         "note": f"the largest tool error along x during the move out (um), against {src}"},
        {"kind": "max_abs", "signal": "Mon/rack", "from_t": 0.0, "to_t": T_HOLD, "value": r["rack_peak"] * 1e6, "rtol": 0.12,
         "note": f"racking: the largest x1 - x2 (um), against {src}"},
        {"kind": "max_abs", "signal": "X1Servo/F", "from_t": 0.0, "to_t": T_HOLD, "value": r["F1_peak"], "rtol": 0.06,
         "note": f"the X1 motor's peak force (N): the welded end carries more of the beam (clamped-pinned), against {src}"},
        {"kind": "max_abs", "signal": "X2Servo/F", "from_t": 0.0, "to_t": T_HOLD, "value": r["F2_peak"], "rtol": 0.06,
         "note": f"the X2 motor's peak force (N), against {src}"},
        {"kind": "max_abs_le", "signal": "Mon/util", "value": 100.0,
         "note": f"the beam's peak von Mises stays below the allowable ({SIGMA_ALLOW / 1e6:.0f} MPa, fatigue of EN AW-6063 T6)"},
    ]
    if r["residual"] > 2 * BAND:
        out.append({"kind": "max_abs", "signal": "Mon/ex", "from_t": r["t_ref"], "to_t": T_HOLD, "value": r["residual"] * 1e6,
                    "rtol": 0.12, "note": f"the residual vibration after the move out (um), against {src}"})
        # The settling time is the last crossing of the band by a decaying ~47 Hz oscillation: a 5 %
        # larger residual moves it by up to a half period (10.7 ms).
        out.append({"kind": "final_value", "signal": "Mon/settle", "t": T_HOLD, "value": r["settle"], "abs": abs_settle,
                    "note": f"the settling time into +-{BAND * 1e6:.0f} um after the move out (s), against {src} "
                            "(a band crossing: up to half a period of the 47 Hz mode apart)"})
    else:
        # The rigid-joint reference leaves 6 um; the guides' rotational compliance lowers the beam's
        # lightly damped rocking mode from 192 to 167 Hz, which the shaper (tuned at f_s) leaves in:
        # bounds, not equalities (README, "Shaping").
        out.append({"kind": "max_abs_le", "signal": "Mon/ex", "from_t": r["t_ref"], "to_t": T_HOLD, "value": 2.5 * BAND * 1e6,
                    "note": f"the shaped move's residual vibration stays below {2.5 * BAND * 1e6:.0f} um (a fifth of the plain "
                            f"move's; the rigid-joint reference gives {r['residual'] * 1e6:.1f} um, {src})"})
        out.append({"kind": "final_value", "signal": "Mon/settle", "t": T_HOLD, "value": 0.0, "abs": 0.015,
                    "note": "the settling time after the shaped move is at most 15 ms (the plain move's is about 35 ms)"})
    for k, p in enumerate(STRESS["points"][:3]):
        out.append({"kind": "max_abs", "signal": f"Beam/sigma_vm[{k + 1}]", "from_t": 0.0, "to_t": T_HOLD,
                    "value": r["vm_peak"][k], "rtol": rt_vm,
                    "note": f"peak von Mises at the hotspot '{p['name']}' (Pa): the modal superposition of the stress table in {src}"})
    out.append({"kind": "max_abs", "signal": "Beam/sigma_max", "from_t": 0.0, "to_t": T_HOLD, "value": r["sigma_max_peak"],
                "rtol": 0.15, "note": f"peak von Mises over all stress points (Pa), against {src}"})
    return out


def expected(f_s: float, sim: dict) -> dict:
    common = [{"kind": "no_diagnostics", "codes": ["E101", "E102", "E108", "W201", "W202"]}, {"kind": "scene_bindings"}]
    note_defl = (f"beam theory, clamped-clamped over the elastic span {L_SPAN} m with shear: the carriage "
                 f"P = {HAND['P']:.2f} N at mid-span and the beam's weight w = {HAND['w']:.2f} N/m, "
                 f"EI = {HAND['EI']:.4g} N*m^2: {HAND['defl'] * 1e6:.2f} um")
    checks_static = list(common) + [
        {"kind": "final_value", "signal": "Beam/poseE[7]", "t": 0.5, "value": 0.03 - HAND["defl"], "abs": 0.07 * HAND["defl"],
         "note": "the rail under the carriage moves by the beam's deflection (x, up in this view): " + note_defl},
    ]
    for k, p in enumerate(STRESS["points"][:2]):
        h = HAND[p["name"]]
        checks_static.append(
            {"kind": "final_value", "signal": f"Beam/sigma_vm[{k + 1}]", "t": 0.5, "value": h["vm"], "rtol": 0.05,
             "note": f"{p['name']}: M = {h['M']:.3f} N*m at {h['x'] * 1e3:.0f} mm from the clamp, sigma = M c / I = "
                     f"{h['sigma'] / 1e3:.1f} kPa, torsion shear {h['tau'] / 1e3:.1f} kPa, von Mises {h['vm'] / 1e3:.1f} kPa"})
    h = HAND[STRESS["points"][2]["name"]]
    checks_static.append(
        {"kind": "max_abs_le", "signal": "Beam/sigma_vm[3]", "from_t": 0.4, "to_t": 0.5, "value": h["vm"],
         "note": f"{STRESS['points'][2]['name']}, under the carriage: below the beam-theory {h['vm'] / 1e3:.1f} kPa (the "
                 "guide blocks spread the load over 100 mm and the box's walls carry it with shear lag); the "
                 "self-weight case checks this hotspot against beam theory"})
    checks_weight = list(common)
    note_w = (f"the beam's own weight alone (the Y carriage weightless), w = {HAND_W['w']:.2f} N/m: "
              f"w L^4 / (384 E I) + w L^2 / (8 k G A) = {HAND_W['defl'] * 1e6:.2f} um")
    checks_weight.append({"kind": "final_value", "signal": "Beam/poseE[7]", "t": 0.5, "value": 0.03 - HAND_W["defl"],
                          "abs": 0.06 * HAND_W["defl"], "note": note_w})
    for k, p in enumerate(STRESS["points"][:3]):
        hw = HAND_W[p["name"]]
        checks_weight.append(
            {"kind": "final_value", "signal": f"Beam/sigma_vm[{k + 1}]", "t": 0.5, "value": hw["vm"], "rtol": 0.06,
             "note": f"{p['name']}: M = {hw['M']:.3f} N*m, sigma = M c / I = {hw['sigma'] / 1e3:.1f} kPa"})
    sc = sim.get("scenarios", {})
    models: dict = {NAME: {"checks": list(common) + (scenario_checks("plain", sc["plain"], "plain move") if "plain" in sc else [])}}
    for name, overrides, label in (("zvd", {"global:shaping": 2.0}, "ZVD-shaped move"),
                                   ("notch", {"global:notch": 0.0}, f"full notch at {F_NOTCH:.0f} Hz"),
                                   ("kf2_0.9", {"global:kf2": 0.9}, "X2 motor 10 % weak"),
                                   ("y_c_0.15", {"global:y_c": 0.15}, "Y carriage 0.15 m along the rail")):
        if name in sc:
            models[f"{NAME}-{name.replace('_', '-')}"] = {"model": NAME, "overrides": overrides,
                                                         "checks": scenario_checks(name, sc[name], label, name.startswith("y_c"))}
    models[STATIC] = {"checks": checks_static}
    models[f"{STATIC}-self-weight"] = {"model": STATIC, "overrides": {"global:g_y": 0.0}, "checks": checks_weight}
    return {
        "project": NAME,
        "description": "An H-gantry with a FEM crossbeam (ModalBody3D with a rail): two linear-motor X axes with servo drives, a Y carriage on the moving rail interface, point-to-point moves plain and input-shaped, racking, and the beam's stress, against a scipy modal model; plus the beam's static deflection and stress against beam theory.",
        "models": models,
    }


def write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> None:
    sim_path = HERE / "reference.json"
    sim = json.loads(sim_path.read_text(encoding="utf-8")) if sim_path.exists() else {}
    f_s, zeta_s = float(sim.get("f_s", 30.0)), float(sim.get("zeta_s", 0.02))
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    (ROOT / "scenes").mkdir(parents=True, exist_ok=True)
    for name, d, static in ((NAME, gantry(f_s, zeta_s), False), (STATIC, static_model(), True)):
        write(ROOT / "models" / f"{name}.bgmodel.json", json.dumps(d, indent=2, ensure_ascii=False) + "\n")
        write(ROOT / "scenes" / f"{name}.sdf", scene_text(name, static))
    write(ROOT / "expected.json", json.dumps(expected(f_s, sim), indent=2, ensure_ascii=False) + "\n")
    write(ROOT / "bgsim.project.json", json.dumps(
        {"format": "bgsim.project", "language": "0.1.0", "name": NAME, "models": [NAME, STATIC],
         "libraryDir": "library", "scenesDir": "scenes"}, indent=2) + "\n")
    hz = cantilever_hz(E_AL * I_Z, G_AL * AS_X, 1) + cantilever_hz(E_AL * I_X, G_AL * AS_Z, 1)
    print(f"beam: nm {NM}, mass {M_BEAM:.3f} kg, section A {A_SEC * 1e6:.1f} mm^2, centroid x {XC * 1e3:.2f} mm, "
          f"I_z {I_Z:.4e}, I_x {I_X:.4e}, J_t {J_T:.4e} m^4")
    print(f"cantilever (clamped at A) beam theory: x-bending {hz[0]:.2f} Hz, z-bending {hz[1]:.2f} Hz; "
          f"FE {MODAL['validation']['frequencies']['clamped']['full_hz'][:2]}")
    print(f"static hand: deflection {HAND['defl'] * 1e6:.3f} um; " + ", ".join(
        f"{p['name']} {HAND[p['name']]['vm'] / 1e3:.1f} kPa" for p in STRESS["points"][:3]))
    print(f"X drive mass M_x {M_X:.3f} kg; moving X mass {2 * M_XC + M_BEAM + M_YC + MS:.2f} kg")


if __name__ == "__main__":
    main()
