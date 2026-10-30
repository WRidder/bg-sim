# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13", "matplotlib>=3.9"]
# ///
"""Write `models/pendulum-triple-cart.docs/` (W5.6 format) from two real bond-graph runs.

    uv run examples/pendulum-triple-cart/design/build_docs.py <run dir of pendulum-triple-cart> <run dir of pendulum-triple-cart-free>

The run folders are the `runs/<id>` folders of the backend (manifest.json + columns.f64) of the two models,
for example from `julia --project=julia/BGSim` or from a project copy opened in the editor. The text and the
figures come from `docsgen.py`; the design numbers are recomputed by `cartpend.design`.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[1] / "pendulum-double-cart" / "design"
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(SHARED))
import cartpend as cp  # noqa: E402
import docsgen  # noqa: E402
from design import SCENARIO  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    dyn, traj, tab = cp.design(SCENARIO)
    out = SCENARIO.root / "models" / f"{SCENARIO.model}.docs"
    metrics, dth, dx = docsgen.build(SCENARIO, dyn, tab, traj, sys.argv[1], sys.argv[2], out, {})
    print("docs written to", out)
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in metrics.items()})
