"""Bond-graph model documents of `quad-pendulum`, generated from the design files.

Cart (planar multibond, `stdlib:planar/*`, `stdlib:multibond/*`)::

    Ground -- Rail (Prismatic2D) -- CartJ(1) -- Cart (RigidBody2D)
                 |drive               `-- Joint1 -- Link1 -- N1(1) -- Body1 (RigidBody2D)
                 |                                   `-- Joint2 -- Link2 -- N2(1) -- Body2 ... Body4 -- Push
       Force (ForceSource) + RailFriction (Damper) + EndStops (HardStop), each against a Fixed frame

Rotary (spatial multibond)::

    World -- Mount -- J1 (Revolute3D, world z) -- ArmLink -- BJ1 -- Arm (RigidBody3D)
                      |drive: Motor (TorqueSource) + ArmBearing (RotationalDamper); hub inertia in Arm
                      T2 -- J2 (Revolute3D, arm axis) -- Link1 -- BJ2 -- Rod1 ... (one joint and one body per link)

The pendulum joints are passive (viscous friction only). The firmware block reads the joint encoders,
the monitor block reads the bodies' twists and poses.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

G0 = 9.81
DEG = math.pi / 180


def num(x) -> str:
    return repr(float(x))


class Diagram:
    def __init__(self):
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.k = {"n": 0, "b": 0, "w": 0, "s": 0}

    def node(self, name, ref, x, y, params=None, starts=None, constants=None):
        self.k["n"] += 1
        nid = f"n{self.k['n']:03d}"
        blk = {"junction": ref} if ref in ("0", "1") else {"ref": ref}
        self.nodes.append({
            "id": nid, "name": name, "block": blk, "position": {"x": x, "y": y}, "rotation": 0, "flipX": False,
            "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        return nid

    def _conn(self, kind, a, ap, b, bp):
        self.k[kind[0]] += 1
        fr = {"node": a} if ap is None else {"node": a, "port": ap}
        to = {"node": b} if bp is None else {"node": b, "port": bp}
        self.conns.append({"id": f"{kind[0]}{self.k[kind[0]]:03d}", "kind": kind, "from": fr, "to": to})

    def bond(self, a, ap, b, bp=None):
        self._conn("bond", a, ap, b, bp)

    def wire(self, a, ap, b, bp):
        self._conn("wire", a, ap, b, bp)

    def sig(self, a, ap, b, bp):
        self._conn("signal", a, ap, b, bp)

    def doc(self):
        return {"nodes": self.nodes, "connections": self.conns}


def ports(dz, two: bool) -> tuple:
    """Signals from the Traj block to the firmware: the combined ("v") or the separate ("x") feed-forward,
    and the controller choice when the firmware holds two controllers."""
    p = ("ff", "Ks") if dz.get("ff_form", "x") == "v" else ("ff", "xs", "Ks")
    return p + ("sel",) if two else p


def settings(t_end, points, reltol=1e-7, abstol=1e-9, solver="Rodas5P"):
    return {"t_start": 0.0, "t_end": t_end, "solver": solver, "reltol": reltol, "abstol": abstol, "max_step": None,
            "output": {"mode": "points", "points": points}, "event_limit": 100000}


def gpar(name, value, unit=None, description=None):
    return {"name": name, "value": value, "unit": unit, "description": description}


# ============================================================================ cart


def cart_static_deflection(dz, th_abs):
    """Pivot spring deflections of the rest pose (child frame) and the rail deflection."""
    ds = []
    m = dz["m_model"]
    for j in range(len(m)):
        below = sum(m[j:])
        big = th_abs[j] + math.pi / 2
        f = below * G0 / dz["kt_pivot"]
        ds.append([-math.sin(big) * f, -math.cos(big) * f])
    d_rail = -(dz["m_base"] + sum(m)) * G0 / dz["kd_rail"]
    return ds, d_rail


def build_cart(dz, *, name, mode, t_end, points, th0=None, x0=0.0, comment="", dashboard=None, parameters=None,
               push=None, reltol=1e-7, abstol=1e-9, two=True):
    """mode: "swingup", "balance" or "free" (controller off). th0: absolute start angles (rad, from upright).
    two: the firmware holds two controllers (Traj/controller, the travel limit lines)."""
    n = len(dz["L"])
    L, c = dz["L"], [l / 2 for l in dz["L"]]
    D = Diagram()
    th = list(th0) if th0 is not None else [-math.pi] * n
    ds, d_rail = cart_static_deflection(dz, th)
    use_globals = parameters is not None
    X = lambda col: 80 + 190 * col  # noqa: E731
    ground = D.node("Ground", "stdlib:multibond/GroundPlanar", X(0), 360)
    rail = D.node("Rail", "stdlib:planar/Prismatic2D", X(1), 360,
                  params={"phi": "0.0", "kr": num(dz["kr_rail"]), "br": num(dz["br_rail"]),
                          "kd": num(dz["kd_rail"]), "bd": num(dz["bd_rail"]), "q0": num(x0)},
                  starts={"d": num(d_rail)})
    cartj = D.node("CartJ", "1", X(2), 360)
    cart = D.node("Cart", "stdlib:planar/RigidBody2D", X(2), 500,
                  params={"m": num(dz["m_base"]), "J": num(dz["J_cart"]), "g0": num(G0)})
    D.bond(ground, "p", rail, "parent")
    D.bond(rail, "child", cartj)
    D.bond(cart, "p", cartj)
    D.sig(rail, "pose", cart, "g")
    prev_node, prev_pose = cartj, (rail, "pose")
    joints, bodies, nodes_j = [], [], []
    for j in range(n):
        col = 3 + 2 * j
        q0 = th[0] + math.pi / 2 if j == 0 else th[j] - th[j - 1]
        q0s = num(q0)
        if use_globals and mode == "balance":
            q0s = (f"1.5707963267948966 + th0_1*{DEG!r}" if j == 0 else f"(th0_{j + 1} - th0_{j})*{DEG!r}")
        rx = 0.0 if j == 0 else L[j - 1] - c[j - 1]
        jn = D.node(f"Joint{j + 1}", "stdlib:planar/Revolute2DCompliant", X(col), 360,
                    params={"rx": num(rx), "ry": "0.0", "kt": num(dz["kt_pivot"]), "bt": num(dz["bt_pivot"]),
                            "k": "0.0", "b": num(dz["b_joint"]), "q0": q0s, "qrest": "0.0"},
                    starts={"d": "[" + ", ".join(num(v) for v in ds[j]) + "]"})
        ln = D.node(f"Link{j + 1}", "stdlib:planar/FixedJoint2D", X(col) + 110, 360,
                    params={"x": num(c[j]), "y": "0.0", "theta": "0.0"})
        nj = D.node(f"N{j + 1}", "1", X(col) + 220, 360)
        mpar = num(dz["m_model"][j])
        jpar = num(dz["J_model"][j])
        if use_globals:
            mpar, jpar = f"m_scale*{mpar}", f"m_scale*{jpar}"
        bd = D.node(f"Body{j + 1}", "stdlib:planar/RigidBody2D", X(col) + 220, 500,
                    params={"m": mpar, "J": jpar, "g0": num(G0)})
        dr = D.node(f"Passive{j + 1}", "stdlib:bondgraph/Se", X(col), 220, params={"e": "0.0"})
        D.bond(jn, "parent", prev_node)
        D.bond(jn, "child", ln, "parent")
        D.bond(ln, "child", nj)
        D.bond(bd, "p", nj)
        D.bond(dr, "p", jn, "drive")
        cm = D.node(f"CoM{j + 1}", "stdlib:planar/LocalPose2D", X(col) + 110, 640, params={"x": num(c[j])})
        pj = D.node(f"PoseJ{j + 1}", "stdlib:multibond/ComposePose2D", X(col), 640)
        pb = D.node(f"PoseB{j + 1}", "stdlib:multibond/ComposePose2D", X(col) + 220, 640)
        D.sig(prev_pose[0], prev_pose[1], pj, "gp")
        D.sig(jn, "pose", pj, "gl")
        D.sig(pj, "g", pb, "gp")
        D.sig(cm, "g", pb, "gl")
        D.sig(pb, "g", bd, "g")
        prev_node, prev_pose = nj, (pb, "g")
        joints.append(jn)
        bodies.append((bd, pb))
        nodes_j.append(nj)

    # disturbance: a force pulse perpendicular to the top link at its tip
    px = X(3 + 2 * n)
    pushb = D.node("Push", "stdlib:multibond/ExternalWrenchPlanar", px, 360)
    D.bond(pushb, "p", nodes_j[-1])
    pa = push or {"amplitude": 0.0, "t_start": 1.0e6, "duration": 0.05}
    amp = "push_N" if use_globals and "push_N" in [p["name"] for p in parameters] else num(pa["amplitude"])
    pulse = D.node("PushPulse", "stdlib:sources/Pulse", px, 220,
                   params={"amplitude": amp, "period": "1000.0", "duty": num(pa["duration"] / 1000.0),
                           "t_start": num(pa["t_start"])})
    lever = D.node("PushLever", "stdlib:continuous/Gain", px + 110, 220, params={"k": num(L[-1] - c[-1])})
    zero = D.node("PushZero", "stdlib:sources/Constant", px + 110, 120, params={"value": "0.0"})
    D.sig(pulse, "y", pushb, "wy")
    D.sig(pulse, "y", lever, "u")
    D.sig(lever, "y", pushb, "wr")
    D.sig(zero, "y", pushb, "wx")

    # rail drive: ideal force actuator, viscous rail friction, soft end stops
    act = D.node("Force", "stdlib:translation/ForceSource", X(1) - 60, 120, params={"F": num(dz.get("force_sign", 1.0))})
    fix1 = D.node("Frame1", "stdlib:translation/Fixed", X(1) - 60, 20)
    fric = D.node("RailFriction", "stdlib:translation/Damper", X(2), 120, params={"d": num(dz["b_base"])})
    fix2 = D.node("Frame2", "stdlib:translation/Fixed", X(2), 20)
    stop = D.node("EndStops", "stdlib:translation/HardStop", X(3), 120,
                  params={"lower": num(-dz["s_max"]), "upper": num(dz["s_max"]), "k": num(dz["k_stop"]),
                          "d": num(dz["d_stop"])}, starts={"x": num(x0)})
    fix3 = D.node("Frame3", "stdlib:translation/Fixed", X(3), 20)
    # the source's port `a` takes power in (a.e = F u is the force it receives), so port `b` faces the
    # rail: a positive command then pushes the cart towards +x
    D.wire(act, "b", rail, "drive")
    D.wire(act, "a", fix1, "a")
    D.wire(fric, "a", rail, "drive")
    D.wire(fric, "b", fix2, "a")
    D.wire(stop, "a", rail, "drive")
    D.wire(stop, "b", fix3, "a")

    # firmware and monitor
    clock = D.node("Clock", "stdlib:sources/Time", X(0) - 120, 120)
    cparams = {}
    if mode == "free":
        cparams = {"t_on": "1.0e6"}
    if mode == "balance":
        cparams = {"balance_only": "true"}
    if use_globals:
        for gname, pname in (("delay_ms", "delay_n"), ("quant", "quant"), ("F_max", "u_max")):
            if gname in [p["name"] for p in parameters]:
                cparams[pname] = gname
    ctrl = D.node("Ctrl", f"project:{dz['ctrl_block']}", X(0), 120, params=cparams)
    traj = D.node("Traj", f"project:{dz['ctrl_block'].replace('Ctrl', 'Traj')}", X(0) - 120, 240)
    D.sig(clock, "y", traj, "tm")
    for port in ports(dz, two):
        D.sig(traj, port, ctrl, port)
    D.sig(clock, "y", ctrl, "tm")
    D.sig(rail, "qout", ctrl, "s")
    D.sig(rail, "qdout", ctrl, "sd")
    for j, jn in enumerate(joints):
        D.sig(jn, "qout", ctrl, f"q{j + 1}")
        D.sig(jn, "qdout", ctrl, f"wq{j + 1}")
    D.sig(ctrl, "u", act, "u")
    mparams = {}
    if use_globals:
        mparams = {"m": "[" + ", ".join(f"m_scale*{num(v)}" for v in dz["m_model"]) + "]",
                   "J": "[" + ", ".join(f"m_scale*{num(v)}" for v in dz["J_model"]) + "]"}
    mon = D.node("Mon", f"project:{dz['monitor_block']}", X(0), 780, params=mparams)
    D.sig(rail, "qdout", mon, "sd")
    if two:
        D.sig(rail, "qout", mon, "s")
        D.sig(traj, "lim", mon, "lim")
    D.sig(ctrl, "u", mon, "u")
    for j, jn in enumerate(joints):
        D.sig(jn, "qout", mon, f"q{j + 1}")
        D.sig(jn, "qdout", mon, f"wq{j + 1}")
        D.sig(bodies[j][0], "V", mon, f"V{j + 1}")
        D.sig(bodies[j][1], "g", mon, f"g{j + 1}")

    plots = [
        {"id": "p_angles", "title": "Link angles from upright (deg)", "signals": [f"Mon/th{i + 1}" for i in range(n)]},
        {"id": "p_energy", "title": "Stacked energy per link (J) and the UPRIGHT level",
         "signals": [f"Mon/S{i + 1}" for i in range(n)] + ["Mon/E_up"]},
        ({"id": "p_cart", "title": "Cart position x (m) and the travel limit of the chosen controller", "signals": ["Rail/qout", "Mon/lim_hi", "Mon/lim_lo"]}
         if two else {"id": "p_cart", "title": "Cart position x (m)", "signals": ["Rail/qout"]}),
        {"id": "p_force", "title": "Cart force F (N) and controller phase", "signals": ["Ctrl/u", "Ctrl/phase"]},
        {"id": "p_ledger", "title": "Energy ledger (J): E_tot, W_in, W_loss, E_tot - W_in + W_loss",
         "signals": ["Mon/E_tot", "Mon/W_in", "Mon/W_loss", "Mon/ledger"]},
    ]
    bindings = [{"target": "joint:rail", "property": "position", "signal": "Rail/qout"}]
    for j in range(n):
        bindings.append({"target": f"joint:hinge{j + 1}", "property": "position", "signal": f"Joint{j + 1}/qout"})
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": D.doc(), "settings": settings(t_end, points, reltol, abstol), "plots": plots,
        "scene": {"file": "scenes/quad-pendulum.sdf"}, "bindings": bindings,
    }
    if parameters is not None:
        doc["parameters"] = parameters
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc


# ============================================================================ rotary (spatial)


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def qrot(q, v):
    w, x, y, z = q
    p = qmul(qmul(q, (0.0, *v)), (w, -x, -y, -z))
    return p[1:]


def pose_mul(a, b):
    (qa, ta), (qb, tb) = a, b
    r = qrot(qa, tb)
    return qmul(qa, qb), tuple(ta[i] + r[i] for i in range(3))


def pose_inv(p):
    q, t = p
    qi = (q[0], -q[1], -q[2], -q[3])
    r = qrot(qi, t)
    return qi, tuple(-c for c in r)


def pose_params(p):
    q, t = p
    names = ("qw", "qx", "qy", "qz", "x", "y", "z")
    return {k: num(0.0 if abs(v) < 1e-15 else v) for k, v in zip(names, (*q, *t))}


def rotation_matrix(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
SQ = math.sqrt(0.5)
RJF = ((0.0, SQ, 0.0, SQ), (0.0, 0.0, 0.0))  # local z = arm axis, local x = world z (upright)


def rotary_geometry(dz):
    n = len(dz["L"])
    ln = [IDENTITY, (RJF[0], (dz["arm_l"], 0.0, 0.0))]
    for k in range(1, n):
        ln.append((IDENTITY[0], (dz["L"][k - 1], 0.0, 0.0)))
    lc = [((1.0, 0.0, 0.0, 0.0), (dz["arm_l"] / 2, 0.0, 0.0))]
    for k in range(n):
        lc.append(((1.0, 0.0, 0.0, 0.0), (dz["L"][k] / 2, 0.0, 0.0)))
    mass = [dz["m_base"], *dz["m_model"]]
    # the hub/rotor inertia about the vertical axis is lumped into the arm body (an Inertia on J1.drive
    # would be a second store on the same rate as the arm's angular momentum: derivative causality)
    ja = list(dz["Jp_arm"])
    ja[2] += dz["J_hub"]
    inertia = [ja, *dz["Jp_model"]]
    return ln, lc, mass, inertia


def rotary_static(ln, lc, mass, q0, k):
    child = IDENTITY
    joints, bodies = [], []
    for i in range(len(ln)):
        jf = pose_mul(child, ln[i])
        rz = ((math.cos(q0[i] / 2), 0.0, 0.0, math.sin(q0[i] / 2)), (0.0, 0.0, 0.0))
        child = pose_mul(jf, rz)
        joints.append((np.array(jf[1]), rotation_matrix(child[0])))
        bodies.append(np.array(pose_mul(child, lc[i])[1]))
    out = []
    for i in range(len(ln)):
        origin, rc = joints[i]
        force, moment = np.zeros(3), np.zeros(3)
        for j in range(i, len(ln)):
            w = np.array([0.0, 0.0, -mass[j] * G0])
            force += w
            moment += np.cross(bodies[j] - origin, w)
        out.append((list((rc.T @ moment / k)[:2]), list(rc.T @ force / k)))
    return out


def vecs(v):
    return "[" + ", ".join(num(x) for x in v) + "]"


def build_rotary(dz, *, name, mode, t_end, points, phi0=None, s0=0.0, comment="", dashboard=None, parameters=None,
                 push=None, reltol=1e-7, abstol=1e-9, two=True):
    """phi0: absolute link angles from upright (rad); joint coordinates q = [s, phi1, phi2-phi1, ..].
    two: as in build_cart."""
    n = len(dz["L"])
    nq = n + 1
    ln, lc, mass, inertia = rotary_geometry(dz)
    k_joint = dz["k_joint"]
    phi = list(phi0) if phi0 is not None else [math.pi] * n
    q_start = [s0, phi[0]] + [phi[k] - phi[k - 1] for k in range(1, n)]
    defl = rotary_static(ln, lc, mass, q_start, k_joint)
    distal = [sum(mass[j:]) for j in range(nq)]
    reach = dz["arm_l"] + sum(dz["L"])
    jref = [sum(m * reach**2 + max(jj) for m, jj in zip(mass[j:], inertia[j:])) for j in range(nq)]
    use_globals = parameters is not None
    gnames = [p["name"] for p in parameters] if use_globals else []
    D = Diagram()
    bx = [380 + 460 * i for i in range(nq)]
    ry = [320 + 220 * i for i in range(nq)]
    band = 340 + 220 * nq + 100
    world = D.node("World", "stdlib:multibond/GroundSpatial", bx[0] - 140, ry[0])
    mount = D.node("Mount", "stdlib:multibond/FixedTransform3DNeutral", bx[0], ry[0], params=pose_params(IDENTITY))
    mpose = D.node("MountPose", "stdlib:spatial/LocalPose3D", bx[0] - 140, band, params=pose_params(IDENTITY))
    D.bond(world, "p", mount, "b")
    prev_world, prev_bj = mpose, None
    J, BJ, BODY, PB = [], [], [], []
    for i in range(nq):
        k = i + 1
        x0, y0 = bx[i], ry[i]
        q0s = num(q_start[i])
        if use_globals and mode == "balance" and i >= 1:
            q0s = (f"th0_1*{DEG!r}" if i == 1 else f"(th0_{i} - th0_{i - 1})*{DEG!r}")
            if i == 1:
                q0s = f"th0_1*{DEG!r}"
        jn = D.node(f"J{k}", "stdlib:spatial/Revolute3D", x0 + 120, y0,
                    params={"kt": num(k_joint), "kr": num(k_joint), "bt": num(1.4 * math.sqrt(k_joint * distal[i])),
                            "br": num(1.4 * math.sqrt(k_joint * jref[i])), "q0": q0s},
                    starts={"dth": vecs(defl[i][0]), "dl": vecs(defl[i][1])})
        lk = D.node("ArmLink" if i == 0 else f"Link{i}", "stdlib:multibond/FixedTransform3DNeutral", x0 + 240, y0,
                    params=pose_params(lc[i]))
        bj = D.node(f"BJ{k}", "1", x0 + 360, y0 + 10)
        mpar, jpar = num(mass[i]), vecs(inertia[i])
        if use_globals and i >= 1:
            mpar = f"m_scale*{mpar}"
            jpar = "[" + ", ".join(f"m_scale*{num(v)}" for v in inertia[i]) + "]"
        body = D.node("Arm" if i == 0 else f"Rod{i}", "stdlib:spatial/RigidBody3D", x0 + 350, y0 + 100,
                      params={"m": mpar, "J": jpar, "g0": num(G0)})
        if i == 0:
            D.bond(mount, "a", jn, "parent")
        else:
            t = D.node(f"T{k}", "stdlib:multibond/FixedTransform3DNeutral", x0, y0,
                       params=pose_params(pose_mul(pose_inv(ln[i]), lc[i - 1])))
            D.bond(t, "a", jn, "parent")
            D.bond(t, "b", prev_bj)
        D.bond(jn, "child", lk, "a")
        D.bond(lk, "b", bj)
        D.bond(body, "p", bj)
        lnn = D.node(f"LN{k}", "stdlib:spatial/LocalPose3D", x0, band + 100, params=pose_params(ln[i]))
        ca_ = D.node(f"CA{k}", "stdlib:multibond/ComposePose3D", x0, band)
        w = D.node(f"W{k}", "stdlib:multibond/ComposePose3D", x0 + 120, band)
        lcn = D.node(f"LC{k}", "stdlib:spatial/LocalPose3D", x0 + 350, band + 240, params=pose_params(lc[i]))
        pb = D.node(f"P{k}", "stdlib:multibond/ComposePose3D", x0 + 350, band + 120)
        D.sig(prev_world, "g", ca_, "gp")
        D.sig(lnn, "g", ca_, "gl")
        D.sig(ca_, "g", w, "gp")
        D.sig(jn, "pose", w, "gl")
        D.sig(w, "g", pb, "gp")
        D.sig(lcn, "g", pb, "gl")
        D.sig(pb, "g", body, "g")
        prev_world, prev_bj = w, bj
        J.append(jn)
        BJ.append(bj)
        BODY.append(body)
        PB.append(pb)

    # passive pendulum joints: bearing friction on the drive port
    for i in range(1, nq):
        f = D.node(f"Bearing{i + 1}", "stdlib:rotation/RotationalDamper", bx[i] + 120, ry[i] - 110,
                   params={"d": num(dz["b_joint"])})
        fx = D.node(f"Frame{i + 1}", "stdlib:rotation/FixedShaft", bx[i] + 280, ry[i] - 110)
        D.wire(J[i], "drive", f, "a")
        D.wire(f, "b", fx, "a")
    # arm drive: ideal torque and bearing friction (the hub/rotor inertia is in the Arm body)
    mot = D.node("Motor", "stdlib:rotation/TorqueSource", bx[0] - 140, ry[0] + 330, params={"T": num(dz.get("force_sign", 1.0))})
    mfx = D.node("Stator", "stdlib:rotation/FixedShaft", bx[0] - 300, ry[0] + 330)
    brg = D.node("ArmBearing", "stdlib:rotation/RotationalDamper", bx[0] + 40, ry[0] + 330, params={"d": num(dz["b_base"])})
    bfx = D.node("Frame1", "stdlib:rotation/FixedShaft", bx[0] + 40, ry[0] + 440)
    # as for the cart: port `b` of the source faces the joint, so a positive command turns the arm +z
    D.wire(mot, "b", J[0], "drive")
    D.wire(mot, "a", mfx, "a")
    D.wire(brg, "a", J[0], "drive")
    D.wire(brg, "b", bfx, "a")

    # disturbance at the tip of the top link, perpendicular to the rod in the pendulum plane
    tip = pose_params(((1.0, 0.0, 0.0, 0.0), (-dz["L"][-1] / 2, 0.0, 0.0)))
    tipt = D.node("TipPoint", "stdlib:multibond/FixedTransform3DNeutral", bx[-1] + 360, ry[-1] + 230, params=tip)
    dist = D.node("Push", "stdlib:multibond/ExternalWrenchSpatial", bx[-1] + 520, ry[-1] + 230)
    pa = push or {"amplitude": 0.0, "t_start": 1.0e6, "duration": 0.05}
    amp = "push_N" if "push_N" in gnames else num(pa["amplitude"])
    pulse = D.node("PushPulse", "stdlib:sources/Pulse", bx[-1] + 520, ry[-1] + 120,
                   params={"amplitude": amp, "period": "1000.0", "duty": num(pa["duration"] / 1000.0),
                           "t_start": num(pa["t_start"])})
    zero = D.node("Zero", "stdlib:sources/Constant", bx[-1] + 360, ry[-1] + 120, params={"value": "0.0"})
    D.bond(dist, "p", tipt, "a")
    D.bond(tipt, "b", BJ[-1])
    for port in ("tx", "ty", "tz", "fx", "fz"):
        D.sig(zero, "y", dist, port)
    D.sig(pulse, "y", dist, "fy")

    clock = D.node("Clock", "stdlib:sources/Time", bx[0] - 300, 60)
    cparams = {}
    if mode == "free":
        cparams = {"t_on": "1.0e6"}
    if mode == "balance":
        cparams = {"balance_only": "true"}
    for gname, pname in (("delay_ms", "delay_n"), ("quant", "quant"), ("T_max", "u_max")):
        if gname in gnames:
            cparams[pname] = gname
    ctrl = D.node("Ctrl", f"project:{dz['ctrl_block']}", bx[0] - 140, 60, params=cparams)
    traj = D.node("Traj", f"project:{dz['ctrl_block'].replace('Ctrl', 'Traj')}", bx[0] - 300, 180)
    D.sig(clock, "y", traj, "tm")
    for port in ports(dz, two):
        D.sig(traj, port, ctrl, port)
    D.sig(clock, "y", ctrl, "tm")
    D.sig(J[0], "qout", ctrl, "s")
    D.sig(J[0], "qdout", ctrl, "sd")
    for i in range(n):
        D.sig(J[i + 1], "qout", ctrl, f"q{i + 1}")
        D.sig(J[i + 1], "qdout", ctrl, f"wq{i + 1}")
    D.sig(ctrl, "u", mot, "u")
    mparams = {}
    if use_globals:
        mparams = {"m": "[" + ", ".join(f"m_scale*{num(v)}" for v in dz["m_model"]) + "]"}
        for i in range(n):
            mparams[f"Jp{i + 1}"] = "[" + ", ".join(f"m_scale*{num(v)}" for v in dz["Jp_model"][i]) + "]"
    mon = D.node("Mon", f"project:{dz['monitor_block']}", bx[-1] + 360, 60, params=mparams)
    D.sig(J[0], "qdout", mon, "sd")
    if two:
        D.sig(J[0], "qout", mon, "s")
        D.sig(traj, "lim", mon, "lim")
    D.sig(ctrl, "u", mon, "u")
    for i in range(n):
        D.sig(J[i + 1], "qout", mon, f"q{i + 1}")
        D.sig(J[i + 1], "qdout", mon, f"wq{i + 1}")
        D.sig(BODY[i + 1], "V", mon, f"V{i + 1}")
        D.sig(PB[i + 1], "g", mon, f"g{i + 1}")

    plots = [
        {"id": "p_angles", "title": "Link angles from upright (deg)", "signals": [f"Mon/th{i + 1}" for i in range(n)]},
        {"id": "p_energy", "title": "Stacked energy per link (J) and the UPRIGHT level",
         "signals": [f"Mon/S{i + 1}" for i in range(n)] + ["Mon/E_up"]},
        ({"id": "p_arm", "title": "Arm angle (rad) and the travel limit of the chosen controller", "signals": ["J1/qout", "Mon/lim_hi", "Mon/lim_lo"]}
         if two else {"id": "p_arm", "title": "Arm angle (rad)", "signals": ["J1/qout"]}),
        {"id": "p_torque", "title": "Arm torque (N m) and controller phase", "signals": ["Ctrl/u", "Ctrl/phase"]},
        {"id": "p_ledger", "title": "Energy ledger (J): E_tot, W_in, W_loss, E_tot - W_in + W_loss",
         "signals": ["Mon/E_tot", "Mon/W_in", "Mon/W_loss", "Mon/ledger"]},
    ]
    bindings = [{"target": "joint:arm", "property": "position", "signal": "J1/qout"}]
    for i in range(n):
        bindings.append({"target": f"joint:link{i + 1}", "property": "position", "signal": f"J{i + 2}/qout"})
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": D.doc(), "settings": settings(t_end, points, reltol, abstol), "plots": plots,
        "scene": {"file": "scenes/quad-pendulum-rotary.sdf"}, "bindings": bindings,
    }
    if parameters is not None:
        doc["parameters"] = parameters
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc


def write(path: Path, doc) -> None:
    with open(path, "w", newline="\n", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
