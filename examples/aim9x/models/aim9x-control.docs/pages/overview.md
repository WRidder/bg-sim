# Rate-command autopilot and TVC

The same airframe under the skid-to-turn autopilot. The guidance command is a specific force; the autopilot turns it into a body-rate command `a/V` and a fast rate loop moves the canards. The gain is scheduled on the square root of dynamic pressure, so the loop stays roughly constant over the boost. A two-axis thrust-vector augmentation takes a small share of the acceleration error while the motor burns.

![The model canvas|900](assets/0b78990f318d.png)

| block | role |
| --- | --- |
| [AP](block:AP) | roll-angle loop, pitch/yaw rate loop, gain schedule, TVC allocation |
| [AzCmd](block:AzCmd), [AyCmd](block:AyCmd) | a 40 m/s^2 pitch step at 0.5 s and a 20 m/s^2 yaw step at 3 s |
| [Mixer](block:Mixer) | virtual commands to the four canards |
| [Fin1](block:Fin1) .. [Fin4](block:Fin4) | the servos |

## What to try

1. Press **Run**: the pitch step builds about 2.9 g and the yaw step about 0.6 g; the roll loop holds wings level to 0.01 deg.
2. Set `tvc_on` to 0: the boost still flies on the canards alone; the `AP/tvc_p` trace goes to zero.
3. Lower `K_q` in [AP](block:AP): the rate loop slows and the acceleration response lags.

![acceleration, commands, canards and TVC|900](assets/d449f4fc3da4.png)

The `expected.json` checks the command and deflection limits, the roll hold, the fin stops and the TVC gimbal stop.
