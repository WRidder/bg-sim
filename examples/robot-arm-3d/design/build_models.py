# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the RRR model documents of `robot-arm-3d` (plan 9.8, X5.3).

    uv run examples/robot-arm-3d/design/build_models.py

Models written into `models/` (the X-MB3 six-axis `arm.bgmodel.json` is never touched):

* `rrr`            the equation-block arm `ArmDynamics3R` behind 3 x (DCMotor -> IdealGear 50),
                   the 1 ms PD + gravity controller `ArmCtrl3R`, minimum-jerk TimeTables;
* `rrr-free`       the same arm with the motors removed (`Se e = 0`), g = 0 and an initial
                   rate: the energy-conservation model;
* `rrr-torque`     the same arm driven by ideal torque sources from the same controller and
                   references (the comparison partner of the multibond model);
* `rrr-multibond`  the same RRR geometry built from the M3 spatial stdlib (compliant
                   `Revolute3D`, `RigidBody3D`, `FixedTransform3DNeutral`) behind the same
                   torque sources, controller and references; `-soft` changes the joint
                   stiffness only.

Every designed number (tables, gains, free start) comes from `design.py`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import design as dz

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

SCENE = {"file": "scenes/rrr.sdf"}


# ------------------------------------------------------------------ small helpers


def fmt(value: float) -> str:
    return repr(float(value))


def vec(values) -> str:
    return "[" + ", ".join(fmt(v) for v in values) + "]"


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[dict] = []
        self._ids: dict[str, str] = {}

    def node(
        self,
        key: str,
        name: str,
        block: dict,
        x: int,
        y: int,
        params: dict | None = None,
        constants: dict | None = None,
        starts: dict | None = None,
        rotation: int = 0,
        flip: bool = False,
    ) -> str:
        self._ids[key] = key
        self.nodes.append(
            {
                "id": key,
                "name": name,
                "block": block,
                "position": {"x": x, "y": y},
                "rotation": rotation,
                "flipX": flip,
                "params": {k: str(v) for k, v in (params or {}).items()},
                "constants": {k: str(v) for k, v in (constants or {}).items()},
                "starts": {k: str(v) for k, v in (starts or {}).items()},
                "ui": {"showLabel": True, "color": None},
            }
        )
        return key

    def ref(self, key: str, name: str, ref: str, x: int, y: int, **kw) -> str:
        return self.node(key, name, {"ref": ref}, x, y, **kw)

    def junction(self, key: str, name: str, x: int, y: int) -> str:
        return self.node(key, name, {"junction": "1"}, x, y)

    def connect(
        self,
        kind: str,
        a: tuple[str, str | None],
        b: tuple[str, str | None],
        route: list[tuple[int, int]] | None = None,
        label: str | None = None,
    ) -> None:
        def end(pair):
            node, port = pair
            return {"node": node} if port is None else {"node": node, "port": port}

        self.connections.append(
            {
                "id": f"{kind[0]}{len(self.connections) + 1:02d}",
                "kind": kind,
                "from": end(a),
                "to": end(b),
                "route": [{"x": px, "y": py} for px, py in (route or [])],
                "label": label,
            }
        )

    def document(self) -> dict:
        return {
            "nodes": self.nodes,
            "connections": self.connections,
            "subsystemPorts": [],
            "annotations": [],
        }


def project_block(name: str) -> dict:
    return {"ref": f"project:{name}"}


# ------------------------------------------------------------------ quaternion poses


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def qrot(q, v):
    w, x, y, z = q
    p = qmul(qmul(q, (0.0, *v)), (w, -x, -y, -z))
    return p[1:]


def pose_mul(a, b):
    (qa, ta), (qb, tb) = a, b
    rotated = qrot(qa, tb)
    return qmul(qa, qb), tuple(ta[i] + rotated[i] for i in range(3))


def pose_inv(p):
    q, t = p
    qi = (q[0], -q[1], -q[2], -q[3])
    rotated = qrot(qi, t)
    return qi, tuple(-c for c in rotated)


def clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-15 else value


def pose_params(p) -> dict:
    q, t = p
    names = ("qw", "qx", "qy", "qz", "x", "y", "z")
    return {n: fmt(clean(v)) for n, v in zip(names, (*q, *t), strict=True)}


IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
S = math.sqrt(0.5)
# Joint 2 and 3 frames: local z = world -y (positive rotation raises the arm), local x = the
# arm direction.  That frame is Rx(+90 deg).
RX90 = ((S, S, 0.0, 0.0), (0.0, 0.0, 0.0))


# ------------------------------------------------------------------ drives (shared)


def settings(
    solver: str, reltol: float, abstol: float, points: int, t_end: float = dz.T_END
) -> dict:
    return {
        "t_start": 0.0,
        "t_end": t_end,
        "solver": solver,
        "reltol": reltol,
        "abstol": abstol,
        "max_step": None,
        "output": {"mode": "points", "points": points},
        "event_limit": 10000,
    }


def bindings(signals: list[str]) -> list[dict]:
    return [
        {"target": f"joint:{name}", "property": "position", "signal": signal}
        for name, signal in zip(("joint1", "joint2", "joint3"), signals, strict=True)
    ]


def controller_params(design: dict) -> dict:
    p = {}
    for i in range(3):
        p[f"Kp{i + 1}"] = fmt(design["Kp"][i])
        p[f"Kd{i + 1}"] = fmt(design["Kd"][i])
    p.update(
        l2=fmt(dz.L2), l3=fmt(dz.L3), m2=fmt(dz.M2), m3=fmt(dz.M3), g=fmt(dz.G),
        R=fmt(dz.R_W), k_t=fmt(dz.K_T), n=fmt(dz.N_GEAR), umax=fmt(dz.UMAX),
    )  # fmt: skip
    return p


CTRL_X, CTRL_Y = 360, 100  # the controller sits in a band above the plant
CTRL_RIGHT = 440  # where the feedback wires enter the controller (right edge + 20)
ROWS = [340, 540, 740]  # the three drive rows of the equation models
ARM_X, ARM_Y = 780, 540  # the equation-block arm (three power ports on its left edge)
# gear / torque source -> the arm's three power ports
ARM_LANES = [[(690, 370), (690, 560)], [], [(710, 770), (710, 580)]]


def add_references(d: Diagram, design: dict) -> None:
    """The three minimum-jerk TimeTables (design.py), left of the controller."""
    table = design["table"]
    for i in range(3):
        d.ref(
            f"ref{i + 1}", f"Ref{i + 1}", "stdlib:sources/TimeTable", 60, 40 + 80 * i,
            params={
                "t_start": "0.0", "sample_time": fmt(dz.TABLE_DT),
                "values": vec(table[:, i]), "method": "1",
            },
            constants={"N": str(table.shape[0])},
        )  # fmt: skip


def add_controller(
    d: Diagram, design: dict, feedback: list[tuple[str, str, int, int]]
) -> None:
    """The firmware, its references and the six measurement wires.

    ``feedback`` lists the wires as ``(node, port, x, y)``, in the order q1, q2, q3, qd1, qd2,
    qd3: ``(x, y)`` is the first waypoint of the route (the line leaves the source towards it).
    Each wire runs up a vertical lane to a level on the controller's right edge; the lanes
    further right take the higher levels, so the six wires never cross.
    """
    d.node(
        "ctrl",
        "Ctrl",
        project_block("ArmCtrl3R"),
        CTRL_X,
        CTRL_Y,
        params=controller_params(design),
    )
    for i in range(3):
        d.connect("signal", (f"ref{i + 1}", "y"), ("ctrl", f"ref{i + 1}"))
    order = sorted(range(6), key=lambda m: feedback[m][2])
    level = {m: 160 - 10 * (5 - rank) for rank, m in enumerate(order)}
    names = [f"q{i + 1}" for i in range(3)] + [f"qd{i + 1}" for i in range(3)]
    for m in range(6):
        node, port, x, y = feedback[m]
        d.connect(
            "signal",
            (node, port),
            ("ctrl", names[m]),
            route=[(x, y), (x, level[m]), (CTRL_RIGHT, level[m])],
        )


def add_motors(d: Diagram, arm_ports: list[tuple[str, str]]) -> None:
    """Three voltage amplifiers + DCMotors + IdealGears; the gear output goes to `arm_ports`."""
    for i in range(3):
        k = i + 1
        y = ROWS[i]
        d.ref(
            f"amp{k}",
            f"Amp{k}",
            "stdlib:electrical/VoltageSource",
            240,
            y,
            params={"V": "1.0"},
        )
        d.ref(f"gnd{k}", f"Gnd{k}", "stdlib:electrical/Ground", 240, y + 100)
        d.ref(
            f"mot{k}", f"Motor{k}", "stdlib:converters/DCMotor", 400, y,
            params={
                "R": fmt(dz.R_W), "L": fmt(dz.L_W), "k_t": fmt(dz.K_T),
                "J": fmt(dz.J_M), "d": "0.0",
            },
        )  # fmt: skip
        d.ref(f"fix{k}", f"Fix{k}", "stdlib:rotation/FixedShaft", 400, y - 100)
        d.ref(
            f"gear{k}",
            f"Gear{k}",
            "stdlib:rotation/IdealGear",
            560,
            y,
            params={"n": fmt(dz.N_GEAR)},
        )
        d.connect("wire", (f"amp{k}", "p"), (f"mot{k}", "p"))
        d.connect("wire", (f"mot{k}", "n"), (f"gnd{k}", "p"))
        d.connect("wire", (f"amp{k}", "n"), (f"gnd{k}", "p"))
        d.connect("wire", (f"mot{k}", "housing"), (f"fix{k}", "a"))
        d.connect("wire", (f"mot{k}", "shaft"), (f"gear{k}", "a"))
        d.connect("wire", (f"gear{k}", "b"), arm_ports[i], route=ARM_LANES[i])
        # controller output: along a level above the plant, then down a lane left of the amps
        lanes = [
            [(380, 280), (270, 280)],
            [(380, 270), (200, 270), (200, y + 30)],
            [(380, 260), (170, 260), (170, y + 30)],
        ]
        d.connect("signal", ("ctrl", f"u{k}"), (f"amp{k}", "u"), route=lanes[i])


def torque_lanes(x: list[int], y: list[int]) -> list[list[tuple[int, int]]]:
    """Controller output -> a drive block at (x[i], y[i]): the first from above, the others
    down a lane to the left of the block (levels 280, 270, 260: no crossings)."""
    return [
        [(380, 280), (x[0] + 30, 280)],
        [(380, 270), (x[1] - 40, 270), (x[1] - 40, y[1] + 30)],
        [(380, 260), (x[2] - 70, 260), (x[2] - 70, y[2] + 30)],
    ]


def add_torque_sources(
    d: Diagram,
    arm_ports: list[tuple[str, str]],
    x: list[int],
    y: list[int],
    bond_routes: list[list[tuple[int, int]]],
    top_lanes: bool = False,
) -> None:
    """Ideal joint-torque sources (MSe, gain 1) driven by the controller's `tc` outputs.

    With ``top_lanes`` every wire runs along its level and down a lane to the top of its block."""
    lanes = torque_lanes(x, y)
    if top_lanes:
        lanes = [
            [(380, 280 - 10 * i), (x[i] + 30, 280 - 10 * i), (x[i] + 30, y[i] - 10)]
            for i in range(3)
        ]
    for i in range(3):
        k = i + 1
        d.ref(
            f"drv{k}",
            f"Drive{k}",
            "stdlib:bondgraph/MSe",
            x[i],
            y[i],
            params={"gain": "1.0"},
        )
        d.connect("bond", (f"drv{k}", "p"), arm_ports[i], route=bond_routes[i])
        d.connect("signal", ("ctrl", f"tc{k}"), (f"drv{k}", "u"), route=lanes[i])


# ------------------------------------------------------------------ rrr (equation block)


def arm_params(g: float = dz.G) -> dict:
    return {
        "l2": fmt(dz.L2), "l3": fmt(dz.L3), "m2": fmt(dz.M2), "m3": fmt(dz.M3),
        "Jb": fmt(dz.JB), "g": fmt(g),
    }  # fmt: skip


def driven_plots(angle: list[str], rate: list[str]) -> list[dict]:
    return [
        {
            "id": "p1",
            "title": "Joint angles and references",
            "signals": [*angle, "Ref1/y", "Ref2/y", "Ref3/y"],
        },
        {
            "id": "p2",
            "title": "Tracking errors",
            "signals": ["Ctrl/e1", "Ctrl/e2", "Ctrl/e3"],
        },
        {
            "id": "p3",
            "title": "Motor voltages",
            "signals": ["Ctrl/u1", "Ctrl/u2", "Ctrl/u3"],
        },
        {"id": "p4", "title": "Joint rates", "signals": rate},
    ]


def torque_plots(angle: list[str], rate: list[str]) -> list[dict]:
    plots = driven_plots(angle, rate)
    plots[2] = {
        "id": "p3",
        "title": "Joint torque commands",
        "signals": ["Ctrl/tc1", "Ctrl/tc2", "Ctrl/tc3"],
    }
    return plots


def arm_feedback() -> list[tuple[str, str, int, int]]:
    """The arm's six measurement outputs leave its right edge towards lanes at x = 900 ..."""
    names = ["q1", "q2", "q3", "qd1", "qd2", "qd3"]
    return [("arm", names[m], 900 + 20 * m, ARM_Y + 30) for m in range(6)]


def build_rrr(design: dict) -> dict:
    d = Diagram()
    d.ref(
        "arm", "Arm", "project:ArmDynamics3R", ARM_X, ARM_Y, params=arm_params(),
        starts={"q": vec(dz.Q_START)},
    )  # fmt: skip
    add_references(d, design)
    add_controller(d, design, arm_feedback())
    add_motors(d, [("arm", "j1"), ("arm", "j2"), ("arm", "j3")])
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "rrr",
        "$comment": (
            "X5.3 / plan 9.8: RRR arm as an equation block. ArmDynamics3R (point masses, Hamiltonian "
            "form, three Rotation ports) behind 3 x (DCMotor -> IdealGear n = 50). The 1 ms ArmCtrl3R "
            "is a PD + gravity compensation (dV/dq from the measured q) that turns the joint torque "
            "command into a motor voltage; the references are minimum-jerk TimeTables from design.py."
        ),
        "diagram": d.document(),
        "settings": settings("auto", 1e-8, 1e-10, 2001),
        "plots": driven_plots(
            ["Arm/q1", "Arm/q2", "Arm/q3"], ["Arm/qd1", "Arm/qd2", "Arm/qd3"]
        ),
        "scene": SCENE,
        "bindings": bindings(["Arm/q1", "Arm/q2", "Arm/q3"]),
    }


def build_torque(design: dict) -> dict:
    d = Diagram()
    d.ref(
        "arm", "Arm", "project:ArmDynamics3R", ARM_X, ARM_Y, params=arm_params(),
        starts={"q": vec(dz.Q_START)},
    )  # fmt: skip
    add_references(d, design)
    add_controller(d, design, arm_feedback())
    add_torque_sources(
        d, [("arm", "j1"), ("arm", "j2"), ("arm", "j3")], [560] * 3, ROWS, ARM_LANES
    )
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "rrr-torque",
        "$comment": (
            "X5.3 / DEC-M5-2 comparison partner of rrr-multibond: ArmDynamics3R driven by ideal joint "
            "torque sources (MSe) from the same ArmCtrl3R firmware and TimeTable references as the "
            "multibond model. The motors are removed on purpose: a rotor inertia rigidly coupled to the "
            "multibond joint rate is derivative-causal (W201) and the multibond model fails at t = 0."
        ),
        "diagram": d.document(),
        "settings": settings("auto", 1e-8, 1e-10, 2001),
        "plots": torque_plots(
            ["Arm/q1", "Arm/q2", "Arm/q3"], ["Arm/qd1", "Arm/qd2", "Arm/qd3"]
        ),
        "scene": SCENE,
        "bindings": bindings(["Arm/q1", "Arm/q2", "Arm/q3"]),
    }


def build_free() -> dict:
    d = Diagram()
    q0, p0 = dz.free_start()
    d.ref(
        "arm", "Arm", "project:ArmDynamics3R", 400, 220, params=arm_params(0.0),
        starts={"q": vec(q0), "p": vec(p0)},
    )  # fmt: skip
    for i in range(3):
        k = i + 1
        d.ref(
            f"se{k}",
            f"Free{k}",
            "stdlib:bondgraph/Se",
            160,
            100 + 120 * i,
            params={"e": "0.0"},
        )
        d.connect("bond", (f"se{k}", "p"), ("arm", f"j{k}"))
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "rrr-free",
        "$comment": (
            "X5.3 / plan 9.8 energy test: ArmDynamics3R with the motors removed (zero-torque Se on every "
            "joint) and g = 0, released with the joint rates (2, -1.5, 2.5) rad/s. Total energy E = T + V "
            "is a block output and must stay constant."
        ),
        "diagram": d.document(),
        "settings": settings("auto", 1e-10, 1e-12, 1001),
        "plots": [
            {
                "id": "p1",
                "title": "Joint angles (free motion)",
                "signals": ["Arm/q1", "Arm/q2", "Arm/q3"],
            },
            {
                "id": "p2",
                "title": "Joint rates",
                "signals": ["Arm/qd1", "Arm/qd2", "Arm/qd3"],
            },
            {"id": "p3", "title": "Total energy", "signals": ["Arm/E"]},
        ],
        "scene": SCENE,
        "bindings": bindings(["Arm/q1", "Arm/q2", "Arm/q3"]),
    }


# ------------------------------------------------------------------ rrr-multibond

JP = 1e-8  # principal moments of the point-mass bodies [kg m^2] (a point has none)
MB = 1.0  # base body mass at the pivot [kg]; its inertia about z is Jb

STAIR_X, STAIR_Y = 420, 340  # first row of the chain staircase
STAIR_DX, STAIR_DY = 480, 200
BAND_Y = 1000  # the composed-pose chain


def rotation_matrix(q) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def static_deflections(
    ln, lc, mass, q0, k: float
) -> list[tuple[list[float], list[float]]]:
    """The held-direction deflections (dth_xy, dl) at rest in the start pose.

    The weight of everything distal to joint i loads its compliant directions: the child
    origin sags by F/kt (`dl`, child-frame components) and the child rotates by M/kr about
    the two held axes (`dth`), where F and M are the weight and its moment about the joint
    origin.  Starting the arm on these values (as X-MB3 does) releases it at rest on its
    static deflection instead of exciting the stiff held modes.
    """
    child = IDENTITY
    joints = []  # (origin, R_child)
    bodies = []  # CoM position in the world
    for i in range(3):
        joint_frame = pose_mul(child, ln[i])
        rz = ((math.cos(q0[i] / 2), 0.0, 0.0, math.sin(q0[i] / 2)), (0.0, 0.0, 0.0))
        child = pose_mul(joint_frame, rz)
        joints.append((np.array(joint_frame[1]), rotation_matrix(child[0])))
        bodies.append(np.array(pose_mul(child, lc[i])[1]))
    result = []
    for i in range(3):
        origin, r_child = joints[i]
        force = np.zeros(3)
        moment = np.zeros(3)
        for j in range(i, 3):
            weight = np.array([0.0, 0.0, -mass[j] * dz.G])
            force += weight
            moment += np.cross(bodies[j] - origin, weight)
        dl = r_child.T @ force / k
        dth = (r_child.T @ moment / k)[:2]
        result.append((list(dth), list(dl)))
    return result


def build_multibond(design: dict, k_joint: float, name: str) -> dict:
    d = Diagram()
    kt = kr = k_joint
    # LN_i: pose of the joint-i frame in the child frame of joint i-1 (the world for joint 1)
    ln = [IDENTITY, RX90, ((1.0, 0.0, 0.0, 0.0), (dz.L2, 0.0, 0.0))]
    # LC_i: pose of the body-i CoM frame in the child frame of joint i
    lc = [
        IDENTITY,
        ((1.0, 0.0, 0.0, 0.0), (dz.L2, 0.0, 0.0)),
        ((1.0, 0.0, 0.0, 0.0), (dz.L3, 0.0, 0.0)),
    ]
    mass = [MB, dz.M2, dz.M3]
    inertia = [[dz.JB] * 3, [JP] * 3, [JP] * 3]
    distal = [MB + dz.M2 + dz.M3, dz.M2 + dz.M3, dz.M3]
    q0 = dz.Q_START
    deflections = static_deflections(ln, lc, mass, q0, k_joint)

    bx = [STAIR_X + STAIR_DX * i for i in range(3)]
    ry = [STAIR_Y + STAIR_DY * i for i in range(3)]
    d.ref("world", "World", "stdlib:multibond/GroundSpatial", bx[0] - 120, ry[0])
    d.ref(
        "mount",
        "Mount",
        "stdlib:multibond/FixedTransform3DNeutral",
        bx[0],
        ry[0],
        params=pose_params(IDENTITY),
    )
    d.ref(
        "mpose",
        "MountPose",
        "stdlib:spatial/LocalPose3D",
        bx[0] - 120,
        BAND_Y,
        params=pose_params(IDENTITY),
    )
    d.connect("bond", ("world", "p"), ("mount", "b"))

    prev_world = "mpose"  # the ComposePose3D output holding W_{i-1}
    for i in range(3):
        k = i + 1
        x0, y0 = bx[i], ry[i]
        d.ref(
            f"j{k}", f"J{k}", "stdlib:spatial/Revolute3D", x0 + 120, y0,
            params={
                "kt": fmt(kt), "kr": fmt(kr),
                "bt": fmt(1.4 * math.sqrt(kt * distal[i])),
                "br": fmt(1.4 * math.sqrt(kr * 0.3)),
                "q0": fmt(q0[i]),
            },
            starts={"dth": vec(deflections[i][0]), "dl": vec(deflections[i][1])},
        )  # fmt: skip
        d.ref(
            f"link{k}",
            f"Link{k}",
            "stdlib:multibond/FixedTransform3DNeutral",
            x0 + 240,
            y0,
            params=pose_params(lc[i]),
        )
        d.junction(f"bj{k}", f"BJ{k}", x0 + 360, y0 + 10)
        d.ref(
            f"b{k}", f"B{k}", "stdlib:spatial/RigidBody3D", x0 + 350, y0 + 100,
            params={"m": fmt(mass[i]), "J": vec(inertia[i]), "g0": fmt(dz.G)},
        )  # fmt: skip
        if i == 0:
            d.connect("bond", ("mount", "a"), ("j1", "parent"))
        else:
            # T_{i+1}: pose of body i in the joint-(i+1) frame = LN^-1 o LC_i
            t_pose = pose_mul(pose_inv(ln[i]), lc[i - 1])
            d.ref(
                f"t{k}",
                f"T{k}",
                "stdlib:multibond/FixedTransform3DNeutral",
                x0,
                y0,
                params=pose_params(t_pose),
            )
            d.connect("bond", (f"t{k}", "a"), (f"j{k}", "parent"))
            d.connect("bond", (f"t{k}", "b"), (f"bj{k - 1}", None))
        d.connect("bond", (f"j{k}", "child"), (f"link{k}", "a"))
        d.connect("bond", (f"link{k}", "b"), (f"bj{k}", None))
        d.connect("bond", (f"b{k}", "p"), (f"bj{k}", None))
        # pose chain: W_i = W_{i-1} o LN_i o J_i.pose ; body pose = W_i o LC_i
        d.ref(
            f"ln{k}",
            f"LN{k}",
            "stdlib:spatial/LocalPose3D",
            x0,
            BAND_Y + 100,
            params=pose_params(ln[i]),
        )
        d.ref(f"ca{k}", f"CA{k}", "stdlib:multibond/ComposePose3D", x0, BAND_Y)
        d.ref(f"w{k}", f"W{k}", "stdlib:multibond/ComposePose3D", x0 + 120, BAND_Y)
        d.ref(
            f"lc{k}",
            f"LC{k}",
            "stdlib:spatial/LocalPose3D",
            x0 + 350,
            BAND_Y + 240,
            params=pose_params(lc[i]),
        )
        d.ref(
            f"pb{k}", f"P{k}", "stdlib:multibond/ComposePose3D", x0 + 350, BAND_Y + 120
        )
        d.connect("signal", (prev_world, "g"), (f"ca{k}", "gp"))
        d.connect("signal", (f"ln{k}", "g"), (f"ca{k}", "gl"))
        d.connect("signal", (f"ca{k}", "g"), (f"w{k}", "gp"))
        d.connect("signal", (f"j{k}", "pose"), (f"w{k}", "gl"))
        d.connect("signal", (f"w{k}", "g"), (f"pb{k}", "gp"))
        d.connect("signal", (f"lc{k}", "g"), (f"pb{k}", "gl"))
        d.connect("signal", (f"pb{k}", "g"), (f"b{k}", "g"))
        prev_world = f"w{k}"

    # measurement wires leave the joints upwards: lanes x = joint centre + 30 (q) / + 50 (qd)
    feedback = [
        (f"j{k}", "qout", bx[k - 1] + 150, ry[k - 1] - 30) for k in (1, 2, 3)
    ] + [(f"j{k}", "qdout", bx[k - 1] + 170, ry[k - 1] - 30) for k in (1, 2, 3)]
    add_references(d, design)
    add_controller(d, design, feedback)
    add_torque_sources(
        d,
        [("j1", "drive"), ("j2", "drive"), ("j3", "drive")],
        [bx[i] + 200 for i in range(3)],
        [ry[i] + 100 for i in range(3)],
        [[], [], []],
        top_lanes=True,
    )
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": (
            "X5.3 / DEC-M5-2: the RRR geometry of ArmDynamics3R built from the M3 spatial stdlib. Base "
            "body (1 kg at the pivot, yaw inertia Jb = 0.05) on a compliant Revolute3D about world z; "
            "upper arm and forearm joints about world -y (joint frame Rx(90 deg), local z = -y); point "
            "masses m2 = 2 at the elbow and m3 = 1 at the tip as RigidBody3D with 1e-8 kg m^2 "
            "principal moments, links l2 = 0.4 and l3 = 0.3 as FixedTransform3DNeutral. The torque "
            "sources, controller and TimeTable references are those of model rrr-torque. Held directions "
            f"have kt = kr = {k_joint:g}, and the arm is released on its static deflections; the only "
            "difference to the equation block is the joint compliance (and the 1e-8 point-mass inertias)."
        ),
        "diagram": d.document(),
        "settings": settings("Rodas5P", 1e-8, 1e-10, 2001),
        "plots": torque_plots(
            ["J1/qout", "J2/qout", "J3/qout"], ["J1/qdout", "J2/qdout", "J3/qdout"]
        ),
        "scene": SCENE,
        "bindings": bindings(["J1/qout", "J2/qout", "J3/qout"]),
    }


# ------------------------------------------------------------------ main


def write(model: dict) -> None:
    path = MODELS / f"{model['name']}.bgmodel.json"
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT.parent.parent)}")


def main() -> None:
    design = dz.design()
    write(build_rrr(design))
    write(build_free())
    write(build_torque(design))
    write(build_multibond(design, 1e7, "rrr-multibond"))
    write(build_multibond(design, 1e6, "rrr-multibond-soft"))
    write(build_multibond(design, 1e8, "rrr-multibond-stiff"))


if __name__ == "__main__":
    main()
