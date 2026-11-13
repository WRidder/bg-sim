# Constrained MPC on the same cart-pole

[MPC1](block:MPC1) (`library/MPC.jl`) replaces the LQR with a 20 ms model-predictive
controller. The plant, the scene and the 0.1 rad start are the same as
[the original model](model:inverted-pendulum-cart); the step is now 0.3 m, which the
unconstrained LQR would ask for with 26.8 N. The MPC respects the real ±20 N actuator and
a 200 N/s slew limit.

## The QP

The prediction is the discrete linearisation at upright, condensed over $N=20$ samples.
With $U = u_{prev}\mathbf 1 + L\Delta U$, the cost is

$$J = \tfrac12 \Delta U^T H_d \Delta U + f_d^T \Delta U + \text{const},$$

$$H_d = L^T(\Gamma^T\bar Q\Gamma+\bar R)L,\qquad f_d = L^T\left(\Gamma^T\bar Q\Phi e_0 + \Gamma^T\bar Q\Gamma\mathbf 1\,u_{prev}\right),$$

and the only constraint is the box $\lvert\Delta u_k\rvert\le0.2$ N. [MPC1](block:MPC1)
solves it by 20 ADMM iterations per 1 ms tick,

$$U_c = (H_d+\rho I)^{-1}(\rho(z-y)-f_d),\qquad z = \operatorname{clamp}(U_c+y,\pm0.2),\qquad y\leftarrow y+U_c-z,$$

warm-started from the previous tick, and applies
$u=\operatorname{clamp}(u_{prev}+z_1,\pm20)$. The QP matrices are parameters of the block;
`design/mpc.py` writes them and `design/build_mpc.py` regenerates the block and the model.

![MPC run|900](assets/5e186a1fbb75.png)

## Results

The MPC reaches 0.3 m and settles; the angle peaks at **12.9°** and the force at
**18.58 N**, inside both limits. The rate-limited LQR on [the next page](model:inverted-pendulum-cart-rate)
peaks at 15.5° and 20.00 N. The MPC starts braking earlier because it plans the force
increment over 20 ms. The run takes about 28 s in the check environment, against 16 s for
the rate-limited LQR.

## What to try

- Set `MPC1.du_max` to 0.1 N (100 N/s): the MPC becomes slower and the angle peak grows.
- Set it to 1 N: the MPC plans a more aggressive force and the peak angle falls, until the
  20 N limit binds.
- Open the block source and set `iterations` to 5: the ADMM solution is not converged and
  the force chatters. Twenty iterations are the design point.
