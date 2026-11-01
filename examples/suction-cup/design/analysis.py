# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Hand calculations for the suction-cup example, and their check against simulations.

* the operating vacuum (the ejector curve meets the lip leak) and the holding capacity A_eff dp;
* the static hold: k_ax ext + A_fold dp - F_bot(ext) = m g, i.e. the vacuum lift stroke that
  lifts the box off the table, and the extension of the hanging box;
* the axial spring-mass mode: k = k_ax + dF_bot/d(-ext) at the hang, w_n = sqrt(k/m),
  zeta = d_ax / (2 sqrt(k m));
* the lateral/tilt modes of the box hanging on the bellows (two degrees of freedom, linearised
  about the hang: lateral bellows deflection e and box tilt phi, the side stiffnesses carry the
  factor kf = (1 + c_vac dp/p_atm) exp(-c_ext ext/L0)) and the transmissibility from the tool's
  lateral motion to the box's centre of mass;
* the quasi-static utilisation of the steps and the swing.

With ``--sim`` it also runs the models (``run_model.jl``) and prints the simulated numbers next to
the hand values. Writes ``design/results.json`` (the numbers README, docs and expected.json quote).

    uv run examples/suction-cup/design/analysis.py [--sim]
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import params as P  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent.parent
C, V, B = P.CUP, P.VACUUM, P.BOX
CD, RHO, P_TR = 0.6, 1.2, 500.0


def leak(dp: float) -> float:
    """Free-air leak past a sealed lip at vacuum dp (the block's regularised orifice law)."""
    return CD * C["A_lip0"] * dp * math.sqrt(2.0 / (RHO * math.sqrt(dp * dp + P_TR * P_TR)))


def operating_vacuum(dp_max: float = V["dp_max"], q_max: float = V["Q_max"]) -> float:
    """Q_max (1 - dp/dp_max) = leak(dp) (bisection)."""
    lo, hi = 0.0, dp_max
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if q_max * (1 - mid / dp_max) > leak(mid) else (lo, mid)
    return 0.5 * (lo + hi)


def bottoming(ext: float, cup: dict = C) -> tuple[float, float]:
    """F_bot and dF_bot/d(-ext) of the block's law (pos with h_eps = 1e-6 m)."""
    xo = -ext - cup["s_bot"]
    root = math.sqrt(xo * xo + 1.0e-12)
    xb, dxb = 0.5 * (xo + root), 0.5 * (1 + xo / root)
    r = xb / cup["x_bot"]
    return cup["k_bot"] * xb * r ** (cup["n_bot"] - 1), cup["n_bot"] * cup["k_bot"] * r ** (cup["n_bot"] - 1) * dxb


def hang_extension(t_ax: float, dp: float, cup: dict = C) -> float:
    """k_ax ext + A_fold dp - F_bot(ext) = T (bisection)."""
    lo, hi = -cup["L0"], cup["L0"]
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f = cup["k_ax"] * mid + cup["A_fold"] * dp - bottoming(mid, cup)[0]
        lo, hi = (mid, hi) if f < t_ax else (lo, mid)
    return 0.5 * (lo + hi)


def stiff_factor(dp: float, ext: float, cup: dict = C) -> float:
    return (1 + cup["c_vac"] * dp / P.P_ATM) * math.exp(-cup["c_ext"] * ext / cup["L0"])


def lateral_model(m: float, dp: float, cup: dict = C, box: dict = B):
    """Mass, damping and stiffness matrices of (e, phi) and the forcing vector of the tool x."""
    ext = hang_extension(m * P.G0, dp, cup)
    kf = stiff_factor(dp, ext, cup)
    k, kt = cup["k_lat"] * kf, cup["k_tilt"] * kf
    h = box["H_p"] / 2 - box["cz"]
    J = m * (box["L_p"] ** 2 + box["H_p"] ** 2) / 12
    Mm = np.array([[m, -m * h], [0.0, J]])
    Cm = np.array([[cup["d_lat"], 0.0], [h * cup["d_lat"], cup["d_rot"]]])
    Km = np.array([[k, 0.0], [h * k, kt + m * P.G0 * h]])
    return Mm, Cm, Km, h, kf, ext


def lateral_modes(m: float, dp: float, cup: dict = C) -> list[float]:
    """Undamped natural frequencies (rad/s) of the two lateral/tilt modes."""
    Mm, _, Km, *_ = lateral_model(m, dp, cup)
    w2 = np.linalg.eigvals(np.linalg.solve(Mm, Km))
    return sorted(float(math.sqrt(x.real)) for x in w2)


def lateral_damping(m: float, dp: float, cup: dict = C) -> list[float]:
    """Damping ratios of the two lateral/tilt modes (state-space eigenvalues), low mode first."""
    Mm, Cm, Km, *_ = lateral_model(m, dp, cup)
    Mi = np.linalg.inv(Mm)
    A = np.block([[np.zeros((2, 2)), np.eye(2)], [-Mi @ Km, -Mi @ Cm]])
    lam = [x for x in np.linalg.eigvals(A) if x.imag > 0]
    return [float(-x.real / abs(x)) for x in sorted(lam, key=abs)]


def transmissibility(m: float, dp: float, freqs: np.ndarray, cup: dict = C) -> np.ndarray:
    """|X_com / X_tool| of the damped linear model: m (e'' - h phi'') = -k e - c e' - m x_T''."""
    Mm, Cm, Km, h, *_ = lateral_model(m, dp, cup)
    out = []
    for f in freqs:
        w = 2 * math.pi * f
        Z = Km - w * w * Mm + 1j * w * Cm
        q = np.linalg.solve(Z, np.array([m * w * w, 0.0]))
        out.append(abs(1 + q[0] - h * q[1]))
    return np.array(out)


def hand() -> dict:
    m = B["m_p"]
    dp = operating_vacuum()
    fcap = C["A_eff"] * dp
    ext_hang = hang_extension(m * P.G0, dp)
    ext_free = hang_extension(0.0, dp)
    k_tan = C["k_ax"] + bottoming(ext_hang)[1]
    wn_ax = math.sqrt(k_tan / m)
    zeta_ax = C["d_ax"] / (2 * math.sqrt(k_tan * m))
    modes = lateral_modes(m, dp)
    _, _, _, h, kf, _ = lateral_model(m, dp)
    freqs = np.linspace(0.5, 25.0, 491)
    tr = transmissibility(m, dp, freqs)
    i_pk = int(np.argmax(tr))
    # the linear cup (nonlinear terms off)
    lin = {**C, **P.LINEAR_OFF}
    ext_hang_lin = hang_extension(m * P.G0, dp, lin)
    modes_lin = lateral_modes(m, dp, lin)
    # quasi-static utilisation: steady acceleration a of the tool along x on the hanging box
    # U = (T + 4 M / D + F/mu) / Fcap with T = m g, F = m a, M = m a h (the bellows carry the
    # moment of the lateral force about the centre of mass at the lip ... the box tilts until
    # the bellows moment and the lip couple balance m a h)
    def u_steps(a: float, mass: float = m) -> float:
        return (mass * P.G0 + 4 * mass * a * h / C["D_lip"] + mass * a / C["mu"]) / fcap

    def u_tilt(th: float, mass: float = m) -> float:
        """Quasi-static tool tilt th: gravity splits into axial m g cos and shear m g sin."""
        return (mass * P.G0 * math.cos(th) + 4 * mass * P.G0 * math.sin(th) * h / C["D_lip"]
                + mass * P.G0 * math.sin(th) / C["mu"]) / fcap

    def ex_tilt(th: float, mass: float = m) -> float:
        """Lateral bellows deflection at a quasi-static tool tilt th: shear m g sin over k_lat kf, with
        kf at the axial load m g cos."""
        ext = hang_extension(mass * P.G0 * math.cos(th), dp)
        return mass * P.G0 * math.sin(th) / (C["k_lat"] * stiff_factor(dp, ext))

    a_hold = (fcap - m * P.G0) / (m * (4 * h / C["D_lip"] + 1 / C["mu"]))
    return {
        "mass": m,
        "dp_op": dp, "Fcap": fcap, "U_static": m * P.G0 / fcap,
        "lift_force": C["A_fold"] * dp,
        "ext_free": ext_free, "ext_hang": ext_hang, "lift_off": -ext_hang,
        "ext_hang_linear": ext_hang_lin,
        "k_ax_tangent": k_tan, "wn_ax": wn_ax, "f_ax": wn_ax / (2 * math.pi), "zeta_ax": zeta_ax,
        "kf_hang": kf, "h_com": h,
        "lateral_modes_hz": [w / (2 * math.pi) for w in modes],
        "lateral_zeta": lateral_damping(m, dp),
        "lateral_modes_linear_hz": [w / (2 * math.pi) for w in modes_lin],
        "tr_peak_hz": float(freqs[i_pk]), "tr_peak": float(tr[i_pk]),
        "tr_curve": {"f": [round(float(x), 3) for x in freqs[::10]], "tr": [round(float(x), 4) for x in tr[::10]]},
        "a_static_limit": a_hold,
        "U_steps": {f"{a:.2f}": u_steps(a) for a in (P.MOTION["a_s"] / 3, 2 * P.MOTION["a_s"] / 3, P.MOTION["a_s"])},
        "U_overload_steps": {f"{a:.2f}": u_steps(a, 0.8) for a in (3.0, 6.0, 9.0)},
        "U_tilt": u_tilt(math.radians(P.MOTION["th_A"])),
        "ex_tilt": ex_tilt(math.radians(P.MOTION["th_A"])),
        "U_tilt_90": u_tilt(math.radians(90.0)),
        "s_bot": C["s_bot"],
    }


def run_models(jobs: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        jf = Path(tmp) / "jobs.json"
        jf.write_text(json.dumps(jobs), encoding="utf-8")
        subprocess.run(["julia", f"--project={REPO / 'julia' / 'BGSim'}", str(HERE / "run_model.jl"), str(jf), tmp],
                       check=True)
        out = {}
        for job in jobs:
            data = json.loads((Path(tmp) / f"{job['id']}.json").read_text(encoding="utf-8"))
            out[job["id"]] = {k: np.array(v) for k, v in data.get("signals", {}).items()}
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="run the models and compare")
    args = ap.parse_args()
    r = hand()
    print(f"operating vacuum {r['dp_op']:.1f} Pa, Fcap {r['Fcap']:.3f} N, static U {r['U_static']:.4f}")
    print(f"lift force A_fold dp {r['lift_force']:.3f} N; unloaded stroke {1e3 * r['ext_free']:.3f} mm; "
          f"hanging box ext {1e3 * r['ext_hang']:.4f} mm (linear cup {1e3 * r['ext_hang_linear']:.4f} mm)")
    print(f"axial mode: k {r['k_ax_tangent']:.1f} N/m, f {r['f_ax']:.3f} Hz (wn {r['wn_ax']:.3f} rad/s), zeta {r['zeta_ax']:.4f}")
    print(f"lateral modes {['%.3f' % f for f in r['lateral_modes_hz']]} Hz (kf {r['kf_hang']:.4f}); linear cup "
          f"{['%.3f' % f for f in r['lateral_modes_linear_hz']]} Hz; TR peak {r['tr_peak']:.2f} at {r['tr_peak_hz']:.2f} Hz")
    print(f"quasi-static steps U {r['U_steps']}, a limit {r['a_static_limit']:.2f} m/s^2; overload U {r['U_overload_steps']}")
    print(f"tilt U at th_A {r['U_tilt']:.3f} (lateral deflection {1e3 * r['ex_tilt']:.4f} mm), 90 deg {r['U_tilt_90']:.3f}")
    if args.sim:
        sims = run_models([{"id": "hold", "model": "hold-release"}, {"id": "swing", "model": "swing"}])
        hold, swing = sims["hold"], sims["swing"]
        at = lambda run, sig, tk: float(np.interp(tk, run["time"], run[sig]))  # noqa: E731
        r["sim_dp"] = at(hold, "Cup/dp", 2.0)
        r["sim_ext_hang"] = at(hold, "Cup/ext", 2.0)
        z_rest = B["H_p"] / 2 - P.rest_penetration(B["m_p"])        # the box centre resting on the table
        r["sim_lift_off"] = at(hold, "Pose/g[7]", 0.4) - z_rest
        r["sim_U_tilt"] = at(swing, "Cup/U", 2.2)
        r["sim_ex_tilt"] = at(swing, "Cup/ex", 2.2)
        print(f"sim: dp {r['sim_dp']:.1f} Pa, hanging ext {1e3 * r['sim_ext_hang']:.4f} mm, box lifted off the "
              f"table by {1e3 * r['sim_lift_off']:.4f} mm; at the {P.MOTION['th_A']:g} deg tilt U "
              f"{r['sim_U_tilt']:.3f}, ex {1e3 * r['sim_ex_tilt']:.4f} mm")
    (HERE / "results.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", HERE / "results.json")


if __name__ == "__main__":
    main()
