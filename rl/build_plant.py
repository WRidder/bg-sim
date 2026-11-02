"""R0.1: build the plant FMU written by rl/export_plant.jl and check it in fmpy.

    uv run --project rl rl/build_plant.py <out_dir>

1. ``bgsim_server.fmu_build.build_fmu``: -Werror, C++17, the hot-path symbol check, the counting
   allocation harness and the doStep timing (as every export).
2. ``fmpy.validation.validate_fmu`` is clean; the interface is the markers (V, F_push in; x, q1,
   q2, v, w1, w2, i_m out) and the exposed globals (fixed parameters with min/max).
3. The FMU driven by the voltage trajectory of ``inputs.json`` against the Julia reference
   (Rodas5P, reltol 1e-8): max error of every output relative to its peak.
4. The same with the modified globals set before initialisation, against the Julia run with
   those globals (``reference_mod``).
5. A value outside its range is refused (fmi2Error).
Writes ``<out_dir>/check.json``; exit code 1 when a gate fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend import ROOT, RUNTIME  # noqa: E402

sys.path.insert(0, str(ROOT / "backend" / "src"))
from bgsim_server.fmu_build import build_fmu  # noqa: E402

# The reference records each output marker's input as `<name>/u`.
REF_SIGNAL = {k: k + "/u" for k in ("x", "q1", "q2", "v", "w1", "w2", "i_m")}
GATE = 2e-3   # relative to the peak, over a 3 s open-loop run of a chaotic double pendulum
# The motor current: the electrical pole (-R/L = -3000 1/s) is not resolved by a 1 ms Rosenbrock
# step (h|lambda| = 3, damped instead), so right after a voltage step the sampled current differs
# by a few percent; the force it integrates to (and every mechanical output) is unaffected. It is
# a privileged (critic) signal only, the policy never sees it.
GATE_CURRENT = 5e-2


def reference(ref_dir: Path):
    manifest = json.loads((ref_dir / "manifest.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in manifest["signals"]]
    rows = np.fromfile(ref_dir / "stream.f64", dtype="<f8").reshape(-1, 1 + len(ids))
    keep = np.append(rows[1:, 0] != rows[:-1, 0], True)
    return ids, rows[keep]


def run_driven(fmu: Path, names, inputs, t_end, step, start=None, log=None):
    from fmpy import extract, read_model_description
    from fmpy.fmi2 import FMU2Slave

    md = read_model_description(str(fmu))
    vr = {v.name: v.valueReference for v in md.modelVariables}
    n = round(t_end / step)
    u = np.asarray(inputs["u"]["V"], dtype=float)
    rows = np.empty((n + 1, len(names)))
    slave = FMU2Slave(guid=md.guid, unzipDirectory=extract(str(fmu)),
                      modelIdentifier=md.coSimulation.modelIdentifier, instanceName="r01",
                      fmiCallLogger=log)
    slave.instantiate(loggingOn=log is not None)
    try:
        slave.setupExperiment(startTime=0.0, stopTime=t_end)
        for k, v in (start or {}).items():
            slave.setReal([vr[k]], [v])
        slave.enterInitializationMode()
        slave.exitInitializationMode()
        out_vrs = [vr[k] for k in names]
        for k in range(n + 1):
            slave.setReal([vr["V"]], [u[k]])
            rows[k] = slave.getReal(out_vrs)
            if k < n:
                slave.doStep(currentCommunicationPoint=k * step, communicationStepSize=step)
        slave.terminate()
    finally:
        slave.freeInstance()
    return rows


def compare(rows, names, ref_dir, step):
    ids, ref = reference(ref_dir)
    col = {s: i + 1 for i, s in enumerate(ids)}
    t = step * np.arange(len(rows))
    idx = np.clip(np.searchsorted(ref[:, 0], t - 1e-12), 0, len(ref) - 1)
    ok = np.abs(ref[idx, 0] - t) < 1e-9
    out = {}
    for j, name in enumerate(names):
        b = ref[idx[ok], col[REF_SIGNAL[name]]]
        a = rows[ok, j]
        peak = float(np.max(np.abs(b)))
        out[name] = {"maxAbs": float(np.max(np.abs(a - b))), "peak": peak,
                     "rel": float(np.max(np.abs(a - b)) / peak)}
    return out


def refused_out_of_range(fmu: Path, name: str, value: float) -> bool:
    from fmpy import extract, read_model_description
    from fmpy.fmi2 import FMU2Slave

    md = read_model_description(str(fmu))
    vr = {v.name: v.valueReference for v in md.modelVariables}
    slave = FMU2Slave(guid=md.guid, unzipDirectory=extract(str(fmu)),
                      modelIdentifier=md.coSimulation.modelIdentifier, instanceName="range")
    slave.instantiate()
    try:
        slave.setupExperiment(startTime=0.0)
        try:
            slave.setReal([vr[name]], [value])
        except Exception:
            return True
        return False
    finally:
        slave.freeInstance()


def main(out: Path) -> int:
    from fmpy import read_model_description
    from fmpy.validation import validate_fmu

    case = json.loads((out / "case.json").read_text(encoding="utf-8-sig"))
    export = out / "export"
    res = build_fmu(export, runtime_dir=RUNTIME, harness_steps=20_000)
    report = json.loads((export / "export.json").read_text(encoding="utf-8"))
    rec = {"method": report["method"], "dt": report["dt"], "substeps": report["substeps"],
           "build": report["build"], "states": report["states"]}
    print(f"build ok={res.ok} doStep mean {res.step_time_mean_us} us max {res.step_time_max_us} us "
          f"(step {report['step']} s = {report['substeps']} x {report['method']} {report['dt']} s), "
          f"allocations after instantiate {res.allocations_after_instantiate}, "
          f"forbidden {res.forbidden_symbols}, C++17 {res.cxx_ok}")
    problems = validate_fmu(str(res.fmu))
    rec["validate"] = problems
    md = read_model_description(str(res.fmu))
    rec["interface"] = {
        "inputs": [v.name for v in md.modelVariables if v.causality == "input"],
        "outputs": [v.name for v in md.modelVariables if v.causality == "output"],
        "parameters": {v.name: [v.min, v.max, v.start, v.unit] for v in md.modelVariables
                       if v.causality == "parameter"},
        "calculated": [v.name for v in md.modelVariables if v.causality == "calculatedParameter"],
    }
    print("fmpy validate:", problems or "clean")
    print("interface:", json.dumps(rec["interface"]))
    inputs = json.loads((out / "inputs.json").read_text(encoding="utf-8"))
    names = list(REF_SIGNAL)
    rows = run_driven(res.fmu, names, inputs, case["tEnd"], case["step"])
    rec["nominal"] = compare(rows, names, out / "reference", case["step"])
    rows = run_driven(res.fmu, names, inputs, case["tEnd"], case["step"], start=case["modified"])
    rec["modified"] = compare(rows, names, out / "reference_mod", case["step"])
    for label in ("nominal", "modified"):
        print(label, {k: f"{v['rel']:.2e}" for k, v in rec[label].items()})
    name = "m1" if "m1" in case["ranges"] else sorted(case["ranges"])[0]
    lo, hi = case["ranges"][name]
    bad = hi + (hi - lo)
    rec["outOfRangeRefused"] = refused_out_of_range(res.fmu, name, bad)
    print(f"{name} = {bad:g} (range [{lo:g}, {hi:g}]) refused:", rec["outOfRangeRefused"])
    worst = max(v["rel"] for lab in ("nominal", "modified") for k, v in rec[lab].items() if k != "i_m")
    worst_i = max(rec[lab]["i_m"]["rel"] for lab in ("nominal", "modified"))
    rec["worstRel"] = worst
    rec["worstRelCurrent"] = worst_i
    rec["gate"] = GATE
    rec["gateCurrent"] = GATE_CURRENT
    ok = (res.ok and not problems and rec["outOfRangeRefused"] and worst <= GATE
          and worst_i <= GATE_CURRENT)
    rec["ok"] = ok
    (out / "check.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print("R0.1", "PASS" if ok else "FAIL", f"(mechanics worst {worst:.2e} of the peak, gate {GATE}; "
          f"current {worst_i:.2e}, gate {GATE_CURRENT})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve()))
