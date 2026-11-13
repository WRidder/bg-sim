# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Write `expected.json` of `humanoid-dual-arm` from the independent references and four measured runs.

    uv run examples/humanoid-dual-arm/design/build_expected.py --ik <run> --ik6 <run> --hold <run> --hold6 <run>

The runs are the four scenarios of `expected.json` (`design/run_model.jl`, the 6-DOF ones with
`{"Traj/dof6": true}`). The expected values come from `design/references.json`
(`design/references.py`: the page's IK in numpy, the Python twin of the firmware, the forward
kinematics of the start posture), never from the runs. The runs only set the tolerances: each
bound is a stated multiple (5x) of the measured deviation with a floor, and the note records the
measurement. The task limits of the page (hand pose held under 2 mm and 2 deg) are absolute.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import humanoid as dz
import references
import srs
from runio import at, load_run

ROOT = Path(__file__).resolve().parent.parent
FACTOR = 5.0
NO_CODES = ["W201", "W205", "W206", "E006", "E007", "E101", "E102", "E103", "E106", "E901"]
DOF6 = {"Traj/dof6": True}
T_HOLD, T_BIAS, T_END = dz.T_HOLD, dz.T_BIAS, dz.T_END
T_MOVED = dz.TIMING["settle"] + dz.TIMING["move"]  # the object arrives at the commanded pose
W_DWELL = (T_MOVED + 0.5, T_HOLD + 0.05)  # converged at the commanded pose, bias 0
W_BIAS = (T_HOLD + 0.05, T_END)  # bias ramp and hold
T_TRACK = 0.0
INSTANCES = {"L": "IKL", "R": "IKR", "IL": "IdealL", "IR": "IdealR"}


def bound(measured: float, floor: float) -> float:
    return float(f"{max(FACTOR * measured, floor):.2g}")


def no_diagnostics() -> dict:
    return {"kind": "no_diagnostics", "codes": NO_CODES,
            "note": "no causality, unit, connection or solver diagnostics"}  # fmt: skip


def cursor(sig: str, tc: float, value: float, tol: float, note: str) -> dict:
    return {"kind": "cursor_value", "signal": sig, "t": round(tc, 6), "value": float(value), "abs": tol, "note": note}


class Run:
    def __init__(self, path: Path):
        self.t, self.c = load_run(path)

    def at(self, sig: str, tc: float) -> float:
        return at(self.t, self.c[sig], tc)

    def peak(self, sig: str, a: float, b: float) -> float:
        m = (self.t >= a) & (self.t <= b)
        return float(np.abs(self.c[sig][m]).max())

    def low(self, sig: str, a: float, b: float) -> float:
        m = (self.t >= a) & (self.t <= b)
        return float(self.c[sig][m].min())


# ------------------------------------------------------------------ humanoid-ik


def ik_checks(refs: dict, run: Run, dof6: bool) -> list[dict]:
    tw = refs["twin"]["6dof" if dof6 else "7dof"]
    page = refs["page"]
    dof = "6dof" if dof6 else "7dof"
    checks: list[dict] = [] if dof6 else [{"kind": "scene_bindings"}]
    # 1. the in-model IK equals the Python twin of the firmware, tick by tick
    for key, inst in INSTANCES.items():
        for tname, tc in (("t_hold", T_HOLD), ("t_bias", T_BIAS)):
            ref = tw[tname][key]
            for k in range(1, 8):
                sig = f"{inst}/q{k}"
                meas = abs(run.at(sig, tc) - ref["q"][k - 1])
                checks.append(cursor(sig, tc, ref["q"][k - 1], bound(meas, 1e-9),
                                     f"in-model ArmIK equals its numpy twin (humanoid.twin) at the {tname[2:]} instant; measured |delta| {meas:.2g} deg"))  # fmt: skip
            for sig_name, ref_key, unit in (("pe", "pe", "mm"), ("oe", "oe", "deg"), ("lim", "lim", "%")):
                sig = f"{inst}/{sig_name}"
                meas = abs(run.at(sig, tc) - ref[ref_key])
                checks.append(cursor(sig, tc, ref[ref_key], bound(meas, 1e-9),
                                     f"{sig_name} readout equals the twin; measured |delta| {meas:.2g} {unit}"))  # fmt: skip
    # 2. against the page's own solver (finite-difference Jacobian, iterated to rest from home)
    for key, inst, ideal in (("L", "IKL", "stacked"), ("IL", "IdealL", "ideal")):
        for tc, bias in ((T_HOLD, 0), (T_BIAS, 30)):
            ref = page[f"{dof}_{ideal}_bias{bias}"]
            for sig_name, ref_key, floor in (("pe", "pe_mm", 0.02), ("oe", "oe_deg", 0.02)):
                sig = f"{inst}/{sig_name}"
                meas = abs(run.at(sig, tc) - ref[ref_key])
                checks.append(cursor(sig, tc, ref[ref_key], bound(meas, floor),
                                     f"the page's IK (srs.solve, 1 deg finite-difference Jacobian, iterated to rest) at the default pose, bias {bias} deg: "
                                     f"{ref[ref_key]:.4g}; measured |delta| {meas:.2g}"))  # fmt: skip
            for k in range(1, 8):
                sig = f"{inst}/q{k}"
                meas = abs(run.at(sig, tc) - ref["q"][k - 1])
                checks.append(cursor(sig, tc, ref["q"][k - 1], bound(meas, 0.05),
                                     f"joint {k} of the page's IK solution (bias {bias} deg); measured |delta| {meas:.2g} deg (exact vs 1 deg finite-difference Jacobian)"))  # fmt: skip
    if not dof6:
        # 3. the 7-DOF arms hold the pose (page: pe < 2 mm and oe < 2 deg) at bias 0 and under the bias
        for inst in INSTANCES.values():
            for sig_name, lim in (("pe", 2.0), ("oe", 2.0)):
                sig = f"{inst}/{sig_name}"
                meas = run.peak(sig, W_DWELL[0], T_END)
                checks.append({"kind": "max_abs_le", "signal": sig, "from_t": W_DWELL[0], "to_t": T_END, "value": lim,
                               "note": f"7-DOF holds the commanded pose (page limit {lim:g}) through the dwell and the elbow-bias sweep; measured peak {meas:.3g}"})  # fmt: skip
            checks.append({"kind": "min_ge", "signal": f"{inst}/held", "from_t": W_DWELL[0], "to_t": T_END, "value": 1.0,
                           "note": "the held indicator stays on"})  # fmt: skip
        # 4. the elbow moves under the bias (self-motion), the hand does not
        for inst, key in (("IKL", "L"), ("IKR", "R")):
            e0 = np.array([run.at(f"{inst}/e{c}", T_HOLD) for c in "xyz"])
            e1 = np.array([run.at(f"{inst}/e{c}", T_BIAS) for c in "xyz"])
            r0 = np.array(tw["t_hold"][key]["elbow"])
            r1 = np.array(tw["t_bias"][key]["elbow"])
            for j, c in enumerate("xyz"):
                for tc, val, ref in ((T_HOLD, e0[j], r0[j]), (T_BIAS, e1[j], r1[j])):
                    meas = abs(val - ref)
                    checks.append(cursor(f"{inst}/e{c}", tc, ref, bound(meas, 1e-6),
                                         f"elbow {c} (page frame) of the twin; bias {0 if tc == T_HOLD else dz.BIAS:g} deg; the elbow moves "
                                         f"{1000 * np.linalg.norm(r1 - r0):.1f} mm between the two instants while the hand stays on target; measured |delta| {meas:.2g} m"))  # fmt: skip
    else:
        # 3. the 6-DOF arms (J5 locked) fail: joints on their limits, residual error, no self-motion
        for inst in ("IKL", "IKR"):
            for k, val, why in ((3, -90.0, "J3 on its lower limit -90 deg"), (6, -60.0, "J6 on its lower limit -60 deg"),
                                (5, 0.0, "J5 locked at 0")):  # fmt: skip
                sig = f"{inst}/q{k}"
                meas = abs(run.at(sig, T_HOLD) - val)
                checks.append(cursor(sig, T_HOLD, val, bound(meas, 1e-9), f"6-DOF: {why}; measured |delta| {meas:.2g} deg"))
            checks.append({"kind": "max_abs_le", "signal": f"{inst}/lim", "from_t": W_DWELL[0], "to_t": T_END, "value": 1e-9,
                           "note": "6-DOF: a joint sits on its limit (nearest limit 0 %) through the dwell and the bias sweep"})  # fmt: skip
            checks.append({"kind": "max_abs_le", "signal": f"{inst}/held", "from_t": W_DWELL[0], "to_t": T_END, "value": 0.0,
                           "note": "6-DOF stacked arm misses the pose (page: not held)"})  # fmt: skip
            for sig_name, lo in (("pe", 3.0), ("oe", 3.0)):
                sig = f"{inst}/{sig_name}"
                meas = run.low(sig, W_DWELL[0], T_END)
                checks.append({"kind": "min_ge", "signal": sig, "from_t": W_DWELL[0], "to_t": T_END, "value": lo,
                               "note": f"6-DOF residual hand error stays above {lo:g} (twin {tw['t_hold']['L'][sig_name]:.3f}); measured minimum {meas:.4g}"})  # fmt: skip
        for c in "xyz":
            sig = f"IKL/e{c}"
            d = abs(run.at(sig, T_BIAS) - run.at(sig, T_HOLD))
            ref = tw["t_hold"]["L"]["elbow"]["xyz".index(c)]
            checks.append(cursor(sig, T_BIAS, ref, bound(d, 1e-6),
                                 f"6-DOF: no slack, the elbow bias does not move the elbow (value of the bias-0 twin); measured shift {d:.2g} m"))  # fmt: skip
        checks.append({"kind": "min_ge", "signal": "IdealL/held", "from_t": W_DWELL[0], "to_t": T_END, "value": 1.0,
                       "note": "the ideal SRS (no offsets) still holds the pose with J5 locked (page: 0.96 mm, 0.77 deg), the stacked offsets are what break it"})  # fmt: skip
    checks.append(no_diagnostics())
    return checks


# ------------------------------------------------------------------ humanoid-hold


def hold_checks(refs: dict, run: Run, dof6: bool) -> list[dict]:
    tw = refs["twin"]["6dof" if dof6 else "7dof"]
    fk = refs["fk"]
    checks: list[dict] = [] if dof6 else [{"kind": "scene_bindings"}]
    if not dof6:
        # forward kinematics of the start posture through the multibody pose chain
        for k in range(1, 8):
            for p in "LR":
                sig = f"{p}Arm{k}/J/qout"
                checks.append(cursor(sig, 0.0, fk[p]["q_rad"][k - 1], 1e-9,
                                     "starts at the 6-DOF solution of the start pose (drive springs preloaded with the holding torque)"))  # fmt: skip
        for p in "LR":
            for i in range(1, 8):
                sig = f"{p}Hand/g[{i}]"
                meas = abs(run.at(sig, 0.0) - fk[p]["hand"][i - 1])
                checks.append(cursor(sig, 0.0, fk[p]["hand"][i - 1], bound(meas, 1e-9),
                                     f"hand pose of the start posture: numpy FK (srs.fk in the bg-sim world); measured |delta| {meas:.2g}"))  # fmt: skip
        for j, c in enumerate("xyz"):
            sig = f"LArm4/W/g[{5 + j}]"
            meas = abs(run.at(sig, 0.0) - fk["L"]["elbow"][j])
            checks.append(cursor(sig, 0.0, fk["L"]["elbow"][j], bound(meas, 1e-9),
                                 f"left elbow (J4 frame) {c} of the start posture, numpy FK; measured |delta| {meas:.2g} m"))  # fmt: skip
        for i in range(1, 8):
            sig = f"BoxPose/g[{i}]"
            meas = abs(run.at(sig, 0.0) - fk["box_from_left"][i - 1])
            checks.append(cursor(sig, 0.0, fk["box_from_left"][i - 1], bound(meas, 1e-9),
                                 f"box pose from the left hand through the grasp transform; measured |delta| {meas:.2g}"))  # fmt: skip
    # the in-model IK is open loop: it equals the twin in the dynamic model too
    for tc in (T_HOLD, T_BIAS):
        ref = tw["t_hold" if tc == T_HOLD else "t_bias"]["L"]
        for k in range(1, 8):
            sig = f"IKL/q{k}"
            meas = abs(run.at(sig, tc) - ref["q"][k - 1])
            checks.append(cursor(sig, tc, ref["q"][k - 1], bound(meas, 1e-9),
                                 f"in-model ArmIK equals its numpy twin; measured |delta| {meas:.2g} deg"))  # fmt: skip
    # joint tracking: the servos follow the IK
    for p in "LR":
        for k in range(1, 8):
            m = run.t >= T_TRACK
            meas = float(np.abs(run.c[f"{p}Arm{k}/J/qout"][m] - run.c[f"IK{p}/qr{k}"][m]).max())
            checks.append({"kind": "compare_signals", "signal": f"{p}Arm{k}/J/qout", "signal_b": f"IK{p}/qr{k}",
                           "from_t": T_TRACK, "max_abs": float(f"{max(1.5 * meas, 1e-3):.2g}"),
                           "note": f"joint {k} follows the IK command (PID servo through the elastic gear); measured {meas:.3g} rad ({np.degrees(meas):.3g} deg), bound 1.5x"})  # fmt: skip
    if not dof6:
        for sig in ("BoxError/e_mm", "BoxError/e_deg", "LHandError/e_mm", "LHandError/e_deg", "RHandError/e_mm", "RHandError/e_deg"):
            meas = run.peak(sig, 0.0, T_END)
            checks.append({"kind": "max_abs_le", "signal": sig, "value": 2.0,
                           "note": f"the simulated box and hands stay within the page's hold limit (2 mm, 2 deg) through the whole run, the move and the elbow sweep included; measured peak {meas:.3g}"})  # fmt: skip
        # the elbow moves under the bias in the dynamic model as in the twin
        for tc, tname in ((T_HOLD, "t_hold"), (T_BIAS, "t_bias")):
            ref = tw[tname]["L"]["elbow_world"]
            for j, c in enumerate("xyz"):
                sig = f"LArm4/W/g[{5 + j}]"
                meas = abs(run.at(sig, tc) - ref[j])
                checks.append(cursor(sig, tc, ref[j], bound(meas, 1e-4),
                                     f"simulated left elbow {c} (world) against the twin's IK elbow, bias {0 if tc == T_HOLD else dz.BIAS:g} deg "
                                     f"(the elbow moves {1000 * np.linalg.norm(np.subtract(tw['t_bias']['L']['elbow_world'], tw['t_hold']['L']['elbow_world'])):.1f} mm); measured |delta| {meas:.2g} m"))  # fmt: skip
        # the box weight is shared, the servos stay inside their torque limits
        half = 0.5 * dz.BOX_MASS * dz.G0
        for p in "LR":
            sig = f"{p}GraspLoad/F"
            meas = abs(run.at(sig, T_HOLD) - half)
            checks.append(cursor(sig, T_HOLD, half, bound(meas, 0.5),
                                 f"each grasp carries about half the box weight (m g / 2 = {half:.3f} N) plus a small internal squeeze; measured |delta| {meas:.2g} N"))  # fmt: skip
            for sig, unit in ((f"{p}GraspLoad/F", "N"), (f"{p}GraspLoad/M", "N m")):
                meas = run.peak(sig, T_TRACK, T_END)
                lim = float(f"{2 * meas:.2g}")
                checks.append({"kind": "max_abs_le", "signal": sig, "from_t": T_TRACK, "value": lim,
                               "note": f"7-DOF: the two arms barely squeeze the box (compare humanoid-hold-6dof); measured peak {meas:.3g} {unit}, bound 2x"})  # fmt: skip
            for k in range(1, 8):
                sig = f"Servo{p}/u{k}"
                meas = run.peak(sig, 0.0, T_END)
                lim = float(dz.U_MAX[k - 1])
                checks.append({"kind": "max_abs_le", "signal": sig, "value": 0.8 * lim,
                               "note": f"7-DOF: joint {k} torque stays well inside its limit {lim:g} N m (bound 80 %); measured peak {meas:.3g} N m"})  # fmt: skip
        checks.append({"kind": "energy_ledger", "tol": 1e-6,
                       "note": "power continuity of the whole bond graph (two arms, drives, grasp springs, box): Tellegen residual"})  # fmt: skip
    else:
        # the 6-DOF arms cannot reach the grasp: joints on limits, the hand errors stay, the elbow stays
        for p in "LR":
            for k, val in ((3, -90.0), (5, 0.0)):
                sig = f"{p}Arm{k}/J/qout"
                v = np.radians(val)
                meas = abs(run.at(sig, T_BIAS) - v)
                checks.append(cursor(sig, T_BIAS, v, bound(meas, 1e-4),
                                     f"6-DOF: joint {k} at {val:g} deg ({'its lower limit' if k == 3 else 'locked'}) in the dynamic model; measured |delta| {meas:.2g} rad"))  # fmt: skip
            sig = f"Servo{p}/u6"
            lim = float(dz.U_MAX[5])
            sat = run.t[np.abs(run.c[sig]) >= lim - 1e-6]
            t_sat = float(sat[0]) if sat.size else float("nan")
            checks.append({"kind": "min_ge", "signal": f"Servo{p}/u6", "from_t": T_BIAS - 0.5, "to_t": T_END, "value": lim - 1e-6,
                           "note": f"6-DOF: the wrist servo J6 saturates at its {lim:g} N m limit: the grasp twists the wrist "
                                   f"{abs(np.degrees(run.at(f'{p}J6/qout', T_BIAS)) + 60):.1f} deg past its -60 deg limit; measured: saturated from t = {t_sat:.2f} s"})  # fmt: skip
            for sig, lo, unit in ((f"{p}GraspLoad/F", 50.0, "N"), (f"{p}GraspLoad/M", 10.0, "N m")):
                meas = run.low(sig, T_HOLD, T_END)
                checks.append({"kind": "min_ge", "signal": sig, "from_t": T_HOLD, "to_t": T_END, "value": lo,
                               "note": f"6-DOF: the two arms fight through the box (internal squeeze; 7-DOF: about 8 N, 0.4 N m); measured minimum {meas:.3g} {unit}"})  # fmt: skip
            for sig_name, lo in (("e_mm", 1.0), ("e_deg", 1.0)):
                sig = f"{p}HandError/{sig_name}"
                meas = run.low(sig, W_DWELL[0], T_END)
                checks.append({"kind": "min_ge", "signal": sig, "from_t": W_DWELL[0], "to_t": T_END, "value": lo,
                               "note": f"6-DOF: the hands miss the grasp target at the commanded pose; measured minimum {meas:.3g}"})  # fmt: skip
        for j, c in enumerate("xyz"):
            sig = f"LArm4/W/g[{5 + j}]"
            d = abs(run.at(sig, T_BIAS) - run.at(sig, T_HOLD))
            ref = tw["t_hold"]["L"]["elbow_world"][j]
            meas = abs(run.at(sig, T_BIAS) - ref)
            checks.append(cursor(sig, T_BIAS, ref, bound(meas, 1e-4),
                                 f"6-DOF: the elbow bias does not move the elbow (twin elbow {c} at bias 0); measured shift between the instants {d:.2g} m, |delta| to the twin {meas:.2g} m"))  # fmt: skip
    checks.append(no_diagnostics())
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    for name in ("ik", "ik6", "hold", "hold6"):
        ap.add_argument(f"--{name}", type=Path, required=True)
    a = ap.parse_args()
    refs = references.load()
    doc = {
        "project": "humanoid-dual-arm",
        "description": (
            "Two stacked 7-DOF SRS arms on a humanoid torso hold one box. humanoid-ik: the 1 kHz firmware alone "
            "(object trajectory, damped-least-squares IK with a null-space pull toward home and an elbow bias, "
            "per arm, and an ideal-SRS pair), checked tick by tick against its numpy twin and against the "
            "interactive page's own IK. humanoid-ik-6dof: J5 locked, the stacked arms run into the J3 and J6 limits "
            "and miss the pose by about 3.5 mm and 3.3 deg. humanoid-hold: the dynamic multibody arms (illustrative "
            "masses, bond-graph drives, PID servos) carry the box on stiff grasp springs; the forward kinematics of "
            "the start posture, the 2 mm / 2 deg hold, the elbow self-motion under the bias and the power "
            "balance. humanoid-hold-6dof: the same with J5 locked. Generated by design/build_expected.py."
        ),
        "models": {
            "humanoid-ik": {"run_timeout": 600.0, "checks": ik_checks(refs, Run(a.ik), False)},
            "humanoid-ik-6dof": {"model": "humanoid-ik", "overrides": DOF6, "run_timeout": 600.0,
                                 "checks": ik_checks(refs, Run(a.ik6), True)},  # fmt: skip
            "humanoid-hold": {"run_timeout": 900.0, "checks": hold_checks(refs, Run(a.hold), False)},
            "humanoid-hold-6dof": {"model": "humanoid-hold", "overrides": DOF6, "run_timeout": 900.0,
                                   "checks": hold_checks(refs, Run(a.hold6), True)},  # fmt: skip
        },
    }
    path = ROOT / "expected.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name, m in doc["models"].items():
        print(f"{name}: {len(m['checks'])} checks")
    print(f"wrote {path.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
