# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Fit the low-advance-ratio correction of the c172p propeller tables to the POH.

    uv run examples/cessna/design/prop_fit.py            # the fit (a few minutes)
    uv run examples/cessna/design/prop_fit.py --check    # evaluate the tables in c172_data.py

With FGPiston's own ISFC calibration (the rated 160 hp) the prop_75in2f tables of JSBSim's c172p
make too little thrust at low speed: the static rpm is 2195 (POH 2300 to 2420), the climb at
76 KIAS 512 ft/min (POH 700) and the take-off ground roll 1492 ft (POH 892). The correction
(`c172_data.prop_correction`) scales C_T and C_P by a cosine taper that is 1 + k at J = 0 and
fades to exactly 1 at J1, so the cruise and maximum-speed range (J about 0.7 to 0.8) keeps the
JSBSim tables. This script finds kT, kP, J1T and J1P by weighted least squares on the POH
targets (`poh.py`), in priority order: the sea-level climb at 76 KIAS, the static rpm, the
take-off ground roll and distance over 50 ft, and the climb at 8000 ft.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import c172_data as D  # noqa: E402
import perf as P  # noqa: E402
import c172_ref as M  # noqa: E402
import poh  # noqa: E402

KT = P.KT
FT = P.FT
PERF = poh.PERFORMANCE

# (target, scale, weight): the residual is weight * (value - target) / scale. The static rpm is
# weighted most, so it stays inside the POH range. Two targets get half weight because the
# propeller is not what keeps them off the POH: the distance over 50 ft (the model lifts off at
# about 54 KCAS, POH 51 KIAS, since c172p's flaps-10 stall is 3 kt high, and then accelerates in
# ground effect to its climb speed) and the climb at 8000 ft (the model loses less climb with
# altitude than the POH). With full weight the fit raises the static C_T further (kT 0.5) and
# trades the ground roll and the 8000 ft climb for the 50 ft distance.
TARGETS = {
    "roc_sl_76": (PERF["roc_sl_fpm"][0], 700.0, 3.0),
    "static_rpm": (0.5 * (poh.STATIC_RPM[0][0] + poh.STATIC_RPM[0][1]), 2360.0, 4.0),
    "takeoff_roll_ft": (PERF["takeoff_roll_ft"][0], 892.0, 1.0),
    "takeoff_50ft_ft": (PERF["takeoff_50ft_ft"][0], 1628.0, 0.5),
    "roc_8000_72": (PERF["roc_8000_fpm"][0], 332.0, 0.5),
}
# one-sided: the maximum speed at sea level (126.2 KTAS with the JSBSim tables, POH 123 kt) must
# not get worse; (limit, scale, weight)
VMAX_LIMIT = (126.2, 1.0, 3.0)


def set_tables(kT, j1T, kP, j1P):
    D.C_THRUST, D.C_POWER = D.prop_correction(kT, j1T, kP, j1P)


def roc_at(kcas, h):
    x, c, info = P.trim_cas(kcas * KT, h, throttle=1.0, mixture=P.best_power_mixture(h),
                            guess=[0.08, 0, -0.2, 0, 0, 0.05, 240.0])
    return info["vt"] * math.sin(info["gamma"]) / FT * 60.0, info


def evaluate(full=False):
    out = {}
    out["roc_sl_76"], i76 = roc_at(76.0, 0.0)
    out["rpm_sl_76"] = i76["rpm"]
    out["roc_8000_72"], _ = roc_at(72.0, 8000 * FT)
    x, c, g = P.ground_state(throttle=1.0, flap_deg=10.0)
    o = M.outputs(x, c, M.Params())
    out["static_rpm"] = o["rpm"]
    out["static_thrust_n"] = o["thrust"]
    to = P.takeoff()
    out["takeoff_roll_ft"] = to["x"] / FT
    out["takeoff_50ft_ft"] = to["x50"] / FT
    out["kcas_liftoff"] = to["kcas"]
    out["vmax_sl_ktas"] = P.level_full_throttle(0.0)["ktas"]
    if full:
        out["climb_sl"] = P.best_climb(0.0)
        out["climb_8000"] = P.best_climb(8000 * FT)
        out["vmax_sl"] = P.level_full_throttle(0.0)
        out["vmax_8000"] = P.level_full_throttle(8000 * FT)
    return out


def residuals(z, log):
    t0 = time.time()
    set_tables(*z)
    ev = evaluate()
    r = [w * (ev[k] - tgt) / sc for k, (tgt, sc, w) in TARGETS.items()]
    lim, sc, w = VMAX_LIMIT
    r.append(w * max(0.0, ev["vmax_sl_ktas"] - lim) / sc)
    log.append((list(z), ev))
    print(f"  z={np.round(z, 4).tolist()} " + " ".join(f"{k}={ev[k]:.1f}" for k in (*TARGETS, "vmax_sl_ktas"))
          + f" |r|={np.linalg.norm(r):.4f} ({time.time() - t0:.1f} s)", flush=True)
    return np.array(r)


def efficiency_table(ct, cp):
    js = np.linspace(0.0, 1.1, 12)
    return [(float(j), float(j * M.lookup1(j, ct) / M.lookup1(j, cp))) for j in js]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="evaluate the tables in c172_data.py only")
    ap.add_argument("--x0", type=float, nargs=4, default=None)
    args = ap.parse_args()
    if args.check:
        for label, z in (("JSBSim", (0.0, 1.0, 0.0, 1.0)), ("fitted", D.PROP_FIT)):
            set_tables(*z)
            ev = evaluate(full=True)
            print(label, z)
            for k, v in ev.items():
                print(f"  {k}: {v}")
            print("  efficiency:", [(j, round(e, 3)) for j, e in efficiency_table(D.C_THRUST, D.C_POWER)])
        return 0
    log = []
    x0 = args.x0 or [0.4, 0.72, -0.18, 0.73]
    sol = least_squares(residuals, x0, args=(log,), bounds=([0.0, 0.4, -0.4, 0.4], [0.6, 1.0, 0.1, 1.0]),
                        diff_step=1e-3, xtol=1e-3, ftol=1e-3)
    print("fit:", np.round(sol.x, 4).tolist(), "cost", sol.cost)
    set_tables(*sol.x)
    ev = evaluate(full=True)
    for k, v in ev.items():
        print(f"  {k}: {v}")
    print("  efficiency:", [(j, round(e, 3)) for j, e in efficiency_table(D.C_THRUST, D.C_POWER)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
