# F-16 open loop

The nonlinear F-16 of Stevens & Lewis (*Aircraft Control and Simulation*, Section 3.6), on the low-speed wind-tunnel data of NASA TP-1538. Three aircraft are trimmed at the book's point, 502 ft/s (153 m/s) at sea level, with the centre of gravity at 0.30, 0.35 and 0.38 of the mean chord, and each is released on its own mode. The further aft the CG, the less the airframe weathercocks into the wind: at 0.38 it is statically unstable.

![The model canvas|900](assets/3667084db799.png)

| block | role |
| --- | --- |
| [A30](block:A30), [A35](block:A35), [A38](block:A38) | one airframe each, an instance of the library subsystem `F16Airframe` that sets its CG and start state: rigid body, air data, NASA tables, force build-up, engine |
| [ElA30](block:ElA30), [ThrA30](block:ThrA30) | the book's trim elevator and throttle (and likewise for A35, A38) |
| [GrowA38](block:GrowA38) | $\lambda = q/(\theta - \theta_0)$: on an unstable real mode this is the eigenvalue |
| [EnergyA30](block:EnergyA30), [WorkA30](block:WorkA30) | A30's energy ledger on the airframe's audit outputs: kinetic + potential energy, and the work of the wrench |

## What to try

1. Press **Run**. A30 rings down (short period $-1.204 \pm 1.492j$), A38 pitches up with $e^{0.657 t}$ and stalls.
2. Plot [GrowA38/lambda](signal:GrowA38/lambda): it reads +0.657 1/s while the deviation is small.
3. Move the CG of A38 forward with the dashboard slider: below about 0.35 the divergence disappears.

## 3D view

The view keeps A30 (grey) framed and moves the world around it; A35 (sand) and A38 (blue) fly 30 m to the sides. The floor is a reference plane 150 m below the start altitude: it follows climbs and descents of up to 100 m (beyond that it stays in view as an attitude reference) and its stripes scroll with the ground track; the dots behind each aircraft are its path over the last second. Picture at 6 s:

![3D view at t = 6 s|600](assets/cef33e2e4975.png)

Continue with [the airframe](page:airframe) and [the results](page:results).
