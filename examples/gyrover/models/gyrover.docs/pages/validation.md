# Validation

Every number below is a check in `expected.json`, run by `uv run examples/run_checks.py --only gyrover`.

## Bond graph against the reference model

| run | quantity | largest difference |
| --- | --- | --- |
| showcase (30 s, all loops) | heading, lean, tilt | 2.1e-5, 2.0e-5, 2.8e-5 rad |
| | path x, y; speed | 0.27 mm, 0.17 mm; 0.15 mm/s |
| steady turn (after 3 s) | heading rate, lean | 5.1e-6 rad/s, 3.9e-6 rad |
| paper's figure 3 | pendulum angle, tilt, lean | 3.6e-5, 3.8e-5, 4.1e-5 rad |
| uncontrolled rolling (to 2 s) | heading, lean, path | 7.3e-3 rad, 3.5e-3 rad, 0.53 mm |

The uncontrolled rolling (`free` against `reference`, 1.5 m/s, 0.05 rad lean, no motor) is the sensitive case: the free robot has a slowly growing nutation, and the two models separate after about 2.5 s, which the slip and the joint compliance of the bond graph are enough to cause.

![Uncontrolled rolling, bond graph|1000](assets/aa659bc7ca86.png)

![Uncontrolled rolling, reference model|1000](assets/2880db6cf668.png)

## Energy

Without damping and drive (model `free`: undamped joints, the tilt held by a spring) the bond graph's energy book `Energy/Ebal` = kinetic + potential + contact spring energy + integrated contact loss stays constant to 3.4 mJ over 6 s. The contact losses are **2.6 mJ in the first 2 s** of clean rolling and **1.18 J by 6 s**, once the nutation makes the tyre side-slip. The reference model (no contact) conserves its energy to 0.3 mJ over 2 s. In the showcase, `Ebal` (with the motor work subtracted) holds to 2.8 mJ against 5.5 J of motor work.

![Energy book of the showcase|1000](assets/b10964a6e321.png)

## The steady turn

A wheel that leans by $\phi$ while rolling at speed $v$ turns. The balance of moments about the contact line (gravity against the gyroscopic moment of the flywheel and the centrifugal and spin moments of the robot) gives, to first order in the transverse inertias,

$$\dot\psi = -\frac{mgh\,\sin\phi}{H\cos(\phi - \theta_2) + m h\, v\cos\phi}$$

with $mgh = g\,(m_{tot}R - m_p l_p - m_{gr} l_g) = 10.41$ N m, the flywheel momentum $H = J_{ra}\,\omega_3 = 4.73$ N m s and $mh = m_{tot}R - m_p l_p + J_{wa}/R = 1.19$ kg m. `design.steady_turn` solves the full equations of the reference model for the exact steady turn.

Model `steady-turn` holds a lean set-point with the lateral loop at 1.5 m/s. It settles at lean 0.2088 rad, tilt 0.1114 rad, speed 1.4902 m/s and heading rate **-0.335169 rad/s**; the exact solution at that state is **-0.335157** (the formula: -0.335292). The radius $v/\dot\psi$ = 4.446 m agrees with a circle fitted to the path (4.445 m). In the showcase turns the formula gives 0.31251 rad/s against the measured 0.3126.

![Steady turn|1000](assets/7cb3f95d3c85.png)

## Gyroscopic stabilisation

Released at rest, standing on the rim at a 0.05 rad lean with the tilt held:

- **flywheel at 15 000 rpm** (model `spin`): the lean stays between 0.050 and 0.0519 rad for 5 s (a nutation of 1.9 mrad); the gravity moment makes the robot precess slowly about the vertical instead (heading rate -0.054 rad/s).
- **flywheel stopped** (model `no-spin`): the robot falls over. The lean grows as $e^{6.2 t}$ and passes 0.5 rad after 0.43 s.

![Flywheel spinning|1000](assets/bf0cf447ce49.png)

![Flywheel stopped|1000](assets/d9e5748faaea.png)
