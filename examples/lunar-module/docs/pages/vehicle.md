# The Apollo 11 lunar module

Three models of Eagle, the lunar module of Apollo 11, on one 3D (multibond) bond graph of a rigid body that loses mass:

| model | flight |
| --- | --- |
| [Powered descent](model:lm-descent) | descent-engine ignition (PDI) 15 km up at 1,695 m/s, to touchdown on four footpads 12.6 min later |
| [Landing by hand](model:lm-hover) | the landing phase (P66) flown from the dashboard, with Armstrong's propellant |
| [Ascent](model:lm-ascent) | lift-off from the descent stage to orbit insertion, 7 min 17 s |

![The descent model: the variable-mass body on top, propulsion, guidance and attitude in the middle, the landing gear below|900](assets/066f29d663cb.png)

## The bond graph

- A `Free3D` joint ties the vehicle's 1-junction `Body` to the ground (`World`).
- `Inertia` (`VariableInertia3D`, a project block) is a **modulated spatial inertia**: its state is the body-frame momentum $P = [h; p]$, and the mass $m(t)$ and principal moments $J(t)$ are input signals from the propellant tank.
- `Coriolis` adds the gyroscopic terms, `Twist` taps the body twist.
- Three `ExternalWrenchSpatial` sources carry the engine thrust, the RCS torques and inverse-square lunar gravity.
- Six `MR` elements `Out1..Out6` on the joint's drive ports have the resistance $r = -\dot m$ (linear) and $r = -\dot J_k$ (angular): the propellant that leaves takes its momentum with it, so $m\,\dot v = F$.
- The descent and hover models add the **landing gear**: four `ContactPoint`s, one per footpad, mounted on `Body` through `FixedTransform3DNeutral`s. Each pad meets the tangent plane of the lunar sphere straight below it (`LunarSurface3D`).

The flight runs in the landing-site frame: x downrange, z up, the Moon's centre at $(0, 0, -R)$. The body axes are the LM's own: X up the thrust axis, Z forward through the hatch.

Continue with [parameters and sources](page:parameters) and [validation](page:validation).
