# Results

![Left leg goals and encoders, motor and battery currents|900](assets/3d08845e2e5e.png)

## The quasi-static reference

With the trunk held, each joint settles where the P law balances gravity: $K (q_\text{goal} - q) + \tau_g(q) = 0$, with $K$ = 0.5544 N·m/rad. `design/robot.py` (`hang_reference`) computes the gravity torques $\tau_g = -\partial U/\partial q$ from the MJCF bodies. A joint can also stop anywhere inside its friction budget at rest, which is a band of $\pm F/K$ (15 to 35 mrad here).

| joint | goal | reference | bg-sim at 1.2 s | band |
| --- | --- | --- | --- | --- |
| left hip pitch | -0.1510 | -0.1717 | -0.1914 | ±0.024 |
| left knee | 0.5811 | 0.5552 | 0.5377 | ±0.026 |
| left ankle | 0.7321 | 0.7353 | 0.7198 | ±0.018 |
| left hip roll | -0.0873 | -0.1400 | -0.1185 | ±0.035 |

Every leg joint stops 15 to 20 mrad short of the reference, on the side it came from, as a joint stopped by its friction does. `expected.json` checks nine joints before the step and at the end, each within its band plus 5 mrad. It also checks the time at which the knee goal crosses half-way through the delay line ($0.2 + 0.02 - 0.0025$ s) and the current bound.
