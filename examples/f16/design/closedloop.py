"""Nonlinear closed-loop reference: the book's F-16 (f16_ref, bg-sim table clamping) with the
same command path, fly-by-wire law, actuator, rate-limit compensation and pilot model as the
bg-sim models. Fixed-step RK4 (1 ms); the pilot's delay reads a stored history, like the bg-sim
TransportDelay block (stored every 1 ms, linear interpolation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

import f16_ref as F
import f16_si as SI
import fbw

RTOD = 180.0 / math.pi
G = F.G_FT


@dataclass
class Config:
    xcg: float = 0.38
    vt: float = 600.0           # ft/s, trim
    h: float = 10000.0          # ft, trim
    t_end: float = 10.0
    dt: float = 0.001
    mode: str = "q"             # "q": q_cmd(t) given; "g": stick(t) -> g-command path
    q_cmd: object = None        # callable t -> deg/s (mode q)
    stick: object = None        # callable t -> stick (mode g, no pilot)
    limiter: bool = True
    throttle: object = None     # callable t -> throttle, default trim
    frozen: dict | None = None  # fixed gains instead of the schedule
    pilot: dict | None = None   # {"gain": deg->stick, "delay": s, "target": callable t -> theta deg}
    comp: dict | None = None    # phase-compensated rate limiter {"rate": deg/s, "k": 1/s, "tf": s}
    q_per_stick: float = 40.0   # mode q with a pilot: pitch-rate command per unit stick (deg/s)
    out_every: float = 0.01
    extra: dict = field(default_factory=dict)


def trim(cfg):
    from f16_lin import trim_level
    return trim_level(cfg.vt, cfg.h, cfg.xcg, guess=(0.3, -1.0, 0.05))


def air(x):
    vt, alpha, beta, phi, theta = x[0], x[1], x[2], x[3], x[4]
    mach, qbar = F.adc(vt, x[11])
    ca, cb = math.cos(alpha), math.cos(beta)
    u, v, w = vt * ca * cb, vt * math.sin(beta), vt * math.sin(alpha) * cb
    # gamma: climb rate / vt
    hdot = u * math.sin(theta) - v * math.sin(phi) * math.cos(theta) - w * math.cos(phi) * math.cos(theta)
    gamma = math.asin(max(-1.0, min(1.0, hdot / vt)))
    return mach, qbar, gamma


def gains(cfg, des, qbar_psf, mach):
    if cfg.frozen is not None:
        return cfg.frozen["Ka"], cfg.frozen["Kq"], cfg.frozen["Ki"]
    qpa = qbar_psf * SI.PSF
    return (fbw.gain(des, "Ka", qpa, mach), fbw.gain(des, "Kq", qpa, mach), fbw.gain(des, "Ki", qpa, mach))


def command(cfg, des, t, x, nz, stick):
    """The GCommand block: stick -> nz -> q, with the min-select limiter."""
    mach, qbar, gamma = air(x)
    vt, alpha, phi = x[0], x[1] * RTOD, x[3]
    cg = math.cos(gamma) * math.cos(phi)
    nz_stick = 1.0 + fbw.NZ_PER_STICK * stick
    q_stick = G / vt * (nz_stick - cg) * RTOD
    q_alim = fbw.K_ALIM * (fbw.ALPHA_MAX - alpha)
    q_glim = G / vt * (fbw.NZ_MAX - cg) * RTOD + fbw.K_GLIM * (fbw.NZ_MAX - nz)
    if cfg.limiter:
        return min(q_stick, q_alim, q_glim), (q_stick, q_alim, q_glim)
    return q_stick, (q_stick, q_alim, q_glim)


def run(cfg: Config, des):
    F.CLAMP_AB = True
    tr = trim(cfg)
    x = np.zeros(13)
    x[0], x[1], x[4], x[11], x[12] = cfg.vt, tr["alpha"], tr["theta"], cfg.h, tr["power"]
    mach0, qbar0, _ = air(x)
    Ka, Kq, Ki = gains(cfg, des, qbar0, mach0)
    xi0 = tr["el"] - Ka * tr["alpha"] * RTOD          # u = el_trim at q = 0, q_cmd = 0
    # state: x13, act, xi, comp y, comp filter state
    X = np.concatenate([x, [tr["el"], xi0, tr["el"], tr["el"]]])
    thr0 = tr["throttle"]
    hist_t, hist_th = [], []
    n_steps = int(round(cfg.t_end / cfg.dt))
    every = int(round(cfg.out_every / cfg.dt))
    rec = {k: [] for k in ("t", "alpha", "q", "nz", "theta", "vt", "h", "el", "el_rate", "u", "q_cmd",
                           "stick", "xi", "mach", "qbar", "comp", "gamma")}
    state = {"stick": 0.0}

    def pilot_stick(t):
        p = cfg.pilot
        td = t - p["delay"]
        if td <= 0 or not hist_t:
            th = hist_th[0] if hist_th else tr["theta"] * RTOD
        else:
            th = float(np.interp(td, hist_t, hist_th))
        s = p["gain"] * (p["target"](t) - th)     # gain in stick per deg
        return max(-1.0, min(1.0, s))

    def f(t, X, stick):
        x13 = X[:13]
        act, xi, cy, cf = X[13], X[14], X[15], X[16]
        thr = cfg.throttle(t) if cfg.throttle else thr0
        _, nz = F.f16(x13, [thr, act, 0.0, 0.0], cfg.xcg)
        mach, qbar, gamma = air(x13)
        if cfg.mode == "q":
            if cfg.pilot:
                # pitch-rate command mode: stick -> q, through the same min-select limiter
                q_cmd = cfg.q_per_stick * stick
                if cfg.limiter:
                    _, (_, q_alim, q_glim) = command(cfg, des, t, x13, nz, 0.0)
                    q_cmd = min(q_cmd, q_alim, q_glim)
            else:
                q_cmd = cfg.q_cmd(t)
        else:
            q_cmd, _ = command(cfg, des, t, x13, nz, stick)
        Ka, Kq, Ki = gains(cfg, des, qbar, mach)
        alpha, q = x13[1] * RTOD, x13[7] * RTOD
        u = Ka * alpha + Kq * (q - fbw.KFF * q_cmd) + xi
        usat = max(-fbw.ACT_POS, min(fbw.ACT_POS, u))
        dxi = Ki * (q - q_cmd) + (usat - u) / fbw.T_AW
        if cfg.comp:
            c = cfg.comp
            du = (usat - cf) / c["tf"]                    # FilteredDerivative of the command
            dcy = max(-c["rate"], min(c["rate"], du + c["k"] * (usat - cy)))
            dcf = du
            ain = max(-fbw.ACT_POS, min(fbw.ACT_POS, cy))   # the actuator's input limit
        else:
            dcy = dcf = 0.0
            ain = usat
        dact = max(-fbw.ACT_RATE, min(fbw.ACT_RATE, fbw.ACT_W * (ain - act)))
        xd, _ = F.f16(x13, [thr, act, 0.0, 0.0], cfg.xcg)
        return np.concatenate([xd, [dact, dxi, dcy, dcf]]), (nz, q_cmd, u, dact, mach, qbar, gamma)

    t = 0.0
    for k in range(n_steps + 1):
        hist_t.append(t)
        hist_th.append(X[4] * RTOD)
        if cfg.pilot:
            stick = pilot_stick(t)
        elif cfg.stick:
            stick = cfg.stick(t)
        else:
            stick = 0.0
        k1, aux = f(t, X, stick)
        if k % every == 0:
            nz, q_cmd, u, dact, mach, qbar, gamma = aux
            for key, val in (("t", t), ("alpha", X[1] * RTOD), ("q", X[7] * RTOD), ("nz", nz),
                             ("theta", X[4] * RTOD), ("vt", X[0] * SI.FT), ("h", X[11] * SI.FT),
                             ("el", X[13]), ("el_rate", dact), ("u", u), ("q_cmd", q_cmd), ("stick", stick),
                             ("xi", X[14]), ("mach", mach), ("qbar", qbar * SI.PSF), ("comp", X[15]),
                             ("gamma", gamma * RTOD)):
                rec[key].append(float(val))
        if k == n_steps:
            break
        h = cfg.dt
        k2, _ = f(t + h / 2, X + h / 2 * k1, stick)
        k3, _ = f(t + h / 2, X + h / 2 * k2, stick)
        k4, _ = f(t + h, X + h * k3, stick)
        X = X + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t = (k + 1) * h
    rec["trim"] = {k: float(v) for k, v in tr.items() if isinstance(v, (int, float))}
    rec["xi0"] = xi0
    return rec
