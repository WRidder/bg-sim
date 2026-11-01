# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "numba>=0.60", "cma>=3.3"]
# ///
"""Free motion optimisation of the pick and place: the highest pick rate that keeps the parcel.

    uv run examples/fanuc-pick/design/optimize_free.py [--cases box,sphere] [--stages A1,A2] [--workers 20]

`optimize.py` finds the fastest trajectory of each of the four fixed families (a speed scale and
a few shape numbers). This script lifts the restrictions one by one and optimises every freedom
with CMA-ES (a derivative-free evolution strategy, `cma`) on the same reduced model, each stage
warm-started from the one before:

* A0 (baseline): the best family of `optimize.py` (results.json `cases`), re-evaluated.
* A1 (+ tilt): families 3 and 4 with the waiter's tilt: the tool axis follows the specific force
  of the carton (gain, largest tilt, filter and fade times are variables, with the shape and the
  speed of `optimize.py`).
* A2 (+ free timing): family 5. Every segment has its own duration (lift, transfer, lower,
  approach and depart), the transfer starts and ends where the optimiser puts it inside the
  carry (lift and lower overlap it as far as it likes), the transfer profile is asymmetric (its
  own acceleration and deceleration shares), with the tilt; the yaw turns over the transfer.
* A3 (+ yaw spreading): the yaw turn gets its own window inside the carry.
* A4 (+ overlap): the vacuum switch-on before the contact (t_vac), the seal wait (T_seal), the
  vent wait (T_rel) and the approach and depart durations are variables too.

Objective: the cycle period T_cyc + T_ret (the empty joint move back to the approach start at
the robot's full rates), so picks per minute = 60 / (T_cyc + T_ret). Constraints:

* the LR-10iA/10 datasheet limits: `util_max <= 1` (joint ranges, rates, accelerations, jerks,
  wrist moment and inertia, payload), the arm being kinematic;
* clearance: every bottom corner of the (tilted) carton at least CLEAR above the support when
  the flange is more than R_CLEAR from the pick and the place, and never lower than half the
  flange height above the contact pose near them;
* holding: the reduced model's margin M_tot >= M_req (0.5; 0.3 for loose contents, and the
  loose cases are run again at 0.5 to see whether the free motion reaches it) and no drop;
* vent: the residual holding force at the depart start, 5 A_eff dp(tD), at most 0.2 m g
  (dp(tD) = dp(tE) exp(-T_rel / tau), tau = V_cup / (p_atm (G_rel + perm A_eff))).

The penalty function adds the constraint violations to the period; only points that meet every
constraint count as results. Writes the `ablation` section of design/results.json (the
`<case>-tilt-best` and `<case>-opt` models of build_models.py) and the ablation table of
README.md (between the `ablation` markers).
"""

from __future__ import annotations

import argparse
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

import fanuc as fz  # noqa: E402
import optimize as O  # noqa: E402
import params as P  # noqa: E402
import planner  # noqa: E402
import reduced as Rd  # noqa: E402

NL = "\n"
CLEAR, R_CLEAR = O.CLEAR, O.R_CLEAR
VENT = 0.2            # residual holding force at the depart start, fraction of the parcel weight
STAGES = ("A1", "A2", "A3", "A4")
STAGE_TITLES = {"A0": "baseline (best of families 1-4)", "A1": "+ tilt (waiter)", "A2": "+ free timing (family 5)",
                "A3": "+ yaw spreading", "A4": "+ vacuum/approach/depart overlap"}

#: variable -> (low, high); the stages pick a subset
VARS = {
    # families 3/4 (optimize.py's speed scale and shape)
    "s": (0.05, 1.0), "rho": (0.1, 1.5), "lam": (0.1, 1.0), "H_lift": (0.02, 0.15), "r_b": (0.0, 0.12),
    # tilt
    "tilt_gain": (0.0, 1.5), "tilt_max_deg": (3.0, 40.0), "T_tw": (0.02, 0.30), "T_tr": (0.03, 0.30),
    # family 5 timing
    "f5_Tl": (0.04, 0.6), "f5_Td": (0.04, 0.6), "f5_Tx": (0.15, 1.6), "f5_ox": (0.0, 0.4), "f5_ex": (0.0, 0.4),
    "f5_ax": (0.05, 0.9), "f5_dx": (0.05, 0.9), "f5_y0": (0.0, 0.9), "f5_y1": (0.1, 1.0),
    # overlap
    "T_seal": (0.0, 0.15), "t_vac": (0.0, 0.25), "T_rel": (0.002, 0.10), "f5_Ta": (0.06, 0.6), "f5_Tp": (0.06, 0.6),
}
FAM34 = ("s", "rho", "lam", "H_lift", "r_b", "T_seal")
TILT = ("tilt_gain", "tilt_max_deg", "T_tw", "T_tr")
F5 = ("lam", "H_lift", "f5_Tl", "f5_Td", "f5_Tx", "f5_ox", "f5_ex", "f5_ax", "f5_dx")
STAGE_VARS = {
    "A1": FAM34 + TILT,
    "A2": F5 + TILT,
    "A3": F5 + TILT + ("f5_y0", "f5_y1"),
    "A4": F5 + TILT + ("f5_y0", "f5_y1", "T_seal", "t_vac", "T_rel", "f5_Ta", "f5_Tp"),
}


def num(x: float, nd: int = 4) -> str:
    return O.num(x, nd)


class Free:
    """One load case: evaluation of a set of globals (plan, clearance, vent, reduced dynamics)."""

    def __init__(self, case: dict, m_req: float | None = None) -> None:
        self.case, self.kind = case, case["kind"]
        self.pr = O.Problem(case, 5)
        self.m_req = m_req

    def overrides(self, stage: str, fam: int, x: dict, fixed: dict) -> dict:
        """Globals (strings) of a stage point: the fixed values of the earlier stages, then x."""
        ov = dict(fixed)
        if stage == "A1":
            shape = {k: x[k] for k in ("rho", "lam", "H_lift", "r_b", "T_seal")}
            ov.update(O.trajectory_overrides(fam, x["s"], shape))
        else:
            ov["family"] = "5"
            for k in ("lam", "H_lift", "f5_Tl", "f5_Td", "f5_Tx", "f5_ox", "f5_ex", "f5_ax", "f5_dx"):
                ov[k] = num(x[k], 4)
            if stage == "A2":
                tc = x["f5_ox"] + x["f5_Tx"] + x["f5_ex"]
                ov["f5_y0"] = num(x["f5_ox"] / tc, 4)
                ov["f5_y1"] = num((x["f5_ox"] + x["f5_Tx"]) / tc, 4)
        for k in TILT + ("f5_y0", "f5_y1", "T_seal", "t_vac", "T_rel", "f5_Ta", "f5_Tp"):
            if k in x and k in STAGE_VARS[stage]:
                ov[k] = num(x[k], 4)
        return ov

    def evaluate(self, ov: dict, dynamics: bool = True) -> dict:
        g = self.pr.globals_of(ov)
        m_req = g["M_req"] if self.m_req is None else self.m_req
        ref = planner.reference(g)
        tl = ref["tl"]
        period = float(ref["T_cyc"] + ref["T_ret"])
        clear = clearance(g, ref)
        vent = vent_ratio(g, tl)
        out = {"ov": ov, "T_cyc": float(ref["T_cyc"]), "T_ret": float(ref["T_ret"]), "period": period,
               "util": float(ref["util_max"]), "clear": clear, "vent": vent, "M_req": m_req,
               "tilt_pk": float(np.max(ref["tilt"])), "M_tot": None, "dropped": None}
        pen = 20.0 * max(0.0, out["util"] - 1.0) + 20.0 * max(0.0, -clear - 1.0e-6) + 2.0 * max(0.0, vent - 1.0)
        plan_ok = pen == 0.0
        if plan_ok and dynamics:
            res = Rd.Pick(g, self.kind, ref).run()
            M = float(res["M_tot"]) if res.get("ok") else -9.0
            out.update(M_tot=M, dropped=bool(res.get("dropped", True)), margins=[float(m) for m in res["margins"]]
                       if res.get("margins") is not None else None)
            pen += 5.0 * max(0.0, m_req - M) + (2.0 if out["dropped"] else 0.0)
        else:
            pen += 1.0
        out["ok"] = bool(pen == 0.0)
        out["f"] = period + pen
        return out


def clearance(g: dict, ref: dict) -> float:
    """Smallest corner clearance minus its requirement while carried (>= 0 is feasible), m."""
    tl = ref["tl"]
    t = ref["t"]
    held = (ref["held"] > 0.5) & (t >= tl["tL"]) & (t <= tl["tE"])
    if not np.any(held):
        return 1.0
    psg = math.radians(g["psig_deg"])
    cs, sn = math.cos(psg), math.sin(psg)
    zc = -(g["h_stack"] + g["H_p"])
    corners = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            x, y = -g["gx"] + sx * g["L_p"] / 2, -g["gy"] + sy * g["W_p"] / 2
            corners.append((cs * x + sn * y, -sn * x + cs * y, zc))
    corners = np.array(corners).T                        # 3 x 4, gripper frame (z up)
    pos = ref["g"][4:7]
    worst = 1.0
    for k in np.nonzero(held)[0]:
        R = fz.rot_of_quat(ref["g"][0:4, k])
        hz = pos[2, k] - tl["zB"]                         # flange height above the contact pose
        cz = hz + float(np.min((R @ corners)[2] - zc))    # lowest corner above the support
        away = (math.hypot(pos[0, k] - tl["xB"], pos[1, k] - tl["yB"]) > R_CLEAR and
                math.hypot(pos[0, k] - tl["xE"], pos[1, k] - tl["yE"]) > R_CLEAR)
        need = CLEAR if away else min(CLEAR, 0.5 * hz)
        worst = min(worst, cz - need)
    return float(worst)


def vent_ratio(g: dict, tl: dict) -> float:
    """Residual holding force at the depart start over VENT m g (<= 1 is feasible)."""
    dp_e = g["dp_max"] * 0.95
    tau = g["V_cup"] / (P.P_ATM * (g["G_rel"] + g["perm"] * g["A_eff"]))
    f_res = 5 * g["A_eff"] * dp_e * math.exp(-(tl["tD"] - tl["tE"]) / tau)
    return float(f_res / (VENT * g["m_p"] * P.G0))


# ------------------------------------------------------------------ CMA-ES driver
_FREE: dict = {}


def _eval_job(args):
    case_id, m_req, stage, fam, xd, fixed = args
    key = (case_id, m_req)
    if key not in _FREE:
        _FREE[key] = Free(next(c for c in O.CASES if c["id"] == case_id), m_req)
    fr = _FREE[key]
    try:
        return fr.evaluate(fr.overrides(stage, fam, xd, fixed))
    except Exception as e:  # noqa: BLE001 (a failed point is a bad point)
        return {"f": 99.0, "ok": False, "error": repr(e)}


def to_unit(names, x):
    return np.array([(x[k] - VARS[k][0]) / (VARS[k][1] - VARS[k][0]) for k in names])


def from_unit(names, u):
    return {k: VARS[k][0] + float(np.clip(v, 0.0, 1.0)) * (VARS[k][1] - VARS[k][0]) for k, v in zip(names, u)}


def run_stage(ex, case: dict, m_req, stage: str, fam: int, x0: dict, fixed: dict, budget: int, sigma: float,
              log) -> dict:
    import cma

    names = STAGE_VARS[stage]
    x0 = {k: float(np.clip(x0[k], *VARS[k])) for k in names}
    es = cma.CMAEvolutionStrategy(to_unit(names, x0), sigma,
                                  {"bounds": [0.0, 1.0], "popsize": 20, "maxfevals": budget, "verbose": -9,
                                   "seed": 1234, "tolfun": 1e-5})
    best = None
    n = 0
    first = _eval_job((case["id"], m_req, stage, fam, x0, fixed))
    if first.get("ok"):
        best = {**first, "x": x0}
    while not es.stop():
        us = es.ask()
        xs = [from_unit(names, u) for u in us]
        res = list(ex.map(_eval_job, [(case["id"], m_req, stage, fam, x, fixed) for x in xs]))
        n += len(res)
        es.tell(us, [r["f"] for r in res])
        for x, r in zip(xs, res):
            if r.get("ok") and (best is None or r["period"] < best["period"]):
                best = {**r, "x": x}
        if es.countiter % 10 == 0:
            log(f"    {stage} fam {fam} it {es.countiter} evals {n} f_min {min(r['f'] for r in res):.4f} "
                f"best {best['period'] if best else None}")
    if best is not None:
        best, m = polish(ex, case, m_req, stage, fam, best, fixed)
        n += m
        log(f"    {stage} fam {fam} polished: period {best['period']:.4f}")
    return {"best": best, "evals": n}


#: the durations a family 5 time scale multiplies (A4 also the approach, depart and vacuum lead)
DUR5 = ("f5_Tl", "f5_Td", "f5_Tx", "f5_ox", "f5_ex")
DUR5_A4 = DUR5 + ("f5_Ta", "f5_Tp", "T_seal", "t_vac")


def scaled(stage: str, x: dict, k: float) -> dict:
    """The point x run faster by the factor k: the speed scale s times k (A1), or every family 5
    duration divided by k (the plan keeps its shape, every rate grows by k)."""
    if stage == "A1":
        return {**x, "s": min(x["s"] * k, VARS["s"][1])}
    keys = DUR5_A4 if stage == "A4" else DUR5
    return {**x, **{kk: x[kk] / k for kk in keys if kk in x}}


def polish(ex, case: dict, m_req, stage: str, fam: int, best: dict, fixed: dict) -> tuple[dict, int]:
    """Push the stage optimum to its constraint boundary along its own time scale: the CMA-ES
    penalty search stops a little inside the feasible set; bisect the largest k >= 1 that keeps
    every constraint (8 steps, 6 trial factors evaluated in parallel each)."""
    lo, hi = 1.0, 1.3
    x0 = best["x"]
    n = 0
    for _ in range(3):
        ks = list(np.linspace(lo, hi, 8)[1:-1]) + [hi]
        xs = [scaled(stage, x0, k) for k in ks]
        res = list(ex.map(_eval_job, [(case["id"], m_req, stage, fam, x, fixed) for x in xs]))
        n += len(res)
        good = [(k, x, r) for k, x, r in zip(ks, xs, res) if r.get("ok")]
        if not good:
            hi = ks[0]
            continue
        k, x, r = max(good, key=lambda g: g[0])
        if r["period"] < best["period"]:
            best = {**r, "x": x}
        nxt = [kk for kk in ks if kk > k]
        lo, hi = k, (nxt[0] if nxt else k * 1.15)
    return best, n


def baseline(case: dict, results: dict) -> dict | None:
    for c in results.get("cases", []):
        if c["id"] == case["id"] and c.get("best"):
            return c
    return None


def summary(r: dict) -> dict:
    keep = ("T_cyc", "T_ret", "period", "util", "clear", "vent", "M_tot", "dropped", "margins", "tilt_pk", "M_req")
    out = {k: (round(r[k], 4) if isinstance(r.get(k), float) else r.get(k)) for k in keep}
    out["picks_per_min"] = round(60.0 / r["period"], 2)
    out["globals"] = r["ov"]
    out["x"] = r.get("x")
    return out


def optimise_case(ex, case: dict, results: dict, m_req, stages, budget: int, log, old: dict | None = None) -> dict:
    """Run the stages; with ``old`` (an earlier result of the case) every stage restarts from its earlier
    optimum with a smaller step (the earlier optimum is the first point, so it is never lost)."""
    old = {s: {**r, "x": r.get("x") or x_from_ov(s, r["family"], r["globals"])}
           for s, r in (old or {}).get("stages", {}).items() if s != "A0" and r.get("ok")}
    base = baseline(case, results)
    fr = Free(case, m_req)
    out = {"id": case["id"], "title": case["title"], "kind": case["kind"], "M_req": m_req, "stages": {}}
    fixed0 = dict(case["overrides"])
    if base is None:
        log(f"{case['id']}: no feasible baseline in results.json; starting family 5 from the defaults")
        b_ov, bfam = {**fixed0}, 3
    else:
        b_ov, bfam = dict(base["best"]["globals"]), int(base["best"]["family"])
        r0 = fr.evaluate(b_ov)
        out["stages"]["A0"] = {**summary(r0), "family": bfam, "ok": r0["ok"]}
        log(f"{case['id']} A0 family {bfam}: period {r0['period']:.4f} (T_cyc {r0['T_cyc']:.4f} + T_ret "
            f"{r0['T_ret']:.4f}) M {r0['M_tot']} ok {r0['ok']}")
    prev = None
    # A1: tilt on families 3 and 4, from the baseline shape of that family (or the defaults)
    if "A1" in stages:
        best1 = None
        o1 = old.get("A1", {})
        if o1.get("x"):
            r = run_stage(ex, case, m_req, "A1", o1["family"], o1["x"], fixed0, budget, 0.08, log)
            best1 = {**r["best"], "family": o1["family"]} if r["best"] else None
        for fam in () if best1 else (3, 4):
            fres = (base or {}).get("families", {}).get(str(fam), {}) if base else {}
            shape = fres.get("shape") or {"rho": 0.6, "lam": 0.5, "H_lift": 0.05, "r_b": 0.06, "T_seal": 0.06}
            x0 = {"s": fres.get("s", 0.4), **shape, "tilt_gain": 0.3, "tilt_max_deg": 10.0, "T_tw": 0.20, "T_tr": 0.20}
            r = run_stage(ex, case, m_req, "A1", fam, x0, fixed0, budget, 0.2, log)
            if r["best"] and (best1 is None or r["best"]["period"] < best1["period"]):
                best1 = {**r["best"], "family": fam}
        if best1:
            out["stages"]["A1"] = {**summary(best1), "family": best1["family"], "ok": True}
            log(f"{case['id']} A1: period {best1['period']:.4f} family {best1['family']} M {best1['M_tot']:.3f}")
            prev = best1
    # A2..A4: family 5, warm-started from the timeline of the best plan so far
    x = None
    for stage in ("A2", "A3", "A4"):
        if stage not in stages:
            continue
        if x is None:
            src = prev["ov"] if prev else b_ov
            x = f5_start(fr, src)
        # before A4 the vacuum and vent timing and the approach/depart durations stay those of
        # the plan the stage starts from
        fixed = {**fixed0, **{k: num(x[k], 4) for k in ("T_seal", "t_vac", "T_rel", "f5_Ta", "f5_Tp")}}
        xs, sig = x, 0.15
        if old.get(stage, {}).get("x"):
            xs, sig = {**x, **old[stage]["x"]}, 0.08
            fixed = {**fixed0, **{k: num(xs[k], 4) for k in ("T_seal", "t_vac", "T_rel", "f5_Ta", "f5_Tp")}}
        r = run_stage(ex, case, m_req, stage, 5, xs, fixed, budget, sig, log)
        if r["best"]:
            b = r["best"]
            out["stages"][stage] = {**summary(b), "family": 5, "ok": True}
            log(f"{case['id']} {stage}: period {b['period']:.4f} (T_cyc {b['T_cyc']:.4f}) M {b['M_tot']:.3f} "
                f"util {b['util']:.3f} tilt {b['tilt_pk']:.1f} deg")
            x = {**x, **b["x"]}
            # carry the stage's yaw window into the next stage's start
            if stage == "A2":
                x["f5_y0"] = float(b["ov"]["f5_y0"])
                x["f5_y1"] = float(b["ov"]["f5_y1"])
    return out


def x_from_ov(stage: str, fam: int, ov: dict) -> dict:
    """The decision variables of a stage from its globals (results written without ``x``)."""
    g = {k: float(v) for k, v in ov.items() if k in VARS or k in ("kv", "ka", "v_c", "a_c")}
    if stage == "A1":
        if fam in (1, 4):
            s, rho = g["kv"], g["ka"] / g["kv"]
        else:
            s = g["v_c"] / O.CART_REF["v_c"]
            rho = g["a_c"] / (s * O.CART_REF["a_c"])
        g.update(s=s, rho=rho)
    return {k: v for k, v in g.items() if k in STAGE_VARS[stage]}


def f5_start(fr: Free, ov: dict) -> dict:
    """A family 5 start point that reproduces the timeline of a family 1-4 plan."""
    g = fr.pr.globals_of(ov)
    ref = planner.reference(g, t_end=0.0)
    tl = ref["tl"]
    ox = max(float(tl["t2s"] - tl["tL"]), 0.0)
    tx = float(tl["T2"])
    ex_ = max(float(tl["tE"] - tl["t2s"] - tl["T2"]), 0.0)
    tc = ox + tx + ex_
    x = {"lam": g["lam"], "H_lift": g["H_lift"], "f5_Tl": float(tl["T1"]), "f5_Td": float(tl["T3"]), "f5_Tx": tx,
         "f5_ox": ox, "f5_ex": ex_, "f5_ax": 0.4, "f5_dx": 0.4, "f5_y0": ox / tc, "f5_y1": (ox + tx) / tc,
         "tilt_gain": g["tilt_gain"] or 0.3, "tilt_max_deg": g["tilt_max_deg"] if g["tilt_gain"] else 10.0,
         "T_tw": g["T_tw"] if g["tilt_gain"] else 0.2, "T_tr": g["T_tr"] if g["tilt_gain"] else 0.2,
         "T_seal": g["T_seal"], "t_vac": g["t_vac"], "T_rel": g["T_rel"], "f5_Ta": float(tl["T_app"]),
         "f5_Tp": float(tl["T_dep"])}
    return x


def keep_best(old: dict, new: dict) -> dict:
    """Per stage the better feasible result of an earlier run and this one (a refine run restarts
    from the earlier optimum, but the gripper timing it holds fixed comes from the new chain)."""
    out = dict(old)
    for s, r in new.items():
        o = old.get(s)
        if not (o and o.get("ok")) or (r.get("ok") and r["period"] < o["period"]):
            out[s] = r
    return out


def ablation_table(data: dict) -> str:
    stages = ["A0", "A1", "A2", "A3", "A4"]
    lines = ["| Load case | " + " | ".join(f"{s} {STAGE_TITLES[s]}" for s in stages) + " |",
             "| --- |" + " --- |" * len(stages)]
    for c in data["cases"]:
        cells = [f"{c['title']} (M ≥ {c['M_req']})"]
        best = None
        for s in stages:
            r = c["stages"].get(s)
            # every stage has the freedoms of the ones before it: a stage that does not beat the
            # best so far adds nothing (the best so far stays the answer)
            if r and r.get("ok") and (best is None or r["period"] < best["period"]):
                best = r
                cells.append(f"**{r['picks_per_min']:.1f}/min** ({r['T_cyc']:.3f} + {r['T_ret']:.3f} s, "
                             f"M {r['M_tot']:.2f}, tilt {r['tilt_pk']:.0f}°, robot {100 * r['util']:.0f} %)")
            elif best is not None:
                cells.append("no gain")
            else:
                cells.append("not feasible" if r else "-")
        lines.append("| " + " | ".join(cells) + " |")
    return NL.join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    ap.add_argument("--cases", default="box,offset-com,sphere,cylinder")
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--budget", type=int, default=1600, help="CMA-ES evaluations per stage (and family)")
    ap.add_argument("--refine", action="store_true", help="restart every stage from its earlier optimum")
    ap.add_argument("--loose-strict", action="store_true", help="also run the loose cases at M_req = 0.5")
    ap.add_argument("--workers", type=int, default=min(20, os.cpu_count() or 1))
    ap.add_argument("--out", default=str(HERE / "results.json"))
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    results = json.loads(Path(a.out).read_text(encoding="utf-8"))
    stages = a.stages.split(",")
    t0 = time.time()
    log_path = Path(a.out).parent / "optimize_free.log"   # (not part of the example)

    def log(msg: str) -> None:
        line = f"[{time.time() - t0:7.0f} s] {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + NL)

    old = {c["id"] + ("@" + str(c["M_req"]) if c.get("strict") else ""): c for c in
           results.get("ablation", {}).get("cases", [])}
    runs = []
    for cid in a.cases.split(","):
        case = next(c for c in O.CASES if c["id"] == cid)
        runs.append((case, None))
        if a.loose_strict and case["kind"] != "box":
            runs.append((case, 0.5))
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for case, m_req in runs:
            key0 = case["id"] + ("@0.5" if m_req is not None else "")
            r = optimise_case(ex, case, results, m_req, stages, a.budget, log, old.get(key0) if a.refine else None)
            if r["M_req"] is None:
                r["M_req"] = O.Problem(case, 5).globals_of({})["M_req"]
            else:
                r["strict"] = True
            key = r["id"] + ("@" + str(r["M_req"]) if r.get("strict") else "")
            prev = old.get(key, {"stages": {}})
            r["stages"] = keep_best(prev.get("stages", {}), r["stages"])
            old[key] = r
            results["ablation"] = {"generated_by": "design/optimize_free.py", "vent": VENT, "clearance": CLEAR,
                                   "r_clear": R_CLEAR, "cases": list(old.values())}
            Path(a.out).write_text(json.dumps(results, indent=2) + NL, encoding="utf-8", newline=NL)
            log(f"wrote {a.out}")
    table = ablation_table(results["ablation"])
    print(table)
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    m0, m1 = "<!-- ablation:start -->", "<!-- ablation:end -->"
    if m0 in text and m1 in text:
        head, rest = text.split(m0, 1)
        _, tail = rest.split(m1, 1)
        path.write_text(head + m0 + NL + table + NL + m1 + tail, encoding="utf-8", newline=NL)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
