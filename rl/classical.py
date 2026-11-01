# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""The example's classical controller data for the RL variants (plan/RL_PLAN.md, risk 4):

    uv run rl/classical.py [out.json]      (default rl/classical.json)

- ``K``, ``P``: the 1 kHz discrete balance LQR of `pendulum-double-cart` (design/design.py, the same
  gain as library/DoubleCartCtrl.jl) and its cost-to-go matrix: the hybrid's catch region is
  z' P z < catch_tol with z = [x, th1, th2, v, w1, w2] (as the quad-pendulum firmwares do);
- the TVLQR swing-up tables (knots, feed-forward, nominal state, gains; T_s, t_on) for an
  imitation warm start of the swing-up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "examples" / "pendulum-double-cart" / "design"))
import cartpend as cp  # noqa: E402
import design as d  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "classical.json"
    sc = d.SCENARIO
    dyn, _, tab = cp.design(sc)
    K, P, _ = cp.dlqr(sc.plant, dyn, sc.Q, sc.R, 1e-3)
    data = {"K": K.tolist(), "P": P.tolist(), "Q": np.diag(sc.Q).tolist(), "R": sc.R,
            "t_on": tab.t_on, "T_s": tab.T_s, "tk": tab.tk.tolist(), "uff": tab.uff.tolist(),
            "xs": tab.xs.tolist(), "Ks": tab.Ks.tolist(), "u_max": tab.u_max}
    out.write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")
    print("K", np.round(K, 4))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
