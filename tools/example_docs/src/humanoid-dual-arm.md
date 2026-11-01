@@ figures humanoid-ik
{
  "diagram": {"kind": "diagram", "model": "humanoid-ik"},
  "scene": {"kind": "scene", "model": "humanoid-ik", "t": 6.5},
  "run": {
    "kind": "plot", "model": "humanoid-ik", "xlim": [0, 6.5],
    "rows": [
      {"ylabel": "left arm joint [deg]", "series": [{"signal": "IKL/q1", "label": "q1"}, {"signal": "IKL/q2", "label": "q2"}, {"signal": "IKL/q3", "label": "q3"}, {"signal": "IKL/q4", "label": "q4"}, {"signal": "IKL/q5", "label": "q5"}, {"signal": "IKL/q6", "label": "q6"}, {"signal": "IKL/q7", "label": "q7"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "hand error [mm, deg]", "series": [{"signal": "IKL/pe", "label": "pe [mm]"}, {"signal": "IKL/oe", "label": "oe [deg]"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "left elbow (page) [m]", "series": [{"signal": "IKL/ex", "label": "x"}, {"signal": "IKL/ey", "label": "y"}, {"signal": "IKL/ez", "label": "z"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "elbow bias [deg]", "series": [{"signal": "Traj/elbow_bias", "label": "bias"}], "legend": true, "legend_loc": "right"}
    ]
  },
  "run6": {
    "kind": "plot", "model": "humanoid-ik", "overrides": {"Traj/dof6": true}, "xlim": [0, 6.5],
    "rows": [
      {"ylabel": "left arm joint [deg]", "series": [{"signal": "IKL/q1", "label": "q1"}, {"signal": "IKL/q2", "label": "q2"}, {"signal": "IKL/q3", "label": "q3"}, {"signal": "IKL/q4", "label": "q4"}, {"signal": "IKL/q5", "label": "q5"}, {"signal": "IKL/q6", "label": "q6"}, {"signal": "IKL/q7", "label": "q7"}], "legend": true, "legend_loc": "right",
       "hlines": [{"y": -90, "label": "J3 limit"}, {"y": -60, "label": "J6 limit"}]},
      {"ylabel": "hand error [mm, deg]", "series": [{"signal": "IKL/pe", "label": "stacked pe [mm]"}, {"signal": "IKL/oe", "label": "stacked oe [deg]"}, {"signal": "IdealL/pe", "label": "ideal pe [mm]", "style": "--"}, {"signal": "IdealL/oe", "label": "ideal oe [deg]", "style": "--"}], "legend": true, "legend_loc": "right",
       "hlines": [{"y": 2, "label": "held below 2"}]},
      {"ylabel": "nearest limit [%]", "series": [{"signal": "IKL/lim", "label": "stacked"}, {"signal": "IdealL/lim", "label": "ideal", "style": "--"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page humanoid-ik overview - | Overview
# Humanoid dual arm: the IK of two 7-DOF SRS arms on one box

A humanoid torso with two stacked 7-DOF SRS arms: shoulder pitch, roll and yaw, the elbow, forearm yaw, and wrist pitch and roll. The arms have real shoulder and wrist offsets. Both hands grasp one box. This model is the 1 kHz firmware alone, kinematic and fast, and mirrors the interactive page it was built from:

- [Traj](block:Traj) (`ObjectTrajectory`) holds the box at a start pose for 1.5 s. It then moves the box rest-to-rest to the commanded pose (dashboard sliders x/y/z/roll/pitch/yaw), dwells, and ramps the **elbow bias** from 0 to 30°. Its `dof6` switch locks J5 on every arm.
- [IKL](block:IKL) and [IKR](block:IKR) (`ArmIK`) are the stacked robot arms. Each runs the page's damped least squares with a null-space pull toward home, one iteration per tick.
- [IdealL](block:IdealL) and [IdealR](block:IdealR) are an ideal SRS pair (no shoulder or wrist offsets, the same link lengths). They are drawn 1 m to the robot's right for comparison.

![The model canvas|900](@fig:diagram)

The run: 6.5 s, `Tsit5` (there are no continuous states), 1301 output points. It takes about 3.4 s of solve time and 11 s in total.

## Dashboard

The dashboard repeats the page:

- **Inputs:** the object pose sliders, the elbow bias and the 6-DOF toggle (`Traj/dof6`). With auto-rerun, every change runs the model again.
- **Readouts:** the hand position error (mm), the orientation error (deg) and the nearest joint limit (%) of the stacked left and right arms and of the ideal left arm, coloured green below 2 mm / 2°, plus a held indicator.
- **Plots** of the joint angles and errors, and the redundancy text: 14 joints against 12 constraints.

## 3D view

The robot stands at the origin: left arm blue, right arm orange, the box purple with a translucent box at the commanded pose. The ideal pair (green) stands 1 m to its right.

![3D view at t = 6.5 s: elbow bias 30 deg, both elbows swung to the robot's right|500](@fig:scene)

Continue with [the IK and the redundancy](page:ik), [the 6-DOF failure](page:dof6) and [the results](page:results).
@@ page humanoid-ik ik overview | IK and redundancy
# The IK and the redundancy

## Counting

A rigid grasp fixes the full pose of a hand (3 position + 3 orientation constraints), so two hands on one box give **12 constraints**. Two 7-DOF arms have **14 joints, 2 left over**: one **self-motion** per arm, where the elbow swings about the shoulder-wrist line while the hand stays put.

## The page's damped least squares

[IKL](block:IKL) runs once per 1 ms tick, warm-started from its last solution. Angles are in degrees and the Jacobian is per degree, which are the page's units, so the page's constants carry over:

$$e = \begin{bmatrix} p_t - p \\ \tfrac12\, r_w \sum_i c_i \times t_i \end{bmatrix},\quad y = (JJ^\top + 10^{-5} I)^{-1} e,\quad z = 0.1\,(q_{home} - q)$$

$$v = (JJ^\top + 10^{-9} I)^{-1} J z,\qquad d = z + J^\top (y - v),\qquad q \leftarrow \mathrm{clamp}(q + d)$$

$r_w = 0.3$ m/rad weighs orientation against position. The task step $J^\top y$ removes the hand error. The pull $z$ toward home is projected out of the task space ($z - J^\top v$ is its null-space part), so it moves only the self-motion: among all the postures that hold the box, it picks the one closest to home.

**Elbow bias.** The bias is added to the shoulder-yaw home angle, mirrored by the arm's side $s$. The null-space pull then swings the elbows to the new home while the hands stay on the box. With 30° of bias the left elbow moves 47 mm and the right elbow 52 mm, and the hand error stays below 0.006 mm. Because the yaw joint also turns by $s\,q$, both elbows swing to the same side of the robot.

![Left arm: joints, hand error, elbow position and the bias ramp|900](@fig:run)

## Differences from the page

- **Exact Jacobian.** Where the page takes a 1° finite difference, the block uses the exact derivative of the page's error. This is generated scalar code, checked against a central difference to 5e-11. The solutions differ by up to 0.2° (stacked) and 0.4° (ideal) per joint.
- **Rate limit.** The whole step is scaled down to at most 0.05° per joint and tick (50°/s), where the page clamps each joint to ±8°. Scaling keeps the direction of the step, so a fast self-motion stays in the null space. The fixed points are the page's.
- **Solves.** The two 6×6 systems are solved by generated Cholesky factorisations: the compiler rejects `A \ b` on arrays (see [the results](page:results)).
@@ page humanoid-ik dof6 overview | The 6-DOF failure
# The 6-DOF failure

Switch on **6-DOF arms** (`Traj/dof6`): J5, the forearm yaw, is locked at 0. That leaves **12 joints for 12 constraints, no slack.** The object pose alone fixes both postures, and the elbow bias does nothing.

At the page's default pose (0, −0.1, 0.4) m the stacked arms cannot reach the grasp. The IK drives J3 onto its −90° limit and J6 onto its −60° limit and stops there with a residual hand error of **3.5 mm and 3.3°**. The pose is not held (the limit is 2 mm / 2°) and the nearest limit is 0 %. The ideal SRS arms (no offsets) still reach the pose within 0.97 mm and 0.77° on the same lock: **the shoulder and wrist offsets break the 6-DOF arm, and the seventh joint absorbs them.**

![6-DOF (J5 locked): left arm joints with the J3 and J6 limits, the hand errors of the stacked and ideal arms, and the nearest limit|900](@fig:run6)

The start pose of the scenario, (0, −0.20, 0.35) m, was chosen so that the 6-DOF stacked arms hold it exactly. Both variants therefore start from the same posture, and the difference appears when the box moves to the default pose.
@@ page humanoid-ik results overview | Results and checks
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
@@ figures humanoid-hold
{
  "diagram": {"kind": "diagram", "model": "humanoid-hold"},
  "scene": {"kind": "scene", "model": "humanoid-hold", "t": 4.0},
  "run": {
    "kind": "plot", "model": "humanoid-hold", "xlim": [0, 6.5],
    "rows": [
      {"ylabel": "left joint [rad]", "series": [{"signal": "LJ1/qout", "label": "q1"}, {"signal": "LJ2/qout", "label": "q2"}, {"signal": "LJ3/qout", "label": "q3"}, {"signal": "LJ4/qout", "label": "q4"}, {"signal": "LJ5/qout", "label": "q5"}, {"signal": "LJ6/qout", "label": "q6"}, {"signal": "LJ7/qout", "label": "q7"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "box error [mm, deg]", "series": [{"signal": "BoxError/e_mm", "label": "box [mm]"}, {"signal": "BoxError/e_deg", "label": "box [deg]"}, {"signal": "LHandError/e_mm", "label": "left hand [mm]", "style": "--"}], "legend": true, "legend_loc": "right",
       "hlines": [{"y": 2, "label": "2 mm / 2 deg"}]},
      {"ylabel": "left elbow (world) [m]", "series": [{"signal": "LW4/g[5]", "label": "x"}, {"signal": "LW4/g[6]", "label": "y"}, {"signal": "LW4/g[7]", "label": "z"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "grasp load [N, N m]", "series": [{"signal": "LGraspLoad/F", "label": "left F"}, {"signal": "RGraspLoad/F", "label": "right F"}, {"signal": "LGraspLoad/M", "label": "left M"}], "legend": true, "legend_loc": "right"}
    ]
  },
  "run6": {
    "kind": "plot", "model": "humanoid-hold", "overrides": {"Traj/dof6": true}, "xlim": [0, 6.5],
    "rows": [
      {"ylabel": "hand / box error [mm, deg]", "series": [{"signal": "LHandError/e_mm", "label": "left hand [mm]"}, {"signal": "LHandError/e_deg", "label": "left hand [deg]"}, {"signal": "BoxError/e_mm", "label": "box [mm]", "style": "--"}], "legend": true, "legend_loc": "right",
       "hlines": [{"y": 2, "label": "2 mm / 2 deg"}]},
      {"ylabel": "grasp load [N, N m]", "series": [{"signal": "LGraspLoad/F", "label": "left F"}, {"signal": "LGraspLoad/M", "label": "left M"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "left servo [N m]", "series": [{"signal": "ServoL/u2", "label": "u2"}, {"signal": "ServoL/u4", "label": "u4"}, {"signal": "ServoL/u6", "label": "u6"}], "legend": true, "legend_loc": "right",
       "hlines": [{"y": 20, "label": "J6 limit"}]}
    ]
  }
}
@@ page humanoid-hold overview - | Overview
# Humanoid dual arm: the dynamic bimanual hold

The firmware of `humanoid-ik` on the **dynamic** robot. Two multibody arms carry a 1.5 kg box on stiff grasp springs:

- **Arms** ([LJ1](block:LJ1) to `LJ7`, `RJ1` to `RJ7`): `Revolute3D` joints with the page's axes and offsets, and the five other directions compliant ($10^6$, damped at 0.7 of critical). The links ([LB1](block:LB1) to `LB7`) are `RigidBody3D` solid cylinders with **illustrative** masses: 1.0, 1.0, 2.0, 0.8, 1.2, 0.4 and 0.6 kg.
- **Drives**, one per joint: the motor torque `MSe` ([LMotor1](block:LMotor1)) on the reflected rotor inertia ([LRotor1](block:LRotor1)), then a torque sensor ([LTauSense1](block:LTauSense1)) and an elastic gear ([LSpring1](block:LSpring1), [LDamper1](block:LDamper1)) on the relative rate, then joint friction ([LFriction1](block:LFriction1)) into the joint's drive port. The springs start preloaded with the holding torque.
- **Grasp**: per hand, a `Revolute3D` weld ([LWeld](block:LWeld)) with all six directions sprung at $10^5$ N/m and $10^3$ N·m/rad, between the hand and the box ([Box](block:Box)).
- **Firmware** at 1 kHz: [Traj](block:Traj) → [IKL](block:IKL)/[IKR](block:IKR) → [ServoL](block:ServoL)/[ServoR](block:ServoR) (PID with integral and the holding-torque feedforward, torque limits 80 / 20 N·m).

![The model canvas|900](@fig:diagram)

The run: 6.5 s, `FBDF` with `reltol` 1e-4 and `abstol` 1e-6, 1301 output points. The system has 46 states and 6416 equations. It takes about 31 s of solve time and 66 s in total.

![3D view at t = 4 s: the box at the commanded pose|500](@fig:scene)

Continue with [the results](page:hold-results).
@@ page humanoid-hold hold-results overview | Results and checks
# Results and checks

## 7-DOF

![Left joints, box and hand error, left elbow, grasp loads|900](@fig:run)

The arms track the IK through the move and the bias sweep. The box stays within 1.35 mm and 0.18° of its commanded pose over the whole run, and the hands within 1.29 mm and 0.19° of the grasp. Under the elbow bias the simulated left elbow moves like the IK elbow (within 0.23 mm). Each grasp carries about half the box weight (8.5 N against 7.36 N), and no servo uses more than 13 N·m.

## 6-DOF (J5 locked)

![6-DOF: hand error, grasp load and the left servo torques|900](@fig:run6)

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
