# LQR with a Kalman filter

**Scenario.** The same scenario as the PID model: steps at 1 s, 6 s and 11 s, and a push at 15 s.

**The controller.** [LQGX](block:LQGX) and [LQGY](block:LQGY) each hold a steady-state Kalman
filter. Its model knows that the camera ([FrameX/y](signal:FrameX/y)) is one frame late, so the
estimate [LQGX/xhat](signal:LQGX/xhat) is where the ball is now. An LQR with integral action and
anti-windup follows the filter. All gains come from `design/design.py`.

**Against the design.** The x step settles in **1.97 s** with **1.4 %** overshoot; the design
gives 1.6 s and 1.5 %. The integral is slow (50 s), so the ball first stops within about 2 mm,
where the rolling resistance holds it. The push moves the ball by only 46 mm (PID: 61 mm). In the
design, the LQR tolerates 8 frames of camera delay and the PID 7. On the rig with 6 frames, the LQR
overshoots by 9 % and the PID by 24 %.

**The hop.** At 11 s both set-points jump back while the ball is 0.1 m off the axis. The LQR
commands a 0.6 rad servo step, and the plate edge drops faster than gravity can follow. The ball
leaves the plate for about 20 ms: [Contact/f_n](signal:Contact/f_n) reads zero, and the ball slips
briefly on landing. Set the **set-point filter** on the dashboard to 1 s and the hop goes away. With
the feed-forward riding on the filtered reference, the steps then settle in 0.9 s.

![Steps, the Kalman estimate and the normal force|900](assets/d607bfa6f1f6.png)

![Between 1 and 2 s: the camera lags one frame, the estimate does not|900](assets/c25a79b9d1ae.png)

The rig and the comparison: [the ball-and-plate rig](project:rig).
