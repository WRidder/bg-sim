# Open loop: the aerodynamics and the modes

The turbine at 8 m/s with a fixed pitch ([PitchFixed](block:PitchFixed), 0°) and a fixed generator torque ([TorqueCmd](block:TorqueCmd)), with no controller. It starts in the region-2 steady state of `design/design.py`. See [the turbine](project:turbine).

![Ring-downs and the torque step|900](assets/0083dcaf5fae.png)

## What you see

- **Tower.** The tower is released undeflected. It rings about its static deflection under the thrust (0.213 m) at 0.322 Hz. The damping ratio is 4.8 %: 1 % structural, the rest the rotor's aerodynamic damping through [Aero/v_rel](signal:Aero/v_rel).
- **Drivetrain.** At 120 s the generator torque steps up by 5 %. The shaft twist ([ShaftC/q](signal:ShaftC/q)) rings at 2.22 Hz with 5 % damping.
- **Rotor.** The rotor then slows to a new equilibrium, 8.70 rpm at a tip-speed ratio of 7.17, where the aerodynamic torque matches the new generator torque.

The checks compare each of these with the linearised plant and the steady states of `design/design.py`.

## What to try

- Set `dtq` to −0.1: the rotor speeds up to a higher tip-speed ratio.
- Raise `v_ol`: the tower's aerodynamic damping grows with the wind.
