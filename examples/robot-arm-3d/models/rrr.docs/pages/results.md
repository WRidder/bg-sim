# Results and checks

![Joint angles, tracking errors and motor voltages of the RRR arm|900](assets/51e8ebbf68be.png)

| check | measured (README) |
| --- | --- |
| tracking error after the moves settle (plan: below 0.01 rad), from 4.0 s | 1.5e-8, 9.1e-9, 2.0e-8 rad; from 3.5 s: 1.2e-5, 1.5e-6, 1.5e-5 rad |
| tracking error during the moves | 0.0145, 0.0088, 0.0203 rad |
| peak motor voltage (limit 48 V) | 14.8, 6.6, 6.6 V |
| Julia run against the numpy closed-loop replica, `Arm/q1..q3` over the whole run | 6.4e-11, 5.6e-11, 1.7e-9 rad |
| diagnostics | W201 only: the motor rotors behind the rigid gears are derivative-causal with the arm inertia (the reduction handles it) |

One detail of the replica: the Julia run holds the controller output at its default (0 V) through the first period, so the first command lands at 1 ms; the replica does the same (`first_tick = 1`); with the command at $t = 0$ it differs by 4e-4 rad during the first 0.2 s.
