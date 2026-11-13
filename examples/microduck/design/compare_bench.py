# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Compare a run of xl330-step with the BAM identification simulator (design/xl330.py).

    uv run examples/microduck/design/compare_bench.py <run_dir> [--json out.json]
"""

from __future__ import annotations

import json
import sys

import numpy as np

import build_model as bm
import xl330 as xl
from readrun import read_run

TIMES = [0.13, 0.15, 0.2, 0.3, 0.5, 0.85, 0.93, 0.95, 1.0, 1.1, 1.5]


def reference(gap: float = 0.0):
    mgl = bm.BENCH["m"] * bm.G0 * bm.BENCH["l"]
    return xl.simulate_pendulum(bm.bench_goal, 1.6, bm.BENCH_INERTIA, mgl)


def main() -> int:
    run = read_run(sys.argv[1])
    t, q, w, tm = reference()
    rows = []
    for tt in TIMES:
        rows.append((tt, float(np.interp(tt, run["t"], run["Servo/Encoder/y"])), float(np.interp(tt, t, q)),
                     float(np.interp(tt, run["t"], run["Servo/MotorTorque/y"])), float(np.interp(tt, t, tm))))
    print(f"{'t':>6} {'q bgsim':>10} {'q BAM':>10} {'diff':>9}   {'tau_m bgsim':>11} {'tau_m BAM':>10}")
    for r in rows:
        print(f"{r[0]:6.2f} {r[1]:10.5f} {r[2]:10.5f} {r[1]-r[2]:9.5f}   {r[3]:11.5f} {r[4]:10.5f}")
    qi = np.interp(t, run["t"], run["Servo/Encoder/y"])
    print("max |q diff| over the run:", float(np.max(np.abs(qi - q))))
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        json.dump({"rows": rows, "max_diff": float(np.max(np.abs(qi - q)))}, open(out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
