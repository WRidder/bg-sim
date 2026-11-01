# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Phase B, step 1: twin-only feasibility screen of the quad-pendulum controllers on a realistic rig.

    uv run examples/quad-pendulum/design/screen.py ablation [cart,cart_short,rotary] [--jobs 4]
    uv run examples/quad-pendulum/design/screen.py redesign <variant>      # see REDESIGN
    uv run examples/quad-pendulum/design/screen.py mc [variants] [--n 40] [--jobs 4]

The truth model is the Lagrangian twin (`quadlib.Plant`) of the rig with the non-idealities of
`realism.json` (`quadlib.realistic_rig`): encoder boards, magnets and cables lumped into the links,
smooth Coulomb friction on the base and every pendulum joint, cable springs and dampers, motor ripple
and cogging (RK4 with 8 substeps per 1 ms sample, to follow the cart's ripple). The firmware replica gets
the sensors (14-bit joint encoders with noise, the base encoder) and the loop (a whole-sample delay and a
first-order current loop). Rates: filtered backward differences (baseline) or an EKF on the designer's
model of the realistic rig (`quadlib.design_rig`: no Coulomb, no ripple).

- `ablation`: the controllers one effect at a time, then all together (nominal values), swing-up and
  balance-with-push, each with both estimators;
- `redesign`: a controller designed on the realistic design model (longer swing-up, torque margin, lower
  gains); writes `design/_screen/design_<variant>.json`;
- `mc`: Monte Carlo over the ranges of realism.json (all effects, uniform draws), per controller and
  estimator.

Results go to `design/_screen/*.json` (not in git) and the summary to `design/screen_results.json`.
"""

from __future__ import annotations

import dataclasses
import json
import math
import multiprocessing as mp
import sys
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import quadlib as ql  # noqa: E402

OUT = HERE / "_screen"
SUMMARY = HERE / "screen_results.json"
EFFECTS = list(ql.EFFECTS)
SUB = 8   # RK4 substeps per sample of the truth model


# ----------------------------------------------------------------------------- controllers
def design_file(variant: str) -> Path:
    p = HERE / f"design_{variant}.json"
    return p if p.is_file() else OUT / f"design_{variant}.json"


@lru_cache(maxsize=None)
def load_design(variant: str) -> dict:
    return json.loads(design_file(variant).read_text(encoding="utf-8"))


def base_rig(kind: str) -> ql.Rig:
    import design
    return design.CFG[kind]["rig"]


# ----------------------------------------------------------------------------- truth model
@lru_cache(maxsize=64)
def _plant(rig_json: str) -> tuple:
    rig = ql.Rig(**json.loads(rig_json))
    plant = ql.Plant(rig)
    step, _ = plant.steps(sub=SUB)
    return plant, step


def plant_of(rig: ql.Rig):
    return _plant(json.dumps(dataclasses.asdict(rig), sort_keys=True))


@lru_cache(maxsize=8)
def _ekf(rig_json: str, q_acc: tuple, r_meas: tuple) -> ql.EKF:
    return ql.EKF(ql.Plant(ql.Rig(**json.loads(rig_json))), q_acc, r_meas)


def ekf_of(rig: ql.Rig, q_acc, r_meas) -> ql.EKF:
    return _ekf(json.dumps(dataclasses.asdict(rig), sort_keys=True), tuple(q_acc), tuple(r_meas))


def run_case(job: dict) -> dict:
    """One closed-loop run. job: variant, kind, p (realism params), effects, estimator, scenario, seed."""
    kind, variant = job["kind"], job["variant"]
    dz = load_design(variant)
    rig0 = base_rig(kind)
    comp = job.get("comp", 0.0)
    rs = ql.realistic_setup(rig0, job["p"], job["effects"], job["estimator"], job.get("ekf_q"), comp,
                            int(job.get("seed", 0)), SUB, make_plant=plant_of, make_ekf=ekf_of)
    plant, step, tau_act = rs.plant, rs.step, rs.tau_act
    fw = ql.firmware_from_design(dz, **(rs.fw_kw | job.get("fw", {})))
    travel = dz.get("travel", dz["s_max"])
    t0 = time.time()
    if job["scenario"] == "swingup":
        x0 = ql.rest_state(plant)
        t_end = dz["t_on"] + dz["t_s"] + 4.0
        ts, xs, us, ph, st = ql.closed_loop(step, fw, x0, t_end, tau_act=tau_act)
    else:
        fwb = dataclasses.replace(fw, balance_only=True)
        x0 = np.zeros(rig0.nx)
        x0[1:1 + rig0.n] = np.radians(dz["balance"]["th0"])
        pu = dz["balance"]["push"]
        amp, pt0, pdur = pu["amplitude"], pu["t_start"], pu["duration"]
        ts, xs, us, ph, st = ql.closed_loop(step, fwb, x0, dz["balance"]["t_end"], tau_act=tau_act,
                                            force=lambda t: amp if pt0 <= t < pt0 + pdur else 0.0)
    n = rig0.n
    fin = np.all(np.isfinite(xs), axis=1)
    k_last = int(np.max(np.where(fin)[0]))
    dev = np.degrees(np.max(np.abs(xs[: k_last + 1, 1:1 + n]), axis=1))
    tail = ts[: k_last + 1] >= ts[-1] - 2.0
    out = {
        "variant": variant, "kind": kind, "effects": list(job["effects"]), "estimator": job["estimator"],
        "scenario": job["scenario"], "seed": job.get("seed", 0), "tag": job.get("tag"), "comp": comp,
        "fw": job.get("fw", {}),
        "seconds": round(time.time() - t0, 1),
        "finished": bool(fin.all()),
        "caught": bool(st.get("latched", 0) > 0.5),
        "t_catch": float(st.get("t_catch", math.nan)),
        "tail_dev_deg": float(np.max(dev[tail])) if fin.all() else math.inf,
        "tail_rms_dev_deg": float(np.sqrt(np.mean(dev[tail] ** 2))) if fin.all() else math.inf,
        "peak_u_frac": float(np.max(np.abs(us[: k_last + 1])) / dz["u_max"]),
        "sat_frac": float(np.mean(np.abs(us[: k_last + 1]) >= 0.999 * dz["u_max"])),
        "peak_s": float(np.max(np.abs(xs[: k_last + 1, 0]))),
        "tail_s": float(np.max(np.abs(xs[: k_last + 1, 0][tail]))) if fin.all() else math.inf,
        "tail_u_rms": float(np.sqrt(np.mean(us[: k_last + 1][tail] ** 2))) if fin.all() else math.inf,
        "travel": travel,
    }
    out["ok"] = bool(out["finished"] and (out["caught"] or job["scenario"] == "balance")
                     and out["tail_dev_deg"] < 2.0 and out["peak_s"] <= travel)
    return out


def run_jobs(jobs, n_jobs: int):
    if n_jobs <= 1:
        return [run_case(j) for j in jobs]
    with mp.get_context("spawn").Pool(n_jobs) as pool:
        return pool.map(run_case, jobs, chunksize=1)


# ----------------------------------------------------------------------------- commands
def ablation(variants, n_jobs, comp=0.0, fw=None, name="", pover=None, ekf_q=None, sets=None):
    jobs = []
    sets = sets or ([[]] + [[e] for e in EFFECTS] + [EFFECTS])
    for v in variants:
        kind = load_design(v)["kind"]
        p = ql.realism_nominal(kind) | (pover or {})
        for eff in sets:
            for est in ("diff", "ekf"):
                for sc in ("swingup", "balance"):
                    jobs.append({"variant": v, "kind": kind, "p": p, "effects": eff, "estimator": est, "scenario": sc,
                                 "tag": "+".join(eff) or "ideal", "comp": comp, "fw": fw or {}, "ekf_q": ekf_q})
    t0 = time.time()
    res = run_jobs(jobs, n_jobs)
    OUT.mkdir(exist_ok=True)
    (OUT / f"ablation_{'_'.join(variants)}{name}.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(f"{len(jobs)} runs in {time.time() - t0:.0f} s")
    for v in variants:
        print(f"\n== {v}")
        print(f"{'effects':38s} {'est':5s} | swing-up: ok  catch   tail dev  peak u  sat   peak s | balance: ok tail dev  u rms")
        for eff in sets:
            tag = "+".join(eff) or "ideal"
            for est in ("diff", "ekf"):
                if not any(r["variant"] == v and r["tag"] == tag and r["estimator"] == est for r in res):
                    continue
                a = next(r for r in res if r["variant"] == v and r["tag"] == tag and r["estimator"] == est and r["scenario"] == "swingup")
                b = next(r for r in res if r["variant"] == v and r["tag"] == tag and r["estimator"] == est and r["scenario"] == "balance")
                print(f"{tag:38s} {est:5s} | {str(a['ok']):5s} {a['t_catch']:6.2f} {a['tail_dev_deg']:9.3f} {a['peak_u_frac']:6.2f} "
                      f"{a['sat_frac']:5.3f} {a['peak_s']:7.3f} | {str(b['ok']):5s} {b['tail_dev_deg']:8.3f} {b['tail_u_rms']:6.3f}")
    return res


def mc(variants, n, n_jobs, estimators=("diff", "ekf"), scenarios=("swingup", "balance"), seed0=1000, comp=0.0,
       fw=None, name="", pover=None, ekf_q=None):
    jobs = []
    for v in variants:
        kind = load_design(v)["kind"]
        rng = np.random.default_rng(seed0)
        draws = [ql.sample_realism(kind, rng) | (pover or {}) for _ in range(n)]
        for i, p in enumerate(draws):
            for est in estimators:
                for sc in scenarios:
                    jobs.append({"variant": v, "kind": kind, "p": p, "effects": EFFECTS, "estimator": est,
                                 "scenario": sc, "seed": seed0 + i, "tag": f"mc{i}", "comp": comp, "fw": fw or {},
                                 "ekf_q": ekf_q})
    t0 = time.time()
    res = run_jobs(jobs, n_jobs)
    for r, j in zip(res, jobs):
        r["p"] = j["p"]
    OUT.mkdir(exist_ok=True)
    (OUT / f"mc_{'_'.join(variants)}{name}.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(f"{len(jobs)} runs in {time.time() - t0:.0f} s")
    for v in variants:
        for est in estimators:
            for sc in scenarios:
                rr = [r for r in res if r["variant"] == v and r["estimator"] == est and r["scenario"] == sc]
                ok = sum(r["ok"] for r in rr)
                good = [r for r in rr if r["ok"]]
                print(f"{v:14s} {est:5s} {sc:8s}: {ok}/{len(rr)} ok"
                      + (f"; tail dev median {np.median([r['tail_dev_deg'] for r in good]):.3f} deg, "
                         f"max {max(r['tail_dev_deg'] for r in good):.3f}; peak u {max(r['peak_u_frac'] for r in good):.2f}; "
                         f"peak s {max(r['peak_s'] for r in good):.3f}" if good else ""))
    return res


# ----------------------------------------------------------------------------- redesign
# Controllers designed on the designer's model of the realistic rig (`design_rig` of the nominal
# realistic rig): longer swing-up, a torque margin (|u| <= u_frac u_max planned), lower gains.
REDESIGN = {
    # lower balance gains (LQR weights / 100) and a softer tracking weight; the screen shows it is worse
    "cart_real": {"base": "cart", "t_s": 5.0, "u_frac": 0.65, "qdiag": [1.0, 4.0, 4.0, 4.0, 4.0, 0.1, 0.05, 0.05, 0.05, 0.05],
                  "r": None, "qdiag_tv": None, "r_tv": 1.0},
    "rotary_real": {"base": "rotary", "t_s": 7.0, "u_frac": 0.7, "swings": 4, "s_amp": 0.8,
                    "solves": [[140, 1.0], [280, 1.0]], "r": 30.0, "r_tv": 10.0, "tau_f": 0.005},
}


def redesign(variant: str, overrides: dict | None = None):
    import design
    spec = dict(REDESIGN[variant]) | (overrides or {})
    base = spec.pop("base")
    cfg = dict(design.CFG[base])
    R0 = cfg["rig"]
    kind = R0.kind
    dr = ql.design_rig(ql.realistic_rig(R0, ql.realism_nominal(kind)))
    u_frac = spec.pop("u_frac", 1.0)
    for k, v in spec.items():
        if v is not None:
            cfg[k] = v
    cfg["u_lim"] = min(cfg["u_lim"], u_frac * R0.u_max)
    cfg["slew_lim"] = min(cfg["slew_lim"], u_frac * R0.slew)
    plant = ql.Plant(dr)
    k_lqr, p_lqr, poles, open_poles = ql.dlqr(plant, cfg["qdiag"], cfg["r"])
    print(f"[{variant}] open-loop poles {np.round(np.sort(open_poles.real), 2)}; LQR max gain {np.max(np.abs(k_lqr)):.0f}")
    OUT.mkdir(exist_ok=True)
    traj = design.trajectory(plant, cfg, OUT / f"_traj_{variant}.npz", False)
    fw, info = design.firmware(plant, cfg, traj, k_lqr, p_lqr)
    print(f"[{variant}] TVLQR roll-out end error {info['rollout_end_err']:.2e}, max nominal u {info['max_u_nominal']:.2f}, "
          f"max gain {info['max_gain']:.0f}")
    dz0 = load_design(base)
    dz = {
        "kind": kind, "variant": variant, "rig": "realistic", "travel": cfg["travel"], "u_max": R0.u_max, "slew": R0.slew,
        "s_max": R0.s_max, "t_on": cfg["t_on"], "t_s": cfg["t_s"], "dt_tab": cfg["dt_tab"], "catch_tol": cfg["catch_tol"],
        "res_s": cfg["res_s"], "res_q": cfg["res_q"], "tau_f": cfg["tau_f"], "k_lqr": k_lqr.tolist(), "p_lqr": p_lqr.tolist(),
        "tab_x": fw.tab_x.tolist(), "tab_u": fw.tab_u.tolist(), "tab_k": fw.tab_k.tolist(),
        "tab_v": fw.tab_v.tolist() if fw.tab_v is not None else None, "ff_form": cfg["ff_form"],
        "balance": dz0["balance"], "cfg": {k: cfg[k] for k in ("t_s", "u_lim", "s_lim", "slew_lim", "qdiag", "r", "qdiag_tv", "r_tv", "solves")},
        "collocation": {"log": traj["log"], "seconds": traj["seconds"]}, "tvlqr": info,
        "max_gain_lqr": float(np.max(np.abs(k_lqr))),
    }
    (OUT / f"design_{variant}.json").write_text(json.dumps(dz) + "\n", encoding="utf-8")
    load_design.cache_clear()
    print(f"wrote {OUT / f'design_{variant}.json'}")
    return dz


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    n_jobs = int(opt("--jobs", 4))
    comp = float(opt("--comp", 0.0))
    fw = json.loads(opt("--fw", "{}"))
    pover = json.loads(opt("--p", "{}"))
    ekf_q = json.loads(opt("--ekf-q", "null"))
    sets = json.loads(opt("--sets", "null"))
    est = tuple(opt("--est", "diff,ekf").split(","))
    name = opt("--name", "")
    cmd = argv[0]
    vals = {opt(k) for k in ("--jobs", "--comp", "--fw", "--name", "--n", "--p", "--ekf-q", "--sets", "--est")}
    rest = [a for a in argv[1:] if not a.startswith("--") and a not in vals]
    if cmd == "ablation":
        ablation(rest[0].split(",") if rest else ["cart", "cart_short", "rotary"], n_jobs, comp, fw, name, pover, ekf_q, sets)
    elif cmd == "redesign":
        redesign(rest[0], json.loads(rest[1]) if len(rest) > 1 else None)
    elif cmd == "mc":
        n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 40
        mc(rest[0].split(",") if rest else ["cart", "cart_short", "rotary"], n, n_jobs, estimators=est, comp=comp, fw=fw,
           name=name, pover=pover, ekf_q=ekf_q)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
