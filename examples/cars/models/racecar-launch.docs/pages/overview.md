# Race car: launch

Full accelerator from rest for 12 s. The rear motor ([MotorR](block:MotorR), [MachineR](block:MachineR)) gives its 300 N m torque limit up to the base speed $P_{max}/T_{max} = 867$ rad/s (8280 rpm, 38 m/s, reached after about 5 s), then its 260 kW power limit. The traction control trims the torque in the first 0.1 s while the slicks take up the load. The battery current rises to 740 A and the state of charge falls by 2 % in 12 s.

![The model canvas|900](assets/6b264e099bff.png)

## What to try

- Move the torque and power limits on the dashboard (globals `T_max` and `P_max_kw`).
- Plot [MotorR/tc](signal:MotorR/tc), the traction-control factor, with `RL/Tyre/kappa`.

![3D view at t = 4 s|600](assets/e615ad10f91d.png)

Continue with [the electric drive](page:drive) and [the results](page:results).
