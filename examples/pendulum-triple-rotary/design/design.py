# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6", "matplotlib>=3.8", "httpx>=0.28"]
# ///
"""Design of `pendulum-triple-rotary` (X5.13): the rotary arm of the Quanser double pendulum with a
three-link chain (NOT a Quanser product).

    uv run examples/pendulum-triple-rotary/design/design.py [--fresh]

Steps (the method is in `triple_lib.py`):

1. feasibility numbers (energy to raise the chain against the servo's power and speed);
2. the discrete LQR at the upright (1 kHz, zero-order hold);
3. the swing-up trajectory: implicit Hermite-Simpson collocation (CasADi/IPOPT), a coarse solve,
   a refinement of the grid and a continuation of the voltage bound, each warm-started;
4. the discrete TVLQR along it (with one consistent roll-out of the sampled model);
5. the closed loop of the whole scenario with the firmware logic (1 kHz, table interpolation,
   clamp, catch rule), nominal and with perturbed models;
6. the free swing of the design model for the bond-graph comparison.

Writes `design/design.json`; `build_model.py` turns it into the models, the controller block and
the scene. `--fresh` ignores the cached trajectory `design/_swingup.npz`.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import triple_lib as tl

CFG = {
    "example": "pendulum-triple-rotary",
    "t_on": 1.0,
    "t_s": 4.0,
    "stable_s": 3.5,
    "after_s": 3.5,
    # collocation: (intervals, voltage bound, link-rate weight) per solve, each warm-started from the
    # previous one. The heavy rate weight of the first solve selects a smooth basin (from the linear
    # guess IPOPT otherwise lands in whip-like optima with link rates of 30-60 rad/s); the later solves
    # relax it, refine the grid and leave 1 V of the amplifier to the feedback.
    "solves": [[100, 15.0, 1.0], [100, 15.0, 0.05], [250, 15.0, 0.05], [250, 14.0, 0.05]],
    "theta_max": 2.5,
    "w_du": 0.01,
    "dt_tab": 0.01,
    # state weights [arm, link1, link2, link3, rates] (rad, rad/s); R in 1/V^2. The same weights for
    # the TVLQR and the balance LQR, so the TVLQR ends exactly in the LQR gain.
    "qdiag": [20.0, 200.0, 200.0, 200.0, 1.0, 5.0, 5.0, 5.0],
    "r": 5.0,
    "catch_tol": 3.0e4,
    "dist_force": 0.1,
    "dist_duration": 0.05,
    "free_start": [0.25, 2.4, -0.9, 0.6],
    "t_free": 2.0,
    "k_joint": 1.0e8,
    "k_shaft": 1.0e7,
    "d_shaft": 200.0,
    "comment": (
        "X5.13: rotary triple inverted pendulum on the spatial multibond stdlib (NOT a Quanser product: the arm, "
        "the SRV02 servo and the pendulum links of the Quanser rotary double pendulum, chained short + short + "
        "medium). World -> Mount -> J1 (Revolute3D about world z, the arm) -> arm bar (RigidBody3D) -> J2, J3, J4 "
        "(Revolute3D about the arm axis, one per link), every body a RigidBody3D with a distributed mass (COM at the "
        "bar middle). The arm is driven by an SRV02-like servo with a 15 V amplifier: Motor (ElectricDrive, voltage "
        "input) -> Shaft (ElasticShaft) -> Gear (IdealGear, 70:1) -> J1.drive. The 1 kHz firmware Ctrl (phases: "
        "idle, discrete TVLQR swing-up along the collocation trajectory, latched discrete LQR balance) reads the "
        "joint angles and rates. Dist is a force pulse on the tip of the top link. Joint compliance kt = kr = 1e8 "
        "(N/m, N m/rad); every state is integral."
    ),
    "comment_free": (
        "X5.13 design check: the same bond graph released at rest from a non-trivial pose with the controller "
        "disabled (t_on far in the future, no disturbance). design.py integrates its Lagrangian model from the "
        "same pose; expected.json compares the arm and link angles."
    ),
}


def scenario_times(cfg: dict) -> dict:
    t_catch = cfg["t_on"] + cfg["t_s"]
    t_dist = t_catch + cfg["stable_s"]
    return {"t_catch": t_catch, "t_dist": t_dist, "t_end": t_dist + cfg["after_s"]}


def trajectory(plant: tl.Plant, cfg: dict, cache: Path, fresh: bool) -> dict:
    key = json.dumps({k: cfg[k] for k in ("t_s", "solves", "theta_max", "w_du")}
                     | {"plant": [plant.lengths, plant.masses, plant.drive.jrot, plant.drive.vmax, plant.jfric]}, sort_keys=True)
    if cache.is_file() and not fresh:
        data = np.load(cache, allow_pickle=False)
        if str(data["key"]) == key:
            return {"x": data["x"], "u": data["u"], "cost": float(data["cost"]), "t_s": cfg["t_s"],
                    "log": json.loads(str(data["log"])), "seconds": float(data["seconds"])}
    guess = tl.linear_guess(plant, cfg["solves"][0][0])
    log = []
    traj = None
    started = time.time()
    for nk, vmax, w_rate in cfg["solves"]:
        if traj is not None:
            guess = tl.resample(plant, traj, nk) if nk != traj["nk"] else (traj["x"], traj["u"])
        traj = tl.collocate(plant, cfg["t_s"], nk, guess, vmax, cfg["theta_max"], cfg["w_du"], w_rate)
        rates = np.abs(traj["x"][plant.nq + 1:])
        entry = {"nk": nk, "vmax": vmax, "w_rate": w_rate, "iters": traj["iters"], "seconds": round(traj["seconds"], 1),
                 "cost": round(traj["cost"], 2), "max_link_rate": round(float(rates.max()), 2),
                 "max_arm_rate": round(float(np.abs(traj["x"][plant.nq]).max()), 2),
                 "max_arm": round(float(np.abs(traj["x"][0]).max()), 3)}
        log.append(entry)
        print(f"  collocation {entry}", flush=True)
    seconds = time.time() - started
    np.savez(cache, key=key, x=traj["x"], u=traj["u"], cost=traj["cost"], log=json.dumps(log), seconds=seconds)
    traj["log"] = log
    traj["seconds"] = seconds
    return traj


def make_firmware(plant: tl.Plant, cfg: dict, traj: dict) -> tuple[tl.Firmware, dict]:
    k_lqr, p_lqr, poles = tl.dlqr(plant, cfg["qdiag"], cfg["r"])
    started = time.time()
    xs, us, ks, end_err = tl.tvlqr(plant, traj, cfg["qdiag"], cfg["r"], k_lqr, p_lqr)
    stride = int(round(cfg["dt_tab"] / tl.TS))
    tab_x, tab_u, tab_k = xs[::stride].copy(), us[::stride].copy(), ks[::stride].copy()
    # the last row: upright, 0 V, the LQR gain (the roll-out ends within `end_err` of it)
    tab_x[-1], tab_u[-1], tab_k[-1] = 0.0, 0.0, k_lqr
    fw = tl.Firmware(t_on=cfg["t_on"], t_s=cfg["t_s"], dt_tab=cfg["dt_tab"], tab_x=tab_x, tab_u=tab_u, tab_k=tab_k,
                     k_lqr=k_lqr, p_catch=p_lqr, catch_tol=cfg["catch_tol"], vmax=plant.drive.vmax)
    info = {"tvlqr_seconds": time.time() - started, "rollout_end_err": end_err, "poles": poles,
            "max_u_nominal": float(np.abs(us).max()), "max_gain": float(np.abs(ks).max())}
    return fw, info


def metrics(plant: tl.Plant, cfg: dict, times: dict, ts, xs, us, ph, st) -> dict:
    nq = plant.nq
    if not np.all(np.isfinite(xs)):
        return {"ok": False}
    phi = np.cumsum(xs[:, 1:nq], axis=1)
    dev = np.max(np.abs(phi), axis=1)
    t_catch = st.get("t_catch", math.nan)
    t_dist = times["t_dist"]
    pre = (ts >= (t_catch if math.isfinite(t_catch) else times["t_catch"]) + 1.5) & (ts < t_dist)
    post = ts >= t_dist
    outside = np.where((dev > math.radians(0.5)) & post)[0]
    near = np.where((dev < math.radians(3.0)) & (ts > cfg["t_on"]))[0]
    rest = (ts > 0.05) & (ts < cfg["t_on"])
    return {
        "ok": bool(dev[-1] < math.radians(0.5)),
        "t_upright": float(ts[near[0]]) if len(near) else math.nan,
        "t_catch": float(t_catch),
        "band_pre_deg": math.degrees(float(np.max(dev[pre]))),
        "peak_defl_deg": math.degrees(float(np.max(np.abs(phi[post & (ts <= t_dist + 2.0), -1])))),
        "t_recover": float(ts[outside[-1]]) - t_dist if len(outside) else 0.0,
        "final_dev_deg": math.degrees(float(dev[-1])),
        "peak_v": float(np.max(np.abs(us))),
        "max_arm": float(np.max(np.abs(xs[:, 0]))),
        "rest_dev": float(np.max(np.abs(xs[rest] - xs[0]))),
        "i_rms": float(np.sqrt(np.mean(((us - plant.drive.ng * plant.drive.kt * xs[:, nq]) / plant.drive.rm) ** 2))),
    }


def scenario(plant: tl.Plant, fw: tl.Firmware, cfg: dict, times: dict, force: float | None = None):
    step, _ = plant.steps()
    f = cfg["dist_force"] if force is None else force
    t0, dur = times["t_dist"], cfg["dist_duration"]
    out = tl.closed_loop(step, fw, plant.hanging(), times["t_end"], force=lambda t: f if t0 <= t < t0 + dur else 0.0)
    return out, metrics(plant, cfg, times, *out)


def perturbed(cfg: dict) -> dict[str, tl.Plant]:
    lengths, masses = tl.LINKS
    return {
        "link masses +3 %": tl.Plant(lengths, [m * 1.03 for m in masses], tl.Drive()),
        "link masses -3 %": tl.Plant(lengths, [m * 0.97 for m in masses], tl.Drive()),
        "link lengths +1 %": tl.Plant([v * 1.01 for v in lengths], masses, tl.Drive()),
        "bearing friction x3": tl.Plant(lengths, masses, tl.Drive(), jfric=3 * tl.JFRIC),
        "motor kt -3 %": tl.Plant(lengths, masses, tl.Drive(kt=0.97 * 0.0333)),
        "load friction x1.5": tl.Plant(lengths, masses, tl.Drive(beq=1.5 * 0.015)),
    }


def main(argv: list[str]) -> None:
    cfg = CFG
    plant = tl.Plant(*tl.LINKS, tl.Drive())
    times = scenario_times(cfg)
    feas = tl.feasibility(plant, cfg["t_s"])
    print("feasibility:", {k: round(v, 3) for k, v in feas.items()})
    traj = trajectory(plant, cfg, HERE / "_swingup.npz", "--fresh" in argv)
    print(f"trajectory optimisation: {traj['seconds']:.1f} s, cost {traj['cost']:.2f}")
    fw, info = make_firmware(plant, cfg, traj)
    print(f"TVLQR: {info['tvlqr_seconds']:.1f} s, roll-out end error {info['rollout_end_err']:.2e}, "
          f"max nominal voltage {info['max_u_nominal']:.2f} V, max gain {info['max_gain']:.1f}")
    print(f"LQR equivalent poles: {np.round(np.sort(info['poles'].real), 2)}")
    (ts, xs, us, ph, st), m = scenario(plant, fw, cfg, times)
    print("closed loop (design model):", {k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()})
    robust = {}
    for name, p in perturbed(cfg).items():
        _, mp = scenario(p, fw, cfg, times)
        robust[name] = {k: mp.get(k) for k in ("ok", "t_catch", "band_pre_deg", "peak_defl_deg", "t_recover", "peak_v")}
        print(f"  {name}: {({k: round(v, 3) if isinstance(v, float) else v for k, v in robust[name].items()})}")
    # the largest pulse the nominal loop recovers (bisection)
    lo, hi = cfg["dist_force"], 0.4
    for _ in range(7):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if scenario(plant, fw, cfg, times, mid)[1]["ok"] else (lo, mid)
    print(f"largest recovered pulse: {lo:.3f} N ({cfg['dist_duration'] * 1000:.0f} ms); used {cfg['dist_force']} N")
    if not (m["ok"] and all(r["ok"] for r in robust.values())):
        raise SystemExit("the design closed loop does not recover in every case: not writing design.json")
    tn, xf, phif = tl.free_swing(plant, np.array(cfg["free_start"]), cfg["t_free"])
    idx = [int(round(t / 0.01)) for t in np.arange(0.25, cfg["t_free"] + 1e-9, 0.25)]
    d = plant.drive
    doc = {
        "example": cfg["example"],
        "n_links": plant.n_links,
        "lengths": plant.lengths,
        "masses": plant.masses,
        "drive": {"rm": d.rm, "lm": d.lm, "kt": d.kt, "jm": d.jm, "ng": d.ng, "beq": d.beq, "vmax": d.vmax},
        "jfric": plant.jfric,
        "k_joint": cfg["k_joint"],
        "k_shaft": cfg["k_shaft"],
        "d_shaft": cfg["d_shaft"],
        "t_on": cfg["t_on"],
        "t_s": cfg["t_s"],
        "dt_tab": cfg["dt_tab"],
        "vmax": d.vmax,
        "catch_tol": cfg["catch_tol"],
        "qdiag": cfg["qdiag"],
        "r": cfg["r"],
        "k_lqr": fw.k_lqr.tolist(),
        "p_lqr": fw.p_catch.tolist(),
        "poles": [[float(p.real), float(p.imag)] for p in info["poles"]],
        "tab_x": fw.tab_x.tolist(),
        "tab_u": fw.tab_u.tolist(),
        "tab_k": fw.tab_k.tolist(),
        "t_dist": times["t_dist"],
        "t_end": times["t_end"],
        "dist_force": cfg["dist_force"],
        "dist_duration": cfg["dist_duration"],
        "max_pulse": lo,
        "free_start": cfg["free_start"],
        "t_free": cfg["t_free"],
        "free_samples": {
            "t": [float(tn[i]) for i in idx],
            "q": [[float(v) for v in xf[i, :plant.nq]] for i in idx],
            "phi": [[float(v) for v in phif[i]] for i in idx],
        },
        "feasibility": feas,
        "collocation": {"log": traj["log"], "seconds": traj["seconds"], "cost": traj["cost"], "w_du": cfg["w_du"],
                        "w_rate": cfg["solves"][-1][2], "theta_max": cfg["theta_max"]},
        "tvlqr": {k: v for k, v in info.items() if k != "poles"},
        "metrics": m,
        "robustness": robust,
        "comment": cfg["comment"],
        "comment_free": cfg["comment_free"],
    }
    path = HERE / "design.json"
    path.write_text(json.dumps(doc) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
