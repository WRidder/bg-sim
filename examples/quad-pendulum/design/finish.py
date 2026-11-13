# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "httpx>=0.28", "casadi>=3.6"]
# ///
"""Run the bond-graph models on the real backend, compare with the design twin, write `expected.json`.

    uv run examples/quad-pendulum/design/finish.py [--no-run] [--only cart|rotary]

1. runs every model of the project through a private backend (the harness of examples/run_checks.py,
   via `examples/pendulum-double-rotary/design/runner.py`) and keeps the runs in `design/_runs/`; for a rig
   with a short-travel design (so far the cart) the swing-up and balance models run twice, with the
   full-travel controller (Traj/controller = 0) and with the short-travel one (override
   Traj/controller = 1, saved as `<model>-short`);
2. compares the free swing of the bond graph with the Lagrangian twin (quadlib.free_swing);
3. measures the swing-up and balance runs (catch, settled band, peak input, travel, energy ledger) and
   compares them with the design closed loop (design_<rig>.json);
4. writes `design/measured.json` and `expected.json` (the tolerances are named in every check's note); the
   short-travel runs are override scenarios of the same models (`<model>-short`).
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
sys.path.insert(0, str(ROOT.parent / "pendulum-double-rotary" / "design"))

import runner  # noqa: E402

CODES = ["E101", "E102", "E103", "E106", "E901", "W201", "W202", "W205", "W206"]
RIGS = {"cart": "quad-pendulum", "rotary": "quad-rotary"}
SHORT = [{"target": "Traj/controller", "value": 1}]


def base_sig(kind):
    return "Rail/qout" if kind == "cart" else "L1/J/qout"


def base_rate(kind):
    return "Rail/qdout" if kind == "cart" else "L1/J/qdout"


def joint1(kind):
    return "Joint1/qout" if kind == "cart" else "L2/J/qout"


def ledger(sig):
    h = sig["Mon/E_tot"] - sig["Mon/W_in"] + sig["Mon/W_loss"]
    return float(np.max(np.abs(h - h[0])))


def measure_swingup(dz, t, sig) -> dict:
    kind = dz["kind"]
    ph = sig["Ctrl/phase"]
    dev = sig["Mon/dev"]
    t_on, t_s = dz["t_on"], dz["t_s"]
    t_catch = float(t[np.argmax(ph > 1.5)]) if np.any(ph > 1.5) else math.nan
    settle = t_on + t_s + 1.5
    sel = t >= settle
    near = np.where((dev < 5.0) & (t > t_on))[0]
    rest = (t > 0.02) & (t < t_on - 0.01)
    up = np.where((dev > 0.5) & (t > t_on))[0]
    return {
        "t_catch": t_catch,
        "t_within_5deg": float(t[near[0]]) if len(near) else math.nan,
        "t_within_0p5deg_for_good": float(t[up[-1] + 1]) if len(up) and up[-1] + 1 < len(t) else math.nan,
        "settled_dev_deg": float(np.max(dev[sel])),
        "final_dev_deg": float(dev[-1]),
        "final_angles_deg": [float(sig[f"Mon/th{i + 1}"][-1]) for i in range(4)],
        "final_s": float(sig[base_sig(kind)][-1]),
        "settled_s": float(np.max(np.abs(sig[base_sig(kind)][sel]))),
        "peak_u": float(np.max(np.abs(sig["Ctrl/u"]))),
        "peak_s": float(np.max(np.abs(sig[base_sig(kind)]))),
        **({"peak_use": float(np.max(sig["Mon/use"]))} if "Mon/use" in sig else {}),
        "rest_rate": float(np.max(np.abs(sig[base_rate(kind)][rest]))),
        "E_end": float(sig["Mon/S4"][-1]),
        "E_up": float(sig["Mon/E_up"][-1]),
        "ledger_drift": ledger(sig),
        "W_in_end": float(sig["Mon/W_in"][-1]),
        "W_loss_end": float(sig["Mon/W_loss"][-1]),
    }


def measure_balance(dz, t, sig) -> dict:
    kind = dz["kind"]
    dev = sig["Mon/dev"]
    tp = dz["balance"]["push"]["t_start"]
    t_end = dz["balance"]["t_end"]
    out = np.where((dev > 0.5) & (t >= tp))[0]
    return {
        "peak_dev_after_push_deg": float(np.max(dev[t >= tp])),
        "t_recover": float(t[out[-1] + 1]) - tp if len(out) and out[-1] + 1 < len(t) else 0.0,
        "pre_push_dev_deg": float(np.max(dev[(t > tp - 0.5) & (t < tp)])),
        "final_dev_deg": float(dev[-1]),
        "last_second_dev_deg": float(np.max(dev[t >= t_end - 1.0])),
        "peak_u": float(np.max(np.abs(sig["Ctrl/u"]))),
        "peak_s": float(np.max(np.abs(sig[base_sig(kind)]))),
        **({"peak_use": float(np.max(sig["Mon/use"]))} if "Mon/use" in sig else {}),
        "ledger_drift": ledger(sig),
    }


def twin_free(dz, t_eval):
    import quadlib as ql
    R = ql.Rig(kind=dz["kind"], L=dz["L"], m=dz["m_model"], b_joint=dz["b_joint"], m_base=dz["m_base"], b_base=dz["b_base"],
               u_max=dz["u_max"], slew=dz["slew"], s_max=dz["s_max"], arm_l=dz["arm_l"], J_hub=dz["J_hub"])
    plant = ql.Plant(R)
    z0 = np.zeros(R.nx)
    z0[:R.nq] = dz["free"]["z0"]
    return ql.free_swing(plant, z0, t_eval)


def compare_free(dz, t, sig) -> dict:
    kind = dz["kind"]
    # event instants repeat a time stamp: compare on the strictly increasing samples
    tt, idx = np.unique(t[t <= dz["free"]["t_end"] + 1e-9], return_index=True)
    ref = twin_free(dz, tt)
    out = {"s": float(np.max(np.abs(sig[base_sig(kind)][idx] - ref[:, 0])))}
    for i in range(4):
        out[f"th{i + 1}_deg"] = float(np.max(np.abs(sig[f"Mon/th{i + 1}"][idx] - np.degrees(ref[:, 1 + i]))))
    out["max_angle_deg"] = max(out[f"th{i + 1}_deg"] for i in range(4))
    # energy of the free swing: only friction removes energy
    out["ledger_drift"] = ledger(sig)
    return out


def design_angle(dz, t_q):
    run = dz["design_run"]
    tt = np.array(run["t"])
    z = np.array(run["z"])
    return [float(np.degrees(np.interp(t_q, tt, z[:, 1 + i]))) for i in range(4)]


def checks_for(dz, m, mb, free, name, t_end, two=True):
    """Checks of one controller (`dz` its design: full travel, or short travel with `free` None) on the
    swing-up model (end time `t_end`, shared by both controllers) and the balance model. `two`: the
    firmware holds both controllers (the limit lines and the travel used are checked as well)."""
    kind = dz["kind"]
    short = dz.get("variant") == "short"
    S, U = base_sig(kind), "Ctrl/u"
    uu = "N" if kind == "cart" else "N m"
    su = "m" if kind == "cart" else "rad"
    t_on, t_s = dz["t_on"], dz["t_s"]
    lim = dz.get("travel", dz["s_max"])
    lim_txt = (f"+-{lim:g} m" if kind == "cart" else f"+-{math.degrees(lim):.0f} deg ({lim:.4f} rad)")
    who = "short-travel controller (Traj/controller = 1)" if short else "full-travel controller (Traj/controller = 0)"
    settle = t_on + t_s + 1.5
    hang = -180.0 if kind == "cart" else 180.0
    E_up = dz["E_up"]
    sw = [
        {"kind": "no_diagnostics", "codes": CODES, "note": "no solver failure, causal conflict, derivative-causal store, algebraic loop or event-limit stop"},
        {"kind": "scene_bindings"},
        {"kind": "max_abs_le", "signal": U, "from_t": 0.0, "to_t": t_on - 0.01, "value": 1e-12,
         "note": "the actuator is off before the swing-up starts"},
        {"kind": "max_abs_le", "signal": base_rate(kind), "from_t": 0.02, "to_t": t_on - 0.01, "value": max(1e-4, 5 * m["rest_rate"]),
         "note": f"hanging at rest before t_on (5x the start-up residual of the pivot compliance, measured {m['rest_rate']:.2g})"},
        {"kind": "cursor_value", "signal": "Mon/th1", "t": t_on - 0.05, "value": hang, "abs": 0.01,
         "note": "link 1 hangs straight down before the swing-up"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": t_on - 0.05, "value": 0.0, "abs": 1e-9, "note": "hold phase"},
        *([{"kind": "final_value", "signal": "Mon/lim_hi", "t": t_end, "value": round(lim, 9), "abs": 1e-9,
            "note": f"the dashboard's limit line follows the {who}: {lim_txt}"}] if two else []),
        {"kind": "cursor_value", "signal": "Ctrl/swinging", "t": t_on + 1.0, "value": 1.0, "abs": 1e-9, "note": "SWINGING UP (TVLQR)"},
        {"kind": "cursor_value", "signal": "Ctrl/balancing", "t": t_on + t_s + 0.5, "value": 1.0, "abs": 1e-9,
         "note": f"BALANCING: the catch region was reached (catch at {m['t_catch']:.3f} s; design closed loop {dz['metrics']['t_catch']:.3f} s)"},
    ]
    for tq in (t_on + 0.4 * t_s, t_on + 0.7 * t_s):
        ref = design_angle(dz, tq)
        for i in range(4):
            sw.append({"kind": "cursor_value", "signal": f"Mon/th{i + 1}", "t": round(tq, 3), "value": round(ref[i], 4), "abs": 2.0,
                       "note": f"swing-up tracks the design closed loop (design value {ref[i]:.2f} deg; 2 deg band)"})
    band = 0.5
    sw += [
        {"kind": "max_abs_le", "signal": "Mon/dev", "from_t": settle, "to_t": t_end, "value": band,
         "note": f"balance holds: every link within {band} deg of upright from {settle:g} s (measured max {m['settled_dev_deg']:.4f} deg)"},
        {"kind": "max_abs_le", "signal": U, "value": dz["u_max"] + 1e-9,
         "note": f"|u| within the actuator limit {dz['u_max']:g} {uu} (firmware clamp; measured peak {m['peak_u']:.2f} {uu}, design {dz['metrics']['peak_u']:.2f})"},
        {"kind": "max_abs", "signal": U, "value": round(m["peak_u"], 4), "rtol": 0.15,
         "note": f"peak actuator effort {m['peak_u']:.2f} {uu} (design closed loop {dz['metrics']['peak_u']:.2f} {uu}); +-15 %"},
        {"kind": "max_abs_le", "signal": S, "value": round(lim, 9),
         "note": (f"travel inside the {who}'s limit {lim_txt} (measured max {m['peak_s']:.3f} {su})" if short else
                  f"the {'cart stays on the +-' + format(dz['s_max'], 'g') + ' m rail' if kind == 'cart' else 'arm stays inside the +-' + format(dz['s_max'], 'g') + ' rad cable limit'} (measured max {m['peak_s']:.3f} {su})")},
        *([{"kind": "max_abs_le", "signal": "Mon/use", "value": 100.0,
            "note": f"travel used stays below 100 % of the {who}'s limit (measured peak {m['peak_use']:.1f} %)"}] if two else []),
        {"kind": "max_abs", "signal": S, "value": round(m["peak_s"], 4), "abs": 0.05 * max(1.0, m["peak_s"]),
         "note": f"peak travel {m['peak_s']:.3f} {su} (design closed loop {dz['metrics']['peak_s']:.3f}; collocation bound {dz['collocation']['s_lim']:g})"},
        {"kind": "final_value", "signal": "Mon/S4", "t": t_end, "value": round(E_up, 6), "abs": 0.01 * E_up,
         "note": f"upright at rest: the stacked energy equals the UPRIGHT level {E_up:.4f} J (measured {m['E_end']:.4f} J)"},
        {"kind": "final_value", "signal": "Mon/E_up", "t": t_end, "value": round(E_up, 9), "abs": 1e-9,
         "note": "UPRIGHT level = sum m_i g 2 h_i of the chain"},
        {"kind": "invariant", "tol": max(1e-3, round(3 * m["ledger_drift"] / E_up, 4)), "scale": E_up,
         "terms": [{"signal": "Mon/E_tot", "coeff": 1.0}, {"signal": "Mon/W_in", "coeff": -1.0}, {"signal": "Mon/W_loss", "coeff": 1.0}],
         "note": (f"energy bookkeeping: E_tot - W_in + W_loss stays constant (work of the actuator minus friction losses equals the "
                  f"change of the mechanical energy); measured drift {m['ledger_drift']:.2e} J (the stiff pivots' spring and damper "
                  f"energy), tolerance 3x that, at least 1e-3 of E_up")},
    ]
    bt = dz["balance"]["t_end"]
    tp = dz["balance"]["push"]["t_start"]
    rec = min(bt - 0.5, tp + max(1.0, 1.3 * mb["t_recover"] + 0.2))
    bal = [
        {"kind": "no_diagnostics", "codes": CODES, "note": "no diagnostics"},
        {"kind": "scene_bindings"},
        {"kind": "cursor_value", "signal": "Ctrl/balancing", "t": 0.01, "value": 1.0, "abs": 1e-9, "note": "balance-only: BALANCING from the start"},
        {"kind": "max_abs_le", "signal": "Mon/dev", "from_t": tp - 0.5, "to_t": tp - 0.01, "value": 0.5,
         "note": f"the start lean is caught: inside 0.5 deg before the push (measured {mb['pre_push_dev_deg']:.3f} deg)"},
        {"kind": "max_abs", "signal": "Mon/dev", "from_t": tp, "to_t": bt, "value": round(mb["peak_dev_after_push_deg"], 4), "rtol": 0.2,
         "note": (f"the {dz['balance']['push']['amplitude']:g} N, 50 ms tip push is real: peak deviation {mb['peak_dev_after_push_deg']:.2f} deg "
                  f"(design {dz['balance']['metrics']['push_peak_dev_deg']:.2f} deg); +-20 %")},
        {"kind": "max_abs_le", "signal": "Mon/dev", "from_t": rec, "to_t": bt, "value": 0.5,
         "note": f"recovered: inside 0.5 deg from {rec:.2f} s (measured {mb['t_recover']:.2f} s after the push)"},
        {"kind": "max_abs_le", "signal": U, "value": dz["u_max"] + 1e-9, "note": f"|u| within the actuator limit (measured peak {mb['peak_u']:.2f} {uu})"},
        *([{"kind": "max_abs_le", "signal": S, "value": round(lim, 9),
            "note": f"push recovery inside the {who}'s travel limit {lim_txt} (measured {mb['peak_s']:.3f} {su}, {mb['peak_use']:.1f} %)"},
           {"kind": "final_value", "signal": "Mon/lim_hi", "t": bt, "value": round(lim, 9), "abs": 1e-9,
            "note": f"the dashboard's limit line follows the {who}"}] if two else
          [{"kind": "max_abs_le", "signal": S, "value": dz["s_max"], "note": f"inside the travel limit (measured {mb['peak_s']:.3f} {su})"}]),
        {"kind": "invariant", "tol": max(1e-3, round(3 * mb["ledger_drift"] / E_up, 4)), "scale": E_up,
         "terms": [{"signal": "Mon/E_tot", "coeff": 1.0}, {"signal": "Mon/W_in", "coeff": -1.0}, {"signal": "Mon/W_loss", "coeff": 1.0}],
         "note": f"energy bookkeeping (measured drift {mb['ledger_drift']:.2e} J)"},
    ]
    if short:
        ov = {"overrides": SHORT}
        return {
            f"{name}-swingup-short": {"model": f"{name}-swingup", **ov, "run_timeout": 1800, "checks": sw},
            f"{name}-balance-short": {"model": f"{name}-balance", **ov, "run_timeout": 900, "checks": bal},
        }
    tol_s = max(2e-5, round(3 * free["s"], 7))
    tol_a = max(2e-3, round(3 * free["max_angle_deg"], 5))
    fr = [{"kind": "no_diagnostics", "codes": CODES, "note": "no diagnostics"}, {"kind": "scene_bindings"}]
    for k, tq in enumerate(dz["free"]["t"]):
        z = dz["free"]["z"][k]
        note = (f"Python twin (Lagrangian, scipy DOP853 at rtol 1e-11) vs bond graph, open-loop free swing from rest; "
                f"tolerance 3x the measured max difference ({free['s']:.2g} {su}, {free['max_angle_deg']:.2g} deg)")
        fr.append({"kind": "cursor_value", "signal": S, "t": tq, "value": round(z[0], 9), "abs": tol_s, "note": note})
        phi = np.degrees(np.array(z[1:]))
        for i in range(4):
            fr.append({"kind": "cursor_value", "signal": f"Mon/th{i + 1}", "t": tq, "value": round(float(phi[i]), 7), "abs": tol_a, "note": note})
    fr.append({"kind": "invariant", "tol": max(1e-4, round(3 * free["ledger_drift"] / E_up, 6)), "scale": E_up,
               "terms": [{"signal": "Mon/E_tot", "coeff": 1.0}, {"signal": "Mon/W_in", "coeff": -1.0}, {"signal": "Mon/W_loss", "coeff": 1.0}],
               "note": f"free swing: mechanical energy + friction losses constant (measured drift {free['ledger_drift']:.2e} J)"})
    return {
        f"{name}-swingup": {"run_timeout": 1800, "checks": sw},
        f"{name}-balance": {"run_timeout": 900, "checks": bal},
        f"{name}-free": {"run_timeout": 900, "checks": fr},
    }


def main(argv):
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    runs = HERE / "_runs"
    kinds = [k for k in ("cart", "rotary") if (HERE / f"design_{k}.json").is_file() and (only is None or only == k)]
    if "--no-run" not in argv:
        models = [f"{RIGS[k]}-{s}" for k in kinds for s in ("free", "balance", "swingup")]
        models += [(f"{RIGS[k]}-{s}-short", f"{RIGS[k]}-{s}", SHORT) for k in kinds for s in ("balance", "swingup")
                   if (HERE / f"design_{k}_short.json").is_file()]
        stats = runner.run_models("quad-pendulum", models, runs, timeout=2400.0)
        old = json.loads((HERE / "run_stats.json").read_text()) if (HERE / "run_stats.json").is_file() else {}
        old.update({k: {"seconds": round(v["seconds"], 1), "points": v["points"]} for k, v in stats.items()})
        (HERE / "run_stats.json").write_text(json.dumps(old, indent=2) + "\n", encoding="utf-8", newline="\n")
    path = ROOT / "expected.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"project": "quad-pendulum", "models": {}}
    doc["project"] = "quad-pendulum"
    doc["description"] = (
        "A chain of four pendulum links swung up from hanging and balanced upright, on a cart (planar multibond bond graph, "
        "ideal force actuator) and on a rotary arm (Furuta, spatial multibond bond graph, ideal torque). 1 kHz firmware: "
        "feed-forward + discrete time-varying LQR along an offline direct-collocation trajectory, latched infinite-horizon LQR "
        "in the catch region. The cart has two controllers, chosen at run time by Traj/controller (dashboard select): the "
        "full-travel design and a short-travel design planned and tuned for +-0.5 m on the same plant; the -short entries "
        "run the same models with Traj/controller = 1. Monitors: link angles, energy per link from the body twists and "
        "poses, the energy ledger, the cart travel against the chosen controller's limit. "
        "The -free models compare the bond graph with the Python (Lagrangian) twin.")
    mpath = HERE / "measured.json"
    measured = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else {}
    for kind in kinds:
        dz = json.loads((HERE / f"design_{kind}.json").read_text(encoding="utf-8"))
        ps = HERE / f"design_{kind}_short.json"
        dzs = json.loads(ps.read_text(encoding="utf-8")) if ps.is_file() else None
        two = dzs is not None
        name = RIGS[kind]
        t_end = max(dz["t_end"], dzs["t_end"]) if two else dz["t_end"]
        t, sig = runner.load(runs / f"{name}-swingup.npz")
        tb, sigb = runner.load(runs / f"{name}-balance.npz")
        tf, sigf = runner.load(runs / f"{name}-free.npz")
        m = measure_swingup(dz, t, sig)
        mb = measure_balance(dz, tb, sigb)
        free = compare_free(dz, tf, sigf)
        print(f"[{kind}] swing-up :", {k: (round(v, 5) if isinstance(v, float) else v) for k, v in m.items()})
        print(f"[{kind}] design   :", {k: round(v, 5) for k, v in dz["metrics"].items() if isinstance(v, float)})
        print(f"[{kind}] balance  :", {k: round(v, 5) for k, v in mb.items()})
        print(f"[{kind}] free twin:", {k: f"{v:.3g}" for k, v in free.items()})
        measured[kind] = {"swingup": m, "balance": mb, "free": free}
        doc["models"].update(checks_for(dz, m, mb, free, name, t_end, two))
        if two:
            ts_, sigs = runner.load(runs / f"{name}-swingup-short.npz")
            tbs, sigbs = runner.load(runs / f"{name}-balance-short.npz")
            ms = measure_swingup(dzs, ts_, sigs)
            mbs = measure_balance(dzs, tbs, sigbs)
            print(f"[{kind}] swing-up short:", {k: (round(v, 5) if isinstance(v, float) else v) for k, v in ms.items()})
            print(f"[{kind}] design short  :", {k: round(v, 5) for k, v in dzs["metrics"].items() if isinstance(v, float)})
            print(f"[{kind}] balance short :", {k: round(v, 5) for k, v in mbs.items()})
            measured[kind] |= {"swingup_short": ms, "balance_short": mbs}
            doc["models"].update(checks_for(dzs, ms, mbs, None, name, t_end))
    mpath.write_text(json.dumps(measured, indent=2) + "\n", encoding="utf-8", newline="\n")
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path)


if __name__ == "__main__":
    main(sys.argv[1:])
