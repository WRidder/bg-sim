"""The design pipeline of the rotary pendulums (X5.13), shared by both examples.

    uv run examples/pendulum-double-rotary/design/design.py            # design, write design.json
    uv run examples/pendulum-double-rotary/design/design.py --verify   # + bond-graph free swing

Steps: Lagrangian model (rotary_lib) -> LQR at the upright -> swing-up trajectory by direct
collocation (CasADi/IPOPT, the motor voltage limit included) -> time-varying LQR along it ->
closed-loop simulation of the whole scenario (hanging, swing-up, catch, balance, disturbance,
recovery) -> design-model free swing. Everything the bond-graph model needs is written to
`design.json`; `build_model.py` turns it into the model, the controller block and the scene.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

import rotary_lib as rl


def scenario_times(cfg: dict) -> dict:
    t_catch = cfg["t_on"] + cfg["t_s"]
    t_dist = t_catch + cfg["stable_s"]
    return {"t_catch": t_catch, "t_dist": t_dist, "t_end": t_dist + cfg["after_s"]}


def trajectory(plant: rl.Plant, cfg: dict, verbose: bool):
    """Continuation in the voltage bound, then refinement of the collocation grid (the finer grids
    are what makes the trajectory dynamically exact: TVLQR cannot track a trajectory that the
    model does not follow)."""
    guess = rl.sim_guess(plant, cfg["t_s"], cfg["nk"], cfg["guess_amp"], cfg["guess_freq"], max(cfg["vmax_steps"]))
    kw = {"theta_max": cfg["theta_max"], "rate_weight": cfg["rate_weight"], "smooth": cfg["smooth"], "rate_max": cfg.get("rate_max")}
    nk = cfg["nk"]
    for vmax in cfg["vmax_steps"]:
        xs, us, um, cost = rl.swing_up(plant, cfg["t_s"], vmax, nk, guess=guess, **kw)
        guess = (xs, us, um)
        if verbose:
            print(f"  trajectory at vmax {vmax:g} V, nk {nk}: cost {cost:.1f}", flush=True)
    for nk in cfg["refine"]:
        guess = rl.refine_guess(plant, cfg["t_s"], xs, us, um, nk)
        xs, us, um, cost = rl.swing_up(plant, cfg["t_s"], cfg["vmax_steps"][-1], nk, guess=guess, **kw)
        if verbose:
            print(f"  refined to nk {nk}: cost {cost:.1f}", flush=True)
    return xs, us, um, cost


def design(n_links: int, cfg: dict, cache: Path | None = None, verbose: bool = True) -> dict:
    plant = rl.Plant(n_links, *rl.LINKS[n_links])
    nx = plant.nx
    qdiag = np.array(cfg["qdiag"], float)
    k_lqr, p_lqr, a, b = rl.lqr(plant, qdiag, cfg["r"])
    poles = np.linalg.eigvals(a - b @ k_lqr.reshape(1, -1))
    t0 = time.time()
    key = json.dumps({k: cfg[k] for k in ("t_s", "vmax_steps", "refine", "theta_max", "nk", "guess_amp", "guess_freq", "rate_weight", "smooth")} | ({"rate_max": cfg["rate_max"]} if cfg.get("rate_max") else {}), sort_keys=True)
    if cache is not None and cache.is_file():
        data = np.load(cache, allow_pickle=True)
        if str(data["key"]) == key:
            xs, us, um, cost = data["xs"], data["us"], data["um"], float(data["cost"])
        else:
            data = None
    else:
        data = None
    if data is None:
        xs, us, um, cost = trajectory(plant, cfg, verbose)
        if cache is not None:
            np.savez(cache, key=key, xs=xs, us=us, um=um, cost=cost)
    t_opt = time.time() - t0
    qtv = np.array(cfg.get("qdiag_tv", cfg["qdiag"]), float)
    tab_x, tab_u, tab_k = rl.tvlqr(plant, cfg["t_s"], xs, us, um, qtv, cfg["r_tv"], rl.lqr(plant, qtv, cfg["r_tv"])[1], cfg["dt_tab"])
    k_final = rl.lqr(plant, qtv, cfg["r_tv"])[0]
    times = scenario_times(cfg)
    d = rl.Design(
        plant=plant, t_on=cfg["t_on"], t_s=cfg["t_s"], vmax=rl.VMAX, qdiag=qdiag, r=cfg["r"],
        k_lqr=k_lqr, p_lqr=p_lqr, dt_tab=cfg["dt_tab"], tab_x=tab_x, tab_u=tab_u, tab_k=tab_k,
        catch_w=np.array(cfg["catch_w"], float), catch_tol=cfg["catch_tol"],
    )  # fmt: skip
    force, dur = cfg["dist_force"], cfg["dist_duration"]

    def disturb(t, x):
        out = np.zeros(nx)
        if times["t_dist"] <= t < times["t_dist"] + dur:
            out[plant.nq:] = force * np.array(plant.qdist(x[: plant.nq])).ravel()
        return out

    ts, xsim, usim, ph, state = rl.simulate(d, plant.hanging(), times["t_end"], disturb=disturb)
    phi = np.cumsum(xsim[:, 1 : plant.nq], axis=1)  # absolute link angles from upright
    # (hanging is phi1 = pi: wrap to the swing-up convention, upright 0, via the final value)
    result = metrics(plant, cfg, times, ts, xsim, usim, ph, phi)
    result["t_opt"] = t_opt
    result["cost"] = cost
    result["poles"] = [complex(p) for p in poles]
    result["k_final_tv_minus_lqr"] = float(np.max(np.abs(k_final - k_lqr))) if cfg["r_tv"] == cfg["r"] else None
    sim = {"t": ts, "x": xsim, "u": usim, "phase": ph, "phi": phi}
    return {"plant": plant, "design": d, "metrics": result, "times": times, "sim": sim, "traj": (xs, us, um)}


def metrics(plant, cfg, times, ts, xsim, usim, ph, phi) -> dict:
    t_catch = float(ts[np.argmax(ph >= 2)]) if np.any(ph >= 2) else math.nan
    dist_force_t = times["t_dist"]
    pre = (ts >= t_catch + 1.5) & (ts < dist_force_t)
    post = ts >= dist_force_t
    band_pre = float(np.max(np.abs(phi[pre]))) if np.any(pre) else math.nan
    peak_defl = float(np.max(np.abs(phi[post][:, -1]))) if np.any(post) else math.nan
    # recovery: the last time any link is outside 0.5 deg after the disturbance starts
    outside = np.where(np.max(np.abs(phi), axis=1) > math.radians(0.5))[0]
    outside = outside[ts[outside] >= dist_force_t]
    t_rec = float(ts[outside[-1]]) - dist_force_t if len(outside) else 0.0
    # swing-up: first time all links within 3 deg of upright after t_on
    near = np.where((np.max(np.abs(phi), axis=1) < math.radians(3.0)) & (ts > cfg["t_on"]))[0]
    return {
        "t_catch": t_catch,
        "band_pre_deg": math.degrees(band_pre),
        "peak_defl_deg": math.degrees(peak_defl),
        "t_recover": t_rec,
        "peak_v": float(np.max(np.abs(usim))),
        "max_arm": float(np.max(np.abs(xsim[:, 0]))),
        "t_upright": float(ts[near[0]]) if len(near) else math.nan,
        "final_dev_deg": math.degrees(float(np.max(np.abs(phi[-1])))),
        "rest_dev": float(np.max(np.abs(phi[(ts > 0.2) & (ts < cfg["t_on"])] - phi[0]))) if True else 0.0,
    }


def free_swing(plant: rl.Plant, start, t_end: float, dt: float = 0.01):
    """Open-loop free swing of the design model (motor terminals at 0 V) from rest at `start`."""
    from scipy.integrate import solve_ivp

    x0 = np.concatenate([start, np.zeros(plant.nq)])
    tn = np.arange(0.0, t_end + 1e-9, dt)
    sol = solve_ivp(lambda t, x: plant.rhs(x, 0.0), (0, t_end), x0, t_eval=tn, rtol=1e-10, atol=1e-12, method="DOP853")
    phi = np.cumsum(sol.y[1 : plant.nq].T, axis=1)
    return tn, sol.y.T, phi


def to_json(example: str, n_links: int, cfg: dict, out: dict, free: dict) -> dict:
    d: rl.Design = out["design"]
    m = out["metrics"]
    times = out["times"]
    return {
        "example": example,
        "n_links": n_links,
        "t_on": cfg["t_on"],
        "t_s": cfg["t_s"],
        "dt_tab": cfg["dt_tab"],
        "vmax": rl.VMAX,
        "catch_w": list(cfg["catch_w"]),
        "catch_tol": cfg["catch_tol"],
        "k_lqr": [float(v) for v in d.k_lqr],
        "tab_x": d.tab_x.tolist(),
        "tab_u": d.tab_u.tolist(),
        "tab_k": d.tab_k.tolist(),
        "t_dist": times["t_dist"],
        "t_end": times["t_end"],
        "dist_force": cfg["dist_force"],
        "dist_duration": cfg["dist_duration"],
        "free_start": list(cfg["free_start"]),
        "t_free": cfg["t_free"],
        "free_samples": free,
        "metrics": {k: (v if not isinstance(v, complex) else [v.real, v.imag]) for k, v in m.items() if k != "poles"},
        "qdiag": list(cfg["qdiag"]),
        "r": cfg["r"],
    }


def run(example_dir: Path, n_links: int, cfg: dict, argv: list[str]) -> None:
    cache = example_dir / "design" / "_swingup.npz"
    out = design(n_links, cfg, cache)
    m = out["metrics"]
    plant: rl.Plant = out["plant"]
    print(f"LQR closed-loop poles: {np.round(np.array(m['poles']), 2)}")
    print(f"trajectory optimisation: cost {m['cost']:.1f}, {m['t_opt']:.1f} s")
    for key in ("t_upright", "t_catch", "band_pre_deg", "peak_defl_deg", "t_recover", "peak_v", "max_arm", "final_dev_deg", "rest_dev"):
        print(f"  {key} = {m[key]:.4f}")
    start = np.array(cfg["free_start"], float)
    tn, xf, phif = free_swing(plant, start, cfg["t_free"])
    idx = [int(round(t / 0.01)) for t in np.arange(0.25, cfg["t_free"] + 1e-9, 0.25)]
    free = {
        "t": [float(tn[i]) for i in idx],
        "q": [[float(v) for v in xf[i, : plant.nq]] for i in idx],
        "phi": [[float(v) for v in phif[i]] for i in idx],
    }
    doc = to_json(cfg["example"], n_links, cfg, out, free)
    doc["comment"] = cfg["comment"]
    doc["comment_free"] = cfg["comment_free"]
    path = example_dir / "design" / "design.json"
    path.write_text(json.dumps(doc) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    if "--plot" in argv:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        s = out["sim"]
        fig, ax = plt.subplots(3, 1, sharex=True, figsize=(9, 7))
        ax[0].plot(s["t"], s["phi"] + np.array([-math.pi] + [0] * (n_links - 1)) * 0)
        ax[1].plot(s["t"], s["u"])
        ax[2].plot(s["t"], s["x"][:, 0])
        fig.savefig(example_dir / "design" / "_design.png", dpi=80)
