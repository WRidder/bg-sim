# /// script
# requires-python = ">=3.13"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Build step of the a109-sim host: export the FMU from bg-sim and write the start list.

    uv run build_fmu.py [--skip-export] [--keep DIR] [--method rk4] [--dt 0.00125]

1. ``julia --project=<repo>/julia/BGSim apps/a109-sim/export_fmu.jl <tmp>`` exports
   ``examples/a109/models/a109-sim`` with the host interface (the export markers as FMU inputs and
   outputs, the start state as FMU parameters), RK4 at a fixed internal step (the analysis would
   size the step at the default start, the hover at 15 m, where the landing gear carries nothing;
   on the ground the tyre contacts are the stiffest part of the model);
2. ``bgsim_server.fmu_build.build_fmu`` compiles it with the system C compiler (gcc), checks the
   hot path (no allocation after instantiate, no forbidden symbol) and times doStep;
3. the FMU is copied to ``build/a109_sim.fmu`` and ``build/build.json`` records the method, the
   internal step and the doStep cost of the harness;
4. ``build/starts.json``: the start conditions, from the design scripts of the example (the trims
   of ``examples/a109/design/heli_si.trim`` with ground effect and the smoothed switches, the same
   function the model's own start globals come from; the helicopter parked on its gear), placed
   and turned in the world, checked against the FMU's parameter ranges.

Nothing in ``build/`` is committed: run this once after cloning, and again when the model changes.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BUILD = HERE / "build"
DESIGN = ROOT / "examples" / "a109" / "design"
KT = 0.5144444444444445
NAMES = ("qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
         "a10", "b10", "Lrot0", "xi0")
# the wheels' contact points below the CG (examples/a109/design/build_model.py, GEAR) and the contact law
GEAR_Z = 1.32
GEAR_K, GEAR_XREF = 2.1e5, 0.04
# (label, kind, airspeed (kt), height of the CG (m), climb rate (m/s), heading (deg), north (m), east (m))
STARTS = [
    ("Helipad H, parked: rotor at 100 %, collective down", "ground", 0.0, None, 0.0, 0.0, 0.0, 0.0),
    ("Hover 3 m over the pad (in ground effect)", "trim", 0.0, 3.0, 0.0, 0.0, 0.0, 0.0),
    ("Hover 15 m over the pad (the model's start)", "trim", 0.0, 15.0, 0.0, 0.0, 0.0, 0.0),
    ("Short final: 30 kt, 30 m, 300 m south of the pad", "trim", 30.0, 30.0, -1.0, 0.0, -300.0, 0.0),
    ("Final approach: 40 kt, 60 m, 900 m south of the pad", "trim", 40.0, 60.0, -1.5, 0.0, -900.0, 0.0),
    ("Downwind: 60 kt, 100 m, heading south", "trim", 60.0, 100.0, 0.0, 180.0, 300.0, -700.0),
    ("Cruise 100 kt, 300 m, heading east", "trim", 100.0, 300.0, 0.0, 90.0, -1500.0, -800.0),
    ("Short final: 20 kt, 15 m, 150 m south of the pad", "trim", 20.0, 15.0, -0.5, 0.0, -150.0, 0.0),
]


def export(tmp: Path, method: str, dt: float) -> Path:
    cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(HERE / "export_fmu.jl"), str(tmp),
           f"--method={method}"] + ([f"--dt={dt}"] if dt > 0 else [])
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
    shutil.copyfile(res.fmu, BUILD / "a109_sim.fmu")
    info = {"method": report["method"], "dt": report["dt"], "substeps": report["substeps"],
            "step": report["step"], "doStepMeanUs": res.step_time_mean_us, "doStepMaxUs": res.step_time_max_us,
            "allocationsAfterInstantiate": res.allocations_after_instantiate, "compiler": res.compiler,
            "fmuBytes": (BUILD / "a109_sim.fmu").stat().st_size,
            "ranges": report.get("tunables", {}).get("ranges")}
    (BUILD / "build.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    budget = 100.0 * res.step_time_mean_us / (report["step"] * 1e6)
    print(f"wrote {BUILD / 'a109_sim.fmu'} ({info['fmuBytes'] // 1024} KB): {info['method']} dt {info['dt']} s "
          f"({info['substeps']} substeps per {report['step'] * 1e3:g} ms step), doStep {res.step_time_mean_us:.1f} us mean, "
          f"{res.step_time_max_us:.1f} us max ({budget:.2f} % of real time), {res.allocations_after_instantiate} "
          f"allocations after instantiate")
    return info


def _ranges() -> dict:
    """The FMU parameter ranges (export_fmu.jl's TUNABLES), parsed from the script."""
    text = (HERE / "export_fmu.jl").read_text(encoding="utf-8")
    return {m.group(1): (float(m.group(2)), float(m.group(3)))
            for m in re.finditer(r'"global:(\w+)" => \(([-0-9.e]+), ([-0-9.e]+)\)', text)}


def _trim(HS, h, v_kt, alt, vs, psi):
    """A steady straight flight at v_kt along the heading psi (rad), climbing at vs (m/s): the speed
    is reached by continuation from the hover (fsolve needs a nearby guess)."""
    import numpy as np

    guess = None
    for v in list(np.arange(0.0, v_kt, 10.0)) + [v_kt]:
        vh = float(v) * KT
        x, c, _ = HS.trim(h, vn=vh * math.cos(psi), ve=vh * math.sin(psi), vd=-vs, psi=psi, alt=alt, guess=guess)
        guess = np.r_[c, x[HS.ITH], x[HS.IPHI], x[HS.IA1], x[HS.IB1]]
    return x, c


def starts() -> list[dict]:
    sys.path.insert(0, str(DESIGN))
    import heli_si as HS
    import heli_sim as SM
    import numpy as np

    design = json.loads((DESIGN / "design.json").read_text(encoding="utf-8"))
    s = HS.si_data()
    h = HS.Heli(s, rpm_mode=1, ge=1, smooth=1.0)
    rig = SM.Rig(design["a109"]["rig"])
    J = s["J_DT"]
    ranges = _ranges()
    out = []
    for label, kind, v_kt, alt, vs, hdg, north, east in STARTS:
        psi = math.radians(hdg)
        if kind == "ground":
            # parked: level, the static deflection of a wheel under a third of the weight (the
            # host lets it settle before the flight starts), the collective down, the governor's
            # integrator at the engine torque of the flat-pitch rotor
            fn = s["m"] * HS.G0 / 3.0
            delta = (fn * math.sqrt(GEAR_XREF) / GEAR_K) ** (2.0 / 3.0)
            x = np.zeros(HS.NX)
            x[HS.IPSI] = psi
            x[HS.IZD] = -(GEAR_Z - delta)
            x[HS.IOM] = s["OMEGA0"]
            sticks = (0.0, 0.0, 0.0, 0.0)
            c = np.radians(rig.direct(*sticks))
            o = h.components(x, c)
            x[HS.IXI] = o["q_mr"] + s["P_LOSS"] / s["OMEGA0"] + s["N_TR"] * o["q_tr"]
            airborne, settle = False, 6.0
        else:
            x, c = _trim(HS, h, v_kt, alt, vs, psi)
            # with the SCAS on, the cyclic and pedals are centred: only the collective is the trim's
            sticks = (rig.sticks(*np.degrees(c))[0], 0.0, 0.0, 0.0)
            airborne, settle = True, 0.0
        x[HS.IXN], x[HS.IYE] = north, east
        pose, P = HS.bg_start(s, x)
        vals = [pose["qw"], pose["qx"], pose["qy"], pose["qz"], pose["px"], pose["py"], pose["pz"], *P,
                x[HS.IA1], x[HS.IB1], J * x[HS.IOM], x[HS.IXI]]
        values = {k: float(v) for k, v in zip(NAMES, vals)}
        for k, v in values.items():
            lo, hi = ranges[k]
            if not lo <= v <= hi:
                raise SystemExit(f"start {label!r}: {k} = {v} is outside the FMU's range [{lo}, {hi}]")
        controls = {"collective": float(sticks[0]), "cyclic_lon": 0.0, "cyclic_lat": 0.0, "pedals": 0.0, "scas": 1.0}
        out.append({"label": label, "values": values, "controls": controls, "airborne": airborne, "settle": settle})
        print(f"start {label}: collective {controls['collective']:.3f}, pitch {math.degrees(x[HS.ITH]):+.2f} deg, "
              f"bank {math.degrees(x[HS.IPHI]):+.2f} deg, at ({north:.0f} N, {east:.0f} E, {values['z0']:.2f} m)")
    # the hover at 15 m is the model's own start (its globals' defaults)
    st = design["sim"]["start"]
    ref = [st["pose"][k] for k in ("qw", "qx", "qy", "qz", "px", "py", "pz")] + st["P"] + [st["a1"], st["b1"]]
    got = [out[2]["values"][k] for k in NAMES[:15]]
    err = max(abs(a - b) for a, b in zip(ref, got))
    print(f"the 15 m hover start against the model's default start: max difference {err:.2e}")
    BUILD.mkdir(exist_ok=True)
    (BUILD / "starts.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skip-export", action="store_true", help="only write build/starts.json")
    parser.add_argument("--keep", type=Path, help="export into this folder instead of a temporary one")
    parser.add_argument("--method", default="rk4", help="the FMU's internal method (auto: the analysis picks)")
    parser.add_argument("--dt", type=float, default=0.00125, help="the internal step (s; 0: the analysis picks)")
    args = parser.parse_args()
    if not args.skip_export:
        if args.keep:
            build(export(args.keep.resolve(), args.method, args.dt))
        else:
            with tempfile.TemporaryDirectory(prefix="a109sim-export-") as tmp:
                build(export(Path(tmp), args.method, args.dt))
    starts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
