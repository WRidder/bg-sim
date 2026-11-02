# Beaver control steps

Six Beavers start at the FDC trim (45 m/s, 6000 ft), and each gets one of the inputs of the thesis' figures 5-2 to 5-7:

| aircraft | input |
| --- | --- |
| [Elevator](block:Elevator), [Aileron](block:Aileron), [Rudder](block:Rudder) | a 3° block for 2 s, from 1 s |
| [Flap](block:Flap) | 3° of flap in 3 s |
| [Rpm](block:Rpm) | +200 rpm in 4 s |
| [Manifold](block:Manifold) | +2 inch Hg of manifold pressure in 2 s |

![The model canvas|900](assets/a47ce11c4530.png)

The responses show the cross-coupling the thesis points out: the elevator block also yaws and rolls the aircraft, the phugoid follows the aileron and rudder inputs, and flaps or power make the aircraft roll (the slipstream's rolling moment grows with $\alpha^2 \Delta p_t$).

![Responses|900](assets/73fcc7c95e9b.png)

## What to try

1. Change the sizes of the inputs with the sliders.
2. Switch the **drivetrain** on. The shaft of the Rpm aircraft now lags the rpm command, with the governor's 2 rad/s, ζ 0.7 loop, instead of following it exactly.

![3D view at t = 20 s|600](assets/7c62bbd09f23.png)
