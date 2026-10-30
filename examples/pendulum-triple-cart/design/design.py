# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `pendulum-triple-cart` example (X5.12): swing-up trajectory, TVLQR and LQR.

The `pendulum-double-cart` rig with a third link: the same cart, rail (+-0.40 m), motor, gearbox,
pulley and belt, and three passive 0.25 m links. The scenario is

    0 .. 1 s        hanging down at rest, motor voltage 0
    1 s             swing-up: direct-collocation trajectory (Hermite-Simpson, IPOPT, |x| <= 0.30 m,
                    |V| <= 16 V) tracked by a time-varying LQR, T_s = 3.5 s (350 collocation intervals)
    4.5 s           catch: switch to the 1 kHz infinite-horizon (discrete) LQR balance controller
    8.0 s           a 40 ms force pulse on the tip link (3.5 s of balance before it)
    ..              recovery; the run ends 14.5 s

The mathematics, the table writer and the model generator are shared with the double pendulum
(`examples/pendulum-double-cart/design/cartpend.py`, `cartmodel.py`). Run

    uv run examples/pendulum-triple-cart/design/design.py [--write] [--compare-free <run dir>]

With ``--write`` it writes `library/TripleCartTraj.jl`, `library/TripleCartCtrl.jl` and
`models/*.bgmodel.json`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT.parent / "pendulum-double-cart" / "design"))
import cartpend as cp  # noqa: E402

# ----------------------------------------------------------------------------- parameters
# The rig of the double pendulum (cart 0.8 kg on a +-0.40 m rail, 24 V / 90 W-class motor, 3:1 gearbox,
# 16 mm pulley, 4e5 N/m belt: see pendulum-double-cart/design/design.py) with three aluminium-rod links of
# 0.25 m (0.10, 0.08, 0.06 kg, COM at the middle, J = m L^2 / 12), viscous joint friction 2e-4 N m s/rad.
# The masses are assumed, like the rest of the rig.
L_LINK = [0.25, 0.25, 0.25]
M_LINK = [0.10, 0.08, 0.06]
PLANT = cp.Plant(
    name="PendulumTripleCart",
    L=L_LINK, m=M_LINK, c=[l / 2 for l in L_LINK], J=[m * l * l / 12 for m, l in zip(M_LINK, L_LINK)],
    b=[2e-4, 2e-4, 2e-4],
    m_cart=0.8, J_cart=1.5e-3,
    R_m=1.5, L_m=5e-4, k_t=0.0302, J_m=1.4e-5, b_m=2e-6, N=3.0, r=0.016,
    u_max=24.0, x_rail=0.40,
)

DOC = """
Firmware of the cart pendulum, 1 kHz. Three phases, latched in `mode`:
  0  hold: the motor voltage is 0 until t_on (the pendulum hangs at rest).
  1  swing-up from t_on: u = u_ff(tau) - K(tau) (z - z*(tau)), tau = t - t_on. The feed-forward voltage u_ff,
     the nominal state z* and the time-varying LQR gain K come from the offline trajectory optimisation;
     the block `TripleCartTraj` looks them up in 10 ms tables and this block samples them at every tick.
  2  balance from tau >= T_s (the nominal ends upright, at rest): u = -K_lqr z, the discrete
     infinite-horizon LQR of the 1 ms sampled linearisation at the upright.
z = [x, th_1, th_2, th_3, v, w_1, w_2, w_3] with the absolute link angles th_i from the upward vertical and
their rates w_i (sums of the joint encoder angles and rates). The output is clamped to +-u_max.
design/design.py writes the gains: do not edit them by hand.
"""

DESCRIPTION = (
    "X5.12 acceptance. The pendulum-double-cart rig with a third link: a cart on a +-0.40 m rail carries a triple pendulum "
    "(planar multibond bond graph: Prismatic2D rail, three Revolute2DCompliant joints with 1e8 N/m pivots, three RigidBody2D rods "
    "of 0.25 m, 0.10/0.08/0.06 kg), driven by a 24 V DC motor through a 3:1 gearbox, a 16 mm pulley and an elastic belt; the "
    "pendulum joints are passive. The 1 kHz firmware (library/TripleCartCtrl.jl with the tables of library/TripleCartTraj.jl, "
    "both written by design/design.py) holds 0 V until 1 s, then tracks a direct-collocation swing-up trajectory (T_s = 3.5 s, "
    "|x| <= 0.30 m, |V| <= 16 V) with a time-varying LQR, switches to the discrete LQR at 4.5 s and is hit by a 40 ms, 0.065 N "
    "force pulse on the tip link at 8 s. The reference numbers are design.py's closed loop of the Lagrangian design model under "
    "the same sampled firmware (RK4). The -free model releases the plant from rest at a non-trivial pose with the motor shorted "
    "(V = 0) and is compared with the design ODE sample by sample."
)

SCENARIO = cp.Scenario(
    prefix="TripleCart", model="pendulum-triple-cart", root=ROOT, plant=PLANT,
    t_on=1.0, t_s=3.5, k_int=350, u_lim=16.0, x_lim=0.30, dt_tab=0.01,
    t_dist=8.0, dist_dur=0.04, dist_amp=0.065, t_end=14.5,
    Q=np.diag([300.0, 400.0, 400.0, 400.0, 10.0, 8.0, 8.0, 8.0]), R=3.0,   # [x, th1..th3, v, w1..w3], 1/V^2
    free_th0=[-2.3, -1.4, -2.0], free_x0=0.05, free_t=1.5,
    doc=DOC, scene="scenes/pendulum-triple-cart.sdf",
)

if __name__ == "__main__":
    cp.main(SCENARIO)
