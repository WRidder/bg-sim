# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `quad-pendulum` example: swing-up trajectory, TVLQR and balance LQR of a chain of four
pendulum links on a cart (`cart`) or on a rotary arm (`rotary`), and the short-travel controller of the
cart (`cart_short`: the same plant, the swing-up planned within +-0.5 m; run it after `cart`).

    uv run examples/quad-pendulum/design/design.py cart|cart_short|rotary [--fresh]

Steps (the method is in `quadlib.py`):

1. the discrete LQR at the upright (1 kHz, zero-order hold) and the open-loop poles;
2. the swing-up trajectory: implicit Hermite-Simpson collocation (CasADi/IPOPT) from hanging rest to
   upright rest in T_s, bounded input, travel and input slew rate; a sequence of warm-started solves
   (heavy link-rate weight first, then lighter, then a finer grid). Cached in `_traj_<rig>.npz`
   (`--fresh` recomputes);
3. the discrete TVLQR along it, with one closed-loop roll-out of the sampled model as the nominal;
4. the closed loop of the firmware replica (1 kHz, table interpolation, clamp, slew limit, catch
   region, latch) on the design model: the swing-up scenario, the balance scenario, robustness
   cases (masses, lengths, friction, delay, quantisation);
5. the free swing of the design model at the check times (the twin check of the bond graph).

Writes `design/design_<kind>.json`; `build_models.py` turns them into the library blocks, models,
scenes and dashboards.
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import quadlib as ql  # noqa: E402

# ----------------------------------------------------------------------------- the rigs
# Cart: four equal aluminium-tube links of 0.275 m and 0.10 kg (uniform rods). Their upright potential
# energy above the hanging rest is 16 m g L = 4.32 J, the "UPRIGHT 4.3 J" level of the reference
# video. A 1 kg cart on a +-1.5 m rail with viscous rail friction 1 N s/m, an ideal force actuator
# limited to +-40 N and 4000 N/s (a belt-driven servo cart), joint friction 5e-4 N m s/rad.
CART = ql.Rig(kind="cart", L=[0.275] * 4, m=[0.10] * 4, b_joint=5e-4, m_base=1.0, b_base=1.0,
              u_max=40.0, slew=4000.0, s_max=1.5)
# Rotary: a 0.30 m, 0.30 kg arm on a direct-drive hub (2e-3 kg m^2 with the rotor), four links of
# 0.15 m and 0.03 kg, ideal torque limited to +-3 N m and 300 N m/s, bearing friction 0.01 N m s/rad
# on the arm and 2e-5 N m s/rad on the pendulum joints. Cable limit +-3 rad of arm travel.
ROTARY = ql.Rig(kind="rotary", L=[0.15] * 4, m=[0.03] * 4, b_joint=2e-5, m_base=0.30, b_base=0.01,
                u_max=3.0, slew=300.0, s_max=3.0, arm_l=0.30, J_hub=2.0e-3)

CFG = {
    "cart": {
        "rig": CART, "ctrl_block": "QuadCartCtrl", "monitor_block": "QuadCartMonitor",
        "t_on": 1.0, "t_s": 5.0, "after": 4.0, "dt_tab": 0.01,
        # firmware tables: "v" the combined feed-forward v = u* + K z* (u = v - K z, 11 tables), "x" the
        # separate u*, z* (u = u* - K (z - z*), 21 tables, exact between the knots). The bond-graph run time
        # grows with the total table size; on the cart the combined form is as robust as the separate one.
        "ff_form": "v",
        # collocation: (intervals, link-rate weight); bounds for the feed-forward (feedback keeps the rest)
        "solves": [[100, 1.0], [100, 0.1], [200, 0.1]], "u_lim": 30.0, "s_lim": 1.0, "slew_lim": 3000.0,
        "w_du": 1e-4, "swings": 3, "s_amp": 0.3,
        # balance LQR (moderate: gains of a few thousand N/rad, tolerant to delay and encoder noise) and the
        # swing-up TVLQR (stiff tracking of the nominal; its terminal cost is the LQR cost-to-go)
        "qdiag": [100.0, 400.0, 400.0, 400.0, 400.0, 10.0, 5.0, 5.0, 5.0, 5.0], "r": 0.3,
        "qdiag_tv": [100.0, 400.0, 400.0, 400.0, 400.0, 1.0, 5.0, 5.0, 5.0, 5.0], "r_tv": 0.1,
        "catch_tol": 1.0e3,
        "res_s": 1.0e-5, "res_q": 2 * math.pi / 65536, "tau_f": 0.002,
        "balance_th0": [2.0, 2.0, 2.0, 2.0], "balance_t": 7.0, "push": {"t_start": 3.0, "duration": 0.05},
        "free_z0": [0.1, -2.4, -1.6, -2.0, -2.9], "free_t": 1.5,
    },
    "rotary": {
        "rig": ROTARY, "ctrl_block": "QuadRotaryCtrl", "monitor_block": "QuadRotaryMonitor",
        "t_on": 1.0, "t_s": 5.0, "after": 4.0, "dt_tab": 0.01,
        # the separate form: with the combined one the interpolation of K z* between the knots (gains up to
        # 4700 N m/rad changing fast) costs the swing-up its robustness to +5 % masses, +1 % lengths and delay
        "ff_form": "x",
        "solves": [[100, 1.0], [100, 0.1], [200, 0.1]], "u_lim": 2.5, "s_lim": 2.5, "slew_lim": 250.0,
        "w_du": 1e-4, "swings": 3, "s_amp": 1.0,
        "qdiag": [2.0, 100.0, 100.0, 100.0, 100.0, 0.1, 1.0, 1.0, 1.0, 1.0], "r": 10.0,
        "qdiag_tv": [200.0, 4000.0, 4000.0, 4000.0, 4000.0, 1.0, 50.0, 50.0, 50.0, 50.0], "r_tv": 1.0,
        "catch_tol": 1.0e3,
        "res_s": 2 * math.pi / 65536, "res_q": 2 * math.pi / 65536, "tau_f": 0.005,
        "balance_th0": [2.0, 2.0, 2.0, 2.0], "balance_t": 7.0, "push": {"t_start": 3.0, "duration": 0.05},
        "free_z0": [0.3, 2.4, 1.6, 2.0, 2.9], "free_t": 1.5,
    },
}
for _k in ("cart", "rotary"):
    CFG[_k] |= {"variant": "full", "prefix": "quad-pendulum" if _k == "cart" else "quad-rotary",
                "travel": CFG[_k]["rig"].s_max}
# Short-travel variant of the cart: the same plant (rail, actuator, end stops), a different controller.
# The swing-up is planned with the cart travel as a hard constraint (|x| <= 0.5 m, with a margin for the
# feedback) and the TVLQR uses heavier rate weights so that the catch and a push stay inside the limit.
CFG["cart_short"] = CFG["cart"] | {
    "variant": "short", "prefix": "quad-pendulum-short", "ctrl_block": "QuadCartShortCtrl", "travel": 0.5,
    "u_lim": 35.0, "s_lim": 0.40, "slew_lim": 3500.0, "swings": 3, "s_amp": 0.3,
    # heavier rate weights than the full-travel TVLQR: with the stiffer full-travel weights the swing-up
    # within +-0.4 m saturated and fell with 3x joint friction or quantised encoders
    "qdiag_tv": [100.0, 400.0, 400.0, 400.0, 400.0, 10.0, 20.0, 20.0, 20.0, 20.0], "r_tv": 0.3,
}
# bond-graph compliances (not in the design model): their effect is measured by the twin check
BOND = {"kt_pivot": 1.0e8, "bt_pivot": 1.0e3, "kr_rail": 1.0e5, "br_rail": 2.0, "kd_rail": 1.0e8, "bd_rail": 2.0e3,
        "k_stop": 2.0e4, "d_stop": 200.0, "k_joint": 1.0e8, "J_cart": 2.0e-3}


def trajectory(plant: ql.Plant, cfg: dict, cache: Path, fresh: bool) -> dict:
    R = plant.rig
    key = json.dumps({k: cfg[k] for k in ("t_s", "solves", "u_lim", "s_lim", "slew_lim", "w_du", "swings", "s_amp")}
                     | {"rig": dataclasses.asdict(R)}, sort_keys=True)
    if cache.is_file() and not fresh:
        d = np.load(cache, allow_pickle=False)
        if str(d["key"]) == key:
            return {"x": d["x"], "u": d["u"], "t_s": cfg["t_s"], "nk": d["x"].shape[1] - 1,
                    "log": json.loads(str(d["log"])), "seconds": float(d["seconds"]), "cost": float(d["cost"])}
    guess = ql.guess_linear(plant, cfg["solves"][0][0], cfg["swings"], cfg["s_amp"])
    traj, log, started = None, [], time.time()
    for nk, w_rate, *u_stage in cfg["solves"]:
        # a stage may tighten the input bound (the last one is the plan's bound)
        u_lim = u_stage[0] if u_stage else cfg["u_lim"]
        if traj is not None:
            guess = ql.resample(plant, traj, nk) if nk != traj["nk"] else (traj["x"], traj["u"])
        traj = ql.collocate(plant, cfg["t_s"], nk, guess, u_lim, cfg["s_lim"], cfg["slew_lim"], cfg["w_du"], w_rate)
        e = {"nk": nk, "w_rate": w_rate, "u_lim": u_lim, "iters": traj["iters"], "seconds": round(traj["seconds"], 1),
             "cost": round(traj["cost"], 3), "max_u": round(float(np.abs(traj["u"]).max()), 3),
             "max_s": round(float(np.abs(traj["x"][0]).max()), 3),
             "max_link_rate": round(float(np.abs(traj["x"][plant.nq + 1:]).max()), 2)}
        log.append(e)
        print("  collocation", e, flush=True)
    seconds = time.time() - started
    np.savez(cache, key=key, x=traj["x"], u=traj["u"], log=json.dumps(log), seconds=seconds, cost=traj["cost"])
    traj["log"], traj["seconds"] = log, seconds
    return traj


def firmware(plant, cfg, traj, k_lqr, p_lqr, **kw) -> tuple[ql.Firmware, dict]:
    R = plant.rig
    t0 = time.time()
    xs, us, ks, end_err = ql.tvlqr(plant, traj, cfg["qdiag_tv"], cfg["r_tv"], k_lqr, p_lqr,
                                   u_clamp=R.u_max if cfg.get("rollout_clamp") else None)
    stride = int(round(cfg["dt_tab"] / ql.TS))
    tab_x, tab_u, tab_k = xs[::stride].copy(), us[::stride].copy(), ks[::stride].copy()
    tab_x[-1], tab_u[-1], tab_k[-1] = 0.0, 0.0, k_lqr
    tab_v = tab_u + np.sum(tab_k * tab_x, axis=1) if cfg["ff_form"] == "v" else None
    fw = ql.Firmware(t_on=cfg["t_on"], t_s=cfg["t_s"], dt_tab=cfg["dt_tab"], tab_x=tab_x, tab_u=tab_u, tab_k=tab_k, tab_v=tab_v,
                     k_lqr=k_lqr, p_catch=p_lqr, catch_tol=cfg["catch_tol"], u_max=R.u_max, slew=R.slew,
                     res_s=cfg["res_s"], res_q=cfg["res_q"], tau_f=cfg["tau_f"], **kw)
    info = {"tvlqr_seconds": time.time() - t0, "rollout_end_err": end_err, "max_u_nominal": float(np.abs(us).max()),
            "max_gain": float(np.abs(ks).max())}
    return fw, info


def metrics(rig: ql.Rig, cfg: dict, ts, xs, us, ph, st, t_settle: float) -> dict:
    n = rig.n
    if not np.all(np.isfinite(xs)):
        return {"ok": False}
    phi = xs[:, 1:1 + n]
    dev = np.degrees(np.max(np.abs(phi), axis=1))
    t_catch = st.get("t_catch", math.nan)
    sel = ts >= t_settle
    near = np.where((dev < 5.0) & (ts > cfg["t_on"]))[0]
    return {
        "ok": bool(dev[-1] < 0.5 and np.max(np.abs(xs[:, 0])) <= cfg["travel"]),
        "t_catch": float(t_catch),
        "t_within_5deg": float(ts[near[0]]) if len(near) else math.nan,
        "settled_dev_deg": float(np.max(dev[sel])),
        "final_dev_deg": float(dev[-1]),
        "final_s": float(xs[-1, 0]),
        "peak_u": float(np.max(np.abs(us))),
        "peak_s": float(np.max(np.abs(xs[:, 0]))),
        "settled_s": float(np.max(np.abs(xs[sel, 0]))),
    }


def run_swingup(plant, fw, cfg, t_end):
    step, _ = plant.steps()
    return ql.closed_loop(step, fw, plant.rig.hanging(), t_end)


def balance_start(rig: ql.Rig, cfg: dict) -> np.ndarray:
    z = np.zeros(rig.nx)
    z[1:1 + rig.n] = np.radians(cfg["balance_th0"])
    return z


def main(argv):
    kind = argv[0]
    cfg = CFG[kind]
    R = cfg["rig"]
    plant = ql.Plant(R)
    k_lqr, p_lqr, poles, open_poles = ql.dlqr(plant, cfg["qdiag"], cfg["r"])
    print(f"[{kind}] open-loop poles {np.round(np.sort(open_poles.real), 2)}")
    print(f"[{kind}] LQR K {np.round(k_lqr, 2)}; closed-loop (equivalent) poles {np.round(np.sort(poles.real), 2)}")
    traj = trajectory(plant, cfg, HERE / f"_traj_{kind}.npz", "--fresh" in argv)
    fw, info = firmware(plant, cfg, traj, k_lqr, p_lqr)
    print(f"[{kind}] TVLQR {info['tvlqr_seconds']:.1f} s, roll-out end error {info['rollout_end_err']:.2e}, "
          f"max nominal input {info['max_u_nominal']:.2f}, max gain {info['max_gain']:.0f}")
    t_end = cfg["t_on"] + cfg["t_s"] + cfg["after"]
    t_settle = cfg["t_on"] + cfg["t_s"] + 1.5
    out = run_swingup(plant, fw, cfg, t_end)
    m = metrics(R, cfg, *out, t_settle)
    print(f"[{kind}] swing-up (design model):", {k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()})
    ts, xs, us, ph, st = out

    robust = {}
    cases = {
        "link masses +5 %": dict(rig=dataclasses.replace(R, m=[v * 1.05 for v in R.m])),
        "link masses -5 %": dict(rig=dataclasses.replace(R, m=[v * 0.95 for v in R.m])),
        "link lengths +1 %": dict(rig=dataclasses.replace(R, L=[v * 1.01 for v in R.L])),
        "joint friction x3": dict(rig=dataclasses.replace(R, b_joint=3 * R.b_joint)),
        "base friction x2": dict(rig=dataclasses.replace(R, b_base=2 * R.b_base)),
        "base mass +10 %": dict(rig=dataclasses.replace(R, m_base=1.1 * R.m_base)),
        "delay 1 ms": dict(delay=1),
        "delay 2 ms": dict(delay=2),
        "quantised encoders": dict(quant=True),
    }
    for name, c in cases.items():
        p2 = ql.Plant(c["rig"]) if "rig" in c else plant
        fw2 = dataclasses.replace(fw, delay=c.get("delay", 0), quant=c.get("quant", False))
        mm = metrics(R, cfg, *run_swingup(p2, fw2, cfg, t_end), t_settle)
        robust[name] = mm
        print(f"   {name}: ok={mm.get('ok')} catch={mm.get('t_catch', math.nan):.3f} "
              f"settled={mm.get('settled_dev_deg', math.nan):.3f} deg peak u={mm.get('peak_u', math.nan):.2f}")
    # balance scenario: from the disturbed upright, balance only
    fwb = dataclasses.replace(fw, balance_only=True)
    step, _ = plant.steps()
    # largest tip push (50 ms) the balance loop recovers from rest upright (back inside 1 deg, on the rail), bisection
    lo, hi = 0.0, 5.0 if R.kind == "cart" else 0.5
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        f = lambda t, a=mid: a if 1.0 <= t < 1.05 else 0.0  # noqa: E731
        o = ql.closed_loop(step, fwb, np.zeros(R.nx), 8.0, force=f)
        ok = (np.all(np.isfinite(o[1])) and np.degrees(np.max(np.abs(o[1][-1, 1:1 + R.n]))) < 1.0
              and np.max(np.abs(o[1][:, 0])) < cfg["travel"])
        lo, hi = (mid, hi) if ok else (lo, mid)
    print(f"[{kind}] largest 50 ms tip push recovered from rest upright: {lo:.4f}")
    push_amp = round(0.5 * lo, 3 if R.kind == "cart" else 4)
    if cfg["variant"] != "full":
        # the balance model is shared by both controllers: the push of the full-travel design
        push_amp = json.loads((HERE / f"design_{R.kind}.json").read_text())["balance"]["push"]["amplitude"]
    pt0, pdur = cfg["push"]["t_start"], cfg["push"]["duration"]
    fpush = lambda t: push_amp if pt0 <= t < pt0 + pdur else 0.0  # noqa: E731
    tb, xb, ub, phb, stb = ql.closed_loop(step, fwb, balance_start(R, cfg), cfg["balance_t"], force=fpush)
    mb = metrics(R, cfg, tb, xb, ub, phb, stb, cfg["balance_t"] - 1.0)
    mb["push_peak_dev_deg"] = float(np.degrees(np.max(np.abs(xb[tb >= pt0, 1:1 + R.n]))))
    print(f"[{kind}] balance from {cfg['balance_th0']} deg, push {push_amp}:", {k: round(v, 4) if isinstance(v, float) else v for k, v in mb.items()})
    bal_cases = {}
    for name, kw in {"delay 2 ms": dict(delay=2), "delay 5 ms": dict(delay=5), "quantised encoders": dict(quant=True)}.items():
        o = ql.closed_loop(step, dataclasses.replace(fwb, **kw), balance_start(R, cfg), cfg["balance_t"], force=fpush)
        bal_cases[name] = metrics(R, cfg, *o, cfg["balance_t"] - 1.0)
        print(f"   balance {name}: ok={bal_cases[name].get('ok')} settled={bal_cases[name].get('settled_dev_deg', math.nan):.3f} deg "
              f"peak u={bal_cases[name].get('peak_u', math.nan):.2f}")

    # the energy series of the design run (for the docs)
    el = np.array([np.array(plant.link_energy(x)).ravel() for x in xs[::10]])
    # free swing of the twin
    z0 = np.zeros(R.nx)
    z0[:R.nq] = cfg["free_z0"]
    tf = np.round(np.arange(0.25, cfg["free_t"] + 1e-9, 0.25), 6)
    zf = ql.free_swing(plant, z0, np.concatenate([[0.0], tf]))[1:]

    upe = R.upright_pe()
    h_hang = [-(sum(R.L[:i]) + R.c[i]) for i in range(R.n)]
    dz = {
        "kind": R.kind, "variant": cfg["variant"], "prefix": cfg["prefix"], "travel": cfg["travel"], "key": kind, "ctrl_block": cfg["ctrl_block"], "monitor_block": cfg["monitor_block"],
        "L": R.L, "m_model": R.m, "J_model": R.J, "b_joint": R.b_joint, "m_base": R.m_base, "b_base": R.b_base,
        "u_max": R.u_max, "slew": R.slew, "s_max": R.s_max, "arm_l": R.arm_l, "J_hub": R.J_hub,
        "Jp_model": [[0.5 * mi * R.r_link**2, mi * (li**2 / 12 + R.r_link**2 / 4), mi * (li**2 / 12 + R.r_link**2 / 4)]
                     for mi, li in zip(R.m, R.L)],
        "Jp_arm": [0.5 * R.m_base * R.r_arm**2, R.m_base * (R.arm_l**2 / 12 + R.r_arm**2 / 4),
                   R.m_base * (R.arm_l**2 / 12 + R.r_arm**2 / 4)],
        "J_axis": R.J_hub + R.m_base * (R.arm_l**2 / 12 + R.r_arm**2 / 4) + R.m_base * (R.arm_l / 2) ** 2,
        "h_hang": h_hang, "upright_pe": upe, "E_up": sum(upe),
        "res_s": cfg["res_s"], "res_q": cfg["res_q"], "tau_f": cfg["tau_f"],
        "t_on": cfg["t_on"], "t_s": cfg["t_s"], "t_end": t_end, "dt_tab": cfg["dt_tab"], "catch_tol": cfg["catch_tol"],
        "qdiag": cfg["qdiag"], "r": cfg["r"], "k_lqr": k_lqr.tolist(), "p_lqr": p_lqr.tolist(),
        "poles": [[float(p.real), float(p.imag)] for p in poles],
        "open_poles": sorted(float(p.real) for p in open_poles),
        "tab_x": fw.tab_x.tolist(), "tab_u": fw.tab_u.tolist(), "tab_k": fw.tab_k.tolist(), "ff_form": cfg["ff_form"],
        "tab_v": fw.tab_v.tolist() if fw.tab_v is not None else None,
        "collocation": {"log": traj["log"], "seconds": traj["seconds"], "u_lim": cfg["u_lim"], "s_lim": cfg["s_lim"],
                        "slew_lim": cfg["slew_lim"], "w_du": cfg["w_du"]},
        "tvlqr": info, "metrics": m, "robustness": robust,
        "balance": {"th0": cfg["balance_th0"], "t_end": cfg["balance_t"], "metrics": mb, "cases": bal_cases,
                    "push": cfg["push"] | {"amplitude": push_amp}, "max_push": lo},
        "free": {"z0": cfg["free_z0"], "t_end": cfg["free_t"], "t": tf.tolist(), "z": zf[:, :R.nq].tolist()},
        "design_run": {"t": ts[::10].tolist(), "z": xs[::10].tolist(), "u": us[::10].tolist(), "phase": ph[::10].tolist(),
                       "E": el.tolist()},
        "design_balance": {"t": tb[::10].tolist(), "z": xb[::10].tolist(), "u": ub[::10].tolist()},
    } | BOND
    path = HERE / f"design_{kind}.json"
    path.write_text(json.dumps(dz) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
