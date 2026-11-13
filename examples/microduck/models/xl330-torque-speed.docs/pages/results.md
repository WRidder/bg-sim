# Results

![Speed, torques, current and duty during the ramp|900](assets/0c59be3c610d.png)

`design/torque_speed.py` computes the curve on paper. The duty is $\min(1, (k_t\omega + R\, i_\text{limit})/V)$, and the horn torque is $k_t i$ minus the M6 friction, with the external torque solved by fixed-point iteration, minus the armature torque of the ramp:

| horn speed | analytic | bg-sim |
| --- | --- | --- |
| -6 rad/s | 0.8411 N·m | 0.8410 N·m |
| 1 rad/s | 0.4134 N·m | 0.4137 N·m |
| 5 rad/s | 0.4308 N·m | 0.4309 N·m |
| 10 rad/s | 0.2914 N·m | 0.2916 N·m |
| 18 rad/s | -0.0310 N·m | -0.0308 N·m |

`expected.json` checks eleven speeds within 0.5 mN·m. The differences come from the smoothed kinks of the friction law. It also checks that the current is 1.75 A on the flat part and never above it.

Against the direction of rotation (negative speeds), the friction and the motor torque add up at the horn: the servo brakes with more than its stall torque.
