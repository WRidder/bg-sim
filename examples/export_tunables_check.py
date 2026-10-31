# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "fmpy>=0.3.20"]
# ///
"""J-EX8 acceptance: FMU parameters set before initialization, checked in fmpy.

    uv run examples/export_tunables_check.py [--out DIR] [--skip-julia] [case ...]

1. ``examples/export_tunables.jl`` exports each case twice (with the tunables, and folded),
   runs a Julia reference with the changed values, and for the globals case a folded export
   with the changed globals at the same step;
2. ``bgsim_server.fmu_build`` builds each FMU: -Werror, C++17, the hot-path symbol check, the
   counting allocation harness and the doStep timing;
3. in fmpy: (a) the tunable FMU with the changed values set before initialization against the
   Julia reference (every output and local, error relative to the signal's peak); (b) for the
   globals case, against the folded export with those globals; (c) a value outside its range
   is refused (fmi2Error, logged); (d) ``fmpy.validation.validate_fmu`` is clean.

The table goes to stdout and ``<out>/TUNABLES_RESULTS.md``. The exit code is non-zero when a
check fails. Gates: (a) 1e-3 of the peak (the X-EX0 tolerance class of these models), (b)
1e-9, zero allocations after instantiate, no forbidden symbol.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from bgsim_server.fmu_build import build_fmu  # noqa: E402
from export_checks import reference  # noqa: E402

RUNTIME = ROOT / "julia" / "BGSim" / "export" / "runtime"
TOL_REFERENCE = 1e-3
TOL_OVERRIDE = 1e-9


def simulate(fmu: Path, report: dict, start: dict[str, float]):
    from fmpy import simulate_fmu

    names = report["locals"] + [o["name"] for o in report["outputs"]]
    res = simulate_fmu(str(fmu), stop_time=report["tEnd"], output_interval=report["step"],
                       output=names, start_values=start, fmi_type="CoSimulation")
    return names, res


def worst_vs_reference(names, res, ref_dir: Path) -> tuple[float, str | None]:
    ids, ref = reference(ref_dir)
    col = {s: i + 1 for i, s in enumerate(ids)}
    t = res["time"]
    idx = np.clip(np.searchsorted(ref[:, 0], t - 1e-12), 0, len(ref) - 1)
    ok = np.abs(ref[idx, 0] - t) < 1e-9
    worst: tuple[float, str | None] = (0.0, None)
    for name in names:
        if name not in col:
            continue
        a, b = res[name][ok], ref[idx[ok], col[name]]
        peak = float(np.max(np.abs(b))) if len(b) else 0.0
        err = float(np.max(np.abs(a - b))) if len(b) else 0.0
        rel = err / peak if peak > 1e-9 else err
        if rel > worst[0]:
            worst = (rel, name)
    return worst


def worst_vs_fmu(names, a, b) -> float:
    worst = 0.0
    for name in names:
        peak = float(np.max(np.abs(b[name])))
        err = float(np.max(np.abs(a[name] - b[name])))
        worst = max(worst, err / peak if peak > 1e-9 else err)
    return worst


def refused(fmu: Path, report: dict, start: dict[str, float]) -> str | None:
    """The logged reason when fmpy's run fails, or None when it ran."""
    from fmpy import simulate_fmu

    messages: list[str] = []

    def logger(component, instance_name, status, category, message):
        messages.append(message.decode() if isinstance(message, bytes) else str(message))

    try:
        simulate_fmu(str(fmu), stop_time=report["step"] * 2, output_interval=report["step"],
                     start_values=start, fmi_type="CoSimulation", logger=logger,
                     debug_logging=False)
    except Exception as err:  # noqa: BLE001 - fmpy raises on fmi2Error
        return " | ".join(messages) or str(err)
    return None


def build(export_dir: Path, report: dict):
    steps = max(200, min(20_000, 20_000_000 // max(1, report["substeps"])))
    result = build_fmu(export_dir, runtime_dir=RUNTIME, harness_steps=steps)
    if not result.ok or result.fmu is None:
        raise RuntimeError(f"build of {export_dir} failed: {result.error}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "export-tunables-out")
    parser.add_argument("--skip-julia", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.skip_julia:
        cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}",
               str(ROOT / "examples" / "export_tunables.jl"), str(out), *args.cases]
        print("+", " ".join(cmd), flush=True)
        if subprocess.run(cmd).returncode != 0:
            print("FAIL: the Julia run crashed")
            return 2

    from fmpy.validation import validate_fmu

    failures: list[str] = []
    rows = []
    for line in (out / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        name = rec["case"]
        if not rec["ok"]:
            failures.append(f"{name}: refused {rec['diagnostics']}")
            continue
        case_dir = Path(rec["dir"])
        tun_rep = json.loads((case_dir / "tunable" / "export.json").read_text(encoding="utf-8"))
        fold_rep = json.loads((case_dir / "folded" / "export.json").read_text(encoding="utf-8"))
        tun_b = build(case_dir / "tunable", tun_rep)
        fold_b = build(case_dir / "folded", fold_rep)
        problems = validate_fmu(str(tun_b.fmu))
        names, res = simulate(tun_b.fmu, tun_rep, rec["values"])
        err_ref, sig = worst_vs_reference(names, res, case_dir / "reference")
        # The FMU at the model's own values against the folded FMU: the same model.
        _, res0 = simulate(tun_b.fmu, tun_rep, {})
        _, resf = simulate(fold_b.fmu, fold_rep, {})
        err_same = worst_vs_fmu(names, res0, resf) if tun_rep["dt"] == fold_rep["dt"] else None
        err_over = None
        if (case_dir / "override").exists():
            over_rep = json.loads((case_dir / "override" / "export.json").read_text(encoding="utf-8"))
            over_b = build(case_dir / "override", over_rep)
            _, reso = simulate(over_b.fmu, over_rep, {})
            err_over = worst_vs_fmu(names, res, reso)
        why = refused(tun_b.fmu, tun_rep, rec["outside"])
        tu = tun_rep["tunables"]
        row = {
            "case": name, "method": f"{tun_rep['method']} {tun_rep['dt']:.3g}",
            "folded": f"{fold_rep['method']} {fold_rep['dt']:.3g}",
            "tunables": ", ".join(tu["requested"] + [f"global:{g}" for g in tu["globals"]]),
            "recomputed": f"{tu['calculated']} calc, {tu['starts']} starts"
                          + (", Newton" if tu["newton"] else ""),
            "errRef": err_ref, "sig": sig, "errSame": err_same, "errOver": err_over,
            "outside": why, "validate": problems,
            "ops": f"{tu['rhsOps']} / {tu['rhsOpsFolded']}",
            "stepTun": tun_b.step_time_mean_us, "stepFold": fold_b.step_time_mean_us,
            "allocs": (tun_b.allocations_after_instantiate, fold_b.allocations_after_instantiate),
            "symbols": tun_b.forbidden_symbols, "cxx": tun_b.cxx_ok,
            "badRange": rec["badRangeRefused"],
        }
        rows.append(row)
        if err_ref > TOL_REFERENCE:
            failures.append(f"{name}: {err_ref:.2e} against the Julia run with the values ({sig})")
        if err_over is not None and err_over > TOL_OVERRIDE:
            failures.append(f"{name}: {err_over:.2e} against the folded export with the globals")
        if why is None or "outside its declared range" not in why:
            failures.append(f"{name}: the out-of-range value was not refused ({why})")
        if problems:
            failures.append(f"{name}: fmpy validate: {problems}")
        if row["allocs"] != (0, 0) or row["symbols"] or row["cxx"] is False:
            failures.append(f"{name}: allocations {row['allocs']}, symbols {row['symbols']}, C++ {row['cxx']}")
        if not rec["badRangeRefused"]:
            failures.append(f"{name}: a range without the model's value was not refused (E110)")

    lines = [
        "| case | tunables | recomputed at init | method (tunable / folded) | (a) vs Julia | (b) vs folded globals | same values vs folded | out of range | rhs ops tunable / folded | doStep µs tunable / folded | allocs | C++ |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        fmt = lambda v: "" if v is None else f"{v:.2e}"  # noqa: E731
        lines.append(
            f"| {r['case']} | {r['tunables']} | {r['recomputed']} | {r['method']} / {r['folded']} | "
            f"{fmt(r['errRef'])} (`{r['sig']}`) | {fmt(r['errOver'])} | {fmt(r['errSame'])} | "
            f"{'refused' if r['outside'] else 'NOT refused'} | {r['ops']} | "
            f"{r['stepTun']:.2f} / {r['stepFold']:.2f} | {r['allocs'][0]} | {r['cxx']} |")
    table = "\n".join(lines)
    (out / "TUNABLES_RESULTS.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    for r in rows:
        print(f"{r['case']}: out-of-range log: {r['outside']}")
    for f in failures:
        print("FAIL:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
