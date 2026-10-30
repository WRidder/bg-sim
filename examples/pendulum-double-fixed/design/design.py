# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Controller design for pendulum-double-fixed (X5.11): swing-up, catch, balance.

The plant is the planar double pendulum of ``params.py`` (two rods with distributed mass, viscous joint
friction, gravity), driven at the first joint by a DC gearmotor (voltage ``u``, ``R_w``, ``L_w``,
``k_t``, ratio ``N``, reflected rotor inertia ``N^2 J_m``). Lagrangian mechanics with CasADi gives
``M(q) qdd + c(q, qd) + g(q) = tau`` (see ``pendulum_common.Dynamics``); this is exactly the plant of the
bond graph, which the free-swing check proves.

1. **Swing-up trajectory** (direct collocation, Hermite-Simpson, IPOPT): from both links hanging at rest
   to both links upright at rest in ``T_s`` seconds, minimising the integral of ``(u / u_limit)^2`` with
   ``|u| <= 11 V`` (the rest of the 12 V supply is feedback margin).
2. **TVLQR** along that trajectory: a discrete time-varying Riccati recursion at the 1 kHz controller rate
   from the linearisation (exact ZOH) at every sample, terminated by the balance LQR's Riccati matrix.
3. **Balance LQR** at upright (exact ZOH, 1 kHz), the same weights.
4. **Switching rule**: the LQR takes over, latched, the first tick with ``V(x) = (x - x_up)' P (x - x_up)``
   below ``V_catch`` (P is the LQR Riccati matrix); ``V_catch`` is ``V`` of the nominal trajectory 0.2 s before
   its end, so the catch happens inside the region where the LQR is verified to hold the pendulum.
5. The whole scenario is simulated with the **same control law** (tables rounded as written) on the full
   non-linear model with the winding current, with the disturbance, to predict what the bond-graph run does.

The script writes ``library/DoublePendCtrl.jl`` (all tables are constants of that block) and
``design/results.json`` (numbers for the README, the docs and expected.json).

    uv run examples/pendulum-double-fixed/design/design.py
    uv run examples/pendulum-double-fixed/design/design.py --compare run.npz    # free swing vs a bond-graph run
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import params as prm  # noqa: E402
from pendulum_flow import run  # noqa: E402

if __name__ == "__main__":
    run(prm)
