# /// script
# requires-python = ">=3.13"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Build step of the f16-sim host: export the FMU from bg-sim and write the start list.

    uv run build_fmu.py [--skip-export] [--keep DIR]

1. ``julia --project=<repo>/julia/BGSim <repo>/examples/export_f16.jl <tmp> --no-reference``
   exports ``examples/f16/models/f16-sim`` with the host interface (inputs, outputs, the trim
   globals, CG, mass and the law switches as FMU parameters);
2. ``bgsim_server.fmu_build.build_fmu`` compiles it with the system C compiler (gcc), checks the
   hot path (no allocation after instantiate, no forbidden symbol) and zips the FMU;
3. the FMU is copied to ``build/f16_sim.fmu`` and ``build/build.json`` records the method, the
   internal step and the doStep cost of the harness;
4. ``build/starts.json``: the trims of the start-condition menu, from the design scripts of the
   example (``examples/f16/design/simscen.trim_globals``, the same trim the model's own globals
   come from), checked against the FMU's parameter ranges.

Nothing in ``build/`` is committed: run this once after cloning, and again when the model changes.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BUILD = HERE / "build"
XCG = 0.35
# (label, ft/s, ft): the start-condition menu
STARTS = [
    ("Cruise 500 ft/s, 10 000 ft", 500.0, 10000.0),
    ("Slow 300 ft/s, 10 000 ft", 300.0, 10000.0),
    ("Fast 700 ft/s, 5 000 ft", 700.0, 5000.0),
    ("Low and fast 900 ft/s, 2 000 ft", 900.0, 2000.0),
    ("High 600 ft/s, 20 000 ft", 600.0, 20000.0),
    ("Approach 350 ft/s, 2 000 ft", 350.0, 2000.0),
]
# On the airfield (src/f16sim/terrain.py): the south end of the runway, and a final approach to it
RUNWAY_START = (3000.0 - 1500.0 + 100.0, -1800.0)     # north, east (m)
APPROACH_V, APPROACH_GAMMA, APPROACH_DIST = 76.0, -3.0, 3000.0      # m/s (148 kt), deg, m from the threshold


def export(tmp: Path) -> Path:
    cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(ROOT / "examples" / "export_f16.jl"),
           str(tmp), "--no-reference"]
    print("+", " ".join(cmd), flush=True)
    if subprocess.run(cmd).returncode != 0:
        raise SystemExit("the export failed (see the Julia output above)")
    return tmp / "fmu"


def build(export_dir: Path) -> dict:
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from bgsim_server.fmu_build import build_fmu

    res = build_fmu(export_dir, runtime_dir=ROOT / "julia" / "BGSim" / "export" / "runtime", harness_steps=2000)
    if not res.ok or res.fmu is None:
        raise SystemExit(f"the FMU build failed: {res.error}")
    report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
    BUILD.mkdir(exist_ok=True)
    shutil.copyfile(res.fmu, BUILD / "f16_sim.fmu")
    info = {"method": report["method"], "dt": report["dt"], "substeps": report["substeps"],
            "step": report["step"], "doStepMeanUs": res.step_time_mean_us, "doStepMaxUs": res.step_time_max_us,
            "allocationsAfterInstantiate": res.allocations_after_instantiate, "compiler": res.compiler,
            "ranges": report.get("tunables", {}).get("ranges")}
    (BUILD / "build.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {BUILD / 'f16_sim.fmu'}: {info['method']} dt {info['dt']} s, doStep "
          f"{res.step_time_mean_us:.1f} us mean, {res.allocations_after_instantiate} allocations after instantiate")
    return info


def starts() -> list[dict]:
    sys.path.insert(0, str(ROOT / "examples" / "f16" / "design"))
    import simscen

    out = []
    for label, vt, h in STARTS:
        _, g = simscen.trim_globals(vt, h, XCG)
        rec = {"label": label, "vt0": g["vt0"], "h0": g["h0"], "alpha0": g["alpha0"], "el0": g["el0"],
               "thtl0": g["thtl0"], "xcg": XCG}
        if not (0.0 <= rec["vt0"] <= 400.0 and 0.0 <= rec["h0"] <= 12000.0 and -5.0 <= rec["alpha0"] <= 25.0
                and -25.0 <= rec["el0"] <= 25.0 and 0.0 <= rec["thtl0"] <= 1.0):
            raise SystemExit(f"start {label!r} is outside the FMU's parameter ranges: {rec}")
        out.append(rec)
        print(f"start {label}: alpha {rec['alpha0']:.2f} deg, stabilator {rec['el0']:.2f} deg, throttle {rec['thtl0']:.3f}")
    import gear

    des = json.loads((ROOT / "examples" / "f16" / "design" / "design.json").read_text(encoding="utf-8"))["fbw"]
    st = gear.static(XCG)
    out.append({"label": "Runway, gear down, idle", "vt0": 0.0, "h0": st["h"], "alpha0": st["theta_deg"], "el0": 0.0,
                "thtl0": 0.0, "xcg": XCG, "gear0": 1.0, "north0": RUNWAY_START[0], "east0": RUNWAY_START[1]})
    ap = gear.trim_approach(des, APPROACH_V, APPROACH_GAMMA, xcg=XCG)
    h_app = APPROACH_DIST * math.tan(math.radians(-APPROACH_GAMMA)) + st["h"]
    out.append({"label": "Final approach, 148 kt, 3 deg, gear down", **ap, "h0": h_app, "xcg": XCG, "gear0": 1.0,
                "north0": 3000.0 - 1500.0 + 300.0 - APPROACH_DIST, "east0": RUNWAY_START[1]})
    print(f"start final approach: alpha {ap['alpha0']:.2f} deg, stabilator {ap['el0']:.2f} deg, throttle {ap['thtl0']:.3f}")
    BUILD.mkdir(exist_ok=True)
    (BUILD / "starts.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skip-export", action="store_true", help="only write build/starts.json")
    parser.add_argument("--keep", type=Path, help="export into this folder instead of a temporary one")
    args = parser.parse_args()
    if not args.skip_export:
        if args.keep:
            build(export(args.keep.resolve()))
        else:
            with tempfile.TemporaryDirectory(prefix="f16sim-export-") as tmp:
                build(export(Path(tmp)))
    starts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
