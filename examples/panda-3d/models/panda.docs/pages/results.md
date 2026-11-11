# Results and checks

![Joint angles, joint-torque sensors and the flange against its target|900](assets/10d4721649d2.png)

| quantity | value |
| --- | --- |
| IK in the model vs the Python port, along the run | 4e-15 rad |
| FK of the in-model IK vs its target, along the run | 1e-15 m, 2e-15 (rotation) |
| IK round trip, 20000 random poses ($q_4 \le -0.5$) | 4.5e-13 m, 1.1e-12 (rotation), all solved |
| TCP tracking error, max / rms over the tour | 16.6 mm / 6.6 mm (lag in the moves, no inertia feedforward) |
| TCP error at the end of each dwell | 0.64, 0.92, 0.61, 0.32 mm |
| TCP error at 5.15 s | 0.055 mm |
| settled $\tau_J$ minus the MuJoCo gravity torque | under 1.6e-3 N·m |
| peak joint rates | 1.53 rad/s (joint 2; limit 2.175) |
| `IK/flag` | 0 throughout |
| compiled system | 21 states, 2907 equations |
| flatten / compile / solve | 1.3 s / 3.4 s / 18.8 s (23328 steps) |

`expected.json` holds 84 checks for this model, written by `design/build_expected.py` from the references: the start pose; the return to the ready pose; the flange back home; the flange tracking per axis (1.5x the measured value); the flange and the IK output at the middle of each dwell (the IK against the Python port within 1e-8 rad); the settled torque sensors against MuJoCo gravity; the torque and rate limits; the IK flag; and no diagnostics.
