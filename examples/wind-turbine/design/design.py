# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Reference numbers of the wind-turbine example, written to `design/design.json`.

    uv run examples/wind-turbine/design/design.py
    uv run examples/wind-turbine/design/build_model.py

* the Cp and Ct tables over the tip-speed ratio and the pitch (`bem.py`, from the report's blade
  and airfoil data), and their peak against the report (0.482 at lambda 7.55, beta 0);
* the tower's first fore-aft mode as a modal mass, stiffness and damping (`tower.py`);
* the closed-loop steady states (rotor speed, pitch, torques, power, thrust, tower deflection) of
  the baseline controller with these tables, at a list of wind speeds, next to the report's
  region-3 pitch of Table 7-1;
* the open-loop operating point and the linearised modes of the plant (drivetrain torsion and
  tower fore-aft with aerodynamic damping), with the same bilinear table interpolation as the
  stdlib Lookup2D block;
* the analytic two-inertia drivetrain frequency.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bem  # noqa: E402
import nrel5mw as T  # noqa: E402
import tower  # noqa: E402

TSR = np.arange(2.0, 16.01, 0.5)                 # 29 points
PITCH = np.arange(-1.0, 27.01, 1.0)              # 29 points (deg)
AREA = math.pi * T.R_TIP ** 2


def interp2(u, v, xs, ys, tab):
    """The stdlib Lookup2D law (bilinear, edge values held): tab[i, j] at (xs[j], ys[i])."""
    u = min(max(u, xs[0]), xs[-1])
    v = min(max(v, ys[0]), ys[-1])
    j = min(max(int(np.searchsorted(xs, u) - 1), 0), len(xs) - 2)
    i = min(max(int(np.searchsorted(ys, v) - 1), 0), len(ys) - 2)
    fx = (u - xs[j]) / (xs[j + 1] - xs[j])
    fy = (v - ys[i]) / (ys[i + 1] - ys[i])
    lo = (1 - fx) * tab[i, j] + fx * tab[i, j + 1]
    hi = (1 - fx) * tab[i + 1, j] + fx * tab[i + 1, j + 1]
    return (1 - fy) * lo + fy * hi


class Plant:
    def __init__(self, cp, ct, tw):
        self.cp, self.ct, self.tw = cp, ct, tw
        self.c = T.CTRL
        self.d = T.ctrl_derived()

    def aero(self, w_r, v_rel, beta_rad):
        lam = w_r * T.R_TIP / v_rel
        bd = math.degrees(beta_rad)
        cp = interp2(lam, bd, TSR, PITCH, self.cp)
        ct = interp2(lam, bd, TSR, PITCH, self.ct)
        q = 0.5 * T.RHO * AREA * v_rel ** 2
        return {"lambda": lam, "cp": cp, "ct": ct, "power": q * v_rel * cp, "torque": q * v_rel * cp / w_r,
                "thrust": q * ct}

    def vs_torque(self, w, beta):
        c, d = self.c, self.d
        if w >= c["vs_rtgnsp"] or beta >= c["vs_rgn3mp"]:
            tq = c["vs_rtpwr"] / w
        elif w <= c["vs_ctinsp"]:
            tq = 0.0
        elif w < c["vs_rgn2sp"]:
            tq = d["vs_slope15"] * (w - c["vs_ctinsp"])
        elif w < d["vs_trgnsp"]:
            tq = c["vs_rgn2k"] * w * w
        else:
            tq = d["vs_slope25"] * (w - d["vs_sysp"])
        return min(tq, c["vs_maxtq"])

    def region(self, w, beta):
        c, d = self.c, self.d
        if w >= c["vs_rtgnsp"] or beta >= c["vs_rgn3mp"]:
            return "3"
        if w <= c["vs_ctinsp"]:
            return "1"
        if w < c["vs_rgn2sp"]:
            return "1.5"
        if w < d["vs_trgnsp"]:
            return "2"
        return "2.5"

    def steady(self, v: float) -> dict:
        """Closed-loop steady state at the hub-height wind v (tower at rest, deflected by the thrust)."""
        ref = self.c["pc_refspd"]

        def f(wg, beta=0.0):
            return self.aero(wg / T.GEAR, v, beta)["torque"] / T.GEAR - self.vs_torque(wg, beta)

        grid = np.linspace(self.c["vs_ctinsp"] * 0.98, ref, 400)
        vals = [f(w) for w in grid]
        wg = None
        for k in range(len(grid) - 1, 0, -1):      # the highest root below rated speed (pitch 0)
            if vals[k - 1] * vals[k] <= 0.0 and vals[k - 1] > 0.0 >= vals[k] or (vals[k - 1] > 0 and vals[k] < 0):
                wg = brentq(f, grid[k - 1], grid[k], xtol=1e-12)
                break
        if wg is not None and f(ref) < 0.0:
            beta = 0.0
        else:                                       # region 3: rated speed, pitch to the power
            wg = ref

            def g(b):
                return self.aero(ref / T.GEAR, v, b)["power"] - self.c["vs_rtpwr"]

            beta = brentq(g, 0.0, math.radians(PITCH[-1]), xtol=1e-12)
        a = self.aero(wg / T.GEAR, v, beta)
        tg = self.vs_torque(wg, beta)
        x = a["thrust"] / self.tw["k_gen"]
        return {"v": v, "region": self.region(wg, beta), "w_gen": wg, "w_rotor": wg / T.GEAR,
                "rpm_rotor": wg / T.GEAR / T.RPM, "rpm_gen": wg / T.RPM, "pitch": beta, "pitch_deg": math.degrees(beta),
                "t_gen": tg, "t_shaft": tg * T.GEAR, "twist": tg * T.GEAR / T.K_SHAFT,
                "p_mech": tg * wg, "p_elec": T.ETA_GEN * tg * wg, "p_aero": a["power"], "thrust": a["thrust"],
                "lambda": a["lambda"], "cp": a["cp"], "ct": a["ct"], "x_tower": x}

    def rhs_open(self, s, v, beta, tg):
        """Open-loop plant: s = [w_r, twist, w_g, x, xdot]; fixed pitch and generator torque."""
        w_r, th, w_g, x, xd = s
        a = self.aero(w_r, v - xd, beta)
        ts = T.K_SHAFT * th + T.C_SHAFT * (w_r - w_g / T.GEAR)
        tw = self.tw
        return np.array([(a["torque"] - ts) / T.J_ROTOR, w_r - w_g / T.GEAR, (ts / T.GEAR - tg) / T.J_GEN, xd,
                         (a["thrust"] - tw["k_gen"] * x - tw["c_gen"] * xd) / tw["m_gen"]])


def modes(plant: Plant, st: dict) -> dict:
    """Linearised open-loop modes about a steady state (central differences)."""
    s0 = np.array([st["w_rotor"], st["twist"], st["w_gen"], st["x_tower"], 0.0])
    n = len(s0)
    A = np.zeros((n, n))
    scale = np.array([1e-4, 1e-8, 1e-3, 1e-4, 1e-4])
    for k in range(n):
        dp = s0.copy()
        dm = s0.copy()
        dp[k] += scale[k]
        dm[k] -= scale[k]
        A[:, k] = (plant.rhs_open(dp, st["v"], st["pitch"], st["t_gen"]) -
                   plant.rhs_open(dm, st["v"], st["pitch"], st["t_gen"])) / (2 * scale[k])
    ev = np.linalg.eigvals(A)
    out = {"eigenvalues": [[float(e.real), float(e.imag)] for e in sorted(ev, key=lambda e: abs(e))]}
    osc = sorted([e for e in ev if e.imag > 0], key=lambda e: abs(e))
    for name, e in zip(("tower", "drivetrain"), osc):
        wn = abs(e)
        out[name] = {"wn": float(wn), "f_hz": float(wn / (2 * math.pi)), "zeta": float(-e.real / wn)}
    real = [e for e in ev if abs(e.imag) < 1e-9]
    out["rotor_pole"] = float(max(real, key=lambda e: e.real).real) if real else None
    return out


def main() -> int:
    print("BEM tables ...", flush=True)
    cp, ct = bem.tables(TSR, PITCH)
    fine = [(bem.rotor(l, 0.0)[0], l) for l in np.arange(6.5, 9.0, 0.05)]
    cp_max, tsr_opt = max(fine)
    tw = tower.tower_mode()
    plant = Plant(cp, ct, tw)
    winds = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 10.5, 11.0, 11.4, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0,
             19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0]
    steady = [plant.steady(v) for v in winds]
    report = {row[0]: row[2] for row in T.TABLE_7_1}
    for s in steady:
        if s["v"] in report:
            s["pitch_deg_report"] = report[s["v"]]
    # rated wind: the lowest wind at which the controller reaches rated speed and power with zero pitch
    ref = T.CTRL["pc_refspd"]
    v_rated = brentq(lambda v: plant.aero(ref / T.GEAR, v, 0.0)["power"] - T.CTRL["vs_rtpwr"], 9.0, 14.0)
    # open-loop operating point (8 m/s, region 2) and its modes
    ol = plant.steady(8.0)
    ol_modes = modes(plant, ol)
    # after a 5 % generator-torque step (fixed pitch): the stable branch (high lambda) of Ta(w) = N Tg
    tg1 = 1.05 * ol["t_gen"]
    w1 = brentq(lambda w: plant.aero(w, ol["v"], 0.0)["torque"] - T.GEAR * tg1, 0.8 * ol["w_rotor"], ol["w_rotor"])
    a1 = plant.aero(w1, ol["v"], 0.0)
    after = {"t_gen": tg1, "w_rotor": w1, "rpm_rotor": w1 / T.RPM, "lambda": a1["lambda"], "cp": a1["cp"],
             "thrust": a1["thrust"]}
    k, jr, jg = T.K_SHAFT, T.J_ROTOR, T.J_GEN * T.GEAR ** 2
    w_dt = math.sqrt(k * (1.0 / jr + 1.0 / jg))
    zeta_dt = T.C_SHAFT * (1.0 / jr + 1.0 / jg) / (2.0 * w_dt)
    out = {
        "source": "design/design.py (BEM: design/bem.py, tower: design/tower.py, data: design/nrel5mw.py)",
        "tables": {"tsr": TSR.tolist(), "pitch_deg": PITCH.tolist(), "cp": np.round(cp, 6).tolist(),
                   "ct": np.round(ct, 6).tolist()},
        "cp_peak": {"cp": cp_max, "tsr": float(tsr_opt), "pitch_deg": 0.0, "report_cp": T.CP_MAX_REPORT,
                    "report_tsr": T.TSR_OPT_REPORT, "cp_at_report_tsr": bem.rotor(T.TSR_OPT_REPORT, 0.0)[0]},
        "tower": tw,
        "rna": tower.rna_body(),
        "drivetrain": {"j_rotor": jr, "j_gen_lss": jg, "k": k, "c": T.C_SHAFT, "wn": w_dt, "f_hz": w_dt / (2 * math.pi),
                       "zeta": zeta_dt, "note": "two-inertia formula w = sqrt(k (1/J_r + 1/(N^2 J_g))), rigid blades"},
        "ctrl": {**T.CTRL, **T.ctrl_derived()},
        "v_rated": v_rated,
        "steady": steady,
        "open_loop": {"operating_point": ol, "modes": ol_modes, "after_step": after},
    }
    (HERE / "design.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"Cp max {cp_max:.4f} at lambda {tsr_opt:.2f} (report {T.CP_MAX_REPORT} at {T.TSR_OPT_REPORT})")
    print(f"tower f1 {tw['f1_hz']:.4f} Hz, m {tw['m_gen']:.0f} kg, k {tw['k_gen']:.4g} N/m")
    print(f"drivetrain {w_dt:.4f} rad/s = {w_dt / 2 / math.pi:.4f} Hz, zeta {zeta_dt:.4f}")
    print(f"rated wind {v_rated:.3f} m/s")
    print(" v   reg  rpm    pitch  (NREL)   Tg      Pel     thrust  lambda  cp")
    for s in steady:
        print(f"{s['v']:5.1f} {s['region']:>4} {s['rpm_rotor']:6.3f} {s['pitch_deg']:6.2f} "
              f"({s.get('pitch_deg_report', float('nan')):5.2f}) {s['t_gen']:8.1f} {s['p_elec'] / 1e6:6.3f} "
              f"{s['thrust'] / 1e3:7.1f} {s['lambda']:6.3f} {s['cp']:.4f}")
    print("open-loop modes at 8 m/s:", json.dumps({k: v for k, v in ol_modes.items() if k != "eigenvalues"}))
    print("open loop after the torque step:", json.dumps(after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
