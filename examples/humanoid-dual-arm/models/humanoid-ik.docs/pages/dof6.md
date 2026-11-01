# The 6-DOF failure

Switch on **6-DOF arms** (`Traj/dof6`): J5, the forearm yaw, is locked at 0. That leaves **12 joints for 12 constraints, no slack.** The object pose alone fixes both postures, and the elbow bias does nothing.

At the page's default pose (0, −0.1, 0.4) m the stacked arms cannot reach the grasp. The IK drives J3 onto its −90° limit and J6 onto its −60° limit and stops there with a residual hand error of **3.5 mm and 3.3°**. The pose is not held (the limit is 2 mm / 2°) and the nearest limit is 0 %. The ideal SRS arms (no offsets) still reach the pose within 0.97 mm and 0.77° on the same lock: **the shoulder and wrist offsets break the 6-DOF arm, and the seventh joint absorbs them.**

![6-DOF (J5 locked): left arm joints with the J3 and J6 limits, the hand errors of the stacked and ideal arms, and the nearest limit|900](assets/712f5bc0c018.png)

The start pose of the scenario, (0, −0.20, 0.35) m, was chosen so that the 6-DOF stacked arms hold it exactly. Both variants therefore start from the same posture, and the difference appears when the box moves to the default pose.
