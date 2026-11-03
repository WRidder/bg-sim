# Cascaded PID

**Scenario.** The ball starts at rest on the level plate at the centre. The set-points are:

- x to **0.10 m** at 1 s;
- y to **0.08 m** at 6 s;
- both back to the centre at 11 s;
- a **0.6 N, 50 ms** push in y at 15 s ([Push](block:Push)).

**The loops.** [PIDX](block:PIDX) and [PIDY](block:PIDY) run at 30 Hz on the camera reading
([FrameX/y](signal:FrameX/y), one frame old) and give the servo set-points. [ServoX](block:ServoX)
and [ServoY](block:ServoY) close the 500 Hz servo loops on the encoders.

**Against the design.** The x step settles (±2 mm) in **1.65 s** with **0.8 %** overshoot. The
linear design in `design/design.py` gives 1.37 s and 1.9 %. The rig adds the dead band, the pixel
rounding, the camera noise and the rolling resistance. The resistance lets the ball rest on a tilt
of up to 0.002 rad, so the ball stops within about 1 mm and the integral removes the rest. The push
moves the ball by 61 mm, and it is back within 4 mm 5 s later.

![Steps and push: position, plate angles and servo voltages|900](assets/b54ca5e15317.png)

**What to try.** Lower Kp on the dashboard. Switch the task to the circle or the figure-8: without
feed-forward the PID lags about 40 mm behind. Set the push to 1.2 N. Set the ball inertia to 0.667,
a hollow ball, which accelerates 16 % less per plate angle.

The rig and the comparison with the LQR: [the ball-and-plate rig](project:rig).
