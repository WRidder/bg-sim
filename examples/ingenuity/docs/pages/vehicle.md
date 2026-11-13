# Ingenuity Mars Helicopter

NASA/JPL's Ingenuity made the first powered, controlled flight on another planet on 19 April 2021. This example models it as a bond graph: a 3D multibond airframe on four landing-gear contacts, two counter-rotating rotors driven by motor bond graphs, blade-element/momentum rotor aerodynamics and the flight-control structure of the published guidance-and-control paper. Mars: $g$ = 3.71 m/s², CO2 at 0.012 to 0.02 kg/m³. Ingenuity flies at a fixed rotor speed and controls thrust with the blade pitch alone.

| model | what it shows |
| --- | --- |
| [ingenuity](model:ingenuity) | a demonstration flight: take off, 3 m hover, 5 m east, a 90 deg turn, landing; dashboard with density, rotor speed and wind |
| [ingenuity-flight-one](model:ingenuity-flight-one) | a replica of Flight One, checked against the published flight figures |
| [ingenuity-rotor-stand](model:ingenuity-rotor-stand) | the rotor on a stand in the JPL Space Simulator: thrust sweep and cyclic steps against the test data |

![The demonstration flight, 12 s in: flying east at 3 m|600](assets/72a69ced654f.png)

![The model canvas|900](assets/8c4443f19638.png)

## The bond graph

- **Airframe (3D multibond).** `GroundSpatial` -> `Free3D` -> `RigidBody3D` (1.8 kg, Mars gravity, apparent roll/pitch inertia). The rotors (`Rotor3D`), the hub wrenches and the drag wrench (`ExternalWrenchSpatial` through `FixedTransform3DNeutral` mounts) and four `ContactPoint` feet are all bonded to the body. The same model rests on the ground, takes off and lands.
- **Propulsion.** Per rotor an electrical 1-junction (`MSe` winding voltage, `R` losses, `Df` current, `GY` motor) and a shaft 1-junction (motor, the rotor's spin momentum in `Rotor3D`, the rotor aerodynamics `RotorBEMT` as a nonlinear R). The rotor's torque reaction and gyroscopic moment reach the airframe through `Rotor3D`.
- **Aerodynamics.** `RotorBEMT` balances blade-element lift and annulus momentum at 16 stations of the published blade (chord and twist, Koning et al. 2018), with the published lift slope, a 20 % induced-velocity correction and tip loss. The lower rotor sees the upper rotor's inflow. The hub moments are quasi-steady: cyclic, edgewise flow (Pitt-Peters times 2.5) and the identified rate moment (Grip et al. 2017).
- **Flight software.** `FlightPlan` (minimum-jerk moves, 1 m/s climb and descent) and `FlightControl` at 500 Hz: heave on the symmetric collective, yaw on the antisymmetric collective, roll and pitch on cyclic, horizontal position as an outer loop (the loop structure of Grip et al. 2018). Servos: 12 Hz, 85 % damping (published). Navigation is taken as perfect.

Continue with [the parameters](project:parameters) and [the validation](project:validation).
