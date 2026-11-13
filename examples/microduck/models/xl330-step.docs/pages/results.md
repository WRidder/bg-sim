# Results

![Goal and encoder, winding current, torques|900](assets/defaaadc3a2f.png)

During the swing up the current peaks at 1.46 A, just under the 1.75 A limit: at kp 200 an error of 1 rad asks for 58 % PWM. Near the goal, the P law and gravity balance: the encoder holds 0.910 rad, short of 1 rad, with a holding torque of 0.050 N·m.

## Checks against the BAM simulator

`design/xl330.py` ports BAM's `simulate.py` (the M6 friction with its stopping logic, a rigid gear, the same latency, a time step of 10 µs). On this bench:

| quantity | BAM simulator | bg-sim |
| --- | --- | --- |
| angle at 0.3 s | 0.7691 rad | 0.7750 rad |
| angle held at the goal (0.5 s) | 0.9084 rad | 0.9102 rad |
| holding torque at 0.5 s | 0.0508 N·m | 0.0499 N·m |
| angle at 1.0 s (falling back) | 0.5913 rad | 0.5755 rad |
| rest angle after the return | -0.01736 rad | -0.0172 rad |

The largest difference is 16 mrad, during the fast swings. The delay line samples every 5 ms and ramps a goal step over one tick, half a tick early. The rest angles agree to 0.2 mrad, which is a test of the friction budget. `expected.json` checks nine encoder angles within 0.02 rad, the rest angle within 2 mrad and the holding torque within 5 mN·m.
