# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Realism screen (twin only) of the classical controller of the double-cart lab rig (plan C0).

    uv run examples/pendulum-double-cart-lab/design/screen.py all [--jobs 5] [--n 48]
    uv run examples/pendulum-double-cart-lab/design/screen.py ablation|budget|encoders|estimator|comp|mc|summary [--jobs 5]

The truth model is the twin of `lablib.setup` for a parameter set of `realism.json`: the link parts lumped
into the links, smooth Coulomb friction on both joints, on the carriage and at the motor, cable springs and
drag, the motor constants, commutation ripple and cogging (RK4, 8 substeps per 1 ms sample). The firmware
replica (`lablib.firmware`: the design's tables and gains, `design/design.json`) gets the sensors (14-bit
joint encoders with noise, the motor encoder through the belt) and the loop (a whole-sample delay and the
armature current lag L/R). Rates: filtered differences (`diff`, tau_f 2 ms, the baseline) or an EKF on the
nominal twin (`ekf`). Optional Coulomb compensation of the cart (`comp`, fraction of the nominal force).

Scenarios: `swingup` (hanging rest, the swing-up, catch at 4.0 s, run to 8 s) and `balance` (2 deg lean of
both links, the swing-up model's 0.45 N, 40 ms tip push at 2 s, run to 7 s). Pass ('ok'): the run finishes,
the cart stays off the end stops (|x| < 1.0 m) and every link is within 2 deg of upright over the last 2 s.

Parts:
- `ablation`: one effect at a time, then all together (nominal values), both estimators;
- `budget`: Coulomb friction per joint (the other joint and every other effect nominal), EKF and diff;
- `encoders`: the joint-encoder grade (12, 14, 16, 18 bit with typical noise), both estimators;
- `estimator`: the diff time constant tau_f and the EKF process noise;
- `comp`: the cart Coulomb compensation 0, 0.5, 1.0;
- `mc`: Monte Carlo over the ranges of realism.json (all effects, uniform draws), per estimator.
`all` runs every part and writes the summary `design/screen_results.json` (`summary` rewrites it from the raw
runs); raw runs go to `design/_screen/`.
"""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import design as dsg  # noqa: E402
import lablib as lb  # noqa: E402

ql = lb.ql
OUT = HERE / "_screen"
SUMMARY = HERE / "screen_results.json"
SUB = 8
SWING_END = 8.0
BAL = {"th0_deg": [2.0, 2.0], "t_push": 2.0, "amp": 0.45, "dur": 0.04, "t_end": 7.0}
TAIL = 2.0
DEV_OK = 2.0

_TAB = None


def tables():
    global _TAB
    if _TAB is None:
        _TAB = dsg.load_tables()
    return _TAB


def run_case(job: dict) -> dict:
    """One closed loop. job: p (realism params), effects, estimator, comp, scenario, seed, fw (Firmware overrides),
    ekf_q, tag."""
    tab = tables()
    t0 = time.time()
    rs = lb.setup(job["p"], job["effects"], job["estimator"], job.get("ekf_q"), job.get("comp", 0.0),
                  int(job.get("seed", 0)), SUB)
    kw = rs.fw_kw | job.get("fw", {})
    if job["scenario"] == "swingup":
        fw = lb.firmware(tab, **kw)
        x0 = ql.rest_state(rs.plant)
        ts, xs, us, ph, st = ql.closed_loop(rs.step, fw, x0, SWING_END, tau_act=rs.tau_act)
    else:
        fw = lb.firmware(tab, balance_only=True, **kw)
        x0 = dsg.balance_x0(BAL["th0_deg"])
        ts, xs, us, ph, st = ql.closed_loop(rs.step, fw, x0, BAL["t_end"], tau_act=rs.tau_act,
                                            force=dsg.push_force(BAL["t_push"], BAL["dur"], BAL["amp"]))
    fin = np.all(np.isfinite(xs), axis=1)
    k = int(np.max(np.where(fin)[0]))
    x, u = xs[: k + 1], us[: k + 1]
    dev = np.degrees(np.max(np.abs(x[:, 1:3]), axis=1))
    tail = ts[: k + 1] >= ts[-1] - TAIL
    cur = lb.current(rs.p, u, x[:, 3])
    p_x = float(np.max(np.abs(x[:, 0])))
    out = {
        "tag": job.get("tag"), "scenario": job["scenario"], "estimator": job["estimator"], "comp": job.get("comp", 0.0),
        "effects": list(job["effects"]), "seed": job.get("seed", 0), "seconds": round(time.time() - t0, 1),
        "finished": bool(fin.all()),
        "tail_dev_deg": float(np.max(dev[tail])) if fin.all() else math.inf,
        "tail_rms_deg": float(np.sqrt(np.mean(dev[tail] ** 2))) if fin.all() else math.inf,
        "tail_x": float(np.max(np.abs(x[tail, 0]))) if fin.all() else math.inf,
        "tail_u_rms": float(np.sqrt(np.mean(u[tail] ** 2))) if fin.all() else math.inf,
        "peak_u": float(np.max(np.abs(u))), "sat_frac": float(np.mean(np.abs(u) >= 0.999 * tab.u_max)),
        "peak_i": float(np.max(np.abs(cur))), "peak_x": p_x,
    }
    out["ok"] = bool(out["finished"] and p_x < rs.p["x_rail"] and out["tail_dev_deg"] < DEV_OK)
    return out


def run_jobs(jobs, n_jobs: int):
    if n_jobs <= 1:
        return [run_case(j) for j in jobs]
    with mp.get_context("spawn").Pool(n_jobs) as pool:
        return pool.map(run_case, jobs, chunksize=1)


def job(p, effects=lb.EFFECTS, est="ekf", sc="swingup", comp=1.0, tag="", **kw):
    return {"p": p, "effects": list(effects), "estimator": est, "scenario": sc, "comp": comp, "tag": tag} | kw


def both(p, effects=lb.EFFECTS, ests=("diff", "ekf"), comp=1.0, tag="", **kw):
    return [job(p, effects, e, s, comp, tag, **kw) for e in ests for s in ("swingup", "balance")]


def row(res, tag, est):
    a = next((r for r in res if r["tag"] == tag and r["estimator"] == est and r["scenario"] == "swingup"), None)
    b = next((r for r in res if r["tag"] == tag and r["estimator"] == est and r["scenario"] == "balance"), None)
    return a, b


def fmt(r):
    if r is None:
        return "-"
    return (f"{'ok' if r['ok'] else 'FAIL'} {r['tail_dev_deg']:.3f} deg" if r["finished"] else "diverges") + \
        (f", u {r['peak_u']:.1f} V, x {r['peak_x']:.2f} m" if r["finished"] else "")


def print_table(res, tags, ests=("diff", "ekf"), title=""):
    print(f"\n== {title}")
    print(f"{'case':44s} {'est':5s} | swing-up (tail dev, peak u, peak x)       | balance with push")
    for tag in tags:
        for e in ests:
            a, b = row(res, tag, e)
            if a is None and b is None:
                continue
            print(f"{tag:44s} {e:5s} | {fmt(a):42s} | {fmt(b)}")


def save(name, res):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- parts
def ablation(n_jobs):
    p = lb.nominal()
    sets = [("ideal", [])] + [(e, [e]) for e in lb.EFFECTS] + [("all", list(lb.EFFECTS)),
                                                              ("all, no compensation", list(lb.EFFECTS))]
    jobs = []
    for tag, eff in sets:
        jobs += both(p, eff, comp=1.0 if "fbase" in eff and "no comp" not in tag else 0.0, tag=tag)
    res = run_jobs(jobs, n_jobs)
    save("ablation", res)
    print_table(res, [t for t, _ in sets], title="ablation: one effect at a time (nominal realism), compensation 1.0 with fbase")
    return res


TC = [0.0, 1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2]


def budget(n_jobs):
    p = lb.nominal()
    jobs = []
    for j in (1, 2):
        for tc in TC:
            jobs += both(p | {f"tc_joint{j}": tc}, tag=f"tc_joint{j} = {tc:g}")
    # both joints at once
    for tc in TC:
        jobs += both(p | {"tc_joint1": tc, "tc_joint2": tc}, tag=f"tc_joint1 = tc_joint2 = {tc:g}")
    res = run_jobs(jobs, n_jobs)
    save("budget", res)
    tags = [f"tc_joint{j} = {tc:g}" for j in (1, 2) for tc in TC] + [f"tc_joint1 = tc_joint2 = {tc:g}" for tc in TC]
    print_table(res, tags, title="Coulomb friction budget per joint (all effects nominal, compensation 1.0)")
    return res


GRADES = {
    "12 bit, 0.08 deg (AS5600 class)": {"joint_bits": 12, "joint_noise": 0.08},
    "14 bit, 0.03 deg (AS5048 class, nominal)": {"joint_bits": 14, "joint_noise": 0.03},
    "14 bit, 0.08 deg (noisy AS5048)": {"joint_bits": 14, "joint_noise": 0.08},
    "16 bit, 0.005 deg": {"joint_bits": 16, "joint_noise": 0.005},
    "18 bit, 0.001 deg (optical/inductive)": {"joint_bits": 18, "joint_noise": 0.001},
}


def encoders(n_jobs):
    p = lb.nominal()
    jobs = []
    for tag, over in GRADES.items():
        jobs += both(p | over, tag=tag)
    res = run_jobs(jobs, n_jobs)
    save("encoders", res)
    print_table(res, list(GRADES), title="joint-encoder grade (all effects nominal, compensation 1.0)")
    return res


def estimator(n_jobs):
    p = lb.nominal()
    jobs = []
    tags = []
    for tf in (0.001, 0.002, 0.005, 0.01):
        tag = f"diff, tau_f = {tf * 1000:g} ms"
        tags.append(tag)
        jobs += both(p, ests=("diff",), tag=tag, fw={"tau_f": tf})
    for q in ((0.3, 3.0), (1.0, 10.0), (3.0, 30.0), (10.0, 100.0)):
        tag = f"ekf, q_acc = {q}"
        tags.append(tag)
        jobs += both(p, ests=("ekf",), tag=tag, ekf_q=list(q))
    res = run_jobs(jobs, n_jobs)
    save("estimator", res)
    print_table(res, tags, title="rate estimator (all effects nominal, compensation 1.0)")
    return res


def comp(n_jobs):
    p = lb.nominal()
    jobs = []
    tags = []
    for c in (0.0, 0.5, 1.0):
        tag = f"compensation {c:g}"
        tags.append(tag)
        jobs += both(p, comp=c, tag=tag)
        tag = f"compensation {c:g}, carriage Coulomb x2 (2 N)"
        tags.append(tag)
        jobs += both(p | {"tc_carriage": 2.0}, comp=c, tag=tag)
    res = run_jobs(jobs, n_jobs)
    save("comp", res)
    print_table(res, tags, title="Coulomb compensation of the cart (all effects nominal)")
    return res


def mc(n_jobs, n=48, seed0=2000):
    rng = np.random.default_rng(seed0)
    draws = [lb.sample(rng) for _ in range(n)]
    jobs = []
    for i, p in enumerate(draws):
        jobs += both(p, tag=f"mc{i}", seed=seed0 + i)
    res = run_jobs(jobs, n_jobs)
    for r, j in zip(res, jobs):
        r["p"] = j["p"]
    save("mc", res)
    summ = mc_summary(res)
    for k, v in summ.items():
        print(f"MC {k}: {v}")
    return res


def mc_summary(res):
    out = {}
    for e in ("diff", "ekf"):
        for s in ("swingup", "balance"):
            rr = [r for r in res if r["estimator"] == e and r["scenario"] == s]
            good = [r for r in rr if r["ok"]]
            d = {"ok": f"{len(good)}/{len(rr)}"}
            if good:
                tdev = [r["tail_dev_deg"] for r in good]
                d |= {"tail_dev_deg_median": round(float(np.median(tdev)), 3), "tail_dev_deg_max": round(max(tdev), 3),
                      "peak_u_max": round(max(r["peak_u"] for r in good), 2), "peak_i_max": round(max(r["peak_i"] for r in good), 2),
                      "peak_x_max": round(max(r["peak_x"] for r in good), 3)}
            bad = [r for r in rr if not r["ok"]]
            if bad:
                d["failures"] = [{"tag": r["tag"], "tail_dev_deg": round(r["tail_dev_deg"], 2) if r["finished"] else "diverged",
                                  "peak_x": round(r["peak_x"], 3)} for r in bad]
            out[f"{e} {s}"] = d
    return out


# ----------------------------------------------------------------------------- summary
EFFECT_TEXT = {
    "mass": "link parts (tube, hubs, encoder head and board, magnet, tip cap, cable) lumped into the links; masses, lengths, COM shifts and the cart spread",
    "drive": "motor constants (R, L, k_t, J_m), gear ratio, pulley radius, belt stiffness and damping",
    "fbase": "carriage Coulomb + viscous friction, motor Coulomb + viscous friction (compensated in volts by 'comp')",
    "fjoint": "Coulomb (tc_joint1/2) + viscous friction in both pendulum joints",
    "cable": "the encoder cable: a spring and drag across joint 1, drag along the rail",
    "sensor": "14-bit joint encoders with white noise (0.03 deg rms nominal), the motor encoder through the belt",
    "loop": "2 ms whole-sample delay + the armature lag L/R (0.33 ms)",
    "ripple": "commutation ripple (2 %) and cogging (0.2 N), 14 per motor revolution",
}

VERDICT = (
    "Feasible with margin. The unchanged classical controller of design.json (swing-up, catch, discrete LQR) passes "
    "with every effect at its nominal value and in all 48 Monte Carlo draws over the ranges of realism.json, provided "
    "the rates come from an EKF on the nominal model (or the joint encoders are 16-bit class). With the AS5048-class "
    "14-bit encoders, filtered differences are only marginal: the nominal rig passes (0.6 deg) but the voltage chatters "
    "at 9 V rms and peaks at the 24 V limit, and 12 of 48 Monte Carlo draws limit-cycle at 2-4 deg (all with joint noise of "
    "0.055 deg rms or more; the tail deviation follows the noise, Spearman 0.97). The joint Coulomb friction budget is about 1e-3 N m on joint 2 and about "
    "5e-3 N m on joint 1 (5-25x the assumed 2e-4 N m of small ball bearings), so the 0.35 m links take ordinary "
    "bearings, unlike the cart quad (5e-5 N m). The cart Coulomb compensation helps (tail 0.44 -> 0.13 deg) but is "
    "not required. Mass, drive, cable, loop delay and ripple are negligible."
)

RECOMMENDATIONS = [
    "Firmware: an EKF on the nominal realistic model with process noise q_acc = (1, 10) (cart, links); (0.3, 3) to "
    "(10, 100) all pass, (10, 100) raises the balance voltage to 20 V. Keep filtered differences only as the baseline "
    "(tau_f 5-10 ms if used: 0.2 deg but 21-22 V peaks).",
    "Joint encoders: 14-bit AS5048 class (0.03 deg rms) with the EKF; a 12-bit AS5600 or a noisy 14-bit part also "
    "passes with the EKF (0.3-0.4 deg) but fails with differences; 16 bit and up passes with either estimator.",
    "Joint bearings: budget 1e-3 N m Coulomb on joint 2 (the limit; 2e-3 is marginal at 1.7 deg) and 5e-3 N m on "
    "joint 1. Measure them with the free-swing decay of the free model.",
    "Cart: Coulomb compensation fc tanh(v / 2 eps) in volts with fc = the measured carriage + motor friction; 0.5 of "
    "it already gives most of the gain.",
    "Margins at the nominal rig with the EKF: swing-up peak 15.1 V and 5.8 A, push balance 16.3 V and 8.9 A, cart "
    "within 0.39 m of the 1.0 m rail end; the Monte Carlo worst case 18.2 V, 8.5 A balance current, 0.39 m.",
]


def _cell(r):
    if r is None:
        return None
    if not r["finished"]:
        return "diverges"
    return (f"{'ok' if r['ok'] else 'FAIL'} {r['tail_dev_deg']:.3f} deg, u {r['peak_u']:.1f} V, i {r['peak_i']:.1f} A, "
            f"x {r['peak_x']:.2f} m, tail u rms {r['tail_u_rms']:.1f} V")


def _table(res):
    tags = list(dict.fromkeys(r["tag"] for r in res))
    out = {}
    for tag in tags:
        d = {}
        for e in ("diff", "ekf"):
            a, b = row(res, tag, e)
            if a is not None or b is not None:
                d[e] = {"swingup": _cell(a), "balance": _cell(b)}
        out[tag] = d
    return out


def summary(n_jobs=None):
    ev = {}
    setups = {
        "ablation": "nominal realism, one effect at a time then all; compensation 1.0 when fbase is on",
        "budget": "all effects nominal, compensation 1.0, Coulomb friction (N m) of one joint or both",
        "encoders": "all effects nominal, compensation 1.0, joint-encoder resolution and noise",
        "estimator": "all effects nominal, compensation 1.0, diff time constant and EKF process noise",
        "comp": "all effects nominal, the cart Coulomb compensation fraction (EKF and diff)",
    }
    for name, setup in setups.items():
        f = OUT / f"{name}.json"
        if f.exists():
            ev[name] = {"setup": setup + "; per case: tail deviation over the last 2 s, peak u, peak i, peak |x|, tail u rms"} \
                | _table(json.loads(f.read_text(encoding="utf-8")))
    f = OUT / "mc.json"
    if f.exists():
        res = json.loads(f.read_text(encoding="utf-8"))
        n = len({r["tag"] for r in res})
        ev["monte_carlo"] = {"setup": f"{n} uniform draws over the ranges of realism.json (seeds 2000-{2000 + n - 1}), all effects, "
                                      "compensation 1.0; the diff failures all have joint noise of 0.055-0.079 deg rms (passes up to 0.070)"} \
            | mc_summary(res)
    doc = {
        "format": "bgsim.screen-results",
        "version": 1,
        "date": "2026-11-02",
        "description": (
            "Plan C0: twin-only realism screen of the double-cart lab rig's classical controller (design/screen.py; raw runs "
            "in design/_screen/, not committed). Truth: the Lagrangian twin of lablib.setup with the realism effects, RK4 with "
            "8 substeps per 1 ms sample. Firmware replica: 1 kHz, the design's tables, TVLQR and discrete LQR, the sensors, "
            "delay and current lag, rates from filtered differences ('diff', tau_f 2 ms, the baseline) or an EKF on the "
            "nominal twin ('ekf', q_acc (1, 10)). Scenarios: 'swingup' (hanging rest, catch at 4.0 s, to 8 s) and "
            "'balance' (2 deg lean per link, 0.45 N 40 ms tip push at 2 s, to 7 s)."),
        "criteria": {"tail_dev_deg_max": DEV_OK, "tail_window_s": TAIL, "x_max_m": 1.0,
                     "note": "ok = the run finishes, |x| stays below the rail end, every link within 2 deg of upright over the last 2 s"},
        "effects": EFFECT_TEXT,
        "verdict": VERDICT,
        "recommendations": RECOMMENDATIONS,
        "evidence": ev,
        "runs": {"commands": ["uv run examples/pendulum-double-cart-lab/design/screen.py all --jobs 5 --n 48"],
                 "wall_time_s": 243},
    }
    SUMMARY.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {SUMMARY}")
    return doc


PARTS = {"ablation": ablation, "budget": budget, "encoders": encoders, "estimator": estimator, "comp": comp, "mc": mc}


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    n_jobs = int(opt("--jobs", 5))
    cmd = argv[0] if argv else "all"
    t0 = time.time()
    if cmd == "all":
        for name, fn in PARTS.items():
            if name == "mc":
                fn(n_jobs, int(opt("--n", 48)))
            else:
                fn(n_jobs)
        summary()
    elif cmd == "summary":
        summary()
    elif cmd in PARTS:
        if cmd == "mc":
            mc(n_jobs, int(opt("--n", 48)))
        else:
            PARTS[cmd](n_jobs)
    else:
        raise SystemExit(__doc__)
    print(f"\n{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
