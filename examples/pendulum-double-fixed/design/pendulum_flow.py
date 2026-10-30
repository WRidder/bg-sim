"""The design flow shared by the fixed-pivot pendulum examples: trajectory, LQR, TVLQR, tables, prediction."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pendulum_common import (  # noqa: E402
    TS,
    Dynamics,
    Nominal,
    Tables,
    free_swing,
    lqr_gain,
    simulate,
    swing_up,
    tables_from,
    tvlqr,
)
from pendulum_expected import write_expected  # noqa: E402
from pendulum_model import fmt_table, write_ctrl_block  # noqa: E402


def design(prm, library_dir: Path | None = None, results_path: Path | None = None) -> dict:
    P, C = prm.PLANT, prm.CFG
    dyn = Dynamics(P)
    n = dyn.n
    A, B = dyn.linearise(dyn.x_up)
    poles = np.sort(np.linalg.eigvals(A).real)
    print("open-loop poles at upright (1/s):", np.array2string(poles, precision=3))

    t0 = time.time()
    tt, X, U = swing_up(dyn, C["T_s"], C["nk"], C["u_to"], **C.get("to_options", {}))
    print(f"collocation: {C['nk']} intervals, peak |u| = {abs(U).max():.3f} V, {time.time() - t0:.1f} s")
    nom = Nominal(dyn, tt, X, U)

    K_lqr, P_lqr, Ad, Bd = lqr_gain(dyn, C["Q"], C["R"])
    Kt = tvlqr(dyn, nom, C["Q"], C["R"], P_lqr)
    e = nom.x - dyn.x_up
    Vn = np.einsum("ki,ij,kj->k", e, P_lqr, e)
    V_catch = float(f"{Vn[int(round((C['T_s'] - C['catch_before_end']) / TS))]:.4g}")
    print(f"LQR K = {np.array2string(K_lqr, precision=4)}, V_catch = {V_catch}")

    tab = tables_from(nom, Kt, C["dt_tab"], (K_lqr, P_lqr), C["t_on"], V_catch, P.umax, dyn.x_up)
    # the block holds the tables rounded to 9 significant digits: simulate with those
    tab = Tables(tab.dt, np.array(fmt_table(tab.xs.ravel())).reshape(tab.xs.shape), np.array(fmt_table(tab.us)),
                 np.array(fmt_table(tab.Ks.ravel())).reshape(tab.Ks.shape), np.array(fmt_table(tab.K_lqr)),
                 np.array(fmt_table(tab.P_lqr.ravel())).reshape(tab.P_lqr.shape), tab.t_on, tab.T_s, tab.V_catch,
                 tab.u_max, tab.x_up)

    t, xs, u, ph = simulate(dyn, tab, dyn.x_down, C["t_end"], dist=(C["t_dist"], C["pulse_len"], C["F"]))
    a = np.cumsum(xs[:, :n], axis=1) - math.pi / 2  # absolute link angles from upright
    catch = float(t[np.argmax(ph == 2)])
    pre = (t >= catch + 0.5) & (t < C["t_dist"])
    post = t >= C["t_dist"]
    band_pre = float(np.abs(a[pre]).max())
    peak_dist = float(np.abs(a[post]).max(axis=0).max())
    tip_peak = float(np.abs(a[post, -1]).max())
    tol = math.radians(1.0)
    outside = np.where((np.abs(a) > tol).any(axis=1) & post)[0]
    recovered = float(t[outside[-1]]) if len(outside) else C["t_dist"]
    still = np.abs(xs[t < C["t_on"], 0] - dyn.x_down[0]).max()
    res = dict(
        poles=poles.tolist(),
        K_lqr=K_lqr.tolist(),
        V_catch=V_catch,
        peak_u_to=float(abs(U).max()),
        peak_u_run=float(abs(u).max()),
        t_catch=catch,
        swing_up_end=C["t_on"] + C["T_s"],
        band_pre=band_pre,
        peak_dist_all=peak_dist,
        peak_dist_tip=tip_peak,
        peak_by_link=np.abs(a[post]).max(axis=0).tolist(),
        recovered_1deg=recovered,
        peak_u_after=float(abs(u[post]).max()),
        hanging_motion=float(still),
        final_abs_angles=a[-1].tolist(),
        rows=int(tab.xs.shape[0]),
    )
    print(json.dumps(res, indent=1))

    here = Path(prm.HERE)
    lib = library_dir or here.parent / "library"
    write_ctrl_block(lib / f"{prm.CTRL_BLOCK}.jl", prm.CTRL_BLOCK, tab, n, f"{prm.EXAMPLE} controller")
    (results_path or here / "results.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8", newline="\n")
    if "--save-prediction" in sys.argv:
        np.savez(sys.argv[sys.argv.index("--save-prediction") + 1], t=t, x=xs, u=u, phase=ph, a=a)
    free_diff = here / "free_max_diff.json"
    if free_diff.is_file():
        res["free_max_diff"] = json.loads(free_diff.read_text(encoding="utf-8"))["max_diff"]
    write_expected(prm, res, dict(t=t, x=xs, u=u, phase=ph, a=a), here.parent / "expected.json")
    return res


def compare_free(prm, npz_path: str) -> None:
    """Free swing of the design model (u = 0) against a bond-graph run of ``models/free.bgmodel.json``."""
    P, C = prm.PLANT, prm.CFG
    dyn = Dynamics(P)
    n = dyn.n
    run = np.load(npz_path)
    tr = run["time"]
    x0 = np.array(list(C["free_q0"]) + [0.0] * n)
    td, qd_ = free_swing(dyn, x0, C["free_t_end"], 3001)
    diffs = []
    for k in range(n):
        sig = run[f"Joint{k + 1}__qout"]
        ref = np.interp(tr, td, qd_[:, k])
        diffs.append(float(np.abs(sig - ref).max()))
        print(f"joint {k + 1}: max |bond graph - design| = {diffs[-1]:.3e} rad")
    (Path(prm.HERE) / "free_max_diff.json").write_text(
        json.dumps({"max_diff": max(diffs)}), encoding="utf-8", newline="\n"
    )
    print(f"max angle difference over the 3 s free swing: {max(diffs):.3e} rad "
          f"(swing range q1 {qd_[:, 0].min():.2f}..{qd_[:, 0].max():.2f} rad)")


def run(prm) -> None:
    """Entry point of a ``design.py``: ``--compare run.npz`` checks the free swing, otherwise design."""
    if "--compare" in sys.argv:
        compare_free(prm, sys.argv[sys.argv.index("--compare") + 1])
        return
    design(prm)
