# Results and checks

![Speed, position and q-axis current of the baseline run|900](assets/b3616fbc470f.png)

Zoom on the speed step at 0.05 s (the current saturates at the 15 A limit):

![Speed step and current|900](assets/c51c722d9f33.png)

## Measured results (README, `expected.json`)

| check | baseline |
| --- | --- |
| speed 100 rad/s: rise / overshoot / settle | 5.1 ms / 3.4 % / 15 ms |
| position step (about 9.5 rad to 0): rise / overshoot / settle (5 mrad) | 106 ms / 0 % / 380 ms |
| current 15 A: rise / overshoot / settle (0.8 A) | 0.44 ms / 4.2 % / 0.63 ms |
| peak $i_q$ / torque | 15.80 A / 7.585 N·m |
| peak voltage vector | 173.205 V |
| phase-current ripple (RMS) | 0.00064 A |
| position at 1.15 s | -6.6e-4 rad |
| speed at 1.15 s | 0.014 rad/s |

The current and torque checks allow 16 A / 7.7 N·m although the command limit is 15 A / 7.2 N·m: the measured $i_q$ overshoots the reference by up to 5 % with the 500 Hz current loop. The averaged $V_{dc}/\sqrt3$ limit is exact (173.205 V). The run reports only W205 (the dimensionless Generic bond island, expected for a bond graph without a concrete domain); E900, E901, E103, E104, E105, E106 and W206 are forbidden by `no_diagnostics`.

The five variants have 12 / 15 / 13 / 15 / 19 model checks and 8 baseline-versus-variant comparisons (82 checks in total); the whole example lane reported 170 passed, 0 failed in 155.8 s.
