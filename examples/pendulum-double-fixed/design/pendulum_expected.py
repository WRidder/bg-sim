"""Writer of ``expected.json`` for the fixed-pivot pendulum examples (X5.11).

The reference numbers are the independent sampled-data integration of ``design.py`` (CVODES on the
non-linear design model with the winding current, the same control law and tables, the same
disturbance), never numbers read back from the bond-graph run.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from pendulum_common import TS, Dynamics, free_swing


def write_expected(prm, res: dict, pred: dict, path: Path) -> None:
    P, C = prm.PLANT, prm.CFG
    n = P.n
    dyn = Dynamics(P)
    a, xs = pred["a"], pred["x"]
    t_on, T_s, t_dist, t_end = C["t_on"], C["T_s"], C["t_dist"], C["t_end"]
    t_catch = res["t_catch"]
    pi = math.pi

    def at(time: float) -> int:
        return int(round(time / TS))

    sig = [f"Upright/a{k + 1}" for k in range(n)]
    checks: list[dict] = []
    add = checks.append

    # hanging at rest before t_on
    for k in range(n):
        add(dict(kind="cursor_value", signal=sig[k], t=0.0, value=-pi, abs=1e-9,
                 note=f"link {k + 1} hangs straight down at t = 0 (absolute angle from upright: -pi)"))
    for k in range(n):
        add(dict(kind="max_abs_le", signal=f"Joint{k + 1}/qdout", from_t=0.0, to_t=t_on - 0.002, value=1e-6,
                 note=f"joint {k + 1} stays at rest until the swing-up starts (measured 0; 1e-6 rad/s is far above the solver noise)"))
    add(dict(kind="max_abs_le", signal="Ctrl/u", from_t=0.0, to_t=t_on - 0.002, value=1e-9,
             note="the motor voltage is 0 until t_on"))
    add(dict(kind="cursor_value", signal="Ctrl/phase", t=t_on - 0.1, value=0.0, abs=1e-9, note="phase 0: hanging"))

    # swing-up, catch, balance
    add(dict(kind="cursor_value", signal="Ctrl/phase", t=t_on + 1.0, value=1.0, abs=1e-9,
             note="phase 1: swing-up along the optimised trajectory"))
    add(dict(kind="zero_crossing", signal="Ctrl/phase", level=1.5, direction="up", n=1, value=t_catch, abs=0.02,
             note=f"the LQR catches the chain at t = {t_catch:.3f} s (design.py; the trajectory ends at {t_on + T_s:g} s)"))
    add(dict(kind="cursor_value", signal="Ctrl/phase", t=t_dist - 0.1, value=2.0, abs=1e-9, note="phase 2: balance"))
    for tm in (round(t_on + f * T_s, 3) for f in (0.25, 0.5, 0.75)):
        for k in range(n):
            add(dict(kind="cursor_value", signal=sig[k], t=tm, value=float(a[at(tm), k]), abs=2e-3,
                     note=f"design.py: swing-up state of link {k + 1} at t = {tm:g} s (tolerance 2 mrad; the swing-up is "
                          "open-loop unstable, so a plant mismatch would grow, not stay small)"))
    for k in range(n):
        add(dict(kind="max_abs_le", signal=sig[k], from_t=t_on + T_s, to_t=t_dist - 0.01, value=math.radians(0.2),
                 note=f"upright reached by t_on + T_s = {t_on + T_s:g} s: link {k + 1} stays within 0.2 deg of upright until the disturbance"))
        band = float(np.abs(a[at(t_catch + 0.5): at(t_dist - 0.01), k]).max())
        add(dict(kind="max_abs", signal=sig[k], from_t=t_catch + 0.5, to_t=t_dist - 0.01, value=band, abs=2e-4,
                 note=f"design.py: link {k + 1} holds upright within {band:.2e} rad ({math.degrees(band):.4f} deg) before the disturbance"))

    # the disturbance is real and is recovered
    add(dict(kind="cursor_value", signal="DistForce/y", t=t_dist + 0.5 * C["pulse_len"], value=C["F"], abs=1e-9,
             note=f"the tip force pulse of {C['F']:g} N lasts {C['pulse_len'] * 1e3:g} ms from t = {t_dist:g} s"))
    add(dict(kind="cursor_value", signal="DistForce/y", t=t_dist + C["pulse_len"] + 0.05, value=0.0, abs=1e-9,
             note="the pulse is over"))
    post = slice(at(t_dist), at(t_dist + 3.0))
    for k in range(n):
        peak = float(np.abs(a[post, k]).max())
        add(dict(kind="max_abs", signal=sig[k], from_t=t_dist, to_t=t_dist + 3.0, value=peak, rtol=0.05,
                 note=f"design.py: peak deflection of link {k + 1} after the pulse, {math.degrees(peak):.2f} deg "
                      "(the disturbance is real: the value is checked, not bounded)"))
    add(dict(kind="max_abs", signal="Ctrl/u", from_t=t_dist, to_t=t_end, value=res["peak_u_after"], rtol=0.03,
             note="design.py: the voltage peak of the recovery"))
    for k in range(n):
        add(dict(kind="max_abs_le", signal=sig[k], from_t=t_end - 1.0, to_t=t_end, value=1e-3,
                 note=f"link {k + 1} is back at upright within 1e-3 rad (0.057 deg) over the last second (measured below 1e-4)"))
    for k in range(n):
        add(dict(kind="max_abs_le", signal=sig[k], from_t=res["recovered_1deg"] + 0.02, to_t=t_end, value=math.radians(1.0),
                 note=f"recovered: link {k + 1} is inside 1 deg from t = {res['recovered_1deg']:.2f} s on "
                      f"({res['recovered_1deg'] - t_dist:.2f} s after the pulse starts)"))

    # the motor
    add(dict(kind="max_abs_le", signal="Ctrl/u", from_t=0.0, to_t=t_end, value=P.umax,
             note=f"the motor voltage stays inside the {P.umax:g} V supply (clamp in the controller; design.py peak {res['peak_u_run']:.3f} V)"))
    add(dict(kind="max_abs", signal="Ctrl/u", from_t=0.0, to_t=t_end, value=res["peak_u_run"], abs=0.05,
             note="design.py: peak motor voltage of the whole run"))
    add(dict(kind="max_abs_le", signal="Motor/isense/y", from_t=0.0, to_t=t_end, value=P.umax / P.Rw,
             note=f"the winding current stays below the stall current {P.umax / P.Rw:g} A"))
    add(dict(kind="max_abs", signal="Joint1/qdout", from_t=0.0, to_t=t_end, value=float(np.abs(xs[:, n]).max()), rtol=0.03,
             note="design.py: peak rate of joint 1 over the run (rad/s)"))

    # scene
    fk = [dict(link=f"link{k + 1}", point=[P.lc[k], 0, 0], signals=[f"PoseB{k + 1}/g[2]", None, f"PoseB{k + 1}/g[3]"], tol=1e-6)
          for k in range(n)]
    fk.append(dict(link=f"link{n}", point=[P.L[-1], 0, 0], signals=["PoseTip/g[2]", None, "PoseTip/g[3]"], tol=1e-6))
    add(dict(kind="scene_bindings", fk=fk))
    codes = ["E901", "E106", "W201", "W202", "W205", "W206", "E101", "E103"]
    add(dict(kind="no_diagnostics", codes=codes,
             note="no solver failure, causal conflict, derivative-causal store, algebraic loop or event-limit stop"))

    # free swing: the design ODE (independent) against the bond graph
    x0 = np.array(list(C["free_q0"]) + [0.0] * n)
    tf, qf = free_swing(dyn, x0, C["free_t_end"], C["free_points"])
    diff = res.get("free_max_diff")
    free_checks = []
    for tm in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        for k in range(n):
            free_checks.append(dict(
                kind="cursor_value", signal=f"Joint{k + 1}/qout", t=tm, value=float(np.interp(tm, tf, qf[:, k])), abs=1e-4,
                note=f"design ODE (u = 0, Radau 1e-11) vs the bond graph, joint {k + 1} at t = {tm:g} s"
                     + (f"; the whole 3 s swing agrees to {diff:.1e} rad" if diff else "")))
    free_checks.append(dict(kind="no_diagnostics", codes=codes))

    doc = dict(
        project=prm.EXAMPLE,
        description=(
            f"X5.11 acceptance of {prm.EXAMPLE}. The reference numbers are design/design.py's independent sampled-data "
            "integration (CVODES on the non-linear design model with the winding current) of the same control law and "
            "tables, with the disturbance; the bond-graph run reproduces its link angles to about 1e-4 rad over the whole "
            "scenario. Model `free` is the plant without the controller, started away from the hanging position: its "
            "joint angles are compared with the design ODE, which proves that the design model is the bond graph."
        ),
        models={prm.EXAMPLE: dict(checks=checks, run_timeout=900), "free": dict(checks=free_checks)},
    )
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
