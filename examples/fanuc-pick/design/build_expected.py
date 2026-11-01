"""Write examples/fanuc-pick/expected.json from design/reference.json (run reference.py first).

    uv run examples/fanuc-pick/design/build_expected.py

Every model: the scene bindings with a forward-kinematics check (the URDF tree of the scene
driven by the joint references against the planner's closed-form flange position), no solver or
structure diagnostics, the planned cycle time, and the holding outcome of the reduced model
(held with its margin, or the drop). Extra checks: the vacuum at the lift (seal ODE), the static
cup forces of `static-hold` (hand calculation), the bounds of the optimum models (margin at least
the requirement, robot limits at most 100 %) and the power ledger of `pick-place`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_models as B  # noqa: E402

NL = "\n"
DIAG = ["W201", "W205", "W206", "E006", "E007", "E101", "E102", "E103", "E106", "E901"]
M_ABS = 0.03          # bg-sim against the reduced model: holding margin
M_SLACK = 0.02        # the optimum models: margin at least M_req - M_SLACK in bg-sim


def r6(x: float) -> float:
    return float(f"{x:.6g}")


def model_checks(name: str, m: dict, ref: dict, best: bool) -> list[dict]:
    tL, tE, tF = m["tL"], m["tE"], m["tF"]
    checks: list[dict] = [
        {"kind": "scene_bindings",
         "fk": [{"link": "gripper", "point": [0, 0, 0],
                 "signals": ["Planner/gref[5]", "Planner/gref[6]", "Planner/gref[7]"], "tol": 1e-6}],
         "note": "the URDF joint tree of the scene, driven by Planner/qr, puts the flange where the planner's "
                 f"closed-form kinematics say (reference.py: URDF chain against gref {m['fk']['pos']:.0e} m)"},
        {"kind": "no_diagnostics", "codes": DIAG},
        {"kind": "cursor_value", "signal": "Planner/T_cyc", "t": r6(tF), "value": round(m["T_cyc"], 9), "rtol": 1e-6,
         "note": "the cycle time of planner.reference (approach start to depart end)"},
    ]
    if m["dropped"]:
        checks += [
            {"kind": "cursor_value", "signal": "Monitor/held_ok", "t": r6(tF), "value": 0.0, "abs": 1e-9,
             "note": "the reduced model drops the parcel too: the cups peel and the drop latch is set"},
            {"kind": "min_ge", "signal": "Monitor/sep", "from_t": r6(tE - 0.02), "to_t": r6(tE - 0.002), "value": 0.02,
             "note": "the parcel is more than d_drop = 20 mm from where it sat in the gripper at the place"},
        ]
    else:
        checks += [
            {"kind": "min_ge", "signal": "Monitor/held_ok", "from_t": 0.0, "to_t": r6(tF), "value": 0.5,
             "note": "held from the pick to the place (no drop)"},
            {"kind": "cursor_value", "signal": "Monitor/M_tot", "t": r6(tF), "value": r6(m["M_tot"]), "abs": M_ABS,
             "note": f"holding margin of the reduced model (reduced.py), {m['M_tot']:.3f}, within {M_ABS}"},
            {"kind": "min_ge", "signal": "Monitor/sep", "from_t": r6(tL + 0.002), "to_t": r6(tE - 0.002), "value": -1e-9},
            {"kind": "max_abs_le", "signal": "Monitor/sep", "from_t": r6(tL + 0.002), "to_t": r6(tE - 0.002),
             "value": 0.02, "note": "the parcel stays within d_drop of its grip position while carried"},
        ]
    if best:
        checks += [
            {"kind": "min_ge", "signal": "Monitor/M_tot", "from_t": r6(tE), "to_t": r6(tF), "value": r6(m["M_req"] - M_SLACK),
             "note": f"the optimum keeps the required margin {m['M_req']} (bg-sim within {M_SLACK} of the reduced model)"},
            {"kind": "max_abs_le", "signal": "Planner/util_max", "from_t": 0.0, "to_t": r6(tF), "value": 100.0,
             "note": "inside the LR-10iA/10 limits (joint ranges, rates, accelerations, jerks, wrist moment and inertia)"},
        ]
    if name == "pick-place":
        checks += [
            {"kind": "cursor_value", "signal": "Cup1/dp", "t": r6(tL), "value": r6(m["dp_lift"][0]), "rtol": 2e-3,
             "note": "vacuum at the lift start: the seal ODE from the lip contact (reduced.Pick.seal)"},
            {"kind": "energy_ledger", "tol": 1e-6,
             "note": "the port-power ledger closes (Tellegen: every bond's two ports carry opposite power)"},
        ]
    if name == "static-hold":
        sh = ref["static_hold"]
        t = r6(sh["t_mid"])
        for k, T in enumerate(sh["T"], start=1):
            checks.append({"kind": "cursor_value", "signal": f"Cup{k}/T", "t": t, "value": r6(T),
                           "rtol": 0.02, "abs": 0.05,
                           "note": f"static cup force of zone {k} (hand calculation of reference.py: rigid plate on "
                                   "five bellows, axial and tilt springs, CoM below the lip plane)"})
        checks.append({"kind": "cursor_value", "signal": "Cup2/U", "t": t, "value": r6(sh["U"][1]), "rtol": 0.03,
                       "note": "utilisation of the most loaded cup at rest: (T + 4 k_t |phi| / D_lip) / (A_eff dp): the "
                               "centre grip cannot reach the margin of 0.5 with this carton"})
        checks.append({"kind": "cursor_value", "signal": "Cup1/dp", "t": t, "value": r6(ref["vacuum"]["dp_op"]),
                       "rtol": 1e-3, "note": "operating vacuum: the ejector curve meets the lip leak plus the Darcy "
                                             "flow through the carton"})
    return checks


def main() -> int:
    ref = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
    res_path = HERE / "results.json"
    best_models = set()
    if res_path.exists():
        for case in json.loads(res_path.read_text(encoding="utf-8")).get("cases", []):
            if case.get("best") and case.get("model"):
                best_models.add(case["model"])
    models = {}
    for name in B.all_scenarios():
        m = ref["models"][name]
        models[name] = {"run_timeout": 1200, "checks": model_checks(name, m, ref, name in best_models)}
    doc = {
        "project": "fanuc-pick",
        "description": "FANUC LR-10iA/10 (LR Mate 200iD/7L geometry, kinematic: it follows the plan inside the "
                       "datasheet limits) picks a carton with a five-zone suction gripper (pneumatic cylinders, "
                       "bellows cups, one ejector per zone) and places it turned. The checks pin the planner "
                       "kinematics to the URDF, the cycle times, the vacuum and the static cup forces to hand "
                       "calculations, and the holding outcome of every model to the reduced model of the optimiser.",
        "models": models,
    }
    (ROOT / "expected.json").write_text(json.dumps(doc, indent=2) + NL, encoding="utf-8", newline=NL)
    print("wrote expected.json:", ", ".join(f"{k} ({len(v['checks'])})" for k, v in models.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
