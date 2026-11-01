# Pilot-induced oscillation

A category II PIO: an aggressive pilot captures a 7 deg pitch-attitude change at 500 ft/s, 15 000 ft. The pilot is a gain of 3 (deg/s of pitch-rate command per deg of attitude error) acting on what he saw 0.25 s ago. Small corrections stay linear and well damped. A large one drives the stabilator into its 60 deg/s rate limit, and the rate limit adds phase lag that the pilot loop cannot afford.

![The model canvas|900](assets/0b36b7d76639.png)

| block | role |
| --- | --- |
| [PlainPilot](block:PlainPilot) | `TransportDelay` (0.25 s), gain, stick limit ±1 (stdlib blocks) |
| [PlainCmd](block:PlainCmd) | `GCommand` in pitch-rate mode: 40 deg/s per unit stick, limiter on |
| [CompComp](block:CompComp) | the phase-compensated rate limiter (stdlib blocks) in front of the servo |

## What to try

1. Press **Run**: Plain oscillates with the stabilator rate pinned at ±60 deg/s; Comp settles in about three seconds.
2. Lower the pilot gain to 2: the plain loop no longer saturates and both cases settle.
3. Ask for 2 deg instead of 7: the same pilot stays linear and the PIO disappears.

![3D view at t = 3 s|600](assets/0bcbc37d7c44.png)

Continue with [the compensation](page:comp).
