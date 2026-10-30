"""Write ``../expected.json`` (the acceptance checks of ``examples/run_checks.py``).

The tolerances are measured, not guessed. Whole-run torque bounds are about 1.25x the
largest error of the real run, which occurs in the first millisecond (the compliant pivots,
kt = 1e8 N/m, ring once when the jerk steps from 0); the settled bounds hold from t = 0.02 s.
Both are below 0.15 % of the peak joint torque. The forward drift bounds are the measured
open-loop drift over 1 s (it grows with the gravity dynamics) with about 1.5x margin.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "expected.json"
IDLE = ["E101", "E102", "E103", "E106", "E108", "E900", "E901", "W206"]
TIP_A = {1: 0.675, 2: 0.525, 3: 0.370}

# (arm, joint): (whole run, from 0.02 s) bound in N*m for the inverse model; payload separately
INV = {(1, 1): (6e-4, 1e-5),
       (2, 1): (0.017, 2.5e-4), (2, 2): (0.0045, 7e-5),
       (3, 1): (0.10, 1.2e-3), (3, 2): (0.038, 4.5e-4), (3, 3): (5e-4, 6e-6)}
PAY = {(3, 1): (0.17, 1.8e-3), (3, 2): (0.07, 7.5e-4), (3, 3): (0.009, 1e-4)}
FWD = {(1, 1): 3e-7, (2, 1): 2e-6, (2, 2): 3e-6, (3, 1): 5e-6, (3, 2): 7e-6, (3, 3): 1.2e-6}


def fk_entries(arms, payload=False):
    out = []
    for n in arms:
        tip = TIP_A[n] + (0.1 if payload else 0.0)
        sig_x = [f"A{n}_PoseTip/g[2]"]
        if len(arms) > 1 and n > 1:
            sig_x.insert(0, f"A{n}_BaseX/y")
        out.append({"link": f"a{n}_link{n}", "point": [tip, 0, 0],
                    "signals": [sig_x if len(sig_x) > 1 else sig_x[0], None, f"A{n}_PoseTip/g[3]"],
                    "tol": 1e-6})
    return out


def inverse_checks(arms, bounds, payload=False):
    checks = [{"kind": "scene_bindings", "fk": fk_entries(arms, payload)}]
    for n in arms:
        for j in range(1, n + 1):
            whole, settled = bounds[(n, j)]
            for ref in ("rtb", "an"):
                sig = f"A{n}_TauErr{j}/e_{ref}"
                checks.append({"kind": "max_abs_le", "signal": sig, "value": whole,
                               "note": f"required torque of the bond-graph joint {j} of the {n}-link arm "
                                       f"vs {'Robotics Toolbox' if ref == 'rtb' else 'the analytical model'}"})
                checks.append({"kind": "max_abs_le", "signal": sig, "from_t": 0.02, "value": settled,
                               "note": "after the start-up transient of the compliant pivots"})
        for j in range(1, n + 1):
            end = -1.5707963267948966 - 1.0 if j == 1 else -1.0
            checks.append({"kind": "cursor_value", "signal": f"A{n}_Joint{j}/qout", "t": 1.0,
                           "value": end, "abs": 1e-6,
                           "note": "the integrated CSV joint speed reaches the CSV end angle"})
    checks.append({"kind": "no_diagnostics", "codes": IDLE})
    return checks


def main():
    models = {
        "planar-links": {"checks": inverse_checks((1, 2, 3), INV)},
        "planar-links-payload": {"checks": inverse_checks((3,), PAY, payload=True)},
    }
    fwd = [{"kind": "scene_bindings", "fk": fk_entries((1, 2, 3))}]
    for (n, j), tol in FWD.items():
        fwd.append({"kind": "max_abs_le", "signal": f"A{n}_QErr{j}/e", "value": tol,
                    "note": f"open-loop angle drift of joint {j} of the {n}-link arm over 1 s"})
    fwd.append({"kind": "no_diagnostics", "codes": IDLE})
    models["planar-links-fwd"] = {"checks": fwd}
    doc = {
        "project": "planar-links",
        "description": "X5.9 acceptance: the 1-, 2- and 3-link planar arms of planar_robot.py on the "
                       "planar multibond elements, compared with the closed-form model and Peter "
                       "Corke's Robotics Toolbox through CsvSource. planar-links: inverse dynamics "
                       "(joint speeds from the CSV, required torque out); planar-links-fwd: forward "
                       "dynamics (CSV torque in, angle drift out); planar-links-payload: the 3-link "
                       "arm with the 1 kg payload against the 4-link RTB robot.",
        "models": models,
    }
    with open(OUT, "w", newline="\n") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
