# Intercept

The full weapon: the airframe and autopilot of the other models, an imaging infrared seeker, proportional navigation and a proximity fuze, against a target aircraft 2 km ahead at 150 m/s. The missile is launched at 400 m/s, 40 m above the target; the motor boosts it to about 970 m/s and the seeker guides it to a proximity kill in 3.3 s.

![The model canvas|900](assets/cd6487b31e88.png)

| block | role |
| --- | --- |
| [Target](block:Target) | the target aircraft, its heading and its rear-aspect infrared intensity |
| [Seeker](block:Seeker) | gimbal, field of view, inertial LOS rates, range and closing speed |
| [Guide](block:Guide) | proportional navigation `a = N V_c (omega x u)` with a 15 m/s^2 aerodynamic limit |
| [AP](block:AP) | the rate-command autopilot of the control model |
| [Status](block:Status) | closest approach, proximity fuze and warhead |

## What to try

1. Press **Run**: the range falls from 2 km to the 15 m fuze in 3.3 s; `Status/hit` goes to 1.
2. Set `nav_N` to 2 or 6: the command and the miss distance change; the seeker field of view and the acceleration limit are what finally bound the miss.
3. Move the target with `tgt_x`, `tgt_y`, `tgt_z` or give it a turn with `turn_rate`: the seeker gimbal and the LOS rates move and the fuze time changes.

The 3D view of the airframe and control models shows the missile itself: the canards move with their servos and the plume follows the motor. The target is tracked in the range and seeker plots above.

![range, acceleration, speed and seeker lock|900](assets/7a3636fa2556.png)

The miss is a **proximity** miss: the fuze fires at 15 m (the continuous-rod warhead's envelope), and the unfuzed trajectory passes inside 13 m of the target.
