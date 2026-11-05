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
4. X-EX1, for a model with export markers: an FMU with input markers is driven through its
   inputs by the trajectory ``export_examples.jl`` wrote (``inputs.json``, the samples the
   reference run was driven with; ``run_driven``), and the markers-only FMU
   (``export-markers``, no ``expose_all``) is built, its modelDescription checked against the
   markers (``check_interface``) and its outputs compared the same way (``interface_check``).
   ``expected.json`` ``models.<m>.export`` gates the result: ``status``, ``max_rel_error``
   (all signals and the interface outputs), ``inputs`` (the trajectory's range per input) and
   ``interface`` (the exact input/output/parameter names).

The summary table goes to stdout and ``<out>/EXPORT_RESULTS.md``; Rosenbrock exports add a
second table with the Jacobian, the LU (non-zeros, fill-in, flops) and the step time. The exit code is non-zero
when an exported model fails a check: a forbidden symbol, an allocation after
instantiate, a failed build, or a diverged FMU, and, where ``expected.json`` has an
``export`` entry, an outcome or an error that misses it or a failed interface check.
Accuracy is otherwise reported, not gated. ``<out>/export_checks.json`` holds every row
(the comparison per signal, the interface check and the input ranges).
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


def run_driven(fmu: Path, names: list[str], inputs: dict, t_end: float, step: float,
               params: dict[str, float] | None = None) -> dict:
    """Run the FMU with its inputs set from ``inputs`` (X-EX1), in an explicit loop.

    ``inputs`` is ``inputs.json`` of ``export_examples.jl``: ``t`` (the communication instants
    k*step) and ``u`` (name -> samples). At each instant t_k the loop sets sample k on the
    inputs, then reads ``names`` (so a row is the right limit after the new input, as the
    reference's), then calls ``doStep(t_k, step)``: the FMU holds sample k over [t_k, t_k+1)
    (zero-order hold; its discrete partitions due at t_k+1 run at the end of that step, so
    they sample k, not k+1). This is exactly what ``simulate(...; inputs)`` does.
    fmpy's ``simulate_fmu(input=...)`` is not used: it records each row before it sets the
    next input (the left limit) and interpolates a table linearly between its rows.
    ``params`` are FMU parameters set before initialization (a run from another start).
    """
    from fmpy import extract, read_model_description
    from fmpy.fmi2 import FMU2Slave

    md = read_model_description(str(fmu))
    vr = {v.name: v.valueReference for v in md.modelVariables}
    t = np.asarray(inputs["t"], dtype=float)
    n = round(t_end / step)
    if len(t) != n + 1 or np.max(np.abs(t - step * np.arange(n + 1))) > 1e-9 * max(1.0, t_end):
        raise ValueError("the input samples are not the communication instants k*step")
    in_names = list(inputs["u"])
    in_vrs = [vr[k] for k in in_names]
    u = np.asarray([inputs["u"][k] for k in in_names], dtype=float)  # (inputs, samples)
    out_vrs = [vr[k] for k in names]
    rows = np.empty((n + 1, len(names)))
    unzip = extract(str(fmu))
    slave = FMU2Slave(guid=md.guid, unzipDirectory=unzip,
                      modelIdentifier=md.coSimulation.modelIdentifier, instanceName="gate")
    slave.instantiate()
    try:
        if params:
            slave.setReal([vr[k] for k in params], list(params.values()))
        slave.setupExperiment(startTime=0.0, stopTime=t_end)
        slave.enterInitializationMode()
        slave.exitInitializationMode()
        for k in range(n + 1):
            slave.setReal(in_vrs, list(u[:, k]))
            rows[k] = slave.getReal(out_vrs)
            if k < n:
                slave.doStep(currentCommunicationPoint=k * step, communicationStepSize=step)
        slave.terminate()
    finally:
        slave.freeInstance()
    res = {"time": step * np.arange(n + 1)}
    for j, name in enumerate(names):
        res[name] = rows[:, j]
    return res


def compare(export_dir: Path, ref_dir: Path, report: dict, fmu: Path,
            inputs: dict | None = None, names: list[str] | None = None) -> dict:
    from fmpy import simulate_fmu

    if names is None:
        names = report["locals"] + [o["name"] for o in report["outputs"]]
    t0 = time.monotonic()
    if inputs is None:
        res = simulate_fmu(str(fmu), stop_time=report["tEnd"], output_interval=report["step"],
                           output=names, fmi_type="CoSimulation")
    else:
        res = run_driven(fmu, names, inputs, report["tEnd"], report["step"])
    wall = time.monotonic() - t0
    ids, ref = reference(ref_dir)
    col = {s: i + 1 for i, s in enumerate(ids)}
    t = res["time"]
    idx = np.clip(np.searchsorted(ref[:, 0], t - 1e-12), 0, len(ref) - 1)
    ok = np.abs(ref[idx, 0] - t) < 1e-9 * max(1.0, report["tEnd"])
    worst = (0.0, None, 0.0, 0.0)
    compared = 0
    nonfinite = []
    per_signal = {}
    for name in names:
        # An output is the signal on its marker's input `u`.
        key = name if name in col else f"{name}/u"
        if key not in col:
            continue
        a = res[name][ok]
        b = ref[idx[ok], col[key]]
        if not np.all(np.isfinite(a)):
            nonfinite.append(name)
            continue
        compared += 1
        peak = float(np.max(np.abs(b))) if len(b) else 0.0
        err = np.abs(a - b)
        k = int(np.argmax(err)) if len(err) else 0
        rel = float(err[k] / peak) if peak > 1e-9 else float(err[k])
        per_signal[name] = {"rel": rel, "abs": float(err[k]), "t": float(t[ok][k]), "peak": peak}
        if rel > worst[0]:
            worst = (rel, name, float(t[ok][k]), peak)
    return {
        "compared": compared, "times": int(ok.sum()), "worstRel": worst[0],
        "worstSignal": worst[1], "worstT": worst[2], "worstPeak": worst[3],
        "nonfinite": nonfinite, "fmpyWallS": wall, "driven": inputs is not None,
        "perSignal": per_signal,
    }


def check_interface(fmu: Path, report: dict, rec: dict, expected: dict | None) -> list[str]:
    """The markers-only FMU's modelDescription against its markers (X-EX1).

    Exactly the marked inputs (causality input, variability continuous, the marker's start
    value, the declared range as min/max if finite) and outputs (causality output,
    continuous or discrete), every other variable a parameter (no locals: `expose_all` is
    off), the outputs listed in ModelStructure, and, when expected.json names them, the
    exact interface. Units are compared when expected.json gives them; the modelDescription
    declares none yet. Returns the problems found (empty: the check passed).
    """
    from fmpy import read_model_description
    from fmpy.validation import validate_fmu

    problems = [f"fmpy validation: {e}" for e in validate_fmu(str(fmu))]
    md = read_model_description(str(fmu))
    by_c: dict[str, list] = {}
    for v in md.modelVariables:
        by_c.setdefault(v.causality, []).append(v)
    ins = {v.name: v for v in by_c.get("input", [])}
    outs = {v.name: v for v in by_c.get("output", [])}
    want_in = {i["name"]: i for i in rec.get("inputs", [])}
    want_out = {o["name"] for o in report["outputs"]}
    if set(ins) != set(want_in):
        problems.append(f"inputs {sorted(ins)} != markers {sorted(want_in)}")
    if set(outs) != want_out:
        problems.append(f"outputs {sorted(outs)} != markers {sorted(want_out)}")
    other = sorted(c for c in by_c if c not in ("input", "output", "parameter"))
    if other:
        problems.append(f"unexpected causalities {other}")
    for name, v in ins.items():
        if v.variability != "continuous" or v.type != "Real":
            problems.append(f"input {name}: {v.type} {v.variability}")
        want = want_in.get(name)
        if want is not None and float(v.start) != float(want["start"]):
            problems.append(f"input {name}: start {v.start} != marker value {want['start']}")
    for name, v in outs.items():
        if v.variability not in ("continuous", "discrete") or v.type != "Real":
            problems.append(f"output {name}: {v.type} {v.variability}")
    for v in by_c.get("parameter", []):
        if v.variability not in ("fixed", "tunable"):
            problems.append(f"parameter {v.name}: variability {v.variability}")
    listed = sorted(u.variable.name for u in md.outputs)
    if listed != sorted(outs):
        problems.append(f"ModelStructure/Outputs {listed} != outputs {sorted(outs)}")
    if expected:
        for kind, have in (("inputs", ins), ("outputs", outs),
                           ("parameters", {v.name: v for v in by_c.get("parameter", [])})):
            if kind in expected and sorted(expected[kind]) != sorted(have):
                problems.append(f"{kind} {sorted(have)} != expected.json {sorted(expected[kind])}")
        for name, unit in (expected.get("units") or {}).items():
            v = ins.get(name) or outs.get(name)
            have_unit = getattr(v, "unit", None) if v is not None else None
            if have_unit != unit:
                problems.append(f"{name}: unit {have_unit!r} != {unit!r}")
    return problems


def interface_check(rec: dict, inputs: dict | None) -> dict:
    """X-EX1: build the markers-only FMU, check its modelDescription and compare its outputs,
    driven through its inputs, with the (equally driven) reference."""
    export_dir = Path(rec["dir"]) / "export-markers"
    report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
    out: dict = {"ok": False, "inputs": [i["name"] for i in report["inputs"]],
                 "outputs": [o["name"] for o in report["outputs"]],
                 "parameters": [p["name"] for p in report["parameters"]],
                 "locals": len(report["locals"])}
    build = build_fmu(export_dir, runtime_dir=RUNTIME, harness_steps=200)
    out["buildOk"] = bool(build.ok and build.fmu is not None)
    if not out["buildOk"]:
        out["problems"] = [f"build failed: {(build.error or '').splitlines()[:1]}"]
        return out
    exp = expected_export(rec["project"], rec["model"]) or {}
    out["problems"] = check_interface(build.fmu, report, rec, exp.get("interface"))
    try:
        cmp = compare(export_dir, Path(rec["dir"]) / "reference", report, build.fmu,
                      inputs=inputs, names=out["outputs"])
        out["perOutput"] = cmp["perSignal"]
        out["worstRel"] = cmp["worstRel"]
        out["worstSignal"] = cmp["worstSignal"]
        out["driven"] = cmp["driven"]
        if cmp["nonfinite"]:
            out["problems"].append(f"non-finite outputs {cmp['nonfinite']}")
        if cmp["compared"] != len(out["outputs"]):
            out["problems"].append(f"compared {cmp['compared']} of {len(out['outputs'])} outputs")
    except Exception as err:  # fmpy raises on an FMU error status
        out["problems"].append(f"FMU error: {str(err)[:300]}")
    out["ok"] = not out["problems"]
    return out


def expected_export(project: str, model: str) -> dict | None:
    path = ROOT / "examples" / project / "expected.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ((data.get("models") or {}).get(model) or {}).get("export")


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
            inputs = None
            if rec.get("inputFile"):
                inputs = json.loads(Path(rec["inputFile"]).read_text(encoding="utf-8"))
            if not build.ok or build.fmu is None:
                row["status"] = "build_failed"
                failures += 1
            else:
                try:
                    row["cmp"] = compare(export_dir, Path(rec["dir"]) / "reference", report,
                                         build.fmu, inputs=inputs)
                    row["status"] = "diverged" if row["cmp"]["nonfinite"] else "compared"
                    failures += row["status"] == "diverged"
                except Exception as err:  # fmpy raises on an FMU error status
                    row["status"] = "fmu_error"
                    row["error"] = str(err)[:300]
                    failures += 1
            if rec.get("markersExport") == "exported":
                row["io"] = interface_check(rec, inputs)
                failures += not row["io"]["ok"]
            exp = expected_export(rec["project"], rec["model"])
            if exp is not None:
                row["expected"] = exp
                problems = []
                if exp.get("status") and exp["status"] != row["status"]:
                    problems.append(f"status {row['status']} != expected {exp['status']}")
                limit = exp.get("max_rel_error")
                worst = (row.get("cmp") or {}).get("worstRel")
                if limit is not None and worst is not None and worst > limit:
                    problems.append(f"worst error {worst:.3e} > max_rel_error {limit:g}")
                io_worst = (row.get("io") or {}).get("worstRel")
                if limit is not None and io_worst is not None and io_worst > limit:
                    problems.append(f"interface error {io_worst:.3e} > max_rel_error {limit:g}")
                row["expectedProblems"] = problems
                failures += bool(problems)
        elif rec["status"] != "exported":
            exp = expected_export(rec["project"], rec["model"])
            if exp is not None and exp.get("status") and exp["status"] != rec["status"]:
                row["expectedProblems"] = [f"status {rec['status']} != expected {exp['status']}"]
                failures += 1
        rows.append(row)
        print(f"{row['key']:55s} {row['status']}"
              + (f"  interface {'OK' if row['io']['ok'] else 'FAIL'}" if row.get("io") else "")
              + ("  " + "; ".join(row["expectedProblems"]) if row.get("expectedProblems") else ""),
              flush=True)

    lines = [
        "| model | status | states | dt | substeps | worst error (rel. to peak) | signal | doStep mean / max µs | note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        rec, rep, b, c = row["rec"], row.get("report"), row.get("build"), row.get("cmp")
        if rep is None:
            reason = "; ".join(f"{d['code']}: {d['message']}" + (f" ({d['hint']})" if d.get("hint") else "")
                               for d in rec.get("diagnostics", []))
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
    io_rows = [row for row in rows if row.get("io")]
    if io_rows:
        lines = [
            "",
            ("Export interface (X-EX1): the markers-only FMU driven through its inputs by the "
             "same zero-order-hold trajectory as the reference (error relative to each output's peak):"),
            "",
            "| model | inputs | outputs | parameters | modelDescription | error per output | check |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in io_rows:
            io = row["io"]
            errs = ", ".join(f"`{k}` {v['rel']:.2e}" for k, v in (io.get("perOutput") or {}).items())
            mdesc = "OK" if not [p for p in io.get("problems", []) if not p.startswith("FMU error")] \
                else "; ".join(io["problems"])[:200]
            lines.append(f"| {row['key']} | {', '.join(io['inputs'])} | {', '.join(io['outputs'])} | "
                         f"{len(io['parameters'])} | {mdesc} | {errs} | "
                         f"{'OK' if io['ok'] else 'FAIL'} |")
        table += "\n" + "\n".join(lines)
    (out / "EXPORT_RESULTS.md").write_text(table + "\n", encoding="utf-8")
    summary = []
    for row in rows:
        b = row.get("build")
        summary.append({
            "key": row["key"], "status": row["status"],
            "inputs": row["rec"].get("inputs"),
            "compare": row.get("cmp"), "interface": row.get("io"),
            "expected": row.get("expected"), "expectedProblems": row.get("expectedProblems"),
            "doStepMeanUs": b.step_time_mean_us if b is not None else None,
        })
    (out / "export_checks.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    print(table)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
