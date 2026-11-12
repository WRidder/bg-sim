# Parameters and sources

The README of the example has the full table, with a status (sourced, assumed or modelling choice) for every number. `design/xl330.py` and `design/robot.py` hold the numbers.

- **Sourced.** Rhoban BAM `xl330/m6.json`, at the commit microduck_rl pins: $k_t$ = 0.3660 N·m/A, $R$ = 2.811 Ω, armature 1.808e-3 kg·m², and the M6 friction terms. From BAM's `XL330Actuator`: the P-gain divisor 256, the PWM limit 885 and the current limit 1.75 A. From the ROBOTIS e-manual: gear 288.4 and 4096 counts/rev. From microduck: the P gain 200, I = D = 0, a 2S Li-ion pack (6.6 to 8.2 V) and the HOME pose. From microduck_rl: the latency range of 15 to 30 ms, 2° of backlash, the friction and armature randomisation, the MJCF masses and inertias, the soles and the foot friction 1.0.
- **Assumed.** The latency is 20 ms, inside the training range. The gear tooth stiffness is 100 N·m/rad and its damping 0.1 N·m·s/rad. The battery resistance is 0.1 Ω and the bus capacitance 1 mF. The contact stiffness and damping are also assumed.
- **Derived.** The P stiffness is 0.554 N·m/rad at 7.4 V and kp 200, the same as the MJCF position actuators (kp 0.55). The stall torque is 0.641 N·m at 1.75 A, and the free speed 20.2 rad/s.
