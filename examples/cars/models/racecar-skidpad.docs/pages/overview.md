# Race car: skid pad

25 m/s with three left steering levels (0.04, 0.08 and 0.12 of full lock, held for 6 s each). A PI on the accelerator ([Throttle](block:Throttle)) holds the speed. The lateral acceleration reaches 0.85 g at the last level; the loads move to the right-hand tyres and the rear motor drives through the open differential with its viscous limited-slip coupling.

![The model canvas|900](assets/32bf15e5135d.png)

## What to try

- Plot [Telemetry/ay](signal:Telemetry/ay), [Telemetry/r](signal:Telemetry/r) and the slip angles `FL/Tyre/alpha` .. `RR/Tyre/alpha`.
- Change `values` of [Steer](block:Steer) for more lock: near 0.16 the rear tyres saturate first and the car spins.

![3D view at t = 18 s|600](assets/53650385d249.png)

Continue with [the results](page:results).
