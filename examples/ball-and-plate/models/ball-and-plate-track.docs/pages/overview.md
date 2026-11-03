# Tracking a figure-8

**Scenario.** The LQR with the Kalman filter follows a **figure-8** ([Task](block:Task), task 3):
x = 0.10 sin(ωt), y = 0.06 sin(2ωt), with an 8 s period. The path grows from the centre over
3 s. Task 2 is a **circle** of radius 0.08 m and period 6 s.

**Feed-forward.** The task block also outputs the reference's velocity, acceleration and jerk. The
controller tilts the plate to the angle that gives the reference acceleration (a/K_bb), plus the
servo lag (τ_s ω) and the ball's weight on the servo. Feedback only corrects what is left.

**Result.** After the growth phase, the RMS error is **1.9 mm in x and 1.7 mm in y**. For the
circle it is 1.8 and 1.9 mm. Most of that comes from the rolling resistance, which the feed-forward
does not know about. A check run without it reaches **0.2 mm**, the value of the linear design. The
PID without feed-forward lags about 40 mm on both paths.

![The figure-8 on the plate (XY)|600](assets/476325d5be75.png)

![Tracking error and plate angles|900](assets/72f97c7394fe.png)

**What to try.** Switch the task to the circle. Set the ball inertia to 0.667: the feed-forward
assumes a solid ball, so the plate tilts too little and the error grows. Use the **3D view** to
watch the red target ring and the ball.

The rig and the comparison: [the ball-and-plate rig](project:rig).
