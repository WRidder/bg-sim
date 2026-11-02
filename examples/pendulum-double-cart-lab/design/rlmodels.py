# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""The RL variants of the double-cart lab rig (plan/RL_PLAN.md, R0.7).

    uv run examples/pendulum-double-cart-lab/design/rlmodels.py [--rl] [--cases <cases.json> <out dir>]

writes, next to the classical models (which stay unchanged):

``pendulum-double-cart-lab-plant``
    The plant only, for the FMU the RL environment steps. The firmware (Clock, Traj, Ctrl) and the push
    pulse are gone; the motor voltage ``V`` and the tip push ``F_push`` are ``ExportInput``s, the
    sensors ``ExportOutput``s: the cart position ``x``, the joint encoder angles ``q1`` (link 1 from the
    rail's x axis) and ``q2`` (link 2 relative to link 1), plus ``v``, ``w1``, ``w2`` and the motor
    current ``i_m`` for the critic. The physical parameters are the globals of `design/realism.json`
    under their own names: every parameter of the bond graph with min < max is exposed in the FMU with
    the realism range (`rl/export_plant.jl --realism=...`); the fixed ones are plain globals; the lumped
    link mass, centre of mass and inertia (`lablib.link_props`), the summed viscous frictions and the
    static pivot deflections are driven globals, recomputed at the FMU's initialisation. The realism
    terms outside the bond-graph elements (R1: Coulomb friction of the joints, the carriage and the
    motor, the cable springs, commutation ripple and cogging) are the forces of the project block
    ``LabRealism`` (the twin's laws, from the plant's own signals) on a rail force source and the joint
    drives, with their globals exposed too (range down to 0, so the FMU also runs the design model).
    The sensors (quantisation, noise) and the loop delay are the env wrapper's (rl/rlpend/renv.py).

``pendulum-double-cart-lab-rl`` (``--rl``)
    The same plant (nominal values) with the trained policy block ``project:DoubleCartLabPolicy``
    (written by ``rl/make_policy_block.py --rig lab``) as the firmware: the encoders in, the motor
    voltage out. The scenario of the classical `pendulum-double-cart-lab`: hanging at rest until 1 s, the
    policy from 1 s, a 40 ms, 0.45 N tip push at 7.5 s, end 12.5 s.

``--cases``: closed-loop variants from given poses at rest (rl/compare.py --rig lab).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lablib as lb  # noqa: E402  (puts examples/pendulum-double-cart/design on the path)
import cartmodel as cm  # noqa: E402
from cartpend import G0  # noqa: E402

ROOT = HERE.parent
SCENE = "scenes/pendulum-double-cart-lab.sdf"
P_NOM = lb.nominal()
PLANT = lb.design_plant(P_NOM)

# realism parameters that enter the bond graph (directly or through a driven global)
BOND = ["L1", "L2", "m_tube1", "m_tube2", "tube_od", "tube_wall", "com_shift1", "com_shift2", "m_hub1", "m_head1",
        "m_hub2", "m_tip2", "s_hub", "s_head", "s_tip", "m_enc_board", "m_enc_magnet", "rho_cable", "m_cart",
        "J_cart", "b_joint1", "b_joint2", "b_cable", "b_carriage", "b_cable_base", "b_motor", "R_m", "L_m", "k_t",
        "J_m", "N_gear", "r_pulley", "k_belt", "d_belt", "x_rail", "k_stop", "d_stop"]

# realism parameters outside the bond-graph elements (R1): the forces of library/LabRealism.jl (the twin's Coulomb
# friction, cable springs, commutation ripple and cogging), driven from the plant's own signals. Their FMU range
# reaches down to 0 (ZERO_OK), so that the FMU also runs the design model (no Coulomb friction, ripple or cable
# spring); the domain randomisation samples the realism.json ranges.
REAL = ["tc_joint1", "tc_joint2", "eps_joint", "tc_carriage", "tc_motor", "eps_base", "k_cable", "k_cable_base",
        "ripple_rel", "ripple_per_rev", "cogging", "cogging_per_rev"]
ZERO_OK = {"tc_joint1", "tc_joint2", "tc_carriage", "tc_motor", "k_cable", "ripple_rel", "cogging"}

# driven globals: lablib.link_props as expressions (parts: mass, position from the pivot, own inertia)
_RO, _RI = "(tube_od/2)", "(tube_od/2 - tube_wall)"
_SQ = lambda e: f"{e}*{e}"  # noqa: E731
_PARTS = {
    1: [("m_tube1", "L1*(0.5 + com_shift1)", f"m_tube1*(L1*L1/12 + ({_SQ(_RO)} + {_SQ(_RI)})/4)"),
        ("m_hub1", "0.0", "m_hub1*s_hub*s_hub/6"),
        ("m_enc_magnet", "0.0", "0.0"),
        ("m_head1", "L1", "m_head1*s_head*s_head/6"),
        ("m_enc_board", "L1", "0.0"),
        ("(rho_cable*L1)", "(L1/2)", "rho_cable*L1*L1*L1/12")],
    2: [("m_tube2", "L2*(0.5 + com_shift2)", f"m_tube2*(L2*L2/12 + ({_SQ(_RO)} + {_SQ(_RI)})/4)"),
        ("m_hub2", "0.0", "m_hub2*s_hub*s_hub/6"),
        ("m_enc_magnet", "0.0", "0.0"),
        ("m_tip2", "L2", "m_tip2*s_tip*s_tip/6")],
}


def _driven() -> list[tuple[str, str, str, str]]:
    out = []
    for j, parts in _PARTS.items():
        out.append((f"m{j}", " + ".join(m for m, _, _ in parts), "kg", f"link {j} mass (lumped parts)"))
        out.append((f"c{j}", "(" + " + ".join(f"{m}*{x}" for m, x, _ in parts) + f")/m{j}", "m",
                    f"joint {j} to the centre of mass of link {j}"))
        out.append((f"J{j}", " + ".join(f"{jj} + {m}*({x} - c{j})*({x} - c{j})" for m, x, jj in parts), "kg*m^2",
                    f"link {j} inertia about its centre of mass (parallel axes)"))
    kt, kd = PLANT.kt_pivot, PLANT.kd_rail
    out += [
        ("rx2", "L1 - c1", "m", "joint 2 in the frame of link 1's centre of mass"),
        ("lever2", "L2 - c2", "m", "lever of the tip push about link 2's centre of mass"),
        ("b1", "b_joint1 + b_cable", "N*m*s/rad", "joint 1 viscous friction with the cable drag"),
        ("b_rail", "b_carriage + b_cable_base", "N*s/m", "carriage, belt and cable-chain viscous friction"),
        ("d1", f"(m1 + m2)*{G0!r}/{kt!r}", "m", "static pivot deflection of joint 1 (hanging)"),
        ("d2", f"m2*{G0!r}/{kt!r}", "m", "static pivot deflection of joint 2 (hanging)"),
        ("d_rail", f"-(m_cart + m1 + m2)*{G0!r}/{kd!r}", "m", "static rail deflection"),
        ("n_motor", "N_gear/r_pulley", "rad/m", "motor angle per cart metre"),
        ("alpha_v", "k_t*N_gear/(r_pulley*R_m)", "N/V", "force per volt at the cart (the twin's alpha)"),
        ("tc_rail", "tc_carriage + tc_motor*N_gear/r_pulley", "N", "carriage + motor Coulomb friction at the cart"),
    ]
    return out


def ranges() -> dict:
    """The exposed globals and their realism ranges: the bond-graph parameters with min < max."""
    spec = lb.spec()
    out = {k: (spec[k]["min"], spec[k]["max"]) for k in BOND + REAL if spec[k]["min"] < spec[k]["max"]}
    return {k: ((0.0, v[1]) if k in ZERO_OK else v) for k, v in out.items()}


def _globals() -> list[dict]:
    spec = lb.spec()
    out = [{"name": k, "value": repr(float(spec[k]["nominal"])), "unit": spec[k]["unit"],
            "description": spec[k]["description"]} for k in BOND + REAL]
    out += [{"name": n, "value": e, "unit": u, "description": d} for n, e, u, d in _driven()]
    return out


def _check_driven():
    """The driven expressions at the nominal values = lablib.link_props (the classical models' numbers)."""
    env = {k: float(v) for k, v in P_NOM.items()}
    for n, e, _, _ in _driven():
        env[n] = eval(e, {}, env)  # noqa: S307 (our own expressions)
    m, c, J = lb.link_props(P_NOM)
    for j in (1, 2):
        for name, ref in ((f"m{j}", m[j - 1]), (f"c{j}", c[j - 1]), (f"J{j}", J[j - 1])):
            assert abs(env[name] - ref) <= 1e-12 * max(1.0, abs(ref)), (name, env[name], ref)
    assert abs(env["b1"] - PLANT.b[0]) < 1e-15 and abs(env["b_rail"] - PLANT.b_cart) < 1e-15
    d = lb.drive(P_NOM)
    assert abs(env["alpha_v"] - d["alpha"]) < 1e-12
    assert abs(env["tc_rail"] - (P_NOM["tc_carriage"] + d["tc_m"])) < 1e-12


def _node(doc, name):
    return next((n for n in doc["diagram"]["nodes"] if n["name"] == name), None)


def _drop(doc, names):
    ids = {n["id"] for n in doc["diagram"]["nodes"] if n["name"] in names}
    doc["diagram"]["nodes"] = [n for n in doc["diagram"]["nodes"] if n["id"] not in ids]
    doc["diagram"]["connections"] = [c for c in doc["diagram"]["connections"]
                                     if c["from"]["node"] not in ids and c["to"]["node"] not in ids]
    return doc


def _bind_globals(doc):
    """Point the physical block parameters at the globals (hanging rest)."""
    _node(doc, "Cart")["params"].update({"m": "m_cart", "J": "J_cart"})
    for j in (1, 2):
        _node(doc, f"Body{j}")["params"].update({"m": f"m{j}", "J": f"J{j}"})
        _node(doc, f"Link{j}")["params"]["x"] = f"c{j}"
        _node(doc, f"CoM{j}")["params"]["x"] = f"c{j}"
    _node(doc, "Joint1")["params"]["b"] = "b1"
    _node(doc, "Joint2")["params"].update({"b": "b_joint2", "rx": "rx2"})
    _node(doc, "Joint1")["starts"]["d"] = "[d1, 0.0]"
    _node(doc, "Joint2")["starts"]["d"] = "[d2, 0.0]"
    _node(doc, "Rail")["starts"]["d"] = "d_rail"
    _node(doc, "Motor")["params"].update({"R_w": "R_m", "L": "L_m", "k_t": "k_t", "J_m": "J_m", "b_m": "b_motor"})
    _node(doc, "Gear")["params"]["N"] = "N_gear"
    _node(doc, "Pulley")["params"]["r"] = "r_pulley"
    _node(doc, "Belt")["params"].update({"k": "k_belt", "d": "d_belt"})
    _node(doc, "RailFriction")["params"]["d"] = "b_rail"
    _node(doc, "EndStops")["params"].update({"lower": "-x_rail", "upper": "x_rail", "k": "k_stop", "d": "d_stop"})
    _node(doc, "PushLever")["params"]["k"] = "lever2"
    doc["parameters"] = _globals()
    return doc




def add_realism(doc, M, v_src, v_port: str = "y"):
    """The realism forces of library/LabRealism.jl (from the voltage signal `v_src`.`v_port` and the plant's
    sensors): a force source on the rail drive (its a.e = F u is the force it takes from the cart, as the
    damper's, so F = -1 pushes along +x) and modulated effort sources on the joint drives (the passive Se)."""
    rail = _node(doc, "Rail")["id"]
    real = M.node("Realism", "project:LabRealism", 520, 820, params={
        "tc_joint1": "tc_joint1", "tc_joint2": "tc_joint2", "eps_joint": "eps_joint", "tc_rail": "tc_rail",
        "eps_base": "eps_base", "k_cable": "k_cable", "k_cable_base": "k_cable_base", "alpha": "alpha_v",
        "n_motor": "n_motor", "ripple_rel": "ripple_rel", "ripple_per_rev": "ripple_per_rev", "cogging": "cogging",
        "cogging_per_rev": "cogging_per_rev"})
    M.sig(v_src, v_port, real, "V")
    for port, (src, sp) in {"x": ("Rail", "qout"), "v": ("Rail", "qdout"), "q1": ("Joint1", "qout"),
                            "w1": ("Joint1", "qdout"), "w2": ("Joint2", "qdout")}.items():
        M.sig(_node(doc, src)["id"], sp, real, port)
    fsrc = M.node("RealismForce", "stdlib:translation/ForceSource", 640, 80, params={"F": "-1.0"})
    ffix = M.node("FrameR", "stdlib:translation/Fixed", 640, -20)
    M.wire(fsrc, "a", rail, "drive")
    M.wire(fsrc, "b", ffix, "a")
    M.sig(real, "F", fsrc, "u")
    for j in (1, 2):
        se = _node(doc, f"Passive{j}")
        se["block"] = {"ref": "stdlib:bondgraph/MSe"}
        se["params"] = {"gain": "1.0"}
        M.sig(real, f"tau{j}", se["id"], "u")
    return real


def plant_model() -> dict:
    doc = cm.build(PLANT, "DoubleCartLab", t_end=5.0, points=5001, scene=SCENE,
                   title="pendulum-double-cart-lab-plant")
    _drop(doc, {"Clock", "Traj", "Ctrl", "PushPulse"})
    M = cm.Model("tmp")
    M.ids = {"n": len(doc["diagram"]["nodes"]) + 100, "b": 900, "s": 900, "w": 900}
    M.nodes, M.conns = doc["diagram"]["nodes"], doc["diagram"]["connections"]
    motor, push, lever = _node(doc, "Motor"), _node(doc, "Push"), _node(doc, "PushLever")
    v_in = M.node("V", "stdlib:converters/ExportInput", 80, 0, params={"value": "0.0"})
    f_in = M.node("F_push", "stdlib:converters/ExportInput", push["position"]["x"], 120, params={"value": "0.0"})
    M.sig(v_in, "y", motor["id"], "u")
    M.sig(f_in, "y", push["id"], "wy")
    M.sig(f_in, "y", lever["id"], "u")
    sensors = [("x", "Rail", "qout"), ("q1", "Joint1", "qout"), ("q2", "Joint2", "qout"),
               ("v", "Rail", "qdout"), ("w1", "Joint1", "qdout"), ("w2", "Joint2", "qdout"),
               ("i_m", "Motor", "i")]
    for k, (name, src, port) in enumerate(sensors):
        out = M.node(name, "stdlib:converters/ExportOutput", 80 + 120 * k, 820)
        M.sig(_node(doc, src)["id"], port, out, "u")
    add_realism(doc, M, v_in)
    _bind_globals(doc)
    doc["plots"] = [
        {"id": "p_q", "title": "Joint encoder angles (rad)", "signals": ["Joint1/qout", "Joint2/qout"]},
        {"id": "p_cart", "title": "Cart position (m)", "signals": ["Rail/qout"]},
        {"id": "p_volt", "title": "Motor voltage (V) and current (A)", "signals": ["V/y", "Motor/isense/y"]},
    ]
    return doc


def rl_model(t_end: float = 12.5, t_on: float = 1.0, push: dict | None = None, th0=None, x0: float = 0.0,
             title: str = "pendulum-double-cart-lab-rl", points: int | None = None,
             block: str = "DoubleCartLabPolicy") -> dict:
    """The closed loop with the trained policy (nominal plant). Default: the classical model's scenario."""
    if push is None:
        push = {"amplitude": 0.45, "t_start": 7.5, "duration": 0.04}
    doc = cm.build(PLANT, "DoubleCartLab", t_end=t_end, points=points or int(round(t_end / 0.005)) + 1,
                   push=push, th0=th0, x0=x0, scene=SCENE, title=title)
    _drop(doc, {"Traj", "Ctrl", "Clock"})
    M = cm.Model("tmp")
    M.ids = {"n": len(doc["diagram"]["nodes"]) + 100, "b": 900, "s": 900, "w": 900}
    M.nodes, M.conns = doc["diagram"]["nodes"], doc["diagram"]["connections"]
    th_start = list(th0) if th0 is not None else [-math.pi] * 2
    pol = M.node("Policy", f"project:{block}", 80, 80, params={"t_on": repr(float(t_on))},
                 starts={"xp": repr(float(x0)), "th1p": repr(th_start[0]), "th2p": repr(th_start[1]),
                         "th1": repr(th_start[0]), "th2": repr(th_start[1])})
    M.sig(_node(doc, "Rail")["id"], "qout", pol, "x")
    M.sig(_node(doc, "Joint1")["id"], "qout", pol, "q1")
    M.sig(_node(doc, "Joint2")["id"], "qout", pol, "q2")
    M.sig(pol, "u", _node(doc, "Motor")["id"], "u")
    doc["plots"] = [
        {"id": "p_angles", "title": "Link angles from upright (rad)", "signals": ["Policy/th1", "Policy/th2"]},
        {"id": "p_cart", "title": "Cart position (m)", "signals": ["Rail/qout"]},
        {"id": "p_volt", "title": "Motor voltage (V)", "signals": ["Policy/u"]},
        {"id": "p_cur", "title": "Motor current (A)", "signals": ["Motor/isense/y"]},
    ]
    return doc


def main(argv: list[str]) -> None:
    _check_driven()
    models = ROOT / "models"
    cm.write(models / "pendulum-double-cart-lab-plant.bgmodel.json", plant_model())
    print("wrote", models / "pendulum-double-cart-lab-plant.bgmodel.json", f"({len(ranges())} exposed globals)")
    (HERE / "rl_ranges.json").write_text(json.dumps({k: list(v) for k, v in ranges().items()}, indent=1) + "\n",
                                         encoding="utf-8", newline="\n")
    if "--rl" in argv:
        cm.write(models / "pendulum-double-cart-lab-rl.bgmodel.json", rl_model())
        print("wrote", models / "pendulum-double-cart-lab-rl.bgmodel.json")
    if "--cases" in argv:
        spec, out = Path(argv[argv.index("--cases") + 1]), Path(argv[argv.index("--cases") + 2])
        out.mkdir(parents=True, exist_ok=True)
        for c in json.loads(spec.read_text(encoding="utf-8")):
            doc = rl_model(t_end=c["t_end"], t_on=0.0, push={"amplitude": 0.0, "t_start": 1.0e6, "duration": 0.04},
                           th0=[c["th1"], c["th2"]], x0=c["x"], title=c["name"],
                           block=c.get("block", "DoubleCartLabPolicy"))
            cm.write(out / f"{c['name']}.bgmodel.json", doc)
        print("wrote the cases into", out)


if __name__ == "__main__":
    main(sys.argv[1:])
