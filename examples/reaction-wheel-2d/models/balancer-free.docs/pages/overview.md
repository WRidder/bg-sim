# Balancer with gravity off: conservation of angular momentum

The same balancer as the `balancer` model, with `g0` = 0 in both bodies and in the controller ([Ctrl](block:Ctrl)). The wheel starts at **30 rad/s** (`inertia/P` = (0.06, 0, 0) of [Wheel](block:Wheel)) and the body at $\theta_0 = 0$. The total angular momentum about the pivot

$$H = 0.257\,\dot\theta + 0.002\,\dot q_w$$

must then stay constant at 0.06 kg·m²/s: the motor only exchanges momentum between body and wheel. See the `balancer` model for the physics, the controller (without the gravity term) and the parameters.

![The model canvas|900](assets/434b4a799915.png)

## Results

![Body angle, wheel speed and motor torque without gravity|900](assets/ea8a2370ada2.png)

The same 0.012 rad pulse leans the body; the wheel **spins down to 25.99 rad/s** as the body leans and **back up to 32.70 rad/s** as it returns, ending at 30.0007 rad/s. $H$ stays at 0.06 kg·m²/s: $\max\lvert H - H_0\rvert = 5.27\cdot10^{-9}$, that is $8.78\cdot10^{-8}$ of $H$ (tolerance 1e-6, the `invariant` check on `Pivot/qdout` with coefficient 0.257 and `WheelJ/qdout` with 0.002). $\lvert\theta\rvert$ stays below 0.011967 rad (band 0.02).

Checks: $\theta_0 = 0$, wheel 30 rad/s; the wheel dips to 25.99 and rises to 32.70 rad/s; torque bound; the invariant; no W201, E101, E102, E103, E106, W206.

## What to try

Plot [WheelJ/qdout](signal:WheelJ/qdout) next to [Pivot/qdout](signal:Pivot/qdout): the wheel rate moves exactly opposite to the body rate times 128 ($J_A/J_w = 0.257/0.002$) whenever the pulse moves the body; their weighted sum is the constant $H$.
