# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Design study of the suction-gripper example: how fast can the parcel be moved?

Analytic part (``sizing.py``, no simulation):

* the operating vacuum where the generator curve meets the leak demand of the six cups, per
  parcel porosity and generator size, and the generator capacity a porosity needs;
* the quasi-static holding limit ``a_max`` (largest steady path acceleration with every cup's
  utilisation ``U <= 1/S``) per yaw, tilt gain and porosity;
* the pick-up time (vacuum build-up after the valve opens) per generator and porosity.

Simulation part (the real model ``models/transfer.bgmodel.json`` through BGSim, run by
``run_model.jl`` in parallel Julia processes; every job only overrides global parameters, so
each process compiles the plant once):

* validation: per-cup forces of a slow move against the quasi-static statics, the simulated
  operating vacuum against the analytic one, the simulated pick-up against the lumped ODE;
* dynamic amplification vs jerk: equal peak acceleration, trapezoid and S-curves of growing
  jerk time;
* the fastest safe move: per profile x yaw x tilt x porosity, the shortest transfer time T with
  no cup losing its seal and ``max U <= 1/S`` during the transfer (grid, then bisection);
* the equal-time comparison of the four profiles and the supply topologies.

Writes ``design/results.json`` (every number the docs and ``expected.json`` quote) and
``design/min_move_time.svg``.

    uv run examples/suction-gripper/design/design.py [--procs 6] [--quick] [--reuse]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE))
import params as P  # noqa: E402
import sizing as S  # noqa: E402

PORO = {"sealed": P.PERM["sealed"], "cardboard": P.PERM["cardboard"], "porous": P.PERM["porous"]}
PROFILES = {1: "trapezoid", 2: "S-curve", 3: "polynomial 3-4-5", 4: "cycloidal"}
YAWS = (0, 45, 90)
TILTS = (0.0, 1.0)
LAM = P.MOTION["lam"]
T_X0 = None  # transfer start, from the model


# ------------------------------------------------------------------ simulation jobs
def model_globals() -> dict:
    doc = json.loads((HERE.parent / "models" / "transfer.bgmodel.json").read_text(encoding="utf-8"))
    return {p["name"]: p["value"] for p in doc["parameters"]}


def run_jobs(jobs: list[dict], procs: int, work: Path, tag: str) -> dict:
    """Run the jobs in `procs` Julia processes; returns {id: result dict}."""
    work.mkdir(parents=True, exist_ok=True)
    out_dir = work / f"out_{tag}"
    out_dir.mkdir(exist_ok=True)
    todo = [j for j in jobs if not (out_dir / f"{j['id']}.json").exists()]
    chunks = [todo[k::procs] for k in range(procs)]
    running = []
    t0 = time.time()
    for k, chunk in enumerate(chunks):
        if not chunk:
            continue
        jf = work / f"jobs_{tag}_{k}.json"
        jf.write_text(json.dumps(chunk), encoding="utf-8")
        log = open(work / f"log_{tag}_{k}.txt", "w", encoding="utf-8")
        cmd = ["julia", "--project=julia/BGSim", "examples/suction-gripper/design/run_model.jl", str(jf), str(out_dir)]
        running.append((subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT), log))
    for proc, log in running:
        proc.wait()
        log.close()
    if todo:
        print(f"  {tag}: {len(todo)} runs in {time.time() - t0:.0f} s ({procs} processes)", flush=True)
    res = {}
    for j in jobs:
        f = out_dir / f"{j['id']}.json"
        res[j["id"]] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"status": "missing"}
    return res


def sig(r: dict, name: str) -> np.ndarray:
    return np.asarray(r["signals"][name], dtype=float)


CUP_SIGNALS = [f"Cup{n}/{q}" for n in range(1, 7) for q in ("U", "T", "F_lat", "dp", "sealed")]
BASE_SIGNALS = CUP_SIGNALS + ["Monitor/n_lost", "Monitor/held", "Monitor/sway_y", "Monitor/sep", "Path/ax", "Path/theta",
                              "Gen/dp", "Gen/Q"]


def transfer_metrics(r: dict, t_x0: float, t_move: float) -> dict:
    """max U and lost cups in the transfer window [t_x0, t_x0 + T + 0.3]."""
    if r.get("status") != "done":
        return {"ok": False, "maxU": math.inf, "lost": 6, "status": r.get("status")}
    t = sig(r, "time")
    w = (t >= t_x0 - 0.02) & (t <= t_x0 + t_move + 0.3)
    u = max(float(sig(r, f"Cup{n}/U")[w].max()) for n in range(1, 7))
    lost = float(sig(r, "Monitor/n_lost")[t <= t_x0 + t_move + 0.3].max())
    held = float(sig(r, "Monitor/held")[t <= t_x0 + t_move + 0.3].min())
    return {"ok": True, "maxU": u, "lost": lost, "held": held}


def job(jid: str, glob: dict, t_end: float, signals=None, points=None) -> dict:
    j = {"id": jid, "model": "transfer", "t_end": round(t_end, 4), "globals": glob,
         "signals": signals or BASE_SIGNALS}
    if points:
        j["points"] = points
    return j


# ------------------------------------------------------------------ analytic part
def analytic() -> dict:
    out = {}
    q_list = [20, 30, 45, 60, 90]  # l/min
    ov = {}
    for name, perm in PORO.items():
        ov[name] = []
        for q in q_list:
            o = S.operating_vacuum(perm, q_max=q / 6e4)
            ov[name].append({"Q_lpm": q, "dp_cup": float(o["dp_cups"].mean()), "dp_man": float(o["dp_man"]),
                             "Q": float(o["Q"])})
    out["operating_vacuum"] = ov
    # quasi-static holding limit at the operating vacuum of the default generator (60 l/min)
    amax = {}
    for name, perm in PORO.items():
        dp = float(S.operating_vacuum(perm)["dp_cups"].mean())
        amax[name] = {"dp": dp, "U_static": float(S.quasi_static(0.0, dp=dp)["U"].max())}
        for yaw in YAWS:
            for k in TILTS:
                amax[name][f"yaw{yaw}_tilt{k:g}"] = S.a_max(psi=math.radians(yaw), k_tilt=k, dp=dp)
    out["a_max"] = amax
    # generator capacity needed for a target acceleration with S = 2 (yaw 0, no tilt)
    need = {}
    for a_target in (1.0, 2.0, 3.0):
        need[f"a{a_target:g}"] = {}
        # vacuum needed: bisection on dp
        lo, hi = 1e3, 6e4
        if S.a_max(dp=hi) < a_target:
            dp_need = math.inf
        else:
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if S.a_max(dp=mid) < a_target else (lo, mid)
            dp_need = hi
        need[f"a{a_target:g}"]["dp_needed"] = dp_need
        for name, perm in PORO.items():
            if not math.isfinite(dp_need) or dp_need >= P.SUPPLY["dp_max"] * 0.999:
                need[f"a{a_target:g}"][name] = math.inf
                continue
            lo, hi = 1e-6, 1e-1
            for _ in range(60):
                mid = math.sqrt(lo * hi)
                dpc = float(S.operating_vacuum(perm, q_max=mid)["dp_cups"].min())
                lo, hi = (mid, hi) if dpc < dp_need else (lo, mid)
            need[f"a{a_target:g}"][name] = hi * 6e4  # l/min
    out["generator_needed_lpm"] = need
    # pick-up time: time until the cup vacuum carries the lift (U_lift <= 1/S) per generator / porosity
    pick = {}
    m = P.PARCEL["m_p"]
    dp_lift = P.SAFETY * m * (P.G0 + P.MOTION["a_lift"]) / (len(P.CUPS) * P.CUP["A_eff"])
    pick["dp_lift_SF"] = dp_lift
    for name, perm in PORO.items():
        pick[name] = []
        for q in q_list:
            pu = S.pickup(perm, q_max=q / 6e4, t_end=1.5)
            above = np.nonzero(pu["dp"] >= dp_lift)[0]
            t90 = pu["t"][np.nonzero(pu["dp"] >= 0.9 * pu["dp"][-1])[0][0]]
            pick[name].append({"Q_lpm": q, "t_lift_ready": float(pu["t"][above[0]]) if above.size else None,
                               "t90": float(t90), "dp_end": float(pu["dp"][-1])})
    out["pickup"] = pick
    # supply topology: one cup over an edge (extra leak area A_edge)
    a_edge = 2e-5
    topo = {}
    for name, a_line, extra in (("manifold", P.SUPPLY["A_line"], a_edge), ("manifold, nozzle 1 mm^2", 1e-6, a_edge)):
        o = S.operating_vacuum(PORO["cardboard"], a_line=a_line, extra=extra)
        topo[name] = {"dp_cups": [float(x) for x in o["dp_cups"]], "dp_man": float(o["dp_man"])}
    o = S.operating_vacuum(PORO["cardboard"], q_max=P.SUPPLY["Q_max"] / 6, n_cups=1)
    topo["separate generators (good cup)"] = {"dp_cups": [float(o["dp_cups"][0])]}
    out["topology"] = topo
    return out


# ------------------------------------------------------------------ simulation studies
def peak_a(kind: int, t_move: float, lam: float = LAM, length: float = P.MOTION["L_move"]) -> float:
    return P.peak_coeff(kind, lam) * length / t_move ** 2


def validation(procs: int, work: Path, t_x0: float) -> dict:
    out = {}
    # (1) slow move: per-cup forces on the acceleration plateau vs the quasi-static statics
    T, lam = 2.0, 0.3
    jobs = [job("val_slow", {"T_move": T, "lam": lam, "perm": 0.0}, t_x0 + T + 0.2)]
    # (2) operating vacuum and pick-up per porosity (the cups at rest on the table, 0.34 s)
    for name, perm in PORO.items():
        # the lift is postponed, so the cups evacuate on the resting parcel for 1.5 s
        jobs.append(job(f"val_vac_{name}", {"perm": perm, "t_lift": 3.0, "t_x0": 5.0}, 1.5,
                        signals=["Cup1/dp", "Cup3/dp", "Gen/dp", "Gen/Q", "Cup1/Q_por", "Cup1/Q_leak"], points=1501))
    # (3) dynamic amplification: equal peak acceleration a_ref, trapezoid and S-curves
    a_ref = 4.0
    daf = [("trapezoid", 1, 0.0)] + [(f"S-curve lam {l:g}", 2, l) for l in (0.1, 0.2, 0.3, 0.5)]
    for label, kind, l in daf:
        tm = math.sqrt(P.peak_coeff(kind, l) * P.MOTION["L_move"] / a_ref)
        jobs.append(job(f"daf_{kind}_{l:g}", {"kind": kind, "lam": l if kind == 2 else LAM, "T_move": tm, "perm": 0.0},
                        t_x0 + tm + 0.4))
    res = run_jobs(jobs, procs, work, "val")

    r = res["val_slow"]
    t = sig(r, "time")
    a_pk = peak_a(2, T, lam)
    ta = T / 3.0
    t_mid = t_x0 + 0.5 * ta          # the middle of the acceleration plateau
    w = (t > t_mid - 0.05) & (t < t_mid + 0.05)
    qs = S.quasi_static(a_pk, dp=float(sig(r, "Cup1/dp")[w].mean()))
    rows = []
    for n in range(1, 7):
        rows.append({"cup": n, "T_sim": float(sig(r, f"Cup{n}/T")[w].mean()), "T_qs": float(qs["T"][n - 1]),
                     "F_lat_sim": float(sig(r, f"Cup{n}/F_lat")[w].mean()), "F_lat_qs": float(qs["F_lat"][n - 1]),
                     "U_sim": float(sig(r, f"Cup{n}/U")[w].mean()), "U_qs": float(qs["U"][n - 1])})
    scale_t = max(abs(x["T_qs"]) for x in rows)
    scale_l = max(abs(x["F_lat_qs"]) for x in rows)
    out["slow_move"] = {"T_move": T, "lam": lam, "a_peak": a_pk, "t_compare": t_mid, "cups": rows,
                        "max_err_T_pct": 100 * max(abs(x["T_sim"] - x["T_qs"]) for x in rows) / scale_t,
                        "max_err_F_lat_pct": 100 * max(abs(x["F_lat_sim"] - x["F_lat_qs"]) for x in rows) / scale_l}

    vac = {}
    for name, perm in PORO.items():
        rr = res[f"val_vac_{name}"]
        tt = sig(rr, "time")
        an = S.operating_vacuum(perm)
        pu = S.pickup(perm, t_end=1.5)
        dsim = sig(rr, "Cup1/dp")
        vac[name] = {"dp_sim": float(dsim[-1]), "dp_analytic": float(an["dp_cups"].mean()),
                     "Gen_dp_sim": float(sig(rr, "Gen/dp")[-1]), "dp_man_analytic": float(an["dp_man"]),
                     "Q_sim": float(sig(rr, "Gen/Q")[-1]), "Q_analytic": float(an["Q"]),
                     "dp_sim_0.05": float(np.interp(0.05, tt, dsim)), "dp_ode_0.05": float(np.interp(0.05, pu["t"], pu["dp"])),
                     "dp_sim_0.1": float(np.interp(0.1, tt, dsim)), "dp_ode_0.1": float(np.interp(0.1, pu["t"], pu["dp"])),
                     "dp_sim_0.3": float(np.interp(0.3, tt, dsim)), "dp_ode_0.3": float(np.interp(0.3, pu["t"], pu["dp"]))}
    out["vacuum"] = vac

    dafr = []
    for label, kind, l in daf:
        tm = math.sqrt(P.peak_coeff(kind, l) * P.MOTION["L_move"] / a_ref)
        rr = res[f"daf_{kind}_{l:g}"]
        tt = sig(rr, "time")
        w = (tt >= t_x0) & (tt <= t_x0 + tm + 0.3)
        dp = float(sig(rr, "Cup1/dp")[(tt > t_x0 - 0.1) & (tt < t_x0)].mean())
        qs0 = S.quasi_static(0.0, dp=dp)["U"]
        qsa = S.quasi_static(a_ref, dp=dp)["U"]
        qsd = S.quasi_static(-a_ref, dp=dp)["U"]
        u_sim = max(float(sig(rr, f"Cup{n}/U")[w].max()) for n in range(1, 7))
        u_qs = float(max(qsa.max(), qsd.max()))
        u0 = float(qs0.max())
        jerk = a_ref / (l * tm / 3.0) if kind == 2 else math.inf
        dafr.append({"profile": label, "T_move": tm, "jerk": jerk, "U_sim": u_sim, "U_qs": u_qs, "U_static": u0,
                     "DAF": (u_sim - u0) / (u_qs - u0), "lost": float(sig(rr, "Monitor/n_lost").max())})
    out["daf"] = {"a_ref": a_ref, "rows": dafr}
    return out


def sweep(procs: int, work: Path, t_x0: float, quick: bool) -> dict:
    """Shortest safe transfer time per profile x yaw x tilt x porosity."""
    combos = []
    kinds = (1, 2, 3, 4)
    poros = list(PORO) if not quick else ["cardboard"]
    for kind in kinds:
        for yaw in YAWS:
            for k in TILTS:
                for pname in poros:
                    combos.append((kind, yaw, k, pname))
    target = 1.0 / P.SAFETY

    def gl(c, tm):
        kind, yaw, k, pname = c
        return {"kind": kind, "psi_deg": yaw, "k_tilt_g": k, "perm": PORO[pname], "T_move": round(tm, 4)}

    def cid(c):
        return f"k{c[0]}_y{c[1]}_t{c[2]:g}_{c[3]}"

    def safe(m):
        return m["ok"] and m["lost"] == 0 and m["maxU"] <= target

    grid = [0.6, 0.75, 0.9, 1.1, 1.35, 1.65, 2.0, 2.5, 3.1, 3.9]
    jobs = []
    for c in combos:
        for tm in grid:
            jobs.append(job(f"{cid(c)}_T{tm:g}", gl(c, tm), t_x0 + tm + 0.32,
                            signals=[f"Cup{n}/U" for n in range(1, 7)] + ["Monitor/n_lost", "Monitor/held"], points=int((t_x0 + tm + 0.32) * 400)))
    res = run_jobs(jobs, procs, work, "grid")
    bracket = {}
    table = {}
    for c in combos:
        ms = [(tm, transfer_metrics(res[f"{cid(c)}_T{tm:g}"], t_x0, tm)) for tm in grid]
        table[cid(c)] = [{"T": tm, "maxU": m["maxU"], "lost": m["lost"]} for tm, m in ms]
        lo, hi = None, None
        for tm, m in ms:
            if safe(m):
                hi = tm if hi is None else min(hi, tm)
        if hi is not None:
            fails = [tm for tm, m in ms if tm < hi]
            lo = max(fails) if fails else None
        bracket[c] = [lo, hi]
    # bisection on the bracket (3 rounds)
    for rnd in range(3):
        jobs = []
        for c, (lo, hi) in bracket.items():
            if lo is None or hi is None:
                continue
            mid = round(0.5 * (lo + hi), 4)
            jobs.append(job(f"{cid(c)}_b{rnd}_T{mid:g}", gl(c, mid), t_x0 + mid + 0.32,
                            signals=[f"Cup{n}/U" for n in range(1, 7)] + ["Monitor/n_lost", "Monitor/held"],
                            points=int((t_x0 + mid + 0.32) * 400)))
        res = run_jobs(jobs, procs, work, f"bis{rnd}")
        for c, (lo, hi) in list(bracket.items()):
            if lo is None or hi is None:
                continue
            mid = round(0.5 * (lo + hi), 4)
            m = transfer_metrics(res[f"{cid(c)}_b{rnd}_T{mid:g}"], t_x0, mid)
            table[cid(c)].append({"T": mid, "maxU": m["maxU"], "lost": m["lost"]})
            bracket[c] = [lo, mid] if safe(m) else [mid, hi]
    out = []
    for c, (lo, hi) in bracket.items():
        kind, yaw, k, pname = c
        tmin = hi
        out.append({"profile": PROFILES[kind], "kind": kind, "yaw": yaw, "tilt": k, "porosity": pname,
                    "T_min": tmin, "T_unsafe": lo,
                    "a_peak": peak_a(kind, tmin) if tmin else None})
    return {"rows": out, "grid": table, "safety": P.SAFETY}


def equal_time(procs: int, work: Path, t_x0: float) -> dict:
    """All four profiles at the same transfer time; and the porous / edge-leak scenarios."""
    jobs = []
    for tm in (0.7, 0.8):
        for kind in (1, 2, 3, 4):
            jobs.append(job(f"eq_{kind}_T{tm:g}", {"kind": kind, "T_move": tm}, t_x0 + tm + 0.5))
    res = run_jobs(jobs, procs, work, "eq")
    rows = []
    for tm in (0.7, 0.8):
        for kind in (1, 2, 3, 4):
            m = transfer_metrics(res[f"eq_{kind}_T{tm:g}"], t_x0, tm)
            rows.append({"T_move": tm, "profile": PROFILES[kind], "a_peak": peak_a(kind, tm), **m})
    return {"rows": rows}


SCEN = {
    "tilt_level": {"kind": 4, "T_move": 1.25, "k_tilt_g": 0},
    "tilt_tray": {"kind": 4, "T_move": 1.25, "k_tilt_g": 1},
    "porous_36lpm": {"perm": PORO["porous"], "Q_max": 6e-4, "T_move": 1.2},
    "porous_60lpm": {"perm": PORO["porous"], "Q_max": 1e-3, "T_move": 1.2},
    "edge_manifold": {"A_edge": 2e-5},
    "edge_valves": {"A_edge": 2e-5, "dp_close": 8000},
    "edge_nozzles": {"A_edge": 2e-5, "A_line": 1e-6},
}


def scenarios(procs: int, work: Path, t_x0: float) -> dict:
    """The claims of the scenario models: tilt gain, porous parcel on a small generator, edge leak."""
    base_t = P.MOTION["T_move"]
    jobs = [job(f"sc_{k}", g, t_x0 + g.get("T_move", base_t) + 0.5) for k, g in SCEN.items()]
    res = run_jobs(jobs, procs, work, "scen")
    out = {}
    for k, g in SCEN.items():
        r = res[f"sc_{k}"]
        tm = g.get("T_move", base_t)
        m = transfer_metrics(r, t_x0, tm)
        t = sig(r, "time")
        pre = (t > t_x0 - 0.1) & (t < t_x0)
        out[k] = {**m, "T_move": tm, "dp_cup1": float(sig(r, "Cup1/dp")[pre].mean()),
                  "dp_cup3": float(sig(r, "Cup3/dp")[pre].mean()), "Gen_Q": float(sig(r, "Gen/Q")[pre].mean()),
                  "lost_before_transfer": float(sig(r, "Monitor/n_lost")[t < t_x0].max()),
                  "held_end": float(sig(r, "Monitor/held")[t <= t_x0 + tm + 0.3].min())}
    return out


# ------------------------------------------------------------------ SVG chart
def svg_chart(sw: dict) -> str:
    """Grouped bars: T_min per profile, for (yaw 0, no tilt) per porosity, plus tilt and yaw 90."""
    rows = sw["rows"]
    series = [("sealed", 0, 0.0, "#1f77b4"), ("cardboard", 0, 0.0, "#d95f02"), ("porous", 0, 0.0, "#7570b3"),
              ("cardboard", 0, 1.0, "#1b9e77"), ("cardboard", 90, 0.0, "#a6761d")]
    labels = ["sealed", "cardboard", "porous", "cardboard + tilt", "cardboard, yaw 90°"]
    kinds = [1, 2, 3, 4]
    wdt, hgt, x0, y0, ph = 760, 340, 60, 30, 240
    vals = []
    for kind in kinds:
        for (pn, yaw, k, _) in series:
            v = next((r["T_min"] for r in rows if r["kind"] == kind and r["porosity"] == pn and r["yaw"] == yaw and r["tilt"] == k), None)
            vals.append(v)
    vmax = max([v for v in vals if v] + [1.0])
    vmax = math.ceil(vmax * 2) / 2
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {wdt} {hgt}" font-family="sans-serif" font-size="12">',
           f'<rect width="{wdt}" height="{hgt}" fill="#ffffff"/>']
    for k in range(int(vmax * 2) + 1):
        v = k * 0.5
        y = y0 + ph - ph * v / vmax
        out.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{wdt - 20}" y2="{y:.1f}" stroke="#e0e0e0"/>')
        out.append(f'<text x="{x0 - 6}" y="{y + 4:.1f}" text-anchor="end" fill="#333">{v:g}</text>')
    out.append(f'<text x="14" y="{y0 + ph / 2}" transform="rotate(-90 14 {y0 + ph / 2})" text-anchor="middle" fill="#333">shortest safe transfer time [s]</text>')
    gw = (wdt - x0 - 20) / len(kinds)
    bw = gw * 0.8 / len(series)
    for i, kind in enumerate(kinds):
        gx = x0 + i * gw + gw * 0.1
        for j, (_, _, _, col) in enumerate(series):
            v = vals[i * len(series) + j]
            x = gx + j * bw
            if v is None:
                out.append(f'<text x="{x + bw / 2:.1f}" y="{y0 + ph - 4}" text-anchor="middle" fill="#888">&gt;</text>')
                continue
            h = ph * v / vmax
            out.append(f'<rect x="{x:.1f}" y="{y0 + ph - h:.1f}" width="{bw - 2:.1f}" height="{h:.1f}" fill="{col}"/>')
            out.append(f'<text x="{x + bw / 2 - 1:.1f}" y="{y0 + ph - h - 3:.1f}" text-anchor="middle" font-size="10" fill="#333">{v:.2f}</text>')
        out.append(f'<text x="{gx + gw * 0.4:.1f}" y="{y0 + ph + 16}" text-anchor="middle" fill="#333">{PROFILES[kind]}</text>')
    lx = x0
    for (_, _, _, col), lab in zip(series, labels):
        out.append(f'<rect x="{lx}" y="{hgt - 22}" width="12" height="12" fill="{col}"/>')
        out.append(f'<text x="{lx + 16}" y="{hgt - 12}" fill="#333">{lab}</text>')
        lx += 16 + 8 * len(lab) + 18
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--quick", action="store_true", help="cardboard only in the sweep")
    ap.add_argument("--work", default=str(Path(tempfile.gettempdir()) / "bgsim-suction-design"),
                    help="run directory; finished runs are reused")
    ap.add_argument("--fresh", action="store_true", help="delete earlier runs first")
    args = ap.parse_args()
    work = Path(args.work)
    if args.fresh and work.exists():
        import shutil
        shutil.rmtree(work)
    g = model_globals()
    t_x0 = float(g["t_x0"])
    results = {"t_x0": t_x0, "safety": P.SAFETY}
    print("analytic sizing ...", flush=True)
    results["analytic"] = analytic()
    print("validation runs ...", flush=True)
    results["validation"] = validation(args.procs, work, t_x0)
    print("equal-time runs ...", flush=True)
    results["equal_time"] = equal_time(args.procs, work, t_x0)
    print("scenario runs ...", flush=True)
    results["scenarios"] = scenarios(args.procs, work, t_x0)
    print("sweep ...", flush=True)
    results["sweep"] = sweep(args.procs, work, t_x0, args.quick)
    (HERE / "results.json").write_text(json.dumps(results, indent=1, allow_nan=True) + "\n", encoding="utf-8", newline="\n")
    (HERE / "min_move_time.svg").write_text(svg_chart(results["sweep"]), encoding="utf-8", newline="\n")
    report(results)


def report(r: dict) -> None:
    an = r["analytic"]
    print("\nOperating vacuum per cup [kPa] (generator l/min):")
    for name, rows in an["operating_vacuum"].items():
        print(f"  {name:10s} " + "  ".join(f"{x['Q_lpm']:3d}: {x['dp_cup'] / 1e3:5.1f}" for x in rows))
    print("\nQuasi-static a_max [m/s^2] at S = 2 (60 l/min):")
    for name, d in an["a_max"].items():
        print(f"  {name:10s} dp {d['dp'] / 1e3:5.1f} kPa U_static {d['U_static']:.3f} " +
              " ".join(f"{k}={v:.2f}" for k, v in d.items() if k.startswith("yaw")))
    print("\nGenerator needed [l/min] for S = 2:", json.dumps(an["generator_needed_lpm"], indent=None))
    print("\nPick-up:", json.dumps(an["pickup"], indent=None)[:800])
    v = r["validation"]
    print(f"\nSlow move: max error T {v['slow_move']['max_err_T_pct']:.2f} %, F_lat {v['slow_move']['max_err_F_lat_pct']:.2f} %")
    for c in v["slow_move"]["cups"]:
        print(f"  cup {c['cup']}: T {c['T_sim']:7.3f} / {c['T_qs']:7.3f}  F_lat {c['F_lat_sim']:6.3f} / {c['F_lat_qs']:6.3f}  U {c['U_sim']:.3f} / {c['U_qs']:.3f}")
    for name, d in v["vacuum"].items():
        print(f"  vacuum {name:10s} sim {d['dp_sim']:8.1f} analytic {d['dp_analytic']:8.1f}  t=0.05: {d['dp_sim_0.05']:8.1f} / {d['dp_ode_0.05']:8.1f}")
    print("DAF at a = %g:" % v["daf"]["a_ref"])
    for d in v["daf"]["rows"]:
        print(f"  {d['profile']:18s} T {d['T_move']:.3f} jerk {d['jerk']:8.1f} U_sim {d['U_sim']:.3f} U_qs {d['U_qs']:.3f} DAF {d['DAF']:.2f} lost {d['lost']:.0f}")
    print("\nEqual time:")
    for d in r["equal_time"]["rows"]:
        print(f"  T {d['T_move']:.2f} {d['profile']:18s} a {d['a_peak']:6.2f} maxU {d['maxU']:.3f} lost {d['lost']:.0f}")
    print("\nScenarios:")
    for k, d in r["scenarios"].items():
        print(f"  {k:14s} maxU {d['maxU']:.3f} lost {d['lost']:.0f} held {d['held_end']:.0f} dp1 {d['dp_cup1']:8.0f} dp3 {d['dp_cup3']:8.0f}")
    print("\nShortest safe transfer time [s] (S = %g):" % r["safety"])
    for d in sorted(r["sweep"]["rows"], key=lambda x: (x["porosity"], x["kind"], x["yaw"], x["tilt"])):
        print(f"  {d['porosity']:10s} {d['profile']:18s} yaw {d['yaw']:3d} tilt {d['tilt']:.0f}: T_min {d['T_min']}  (a_peak {d['a_peak']})")


if __name__ == "__main__":
    main()
