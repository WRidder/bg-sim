# Results and checks

![Attitude error, phase, vertex loads and wheel speeds over the 3.8 s run|900](assets/91e67a1609c6.png)

![Centre of mass height and motor terminal voltage|900](assets/a7f69488d8fe.png)

## Measured (README, `run_checks.py --only tetra-3d`)

| quantity | value |
| --- | --- |
| face rest | each base vertex 4.578 N ($\sum f_n = 13.734$ N), apex 0, CoM height 0.050657 m |
| edge reached and held | phase 2 from 1.05 s; angle to the edge balance direction 0.70 deg at 1.2 s, 0.29 deg at 1.4 s, 0.077 deg from 1.7 s (tilt 0.9560 rad = 54.78 deg, target 54.74 deg); two loaded vertices, 6.867 N each, the other two at most 4e-18 N; CoM height 0.087898 m |
| vertex reached and held | phase 4 from 2.75 s; angle to the vertex balance direction 0.18 deg at 3.3 s, 0.067 deg at 3.5 s, 0.020 deg at 3.75 s (tilt 1.23113 rad, target 1.23096); one loaded vertex, 13.734 N; CoM height 0.152315 m |
| peak wheel speed | wheel 1: 314.5 rad/s (3003 rpm) at 2.56 s; wheels 2/3/4: 119.2 / 119.3 / 212.7 rad/s |
| peak motor torque | 1.473 N·m (wheel 1, 14.7 A) of the 1.6 N·m limit; wheels 2/3/4: 0.794 / 0.799 / 1.174 N·m; the allocator never saturates |
| peak terminal voltage | 32.6 V (motor 1), 12.7 / 12.9 / 22.3 V for motors 2/3/4, supply 48 V |
| null space | $\max\lvert n\cdot\tau - \lambda\rvert = 2.6\cdot10^{-16}$, `Tap/resid` 1.8e-15, realised body torque against the allocation 4e-16 N·m |
| quaternion norm | $\lvert q\rvert^2 - 1 \le 1.4\cdot10^{-14}$ |
| energy ledger | drift 0.95e-3 J over 3.8 s while the motors do 126 J of work |
| cost | 60 checks, 0 failed, 48.5 s in total (the run itself 36 s, 2508 signals) |

The apex has a contact too: it stays above 0.2 m and its load is at most 5e-18 N for the whole run (checked), but nothing is assumed.

## Checks (`expected.json`)

Phase by phase: attitude (tilt and angle to the balance direction), the loaded-vertex count and every vertex's normal force, the CoM height and horizontal position against the geometry, each phase reached ([Seq/ph](signal:Seq/ph)) and held (error bound over the hold window); wheel speeds below 340 rad/s, torques up to 1.6 N·m, terminal voltage below 48 V and their peaks; the null-space tap and the realised torque; quaternion norm; the energy ledger; `scene_bindings`; no W201, E101, E102, E103, E106, E007 or W206. `run_timeout` is 900 s.
