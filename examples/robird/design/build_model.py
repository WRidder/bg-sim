# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Generate `models/robird*.bgmodel.json` and `scenes/robird.sdf` from the data of `params.py` / `design.py`.

The diagram is a plain node/connection list, so it is generated rather than hand-written: two wings with
two aeroelastic segments each, three tail flaps, the flapping drive and the controller repeat a lot.

    uv run examples/robird/design/build_model.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import params as P  # noqa: E402

ROOT = HERE.parent


class Builder:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.conns: list[dict] = []
        self.n = 0
        self.c = 0

    def node(self, name, ref, x, y, params=None, starts=None, constants=None):
        self.n += 1
        nid = f"n{self.n:03d}"
        self.nodes.append({
            "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": x, "y": y},
            "rotation": 0, "flipX": False,
            "params": {k: _s(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: _s(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        return nid

    def conn(self, kind, a, ap, b, bp, label=None):
        self.c += 1
        self.conns.append({"id": f"{kind[0]}{self.c:03d}", "kind": kind, "from": {"node": a, "port": ap},
                           "to": {"node": b, "port": bp}, "route": [], "label": label})

    def sig(self, a, ap, b, bp, label=None):
        self.conn("signal", a, ap, b, bp, label)

    def bond(self, a, ap, b, bp):
        self.conn("bond", a, ap, b, bp)

    def wire(self, a, ap, b, bp):
        self.conn("wire", a, ap, b, bp)


def _s(v):
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, (list, tuple, np.ndarray)):
        return "[" + ", ".join(repr(float(x)) for x in v) + "]"
    if isinstance(v, float):
        return repr(v)
    return str(v)


# ----------------------------------------------------------------------------- poses
def pose_of(R, p):
    q = P.quat_from_matrix(R)
    return {"qw": float(q[0]), "qx": float(q[1]), "qy": float(q[2]), "qz": float(q[3]),
            "x": float(p[0]), "y": float(p[1]), "z": float(p[2])}


def inv_pose(R, p):
    R = np.asarray(R)
    return R.T, -R.T @ np.asarray(p, dtype=float)


# frame columns (x_j, y_j, z_j) in the fuselage frame (x fwd, y left, z up); see the README
WING_FRAME = {
    +1: P.rotmat_from_cols([0, 1, 0], [0, 0, 1], [1, 0, 0]),     # left: x_j = +y_b (span), z_j = +x_b (flap axis, up positive)
    -1: P.rotmat_from_cols([0, -1, 0], [0, 0, 1], [-1, 0, 0]),   # right: x_j = -y_b, z_j = -x_b
}
ELEVON_FRAME = P.rotmat_from_cols([1, 0, 0], [0, 0, 1], [0, -1, 0])   # x_j = chord (fwd), y_j = up, z_j = -y_b : +delta = leading edge up
RUDDER_FRAME = np.eye(3)


def local_node(b, name, x, y, R, p):
    return b.node(name, "stdlib:spatial/LocalPose3D", x, y, params=pose_of(R, p))


def mount_node(b, name, x, y, R, p):
    return b.node(name, "stdlib:multibond/FixedTransform3DNeutral", x, y, params=pose_of(R, p))


def compose(b, name, x, y, gp, gl):
    n = b.node(name, "stdlib:multibond/ComposePose3D", x, y)
    b.sig(gp[0], gp[1], n, "gp")
    b.sig(gl[0], gl[1], n, "gl")
    return n


def vec3(v):
    return [float(x) for x in v]


def solve_psi0() -> tuple[float, float]:
    """Crank angle at which the stroke is at its upper turning point, and the flap angle there."""
    f = lambda psi: P.PHI_FLAP * (math.cos(psi) + 2 * P.H2 * math.cos(2 * psi + P.PH2))
    lo, hi = 0.5, 2.3
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    psi = 0.5 * (lo + hi)
    return psi, P.PHI_FLAP * (math.sin(psi) + P.H2 * math.sin(2 * psi + P.PH2))


# ----------------------------------------------------------------------------- the model
def build(name: str, init: dict, t_end: float, controller=None, extra_plots=None, bindings_on=True) -> dict:
    """init: dict(U, psi0 (heading), theta0 (pitch), z0, x0, y0, f0, drive_start)"""
    b = Builder()
    U = init["U"]
    R0 = P.rz(init.get("heading", 0.0)) @ P.ry(-init.get("pitch", 0.0))
    q0 = P.quat_from_matrix(R0)
    pos0 = np.array([init.get("x0", 0.0), init.get("y0", 0.0), init["z0"]])
    v_w = U * R0[:, 0]
    psi_c, phi_up = solve_psi0()

    def p_lin(Rb, m):
        return [0.0, 0.0, 0.0, *(m * (Rb.T @ v_w))]

    # ---- fuselage (floating 6-DOF body)
    world = b.node("World", "stdlib:multibond/GroundSpatial", 40, 420)
    free = b.node("Free", "stdlib:spatial/Free3D", 220, 420,
                  starts={"qw": q0[0], "qx": q0[1], "qy": q0[2], "qz": q0[3], "px": pos0[0], "py": pos0[1], "pz": pos0[2]})
    body = b.node("Body", "stdlib:spatial/RigidBody3D", 420, 420,
                  params={"m": P.M_FUS, "J": P.J_FUS, "g0": P.G}, starts={"inertia/P": p_lin(R0, P.M_FUS)})
    b.bond(world, "p", free, "parent")
    b.bond(free, "child", body, "p")
    for k in range(1, 7):
        se = b.node(f"FreeSe{k}", "stdlib:bondgraph/Se", 220, 560 + 50 * k, params={"e": "0.0"})
        b.bond(se, "p", free, f"drive{k}")
    b.sig(free, "pose", body, "g", "pose chart (qw qx qy qz x y z)")
    air = b.node("Air", "project:AirMass", 40, 700, params={"wind": init.get("wind", [0.0, 0.0, 0.0])})

    fa = b.node("FusAero", "project:FuselageAero", 620, 560,
                params={"rho": P.RHO, "cdax": P.CDA_FUS[0], "cday": P.CDA_FUS[1], "cdaz": P.CDA_FUS[2], "cdr": P.CDR_FUS})
    fw = b.node("FusWrench", "stdlib:multibond/ExternalWrenchSpatial", 420, 560)
    b.bond(fw, "p", body, "p")
    for ax in ("tx", "ty", "tz", "fx", "fy", "fz"):
        b.sig(fa, ax, fw, ax)
    b.sig(body, "V", fa, "V"), b.sig(free, "pose", fa, "pose"), b.sig(air, "w", fa, "wind")

    aero_nodes: list[str] = []        # StripAero nodes (for the power sum)
    body_nodes: dict[str, str] = {}

    def strip_body(tag, parent_pose, parent_body, R_par, M_R, M_p, joint_ref, joint_params, joint_starts, LC_p,
                   mass, J, aero, x, y):
        """One body below a parent body through one joint (mount, joint, link, body, wrench, pose chain)."""
        mt = mount_node(b, f"Mount{tag}", x, y, *inv_pose(M_R, M_p))
        j = b.node(f"J{tag}", joint_ref, x + 200, y, params=joint_params, starts=joint_starts)
        lk = mount_node(b, f"Link{tag}", x + 400, y, np.eye(3), LC_p)
        Rb = R_par @ M_R @ P.rz(joint_params.get("q0", 0.0))
        bd = b.node(f"B{tag}", "stdlib:spatial/RigidBody3D", x + 600, y,
                    params={"m": mass, "J": J, "g0": P.G}, starts={"inertia/P": p_lin(Rb, mass)})
        b.bond(parent_body, "p", mt, "b")
        b.bond(mt, "a", j, "parent")
        b.bond(j, "child", lk, "a")
        b.bond(lk, "b", bd, "p")
        # pose chain
        lm = local_node(b, f"LocM{tag}", x, y + 120, M_R, M_p)
        pa = compose(b, f"PoseA{tag}", x + 200, y + 120, parent_pose, (lm, "g"))
        pj = compose(b, f"PoseJ{tag}", x + 400, y + 120, (pa, "g"), (j, "pose"))
        ll = local_node(b, f"LocC{tag}", x + 400, y + 220, np.eye(3), LC_p)
        pb = compose(b, f"PoseB{tag}", x + 600, y + 120, (pj, "g"), (ll, "g"))
        b.sig(pb, "g", bd, "g")
        # aerodynamic wrench
        an = b.node(f"Aero{tag}", "project:StripAero", x + 800, y, params=aero, constants={"NS": len(aero["rs"])})
        wr = b.node(f"Wr{tag}", "stdlib:multibond/ExternalWrenchSpatial", x + 1000, y)
        b.bond(wr, "p", bd, "p")
        if joint_params.get("k", 0.0) > 0.0 and tag[0] != "T":
            se = b.node(f"Se{tag}", "stdlib:bondgraph/Se", x + 200, y - 60, params={"e": "0.0"})
            b.bond(se, "p", j, "drive")
        for ax in ("tx", "ty", "tz", "fx", "fy", "fz"):
            b.sig(an, ax, wr, ax)
        b.sig(bd, "V", an, "V"), b.sig(pb, "g", an, "pose"), b.sig(air, "w", an, "wind")
        aero_nodes.append(an)
        return dict(j=j, body=bd, pose=(pb, "g"), joint_pose=(pj, "g"), R=Rb, mass=mass)

    # ---- wings
    wing = {}
    ylab = 1500
    for side, tag in ((+1, "L"), (-1, "R")):
        y0 = 1000 if side > 0 else 1500
        Rf = WING_FRAME[side]
        root = np.array([P.WING_ROOT[0], side * P.WING_ROOT[1], P.WING_ROOT[2]])
        # segment 1
        rs1, S1, c1 = P.segment_strips(P.L1, *P.C1)
        aero1 = dict(ele=vec3(Rf.T @ np.array([1, 0, 0])), en=[0.0, 1.0, 0.0], es=[1.0, 0.0, 0.0],
                     rs=[r - P.L1 / 2 for r in rs1], xc=[-(0.25 - P.XEA) * c for c in c1], S=S1, onev=[1.0] * P.NS,
                     rho=P.RHO, La=P.LA, Lb=P.LB, Da=P.DA, Db=P.DB, amax=P.AMAX)
        s1 = strip_body(
            tag + "1", (free, "pose"), body, R0, Rf, root,
            "project:WingJoint",
            dict(kr=P.K_SWEEP, krp=P.KP_TORS[0], brp=P.BP_TORS[0], br=P.B_SWEEP, kt=P.K_PIVOT, bt=P.B_PIVOT,
                 q0=P.DIHEDRAL + phi_up, k=0.0, b=0.0),
            {"dth": [side * (P.THETA_ROD * math.sin(psi_c + P.PS_ROD) - P.INCIDENCE), 0.0]}, np.array([P.L1 / 2, 0, 0]), P.M1, P.inertia_plate(P.M1, P.L1, sum(c1) / P.NS), aero1,
            200, y0)
        rs2, S2, c2 = P.segment_strips(P.L2, *P.C2)
        aero2 = dict(ele=aero1["ele"], en=[0.0, 1.0, 0.0], es=[1.0, 0.0, 0.0],
                     rs=[r - P.L2 / 2 for r in rs2], xc=[-(0.25 - P.XEA) * c for c in c2], S=S2, onev=[1.0] * P.NS,
                     rho=P.RHO, La=P.LA, Lb=P.LB, Da=P.DA, Db=P.DB, amax=P.AMAX)
        s2 = strip_body(
            tag + "2", s1["pose"], s1["body"], s1["R"], np.eye(3), np.array([P.L1 / 2, 0, 0]),
            "project:WingJoint",
            dict(kr=P.K_SWEEP, krp=P.KP_TORS[1], brp=P.BP_TORS[1], br=P.B_SWEEP, kt=P.K_PIVOT, bt=P.B_PIVOT,
                 q0=0.0, k=P.K_BEND2, b=P.B_BEND2),
            {}, np.array([P.L2 / 2, 0, 0]), P.M2, P.inertia_plate(P.M2, P.L2, sum(c2) / P.NS), aero2,
            200 + 1400, y0)
        wing[tag] = (s1, s2, Rf)
        zero_src = b.node(f"Zero{tag}", "stdlib:sources/Constant", 1900, y0 - 100, params={"value": 0.0})
        b.sig(zero_src, "y", s2["j"], "th_rest")

    # ---- tail flaps
    tail = {}
    ty0 = 2100
    for tag, (pos, frame, span, chord, ele, en, es, ref_axis) in {
        "TL": ((P.TAIL_X, +P.TAIL_Y, 0.0), ELEVON_FRAME, P.FLAP_SPAN, P.FLAP_CHORD, [1, 0, 0], [0, 1, 0], [0, 0, -1], None),
        "TR": ((P.TAIL_X, -P.TAIL_Y, 0.0), ELEVON_FRAME, P.FLAP_SPAN, P.FLAP_CHORD, [1, 0, 0], [0, 1, 0], [0, 0, -1], None),
        "TV": ((P.RUD_X, 0.0, P.RUD_Z), RUDDER_FRAME, P.RUD_SPAN, P.RUD_CHORD, [1, 0, 0], [0, 1, 0], [0, 0, 1], None),
    }.items():
        ns = 2
        w = span / ns
        rs = [w * (i + 0.5) - span / 2 for i in range(ns)]
        aero = dict(ele=ele, en=en, es=es, rs=rs, xc=[-0.03 * chord] * ns, S=[w * chord] * ns, onev=[1.0] * ns,
                    rho=P.RHO, La=P.LA_TAIL, Lb=P.LB_TAIL, Da=P.DA_TAIL, Db=P.DB_TAIL, amax=0.6)
        J = [M for M in P.inertia_plate(P.M_FLAP, span, chord)]
        yy = ty0 + 260 * len(tail)
        t = strip_body(tag, (free, "pose"), body, R0, frame, np.array(pos),
                       "stdlib:spatial/Revolute3DCompliant",
                       dict(kr=2.0, br=0.02, kt=1.0e4, bt=15.0, q0=0.0, k=0.0, b=0.0), {},
                       np.zeros(3), P.M_FLAP, J, aero, 200, yy)
        sv = b.node(f"Servo{tag}", "project:TailServo", 1400, yy, params=P.SERVO)
        ms = b.node(f"ServoT{tag}", "stdlib:bondgraph/MSe", 1600, yy)
        b.sig(t["j"], "qout", sv, "q"), b.sig(t["j"], "qdout", sv, "qd"), b.sig(sv, "tau", ms, "u")
        b.bond(ms, "p", t["j"], "drive")
        tail[tag] = (t, sv)

    # ---- flapping drive: ElectricDrive -> gear -> crank -> elastic shafts -> wing roots
    drv = b.node("Drv", "stdlib:drives/ElectricDrive", 1100, 100,
                 params={"R_w": P.R_W, "L": P.L_W, "k_t": P.K_MOTOR, "J_m": P.J_M, "b_m": P.B_M},
                 starts={"rotor/w": init["f0"] * 2 * math.pi * P.N_GEAR})
    gear = b.node("Gear", "stdlib:rotation/IdealGear", 1300, 100, params={"n": P.N_GEAR})
    crank = b.node("Crank", "project:Crank", 1500, 100,
                   params={"Phi": P.PHI_FLAP, "h2": P.H2, "ph2": P.PH2, "psi0": psi_c, "Theta": P.THETA_ROD, "ps": P.PS_ROD, "inc": P.INCIDENCE})
    b.wire(drv, "shaft", gear, "a")
    b.wire(gear, "b", crank, "a")
    for tag, port in (("L", "bL"), ("R", "bR")):
        sh = b.node(f"Shaft{tag}", "stdlib:rotation/ElasticShaft", 1700, 100 + (60 if tag == "R" else 0),
                    params={"k": P.K_SHAFT, "d": P.D_SHAFT})
        b.wire(crank, port, sh, "a")
        b.wire(sh, "b", wing[tag][0]["j"], "drive")

    for tag, port in (("L", "pitL"), ("R", "pitR")):
        b.sig(crank, port, wing[tag][0]["j"], "th_rest")
    truth = b.node("Truth", "project:Truth", 620, 420)
    b.sig(free, "pose", truth, "pose"), b.sig(body, "V", truth, "V")
    pk = b.node("PaSum", "project:SumPa", 900, 560)
    for i, an in enumerate(aero_nodes, start=1):
        b.sig(an, "Pa", pk, f"u{i}")
    b.sig(fa, "Pa", pk, f"u{len(aero_nodes) + 1}")

    ctx = dict(b=b, free=free, body=body, truth=truth, drv=drv, crank=crank, tail=tail, wing=wing, air=air,
               aero_nodes=aero_nodes, psi_c=psi_c)
    plots, bindings = [], []
    if controller is not None:
        plots = controller(ctx) or []
    # initial momenta of the child bodies: the velocity of the body frame in its own axes
    return b, ctx, plots


def finish(b: Builder, ctx: dict, name: str, init: dict, t_end: float, plots, comment: str, points: int,
           reltol=1e-4, abstol=1e-6) -> dict:
    bind = [{"target": "link:fuselage", "property": "pose",
             "signal": ["Truth/q[1]", "Truth/q[2]", "Truth/q[3]", "Truth/q[4]", "Truth/x", "Truth/y", "Truth/z"]}]
    for tag in ("L", "R"):
        bind.append({"target": f"joint:flap_{tag}", "property": "position", "signal": f"J{tag}1/qout"})
        bind.append({"target": f"joint:torsion_{tag}", "property": "position", "signal": f"J{tag}1/dang[1]"})
        bind.append({"target": f"joint:bend_{tag}", "property": "position", "signal": f"J{tag}2/qout"})
        bind.append({"target": f"joint:torsion2_{tag}", "property": "position", "signal": f"J{tag}2/dang[1]"})
    for tag, nm in (("TL", "elevon_L"), ("TR", "elevon_R"), ("TV", "rudder")):
        bind.append({"target": f"joint:{nm}", "property": "position", "signal": f"J{tag}/qout"})
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": {"nodes": b.nodes, "connections": b.conns, "subsystemPorts": [], "annotations": []},
        "settings": {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": reltol, "abstol": abstol,
                     "max_step": None, "output": {"mode": "points", "points": points}, "event_limit": 1000000},
        "plots": plots,
        "scene": {"file": "scenes/robird.sdf"},
        "bindings": bind,
    }


# ----------------------------------------------------------------------------- open-loop (trim) wiring
def flap_ctrl(ctx, f_node, f_port):
    """FlapMotorCtrl between a flapping-frequency command signal and the drive voltage."""
    b = ctx["b"]
    bat = b.node("Bat", "stdlib:sources/Constant", 1100, 300, params={"value": P.V_BAT})
    fc = b.node("FlapCtl", "project:FlapMotorCtrl", 1100, 220,
                params={"N": P.N_GEAR, "k_e": P.K_MOTOR, "k_t": P.K_MOTOR, "R_w": P.R_W, "b_m": P.B_M})
    b.sig(f_node, f_port, fc, "f_cmd")
    b.sig(ctx["drv"], "w", fc, "w")
    b.sig(bat, "y", fc, "vbat")
    b.sig(fc, "u", ctx["drv"], "u")
    return fc


def open_loop(f_cmd, de, da, dr, aL=1.0, aR=1.0):
    """controller(ctx) adding constant commands: flapping frequency (Hz), elevator, aileron (differential), rudder (rad)."""
    def wire(ctx):
        b = ctx["b"]
        cf = b.node("CmdF", "stdlib:sources/Constant", 900, 220, params={"value": f_cmd})
        flap_ctrl(ctx, cf, "y")
        cmds = {}
        for tag, val in (("TL", de + da), ("TR", de - da), ("TV", dr)):
            c = b.node(f"Cmd{tag}", "stdlib:sources/Constant", 1250, 100, params={"value": val})
            b.sig(c, "y", ctx["tail"][tag][1], "sp")
            cmds[tag] = c
        ca = b.node("CmdAmpL", "stdlib:sources/Constant", 1300, 20, params={"value": aL})
        cb = b.node("CmdAmpR", "stdlib:sources/Constant", 1300, 60, params={"value": aR})
        b.sig(ca, "y", ctx["crank"], "aL"), b.sig(cb, "y", ctx["crank"], "aR")
        return [
            {"id": "p1", "title": "Position (m)", "signals": ["Truth/x", "Truth/y", "Truth/z"]},
            {"id": "p2", "title": "Flap angles (rad)", "signals": ["JL1/qout", "JR1/qout"]},
        ]
    return wire


# ----------------------------------------------------------------------------- closed loop
def closed_loop(tab: dict, ctl: dict, U: float, stat_from: float = 8.0):
    """controller(ctx): Time -> Guidance -> FlightCtrl -> flapping drive, tail servos and wing amplitude asymmetry."""
    def wire(ctx):
        b = ctx["b"]
        clock = b.node("Clock", "stdlib:sources/Time", 600, 20)
        gd = b.node("Guide", "project:Guidance", 900, 100,
                    params=dict(px=tab["x"], py=tab["y"], pz=tab["z"], pth=tab["psi"], pk=tab["kappa"], ds=float(tab["s"][1]),
                                Ucmd=U, **ctl["guide"]),
                    constants={"NP": len(tab["x"])})
        fc = b.node("Fctl", "project:FlightCtrl", 1100, 100, params=dict(U_cmd=U, g0=P.G, **ctl["fc"]))
        tr = ctx["truth"]
        b.sig(tr, "p", gd, "p"), b.sig(tr, "vw", gd, "v"), b.sig(clock, "y", gd, "tm")
        b.sig(tr, "q", fc, "q"), b.sig(tr, "wb", fc, "wb"), b.sig(tr, "vw", fc, "vw"), b.sig(tr, "z", fc, "zp")
        b.sig(gd, "psid", fc, "psid"), b.sig(gd, "z_ref", fc, "z_ref"), b.sig(gd, "vz_ff", fc, "vz_ff")
        flap_ctrl(ctx, fc, "f_cmd")
        b.sig(fc, "sp_L", ctx["tail"]["TL"][1], "sp")
        b.sig(fc, "sp_R", ctx["tail"]["TR"][1], "sp")
        b.sig(fc, "sp_V", ctx["tail"]["TV"][1], "sp")
        b.sig(fc, "aL", ctx["crank"], "aL"), b.sig(fc, "aR", ctx["crank"], "aR")
        mt = b.node("Meas", "project:Metrics", 900, 260, params={"t_from": stat_from})
        b.sig(tr, "x", mt, "x"), b.sig(tr, "y", mt, "y"), b.sig(gd, "e_ct", mt, "e_ct"), b.sig(gd, "e_z", mt, "e_z")
        b.sig(clock, "y", mt, "tm")
        return [
            {"id": "p1", "title": "Top view: position (m)", "signals": ["Truth/x", "Truth/y", "Guide/x_ref", "Guide/y_ref"]},
            {"id": "p2", "title": "Altitude and reference (m)", "signals": ["Truth/z", "Guide/z_ref"]},
            {"id": "p3", "title": "Cross-track error (m) and altitude error (m)", "signals": ["Guide/e_ct", "Guide/e_z"]},
            {"id": "p4", "title": "Attitude (rad): roll, pitch up, yaw", "signals": ["Fctl/phi", "Fctl/phi_cmd", "Fctl/theta", "Fctl/theta_cmd"]},
            {"id": "p5", "title": "Tail deflections (rad)", "signals": ["JTL/qout", "JTR/qout", "JTV/qout"]},
            {"id": "p6", "title": "Flap angle (rad) and crank angle", "signals": ["JL1/qout", "JR1/qout"]},
            {"id": "p7", "title": "Motor: voltage, current, speed", "signals": ["Drv/source/u", "Drv/isense/y", "Drv/wsense/y"]},
            {"id": "p8", "title": "Speed (m/s) and flapping frequency command (Hz)", "signals": ["Fctl/speed", "Fctl/f_cmd"]},
            {"id": "p9", "title": "Aerodynamic power (W)", "signals": ["PaSum/P", "PaSum/Pavg"]},
        ]
    return wire


# ----------------------------------------------------------------------------- 3D scene
S_VIS = 20.0       # the bird is drawn 20 times larger than it is: the figure is 220 m wide and the viewer camera does not follow


def rpy_of(R):
    R = np.asarray(R)
    pitch = -math.asin(max(-1.0, min(1.0, R[2, 0])))
    roll = math.atan2(R[2, 1], R[2, 2])
    yaw = math.atan2(R[1, 0], R[0, 0])
    return roll, pitch, yaw


def _vis(name, geom, pos, rpy, rgba):
    return (f'      <visual name="{name}">\n        <pose>{pos[0]:.6g} {pos[1]:.6g} {pos[2]:.6g} {rpy[0]:.7g} {rpy[1]:.7g} {rpy[2]:.7g}</pose>\n'
            f'        <geometry>{geom}</geometry>\n        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def _box(sx, sy, sz):
    return f"<box><size>{sx:.6g} {sy:.6g} {sz:.6g}</size></box>"


def _cyl(r, h):
    return f"<cylinder><radius>{r:.6g}</radius><length>{h:.6g}</length></cylinder>"


def _sph(r):
    return f"<sphere><radius>{r:.6g}</radius></sphere>"


def build_scene(scale: float = S_VIS, tab: dict | None = None) -> str:
    import design as d
    s = scale
    if tab is None:
        tab = d.PATH.table(d.SIZE["A"], d.SIZE["B"], d.SIZE["Cz"], d.SIZE["z0"], ds=2.0)
    span = 2 * (P.WING_ROOT[1] + P.L1 + P.L2)
    out = ['<?xml version="1.0"?>\n<!--\n'
           '  robird (X5.15): a robotic peregrine falcon after van der Grinten et al. (2015) flying a horizontal 1:2 figure of eight.\n'
           '  Generated by design/build_model.py. Z-up, metres. The link "fuselage" is the body frame at the centre of mass (x forward, y left,\n'
           '  z up); its pose is bound to the seven pose signals. Per wing: "flap" (hub link, about the forward axis), "torsion" (about the\n'
           '  span axis, the aeroelastic twist of the root joint, bound to its deflection), "bend" (outer against inner segment). The tail has two\n'
           '  elevons (about the span axis, positive = leading edge up) and a rudder (about the vertical axis).\n'
           f'  The bird is drawn {s:g} times larger than it is ({span * s:.1f} m wing span on screen for {span:.2f} m)\n'
           '  because the figure is 220 m wide and the viewer camera does not follow; all joint offsets are scaled the same way, the pose\n'
           '  binding is in true metres. The orange spheres mark the Lissajous path.\n-->\n'
           '<sdf version="1.9">\n  <model name="robird">\n    <link name="ground">\n      <pose>0 0 0 0 0 0</pose>\n']
    out.append(_vis("floor", _box(250.0, 120.0, 0.3), (0, 0, -0.15), (0, 0, 0), "0.55 0.62 0.5 1"))
    lap = tab["lap"]
    ds = float(tab["s"][1])
    for k, sv in enumerate(np.arange(0.0, lap, 14.0)):
        i = int(round(sv / ds))
        out.append(_vis(f"path_{k:02d}", _sph(0.9), (tab["x"][i], tab["y"][i], tab["z"][i]), (0, 0, 0), "0.95 0.55 0.1 1"))
    out.append(_vis("start", _sph(1.6), (tab["x"][0], tab["y"][0], tab["z"][0]), (0, 0, 0), "0.2 0.75 0.3 1"))
    out.append("    </link>\n\n    <link name=\"fuselage\">\n      <pose>0 0 0 0 0 0</pose>\n")
    slate, belly, dark = "0.30 0.34 0.44 1", "0.88 0.88 0.84 1", "0.12 0.12 0.14 1"
    out.append(_vis("torso", _cyl(0.052 * s, 0.34 * s), (-0.03 * s, 0, 0), (0, math.pi / 2, 0), slate))
    out.append(_vis("belly", _cyl(0.042 * s, 0.26 * s), (0.0, 0, -0.016 * s), (0, math.pi / 2, 0), belly))
    out.append(_vis("rear", _cyl(0.032 * s, 0.14 * s), (-0.23 * s, 0, 0), (0, math.pi / 2, 0), slate))
    out.append(_vis("head", _sph(0.040 * s), (0.20 * s, 0, 0.012 * s), (0, 0, 0), slate))
    out.append(_vis("cheek", _sph(0.026 * s), (0.215 * s, 0, -0.01 * s), (0, 0, 0), belly))
    out.append(_vis("beak", _box(0.036 * s, 0.014 * s, 0.022 * s), (0.246 * s, 0, 0.0), (0, 0, 0), "0.9 0.75 0.2 1"))
    for sd, nm in ((1, "l"), (-1, "r")):
        out.append(_vis(f"eye_{nm}", _sph(0.009 * s), (0.218 * s, sd * 0.030 * s, 0.024 * s), (0, 0, 0), dark))
    out.append("    </link>\n")
    joints = []
    for side, tag in ((+1, "L"), (-1, "R")):
        Rf = WING_FRAME[side]
        root = np.array([P.WING_ROOT[0], side * P.WING_ROOT[1], P.WING_ROOT[2]]) * s
        rpy = rpy_of(Rf)
        c1 = sum(P.segment_strips(P.L1, *P.C1)[2]) / P.NS
        c2 = sum(P.segment_strips(P.L2, *P.C2)[2]) / P.NS
        out.append(f'\n    <link name="hub_{tag}">\n      <pose>{root[0]:.6g} {root[1]:.6g} {root[2]:.6g} {rpy[0]:.7g} {rpy[1]:.7g} {rpy[2]:.7g}</pose>\n    </link>\n')
        out.append(f'\n    <link name="wing_in_{tag}">\n      <pose>{root[0]:.6g} {root[1]:.6g} {root[2]:.6g} {rpy[0]:.7g} {rpy[1]:.7g} {rpy[2]:.7g}</pose>\n')
        zc = -0.4 * c1 * s * side
        out.append(_vis(f"wing_in_{tag}", _box(P.L1 * s, 0.010 * s, c1 * s), (P.L1 / 2 * s, 0, zc), (0, 0, 0), "0.20 0.24 0.32 1"))
        out.append(_vis(f"arm_{tag}", _cyl(0.008 * s, P.L1 * s), (P.L1 / 2 * s, 0.008 * s, 0), (0, math.pi / 2, 0), dark))
        out.append("    </link>\n")
        pos2 = root + Rf @ np.array([P.L1 * s, 0, 0])
        out.append(f'\n    <link name="hub2_{tag}">\n      <pose>{pos2[0]:.6g} {pos2[1]:.6g} {pos2[2]:.6g} {rpy[0]:.7g} {rpy[1]:.7g} {rpy[2]:.7g}</pose>\n    </link>\n')
        out.append(f'\n    <link name="wing_out_{tag}">\n      <pose>{pos2[0]:.6g} {pos2[1]:.6g} {pos2[2]:.6g} {rpy[0]:.7g} {rpy[1]:.7g} {rpy[2]:.7g}</pose>\n')
        zc2 = -0.4 * c2 * s * side
        out.append(_vis(f"wing_out_{tag}", _box(P.L2 * s, 0.008 * s, c2 * s), (P.L2 / 2 * s, 0, zc2), (0, 0, 0), "0.62 0.68 0.78 1"))
        out.append(_vis(f"tip_{tag}", _box(0.06 * s, 0.009 * s, c2 * 0.7 * s), ((P.L2 - 0.03) * s, 0, zc2 * 0.9), (0, 0, 0), "0.15 0.17 0.22 1"))
        out.append("    </link>\n")
        joints += [(f"flap_{tag}", "fuselage", f"hub_{tag}", (0, 0, 1)), (f"torsion_{tag}", f"hub_{tag}", f"wing_in_{tag}", (1, 0, 0)),
                   (f"bend_{tag}", f"wing_in_{tag}", f"hub2_{tag}", (0, 0, 1)), (f"torsion2_{tag}", f"hub2_{tag}", f"wing_out_{tag}", (1, 0, 0))]
    for tag, nm, pos, R, size in (
        ("TL", "elevon_L", (P.TAIL_X, +P.TAIL_Y, 0.0), ELEVON_FRAME, (0.13, 0.006, 0.15)),
        ("TR", "elevon_R", (P.TAIL_X, -P.TAIL_Y, 0.0), ELEVON_FRAME, (0.13, 0.006, 0.15)),
        ("TV", "rudder", (P.RUD_X, 0.0, P.RUD_Z), RUDDER_FRAME, (0.13, 0.006, 0.09)),
    ):
        rpy = rpy_of(R)
        p = np.array(pos) * s
        out.append(f'\n    <link name="{nm}_link">\n      <pose>{p[0]:.6g} {p[1]:.6g} {p[2]:.6g} {rpy[0]:.7g} {rpy[1]:.7g} {rpy[2]:.7g}</pose>\n')
        col = "0.34 0.38 0.48 1" if tag != "TV" else "0.80 0.30 0.25 1"
        out.append(_vis(nm, _box(size[0] * s, size[1] * s, size[2] * s), (-0.03 * s, 0, 0), (0, 0, 0), col))
        out.append("    </link>\n")
        joints.append((nm, "fuselage", f"{nm}_link", (0, 0, 1)))
    for name, parent, child, ax in joints:
        out.append(f'\n    <joint name="{name}" type="continuous">\n      <parent>{parent}</parent>\n      <child>{child}</child>\n'
                   f'      <axis><xyz>{ax[0]} {ax[1]} {ax[2]}</xyz></axis>\n    </joint>\n')
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


# ----------------------------------------------------------------------------- main
def main() -> int:
    import design as d
    cmt = ("X5.15: a robotic peregrine falcon (Robird) after van der Grinten et al. 2015 flies a horizontal Lissajous figure of eight. "
           "Generated by design/build_model.py from design/params.py and design/design.py; see the README.")
    doc, tab = d.closed_loop_doc(d.SIZE["t_end"], "robird", comment=cmt)
    out = ROOT / "models" / "robird.bgmodel.json"
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(doc['diagram']['nodes'])} nodes, {len(doc['diagram']['connections'])} connections)")
    tr = d.TRIM
    init = dict(U=d.SIZE["U"], heading=0.0, pitch=tr["th0"], z0=d.SIZE["z0"], f0=tr["f0"])
    t_end = 3.0
    b, ctx, plots = build("robird-trim", init, t_end, controller=open_loop(tr["f0"], tr["de0"], 0.0, 0.0))
    tdoc = finish(b, ctx, "robird-trim", init, t_end, plots,
                  "Open-loop trim model: the straight-flight trim of design/design.py (flapping frequency, elevator) with constant commands, 3 s.",
                  int(t_end * 200) + 1)
    (ROOT / "models" / "robird-trim.bgmodel.json").write_text(json.dumps(tdoc, indent=2) + "\n", encoding="utf-8", newline="\n")
    sdf = ROOT / "scenes" / "robird.sdf"
    sdf.write_text(build_scene(tab=tab), encoding="utf-8", newline="\n")
    print(f"wrote {sdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
