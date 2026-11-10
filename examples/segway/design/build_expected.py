# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Writes ``expected.json`` of the `segway` example from the numbers of ``design.py`` (read from
``design/design.json``, which ``design.py`` writes). Every reference is independent of the bond graph:
the analytic linearisation, the Riccati design and the non-linear Lagrange reference simulation of
``design.py`` (RK4, same controller), or a published figure.

    uv run examples/segway/design/design.py && uv run examples/segway/design/build_expected.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DES = json.loads((ROOT / "design" / "design.json").read_text(encoding="utf-8"))
P = DES["params"]
SC = DES["scenario"]

NO_DIAG = {
    "kind": "no_diagnostics",
    "codes": ["E901", "E106", "W201", "W202", "W206"],
    "note": "no solver failure, no causal conflict, no derivative-causal store (the motors are ideal torque sources and the "
            "joints are compliant, so every store is integral), no algebraic loop, no event-limit stop",
}
SCENE = {
    "kind": "scene_bindings",
    "note": "the body and the two wheels follow their composed poses (body: PoseIntegrator3D, wheels: body pose o mount o axle joint)",
}


def cv(signal, t, value, abs_, note):
    return {"kind": "cursor_value", "signal": signal, "t": t, "value": round(value, 6), "abs": abs_, "note": note}


def mx(signal, lo, hi, value, abs_, note, rtol=None):
    c = {"kind": "max_abs", "signal": signal, "from_t": lo, "to_t": hi, "value": round(value, 6), "abs": abs_, "note": note}
    if rtol:
        c["rtol"] = rtol
    return c


def le(signal, value, note, lo=None, hi=None):
    c = {"kind": "max_abs_le", "signal": signal, "value": value, "note": note}
    if lo is not None:
        c["from_t"], c["to_t"] = lo, hi
    return c


def limits(prefix_note=""):
    return [
        le("Ctrl/tau_l", P["tau_max"] + 1e-6, "the torque of each wheel stays within the stated peak torque of 80 N m (an estimate of a PT-class drive)"),
        le("Ctrl/vreq_l", P["U_max"], "the terminal voltage the motor needs, R i + k_t n (joint rate), stays below the 72 V battery bus (estimate, see README)"),
        le("Ctrl/vreq_r", P["U_max"], "same for the wheel at -y"),
    ]


def contact_checks():
    return [
        le("TyreL/s_lat", 3e-4, "lateral creep of the tyre stays below 0.3 mm/s: the friction cone is far from saturated (measured at most 0.12 mm/s, in the turns)"),
        le("TyreL/s_lon", 3e-4, "longitudinal creep below 0.3 mm/s (measured at most 0.21 mm/s, in the first 10 ms while the tyre settles): the contact rolls without slipping"),
    ]


def build() -> dict:
    cur = DES["cursors"]
    models = {}

    # ---------------------------------------------------------------- balance
    ch = [SCENE]
    ch.append(cv("TyreL/f_n", 3.0, (P["m_b"] / 2 + P["m_w"]) * P["g"], 8.0,
                 "static load of one wheel, (m_b / 2 + m_w) g = 564 N (statics, independent): the vehicle balances upright at rest"))
    for t in ("0.5", "1.0", "4.0", "5.0", "9.4"):
        c = cur[t]
        ch.append(cv("Sense/theta", float(t), c["theta"], 0.002 if t in ("4.0", "5.0", "9.4") else 0.0006,
                     f"body pitch at t = {t} s from the non-linear Lagrange reference of design.py (same LQR, RK4)"))
    for t in ("5.0", "7.0", "9.1", "12.0"):
        c = cur[t]
        ch.append(cv("Ctrl/v", float(t), c["v"], 0.02, f"axle speed at t = {t} s from the reference simulation (speed ramp from 3 s, push at 9 s)"))
    ch.append(cv("Sense/xa", 12.0, cur["12.0"]["x"], 0.05, "distance travelled by t = 12 s, reference simulation"))
    ch.append(cv("Ctrl/tau_l", 4.0, cur["4.0"]["tau"] / 2, 0.8, "torque of one wheel during the acceleration, half the reference total torque"))
    ch.append(cv("Ctrl/v", 14.0, SC["v_step"], 0.02,
                 "steady-state speed tracking: the speed ends at the 1.5 m/s set-point (the integral of the speed error removes any offset); reference 1.497 m/s"))
    ch.append(mx("Sense/theta", 0.0, 14.0, DES["peaks"]["theta"], 0.006, "largest body pitch of the run (the lean while accelerating), reference simulation"))
    ch.append(mx("Sense/theta", 9.0, 11.0, DES["peaks"]["theta_push"], 0.004, "largest pitch after the 150 N push at t = 9 s: the push is rejected, the vehicle never falls"))
    ch.append(mx("Ctrl/tau_l", 0.0, 14.0, DES["peaks"]["tau"], 1.5, "largest wheel torque of the run, reference simulation (design.py prints it)"))
    ch.append(mx("Ctrl/vreq_l", 0.0, 14.0, DES["peaks"]["v_req"], 0.8, "largest terminal voltage the motors need, reference simulation"))
    ch += limits()
    ch += contact_checks()
    ch.append(mx("Sense/wz", 0.0, 14.0, 0.0, 1e-3, "straight ahead: the yaw rate stays zero (the two wheels see the same torque)"))
    ch.append(NO_DIAG)
    models["balance"] = {"checks": ch}

    # ---------------------------------------------------------------- open loop
    op = DES["open"]
    ch = [SCENE]
    for t, v in op["cursors"].items():
        ch.append(cv("Sense/theta", float(t), v, max(2e-4, 0.03 * v),
                     f"free fall from {op['theta0']} rad at t = {t} s: non-linear reference simulation of design.py with no control; the tilt "
                     f"grows with the unstable pole +{DES['open_loop'][-1]:.4f} 1/s of the analytic linearisation"))
    ch.append(NO_DIAG)
    models["open-loop"] = {"checks": ch}

    # ---------------------------------------------------------------- top speed
    tp = DES["top"]
    ch = [SCENE]
    for t, c in tp["cursors"].items():
        if float(t) < 4:
            continue
        ch.append(cv("Ctrl/v", float(t), c["v"], 0.03, f"axle speed at t = {t} s from the reference simulation (ramp to 20 km/h from t = {tp['t_ramp0']} s)"))
    for t in ("6.0", "11.0", "17.0"):
        ch.append(cv("Sense/theta", float(t), tp["cursors"][t]["theta"], 0.004, f"body pitch at t = {t} s, reference simulation"))
    for t in ("8.0", "11.0", "17.0"):
        ch.append(cv("Ctrl/vreq_l", float(t), tp["cursors"][t]["V"], 1.0, f"voltage the motor needs at t = {t} s, reference simulation"))
    ch.append(cv("Ctrl/v", tp["t_end"], tp["v_step"], 0.03,
                 "the published top speed of the Segway i2, 20 km/h = 5.556 m/s (Segway i2 reference manual: specifications), is reached and held"))
    ch.append(cv("Ctrl/vreq_l", tp["t_end"], P["K"] * tp["v_step"] / P["r"], 0.8,
                 "at constant speed the voltage is the back-EMF, k_t n v / r = 2.88 * 5.556 / 0.24 = 66.7 V (analytic): the 72 V bus has 8 % margin"))
    ch.append(mx("Ctrl/vreq_l", 0.0, tp["t_end"], tp["peak_v"], 1.0, "peak voltage demand of the run (overshoot of the speed loop at the end of the ramp), reference simulation"))
    ch.append(mx("Sense/theta", 0.0, tp["t_end"], tp["peak_theta"], 0.006, "largest lean of the run (while accelerating), reference simulation"))
    ch += limits()
    ch += contact_checks()
    ch.append(NO_DIAG)
    models["top-speed"] = {"checks": ch}

    # ---------------------------------------------------------------- figure of eight
    ei = DES["eight"]
    ec = ei["cursors"]
    ch = [SCENE]
    for t in ("6.0", "9.5", "12.0", "15.0", "20.0", "24.0", "28.0"):
        c = ec[t]
        ch.append(cv("Sense/heading", float(t), c["psi"], 0.02, f"heading at t = {t} s: non-linear pitch plane plus the yaw loop and kinematic path of design.py"))
        ch.append(cv("Sense/xa", float(t), c["x"], 0.06, f"axle position x at t = {t} s, reference path (path length 1.5 m/s * t)"))
        ch.append(cv("Sense/ya", float(t), c["y"], 0.06, f"axle position y at t = {t} s, reference path"))
    ch.append(cv("Ctrl/v", 28.0, SC["v_step"], 0.01, "the cruise speed 1.5 m/s is held through both circles"))
    ch.append(cv("Sense/heading", 28.0, 0.0, 0.01, "the heading returns to 0: the eight is closed (+2 pi, then -2 pi)"))
    ch.append(cv("Sense/wz", 9.5, ec["9.5"]["dpsi"], 0.01, "yaw rate on the first circle, 2 pi / 11 s = 0.571 rad/s"))
    ch.append(cv("Sense/wz", 20.0, ec["20.0"]["dpsi"], 0.01, "yaw rate on the second circle, -0.571 rad/s"))
    ch.append(mx("Sense/wz", 0.0, 28.0, ei["peak_rate"], 0.01, "peak yaw rate of the eight, reference"))
    ch.append(mx("Ctrl/tau_l", 0.0, 28.0, ei["peak_tau"], 1.5,
                 "largest wheel torque of the run: the start-up acceleration (the same pitch-plane reference as `balance`, from upright)"))
    ch.append(mx("Sense/theta", 0.0, 28.0, ei["peak_theta"], 0.006, "largest pitch (the lean during the speed-up), reference"))
    ch += limits()
    ch += contact_checks()
    ch.append(NO_DIAG)
    models["figure-eight"] = {"checks": ch}

    return {
        "project": "segway",
        "description": (
            "Acceptance of the segway example: a two-wheeled self-balancing transporter with a rider as a 3D bond graph "
            "(RigidBody3D body on a PoseIntegrator3D, two RigidBody3D wheels on Revolute3D axle joints, RollingDisk tyre contacts, "
            "MSe motor torques, ExternalWrenchSpatial push). The references are independent of the bond graph: the analytic "
            "linearisation (open-loop pole +5.23 1/s) and Riccati design of design/design.py, its non-linear Lagrange reference "
            "simulation of the same closed loop (RK4), the statics of the load, and the published top speed of the Segway i2. "
            "No flight or test log of a Segway with a rider could be found, so the physical parameters are estimates apart from "
            "the quoted specifications (see the README)."
        ),
        "models": models,
    }


if __name__ == "__main__":
    doc = build()
    (ROOT / "expected.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote expected.json:", {k: len(v["checks"]) for k, v in doc["models"].items()})
