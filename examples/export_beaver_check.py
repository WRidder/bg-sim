# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "fmpy>=0.3.20"]
# ///
"""Acceptance of the beaver-sim FMU.

    uv run examples/export_beaver_check.py [--out DIR] [--skip-julia]

1. ``examples/export_beaver.jl`` exports ``beaver/models/beaver-sim`` with the host interface (the
   ExportInputPass markers as inputs: column, pedals, flaps, trim, engine levers, autopilot modes
   and references, wind; the ExportOutput markers as outputs; the drivetrain switch and the
   aileron and rudder trims as FMU parameters with ranges; 5 ms communication step, the analysis
   picks the method and the internal step) and runs a bg-sim reference of three runs driven
   through the same inputs: the demo (climb, turn, level-off on the autopilot), a hand-flown
   sequence with the autopilot off, and flaps and wind on the autopilot;
2. ``bgsim_server.fmu_build`` builds the FMU: -Werror, C++17, the hot-path symbol check, the
   counting allocation harness and the doStep timing;
3. in fmpy every run is driven through the FMU's inputs (``export_checks.run_driven``:
   zero-order hold, the reference's convention) and every output is compared with the
   reference: the worst deviation relative to the signal's peak, and the absolute deviation of
   the flight variables a pilot reads; a parameter outside its range is refused, and
   ``fmpy.validation.validate_fmu`` is clean.

The table goes to stdout and ``<out>/BEAVER_FMU_RESULTS.md``; the exit code is non-zero when a
gate fails. Gates: zero allocations after instantiate, no forbidden symbol, doStep below a
fifth of the 5 ms step, worst relative deviation below ``TOL_REL``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from bgsim_server.fmu_build import build_fmu  # noqa: E402
from export_checks import run_driven  # noqa: E402
from export_f16_check import deviations, refused  # noqa: E402

RUNTIME = ROOT / "julia" / "BGSim" / "export" / "runtime"
SCENARIOS = ("demo", "hand_flown", "flaps_wind")
TOL_REL = 1e-2            # of the signal's peak over the run
STEP_BUDGET_US = 1000.0   # a fifth of the 5 ms communication step
SHOWN = [("alpha_deg", "deg"), ("beta_deg", "deg"), ("phi_deg", "deg"), ("theta_deg", "deg"),
         ("psi_deg", "deg"), ("alt_m", "m"), ("tas_mps", "m/s"), ("engine_rpm", "rpm")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "export-beaver-out")
    parser.add_argument("--skip-julia", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.skip_julia:
        cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(ROOT / "examples" / "export_beaver.jl"), str(out)]
        print("+", " ".join(cmd), flush=True)
        if subprocess.run(cmd).returncode != 0:
            print("FAIL: the export or the reference run failed")
            return 2
    rec = json.loads((out / "export.jsonl").read_text(encoding="utf-8").splitlines()[0])
    if not rec["ok"]:
        print("FAIL: the export was refused:", rec["diagnostics"])
        return 1
    report = json.loads((out / "fmu" / "export.json").read_text(encoding="utf-8"))
    built = build_fmu(out / "fmu", runtime_dir=RUNTIME, harness_steps=20_000)
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
    if built.step_time_mean_us > STEP_BUDGET_US:
        failures.append(f"doStep {built.step_time_mean_us:.0f} us is over {STEP_BUDGET_US:.0f} us")
    why = refused(built.fmu, "drivetrain", 2.0)
    if why is None or "outside its declared range" not in why:
        failures.append(f"drivetrain = 2 (range 0..1) was not refused ({why})")

    names = [o["name"] for o in report["outputs"]]
    rows = []
    for sc in SCENARIOS:
        inputs = json.loads((out / sc / "inputs.json").read_text(encoding="utf-8"))
        t_end = float(inputs["t"][-1])
        t0 = time.perf_counter()
        res = run_driven(built.fmu, names, inputs, t_end, rec["step"])
        wall = time.perf_counter() - t0
        dev = deviations(res, out / sc / "reference", names)
        worst = max(dev.items(), key=lambda kv: kv[1]["rel"])
        rows.append((sc, t_end, wall, worst, dev))
        if len(dev) != len(names):
            failures.append(f"{sc}: {len(names) - len(dev)} outputs not in the reference")
        if not all(d["finite"] for d in dev.values()):
            failures.append(f"{sc}: non-finite outputs")
        if worst[1]["rel"] > TOL_REL:
            failures.append(f"{sc}: {worst[0]} deviates {worst[1]['rel']:.2e} of its peak at t = {worst[1]['t']:.2f} s")

    tun = report.get("tunables", {})
    lines = [
        f"FMU: {report['method']} dt {report['dt'] * 1e3:g} ms, {report['substeps']} substep(s) per "
        f"{rec['step'] * 1e3:g} ms communication step; {len(report.get('inputs', []))} inputs, {len(names)} outputs, "
        f"parameters: {', '.join(tun.get('requested', []) + ['global:' + g for g in tun.get('globals', [])])}",
        f"doStep mean {built.step_time_mean_us:.1f} us (max {built.step_time_max_us:.1f} us), allocations after "
        f"instantiate {built.allocations_after_instantiate}, forbidden symbols {built.forbidden_symbols or 'none'}, "
        f"C++ {built.cxx_ok}, fmpy validate {'clean' if not problems else problems}",
        "",
        "| run | s | fmpy wall s | worst (rel. to peak) | " + " | ".join(f"{n} ({u})" for n, u in SHOWN) + " |",
        "| --- | --- | --- | --- | " + " | ".join("---" for _ in SHOWN) + " |",
    ]
    for sc, t_end, wall, worst, dev in rows:
        lines.append(f"| {sc} | {t_end:g} | {wall:.2f} | {worst[1]['rel']:.2e} (`{worst[0]}`) | "
                     + " | ".join(f"{dev[n]['abs']:.2e}" if n in dev else "" for n, _ in SHOWN) + " |")
    table = "\n".join(lines)
    (out / "BEAVER_FMU_RESULTS.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    for f in failures:
        print("FAIL:", f)
    if not failures:
        print("PASS: the beaver-sim FMU matches bg-sim on all runs")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
