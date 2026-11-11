# A109 open loop

The Agusta A109 of Heffley and Mnich's *Minimum-Complexity Helicopter Simulation Math Model* (NASA CR-177476, 1988, Appendix D). It is built as a bond graph:

* a multibond rigid body;
* one modulated wrench source per component (main rotor, fuselage, tail rotor, tailplane, fin);
* a rotational bond graph for the drivetrain.

Four helicopters are released from trim at sea level:

* **Hover**: the trim, released.
* **Coll**: a +0.5 deg collective step in hover.
* **Lon**: a 0.5 deg forward cyclic pulse in hover.
* **Fwd**: a 1 deg pedal pulse at 100 kt.

![The model canvas|900](assets/ae25ada341d2.png)

| block | role |
| --- | --- |
| [Hover](block:Hover), [Coll](block:Coll), [Lon](block:Lon), [Fwd](block:Fwd) | one airframe each (a subsystem): rigid body, air data, the five components, drivetrain and governor |
| [Hoverth0](block:Hoverth0), [CollB1](block:CollB1) and the like | the trim blade angles (deg) and the steps and pulses |
| [HoverView](block:HoverView) and the like | `HeliView`: keeps Hover framed; rotor disc and tail rotor poses |

## What to try

1. Press **Run**. Coll climbs and its nose yaws right. The main-rotor torque grows with the collective, and its reaction turns the fuselage: the collective→yaw coupling comes out of the drivetrain bond graph.
2. Watch Lon. The cyclic pulse starts the hover phugoid, an oscillation of about 10 s period that grows ($+0.21 \pm 0.60j$ 1/s).
3. Switch the dashboard's rotor speed to the report's constant 385 rpm and run again. The trims stay the same, but Coll yaws further, because the rotor no longer droops.

## 3D view

Hover (red) is framed. Coll (white) flies 16 m to its right, Lon (blue) to its left and Fwd (yellow) behind; Fwd is shown relative to its 100 kt trimmed path. The rotor discs tilt with the flapping. The blades spin at a tenth of their real speed.

![3D view at t = 6 s|600](assets/5517873ebee0.png)

Continue with [the structure](page:structure) and [the results](page:results).
