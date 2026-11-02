# The plant for the FMU (RL environment)

**What it is.** The bond graph of the rig without firmware, clock or push pulse: the model that
`rl/export_plant.jl --rig=lab` exports as the FMU the RL environment steps
([learned controllers](project:learned)). Run alone it starts hanging at rest with 0 V for 5 s, so nothing
moves until you set an input.

| interface | blocks |
| --- | --- |
| inputs (`ExportInput`) | [V](block:V): motor voltage (V); [F_push](block:F_push): horizontal tip force on link 2 (N) |
| encoder outputs (`ExportOutput`) | [x](block:x): cart position (m); [q1](block:q1): link 1 from the rail's x axis (rad); [q2](block:q2): link 2 relative to link 1 (rad) |
| critic outputs | [v](block:v), [w1](block:w1), [w2](block:w2): the rates; [i_m](block:i_m): the motor current |

**Globals.** Every `realism.json` parameter is a global under its own name. The 27 that enter the bond graph and
have a range (link parts, cable, cart mass, viscous frictions, motor R, L, $k_t$, $J_m$, pulley radius, belt)
and the 8 of the realism forces are exposed in the FMU with their ranges (`design/rl_ranges.json`), so the
environment can draw a parameter set per episode. The lumped link masses, centres of mass and inertias
(`m1`, `c1`, `J1`, ...) are driven globals, recomputed at the FMU's initialisation.
[Realism](block:Realism) (`library/LabRealism.jl`) adds the forces outside the bond-graph elements: Coulomb
friction of the joints, the carriage and the motor, the cable springs, commutation ripple and cogging. Sensor
quantisation, noise and the loop delay stay in the environment.

![The plant: the bond graph, the export inputs and outputs, the realism forces|900](assets/7fb96e577903.png)

**Dashboard.** The FMU's view: cart position and velocity, the joint encoder angles $q_1$, $q_2$ (rad),
voltage and current; plots of the encoders, the cart, voltage and current, and the realism forces. No monitor
block is added here, so the FMU stays the plant alone. The sliders set a constant test voltage, a constant tip
force and the cart mass (`global:m_cart`). With 2 V the cart runs at about 0.27 m/s against the back-EMF and
the carriage friction (the cogging makes the realism force ripple) and reaches the end stop at 1.0 m after
3.7 s, where the current rises to the stall value of 2 V:

![A run with V = 2 V: cart, joints, current and the realism forces|900](assets/37fd12126e4b.png)
