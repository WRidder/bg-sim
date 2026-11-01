# Results

![Yaw rate, tyre loads and body slip|900](assets/0492a19a27f9.png)

The reference is a nonlinear four-wheel steady state (`design/reference.py`): combined-slip tyres with the same formulas, lateral and longitudinal load transfer from a static solve of the suspension, aero, the open differential with its viscous coupling, the free-rolling front wheels with rolling resistance, the unsprung masses' centripetal forces and the wheels' gyroscopic moment.

| steer | yaw rate [rad/s] | body slip [mrad] | lateral acceleration [g] |
| --- | --- | --- | --- |
| 0.04 | 0.11565 / 0.11582 | -11.28 / -11.32 | 0.298 / 0.295 |
| 0.08 | 0.22704 / 0.22742 | -23.26 / -23.35 | 0.585 / 0.579 |
| 0.12 | 0.32935 / 0.32993 | -36.47 / -36.62 | 0.848 / 0.840 |

Each cell is bg-sim / reference.

The four tyre loads agree to 0.7 %. The linear bicycle model (understeer gradient -0.25 deg/g at 25 m/s) predicts 0.35 g at the first level; the four-wheel model is lower because the cornering stiffness falls with load transfer.
