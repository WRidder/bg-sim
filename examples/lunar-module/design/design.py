# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Fit the descent guidance targets and write the reference numbers (design.json).

    uv run examples/lunar-module/design/design.py           # reference runs, design.json
    uv run examples/lunar-module/design/design.py --refit   # refit the guidance targets first

What is FITTED (least squares on the scipy reference, reference.py), each to published data:

* the PDI range to the landing site, to the throttle recovery at 386 s (MR 5.3);
* the acceleration through high gate (the braking-phase target is the high-gate state carried on
  for 60 s at that acceleration, as Apollo's P63 target lies beyond high gate), to the high-gate
  altitude 7,129 ft and descent rate 125 ft/s at 507 s (MR 5.3, table 5-I);
* the end time and height of the approach-phase (P64) target, to Aldrin's altitude and descent-rate
  callouts at 596 .. 611 s (ALSJ).

Everything else in design.json is an output of the reference runs: the bond-graph models are
checked against it (tight: the same equations), and against the published values not used above
(honest tolerances, see expected.json).
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
import reference as ref  # noqa: E402

OUT = HERE / "design.json"
X0 = [481.5, -1.3, 0.4, 690.0, 30.0]   # range km, a_hg x, a_hg z, T64 end, h64


def cfg_of(x) -> dict:
    return {"range_pdi": x[0] * 1e3, "a_hg": (x[1], 0.0, x[2]), "t64_end": x[3], "h64": x[4]}


def residuals(x):
    run = ref.Descent(**cfg_of(x)).run(t_end=d.T_P66, dt=0.5, rtol=1e-8, atol=1e-6)
    t, y = run["t"], run["y"]

    def at(tt):
        k = int(np.argmin(np.abs(t - tt)))
        return ref.readouts(y[k, 0:3], y[k, 3:6])
    res = [(run["ev"].get("throttle_recovery", 999.0) - d.T_THROTTLE_RECOVERY) / 2.0]
    hg = at(d.T_HG)
    res += [(hg["h"] - d.H_HG) / 30.0, (hg["rdot"] - d.HDOT_HG) / 1.0]
    for tc, alt, rate, _ in d.CALLOUTS[:4]:
        r = at(tc)
        res += [(r["h"] / d.FT - alt) / 20.0, (-r["rdot"] / d.FT - rate) / 2.0]
    return np.array(res)


def fit() -> list:
    sol = least_squares(residuals, X0, x_scale=[5.0, 0.3, 0.3, 10.0, 10.0], diff_step=1e-3, max_nfev=60)
    print("fit", sol.x.tolist(), "cost", sol.cost)
    print("residuals", np.round(residuals(sol.x), 3).tolist())
    return sol.x.tolist()


def sample(run, tt):
    t, y = run["t"], run["y"]
    k = int(np.argmin(np.abs(t - tt)))
    r = ref.readouts(y[k, 0:3], y[k, 3:6])
    r.update({"m": float(y[k, 13]), "T": float(y[k, 14]), "dv": float(y[k, 15]), "t": float(t[k])})
    return {k2: float(v) for k2, v in r.items()}


def main() -> int:
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if "--refit" in sys.argv or "fit_x" not in old:
        x = fit()
    else:
        x = old["fit_x"]
    cfg = cfg_of(x)
    out = {"fit_x": x, "descent_cfg": {k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.items()}}
    des = ref.Descent(**cfg)
    run = des.run(t_end=780.0, dt=0.1)
    ev = run["ev"]
    td = ev["td_state"]
    m_dry = d.M_PDI - d.PROP_PDI
    out["descent"] = {
        "throttle_recovery": float(ev["throttle_recovery"]),
        "touchdown": float(ev["touchdown"]),
        "td": {**{k: float(v) for k, v in ref.readouts(td[0:3], td[3:6]).items()}, "m": float(td[13]),
               "dv": float(td[15]), "prop_left": float(td[13] - m_dry)},
        "samples": {f"{tt:g}": sample(run, tt) for tt in
                    [0.0, 26.0, 100.0, 176.0, 258.0, 300.0, 384.0, 402.0, 450.0, 507.0, 550.0, 596.0, 606.0,
                     611.0, 617.0, 650.0, 700.0, 740.0]},
        "callouts": [{"t": c[0], **{k: v for k, v in sample(run, c[0]).items() if k in ("h", "rdot", "vh")}}
                     for c in d.CALLOUTS],
        "q0": ref.quat_from_rotm(ref.desired_frame(ref.Descent.quadratic(
            np.array(d.pdi_state(cfg["range_pdi"])["p"]), np.array(d.pdi_state(cfg["range_pdi"])["v"]),
            des.tgt63, 0.0) - ref.gravity(np.array(d.pdi_state(cfg["range_pdi"])["p"])), math.pi)).tolist(),
        "tgt63": {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in des.tgt63.items()},
        "tgt64": {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in des.tgt64.items()},
    }
    print("descent:", json.dumps({k: v for k, v in out["descent"].items() if k in ("throttle_recovery", "touchdown", "td")}))
    # ---- ascent
    asc = ref.Ascent()
    ra = asc.run(t_end=460.0, dt=0.1)
    cs = ra["ev"]["cut_state"]
    apo, peri = ref.orbit(cs[0:3], cs[3:6])
    k450 = int(np.argmin(np.abs(ra["t"] - 450.0)))      # after the thrust tail-off
    y450 = ra["y"][k450]
    apo450, peri450 = ref.orbit(y450[0:3], y450[3:6])
    out["ascent"] = {
        "after": {**sample(ra, 450.0), "apolune": float(apo450), "perilune": float(peri450)},
        "pitchover": float(ra["ev"]["pitchover"]), "cutoff": float(ra["ev"]["cutoff"]),
        "cut": {**{k: float(v) for k, v in ref.readouts(cs[0:3], cs[3:6]).items()}, "m": float(cs[13]),
                "dv": float(cs[15]), "apolune": float(apo), "perilune": float(peri)},
        "samples": {f"{tt:g}": sample(ra, tt) for tt in [5.0, 10.0, 20.0, 60.0, 120.0, 200.0, 300.0, 400.0, 430.0]},
        "q0": ref.quat_from_rotm(ref.desired_frame(np.array([0.0, 0.0, 1.0]), 0.0)).tolist(),
    }
    print("ascent:", json.dumps({k: v for k, v in out["ascent"].items() if k != "samples"}))
    # ---- ascent in vacuum, thrust held vertical: Tsiolkovsky
    av = ref.Ascent(gravity_scale=0.0, steer=0.0).run(t_end=300.0, dt=0.5)
    y = av["y"][-1]
    out["ascent_vacuum"] = {"t": float(av["t"][-1]), "speed": float(np.linalg.norm(y[3:6])), "m": float(y[13]),
                            "dv": float(y[15])}
    print("vacuum:", out["ascent_vacuum"])
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
