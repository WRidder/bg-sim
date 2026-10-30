# Results and checks

![Joint angles, controller torques and TCP position|900](assets/d1261d231441.png)

## Measured (README, 2 s run)

| quantity | value |
| --- | --- |
| settled joint-angle error at 2.0 s | 1.0e-5, 3.4e-5, 1.3e-5, 9.6e-5, 7.8e-5, 2.0e-5 rad |
| TCP error against analytic FK of the target angles | 9.9e-5 m (target (-0.44364, -0.70827, 0.21091) m) |
| peak torque | 19.8, 54.6, 20.7, 1.53, 0.20, 0.0013 N·m (limits never reached) |
| peak tracking error | 0.038, 0.018, 0.016, 0.029, 0.105, 0.0053 rad |
| settled torque minus target gravity torque | under 7e-3 N·m |
| states of the compiled system | 72 |
| accepted steps | 8973 |
| compile | 9.6 s with a structural cache hit; a cold first compile about 90 s |
| solve | 113 s for 2.0 s of simulated time |
| `uv run examples/run_checks.py --only robot-arm-3d` | 43 checks for `arm` in the original X-MB3 run |

The check bounds are 5x the measured errors. The TCP position differs from the rigid-body forward kinematics by the compliant joints' sag (about 1e-5 m per joint under gravity) plus the angle error times the 0.9 m reach.

## Checks (`expected.json`)

Start joint angles (home pose) and settled angles at 2 s (within 0.5 mrad); joint rates at 2 s below 0.005 rad/s; the TCP at the start (-0.6278019, -0.1220454, 0.2971925) m and at 2 s (-0.4436411, -0.7082700, 0.2109132) m; the settled controller torques [Ctrl/u2](signal:Ctrl/u2) = -45.85 N·m and [Ctrl/u3](signal:Ctrl/u3) = -17.83 N·m; torque limits (150 N·m for joints 1 to 3, 28 N·m for 4 to 6); tracking errors bounded; no W201, E101, E102, E103, E106, E007 or W206.
