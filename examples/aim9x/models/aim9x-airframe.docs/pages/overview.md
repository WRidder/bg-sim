# AIM-9X airframe

The open-loop plant of the AIM-9X: a six-degree-of-freedom rigid body on a multibond bond graph, with a burning solid rocket motor, the four cruciform canards and the standard atmosphere. A short pitch doublet at 0.53 s and a yaw doublet at 4 s excite the airframe; there is no autopilot in this model.

![The model canvas|900](assets/63b842de3288.png)

| block | role |
| --- | --- |
| [Free](block:Free), [Inertia](block:Inertia), [Motor](block:Motor) | the 6-DOF body, its modulated inertia and the Mk. 36 motor with the propellant outflow `MR`s |
| [Aero](block:Aero) | lift, drag, the canard force and moment, the pitch/yaw/roll damping |
| [CNa](block:CNa), [CD0](block:CD0) | the Mach tables of the normal-force slope and the zero-lift drag |
| [Fin1](block:Fin1) .. [Fin4](block:Fin4) | the four canard servos (position limit before the lag, 200 deg/s rate limit) |
| [Mixer](block:Mixer) | virtual pitch/yaw/roll to the four canards |

The plant is the same in the [autopilot model](model:aim9x-control/overview) and in the [intercept](model:aim9x-intercept/overview).

## What to try

1. Press **Run**: the pitch doublet starts a short-period ring at about 1 Hz, which dies out as the motor burns; the yaw doublet shows the weathercock stability.
2. Raise `dp_amp` on the dashboard: the ring is linear for a few tenths of a degree, then the cubic lift terms show.
3. Set `tvc_on` to 0 or 1: the open-loop model has no TVC command, so this only matters in the closed-loop models.

![alpha, q, speed and the canards|900](assets/ae325f6c31af.png)

## 3D view

The scene shows the missile at the origin, 3.02 m long, with the seeker window, the fixed tail fins and the olive band in one lofted mesh; the four canards are separate meshes on their hinge axes, so they turn with the servo signals. The nozzle plume scales with the motor thrust and a warm glow sits at the exit. The viewer's reference grid gives the scale.

![The missile at t = 1 s|600](assets/b87d73d11d6f.png)
