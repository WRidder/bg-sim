# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "numba>=0.60"]
# ///
"""Cycle-time optimisation of the pick and place: the fastest trajectory per load case and family.

    uv run examples/fanuc-pick/design/optimize.py [--quick] [--cases box,sphere] [--families 3,4]

For every load case (centred carton, offset centre of mass, loose sphere, loose cylinder) and
every trajectory family (1 joint PTP with stops, 2 Cartesian with stops, 3 Cartesian blended,
4 joint blended) it minimises the cycle time T_cyc subject to

* the LR-10iA/10 limits (joint ranges, rates, accelerations and jerks, wrist moment, wrist
  inertia and payload): `planner.reference(...)["util_max"] <= 1` (the arm is kinematic: it
  follows the plan exactly when the plan stays inside these limits);
* a clearance: the parcel bottom at least `CLEAR` above the support while the gripper is more
  than `R_CLEAR` (horizontally) away from the pick and the place;
* the holding margin of the reduced model (`reduced.py`, validated against bg-sim):
  `M_tot = min over zones (1 - peak U while carried) >= M_req` (0.5) and no drop.

Decision variables. The speed scale `s` (joint families: kv = s, ka = rho s; Cartesian families:
v_c, w_c = s times the reference speeds, a_c, al_c, j_c, jw_c = rho s times the reference
accelerations and jerks) and the shape: rho (acceleration against speed), lam (jerk phase share),
H_lift (lift height), r_b (blend distance, families 3 and 4) and T_seal (vacuum wait). For a
shape, the fastest feasible `s` follows from bisection (T_cyc falls with s, the margin with it);
the shapes are searched on a coarse grid and refined by a coordinate search.

Writes `design/results.json` (read by `build_models.py`: the optimum of every case becomes the
model `<case>-best`) and the results table of README.md (between the `results` markers).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_models as B  # noqa: E402
import params as P  # noqa: E402
import planner  # noqa: E402
import reduced as Rd  # noqa: E402

NL = "\n"
CLEAR = 0.02          # m  parcel bottom above the support away from the pick and the place
R_CLEAR = 0.05        # m  horizontal radius around the pick and the place where it may be lower
#: Cartesian reference limits at s = 1, rho = 1 (above what the joints allow: util caps s)
CART_REF = dict(v_c=2.5, w_c=6.0, a_c=20.0, al_c=40.0, j_c=400.0, jw_c=800.0)
SHAPE_KEYS = ("rho", "lam", "H_lift", "r_b", "T_seal")
GRID = dict(rho=(0.3, 0.6), lam=(0.5, 0.9), H_lift=(0.03, 0.07), r_b=(0.04, 0.08), T_seal=(0.02, 0.06))
STEP = dict(rho=0.15, lam=0.2, H_lift=0.02, r_b=0.02, T_seal=0.02)
BOUNDS = dict(rho=(0.1, 1.5), lam=(0.1, 1.0), H_lift=(0.02, 0.15), r_b=(0.0, 0.12), T_seal=(0.0, 0.15))
ROUND = dict(rho=3, lam=3, H_lift=3, r_b=3, T_seal=3)
S_MIN = 0.05

#: the load cases; the required margin is the model's global M_req (0.5, loose contents 0.3)
CASES = [
    dict(id="box", title="Carton 1.5 kg, centred CoM", model="pick-place-best", kind="box", overrides={}),
    dict(id="offset-com", title="Carton 1.5 kg, CoM offset (60, 30) mm, gripped over the CoM", model="offset-com-best",
         kind="box", overrides={"cx": "0.06", "cy": "0.03", "gx": "0.06", "gy": "0.03"}),
    dict(id="offset-centre", title="Carton 1.5 kg, CoM offset (60, 30) mm, gripped at the box centre", model=None,
         kind="box", overrides={"cx": "0.06", "cy": "0.03"}),
    dict(id="sphere", title="Carton 0.6 kg + loose ball 0.5 kg", model="loose-sphere-best", kind="sphere", overrides={}),
    dict(id="cylinder", title="Carton 0.6 kg + loose bottle 0.5 kg", model="loose-cylinder-best", kind="cylinder",
         overrides={}),
]


def num(x: float, nd: int = 4) -> str:
    v = round(float(x), nd)
    text = repr(v)
    return text[:-2] if text.endswith(".0") else text


def trajectory_overrides(fam: int, s: float, shape: dict) -> dict:
    """Globals of a family, speed scale and shape (strings, as the model tables hold them)."""
    ov = {"family": str(fam), "lam": num(shape["lam"], 3), "H_lift": num(shape["H_lift"], 3),
          "T_seal": num(shape["T_seal"], 3), "r_b": num(shape["r_b"] if fam in (3, 4) else 0.0, 3)}
    rho = shape["rho"]
    if fam in (1, 4):
        ov["kv"] = num(s, 3)
        ov["ka"] = num(rho * s, 3)
    else:
        for k in ("v_c", "w_c"):
            ov[k] = num(s * CART_REF[k], 3)
        for k in ("a_c", "al_c", "j_c", "jw_c"):
            ov[k] = num(rho * s * CART_REF[k], 3)
    return ov


class Problem:
    """One load case and family: cached plan and margin evaluations."""

    def __init__(self, case: dict, fam: int) -> None:
        self.case, self.fam, self.kind = case, fam, case["kind"]
        self.base = {**B.kind_overrides(self.kind), **case["overrides"]}
        self.rows = P.global_rows() + B.extra_rows(self.kind)
        self.n_plan = 0
        self.n_dyn = 0
        self._cache: dict = {}

    def globals_of(self, ov: dict) -> dict:
        return P.eval_globals(self.rows, {**self.base, **ov})

    def plan(self, s: float, shape: dict) -> dict:
        ov = trajectory_overrides(self.fam, s, shape)
        key = ("plan", tuple(sorted(ov.items())))
        if key in self._cache:
            return self._cache[key]
        g = self.globals_of(ov)
        ref = planner.reference(g)
        self.n_plan += 1
        tl = ref["tl"]
        pos = ref["g"][4:7]
        held = ref["held"] > 0.5
        dB = np.hypot(pos[0] - tl["xB"], pos[1] - tl["yB"])
        dE = np.hypot(pos[0] - tl["xE"], pos[1] - tl["yE"])
        away = held & (dB > R_CLEAR) & (dE > R_CLEAR)
        clear = float(np.min(pos[2][away] - tl["zB"])) if np.any(away) else 1.0
        out = {"ov": ov, "g": g, "ref": ref, "T_cyc": ref["T_cyc"], "util_max": ref["util_max"], "clear": clear,
               "plan_ok": bool(ref["util_max"] <= 1.0 and clear >= CLEAR)}
        self._cache[key] = out
        return out

    def dynamics(self, s: float, shape: dict) -> dict:
        pl = self.plan(s, shape)
        key = ("dyn", tuple(sorted(pl["ov"].items())))
        if key in self._cache:
            return self._cache[key]
        res = Rd.Pick(pl["g"], self.kind, pl["ref"]).run()
        self.n_dyn += 1
        M = float(res["M_tot"]) if res.get("ok") else -9.0
        dropped = bool(res.get("dropped", True))
        out = {**pl, "M_tot": M, "dropped": dropped, "margins": res.get("margins"),
               "ok": bool(pl["plan_ok"] and M >= pl["g"]["M_req"] and not dropped)}
        self._cache[key] = out
        return out

    def fastest(self, shape: dict) -> dict | None:
        """The largest speed scale of a shape that meets every constraint (bisection)."""
        if not self.plan(S_MIN, shape)["plan_ok"]:
            return None
        lo, hi = S_MIN, 1.0
        if not self.plan(hi, shape)["plan_ok"]:
            for _ in range(10):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if self.plan(mid, shape)["plan_ok"] else (lo, mid)
            hi = lo
        s_u = round(hi, 3)
        if self.dynamics(s_u, shape)["ok"]:
            return self.dynamics(s_u, shape) | {"s": s_u}
        lo, hi = S_MIN, s_u
        if not self.dynamics(lo, shape)["ok"]:
            return None
        for _ in range(7):
            mid = round(0.5 * (lo + hi), 3)
            if mid in (lo, hi):
                break
            lo, hi = (mid, hi) if self.dynamics(mid, shape)["ok"] else (lo, mid)
        return self.dynamics(lo, shape) | {"s": lo}

    def shape_keys(self) -> tuple[str, ...]:
        return SHAPE_KEYS if self.fam in (3, 4) else tuple(k for k in SHAPE_KEYS if k != "r_b")

    def optimise(self, quick: bool = False) -> dict:
        keys = self.shape_keys()
        best, best_shape = None, None
        default = {"r_b": 0.0, **{k: GRID[k][0] for k in SHAPE_KEYS}}
        grid = [GRID[k] for k in keys]
        if quick:
            grid = [(g[0],) for g in grid]
        for combo in itertools.product(*grid):
            shape = {**default, **dict(zip(keys, combo, strict=True))}
            r = self.fastest(shape)
            if r is not None and (best is None or r["T_cyc"] < best["T_cyc"]):
                best, best_shape = r, shape
        if best is None:
            # the best margin at the crawl (the default shape at S_MIN) tells why
            crawl = self.dynamics(S_MIN, default)
            return {"family": self.fam, "feasible": False, "crawl_M_tot": round(crawl["M_tot"], 4),
                    "crawl_dropped": crawl["dropped"], "n_plan": self.n_plan, "n_dyn": self.n_dyn}
        step = dict(STEP)
        for _ in range(1 if quick else 3):
            improved = False
            for k in keys:
                for sgn in (1.0, -1.0):
                    trial = dict(best_shape)
                    lo, hi = BOUNDS[k]
                    trial[k] = round(min(max(trial[k] + sgn * step[k], lo), hi), ROUND[k])
                    if trial[k] == best_shape[k]:
                        continue
                    r = self.fastest(trial)
                    if r is not None and r["T_cyc"] < best["T_cyc"] - 1e-4:
                        best, best_shape, improved = r, trial, True
                        break
            if not improved:
                step = {k: v / 2 for k, v in step.items()}
        return {
            "family": self.fam, "feasible": True, "T_cyc": round(best["T_cyc"], 4), "M_tot": round(best["M_tot"], 4),
            "margins": [round(m, 4) for m in best["margins"]], "util_max": round(best["util_max"], 4),
            "clear": round(best["clear"], 4), "s": best["s"], "shape": best_shape, "globals": best["ov"],
            "n_plan": self.n_plan, "n_dyn": self.n_dyn,
        }


def default_run(case: dict) -> dict:
    """The case at the default trajectory (family 3 at the default limits), for comparison."""
    pr = Problem(case, int(P.MOTION["family"]))
    g = pr.globals_of({})
    ref = planner.reference(g)
    res = Rd.Pick(g, case["kind"], ref).run()
    return {"T_cyc": round(ref["T_cyc"], 4), "M_tot": round(float(res["M_tot"]), 4), "dropped": bool(res["dropped"]),
            "util_max": round(ref["util_max"], 4)}


def _job(args: tuple) -> tuple[str, int, dict, float]:
    case_id, fam, quick = args
    case = next(c for c in CASES if c["id"] == case_id)
    t0 = time.time()
    out = Problem(case, fam).optimise(quick)
    return case_id, fam, out, time.time() - t0


def readme_table(data: dict) -> str:
    lines = ["| Load case | Default (family 3) | Family 1 joint PTP | Family 2 Cartesian | Family 3 Cartesian blended "
             "| Family 4 joint blended | Best |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for case in data["cases"]:
        d = case["default"]
        cells = [case["title"], f"{d['T_cyc']:.3f} s, " + ("drop" if d["dropped"] else f"M {d['M_tot']:+.2f}")]
        for fam in (1, 2, 3, 4):
            r = case["families"].get(str(fam))
            cells.append(f"{r['T_cyc']:.3f} s (M {r['M_tot']:.2f}, robot {100 * r['util_max']:.0f} %)"
                         if r and r.get("feasible") else "infeasible")
        b = case.get("best")
        cells.append(f"**{b['T_cyc']:.3f} s** (family {b['family']})" if b else
                     f"none: margin {max(r.get('crawl_M_tot', -9) for r in case['families'].values()):.2f} "
                     f"at 5 % speed (needs {case['M_req']})")
        lines.append("| " + " | ".join(cells) + " |")
    return NL.join(lines)


def write_readme(table: str) -> None:
    path = ROOT / "README.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    a, b = "<!-- results:start -->", "<!-- results:end -->"
    if a in text and b in text:
        head, rest = text.split(a, 1)
        _, tail = rest.split(b, 1)
        path.write_text(head + a + NL + table + NL + b + tail, encoding="utf-8", newline=NL)
        print("updated", path.relative_to(ROOT.parent.parent))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    ap.add_argument("--quick", action="store_true", help="one grid point and one refinement pass (a smoke test)")
    ap.add_argument("--cases", default=",".join(c["id"] for c in CASES))
    ap.add_argument("--families", default="1,2,3,4")
    ap.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 1))
    ap.add_argument("--out", default=str(HERE / "results.json"))
    a = ap.parse_args(argv)
    case_ids = a.cases.split(",")
    fams = [int(f) for f in a.families.split(",")]
    t0 = time.time()
    # compile the numba kernels once before the workers load them from the cache
    defaults = {c["id"]: default_run(c) for c in CASES if c["id"] in case_ids}
    print(f"defaults {defaults}  ({time.time() - t0:.1f} s)", flush=True)
    jobs = [(c, f, a.quick) for c in case_ids for f in fams]
    results: dict = {c: {} for c in case_ids}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for cid, fam, out, dt in ex.map(_job, jobs):
            results[cid][str(fam)] = out
            print(f"{cid:11s} family {fam}: " + (f"T_cyc {out['T_cyc']:.3f} s  M {out['M_tot']:.3f}  util "
                  f"{out['util_max']:.3f}  s {out['s']}  shape {out['shape']}" if out["feasible"] else "infeasible")
                  + f"  ({out['n_plan']} plans, {out['n_dyn']} dynamic runs, {dt:.0f} s)", flush=True)
    cases = []
    for c in CASES:
        if c["id"] not in case_ids:
            continue
        fr = results[c["id"]]
        feas = [r for r in fr.values() if r.get("feasible")]
        best = min(feas, key=lambda r: r["T_cyc"]) if feas else None
        m_req = Problem(c, 1).globals_of({})["M_req"]
        entry = {"id": c["id"], "title": c["title"], "model": c["model"], "kind": c["kind"], "M_req": m_req,
                 "overrides": c["overrides"], "default": defaults[c["id"]], "families": fr}
        if best:
            fam = best["family"]
            comment = (f"{c['title']}: the fastest trajectory of design/optimize.py, family {fam} "
                       f"({P.FAMILY_NAMES[fam]}), T_cyc {best['T_cyc']:.3f} s at a holding margin of "
                       f"{best['M_tot']:.2f} (required {m_req}) and {100 * best['util_max']:.0f} % of the robot limits.")
            entry["best"] = {"family": fam, "T_cyc": best["T_cyc"], "M_tot": best["M_tot"], "util_max": best["util_max"],
                             "comment": comment, "globals": {**c["overrides"], **best["globals"]}}
        cases.append(entry)
    data = {"generated_by": "design/optimize.py", "M_req": P.MOTION["M_req"], "clearance": CLEAR,
            "r_clear": R_CLEAR, "cart_ref": CART_REF, "quick": a.quick, "cases": cases}
    if Path(a.out).exists():   # keep the sections of optimize_free.py
        old = json.loads(Path(a.out).read_text(encoding="utf-8"))
        data.update({k: v for k, v in old.items() if k not in data})
    Path(a.out).write_text(json.dumps(data, indent=2) + NL, encoding="utf-8", newline=NL)
    print("wrote", a.out, f"({time.time() - t0:.0f} s)")
    if len(cases) == len(CASES) and not a.quick:
        table = readme_table(data)
        print(table)
        write_readme(table)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
