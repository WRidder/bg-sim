# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13", "cvxpy>=1.5", "control>=0.10", "slycot"]
# ///
"""Plan C1: robust balance controllers of the double-cart lab rig, designed against the whole parameter box
of `realism.json` with the loop delay, the armature lag and the firmware's estimator in the loop, at 1 kHz.

    uv run examples/pendulum-double-cart-lab/design/robust_c1.py design [--only mm_lqr,gmf,hinf,mu]
    uv run examples/pendulum-double-cart-lab/design/robust_c1.py verify [--only ...] [--mixed 16]
    uv run examples/pendulum-double-cart-lab/design/robust_c1.py harness [--only ...] [--jobs 8]

Structure (every design; `robust_lin.ObserverCtrl`): the firmware's observer on the nominal sampled model,
predicting with the command it applied 2 samples ago (the EKF of lablib.setup; for analysis its steady-state
gain at the upright), and u = -K [x_hat; u_{k-1}; u_{k-2}] (6 state gains, 2 gains on its own last commands).

Models (`models()`): the truth of `robust_lin.truth_dt` (the twin linearised at the upright without the
Coulomb friction, the delay of the draw, the armature lag) at 2^8 = 256 corners of grouped factors (all link
part masses, the COM shifts, cart and rotor mass, R_m, k_t, all viscous frictions, the cable springs, the
delay 1 or 2 samples) and 64 uniform draws over the box (seeds 5000.., apart from the test's 3000-3063).

Designs:
- `nominal`: the design.json discrete LQR (Q = diag(300, 400, 400, 10, 8, 8), R = 0.3) on the EKF.
- `mm_lqr`: multi-model LQR: the 8 gains minimise the mean H2 cost (design Q and R, a 0.45 N push, a drive
  disturbance and the encoder noise as inputs) over all 320 models (the loop with delay, lag and estimator).
- `mm_lqr_wc`: the same with the worst-case cost (a smooth max, the 8-norm over the models).
- `gmf`: Glover-McFarlane loop shaping: the shaped plant W2 G W1 with the design's weights (W2 = sqrt of the
  position weights, W1 = 1 / sqrt(R)), the central controller at gamma = 1.1 gamma_min (observer form: an
  LQR-like state feedback and a robustified Kalman gain), on the nominal continuous model, implemented as the
  observer gain L and the gain K; `gmf_tuned` scales the shaping for the best worst-case disk margin.
- `hinf`: structured H-infinity: the 8 gains (on the fixed EKF) minimise the worst-case H-infinity norm of the
  weighted performance channels over the models (nonsmooth: Nelder-Mead from the MM-LQR, active model set).
- `mu`: mu-synthesis by D-K iteration with the fixed structure: the LFT of `robust_lin.build_lft` (every
  uncertain parameter a real scalar, the delay, the lag and unmodelled dynamics a complex multiplicative weight
  at the drive), K-step = the 8 gains minimising the peak of sigma(D M D^-1) over frequency with the D scales
  of the last D-step (frequency-wise optimal, complex-mu bound), D-step = the complex-mu upper bound.

Verification (`verify`): for every design the spectral radius over all models and the 64 test draws, the
disk / gain / phase / delay margins at the plant input (nominal and the worst over the models), the
integer-sample delay margin, the belt mode (softest belt, lowest damping) and the mu-analysis (RS and RP,
complex and mixed upper bounds). The results go to `design/robust_c1.json`; `harness` runs every design on
the robustness test (`balance_push`, and `swingup` with the nominal TVLQR swing-up handing over at T_s).
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import scipy.linalg as sla
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lablib as lb  # noqa: E402
import robust_lin as rl  # noqa: E402

OUT = HERE / "robust_c1.json"
TS = lb.TS
P_NOM = lb.nominal()
SPEC = lb.spec()
QD = np.array([300.0, 400.0, 400.0, 10.0, 8.0, 8.0])
RD = 0.3
KSCALE = np.array([30.0, 160.0, 330.0, 28.0, 6.6, 48.0, 1.0, 1.0])

# ----------------------------------------------------------------------------- the model set
GROUPS = {
    "link_mass": ["m_tube1", "m_tube2", "m_hub1", "m_head1", "m_hub2", "m_tip2", "m_enc_board", "m_enc_magnet", "rho_cable"],
    "com": ["com_shift1", "com_shift2"],
    "cart": ["m_cart", "J_m"],
    "R_m": ["R_m"],
    "k_t": ["k_t"],
    "friction": ["b_joint1", "b_joint2", "b_carriage", "b_motor", "b_cable", "b_cable_base"],
    "cable": ["k_cable", "k_cable_base"],
}


def corner(signs: dict) -> dict:
    p = dict(P_NOM)
    for g, s in signs.items():
        if g == "delay":
            p["delay"] = 1 if s < 0 else 2
            continue
        for k in GROUPS[g]:
            p[k] = SPEC[k]["min"] if s < 0 else SPEC[k]["max"]
    return p


def models(n_samples: int = 64, seed: int = 5000) -> list[tuple[str, dict]]:
    out = [("nominal", dict(P_NOM)), ("nominal_d1", P_NOM | {"delay": 1})]
    keys = list(GROUPS) + ["delay"]
    for i in range(2 ** len(keys)):
        signs = {k: (1 if (i >> j) & 1 else -1) for j, k in enumerate(keys)}
        out.append((f"c{i:03d}", corner(signs)))
    rng = np.random.default_rng(seed)
    for i in range(n_samples):
        out.append((f"s{i:02d}", lb.sample(rng)))
    return out


def test_draws() -> list[tuple[str, dict]]:
    import robustness as rb
    return [(lab, p) for lab, p, _ in rb.draws()]


_TRUTH: dict = {}


def truths(ms, belt=False):
    key = (tuple(l for l, _ in ms), belt)
    if key not in _TRUTH:
        _TRUTH[key] = [rl.truth_dt(p, belt=belt) for _, p in ms]
    return _TRUTH[key]


# ----------------------------------------------------------------------------- weights
# H2: w = [push (rms per sample of a 0.45 N, 40 ms push every 5 s), drive disturbance 0.1 V, the encoder
# noise (nominal: quantisation + 0.03 deg)], z = [sqrt(Q) z, sqrt(R) u]
RES_Q = 2 * math.pi / 2**14
N_TH = math.sqrt(RES_Q**2 / 12 + math.radians(P_NOM["joint_noise"]) ** 2)
N_X = P_NOM["base_res"] / math.sqrt(12)
WW_H2 = np.diag([0.45 * math.sqrt(0.04 / 5.0), 0.1, N_X, N_TH, N_TH])
WZ_H2 = np.diag(np.concatenate([np.sqrt(QD), [math.sqrt(RD)]]))
# H-infinity / mu performance: w = [0.45 N push, 0.3 V drive disturbance, noise at the worst joint noise of the
# box (0.08 deg)], z = [x, th1, th2, u] scaled per output so the nominal LQR's peak gain is 0.5 (RP < 1: no
# output's worst-case gain over the box more than twice the nominal design's)
N_TH_MAX = math.sqrt(RES_Q**2 / 12 + math.radians(SPEC["joint_noise"]["max"]) ** 2)
WW_HINF = [0.45, 0.3, N_X, N_TH_MAX, N_TH_MAX]
WZ_HINF = None          # set by calibrate_hinf()


def sel_z():
    S = np.zeros((4, 7))
    S[0, 0], S[1, 1], S[2, 2], S[3, 6] = 1.0, 1.0, 1.0, 1.0
    return S


def calibrate_hinf(ctrl=None):
    """Per-output scales: 0.5 / (the nominal LQR's peak gain from the weighted w to that output)."""
    global WZ_HINF
    ctrl = ctrl or rl.ObserverCtrl(K=rl.nominal_lqr(), L=rl.ekf_gain()).lti()
    cl = rl.closed_loop(rl.truth_dt(P_NOM), ctrl)
    F = rl.freqresp(cl.A, cl.B @ np.diag(WW_HINF), sel_z() @ cl.C, sel_z() @ cl.D @ np.diag(WW_HINF), rl.grid(300))
    peaks = np.max(np.linalg.norm(F, axis=2), axis=0)
    WZ_HINF = 0.5 / peaks
    return WZ_HINF


# ----------------------------------------------------------------------------- costs
def ctrl_of(theta, L):
    return rl.ObserverCtrl(K=np.asarray(theta) * KSCALE, L=L).lti()


def h2_costs(theta, L, Ts):
    C = ctrl_of(theta, L)
    out = []
    for T in Ts:
        cl = rl.closed_loop(T, C)
        r = rl.rho(cl)
        out.append(rl.h2(cl, WZ_H2, WW_H2) ** 2 if r < 1.0 else 1e6 * (1 + r))
    return np.array(out)


def hinf_costs(theta, L, Ts, w):
    C = ctrl_of(theta, L)
    Wz = np.diag(WZ_HINF) @ sel_z()
    Ww = np.diag(WW_HINF)
    out = []
    for T in Ts:
        cl = rl.closed_loop(T, C)
        out.append(rl.hinf(cl, Wz, Ww, w))
    return np.array(out)


def numgrad_min(fun, x0, iters=200, label=""):
    t0 = time.time()
    r = minimize(fun, x0, method="L-BFGS-B", options={"maxiter": iters, "eps": 1e-5})
    print(f"  {label}: {r.fun:.6g} after {r.nit} iterations ({time.time() - t0:.0f} s): {r.message}")
    return r.x


# ----------------------------------------------------------------------------- designs
def d_nominal():
    return {"K": np.concatenate([rl.nominal_lqr(), [0.0, 0.0]]), "L": None,
            "method": "design.json discrete LQR, Q = diag(300, 400, 400, 10, 8, 8), R = 0.3, on the EKF"}


def d_mm_lqr(worst=False):
    ms = models()
    Ts = truths(ms)
    L = rl.ekf_gain()
    th0 = np.concatenate([rl.nominal_lqr(), [0.0, 0.0]]) / KSCALE
    J0 = h2_costs(th0, L, Ts)
    print(f"  nominal LQR: H2 cost mean {J0.mean():.5g}, max {J0.max():.5g}, nominal {J0[0]:.5g}")
    if worst:
        fun = lambda th: float(np.mean((h2_costs(th, L, Ts) / J0.mean()) ** 8) ** (1 / 8))  # noqa: E731
    else:
        fun = lambda th: float(np.mean(h2_costs(th, L, Ts)) / J0.mean())  # noqa: E731
    th = numgrad_min(fun, th0, 150, "worst-case (8-norm)" if worst else "mean")
    J = h2_costs(th, L, Ts)
    print(f"  {'mm_lqr_wc' if worst else 'mm_lqr'}: H2 cost mean {J.mean():.5g}, max {J.max():.5g}, nominal {J[0]:.5g}")
    return {"K": th * KSCALE, "L": None,
            "method": ("multi-model LQR, worst case (8-norm) of the H2 cost" if worst else "multi-model LQR, mean H2 cost")
            + " over 320 models (256 corners, 64 draws) with delay, lag and the EKF in the loop; 8 gains, L-BFGS",
            "h2": {"nominal_lqr_mean": float(J0.mean()), "nominal_lqr_max": float(J0.max()), "mean": float(J.mean()),
                   "max": float(J.max())}}


def gmf_design(wx, wth, w1, gamma_factor=1.1, p=None):
    """Glover-McFarlane on the continuous nominal model: shaped plant Gs = W2 G W1, W2 = diag(wx, wth, wth) on
    the measured positions, W1 = w1. Returns (K (6,), L (6, 3), gamma_min)."""
    A, B, _ = rl.lin_cont(p or P_NOM)
    C = np.zeros((3, 6))
    C[0, 0], C[1, 1], C[2, 2] = 1.0, 1.0, 1.0
    W2 = np.diag([wx, wth, wth])
    Bs, Cs = B * w1, W2 @ C
    X = sla.solve_continuous_are(A, Bs, Cs.T @ Cs, np.eye(1))
    Z = sla.solve_continuous_are(A.T, Cs.T, Bs @ Bs.T, np.eye(3))
    gmin = math.sqrt(1 + max(np.linalg.eigvals(X @ Z).real))
    g = gamma_factor * gmin
    F = -Bs.T @ X                                          # u_s = F x_hat
    Lm = (1 - g * g) * np.eye(6) + X @ Z
    H = g * g * np.linalg.solve(Lm.T, Z @ Cs.T)            # x_hat' = A x_hat + B u + H W2 (C x_hat - y)
    K = -(w1 * F).ravel()                                  # u = -K x_hat
    # the firmware's current estimator: (I - L Hm) ~ (I + H W2 C TS)  ->  L T_REL = -H W2 TS
    Lg = -(H @ W2) * TS @ np.linalg.inv(rl.T_REL)
    return K, Lg, gmin


def d_gmf(tuned=False):
    wx, wth, w1 = math.sqrt(QD[0]), math.sqrt(QD[1]), 1 / math.sqrt(RD)
    K, Lg, gmin = gmf_design(wx, wth, w1)
    rec = {"shaping": [wx, wth, w1], "gamma_min": gmin, "eps_max": 1 / gmin}
    print(f"  GMF with the design weights: gamma_min {gmin:.3f} (eps_max {1 / gmin:.3f})")
    if tuned:
        ms = models()
        Ts = truths(ms)

        def worst_disk(x):
            K_, L_, g_ = gmf_design(wx * math.exp(x[0]), wth * math.exp(x[1]), w1 * math.exp(x[2]))
            C = rl.ObserverCtrl(K=K_, L=L_).lti()
            al = []
            for T in Ts[::16]:
                if rl.rho(rl.closed_loop(T, C)) >= 1:
                    return 10.0
                al.append(rl.loop_at_input(T, C, rl.grid(300))["disk_alpha"])
            return -min(al)
        # a grid over the shaping (the worst-case disk margin is flat or discontinuous for a local search)
        best = None
        for sx in (0.3, 1.0, 1.7):
            for sth in (1.0, 2.0, 3.0, 5.0):
                for s1 in (1.0, 1.6, 2.7):
                    x = np.log([sx, sth, s1])
                    v = worst_disk(x)
                    if best is None or v < best[0]:
                        best = (v, x)
        # (a local search from the grid's best drifts to extreme angle weights with high noise gains: the grid's
        # best is kept)
        x = best[1]
        r = type("R", (), {"fun": best[0]})()
        K, Lg, gmin = gmf_design(wx * math.exp(x[0]), wth * math.exp(x[1]), w1 * math.exp(x[2]))
        rec = {"shaping": [wx * math.exp(x[0]), wth * math.exp(x[1]), w1 * math.exp(x[2])], "gamma_min": gmin,
               "eps_max": 1 / gmin, "worst_disk_alpha_design_set": -r.fun}
        print(f"  GMF tuned: shaping {np.round(rec['shaping'], 3)}, gamma_min {gmin:.3f}, worst disk alpha {-r.fun:.3f}")
    return {"K": np.concatenate([K, [0.0, 0.0]]), "L": Lg,
            "method": "Glover-McFarlane loop shaping, W2 = diag(sqrt 300, sqrt 400, sqrt 400) on [x, th1, th2], W1 = 1/sqrt 0.3"
            + (" scaled for the best worst-case disk margin" if tuned else "") + ", central controller at 1.1 gamma_min "
            "(observer form), own linear observer", "gmf": rec}


def d_hinf(start):
    ms = models()
    Ts = truths(ms)
    L = rl.ekf_gain()
    w = rl.grid(90)
    th = np.asarray(start, float) / KSCALE
    act = list(range(0, len(Ts), 8))
    for rnd in range(4):
        sub = [Ts[i] for i in act]
        fun = lambda t: float(np.max(hinf_costs(t, L, sub, w)))  # noqa: E731
        t0 = time.time()
        r = minimize(fun, th, method="Nelder-Mead", options={"maxiter": 1500, "xatol": 1e-4, "fatol": 1e-5, "adaptive": True})
        th = r.x
        allc = hinf_costs(th, L, Ts, w)
        worst = np.argsort(-allc)[:6]
        print(f"  round {rnd}: active {len(act)} models, max {r.fun:.4f}; over all models {allc.max():.4f} "
              f"({ms[int(worst[0])][0]}) ({time.time() - t0:.0f} s)")
        new = [int(i) for i in worst if int(i) not in act]
        if not new or allc.max() <= r.fun * 1.001:
            break
        act += new
    return {"K": th * KSCALE, "L": None,
            "method": "structured H-infinity: the 8 gains on the fixed EKF minimise the worst-case weighted H-infinity norm "
            "(push, drive disturbance, noise -> x, th1, th2, u) over the models (Nelder-Mead, active model set)",
            "hinf": {"worst": float(allc.max()), "nominal_model": float(allc[0])}}


def d_mu(start, iters=4):
    G = rl.build_lft(ww=WW_HINF, wz=WZ_HINF)
    L = rl.ekf_gain()
    w = rl.grid(70)
    th = np.asarray(start, float) / KSCALE
    npp = G.B1.shape[1]
    hist = []
    for it in range(iters):
        C = ctrl_of(th, L)
        M = rl.lft_matrices(G, C)
        F = rl.freqresp(M.A, M.B, M.C, M.D, w)
        Ds, mus = [], []
        x = None
        for Fk in F:
            Mrp, brp = rl.pad_rp(Fk, G)
            v, x = rl.mu_upper_complex(Mrp, brp, x, return_x=True)
            Ds.append(np.exp(np.concatenate([x, [0.0]])[rl.block_index(brp)]))
            mus.append(v)
        print(f"  D-K {it}: RP complex-mu peak {max(mus):.4f} at {w[int(np.argmax(mus))]:.1f} rad/s")
        hist.append(float(max(mus)))
        _, brp = rl.pad_rp(F[0], G)

        def kstep(t):
            Ct = ctrl_of(t, L)
            Mt = rl.lft_matrices(G, Ct)
            if rl.rho(Mt) >= 1.0:
                return 1e3
            Ft = rl.freqresp(Mt.A, Mt.B, Mt.C, Mt.D, w)
            val = 0.0
            for Fk, d in zip(Ft, Ds):
                Mrp, _ = rl.pad_rp(Fk, G)
                val = max(val, float(np.linalg.norm((d[:, None] * Mrp) / d[None, :], 2)))
            return val
        t0 = time.time()
        r = minimize(kstep, th, method="Nelder-Mead", options={"maxiter": 800, "xatol": 1e-4, "fatol": 1e-5, "adaptive": True})
        print(f"     K-step: scaled peak {r.fun:.4f} ({time.time() - t0:.0f} s)")
        if r.fun > hist[-1] * 0.999:
            break
        th = r.x
    return {"K": th * KSCALE, "L": None,
            "method": "mu-synthesis, D-K iteration with the fixed structure (8 gains on the EKF): K-step Nelder-Mead on the peak of "
            "sigma(D M D^-1) with frequency-wise D scales, D-step the complex-mu upper bound; LFT of robust_lin.build_lft",
            "dk_history_rp_complex": hist}


# ----------------------------------------------------------------------------- verification
def lyap_P(K):
    A, B, _ = rl.lin_cont(P_NOM)
    Ad, Bd = rl.zoh(A, B)
    Acl = Ad - Bd @ np.asarray(K[:6])[None, :]
    if np.max(np.abs(np.linalg.eigvals(Acl))) >= 1:
        return None
    return sla.solve_discrete_lyapunov(Acl.T, np.diag(QD))


def verify(name, d, mixed=16):
    K, L = np.asarray(d["K"]), (rl.ekf_gain() if d.get("L") is None else np.asarray(d["L"]))
    C = rl.ObserverCtrl(K=K, L=L).lti()
    ms = models()
    Ts = truths(ms)
    rhos = np.array([rl.rho(rl.closed_loop(T, C)) for T in Ts])
    td = test_draws()
    rt = np.array([rl.rho(rl.closed_loop(rl.truth_dt(p), C)) for _, p in td])
    nom = rl.loop_at_input(rl.truth_dt(P_NOM), C)
    disk = []
    dms = []
    for T in Ts:
        if rl.rho(rl.closed_loop(T, C)) < 1:
            m = rl.loop_at_input(T, C, rl.grid(600))
            disk.append(m["disk_alpha"])
            dms.append(m["delay_margin_ms"] or 0.0)
    belt = {}
    for kb, db in ((P_NOM["k_belt"], P_NOM["d_belt"]), (SPEC["k_belt"]["min"], SPEC["d_belt"]["min"])):
        for dl in (1, 2):
            Tb = rl.truth_dt(P_NOM | {"k_belt": kb, "d_belt": db}, belt=True, delay=dl)
            belt[f"k{kb:g}_d{db:g}_delay{dl}"] = rl.rho(rl.closed_loop(Tb, C))
    G = rl.build_lft(ww=WW_HINF, wz=WZ_HINF)
    t0 = time.time()
    mu = rl.mu_analysis(G, C, w=rl.grid(80), mixed=mixed > 0, n_mixed=mixed)
    J = h2_costs(K / KSCALE, L, Ts)
    Hc = hinf_costs(K / KSCALE, L, Ts, rl.grid(90))
    out = {
        "max_rho_models": float(rhos.max()), "max_rho_test_draws": float(rt.max()),
        "slowest_pole_per_s": float(math.log(max(rhos.max(), 1e-12)) / TS),
        "unstable_models": int(np.sum(rhos >= 1)), "unstable_test_draws": int(np.sum(rt >= 1)),
        "nominal_loop": {k: v for k, v in nom.items() if k not in ("crossovers_rad_s", "pms_deg")}
        | {"crossover_rad_s": nom["crossovers_rad_s"]},
        "worst_disk_alpha": float(min(disk)) if disk else None,
        "worst_disk_pm_deg": math.degrees(2 * math.atan(min(disk) / 2)) if disk else None,
        "worst_delay_margin_ms": float(min(dms)) if dms else None,
        "delay_margin_samples_nominal": rl.delay_margin_samples(P_NOM, C),
        "belt_rho": belt,
        "h2_mean": float(J.mean()), "h2_max": float(J.max()),
        "hinf_worst": float(Hc.max()), "hinf_nominal": float(Hc[0]),
        "mu": {k: v for k, v in mu.items() if k not in ("w", "rs_complex", "rp_complex", "np")},
        "mu_curve": {"w": np.round(mu.get("w", []), 4).tolist(), "rs": np.round(mu.get("rs_complex", []), 4).tolist(),
                     "rp": np.round(mu.get("rp_complex", []), 4).tolist(), "np": np.round(mu.get("np", []), 4).tolist()},
    }
    print(f"  {name}: rho max {out['max_rho_models']:.5f} (test draws {out['max_rho_test_draws']:.5f}), disk alpha nominal "
          f"{nom['disk_alpha']:.3f} worst {out['worst_disk_alpha']:.3f}, PM {nom['pm_deg']:.1f} deg, DM {nom['delay_margin_ms']:.2f} ms "
          f"({out['delay_margin_samples_nominal']} samples), H2 mean {J.mean():.4g}, Hinf worst {Hc.max():.4f}, "
          f"mu RS {mu.get('rs_complex_peak', float('nan')):.3f}/{mu.get('rs_mixed_peak', float('nan')):.3f} "
          f"RP {mu.get('rp_complex_peak', float('nan')):.3f}/{mu.get('rp_mixed_peak', float('nan')):.3f} ({time.time() - t0:.0f} s)")
    return out


# ----------------------------------------------------------------------------- driver
def load():
    if OUT.is_file():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {"format": "bgsim.robust-c1", "version": 1, "designs": {}}


def save(doc):
    def conv(o):
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        raise TypeError(type(o))
    OUT.write_text(json.dumps(doc, indent=1, default=conv) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT)


ORDER = ["nominal", "mm_lqr", "mm_lqr_wc", "gmf", "gmf_tuned", "hinf", "mu"]


def main(argv):
    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    cmd = argv[0] if argv else ""
    only = opt("--only")
    names = only.split(",") if only else ORDER
    calibrate_hinf()
    doc = load()
    doc["weights"] = {"h2_w": np.diag(WW_H2).tolist(), "h2_z": np.diag(WZ_H2).tolist(), "hinf_w": WW_HINF,
                      "hinf_z": WZ_HINF.tolist()}
    D = doc["designs"]
    if cmd == "design":
        for n in names:
            print(f"== {n}")
            t0 = time.time()
            if n == "nominal":
                d = d_nominal()
            elif n == "mm_lqr":
                d = d_mm_lqr(False)
            elif n == "mm_lqr_wc":
                d = d_mm_lqr(True)
            elif n == "gmf":
                d = d_gmf(False)
            elif n == "gmf_tuned":
                d = d_gmf(True)
            elif n == "hinf":
                d = d_hinf(D.get("mm_lqr", d_nominal())["K"])
            elif n == "mu":
                d = d_mu(D.get("hinf", D.get("mm_lqr", d_nominal()))["K"])
            else:
                raise SystemExit(f"unknown design {n}")
            d["design_s"] = round(time.time() - t0, 1)
            P = lyap_P(d["K"])
            d["P"] = P
            old = D.get(n, {})
            d["verify"] = old.get("verify") if old.get("K") is not None and np.allclose(old["K"], d["K"]) else None
            D[n] = d
            save(doc)
    elif cmd == "verify":
        for n in names:
            if n in D:
                D[n]["verify"] = verify(n, D[n], int(opt("--mixed", 16)))
                save(doc)
    elif cmd == "harness":
        import robustness as rb
        for n in names:
            if n not in D:
                continue
            rb.run_controller("robust_ctrl:make", f"c1-{n}", {"balance": n}, ["swingup", "balance_push"],
                              int(opt("--jobs", 8)))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
