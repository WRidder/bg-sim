# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""The analytic torque-speed curve of xl330-torque-speed, and its comparison with a run.

    uv run examples/microduck/design/torque_speed.py [<run_dir>]

With the goal far ahead the firmware asks for full PWM, so the duty is the upper edge of BAM's
current-limit window, min(1, (kt w + R i_limit)/V). The torque at the horn is the motor torque
minus the M6 friction (with tau_e = -tau_l, solved by fixed-point iteration) minus the armature
torque of the ramp acceleration.
"""

from __future__ import annotations

import math
import sys

import numpy as np

import build_model as bm
import xl330 as xl

SPEEDS = [-6.0, -3.0, -1.0, 1.0, 3.0, 5.0, 6.5, 8.0, 10.0, 14.0, 18.0]


def time_of(w: float) -> float:
    r = bm.SPEED_RAMP
    return r["t_start"] + (w - r["initial"]) / r["slope"]


def horn_torque(w: float, v=xl.V_NOMINAL, i_limit=xl.I_LIMIT) -> tuple[float, float, float]:
    """(tau_m, tau_l, current) at horn speed w during the ramp."""
    d = xl.duty(1e9, 0.0, w, v, i_limit=i_limit)
    tm = xl.motor_torque(d, w, v)
    acc = bm.SPEED_RAMP["slope"]
    tl = tm
    for _ in range(50):
        fl, fv = xl.bam_friction(tm, -tl, w)
        tl_new = tm - fl * math.tanh(w / xl.W_S) - fv * w - xl.BAM["armature"] * acc
        if abs(tl_new - tl) < 1e-14:
            break
        tl = tl_new
    return tm, tl, tm / xl.BAM["kt"]


def main() -> int:
    run = None
    if len(sys.argv) > 1:
        from readrun import read_run
        run = read_run(sys.argv[1])
    print(f"{'w':>6} {'t':>6} {'tau_m':>9} {'tau_l':>9} {'i':>7}" + ("   bgsim tau_m  bgsim tau_l" if run else ""))
    for w in SPEEDS:
        t = time_of(w)
        tm, tl, i = horn_torque(w)
        line = f"{w:6.1f} {t:6.3f} {tm:9.5f} {tl:9.5f} {i:7.4f}"
        if run:
            line += f"   {np.interp(t, run['t'], run['Servo/MotorTorque/y']):11.5f}  {np.interp(t, run['t'], run['Servo/Transmit/y']):11.5f}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
