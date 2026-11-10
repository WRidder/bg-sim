# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Reference numbers for the rocket example: writes design/design.json.

    uv run examples/rocket/design/design.py [--refit]

1. The Saturn V pitch program. The real vehicle flew a time-polynomial tilt program in the S-IC
   burn and the iterative guidance mode (IGM) on the upper stages; neither is published as a table
   in the AS-506 report. The model uses a piecewise-linear elevation command theta_cmd(t) (body
   x axis above the launch-site horizontal, inertial launch frame, as the Saturn instrument unit
   used), whose knot values are fitted here so that the planar reference matches the published
   altitude, flight-path angle and surface range at the five cutoff events (AS-506 Table 4-2) and
   the altitude at Mach 1 and at max Q (Table 4-1), with the attitude loop in the loop. Those
   quantities are therefore *fitted*; the speeds, the times of Mach 1 and max Q, the dynamic
   pressure, the accelerations and the masses are not, and the checks that compare them with the
   report are validations of the propulsion, mass and drag data. The fit is stored; `--refit`
   redoes it.
2. The full references (scipy, with the attitude loop through the gimbal) of the V-2 and of the
   Saturn V, and the analytic Tsiolkovsky numbers.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as d  # noqa: E402
import reference as r  # noqa: E402

OUT = HERE / "design.json"
PITCH_T = [0.0, d.T_PITCH, 25.0, 40.0, 55.0, 70.0, 85.0, 100.0, 120.0, 140.0, 160.0, 200.0, 260.0, 330.0, 400.0,
           460.0, 520.0, 560.0, 620.0, 712.0]
PITCH_GUESS = [90.0, 90.0, 88.0, 82.0, 72.0, 61.0, 51.0, 43.0, 34.0, 28.0, 23.0, 24.5, 23.6, 17.6, 9.0, 2.0, -3.3,
               -9.1, -16.2, -24.0]
T_END_SV = 712.0
T_END_V2 = 400.0


def event_residuals(sig: dict) -> list[float]:
    res = [(r.at(sig, "h", d.SV_MACH1["t"]) - d.SV_MACH1["h"]) / 300.0,     # altitude at Mach 1 (AS-506)
           (r.at(sig, "h", d.SV_MAXQ["t"]) - d.SV_MAXQ["h"]) / 300.0]       # altitude at max Q (AS-506)
    for ev in d.SV_EVENTS.values():
        res.append((r.at(sig, "h", ev["t"]) - ev["h"]) / 1000.0)        # 1 km
        res.append((r.at(sig, "fpa", ev["t"]) - ev["fpa"]) / 0.2)       # 0.2 deg
        res.append((r.at(sig, "s", ev["t"]) - ev["s"]) / 10_000.0)      # 10 km
    return res


def fit_pitch() -> list[float]:
    free = slice(2, len(PITCH_T))

    def resid(x):
        deg = PITCH_GUESS[:2] + list(x)
        v = r.saturn(PITCH_T, deg)
        sig = r.derived(r.simulate(v, T_END_SV, dt_out=0.5, rtol=1e-8, atol=1e-6))
        smooth = np.diff(np.array(deg), 2) / 6.0
        return np.concatenate([event_residuals(sig), smooth])

    sol = least_squares(resid, np.array(PITCH_GUESS[free]), diff_step=1e-3, x_scale=5.0, max_nfev=60, verbose=1)
    return [round(v, 4) for v in PITCH_GUESS[:2] + list(sol.x)]


def summary(sig: dict, events: dict) -> dict:
    out = {}
    for name, ev in events.items():
        t = ev["t"]
        out[name] = {k: r.at(sig, k, t) for k in ("h", "s", "speed", "fpa", "m", "acc", "theta", "dv")}
    return out


def main() -> int:
    old = json.loads(OUT.read_text()) if OUT.is_file() else {}
    if "--refit" in sys.argv or "pitch_deg" not in old:
        pitch = fit_pitch()
    else:
        pitch = old["pitch_deg"]

    # --- Saturn V, full reference (attitude loop through the gimbal)
    sv = r.saturn(PITCH_T, pitch)
    sv_sig = r.derived(r.simulate(sv, T_END_SV, dt_out=0.1))
    asc = sv_sig["t"] <= 200.0
    k_q = int(np.argmax(np.where(asc, sv_sig["qbar"], 0.0)))
    sv_ref = {
        "events": summary(sv_sig, d.SV_EVENTS),
        "mach1_t": r.crossing(sv_sig, "mach", 1.0),
        "mach1_h": float(np.interp(r.crossing(sv_sig, "mach", 1.0), sv_sig["t"], sv_sig["h"])),
        "maxq": float(sv_sig["qbar"][k_q]), "maxq_t": float(sv_sig["t"][k_q]), "maxq_h": float(sv_sig["h"][k_q]),
        "acc_oeco": r.at(sv_sig, "acc", 161.5),
        "acc_sii": r.at(sv_sig, "acc", 460.5),
        "acc_sivb": r.at(sv_sig, "acc", 699.3),
        "m_oeco": r.at(sv_sig, "m", d.T_OECO), "m_sii_oeco": r.at(sv_sig, "m", d.T_SII_OECO),
        "m_sivb_eco": r.at(sv_sig, "m", d.T_SIVB_ECO),
        "v_insert": r.at(sv_sig, "speed", d.T_INSERT), "h_insert": r.at(sv_sig, "h", d.T_INSERT),
        "delta_max": float(np.max(np.abs(sv_sig["delta"][sv_sig["t"] > 1.0]))),
    }
    # per-stage Tsiolkovsky (vacuum, published masses at ignition and cutoff)
    tsiol = {
        "S-IC": d.F1_C_VAC * math.log(d.M_HDA / d.M_OECO),
        "S-II": None,
        "S-IVB": d.SIVB_C * math.log(d.M_SIVB_IGN / d.M_SIVB_ECO),
    }
    # S-II burns at two exhaust velocities: high EMR to the EMR shift, then low EMR. The mass at the
    # shift is the reference run's (the report gives none).
    # The jettisons of the interstage and the tower split the burn: Tsiolkovsky holds piecewise.
    def m_at(t):
        return r.at(sv_sig, "m", t)
    tj = r.TAU_JET
    tsiol["S-II"] = (d.SII_C_HIGH * (math.log(d.M_SII_IGN / m_at(d.T_IS)) + math.log(m_at(d.T_IS + tj) / m_at(d.T_LET))
                                     + math.log(m_at(d.T_LET + tj) / m_at(d.T_EMR)))
                     + d.SII_C_LOW * math.log(m_at(d.T_EMR) / d.M_SII_OECO))

    # --- Saturn V in vacuum, without gravity and drag: the dv counter is Tsiolkovsky
    vac = r.saturn(PITCH_T, pitch, gravity=0.0, drag=0.0, ambient=0.0)
    vac_sig = r.derived(r.simulate(vac, T_END_SV, dt_out=0.1))
    sv_vac = {name: r.at(vac_sig, "dv", t) for name, t in
              (("dv_160", 160.0), ("dv_460", 460.0), ("dv_699", 699.0), ("dv_712", 712.0))}
    sv_vac |= {name: r.at(vac_sig, "m", t) for name, t in (("m_160", 160.0), ("m_200", 200.0), ("m_460", 460.0),
                                                         ("m_560", 560.0), ("m_699", 699.0))}

    # --- V-2
    v2_sig = r.derived(r.simulate(r.v2(), T_END_V2, dt_out=0.1))
    k_ap = int(np.argmax(v2_sig["h"]))
    up = v2_sig["t"] <= v2_sig["t"][k_ap]
    k_q2 = int(np.argmax(np.where(up, v2_sig["qbar"], 0.0)))
    v2_ref = {
        "v_burnout": r.at(v2_sig, "speed", d.V2["t_burn"]),
        "h_burnout": r.at(v2_sig, "h", d.V2["t_burn"]),
        "apogee": float(v2_sig["h"][k_ap]), "t_apogee": float(v2_sig["t"][k_ap]),
        "maxq": float(v2_sig["qbar"][k_q2]), "maxq_t": float(v2_sig["t"][k_q2]),
        "mach1_t": r.crossing(v2_sig, "mach", 1.0),
        "acc_burnout": r.at(v2_sig, "acc", 64.9),
        "m_burnout": r.at(v2_sig, "m", d.V2["t_burn"]),
    }
    m_f = d.V2["m0"] - d.V2["mdot"] * d.V2["t_burn"] - d.V2["mdot"] * d.TAU_ENGINE * (1.0 - math.exp(-15.0 / d.TAU_ENGINE))
    v2_vac = {"t": 80.0, "m_f": m_f, "dv": d.V2["c_vac"] * math.log(d.V2["m0"] / m_f)}
    vv = r.derived(r.simulate(r.v2(gravity=0.0, drag=0.0, ambient=0.0), 80.0, dt_out=0.1))
    v2_vac["speed_scipy"] = float(vv["speed"][-1])

    out = {
        "pitch_t": PITCH_T, "pitch_deg": pitch,
        "saturn": sv_ref, "saturn_vacuum": sv_vac, "tsiolkovsky_saturn": tsiol,
        "v2": v2_ref, "v2_vacuum": v2_vac,
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
