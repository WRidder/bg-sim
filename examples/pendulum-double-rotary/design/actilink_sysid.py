# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6"]
# ///
"""System identification of the ACTILINK rotary double pendulum from logged experiments.

    uv run examples/pendulum-double-rotary/design/actilink_sysid.py <csv_dir> [--truth] [--out fits.json]

Every fit reads one CSV per experiment, `<csv_dir>/<model>.csv`, in the layout of bg-sim's run
export (`t` first, then one column per signal id). On the rig, log the same quantities under the
same names (the drive's objects in brackets, DS402 over EtherCAT):

| experiment (model)        | columns                                                                         |
|---------------------------|---------------------------------------------------------------------------------|
| actilink-sysid-current    | CurrentLoop/uq, CurrentLoop/iq (the drive's 16 kHz trace: q voltage and current), Wm/y (motor speed) |
| actilink-sysid-friction   | Cmd/w_cmd (target velocity 0x60FF), DriveLoop/tau_ref (torque actual 0x6077 in N m), CurrentLoop/uq, CurrentLoop/iq, Wm/y |
| actilink-sysid-gear       | MotorEnc/y (motor encoder, rad at the motor), OutputEnc/y (output encoder), DriveLoop/tau_ref |
| actilink-sysid-swing1/2   | Enc1A/y or Enc2A/y (the AS5048 register as an angle in [0, 2 pi))               |
| actilink-sysid-encoder    | OutputEnc/y (20-bit output encoder, read at the cycle), EncBench/y (bench AS5048)   |
| actilink-sysid-chirp      | DriveLoop/tau_ref, OutputEnc/y                                                  |

Known inputs (not identified here): the gear ratio N (datasheet), the drive's loop periods, the
link masses (scale) and COM distances (balance point), the AS5048 calibration at the hanging rest.
With `--truth` the fits are compared with the parameters the bg-sim models were built with.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import actilink_io as aio
import actilink_lib as al

TS_I = 1.0 / 16000.0
TS_C = 1.0e-3


def held(t: np.ndarray, y: np.ndarray, tq: np.ndarray) -> np.ndarray:
    """Value of a held (zero-order) signal at the instants tq: the last sample at or before tq."""
    idx = np.searchsorted(t, tq, side="right") - 1
    return y[np.clip(idx, 0, len(y) - 1)]


# ------------------------------------------------------------------ 1. winding (current step)
def fit_current(t, c, t0: float, t1: float) -> dict:
    """ZOH model of the q winding between current-loop ticks k and k+1 (u_q held, speed ~ const):
    i[k+1] = a i[k] + b (u[k] - ke w[k]); R = (1 - a)/b, L = -R Ts / ln a."""
    k0, k1 = math.ceil(t0 / TS_I), math.floor(t1 / TS_I)
    tk = np.arange(k0, k1) * TS_I + 0.5 * TS_I
    i = held(t, c["CurrentLoop/iq"], tk)  # sampled at tick k (before the new voltage)
    u = held(t, c["CurrentLoop/uq"], tk)  # applied from tick k
    w = np.interp(tk, t, c["Wm/y"]) if "Wm/y" in c else np.zeros_like(tk)
    A = np.column_stack([i[:-1], u[:-1], -w[:-1]])
    sol, *_ = np.linalg.lstsq(A, i[1:], rcond=None)
    a, b, bke = sol
    R = (1 - a) / b
    L = -R * TS_I / math.log(a)
    return {"R_phase": float(R), "L_phase": float(L), "ke_fit": float(bke / b) if b else math.nan}


# ------------------------------------------------------------------ 2. friction and back-EMF
def stribeck_total(p, w):
    fc, fs, vs, fv = p
    return np.sign(w) * (fc + (fs - fc) * np.exp(-(w / vs) ** 2)) + fv * w


def fit_friction(t, c, N: float, R_phase: float | None = None) -> dict:
    wc = c["Cmd/w_cmd"]
    edges = np.where(np.abs(np.diff(wc)) > 1e-9)[0]
    starts = np.r_[edges + 1]
    levels = []
    for s, e in zip(starts, np.r_[starts[1:], len(t)], strict=True):
        if abs(wc[s]) < 1e-9:
            continue
        ts, te = t[s], t[e - 1]
        win = (t >= ts + 0.5 * (te - ts)) & (t <= te)
        levels.append((float(wc[s]), float(np.mean(c["DriveLoop/tau_ref"][win])), float(np.mean(c["CurrentLoop/uq"][win])),
                       float(np.mean(c["CurrentLoop/iq"][win])), float(np.mean(c["Wm/y"][win])) if "Wm/y" in c else float(wc[s]) * N))
    lv = np.array(levels)
    w, tau = lv[:, 0], lv[:, 1]
    res = least_squares(lambda p: stribeck_total(p, w) - tau, x0=[0.5 * np.max(np.abs(tau)), 0.6 * np.max(np.abs(tau)), 0.3, 0.001],
                        bounds=([0, 0, 1e-3, 0], [10, 10, 10, 1]))
    fc, fs, vs, fv = res.x
    # back-EMF: u_q = R i_q + ke w_m (per level); with R from the current step if given
    if R_phase is None:
        A = np.column_stack([lv[:, 3], lv[:, 4]])
        (_, ke), *_ = np.linalg.lstsq(A, lv[:, 2], rcond=None)
    else:
        ke = float(np.sum((lv[:, 2] - R_phase * lv[:, 3]) * lv[:, 4]) / np.sum(lv[:, 4] ** 2))
    kt_rms = 1.5 * ke * math.sqrt(2.0)
    return {"Fc": float(fc), "Fs": float(fs), "vs": float(vs), "Fv": float(fv), "ke": float(ke), "kt_rms": float(kt_rms),
            "levels": lv[:, :2].tolist(), "rms_residual": float(np.sqrt(np.mean(res.fun**2)))}


# ------------------------------------------------------------------ 3. gear stiffness and backlash
def gear_curve(p, phi):
    k1, k3, tk, bl = p[:4]
    b = 0.5 * bl
    eps = 0.2 * b + 1e-9
    a1, a2 = phi - b, -phi - b
    dz = 0.5 * (a1 + np.sqrt(a1 * a1 + eps * eps)) - 0.5 * (a2 + np.sqrt(a2 * a2 + eps * eps))
    dk = tk / k1
    return k3 * dz - (k3 - k1) * dk * np.tanh(dz / dk)


def fit_gear(t, c, N: float) -> dict:
    tq = np.arange(0.0, t[-1], 2.5e-4) + 1.25e-4
    th_m = held(t, c["MotorEnc/y"], tq) / N
    th_o = held(t, c["OutputEnc/y"], tq)
    tau = held(t, c["DriveLoop/tau_ref"], tq)
    phi = th_m - th_o
    # direction of the rotor motion from a smoothed derivative of the deflection
    k = 40
    dphi = np.convolve(np.gradient(phi, tq), np.ones(k) / k, mode="same")
    use = np.abs(tau) > 0.02
    tau_peak = float(np.max(np.abs(tau)))

    def resid(p):
        k1, k3, tk, bl, fc, ph0 = p
        model = gear_curve((k1, k3, tk, bl), phi - ph0) + fc * np.tanh(dphi / 2e-4)
        return (model - tau)[use]

    x0 = [0.5 * tau_peak / max(np.ptp(phi) / 2, 1e-6), 2 * tau_peak / max(np.ptp(phi) / 2, 1e-6), 0.3 * tau_peak, 0.5 * np.ptp(phi) * 0.3, 0.1, 0.0]
    res = least_squares(resid, x0=x0, bounds=([10, 10, 0.01, 0, 0, -0.01], [1e6, 1e6, 100, 0.05, 5, 0.01]), x_scale="jac")
    k1, k3, tk, bl, fc, ph0 = res.x
    return {"k1": float(k1), "k3": float(k3), "tau_knee": float(tk), "backlash": float(bl), "backlash_arcmin": float(bl / al.ARCMIN),
            "Fc_motor_side": float(fc), "offset": float(ph0), "rms_residual": float(np.sqrt(np.mean(res.fun**2)))}


# ------------------------------------------------------------------ 4./5. pendulum swings
def unwrap_register(y: np.ndarray) -> np.ndarray:
    return np.unwrap(y)


def fit_swing(t, c, sig: str, m: float, mc: float, t_skip: float = 0.05) -> dict:
    """Free oscillation J th'' = -m g c sin(th - th_h) - Fc tanh(th'/eps) - Fv th' fitted to the
    unwrapped AS5048 reading (sampled at the cycle). m c from the scale and the balance point;
    identified: w0^2 = m g c / J, Fc/J, Fv/J, the hanging reading th_h and the release angle."""
    tk = np.arange(1, int(t[-1] / TS_C)) * TS_C + 0.5 * TS_C
    y = unwrap_register(held(t, c[sig], tk))
    sel = tk >= t_skip
    tk, y = tk[sel], y[sel]
    th_h0 = float(np.mean(y[-2000:]))

    def simulate(p):
        w02, fcj, fvj, th_h, a0 = p
        f = lambda _t, x: [x[1], -w02 * math.sin(x[0] - th_h) - fcj * math.tanh(x[1] / al.V_EPS_J) - fvj * x[1]]
        sol = solve_ivp(f, (0.0, tk[-1]), [a0, 0.0], t_eval=tk, rtol=1e-9, atol=1e-11, method="LSODA")
        return sol.y[0]

    x0 = [25.0, 0.05, 1e-3, th_h0, float(y[0])]
    # a coarse grid on w0^2 first (the period), then the full least squares
    best = None
    for w02 in np.linspace(5, 80, 76):
        r = simulate([w02, 0.02, 0.0, th_h0, y[0]])[: min(3000, len(y))] - y[: min(3000, len(y))]
        cost = float(np.sum(r * r))
        if best is None or cost < best[0]:
            best = (cost, w02)
    x0[0] = best[1]
    res = least_squares(lambda p: simulate(p) - y, x0=x0, x_scale=[10, 0.01, 1e-3, 0.01, 0.1],
                        bounds=([1, 0, 0, -10, -20], [500, 5, 1, 20, 20]))
    w02, fcj, fvj, th_h, a0 = res.x
    J = m * al.G * mc / m / w02 if m > 0 else math.nan
    J = al.G * mc / w02
    return {"w0": float(math.sqrt(w02)), "period": float(2 * math.pi / math.sqrt(w02)), "J_pivot": float(J),
            "Fc": float(fcj * J), "Fv": float(fvj * J), "hang_reading": float(th_h), "release": float(a0 - th_h),
            "rms_residual_deg": float(math.degrees(np.sqrt(np.mean(res.fun**2))))}


# ------------------------------------------------------------------ 6. encoder bench
def fit_encoder(t, c) -> dict:
    """Bench AS5048 against the 20-bit output encoder, both read in the 1 kHz cycle (the AS5048 a
    latency `lat` before the cycle). At constant speed w: d = y_as - th_ref = c0 - w lat + INL(th)
    + noise, INL = A1 sin th + B1 cos th + A2 sin 2th + B2 cos 2th: linear least squares; the two
    directions separate the latency from the offset."""
    tk = np.arange(1, int(t[-1] / TS_C)) * TS_C + 0.5 * TS_C
    ref = np.unwrap(held(t, c["OutputEnc/y"], tk))
    yas = np.unwrap(held(t, c["EncBench/y"], tk))
    w = np.gradient(ref, TS_C)
    w = np.convolve(w, np.ones(21) / 21, mode="same")
    use = np.abs(w) > 0.5 * np.max(np.abs(w))
    use[:50] = False
    use[-50:] = False
    d = (yas - ref)[use]
    th = ref[use]
    A = np.column_stack([np.ones_like(th), -w[use], np.sin(th), np.cos(th), np.sin(2 * th), np.cos(2 * th)])
    sol, *_ = np.linalg.lstsq(A, d - np.round((d - np.median(d)) / (2 * np.pi)) * 2 * np.pi, rcond=None)
    r = d - A @ sol
    r = r - np.mean(r)
    q = 2 * np.pi / 2**14
    noise = math.sqrt(max(float(np.var(r)) - q * q / 12.0, 0.0))
    return {"latency_ms": float(sol[1] * 1e3), "inl1_deg": float(math.degrees(math.hypot(sol[2], sol[3]))),
            "inl1_phase_deg": float(math.degrees(math.atan2(sol[3], sol[2]))),
            "inl2_deg": float(math.degrees(math.hypot(sol[4], sol[5]))),
            "inl2_phase_deg": float(math.degrees(math.atan2(sol[5], sol[4]))), "noise_deg": float(math.degrees(noise))}


# ------------------------------------------------------------------ 7. chirp: rotor inertia
def rig_inertia_locked(size: str | None = None) -> float:
    """Inertia of the arm with the pendulum locked hanging about the vertical axis, from the rig's
    geometry and masses (the design model's mass matrix at q = [0, pi, 0]); on the rig, the masses
    from the scale, the COM distances from the balance point and the link inertias from the swing tests."""
    import casadi as ca

    rg = al.rig()
    q = ca.SX.sym("q", 3)
    qd = ca.SX.sym("qd", 3)
    kin, _, _, _ = al.lagrangian(rg, q, qd, 0.0)
    m = ca.Function("m", [q], [ca.hessian(kin, qd)[0]])
    return float(np.array(m([0.0, math.pi, 0.0]))[0, 0])


def fit_chirp(t, c, fric: dict, j_rig: float) -> dict:
    """Torque chirp on the arm, pendulum locked: (J_rig + J_out) a = tau - F(w), with the friction F
    of the staircase (Coulomb, Stribeck, viscous) and the speed and acceleration from the 20-bit output
    encoder (Savitzky-Golay, 41 ms window). Least squares for J_out and a viscous correction dFv."""
    from scipy.signal import savgol_filter

    tk = np.arange(1, int(t[-1] / TS_C)) * TS_C + 0.5 * TS_C
    tau = held(t, c["DriveLoop/tau_ref"], tk)
    th = held(t, c["OutputEnc/y"], tk)
    w = savgol_filter(th, 41, 3, deriv=1, delta=TS_C)
    a = savgol_filter(th, 41, 3, deriv=2, delta=TS_C)
    tau = savgol_filter(tau, 41, 3)  # the same smoothing on the input (zero lag, matched)
    f = (fric["Fc"] + (fric["Fs"] - fric["Fc"]) * np.exp(-(w / fric["vs"]) ** 2)) * np.tanh(w / 0.01) + fric["Fv"] * w
    use = (np.abs(w) > 0.2) & (tk > 0.3) & (tk < tk[-1] - 0.3)  # away from the stick phases at the reversals
    A = np.column_stack([a[use], w[use]])
    (j_tot, dfv), *_ = np.linalg.lstsq(A, (tau - f)[use], rcond=None)
    r = (tau - f)[use] - A @ np.array([j_tot, dfv])
    return {"J_total": float(j_tot), "J_rig": float(j_rig), "J_out": float(j_tot - j_rig), "dFv": float(dfv),
            "rms_residual": float(np.sqrt(np.mean(r * r))), "arm_ptp_deg": float(math.degrees(np.ptp(th)))}


# ------------------------------------------------------------------ truth and driver
def truth(size: str) -> dict:
    dr = al.drive(size)
    rg = al.rig()
    b = rg["bodies"]
    l1 = rg["link_l"]
    m12 = b[1].m + b[2].m
    mc1 = b[1].m * b[1].c + b[2].m * (l1 + b[2].c)
    j1 = b[1].J[2] + b[1].m * b[1].c**2 + b[2].J[2] + b[2].m * (l1 + b[2].c) ** 2
    j2 = b[2].J[2] + b[2].m * b[2].c**2
    return {
        "R_phase": dr.R, "L_phase": dr.L, "kt_rms": dr.kt_rms, "ke": dr.r_gy,
        "Fc": dr.Fc_in + dr.Fc_out, "Fs": dr.Fs_in + dr.Fc_out, "vs": dr.vs_in, "Fv": dr.Fv_in + dr.Fv_out,
        "k1": dr.k1, "k3": dr.k3, "tau_knee": dr.tau_knee, "backlash": dr.backlash, "Fc_motor_side": dr.Fc_in,
        "swing1": {"m": m12, "mc": mc1, "J_pivot": j1, "Fc": rg["Fc_j"], "Fv": rg["Fv_j"]},
        "swing2": {"m": b[2].m, "mc": b[2].m * b[2].c, "J_pivot": j2, "Fc": rg["Fc_j"], "Fv": rg["Fv_j"]},
        "J_out": dr.J_out,
    }


def run_all(csv_dir: Path, size: str, zcal: dict, lat: float, inl1, noise: float) -> dict:
    tr = truth(size)
    dr = al.drive(size)
    fits = {}

    def load(name):
        p = csv_dir / f"{name}.csv"
        return aio.read_csv(p) if p.is_file() else (None, None)

    t, c = load("actilink-sysid-current")
    if t is not None:
        fits["current"] = fit_current(t, c, 0.0105, 0.039)
    t, c = load("actilink-sysid-friction")
    if t is not None:
        fits["friction"] = fit_friction(t, c, dr.N, fits.get("current", {}).get("R_phase"))
    t, c = load("actilink-sysid-gear")
    if t is not None:
        fits["gear"] = fit_gear(t, c, dr.N)
    for k, sig in ((1, "Enc1A/y"), (2, "Enc2A/y")):
        t, c = load(f"actilink-sysid-swing{k}")
        if t is not None:
            s = tr[f"swing{k}"]
            fits[f"swing{k}"] = fit_swing(t, c, sig, s["m"], s["mc"])
    t, c = load("actilink-sysid-encoder")
    if t is not None:
        fits["encoder"] = fit_encoder(t, c)
    t, c = load("actilink-sysid-chirp")
    if t is not None:
        fr = fits.get("friction") or {"Fc": tr["Fc"], "Fs": tr["Fs"], "vs": tr["vs"], "Fv": tr["Fv"]}
        fits["chirp"] = fit_chirp(t, c, fr, rig_inertia_locked())
    # comparison with the model's own parameters
    cmp = []

    def row(group, name, fit, true, tol):
        err = (fit - true) / true if true != 0 else fit - true
        cmp.append({"group": group, "name": name, "fit": fit, "true": true, "rel_err": err, "tol": tol, "ok": abs(err) <= tol})

    if "current" in fits:
        row("winding", "R_phase [Ohm]", fits["current"]["R_phase"], tr["R_phase"], 0.03)
        row("winding", "L_phase [H]", fits["current"]["L_phase"], tr["L_phase"], 0.05)
    if "friction" in fits:
        f = fits["friction"]
        row("friction", "kt [N m/A_rms] (back-EMF)", f["kt_rms"], tr["kt_rms"], 0.03)
        row("friction", "Fc [N m]", f["Fc"], tr["Fc"], 0.10)
        row("friction", "Fs [N m]", f["Fs"], tr["Fs"], 0.10)
        row("friction", "vs [rad/s]", f["vs"], tr["vs"], 0.25)
        row("friction", "Fv [N m s/rad]", f["Fv"], tr["Fv"], 0.15)
    if "gear" in fits:
        g = fits["gear"]
        row("gear", "k1 [N m/rad]", g["k1"], tr["k1"], 0.15)
        row("gear", "k3 [N m/rad]", g["k3"], tr["k3"], 0.10)
        row("gear", "backlash [rad]", g["backlash"], tr["backlash"], 0.15)
    for k in (1, 2):
        if f"swing{k}" in fits:
            s = fits[f"swing{k}"]
            row(f"swing{k}", "J_pivot [kg m^2]", s["J_pivot"], tr[f"swing{k}"]["J_pivot"], 0.02)
            row(f"swing{k}", "Fc joint [N m]", s["Fc"], tr[f"swing{k}"]["Fc"], 0.25)
    if "encoder" in fits:
        e = fits["encoder"]
        row("encoder", "latency [ms]", e["latency_ms"], lat * 1e3, 0.10)
        row("encoder", "INL 1st harmonic [deg]", e["inl1_deg"], math.degrees(inl1[0]), 0.10)
        row("encoder", "INL 2nd harmonic [deg]", e["inl2_deg"], math.degrees(inl1[2]), 0.15)
        row("encoder", "noise [deg rms]", e["noise_deg"], math.degrees(noise), 0.10)
    if "chirp" in fits:
        row("chirp", "J_out [kg m^2]", fits["chirp"]["J_out"], tr["J_out"], 0.15)
    return {"fits": fits, "compare": cmp}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    dz = json.loads((HERE / "actilink_design.json").read_text(encoding="utf-8"))
    enc = dz["enc"]
    result = run_all(args.csv_dir, dz["size"], dz["zcal"], enc["lat_a"], enc["inl1"], enc["sigma"])
    for r in result["compare"]:
        print(f"  {r['group']:9s} {r['name']:28s} fit {r['fit']:.6g}  model {r['true']:.6g}  "
              f"error {100 * r['rel_err']:+.1f} % (tol {100 * r['tol']:.0f} %) {'ok' if r['ok'] else 'FAIL'}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
