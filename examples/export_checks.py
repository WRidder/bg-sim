# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "fmpy>=0.3.20"]
# ///
"""Export every example model to an FMU and compare it with simulation (plan X-EX1).

    uv run examples/export_checks.py [--out DIR] [--skip-julia] [project[/model] ...]

1. ``examples/export_examples.jl`` (one Julia process) exports each model, runs its reference
   simulation and writes ``results.jsonl`` (a refused model records its E110/E111 reason);
2. for each exported model, ``bgsim_server.fmu_build`` compiles the FMU and runs the
   hot-path symbol check and the counting allocation harness;
3. the FMU runs in fmpy on the reference's output grid, and every recorded signal is compared
   with the reference (right limits at event instants): the error relative to the signal's
   peak, signals with a peak below 1e-9 compared absolutely.

The summary table goes to stdout and ``<out>/EXPORT_RESULTS.md``. The exit code is non-zero
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("only", nargs="*", help="project or project/model filters")
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "export-out")
    parser.add_argument("--skip-julia", action="store_true",
                        help="reuse an existing results.jsonl")
    args = parser.parse_args()
    out = args.out.resolve()

    if not args.skip_julia:
        cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}",
               str(ROOT / "examples" / "export_examples.jl"), str(out), *args.only]
        print("+", " ".join(cmd), flush=True)
        if subprocess.run(cmd).returncode != 0:
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
            build = build_fmu(export_dir, runtime_dir=RUNTIME, harness_steps=20_000)
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
