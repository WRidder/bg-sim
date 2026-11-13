# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "fmpy>=0.3.20"]
# ///
"""Acceptance of the cessna-sim FMU (the FMU of the cessna-sim host, apps/web).

    uv run examples/export_cessna_check.py [--out DIR] [--skip-julia]

1. ``examples/export_cessna.jl`` exports ``cessna/models/cessna-sim`` with the host interface
   (the 16 ExportInputPass markers as inputs, the ExportOutput markers as outputs, the 20 start
   globals as FMU parameters with ranges; 5 ms communication step, the analysis picks the method
   and the internal step) and runs a bg-sim reference of three ground scenarios driven through
   the same inputs, from the runway start: a full-power take-off roll with a pedal pulse and the
   rotation, a braked run-up (throttle, mixture, flaps and trim), and nose-wheel steering in a
   crosswind with a toe-brake input;
2. ``bgsim_server.fmu_build`` builds the FMU: -Werror, C++17, the hot-path symbol check, the
   counting allocation harness and the doStep timing;
3. in fmpy every scenario is driven through the FMU's inputs (``export_checks.run_driven``:
   zero-order hold, the reference's convention) and every output is compared with the
   reference: the worst deviation relative to the signal's peak, and the absolute deviation of
   the variables a pilot reads; a parameter outside its range is refused, and
   ``fmpy.validation.validate_fmu`` is clean.

The table goes to stdout and ``<out>/CESSNA_FMU_RESULTS.md``; the exit code is non-zero when a
gate fails. Gates: zero allocations after instantiate, no forbidden symbol, doStep below a fifth
of the 5 ms step, worst relative deviation below ``TOL_REL``.

The ground scenarios are the hard case of this FMU: the tyre forces and the strut contacts are
stiff, the wheel slip saturates, and the stall hysteresis and the contact switches are evaluated
once per step (W203). The take-off roll's rotation pulls the wing through the stall hysteresis'
upper threshold at low speed: that switch can come one step (5 ms) late, about 4 % of the stall
flag for a moment (the flags are gated on their own bound, 10 %); everything else agrees to
about 1e-4 of its peak or better.
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
SCENARIOS = ("takeoff_roll", "runup_brakes", "steer_wind")
TOL_REL = 1e-2            # of the signal's peak over the scenario
# indicators that switch: a switch evaluated once per step (W203) can come one step late, so these
# are gated on their own, looser bound (the stall flag is a 20 ms first-order hysteresis state)
INDICATORS = {"stall_flag": 0.1, "on_ground": 0.1}
STEP_BUDGET_US = 1000.0   # a fifth of the 5 ms communication step
# the variables whose absolute deviation the table lists
SHOWN = [("north_m", "m"), ("east_m", "m"), ("psi_deg", "deg"), ("theta_deg", "deg"), ("kias", "kt"),
         ("rpm", "rpm"), ("thrust_n", "N"), ("fn_nose", "N")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "export-cessna-out")
    parser.add_argument("--skip-julia", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.skip_julia:
        cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(ROOT / "examples" / "export_cessna.jl"), str(out)]
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
    why = refused(built.fmu, "z0", 5000.0)
    if why is None or "outside its declared range" not in why:
        failures.append(f"z0 = 5000 (range 0..4000) was not refused ({why})")

    names = [o["name"] for o in report["outputs"]]
    rows = []
    for sc in SCENARIOS:
        inputs = json.loads((out / sc / "inputs.json").read_text(encoding="utf-8"))
        t_end = float(inputs["t"][-1])
        t0 = time.perf_counter()
        res = run_driven(built.fmu, names, inputs, t_end, rec["step"])
        wall = time.perf_counter() - t0
        dev = deviations(res, out / sc / "reference", names)
        worst = max(((n, d) for n, d in dev.items() if n not in INDICATORS), key=lambda kv: kv[1]["rel"])
        for n, tol in INDICATORS.items():
            if n in dev and dev[n]["rel"] > tol:
                failures.append(f"{sc}: indicator {n} deviates {dev[n]['rel']:.2e} at t = {dev[n]['t']:.2f} s")
        rows.append((sc, t_end, wall, worst, dev))
        if len(dev) != len(names):
            failures.append(f"{sc}: {len(names) - len(dev)} outputs not in the reference")
        if not all(d["finite"] for d in dev.values()):
            failures.append(f"{sc}: non-finite outputs")
        if worst[1]["rel"] > TOL_REL:
            failures.append(f"{sc}: {worst[0]} deviates {worst[1]['rel']:.2e} of its peak at t = {worst[1]['t']:.2f} s")

    tun = report.get("tunables", {})
    params = tun.get("requested", []) + ["global:" + g for g in tun.get("globals", [])]
    lines = [
        f"FMU: {report['method']} dt {report['dt'] * 1e3:g} ms, {report['substeps']} substep(s) per "
        f"{rec['step'] * 1e3:g} ms communication step; {len(report.get('inputs', []))} inputs, {len(names)} outputs, "
        f"{len(params)} parameters",
        f"doStep mean {built.step_time_mean_us:.1f} us (max {built.step_time_max_us:.1f} us), allocations after "
        f"instantiate {built.allocations_after_instantiate}, forbidden symbols {built.forbidden_symbols or 'none'}, "
        f"C++ {built.cxx_ok}, fmpy validate {'clean' if not problems else problems}",
        "",
        "| scenario | s | fmpy wall s | worst (rel. to peak) | stall_flag | "
        + " | ".join(f"{n} ({u})" for n, u in SHOWN) + " |",
        "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in SHOWN) + " |",
    ]
    for sc, t_end, wall, worst, dev in rows:
        lines.append(f"| {sc} | {t_end:g} | {wall:.2f} | {worst[1]['rel']:.2e} (`{worst[0]}`) | "
                     f"{dev['stall_flag']['abs']:.2e} | " + " | ".join(f"{dev[n]['abs']:.2e}" if n in dev else "" for n, _ in SHOWN) + " |")
    table = "\n".join(lines)
    (out / "CESSNA_FMU_RESULTS.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    for f in failures:
        print("FAIL:", f)
    if not failures:
        print("PASS: the cessna-sim FMU matches bg-sim on all scenarios")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
