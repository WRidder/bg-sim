# Validation

![The quasi-steady power curve of wind-turbine-steady|900](assets/a5e96f90c236.png)

**Steady states.** The checks run `wind-turbine-steady` with a constant wind at 5, 8, 10, 11, 12, 14, 18 and 25 m/s. Each run checks:
- the rotor speed, the generator torque, the power, the thrust and the tower deflection against `design/design.py`, which runs the same controller law and tables in numpy;
- in region 3, the pitch against the report's Table 7-1.

| wind [m/s] | pitch here [deg] | Table 7-1 [deg] |
| --- | --- | --- |
| 12 | 3.91 | 3.83 |
| 14 | 8.62 | 8.70 |
| 18 | 14.85 | 14.92 |
| 25 | 22.97 | 23.47 |

Rated power is 5.000 MW from 11.3 m/s up.

**Modes.**
- The drivetrain torsion mode is 2.223 Hz with 5 % damping, the two-inertia formula $\omega = \sqrt{k(1/J_r + 1/(N^2 J_g))}$.
- The tower mode is 0.32 Hz. It is about 5 % damped in operation: 1 % structural plus the rotor's aerodynamic damping.
- [wind-turbine-open-loop](model:wind-turbine-open-loop) reads both from ring-downs, and [wind-turbine-turbulent](model:wind-turbine-turbulent) from the spectrum.

The report's drivetrain mode (0.62 Hz) involves the blades' edgewise bending, which this rigid-rotor model leaves out.

**Energy.** The port-power ledger of every model closes:
- the Tellegen residual is zero to round-off;
- the kinetic and elastic energy changes by the work of the aerodynamic torque, the thrust and the generator, minus the damping.
