# /// script
# requires-python = ">=3.13"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Build the models of the web games: export each FMU from bg-sim and compile it to WebAssembly.

    uv run build_fmu.py [f16|missile|cessna|a109|racecar|buggy ...] [--starts] [--no-fmu] [--keep DIR]

With no target, all six. For each target:

1. ``julia --project=<repo>/julia/BGSim <repo>/examples/export_<...>.jl <tmp>`` exports the example's
   ``-sim`` model with the game's interface (the export markers as FMU inputs and outputs, the start
   state and the tunables as FMU parameters);
2. ``bgsim_server.fmu_build.build_fmu`` compiles it with the system C compiler (gcc), checks the
   hot path (no allocation after instantiate, no forbidden symbol) and zips the FMU;
3. the FMU is copied to ``build/<name>.fmu`` and ``build/build.json`` records, per target, the
   method, the internal step and the doStep cost of the harness;
4. ``build_wasm.py`` turns it into ``src/<game>/<module>.gen.ts``, which the game imports.

``--starts`` also writes the start lists ``src/<game>/starts.json`` of the F-16, the Cessna and the
A109 from the design scripts of the examples (the same trims the models' own start globals come
from), checked against the FMU's parameter ranges. They are committed: run it when a model's trim
or a start list below changes. ``--no-fmu`` skips steps 1 to 4 (only useful with ``--starts``).

Nothing in ``build/`` and no ``*.gen.ts`` is committed: run this once after cloning, and again when
a model changes.
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
EXAMPLES = ROOT / "examples"
BUILD = HERE / "build"

# target: (game folder under src/, export script, its arguments, the export folder under the output
# folder, the FMU's name in build/, the generated module)
TARGETS = {
    "f16": ("f16", "export_f16.jl", ["--no-reference"], "fmu", "f16_sim.fmu", "model.gen.ts"),
    "missile": ("f16", "export_aim9x.jl", [], "fmu", "aim9x_fmu.fmu", "missile.gen.ts"),
    "cessna": ("cessna", "export_cessna.jl", ["--no-reference"], "fmu", "cessna_sim.fmu", "model.gen.ts"),
    # RK4 at a fixed internal step: the analysis would size the step at the default start, the hover
    # at 15 m, where the landing gear carries nothing; on the ground the tyre contacts are the
    # stiffest part of the model
    "a109": ("a109", "export_a109.jl", ["--method=rk4", "--dt=0.00125"], "fmu", "a109_sim.fmu", "model.gen.ts"),
    "racecar": ("cars", "export_cars.jl", ["racecar", "--no-reference"], "racecar/fmu", "racecar_sim.fmu", "racecar.gen.ts"),
    "buggy": ("cars", "export_cars.jl", ["buggy", "--no-reference"], "buggy/fmu", "buggy_sim.fmu", "buggy.gen.ts"),
}


def export(target: str, out: Path) -> Path:
    _, script, args, sub, _, _ = TARGETS[target]
    cmd = ["julia", f"--project={ROOT / 'julia' / 'BGSim'}", str(EXAMPLES / script), str(out), *args]
    print("+", " ".join(cmd), flush=True)
    if subprocess.run(cmd, check=False).returncode != 0:
        raise SystemExit(f"the {target} export failed (see the Julia output above)")
    return out / sub


def build(target: str, export_dir: Path) -> None:
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from bgsim_server.fmu_build import build_fmu

    game, _, _, _, name, module = TARGETS[target]
    res = build_fmu(export_dir, runtime_dir=ROOT / "julia" / "BGSim" / "export" / "runtime", harness_steps=2000)
    if not res.ok or res.fmu is None:
        raise SystemExit(f"the {target} FMU build failed: {res.error}")
    report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
    BUILD.mkdir(exist_ok=True)
    fmu = BUILD / name
    shutil.copyfile(res.fmu, fmu)
    path = BUILD / "build.json"
    info = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    info[target] = {"method": report["method"], "dt": report["dt"], "substeps": report["substeps"],
                    "step": report["step"], "doStepMeanUs": res.step_time_mean_us, "doStepMaxUs": res.step_time_max_us,
                    "allocationsAfterInstantiate": res.allocations_after_instantiate, "compiler": res.compiler,
                    "fmuBytes": fmu.stat().st_size}
    path.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8", newline="\n")
    budget = 100.0 * res.step_time_mean_us / (report["step"] * 1e6)
    print(f"wrote {fmu} ({fmu.stat().st_size // 1024} KB): {report['method']} dt {report['dt']} s, doStep "
          f"{res.step_time_mean_us:.1f} us mean, {res.step_time_max_us:.1f} us max ({budget:.2f} % of real time), "
          f"{res.allocations_after_instantiate} allocations after instantiate", flush=True)
    cmd = ["uv", "run", str(HERE / "build_wasm.py"), game, str(fmu), module]
    print("+", " ".join(cmd), flush=True)
    if subprocess.run(cmd, check=False).returncode != 0:
        raise SystemExit(f"the {target} WebAssembly build failed")


def _ranges(script: str) -> dict:
    """The FMU parameter ranges (the export script's TUNABLES), parsed from the script."""
    text = (EXAMPLES / script).read_text(encoding="utf-8")
    return {m.group(1): (float(m.group(2)), float(m.group(3)))
            for m in re.finditer(r'"global:(\w+)" => \(([-0-9.e]+), ([-0-9.e]+)\)', text)}


def _write_starts(game: str, out) -> None:
    path = HERE / "src" / game / "starts.json"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(HERE)}: {len(out)} starts", flush=True)


# --- F-16: the in-flight trims. The runway and the final approach are in src/f16/flight.ts.

F16_XCG = 0.35
# (label, ft/s, ft)
F16_STARTS = [
    ("Cruise 500 ft/s, 10 000 ft", 500.0, 10000.0),
    ("Slow 300 ft/s, 10 000 ft", 300.0, 10000.0),
    ("Fast 700 ft/s, 5 000 ft", 700.0, 5000.0),
    ("Low and fast 900 ft/s, 2 000 ft", 900.0, 2000.0),
    ("High 600 ft/s, 20 000 ft", 600.0, 20000.0),
    ("Approach 350 ft/s, 2 000 ft", 350.0, 2000.0),
]


def starts_f16() -> None:
    sys.path.insert(0, str(EXAMPLES / "f16" / "design"))
    import simscen

    ranges = _ranges("export_f16.jl")
    out = []
    for label, vt, h in F16_STARTS:
        _, g = simscen.trim_globals(vt, h, F16_XCG)
        rec = {"label": label, "vt0": g["vt0"], "h0": g["h0"], "alpha0": g["alpha0"], "el0": g["el0"],
               "thtl0": g["thtl0"], "xcg": F16_XCG}
        for k in ("vt0", "h0", "alpha0", "el0", "thtl0", "xcg"):
            lo, hi = ranges[k]
            if not lo <= rec[k] <= hi:
                raise SystemExit(f"start {label!r}: {k} = {rec[k]} is outside the FMU's range [{lo}, {hi}]")
        out.append(rec)
        print(f"start {label}: alpha {rec['alpha0']:.2f} deg, stabilator {rec['el0']:.2f} deg, throttle {rec['thtl0']:.3f}")
    _write_starts("f16", out)


# --- Cessna: the runway equilibrium of design/perf.ground_state and trims of c172_lin.trim, placed
# and turned in the world.

FT, KT = 0.3048, 0.514444444
CESSNA_H_CG0 = 1.2546
CESSNA_X_AIM = 120.0   # m north: the aiming point on runway 36 (150 m past the threshold at -30 m)
# (label, kind, KCAS, height above the runway (ft), flaps (deg), flight-path angle (deg), heading (deg), north, west)
CESSNA_STARTS = [
    ("Runway 36, engine idle, flaps 10", "runway", None, 0.0, 10.0, 0.0, 0.0, 0.0, 0.0),
    ("Downwind (left traffic), 1000 ft, 90 KIAS", "level", 90.0, 1000.0, 0.0, 0.0, 180.0, 700.0, 900.0),
    ("Final runway 36, 2 nm, flaps 30, 65 KIAS", "descent", 65.0, 600.0, 30.0, -3.0, 0.0, None, 0.0),
    ("Short final, 300 ft, flaps 30, 65 KIAS", "descent", 65.0, 300.0, 30.0, -3.0, 0.0, None, 0.0),
    ("Cruise 4500 ft, 100 KIAS, heading east", "level", 100.0, 4500.0, 0.0, 0.0, 90.0, 1500.0, 0.0),
    ("Climb 76 KIAS, full throttle, 500 ft", "climb", 76.0, 500.0, 0.0, None, 0.0, 1500.0, 0.0),
]
CESSNA_NAMES = ("qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
                "hrot0", "map0", "xad0", "flap0", "qn0", "ql0", "qr0")


def starts_cessna() -> None:
    sys.path.insert(0, str(EXAMPLES / "cessna" / "design"))
    import c172_lin as L
    import c172_ref as M
    import demo as Dm
    import design as Ds
    import numpy as np
    import perf as P

    ranges = _ranges("export_cessna.jl")
    out = []
    for label, kind, kcas, h_ft, flap, gamma_deg, hdg, north, west in CESSNA_STARTS:
        if kind == "runway":
            x, g = Dm.runway_start(flap)
            c = M.Controls(flaps=flap / 10.0)
            airborne = False
        else:
            h = h_ft * FT + CESSNA_H_CG0
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
                north = CESSNA_X_AIM - h_ft * FT / math.tan(-gamma_deg * math.pi / 180.0)
            psi = hdg * math.pi / 180.0
            qz = np.array([math.cos(-psi / 2), 0.0, 0.0, math.sin(-psi / 2)])
            x[M.I_Q:M.I_Q + 4] = M.quat_mul(qz, x[M.I_Q:M.I_Q + 4])
            x[M.I_POS:M.I_POS + 2] = (north, west)
            for k in range(3):
                x[M.I_STRUT + k] = L.penetration(x, M.GEARS[k])
            airborne = True
        st = Ds.state_starts(x, c)
        values = dict(zip(CESSNA_NAMES,
                          st["pose"] + st["P"] + [st["h_rotor"], st["MAP"], st["xad"], st["flap"]] + st["strut"]))
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
    _write_starts("cessna", out)


# --- A109: the trims of design/heli_si.trim with ground effect and the smoothed switches, and the
# helicopter parked on its gear, placed and turned in the world.

A109_NAMES = ("qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
              "a10", "b10", "Lrot0", "xi0")
# the wheels' contact points below the CG (examples/a109/design/build_model.py, GEAR) and the contact law
A109_GEAR_Z = 1.32
A109_GEAR_K, A109_GEAR_XREF = 2.1e5, 0.04
# (label, kind, airspeed (kt), height of the CG (m), climb rate (m/s), heading (deg), north (m), east (m))
A109_STARTS = [
    ("Helipad H, parked: rotor at 100 %, collective down", "ground", 0.0, None, 0.0, 0.0, 0.0, 0.0),
    ("Hover 3 m over the pad (in ground effect)", "trim", 0.0, 3.0, 0.0, 0.0, 0.0, 0.0),
    ("Hover 15 m over the pad (the model's start)", "trim", 0.0, 15.0, 0.0, 0.0, 0.0, 0.0),
    ("Short final: 30 kt, 30 m, 300 m south of the pad", "trim", 30.0, 30.0, -1.0, 0.0, -300.0, 0.0),
    ("Final approach: 40 kt, 60 m, 900 m south of the pad", "trim", 40.0, 60.0, -1.5, 0.0, -900.0, 0.0),
    ("Downwind: 60 kt, 100 m, heading south", "trim", 60.0, 100.0, 0.0, 180.0, 300.0, -700.0),
    ("Cruise 100 kt, 300 m, heading east", "trim", 100.0, 300.0, 0.0, 90.0, -1500.0, -800.0),
    ("Short final: 20 kt, 15 m, 150 m south of the pad", "trim", 20.0, 15.0, -0.5, 0.0, -150.0, 0.0),
]


def _a109_trim(HS, h, v_kt, alt, vs, psi):
    """A steady straight flight at v_kt along the heading psi (rad), climbing at vs (m/s): the speed
    is reached by continuation from the hover (fsolve needs a nearby guess)."""
    import numpy as np

    guess = None
    for v in list(np.arange(0.0, v_kt, 10.0)) + [v_kt]:
        vh = float(v) * 0.5144444444444445
        x, c, _ = HS.trim(h, vn=vh * math.cos(psi), ve=vh * math.sin(psi), vd=-vs, psi=psi, alt=alt, guess=guess)
        guess = np.r_[c, x[HS.ITH], x[HS.IPHI], x[HS.IA1], x[HS.IB1]]
    return x, c


def starts_a109() -> None:
    design_dir = EXAMPLES / "a109" / "design"
    sys.path.insert(0, str(design_dir))
    import heli_si as HS
    import heli_sim as SM
    import numpy as np

    design = json.loads((design_dir / "design.json").read_text(encoding="utf-8"))
    s = HS.si_data()
    h = HS.Heli(s, rpm_mode=1, ge=1, smooth=1.0)
    rig = SM.Rig(design["a109"]["rig"])
    J = s["J_DT"]
    ranges = _ranges("export_a109.jl")
    out = []
    for label, kind, v_kt, alt, vs, hdg, north, east in A109_STARTS:
        psi = math.radians(hdg)
        if kind == "ground":
            # parked: level, the static deflection of a wheel under a third of the weight (the
            # game lets it settle before the flight starts), the collective down, the governor's
            # integrator at the engine torque of the flat-pitch rotor
            fn = s["m"] * HS.G0 / 3.0
            delta = (fn * math.sqrt(A109_GEAR_XREF) / A109_GEAR_K) ** (2.0 / 3.0)
            x = np.zeros(HS.NX)
            x[HS.IPSI] = psi
            x[HS.IZD] = -(A109_GEAR_Z - delta)
            x[HS.IOM] = s["OMEGA0"]
            sticks = (0.0, 0.0, 0.0, 0.0)
            c = np.radians(rig.direct(*sticks))
            o = h.components(x, c)
            x[HS.IXI] = o["q_mr"] + s["P_LOSS"] / s["OMEGA0"] + s["N_TR"] * o["q_tr"]
            airborne, settle = False, 6.0
        else:
            x, c = _a109_trim(HS, h, v_kt, alt, vs, psi)
            # with the SCAS on, the cyclic and pedals are centred: only the collective is the trim's
            sticks = (rig.sticks(*np.degrees(c))[0], 0.0, 0.0, 0.0)
            airborne, settle = True, 0.0
        x[HS.IXN], x[HS.IYE] = north, east
        pose, P = HS.bg_start(s, x)
        vals = [pose["qw"], pose["qx"], pose["qy"], pose["qz"], pose["px"], pose["py"], pose["pz"], *P,
                x[HS.IA1], x[HS.IB1], J * x[HS.IOM], x[HS.IXI]]
        values = {k: float(v) for k, v in zip(A109_NAMES, vals)}
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
    got = [out[2]["values"][k] for k in A109_NAMES[:15]]
    err = max(abs(a - b) for a, b in zip(ref, got))
    print(f"the 15 m hover start against the model's default start: max difference {err:.2e}")
    _write_starts("a109", out)


STARTS = {"f16": starts_f16, "cessna": starts_cessna, "a109": starts_a109}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("targets", nargs="*", help=f"{', '.join(TARGETS)} (default all)")
    parser.add_argument("--starts", action="store_true", help="also write src/<game>/starts.json (f16, cessna, a109)")
    parser.add_argument("--no-fmu", action="store_true", help="do not export and build (with --starts)")
    parser.add_argument("--keep", type=Path, help="export into this folder instead of a temporary one")
    args = parser.parse_args()
    bad = [t for t in args.targets if t not in TARGETS]
    if bad:
        parser.error(f"unknown target(s) {bad}: {', '.join(TARGETS)}")
    targets = args.targets or list(TARGETS)
    if not args.no_fmu:
        for target in targets:
            if args.keep:
                build(target, export(target, args.keep.resolve() / target))
            else:
                with tempfile.TemporaryDirectory(prefix=f"webgames-{target}-") as tmp:
                    build(target, export(target, Path(tmp)))
    if args.starts:
        for target in targets:
            if target in STARTS:
                STARTS[target]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
