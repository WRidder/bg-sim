# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "mujoco>=3.3"]
# ///
"""Write `expected.json` of `panda-3d` from the independent references and two measured runs.

    uv run examples/panda-3d/design/build_expected.py --free <panda-free run> --panda <panda run>
        [--free-rigid <panda-free-rigid run>] [--panda-rigid <panda-rigid run>]

Every option is optional: the models whose run is given are (re)generated, the others keep their
checks from the existing `expected.json`.

The expected values come from the references, never from the runs: MuJoCo (gravity torques, the
frictionless free swing integrated with DOP853), the design's forward kinematics and the Python
port of the He & Liu IK (`panda.py`). The runs (columns.f64 + manifest.json, as written by
`design/run_model.jl` or the backend) only set the tolerances: each bound is a stated multiple
(normally 5x) of the measured deviation, with a floor, and the note records the measurement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import design as dz
import panda as pz
import validate as vz

ROOT = Path(__file__).resolve().parent.parent
FACTOR = 5.0
# held-direction derivative causality, unit and domain errors, missing domains, algebraic loops,
# solver failures
NO_CODES = ["W201", "W205", "W206", "E006", "E007", "E101", "E102", "E103", "E106", "E901"]
# the rigid joints make the link inertias derivative-causal by design (W201 is expected there)
NO_CODES_RIGID = [c for c in NO_CODES if c != "W201"]


def bound(measured: float, floor: float) -> float:
    return float(f"{max(FACTOR * measured, floor):.2g}")


def at(t: np.ndarray, y: np.ndarray, tc: float) -> float:
    return float(np.interp(tc, t, y))


def free_checks(ref: vz.Reference, run_dir: Path, rigid: bool = False) -> list[dict]:
    from scipy.integrate import solve_ivp

    t, cols = vz.read_run(run_dir)
    # the rigid joints follow MuJoCo's rigid chain through the whole chaotic fall
    times = [0.0, 0.1, 0.25, 0.5, 1.0] if rigid else [0.0, 0.1, 0.25, 0.5]
    sol = solve_ivp(lambda _t, x: np.r_[x[7:], ref.qacc(x[:7], x[7:], np.zeros(7))], (0.0, max(times)),
                    np.r_[dz.Q_FREE, np.zeros(7)], method="DOP853", rtol=1e-12, atol=1e-12, t_eval=times)  # fmt: skip
    checks: list[dict] = [{"kind": "scene_bindings"}]
    for j, tc in enumerate(times):
        for k in range(1, 8):
            value = float(sol.y[k - 1, j])
            sig = f"L{k}/J/qout"
            meas = abs(at(t, cols[sig], tc) - value)
            if tc == 0.0:
                tol, why = 1e-9, "released at rest at the ready pose on its consistent deflections"
            elif rigid:
                tol = bound(meas, 1e-8)
                why = (f"MuJoCo free swing (frictionless, DOP853 rtol 1e-12) at t = {tc:g} s; measured |delta| "
                       f"{meas:.2g} rad, bound 5x (floor 1e-8). Rigid joints: the same rigid chain as "
                       "MuJoCo, so the chaotic fall agrees to the integration tolerance")  # fmt: skip
            else:
                tol = bound(meas, 1e-6)
                why = (f"MuJoCo free swing (frictionless, DOP853 rtol 1e-12) at t = {tc:g} s; measured |delta| "
                       f"{meas:.2g} rad, bound 5x (floor 1e-6). The difference grows with time: the held "
                       "directions are compliant (k = 1e7) and the swing is chaotic, see the README")  # fmt: skip
            checks.append({"kind": "cursor_value", "signal": sig, "t": tc, "value": value, "abs": tol, "note": why})
    # the flange of the reference at 0.25 s against TCP/g
    p_ref = ref.flange(sol.y[:7, 2])
    for c, idx in zip("xyz", (5, 6, 7)):
        sig = f"TCP/g[{idx}]"
        meas = abs(at(t, cols[sig], 0.25) - p_ref["xyz".index(c)])
        checks.append({"kind": "cursor_value", "signal": sig, "t": 0.25, "value": float(p_ref["xyz".index(c)]),
                       "abs": bound(meas, 1e-8 if rigid else 1e-6),
                       "note": f"flange {c} of the MuJoCo free swing at 0.25 s; measured |delta| {meas:.2g} m"})  # fmt: skip
    checks.append(no_diagnostics(rigid))
    return checks


def no_diagnostics(rigid: bool) -> dict:
    if rigid:
        return {"kind": "no_diagnostics", "codes": NO_CODES_RIGID,
                "note": "the run reports none of these (only the expected W201 of the rigid joints)"}
    return {"kind": "no_diagnostics", "codes": NO_CODES, "note": "the run reports none of these (it reports no diagnostics at all)"}


def panda_checks(ref: vz.Reference, run_dir: Path, rigid: bool = False) -> list[dict]:
    t, cols = vz.read_run(run_dir)
    checks: list[dict] = [{"kind": "scene_bindings"}]
    t_end = float(t[-1])
    # start and end: the ready pose (the trajectory ends where it started)
    for k in range(1, 8):
        sig = f"Robot/L{k}/J/qout"
        checks.append({"kind": "cursor_value", "signal": sig, "t": 0.0, "value": float(pz.Q_READY[k - 1]), "abs": 1e-9,
                       "note": "starts at the ready pose (drive springs preloaded with the gravity torque)"})  # fmt: skip
    for k in range(1, 8):
        sig = f"Robot/L{k}/J/qout"
        meas = abs(at(t, cols[sig], t_end) - pz.Q_READY[k - 1])
        checks.append({"kind": "cursor_value", "signal": sig, "t": t_end, "value": float(pz.Q_READY[k - 1]),
                       "abs": bound(meas, 1e-5),
                       "note": f"back at the ready pose at the end of the tour (the IK of the home pose with q7 = pi/4); measured |delta| {meas:.2g} rad"})  # fmt: skip
    for c, idx in zip("xyz", (5, 6, 7)):
        sig = f"Robot/TCP/g[{idx}]"
        value = float(dz.P_HOME["xyz".index(c)])
        meas = abs(at(t, cols[sig], t_end) - value)
        checks.append({"kind": "cursor_value", "signal": sig, "t": t_end, "value": value, "abs": bound(meas, 1e-5),
                       "note": f"flange {c} back home (forward kinematics of the ready pose); measured |delta| {meas:.2g} m"})  # fmt: skip
    # TCP tracking along the whole tour, per axis
    for c, idx in zip("xyz", (5, 6, 7)):
        meas = float(np.abs(cols[f"Robot/TCP/g[{idx}]"] - cols[f"Traj/p{c}"]).max())
        checks.append({"kind": "compare_signals", "signal": f"Robot/TCP/g[{idx}]", "signal_b": f"Traj/p{c}",
                       "max_abs": float(f"{1.5 * meas:.2g}"),
                       "note": f"TCP {c} tracking error over the tour (no inertia feedforward, so it lags in the moves); measured {meas:.3g} m, bound 1.5x"})  # fmt: skip
    # at rest in the middle of each dwell: TCP on the waypoint, IK output equals the Python IK
    for w, tw in enumerate(dz.WAYPOINT_TIMES):
        tc = round(tw + 0.5 * dz.T_DWELL, 6)
        if tc > t_end:
            continue
        target = dz.target_pose(tc)
        q_py, code = pz.ik_flange(target, dz.Q7_REF, np.array([at(t, cols[f"Robot/L{k}/J/qout"], tc) for k in range(1, 8)]))
        assert code == 0, (tc, code)
        for k in range(1, 8):
            sig = f"IK/qr{k}"
            meas = abs(at(t, cols[sig], tc) - q_py[k - 1])
            checks.append({"kind": "cursor_value", "signal": sig, "t": tc, "value": float(q_py[k - 1]), "abs": 1e-8,
                           "note": f"in-model IK at waypoint {w + 1} equals the Python port of He & Liu (design/panda.py); measured |delta| {meas:.2g} rad"})  # fmt: skip
        for c, idx in zip("xyz", (5, 6, 7)):
            sig = f"Robot/TCP/g[{idx}]"
            value = float(target[:3, 3]["xyz".index(c)])
            meas = abs(at(t, cols[sig], tc) - value)
            checks.append({"kind": "cursor_value", "signal": sig, "t": tc, "value": value, "abs": bound(meas, 2e-4),
                           "note": f"flange {c} at waypoint {w + 1}, mid-dwell; measured |delta| {meas:.2g} m"})  # fmt: skip
    # settled link-side torque sensors against the MuJoCo gravity torque of the ready pose
    g_ready = ref.gravity(pz.Q_READY)
    for k in range(1, 8):
        sig = f"Robot/TauSense{k}/y"
        meas = abs(at(t, cols[sig], t_end) - g_ready[k - 1])
        checks.append({"kind": "cursor_value", "signal": sig, "t": t_end, "value": float(g_ready[k - 1]), "abs": bound(meas, 1e-3),
                       "note": f"settled joint-torque sensor equals the MuJoCo gravity torque of the ready pose; measured |delta| {meas:.2g} N m"})  # fmt: skip
    # torque limits (Franka: 87 N m joints 1-4, 12 N m joints 5-7) and their use
    for k in range(1, 8):
        lim = float(pz.TAU_MAX[k - 1])
        peak = float(np.abs(cols[f"PD/u{k}"]).max())
        checks.append({"kind": "max_abs_le", "signal": f"Robot/Limit{k}/y", "value": lim,
                       "note": f"drive torque within the Franka limit {lim:g} N m; peak command {peak:.3g} N m"})  # fmt: skip
    checks.append({"kind": "max_abs_le", "signal": "IK/flag", "value": 0.0, "note": "the IK solves every tick (no hold, no flag)"})
    for k in range(1, 8):
        lim = float(pz.QD_MAX[k - 1])
        peak = float(np.abs(cols[f"Robot/L{k}/J/qdout"]).max())
        checks.append({"kind": "max_abs_le", "signal": f"Robot/L{k}/J/qdout", "value": lim,
                       "note": f"joint rate within the Franka limit {lim:g} rad/s; measured peak {peak:.3g} rad/s"})  # fmt: skip
    checks.append(no_diagnostics(rigid))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--free", type=Path)
    parser.add_argument("--panda", type=Path)
    parser.add_argument("--free-rigid", type=Path)
    parser.add_argument("--panda-rigid", type=Path)
    args = parser.parse_args()
    vz.make_mjcf(vz.MJCF)
    ref = vz.Reference(vz.MJCF)
    path = ROOT / "expected.json"
    old = json.loads(path.read_text(encoding="utf-8"))["models"] if path.exists() else {}

    def model(name: str, run: Path | None, build) -> dict:
        if run is not None:
            return {"run_timeout": 900.0, "checks": build(run)}
        return old[name]

    doc = {
        "project": "panda-3d",
        "description": (
            "The Franka Emika Panda on the M3 spatial multibond mechanics with the Gaz et al. 2019 "
            "physically feasible dynamics. panda-free: the frictionless arm released at rest from the "
            "ready pose, against MuJoCo's forward dynamics of the same parameters. panda: the Robot "
            "subsystem (mechanics, bond-graph joint drives with gear, rotor inertia, elastic gear, Gaz "
            "friction and torque limits, quantized encoders, joint-torque sensors) under a 1 kHz outer "
            "layer of Cartesian quintic trajectory, He & Liu analytical IK and PD with gravity and "
            "friction feedforward; checks against MuJoCo gravity, the design forward kinematics and "
            "the Python IK. panda-free-rigid and panda-rigid: the same models on the rigid joint "
            "Revolute3DRigid (index reduction, two states per joint). Generated by "
            "design/build_expected.py."
        ),
        "models": {
            "panda-free": model("panda-free", args.free, lambda r: free_checks(ref, r)),
            "panda": model("panda", args.panda, lambda r: panda_checks(ref, r)),
            "panda-free-rigid": model("panda-free-rigid", args.free_rigid, lambda r: free_checks(ref, r, rigid=True)),
            "panda-rigid": model("panda-rigid", args.panda_rigid, lambda r: panda_checks(ref, r, rigid=True)),
        },
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    n = sum(len(m["checks"]) for m in doc["models"].values())
    print(f"wrote {path.relative_to(ROOT)} ({n} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
