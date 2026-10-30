# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `pendulum-double-cart` example (X5.12): swing-up trajectory, TVLQR and LQR.

A cart on a rail (travel +-0.40 m) carries a double pendulum. A DC motor drives the cart through a
3:1 gearbox and a 16 mm pulley with a belt; the pendulum joints are passive. The scenario is

    0 .. 1 s        hanging down at rest, motor voltage 0
    1 s             swing-up: feed-forward from an offline direct-collocation optimisation
                    (Hermite-Simpson, IPOPT, |x| <= 0.30 m, |V| <= 16 V) tracked by a time-varying
                    LQR, T_s = 2.4 s
    3.4 s           catch: switch to the 1 kHz infinite-horizon (discrete) LQR balance controller
    7.0 s           a 40 ms force pulse on the tip link (3.5 s of balance before it)
    ..              recovery; the run ends 12 s

``cartpend.py`` holds the shared mathematics (Lagrangian dynamics, collocation, TVLQR, LQR, table
writer), ``cartmodel.py`` the bond-graph model generator. Run

    uv run examples/pendulum-double-cart/design/design.py [--write] [--compare-free <run dir>]

It prints the numbers quoted in the README and `expected.json` (the closed loop of the design model
under the 1 kHz firmware). With ``--write`` it writes the tables and gains into `library/DoubleCartTraj.jl`
and `library/DoubleCartCtrl.jl` and generates `models/*.bgmodel.json`; with ``--compare-free`` it compares
a bond-graph run of `pendulum-double-cart-free` (its run folder) with the design ODE.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cartpend as cp  # noqa: E402

ROOT = HERE.parent

# ----------------------------------------------------------------------------- parameters
# Assumed, there is no published data for a belt-driven double pendulum rig of this size:
#   cart carriage 0.8 kg on a +-0.40 m rail; two aluminium-rod links of 0.25 m (0.10 and 0.08 kg, COM at
#   the middle, J = m L^2 / 12); viscous joint friction 2e-4 N m s/rad.
#   24 V brushed servo motor of the 90 W class (R 1.5 ohm incl. leads, L 0.5 mH, k_t = k_e 0.0302 N m/A,
#   rotor 1.4e-5 kg m^2, 2e-6 N m s/rad bearing loss), 3:1 gearbox, 16 mm pulley radius, toothed belt of
#   4e5 N/m. Stall force 24 V * 3.77 N/V = 90 N; the reflected rotor inertia (0.49 kg) is larger than the
#   links together.
L_LINK = [0.25, 0.25]
M_LINK = [0.10, 0.08]
PLANT = cp.Plant(
    name="PendulumDoubleCart",
    L=L_LINK, m=M_LINK, c=[l / 2 for l in L_LINK], J=[m * l * l / 12 for m, l in zip(M_LINK, L_LINK)],
    b=[2e-4, 2e-4],
    m_cart=0.8, J_cart=1.5e-3,
    R_m=1.5, L_m=5e-4, k_t=0.0302, J_m=1.4e-5, b_m=2e-6, N=3.0, r=0.016,
    u_max=24.0, x_rail=0.40,
)

DOC = """
Firmware of the cart pendulum, 1 kHz. Three phases, latched in `mode`:
  0  hold: the motor voltage is 0 until t_on (the pendulum hangs at rest).
  1  swing-up from t_on: u = u_ff(tau) - K(tau) (z - z*(tau)), tau = t - t_on. The feed-forward voltage u_ff,
     the nominal state z* and the time-varying LQR gain K come from the offline trajectory optimisation;
     the block `DoubleCartTraj` looks them up in 10 ms tables and this block samples them at every tick.
  2  balance from tau >= T_s (the nominal ends upright, at rest): u = -K_lqr z, the discrete
     infinite-horizon LQR of the 1 ms sampled linearisation at the upright.
z = [x, th_1, th_2, v, w_1, w_2] with the absolute link angles th_i from the upward vertical and their
rates w_i (sums of the joint encoder angles and rates). The output is clamped to +-u_max.
design/design.py writes the gains: do not edit them by hand.
"""

DESCRIPTION = (
    "X5.12 acceptance. A cart on a +-0.40 m rail carries a double pendulum (planar multibond bond graph: Prismatic2D rail, "
    "two Revolute2DCompliant joints with 1e8 N/m pivots, two RigidBody2D rods of 0.25 m, 0.10/0.08 kg), driven by a 24 V DC motor "
    "through a 3:1 gearbox, a 16 mm pulley and an elastic belt; the pendulum joints are passive. The 1 kHz firmware "
    "(library/DoubleCartCtrl.jl with the tables of library/DoubleCartTraj.jl, both written by design/design.py) holds 0 V until "
    "1 s, then tracks a direct-collocation swing-up trajectory (T_s = 2.4 s, |x| <= 0.30 m, |V| <= 16 V) with a time-varying "
    "LQR, switches to the discrete LQR at 3.4 s and is hit by a 40 ms, 0.28 N force pulse on the tip link at 7 s. The reference "
    "numbers are design.py's closed loop of the Lagrangian design model under the same sampled firmware (RK4); the bond-graph "
    "run reproduces it to ~3e-3 rad during the transients. The -free model releases the plant from rest at a non-trivial pose with "
    "the motor shorted (V = 0) and is compared with the design ODE sample by sample."
)

SCENARIO = cp.Scenario(
    prefix="DoubleCart", model="pendulum-double-cart", root=ROOT, plant=PLANT,
    t_on=1.0, t_s=2.4, k_int=60, u_lim=16.0, x_lim=0.30, dt_tab=0.01,
    t_dist=7.0, dist_dur=0.04, dist_amp=0.28, t_end=12.0,
    Q=np.diag([300.0, 400.0, 400.0, 10.0, 8.0, 8.0]), R=0.3,      # [x, th1, th2, v, w1, w2], 1/V^2
    free_th0=[-2.2, -1.2], free_x0=0.05, free_t=2.0,
    doc=DOC, scene="scenes/pendulum-double-cart.sdf",
)

if __name__ == "__main__":
    cp.main(SCENARIO)
