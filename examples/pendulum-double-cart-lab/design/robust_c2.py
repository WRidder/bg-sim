# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13", "cvxpy>=1.5", "control>=0.10", "slycot"]
# ///
"""Plan C2: a swing-up planned for the parameter box of the double-cart lab rig, and a multi-model TVLQR.

    uv run examples/pendulum-double-cart-lab/design/robust_c2.py design [--half] [--verbose <ipopt log>] [--out <json>]
    uv run examples/pendulum-double-cart-lab/design/robust_c2.py minmax [n]
    uv run examples/pendulum-double-cart-lab/design/robust_c2.py harness [--plans mm_tvlqr,margin] [--balance mm_lqr] [--jobs 8]

Models: the design models (`lablib.design_plant`) of the nominal parameter set and of the 16 corners of four groups
(all link part masses, the COM shifts, cart and rotor mass, the drive gain k_t / R_m), `corner_models`.

`minmax`: the open-loop min-max plan, one feed-forward U(t) (Hermite-Simpson, 75 intervals over T_s = 3.0 s) for
the nominal (ending upright at rest, hard) and n - 1 corners (the largest terminal cost z' P z, normalised by a
2 deg lean, minimised), |V| <= 16.8 V, |x| <= 0.8 m for every model. The swing-up of a double pendulum is too
sensitive for one open-loop input: with 4 corners the best terminal cost is ~1800 leans (the links far from
upright), so the plan needs the feedback and this formulation is reported, not used.

`design` writes two plans to `design/robust_c2.json`:

- `mm_tvlqr`: the nominal plan of design.json with a TVLQR designed against all the models: a common gain K_k
  along the nominal reference (1 ms), from the backward recursion of every model's own cost-to-go P_m,k with the
  gain that minimises the summed one-step costs, K_k = (n R + sum B_m' P_m B_m)^-1 sum B_m' P_m A_m (Q, R of the
  design), terminal P_m each model's discrete LQR cost-to-go;
- `margin`: a nominal plan with actuator and travel margins for the feedback (|V| <= 60 % of the supply,
  |x| <= 0.7 m) and the same multi-model TVLQR.

The closed-loop swing-ups (ideal states) of the nominal, mm_tvlqr and margin tables on every model are reported;
`harness` runs the plans with a C1 balance law on the robustness test (timed catch at T_s).
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import casadi as ca
import numpy as np
import scipy.linalg as sla

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lablib as lb  # noqa: E402
import robust_lin as rl  # noqa: E402

cp = lb.cp
OUT = HERE / "robust_c2.json"
TS = lb.TS
P_NOM = lb.nominal()
SPEC = lb.spec()
QD = np.array([300.0, 400.0, 400.0, 10.0, 8.0, 8.0])
RD = 0.3
U_LIM = 0.7 * P_NOM["u_max"]
X_LIM = 0.8
MARGIN_U = 0.6 * P_NOM["u_max"]
MARGIN_X = 0.7
GROUPS = {
    "link_mass": ["m_tube1", "m_tube2", "m_hub1", "m_head1", "m_hub2", "m_tip2", "m_enc_board", "m_enc_magnet", "rho_cable"],
    "com": ["com_shift1", "com_shift2"],
    "cart": ["m_cart", "J_m"],
    "drive": ["k_t", "R_m"],         # k_t max with R_m min (strong drive) and the reverse
}


def corner_models(half: bool = False) -> list[tuple[str, dict]]:
    """The nominal and the 16 corners of the groups (half: the 8 corners of the 2^(4-1) half fraction, even parity)."""
    out = [("nominal", dict(P_NOM))]
    keys = list(GROUPS)
    for i in range(2 ** len(keys)):
        if half and bin(i).count("1") % 2:
            continue
        p = dict(P_NOM)
        tag = []
        for j, g in enumerate(keys):
            s = 1 if (i >> j) & 1 else -1
            tag.append(f"{g}{'+' if s > 0 else '-'}")
            for k in GROUPS[g]:
                hi = s > 0 if k != "R_m" else s < 0
                p[k] = SPEC[k]["max"] if hi else SPEC[k]["min"]
        out.append((" ".join(tag), p))
    return out


def lqr_P(p) -> np.ndarray:
    A, B, _ = rl.lin_cont(p | rl.NO_COULOMB)
    Ad, Bd = rl.zoh(A, B)
    return sla.solve_discrete_are(Ad, Bd, np.diag(QD), np.array([[RD]]))


def plan(models, t_s=3.0, K=75, w_s=100.0, guess=None, verbose=False, u_lim=U_LIM, x_lim=X_LIM):
    dyns = [cp.Dynamics(lb.design_plant(p)) for _, p in models]
    P0 = lqr_P(P_NOM)
    z2 = np.zeros(6)
    z2[1:3] = math.radians(2.0)
    pref = float(z2 @ P0 @ z2)
    h = t_s / K
    opti = ca.Opti()
    U = opti.variable(1, K + 1)
    Zs = [opti.variable(6, K + 1) for _ in models]
    s = opti.variable()
    cost = 0
    for k in range(K):
        um = 0.5 * (U[0, k] + U[0, k + 1])
        cost += h / 6.0 * (U[0, k] ** 2 + 4 * um**2 + U[0, k + 1] ** 2) + 0.02 * (U[0, k + 1] - U[0, k]) ** 2
    hang = np.array([0.0, -math.pi, -math.pi, 0, 0, 0])
    for m, (dyn, Z) in enumerate(zip(dyns, Zs)):
        f = dyn.f
        F = [f(Z[:, k], U[0, k], 0.0) for k in range(K + 1)]
        for k in range(K):
            zm = 0.5 * (Z[:, k] + Z[:, k + 1]) + h / 8.0 * (F[k] - F[k + 1])
            um = 0.5 * (U[0, k] + U[0, k + 1])
            opti.subject_to(Z[:, k + 1] - Z[:, k] - h / 6.0 * (F[k] + 4 * f(zm, um, 0.0) + F[k + 1]) == 0)
        opti.subject_to(Z[:, 0] == hang)
        opti.subject_to(opti.bounded(-x_lim, Z[0, :], x_lim))
        if m == 0:
            opti.subject_to(Z[:, K] == np.zeros(6))
        else:
            zT = Z[:, K]
            opti.subject_to(s >= ca.mtimes([zT.T, ca.DM(P0), zT]) / pref)
    opti.subject_to(opti.bounded(-u_lim, U, u_lim))
    opti.subject_to(s >= 0)
    opti.minimize(cost + w_s * s)
    if guess is not None:
        opti.set_initial(U, guess[1])
        for Z in Zs:
            opti.set_initial(Z, guess[0])
    opts = {"ipopt.max_iter": 3000, "ipopt.tol": 1e-7, "ipopt.print_level": 0, "print_time": False,
            "ipopt.mu_strategy": "adaptive"}
    if verbose:   # the iteration log to a file (C stdout is block-buffered when redirected)
        opts |= {"ipopt.output_file": str(verbose), "ipopt.file_print_level": 5}
    opti.solver("ipopt", opts)
    t0 = time.time()
    sol = opti.solve()
    print(f"  plan: {len(models)} models, max normalised terminal cost {float(sol.value(s)):.3f}, "
          f"|U| max {np.abs(sol.value(U)).max():.2f} V ({time.time() - t0:.0f} s)")
    return {"t": np.linspace(0, t_s, K + 1), "U": np.array(sol.value(U)).ravel(), "Z": [np.array(sol.value(Z)) for Z in Zs],
            "s": float(sol.value(s)), "T": t_s, "K": K}


def nominal_guess(K=75, t_s=3.0):
    d = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    tk = np.array(d["tk"])
    t = np.linspace(0, t_s, K + 1)
    xs = np.array(d["xs"])
    Z = np.array([np.interp(t, tk, xs[:, i]) for i in range(6)])
    U = np.interp(t, tk, np.array(d["uff"]))
    return Z, U


def rk4_run(dyn, z0, u_of_t, t_end, h=1e-3, fb=None):
    z = np.array(z0, float)
    out = [z.copy()]
    n = int(round(t_end / h))
    for i in range(n):
        t = i * h
        u = u_of_t(t) if fb is None else fb(t, z)
        u = min(max(u, -P_NOM["u_max"]), P_NOM["u_max"])
        k1 = np.array(dyn.f(z, u, 0.0)).ravel()
        k2 = np.array(dyn.f(z + 0.5 * h * k1, u, 0.0)).ravel()
        k3 = np.array(dyn.f(z + 0.5 * h * k2, u, 0.0)).ravel()
        k4 = np.array(dyn.f(z + h * k3, u, 0.0)).ravel()
        z = z + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        out.append(z.copy())
    return np.array(out)


def mm_tvlqr(models, ref_t, ref_z, ref_u, h=1e-3):
    """Common time-varying gain along the reference for all models (backward recursion with per-model cost-to-go)."""
    dyns = [cp.Dynamics(lb.design_plant(p)) for _, p in models]
    n = len(ref_t) - 1
    Pm = [lqr_P(p) for _, p in models]
    Q, R = np.diag(QD) * h / TS, RD * h / TS
    Ks = np.zeros((n + 1, 6))
    A0 = None
    for k in range(n, -1, -1):
        AB = []
        for dyn in dyns:
            A, B = (np.array(m, float) for m in dyn.lin(ref_z[k], ref_u[k]))
            AB.append(rl.zoh(A, B.reshape(6, 1), h))
        M = R * len(models) + sum(Bd.T @ P @ Bd for (Ad, Bd), P in zip(AB, Pm))
        N = sum(Bd.T @ P @ Ad for (Ad, Bd), P in zip(AB, Pm))
        K = np.linalg.solve(M, N)
        Ks[k] = K.ravel()
        Pm = [Q + K.T * R @ K + (Ad - Bd @ K).T @ P @ (Ad - Bd @ K) for (Ad, Bd), P in zip(AB, Pm)]
        Pm = [0.5 * (P + P.T) for P in Pm]
    return Ks


def hermite_ref(traj, h=1e-3):
    """The nominal model's collocation solution at 1 ms: cubic Hermite between the knots (the states and their
    derivatives f(z, u) at the knots, as Hermite-Simpson assumes), the voltage linear."""
    dyn0 = cp.Dynamics(lb.design_plant(P_NOM))
    tk, Z, U = traj["t"], traj["Z"][0], traj["U"]
    F = np.array([np.array(dyn0.f(Z[:, k], U[k], 0.0)).ravel() for k in range(len(tk))]).T
    tt = np.arange(0.0, traj["T"] + 1e-9, h)
    zz = np.zeros((len(tt), 6))
    for j, t in enumerate(tt):
        k = min(int(t / (tk[1] - tk[0])), len(tk) - 2)
        dt = tk[k + 1] - tk[k]
        s_ = (t - tk[k]) / dt
        h00, h10, h01, h11 = 2 * s_**3 - 3 * s_**2 + 1, s_**3 - 2 * s_**2 + s_, -2 * s_**3 + 3 * s_**2, s_**3 - s_**2
        zz[j] = h00 * Z[:, k] + h10 * dt * F[:, k] + h01 * Z[:, k + 1] + h11 * dt * F[:, k + 1]
    return tt, zz, np.interp(tt, tk, U)


def table_ref(d, h=1e-3):
    """A table plan (design.json) at 1 ms: states and voltage interpolated linearly from the 10 ms knots."""
    tk = np.array(d["tk"])
    tt = np.arange(0.0, float(d["t_s"]) + 1e-9, h)
    xs = np.array(d["xs"])
    return tt, np.array([np.interp(tt, tk, xs[:, i]) for i in range(6)]).T, np.interp(tt, tk, np.array(d["uff"]))


def tables(models, ref, t_s, dt_tab=0.01):
    """The multi-model TVLQR along the reference (tt, z, u at 1 ms), and the 10 ms tables."""
    tt, zz, uu = ref
    h = tt[1] - tt[0]
    Ks = mm_tvlqr(models, tt, zz, uu, h)
    tk = np.arange(0.0, t_s + 1e-9, dt_tab)
    idx = np.round(tk / h).astype(int)
    return {"t_s": t_s, "tk": tk, "xs": zz[idx], "uff": uu[idx], "Ks": Ks[idx]}


def spread(models, u_of, t_s=3.0, fb=None):
    """Terminal deviation (normalised cost z' P z / pref, max angle deg) of every model."""
    P0 = lqr_P(P_NOM)
    z2 = np.zeros(6)
    z2[1:3] = math.radians(2.0)
    pref = float(z2 @ P0 @ z2)
    out = []
    for name, p in models:
        dyn = cp.Dynamics(lb.design_plant(p))
        z = rk4_run(dyn, [0, -math.pi, -math.pi, 0, 0, 0], u_of, t_s, 1e-3, fb)[-1]
        zz = z.copy()
        zz[1:3] = np.remainder(zz[1:3] + math.pi, 2 * math.pi) - math.pi
        out.append({"model": name, "cost": float(zz @ P0 @ zz / pref), "max_deg": float(np.degrees(np.abs(zz[1:3]).max())),
                    "x": float(zz[0])})
    return out


def main(argv):
    cmd = argv[0] if argv else ""
    out_path = Path(argv[argv.index("--out") + 1]) if "--out" in argv else OUT
    if cmd == "minmax":
        # the open-loop min-max plan (one feed-forward for the nominal and n - 1 corners): reported, not used
        n = int(argv[1]) if len(argv) > 1 else 5
        models = corner_models()[:n]
        traj = plan(models, guess=nominal_guess())
        print(f"  min-max open-loop plan over {n} models: the largest terminal cost z'Pz is {traj['s']:.0f} x a 2 deg lean")
    elif cmd == "design":
        models = corner_models(half="--half" in argv)
        t0 = time.time()
        d = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
        nominal = {"t_s": float(d["t_s"]), "tk": np.array(d["tk"]), "xs": np.array(d["xs"]), "uff": np.array(d["uff"]),
                   "Ks": np.array(d["Ks"])}
        # A: the nominal plan with the multi-model TVLQR
        t1 = time.time()
        mm_tv = tables(models, table_ref(d), float(d["t_s"]))
        print(f"  mm_tvlqr: the nominal plan, multi-model TVLQR over {len(models)} models ({time.time() - t1:.0f} s)")
        # B: a plan with actuator and travel margins (60 % of the supply, 0.7 m) and the multi-model TVLQR
        t1 = time.time()
        traj = plan(models[:1], guess=nominal_guess(), u_lim=MARGIN_U, x_lim=MARGIN_X,
                    verbose=argv[argv.index("--verbose") + 1] if "--verbose" in argv else None)
        margin = tables(models, hermite_ref(traj), traj["T"])
        print(f"  margin: plan inside {MARGIN_U:.1f} V / {MARGIN_X} m, multi-model TVLQR ({time.time() - t1:.0f} s)")

        def fb_of(tb):
            def fb(t, z):
                i = min(int(t / 0.01), len(tb["tk"]) - 2)
                w = min(t / 0.01 - i, 1.0)
                xr = (1 - w) * tb["xs"][i] + w * tb["xs"][i + 1]
                ur = (1 - w) * tb["uff"][i] + w * tb["uff"][i + 1]
                k = (1 - w) * tb["Ks"][i] + w * tb["Ks"][i + 1]
                return float(ur - k @ (z - xr))
            return fb
        spreads = {}
        for name, tb in (("nominal", nominal), ("mm_tvlqr", mm_tv), ("margin", margin)):
            spreads[name] = spread(models, None, fb=fb_of(tb))
            print(f"  closed loop (ideal states) {name:9s}: terminal cost max {max(r['cost'] for r in spreads[name]):.3f}, "
                  f"max angle {max(r['max_deg'] for r in spreads[name]):.3f} deg, |x| max {max(abs(r['x']) for r in spreads[name]):.4f} m")
        doc = {"format": "bgsim.robust-c2", "version": 1, "description": __doc__.split("\n\n")[1].strip(),
               "models": [m for m, _ in models],
               "plans": {"mm_tvlqr": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in mm_tv.items()},
                         "margin": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in margin.items()}
                         | {"plan_t": traj["t"].tolist(), "plan_U": traj["U"].tolist(), "u_lim": MARGIN_U, "x_lim": MARGIN_X,
                            "peak_u_ff": float(np.abs(traj["U"]).max()), "peak_x": float(np.abs(traj["Z"][0][0]).max())}},
               "closed_loop_spread": spreads,
               "design_s": round(time.time() - t0, 1)}
        out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("wrote", out_path)
    elif cmd == "harness":
        import robustness as rb
        jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 8
        bal = argv[argv.index("--balance") + 1] if "--balance" in argv else "mm_lqr"
        plans = argv[argv.index("--plans") + 1].split(",") if "--plans" in argv else ["mm_tvlqr", "margin"]
        for pl in plans:
            rb.run_controller("robust_ctrl:make", f"c2-{pl}-{bal}", {"balance": bal, "swing": pl}, ["swingup"], jobs)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
