# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""The robust classical firmware of the double-cart lab rig as bgsim models (plan/ROBUST_CLASSICAL_PLAN.md, C1-C3).

    uv run examples/pendulum-double-cart-lab/design/robustmodels.py [--balance mm_lqr] [--plan mm_tvlqr|margin|nominal]
        [--replica <out.npz>]

writes, next to the classical models (which stay unchanged):

``library/DoubleCartLabRobustCtrl.jl``
    The 1 kHz firmware of `design/robust_ctrl.py` (LabController) on the bond graph's states: the C1 balance law
    u = -K [x_hat; u_{k-1}; u_{k-2}] with its predictor-corrector observer (the steady-state EKF gain L on the
    encoder angles and the cart position, the nominal 2-sample loop delay in the prediction), the swing-up
    (feed-forward + TVLQR from the tables), and with ``rearm = 1`` the C3 supervisor: a drop (a link more than
    20 deg from upright) switches to energy removal through the cart (a = -k_E P_x - k_x x - k_v v, applied by the
    collocated partial feedback linearisation V = (m_all a + beta v) / alpha, the rail guard first), the hanging
    LQR settles the links and the cart, and at the hanging rest the swing-up is armed again (the plan shifted to
    the cart's position and the links' turn count) with the catch inside the balance law's region z'Pz < tol.
    The output is the command of two ticks ago: the rig's 2 ms loop delay (sample, compute, PWM) is in the block.
``library/DoubleCartLabRobustTraj.jl``
    The swing-up tables, looked up at the plan time ``tau`` that the firmware publishes (re-armed swing-ups
    restart it).
``models/pendulum-double-cart-lab-robust``
    The classical scenario (hang until 1 s, timed swing-up, catch at 4 s, a 40 ms 0.45 N tip push at 7.5 s,
    end 12.5 s) with the robust balance and the 2 ms delay.
``models/pendulum-double-cart-lab-recover``
    C3: the state-driven firmware (settle, arm at rest, swing-up, region catch), a 100 ms 1.5 N knock-down push
    at 7 s, the energy removal, the hanging rest, the second swing-up and the re-catch; end 20 s.

``--replica``: the same firmware as a Python loop on the nominal twin (design model, the armature lag), for
the comparison with the bgsim runs. The models get the monitor block and the dashboards of `design/dashboards.py`. ``--expected <bg dir> --replica-npz <out.npz>``: the runs of rl/closed_loop.jl
measured, compared with the replica and written as the two models' entries of `expected.json` (others kept).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lablib as lb  # noqa: E402
import cartmodel as cm  # noqa: E402
import dashboards as dash  # noqa: E402
import robust_ctrl as rc  # noqa: E402
import robust_lin as rl  # noqa: E402
from rlmodels import _drop, _node  # noqa: E402

ROOT = HERE.parent
SCENE = "scenes/pendulum-double-cart-lab.sdf"
P_NOM = lb.nominal()
PLANT = lb.design_plant(P_NOM)
PI = math.pi
TWO_PI = 2 * math.pi

SCENARIOS = {
    "robust": {"title": "pendulum-double-cart-lab-robust", "rearm": 0, "t_end": 12.5,
               "push": {"amplitude": 0.45, "t_start": 7.5, "duration": 0.04}},
    "recover": {"title": "pendulum-double-cart-lab-recover", "rearm": 1, "t_end": 20.0,
                "push": {"amplitude": 1.5, "t_start": 7.0, "duration": 0.1}},
}


def _f(v) -> str:
    return "%.12g" % float(v)


def _vec(a) -> str:
    return "[" + ", ".join(_f(v) for v in np.ravel(a)) + "]"


def _mat(a) -> str:
    a = np.atleast_2d(np.asarray(a, float))
    return "[" + "; ".join(" ".join(_f(v) for v in row) for row in a) + "]"


def firmware_params(balance: str, plan: str) -> dict:
    """Every number of the block, taken from the harness controller (robust_ctrl.LabController)."""
    c = rc.LabController(P_NOM, balance=balance, swing=plan, mode="rearm", pfl="simple")
    A, B, _ = rl.lin_cont(P_NOM)
    Ad, Bd = rl.zoh(A, B)
    L = c.bal["L"] if c.bal["L"] is not None else rl.ekf_gain(P_NOM)
    pl = c.plan
    return {
        "balance": balance, "plan": plan, "T_s": float(pl["t_s"]), "u_max": c.u_max,
        "Kb": np.asarray(c.bal["K"], float), "Lo": np.asarray(L, float), "Ad": Ad, "Bd": Bd[:, 0], "P": c.P,
        "catch_tol": c.catch_tol, "catch_lead": c.catch_lead, "drop": c.drop, "Kh": np.asarray(c.K_hang, float),
        "k_e": c.k_e, "a_max": c.a_max, "e_lqr": c.e_lqr, "kc_x": c.kc[0], "kc_v": c.kc[1], "x_guard": c.x_guard,
        "m_all": c.m_all, "beta": c.beta, "alpha": c.alpha, "m1": c.m[0], "m2": c.m[1], "c1": c.c[0], "c2": c.c[1],
        "J1": c.J[0], "J2": c.J[1], "L1": c.L1, "g0": rc.G0,
        "tk": np.asarray(pl["tk"], float), "xs": np.asarray(pl["xs"], float), "uff": np.asarray(pl["uff"], float),
        "Ks": np.asarray(pl["Ks"], float),
    }


# ----------------------------------------------------------------------------- the blocks
CTRL_DOC = """\
Robust classical firmware of the double-cart lab rig, 1 kHz (plan/ROBUST_CLASSICAL_PLAN.md C1-C3; the bgsim
counterpart of design/robust_ctrl.py, written by design/robustmodels.py: do not edit the numbers by hand).
Modes (output phase): 0 hold, 1 swing-up, 2 balance, 3 settle (energy removal, hanging LQR).
  rearm = 0 (timed): 0 V until t_on, the swing-up from t_on (u = u_ff - K(tau) (z - z*(tau))), balance from tau = T_s.
  rearm = 1 (state-driven, C3): settle from t_on; 50 ticks at the hanging rest arm the swing-up (the plan shifted
  to the cart position and the links' turn count); the catch when z'Pz < catch_tol from tau = T_s - catch_lead
  (at T_s at the latest); a link more than `drop` from upright in balance switches back to settle.
Balance: u = -Kb [x_hat; u_{k-1}; u_{k-2}] with the observer x_hat = x_m + Lo (y - H x_m),
  x_m = Am x_hat_{k-1} + Bm u_{k-3}, y = [x, th1, th2 - th1] (angles wrapped), x_hat starts at the state at the catch.
Settle: the rail guard (brake when the stopping point passes x_guard), else while the links' energy E (cart frame,
  zero at the hanging rest) exceeds e_lqr the energy removal a = -k_e P_x - kc_x x - kc_v v through the collocated
  partial feedback linearisation V = (m_all a + beta v) / alpha, then the hanging LQR u = -Kh (z - z_hang).
The output u is the command of two ticks ago (the rig's 2 ms loop delay), clamped to +-u_max.
z = [x, th1, th2, v, w1, w2], absolute link angles from the upward vertical (sums of the joint angles)."""


def write_blocks(prm: dict, lib: Path) -> None:
    nk = len(prm["tk"])
    names = ["x", "th1", "th2", "v", "w1", "w2"]
    L = []
    A = L.append
    A("@block DoubleCartLabRobustTraj begin")
    A(f"    # Swing-up tables of the robust firmware (plan '{prm['plan']}', 10 ms knots): the feed-forward voltage, the")
    A("    # nominal state z* and the TVLQR gain row K, looked up linearly at the plan time tau that the firmware")
    A("    # DoubleCartLabRobustCtrl publishes (held at the ends). Generated by design/robustmodels.py: do not edit.")
    A(f"    @constants NK::Int = {nk}")
    A('    @inputs tau::Real, [unit = "s", description = "Plan time (from the firmware)"]')
    A("    @outputs begin")
    A('        ff::Real, [unit = "V", description = "Feed-forward voltage"]')
    A("        xs::Vec{6}")
    A("        Ks::Vec{6}")
    A("    end")
    A("    @parameters begin")
    A(f'        tk::Vec{{NK}} = {_vec(prm["tk"])}, [unit = "s", description = "Trajectory knots"]')
    A(f'        uff::Vec{{NK}} = {_vec(prm["uff"])}, [unit = "V", description = "Feed-forward voltage"]')
    for i in range(6):
        A(f'        z{i + 1}::Vec{{NK}} = {_vec(prm["xs"][:, i])}, [description = "Nominal {names[i]}"]')
    for i in range(6):
        A(f'        k{i + 1}::Vec{{NK}} = {_vec(prm["Ks"][:, i])}, [description = "TVLQR gain on {names[i]}"]')
    A("    end")
    A("    @equations begin")
    A("        ff ~ interp1(tau, tk, uff)")
    for i in range(6):
        A(f"        xs[{i + 1}] ~ interp1(tau, tk, z{i + 1})")
    for i in range(6):
        A(f"        Ks[{i + 1}] ~ interp1(tau, tk, k{i + 1})")
    A("    end")
    A("end")
    (lib / "DoubleCartLabRobustTraj.jl").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    p = prm
    L = []
    A = L.append
    A("@block DoubleCartLabRobustCtrl begin")
    for ln in CTRL_DOC.split("\n"):
        A(("    # " + ln).rstrip())
    A("    @inputs begin")
    A('        x::Real, [unit = "m", description = "Cart position"]')
    A('        v::Real, [unit = "m/s", description = "Cart velocity"]')
    A('        q1::Real, [unit = "rad", description = "Joint 1 angle: link 1 from the rail\'s x axis"]')
    A('        q2::Real, [unit = "rad", description = "Joint 2 angle: link 2 relative to link 1"]')
    A('        wq1::Real, [unit = "rad/s"]')
    A('        wq2::Real, [unit = "rad/s"]')
    A('        ff::Real, [unit = "V", description = "Feed-forward voltage (tables)"]')
    A("        xs::Vec{6}")
    A("        Ks::Vec{6}")
    A("    end")
    A("    @outputs begin")
    A('        u::Real = 0.0, [unit = "V", description = "Motor terminal voltage (the command of two ticks ago)"]')
    A('        phase::Real = 0.0, [description = "0 hold, 1 swing-up, 2 balance, 3 settle"]')
    A(f'        th1::Real = {-PI:.17g}, [unit = "rad", description = "Absolute angle of link 1 from the upward vertical, wrapped to [-pi, pi)"]')
    A(f'        th2::Real = {-PI:.17g}, [unit = "rad", description = "Absolute angle of link 2 from the upward vertical, wrapped to [-pi, pi)"]')
    A('        tau::Real = 0.0, [unit = "s", description = "Plan time at the next tick in the swing-up, else 0 (drives the tables)"]')
    A('        energy::Real = 0.0, [unit = "J", description = "Energy of the links in the cart frame, 0 at the hanging rest"]')
    A('        drops::Real = 0.0, [description = "Number of drops out of balance"]')
    A("    end")
    A("    @parameters begin")
    A('        t_on::Real = 1, [unit = "s", description = "Start of the firmware (the hold before)"]')
    A('        rearm::Real = 0, [description = "0: timed swing-up and catch; 1: state-driven (C3 settle, arm, region catch, re-arm)"]')
    A(f'        T_s::Real = {_f(p["T_s"])}, [unit = "s", description = "Swing-up duration"]')
    A(f'        u_max::Real = {_f(p["u_max"])}, [unit = "V", min = 0, description = "Voltage limit"]')
    A(f'        Kb::Vec{{8}} = {_vec(p["Kb"])}, [description = "Balance gain ({p["balance"]}) on [x_hat, u_k-1, u_k-2]"]')
    A(f'        Lo::Mat{{6,3}} = {_mat(p["Lo"])}, [description = "Observer gain on [x, th1, th2 - th1]"]')
    A(f'        Am::Mat{{6,6}} = {_mat(p["Ad"])}, [description = "1 ms ZOH model at the upright"]')
    A(f'        Bm::Vec{{6}} = {_vec(p["Bd"])}, [description = "1 ms ZOH input vector (V)"]')
    A(f'        P::Mat{{6,6}} = {_mat(p["P"])}, [description = "Catch metric (the balance law\'s cost-to-go)"]')
    A(f'        catch_tol::Real = {_f(p["catch_tol"])}, [description = "Catch region z\'Pz < catch_tol"]')
    A(f'        catch_lead::Real = {_f(p["catch_lead"])}, [unit = "s", description = "Region catch allowed from T_s - catch_lead"]')
    A(f'        drop::Real = {_f(p["drop"])}, [unit = "rad", description = "Drop detection (rearm)"]')
    A(f'        Kh::Vec{{6}} = {_vec(p["Kh"])}, [description = "Hanging LQR on the deviation from the hanging rest"]')
    A(f'        k_e::Real = {_f(p["k_e"])}, [unit = "1/(kg*s)", description = "Energy removal gain on P_x"]')
    A(f'        a_max::Real = {_f(p["a_max"])}, [unit = "m/s^2", description = "Cart acceleration limit"]')
    A(f'        e_lqr::Real = {_f(p["e_lqr"])}, [unit = "J", description = "Hand-over energy to the hanging LQR"]')
    A(f'        kc_x::Real = {_f(p["kc_x"])}, [unit = "1/s^2", description = "Cart centring (position)"]')
    A(f'        kc_v::Real = {_f(p["kc_v"])}, [unit = "1/s", description = "Cart centring (velocity)"]')
    A('        k_guard::Real = 4, [unit = "1/s^2", description = "Rail guard centring"]')
    A(f'        x_guard::Real = {_f(p["x_guard"])}, [unit = "m", description = "Rail guard on the stopping point"]')
    A(f'        m_all::Real = {_f(p["m_all"])}, [unit = "kg", description = "Cart, reflected rotor and both links"]')
    A(f'        beta::Real = {_f(p["beta"])}, [unit = "N*s/m", description = "Back-EMF and viscous friction at the cart"]')
    A(f'        alpha::Real = {_f(p["alpha"])}, [unit = "N/V", description = "Force per volt"]')
    for k in ("m1", "m2"):
        A(f'        {k}::Real = {_f(p[k])}, [unit = "kg"]')
    for k in ("c1", "c2", "L1"):
        A(f'        {k}::Real = {_f(p[k])}, [unit = "m"]')
    for k in ("J1", "J2"):
        A(f'        {k}::Real = {_f(p[k])}, [unit = "kg*m^2"]')
    A(f'        g0::Real = {_f(p["g0"])}, [unit = "m/s^2"]')
    A("    end")
    A("    @variables begin")
    A('        mode::Real = 0.0, [description = "Latched mode"]')
    A('        t_arm::Real = 0.0, [unit = "s", description = "Start of the current swing-up"]')
    A('        ox::Real = 0.0, [unit = "m", description = "Plan offset: cart position at the arming"]')
    A('        o1::Real = 0.0, [unit = "rad", description = "Plan offset: turns of link 1"]')
    A('        o2::Real = 0.0, [unit = "rad", description = "Plan offset: turns of link 2"]')
    A("        xo::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = \"Observer estimate\"]")
    A('        binit::Real = 1.0, [description = "Initialise the observer at the next balance tick"]')
    A('        damping::Real = 1.0, [description = "Energy removal latched on"]')
    A('        rest::Real = 0.0, [description = "Ticks at the hanging rest"]')
    A('        u1::Real = 0.0, [unit = "V", description = "Command of the previous tick"]')
    A('        u2::Real = 0.0, [unit = "V", description = "Command of two ticks ago"]')
    A('        u3::Real = 0.0, [unit = "V", description = "Command of three ticks ago"]')
    A("    end")
    A("    @discrete Ts = 0.001 begin")
    body = f"""\
t1 = q1 - 1.5707963267948966
t2 = t1 + q2
w1 = wq1
w2 = w1 + wq2
r1 = mod(t1 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
r2 = mod(t2 + 3.141592653589793, 6.283185307179586) - 3.141592653589793
th1 = r1
th2 = r2
# energy of the links in the cart frame and their horizontal momentum relative to the cart
v1x = -c1 * cos(t1) * w1
v1y = -c1 * sin(t1) * w1
v2x = -L1 * cos(t1) * w1 - c2 * cos(t2) * w2
v2y = -L1 * sin(t1) * w1 - c2 * sin(t2) * w2
ek = 0.5 * m1 * (v1x * v1x + v1y * v1y) + 0.5 * J1 * w1 * w1 + 0.5 * m2 * (v2x * v2x + v2y * v2y) + 0.5 * J2 * w2 * w2
ep = g0 * (m1 * c1 * (cos(t1) + 1.0) + m2 * (L1 * (cos(t1) + 1.0) + c2 * (cos(t2) + 1.0)))
E = ek + ep
Px = -(m1 * v1x + m2 * v2x)
energy = E
# mode transitions
if mode < 0.5 && t >= t_on - 1.0e-9
    if rearm > 0.5
        mode = 3.0
        damping = 1.0
        rest = 0.0
    else
        mode = 1.0
        t_arm = t_on
    end
end
if mode > 2.5
    h1 = mod(t1 + 6.283185307179586, 6.283185307179586) - 3.141592653589793
    h2 = mod(t2 + 6.283185307179586, 6.283185307179586) - 3.141592653589793
    if abs(h1) < 0.0698131700797732 && abs(h2) < 0.0698131700797732 && abs(w1) < 0.25 && abs(w2) < 0.25 && abs(x) < 0.1 && abs(v) < 0.1
        rest = rest + 1.0
        if rest >= 50.0
            mode = 1.0
            t_arm = t
            ox = x
            o1 = 6.283185307179586 * round((t1 + 3.141592653589793) / 6.283185307179586)
            o2 = 6.283185307179586 * round((t2 + 3.141592653589793) / 6.283185307179586)
        end
    else
        rest = 0.0
    end
end
ta = t - t_arm
if mode > 0.5 && mode < 1.5
    if rearm > 0.5
        if ta >= T_s - catch_lead
            zc = [x - ox, mod(t1 - o1 + 3.141592653589793, 6.283185307179586) - 3.141592653589793, mod(t2 - o2 + 3.141592653589793, 6.283185307179586) - 3.141592653589793, v, w1, w2]
            if dot(zc, P * zc) < catch_tol || ta >= T_s - 1.0e-9
                mode = 2.0
                binit = 1.0
            end
        end
    else
        if ta >= T_s - 1.0e-9
            mode = 2.0
            binit = 1.0
        end
    end
end
if mode > 1.5 && mode < 2.5 && rearm > 0.5
    if abs(r1) > drop || abs(r2) > drop
        mode = 3.0
        damping = 1.0
        rest = 0.0
        drops = drops + 1.0
    end
end
# the law of the mode
out = 0.0
if mode > 0.5 && mode < 1.5
    out = ff - (Ks[1] * (x - xs[1] - ox) + Ks[2] * (t1 - xs[2] - o1) + Ks[3] * (t2 - xs[3] - o2) + Ks[4] * (v - xs[4]) + Ks[5] * (w1 - xs[5]) + Ks[6] * (w2 - xs[6]))
end
if mode > 1.5 && mode < 2.5
    zb = [x, r1, r2, v, w1, w2]
    if binit > 0.5
        xo = zb
        binit = 0.0
    else
        xm = Am * xo + Bm * u3
        e1 = x - xm[1]
        e2 = mod(r1 - xm[2] + 3.141592653589793, 6.283185307179586) - 3.141592653589793
        e3 = mod(r2 - r1 - (xm[3] - xm[2]) + 3.141592653589793, 6.283185307179586) - 3.141592653589793
        xo = xm + Lo * [e1, e2, e3]
    end
    out = -(Kb[1] * xo[1] + Kb[2] * xo[2] + Kb[3] * xo[3] + Kb[4] * xo[4] + Kb[5] * xo[5] + Kb[6] * xo[6] + Kb[7] * u1 + Kb[8] * u2)
end
if mode > 2.5
    zh = [x, mod(t1 + 6.283185307179586, 6.283185307179586) - 3.141592653589793, mod(t2 + 6.283185307179586, 6.283185307179586) - 3.141592653589793, v, w1, w2]
    xstop = x + v * abs(v) / (1.2 * a_max)
    acc = 0.0
    lqr = 0.0
    if abs(xstop) > x_guard
        acc = ifelse(v >= 0.0, -a_max, a_max) - k_guard * x
    elseif E > e_lqr || damping > 0.5
        if E > 0.5 * e_lqr
            damping = 1.0
        else
            damping = 0.0
        end
        acc = -k_e * Px - kc_x * x - kc_v * v
    else
        lqr = 1.0
    end
    if lqr > 0.5
        out = -dot(Kh, zh)
    else
        out = (m_all * clamp(acc, -a_max, a_max) + beta * v) / alpha
    end
end
out = clamp(out, -u_max, u_max)
tau = 0.0
if mode > 0.5 && mode < 1.5
    tau = t + 0.001 - t_arm
end
phase = mode
u = u2
u3 = u2
u2 = u1
u1 = out"""
    for ln in body.split("\n"):
        A(("        " + ln).rstrip())
    A("    end")
    A("end")
    (lib / "DoubleCartLabRobustCtrl.jl").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


# ----------------------------------------------------------------------------- the models
def model(kind: str) -> dict:
    sc = SCENARIOS[kind]
    t_end = sc["t_end"]
    doc = cm.build(PLANT, "DoubleCartLab", t_end=t_end, points=int(round(t_end / 0.005)) + 1, push=sc["push"],
                   scene=SCENE, title=sc["title"])
    _drop(doc, {"Traj", "Ctrl", "Clock"})
    M = cm.Model("tmp")
    M.ids = {"n": len(doc["diagram"]["nodes"]) + 100, "b": 900, "s": 900, "w": 900}
    M.nodes, M.conns = doc["diagram"]["nodes"], doc["diagram"]["connections"]
    ctrl = M.node("Ctrl", "project:DoubleCartLabRobustCtrl", 80, 80, params={"rearm": repr(float(sc["rearm"]))})
    traj = M.node("Traj", "project:DoubleCartLabRobustTraj", 80, 300)
    M.sig(ctrl, "tau", traj, "tau")
    for port in ("ff", "xs", "Ks"):
        M.sig(traj, port, ctrl, port)
    M.sig(_node(doc, "Rail")["id"], "qout", ctrl, "x")
    M.sig(_node(doc, "Rail")["id"], "qdout", ctrl, "v")
    for j in (1, 2):
        M.sig(_node(doc, f"Joint{j}")["id"], "qout", ctrl, f"q{j}")
        M.sig(_node(doc, f"Joint{j}")["id"], "qdout", ctrl, f"wq{j}")
    M.sig(ctrl, "u", _node(doc, "Motor")["id"], "u")
    doc["plots"] = [
        {"id": "p_angles", "title": "Link angles from upright (rad)", "signals": ["Ctrl/th1", "Ctrl/th2"]},
        {"id": "p_cart", "title": "Cart position (m)", "signals": ["Rail/qout"]},
        {"id": "p_volt", "title": "Motor voltage (V) and phase", "signals": ["Ctrl/u", "Ctrl/phase"]},
        {"id": "p_energy", "title": "Link energy (J)", "signals": ["Ctrl/energy"]},
        {"id": "p_cur", "title": "Motor current (A)", "signals": ["Motor/isense/y"]},
    ]
    return doc


# ----------------------------------------------------------------------------- the Python replica
class Replica:
    """The block's tick, line by line (ideal states z = [x, th1, th2, v, w1, w2])."""

    def __init__(self, prm: dict, rearm: int, t_on: float = 1.0):
        self.p, self.rearm, self.t_on = prm, rearm, t_on
        self.mode, self.t_arm, self.off = 0, 0.0, np.zeros(3)
        self.xo = np.zeros(6)
        self.binit, self.damping, self.rest, self.drops = True, True, 0, 0
        self.u = [0.0, 0.0, 0.0]          # u1, u2, u3
        self.out_u = 0.0
        self.tau = 0.0

    def table(self, tau):
        p = self.p
        tk = p["tk"]
        f = lambda y: np.interp(tau, tk, y)  # noqa: E731
        return f(p["uff"]), np.array([f(p["xs"][:, i]) for i in range(6)]), np.array([f(p["Ks"][:, i]) for i in range(6)])

    def tick(self, t, z):
        p = self.p
        wrap = lambda a: (a + PI) % TWO_PI - PI  # noqa: E731
        x, t1, t2, v, w1, w2 = z
        r1, r2 = wrap(t1), wrap(t2)
        v1x, v1y = -p["c1"] * math.cos(t1) * w1, -p["c1"] * math.sin(t1) * w1
        v2x = -p["L1"] * math.cos(t1) * w1 - p["c2"] * math.cos(t2) * w2
        v2y = -p["L1"] * math.sin(t1) * w1 - p["c2"] * math.sin(t2) * w2
        E = (0.5 * p["m1"] * (v1x**2 + v1y**2) + 0.5 * p["J1"] * w1**2 + 0.5 * p["m2"] * (v2x**2 + v2y**2)
             + 0.5 * p["J2"] * w2**2
             + p["g0"] * (p["m1"] * p["c1"] * (math.cos(t1) + 1) + p["m2"] * (p["L1"] * (math.cos(t1) + 1) + p["c2"] * (math.cos(t2) + 1))))
        Px = -(p["m1"] * v1x + p["m2"] * v2x)
        self.E = E
        if self.mode == 0 and t >= self.t_on - 1e-9:
            if self.rearm:
                self.mode, self.damping, self.rest = 3, True, 0
            else:
                self.mode, self.t_arm = 1, self.t_on
        h1, h2 = (t1 + TWO_PI) % TWO_PI - PI, (t2 + TWO_PI) % TWO_PI - PI
        if self.mode == 3:
            if abs(h1) < math.radians(4) and abs(h2) < math.radians(4) and abs(w1) < 0.25 and abs(w2) < 0.25 and abs(x) < 0.1 and abs(v) < 0.1:
                self.rest += 1
                if self.rest >= 50:
                    self.mode, self.t_arm = 1, t
                    self.off = np.array([x, TWO_PI * round((t1 + PI) / TWO_PI), TWO_PI * round((t2 + PI) / TWO_PI)])
            else:
                self.rest = 0
        ta = t - self.t_arm
        if self.mode == 1:
            if self.rearm:
                if ta >= p["T_s"] - p["catch_lead"]:
                    zc = np.array([x - self.off[0], wrap(t1 - self.off[1]), wrap(t2 - self.off[2]), v, w1, w2])
                    if zc @ p["P"] @ zc < p["catch_tol"] or ta >= p["T_s"] - 1e-9:
                        self.mode, self.binit = 2, True
            elif ta >= p["T_s"] - 1e-9:
                self.mode, self.binit = 2, True
        if self.mode == 2 and self.rearm and (abs(r1) > p["drop"] or abs(r2) > p["drop"]):
            self.mode, self.damping, self.rest = 3, True, 0
            self.drops += 1
        out = 0.0
        u1, u2, u3 = self.u
        if self.mode == 1:
            ff, xs, Ks = self.table(self.tau)
            zr = xs + np.concatenate([self.off, np.zeros(3)])
            out = ff - Ks @ (np.asarray(z) - zr)
        elif self.mode == 2:
            zb = np.array([x, r1, r2, v, w1, w2])
            if self.binit:
                self.xo, self.binit = zb, False
            else:
                xm = p["Ad"] @ self.xo + p["Bd"] * u3
                e = np.array([x - xm[0], wrap(r1 - xm[1]), wrap(r2 - r1 - (xm[2] - xm[1]))])
                self.xo = xm + p["Lo"] @ e
            out = -(p["Kb"][:6] @ self.xo + p["Kb"][6] * u1 + p["Kb"][7] * u2)
        elif self.mode == 3:
            zh = np.array([x, h1, h2, v, w1, w2])
            xstop = x + v * abs(v) / (1.2 * p["a_max"])
            lqr = False
            if abs(xstop) > p["x_guard"]:
                acc = -math.copysign(p["a_max"], v) - 4.0 * x
            elif E > p["e_lqr"] or self.damping:
                self.damping = E > 0.5 * p["e_lqr"]
                acc = -p["k_e"] * Px - p["kc_x"] * x - p["kc_v"] * v
            else:
                lqr = True
            if lqr:
                out = -p["Kh"] @ zh
            else:
                out = (p["m_all"] * min(max(acc, -p["a_max"]), p["a_max"]) + p["beta"] * v) / p["alpha"]
        out = min(max(float(out), -p["u_max"]), p["u_max"])
        self.tau = t + 0.001 - self.t_arm if self.mode == 1 else 0.0
        self.out_u = u2
        self.u = [out, u1, u2]
        return u2


def replica_run(prm: dict, kind: str) -> dict:
    """The block on the nominal twin (design model: no Coulomb friction, cable springs or ripple; the armature lag
    L_m / R_m as the mean over the sample), the tip push of the scenario. Ticks at t = k ms, k >= 1 (bgsim)."""
    sc = SCENARIOS[kind]
    plant, step = lb.twin(lb.effects_only(P_NOM, ()))
    TS = 1e-3
    n = int(round(sc["t_end"] / TS))
    tau_a = P_NOM["L_m"] / P_NOM["R_m"]
    ea = math.exp(-TS / tau_a)
    wa = 1.0 - tau_a / TS * (1.0 - ea)
    r = Replica(prm, sc["rearm"])
    z = np.array([0.0, -PI, -PI, 0.0, 0.0, 0.0])
    u_cmd, uf = 0.0, 0.0
    out = {k: np.zeros(n + 1) for k in ("t", "x", "th1", "th2", "u", "phase", "E")}
    pu = sc["push"]
    for i in range(n + 1):
        t = i * TS
        if i >= 1:
            u_cmd = r.tick(t, z)
        out["t"][i], out["x"][i], out["th1"][i], out["th2"][i] = t, z[0], z[1], z[2]
        out["u"][i], out["phase"][i], out["E"][i] = u_cmd, r.mode, getattr(r, "E", 0.0)
        if i == n:
            break
        ua, uf = uf + (u_cmd - uf) * wa, u_cmd + (uf - u_cmd) * ea
        f = pu["amplitude"] if pu["t_start"] <= t + 0.5 * TS < pu["t_start"] + pu["duration"] else 0.0
        z = np.array(step(z, ua, f)).ravel()
    out["drops"] = r.drops
    return out


# ----------------------------------------------------------------------------- the checks
CODES = ["E101", "E102", "E103", "E106", "E901", "W201", "W202", "W205", "W206"]
DEG = math.pi / 180


def read_run(run_dir: Path) -> dict:
    """A bgsim run (manifest.json + stream.f64, rl/closed_loop.jl), the right limit at every tick."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in manifest["signals"]]
    rows = np.fromfile(run_dir / "stream.f64", dtype="<f8").reshape(-1, 1 + len(ids))
    rows = rows[np.append(rows[1:, 0] != rows[:-1, 0], True)]
    return {s: rows[:, i + 1] for i, s in enumerate(ids)} | {"t": rows[:, 0]}


def _peak(r, sig, a, b):
    m = (r["t"] >= a - 1e-9) & (r["t"] <= b + 1e-9)
    return float(np.max(np.abs(r[sig][m])))


def _transitions(t, ph):
    i = np.nonzero(np.diff(ph))[0] + 1
    return [(round(float(t[k]), 3), int(ph[k])) for k in i]


def _scene_check() -> dict:
    exp = json.loads((ROOT / "expected.json").read_text(encoding="utf-8"))["models"]
    return next(c for c in exp["pendulum-double-cart-lab"]["checks"] if c["kind"] == "scene_bindings")


def compare(bg: dict, rep: dict) -> dict:
    """bgsim against the Python replica on the twin: the phase timeline and the largest differences."""
    tp = rep["t"]
    out = {"phases_bgsim": _transitions(bg["t"], bg["Ctrl/phase"]), "phases_twin": _transitions(tp, rep["phase"])}
    for sig, k in (("Rail/qout", "x"), ("Ctrl/th1", "th1"), ("Ctrl/th2", "th2"), ("Ctrl/u", "u")):
        d = np.abs(np.interp(tp, bg["t"], bg[sig]) - rep[k])
        if k.startswith("th"):
            d = np.abs((d + PI) % TWO_PI - PI)
            near = np.abs(np.abs(rep[k] - TWO_PI * np.round(rep[k] / TWO_PI)) - PI) < 0.05   # the wrap at +-pi
            d[near] = 0.0
        out[f"max_diff_{k}"] = float(np.max(d))
    return out


def checks_robust(r: dict, prm: dict, cmpd: dict) -> list:
    tp, t_end, t_c = 7.5, 12.5, 1.0 + prm["T_s"]
    pk = {k: _peak(r, s, tp, tp + 2.0) for k, s in (("th1", "Ctrl/th1"), ("th2", "Ctrl/th2"), ("x", "Rail/qout"))}
    u_pk, x_pk = _peak(r, "Ctrl/u", 0.0, t_end), _peak(r, "Rail/qout", 0.0, t_end)
    agree = (f"bgsim and the Python replica on the twin (design/robustmodels.py --replica) agree to "
             f"{cmpd['max_diff_x']:.1e} m, {max(cmpd['max_diff_th1'], cmpd['max_diff_th2']):.1e} rad")
    return [
        _scene_check(),
        {"kind": "max_abs", "signal": "Ctrl/u", "from_t": 0.0, "to_t": 0.99, "value": 0.0, "abs": 1e-12,
         "note": "0 V until t_on = 1 s (the hold, and the 2-tick command delay starts at zero)"},
        {"kind": "max_abs", "signal": "Rail/qdout", "from_t": 0.0, "to_t": 0.99, "value": 0.0, "abs": 1e-6,
         "note": "the cart rests until the firmware starts"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": 0.5, "value": 0, "abs": 1e-9, "note": "hold"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": 2.0, "value": 1, "abs": 1e-9, "note": "swing-up (TVLQR)"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": t_c + 0.5, "value": 2, "abs": 1e-9,
         "note": f"the robust balance law ({prm['balance']}) from the timed catch at {t_c:g} s"},
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": t_c + 1.0, "to_t": tp - 0.01, "value": 0.0, "abs": 0.0035,
         "note": f"link 1 within 0.2 deg of upright before the push (measured {_peak(r, 'Ctrl/th1', t_c + 1.0, tp - 0.01) / DEG:.3f} deg; "
                 "the observer on the encoder angles, the 2 ms delay in the loop)"},
        {"kind": "max_abs", "signal": "Ctrl/th2", "from_t": t_c + 1.0, "to_t": tp - 0.01, "value": 0.0, "abs": 0.0035,
         "note": "link 2 within 0.2 deg of upright before the push"},
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": tp, "to_t": tp + 2.0, "value": round(pk["th1"], 4), "abs": 0.01,
         "note": f"the 40 ms 0.45 N tip push: link 1 deflects {pk['th1'] / DEG:.1f} deg (the classical LQR without the delay: "
                 f"10.7 deg; the multi-model LQR is softer: lower gains, more travel); {agree}"},
        {"kind": "max_abs", "signal": "Ctrl/th2", "from_t": tp, "to_t": tp + 2.0, "value": round(pk["th2"], 4), "abs": 0.005,
         "note": f"link 2 deflects {pk['th2'] / DEG:.1f} deg"},
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": tp, "to_t": tp + 2.0, "value": round(pk["x"], 4), "abs": 0.01,
         "note": f"cart travel {pk['x']:.3f} m in the push recovery"},
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": t_end - 1.0, "to_t": t_end, "value": 0.0, "abs": 0.0035,
         "note": "recovered: link 1 within 0.2 deg over the last second"},
        {"kind": "max_abs", "signal": "Ctrl/th2", "from_t": t_end - 1.0, "to_t": t_end, "value": 0.0, "abs": 0.0035,
         "note": "recovered: link 2 within 0.2 deg over the last second"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_end, "value": 24.0,
         "note": "inside the +-24 V supply"},
        {"kind": "max_abs", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_end, "value": round(u_pk, 3), "abs": 0.5,
         "note": f"peak voltage {u_pk:.1f} V (the swing-up)"},
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": 0.0, "to_t": t_end, "value": round(x_pk, 4), "abs": 0.01,
         "note": f"peak travel {x_pk:.3f} m (the swing-up), inside the +-1.0 m rail"},
        {"kind": "no_diagnostics", "codes": CODES, "note": "no solver failure, causal conflict, algebraic loop or event-limit stop"},
    ]


def checks_recover(r: dict, prm: dict, cmpd: dict) -> list:
    t_end, t_k = 20.0, 7.0
    tr = _transitions(r["t"], r["Ctrl/phase"])
    # first catch, the drop, the re-arm and the re-catch
    t_c1 = next(t for t, p in tr if p == 2)
    t_drop = next(t for t, p in tr if p == 3 and t > t_k)
    t_arm2 = next(t for t, p in tr if p == 1 and t > t_drop)
    t_c2 = next(t for t, p in tr if p == 2 and t > t_arm2)
    x_pk, e_pk = _peak(r, "Rail/qout", 0.0, t_end), _peak(r, "Ctrl/energy", t_k, t_drop + 1.0)
    agree = (f"the Python replica on the twin switches phase at the same ticks (within 1 ms) and agrees to {cmpd['max_diff_x']:.1e} m, "
             f"{max(cmpd['max_diff_th1'], cmpd['max_diff_th2']):.1e} rad")
    return [
        _scene_check(),
        {"kind": "max_abs", "signal": "Ctrl/u", "from_t": 0.0, "to_t": 0.99, "value": 0.0, "abs": 1e-12, "note": "0 V until t_on = 1 s"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": 0.5, "value": 0, "abs": 1e-9, "note": "hold"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": 1.02, "value": 3, "abs": 1e-9,
         "note": "state-driven: settle first (the links already hang at rest)"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": 2.0, "value": 1, "abs": 1e-9,
         "note": "50 ticks at the hanging rest arm the swing-up (measured at %.3f s)" % next(t for t, p in tr if p == 1)},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": round(t_c1 + 0.5, 3), "value": 2, "abs": 1e-9,
         "note": f"region catch at {t_c1:.3f} s (z'Pz < catch_tol from T_s - 0.6 s)"},
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": t_c1 + 1.0, "to_t": t_k - 0.01, "value": 0.0, "abs": 0.0035,
         "note": "balanced within 0.2 deg before the knock-down"},
        {"kind": "max_abs", "signal": "Ctrl/th2", "from_t": t_c1 + 1.0, "to_t": t_k - 0.01, "value": 0.0, "abs": 0.0035,
         "note": "link 2 within 0.2 deg before the knock-down"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": round(t_drop + 0.5, 3), "value": 3, "abs": 1e-9,
         "note": f"the 100 ms 1.5 N push at 7 s: a link passes 20 deg at {t_drop:.3f} s, the energy removal through the cart"},
        {"kind": "max_abs", "signal": "Ctrl/energy", "from_t": t_k, "to_t": round(t_drop + 1.0, 3), "value": round(e_pk, 3), "abs": 0.2,
         "note": f"the links' energy after the push peaks at {e_pk:.2f} J (upright: 3.33 J above the hanging rest)"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": round(t_arm2 + 0.5, 3), "value": 1, "abs": 1e-9,
         "note": f"settled at the hanging rest, re-armed at {t_arm2:.3f} s (the plan shifted to the cart position and the turn count)"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": round(t_c2 + 0.5, 3), "value": 2, "abs": 1e-9,
         "note": f"re-caught at {t_c2:.3f} s; {agree}"},
        {"kind": "cursor_value", "signal": "Ctrl/drops", "t": t_end, "value": 1, "abs": 1e-9, "note": "one drop, one recovery"},
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": t_end - 2.0, "to_t": t_end, "value": 0.0, "abs": 0.0035,
         "note": "upright again (wrapped angle) over the last 2 s"},
        {"kind": "max_abs", "signal": "Ctrl/th2", "from_t": t_end - 2.0, "to_t": t_end, "value": 0.0, "abs": 0.0035,
         "note": "link 2 upright again over the last 2 s"},
        {"kind": "max_abs_le", "signal": "Rail/qout", "from_t": 0.0, "to_t": t_end, "value": 0.95,
         "note": "the cart stays inside the robustness test's 0.95 m (the rail guard brakes on the stopping point)"},
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": 0.0, "to_t": t_end, "value": round(x_pk, 4), "abs": 0.02,
         "note": f"peak travel {x_pk:.3f} m, after the knock-down"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_end, "value": 24.0, "note": "inside the +-24 V supply"},
        {"kind": "no_diagnostics", "codes": CODES, "note": "no solver failure, causal conflict, algebraic loop or event-limit stop"},
    ]


def write_expected(prm: dict, bg_dir: Path, rep_path: Path) -> None:
    rep = np.load(rep_path)
    path = ROOT / "expected.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    summary = {}
    for kind, fn in (("robust", checks_robust), ("recover", checks_recover)):
        name = SCENARIOS[kind]["title"]
        r = read_run(bg_dir / name)
        rp = {k: rep[f"{kind}_{k}"] for k in ("t", "x", "th1", "th2", "u", "phase")}
        cmpd = compare(r, rp)
        summary[name] = cmpd
        print(name, json.dumps(cmpd))
        doc["models"][name] = {"run_timeout": 1200, "checks": fn(r, prm, cmpd)}
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path)


def main(argv: list[str]) -> None:
    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    prm = firmware_params(opt("--balance", "mm_lqr"), opt("--plan", "mm_tvlqr"))
    if "--expected" in argv:
        write_expected(prm, Path(opt("--expected")), Path(opt("--replica-npz")))
        return
    if "--replica" in argv:
        res = {k: replica_run(prm, k) for k in SCENARIOS}
        np.savez(opt("--replica"), **{f"{k}_{s}": v for k, r in res.items() for s, v in r.items()})
        for k, r in res.items():
            print(k, f"drops {r['drops']}, peak |x| {np.max(np.abs(r['x'])):.3f} m, peak |u| {np.max(np.abs(r['u'])):.2f} V,"
                  f" final th {r['th1'][-1]:.4f} {r['th2'][-1]:.4f}")
        return
    write_blocks(prm, ROOT / "library")
    print("wrote", ROOT / "library" / "DoubleCartLabRobustCtrl.jl", "and DoubleCartLabRobustTraj.jl",
          f"(balance {prm['balance']}, plan {prm['plan']})")
    for k, sc in SCENARIOS.items():
        path = ROOT / "models" / f"{sc['title']}.bgmodel.json"
        cm.write(path, dash.finish(model(k), k, 0.001))
        print("wrote", path)


if __name__ == "__main__":
    main(sys.argv[1:])
