# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""The RL variants of the double cart pendulum (plan/RL_PLAN.md, step 0).

    uv run examples/pendulum-double-cart/design/rlmodels.py [--rl]

writes two model documents next to the classical ones (which stay unchanged):

``pendulum-double-cart-plant``
    The plant only, for the FMU the RL environment steps (R0.1). The firmware (Clock, Traj, Ctrl)
    is gone; the motor voltage is an ``ExportInput`` (``V``), the push on the tip link another
    (``F_push``, for random pushes in training), and the sensors are ``ExportOutput`` markers:
    cart position ``x`` and the two joint encoder angles ``q1`` (link 1 from the rail's x axis)
    and ``q2`` (link 2 relative to link 1), plus their rates and the motor current (the critic's
    privileged observations; a real rig differences the encoders). The physical parameters are
    global parameters (the independent ones are exposed in the FMU with ranges, see
    ``rl/export_plant.jl``); the derived values (centres of mass, inertias, the static pivot
    deflections) are driven globals, recomputed in the FMU's initialisation.

``pendulum-double-cart-rl``
    The same plant with the trained policy block ``project:DoubleCartPolicy`` (written by
    ``rl/make_policy_block.py``) as the firmware (R0.4/R0.5): the encoders in, the motor voltage out.
    The run starts hanging at rest, swings up, balances, and gets the README's 40 ms push.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cartmodel as cm  # noqa: E402
from cartpend import G0  # noqa: E402
from design import PLANT  # noqa: E402

ROOT = HERE.parent

# Independent globals: name, value, unit, description, (min, max) for the FMU (rl/export_plant.jl
# reads the ranges from this table through the model's `rlRanges` note below).
GLOBALS = [
    ("m_cart", PLANT.m_cart, "kg", "cart carriage mass", (0.6, 1.0)),
    ("m1", PLANT.m[0], "kg", "link 1 mass", (0.08, 0.12)),
    ("m2", PLANT.m[1], "kg", "link 2 mass", (0.064, 0.096)),
    ("L1", PLANT.L[0], "m", "link 1 length (pivot to pivot; centre of mass at the middle)", (0.23, 0.27)),
    ("L2", PLANT.L[1], "m", "link 2 length (centre of mass at the middle)", (0.23, 0.27)),
    ("b1", PLANT.b[0], "N*m*s/rad", "joint 1 viscous friction", (5.0e-5, 1.0e-3)),
    ("b2", PLANT.b[1], "N*m*s/rad", "joint 2 viscous friction", (5.0e-5, 1.0e-3)),
    ("R_m", PLANT.R_m, "Ohm", "motor winding resistance (with leads)", (1.2, 1.9)),
    ("k_t", PLANT.k_t, "N*m/A", "motor torque (= back-EMF) constant", (0.027, 0.033)),
    ("J_m", PLANT.J_m, "kg*m^2", "rotor inertia", (1.1e-5, 1.7e-5)),
    ("b_m", PLANT.b_m, "N*m*s/rad", "rotor bearing loss", (0.0, 1.0e-5)),
]

# Driven globals (recomputed from the exposed ones at initialisation).
DRIVEN = [
    ("c1", "L1/2", "m", "joint 1 to the centre of mass of link 1"),
    ("c2", "L2/2", "m", "joint 2 to the centre of mass of link 2"),
    ("J1", "m1*L1*L1/12", "kg*m^2", "link 1 inertia about its centre of mass (rod)"),
    ("J2", "m2*L2*L2/12", "kg*m^2", "link 2 inertia about its centre of mass (rod)"),
    ("rx2", "L1 - c1", "m", "joint 2 in the frame of link 1's centre of mass"),
    ("lever2", "L2 - c2", "m", "lever of the tip push about link 2's centre of mass"),
    ("d1", f"(m1 + m2)*{G0!r}/{PLANT.kt_pivot!r}", "m", "static pivot deflection of joint 1 (hanging)"),
    ("d2", f"m2*{G0!r}/{PLANT.kt_pivot!r}", "m", "static pivot deflection of joint 2 (hanging)"),
    ("d_rail", f"-(m_cart + m1 + m2)*{G0!r}/{PLANT.kd_rail!r}", "m", "static rail deflection"),
]


def _globals() -> list[dict]:
    out = [{"name": n, "value": repr(float(v)), "unit": u, "description": d} for n, v, u, d, _ in GLOBALS]
    out += [{"name": n, "value": e, "unit": u, "description": d} for n, e, u, d in DRIVEN]
    return out


def _node(doc, name):
    return next(n for n in doc["diagram"]["nodes"] if n["name"] == name)


def _drop(doc, names):
    ids = {n["id"] for n in doc["diagram"]["nodes"] if n["name"] in names}
    doc["diagram"]["nodes"] = [n for n in doc["diagram"]["nodes"] if n["id"] not in ids]
    doc["diagram"]["connections"] = [c for c in doc["diagram"]["connections"]
                                     if c["from"]["node"] not in ids and c["to"]["node"] not in ids]
    return doc


def _bind_globals(doc):
    """Point the physical block parameters at the globals."""
    _node(doc, "Cart")["params"]["m"] = "m_cart"
    for j in (1, 2):
        _node(doc, f"Body{j}")["params"].update({"m": f"m{j}", "J": f"J{j}"})
        _node(doc, f"Link{j}")["params"]["x"] = f"c{j}"
        _node(doc, f"CoM{j}")["params"]["x"] = f"c{j}"
        _node(doc, f"Joint{j}")["params"]["b"] = f"b{j}"
    _node(doc, "Joint2")["params"]["rx"] = "rx2"
    # hanging rest: joint deflection [f, 0] (cartmodel.static_deflection at th = -pi)
    _node(doc, "Joint1")["starts"]["d"] = "[d1, 0.0]"
    _node(doc, "Joint2")["starts"]["d"] = "[d2, 0.0]"
    _node(doc, "Rail")["starts"]["d"] = "d_rail"
    _node(doc, "Motor")["params"].update({"R_w": "R_m", "k_t": "k_t", "J_m": "J_m", "b_m": "b_m"})
    lever = _node(doc, "PushLever")
    if lever is not None:
        lever["params"]["k"] = "lever2"
    doc["parameters"] = _globals()
    return doc


def _check_hanging_deflection():
    ds, d_rail = cm.static_deflection(PLANT, [-3.141592653589793] * 2)
    f1 = (PLANT.m[0] + PLANT.m[1]) * G0 / PLANT.kt_pivot
    assert abs(ds[0][0] - f1) < 1e-15 and abs(ds[0][1]) < 1e-15, ds
    assert abs(d_rail + (PLANT.m_cart + sum(PLANT.m)) * G0 / PLANT.kd_rail) < 1e-15


def plant_model() -> dict:
    doc = cm.build(PLANT, "DoubleCart", t_end=5.0, points=5001, scene="scenes/pendulum-double-cart.sdf",
                   title="pendulum-double-cart-plant")
    _drop(doc, {"Clock", "Traj", "Ctrl", "PushPulse"})
    M = cm.Model("tmp")
    M.ids = {"n": len(doc["diagram"]["nodes"]) + 100, "b": 900, "s": 900, "w": 900}
    M.nodes, M.conns = doc["diagram"]["nodes"], doc["diagram"]["connections"]
    motor, push, lever = _node(doc, "Motor"), _node(doc, "Push"), _node(doc, "PushLever")
    v_in = M.node("V", "stdlib:converters/ExportInput", 80, 0, params={"value": "0.0"})
    f_in = M.node("F_push", "stdlib:converters/ExportInput", push["position"]["x"], 120,
                  params={"value": "0.0"})
    M.sig(v_in, "y", motor["id"], "u")
    M.sig(f_in, "y", push["id"], "wy")
    M.sig(f_in, "y", lever["id"], "u")
    sensors = [("x", "Rail", "qout"), ("q1", "Joint1", "qout"), ("q2", "Joint2", "qout"),
               ("v", "Rail", "qdout"), ("w1", "Joint1", "qdout"), ("w2", "Joint2", "qdout"),
               ("i_m", "Motor", "i")]
    for k, (name, src, port) in enumerate(sensors):
        out = M.node(name, "stdlib:converters/ExportOutput", 80 + 120 * k, 820)
        M.sig(_node(doc, src)["id"], port, out, "u")
    _bind_globals(doc)
    doc["plots"] = [
        {"id": "p_q", "title": "Joint encoder angles (rad)", "signals": ["Joint1/qout", "Joint2/qout"]},
        {"id": "p_cart", "title": "Cart position (m)", "signals": ["Rail/qout"]},
        {"id": "p_volt", "title": "Motor voltage (V) and current (A)", "signals": ["V/y", "Motor/isense/y"]},
    ]
    return doc


def rl_model(t_end: float = 12.0, t_on: float = 1.0, push: dict | None = None, th0=None, x0: float = 0.0,
             title: str = "pendulum-double-cart-rl", points: int | None = None) -> dict:
    """The closed loop with the trained policy. Default: hang until 1 s, swing up and balance, the
    README's 40 ms, 0.28 N push at 7 s. ``th0``/``x0`` start the plant at rest in another pose
    (absolute angles from upright), for the comparison with the training env (R0.5)."""
    if push is None:
        push = {"amplitude": 0.28, "t_start": 7.0, "duration": 0.04}
    doc = cm.build(PLANT, "DoubleCart", t_end=t_end, points=points or int(round(t_end * 1000)) + 1,
                   push=push, th0=th0, x0=x0, scene="scenes/pendulum-double-cart.sdf", title=title)
    _drop(doc, {"Traj", "Ctrl", "Clock"})
    M = cm.Model("tmp")
    M.ids = {"n": len(doc["diagram"]["nodes"]) + 100, "b": 900, "s": 900, "w": 900}
    M.nodes, M.conns = doc["diagram"]["nodes"], doc["diagram"]["connections"]
    motor = _node(doc, "Motor")
    th_start = list(th0) if th0 is not None else [-3.141592653589793] * 2
    pol = M.node("Policy", "project:DoubleCartPolicy", 80, 80,
                 params={"t_on": repr(float(t_on))},
                 starts={"xp": repr(float(x0)), "th1p": repr(th_start[0]), "th2p": repr(th_start[1]),
                         "th1": repr(th_start[0]), "th2": repr(th_start[1])})
    M.sig(_node(doc, "Rail")["id"], "qout", pol, "x")
    M.sig(_node(doc, "Joint1")["id"], "qout", pol, "q1")
    M.sig(_node(doc, "Joint2")["id"], "qout", pol, "q2")
    M.sig(pol, "u", motor["id"], "u")
    doc["plots"] = [
        {"id": "p_angles", "title": "Link angles from upright (rad)", "signals": ["Policy/th1", "Policy/th2"]},
        {"id": "p_cart", "title": "Cart position (m)", "signals": ["Rail/qout"]},
        {"id": "p_volt", "title": "Motor voltage (V)", "signals": ["Policy/u"]},
        {"id": "p_cur", "title": "Motor current (A)", "signals": ["Motor/isense/y"]},
    ]
    return doc


RL_TASKS = {
    "balance": {"t_end": 6.0, "t_on": 0.0, "th0": [0.1, -0.05], "push": {"amplitude": 0.28, "t_start": 3.0,
                                                                         "duration": 0.04}},
    "swingup": {},
}


def main(argv: list[str]) -> None:
    _check_hanging_deflection()
    models = ROOT / "models"
    cm.write(models / "pendulum-double-cart-plant.bgmodel.json", plant_model())
    print("wrote", models / "pendulum-double-cart-plant.bgmodel.json")
    if "--rl" in argv:
        # --rl balance (default): start at rest at 0.1/-0.05 rad, policy from the first tick, push at 3 s.
        # --rl swingup: hang until 1 s, swing up and balance, push at 7 s (12 s).
        task = argv[argv.index("--rl") + 1] if len(argv) > argv.index("--rl") + 1 else "balance"
        doc = rl_model(**RL_TASKS[task])
        cm.write(models / "pendulum-double-cart-rl.bgmodel.json", doc)
        print("wrote", models / "pendulum-double-cart-rl.bgmodel.json", f"({task})")
    if "--cases" in argv:
        # rl/compare.py: closed-loop variants from given poses at rest, policy from t = 0, no push
        import json

        spec, out = Path(argv[argv.index("--cases") + 1]), Path(argv[argv.index("--cases") + 2])
        out.mkdir(parents=True, exist_ok=True)
        for c in json.loads(spec.read_text(encoding="utf-8")):
            doc = rl_model(t_end=c["t_end"], t_on=0.0, push={"amplitude": 0.0, "t_start": 1.0e6, "duration": 0.04},
                           th0=[c["th1"], c["th2"]], x0=c["x"], title=c["name"])
            cm.write(out / f"{c['name']}.bgmodel.json", doc)
        print("wrote the cases into", out)


if __name__ == "__main__":
    main(sys.argv[1:])
