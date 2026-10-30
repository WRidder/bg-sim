"""Write examples/robird/expected.json from the measurements of design/verify.py (tolerances justified in the notes)."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def write(res: dict) -> None:
    f = lambda v, n=4: round(float(v), n)
    T_END = 60.0
    diag = {"kind": "no_diagnostics", "codes": ["E901", "E106", "E007", "W201", "W202", "W205", "W206", "E001", "E101", "E102", "E003"]}
    full = [
        {"kind": "cursor_value", "signal": "Truth/z", "t": 0.0, "value": 25.0, "abs": 1e-9,
         "note": "the bird starts on the path at the cruise altitude z0 = 25 m"},
        {"kind": "cursor_value", "signal": "Truth/vw[1]", "t": 0.0, "value": f(res["v0x"], 3), "abs": 0.05,
         "note": "and at the cruise speed 12 m/s along the start tangent of the figure (its x component U cos(atan(2 B / A)))"},
        {"kind": "fft_peak", "signal": "JL1/qout", "from_t": 8.0, "to_t": T_END, "min_hz": 2.0, "max_hz": 6.0, "value": f(res["fft_flap"], 3),
         "rtol": 0.05,
         "note": "periodic flapping: the dominant frequency of the left wing flap angle (the commanded flapping frequency varies slowly between 3.7 and 4.5 Hz over the figure, mean 4.05 Hz; the spectrum peaks where it dwells longest, 3.8 Hz); the tolerance covers that modulation"},
        {"kind": "rms_difference", "signal": "Drv/wsense/y", "signal_b": "FlapCtl/w_cmd", "from_t": 3.0, "to_t": T_END,
         "value": f(res.get("w_track_rms", 60.0) * 1.5, 1),
         "note": "the motor speed follows the commanded speed N 2 pi f_cmd (rad/s, the reference is N = 28 times the crank speed); the residual is the within-stroke speed ripple of the wing inertia"},
        {"kind": "max_abs_le", "signal": "Guide/e_ct", "from_t": d_stat(), "value": 1.5,
         "note": f"cross-track error along the Lissajous after convergence (t >= 8 s): measured peak {f(res['cross_max'], 2)} m, bound 1.5 m (about 1 % of the 110 m figure and 1.2 wing spans)"},
        {"kind": "cursor_value", "signal": "Meas/rms_ct", "t": T_END, "value": f(res["cross_rms"], 3), "abs": 0.25,
         "note": "RMS cross-track error after convergence"},
        {"kind": "max_abs_le", "signal": "Guide/e_z", "from_t": d_stat(), "value": 1.5,
         "note": f"altitude error against the gentle altitude Lissajous z0 + 1.5 sin(th) after convergence: measured peak {f(res['alt_err_max'], 2)} m"},
        {"kind": "min_ge", "signal": "Truth/z", "from_t": d_stat(), "value": 21.5,
         "note": f"altitude band, lower side: z0 - Cz - 2 m margin (measured minimum {f(res['z_min'], 2)} m)"},
        {"kind": "max_abs_le", "signal": "Truth/z", "from_t": d_stat(), "value": 28.5,
         "note": f"altitude band, upper side: z0 + Cz + 2 m margin (measured maximum {f(res['z_max'], 2)} m)"},
        {"kind": "cursor_value", "signal": "Meas/x_max", "t": T_END, "value": f(res["x_max"], 1), "abs": 3.0,
         "note": "the figure is completed: the extent in +x is A = 110 m (within 3 m)"},
        {"kind": "cursor_value", "signal": "Meas/x_min", "t": T_END, "value": f(res["x_min"], 1), "abs": 3.0, "note": "extent in -x, A = 110 m"},
        {"kind": "cursor_value", "signal": "Meas/y_max", "t": T_END, "value": f(res["y_max"], 1), "abs": 3.0, "note": "extent in +y, B = 42 m"},
        {"kind": "cursor_value", "signal": "Meas/y_min", "t": T_END, "value": f(res["y_min"], 1), "abs": 3.0, "note": "extent in -y, B = 42 m"},
        {"kind": "cursor_value", "signal": "Meas/nx", "t": T_END, "value": f(res["nx"], 0), "abs": 0.5,
         "note": "sign changes of x after convergence: two zero crossings of x(t) = A sin in the rest of the lap"},
        {"kind": "cursor_value", "signal": "Meas/ny", "t": T_END, "value": f(res["ny"], 0), "abs": 0.5,
         "note": "sign changes of y: four zero crossings in one lap of y = B sin 2 th (the figure-eight is flown through)"},
        {"kind": "max_abs_le", "signal": "JTL/qout", "value": 0.5, "note": f"left elevon within +-0.5 rad (measured peak {f(res['tail_max'], 3)} rad)"},
        {"kind": "max_abs_le", "signal": "JTR/qout", "value": 0.5, "note": "right elevon within +-0.5 rad"},
        {"kind": "max_abs_le", "signal": "JTV/qout", "value": 0.5, "note": f"rudder within +-0.5 rad (measured peak {f(res['rudder_max'], 3)} rad)"},
        {"kind": "max_abs_le", "signal": "Drv/source/u", "value": 21.8, "note": "motor voltage below the duty limit 0.98 V_bat = 21.76 V of the 6S pack (measured peak %.1f V)" % res["u_max"]},
        {"kind": "max_abs_le", "signal": "Drv/isense/y", "value": 12.0, "note": "motor current below the assumed 12 A peak rating (measured peak %.1f A, mean %.1f A)" % (res["i_max"], res["i_mean"])},
        {"kind": "max_abs_le", "signal": "Fctl/phi", "value": 0.6, "note": "bank angle within the 0.6 rad (34 deg) limit (measured peak %.2f rad)" % res["phi_max"]},
        {"kind": "min_ge", "signal": "Fctl/speed", "from_t": d_stat(), "value": 10.0, "note": "speed stays above 10 m/s (measured minimum %.1f m/s)" % res["speed_min"]},
        {"kind": "max_abs_le", "signal": "Fctl/speed", "from_t": d_stat(), "value": 14.0, "note": "and below 14 m/s (measured maximum %.1f m/s)" % res["speed_max"]},
        {"kind": "cursor_value", "signal": "PaSum/Pavg", "t": 30.0, "value": f(res["p_air_mean"], 1), "abs": 5.0,
         "note": "energy sanity: the cycle-averaged power given to the air is about 16 W (the average electrical power is about 23 W, an overall efficiency of 70 %% from the bus to the air; measured mean over the figure %.1f W)" % res["p_air_mean"]},
        {"kind": "min_ge", "signal": "PaSum/Pavg", "from_t": 5.0, "value": 5.0, "note": "the aerodynamic power is positive on average (the wings only dissipate): lower bound 5 W"},
        {"kind": "max_abs_le", "signal": "Truth/qerr", "value": 1e-6, "note": "quaternion norm of the free fuselage stays 1"},
        {"kind": "scene_bindings"},
        diag,
    ]
    trim = [
        {"kind": "fft_peak", "signal": "JL1/qout", "from_t": 0.4, "to_t": 3.0, "min_hz": 2.0, "max_hz": 6.0, "value": f(res["trim"]["f0"], 3), "rtol": 0.05,
         "note": "open loop at the trim command: the wing flaps at the commanded frequency (the crank is speed controlled)"},
        {"kind": "max_abs_le", "signal": "JL1/qout", "value": 0.65, "note": "stroke amplitude about 0.5 rad (measured %.3f)" % res.get("trim_flap_amp", 0.5)},
        {"kind": "cursor_value", "signal": "PaSum/Pavg", "t": 3.0, "value": f(res.get("trim_p_air", 12.0), 1), "abs": 6.0,
         "note": "the averaged aerodynamic power of the straight trim flight (compare 16 W averaged over the figure)"},
        {"kind": "no_diagnostics", "codes": diag["codes"]},
    ]
    doc = {
        "project": "robird",
        "description": ("X5.15. A 0.70 kg robotic peregrine falcon after van der Grinten, Folkertsma, Nijenhuis and Stramigioli (2015): a floating "
                        "multibond fuselage, two wings of two aeroelastic segments each (compliant joints, strip-theory aerodynamics with C_L and C_D "
                        "affine in the angle of attack), three tail flaps on first-order servos and a motor-gear-crank flapping drive. A cycle-averaged "
                        "discrete controller (100 Hz attitude/speed loops, 50 Hz look-ahead path guidance) flies a 220 m x 84 m horizontal "
                        "1:2 Lissajous figure of eight with a gentle altitude component at 12 m/s in 60 s. Every number is a measurement of this "
                        "model on the real worker (design/verify.py)."),
        "models": {
            "robird": {"run_timeout": 1800, "checks": full},
            "robird-trim": {"run_timeout": 900, "checks": trim},
        },
    }
    (ROOT / "expected.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json:", len(full), "+", len(trim), "checks")


def d_stat() -> float:
    return 8.0


if __name__ == "__main__":
    write(json.loads((HERE / "results.json").read_text()))
