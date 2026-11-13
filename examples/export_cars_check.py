# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "fmpy>=0.3.20"]
# ///
"""Acceptance of the car-sim FMUs (the FMUs of the car-sim host, apps/web).

    uv run examples/export_cars_check.py [--out DIR] [--skip-julia] [racecar|buggy ...]

1. ``examples/export_cars.jl`` exports ``cars/models/racecar-sim`` and ``buggy-sim`` with the
   host interface (the ExportInputPass markers as inputs: steer, throttle, brake, reverse,
   handbrake and the friction scale per wheel; the ExportOutput markers as outputs: poses,
   wheel states, telemetry, motor and battery; the start charge, the motor envelope and the
   brakes as FMU parameters with ranges; 5 ms communication step, the analysis picks the
   method and the internal step) and runs a bg-sim reference of one drive per vehicle through
   the same inputs (race car: launch, a turn, a low-friction patch under one wheel, braking;
   buggy: a drive over the hills with steering, braking and the handbrake);
2. ``bgsim_server.fmu_build`` builds each FMU: -Werror, C++17, the hot-path symbol check, the
   counting allocation harness and the doStep timing;
3. in fmpy every drive is driven through the FMU's inputs (``export_checks.run_driven``: zero-
   order hold, the reference's convention) and every output is compared with the reference:
   the worst deviation relative to the signal's peak, and the absolute deviation of what a
   driver reads; a parameter outside its range is refused, and ``fmpy.validation`` is clean.

The table goes to stdout and ``<out>/CARS_FMU_RESULTS.md``; the exit code is non-zero when a
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

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from bgsim_server.fmu_build import build_fmu  # noqa: E402
from export_checks import reference, run_driven  # noqa: E402

RUNTIME = ROOT / "julia" / "BGSim" / "export" / "runtime"
SCENARIOS = {"racecar": ("launch_turn_brake",), "buggy": ("hills_drive",)}
TOL_REL = 1e-2            # of the signal's peak over the drive
STEP_BUDGET_US = 1000.0   # a fifth of the 5 ms communication step
SHOWN = [("speed", "m/s"), ("chassis_px", "m"), ("chassis_py", "m"), ("yaw", "rad"), ("roll", "rad"),
         ("fl_fz", "N"), ("rl_kappa", "1"), ("motor_r_torque", "N m"), ("soc", "1")]
OUT_OF_RANGE = ("global:soc0", 1.5)   # a parameter value the FMU must refuse


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
        simulate_fmu(str(fmu), stop_time=0.01, output_interval=0.005, start_values={name: value},
                     fmi_type="CoSimulation", logger=logger, debug_logging=False)
    except Exception as err:  # noqa: BLE001 - fmpy raises on fmi2Error
        return " | ".join(messages) or str(err)
    return None


def check_vehicle(out: Path, vehicle: str, failures: list[str]) -> list[str]:
    vdir = out / vehicle
    rec = json.loads((vdir / "export.jsonl").read_text(encoding="utf-8").splitlines()[0])
    if not rec["ok"]:
        failures.append(f"{vehicle}: the export was refused: {rec['diagnostics']}")
        return []
    report = json.loads((vdir / "fmu" / "export.json").read_text(encoding="utf-8"))
    built = build_fmu(vdir / "fmu", runtime_dir=RUNTIME, harness_steps=20_000)
    if not built.ok or built.fmu is None:
        failures.append(f"{vehicle}: build: {built.error}")
        return []

    from fmpy.validation import validate_fmu

    problems = validate_fmu(str(built.fmu))
    if problems:
        failures.append(f"{vehicle}: fmpy validate: {problems}")
    if built.allocations_after_instantiate != 0 or built.forbidden_symbols or built.cxx_ok is False:
        failures.append(f"{vehicle}: allocations {built.allocations_after_instantiate}, symbols "
                        f"{built.forbidden_symbols}, C++ {built.cxx_ok}")
    if built.step_time_mean_us > STEP_BUDGET_US:
        failures.append(f"{vehicle}: doStep {built.step_time_mean_us:.0f} us is over {STEP_BUDGET_US:.0f} us")
    pname = OUT_OF_RANGE[0].removeprefix("global:")
    why = refused(built.fmu, pname, OUT_OF_RANGE[1])
    if why is None or "outside its declared range" not in why:
        failures.append(f"{vehicle}: {pname} = {OUT_OF_RANGE[1]} was not refused ({why})")

    names = [o["name"] for o in report["outputs"]]
    tun = report.get("tunables", {})
    lines = [
        f"### {vehicle}-sim",
        "",
        f"FMU: {report['method']} dt {report['dt'] * 1e3:g} ms, {report['substeps']} substep(s) per "
        f"{rec['step'] * 1e3:g} ms communication step; {len(report.get('inputs', []))} inputs, {len(names)} outputs, "
        f"parameters: {', '.join(tun.get('requested', []) + ['global:' + g for g in tun.get('globals', [])])}",
        f"doStep mean {built.step_time_mean_us:.1f} us (max {built.step_time_max_us:.1f} us), allocations after "
        f"instantiate {built.allocations_after_instantiate}, forbidden symbols {built.forbidden_symbols or 'none'}, "
        f"C++ {built.cxx_ok}, fmpy validate {'clean' if not problems else problems}",
        "",
        "| drive | s | fmpy wall s | worst (rel. to peak) | " + " | ".join(f"{n} ({u})" for n, u in SHOWN) + " |",
        "| --- | --- | --- | --- | " + " | ".join("---" for _ in SHOWN) + " |",
    ]
    for sc in SCENARIOS[vehicle]:
        inputs = json.loads((vdir / sc / "inputs.json").read_text(encoding="utf-8"))
        t_end = float(inputs["t"][-1])
        t0 = time.perf_counter()
        res = run_driven(built.fmu, names, inputs, t_end, rec["step"])
        wall = time.perf_counter() - t0
        dev = deviations(res, vdir / sc / "reference", names)
        worst = max(dev.items(), key=lambda kv: kv[1]["rel"])
        if len(dev) != len(names):
            failures.append(f"{vehicle} {sc}: {len(names) - len(dev)} outputs not in the reference")
        if not all(d["finite"] for d in dev.values()):
            failures.append(f"{vehicle} {sc}: non-finite outputs")
        if worst[1]["rel"] > TOL_REL:
            failures.append(f"{vehicle} {sc}: {worst[0]} deviates {worst[1]['rel']:.2e} of its peak at "
                            f"t = {worst[1]['t']:.2f} s")
        lines.append(f"| {sc} | {t_end:g} | {wall:.2f} | {worst[1]['rel']:.2e} (`{worst[0]}`) | "
                     + " | ".join(f"{dev[n]['abs']:.2e}" if n in dev else "" for n, _ in SHOWN) + " |")
    return lines + [""]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "export-cars-out")
    parser.add_argument("--skip-julia", action="store_true")
    parser.add_argument("vehicles", nargs="*", default=["racecar", "buggy"])
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.skip_julia:
        cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(ROOT / "examples" / "export_cars.jl"), str(out),
               *args.vehicles]
        print("+", " ".join(cmd), flush=True)
        if subprocess.run(cmd).returncode != 0:
            print("FAIL: the export or the reference run failed")
            return 2
    failures: list[str] = []
    lines: list[str] = []
    for v in args.vehicles:
        lines += check_vehicle(out, v, failures)
    table = "\n".join(lines)
    (out / "CARS_FMU_RESULTS.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    for f in failures:
        print("FAIL:", f)
    if not failures:
        print("PASS: the car-sim FMUs match bg-sim on every drive")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
