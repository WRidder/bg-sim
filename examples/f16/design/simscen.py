"""Reference runs of the `f16-sim` model (three-axis law, `sim3.py`) for its checks.

Each scenario is the f16-sim model with some of its global parameters overridden; the same
dictionary becomes the `overrides` of the check in expected.json (`build_model.py`). The model's
stimulus (stdlib Ramp pairs) is reproduced here:

    pulse(a, t0, dur)  = a (ramp(t; t0, FAST) - ramp(t; t0 + dur, FAST))          stick, pedals, kick
    throttle(t)        = thtl0 + (throttle - thtl0) ramp(t; throttle_t, THR_RAMP)

The trim of a scenario that starts elsewhere than the model's own point (500 ft/s, 10 000 ft)
is computed here and passed as the trim globals vt0, h0, alpha0, el0, thtl0.
"""

from __future__ import annotations

import math

import numpy as np

import f16_si as SI
import sim3

RTOD = 180.0 / math.pi
FAST = 0.05            # s, edges of the stick, pedal and kick pulses
THR_RAMP = 0.2         # s, throttle change
TURN_THROTTLE = 0.33   # the throttle of the 60 deg turn: about holds the 500 ft/s at 2 g
XCG = 0.35             # the f16-sim model's CG
POINT = (500.0, 10000.0)          # ft/s, ft: the model's start (M 0.46, qbar 219 psf)
HIALPHA_POINT = (260.0, 10000.0)  # slow: alpha about 17 deg in level flight

SWITCHES = ("limiter", "turn_comp", "roll_law", "yaw_damper", "beta_hold", "ari", "vv_roll")
# The stimulus globals of the model and their values (throttle_set defaults to the trim throttle).
STIM = {"pitch_amp": 0.0, "pitch_t": 1.0, "pitch_dur": 1.0, "roll_amp": 0.0, "roll_t": 1.0, "roll_dur": 1.0,
        "pedal_amp": 0.0, "pedal_t": 1.0, "pedal_dur": 1.0, "throttle_t": 1.0, "kick_amp": 0.0, "kick_t": 1.0,
        "kick_dur": 0.3}


def ramp(t, t0, tau):
    return min(1.0, max(0.0, (t - t0) / tau))


def pulse(a, t0, dur):
    return lambda t: a * (ramp(t, t0, FAST) - ramp(t, t0 + dur, FAST))


def trim_globals(vt_ft, h_ft, xcg=XCG):
    """The trim globals of the model (SI, deg) at a level-flight point."""
    tr = sim3.trim(vt_ft, h_ft, xcg)
    return tr, {"vt0": vt_ft * SI.FT, "h0": h_ft * SI.FT, "alpha0": tr["alpha"] * RTOD, "el0": tr["el"],
                "thtl0": tr["throttle"]}


def config(spec: dict, t_end: float, point=POINT) -> tuple[sim3.Config, dict]:
    """A sim3 configuration from the f16-sim globals `spec` (unset ones at the model's values)."""
    s = {**STIM, **spec}
    tr, tg = trim_globals(*point)
    thr = s.get("throttle_set", tg["thtl0"])
    cfg = sim3.Config(vt=point[0], h=point[1], xcg=XCG, t_end=t_end,
                      stick_p=pulse(s["pitch_amp"], s["pitch_t"], s["pitch_dur"]),
                      stick_r=pulse(s["roll_amp"], s["roll_t"], s["roll_dur"]),
                      pedal=pulse(s["pedal_amp"], s["pedal_t"], s["pedal_dur"]),
                      throttle=(lambda t: tg["thtl0"] + (thr - tg["thtl0"]) * ramp(t, s["throttle_t"], THR_RAMP)),
                      rdr_kick=pulse(s["kick_amp"], s["kick_t"], s["kick_dur"]))
    for k in SWITCHES:
        setattr(cfg, k, float(s.get(k, 1.0)))
    return cfg, tg


def series(r, every=5):
    return {k: [float(v) for v in r[k][::every]] for k in sim3.REC}


def lateral_modes(des, lat, point=POINT):
    """Linearised dutch roll of the nonlinear closed loop at the trim: the airframe alone, the yaw
    damper alone, the full law and the full law without the yaw damper."""
    tr, _ = trim_globals(*point)
    out = {}
    for name, sw in (("open_loop", dict(roll_law=0, yaw_damper=0, beta_hold=0, ari=0)),
                     ("yaw_damper", dict(roll_law=0, yaw_damper=1, beta_hold=0, ari=0)),
                     ("full", {}),
                     ("full_no_yaw_damper", dict(yaw_damper=0))):
        cfg = sim3.Config(vt=point[0], h=point[1], xcg=XCG)
        for k, v in sw.items():
            setattr(cfg, k, float(v))
        A = sim3.linearise(cfg, des, lat, tr)
        out[name] = sim3.dutch_roll(A)
        out[name]["eig"] = [[float(l.real), float(l.imag)] for l in np.linalg.eigvals(A)]
    return out


def turn_stick(des, lat, target=60.0, dur=1.0):
    """The roll stick that, held for `dur`, banks the aircraft to `target` deg (bisection)."""
    lo, hi = 0.1, 0.6
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        cfg, _ = config({"roll_amp": mid, "roll_dur": dur}, 4.0)
        cfg.out_every = 0.1
        phi = sim3.run(cfg, des, lat)["phi"][-1]
        lo, hi = (mid, hi) if phi < target else (lo, mid)
    return round(0.5 * (lo + hi), 4)


def run(design):
    des, lat = design["fbw"], design["lat"]
    out = {"point": POINT, "xcg": XCG, "fast": FAST, "throttle_ramp": THR_RAMP}
    _, out["trim"] = trim_globals(*POINT)
    _, out["trim_hialpha"] = trim_globals(*HIALPHA_POINT)
    out["modes"] = lateral_modes(des, lat)
    for k, v in out["modes"].items():
        print(f"sim modes {k}: dutch roll zeta {v['zeta']:.4f}, wn {v['wn']:.4f}")
    s_turn = turn_stick(des, lat)
    print(f"sim: roll stick {s_turn} for 1 s banks to 60 deg")
    scen = {
        # the model's own defaults: a coordinated 60 deg bank turn with more throttle
        "turn": ({"roll_amp": s_turn, "roll_dur": 1.0, "throttle_set": TURN_THROTTLE}, 30.0, POINT),
        "roll_step": ({"roll_amp": 0.25, "roll_dur": 2.0, "throttle_set": None}, 5.0, POINT),
        "full_roll": ({"roll_amp": 1.0, "roll_dur": 1.8, "throttle_set": None}, 6.0, POINT),
        "dutch_open": ({"kick_amp": 5.0, "roll_law": 0, "yaw_damper": 0, "beta_hold": 0, "ari": 0, "throttle_set": None},
                       12.0, POINT),
        "dutch_yd": ({"kick_amp": 5.0, "roll_law": 0, "yaw_damper": 1, "beta_hold": 0, "ari": 0, "throttle_set": None},
                     12.0, POINT),
        "dutch_full": ({"kick_amp": 5.0, "throttle_set": None}, 12.0, POINT),
        "hialpha_vv": ({"roll_amp": 1.0, "roll_dur": 1.5, "throttle_set": None}, 6.0, HIALPHA_POINT),
        "hialpha_body": ({"roll_amp": 1.0, "roll_dur": 1.5, "vv_roll": 0, "ari": 0, "throttle_set": None}, 6.0,
                         HIALPHA_POINT),
        "pull": ({"pitch_amp": 1.0, "pitch_dur": 3.0, "throttle_set": None}, 6.0, POINT),
    }
    for name, (spec, t_end, point) in scen.items():
        spec = {k: v for k, v in spec.items() if v is not None}
        cfg, tg = config(spec, t_end, point)
        r = sim3.run(cfg, des, lat)
        rec = {"spec": spec, "t_end": t_end, "point": point, "trim": tg, **series(r)}
        rec["max_abs_beta"] = float(np.max(np.abs(r["beta"])))
        rec["max_alpha"] = float(np.max(r["alpha"]))
        rec["max_nz"] = float(np.max(r["nz"]))
        rec["min_nz"] = float(np.min(r["nz"]))
        rec["max_abs_ail"] = float(np.max(np.abs(r["ail"])))
        rec["max_abs_rdr"] = float(np.max(np.abs(r["rdr"])))
        rec["max_ps"] = float(np.max(r["ps"]))
        rec["max_p_lim"] = float(np.max(r["p_lim"]))
        rec["h_dev"] = float(np.max(np.abs(np.array(r["h"]) - r["h"][0])))
        out[name] = rec
        print(f"sim {name}: |beta| max {rec['max_abs_beta']:.3f} deg, alpha max {rec['max_alpha']:.2f}, "
              f"nz {rec['min_nz']:.2f}..{rec['max_nz']:.2f}, ail {rec['max_abs_ail']:.2f}, rdr {rec['max_abs_rdr']:.2f}, "
              f"ps max {rec['max_ps']:.1f} (lim {rec['max_p_lim']:.1f}), phi end {r['phi'][-1]:.2f}, "
              f"h dev {rec['h_dev']:.1f} m, vt {r['vt'][0]:.1f}->{r['vt'][-1]:.1f}")
    return out
