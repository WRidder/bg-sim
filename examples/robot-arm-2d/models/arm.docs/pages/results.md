# Results and checks

![Joint angles, torques and end effector position|900](assets/e7f7f369d9c5.png)

## Measured (README, real worker)

| quantity | value |
| --- | --- |
| $q_1$, $q_2$ at $t = 3$ s | 0.600000000002, -0.3999999999998 rad |
| settled error | $\max\lvert e_1\rvert = 4.9\cdot10^{-9}$, $\max\lvert e_2\rvert = 2.0\cdot10^{-8}$ rad over $[2, 3]$ s |
| 1 mrad settle time | 0.63 s after the step |
| peak joint torque | 30.000 N·m (shoulder, at its limit) and 9.061 N·m (elbow) |
| peak joint rate | 3.158 rad/s ($q_1$), 5.056 rad/s ($q_2$) |
| tip at $t = 3$ s | (0.6241542193, 0.2854577886) m, angle 0.2 rad |
| analytic FK of (0.6, -0.4) | $0.4\cos0.6 + 0.3\cos0.2 = 0.6241542193$, $0.4\sin0.6 + 0.3\sin0.2 = 0.2854577886$ |
| pose chain against FK over the run | 1.11e-16 m |
| run cost | 54899 adaptive steps (driven, 6003 rows), 262891 (free) |

## Acceptance checks (`expected.json`)

- [Joint1/qout](signal:Joint1/qout) = 0.6 and [Joint2/qout](signal:Joint2/qout) = -0.4 at 3 s within 1e-6 rad; the errors [Ctrl/e1](signal:Ctrl/e1), [Ctrl/e2](signal:Ctrl/e2) below 1e-6 rad over $[2, 3]$ s and below 1 mrad from 0.9 s;
- drive efforts within 30 / 10 N·m;
- `planar_fk` holds to 1e-6 m over all samples; the tip passes the cursor points at 0.3, 0.5 and 1.0 s (2 mm) and the analytic FK at 3 s (1e-6 m);
- an `energy_ledger` check on the driven run (tolerance 2e-4) in addition to what the README lists; no W201, E101, E102, E103, E106 or W206.
