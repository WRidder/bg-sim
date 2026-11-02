# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "httpx>=0.28", "casadi>=3.6"]
# ///
"""Run the three bond-graph models on the real backend, compare with the design, write `expected.json`.

    uv run examples/pendulum-double-cart-lab/design/finish.py [--no-run]

1. runs `pendulum-double-cart-lab`, `-balance` and `-free` through a private backend (the harness of
   examples/run_checks.py via `examples/pendulum-double-rotary/design/runner.py`, a free port) and keeps the
   runs in `design/_runs/` (not in git);
2. measures them (cartpend.measure for the swing-up run) and compares them with the design closed loops and the
   free-swing reference of `design/design.json` (the design ODE, which is the twin: lablib.check_twin);
3. writes `design/measured.json` and `expected.json` (every check names its tolerance in the note).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(ROOT.parent / "pendulum-double-rotary" / "design"))   # runner.py (after HERE: it has a design.py too)

import design as dsg  # noqa: E402
import runner  # noqa: E402

cp = dsg.cp
NAME = "pendulum-double-cart-lab"
CODES = ["E101", "E102", "E103", "E106", "E901", "W201", "W202", "W205", "W206"]
DEG = math.pi / 180


def ref_at(cl: dict, tq: float, i: int) -> float:
    return float(np.interp(tq, np.array(cl["t"]), np.array(cl["z"])[:, i]))


def ref_peak(cl: dict, i: int, t0: float, t1: float) -> float:
    t, z = np.array(cl["t"]), np.array(cl["z"])
    sel = (t >= t0) & (t <= t1)
    return float(np.max(np.abs(z[sel, i])))


def ref_peak_u(cl: dict, t0: float, t1: float) -> float:
    t, u = np.array(cl["t"]), np.array(cl["u"])
    sel = (t >= t0) & (t <= t1)
    return float(np.max(np.abs(u[sel])))


def measure_balance(dz, t, S) -> dict:
    b = dz["balance"]
    th = np.stack([S["Ctrl/th1"], S["Ctrl/th2"]], 1)
    m = np.degrees(np.abs(th).max(1))
    tp = b["t_push"]
    bad = np.where((t > tp + 0.05) & (m > 0.5))[0]
    return {
        "pre_push_deg": float(m[(t > tp - 0.5) & (t < tp)].max()),
        "defl_deg": np.degrees(np.abs(th[t >= tp]).max(0)).tolist(),
        "t_rec": float(t[bad[-1] + 1]) - tp if len(bad) else 0.0,
        "end_deg": float(m[t > t[-1] - 1.0].max()),
        "end_x": float(np.abs(S["Rail/qout"][t > t[-1] - 1.0]).max()),
        "u_peak": float(np.abs(S["Ctrl/u"]).max()),
        "i_peak": float(np.abs(S["Motor/isense/y"]).max()),
        "x_peak": float(np.abs(S["Rail/qout"]).max()),
    }


def compare_free(dz, t, S) -> dict:
    fr = dz["free"]
    tt, idx = np.unique(t[t <= fr["t_end"] + 1e-9], return_index=True)
    ref = cp.free_swing(dsg.SCENARIO, cp.Dynamics(dsg.PLANT), tt)
    th = np.cumsum(np.stack([S["Joint1/qout"][idx], S["Joint2/qout"][idx]], 1), axis=1) - np.pi / 2
    return {"x": float(np.abs(S["Rail/qout"][idx] - ref[:, 0]).max()),
            "th1": float(np.abs(th[:, 0] - ref[:, 1]).max()), "th2": float(np.abs(th[:, 1] - ref[:, 2]).max())}


def scene_check(dz) -> dict:
    c = dz["plant"]["c"]
    return {"kind": "scene_bindings", "fk": [
        {"link": "link1", "point": [round(c[0], 9), 0, 0], "signals": ["PoseB1/g[2]", None, "PoseB1/g[3]"], "tol": 1e-6},
        {"link": "link2", "point": [round(c[1], 9), 0, 0], "signals": ["PoseB2/g[2]", None, "PoseB2/g[3]"], "tol": 1e-6}]}


def checks_swingup(dz, M) -> list:
    sw = dz["swingup"]
    cl = sw["closed_loop"]
    t_on, t_s = dz["t_on"], dz["t_s"]
    t_c, t_d, t_end = t_on + t_s, sw["t_dist"], sw["t_end"]
    u_max, u_lim, x_lim, x_rail = dz["u_max"], dz["u_lim"], dz["x_lim"], dz["x_rail"]
    out = [
        scene_check(dz),
        {"kind": "no_diagnostics", "codes": CODES,
         "note": "no solver failure, causal conflict, derivative-causal store, algebraic loop or event-limit stop"},
    ]
    for sig, what in (("Rail/qdout", "the cart is at rest"), ("Joint1/qdout", "link 1 hangs motionless"),
                      ("Joint2/qdout", "link 2 hangs motionless")):
        out.append({"kind": "max_abs", "signal": sig, "from_t": 0.0, "to_t": t_on - 0.01, "value": 0.0, "abs": 1e-6,
                    "note": f"nothing moves before t_on = {t_on:g} s: {what} (the pivot deflections start at their static values)"})
    out += [
        {"kind": "cursor_value", "signal": "Ctrl/th1", "t": 0.5, "value": -math.pi, "abs": 1e-6,
         "note": "link 1 hangs straight down (-180 deg from the upward vertical) at 0.5 s"},
        {"kind": "max_abs", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_on - 0.01, "value": 0.0, "abs": 1e-12,
         "note": "the motor voltage is 0 before the swing-up"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": 0.5, "value": 0, "abs": 1e-9, "note": "hold phase"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": t_on + 1.0, "value": 1, "abs": 1e-9, "note": "swing-up (TVLQR) phase"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": t_c + 0.5, "value": 2, "abs": 1e-9,
         "note": f"balance (LQR) phase from the catch at {t_c:g} s"},
    ]
    for tq in (t_on + 0.4 * t_s, t_on + 0.7 * t_s, t_c):
        tq = round(tq, 3)
        for i in (1, 2):
            v = ref_at(cl, tq, i)
            out.append({"kind": "cursor_value", "signal": f"Ctrl/th{i}", "t": tq, "value": round(v, 6), "abs": 0.01,
                        "note": f"swing-up, link {i} angle from upright at t = {tq:g} s; the design model's closed loop gives "
                                f"{v:.4f} rad (0.01 rad band)"})
    out += [
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": t_c + 0.1, "to_t": t_d - 0.01, "value": 0.0, "abs": 0.0035,
         "note": f"upright reached: link 1 stays within 0.2 deg of upright from the catch + 0.1 s to the push (measured {M['band_deg']:.4f} deg for both links)"},
        {"kind": "max_abs", "signal": "Ctrl/th2", "from_t": t_c + 0.1, "to_t": t_d - 0.01, "value": 0.0, "abs": 0.0035,
         "note": "upright reached: link 2 stays within 0.2 deg of upright from the catch + 0.1 s to the push"},
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": t_c + 0.1, "to_t": t_d - 0.01, "value": 0.0, "abs": 0.01,
         "note": f"the cart is back within 1 cm of the rail centre (measured {M['band_x'] * 1000:.1f} mm)"},
    ]
    for i, a in ((1, 0.02), (2, 0.01)):
        v = M["defl_deg"][i - 1] * DEG
        r = ref_peak(cl, i, t_d, t_d + 2.0)
        out.append({"kind": "max_abs", "signal": f"Ctrl/th{i}", "from_t": t_d, "to_t": t_d + 2.0, "value": round(v, 6), "abs": a,
                    "note": f"the {sw['dist_amp']:g} N, {sw['dist_dur'] * 1000:g} ms push is real: link {i} deflects by "
                            f"{math.degrees(v):.2f} deg (design closed loop {math.degrees(r):.2f} deg)"})
    rec = round(t_d + M["t_rec"] + 0.05, 3)
    out += [
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": t_d, "to_t": t_d + 2.0, "value": round(M["defl_x"], 6), "abs": 0.02,
         "note": f"the cart travel while the controller catches the push (measured {M['defl_x']:.3f} m)"},
        {"kind": "max_abs_le", "signal": "Ctrl/th1", "from_t": rec, "to_t": t_end, "value": 0.5 * DEG,
         "note": f"link 1 is back inside 0.5 deg from t = {rec:g} s on ({M['t_rec']:.2f} s after the push)"},
        {"kind": "max_abs_le", "signal": "Ctrl/th2", "from_t": rec, "to_t": t_end, "value": 0.5 * DEG,
         "note": "link 2 is back inside 0.5 deg as well"},
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": t_end - 1.0, "to_t": t_end, "value": 0.0, "abs": 0.0035,
         "note": f"recovered: link 1 within 0.2 deg of upright over the last second (both links measured {M['end_deg']:.4f} deg)"},
        {"kind": "max_abs", "signal": "Ctrl/th2", "from_t": t_end - 1.0, "to_t": t_end, "value": 0.0, "abs": 0.0035,
         "note": "recovered: link 2 within 0.2 deg of upright over the last second"},
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": t_end - 1.0, "to_t": t_end, "value": 0.0, "abs": 0.01,
         "note": "the cart is back at the rail centre by the end"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_end, "value": u_max,
         "note": f"the motor voltage stays inside the +-{u_max:g} V supply (the firmware clamps it)"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "from_t": t_on, "to_t": t_c, "value": u_lim,
         "note": f"margin: the swing-up stays inside the planned {u_lim:g} V (70 % of the supply) also with the feedback "
                 f"(measured {M['u_peak_swing']:.2f} V, design closed loop {ref_peak_u(cl, t_on, t_c):.2f} V; feed-forward {sw['traj_peak_u']:.2f} V)"},
        {"kind": "max_abs", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_end, "value": round(M["u_peak"], 4), "abs": 1.5,
         "note": f"peak voltage {M['u_peak']:.2f} V of {u_max:g} V (design closed loop {ref_peak_u(cl, 0, t_end):.2f} V)"},
        {"kind": "max_abs", "signal": "Motor/isense/y", "from_t": 0.0, "to_t": t_end, "value": round(M["i_peak"], 4), "rtol": 0.15,
         "note": f"peak motor current {M['i_peak']:.2f} A (+-15 %; the stall current at 24 V is {u_max / dsg.P_NOM['R_m']:.0f} A)"},
        {"kind": "max_abs_le", "signal": "Rail/qout", "from_t": 0.0, "to_t": t_end, "value": x_lim,
         "note": f"margin: the cart stays inside the planned +-{x_lim:g} m, the end stops at +-{x_rail:g} m are never touched "
                 f"(measured {M['x_peak']:.3f} m)"},
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": 0.0, "to_t": t_end, "value": round(M["x_peak"], 6), "abs": 0.02,
         "note": f"peak cart travel {M['x_peak']:.3f} m (design closed loop {ref_peak(cl, 0, 0, t_end):.3f} m; the trajectory "
                 f"reaches {sw['traj_peak_x']:.3f} m of its +-{x_lim:g} m bound)"},
    ]
    return out


def checks_balance(dz, B) -> list:
    b = dz["balance"]
    cl = b["closed_loop"]
    tp, t_end = b["t_push"], b["t_end"]
    out = [
        scene_check(dz),
        {"kind": "no_diagnostics", "codes": CODES, "note": "no diagnostics"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": 0.01, "value": 2, "abs": 1e-9,
         "note": "balance from the start (Ctrl/t_on = -10 s: tau >= T_s at the first tick)"},
        {"kind": "cursor_value", "signal": "Joint1/qout", "t": 0.0, "value": round(b["th0_deg"][0] * DEG + math.pi / 2, 9),
         "abs": 1e-6, "note": f"the start lean: link 1 at {b['th0_deg'][0]:g} deg from upright (joint angle th1 + pi/2)"},
        {"kind": "max_abs_le", "signal": "Ctrl/th1", "from_t": tp - 0.5, "to_t": tp - 0.01, "value": 0.5 * DEG,
         "note": f"the lean is caught: inside 0.5 deg before the push (both links measured {B['pre_push_deg']:.3f} deg)"},
        {"kind": "max_abs_le", "signal": "Ctrl/th2", "from_t": tp - 0.5, "to_t": tp - 0.01, "value": 0.5 * DEG,
         "note": "link 2 inside 0.5 deg before the push"},
    ]
    for i, a in ((1, 0.02), (2, 0.01)):
        v = B["defl_deg"][i - 1] * DEG
        r = ref_peak(cl, i, tp, t_end)
        out.append({"kind": "max_abs", "signal": f"Ctrl/th{i}", "from_t": tp, "to_t": t_end, "value": round(v, 6), "abs": a,
                    "note": f"the {b['amp']:g} N, {b['dur'] * 1000:g} ms push (78 % of the largest the design recovers) is real: "
                            f"link {i} deflects by {math.degrees(v):.2f} deg (design closed loop {math.degrees(r):.2f} deg)"})
    rec = round(tp + B["t_rec"] + 0.05, 3)
    out += [
        {"kind": "max_abs_le", "signal": "Ctrl/th1", "from_t": rec, "to_t": t_end, "value": 0.5 * DEG,
         "note": f"recovered: link 1 inside 0.5 deg from {rec:g} s ({B['t_rec']:.2f} s after the push)"},
        {"kind": "max_abs_le", "signal": "Ctrl/th2", "from_t": rec, "to_t": t_end, "value": 0.5 * DEG,
         "note": "recovered: link 2 inside 0.5 deg as well"},
        {"kind": "max_abs", "signal": "Ctrl/th1", "from_t": t_end - 1.0, "to_t": t_end, "value": 0.0, "abs": 0.0035,
         "note": f"within 0.2 deg over the last second (measured {B['end_deg']:.4f} deg)"},
        {"kind": "max_abs", "signal": "Rail/qout", "from_t": t_end - 1.0, "to_t": t_end, "value": 0.0, "abs": 0.01,
         "note": f"the cart returns to the centre (measured {B['end_x'] * 1000:.1f} mm)"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_end, "value": dz["u_max"],
         "note": f"inside the {dz['u_max']:g} V supply (measured peak {B['u_peak']:.2f} V)"},
        {"kind": "max_abs", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_end, "value": round(B["u_peak"], 4), "abs": 1.5,
         "note": f"peak voltage {B['u_peak']:.2f} V (design closed loop {ref_peak_u(cl, 0, t_end):.2f} V)"},
        {"kind": "max_abs", "signal": "Motor/isense/y", "from_t": 0.0, "to_t": t_end, "value": round(B["i_peak"], 4), "rtol": 0.15,
         "note": f"peak motor current {B['i_peak']:.2f} A (+-15 %)"},
        {"kind": "max_abs_le", "signal": "Rail/qout", "from_t": 0.0, "to_t": t_end, "value": dz["x_lim"],
         "note": f"the push recovery stays inside +-{dz['x_lim']:g} m (measured {B['x_peak']:.3f} m; design {ref_peak(cl, 0, 0, t_end):.3f} m)"},
    ]
    return out


def checks_free(dz, F) -> list:
    fr = dz["free"]
    tol_x = max(2e-4, round(3 * F["x"], 6))
    tol_a = max(3e-3, round(3 * max(F["th1"], F["th2"]), 5))
    out = [scene_check(dz)]
    note = (f"design ODE (= the Python twin, lablib.check_twin) value, free swing from rest with the motor shorted (V = 0); "
            f"the bond graph agrees to {max(F['th1'], F['th2']):.1e} rad / {F['x']:.1e} m (tolerance 3x that, at least 3e-3 rad / 2e-4 m)")
    for k, tq in enumerate(fr["t"]):
        if tq <= 0.0:
            continue
        z = fr["z"][k]
        q1, q2 = z[1] + math.pi / 2, z[2] - z[1]
        out.append({"kind": "cursor_value", "signal": "Rail/qout", "t": tq, "value": round(z[0], 7), "abs": tol_x, "note": note})
        out.append({"kind": "cursor_value", "signal": "Joint1/qout", "t": tq, "value": round(q1, 6), "abs": tol_a, "note": note})
        out.append({"kind": "cursor_value", "signal": "Joint2/qout", "t": tq, "value": round(q2, 6), "abs": tol_a, "note": note})
    out.append({"kind": "no_diagnostics", "codes": CODES, "note": "the free swing reports no diagnostics"})
    return out


def main(argv):
    runs = HERE / "_runs"
    models = [NAME, f"{NAME}-balance", f"{NAME}-free"]
    stats = {}
    if "--no-run" not in argv:
        stats = runner.run_models(NAME, models, runs, timeout=2400.0)
    dz = json.loads(dsg.DESIGN_JSON.read_text(encoding="utf-8"))
    t, S = runner.load(runs / f"{NAME}.npz")
    tb, Sb = runner.load(runs / f"{NAME}-balance.npz")
    tf, Sf = runner.load(runs / f"{NAME}-free.npz")
    M = cp.measure(dsg.SCENARIO, t, S)
    M["u_peak_swing"] = float(np.abs(S["Ctrl/u"][(t >= dz["t_on"]) & (t <= dz["t_on"] + dz["t_s"])]).max())
    M["i_peak"] = float(np.abs(S["Motor/isense/y"]).max())
    M["i_peak_swing"] = float(np.abs(S["Motor/isense/y"][t < dz["swingup"]["t_dist"]]).max())
    cl = dz["swingup"]["closed_loop"]
    tt = np.unique(t[(t >= dz["t_on"]) & (t <= dz["swingup"]["t_dist"])])
    zc = np.array(cl["z"])
    M["cl_diff_th"] = float(max(np.abs(np.interp(tt, t, S[f"Ctrl/th{i}"]) - np.interp(tt, cl["t"], zc[:, i])).max() for i in (1, 2)))
    M["cl_diff_x"] = float(np.abs(np.interp(tt, t, S["Rail/qout"]) - np.interp(tt, cl["t"], zc[:, 0])).max())
    B = measure_balance(dz, tb, Sb)
    F = compare_free(dz, tf, Sf)
    print("swing-up:", {k: (round(v, 5) if isinstance(v, float) else v) for k, v in M.items()})
    print("balance :", {k: (round(v, 5) if isinstance(v, float) else v) for k, v in B.items()})
    print("free    :", {k: f"{v:.3g}" for k, v in F.items()})
    mpath = HERE / "measured.json"
    old = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else {}
    run_stats = old.get("run_stats", {})
    run_stats.update({k: {"seconds": round(v["seconds"], 1), "points": v["points"]} for k, v in stats.items()})
    mpath.write_text(json.dumps({"swingup": M, "balance": B, "free": F, "run_stats": run_stats}, indent=2) + "\n",
                     encoding="utf-8", newline="\n")
    doc = {"project": NAME, "description": dsg.DESCRIPTION, "models": {
        NAME: {"run_timeout": 1200, "checks": checks_swingup(dz, M)},
        f"{NAME}-balance": {"run_timeout": 900, "checks": checks_balance(dz, B)},
        f"{NAME}-free": {"run_timeout": 900, "checks": checks_free(dz, F)},
    }}
    path = ROOT / "expected.json"
    # keep the entries of models this script does not write (the RL model: rl/compare.py, plan/RL_PLAN.md R0.7)
    if path.is_file():
        for k, v in json.loads(path.read_text(encoding="utf-8"))["models"].items():
            doc["models"].setdefault(k, v)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path, "and", mpath)


if __name__ == "__main__":
    main(sys.argv[1:])
