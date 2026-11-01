# Results and checks

| quantity | reference | bg-sim |
| --- | --- | --- |
| in-model IK vs its numpy twin, every tick, four arms, 7-DOF and 6-DOF | `humanoid.twin` | 4.4e-14 deg |
| 7-DOF, default pose: pe, oe, nearest limit | page: 0.0053 mm, 0.0010°, 9.7 % | 0.0052 mm, 0.00096°, 9.6 % |
| 7-DOF joints vs the page's solution | page IK (finite-difference Jacobian) | ≤ 0.2° stacked, ≤ 0.41° ideal |
| 7-DOF through the dwell and the bias sweep | held below 2 mm, 2° | peak 0.006 mm, 0.001° |
| elbow travel under 30° bias | twin | left 47.1 mm, right 52.4 mm |
| 6-DOF, default pose: pe, oe | page: 3.468 mm, 3.349° | 3.535 mm, 3.348° |
| 6-DOF joints | J3 = −90°, J6 = −60°, J5 = 0 | exact |
| 6-DOF elbow under the bias | does not move | shift < 6e-7 m |
| 6-DOF ideal SRS | page: 0.960 mm, 0.772°, held | 0.970 mm, 0.771°, held |

`expected.json` runs this model twice: as is and with `Traj/dof6 = true`. The 277 checks are written by `design/build_expected.py` from `design/references.json` (the page's IK in numpy, the twin and the forward kinematics), with tolerances of 5× the measured deviation.

**Notes on bg-sim.**

- The language spec offers `A \ b` (a fixed-size LU) in all scopes, but the compiler rejects `\` with array operands (E004). `ArmIK` uses generated Cholesky solves instead.
- Angle quantities declared in `deg` clash with `rad` (E006 "differ only in scale"), and `%` is not a valid unit. The degree-valued parameters and readouts carry no unit attribute.
