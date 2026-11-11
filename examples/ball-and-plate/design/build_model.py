# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Writes the models, the scene and expected.json of the `ball-and-plate` example.

    uv run examples/ball-and-plate/design/design.py        # first: the control design (design.json)
    uv run examples/ball-and-plate/design/build_model.py   # models/*.bgmodel.json, scenes, expected.json

The plant is the same bond graph in every model:

* the plate is a `RigidBody3D` on a `Universal3D` gimbal (first axis world y, second the plate x
  axis), mounted on the world through `FixedTransform3DNeutral`; its pose is composed from the
  gimbal pose (`LocalPose3D`, `ComposePose3D`);
* the ball is a free `RigidBody3D` whose pose a `PoseIntegrator3D` integrates;
* the two bodies touch through the stdlib `RollingSphere` contact (Hunt-Crossley normal force,
  regularised Coulomb friction = rolling without slip, rolling resistance);
* each gimbal axis is driven by a servo: a DC motor and gearbox bond graph (`MSe` voltage, `R`
  armature, `I` inductance, `GY` motor constant, `TF` gearbox, `I`/`R` output inertia and
  friction), the crank and push rod as an `MTF` whose modulus is the crank kinematics
  (`library/CrankLinkage.jl`), and the push-rod compliance as a `C`/`R` pair on a 0-junction
  between the rod and the gimbal drive;
* the free model replaces the servos by stiff `C`/`R` locks at a fixed tilt.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
DESIGN = json.loads((Path(__file__).resolve().parent / "design.json").read_text(encoding="utf-8")) \
    if (Path(__file__).resolve().parent / "design.json").exists() else {}

SOLVER = "Rodas5P"


def num(x) -> str:
    return repr(float(x))


def vec(v) -> str:
    return "[" + ", ".join(num(x) for x in v) + "]"


def Rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def Ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def quat(R):
    """(w, x, y, z) of a rotation matrix, w >= 0."""
    t = np.trace(R)
    if t > 0:
        s = 0.5 / np.sqrt(t + 1.0)
        q = np.array([0.25 / s, (R[2, 1] - R[1, 2]) * s, (R[0, 2] - R[2, 0]) * s, (R[1, 0] - R[0, 1]) * s])
    else:
        i = int(np.argmax(np.diag(R)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = 2.0 * np.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k])
        q = np.zeros(4)
        q[0] = (R[k, j] - R[j, k]) / s
        q[1 + i] = 0.25 * s
        q[1 + j] = (R[j, i] + R[i, j]) / s
        q[1 + k] = (R[k, i] + R[i, k]) / s
    q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def pose_params(R, p):
    q = quat(np.asarray(R, dtype=float))
    return {"qw": num(q[0]), "qx": num(q[1]), "qy": num(q[2]), "qz": num(q[3]),
            "x": num(p[0]), "y": num(p[1]), "z": num(p[2])}


# Gimbal frame in the world: joint z = world y (first axis), joint x = world x (second axis), so
# the plate rotation is R = Ry(q1) Rx(q2) for the joint rotation Rz(q1) Rx(q2).
C_J = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
P_J = np.array([0.0, 0.0, rig.H_PIVOT])

# ball inertia through the model-level global k_ball (J = k_ball m r^2; a run override switches
# the solid steel ball to a hollow one)
_MR2 = num(rig.M_BALL * rig.R_BALL**2)
BALL_J = f"[k_ball * {_MR2}, k_ball * {_MR2}, k_ball * {_MR2}]"


def plate_rotation(q1, q2):
    return Ry(q1) @ Rx(q2)


# ------------------------------------------------------------------ diagram builder
class Diagram:
    def __init__(self):
        self.nodes, self.conns = [], []
        self._ids = {}
        self._n = {"b": 0, "s": 0}

    def node(self, name, ref, x, y, params=None, starts=None, constants=None):
        nid = f"n{len(self.nodes) + 1:03d}"
        self._ids[name] = nid
        blk = {"junction": ref} if ref in ("0", "1") else {"ref": ref}
        self.nodes.append({
            "id": nid, "name": name, "block": blk, "position": {"x": int(x), "y": int(y)},
            "rotation": 0, "flipX": False,
            "params": {k: (v if isinstance(v, str) else num(v)) for k, v in (params or {}).items()},
            "constants": {k: (v if isinstance(v, str) else str(v) if isinstance(v, int) else num(v))
                          for k, v in (constants or {}).items()},
            "starts": {k: (v if isinstance(v, str) else num(v)) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })

    def _c(self, kind, a, pa, b, pb):
        self._n[kind[0]] += 1
        fr = {"node": self._ids[a]} if pa is None else {"node": self._ids[a], "port": pa}
        to = {"node": self._ids[b]} if pb is None else {"node": self._ids[b], "port": pb}
        self.conns.append({"id": f"{kind[0]}{self._n[kind[0]]:03d}", "kind": kind, "from": fr, "to": to,
                           "label": None})

    def bond(self, a, pa, b, pb=None):
        self._c("bond", a, pa, b, pb)

    def sig(self, a, pa, b, pb):
        self._c("signal", a, pa, b, pb)


def settings(t_end, points, reltol=1e-7, abstol=1e-9, event_limit=100000):
    return {"t_start": 0.0, "t_end": float(t_end), "solver": SOLVER, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": event_limit}



# ------------------------------------------------------------------ plant
def ball_start(q1, q2, x0, y0):
    """World pose of the ball centre resting on the plate at plate coordinates (x0, y0)."""
    R = plate_rotation(q1, q2)
    c = P_J + R @ np.array([x0, y0, rig.H_BALL - rig.DELTA0])
    return R, c


def gimbal_sag(q1, q2):
    """Static pivot deflection of the gimbal (child frame) under the weight of plate and ball."""
    Rc = C_J @ Rz(q1) @ Rx(q2)
    F = (rig.M_PLATE + rig.M_BALL) * rig.G0
    return Rc.T @ np.array([0.0, 0.0, -F / 1.0e6])


def Rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def plate_and_ball(D: Diagram, q10: float, q20: float, x0: float, y0: float, *, crr=rig.CRR):
    """Gimbal, plate, ball and the rolling contact (node names are used by checks and docs)."""
    # gimbal on the world
    D.node("World", "stdlib:multibond/GroundSpatial", 80, 120)
    D.node("Mount", "stdlib:multibond/FixedTransform3DNeutral", 260, 120,
           params=pose_params(C_J.T, -C_J.T @ P_J))
    D.node("Gimbal", "stdlib:spatial/Universal3D", 440, 120,
           params={"q10": q10, "q20": q20, "br": 50.0, "bt": 300.0},
           starts={"dl": vec(gimbal_sag(q10, q20))})
    D.node("Link", "stdlib:multibond/FixedTransform3DNeutral", 620, 120, params=pose_params(C_J.T, [0, 0, 0]))
    D.node("Plate", "stdlib:spatial/RigidBody3D", 800, 120,
           params={"m": rig.M_PLATE, "J": vec([rig.J_PLATE_XY, rig.J_PLATE_XY, rig.J_PLATE_Z]), "g0": rig.G0})
    D.bond("World", "p", "Mount", "b")
    D.bond("Mount", "a", "Gimbal", "parent")
    D.bond("Gimbal", "child", "Link", "a")
    D.bond("Link", "b", "Plate", "p")
    # plate pose = mount (gimbal frame in the world) o gimbal pose o link
    D.node("GimbalFrame", "stdlib:spatial/LocalPose3D", 260, 300, params=pose_params(C_J, P_J))
    D.node("PoseG", "stdlib:multibond/ComposePose3D", 440, 300)
    D.node("LinkPose", "stdlib:spatial/LocalPose3D", 620, 400, params=pose_params(C_J.T, [0, 0, 0]))
    D.node("PosePlate", "stdlib:multibond/ComposePose3D", 800, 300)
    D.sig("GimbalFrame", "g", "PoseG", "gp")
    D.sig("Gimbal", "pose", "PoseG", "gl")
    D.sig("PoseG", "g", "PosePlate", "gp")
    D.sig("LinkPose", "g", "PosePlate", "gl")
    D.sig("PosePlate", "g", "Plate", "g")
    # ball
    _, c = ball_start(q10, q20, x0, y0)
    D.node("Ball", "stdlib:spatial/RigidBody3D", 1180, 120,
           params={"m": rig.M_BALL, "J": BALL_J, "g0": rig.G0},
           starts={"inertia/P": vec([0, 0, 0, 0, 0, 0])})
    D.node("PoseBall", "stdlib:multibond/PoseIntegrator3D", 1180, 300,
           starts={"qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "px": c[0], "py": c[1], "pz": c[2]})
    D.sig("Ball", "V", "PoseBall", "tw")
    D.sig("PoseBall", "g", "Ball", "g")
    # contact
    D.node("Contact", "stdlib:contact/RollingSphere", 990, 200,
           params={"r": rig.R_BALL, "oz": rig.Z_SURF, "nz": 1.0, "tx": 1.0, "w1": rig.W_FACE, "w2": rig.W_FACE,
                   "we": 1e-3, "k": rig.K_C, "xref": rig.XREF_C, "c": rig.C_C, "mu": rig.MU_C, "vs": rig.VS_C,
                   "crr": crr, "eps": 1e-7})
    D.bond("Plate", "p", "Contact", "a")
    D.bond("Ball", "p", "Contact", "b")
    D.sig("PosePlate", "g", "Contact", "ga")
    D.sig("PoseBall", "g", "Contact", "gb")


def weight_torque(q1, q2, x0, y0):
    """Torque of the ball's weight about the two gimbal axes at the start (N m)."""
    _, c = ball_start(q1, q2, x0, y0)
    r = c - P_J
    F = np.array([0, 0, -rig.M_BALL * rig.G0])
    tau = np.cross(r, F)
    return tau[1], (Ry(q1) @ np.array([1.0, 0, 0])) @ tau


K_LOCK, B_LOCK = 1.0e4, 10.0


def lock_preload(q10, x0):
    """Start value of the lock spring X that holds the ball's weight torque at the start tilt
    (the spring's q falls as q1 rises, so q0 = -tau / k)."""
    tx, _ = weight_torque(q10, 0.0, x0, 0.0)
    return -tx / K_LOCK


def locks(D: Diagram, q10, x0, *, shaker=None):
    """Stiff C/R locks on the two gimbal drives: the plate holds its start tilt (free model), or
    follows a prescribed rate on axis 1 (`shaker` = (amplitude rad, angular frequency rad/s): an
    MSf drives the far end of the lock spring at A W sin(W t), so the plate angle is
    q10 + A (1 - cos W t))."""
    for i, ax in ((1, "X"), (2, "Y")):
        x = 440 + 260 * (i - 1)
        if shaker and i == 1:
            A, W = shaker
            D.node("ShakerRate", "stdlib:sources/Sine", x - 260, -420, params={"amplitude": A * W, "frequency": W})
            # the MSf delivers A W sin(W t) into the 0-junction (a flow source at the tail of its
            # bond imposes +u on the junction), which passes it on to the gimbal drive and the lock
            D.node("Shaker", "stdlib:bondgraph/MSf", x - 120, -420)
            D.node("LockNode", "0", x, -300)
            D.sig("ShakerRate", "y", "Shaker", "u")
            D.bond("Shaker", "p", "LockNode")
            D.bond("LockNode", None, "Gimbal", f"drive{i}")
            D.node(f"Lock{ax}", "1", x, -160)
            D.bond("LockNode", None, f"Lock{ax}")
        else:
            D.node(f"Lock{ax}", "1", x, -160)
            D.bond("Gimbal", f"drive{i}", f"Lock{ax}")
        q0 = lock_preload(q10, x0) if (i == 1 and not shaker) else 0.0
        D.node(f"Spring{ax}", "stdlib:bondgraph/C", x - 60, -60, params={"c": 1.0 / K_LOCK}, starts={"q": q0})
        D.node(f"Damper{ax}", "stdlib:bondgraph/R", x + 60, -60, params={"r": B_LOCK})
        D.bond(f"Lock{ax}", None, f"Spring{ax}", "p")
        D.bond(f"Lock{ax}", None, f"Damper{ax}", "p")


def servo(D: Diagram, ax: str, i: int, y0: int, theta0=0.0):
    """One servo: SRV02 motor and gearbox, crank MTF and push-rod compliance on the gimbal drive i."""
    x = -1500
    D.node(f"Amp{ax}", "stdlib:bondgraph/MSe", x, y0)
    D.node(f"Elec{ax}", "1", x + 140, y0)
    D.node(f"Rm{ax}", "stdlib:bondgraph/R", x + 140, y0 - 110, params={"r": rig.R_M})
    D.node(f"Lm{ax}", "stdlib:bondgraph/I", x + 140, y0 + 110, params={"i": rig.L_M})
    D.node(f"Motor{ax}", "stdlib:bondgraph/GY", x + 280, y0, params={"r": rig.K_M})
    D.node(f"Rotor{ax}", "1", x + 420, y0)
    D.node(f"Gear{ax}", "stdlib:bondgraph/TF", x + 560, y0, params={"n": 1.0 / rig.K_G})
    D.node(f"Shaft{ax}", "1", x + 700, y0)
    D.node(f"Jeq{ax}", "stdlib:bondgraph/I", x + 700, y0 - 110, params={"i": rig.J_EQ})
    D.node(f"Beq{ax}", "stdlib:bondgraph/R", x + 640, y0 + 110, params={"r": rig.B_EQ})
    D.node(f"Theta{ax}", "stdlib:converters/AngleSensor", x + 780, y0 + 110, starts={"phi": theta0})
    D.node(f"Crank{ax}", "stdlib:bondgraph/MTF", x + 860, y0)
    D.node(f"Kin{ax}", "project:CrankLinkage", x + 860, y0 + 220,
           params={"rho": rig.RHO_LINK, "sgn": 1.0 if i == 1 else -1.0})
    D.node(f"Rod{ax}", "0", x + 1000, y0)
    D.node(f"RodSpring{ax}", "1", x + 1000, y0 - 130)
    D.node(f"Krod{ax}", "stdlib:bondgraph/C", x + 940, y0 - 240, params={"c": 1.0 / rig.K_LINK})
    D.node(f"Brod{ax}", "stdlib:bondgraph/R", x + 1060, y0 - 240, params={"r": rig.B_LINK})
    D.bond(f"Amp{ax}", "p", f"Elec{ax}")
    D.bond(f"Elec{ax}", None, f"Rm{ax}", "p")
    D.bond(f"Elec{ax}", None, f"Lm{ax}", "p")
    D.bond(f"Elec{ax}", None, f"Motor{ax}", "p1")
    D.bond(f"Motor{ax}", "p2", f"Rotor{ax}")
    D.bond(f"Rotor{ax}", None, f"Gear{ax}", "p1")
    D.bond(f"Gear{ax}", "p2", f"Shaft{ax}")
    D.bond(f"Shaft{ax}", None, f"Jeq{ax}", "p")
    D.bond(f"Shaft{ax}", None, f"Beq{ax}", "p")
    D.bond(f"Shaft{ax}", None, f"Theta{ax}", "a")
    D.bond(f"Shaft{ax}", None, f"Crank{ax}", "p1")
    D.bond(f"Crank{ax}", "p2", f"Rod{ax}")
    D.bond(f"Rod{ax}", None, "Gimbal", f"drive{i}")
    D.bond(f"Rod{ax}", None, f"RodSpring{ax}")
    D.bond(f"RodSpring{ax}", None, f"Krod{ax}", "p")
    D.bond(f"RodSpring{ax}", None, f"Brod{ax}", "p")
    D.sig(f"Theta{ax}", "y", f"Kin{ax}", "theta")
    D.sig(f"Kin{ax}", "m", f"Crank{ax}", "u")
    # firmware: encoder, position loop, drive dead band
    D.node(f"Enc{ax}", "stdlib:motion/Encoder", x - 300, y0 + 330, params={"cpr": str(rig.ENC_CPR)},
           constants={"sample_period": rig.SERVO_T})
    D.node(f"Servo{ax}", "project:ServoPD", x - 300, y0 + 110,
           params={"Kp": DESIGN["servo"]["Kp"], "Kd": DESIGN["servo"]["Kd"], "tau_f": DESIGN["servo"]["tau_f"],
                   "V_max": rig.V_MAX, "th_max": rig.THETA_MAX})
    D.node(f"Dead{ax}", "stdlib:continuous/DeadZone", x - 150, y0, params={"lower": -rig.V_DEAD, "upper": rig.V_DEAD})
    D.sig(f"Theta{ax}", "y", f"Enc{ax}", "u")
    D.sig(f"Enc{ax}", "y", f"Servo{ax}", "theta")
    D.sig(f"Servo{ax}", "V", f"Dead{ax}", "u")
    D.sig(f"Dead{ax}", "y", f"Amp{ax}", "u")


def camera(D: Diagram, ax: str, index: int, y0: int, seed: int):
    """Overhead camera, one axis: the ball centre's world position plus seeded centroid noise,
    sampled and rounded to the pixel at 30 frames/s, one frame of processing latency."""
    x = 1500
    D.node(f"Pos{ax}", "stdlib:continuous/Select", x, y0, constants={"N": 7, "index": index})
    D.node(f"Noise{ax}", "stdlib:sources/Noise", x, y0 + 100,
           params={"std": rig.CAM_NOISE, "seed": str(seed)}, constants={"sample_time": rig.CAM_T})
    D.node(f"Mux{ax}", "stdlib:continuous/Mux2", x + 150, y0 + 50)
    D.node(f"Sum{ax}", "stdlib:continuous/Sum", x + 280, y0 + 50, params={"signs": "[1.0, 1.0]"},
           constants={"N": 2})
    D.node(f"Pixel{ax}", "stdlib:discrete/Quantizer", x + 410, y0 + 50, params={"resolution": rig.CAM_PIX},
           constants={"sample_period": rig.CAM_T})
    D.node(f"Frame{ax}", "stdlib:discrete/IntegerDelay", x + 540, y0 + 50,
           constants={"N": rig.CAM_DELAY, "sample_period": rig.CAM_T})
    D.sig("PoseBall", "g", f"Pos{ax}", "u")
    D.sig(f"Pos{ax}", "y", f"Mux{ax}", "u1")
    D.sig(f"Noise{ax}", "y", f"Mux{ax}", "u2")
    D.sig(f"Mux{ax}", "y", f"Sum{ax}", "u")
    D.sig(f"Sum{ax}", "y", f"Pixel{ax}", "u")
    D.sig(f"Pixel{ax}", "y", f"Frame{ax}", "u")


def task_and_push(D: Diagram, task: int, push: bool):
    D.node("Task", "project:PlateTask", 1500, 900, params={"task": str(task)})
    D.node("Push", "project:BallPush", 1180, 560,
           params={"t_push": PUSH_T if push else 1.0e6, "dur": PUSH_DUR, "Fy": PUSH_F})
    D.node("PushForce", "stdlib:multibond/ExternalWrenchSpatial", 1180, 440)
    D.node("Zero", "stdlib:sources/Constant", 1000, 560, params={"value": 0.0})
    D.sig("PoseBall", "g", "Push", "gb")
    for k in ("tx", "ty", "tz"):
        D.sig("Zero", "y", "PushForce", k)
    for k in ("fx", "fy", "fz"):
        D.sig("Push", k, "PushForce", k)
    D.bond("PushForce", "p", "Ball", "p")


def viz(D: Diagram):
    D.node("Viz", "project:RigViz", 1000, 760,
           params={"L": rig.L_ROD_X, "r": rig.R_ARM, "z_s": rig.H_PIVOT - rig.L_ROD, "tp": rig.T_PLATE})
    D.sig("PosePlate", "g", "Viz", "gp")
    D.sig("ThetaX", "y", "Viz", "thx")
    D.sig("ThetaY", "y", "Viz", "thy")
    D.sig("Task", "xd", "Viz", "xd")
    D.sig("Task", "yd", "Viz", "yd")


def lqg_params():
    L = DESIGN["lqr"]
    kal = DESIGN["kalman"]

    def mat(M):
        return "[" + "; ".join(" ".join(num(v) for v in row) for row in M) + "]"

    return {"K": vec(L["K"]), "L": mat(L["L"]), "Ae": mat(kal["A"]), "Be": vec(kal["B"]),
            "kbb": rig.K_BB, "tau_s": 2 * DESIGN["servo"]["zeta"] / DESIGN["servo"]["wn"],
            "cbw": DESIGN["axis"]["cb"] / DESIGN["servo"]["wn"] ** 2, "th_max": rig.THETA_MAX}


def rig_model(name, comment, ctrl, task, t_end, points, push=True, dashboard=None):
    """The closed-loop rig: plant, servos, camera, the outer controller `ctrl` ('pid' or 'lqr')."""
    D = Diagram()
    plate_and_ball(D, 0.0, 0.0, 0.0, 0.0)
    servo(D, "X", 1, -500)
    servo(D, "Y", 2, -1100)
    camera(D, "X", 5, 600, 11)
    camera(D, "Y", 6, 760, 12)
    task_and_push(D, task, push)
    for ax, (r, rv, ra, rj) in (("X", ("xd", "vxd", "axd", "jxd")), ("Y", ("yd", "vyd", "ayd", "jyd"))):
        cx, cy = 2200, (600 if ax == "X" else 760)
        if ctrl == "pid":
            p = DESIGN["pid"]
            D.node(f"PID{ax}", "project:PlatePID", cx, cy,
                   params={"Kp": p["Kp"], "Ki": p["Ki"], "Kd": p["Kd"], "tau_d": p["tau_d"], "b": p["b"],
                           "e_int": p["e_int"], "th_max": rig.THETA_MAX})
            D.sig("Task", r, f"PID{ax}", "r")
            D.sig(f"Frame{ax}", "y", f"PID{ax}", "y")
            D.sig(f"PID{ax}", "th_ref", f"Servo{ax}", "ref")
        else:
            D.node(f"LQG{ax}", "project:PlateLQG", cx, cy, params=lqg_params())
            D.sig(f"Frame{ax}", "y", f"LQG{ax}", "y")
            D.sig(f"Enc{ax}", "y", f"LQG{ax}", "theta")
            for a, b in ((r, "xr"), (rv, "vr"), (ra, "ar"), (rj, "jr")):
                D.sig("Task", a, f"LQG{ax}", b)
            D.sig(f"LQG{ax}", "th_ref", f"Servo{ax}", "ref")
    viz(D)
    c = "PID" if ctrl == "pid" else "LQG"
    plots = [
        {"id": "xy", "title": "Ball on the plate (y against x) and the reference", "signals": ["PoseBall/g[6]", "Task/yd"],
         "x": "PoseBall/g[5]", "equalAspect": True},
        {"id": "pos", "title": "Ball position and reference", "signals": ["PoseBall/g[5]", "Task/xd", "PoseBall/g[6]", "Task/yd"]},
        {"id": "camera", "title": "Camera reading (30 frames/s, one frame late) and the true x",
         "signals": ["FrameX/y", "PoseBall/g[5]"]},
        {"id": "plate", "title": "Plate angles (gimbal)", "signals": ["Gimbal/q1out", "Gimbal/q2out"]},
        {"id": "servo", "title": "Servo angles and set-points", "signals": ["ThetaX/y", "ServoX/ref", "ThetaY/y", "ServoY/ref"]},
        {"id": "volts", "title": "Servo voltages", "signals": ["ServoX/V", "ServoY/V"]},
        {"id": "slip", "title": "Contact: slip speed (no-slip residual) and normal force", "signals": ["Contact/slip"]},
    ]
    if ctrl == "lqr":
        plots.insert(3, {"id": "estimate", "title": "Kalman estimate of x (now) and the true x",
                         "signals": ["LQGX/xhat", "PoseBall/g[5]", "LQGX/vhat"]})
    extra = {"scene": {"file": "scenes/ball-and-plate.sdf"}, "bindings": bindings()}
    if dashboard:
        extra["dashboard"] = dashboard
    return model_doc(name, comment, D, t_end, points, plots, extra=extra)


def bindings():
    return [
        {"target": "link:plate", "property": "pose", "signal": [f"PosePlate/g[{i}]" for i in range(1, 8)]},
        {"target": "link:ball", "property": "pose",
         "signal": [f"PoseBall/g[{i}]" for i in range(1, 8)]},
        {"target": "joint:crank_x", "property": "position", "signal": "ThetaX/y"},
        {"target": "joint:crank_y", "property": "position", "signal": "ThetaY/y"},
        {"target": "link:rod_x", "property": "pose", "signal": [f"Viz/rodx[{i}]" for i in range(1, 8)]},
        {"target": "link:rod_y", "property": "pose", "signal": [f"Viz/rody[{i}]" for i in range(1, 8)]},
        {"target": "link:target", "property": "pose", "signal": [f"Viz/target[{i}]" for i in range(1, 8)]},
    ]


def free_bindings():
    return [
        {"target": "link:plate", "property": "pose", "signal": [f"PosePlate/g[{i}]" for i in range(1, 8)]},
        {"target": "link:ball", "property": "pose",
         "signal": [f"PoseBall/g[{i}]" for i in range(1, 8)]},
    ]


def model_doc(name, comment, D, t_end, points, plots, extra=None, **kw):
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": {"nodes": D.nodes, "connections": D.conns, "subsystemPorts": [], "annotations": []},
        "settings": settings(t_end, points, **kw),
        "plots": plots,
        "parameters": [{"name": "k_ball", "value": num(rig.J_FACTOR), "unit": "1",
                        "description": "Ball inertia J = k_ball m r^2: 0.4 solid sphere (the rig's steel ball), "
                                       "2/3 thin-walled hollow ball of the same mass and radius"}],
    }
    if extra:
        doc.update(extra)
    return doc


# ------------------------------------------------------------------ models
FREE = DESIGN.get("free", {"alpha_deg": 1.0, "x0": -0.15})
FREE_TILT = math.radians(FREE["alpha_deg"])
FREE_X0 = FREE["x0"]
SWING = DESIGN.get("swing", {"A_deg": 2.0, "f_hz": 2.0, "x0": 0.1, "t_end": 4.0})
PUSH_T, PUSH_DUR, PUSH_F = 15.0, 0.05, 0.6
T_STEPS = 20.0


def free_model():
    D = Diagram()
    plate_and_ball(D, FREE_TILT, 0.0, FREE_X0, 0.0, crr=0.0)
    locks(D, FREE_TILT, FREE_X0)
    D.node("Energy", "project:RigEnergy", 1180, 460,
           params={"mb": rig.M_BALL, "mp": rig.M_PLATE, "g0": rig.G0, "k_lock": K_LOCK, "q10": FREE_TILT, "q20": 0.0,
                   "dq1": lock_preload(FREE_TILT, FREE_X0)})
    for a, pa, b in (("Ball", "P", "Pb"), ("Ball", "V", "Vb"), ("PoseBall", "g", "gb"), ("Plate", "P", "Pp"),
                     ("Plate", "V", "Vp"), ("PosePlate", "g", "gp"), ("Contact", "Ec", "Ec"), ("Contact", "Pd", "Pd"),
                     ("Gimbal", "q1out", "q1"), ("Gimbal", "q2out", "q2")):
        D.sig(a, pa, "Energy", b)
    plots = [
        {"id": "x", "title": "Ball position on the plate (contact point coordinates)", "signals": ["Contact/u1", "Contact/u2"]},
        {"id": "spin", "title": "Spin of the ball relative to the plate (about the plate y axis)", "signals": ["Contact/wr2"]},
        {"id": "slip", "title": "Slip speed (no-slip residual)", "signals": ["Contact/slip"]},
        {"id": "energy", "title": "Energy: stored E and E + loss", "signals": ["Energy/E", "Energy/Ebal"]},
        {"id": "kinetic", "title": "Kinetic energy of the ball and its rotational part (2/7 of it)",
         "signals": ["Energy/Ek", "Energy/Ekrot"]},
    ]
    return model_doc("ball-and-plate-free",
                     "Open loop: the plate locked at a 1 degree tilt about y (stiff C/R locks on the gimbal drives), the "
                     "ball released at rest 0.15 m from the centre, no rolling resistance. Checked against "
                     "x'' = 5/7 g sin(alpha) (solid sphere), the roll time to the centre, zero slip and energy conservation.",
                     D, 2.0, 801, plots, reltol=1e-9, abstol=1e-11,
                     extra={"scene": {"file": "scenes/ball-and-plate.sdf"}, "bindings": free_bindings(),
                            "dashboard": free_dashboard()})


def swing_model():
    A, W = math.radians(SWING["A_deg"]), 2 * math.pi * SWING["f_hz"]
    D = Diagram()
    plate_and_ball(D, -A, 0.0, SWING["x0"], 0.0, crr=0.0)
    locks(D, -A, SWING["x0"], shaker=(A, W))
    # the linearised model x'' = 5/7 g sin(alpha) of the measured plate angle, next to the bond graph
    D.node("SinAlpha", "stdlib:continuous/MathFunction", 1500, 120, constants={"fn": 0})
    D.node("LinAccel", "stdlib:continuous/Gain", 1640, 120, params={"k": rig.K_ROLL * rig.G0})
    D.node("LinV", "stdlib:continuous/Integrator", 1780, 120)
    D.node("LinX", "stdlib:continuous/Integrator", 1920, 120, starts={"x": SWING["x0"]})
    D.sig("Gimbal", "q1out", "SinAlpha", "u")
    D.sig("SinAlpha", "y", "LinAccel", "u")
    D.sig("LinAccel", "y", "LinV", "u")
    D.sig("LinV", "y", "LinX", "u")
    # full minus linear (both see the same plate angle, so the lock spring's tiny droop cancels)
    D.node("Pair", "stdlib:continuous/Mux2", 1780, 260)
    D.node("Drift", "stdlib:continuous/Sum", 1920, 260, params={"signs": "[1.0, -1.0]"}, constants={"N": 2})
    D.sig("Contact", "u1", "Pair", "u1")
    D.sig("LinX", "y", "Pair", "u2")
    D.sig("Pair", "y", "Drift", "u")
    plots = [
        {"id": "x", "title": "Ball position: full 3D rolling vs the linearised x'' = 5/7 g sin(alpha)",
         "signals": ["Contact/u1", "LinX/y"]},
        {"id": "drift", "title": "Full minus linearised: the outward drift from the plate rotation rate", "signals": ["Drift/y"]},
        {"id": "alpha", "title": "Plate angle (prescribed swing)", "signals": ["Gimbal/q1out"]},
        {"id": "slip", "title": "Slip speed (no-slip residual)", "signals": ["Contact/slip"]},
        {"id": "force", "title": "Normal force (the plate's acceleration changes the ball's apparent weight)",
         "signals": ["Contact/f_n"]},
    ]
    return model_doc("ball-and-plate-swing",
                     f"Open loop: the plate swings about y as alpha = -{SWING['A_deg']} deg cos(2 pi {SWING['f_hz']} Hz t), "
                     "prescribed through a stiff lock spring driven by an MSf; the ball starts at rest 0.10 m from the "
                     "axis. The 3D rolling contact includes the plate's rotation rate (centrifugal drift outwards) and "
                     "acceleration (the ball centre is 15.7 mm above the axis); the signal chain LinX integrates the "
                     "linearised x'' = 5/7 g sin(alpha) of the same plate angle. Both are checked against design.py.",
                     D, SWING["t_end"], 1601, plots, reltol=1e-9, abstol=1e-11,
                     extra={"scene": {"file": "scenes/ball-and-plate.sdf"}, "bindings": free_bindings()})


def free_dashboard():
    return {"autoRerun": True, "cards": [
        {"id": "crr", "kind": "slider", "size": "2x1", "title": "Rolling resistance coefficient", "parameter": "Contact/crr",
         "options": {"min": 0.0, "max": 0.02, "step": 0.001, "decimals": 3, "unit": ""}},
        {"id": "ball", "kind": "slider", "size": "2x1", "title": "Ball inertia k (0.4 solid, 0.667 hollow)",
         "parameter": "global:k_ball", "options": {"min": 0.4, "max": 0.6667, "step": 0.2667, "decimals": 3, "unit": ""}},
        {"id": "xnow", "kind": "value", "size": "1x1", "title": "Ball x", "signals": ["Contact/u1"],
         "options": {"decimals": 3, "unit": "m", "sparkline": True}},
        {"id": "slip", "kind": "value", "size": "1x1", "title": "Slip", "signals": ["Contact/slip"],
         "options": {"decimals": 6, "unit": "m/s"}},
        {"id": "x", "kind": "plot", "size": "2x1", "title": "Ball x on the plate", "signals": ["Contact/u1"]},
        {"id": "energy", "kind": "plot", "size": "2x1", "title": "Energy (E + loss is constant)",
         "signals": ["Energy/E", "Energy/Ebal"]},
    ]}


def rig_dashboard(ctrl, tracking=False):
    c = "PIDX" if ctrl == "pid" else "LQGX"
    cards = [
        {"id": "task", "kind": "select", "size": "2x1", "title": "Task", "parameter": "Task/task"},
        {"id": "push", "kind": "slider", "size": "2x1", "title": "Push (peak force)", "parameter": "Push/Fy",
         "options": {"min": 0.0, "max": 1.5, "step": 0.05, "decimals": 2, "unit": "N"}},
        {"id": "smooth", "kind": "slider", "size": "2x1", "title": "Set-point filter of the steps (0: hard steps)",
         "parameter": "Task/t_s", "options": {"min": 0.0, "max": 2.0, "step": 0.1, "decimals": 1, "unit": "s"}},
        {"id": "ball", "kind": "slider", "size": "2x1", "title": "Ball inertia k (0.4 solid, 0.667 hollow)",
         "parameter": "global:k_ball", "options": {"min": 0.4, "max": 0.6667, "step": 0.2667, "decimals": 3, "unit": ""}},
        {"id": "xy", "kind": "plot", "size": "2x2", "title": "Ball and reference on the plate (XY)",
         "signals": ["PoseBall/g[6]", "Task/yd"], "x": "PoseBall/g[5]", "equalAspect": True},
        {"id": "pos", "kind": "plot", "size": "2x1", "title": "x and y against the reference",
         "signals": ["PoseBall/g[5]", "Task/xd", "PoseBall/g[6]", "Task/yd"]},
        {"id": "plate", "kind": "plot", "size": "2x1", "title": "Plate angles", "signals": ["Gimbal/q1out", "Gimbal/q2out"]},
        {"id": "volts", "kind": "plot", "size": "2x1", "title": "Servo voltages", "signals": ["ServoX/V", "ServoY/V"]},
        {"id": "err", "kind": "value", "size": "1x1", "title": "Error x", "signals": [f"{c}/err"],
         "options": {"decimals": 4, "unit": "m", "sparkline": True}},
        {"id": "vx", "kind": "gauge", "size": "1x1", "title": "Servo X voltage", "signals": ["ServoX/V"],
         "options": {"min": -10, "max": 10, "decimals": 1, "unit": "V",
                     "zones": [{"from": -10, "to": -8, "tone": "bad"}, {"from": -8, "to": 8, "tone": "good"},
                               {"from": 8, "to": 10, "tone": "bad"}]}},
    ]
    if ctrl == "pid":
        cards.insert(2, {"id": "kp", "kind": "slider", "size": "2x1", "title": "PID x: Kp", "parameter": "PIDX/Kp",
                         "options": {"min": 0.5, "max": 8.0, "step": 0.1, "decimals": 1, "unit": "rad/m"}})
    if tracking:  # no push and no steps: the push and set-point filter sliders would do nothing
        cards = [card for card in cards if card["id"] not in ("push", "smooth")]
    return {"autoRerun": False, "cards": cards}


def write(name, model):
    MODELS.mkdir(parents=True, exist_ok=True)
    path = MODELS / f"{name}.bgmodel.json"
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT))


NO_DIAG = {"kind": "no_diagnostics", "codes": ["E101", "E102", "E103", "E106", "E901", "W201", "W202", "W205", "W206"],
           "note": "no solver failure, causal conflict, derivative-causal store, algebraic loop or event-limit stop"}


def fk_cranks():
    xs = -rig.L_ROD_X - rig.R_ARM
    return {"kind": "scene_bindings", "fk": [
        {"link": "crank_x_link", "point": [rig.R_ARM, 0, 0], "signals": ["Viz/tipx[1]", "Viz/tipx[2]", "Viz/tipx[3]"],
         "tol": 1e-9},
        {"link": "crank_y_link", "point": [0, rig.R_ARM, 0], "signals": ["Viz/tipy[1]", "Viz/tipy[2]", "Viz/tipy[3]"],
         "tol": 1e-9}],
        "note": f"the crank joints of the scene turn the crank tips where RigViz puts the rod ends (shafts at {xs:.4f} m)"}


def step_checks(ctrl):
    """Steps of the rig models against the design (design.py's sampled linear loop)."""
    d = DESIGN[ctrl]["step"]
    ref = f"design.py ({'PID' if ctrl == 'pid' else 'LQR + Kalman'}, linear, 1 frame): rise {d['rise']:.2f} s, " \
          f"overshoot {100 * d['overshoot']:.1f} %, 2 % settling {d['settling']:.2f} s"
    return [
        {"kind": "step_response", "signal": "PoseBall/g[5]", "from_t": 1.0, "to_t": 6.0, "step_t": 1.0,
         "value": 0.1, "initial": 0.0, "settle_abs": 0.002, "max_rise_time": 1.3, "max_overshoot": 0.05,
         "max_settling_time": 2.5,
         "note": f"x step 0 -> 0.10 m at 1 s, band +-2 mm. {ref}; the rig adds the servo dead band, rolling "
                 "resistance (the ball can rest on a 0.002 rad tilt), pixel rounding and camera noise"},
        {"kind": "step_response", "signal": "PoseBall/g[6]", "from_t": 6.0, "to_t": 11.0, "step_t": 6.0,
         "value": 0.08, "initial": 0.0, "settle_abs": 0.002, "max_rise_time": 1.3, "max_overshoot": 0.05,
         "max_settling_time": 3.0, "note": "y step 0 -> 0.08 m at 6 s (x held at 0.10 m)"},
        {"kind": "cursor_value", "signal": "PoseBall/g[5]", "t": 14.9, "value": 0.0, "abs": 0.003,
         "note": "both axes back at the centre before the push"},
        {"kind": "max_abs_le", "signal": "PoseBall/g[6]", "from_t": 15.0, "to_t": 20.0,
         "value": 0.08 if ctrl == "pid" else 0.06,
         "note": "the 0.6 N, 50 ms push in y (0.019 N s) stays on the plate (PID: 61 mm, LQR: 46 mm)"},
        {"kind": "cursor_value", "signal": "PoseBall/g[6]", "t": 20.0, "value": 0.0, "abs": 0.004,
         "note": "recovered 5 s after the push"},
        {"kind": "max_abs_le", "signal": "ServoX/V", "value": rig.V_MAX, "note": "the voltage limit of the DAQ"},
        {"kind": "max_abs_le", "signal": "Contact/slip", "from_t": 0.1, "value": 0.02,
         "note": "no gross slip: the ball rolls (creep about 1e-5 m/s); when the plate snaps (the 11 s return step "
                 "with the ball 0.1 m off the axis) the ball hops for a few ms and slips up to about 1 cm/s on landing"},
        *[{"kind": "max_abs_le", "signal": f"Contact/u{k}", "value": 0.15,
           "note": "the ball stays on the plate (face half-width 0.175 m)"} for k in (1, 2)],
    ]


def smooth_step_checks():
    """The LQR with the 1 s set-point filter of the steps (Task/t_s = 1): feed-forward through the
    filtered reference, no set-point kick."""
    return [
        {"kind": "step_response", "signal": "PoseBall/g[5]", "from_t": 1.0, "to_t": 6.0, "step_t": 1.0,
         "value": 0.1, "initial": 0.0, "settle_abs": 0.002, "max_overshoot": 0.03, "max_settling_time": 1.5,
         "note": "x 0 -> 0.10 m along a 1 s quintic: the feed-forward tilts the plate ahead of the ball, so it "
                 "settles faster (about 0.9 s) than after the hard step (about 2 s)"},
        {"kind": "max_abs_le", "signal": "Contact/slip", "from_t": 0.1, "value": 0.005,
         "note": "no hop at the return step (the hard-step model slips up to about 1 cm/s there)"},
        NO_DIAG,
    ]


def expected():
    fr, sw, tr = DESIGN["free"], DESIGN["swing"], DESIGN["tracking"]
    drift = [a - b for a, b in zip(sw["x_full"], sw["x_lin"])]
    k_shell = 2.0 / 3.0
    a_shell = rig.G0 * math.sin(FREE_TILT) / (1 + k_shell)
    t_shell = math.sqrt(2 * abs(FREE_X0) / a_shell)
    free_checks = [
        {"kind": "zero_crossing", "signal": "Contact/u1", "n": 1, "direction": "up", "value": fr["t_cross"],
         "abs": 1e-3, "note": f"roll time to the centre, sqrt(2 x0 / a) with a = 5/7 g sin(1 deg) = {fr['accel']:.6f} m/s^2"},
        {"kind": "cursor_value", "signal": "Contact/u1", "t": 2.0, "value": fr["x_end"], "abs": 2e-4,
         "note": "x0 + a t^2 / 2 at 2 s (the lock springs let the tilt grow by 1.6e-5 rad as the ball moves)"},
        {"kind": "ratio", "signal": "Energy/Ekrot", "signal_b": "Energy/Ek", "t": 2.0, "value": 2.0 / 7.0, "rtol": 2e-3,
         "note": "rolling solid sphere: (J w^2) / (m v^2 + J w^2) = (2/5) / (7/5)"},
        {"kind": "max_abs_le", "signal": "Contact/slip", "from_t": 0.05, "value": 2e-5,
         "note": "no-slip residual: the regularised Coulomb friction creeps at (2/7) m g sin(a) vs / (mu f_n) = 1.25e-5 m/s"},
        {"kind": "invariant", "terms": [{"signal": "Energy/Ebal", "coeff": 1.0}], "from_t": 0.1, "scale": 2.8e-3,
         "tol": 1e-5, "note": "E + contact loss is constant (lossless rig, crr = 0): drift below 1e-5 of the final "
                              "kinetic energy 2.8e-3 J (the first 0.1 s settle the contact and joint deflections)"},
        {"kind": "scene_bindings"},
        NO_DIAG,
    ]
    shell_checks = [
        {"kind": "zero_crossing", "signal": "Contact/u1", "n": 1, "direction": "up", "value": t_shell, "abs": 1e-3,
         "note": f"hollow ball (k = 2/3): a = 3/5 g sin(1 deg) = {a_shell:.6f} m/s^2"},
        {"kind": "ratio", "signal": "Energy/Ekrot", "signal_b": "Energy/Ek", "t": 2.0, "value": 0.4, "rtol": 2e-3,
         "note": "(2/3) / (5/3)"},
    ]
    swing_checks = [
        *[{"kind": "cursor_value", "signal": "Drift/y", "t": t, "value": v, "rtol": 5e-3, "abs": 2e-5,
           "note": "full minus linearised position: design.py integrates x'' = 5/7 (g sin a + x a'^2 - (h + 2r/5) a'')"
                   " against x'' = 5/7 g sin a"} for t, v in zip(sw["ts"][1:], drift[1:])],
        {"kind": "cursor_value", "signal": "Contact/u1", "t": sw["t_end"], "value": sw["x_full"][-1], "abs": 1e-3,
         "note": "absolute position; the lock spring droops by m g x / k = 7e-6 rad under the ball, worth 0.4 mm in 4 s"},
        {"kind": "max_abs_le", "signal": "Contact/slip", "from_t": 0.05, "value": 5e-5, "note": "rolls without slip"},
        {"kind": "min_ge", "signal": "Contact/f_n", "from_t": 0.05, "value": 0.5,
         "note": "the plate's angular acceleration (5.5 rad/s^2) changes the normal force, it never lifts off"},
        {"kind": "scene_bindings"},
        NO_DIAG,
    ]

    def rms(task_note, bound, ref):
        return [{"kind": "rms_difference", "signal": f"PoseBall/g[{i}]", "signal_b": f"Task/{a}d", "from_t": 10.0,
                 "to_t": 30.0, "value": bound, "note": f"{task_note}, {a} axis, after the growth; {ref}"}
                for i, a in ((5, "x"), (6, "y"))]

    track = rms("figure-8 tracking error", 0.004,
                f"design.py (linear, no rolling resistance): {tr['figure8_lqr_ff']:.2e} m combined; the rig's "
                "rolling resistance (0.002) needs 0.014 m/s^2 the feed-forward does not know: about 2 mm per axis")
    track_circle = rms("circle tracking error", 0.004, "rig about 1.9 mm per axis")
    track_crr0 = rms("circle tracking error without rolling resistance", 3e-4,
                     f"design.py: {tr['circle_lqr_ff']:.2e} m combined; the rig without rolling resistance about "
                     "2.0e-4 m per axis")
    pid_circle = rms("PID circle tracking error (no feed-forward)", 0.05,
                     f"design.py: {tr['circle_pid']:.4f} m combined ({tr['circle_pid'] / math.sqrt(2):.4f} per axis); "
                     "the PID has no feed-forward, so it lags the moving reference")
    no_push = {"Push/t_push": 1.0e6}
    doc = {
        "project": "ball-and-plate",
        "description": "Ball-and-plate rig (Quanser 2 DOF Ball Balancer type): a 1 in steel ball on a 0.35 m acrylic "
                       "plate on a gimbal, tilted by two SRV02-type servos through cranks and push rods, an overhead "
                       "camera at 30 frames/s with one frame of latency. Open-loop checks against the rolling-sphere "
                       "laws (5/7 g sin a, 3/5 for a hollow ball, the rotation-rate drift of a swinging plate, energy); "
                       "closed-loop checks of the cascaded PID and the LQR + Kalman controllers against the sampled "
                       "linear loops of design/design.py.",
        "models": {
            "ball-and-plate-free": {"checks": free_checks},
            "ball-and-plate-free-hollow": {"model": "ball-and-plate-free", "overrides": {"global:k_ball": k_shell},
                                           "checks": shell_checks + [NO_DIAG]},
            "ball-and-plate-swing": {"checks": swing_checks},
            "ball-and-plate-pid": {"checks": step_checks("pid") + [fk_cranks(), NO_DIAG]},
            "ball-and-plate-lqr": {"checks": step_checks("lqr") + [fk_cranks(), NO_DIAG]},
            "ball-and-plate-lqr-smooth-steps": {"model": "ball-and-plate-lqr", "overrides": {"Task/t_s": 1.0},
                                                "checks": smooth_step_checks()},
            "ball-and-plate-track": {"checks": track + [
                {"kind": "max_abs_le", "signal": "ServoX/V", "value": rig.V_MAX, "note": "voltage limit"},
                fk_cranks(), NO_DIAG]},
            "ball-and-plate-track-circle": {"model": "ball-and-plate-track", "overrides": {"Task/task": 2},
                                            "checks": track_circle + [NO_DIAG]},
            "ball-and-plate-track-circle-crr0": {"model": "ball-and-plate-track",
                                                 "overrides": {"Task/task": 2, "Contact/crr": 0.0},
                                                 "checks": track_crr0 + [NO_DIAG]},
            "ball-and-plate-pid-circle": {"model": "ball-and-plate-pid", "overrides": {"Task/task": 2, **no_push},
                                          "settings": {"t_end": 30.0, "output": {"points": 3001}},
                                          "checks": pid_circle + [NO_DIAG]},
        },
    }
    path = ROOT / "expected.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT))


def main(only=None):
    todo = {
        "ball-and-plate-free": free_model,
        "ball-and-plate-swing": swing_model,
        "ball-and-plate-pid": lambda: rig_model(
            "ball-and-plate-pid", "Cascaded PID: 30 Hz outer loops on the delayed camera (filtered derivative on the "
            "measurement, conditional integral) set the servo angles; 500 Hz servo PD loops on the encoders drive the "
            "SRV02 bond graphs. Steps in x (1 s) and y (6 s), back to the centre (11 s), a 0.6 N push in y (15 s).",
            "pid", 1, T_STEPS, 2001, dashboard=rig_dashboard("pid")),
        "ball-and-plate-lqr": lambda: rig_model(
            "ball-and-plate-lqr", "LQR with a Kalman filter: per axis a steady-state Kalman filter on the model with "
            "the camera's one-frame latency (camera and encoder) and a discrete LQR with integral action at 30 Hz; "
            "the same servo loops, steps and push as ball-and-plate-pid.",
            "lqr", 1, T_STEPS, 2001, dashboard=rig_dashboard("lqr")),
        "ball-and-plate-track": lambda: rig_model(
            "ball-and-plate-track", "Trajectory tracking: the LQR/Kalman controller with the reference feed-forward "
            "(plate angle from the reference acceleration and jerk) follows a figure-8 (task 3, 0.2 x 0.12 m, 8 s "
            "period); task 2 is a circle of radius 0.08 m, 6 s period. Both grow from the centre over 3 s.",
            "lqr", 3, 30.0, 3001, push=False, dashboard=rig_dashboard("lqr", tracking=True)),
    }
    for k, f in todo.items():
        if only and k not in only:
            continue
        write(k, f())
    if not only:
        expected()


if __name__ == "__main__":
    main(sys.argv[1:] or None)
