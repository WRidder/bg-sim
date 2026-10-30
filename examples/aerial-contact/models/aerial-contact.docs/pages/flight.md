# The free-flight controller

The same PX4-style cascade as the quadcopter example (X5.7), re-tuned for the hexarotor and the 250 Hz firmware (`design/design.py` derives every gain and prints the loop margins):

| loop | block | design |
| --- | --- | --- |
| position (P) | [Pos](block:Pos) | $K_p = 1$ 1/s, speed limit 2 m/s |
| velocity (PI) | [Pos](block:Pos) | $K_v = 3$ 1/s, $K_i = 1.2$ 1/s$^2$, thrust vector $F = m(a + g e_z)$, tilt limit 25 degrees |
| attitude (P) | [Att](block:Att) | quaternion error, $K = 5$ 1/s |
| rate (PID) | [Rate](block:Rate) | $K_p = (J + 0.02) \cdot 26$ rad/s: crossover 38 rad/s, phase margin 61 degrees |
| allocation | [Mix](block:Mix) | pseudo-inverse of the $4\times 6$ allocation matrix; attitude has priority over thrust when a rotor saturates |
| rotor speed | [Esc1](block:Esc1) | PI + motor-model feed-forward at 250 Hz: crossover 72 rad/s, phase margin 57 degrees |

**Gravity compensation and the CoM correction.** The thrust feedforward is $m_{nom}(a_{cmd} + g)$ with the total mass (2.5 kg assumed, 2.48 kg true). The arm and the end-effector hang ahead of the centre of mass and tip the nose down with the static torque $-g\,(m_{arm} L_m/2 + m_{ee}(L_m + 0.03)) = -1.604$ N m about $y_b$; the rate controller adds this constant after its limits (`tau_ff`), as the paper does with a tuned constant. The integrators have nothing static to carry, so the hover is clean (height within 1 cm of the set-point). The paper has no integral action in altitude; this model keeps the velocity integrator, which removes the small steady-state height error.

**Sensors.** [Imu](block:Imu) (gyro and accelerometer with bias, noise and Butterworth low-passes) and [Gps](block:Gps) (a 2 cm, 5 cm/s position and velocity fix) read the true state; [Nav](block:Nav) is a fixed-gain observer that observes the tilt through the velocity innovation, so it works with the strong, unmodelled arm reaction in contact: the accelerometer measures *all* non-gravitational forces.

Back to [the overview](page:overview).
