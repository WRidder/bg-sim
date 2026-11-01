"""R0.2: the batched C environment, checked against fmpy and timed.

    uv run --project rl rl/bench_env.py <plant out_dir> [--procs 12] [--quick]

1. Agreement: the shim (rl/cenv/bgenv.c) driven by the voltage trajectory of inputs.json against
   the same FMU in fmpy, nominal and with the modified globals set before initialisation (the
   difference must be at rounding level: it is the same C).
2. Throughput: N instances stepped with random voltages, nsub = 5 internal 1 ms steps per call
   (a 200 Hz policy step), resets of the instances that leave the rail. Single thread for
   N = 1 .. 4096, OpenMP with 12 threads, and 12 processes of one thread each. The time inside
   bg_step (C clock) against the wall time of the Python call gives the overhead.
3. The fmpy fallback: one FMU2Slave, doStep from Python (what one env step costs without the shim).
Writes <out_dir>/bench.json.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rlpend.cbuild import BatchedPlant, build  # noqa: E402

NSUB = 5


def agreement(out: Path, lib: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_plant import run_driven

    case = json.loads((out / "case.json").read_text(encoding="utf-8-sig"))
    inputs = json.loads((out / "inputs.json").read_text(encoding="utf-8"))
    fmu = next((out / "export").glob("*.fmu"))
    names = ["x", "q1", "q2", "v", "w1", "w2", "i_m"]
    u = np.asarray(inputs["u"]["V"])
    res = {}
    for label, start in (("nominal", {}), ("modified", case["modified"])):
        ref = run_driven(fmu, names, inputs, case["tEnd"], case["step"], start=start)
        env = BatchedPlant(out / "export", 3, threads=1, lib=lib)
        env.reset(None, {k: np.full(3, v) for k, v in start.items()})
        rows = np.empty_like(ref)
        col = [env.y_names.index(k) for k in names]
        for k in range(len(u)):
            rows[k] = env.y[0, col]
            if k < len(u) - 1:
                uu = np.zeros((3, env.nu))
                uu[:, 0] = u[k]
                env.step(uu, 1)
        env.close()
        res[label] = float(np.max(np.abs(rows - ref)))
    return res


def run_bench(export_dir: str, lib: str, n: int, threads: int, seconds: float, seed: int = 0) -> dict:
    env = BatchedPlant(Path(export_dir), n, threads=threads, lib=Path(lib))
    rng = np.random.default_rng(seed)
    ix = env.y_names.index("x")
    u = np.zeros((n, env.nu))
    steps = 0
    resets = 0
    wall_step = 0.0
    t_end = time.perf_counter() + seconds
    p0 = env.plant_seconds()
    t0 = time.perf_counter()
    while time.perf_counter() < t_end:
        u[:, 0] = rng.uniform(-12.0, 12.0, n)
        a = time.perf_counter()
        y = env.step(u, NSUB)
        wall_step += time.perf_counter() - a
        steps += n
        out = (np.abs(y[:, ix]) > 0.4) | (env.status != 0)
        if out.any():
            env.reset(out)
            resets += int(out.sum())
    wall = time.perf_counter() - t0
    plant = env.plant_seconds() - p0
    env.close()
    return {"n": n, "threads": threads, "envSteps": steps, "wallS": wall, "resets": resets,
            "stepsPerS": steps / wall, "plantS": plant, "stepCallS": wall_step,
            "usPerInternalStepPlant": plant * threads / (steps * NSUB) * 1e6 if threads == 1 else None,
            "usPerEnvStepWall": wall / steps * 1e6}


def _proc(args):
    return run_bench(*args)


def fmpy_fallback(out: Path, seconds: float) -> dict:
    from fmpy import extract, read_model_description
    from fmpy.fmi2 import FMU2Slave

    fmu = next((out / "export").glob("*.fmu"))
    md = read_model_description(str(fmu))
    vr = {v.name: v.valueReference for v in md.modelVariables}
    s = FMU2Slave(guid=md.guid, unzipDirectory=extract(str(fmu)),
                  modelIdentifier=md.coSimulation.modelIdentifier, instanceName="bench")
    s.instantiate()
    s.setupExperiment(startTime=0.0)
    s.enterInitializationMode()
    s.exitInitializationMode()
    outs = [vr[k] for k in ("x", "q1", "q2")]
    rng = np.random.default_rng(1)
    t, steps = 0.0, 0
    t_end = time.perf_counter() + seconds
    t0 = time.perf_counter()
    while time.perf_counter() < t_end:
        s.setReal([vr["V"]], [float(rng.uniform(-2, 2))])
        for _ in range(NSUB):
            s.doStep(currentCommunicationPoint=t, communicationStepSize=1e-3)
            t += 1e-3
        s.getReal(outs)
        steps += 1
    wall = time.perf_counter() - t0
    s.terminate()
    s.freeInstance()
    return {"envSteps": steps, "wallS": wall, "stepsPerS": steps / wall, "usPerEnvStep": wall / steps * 1e6}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--seconds", type=float, default=4.0)
    args = ap.parse_args()
    out = args.out.resolve()
    lib = build(out / "export")
    rec = {"nsub": NSUB, "policyPeriodS": NSUB * 1e-3}
    rec["agreementMaxAbs"] = agreement(out, lib)
    print("shim vs fmpy (max abs over all outputs):", rec["agreementMaxAbs"])
    rec["single"] = []
    for n in (1, 16, 256, 1024, 4096):
        r = run_bench(str(out / "export"), str(lib), n, 1, args.seconds)
        rec["single"].append(r)
        print(f"1 thread  N={n:5d}: {r['stepsPerS']:9.0f} env steps/s, plant {r['usPerInternalStepPlant']:.2f} us per "
              f"1 ms step, wall {r['usPerEnvStepWall']:.2f} us per env step "
              f"(plant {r['plantS'] / r['wallS'] * 100:.0f} % of the wall time)")
    rec["openmp"] = []
    for n in (1024, 4096):
        r = run_bench(str(out / "export"), str(lib), n, args.procs, args.seconds)
        rec["openmp"].append(r)
        print(f"{args.procs} threads N={n:5d}: {r['stepsPerS']:9.0f} env steps/s "
              f"(step call {r['stepCallS'] / r['wallS'] * 100:.0f} % of the wall time)")
    with mp.get_context("spawn").Pool(args.procs) as pool:
        t0 = time.perf_counter()
        rs = pool.map(_proc, [(str(out / "export"), str(lib), 512, 1, args.seconds, s) for s in range(args.procs)])
        wall = time.perf_counter() - t0
    total = sum(r["stepsPerS"] for r in rs)
    rec["processes"] = {"procs": args.procs, "nPerProc": 512, "stepsPerS": total,
                        "perProc": [r["stepsPerS"] for r in rs], "wallS": wall}
    print(f"{args.procs} processes x N=512: {total:9.0f} env steps/s total "
          f"({min(r['stepsPerS'] for r in rs):.0f} .. {max(r['stepsPerS'] for r in rs):.0f} per process)")
    rec["fmpy"] = fmpy_fallback(out, args.seconds)
    print(f"fmpy fallback (1 instance, 5 doStep per env step): {rec['fmpy']['stepsPerS']:.0f} env steps/s, "
          f"{rec['fmpy']['usPerEnvStep']:.1f} us per env step")
    (out / "bench.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
