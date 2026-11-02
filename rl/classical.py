# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""The example's classical controller data for the RL variants (plan/RL_PLAN.md, risk 4):

    uv run rl/classical.py [out.json]              (default rl/classical.json: pendulum-double-cart)
    uv run rl/classical.py --rig lab [out.json]    (default rl/classical_lab.json: pendulum-double-cart-lab)

- ``K``, ``P``: the 1 kHz discrete balance LQR of the example (its design/design.py, the same gain as
  the firmware block) and its cost-to-go matrix: the hybrid's catch region is z' P z < catch_tol with
  z = [x, th1, th2, v, w1, w2] (as the quad-pendulum firmwares do);
- the TVLQR swing-up tables (knots, feed-forward, nominal state, gains; T_s, t_on) for an imitation
  warm start of the swing-up;
- ``plant``: the design model's link masses, centres of mass and inertias (the env's energy terms).

The lab rig's tables are read from its design/design.json (not re-optimised); K is recomputed from the
lab design model and checked against the stored Klqr.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "examples"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def cart():
    sys.path.insert(0, str(EXAMPLES / "pendulum-double-cart" / "design"))
    import cartpend as cp
    import design as d
    sc = d.SCENARIO
    dyn, _, tab = cp.design(sc)
    K, P, _ = cp.dlqr(sc.plant, dyn, sc.Q, sc.R, 1e-3)
    return sc, tab, K, P


def lab():
    d = _load(EXAMPLES / "pendulum-double-cart-lab" / "design" / "design.py", "lab_design")
    cp = d.cp
    sc = d.SCENARIO
    tab = d.load_tables()
    dyn = cp.Dynamics(sc.plant)
    K, P, _ = cp.dlqr(sc.plant, dyn, sc.Q, sc.R, 1e-3)
    err = np.max(np.abs(K - np.asarray(tab.Klqr)) / np.abs(np.asarray(tab.Klqr)))
    assert err < 1e-9, f"K differs from design.json Klqr by {err:.3g}"
    return sc, tab, K, P


def main() -> int:
    args = list(sys.argv[1:])
    rig = "cart"
    if "--rig" in args:
        i = args.index("--rig")
        rig = args[i + 1]
        del args[i:i + 2]
    out = Path(args[0]) if args else HERE / ("classical.json" if rig == "cart" else f"classical_{rig}.json")
    sc, tab, K, P = cart() if rig == "cart" else lab()
    pl = sc.plant
    data = {"rig": rig, "K": K.tolist(), "P": P.tolist(), "Q": np.diag(sc.Q).tolist(), "R": sc.R,
            "t_on": tab.t_on, "T_s": tab.T_s, "tk": tab.tk.tolist(), "uff": tab.uff.tolist(),
            "xs": tab.xs.tolist(), "Ks": tab.Ks.tolist(), "u_max": tab.u_max,
            "plant": {"m": list(pl.m), "c": list(pl.c), "J": list(pl.J), "L": list(pl.L), "x_rail": pl.x_rail}}
    out.write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")
    print("K", np.round(K, 4))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
