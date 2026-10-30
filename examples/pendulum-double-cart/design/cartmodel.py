"""Bond-graph model documents of the X5.12 cart pendulums, generated from a `cartpend.Plant`.

The plant is a planar multibond bond graph (`stdlib:planar/*`, `stdlib:multibond/*`):

    Ground -- Rail (Prismatic2D) -- CartJ(1) -- Cart (RigidBody2D)
                  |                    `-- Joint1 -- Link1 -- N1(1) -- Body1 (RigidBody2D)
              drive (Translation)                  `-- Joint2 -- Link2 -- N2(1) -- Body2 ... (Push at the tip)
    Motor (ElectricDrive) -- Gear -- Pulley (RackAndPinion) -- Belt (SpringDamper) -- Rail.drive

Joints are the compliant revolute joints with a very stiff pivot (kt = 1e8 N/m, the DEC-MB-2 route to a
rigid revolute: the trajectory error is O(1/kt), measured in the design-vs-bond-graph check) and a
viscous friction `b`. Every pendulum joint's drive port closes on a zero-effort source (passive).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from cartpend import G0, Plant


def _num(x) -> str:
    return repr(float(x))


class Model:
    def __init__(self, name: str):
        self.name = name
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.ids = {"n": 0, "b": 0, "s": 0, "w": 0}

    def node(self, name, ref, x, y, params=None, starts=None, constants=None):
        self.ids["n"] += 1
        nid = f"n{self.ids['n']:03d}"
        blk = {"junction": ref} if ref in ("0", "1") else {"ref": ref}
        self.nodes.append({
            "id": nid, "name": name, "block": blk, "position": {"x": x, "y": y},
            "rotation": 0, "flipX": False,
            "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        return nid

    def _conn(self, kind, a, ap, b, bp):
        self.ids[kind[0]] += 1
        fr = {"node": a} if ap is None else {"node": a, "port": ap}
        to = {"node": b} if bp is None else {"node": b, "port": bp}
        self.conns.append({"id": f"{kind[0]}{self.ids[kind[0]]:03d}", "kind": kind, "from": fr, "to": to})

    def bond(self, a, ap, b, bp=None):
        self._conn("bond", a, ap, b, bp)

    def wire(self, a, ap, b, bp):
        self._conn("wire", a, ap, b, bp)

    def sig(self, a, ap, b, bp):
        self._conn("signal", a, ap, b, bp)


def static_deflection(P: Plant, th_abs: list[float]) -> tuple[list, float]:
    """Pivot spring deflections of the rest pose: joint `d` (child frame) and the rail `d` (m)."""
    ds = []
    for j in range(P.n):
        below = sum(P.m[j:])
        big = th_abs[j] + math.pi / 2          # world angle of the child frame
        f = below * G0 / P.kt_pivot
        ds.append([-math.sin(big) * f, -math.cos(big) * f])
    d_rail = -(P.m_cart + sum(P.m)) * G0 / P.kd_rail
    return ds, d_rail


def build(P: Plant, block: str, *, free: bool = False, th0=None, x0: float = 0.0, t_end: float,
          points: int, push: dict | None = None, ctrl_params: dict | None = None,
          scene: str = "", title: str = "") -> dict:
    """The model document. `free` = open loop from the pose `th0` (absolute angles), `x0`."""
    n = P.n
    M = Model(title or P.name)
    th = list(th0) if th0 is not None else [-math.pi] * n
    ds, d_rail = static_deflection(P, th)

    X = lambda col: 80 + 190 * col  # noqa: E731
    ground = M.node("Ground", "stdlib:multibond/GroundPlanar", X(0), 360)
    rail = M.node("Rail", "stdlib:planar/Prismatic2D", X(1), 360,
                  params={"phi": "0.0", "kr": _num(P.kr_rail), "br": _num(P.br_rail),
                          "kd": _num(P.kd_rail), "bd": _num(P.bd_rail), "q0": _num(x0)},
                  starts={"d": _num(d_rail)})
    cartj = M.node("CartJ", "1", X(2), 360)
    cart = M.node("Cart", "stdlib:planar/RigidBody2D", X(2), 500,
                  params={"m": _num(P.m_cart), "J": _num(P.J_cart), "g0": _num(G0)})
    M.bond(ground, "p", rail, "parent")
    M.bond(rail, "child", cartj)
    M.bond(cart, "p", cartj)

    prev_node, prev_pose = cartj, (rail, "pose")
    joints, bodies, nodes_j = [], [], []
    for j in range(n):
        col = 3 + 2 * j
        q0 = th[0] + math.pi / 2 if j == 0 else th[j] - th[j - 1]
        rx = 0.0 if j == 0 else P.L[j - 1] - P.c[j - 1]
        jn = M.node(f"Joint{j + 1}", "stdlib:planar/Revolute2DCompliant", X(col), 360,
                    params={"rx": _num(rx), "ry": "0.0", "kt": _num(P.kt_pivot), "bt": _num(P.bt_pivot),
                            "k": "0.0", "b": _num(P.b[j]), "q0": _num(q0), "qrest": "0.0"},
                    starts={"d": "[" + ", ".join(_num(v) for v in ds[j]) + "]"})
        ln = M.node(f"Link{j + 1}", "stdlib:planar/FixedJoint2D", X(col) + 110, 360,
                    params={"x": _num(P.c[j]), "y": "0.0", "theta": "0.0"})
        nj = M.node(f"N{j + 1}", "1", X(col) + 220, 360)
        bd = M.node(f"Body{j + 1}", "stdlib:planar/RigidBody2D", X(col) + 220, 500,
                    params={"m": _num(P.m[j]), "J": _num(P.J[j]), "g0": _num(G0)})
        dr = M.node(f"Passive{j + 1}", "stdlib:bondgraph/Se", X(col), 220, params={"e": "0.0"})
        M.bond(jn, "parent", prev_node)
        M.bond(jn, "child", ln, "parent")
        M.bond(ln, "child", nj)
        M.bond(bd, "p", nj)
        M.bond(dr, "p", jn, "drive")
        # composed poses (the pose chain mirrors the power chain)
        cm = M.node(f"CoM{j + 1}", "stdlib:planar/LocalPose2D", X(col) + 110, 640, params={"x": _num(P.c[j])})
        pj = M.node(f"PoseJ{j + 1}", "stdlib:multibond/ComposePose2D", X(col), 640)
        pb = M.node(f"PoseB{j + 1}", "stdlib:multibond/ComposePose2D", X(col) + 220, 640)
        M.sig(prev_pose[0], prev_pose[1], pj, "gp")
        M.sig(jn, "pose", pj, "gl")
        M.sig(pj, "g", pb, "gp")
        M.sig(cm, "g", pb, "gl")
        M.sig(pb, "g", bd, "g")
        prev_node, prev_pose = nj, (pb, "g")
        joints.append(jn)
        bodies.append(bd)
        nodes_j.append(nj)
    M.sig(rail, "pose", cart, "g")

    # disturbance: a force pulse perpendicular to the tip link (and its moment about the COM)
    px = X(3 + 2 * n)
    push_blk = M.node("Push", "stdlib:multibond/ExternalWrenchPlanar", px, 360)
    M.bond(push_blk, "p", nodes_j[-1])
    pa = push or {"amplitude": 0.0, "t_start": 1.0e6, "duration": 0.04}
    pulse = M.node("PushPulse", "stdlib:sources/Pulse", px, 220,
                   params={"amplitude": _num(pa["amplitude"]), "period": "1000.0",
                           "duty": _num(pa["duration"] / 1000.0), "t_start": _num(pa["t_start"])})
    lever = M.node("PushLever", "stdlib:continuous/Gain", px + 110, 220, params={"k": _num(P.L[-1] - P.c[-1])})
    zero = M.node("PushZero", "stdlib:sources/Constant", px + 110, 120, params={"value": "0.0"})
    M.sig(pulse, "y", push_blk, "wy")
    M.sig(pulse, "y", lever, "u")
    M.sig(lever, "y", push_blk, "wr")
    M.sig(zero, "y", push_blk, "wx")

    # drive train: motor -> gearbox -> pulley/belt -> cart
    motor = M.node("Motor", "stdlib:drives/ElectricDrive", X(1), 80,
                   params={"R_w": _num(P.R_m), "L": _num(P.L_m), "k_t": _num(P.k_t), "J_m": _num(P.J_m),
                           "b_m": _num(P.b_m)})
    gear = M.node("Gear", "stdlib:drives/Gearbox", X(2), 80, params={"N": _num(P.N)})
    pulley = M.node("Pulley", "stdlib:converters/RackAndPinion", X(3) - 20, 80, params={"r": _num(P.r)})
    belt = M.node("Belt", "stdlib:translation/SpringDamper", X(4) - 20, 80,
                  params={"k": _num(P.k_belt), "d": _num(P.d_belt)}, starts={"x": "0.0"})
    M.wire(motor, "shaft", gear, "a")
    M.wire(gear, "b", pulley, "a")
    M.wire(pulley, "b", belt, "a")
    M.wire(belt, "b", rail, "drive")

    # firmware
    clock = M.node("Clock", "stdlib:sources/Time", X(0), 220)
    cp = {"t_on": "1.0e9"} if free else {}
    cp.update(ctrl_params or {})
    traj = M.node("Traj", f"project:{block}Traj", X(0), 300, params=({"t_on": cp["t_on"]} if free else {}))
    ctrl = M.node("Ctrl", f"project:{block}Ctrl", X(0), 80, params=cp)
    M.sig(clock, "y", traj, "tm")
    M.sig(traj, "ff", ctrl, "ff")
    M.sig(traj, "xs", ctrl, "xs")
    M.sig(traj, "Ks", ctrl, "Ks")
    M.sig(clock, "y", ctrl, "tm")
    M.sig(rail, "qout", ctrl, "x")
    M.sig(rail, "qdout", ctrl, "v")
    for j, jn in enumerate(joints):
        M.sig(jn, "qout", ctrl, f"q{j + 1}")
        M.sig(jn, "qdout", ctrl, f"wq{j + 1}")
    M.sig(ctrl, "u", motor, "u")

    names = ["Ctrl/th%d" % (i + 1) for i in range(n)]
    plots = [
        {"id": "p_angles", "title": "Link angles from upright (rad)", "signals": names},
        {"id": "p_cart", "title": "Cart position (m)", "signals": ["Rail/qout"]},
        {"id": "p_volt", "title": "Motor voltage (V) and phase", "signals": ["Ctrl/u", "Ctrl/phase"]},
        {"id": "p_cur", "title": "Motor current (A)", "signals": ["Motor/isense/y"]},
    ]
    bindings = [{"target": "joint:rail", "property": "position", "signal": "Rail/qout"}]
    for j in range(n):
        bindings.append({"target": f"joint:hinge{j + 1}", "property": "position", "signal": f"Joint{j + 1}/qout"})
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": title or P.name,
        "diagram": {"nodes": M.nodes, "connections": M.conns},
        "settings": {"t_start": 0.0, "t_end": t_end, "solver": "Rodas5P", "reltol": 1e-8,
                     "abstol": 1e-10, "max_step": None,
                     "output": {"mode": "points", "points": points}, "event_limit": 10000},
        "plots": plots, "scene": {"file": scene}, "bindings": bindings,
    }


def write(path: Path, doc: dict) -> None:
    with open(path, "w", newline="\n") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
