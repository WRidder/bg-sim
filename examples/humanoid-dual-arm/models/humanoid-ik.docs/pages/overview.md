# Humanoid dual arm: the IK of two 7-DOF SRS arms on one box

A humanoid torso with two stacked 7-DOF SRS arms: shoulder pitch, roll and yaw, the elbow, forearm yaw, and wrist pitch and roll. The arms have real shoulder and wrist offsets. Both hands grasp one box. This model is the 1 kHz firmware alone, kinematic and fast, and mirrors the interactive page it was built from:

- [Traj](block:Traj) (`ObjectTrajectory`) holds the box at a start pose for 1.5 s. It then moves the box rest-to-rest to the commanded pose (dashboard sliders x/y/z/roll/pitch/yaw), dwells, and ramps the **elbow bias** from 0 to 30°. Its `dof6` switch locks J5 on every arm.
- [IKL](block:IKL) and [IKR](block:IKR) (`ArmIK`) are the stacked robot arms. Each runs the page's damped least squares with a null-space pull toward home, one iteration per tick.
- [IdealL](block:IdealL) and [IdealR](block:IdealR) are an ideal SRS pair (no shoulder or wrist offsets, the same link lengths). They are drawn 1 m to the robot's right for comparison.

![The model canvas|900](assets/b6f7f420e9a2.png)

The run: 6.5 s, `Tsit5` (there are no continuous states), 1301 output points. It takes about 3.4 s of solve time and 11 s in total.

## Dashboard

The dashboard repeats the page:

- **Inputs:** the object pose sliders, the elbow bias and the 6-DOF toggle (`Traj/dof6`). With auto-rerun, every change runs the model again.
- **Readouts:** the hand position error (mm), the orientation error (deg) and the nearest joint limit (%) of the stacked left and right arms and of the ideal left arm, coloured green below 2 mm / 2°, plus a held indicator.
- **Plots** of the joint angles and errors, and the redundancy text: 14 joints against 12 constraints.

## 3D view

The robot stands at the origin: left arm blue, right arm orange, the box purple with a translucent box at the commanded pose. The ideal pair (green) stands 1 m to its right.

![3D view at t = 6.5 s: elbow bias 30 deg, both elbows swung to the robot's right|500](assets/2cf61d497449.png)

Continue with [the IK and the redundancy](page:ik), [the 6-DOF failure](page:dof6) and [the results](page:results).
