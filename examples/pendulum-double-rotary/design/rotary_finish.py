"""Run the bond-graph models, measure the scenario, write `expected.json` (X5.13).

    uv run examples/pendulum-double-rotary/design/finish.py

1. runs `<example>-free` and `<example>` on the real backend (runner.py) and keeps the runs in
   `design/_runs/`;
2. compares the free swing of the design model (rotary_design.free_swing) with the bond graph;
3. measures swing-up, catch, balance band, disturbance and recovery on the bond-graph run and
   writes `design/measured.json`;
4. writes `expected.json` from the design numbers and the measurements, with the tolerances
   named in each check's note.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import rotary_design as rd
import rotary_lib as rl
import runner

CODES = ["W201", "W206", "E901"]


def measure(dz: dict, t, sig) -> dict:
    n = dz["n_links"]
    dev = sig["Angles/dev"]
    t_on, t_dist = dz["t_on"], dz["t_dist"]
    phase = sig["Ctrl/phase"]
    near = np.where((dev < math.radians(3.0)) & (t > t_on))[0]
    t_upright = float(t[near[0]]) if len(near) else math.nan
    t_catch = float(t[np.argmax(phase >= 2)]) if np.any(phase >= 2) else math.nan
    pre = (t >= t_catch + 1.5) & (t < t_dist)
    post = (t >= t_dist) & (t <= t_dist + 2.0)
    tip = sig[f"Angles/phi{n}"]
    outside = np.where((dev > math.radians(0.5)) & (t >= t_dist))[0]
    rest = (t > 0.05) & (t < t_on)
    return {
        "t_upright": t_upright,
        "t_catch": t_catch,
        "band_pre_deg": math.degrees(float(np.max(dev[pre]))),
        "peak_defl_deg": math.degrees(float(np.max(np.abs(tip[post])))),
        "t_recover": float(t[outside[-1]]) - t_dist if len(outside) else 0.0,
        "final_dev_deg": math.degrees(float(dev[-1])),
        "peak_v": float(np.max(np.abs(sig["Ctrl/u"]))),
        "max_arm": float(np.max(np.abs(sig["J1/qout"]))),
        "rest_rate": float(np.max(np.abs(sig["J1/qdout"][rest]))),
        "rest_motion": float(max(np.ptp(sig[f"J{k + 2}/qout"][rest]) for k in range(n))),
    }


def compare_free(dz: dict, plant: rl.Plant, t, sig) -> dict:
    tn, xf, phif = rd.free_swing(plant, np.array(dz["free_start"]), dz["t_free"])
    out = {}
    worst = 0.0
    cols = [("J1/qout", xf[:, 0])] + [(f"Angles/phi{k + 1}", phif[:, k]) for k in range(plant.n_links)]
    for name, col in cols:
        diff = float(np.max(np.abs(np.interp(tn, t, sig[name]) - col)))
        out[name] = diff
        worst = max(worst, diff)
    out["max"] = worst
    return out


def expected(dz: dict, m: dict, free: dict, name: str) -> dict:
    n = dz["n_links"]
    t_on, t_s, t_dist = dz["t_on"], dz["t_s"], dz["t_dist"]
    t_catch = t_on + t_s
    t_end = dz["t_end"]
    band = max(1.0, 2.0 * m["band_pre_deg"])  # degrees
    t_rec = min(t_dist + 1.25 * m["t_recover"] + 0.3, t_end - 1.0)
    checks = [
        {"kind": "scene_bindings"},
        {"kind": "no_diagnostics", "codes": CODES,
         "note": "no derivative-causality warning, no event-loop warning, no solver failure"},
        {"kind": "max_abs_le", "signal": "J1/qdout", "from_t": 0.05, "to_t": t_on - 0.01,
         "value": max(2e-3, 5 * m["rest_rate"]),
         "note": "at rest before t_on: the arm does not move (motor voltage 0). Bound: 5x the measured start-up residual of the released joint compliance"},
        {"kind": "cursor_value", "signal": "J2/qout", "t": t_on - 0.05, "value": math.pi, "abs": 2e-3,
         "note": "hanging straight down before t_on (link 1 at pi); 2 mrad is larger than the measured joint sag"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": t_on - 0.05, "value": 0.0, "abs": 1e-9,
         "note": "controller idle before t_on"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "from_t": 0.0, "to_t": t_on - 0.01, "value": 1e-12,
         "note": "motor voltage 0 before t_on"},
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": t_catch + 1.0, "value": 2.0, "abs": 1e-9,
         "note": "the balance controller has taken over one second after t_on + T_s"},
        {"kind": "cursor_value", "signal": "Angles/dev", "t": t_catch + 0.5, "value": 0.0,
         "abs": math.radians(band),
         "note": f"upright reached by t_on + T_s + 0.5 s = {t_catch + 0.5:g} s: every link within {band:.1f} deg (measured settled band {m['band_pre_deg']:.2f} deg)"},
        {"kind": "max_abs_le", "signal": "Angles/dev", "from_t": t_catch + 1.5, "to_t": t_dist - 0.01,
         "value": math.radians(band),
         "note": f"all link angles inside {band:.1f} deg of upright between catch + 1.5 s and the disturbance (measured max {m['band_pre_deg']:.2f} deg; the bound is 2x, at least 1 deg)"},
        {"kind": "max_abs", "signal": f"Angles/phi{n}", "from_t": t_dist, "to_t": t_dist + 2.0,
         "value": math.radians(m["peak_defl_deg"]), "rtol": 0.3,
         "note": f"the disturbance is real: the tip link deflects by {m['peak_defl_deg']:.1f} deg (design.py: {dz['metrics']['peak_defl_deg']:.1f} deg); accepted band +-30 %"},
        {"kind": "max_abs_le", "signal": "Angles/dev", "from_t": t_rec, "to_t": t_end,
         "value": math.radians(band),
         "note": f"recovered: back inside {band:.1f} deg from {t_rec:g} s (measured: inside 0.5 deg after {m['t_recover']:.2f} s)"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "value": dz["vmax"] + 1e-9,
         "note": "the motor voltage never exceeds the +-10 V amplifier limit (clamped in the firmware)"},
        {"kind": "max_abs_le", "signal": "J1/qout", "value": 2.0,
         "note": "the arm stays inside +-2 rad (the swing-up trajectory is bounded by 2 rad)"},
    ]
    models = {name: {"run_timeout": 1500.0, "checks": checks}}
    free_checks = [{"kind": "scene_bindings"}, {"kind": "no_diagnostics", "codes": CODES}]
    tol = max(3e-3, 2.0 * free["max"])
    for i, tt in enumerate(dz["free_samples"]["t"]):
        if i % 2 == 0:
            continue  # t = 0.5, 1.0, ... (the file holds every 0.25 s)
        note = (f"design.py free swing vs bond graph, open loop from rest with the motor terminals at 0 V; "
                f"tolerance 2x the measured max difference {free['max']:.2g} rad (at least 3 mrad)")
        free_checks.append({"kind": "cursor_value", "signal": "J1/qout", "t": tt,
                            "value": dz["free_samples"]["q"][i][0], "abs": tol, "note": note})
        for k in range(n):
            free_checks.append({"kind": "cursor_value", "signal": f"Angles/phi{k + 1}", "t": tt,
                                "value": dz["free_samples"]["phi"][i][k], "abs": tol, "note": note})
    models[f"{name}-free"] = {"run_timeout": 900.0, "checks": free_checks}
    return {"project": name, "description": dz["comment"], "models": models}


def run(example_dir: Path, n_links: int, argv: list[str]) -> None:
    if "--docs" in argv:
        import rotary_docs

        rotary_docs.write(example_dir, n_links, example_dir / "design" / "_shots" / "3d.png")
        return
    dz = json.loads((example_dir / "design" / "design.json").read_text(encoding="utf-8"))
    name = dz["example"]
    plant = rl.Plant(n_links, *rl.LINKS[n_links])
    runs = example_dir / "design" / "_runs"
    if "--no-run" not in argv:
        stats = runner.run_models(name, [f"{name}-free", name], runs)
        (example_dir / "design" / "_run_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    t, sig = runner.load(runs / f"{name}.npz")
    tf, sigf = runner.load(runs / f"{name}-free.npz")
    free = compare_free(dz, plant, tf, sigf)
    m = measure(dz, t, sig)
    print("design-vs-bond-graph free swing, max |difference| [rad]:", {k: round(v, 5) for k, v in free.items()})
    print("bond graph:", {k: round(v, 4) for k, v in m.items()})
    print("design.py :", {k: round(v, 4) for k, v in dz["metrics"].items() if isinstance(v, float)})
    (example_dir / "design" / "measured.json").write_text(
        json.dumps({"bond_graph": m, "free_diff": free}, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    doc = expected(dz, m, free, name)
    (example_dir / "expected.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {example_dir / 'expected.json'}")
