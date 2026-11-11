# Results and checks

## 7-DOF

![Left joints, box and hand error, left elbow, grasp loads|900](assets/a76c707ec4ea.png)

The arms track the IK through the move and the bias sweep. The box stays within 1.35 mm and 0.18° of its commanded pose over the whole run, and the hands within 1.29 mm and 0.19° of the grasp. Under the elbow bias the simulated left elbow moves like the IK elbow (within 0.23 mm). Each grasp carries about half the box weight (8.5 N against 7.36 N), and no servo uses more than 13 N·m.

## 6-DOF (J5 locked)

![6-DOF: hand error, grasp load and the left servo torques|900](assets/b8cd546e067f.png)

With J5 locked, the IK leaves each hand 3.5 mm and 3.3° away from its grasp, mirrored on the two arms. The box cannot follow both hands, so the two arms **fight through it**. The grasp force rises to 109 N and the moment to 31 N·m. The J6 wrist servo saturates at its 20 N·m limit from t = 5.09 s, and the grasp pushes the wrist 1.6° past its −60° limit (the dynamic joints have no hard stops). The hands stay at least 4.4 mm and 1.1° off the grasp.

| quantity | reference | bg-sim |
| --- | --- | --- |
| forward kinematics of the start posture (hands, left elbow, box) | numpy FK | ≤ 2.2e-16 |
| 7-DOF: box and hand errors over the run | ≤ 2 mm, 2° | box 1.35 mm, 0.18°; hands 1.29 mm, 0.19° |
| 7-DOF: left elbow vs the twin's IK elbow, bias 0 and 30° | twin | ≤ 0.23 mm |
| 7-DOF: in-model IK vs the twin | twin | 1e-14 deg |
| 7-DOF: grasp force at the dwell | 7.36 N (half the weight) | 8.52 N |
| 6-DOF: hand error after the move | not held | ≥ 4.37 mm, ≥ 1.08° |
| 6-DOF: grasp force, moment | (7-DOF: 8.5 N, 0.4 N·m) | up to 109 N, 31 N·m |
| power continuity (Tellegen) | 0 | 1.3e-17 of the throughput |

`expected.json` runs this model twice (as is and with `Traj/dof6 = true`) with 147 checks.

**Speed.** `Rodas5P` at 1e-6 / 1e-8 needs 18.6 ms per step (about 7 minutes for the run). `FBDF` at 1e-4 / 1e-6 agrees with it within 0.003° per joint over the first 0.3 s, at a tenth of the cost.
