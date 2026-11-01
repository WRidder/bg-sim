# /// script
# requires-python = ">=3.13"
# dependencies = ["numpy>=2.0"]
# ///
"""Build step of the car-sim host: export both FMUs from bg-sim and write the start lists.

    uv run build_fmu.py [racecar|buggy ...] [--skip-export] [--keep DIR]

1. ``julia --project=<repo>/julia/BGSim <repo>/examples/export_cars.jl <tmp> <vehicles> --no-reference``
   exports ``examples/cars/models/racecar-sim`` and ``buggy-sim`` with the host interface (the
   inputs, the outputs, the start pose and charge, the motor and brake limits as FMU parameters);
2. ``bgsim_server.fmu_build.build_fmu`` compiles each with the system C compiler (gcc), checks the
   hot path (no allocation after instantiate, no forbidden symbol) and zips the FMU;
3. the FMUs are copied to ``build/<vehicle>_sim.fmu`` and ``build/build.json`` records, per
   vehicle, the method, the internal step and the doStep cost of the harness;
4. ``build/starts.json``: the start menus. On the track the chassis CG starts at the static ride
   height over z = 0 (``h_s`` of examples/cars/design/design.json); on the hills the start height
   is the highest ground under the four wheels plus ``h_s`` (``carsim.terrain.Hills``, the same
   height field the FMU's terrain uses), so the buggy drops a centimetre onto its wheels. Every
   start is checked against the FMU's parameter ranges.

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
DESIGN = ROOT / "examples" / "cars" / "design" / "design.json"
VEHICLES = ("racecar", "buggy")
# the start menus: (label, arc length on the track [m], lateral offset [m]) and (label, x, y, heading [deg])
TRACK_STARTS = [("Grid: 30 m before the line", -30.0, 0.0), ("Pit straight, 150 m past the line", 150.0, 0.0),
                ("Before the hairpin", 420.0, 0.0), ("Back section", 900.0, 0.0), ("Last corners", 1350.0, 0.0)]
HILL_STARTS = [("Loop start (0, -120), heading east", 0.0, -120.0, 0.0), ("Centre, heading north", 0.0, 0.0, 90.0),
               ("North-east hills", 150.0, 110.0, 200.0), ("West valley", -250.0, -40.0, 30.0),
               ("Far south", 60.0, -330.0, 120.0)]
RANGES = {"racecar": {"x0": (-1000, 1000), "y0": (-1000, 1000), "z0": (0.2, 1.0)},
          "buggy": {"x0": (-380, 380), "y0": (-380, 380), "z0": (-6.0, 8.0)}}


def export(tmp: Path, vehicles) -> Path:
    cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(ROOT / "examples" / "export_cars.jl"),
           str(tmp), *vehicles, "--no-reference"]
    print("+", " ".join(cmd), flush=True)
    if subprocess.run(cmd).returncode != 0:
        raise SystemExit("the export failed (see the Julia output above)")
    return tmp


def build(out: Path, vehicles) -> dict:
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from bgsim_server.fmu_build import build_fmu

    BUILD.mkdir(exist_ok=True)
    path = BUILD / "build.json"
    info = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for veh in vehicles:
        export_dir = out / veh / "fmu"
        res = build_fmu(export_dir, runtime_dir=ROOT / "julia" / "BGSim" / "export" / "runtime", harness_steps=2000)
        if not res.ok or res.fmu is None:
            raise SystemExit(f"the {veh} FMU build failed: {res.error}")
        report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
        shutil.copyfile(res.fmu, BUILD / f"{veh}_sim.fmu")
        info[veh] = {"method": report["method"], "dt": report["dt"], "substeps": report["substeps"],
                     "step": report["step"], "doStepMeanUs": res.step_time_mean_us, "doStepMaxUs": res.step_time_max_us,
                     "allocationsAfterInstantiate": res.allocations_after_instantiate, "compiler": res.compiler,
                     "ranges": report.get("tunables", {}).get("ranges")}
        print(f"wrote {BUILD / f'{veh}_sim.fmu'}: {report['method']} dt {report['dt']} s, doStep "
              f"{res.step_time_mean_us:.1f} us mean ({res.step_time_max_us:.1f} max), "
              f"{res.allocations_after_instantiate} allocations after instantiate")
    path.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    return info


def starts() -> dict:
    sys.path.insert(0, str(HERE / "src"))
    from carsim.terrain import Hills
    from carsim.track import Track

    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    out = {"racecar": [], "buggy": []}
    rc = design["racecar"]
    tr = Track()
    for label, s, d in TRACK_STARTS:
        x, y, yaw = tr.pose_at(s, d)
        out["racecar"].append({"label": label, "x0": round(x, 4), "y0": round(y, 4), "z0": rc["h_s"],
                               "yaw0": round(yaw, 6), "soc0": 0.9})
    bg = design["buggy"]
    corners = [(c["x"], c["y"]) for c in bg["corners"].values()]
    hills = Hills()
    for label, x, y, hdg in HILL_STARTS:
        yaw = math.radians(hdg)
        z0 = hills.start_height(x, y, yaw, corners, bg["h_s"])
        out["buggy"].append({"label": label, "x0": x, "y0": y, "z0": round(z0, 4), "yaw0": round(yaw, 6), "soc0": 0.9})
    for veh, recs in out.items():
        for rec in recs:
            for k, (lo, hi) in RANGES[veh].items():
                if not lo <= rec[k] <= hi:
                    raise SystemExit(f"{veh} start {rec['label']!r}: {k} = {rec[k]} is outside the FMU range [{lo}, {hi}]")
            print(f"{veh} start {rec['label']}: ({rec['x0']:.1f}, {rec['y0']:.1f}, {rec['z0']:.3f}) m, "
                  f"heading {math.degrees(rec['yaw0']):.1f} deg")
    BUILD.mkdir(exist_ok=True)
    (BUILD / "starts.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("vehicles", nargs="*", help="racecar, buggy (default both)")
    parser.add_argument("--skip-export", action="store_true", help="only write build/starts.json")
    parser.add_argument("--keep", type=Path, help="export into this folder instead of a temporary one")
    args = parser.parse_args()
    bad = [v for v in args.vehicles if v not in VEHICLES]
    if bad:
        parser.error(f"unknown vehicle(s) {bad}: {', '.join(VEHICLES)}")
    vehicles = args.vehicles or list(VEHICLES)
    if not args.skip_export:
        if args.keep:
            build(export(args.keep.resolve(), vehicles), vehicles)
        else:
            with tempfile.TemporaryDirectory(prefix="carsim-export-") as tmp:
                build(export(Path(tmp), vehicles), vehicles)
    starts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
