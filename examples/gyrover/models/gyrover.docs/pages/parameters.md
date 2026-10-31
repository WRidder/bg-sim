# Parameters

The paper gives the linearised equations about the upright rest, the tilt-servo model and the two gains, but **no masses or inertias**. The physical parameters were chosen so that the linearisation of our nonlinear model reproduces the paper's matrices (`design/paper_lin.py` prints the comparison).

| parameter | value | source |
| --- | --- | --- |
| flywheel speed | 15 000 rpm = 1571 rad/s | paper |
| tilt servo | $\ddot\theta_2 = \omega_c^2(u_2 - \theta_2) - \sqrt2\,\omega_c\dot\theta_2$, $\omega_c = 20\pi$ | paper, eq. 7 (the $-400\pi^2$, $-88.86$ entries of $A_2$) |
| gains $K_1 = (-18.44, -3.31, 1.16)$, $K_2 = (-0.0077, 1.001, 0.0019, 0.0179, -0.0022)$ | | paper, section 4 |
| wheel radius $R$ | 0.197 m | chosen to match $A_1$, $B_1$ |
| wheel mass, axial / transverse inertia | 2.0 kg, 0.0249 / 0.0146 kg m² | chosen (plausible) and $A_1$ |
| pendulum mass, CoM below the axle | 3.417 kg, 0.0939 m | chosen to match $A_1$ (gravity stiffness) |
| pendulum inertia (principal axes 45 deg off) | 0.0371 / 0.0353 / 0.0091 kg m² | chosen to match $A_1$, $B_1$ and $A_2$ |
| gimbal mass and inertia, CoM on the axle | 0.4 kg, 0.00087 / 0.0006 / 0.0007 kg m² | assumed |
| flywheel mass, axial / transverse inertia | 1.2 kg, 0.00301 / 0.00166 kg m² | axial inertia from the gyroscopic entries of $A_2$ (momentum $H$ = 4.73 N m s) |
| contact | $k = 10^6$ N/m at 1 mm, $c$ = 2 s/m, $\mu$ = 0.9, $v_s$ = 1 mm/s | assumed |

Total mass 7.0 kg. Our linearisation against the paper's:

| entry | ours | paper |
| --- | --- | --- |
| $A_1$ gravity terms | -44.58, -12.04 | -44.32, -11.91 |
| $B_1$ | 14.51, -0.353 | 14.52, -0.37 |
| $A_2$ row 4 | 49.3, -47.3, 6.75, -7.82, 22.4 | 51.5, -49.3, 6.5, -8.7, 23.37 |
| $A_2$ row 5 | 17.2, -16.5, 120.4, -120.8, 7.82 | 19.17, -28.3, 102.5, -103.7, 8.7 |
| $B_2$ | 47.3, 16.5 | 49.3, 28.3 |

The longitudinal subsystem matches to about 1 % and the lateral one to 5-17 %, except the tilt coupling of the heading-rate row (-16.5 against -28.3). Closed-loop poles with the paper's gains:

| loop | ours | paper's matrices | paper text |
| --- | --- | --- | --- |
| longitudinal ($K_1$) | -41.25, -3.60 ± 2.77j | -41.31, -3.59 ± 2.76j | |
| lateral ($K_2$, ideal servo) | -35.2 ± 33.3j, -9.27, -0.90, 0 | -34.3 ± 25.1j, -11.2, -0.86, 0 | -34.45 ± 25.18i, -10.34, -1.37, -0.1 |

The pole at zero is the conserved vertical angular momentum (a heading/precession mode that the lateral feedback cannot move at rest). The paper's -0.1 does not come out of its own printed matrices with the printed four-digit gains either: its $A_2$ is nearly singular.
