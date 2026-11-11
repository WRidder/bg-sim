# The NREL 5 MW reference turbine

This example models the NREL 5 MW reference wind turbine of Jonkman, Butterfield, Musial and Scott, *Definition of a 5-MW Reference Wind Turbine for Offshore System Development* (NREL/TP-500-38060, 2009). It covers the rotor's aerodynamics, the drivetrain, the tower's first fore-aft mode and the report's baseline controller.

| property | value | source |
| --- | --- | --- |
| rotor | 3 blades, 126 m diameter, hub at 90 m | Table 1-1 |
| operating range | cut-in 3 m/s, rated 11.4 m/s, cut-out 25 m/s; 6.9 to 12.1 rpm | Table 1-1 |
| rotor inertia | 38,759,228 kg m² | section 7.3 |
| generator inertia | 534.116 kg m² (high-speed shaft) | chapter 5 |
| gearbox | 97 : 1 | chapter 5 |
| shaft | 867,637,000 N m/rad, 6,215,000 N m s/rad (low-speed-shaft equivalents) | chapter 5 |
| generator | 94.4 % efficient: 5.29661 MW mechanical for 5 MW electrical | chapter 5 |
| tower | first fore-aft mode 0.324 Hz (FAST), 1 % damping | Table 9-1, chapter 6 |

![The model canvas|900](assets/64a577bb4357.png)

![The 3D scene: the tower, the nacelle and the rotor; the wind arrow scales with the wind speed and the blade tip colours with the pitch|600](assets/6552a0233cf3.png)

## The bond graph

The drivetrain is a rotational bond graph:
- `Rotor` 1-junction: the rotor inertia and the aerodynamic torque (an MSe);
- `Shaft` 0-junction: its twist rate loads the shaft's C and R;
- `Gearbox`: a TF of 97;
- `Gen` 1-junction: the generator inertia and the generator, an MSe that absorbs the converter's torque.

The tower is a translational 1-junction with the modal mass, stiffness and damping of its first fore-aft mode. The thrust (an MSe) drives it.

The aerodynamic block `RotorAero` reads the rotor speed and the nacelle velocity. Two stdlib `Lookup2D` blocks hold the BEM tables:

$$\lambda = \frac{\Omega R}{v_{rel}}, \qquad v_{rel} = v - \dot x, \qquad T_a = \frac{\tfrac12 \rho \pi R^2 C_p(\lambda, \beta)\, v_{rel}^3}{\Omega}, \qquad T = \tfrac12 \rho \pi R^2 C_t(\lambda, \beta)\, v_{rel}^2$$

The nacelle velocity in $v_{rel}$ is the aerodynamic damping of the tower: a nacelle moving downwind sees less wind and less thrust.

## The tables

`design/bem.py` computes $C_p$ and $C_t$ by blade-element momentum theory. It uses the report's 17 blade elements (Table 3-1) and its airfoil polars (Appendix B), with these corrections:
- Prandtl tip and hub losses;
- the Buhl high-induction correction;
- the 2.5° precone and the 5° shaft tilt.

The peak is $C_p$ = 0.4855 at $\lambda$ = 7.70, against the report's 0.482 at 7.55.

## The tower

`design/tower.py` is a finite-element model of the report's tower:
- a steel tube 87.6 m high, from 6 m to 3.87 m in diameter;
- 347 t of steel;
- the rotor and nacelle on top as one rigid body of 350 t.

Its first mode is 0.3216 Hz, between the report's FAST (0.3240 Hz) and ADAMS (0.3195 Hz) values. The modal mass is 442,803 kg and the stiffness 1.808 MN/m, normalised to the tower-top deflection.

Continue with [the controller](project:controller) and [the validation](project:validation).
