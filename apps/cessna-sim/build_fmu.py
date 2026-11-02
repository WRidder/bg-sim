# /// script
# requires-python = ">=3.13"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Build step of the cessna-sim host: export the FMU from bg-sim and write the start list.

    uv run build_fmu.py [--skip-export] [--keep DIR]

1. ``julia --project=<repo>/julia/BGSim <repo>/examples/export_cessna.jl <tmp> --no-reference``
   exports ``examples/cessna/models/cessna-sim`` with the host interface (the export markers as
   FMU inputs and outputs, the start state as FMU parameters);
2. ``bgsim_server.fmu_build.build_fmu`` compiles it with the system C compiler (gcc), checks the
   hot path (no allocation after instantiate, no forbidden symbol) and zips the FMU;
3. the FMU is copied to ``build/cessna_sim.fmu`` and ``build/build.json`` records the method, the
   internal step and the doStep cost of the harness;
4. ``build/starts.json``: the start conditions, from the design scripts of the example (the
   runway equilibrium of ``examples/cessna/design/perf.ground_state`` and trims of
   ``c172_lin.trim``, the same functions the model's own start globals come from), placed and
   turned in the world, checked against the FMU's parameter ranges.

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
DESIGN = ROOT / "examples" / "cessna" / "design"
FT, KT = 0.3048, 0.514444444
H_CG0 = 1.2546
X_AIM = 120.0          # m north: the aiming point on runway 36 (150 m past the threshold at -30 m)
# (label, kind, KCAS, height above the runway (ft), flaps (deg), flight-path angle (deg), heading (deg), north, west)
STARTS = [
    ("Runway 36, engine idle, flaps 10", "runway", None, 0.0, 10.0, 0.0, 0.0, 0.0, 0.0),
    ("Downwind (left traffic), 1000 ft, 90 KIAS", "level", 90.0, 1000.0, 0.0, 0.0, 180.0, 700.0, 900.0),
    ("Final runway 36, 2 nm, flaps 30, 65 KIAS", "descent", 65.0, 600.0, 30.0, -3.0, 0.0, None, 0.0),
    ("Short final, 300 ft, flaps 30, 65 KIAS", "descent", 65.0, 300.0, 30.0, -3.0, 0.0, None, 0.0),
    ("Cruise 4500 ft, 100 KIAS, heading east", "level", 100.0, 4500.0, 0.0, 0.0, 90.0, 1500.0, 0.0),
    ("Climb 76 KIAS, full throttle, 500 ft", "climb", 76.0, 500.0, 0.0, None, 0.0, 1500.0, 0.0),
]
NAMES = ("qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
         "hrot0", "map0", "xad0", "flap0", "qn0", "ql0", "qr0")


def export(tmp: Path) -> Path:
    cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(ROOT / "examples" / "export_cessna.jl"),
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
    shutil.copyfile(res.fmu, BUILD / "cessna_sim.fmu")
    info = {"method": report["method"], "dt": report["dt"], "substeps": report["substeps"],
            "step": report["step"], "doStepMeanUs": res.step_time_mean_us, "doStepMaxUs": res.step_time_max_us,
            "allocationsAfterInstantiate": res.allocations_after_instantiate, "compiler": res.compiler,
            "ranges": report.get("tunables", {}).get("ranges")}
    (BUILD / "build.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {BUILD / 'cessna_sim.fmu'}: {info['method']} dt {info['dt']} s, doStep "
          f"{res.step_time_mean_us:.1f} us mean, {res.allocations_after_instantiate} allocations after instantiate")
    return info


def _ranges() -> dict:
    """The FMU parameter ranges (examples/export_cessna.jl's TUNABLES), parsed from the script."""
    import re

    text = (ROOT / "examples" / "export_cessna.jl").read_text(encoding="utf-8")
    return {m.group(1): (float(m.group(2)), float(m.group(3)))
            for m in re.finditer(r'"global:(\w+)" => \(([-0-9.e]+), ([-0-9.e]+)\)', text)}


def starts() -> list[dict]:
    sys.path.insert(0, str(DESIGN))
    import c172_lin as L
    import c172_ref as M
    import demo as Dm
    import design as Ds
    import numpy as np
    import perf as P

    ranges = _ranges()
    out = []
    for label, kind, kcas, h_ft, flap, gamma_deg, hdg, north, west in STARTS:
        if kind == "runway":
            x, g = Dm.runway_start(flap)
            c = M.Controls(flaps=flap / 10.0)
            airborne = False
        else:
            h = h_ft * FT + H_CG0
            mix = P.best_power_mixture(h)
            if kind == "climb":
                x, c, info = P.trim_cas(kcas * KT, h, throttle=1.0, mixture=mix, guess=[0.08, 0, -0.2, 0, 0, 0.05, 240.0])
            else:
                for guess in ([0.03, 0, -0.2, 0, 0, 0.6, 230.0], [0.05, 0, -0.3, 0, 0, 0.4, 210.0],
                              [0.0, 0, -0.5, 0, 0, 0.3, 200.0], [0.08, 0, 0.0, 0, 0, 0.5, 220.0]):
                    x, c, info = P.trim_cas(kcas * KT, h, gamma=gamma_deg * math.pi / 180.0, flap_deg=flap,
                                            mixture=mix, guess=guess)
                    if info["ok"]:
                        break
            if not info["ok"]:
                raise SystemExit(f"start {label!r}: the trim failed ({info['residual']:.2e})")
            if north is None:   # on the glide path to the aiming point
                north = X_AIM - h_ft * FT / math.tan(-gamma_deg * math.pi / 180.0)
            psi = hdg * math.pi / 180.0
            qz = np.array([math.cos(-psi / 2), 0.0, 0.0, math.sin(-psi / 2)])
            x[M.I_Q:M.I_Q + 4] = M.quat_mul(qz, x[M.I_Q:M.I_Q + 4])
            x[M.I_POS:M.I_POS + 2] = (north, west)
            for k in range(3):
                x[M.I_STRUT + k] = L.penetration(x, M.GEARS[k])
            airborne = True
        st = Ds.state_starts(x, c)
        values = dict(zip(NAMES, st["pose"] + st["P"] + [st["h_rotor"], st["MAP"], st["xad"], st["flap"]] + st["strut"]))
        for k, v in values.items():
            lo, hi = ranges[k]
            if not lo <= v <= hi:
                raise SystemExit(f"start {label!r}: {k} = {v} is outside the FMU's range [{lo}, {hi}]")
        ctl = st["controls"]
        controls = {"throttle": ctl["throttle"], "mixture": ctl["mixture"], "flaps": ctl["flaps"],
                    "trim": max(-1.0, min(1.0, ctl["yoke_pitch"] + ctl["trim"]))}
        out.append({"label": label, "values": values, "controls": controls, "airborne": airborne})
        print(f"start {label}: throttle {controls['throttle']:.3f}, trim {controls['trim']:+.3f}, "
              f"mixture {controls['mixture']:.2f}, at ({values['x0']:.0f}, {values['y0']:.0f}, {values['z0']:.1f}) m")
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
            with tempfile.TemporaryDirectory(prefix="cessnasim-export-") as tmp:
                build(export(Path(tmp)))
    starts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
