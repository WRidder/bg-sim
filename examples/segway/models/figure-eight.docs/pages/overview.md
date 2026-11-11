# A figure of eight

**Scenario.** The transporter accelerates to **1.5 m/s** and, from 4 s, the heading set-point turns **+2π** in 11 s and then back by 2π in the next 11 s: two circles of opposite sense (radius $v\,T/2\pi = 2.6$ m) that join into an eight. Differential wheel torque steers: the wheel on the outside torques more than the one on the inside; the pitch loop is the same as in [the balance model](model:balance).

![The model canvas|1000](assets/8fc9af7b7f20.png)

![Path of the axle|620](assets/c528ee6b0b10.png)

![Heading, wheel torques and the voltage the motors need|900](assets/d7ffab608b23.png)

**Checks.** The heading, the position and the yaw rate follow the reference of `design/design.py` (non-linear pitch plane, yaw loop and the kinematic path of the axle): the heading returns to 0, and the axle passes the crossing point of the eight at the start of the first circle, between the circles and again at the end of the second one (the speed-up before the first circle is not part of the eight). The tyres creep less than 0.13 mm/s.

![3D view at t = 10 s|500](assets/a65bb5161793.png)

**Try:** change the cruise speed and the loop time with the dashboard sliders; a tighter or faster loop raises the lateral acceleration $v\,\dot\psi$, and the tyre friction cone ($\mu = 0.9$) is the limit.
