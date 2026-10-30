# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Controller design for pendulum-triple-fixed (X5.11): swing-up, catch, balance of a triple pendulum.

Same flow as ``pendulum-double-fixed/design/design.py`` (shared code in that folder's
``pendulum_common.py`` / ``pendulum_flow.py``), applied to the three-link plant of ``params.py``:
Lagrangian dynamics, direct-collocation swing-up (Hermite-Simpson, IPOPT), time-varying LQR along the
trajectory, a 1 kHz LQR for the balance, the catch rule ``V(x) < V_catch``, and a prediction of the whole
scenario with the control law of ``library/TriplePendCtrl.jl`` (written here, with all its tables).

    uv run examples/pendulum-triple-fixed/design/design.py
    uv run examples/pendulum-triple-fixed/design/design.py --compare run.npz    # free swing vs a bond-graph run
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / "pendulum-double-fixed" / "design"))  # shared design code

import params as prm  # noqa: E402
from pendulum_flow import run  # noqa: E402

if __name__ == "__main__":
    run(prm)
