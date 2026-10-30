# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "fmpy>=0.3.20"]
# ///
"""Export every example model to an FMU and compare it with simulation (plan X-EX1).

    uv run examples/export_checks.py [--out DIR] [--skip-julia] [--settings JSON]
                                     [project[/model] ...]

1. ``examples/export_examples.jl`` (one Julia process) exports each model, runs its reference
   simulation and writes ``results.jsonl`` (a refused model records its E110/E111 reason);
2. for each exported model, ``bgsim_server.fmu_build`` compiles the FMU and runs the
   hot-path symbol check and the counting allocation harness;
3. the FMU runs in fmpy on the reference's output grid, and every recorded signal is compared
   with the reference (right limits at event instants): the error relative to the signal's
   peak, signals with a peak below 1e-9 compared absolutely.

The summary table goes to stdout and ``<out>/EXPORT_RESULTS.md``; Rosenbrock exports add a
second table with the Jacobian, the LU (non-zeros, fill-in, flops) and the step time. The exit code is non-zero
when an exported model fails a check: a forbidden symbol, an allocation after
instantiate, a failed build, or a diverged FMU. Accuracy is reported, not yet gated: the
per-example thresholds become ``fmu_compare`` checks in ``expected.json``.
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

from bgsim_server.fmu_build import build_fmu  # noqa: E402

RUNTIME = ROOT / "julia" / "BGSim" / "export" / "runtime"


def reference(ref_dir: Path):
    manifest = json.loads((ref_dir / "manifest.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in manifest["signals"]]
    rows = np.fromfile(ref_dir / "stream.f64", dtype="<f8").reshape(-1, 1 + len(ids))
    keep = np.append(rows[1:, 0] != rows[:-1, 0], True)  # right limit at event instants
    return ids, rows[keep]


def compare(export_dir: Path, ref_dir: Path, report: dict, fmu: Path) -> dict:
    from fmpy import simulate_fmu

    names = report["locals"] + [o["name"] for o in report["outputs"]]
    t0 = time.monotonic()
    res = simulate_fmu(str(fmu), stop_time=report["tEnd"], output_interval=report["step"],
                       output=names, fmi_type="CoSimulation")
    wall = time.monotonic() - t0
    ids, ref = reference(ref_dir)
    col = {s: i + 1 for i, s in enumerate(ids)}
    t = res["time"]
    idx = np.clip(np.searchsorted(ref[:, 0], t - 1e-12), 0, len(ref) - 1)
    ok = np.abs(ref[idx, 0] - t) < 1e-9 * max(1.0, report["tEnd"])
    worst = (0.0, None, 0.0, 0.0)
    compared = 0
    nonfinite = []
    for name in names:
        if name not in col:
            continue
        a = res[name][ok]
        b = ref[idx[ok], col[name]]
        if not np.all(np.isfinite(a)):
            nonfinite.append(name)
            continue
        compared += 1
        peak = float(np.max(np.abs(b))) if len(b) else 0.0
        err = np.abs(a - b)
        k = int(np.argmax(err)) if len(err) else 0
        rel = float(err[k] / peak) if peak > 1e-9 else float(err[k])
        if rel > worst[0]:
            worst = (rel, name, float(t[ok][k]), peak)
    return {
        "compared": compared, "times": int(ok.sum()), "worstRel": worst[0],
        "worstSignal": worst[1], "worstT": worst[2], "worstPeak": worst[3],
        "nonfinite": nonfinite, "fmpyWallS": wall,
    }


def _finished(results: Path) -> set[str]:
    if not results.exists():
        return set()
    keys = set()
    for line in results.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # a line being written
        keys.add(f"{rec['project']}/{rec['model']}")
    return keys


def _kill_tree(process: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        process.kill()
    process.wait()


def run_julia(out: Path, only: list[str], budget: float, settings: str | None = None) -> int:
    """Run the Julia driver; kill and log a model that exceeds ``budget``, then resume."""
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    current = out / "current.json"
    resume = False
    while True:
        current.unlink(missing_ok=True)
        cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}",
               str(ROOT / "examples" / "export_examples.jl"), str(out),
               *(["--resume"] if resume else []),
               *([f"--settings={settings}"] if settings else []), *only]
        print("+", " ".join(cmd), flush=True)
        process = subprocess.Popen(cmd)
        timed_out = None
        while process.poll() is None:
            time.sleep(2.0)
            try:
                cur = json.loads(current.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            key = f"{cur['project']}/{cur['model']}"
            finished = key in _finished(results)
            if not finished and time.time() - cur["started"] > budget:
                timed_out = cur
                print(f"timeout: {key} exceeded {budget:g} s; killing and resuming", flush=True)
                _kill_tree(process)
                break
        if timed_out is None:
            return process.returncode
        with results.open("a", encoding="utf-8") as io:
            io.write(json.dumps({"project": timed_out["project"], "model": timed_out["model"],
                                 "status": "timeout", "budgetS": budget}) + "\n")
        resume = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("only", nargs="*", help="project or project/model filters")
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "export-out")
    parser.add_argument("--skip-julia", action="store_true",
                        help="reuse an existing results.jsonl")
    parser.add_argument("--budget", type=float, default=600.0,
                        help="seconds one model may take (export + reference); a model over "
                             "budget is killed and logged as 'timeout'")
    parser.add_argument("--settings", default=None,
                        help="export settings as JSON for every model, e.g. "
                             "'{\"method\": \"ros2\", \"linear_solver\": \"sparse\"}'")
    args = parser.parse_args()
    out = args.out.resolve()
    if args.settings is not None:
        args.settings = json.dumps(json.loads(args.settings), separators=(",", ":"))

    if not args.skip_julia and run_julia(out, args.only, args.budget, args.settings) != 0:
        print("FAIL: the Julia export run crashed")
        return 2

    rows = []
    failures = 0
    for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        row = {"key": f"{rec['project']}/{rec['model']}", "status": rec["status"], "rec": rec}
        if rec["status"] == "exported":
            export_dir = Path(rec["dir"]) / "export"
            report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
            row["report"] = report
            steps = max(200, min(20_000, 20_000_000 // max(1, report["substeps"])))
            build = build_fmu(export_dir, runtime_dir=RUNTIME, harness_steps=steps)
            row["build"] = build
            if not build.ok or build.fmu is None:
                row["status"] = "build_failed"
                failures += 1
            else:
                try:
                    row["cmp"] = compare(export_dir, Path(rec["dir"]) / "reference", report,
                                         build.fmu)
                    row["status"] = "diverged" if row["cmp"]["nonfinite"] else "compared"
                    failures += row["status"] == "diverged"
                except Exception as err:  # fmpy raises on an FMU error status
                    row["status"] = "fmu_error"
                    row["error"] = str(err)[:300]
                    failures += 1
        rows.append(row)
        print(f"{row['key']:55s} {row['status']}", flush=True)

    lines = [
        "| model | status | states | dt | substeps | worst error (rel. to peak) | signal | doStep mean / max µs | note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        rec, rep, b, c = row["rec"], row.get("report"), row.get("build"), row.get("cmp")
        if rep is None:
            reason = "; ".join(f"{d['code']}: {d['message']}" for d in rec.get("diagnostics", []))
            reason = reason or rec.get("error", "")[:200]
            if rec["status"] == "timeout":
                reason = f"over the {rec['budgetS']:g} s budget (logged, not investigated)"
            lines.append(f"| {row['key']} | {row['status']} | | | | | | | {reason[:220]} |")
            continue
        warn = sorted({w["code"] for w in rec.get("warnings", []) if w["code"] != "W209"})
        note = ", ".join(warn)
        if b is not None and b.error:
            note += " " + b.error.splitlines()[0][:150]
        if row.get("error"):
            note += " " + row["error"][:150]
        timing = (f"{b.step_time_mean_us:.2f} / {b.step_time_max_us:.0f}"
                  if b is not None and b.step_time_mean_us is not None else "")
        worst = f"{c['worstRel']:.2e}" if c else ""
        sig = f"`{c['worstSignal']}`" if c and c["worstSignal"] else ""
        lines.append(f"| {row['key']} | {row['status']} | {rep['states']} | {rep['dt']:.3g} | "
                     f"{rep['substeps']} | {worst} | {sig} | {timing} | {note} |")
    table = "\n".join(lines)
    step_rows = [row for row in rows if (row.get("report") or {}).get("linearAlgebra")]
    if step_rows:
        lines = [
            "",
            "Linear algebra and step time (Rosenbrock exports; LU flops per factorization):",
            "",
            "| model | method | Jacobian | colours | nnz J | LU | nnz LU | fill-in | LU flops "
            "(dense) | pivot ratio | doStep mean / max µs |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in step_rows:
            rep, b = row["report"], row.get("build")
            la = rep["linearAlgebra"]
            timing = (f"{b.step_time_mean_us:.2f} / {b.step_time_max_us:.0f}"
                      if b is not None and b.step_time_mean_us is not None else "")
            jac = la["jacobian"] + (f" ({la['fdDerivativeCalls']} calls)"
                                    if la.get("fdDerivativeCalls") else "")
            sparse = la["linearSolver"] == "sparse"
            lines.append(
                f"| {row['key']} | {rep['method']}, dt {rep['dt']:.3g} | {jac} | {la['colours']} | "
                f"{la['nnzJ']} | {la['linearSolver']} | {la['nnzLU'] if sparse else ''} | "
                f"{la['fillIn'] if sparse else ''} | {la['luFlops']} ({la['denseLuFlops']}) | "
                f"{la['pivotCheck']['minPivotRatio']:.2e} | {timing} |")
        table += "\n" + "\n".join(lines)
    (out / "EXPORT_RESULTS.md").write_text(table + "\n", encoding="utf-8")
    print()
    print(table)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
