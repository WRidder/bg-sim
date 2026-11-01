# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6"]
# ///
"""Sizing and control design of the ACTILINK-JD rotary double pendulum (models `actilink-*`).

    uv run examples/pendulum-double-rotary/design/actilink_design.py [--size JD08] [--no-sizing] [--no-sims]

1. Sizing: for JD08, JD10 and JD12 the same swing-up problem (Hermite-Simpson collocation from
   hanging to upright in T_s, min integral of torque^2, arm within +-theta_max) on the rigid design
   model with that drive's reflected rotor inertia and friction; peak/RMS torque, speed,
   acceleration and the tilting moment on the output bearing along it; the balance LQR's margins
   (gain, phase and delay margin at the drive input, the EtherCAT delay included); backlash, mass.
2. Design for the chosen size: the swing-up trajectory on finer grids, the TVLQR table, the
   discrete balance LQR (1 kHz, one-cycle EtherCAT delay as a state), the alpha-beta-gamma
   estimator gains, the current-loop and CSV velocity-loop gains, the AS5048 calibration offsets.
3. Closed-loop checks on the Python twin with every firmware replica (balance from a disturbed
   upright, swing-up + catch, push on link 2; SPI and I2C chains; JD08 against JD10 backlash) and
   the twin's open-loop free swing for the comparison with the bond graph.

Writes `design/actilink_design.json` (read by actilink_build.py and actilink_finish.py) and
`design/actilink_sizing.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import actilink_lib as al
import rotary_lib as rl

CFG = {
    "t_s": 3.0,  # swing-up duration [s]
    "theta_max": 3.0,  # arm travel bound of the trajectory [rad]
    "u_traj": 6.0,  # torque bound of the trajectory [N m] (well inside every size's peak torque)
    "nk": [60, 120, 240],
    "guess_amp": 0.4,
    "guess_freq": 0.8,
    "rate_weight": 0.02,
    "smooth": 0.01,
    "dt_tab": 0.01,
    # balance LQR: [arm, link1, link2, arm rate, link1 rate, link2 rate], R in 1/(N m)^2
    "qdiag": [2.0, 400.0, 400.0, 0.5, 4.0, 4.0],
    "r": 1.0,
    "qdiag_tv": [2.0, 400.0, 400.0, 0.5, 4.0, 4.0],
    "r_tv": 1.0,
    "catch_w": [0.3, 1.0, 1.0, 0.05, 0.1, 0.1],
    "catch_tol": 0.35,
    "umax": 12.0,  # command limit sent to the drive [N m] (drive clamps at its own peak too)
    # estimator: white-jerk PSD per joint [rad^2/s^5]
    "q_jerk": [1.0e5, 3.0e3, 3.0e3],
    "t_on": 1.0,
    "push_force": 0.3,  # [N] on the link-2 tip (0.4 N still recovers, 0.5 N does not)
    "push_dur": 0.05,
    "balance_start": [0.0, 0.05, -0.05],  # disturbed upright start [rad]
    "free_start": [0.2, 2.5, -0.8],
    "t_free": 3.0,
}
SIZES = ["JD08", "JD10", "JD12"]


def trajectory(plant: al.ALPlant, cfg: dict, nks: list[int], verbose=True):
    guess = rl.sim_guess(plant, cfg["t_s"], nks[0], cfg["guess_amp"], cfg["guess_freq"], cfg["u_traj"])
    kw = {"theta_max": cfg["theta_max"], "rate_weight": cfg["rate_weight"], "smooth": cfg["smooth"]}
    xs, us, um, cost = rl.swing_up(plant, cfg["t_s"], cfg["u_traj"], nks[0], guess=guess, **kw)
    if verbose:
        print(f"    nk {nks[0]}: cost {cost:.3f}", flush=True)
    for nk in nks[1:]:
        guess = rl.refine_guess(plant, cfg["t_s"], xs, us, um, nk)
        xs, us, um, cost = rl.swing_up(plant, cfg["t_s"], cfg["u_traj"], nk, guess=guess, **kw)
        if verbose:
            print(f"    nk {nk}: cost {cost:.3f}", flush=True)
    return xs, us, um, cost


def margins(plant: al.ALPlant, K: np.ndarray, Ts: float, delay: int, qdiag, r):
    """Loop broken at the drive input of the discrete LQR (with the delay states): gain margin
    (upper), phase margin, delay margin; also the closed-loop spectral radius."""
    a, b = plant.linearise(np.zeros(6), 0.0)
    _, A, B = al.dlqr_delay(a, b, Ts, qdiag, r, delay)
    w = np.logspace(-1, math.log10(math.pi / Ts * 0.999), 4000)
    n = A.shape[0]
    L = np.array([(K @ np.linalg.solve(np.exp(1j * wi * Ts) * np.eye(n) - A, B)).item() for wi in w])
    mag = np.abs(L)
    pm, wc = math.inf, math.nan
    for i in np.where(np.diff(np.sign(mag - 1.0)) != 0)[0]:
        m = abs(math.degrees(math.atan2(-np.imag(L[i]), -np.real(L[i]))))  # distance of arg L from -180 deg
        if m < pm:
            pm, wc = m, w[i]
    gm_up, gm_lo = math.inf, 0.0
    for i in np.where(np.diff(np.sign(np.imag(L))) != 0)[0]:
        if np.real(L[i]) < 0:
            g = 1.0 / abs(L[i])
            if g > 1:
                gm_up = min(gm_up, g)
            else:
                gm_lo = max(gm_lo, g)
    acl = A - B @ K.reshape(1, -1)
    return {
        "gain_margin_up_db": 20 * math.log10(gm_up) if math.isfinite(gm_up) else math.inf,
        "gain_margin_low_db": 20 * math.log10(gm_lo) if gm_lo > 0 else -math.inf,
        "phase_margin_deg": pm,
        "crossover_hz": wc / (2 * math.pi),
        "delay_margin_ms": (math.radians(pm) / wc * 1e3) if not math.isnan(wc) else math.nan,
        "spectral_radius": float(np.max(np.abs(np.linalg.eigvals(acl)))),
    }


def bearing_k(dr: al.Drive, hw: dict, mean_rpm: float, hours: float = 10000.0) -> tuple[float, float]:
    rated = float(hw["actuators"][dr.name]["speed_rated"]["value"])
    k_life = (10000.0 * rated / hours / mean_rpm) ** (1.0 / 3.0)
    k_static = {"JD08": 2.21, "JD10": 1.92, "JD12": 1.72}[dr.name]
    return k_life, k_static


def sizing(cfg: dict) -> list[dict]:
    hw = al.hardware()
    rg = al.rig()
    rows = []
    for size in SIZES:
        dr = al.drive(size, hw)
        plant = al.ALPlant(dr, rg)
        print(f"  {size}: trajectory", flush=True)
        t0 = time.time()
        xs, us, _um, cost = trajectory(plant, cfg, cfg["nk"][:2], verbose=True)
        tn = np.linspace(0, cfg["t_s"], xs.shape[1])
        acc = np.array([plant.rhs(xs[:, k], us[k])[3] for k in range(xs.shape[1])])
        tilt = np.array([plant.tilt_moment(xs[:, k], us[k]) for k in range(xs.shape[1])])
        power = us * xs[3]
        a, b = plant.linearise(np.zeros(6), 0.0)
        K, _, _ = al.dlqr_delay(a, b, 1e-3, cfg["qdiag"], cfg["r"], 1)
        mg = margins(plant, K, 1e-3, 1, cfg["qdiag"], cfg["r"])
        # mean output speed over a duty cycle: one swing-up per minute, balancing otherwise
        rms_cycle = math.sqrt(float(np.trapezoid(us**2, tn)) / 60.0)
        k_life, k_static = bearing_k(dr, hw, mean_rpm=5.0)
        tilt_rating = float(hw["actuators"][size]["tilting_moment"]["value"])
        j_total = float(plant.mass_fn(np.zeros(3))[0, 0])
        row = {
            "size": size, "ratio": dr.N, "tau_peak": dr.tau_peak, "tau_rated": dr.tau_rated,
            "w_max": dr.w_max, "J_out": dr.J_out, "J_axis_upright": j_total,
            "J_out_share": dr.J_out / j_total, "backlash_arcmin": dr.backlash / al.ARCMIN, "mass": dr.mass,
            "traj_cost": cost, "traj_tau_peak": float(np.max(np.abs(us))),
            "traj_tau_rms": math.sqrt(float(np.trapezoid(us**2, tn)) / cfg["t_s"]),
            "duty_tau_rms": rms_cycle, "traj_w_peak": float(np.max(np.abs(xs[3]))),
            "traj_acc_peak": float(np.max(np.abs(acc))), "traj_power_peak": float(np.max(np.abs(power))),
            "tilt_static": float(tilt[0]), "tilt_peak": float(np.max(tilt)), "tilt_rating": tilt_rating,
            "tilt_rating_static": tilt_rating * k_static, "tilt_rating_life": tilt_rating * k_life,
            "lqr": mg, "t_opt": time.time() - t0,
        }  # fmt: skip
        rows.append(row)
        print(f"  {size}: peak {row['traj_tau_peak']:.2f} N m, rms {row['traj_tau_rms']:.2f}, w {row['traj_w_peak']:.2f} rad/s, "
              f"tilt {row['tilt_static']:.2f}/{row['tilt_peak']:.2f} N m (rating {tilt_rating} x K), "
              f"PM {mg['phase_margin_deg']:.1f} deg, DM {mg['delay_margin_ms']:.2f} ms", flush=True)
    return rows


# ------------------------------------------------------------------ the design of the chosen size
def firmware(dr: al.Drive, cfg: dict, j_load: float) -> al.Firmware:
    hw = al.hardware()
    fw = al.Firmware(dr)
    fw.lat_a = float(hw["as5048"]["latency_spi"]["value"])
    fw.lat_b = float(hw["as5048"]["latency_i2c"]["value"])
    fw.tune_current(float(hw["drive_common"]["current_loop_bw"]["value"]))
    fw.tune_velocity(j_load, 15.0)
    return fw


def zcal(fw: al.Firmware) -> dict:
    """Calibration at the hanging rest: the mean register minus the true angle (link 1 at pi,
    link 2 at 0), i.e. zero + INL at that angle; the same sensor on both chains."""
    z1 = (fw.zero[0] + al.inl(math.pi, fw.inl1)) % al.TWO_PI
    z2 = (fw.zero[1] + al.inl(0.0, fw.inl2)) % al.TWO_PI
    return {"z1a": z1, "z2a": z2, "z1b": z1, "z2b": z2}


def design(size: str, cfg: dict) -> dict:
    hw = al.hardware()
    rg = al.rig()
    dr = al.drive(size, hw)
    plant = al.ALPlant(dr, rg)
    print(f"design {size}: trajectory", flush=True)
    xs, us, um, cost = trajectory(plant, cfg, cfg["nk"])
    qtv = np.array(cfg["qdiag_tv"], float)
    p_final = rl.lqr(plant, qtv, cfg["r_tv"])[1]
    tab_x, tab_u, tab_k = rl.tvlqr(plant, cfg["t_s"], xs, us, um, qtv, cfg["r_tv"], p_final, cfg["dt_tab"])
    a, b = plant.linearise(np.zeros(6), 0.0)
    K, _, _ = al.dlqr_delay(a, b, 1e-3, cfg["qdiag"], cfg["r"], 1)
    mg = margins(plant, K, 1e-3, 1, cfg["qdiag"], cfg["r"])
    j_load = float(plant.mass_fn(plant.hanging()[:3])[0, 0])
    fw = firmware(dr, cfg, j_load)
    sig_arm = (al.TWO_PI / 2**dr.out_bits) / math.sqrt(12)
    sig_link = math.hypot(fw.noise, (al.TWO_PI / 2**fw.bits) / math.sqrt(12))
    abg = [al.abg_gains(1e-3, s, q) for s, q in zip([sig_arm, sig_link, sig_link], cfg["q_jerk"], strict=True)]
    dz = {
        "size": size, "hw": True, "t_on": cfg["t_on"], "t_s": cfg["t_s"], "dt_tab": cfg["dt_tab"],
        "umax": cfg["umax"], "catch_w": cfg["catch_w"], "catch_tol": cfg["catch_tol"],
        "tab": np.hstack([tab_x, tab_u[:, None], tab_k]).tolist(), "K": K.tolist(),
        "abg": [g.tolist() for g in abg], "lqr_margins": mg, "traj_cost": cost,
        "traj": {"xs": xs.tolist(), "us": us.tolist(), "um": um.tolist()},
        "fw": {"kp_i": fw.kp_i, "ki_i": fw.ki_i, "kp_w": fw.kp_w, "ki_w": fw.ki_w, "j_load": j_load},
        "enc": {"lat_a": fw.lat_a, "lat_b": fw.lat_b, "sigma": fw.noise, "inl1": list(fw.inl1), "inl2": list(fw.inl2),
                "zero1": fw.zero[0], "zero2": fw.zero[1]},
        "zcal": zcal(fw), "cfg": cfg,
    }  # fmt: skip
    print(f"  LQR K = {np.round(K, 3)}, margins {mg}", flush=True)
    return dz


def ctrl_cfg(dz: dict, *, balance_only: bool, th1_init: float, bus: int = 0, t_on=None) -> dict:
    zc = dz["zcal"]
    return {
        "Ts": 1e-3, "delay": 1, "t_on": dz["t_on"] if t_on is None else t_on, "t_s": dz["t_s"], "dt_tab": dz["dt_tab"],
        "tab": np.array(dz["tab"]), "K": np.array(dz["K"]), "x_ref": np.zeros(6), "catch_w": np.array(dz["catch_w"]),
        "catch_tol": dz["catch_tol"], "umax": dz["umax"], "abg": [np.array(g) for g in dz["abg"]],
        "balance_only": balance_only, "th1_init": th1_init,
        "z1": zc["z1b"] if bus else zc["z1a"], "z2": zc["z2b"] if bus else zc["z2a"],
    }  # fmt: skip


def make_fw(dz: dict, dr: al.Drive) -> al.Firmware:
    fw = al.Firmware(dr)
    for k in ("kp_i", "ki_i", "kp_w", "ki_w"):
        setattr(fw, k, dz["fw"][k])
    fw.lat_a, fw.lat_b = dz["enc"]["lat_a"], dz["enc"]["lat_b"]
    return fw


def summarize(rec: dict, t_push: float | None = None) -> dict:
    t = rec["t"]
    x = rec["x"]
    phi = np.stack([x[:, 1], x[:, 1] + x[:, 2]], axis=1)
    phi_w = (phi + math.pi) % (2 * math.pi) - math.pi
    dev = np.max(np.abs(phi_w), axis=1)
    mode = rec["mode"]
    out = {
        "tau_peak": float(np.max(np.abs(rec["tau_cmd"]))),
        "iq_peak": float(np.max(np.abs(rec["iq"]))),
        "uq_peak": float(np.max(np.abs(rec["uq"]))),
        "arm_max": float(np.max(np.abs(x[:, 0]))),
        "gear_defl_max": float(np.max(np.abs(x[:, 6] - x[:, 0]))),
        "final_dev_deg": math.degrees(float(dev[-1])),
        "t_catch": float(t[np.argmax(mode >= 2)]) if np.any(mode >= 2) else math.nan,
    }
    tail = t >= t[-1] - 1.0
    out["tail_dev_deg"] = math.degrees(float(np.max(dev[tail])))
    out["tail_arm_mean"] = float(np.mean(x[tail, 0]))
    out["tail_arm_p2p_deg"] = math.degrees(float(np.ptp(x[tail, 0])))
    if t_push is not None:
        post = t >= t_push
        out["push_peak_deg"] = math.degrees(float(np.max(np.abs(phi_w[post, 1]))))
        outside = np.where((dev > math.radians(1.0)) & post)[0]
        out["t_recover"] = float(t[outside[-1]] - t_push) if len(outside) else 0.0
    return out


def python_runs(dz: dict, cfg: dict, quick: bool = False) -> dict:
    rg = al.rig()
    res = {}
    for size in (dz["size"],) + (() if quick else ("JD08",)):
        dr = al.drive(size)
        twin = al.ALTwin(dr, rg)
        fw = make_fw(dz, dr)
        for bus in (0, 1):
            if size != dz["size"] and bus == 1:
                continue
            tag = f"{size}-{'spi' if bus == 0 else 'i2c'}"
            t0 = time.time()
            x0 = twin.state(np.array(cfg["balance_start"]))
            rec = al.simulate_closed_loop(twin, fw, ctrl_cfg(dz, balance_only=True, th1_init=0.0, bus=bus, t_on=0.0),
                                          x0, 5.0, bus=bus, seed=3)
            res[f"balance-{tag}"] = summarize(rec)
            print(f"  balance {tag}: {res[f'balance-{tag}']} ({time.time() - t0:.0f} s)", flush=True)
            t_push = 2.0
            dist = lambda t, tp=t_push: cfg["push_force"] if tp <= t < tp + cfg["push_dur"] else 0.0
            x0 = twin.state(np.zeros(3))
            rec = al.simulate_closed_loop(twin, fw, ctrl_cfg(dz, balance_only=True, th1_init=0.0, bus=bus, t_on=0.0),
                                          x0, 6.0, bus=bus, dist=dist, seed=4)
            res[f"push-{tag}"] = summarize(rec, t_push)
            print(f"  push {tag}: {res[f'push-{tag}']}", flush=True)
            if size == dz["size"] and bus == 0:
                np.savez(HERE / "_actilink_push.npz", **rec)
    dr = al.drive(dz["size"])
    twin = al.ALTwin(dr, rg)
    fw = make_fw(dz, dr)
    t0 = time.time()
    x0 = twin.state(np.array([0.0, math.pi, 0.0]))
    rec = al.simulate_closed_loop(twin, fw, ctrl_cfg(dz, balance_only=False, th1_init=math.pi), x0,
                                  dz["t_on"] + dz["t_s"] + 3.0, bus=0, seed=5)
    res["swingup"] = summarize(rec)
    np.savez(HERE / "_actilink_swingup.npz", **rec)
    print(f"  swing-up: {res['swingup']} ({time.time() - t0:.0f} s)", flush=True)
    return res


def free_swing(dz: dict, cfg: dict) -> dict:
    """Twin + drive in CST with a zero target (current loop holding i_q = 0), from rest."""
    rg = al.rig()
    dr = al.drive(dz["size"])
    twin = al.ALTwin(dr, rg)
    fw = make_fw(dz, dr)
    x0 = twin.state(np.array(cfg["free_start"]))
    rec = al.simulate_closed_loop(twin, fw, None, x0, cfg["t_free"], record_every=16, energy=True, noise=False)
    t = rec["t"]
    idx = [int(np.argmin(np.abs(t - tt))) for tt in np.arange(0.25, cfg["t_free"] + 1e-9, 0.25)]
    x = rec["x"]
    return {
        "t": [float(t[i]) for i in idx],
        "q": [[float(v) for v in x[i, 0:3]] for i in idx],
        "phi": [[float(x[i, 1]), float(x[i, 1] + x[i, 2])] for i in idx],
        "defl": [float(x[i, 6] - x[i, 0]) for i in idx],
        "energy_drift": float(np.max(np.abs(rec["estore"] + rec["loss"] - rec["pin"] - (rec["estore"][0] + rec["loss"][0] - rec["pin"][0])))),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="JD10")
    ap.add_argument("--no-sizing", action="store_true")
    ap.add_argument("--no-sims", action="store_true")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    cfg = CFG
    if not args.no_sizing:
        rows = sizing(cfg)
        (HERE / "actilink_sizing.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8", newline="\n")
    dz = design(args.size, cfg)
    dz["free"] = free_swing(dz, cfg)
    print(f"  free swing samples written; twin energy drift {dz['free']['energy_drift']:.2e} J", flush=True)
    if not args.no_sims:
        dz["python_runs"] = python_runs(dz, cfg, quick=args.quick)
    path = HERE / "actilink_design.json"
    path.write_text(json.dumps(dz) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
