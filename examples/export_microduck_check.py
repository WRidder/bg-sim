# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "fmpy>=0.3.20"]
# ///
"""Acceptance of the microduck-policy FMU (the plant of the browser demo, apps/web/microduck).

    uv run examples/export_microduck_check.py [--out DIR] [--skip-julia] [--dt S] [--method M]

1. ``examples/export_microduck.jl`` exports ``microduck/models/microduck-policy`` with the policy
   interface (14 ``<joint>_target`` inputs and ``kp``; the joint, trunk and sole outputs; ``v_bat``
   and ``i_limit`` as FMU parameters with ranges; 20 ms communication step, the internal step and
   method set) and runs bg-sim references of two scripted runs driven through the same inputs:
   ``stand`` (everything held at the start values for 0.6 s) and ``squat`` (0.6 s: the legs step
   to a 15 mm squat at 0.2 s, the gain drops to 160 at 0.3 s and back at 0.45 s, the neck nods at
   0.4 s). Without a policy HOME tips forward, so both runs stop before the robot falls;
2. ``bgsim_server.fmu_build`` builds the FMU: -Werror, C++17, the hot-path symbol check, the
   counting allocation harness and the doStep timing;
3. in fmpy each run is driven through the FMU's inputs (``export_checks.run_driven``) and every
   output is compared with the reference: the worst deviation relative to the signal's peak, and
   the absolute deviation of the joint angles, the trunk height and the projected gravity.

The table goes to stdout and ``<out>/MICRODUCK_FMU_RESULTS.md``; the exit code is non-zero when a
gate fails. Gates: zero allocations after instantiate, no forbidden symbol, fmpy validate clean,
a value outside a parameter's range refused, every output finite, joint angles within
``TOL_Q`` rad, the trunk height within ``TOL_Z`` m, every joint velocity within ``TOL_QD`` rad/s and
every trunk angular-velocity component within ``TOL_W`` rad/s of the reference (the policy observes
all of them).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from bgsim_server.fmu_build import build_fmu  # noqa: E402
from export_checks import reference, run_driven  # noqa: E402

RUNTIME = ROOT / "julia" / "BGSim" / "export" / "runtime"
SCENARIOS = ("stand", "squat")
TOL_Q = 2e-3      # rad, every joint angle against the reference
TOL_Z = 5e-4      # m, the trunk height
# The policy observes the joint velocities and the gyro too, so they are gated as well, absolutely
# (a relative error is meaningless for a joint that hardly moves): a tenth of the observation
# noise velstand was trained with (joint_vel +-0.25 rad/s, base_ang_vel +-0.03 rad/s,
# microduck_velocity_env_cfg.py), so a disagreement stays well inside what the policy ignores.
TOL_QD = 0.025    # rad/s, every joint velocity
TOL_W = 0.003     # rad/s, every trunk angular-velocity component
SHOWN = [("left_knee_q", "rad"), ("left_ankle_q", "rad"), ("neck_pitch_q", "rad"), ("left_knee_qd", "rad/s"),
         ("head_yaw_qd", "rad/s"), ("trunk_wx", "rad/s"), ("trunk_wz", "rad/s"),
         ("trunk_z", "m"), ("gravity_x", "1"), ("trunk_wy", "rad/s"), ("left_foot_contact", "N")]


def deviations(res: dict, ref_dir: Path, names: list[str]) -> dict:
    ids, ref = reference(ref_dir)
    col = {s: i + 1 for i, s in enumerate(ids)}
    t = res["time"]
    idx = np.clip(np.searchsorted(ref[:, 0], t - 1e-12), 0, len(ref) - 1)
    ok = np.abs(ref[idx, 0] - t) < 1e-9
    out = {}
    for name in names:
        key = name if name in col else f"{name}/u"
        if key not in col:
            continue
        a, b = res[name][ok], ref[idx[ok], col[key]]
        err = np.abs(a - b)
        peak = float(np.max(np.abs(b)))
        k = int(np.argmax(err))
        out[name] = {"abs": float(err[k]), "rel": float(err[k] / peak) if peak > 1e-9 else float(err[k]),
                     "t": float(t[ok][k]), "peak": peak, "finite": bool(np.all(np.isfinite(a)))}
    return out


def refused(fmu: Path, name: str, value: float) -> str | None:
    from fmpy import simulate_fmu

    messages: list[str] = []

    def logger(component, instance_name, status, category, message):
        messages.append(message.decode() if isinstance(message, bytes) else str(message))

    try:
        simulate_fmu(str(fmu), stop_time=0.02, output_interval=0.02, start_values={name: value},
                     fmi_type="CoSimulation", logger=logger, debug_logging=False)
    except Exception as err:  # noqa: BLE001 - fmpy raises on fmi2Error
        return " | ".join(messages) or str(err)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "export-microduck-out")
    parser.add_argument("--skip-julia", action="store_true")
    parser.add_argument("--dt", default="0.001")
    parser.add_argument("--method", default="ros34pw2")
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.skip_julia:
        cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(ROOT / "examples" / "export_microduck.jl"), str(out),
               "--dt", args.dt, "--method", args.method]
        print("+", " ".join(cmd), flush=True)
        if subprocess.run(cmd).returncode != 0:
            print("FAIL: the export or the reference run failed")
            return 2
    rec = json.loads((out / "export.jsonl").read_text(encoding="utf-8").splitlines()[0])
    if not rec["ok"]:
        print("FAIL: the export was refused:", rec["diagnostics"])
        return 1
    report = json.loads((out / "fmu" / "export.json").read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    # 50 steps (1 s): the harness holds the inputs at their start values, and HOME without a
    # policy tips over near 1 s.
    built = build_fmu(out / "fmu", runtime_dir=RUNTIME, harness_steps=50)
    build_s = time.perf_counter() - t0
    if not built.ok or built.fmu is None:
        print("FAIL: build:", built.error)
        return 1

    from fmpy.validation import validate_fmu

    failures: list[str] = []
    problems = validate_fmu(str(built.fmu))
    if problems:
        failures.append(f"fmpy validate: {problems}")
    if built.allocations_after_instantiate != 0 or built.forbidden_symbols or built.cxx_ok is False:
        failures.append(f"allocations {built.allocations_after_instantiate}, symbols {built.forbidden_symbols}, "
                        f"C++ {built.cxx_ok}")
    why = refused(built.fmu, "v_bat", 9.0)
    if why is None or "outside its declared range" not in why:
        failures.append(f"v_bat = 9 V (range 6.5..8.2) was not refused ({why})")

    names = [o["name"] for o in report["outputs"]]
    rows = []
    gates = []
    for sc in SCENARIOS:
        inputs = json.loads((out / sc / "inputs.json").read_text(encoding="utf-8"))
        t_end = float(inputs["t"][-1])
        t0 = time.perf_counter()
        res = run_driven(built.fmu, names, inputs, t_end, rec["step"], inputs.get("params"))
        wall = time.perf_counter() - t0
        dev = deviations(res, out / sc / "reference", names)
        worst = max(dev.items(), key=lambda kv: kv[1]["rel"])
        rows.append((sc, t_end, wall, worst, dev))
        if len(dev) != len(names):
            failures.append(f"{sc}: {len(names) - len(dev)} outputs not in the reference")
        if not all(d["finite"] for d in dev.values()):
            failures.append(f"{sc}: non-finite outputs")
        q_worst = max((d["abs"], n) for n, d in dev.items() if n.endswith("_q"))
        if q_worst[0] > TOL_Q:
            failures.append(f"{sc}: {q_worst[1]} deviates {q_worst[0]:.2e} rad")
        if dev["trunk_z"]["abs"] > TOL_Z:
            failures.append(f"{sc}: trunk_z deviates {dev['trunk_z']['abs']:.2e} m")
        for label, names_of, tol in (("joint velocity", [n for n in dev if n.endswith("_qd")], TOL_QD),
                                     ("trunk angular velocity", [n for n in dev if n.startswith("trunk_w")], TOL_W)):
            if not names_of:
                failures.append(f"{sc}: no {label} output to compare")
                continue
            w = max((dev[n]["abs"], n) for n in names_of)
            gates.append((sc, label, w[1], w[0], dev[w[1]]["t"], dev[w[1]]["peak"], tol))
            if w[0] > tol:
                failures.append(f"{sc}: {label} {w[1]} deviates {w[0]:.2e} rad/s (gate {tol:g})")

    la = report.get("linearAlgebra", {})
    lines = [
        f"FMU: {report['method']} dt {report['dt'] * 1e3:g} ms, {report['substeps']} substep(s) per "
        f"{rec['step'] * 1e3:g} ms communication step; {len(report.get('inputs', []))} inputs, {len(names)} outputs; "
        f"export {rec['exportS']:.0f} s, build {build_s:.0f} s",
        f"states {report.get('states', report.get('nx', '?'))}, linear algebra {la.get('kind', la.get('solver', '?'))}, "
        f"nnz J {la.get('nnzJ', '?')}, nnz LU {la.get('nnzLU', '?')}, LU flops {la.get('luFlops', '?')}",
        f"doStep ({rec['step'] * 1e3:g} ms) mean {built.step_time_mean_us:.0f} us (max {built.step_time_max_us:.0f} us): "
        f"{built.step_time_mean_us * 1e-6 / rec['step']:.3f} s of wall time per simulated second (harness, standing still)",
        f"allocations after instantiate {built.allocations_after_instantiate}, forbidden symbols "
        f"{built.forbidden_symbols or 'none'}, C++ {built.cxx_ok}, fmpy validate {'clean' if not problems else problems}",
        "",
        "| run | s | fmpy wall s (per sim s) | worst (rel. to peak) | " + " | ".join(f"{n} ({u})" for n, u in SHOWN) + " |",
        "| --- | --- | --- | --- | " + " | ".join("---" for _ in SHOWN) + " |",
    ]
    for sc, t_end, wall, worst, dev in rows:
        lines.append(f"| {sc} | {t_end:g} | {wall:.2f} ({wall / t_end:.3f}) | {worst[1]['rel']:.2e} (`{worst[0]}`) | "
                     + " | ".join(f"{dev[n]['abs']:.2e}" if n in dev else "" for n, _ in SHOWN) + " |")
    lines += ["", "| run | gate | worst signal | abs deviation | at t (s) | its peak | gate (abs) |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for sc, label, name, err, at, peak, tol in gates:
        lines.append(f"| {sc} | {label} | `{name}` | {err:.2e} | {at:.2f} | {peak:.2e} | {tol:g} |")
    table = "\n".join(lines)
    (out / "MICRODUCK_FMU_RESULTS.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    for f in failures:
        print("FAIL:", f)
    if not failures:
        print("PASS: the microduck-policy FMU matches bg-sim on both runs")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
