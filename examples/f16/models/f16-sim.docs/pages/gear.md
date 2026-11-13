# Landing gear

A tricycle gear with the structure of the Cessna's: on each leg a mount, the Cessna's `GearContact` (a modulated transformer) and 1-junctions with a spring, a damper, rolling and brake friction, and a side force. The data are from JSBSim's `f16.xml`, with the damping halved. `examples/f16/README.md`, section "Landing gear", lists every source and what is assumed.

Added to the Cessna's structure:

- **Retraction**: an `MSf` in series with each strut, through a 0-junction. Its flow is the rate at which `GearActuator` lifts the contact point, 5 s for the whole travel. The gear's drag is `GearDrag`.
- **Steering**: `GearLogic` turns the pedals into the nose-wheel angle, with a `Lookup1D` limit over the ground speed that keeps full pedal near 0.35 g. The aircraft would tip over at about 0.75 g.
- **Weight on wheels**: `w` runs from 0 to 1 with the force in the main struts' springs, and is exactly 0 in the air. It fades the three laws to direct commands, and with weight on the wheels it holds the gear down.

The globals `gear0` and `gear_set` default to 0, gear up: then the ground is a crash as before, and flight is unchanged.

## Checks

`design/gear.py` is an independent reference: a rigid aircraft in the vertical plane with the same coefficients, engine and pitch law, and the strut and tyre laws written from geometry.

| run | quantity | reference | bg-sim |
| --- | --- | --- | --- |
| at rest, idle, brakes set | CG height | 1.6228 m | 1.6228 m |
| | nose / main wheel load | 22.38 / 34.39 kN | 22.38 / 34.39 kN |
| taxi, then brakes | where it stops | 324.7 m | 324.7 m |
| take-off, full afterburner | height at 20 s | 220.8 m | 220.8 m |
| landing, 2.13 m/s of sink, no flare | peak main wheel | 113.9 kN | 115.3 kN |
| | peak nose wheel | 57.4 kN | 57.4 kN |
| | where it stops | 2205.5 m | 2205.5 m |
| half pedal at 6.6 m/s | yaw rate | 13.47 deg/s | 13.61 deg/s |
