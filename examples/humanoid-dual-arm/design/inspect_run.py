# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Print a summary of a humanoid-hold run (development aid).

    uv run examples/humanoid-dual-arm/design/inspect_run.py <run_dir> [t ...]
"""

from __future__ import annotations

import sys

import numpy as np

import humanoid as dz
import srs
from runio import at, load_run


def main() -> None:
    t, c = load_run(sys.argv[1])
    times = [float(x) for x in sys.argv[2:]] or list(np.linspace(t[0], t[-1], 7))
    print(f"t {t[0]}..{t[-1]}, {len(t)} samples")
    q0 = dz.Q_START
    for tt in times:
        print(f"--- t = {tt:.3f}")
        for p in ("L", "R"):
            q = np.array([at(t, c[f"{p}J{k}/qout"], tt) for k in range(1, 8)]) / srs.D
            ik = np.array([at(t, c[f"IK{p}/q{k}"], tt) for k in range(1, 8)])
            print(f"  {p} q {np.round(q, 3)}  ik-q {np.round(q - ik, 3)}")
            print(f"    hand err {at(t, c[f'{p}HandError/e_mm'], tt):.3f} mm {at(t, c[f'{p}HandError/e_deg'], tt):.3f} deg;"
                  f" grasp F {at(t, c[f'{p}GraspLoad/F'], tt):.2f} N M {at(t, c[f'{p}GraspLoad/M'], tt):.3f};"
                  f" u {np.round([at(t, c[f'Servo{p}/u{k}'], tt) for k in range(1, 8)], 2)}")  # fmt: skip
        print(f"  box err {at(t, c['BoxError/e_mm'], tt):.3f} mm {at(t, c['BoxError/e_deg'], tt):.3f} deg; "
              f"elbow L {np.round([at(t, c[f'LW4/g[{k}]'], tt) for k in (5, 6, 7)], 4)}")  # fmt: skip
    print("start q", np.round(q0, 3))


if __name__ == "__main__":
    main()
