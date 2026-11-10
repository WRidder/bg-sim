# Maglev train

An **electromagnetic suspension (EMS)** train in the style of the Transrapid: magnets on the vehicle pull *up* towards a ferromagnetic rail on the underside of the guideway, and the gap between magnet and rail (about 10 mm) is kept by feedback, because the attraction grows when the gap shrinks: **a magnet alone is unstable**. A long stator (linear synchronous motor, LSM) in the guideway pushes the car forward.

| model | what it shows |
| --- | --- |
| [maglev-module](model:maglev-module) | One levitation module carrying a quarter of a car: lift-off from the skids, gap regulation at 10 mm, a guideway step and a payload step. The controller comes from an LQR design in `design/design.py`. |
| [maglev-module-open-loop](model:maglev-module-open-loop) | The same module without feedback, released 10 nm from its trim gap: the gap deviation grows with the unstable pole of the linearisation. |
| [maglev-vehicle](model:maglev-vehicle) | A 53 t car section on two such modules. The car body is a **3D rigid body** (floating base, spatial multibond) that heaves, pitches and travels; the LSM accelerates it to 430 km/h, it cruises and brakes on a guideway of sagging spans with one bump. |

Every plant is a **bond graph**. The coil and the magnet field are the stdlib `Electromagnet` (an energy-conserving IC-field with $L(h) = L_\infty + 2\alpha/h$ and $F = \alpha i^2/h^2$), the bogie, the secondary suspension and the skids are bond-graph elements, and the car body is the stdlib `RigidBody3D` on a `Free3D` joint. The scalar module graph is attached to the spatial body through the six drive ports of the joint: heave is `drive6`, pitch is `drive2` and the along-track motion is `drive4`.

## Where the numbers come from

See [parameters and sources](page:parameters). In short: the nominal gap (10 mm), the cruise speed (430 km/h), the acceleration (about 1 m/s²), the drag (Cd 0.26, 16 m²) and the car size and mass (27 m, 3.7 m, 53 t) are published Transrapid figures; the magnet constant, the coil, the chopper, the secondary suspension and the controller are **estimates** chosen here. The references of the checks are analytic (trim, weight balance, the open-loop pole) and independent nonlinear scipy simulations of the same equations (`design/design.py`). No published time series of a Transrapid levitation loop could be found, so there is no comparison with measured data.
