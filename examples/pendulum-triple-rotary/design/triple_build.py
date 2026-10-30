"""Model, library block and scene generator of `pendulum-triple-rotary` (X5.13).

Adapted from `examples/pendulum-double-rotary/design/rotary_build.py`: the drive, the joint and gear
stiffness come from `design.json`, and the firmware catches with the LQR cost-to-go `x' P x`
instead of a weighted norm. The design numbers come from `design.json` (written by `design.py`), the
bond graph is assembled here.

Bond graph (multibond, spatial)::

    World -- Mount -- J1 (Revolute3D, world z) -- ArmLink -- BJ1 -- Arm (RigidBody3D)
                       |drive                                 |
       Motor (ElectricDrive) -- Shaft (ElasticShaft) -- Gear (IdealGear)
                                                              T2 -- J2 (Revolute3D, arm axis) -- L1 link -- BJ2 -- Link1
                                                                            T3 -- J3 ... (one joint and one body per link)
    Dist (ExternalWrenchSpatial) on the tip link through a FixedTransform3DNeutral at the tip.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import triple_lib as tl

# ------------------------------------------------------------------ small helpers


def plant_from(dz: dict) -> tl.Plant:
    """The design model with the parameters stored in `design.json`."""
    return tl.Plant(dz["lengths"], dz["masses"], tl.Drive(**dz["drive"]), jfric=dz["jfric"])



def fmt(value: float) -> str:
    return repr(float(value))


def vec(values) -> str:
    return "[" + ", ".join(fmt(v) for v in values) + "]"


def mat(rows) -> str:
    return "[" + "; ".join(" ".join(f"{v:.9g}" for v in row) for row in rows) + "]"


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[dict] = []

    def node(self, key, name, block, x, y, params=None, constants=None, starts=None) -> str:
        self.nodes.append(
            {
                "id": key,
                "name": name,
                "block": block,
                "position": {"x": x, "y": y},
                "rotation": 0,
                "flipX": False,
                "params": {k: str(v) for k, v in (params or {}).items()},
                "constants": {k: str(v) for k, v in (constants or {}).items()},
                "starts": {k: str(v) for k, v in (starts or {}).items()},
                "ui": {"showLabel": True, "color": None},
            }
        )
        return key

    def ref(self, key, name, ref, x, y, **kw) -> str:
        return self.node(key, name, {"ref": ref}, x, y, **kw)

    def junction(self, key, name, x, y) -> str:
        return self.node(key, name, {"junction": "1"}, x, y)

    def connect(self, kind, a, b, route=None) -> None:
        def end(pair):
            node, port = pair
            return {"node": node} if port is None else {"node": node, "port": port}

        self.connections.append(
            {
                "id": f"{kind[0]}{len(self.connections) + 1:03d}",
                "kind": kind,
                "from": end(a),
                "to": end(b),
                "route": [{"x": px, "y": py} for px, py in (route or [])],
                "label": None,
            }
        )

    def document(self) -> dict:
        return {
            "nodes": self.nodes,
            "connections": self.connections,
            "subsystemPorts": [],
            "annotations": [],
        }


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


def rotation_matrix(q) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
S = math.sqrt(0.5)
# frame of the first pendulum joint in the arm frame: local z = the arm axis, local x = world z
# (upright), i.e. the rotation by 180 deg about (1, 0, 1)/sqrt(2)
RJF = ((0.0, S, 0.0, S), (0.0, 0.0, 0.0))


def geometry(plant: tl.Plant):
    """LN_i (joint frames), LC_i (COM frames), masses, principal inertias."""
    n = plant.n_links
    ln = [IDENTITY, (RJF[0], (plant.arm_l, 0.0, 0.0))]
    for k in range(1, n):
        ln.append((IDENTITY[0], (plant.lengths[k - 1], 0.0, 0.0)))
    lc = [((1.0, 0.0, 0.0, 0.0), (plant.arm_l / 2, 0.0, 0.0))]
    for k in range(n):
        lc.append(((1.0, 0.0, 0.0, 0.0), (plant.lengths[k] / 2, 0.0, 0.0)))
    mass = [plant.arm_m, *plant.masses]
    return ln, lc, mass, plant.body_j


def static_deflections(ln, lc, mass, q0, k):
    """Held-direction deflections (dth_xy, dl) at rest in the pose `q0` (see robot-arm-3d)."""
    child = IDENTITY
    joints, bodies = [], []
    for i in range(len(ln)):
        joint_frame = pose_mul(child, ln[i])
        rz = ((math.cos(q0[i] / 2), 0.0, 0.0, math.sin(q0[i] / 2)), (0.0, 0.0, 0.0))
        child = pose_mul(joint_frame, rz)
        joints.append((np.array(joint_frame[1]), rotation_matrix(child[0])))
        bodies.append(np.array(pose_mul(child, lc[i])[1]))
    result = []
    for i in range(len(ln)):
        origin, r_child = joints[i]
        force = np.zeros(3)
        moment = np.zeros(3)
        for j in range(i, len(ln)):
            weight = np.array([0.0, 0.0, -mass[j] * tl.G])
            force += weight
            moment += np.cross(bodies[j] - origin, weight)
        result.append((list((r_child.T @ moment / k)[:2]), list(r_child.T @ force / k)))
    return result


# ------------------------------------------------------------------ the controller block


def controller_source(plant: tl.Plant, dz: dict) -> str:
    nt = len(dz["tab_u"])
    table = mat(np.hstack([dz["tab_x"], np.array(dz["tab_u"])[:, None], dz["tab_k"]]))
    n = plant.nq
    nx = plant.nx
    cols = 2 * nx + 1
    q = [f"q{i + 1}" for i in range(n)]
    w = [f"w{i + 1}" for i in range(n)]
    x = q + w
    lines = []
    add = lines.append
    add("@block RotaryCtrl begin")
    add("    # 1 kHz firmware of the rotary pendulum (generated by design/build_model.py from design.json).")
    add("    #")
    add("    #   phase 0  t < t_on            motor voltage 0 (hanging, at rest)")
    add("    #   phase 1  swing-up            u = u*(t) - K(t) (x - x*(t)),  the TVLQR table `Tab` (rows every dt_tab)")
    add("    #   phase 2  balance (latched)   u = -Klqr x,  the infinite-horizon LQR at the upright")
    add("    #")
    add("    # x = [q1 .. q_n, w1 .. w_n]: the joint coordinates and rates of the bond graph (arm angle, first link")
    add("    # from upright, then every link relative to the one below). A table row is")
    add("    # [x*_1 .. x*_2n, u*, K_1 .. K_2n]; the row is picked by linear interpolation (hat functions) at")
    add("    # (tm - t_on)/dt_tab. The switch to phase 2 happens once, when tm - t_on >= t_s and the LQR")
    add("    # cost-to-go V = x^T Pc x is below catch_tol; the voltage is clamped to +-umax. The sampling")
    add("    # (zero-order hold) breaks the algebraic loop through the plant.")
    add(f"    @constants NT::Int = {nt}")
    add("    @inputs begin")
    for name in x:
        add(f"        {name}::Real")
    add("        tm::Real")
    add("    end")
    add("    @outputs begin")
    add('        u::Real = 0.0, [unit = "V"]')
    add("        phase::Real = 0.0")
    add("        vcost::Real = 0.0")
    add("    end")
    add("    @parameters begin")
    add(f"        Tab::Mat{{NT,{cols}}} = {table}, [description = \"TVLQR table: x*, u*, K per row\"]")
    add(f"        Klqr::Vec{{{nx}}} = {vec(dz['k_lqr'])}, [description = \"Infinite-horizon LQR gain\"]")
    add(f"        Pc::Mat{{{nx},{nx}}} = {mat(dz['p_lqr'])}, [description = \"LQR cost-to-go matrix of the catch rule\"]")
    add('        t_on::Real = 1.0, [unit = "s", description = "Start of the swing-up"]')
    add('        t_s::Real = 4.0, [unit = "s", min = 0, description = "Swing-up duration of the trajectory"]')
    add('        dt_tab::Real = 0.01, [unit = "s", min = 0, description = "Row spacing of the table"]')
    add('        catch_tol::Real = 1.0, [min = 0, description = "Catch threshold of the cost-to-go x^T Pc x"]')
    add('        umax::Real = 15.0, [unit = "V", min = 0, description = "Amplifier voltage limit"]')
    add("    end")
    add("    @variables latched::Real = 0.0, [description = \"1 once the balance controller has taken over\"]")
    add("    @discrete Ts = 1e-3 begin")
    add("        tau = tm - t_on")
    add("        s = clamp(tau / dt_tab, 0.0, NT - 1.0) + 1.0")
    for c in range(cols):
        add(f"        c{c + 1} = 0.0")
    add("        for k in 1:NT")
    add("            wk = max(0.0, 1.0 - abs(s - k))")
    for c in range(cols):
        add(f"            c{c + 1} = c{c + 1} + wk * Tab[k, {c + 1}]")
    add("        end")
    terms_tv = " + ".join(f"c{nx + 2 + i} * ({x[i]} - c{i + 1})" for i in range(nx))
    terms_l = " + ".join(f"Klqr[{i + 1}] * {x[i]}" for i in range(nx))
    norm = " + ".join(
        f"Pc[{i + 1}, {i + 1}] * {x[i]} * {x[i]}" if i == j else f"2.0 * Pc[{i + 1}, {j + 1}] * {x[i]} * {x[j]}"
        for i in range(nx)
        for j in range(i, nx)
    )
    add(f"        utv = c{nx + 1} - ({terms_tv})")
    add(f"        ulq = -({terms_l})")
    add(f"        en = {norm}")
    add("        lat = ifelse(latched > 0.5 || (tau >= t_s && en < catch_tol), 1.0, 0.0)")
    add("        latched = lat")
    add("        u = clamp(ifelse(tm < t_on, 0.0, ifelse(lat > 0.5, ulq, utv)), -umax, umax)")
    add("        phase = ifelse(tm < t_on, 0.0, ifelse(lat > 0.5, 2.0, 1.0))")
    add("        vcost = en")
    add("    end")
    add("end")
    return "\n".join(lines) + "\n"


def angles_source(plant: tl.Plant) -> str:
    n = plant.n_links
    lines = ["@block LinkAngles begin"]
    lines.append("    # Absolute link angles from upright, phi_k = q_1 + ... + q_k (the joint angles are relative),")
    lines.append("    # and the largest absolute deviation of any link from upright. For plots and checks.")
    lines.append("    @inputs begin")
    for k in range(n):
        lines.append(f'        q{k + 1}::Real, [unit = "rad"]')
    lines.append("    end")
    lines.append("    @outputs begin")
    for k in range(n):
        lines.append(f'        phi{k + 1}::Real, [unit = "rad"]')
    lines.append('        dev::Real, [unit = "rad"]')
    lines.append("    end")
    lines.append("    @equations begin")
    for k in range(n):
        lines.append(f"        phi{k + 1} ~ " + " + ".join(f"q{j + 1}" for j in range(k + 1)))
    lines.append("        dev ~ max(" + ", ".join(f"abs(phi{k + 1})" for k in range(n)) + ")")
    lines.append("    end")
    lines.append("end")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ the model


def settings(t_end: float, points: int, reltol=1e-6, abstol=1e-8) -> dict:
    return {
        "t_start": 0.0,
        "t_end": t_end,
        "solver": "Rodas5P",
        "reltol": reltol,
        "abstol": abstol,
        "max_step": None,
        "output": {"mode": "points", "points": points},
        "event_limit": 100000,
    }


def build_model(plant: tl.Plant, dz: dict, name: str, free: bool) -> dict:
    n = plant.n_links
    nq = plant.nq
    ln, lc, mass, inertia = geometry(plant)
    k_joint = dz["k_joint"]
    dr = dz["drive"]
    q_start = list(dz["free_start"] if free else [0.0, math.pi] + [0.0] * (n - 1))
    deflections = static_deflections(ln, lc, mass, q_start, k_joint)
    # reference inertia of what hangs beyond each joint for the held-rotation damping
    distal = [sum(mass[j:]) for j in range(nq)]
    jref = [sum(m * (plant.arm_l + sum(plant.lengths)) ** 2 + max(jj) for m, jj in zip(mass[j:], inertia[j:], strict=True)) for j in range(nq)]

    d = Diagram()
    bx = [380 + 460 * i for i in range(nq)]
    ry = [320 + 220 * i for i in range(nq)]
    band = 340 + 220 * nq + 100
    d.ref("world", "World", "stdlib:multibond/GroundSpatial", bx[0] - 140, ry[0])
    d.ref("mount", "Mount", "stdlib:multibond/FixedTransform3DNeutral", bx[0], ry[0], params=pose_params(IDENTITY))
    d.ref("mpose", "MountPose", "stdlib:spatial/LocalPose3D", bx[0] - 140, band, params=pose_params(IDENTITY))
    d.connect("bond", ("world", "p"), ("mount", "b"))

    prev_world = "mpose"
    for i in range(nq):
        k = i + 1
        x0, y0 = bx[i], ry[i]
        d.ref(
            f"j{k}", f"J{k}", "stdlib:spatial/Revolute3D", x0 + 120, y0,
            params={
                "kt": fmt(k_joint), "kr": fmt(k_joint),
                "bt": fmt(1.4 * math.sqrt(k_joint * distal[i])),
                "br": fmt(1.4 * math.sqrt(k_joint * jref[i])),
                "q0": fmt(q_start[i]),
            },
            starts={"dth": vec(deflections[i][0]), "dl": vec(deflections[i][1])},
        )  # fmt: skip
        d.ref(f"link{k}", f"Link{k}", "stdlib:multibond/FixedTransform3DNeutral", x0 + 240, y0, params=pose_params(lc[i]))
        d.junction(f"bj{k}", f"BJ{k}", x0 + 360, y0 + 10)
        body = "Arm" if i == 0 else f"Rod{i}"
        d.ref(
            f"b{k}", body, "stdlib:spatial/RigidBody3D", x0 + 350, y0 + 100,
            params={"m": fmt(mass[i]), "J": vec(inertia[i]), "g0": fmt(tl.G)},
        )  # fmt: skip
        if i == 0:
            d.connect("bond", ("mount", "a"), ("j1", "parent"))
        else:
            t_pose = pose_mul(pose_inv(ln[i]), lc[i - 1])
            d.ref(f"t{k}", f"T{k}", "stdlib:multibond/FixedTransform3DNeutral", x0, y0, params=pose_params(t_pose))
            d.connect("bond", (f"t{k}", "a"), (f"j{k}", "parent"))
            d.connect("bond", (f"t{k}", "b"), (f"bj{k - 1}", None))
        d.connect("bond", (f"j{k}", "child"), (f"link{k}", "a"))
        d.connect("bond", (f"link{k}", "b"), (f"bj{k}", None))
        d.connect("bond", (f"b{k}", "p"), (f"bj{k}", None))
        d.ref(f"ln{k}", f"LN{k}", "stdlib:spatial/LocalPose3D", x0, band + 100, params=pose_params(ln[i]))
        d.ref(f"ca{k}", f"CA{k}", "stdlib:multibond/ComposePose3D", x0, band)
        d.ref(f"w{k}", f"W{k}", "stdlib:multibond/ComposePose3D", x0 + 120, band)
        d.ref(f"lc{k}", f"LC{k}", "stdlib:spatial/LocalPose3D", x0 + 350, band + 240, params=pose_params(lc[i]))
        d.ref(f"pb{k}", f"P{k}", "stdlib:multibond/ComposePose3D", x0 + 350, band + 120)
        d.connect("signal", (prev_world, "g"), (f"ca{k}", "gp"))
        d.connect("signal", (f"ln{k}", "g"), (f"ca{k}", "gl"))
        d.connect("signal", (f"ca{k}", "g"), (f"w{k}", "gp"))
        d.connect("signal", (f"j{k}", "pose"), (f"w{k}", "gl"))
        d.connect("signal", (f"w{k}", "g"), (f"pb{k}", "gp"))
        d.connect("signal", (f"lc{k}", "g"), (f"pb{k}", "gl"))
        d.connect("signal", (f"pb{k}", "g"), (f"b{k}", "g"))
        prev_world = f"w{k}"

    # the pendulum joints are passive: bearing friction only (a viscous damper on the drive port)
    for i in range(1, nq):
        k = i + 1
        d.ref(f"fric{k}", f"Bearing{k}", "stdlib:rotation/RotationalDamper", bx[i] + 120, ry[i] - 110, params={"d": fmt(dz["jfric"])})
        d.ref(f"fix{k}", f"Frame{k}", "stdlib:rotation/FixedShaft", bx[i] + 280, ry[i] - 110)
        d.connect("wire", (f"j{k}", "drive"), (f"fric{k}", "a"))
        d.connect("wire", (f"fric{k}", "b"), (f"fix{k}", "a"))

    # drive: Motor (ElectricDrive, voltage input) - Shaft (ElasticShaft) - Gear - J1.drive
    d.ref(
        "motor", "Motor", "stdlib:drives/ElectricDrive", bx[0] - 140, ry[0] + 330,
        params={"R_w": fmt(dr["rm"]), "L": fmt(dr["lm"]), "k_t": fmt(dr["kt"]), "J_m": fmt(dr["jm"]), "b_m": fmt(dr["beq"] / dr["ng"] ** 2)},
    )  # fmt: skip
    d.ref(
        "shaft", "Shaft", "stdlib:rotation/ElasticShaft", bx[0] + 40, ry[0] + 330,
        params={"k": fmt(dz["k_shaft"] / dr["ng"] ** 2), "d": fmt(dz["d_shaft"] / dr["ng"] ** 2)},
    )  # fmt: skip
    d.ref("gear", "Gear", "stdlib:rotation/IdealGear", bx[0] + 200, ry[0] + 330, params={"n": fmt(dr["ng"])})
    d.connect("wire", ("motor", "shaft"), ("shaft", "a"))
    d.connect("wire", ("shaft", "b"), ("gear", "a"))
    d.connect("wire", ("gear", "b"), ("j1", "drive"))

    # firmware, clock and measurements
    params = {
        "t_on": fmt(1.0e6 if free else dz["t_on"]),
        "t_s": fmt(dz["t_s"]),
        "dt_tab": fmt(dz["dt_tab"]),
        "catch_tol": fmt(dz["catch_tol"]),
        "umax": fmt(dz["vmax"]),
    }
    d.ref("ctrl", "Ctrl", "project:RotaryCtrl", bx[0] - 140, 60, params=params, constants={"NT": str(len(dz["tab_u"]))})
    d.ref("clock", "Clock", "stdlib:sources/Time", bx[0] - 300, 60)
    d.connect("signal", ("clock", "y"), ("ctrl", "tm"))
    d.connect("signal", ("ctrl", "u"), ("motor", "u"))
    for i in range(nq):
        k = i + 1
        d.connect("signal", (f"j{k}", "qout"), ("ctrl", f"q{k}"))
        d.connect("signal", (f"j{k}", "qdout"), ("ctrl", f"w{k}"))
    d.ref("angles", "Angles", "project:LinkAngles", bx[-1] + 360, 60)
    for k in range(1, n + 1):
        d.connect("signal", (f"j{k + 1}", "qout"), ("angles", f"q{k}"))

    # the disturbance: a force pulse on the tip of the last link, perpendicular to the rod in the pendulum plane
    tip = pose_params(((1.0, 0.0, 0.0, 0.0), (-plant.lengths[-1] / 2, 0.0, 0.0)))
    d.ref("tipt", "TipPoint", "stdlib:multibond/FixedTransform3DNeutral", bx[-1] + 360, ry[-1] + 230, params=tip)
    d.ref("dist", "Dist", "stdlib:multibond/ExternalWrenchSpatial", bx[-1] + 520, ry[-1] + 230)
    d.ref(
        "pulse", "DistPulse", "stdlib:sources/Pulse", bx[-1] + 520, ry[-1] + 120,
        params={
            "amplitude": fmt(0.0 if free else dz["dist_force"]),
            "period": "1000.0",
            "duty": fmt(dz["dist_duration"] / 1000.0),
            "t_start": fmt(dz["t_dist"]),
        },
    )  # fmt: skip
    d.ref("zero", "Zero", "stdlib:sources/Constant", bx[-1] + 360, ry[-1] + 120, params={"value": "0.0"})
    d.connect("bond", ("dist", "p"), ("tipt", "a"))
    d.connect("bond", ("tipt", "b"), (f"bj{nq}", None))
    for port in ("tx", "ty", "tz", "fx", "fz"):
        d.connect("signal", ("zero", "y"), ("dist", port))
    d.connect("signal", ("pulse", "y"), ("dist", "fy"))

    names = [f"J{i + 1}/qout" for i in range(nq)]
    joint_names = ["arm"] + [f"link{k}" for k in range(1, n + 1)]
    t_end = dz["t_free"] if free else dz["t_end"]
    plots = [
        {"id": "p1", "title": "Link angles from upright", "signals": [f"Angles/phi{k}" for k in range(1, n + 1)]},
        {"id": "p2", "title": "Arm angle", "signals": ["J1/qout"]},
        {"id": "p3", "title": "Motor voltage", "signals": ["Ctrl/u"]},
        {"id": "p4", "title": "Controller phase", "signals": ["Ctrl/phase"]},
        {"id": "p5", "title": "Joint rates", "signals": [f"J{i + 1}/qdout" for i in range(nq)]},
    ]
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": dz["comment_free" if free else "comment"],
        "diagram": d.document(),
        "settings": settings(t_end, int(t_end * 1000) + 1, reltol=1e-9, abstol=1e-10) if free else settings(t_end, int(t_end * 250) + 1),
        "plots": plots,
        "scene": {"file": f"scenes/{dz['example']}.sdf"},
        "bindings": [
            {"target": f"joint:{jn}", "property": "position", "signal": sg}
            for jn, sg in zip(joint_names, names, strict=True)
        ],
    }


# ------------------------------------------------------------------ scene


def scene_sdf(plant: tl.Plant, example: str) -> str:
    n = plant.n_links
    la = plant.arm_l
    colors = ["0.35 0.7 0.45 1", "0.85 0.35 0.3 1", "0.95 0.75 0.2 1"]
    out = [
        '<?xml version="1.0"?>',
        "<!--",
        f"  {example} (X5.13): a Quanser-style rotary arm with a chain of {n} pendulum links.",
        "",
        "  Z-up, metres. The scene is drawn at q = 0: the arm along +X from the vertical axis, the links",
        "  standing upright (+Z) on its tip. The arm turns about +Z (joint arm, the model's J1/qout). The",
        "  links swing about the arm axis, joint axis +X (J2/qout ... : a positive angle tilts the chain",
        "  towards -Y, relative to the link below). The model's hanging start is q2 = pi.",
        "-->",
        '<sdf version="1.9">',
        f'  <model name="{example.replace("-", "_")}">',
        '    <link name="base">',
        "      <pose>0 0 0 0 0 0</pose>",
        '      <visual name="servo_housing">',
        "        <pose>0 0 -0.06 0 0 0</pose>",
        "        <geometry><box><size>0.16 0.12 0.12</size></box></geometry>",
        "        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>",
        "      </visual>",
        '      <visual name="base_plate">',
        "        <pose>0 0 -0.125 0 0 0</pose>",
        "        <geometry><box><size>0.34 0.24 0.01</size></box></geometry>",
        "        <material><diffuse>0.55 0.57 0.6 1</diffuse></material>",
        "      </visual>",
        "    </link>",
        '    <link name="arm_bar">',
        "      <pose>0 0 0 0 0 0</pose>",
        '      <visual name="hub">',
        "        <geometry><cylinder><radius>0.03</radius><length>0.03</length></cylinder></geometry>",
        "        <material><diffuse>0.25 0.5 0.85 1</diffuse></material>",
        "      </visual>",
        '      <visual name="arm_bar">',
        f"        <pose>{la / 2} 0 0 0 1.5707963 0</pose>",
        f"        <geometry><cylinder><radius>0.008</radius><length>{la}</length></cylinder></geometry>",
        "        <material><diffuse>0.25 0.5 0.85 1</diffuse></material>",
        "      </visual>",
        '      <visual name="tip_block">',
        f"        <pose>{la} 0 0 0 0 0</pose>",
        "        <geometry><box><size>0.03 0.03 0.03</size></box></geometry>",
        "        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>",
        "      </visual>",
        "    </link>",
    ]
    for k in range(n):
        l = plant.lengths[k]
        z0 = sum(plant.lengths[:k])
        out += [
            f'    <link name="rod{k + 1}">',
            f"      <pose>{la} 0 {z0} 0 0 0</pose>",
            f'      <visual name="rod{k + 1}">',
            f"        <pose>0 0 {l / 2} 0 0 0</pose>",
            f"        <geometry><cylinder><radius>{0.006 - 0.001 * k}</radius><length>{l}</length></cylinder></geometry>",
            f"        <material><diffuse>{colors[k % 3]}</diffuse></material>",
            "      </visual>",
            f'      <visual name="joint{k + 1}">',
            "        <pose>0 0 0 0 1.5707963 0</pose>",
            "        <geometry><cylinder><radius>0.012</radius><length>0.03</length></cylinder></geometry>",
            "        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>",
            "      </visual>",
        ]
        if k == n - 1:
            out += [
                '      <visual name="tip">',
                f"        <pose>0 0 {l} 0 0 0</pose>",
                "        <geometry><sphere><radius>0.015</radius></sphere></geometry>",
                "        <material><diffuse>0.9 0.55 0.1 1</diffuse></material>",
                "      </visual>",
            ]
        out.append("    </link>")
    out += [
        '    <joint name="arm" type="revolute">',
        "      <parent>base</parent>",
        "      <child>arm_bar</child>",
        "      <axis><xyz>0 0 1</xyz><limit><lower>-6.2831853</lower><upper>6.2831853</upper></limit></axis>",
        "    </joint>",
    ]
    for k in range(n):
        parent = "arm_bar" if k == 0 else f"rod{k}"
        out += [
            f'    <joint name="link{k + 1}" type="revolute">',
            f"      <parent>{parent}</parent>",
            f"      <child>rod{k + 1}</child>",
            "      <axis><xyz>1 0 0</xyz><limit><lower>-9.4247780</lower><upper>9.4247780</upper></limit></axis>",
            "    </joint>",
        ]
    out += ["  </model>", "</sdf>", ""]
    return "\n".join(out)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")
