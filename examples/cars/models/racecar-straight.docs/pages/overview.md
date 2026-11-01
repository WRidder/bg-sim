# Race car: top speed and regenerative braking

The race car starts at the top speed of the reference: 260 kW against the drag, the rolling resistance and the tyre slip. At 10 s the accelerator comes off and the brake pedal goes to 50 % (a 55 ms ramp). The rear motor takes what it can of the rear brake demand. Above about 50 m/s its 200 kW regen power limit caps it, and the rear friction brakes take the rest ([Brakes](block:Brakes)). Below that speed the motor covers the whole rear demand (185.7 N m at the rotor) and the rear friction brakes are idle. The front axle has no motor, so its friction brakes take their full share. The battery current reverses and the state of charge rises.

![The model canvas|900](assets/7e3555ea9eaa.png)

## What to try

- Move the brake pedal and the regen power limit on the dashboard (globals `brake_set` and `P_regen_kw`). With the regen limit at 0 the friction brakes do all the work and the charge does not rise.
- Plot [Brakes/rl](signal:Brakes/rl) (the rear friction torque) against [MotorR/regen](signal:MotorR/regen).

![3D view at t = 11 s|600](assets/832d0c8cdc00.png)

Continue with [the results](page:results).
