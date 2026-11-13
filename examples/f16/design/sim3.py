"""Three-axis closed loop of the `f16-sim` model: the nonlinear reference and its linearisation.

The book's F-16 (`f16_ref`, bg-sim table clamping) with the same blocks as the bg-sim model, one
function per block so each can be compared with its `.jl` source:

    PitchCommand   stick -> g-command with turn compensation, +9/-3 g and alpha limiter
    PitchFBW       u = Ka (alpha - alpha_ref) + Kq (q - kff q_cmd) + xi        (library/PitchFBW.jl)
    LateralFBW     roll-rate command about the velocity vector, yaw damper, ARI, sideslip command
    StabComp       phase-compensated rate limiter ahead of the stabilator servo (below)
    actuators      travel limit, 20.2 rad/s lag, rate limit (stabilator, ailerons, rudder)
    F16Engine      the book's power-level lag (inside f16_ref, state 13)

State: the book's 13 (ft units) + the three servo positions (deg) + the pitch integrator xi_q,
the roll integrator xi_p, the sideslip integrator xi_b (deg), the washout state xw (deg/s) and the
two states of the stabilator's rate-limit compensator (deg): 22 states. Angles of the laws in deg, rates in deg/s, as in the blocks.

`run` integrates with fixed-step RK4 (1 ms); the inputs (stick, pedals, throttle, rudder kick)
are functions of time built from the same 0.05 s ramps as the model's stimulus. `linearise`
differentiates the right-hand side numerically at a trim point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

import f16_ref as F
import f16_si as SI
import fbw

RTOD = 180.0 / math.pi
G0_SI = SI.G0                      # 9.805416 m/s^2: the book's 32.17 ft/s^2
NX = 22
I_EL, I_AIL, I_RDR, I_XQ, I_XP, I_XB, I_XW, I_CY, I_CF = 13, 14, 15, 16, 17, 18, 19, 20, 21

# ---- actuators (Stevens & Lewis, Section 3.6 / Table 3.6-? : first-order 20.2 rad/s lags)
ACT = {"el": {"pos": 25.0, "rate": 60.0, "w": 20.2},
       "ail": {"pos": 21.5, "rate": 80.0, "w": 20.2},
       "rdr": {"pos": 30.0, "rate": 120.0, "w": 20.2}}

# ---- the stabilator's phase-compensated rate limiter (StabComp.jl; the one of f16-pio):
#     y' = clamp(du_f/dt + (k + w k_ground) e + k2 dz(e, e0), +-rate),   e = u - y,
#     du_f/dt = (u - x_f)/tf,  x_f' = du_f/dt,   dz(e, e0) = e - clamp(e, +-e0)
# Below about 150 KEAS the pitch law's gains are large (Kq is 3.2 deg per deg/s at 80 psf), so a
# small pitch rate already asks for more than the servo's 60 deg/s. A plain rate limit then lags
# the command by up to a quarter period and the loop settles in a limit cycle, stabilator
# +-20 deg at 60 deg/s. The compensator turns round with the command, which takes that lag out.
# k must stay small (from about 2 1/s the limit cycle is back). But a stick reversal at full rate
# leaves the output up to 20 deg off the command, and at 0.5 1/s that offset would hold the
# stabilator away from the law for seconds: a take-off pitched up to 80 deg. So beyond e0 the
# pull-back is k2. On the wheels (w, only in gear.py) k_ground makes it a plain rate limit, so
# the direct stick command reaches the stabilator at once.
STAB_COMP = {"rate": 60.0, "k": 0.5, "k2": 6.0, "e0": 12.0, "k_ground": 20.0, "tf": 0.01}

# ---- pitch command (PitchCommand.jl)
NZ_PULL = 10.0         # g per unit aft stick: full aft asks for 11 g (the limiter holds 9 g)
NZ_PUSH = 4.0          # g per unit forward stick: full forward asks for -3 g
NZ_MIN = -3.0          # g, negative load-factor limit
K_NZC = 2.0            # g-error feedback of the command, in units of g0/vt: builds the load factor fast
NZC_LIM = 0.5          # g, clamp of that g error (keeps full-stick pulls from overdriving the alpha limit)
# ---- lateral law (LateralFBW.jl)
P_MAX = 240.0          # deg/s, roll-rate command at full stick, 1 g, high qbar
QBAR_FULL = 12000.0    # Pa (250 psf): the full roll rate is available above this dynamic pressure
FQ_MIN = 0.3           # the roll-rate limit never falls below 30 % of P_MAX through qbar ...
KN = 0.075             # ... and falls by 7.5 % per g above 1 g,
FN_MIN = 0.4           # to 40 % at 9 g
BETA_PER_PEDAL = 6.0   # deg of sideslip commanded by full pedal (right pedal: nose right, beta < 0)
TAU_WO = 1.0           # s, washout of the stability-axis yaw rate
KFF_P = 0.5            # share of p_cmd in the roll law's proportional path


@dataclass
class Config:
    vt: float = 500.0                 # ft/s, trim
    h: float = 10000.0                # ft, trim
    xcg: float = 0.35
    t_end: float = 10.0
    dt: float = 0.001
    out_every: float = 0.01
    stick_p: object = None            # callable t -> -1..1 (aft +)
    stick_r: object = None            # callable t -> -1..1 (right +)
    pedal: object = None              # callable t -> -1..1 (right +)
    throttle: object = None           # callable t -> 0..1 (default: trim)
    rdr_kick: object = None           # callable t -> deg added to the rudder command
    limiter: float = 1.0
    turn_comp: float = 1.0
    roll_law: float = 1.0
    yaw_damper: float = 1.0
    beta_hold: float = 1.0
    ari: float = 1.0
    vv_roll: float = 1.0
    extra: dict = field(default_factory=dict)


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def table(des, name, qbar_pa, mach):
    """A scheduled gain: the bg-sim Lookup2D, bilinear over (qbar, Mach), edge values held."""
    return F.interp2(qbar_pa, mach, np.array(des["qbar_pa"]), np.array(des["mach"]),
                     np.array(des[name]).T, False, False)


def ari_gain(lat, alpha_deg):
    """The ARI gain over alpha: the bg-sim Lookup1D (edge values held)."""
    return F.interp1(alpha_deg, np.array(lat["ari_alpha"]), np.array(lat["ari"]), False)


def air(x):
    """F16AirData: Mach, qbar (psf), gamma (rad)."""
    vt, alpha, beta, phi, theta = x[0], x[1], x[2], x[3], x[4]
    mach, qbar = F.adc(vt, x[11])
    u, v, w = vt * math.cos(alpha) * math.cos(beta), vt * math.sin(beta), vt * math.sin(alpha) * math.cos(beta)
    hdot = u * math.sin(theta) - v * math.sin(phi) * math.cos(theta) - w * math.cos(phi) * math.cos(theta)
    gamma = math.asin(_clamp(hdot / vt, -1.0, 1.0))
    return mach, qbar, gamma


def pitch_command(cfg, stick, vt_si, alpha_deg, nz, gamma, phi, theta):
    """PitchCommand.jl: q_cmd (deg/s) and the parts the block outputs."""
    lim = fbw.ALPHA_MAX, fbw.NZ_MAX, fbw.K_ALIM, fbw.K_GLIM
    cphi = math.cos(phi)
    cg = math.cos(gamma) * cphi
    tc = cfg.turn_comp * ((1.0 / cphi - 1.0) if cphi >= 0.5 else max(2.0 * cphi, 0.0))
    nz_stick = 1.0 + (NZ_PULL * stick if stick >= 0.0 else NZ_PUSH * stick) + tc
    k = G0_SI / vt_si * RTOD
    dn_cmd = nz_stick - cg                       # load factor asked for above the path's 1 g
    dn = nz - math.cos(theta) * cphi             # the same, measured (zero in steady straight flight)
    q_stick = k * (dn_cmd + K_NZC * min(max(dn_cmd - dn, -NZC_LIM), NZC_LIM))
    q_alpha = lim[2] * (lim[0] - alpha_deg)
    q_g = k * (lim[1] - cg) + lim[3] * (lim[1] - nz)
    q_neg = k * (NZ_MIN - cg) + lim[3] * (NZ_MIN - nz)
    if cfg.limiter > 0.5:
        q_cmd = max(min(q_stick, q_alpha, q_g), q_neg)
    else:
        q_cmd = q_stick
    return q_cmd, q_stick, nz_stick


def roll_limit(qbar_pa, nz):
    fq = _clamp(qbar_pa / QBAR_FULL, FQ_MIN, 1.0)
    fn = _clamp(1.0 - KN * (nz - 1.0), FN_MIN, 1.0)
    return P_MAX * fq * fn


def lateral(cfg, g, X, stick_r, pedal, alpha_deg, beta_deg, p_deg, r_deg, nz, qbar_pa, k_ari):
    """LateralFBW.jl: aileron and rudder commands (deg) and the state derivatives."""
    xp, xb, xw = X[I_XP], X[I_XB], X[I_XW]
    a = alpha_deg / RTOD
    ca = cfg.vv_roll * math.cos(a) + (1.0 - cfg.vv_roll)
    sa = cfg.vv_roll * math.sin(a)
    ps = p_deg * ca + r_deg * sa
    rs = r_deg * ca - p_deg * sa
    p_lim = roll_limit(qbar_pa, nz)
    p_cmd = p_lim * stick_r
    ail_raw = cfg.roll_law * g["Kp"] * (ps - KFF_P * p_cmd) + xp
    ail = _clamp(ail_raw, -ACT["ail"]["pos"], ACT["ail"]["pos"])
    dxp = cfg.roll_law * g["Kip"] * (ps - p_cmd) + (ail - ail_raw) / fbw.T_AW
    beta_cmd = -BETA_PER_PEDAL * pedal
    r_wo = rs - xw
    dxw = r_wo / TAU_WO
    rdr_raw = (cfg.ari * k_ari * ail + cfg.yaw_damper * g["Kr"] * r_wo
               + cfg.beta_hold * g["Kb"] * (beta_deg - beta_cmd) + xb)
    rdr = _clamp(rdr_raw, -ACT["rdr"]["pos"], ACT["rdr"]["pos"])
    dxb = cfg.beta_hold * g["Kib"] * (beta_deg - beta_cmd) + (rdr - rdr_raw) / fbw.T_AW
    return ail, rdr, dxp, dxb, dxw, {"ps": ps, "rs": rs, "p_lim": p_lim, "p_cmd": p_cmd, "beta_cmd": beta_cmd}


def stab_comp(u, y, xf, w):
    """StabComp.jl: the rates of its output y and of its filter state xf."""
    c = STAB_COMP
    du = (u - xf) / c["tf"]
    e = u - y
    pull = (c["k"] + w * c["k_ground"]) * e + c["k2"] * (e - _clamp(e, -c["e0"], c["e0"]))
    return _clamp(du + pull, -c["rate"], c["rate"]), du


def servo(name, u, x):
    a = ACT[name]
    return _clamp(a["w"] * (_clamp(u, -a["pos"], a["pos"]) - x), -a["rate"], a["rate"])


def gains(des, lat, qbar_pa, mach):
    g = {k: table(des, k, qbar_pa, mach) for k in ("Ka", "Kq", "Ki")}
    g.update({k: table(lat, k, qbar_pa, mach) for k in ("Kp", "Kip", "Kr", "Kb", "Kib")})
    return g


def rhs(cfg, des, lat, X, inp, alpha_ref):
    """dX/dt and the recorded quantities. `inp` = (stick_p, stick_r, pedal, throttle, kick)."""
    stick_p, stick_r, pedal, thr, kick = inp
    x13 = X[:13]
    el, ail_x, rdr_x = X[I_EL], X[I_AIL], X[I_RDR]
    xd, nz = F.f16(x13, [thr, el, ail_x, rdr_x], cfg.xcg)
    mach, qbar_psf, gamma = air(x13)
    qbar_pa = qbar_psf * SI.PSF
    vt_si = x13[0] * SI.FT
    alpha_deg, beta_deg = x13[1] * RTOD, x13[2] * RTOD
    p_deg, q_deg, r_deg = x13[6] * RTOD, x13[7] * RTOD, x13[8] * RTOD
    g = gains(des, lat, qbar_pa, mach)
    q_cmd, q_stick, nz_stick = pitch_command(cfg, stick_p, vt_si, alpha_deg, nz, gamma, x13[3], x13[4])
    u_raw = g["Ka"] * (alpha_deg - alpha_ref) + g["Kq"] * (q_deg - fbw.KFF * q_cmd) + X[I_XQ]
    u = _clamp(u_raw, -fbw.ACT_POS, fbw.ACT_POS)
    dxq = g["Ki"] * (q_deg - q_cmd) + (u - u_raw) / fbw.T_AW
    k_ari = ari_gain(lat, alpha_deg)
    ail, rdr, dxp, dxb, dxw, lat_out = lateral(cfg, g, X, stick_r, pedal, alpha_deg, beta_deg, p_deg, r_deg,
                                                nz, qbar_pa, k_ari)
    dX = np.empty(NX)
    dX[:13] = xd
    dX[I_CY], dX[I_CF] = stab_comp(u, X[I_CY], X[I_CF], 0.0)
    dX[I_EL] = servo("el", X[I_CY], el)
    dX[I_AIL] = servo("ail", ail, ail_x)
    dX[I_RDR] = servo("rdr", rdr + kick, rdr_x)
    dX[I_XQ], dX[I_XP], dX[I_XB], dX[I_XW] = dxq, dxp, dxb, dxw
    aux = {"nz": nz, "mach": mach, "qbar": qbar_pa, "gamma": gamma, "q_cmd": q_cmd, "q_stick": q_stick,
           "u": u, "ail_cmd": ail, "rdr_cmd": rdr, "k_ari": k_ari, **lat_out, **g}
    return dX, aux


def trim(vt, h, xcg):
    from f16_lin import trim_level
    return trim_level(vt, h, xcg, guess=(0.3, -1.0, 0.05))


def start_state(tr):
    """Trimmed level flight; the pitch integrator holds the trim elevator (alpha_ref = trim alpha)."""
    X = np.zeros(NX)
    X[0], X[1], X[4], X[11], X[12] = tr["vt"], tr["alpha"], tr["theta"], tr["h"], tr["power"]
    X[I_EL] = tr["el"]
    X[I_XQ] = tr["el"]
    X[I_CY] = tr["el"]
    X[I_CF] = tr["el"]
    return X


def _f(fn, t, default):
    return default if fn is None else fn(t)


def inputs_at(cfg, t, thr0):
    return (_f(cfg.stick_p, t, 0.0), _f(cfg.stick_r, t, 0.0), _f(cfg.pedal, t, 0.0),
            _f(cfg.throttle, t, thr0), _f(cfg.rdr_kick, t, 0.0))


REC = ("t", "alpha", "beta", "p", "q", "r", "phi", "theta", "psi", "vt", "h", "nz", "el", "ail", "rdr",
       "ps", "rs", "p_lim", "p_cmd", "q_cmd", "pow", "mach", "gamma", "north", "east")


def run(cfg: Config, des, lat):
    F.CLAMP_AB = True
    tr = trim(cfg.vt, cfg.h, cfg.xcg)
    X = start_state(tr)
    alpha_ref = tr["alpha"] * RTOD
    thr0 = tr["throttle"]
    n = int(round(cfg.t_end / cfg.dt))
    every = int(round(cfg.out_every / cfg.dt))
    rec = {k: [] for k in REC}
    h = cfg.dt
    for k in range(n + 1):
        t = k * h
        inp = inputs_at(cfg, t, thr0)
        k1, aux = rhs(cfg, des, lat, X, inp, alpha_ref)
        if k % every == 0:
            vals = {"t": t, "alpha": X[1] * RTOD, "beta": X[2] * RTOD, "p": X[6] * RTOD, "q": X[7] * RTOD,
                    "r": X[8] * RTOD, "phi": X[3] * RTOD, "theta": X[4] * RTOD, "psi": X[5] * RTOD,
                    "vt": X[0] * SI.FT, "h": X[11] * SI.FT, "nz": aux["nz"], "el": X[I_EL], "ail": X[I_AIL],
                    "rdr": X[I_RDR], "ps": aux["ps"], "rs": aux["rs"], "p_lim": aux["p_lim"],
                    "p_cmd": aux["p_cmd"], "q_cmd": aux["q_cmd"], "pow": X[12], "mach": aux["mach"],
                    "gamma": aux["gamma"] * RTOD, "north": X[9] * SI.FT, "east": X[10] * SI.FT}
            for key in REC:
                rec[key].append(float(vals[key]))
        if k == n:
            break
        # The stimulus is evaluated at the stage times, as the bg-sim model sees its ramps.
        k2, _ = rhs(cfg, des, lat, X + h / 2 * k1, inputs_at(cfg, t + h / 2, thr0), alpha_ref)
        k3, _ = rhs(cfg, des, lat, X + h / 2 * k2, inputs_at(cfg, t + h / 2, thr0), alpha_ref)
        k4, _ = rhs(cfg, des, lat, X + h * k3, inputs_at(cfg, t + h, thr0), alpha_ref)
        X = X + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    rec["trim"] = {k: float(v) for k, v in tr.items() if isinstance(v, (int, float))}
    return rec


LAT = (2, 3, 6, 8, I_AIL, I_RDR, I_XP, I_XB, I_XW)          # beta, phi, p, r, servos, law states
LAT_NAMES = ["beta", "phi", "p", "r", "ail", "rdr", "xi_p", "xi_b", "xw"]


def linearise(cfg, des, lat, tr, idx=LAT, eps=1e-6):
    """A = d(dX/dt)/dX over the states `idx` at the trim point (sticks centred)."""
    F.CLAMP_AB = True
    X0 = start_state(tr)
    alpha_ref = tr["alpha"] * RTOD
    inp = (0.0, 0.0, 0.0, tr["throttle"], 0.0)
    A = np.zeros((len(idx), len(idx)))
    for j, k in enumerate(idx):
        e = eps * max(1.0, abs(X0[k]))
        Xp, Xm = X0.copy(), X0.copy()
        Xp[k] += e
        Xm[k] -= e
        A[:, j] = (rhs(cfg, des, lat, Xp, inp, alpha_ref)[0][list(idx)]
                   - rhs(cfg, des, lat, Xm, inp, alpha_ref)[0][list(idx)]) / (2 * e)
    return A


def dutch_roll(A):
    """The dutch roll of a lateral model whose first four states are (beta, phi, p, r): the
    complex pair (below the servo's 20 rad/s) whose eigenvector is most sideslip and yaw rate."""
    lam, vec = np.linalg.eig(A)
    best, score = None, -1.0
    for k, l in enumerate(lam):
        if l.imag <= 1e-6 or abs(l) > 15.0:
            continue
        v = vec[:, k]
        s = (abs(v[0]) + abs(v[3])) / (abs(v[0]) + abs(v[2]) + abs(v[3]) + 1e-12)
        if s > score:
            best, score = l, s
    if best is None:
        return None
    return {"zeta": float(-best.real / abs(best)), "wn": float(abs(best)), "re": float(best.real),
            "im": float(best.imag), "beta_share": float(score)}
