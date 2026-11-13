# Rate-limited LQR: the fair comparison

[RateLimitedLQR1](block:RateLimitedLQR1) (`library/RateLimitedLQR.jl`) is the same LQR
state feedback as [the original model](model:inverted-pendulum-cart), sampled at 1 ms,
with the actuator's slew limit in the firmware:

$$u_{cmd} = \operatorname{clamp}(-K[x-x_{ref},v,\theta,\omega],\pm20),$$

$$u = \operatorname{clamp}\!\left(u_{prev}+\operatorname{clamp}(u_{cmd}-u_{prev},\pm0.2),\pm20\right).$$

It is the fair comparison for the MPC: the same plant, the same 0.3 m step and the same
20 N / 200 N/s actuator, but no plan beyond the current error.

![Rate-limited LQR run|900](assets/3ed055a087dc.png)

The applied force is the block's output: the limiter turns the LQR's instantaneous demand
into a 200 N/s ramp, and the run peaks at exactly 20.00 N. The angle peaks at
**15.5°**, 2.6° above the MPC's 12.9°. Both settle at 0.3 m; the rate limit costs a little
settling (0.64° around t = 3 s against the MPC's 0.52°).

The same block is the comparison used in [the MPC page](model:inverted-pendulum-cart-mpc);
the two models share the plant, the scene and the step.
