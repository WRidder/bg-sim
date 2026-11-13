# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.11"]
# ///
"""Generate `models/aerial-contact.bgmodel.json` and `scenes/aerial-contact.sdf` from `design.py`.

The diagram is a plain node/connection list, so it is generated rather than hand-written: six rotor
chains, the pose composition of the manipulator chain and the three wheel contacts repeat a lot. The
rotors (`Rotor1..6`) and the omni-wheel contacts (`Wheel1..3`) are instances of the library subsystems
`library/Rotor.bgsub.json` and `library/OmniWheel.bgsub.json`, which this script writes too. Run

    uv run examples/aerial-contact/design/build_model.py

after every change of `design.py`; the model document is then reproducible from the design data.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design as d  # noqa: E402

ROOT = HERE.parent
W_HOVER = math.sqrt(d.M_TRUE * d.G / d.N_ROT / d.KT_PROP)      # rad/s hover rotor speed (the run starts in hover)
SQ2 = math.sqrt(0.5)

nodes: list[dict] = []
conns: list[dict] = []
_ids = {"n": 0, "c": 0}


def node(name: str, ref: str, x: float, y: float, params: dict | None = None, starts: dict | None = None,
         constants: dict | None = None) -> str:
    _ids["n"] += 1
    nid = f"n{_ids['n']:02d}"
    nodes.append({
        "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": x, "y": y},
        "rotation": 0, "flipX": False,
        "params": {k: str(v) for k, v in (params or {}).items()},
        "constants": {k: str(v) for k, v in (constants or {}).items()},
        "starts": {k: str(v) for k, v in (starts or {}).items()},
        "ui": {"showLabel": True, "color": None},
    })
    return nid


def conn(kind: str, a: str, ap: str, b: str, bp: str, label: str | None = None) -> None:
    _ids["c"] += 1
    conns.append({
        "id": f"{kind[0]}{_ids['c']:02d}", "kind": kind, "from": {"node": a, "port": ap},
        "to": {"node": b, "port": bp}, "route": [], "label": label,
    })


def sig(a, ap, b, bp, label=None):
    conn("signal", a, ap, b, bp, label)


def bond(a, ap, b, bp):
    conn("bond", a, ap, b, bp)


def local(name, x, y, pos, quat=(1.0, 0.0, 0.0, 0.0)):
    return node(name, "stdlib:spatial/LocalPose3D", x, y,
                params={"qw": quat[0], "qx": quat[1], "qy": quat[2], "qz": quat[3], "x": pos[0], "y": pos[1], "z": pos[2]})


def mount(name, x, y, pos, quat=(1.0, 0.0, 0.0, 0.0)):
    return node(name, "stdlib:multibond/FixedTransform3DNeutral", x, y,
                params={"qw": quat[0], "qx": quat[1], "qy": quat[2], "qz": quat[3], "x": pos[0], "y": pos[1], "z": pos[2]})


def compose(name, x, y, gp, gl):
    n = node(name, "stdlib:multibond/ComposePose3D", x, y)
    sig(gp[0], gp[1], n, "gp")
    sig(gl[0], gl[1], n, "gl")
    return n


# ----------------------------------------------------------------------------- library subsystems
def _sub_node(name: str, ref: str, x: float, y: float, params: dict | None = None, starts: dict | None = None) -> dict:
    """A node of a library subsystem: its id is its name."""
    return {"id": name, "name": name, "block": {"ref": ref}, "position": {"x": x, "y": y},
            "rotation": 0, "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {}, "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None}}


def _sub_conns(prefix: str, rows: list[tuple]) -> list[dict]:
    return [{"id": f"{prefix}{kind[0]}{k:03d}", "kind": kind, "from": {"node": a, "port": ap},
             "to": {"node": b, "port": bp}, "route": [], "label": None}
            for k, (kind, a, ap, b, bp) in enumerate(rows, start=1)]


def _sig_port(name, direction, node_, port, unit=None, size=1) -> dict:
    return {"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
            "unit": unit, "node": node_, "port": port}


def _definition(name: str, description: str, nodes_: list[dict], rows: list[tuple], ports: list[dict],
                pins: list[str]) -> dict:
    return {"format": "bgsim.subsystem", "name": name, "description": description, "ports": ports,
            "diagram": {"nodes": nodes_, "connections": _sub_conns(name.lower() + "_", rows),
                        "subsystemPorts": [], "annotations": []},
            "pins": {"params": pins, "starts": []}}


IDENTITY = {"qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0}


def omni_wheel_definition() -> dict:
    """library/OmniWheel.bgsub.json: one omni-wheel contact of the end-effector, the ContactFoot pattern
    of the other examples with the example's OmniContact (driven direction, free rollers) in place of
    ContactPoint."""
    c = d.CONTACT
    return _definition(
        "OmniWheel",
        "One omni-wheel contact of the end-effector: the wheel point in the end-effector frame (Local), its "
        "world pose (Compose), the fixed mount from the end-effector to the wheel (Mount) and the anisotropic "
        "OmniContact (Contact: Hertz normal force, traction along the driven direction at the commanded wheel "
        "speed u, free rollers across it) on the plane given at o and fr. Pin the wheel position with Local/x, "
        "Local/y, Local/z, the mount with Mount/x, Mount/y, Mount/z (the negated offsets) and the driven "
        "direction with Contact/dby, Contact/dbz. Generated by design/build_model.py.",
        [_sub_node("Local", "stdlib:spatial/LocalPose3D", 0, 0, {**IDENTITY, "x": 0.0, "y": 0.0, "z": 0.0}),
         _sub_node("Compose", "stdlib:multibond/ComposePose3D", 160, 0),
         _sub_node("Mount", "stdlib:multibond/FixedTransform3DNeutral", 0, 180, {**IDENTITY, "x": 0.0, "y": 0.0, "z": 0.0}),
         _sub_node("Contact", "project:OmniContact", 320, 120,
                   {"k": c["k"], "xref": c["xref"], "c": c["c"], "mu_d": c["mu_d"], "mu_r": c["mu_r"], "vs": c["vs"],
                    "vr": c["vr"], "eps": c["eps"], "dby": 0.0, "dbz": 1.0})],
        [("bond", "Mount", "a", "Contact", "p"),
         ("signal", "Local", "g", "Compose", "gl"),
         ("signal", "Compose", "g", "Contact", "g")],
        [{"name": "p", "kind": "power", "domain": "Spatial", "size": [6], "node": "Mount", "port": "b"},
         _sig_port("pose", "input", "Compose", "gp", size=7),
         _sig_port("o", "input", "Contact", "o", unit="m", size=3),
         _sig_port("fr", "input", "Contact", "fr", unit="1", size=9),
         _sig_port("u", "input", "Contact", "u", unit="m/s"),
         _sig_port("f_n", "output", "Contact", "f_n", unit="N")],
        ["Local/x", "Local/y", "Local/z", "Mount/x", "Mount/y", "Mount/z", "Contact/dby", "Contact/dbz"])


def rotor_definition() -> dict:
    """library/Rotor.bgsub.json: one rotor chain, ESC -> ElectricDrive -> Propeller (the quadcopter's
    Rotor, with this example's values and the hover speed as the start)."""
    p = d.PARAMS
    return _definition(
        "Rotor",
        "One rotor: the electronic speed controller (Esc, a speed PI with the motor-model feed-forward), the "
        "stdlib ElectricDrive bond graph motor with the rotor and propeller inertia (Drive, starting at the "
        "hover speed) and the propeller (Prop: thrust and drag torque). Every rotor has the same values, so "
        "nothing is pinned. Generated by design/build_model.py.",
        [_sub_node("Esc", "project:Esc", 0, 0,
                   {"k_e": d.K_E, "k_t": d.K_T, "R_w": d.R_W, "kQ": d.KQ_PROP, "b_m": d.B_M,
                    "Kp": p["esc"]["Kp"], "Ki": p["esc"]["Ki"]}),
         _sub_node("Drive", "stdlib:drives/ElectricDrive", 200, 0,
                   {"R_w": d.R_W, "L": d.L_W, "k_t": d.K_T, "J_m": d.J_M, "b_m": d.B_M},
                   starts={"rotor/w": f"{W_HOVER:.6g}"}),
         _sub_node("Prop", "project:Propeller", 400, 0, {"kT": d.KT_PROP, "kQ": d.KQ_PROP})],
        [("wire", "Drive", "shaft", "Prop", "shaft"),
         ("signal", "Esc", "u", "Drive", "u"),
         ("signal", "Drive", "w", "Esc", "w")],
        [_sig_port("w_cmd", "input", "Esc", "w_cmd"),
         _sig_port("vbat", "input", "Esc", "vbat"),
         _sig_port("T", "output", "Prop", "T", unit="N"),
         _sig_port("i", "output", "Drive", "i", unit="A"),
         _sig_port("w", "output", "Drive", "w", unit="rad/s"),
         _sig_port("P_el", "output", "Drive", "P_el", unit="W")],
        [])


def build() -> dict:
    p = d.PARAMS
    lqr = p["lqr"]
    N = d.N_ROT
    L = d.L_M
    # ------------------------------------------------------------------ multirotor (multibond floating body)
    world = node("World", "stdlib:multibond/GroundSpatial", 40, 420)
    free = node("Free", "stdlib:spatial/Free3D", 220, 420, starts={"px": d.X0, "pz": d.Z0})
    body = node("Body", "stdlib:spatial/RigidBody3D", 420, 420,
                params={"m": d.M_B, "J": p["J"], "g0": d.G}, starts={"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
    wrench = node("Wrench", "stdlib:multibond/ExternalWrenchSpatial", 420, 560)
    bond(world, "p", free, "parent")
    bond(free, "child", body, "p")
    bond(wrench, "p", body, "p")
    for k in range(1, 7):
        se = node(f"FreeSe{k}", "stdlib:bondgraph/Se", 220, 560 + 50 * k, params={"e": "0.0"})
        bond(se, "p", free, f"drive{k}")
    sig(free, "pose", body, "g", "pose chart (qw qx qy qz x y z)")

    # ------------------------------------------------------------------ propulsion: ESC -> ElectricDrive -> Propeller x6
    rw = node("RW", "project:RotorWrench", 620, 560,
              params={"rx": p["rx"], "ry": p["ry"], "spin": p["spin"], "onev": p["onev"], "kt": d.K_T, "bm": d.B_M, "Jr": d.J_M,
                      "cdx": d.CD[0], "cdy": d.CD[1], "cdz": d.CD[2], "cdr": d.CDR})
    for axis in ("tx", "ty", "tz", "fx", "fy", "fz"):
        sig(rw, axis, wrench, axis)
    pk_t = node("PackT", "project:Pack6", 900, 700)
    pk_i = node("PackI", "project:Pack6", 900, 800)
    pk_w = node("PackW", "project:Pack6", 900, 900)
    sig(pk_t, "y", rw, "T")
    sig(pk_i, "y", rw, "i")
    sig(pk_w, "y", rw, "w")
    sig(body, "V", rw, "V")
    supply = node("Supply", "stdlib:sources/Constant", 1100, 40, params={"value": d.V_SUPPLY})
    rotors = []
    for k in range(1, N + 1):
        ro = node(f"Rotor{k}", "project:Rotor", 1640, 60 + 200 * (k - 1))
        sig(supply, "y", ro, "vbat")
        sig(ro, "T", pk_t, f"u{k}")
        sig(ro, "i", pk_i, f"u{k}")
        sig(ro, "w", pk_w, f"u{k}")
        rotors.append(ro)

    # ------------------------------------------------------------------ manipulator: servo, tube, rubber mount, end-effector
    # frames: joint frame j on the multirotor: x_j = x_b, y_j = -z_b, z_j = y_b (a rotation of -90 deg about x), so the joint
    # angle q is a rotation about +y_b and the arm elevation is mu = -q. The arm body frame is the joint child frame turned back
    # by +90 deg about x (qj_inv), so at q = 0 the arm, the tip and the end-effector frames are aligned with the multirotor frame
    # (x forward, y left, z up) and the wheel geometry of the end-effector is written in world-aligned axes.
    qj = (SQ2, -SQ2, 0.0, 0.0)
    qj_inv = (SQ2, SQ2, 0.0, 0.0)
    loc_s = local("LocS", 220, 1300, (0, 0, 0), qj)
    mnt_s = mount("MountS", 420, 1300, (0, 0, 0), qj_inv)
    servo = node("Servo", "stdlib:spatial/Revolute3D", 620, 1300,
                 params={"kr": 500.0, "br": 1.5, "kt": 1.0e5, "bt": 300.0, "q0": 0.0})
    link_a = mount("LinkA", 820, 1300, (L / 2, 0, 0), qj_inv)
    arm = node("Arm", "stdlib:spatial/RigidBody3D", 1020, 1300,
               params={"m": d.M_ARM, "J": "[" + ", ".join(f"{v:.9g}" for v in d.J_ARM) + "]", "g0": d.G},
               starts={"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
    bond(body, "p", mnt_s, "b")
    bond(mnt_s, "a", servo, "parent")
    bond(servo, "child", link_a, "a")
    bond(link_a, "b", arm, "p")
    servo_ctl = node("ServoCtl", "project:ArmServo", 620, 1450,
                     params={"Kp": d.SERVO_KP, "Kd": d.SERVO_KD, "tau_max": d.SERVO_TAU_MAX})
    servo_t = node("ServoT", "stdlib:bondgraph/MSe", 820, 1450, params={})
    sig(servo, "qout", servo_ctl, "q")
    sig(servo, "qdout", servo_ctl, "qd")
    sig(servo_ctl, "tau", servo_t, "u")
    bond(servo_t, "p", servo, "drive")

    tip_m = mount("TipM", 1020, 1450, (-L / 2, 0, 0))
    rub = node("Rub", "stdlib:spatial/Spherical3D", 1220, 1300, params={"kt": 1.0e5, "bt": 150.0})
    link_e = mount("LinkE", 1420, 1300, (d.EE_CX, 0, 0))
    ee = node("EE", "stdlib:spatial/RigidBody3D", 1620, 1300,
              params={"m": d.M_EE, "J": "[" + ", ".join(f"{v:.9g}" for v in d.J_EE) + "]", "g0": d.G},
              starts={"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
    bond(arm, "p", tip_m, "b")
    bond(tip_m, "a", rub, "parent")
    bond(rub, "child", link_e, "a")
    bond(link_e, "b", ee, "p")
    rub_k = node("RubK", "project:RubberMount", 1220, 1450, params={"k": d.RUBBER_K, "b": d.RUBBER_B})
    sig(rub, "qrel", rub_k, "qrel")
    sig(rub, "omega", rub_k, "om")
    for i in (1, 2, 3):
        m = node(f"RubT{i}", "stdlib:bondgraph/MSe", 1420 + 100 * i, 1450, params={})
        sig(rub_k, f"t{i}", m, "u")
        bond(m, "p", rub, f"drive{i}")
    # pose chain (world poses of the frames; the bodies read them for gravity and the contacts for the wall)
    loc_arm = local("LocArm", 820, 1650, (L / 2, 0, 0), qj_inv)
    loc_tip = local("LocTip", 1020, 1650, (L, 0, 0), qj_inv)
    loc_ee = local("LocEE", 1420, 1650, (d.EE_CX, 0, 0))
    pa = compose("PoseA", 420, 1750, (free, "pose"), (loc_s, "g"))
    pj = compose("PoseJ", 620, 1750, (pa, "g"), (servo, "pose"))
    parm = compose("PoseArm", 820, 1750, (pj, "g"), (loc_arm, "g"))
    ptip0 = compose("PoseTip0", 1020, 1750, (pj, "g"), (loc_tip, "g"))
    ptip1 = compose("PoseTip", 1220, 1750, (ptip0, "g"), (rub, "pose"))
    pee = compose("PoseEE", 1420, 1750, (ptip1, "g"), (loc_ee, "g"))
    sig(parm, "g", arm, "g")
    sig(pee, "g", ee, "g")
    # the arm tip relative to the multirotor (for the 3D axis-sign check)
    rb1 = compose("RelA", 620, 1900, (loc_s, "g"), (servo, "pose"))
    rb2 = compose("RelTip", 1020, 1900, (rb1, "g"), (loc_tip, "g"))

    # ------------------------------------------------------------------ the wall and the three omni-wheel contacts
    wall = node("Wall", "stdlib:contact/ContactSurface", 1700, 1500,
                params={"ox": d.WALL_X, "oy": 0.0, "oz": 0.0, "nx": -1.0, "ny": 0.0, "nz": 0.0})
    omni = node("Omni", "project:OmniDrive", 1700, 1650,
                params={"v_max": d.V_EE_MAX, "r_w": d.WHEEL_R, "a1": d.WHEEL_ALPHA[0], "a2": d.WHEEL_ALPHA[1], "a3": d.WHEEL_ALPHA[2]})
    wheels = []
    for k in (1, 2, 3):
        a = d.WHEEL_ALPHA[k - 1]
        pos = (d.EE_WX - d.EE_CX, d.EE_RHO * math.cos(a), d.EE_RHO * math.sin(a))
        ct = node(f"Wheel{k}", "project:OmniWheel", 1900 + 200 * (k - 1), 1380,
                  params={"Local/x": pos[0], "Local/y": pos[1], "Local/z": pos[2],
                          "Mount/x": -pos[0], "Mount/y": -pos[1], "Mount/z": -pos[2],
                          "Contact/dby": -math.sin(a), "Contact/dbz": math.cos(a)})
        bond(ee, "p", ct, "p")
        sig(pee, "g", ct, "pose")
        sig(wall, "o", ct, "o")
        sig(wall, "fr", ct, "fr")
        sig(omni, f"u{k}", ct, "u")
        wheels.append(ct)
    wf = node("WallForce", "project:WallForce", 2650, 1450, params={"m_d": d.M_D, "g0": d.G})
    for k, ct in enumerate(wheels, start=1):
        sig(ct, "f_n", wf, f"f{k}")

    # ------------------------------------------------------------------ truth taps and sensors
    truth = node("Truth", "project:Truth", 620, 420)
    sig(free, "pose", truth, "pose")
    sig(body, "V", truth, "V")
    truth_e = node("TruthE", "project:Truth", 1850, 1250)
    sig(pee, "g", truth_e, "pose")
    sig(ee, "V", truth_e, "V")
    specf = node("SpecF", "project:SpecForce", 620, 760, params={"g0": d.G})
    sig(body, "V", specf, "V")
    sig(free, "pose", specf, "pose")
    imu = node("Imu", "project:ImuSensor", 820, 760,
               params={"bgc": p["lp"]["bgc"], "agc": p["lp"]["agc"], "bac": p["lp"]["bac"], "aac": p["lp"]["aac"]})
    gps = node("Gps", "project:GpsSensor", 820, 900)
    sig(truth, "wb", imu, "w")
    sig(specf, "fs", imu, "f", "true specific force (thrust, drag and the arm reaction)")
    sig(truth, "p", gps, "p")
    sig(truth, "vw", gps, "v")
    sig(truth, "yaw", gps, "yaw")

    # ------------------------------------------------------------------ controllers
    nav = node("Nav", "project:NavFilter", 1020, 60, params={**p["nav"], "g0": d.G},
               starts={"ps": f"[{d.X0}, 0.0, {d.Z0}]"})
    clock = node("Clock", "stdlib:sources/Time", 820, 60)
    zero = node("Zero", "stdlib:sources/Constant", 820, 200, params={"value": 0.0})
    armed = node("Armed", "stdlib:sources/Constant", 820, 280, params={"value": 1.0})
    sc = d.SCEN
    sup = node("Sup", "project:Supervisor", 1020, 220,
               params={"p0": f"[{d.X0}, 0.0, {d.Z0}]", "t_move": sc["t_move1"], "d_move": sc["d_move1"], "dx_move": sc["dx1"],
                       "t_engage": sc["t_engage"], "t_disengage": sc["t_disengage"], "wall_x": d.WALL_X, "d_guard": sc["d_guard"],
                       "d_contact": sc["d_contact"], "C": sc["C"], "L_m": d.L_M, "e_wx": d.EE_WX,
                       "th0": math.radians(sc["theta0"]), "th1": math.radians(sc["theta1"]), "T1": sc["t_ramp1"],
                       "th2": math.radians(sc["theta2"]), "T2s": sc["t_ramp2_start"], "T2": sc["t_ramp2"],
                       "t_loc": sc["t_loc"], "t_up": sc["t_up"], "t_pause": sc["t_pause"], "t_down": sc["t_down"],
                       "v_cmd": sc["v_cmd"]})
    pos = node("Pos", "project:PositionCtrl", 1220, 220,
               params={"m_nom": d.M_NOM, "g0": d.G, **{k: v for k, v in p["outer"].items() if k in ("Kp_xy", "Kv_xy", "Ki_xy", "Kp_z", "Kv_z", "Ki_z")}})
    eng = node("Eng", "project:EngageCtrl", 1220, 380,
               params={"m_nom": d.M_NOM, "g0": d.G, "Kp_z": p["outer"]["Kp_z"], "Kv_z": p["outer"]["Kv_z"], "Ki_z": p["outer"]["Ki_z"]})
    con = node("Con", "project:ContactCtrl", 1220, 520,
               params={"th": lqr["th"], "Ktab": lqr["Ktab"], "sa_tab": lqr["sa"], "dth": math.radians(5.0), "m_d": d.M_D, "g0": d.G,
                       "tau_eq": lqr["tau_y_eq"]}, constants={"NT": lqr["n"]})
    sel = node("Sel", "project:PhaseSelect", 1420, 380)
    att = node("Att", "project:AttitudeCtrl", 1420, 220, params={"K_rp": p["outer"]["K_rp"]})
    rate = node("Rate", "project:RateCtrl", 1420, 520, params={**p["rate"], "tau_ff": f"[0.0, {p['tau_ff']:.9g}, 0.0]"})
    mix = node("Mix", "project:Mixer", 1220, 640,
               params={"Minv": p["Minv"], "kT": d.KT_PROP, "T_min": d.T_MIN, "T_max": d.T_MAX})
    unp = node("Unp", "project:Unpack6", 1020, 640)
    sig(clock, "y", sup, "tm")
    sig(nav, "p", sup, "p"), sig(nav, "v", sup, "v"), sig(nav, "q", sup, "q")
    sig(imu, "gyro_f", nav, "gyro"), sig(imu, "acc_f", nav, "acc")
    sig(gps, "pm", nav, "pm"), sig(gps, "vm", nav, "vm"), sig(gps, "psim", nav, "psim"), sig(gps, "n", nav, "n")
    for a_, b_ in (("p_sp", "p_sp"), ("v_sp", "v_sp"), ("a_sp", "a_sp"), ("psi_sp", "psi_sp")):
        sig(sup, a_, pos, b_)
    sig(sup, "a_pos", pos, "armed")
    sig(nav, "p", pos, "p"), sig(nav, "v", pos, "v"), sig(nav, "q", pos, "q")
    sig(nav, "p", eng, "p"), sig(nav, "v", eng, "v"), sig(nav, "q", eng, "q")
    sig(sup, "theta_sp", eng, "theta_sp"), sig(sup, "psi_sp", eng, "psi_sp"), sig(sup, "z_hold", eng, "z_sp"), sig(sup, "sel_eng", eng, "active")
    sig(nav, "q", con, "q"), sig(nav, "w", con, "w"), sig(sup, "theta_sp", con, "theta_sp"), sig(sup, "psi_sp", con, "psi_sp")
    sig(pos, "qd", sel, "qd_pos"), sig(pos, "F", sel, "F_pos"), sig(eng, "qd", sel, "qd_eng"), sig(eng, "F", sel, "F_eng")
    sig(con, "F", sel, "F_lqr"), sig(sup, "sel_eng", sel, "sel_eng"), sig(sup, "sel_lqr", sel, "sel_lqr")
    sig(nav, "q", att, "q"), sig(sel, "qd", att, "qd"), sig(zero, "y", att, "yaw_rate_ff")
    sig(att, "w_sp", rate, "w_sp"), sig(nav, "w", rate, "w"), sig(sup, "a_rate", rate, "armed")
    sig(sel, "F", mix, "F"), sig(rate, "tau", mix, "tau"), sig(con, "tau", mix, "tau2"), sig(sup, "sel_lqr", mix, "sel")
    sig(armed, "y", mix, "armed")
    sig(mix, "w_cmd", unp, "u")
    for k in range(N):
        sig(unp, f"y{k + 1}", rotors[k], "w_cmd")
    sig(sup, "cmd", omni, "cmd")
    sig(sup, "mu_sp", servo_ctl, "mu_sp")
    sig(sup, "theta_sp", wf, "theta_sp")

    plots = [
        {"id": "p1", "title": "Multirotor position and set-point (m)",
         "signals": ["Truth/x", "Truth/y", "Truth/z", "Sup/p_sp[1]", "Sup/p_sp[3]"]},
        {"id": "p2", "title": "Phase (0 free, 1 engage, 2 contact, 3 disengage) and wheel plane to wall (m)",
         "signals": ["Sup/phase", "Sup/d_ee"]},
        {"id": "p3", "title": "Normal force on the wall, per wheel and total (N), and m g tan(theta_sp)",
         "signals": ["Wheel1/Contact/f_n", "Wheel2/Contact/f_n", "Wheel3/Contact/f_n", "WallForce/N", "WallForce/Npred"]},
        {"id": "p4", "title": "Multirotor roll, pitch, yaw (rad) and pitch reference",
         "signals": ["Truth/roll", "Truth/pitch", "Truth/yaw", "Sup/theta_sp"]},
        {"id": "p5", "title": "End-effector height (m) and velocity command", "signals": ["TruthE/z", "Sup/cmd[2]"]},
        {"id": "p6", "title": "Arm elevation mu and its set-point (rad)", "signals": ["ServoCtl/mu", "Sup/mu_sp"]},
        {"id": "p7", "title": "Rotor speeds (rad/s)", "signals": [f"Rotor{k}/Drive/rotor/w" for k in range(1, N + 1)]},
        {"id": "p8", "title": "Contact controller: thrust (N) and torques (N m)", "signals": ["Con/F", "Con/tau[1]", "Con/tau[2]", "Con/tau[3]"]},
        {"id": "p9", "title": "Wheel slip along the driven direction (m/s)", "signals": ["Wheel1/Contact/sd", "Wheel2/Contact/sd", "Wheel3/Contact/sd"]},
    ]
    bindings = [
        {"target": "link:body", "property": "pose",
         "signal": ["Truth/q[1]", "Truth/q[2]", "Truth/q[3]", "Truth/q[4]", "Truth/x", "Truth/y", "Truth/z"]},
        {"target": "link:ee", "property": "pose",
         "signal": ["TruthE/q[1]", "TruthE/q[2]", "TruthE/q[3]", "TruthE/q[4]", "TruthE/x", "TruthE/y", "TruthE/z"]},
        {"target": "joint:arm", "property": "position", "signal": "Servo/qout", "gain": 1.0, "offset": 0.0},
    ]
    for k in range(1, N + 1):
        bindings.append({"target": f"joint:rotor_{k}", "property": "position", "signal": f"Rotor{k}/Drive/rotor/phi",
                         "gain": float(d.SPIN[k - 1]), "offset": 0.0})
    for k in (1, 2, 3):
        bindings.append({"target": f"joint:wheel_{k}", "property": "position", "signal": f"Omni/phi{k}", "gain": 1.0, "offset": 0.0})

    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "aerial-contact",
        "$comment": "X5.8: the multimodal aerial manipulator of Wopereis et al. 2018. Generated by design/build_model.py from design/design.py; see the README.",
        "diagram": {"nodes": nodes, "connections": conns, "subsystemPorts": [], "annotations": []},
        "settings": {"t_start": 0.0, "t_end": d.SCEN["t_end"], "solver": "auto", "reltol": 1e-4, "abstol": 1e-6,
                     "max_step": None, "output": {"mode": "points", "points": int(d.SCEN["t_end"] * 50) + 1}, "event_limit": 100000},
        "plots": plots,
        "scene": {"file": "scenes/aerial-contact.sdf"},
        "bindings": bindings,
    }


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
    out = []
    out.append('''<?xml version="1.0"?>
<!--
  aerial-contact (X5.8): the hexarotor with its arm, the rubber-mounted end-effector with three omni-wheels and the
  wall. Generated by design/build_model.py from the numbers of design/design.py.

  Z-up, metres. The link "body" is the multirotor frame at the centre of mass (x forward, y left, z up); its pose is bound to
  the seven pose signals of the model. The arm link "arm_link" is a child of "body" on the revolute joint "arm" (axis +y, bound to the servo
  angle q = -mu); the six rotor links turn about the body z axis (joints "rotor_1" .. "rotor_6"). The end-effector "ee" is
  a root link whose world pose is bound (the rubber mount between the tube and the end-effector is a compliant spherical
  joint, so its pose is a signal, not a joint); its three omni-wheels turn on the continuous joints "wheel_1" .. "wheel_3"
  (bound to the integrated wheel angles). The wall is the plane x = 1.6 m; the wheels roll on its face (x = 1.6 m).
-->
<sdf version="1.9">
  <model name="aerial-contact">
    <link name="world_fixed">
      <pose>0 0 0 0 0 0</pose>
''')
    out.append(_visual("floor", _box(5.0, 4.0, 0.02), (0.8, 0.0, -0.01, 0, 0, 0), "0.62 0.64 0.66 1"))
    out.append(_visual("wall", _box(0.04, 3.0, 2.4), (d.WALL_X + 0.02, 0.0, 1.2, 0, 0, 0), "0.78 0.76 0.72 1"))
    for i, z in enumerate((0.5, 1.0, 1.5, 2.0)):
        out.append(_visual(f"wall_mark_{i}", _box(0.002, 0.5, 0.01), (d.WALL_X - 0.001, 0.0, z, 0, 0, 0), "0.2 0.3 0.6 1"))
    out.append("    </link>\n\n    <link name=\"body\">\n      <pose>0 0 0 0 0 0</pose>\n")
    out.append(_visual("plate_bottom", _box(0.24, 0.20, 0.012), (-0.02, 0, -0.03, 0, 0, 0), "0.1 0.1 0.12 1"))
    out.append(_visual("battery_box", _box(0.16, 0.06, 0.04), (-0.03, 0, -0.06, 0, 0, 0), "0.25 0.3 0.7 1"))
    out.append(_visual("plate_top", _box(0.20, 0.17, 0.006), (-0.02, 0, 0.02, 0, 0, 0), "0.15 0.15 0.18 1"))
    out.append(_visual("electronics", _box(0.08, 0.06, 0.02), (-0.04, 0, 0.035, 0, 0, 0), "0.2 0.55 0.35 1"))
    out.append(_visual("nose", _box(0.04, 0.04, 0.016), (0.11, 0, 0.0, 0, 0, 0), "0.9 0.15 0.15 1"))
    out.append(_visual("servo", _box(0.05, 0.034, 0.05), (0.07, 0, -0.01, 0, 0, 0), "0.15 0.15 0.5 1"))
    for k in range(d.N_ROT):
        rx, ry = float(d.RX[k]), float(d.RY[k])
        yaw = math.atan2(ry, rx)
        out.append(_visual(f"arm_{k + 1}", _box(d.ARM_R, 0.024, 0.014), (rx / 2, ry / 2, 0.0, 0, 0, yaw), "0.12 0.12 0.14 1"))
        out.append(_visual(f"motor_{k + 1}", _cyl(0.0145, 0.036), (rx, ry, 0.018, 0, 0, 0), "0.7 0.7 0.72 1"))
    out.append("    </link>\n")
    for k in range(d.N_ROT):
        rx, ry = float(d.RX[k]), float(d.RY[k])
        out.append(f'\n    <link name="rotor_{k + 1}_link">\n      <pose>{rx:.5g} {ry:.5g} 0.05 0 0 0</pose>\n')
        out.append(_visual(f"blade_{k + 1}", _box(0.254, 0.018, 0.003), (0, 0, 0, 0, 0, 0), "0.08 0.08 0.1 1"))
        out.append(_visual(f"tip_{k + 1}", _box(0.05, 0.019, 0.0035), (0.102, 0, 0, 0, 0, 0), "1.0 0.5 0.05 1"))
        out.append(_visual(f"hub_{k + 1}", _cyl(0.012, 0.012), (0, 0, 0, 0, 0, 0), "0.8 0.8 0.82 1"))
        out.append("    </link>\n")
    # the carbon tube: its frame is the joint child frame (origin at the multirotor centre of mass, x along the tube)
    out.append('\n    <link name="arm_link">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_visual("tube", _cyl(0.006, d.L_M), (d.L_M / 2, 0, 0, 0, math.pi / 2, 0), "0.08 0.08 0.09 1"))
    out.append(_visual("horn", _cyl(0.02, 0.01), (0.0, 0, 0, math.pi / 2, 0, 0), "0.7 0.7 0.72 1"))
    out.append("    </link>\n")
    # the end-effector: its frame is the centre of mass; the elastic joint is at -EE_CX, the wheel plane at EE_WX - EE_CX
    out.append('\n    <link name="ee">\n      <pose>0 0 0 0 0 0</pose>\n')
    out.append(_visual("mount", _cyl(0.014, 0.02), (-d.EE_CX + 0.0, 0, 0, 0, math.pi / 2, 0), "0.15 0.5 0.2 1"))
    out.append(_visual("base", _cyl(0.062, 0.016), (0.015, 0, 0, 0, math.pi / 2, 0), "0.3 0.3 0.35 1"))
    out.append(_visual("brush", _cyl(0.02, 0.02), (d.EE_WX - d.EE_CX - 0.01, 0, 0, 0, math.pi / 2, 0), "0.9 0.8 0.2 1"))
    out.append("    </link>\n")
    for k in (1, 2, 3):
        a = float(d.WHEEL_ALPHA[k - 1])
        cx = d.EE_WX - d.EE_CX - d.WHEEL_R
        out.append(f'\n    <link name="wheel_{k}_link">\n      <pose>{cx:.5g} {d.EE_RHO * math.cos(a):.5g} {d.EE_RHO * math.sin(a):.5g} 0 0 0</pose>\n')
        # the wheel axle is along the radius (cos a, sin a) in the y-z plane
        out.append(_visual(f"tyre_{k}", _cyl(d.WHEEL_R, 0.014), (0, 0, 0, 0, 0, 0), "0.1 0.1 0.1 1"))
        out.append(_visual(f"wheel_mark_{k}", _box(0.012, 0.014, 0.012), (d.WHEEL_R * 0.8, 0, 0, 0, 0, 0), "0.9 0.2 0.2 1"))
        out.append("    </link>\n")
    out.append('\n    <joint name="arm" type="revolute">\n      <parent>body</parent>\n      <child>arm_link</child>\n'
               '      <axis><xyz>0 1 0</xyz></axis>\n    </joint>\n')
    for k in range(1, d.N_ROT + 1):
        out.append(
            f'\n    <joint name="rotor_{k}" type="continuous">\n      <parent>body</parent>\n'
            f'      <child>rotor_{k}_link</child>\n      <axis><xyz>0 0 1</xyz></axis>\n    </joint>\n'
        )
    for k in (1, 2, 3):
        a = float(d.WHEEL_ALPHA[k - 1])
        out.append(
            f'\n    <joint name="wheel_{k}" type="continuous">\n      <parent>ee</parent>\n'
            f'      <child>wheel_{k}_link</child>\n      <axis><xyz>0 {math.cos(a):.6g} {math.sin(a):.6g}</xyz></axis>\n    </joint>\n'
        )
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


def sync_contact_library() -> None:
    """The default of `Ktab` in `library/ContactCtrl.jl` is the designed table (the block compiles and runs on its own)."""
    path = ROOT / "library" / "ContactCtrl.jl"
    text = path.read_text(encoding="utf-8")
    new = re.sub(r"(Ktab::Mat\{NT,24\} = )\[[^\]]*\](, \[description)", lambda m: m.group(1) + d.PARAMS["lqr"]["Ktab"] + m.group(2), text)
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")


def main() -> int:
    sync_contact_library()
    for definition in (omni_wheel_definition(), rotor_definition()):
        path = ROOT / "library" / f"{definition['name']}.bgsub.json"
        path.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    model = build()
    out = ROOT / "models" / "aerial-contact.bgmodel.json"
    out.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(nodes)} nodes, {len(conns)} connections)")
    sdf = ROOT / "scenes" / "aerial-contact.sdf"
    sdf.write_text(build_scene(), encoding="utf-8", newline="\n")
    print(f"wrote {sdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
