# Results and checks

## Inverse dynamics (this model)

![Torque error of the 3-link arm against the Robotics Toolbox|760](assets/ea6073954eae.png)

The error signals are [A3_TauErr1/e_rtb](signal:A3_TauErr1/e_rtb), `e_an` and the same for every joint of every arm. Largest absolute error over the run, bond graph minus Robotics Toolbox (the analytical error is identical to 1e-12):

| arm, joint | peak torque [N·m] | whole run [N·m] | from 0.02 s [N·m] |
| --- | --- | --- | --- |
| 1-link, joint 1 | 8.6 | 4.9e-4 | 7.8e-6 |
| 2-link, joint 1 / 2 | 39 / 13.5 | 1.3e-2 / 3.6e-3 | 1.8e-4 / 5.0e-5 |
| 3-link, joint 1 / 2 / 3 | 88 / 35 / 2.0 | 8.1e-2 / 3.0e-2 / 3.9e-4 | 9.5e-4 / 3.5e-4 / 4.5e-6 |
| 3-link + payload, 1 / 2 / 3 | 118 / 53 / 10 | 0.13 / 5.3e-2 / 6.6e-3 | 1.4e-3 / 6.0e-4 / 7.4e-5 |

The error is at most 0.11 % of the peak torque in the first millisecond and 0.0012 % afterwards. The first millisecond is a one-off ring of the compliant pivots (5 kHz, $\sqrt{k_t/m}$) excited when the jerk steps from zero at $t = 0$; it decays within about 10 ms. The tolerances in `expected.json` are the measured values with about 25 % margin. The remainder is the pivot compliance ($\approx 10^{-6}$ m) and the solver tolerance (`reltol` 1e-9); the cubic interpolation error of the speed (2e-11 rad/s) is negligible.

The angles are checked too: the integrated CSV speed reaches the CSV end angle (`cursor_value`, 1e-6 rad), and the scene bindings are validated, with the model tips equal to the scene kinematics to 1e-15 m.

## Forward dynamics (`planar-links-fwd`)

The CSV analytical torque is applied as the joint-side effort and the model integrates the motion in 1 s. The error is the difference of the joint angle to the CSV angle:

![Open-loop angle drift of the 2- and 3-link arms|760](assets/0da262b0dc4e.png)

| arm, joint | max drift [rad] |
| --- | --- |
| 1-link | 1.7e-7 |
| 2-link, 1 / 2 | 1.2e-6 / 7.6e-7 |
| 3-link, 1 / 2 / 3 | 3.3e-6 / 2.2e-6 / 3.4e-7 |

An open-loop arm integrates every torque error twice (the arms lie in the horizontal plane without gravity, so there is no gravitational amplification). The drift is the sum of the interpolation error of the torque, the pivot compliance and the solver tolerance; it is far below the 1 rad motion. The bounds in `expected.json` are the measured drifts with about 1.5× margin.

## 3-link arm with payload (`planar-links-payload`)

![Torque error with the payload against the 4-link Robotics Toolbox robot|760](assets/af95f1885410.png)

Same checks against `tau_rtb` of the 4-link robot (the fourth, dummy, joint held at 0).

## Run time

The three-arm inverse model compiles in about 3 s (1 067 equations, 12 states) and runs in 0.3 s; the forward model compiles in 5 s and runs in 5 s (the stiff pivots). Re-run `uv run examples/run_checks.py --only planar-links` to reproduce every number in `expected.json`.
