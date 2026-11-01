"""Reference simulations of the scenarios (book units inside, results in the bg-sim units).

Every scenario is integrated here with scipy on the reference model `f16_ref.py` with
`CLAMP_AB = True` (the bg-sim table behaviour) and the same controllers as the bg-sim models
(`fbw.py`), so the checks compare bg-sim against an independent implementation of the same
equations, and against the linear predictions where those apply.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.integrate import solve_ivp

import f16_ref as F
import f16_si as SI

RTOD = 180.0 / math.pi
OPEN_LOOP_T_END = 15.0
OPEN_LOOP = [  # (label, xcg, deviation of alpha along the mode, mode)
    ("A30", 0.30, 0.01, "short_period"),
    ("A35", 0.35, 1.0e-3, "unstable"),
    ("A38", 0.38, 1.0e-4, "unstable"),
]


def mode_vector(tr, which):
    lam = np.array([complex(*l) for l in tr["eigvals"]])
    vec = np.array(tr["eigvecs_re"]) + 1j * np.array(tr["eigvecs_im"])
    if which == "unstable":
        k = int(np.argmax(lam.real))
    else:  # the short period: the complex pair with the largest |lambda|
        cand = [k for k in range(len(lam)) if lam[k].imag > 1e-9]
        k = max(cand, key=lambda i: abs(lam[i]))
    v = vec[:, k] / vec[1, k]      # alpha component 1
    return lam[k], v


def x13_from_lon(tr, dlon):
    """Trim plus a deviation of (Vt, alpha, theta, q, h, pow)."""
    x = np.zeros(13)
    x[0], x[1], x[4], x[11], x[12] = tr["vt"], tr["alpha"], tr["theta"], tr["h"], tr["power"]
    for k, idx in enumerate((0, 1, 4, 7, 11, 12)):
        x[idx] += dlon[k]
    return x


def simulate(rhs, x0, t_end, t_eval, max_step=0.01):
    sol = solve_ivp(rhs, (0.0, t_end), x0, method="LSODA", t_eval=t_eval, rtol=1e-10, atol=1e-10,
                    max_step=max_step)
    assert sol.success, sol.message
    return sol


def open_loop(design):
    F.CLAMP_AB = True
    out = []
    for label, xcg, dalpha, which in OPEN_LOOP:
        tr = design["trims"][f"{xcg:.2f}"]
        lam, v = mode_vector(tr, which)
        dlon = (dalpha * v).real
        x0 = x13_from_lon(tr, dlon)
        u = [tr["throttle"], tr["el"], 0.0, 0.0]

        def rhs(t, x, u=u, xcg=xcg):
            return F.f16(x, u, xcg)[0]

        t_eval = np.round(np.arange(0.0, OPEN_LOOP_T_END + 1e-9, 0.25), 10)
        sol = simulate(rhs, x0, OPEN_LOOP_T_END, t_eval)
        alpha_deg = sol.y[1] * RTOD
        q_deg = sol.y[7] * RTOD
        theta = sol.y[4]
        growth = [float(sol.y[7][k] / (theta[k] - tr["theta"])) if abs(theta[k] - tr["theta"]) > 0 else None
                  for k in range(len(t_eval))]
        # the linear prediction of the same initial condition
        lin_alpha = [float((dalpha * v[1] * np.exp(lam * t)).real + tr["alpha"]) * RTOD for t in t_eval]
        lin_q = [float((dalpha * v[3] * np.exp(lam * t)).real) * RTOD for t in t_eval]
        pose, P, power = SI.initial_state(x0)
        out.append({
            "label": label, "xcg": xcg, "lambda": [lam.real, lam.imag], "dalpha": dalpha,
            "x0": x0.tolist(), "start_pose": pose, "start_P": P.tolist(), "start_power": power,
            "el": tr["el"], "throttle": tr["throttle"], "theta0": tr["theta"],
            "t": t_eval.tolist(), "alpha_deg": alpha_deg.tolist(), "q_deg": q_deg.tolist(),
            "theta_deg": (theta * RTOD).tolist(), "vt": (sol.y[0] * SI.FT).tolist(), "h": (sol.y[11] * SI.FT).tolist(),
            "growth": growth, "lin_alpha_deg": lin_alpha, "lin_q_deg": lin_q,
        })
        print(f"open loop {label}: lambda {lam:.5f}, growth q/dtheta at 3 s {growth[12]:.6f}")
    return out


FT_S = SI.FT
# Closed-loop scenarios (xcg = 0.38, the statically unstable airframe).
FBW_POINT = (400.0, 25000.0)        # ft/s, ft: the low-qbar corner of the envelope (qbar 84 psf, M 0.39)
FBW_FROZEN_POINT = (1000.0, 2000.0)  # the gains of this fast point (qbar 1100 psf), frozen, fly the slow one
FBW_STEP = (1.0, 4.0, 5.0)          # q_cmd step: on at 1 s, off at 4 s, 5 deg/s
FBW_T_END = 8.0
ENV_POINT = (900.0, 5000.0)         # M 0.82: fast enough for the 9 g limit to matter
ENV_RAMP = (1.0, 0.5)               # full aft stick, ramped in from 1 s over 0.5 s; throttle to 1.0 at 1 s
ENV_T_END = 12.0
PIO_POINT = (500.0, 15000.0)
PIO_PILOT = {"gain_per_s": 3.0, "delay": 0.25, "amp": 7.0}   # q_cmd = 3/s x attitude error; 0.25 s delay
PIO_COMP = {"rate": 60.0, "k": 0.5, "tf": 0.01}
PIO_T_END = 10.0
PIO_Q_PER_STICK = 40.0
# Commands change over short ramps instead of steps: a step that pushes a saturation (the servo
# rate limit, the stick limit, the engine gearing knee) across its corner at the same instant
# makes the event handling of bg-sim chatter at that instant (W206, the event limit). FAST is
# short against every time constant of the loop, so the responses are those of a step.
FAST = 0.05            # s, rise time of the q_cmd steps and of the pilot target
THROTTLE_RAMP = 0.2    # s, throttle to full afterburner


def ramp(t, t0, tau):
    """0 before t0, 1 after t0 + tau, linear in between (the stdlib Ramp block)."""
    return min(1.0, max(0.0, (t - t0) / tau))


def _start(cfg):
    import closedloop as CL
    tr = CL.trim(cfg)
    x = np.zeros(13)
    x[0], x[1], x[4], x[11], x[12] = cfg.vt, tr["alpha"], tr["theta"], cfg.h, tr["power"]
    pose, P, power = SI.initial_state(x)
    mach, qbar = F.adc(cfg.vt, cfg.h)
    return tr, {"start_pose": pose, "start_P": P.tolist(), "start_power": power, "el0": tr["el"],
                "throttle0": tr["throttle"], "theta0": tr["theta"], "alpha0_deg": tr["alpha"] * RTOD,
                "mach0": mach, "qbar0_pa": qbar * SI.PSF, "vt0": cfg.vt * FT_S, "h0": cfg.h * FT_S}


def _series(r, keys, every=5):
    return {k: [float(v) for v in r[k][::every]] for k in keys}


KEYS = ("t", "alpha", "q", "nz", "theta", "vt", "h", "el", "el_rate", "u", "q_cmd", "stick", "comp")


def closed_loop(design):
    import closedloop as CL
    import fbw
    des = design["fbw"]
    out = {}
    # ---- FBW: scheduled vs frozen gains at the slow point
    t0, t1, a = FBW_STEP
    qstep = (lambda t: a * (ramp(t, t0, FAST) - ramp(t, t1, FAST)))
    vt_f, h_f = FBW_FROZEN_POINT
    mach_f, qbar_f = F.adc(vt_f, h_f)
    frozen = {k: fbw.gain(des, k, qbar_f * SI.PSF, mach_f) for k in ("Ka", "Kq", "Ki")}
    cases = []
    for label, fr in (("Sched", None), ("Frozen", frozen)):
        cfg = CL.Config(vt=FBW_POINT[0], h=FBW_POINT[1], t_end=FBW_T_END, mode="q", q_cmd=qstep, frozen=fr)
        tr, st = _start(cfg)
        r = CL.run(cfg, des)
        cases.append({"label": label, "frozen": fr, "xi0": r["xi0"], **st, **_series(r, KEYS)})
        print(f"fbw {label}: q max {max(r['q']):.3f}, q at 2 s {r['q'][200]:.3f}")
    out["fbw"] = {"point": FBW_POINT, "frozen_point": FBW_FROZEN_POINT, "step": FBW_STEP, "t_end": FBW_T_END,
                  "cases": cases}
    # ---- envelope protection: full aft stick, limiter on / off
    t_r, d_r = ENV_RAMP
    stick = (lambda t: 0.0 if t < t_r else min(1.0, (t - t_r) / d_r))
    cases = []
    for label, lim in (("Protected", True), ("Unprotected", False)):
        cfg = CL.Config(vt=ENV_POINT[0], h=ENV_POINT[1], t_end=ENV_T_END, mode="g", stick=stick, limiter=lim)
        tr, st = _start(cfg)
        cfg.throttle = (lambda t, thr=tr["throttle"]: thr + (1.0 - thr) * ramp(t, t_r, THROTTLE_RAMP))
        r = CL.run(cfg, des)
        cases.append({"label": label, "limiter": lim, "xi0": r["xi0"], **st, **_series(r, KEYS)})
        print(f"envelope {label}: alpha max {max(r['alpha']):.2f}, nz max {max(r['nz']):.3f}")
    out["envelope"] = {"point": ENV_POINT, "ramp": ENV_RAMP, "t_end": ENV_T_END, "cases": cases}
    # ---- PIO: aggressive pilot, plain rate limit vs phase-compensated
    cases = []
    p = PIO_PILOT
    for label, comp in (("Plain", None), ("Comp", PIO_COMP)):
        cfg = CL.Config(vt=PIO_POINT[0], h=PIO_POINT[1], t_end=PIO_T_END, mode="q", limiter=True, comp=comp,
                        q_per_stick=PIO_Q_PER_STICK)
        tr, st = _start(cfg)
        th0 = tr["theta"] * RTOD
        cfg.pilot = {"gain": p["gain_per_s"] / PIO_Q_PER_STICK, "delay": p["delay"],
                     "target": (lambda t, th0=th0: th0 + p["amp"] * ramp(t, 1.0, FAST))}
        r = CL.run(cfg, des)
        th = np.array(r["theta"]) - th0 - p["amp"]
        win = {}
        for a0, b0 in ((2, 4), (4, 6), (6, 8), (8, 10)):
            sl = slice(int(a0 / 0.01), int(b0 / 0.01))
            win[f"{a0}-{b0}"] = float(th[sl].max() - th[sl].min())
        cases.append({"label": label, "compensated": comp is not None, "xi0": r["xi0"], "theta_err_pp": win, **st, **_series(r, KEYS)})
        print(f"pio {label}: theta error peak-to-peak per 2 s window {win}")
    out["fast"] = FAST
    out["throttle_ramp"] = THROTTLE_RAMP
    out["pio"] = {"point": PIO_POINT, "pilot": PIO_PILOT, "comp": PIO_COMP, "t_end": PIO_T_END,
                  "q_per_stick": PIO_Q_PER_STICK, "cases": cases}
    return out


def run(design):
    return {"open_loop": open_loop(design), **closed_loop(design)}
