# Open loop: the unstable pole

**Scenario.** No control: the gains are zero and the motors give no torque. The transporter starts **0.002 rad** off upright and falls forward with free wheels. The tilt grows as $e^{5.23\,t}$, so it doubles every 0.13 s: the controller has to react within a few hundredths of a second.

![The model canvas|1000](assets/f52c8d374f08.png)

![Pitch and pitch rate of the free fall|700](assets/f8c904ae6c09.png)

**Checks.** The unstable open-loop eigenvalue of the analytic linearisation is $+5.2287\ \mathrm{s^{-1}}$ (the positive root of the linear model with the mass matrix $M = [[a_{11}, a_{12}], [a_{12}, a_{22}]]$ of `design/design.py`). The pitch at 0.2, 0.4, 0.6, 0.8 and 1.0 s agrees with the non-linear reference to 3 %. The bond graph has the wheels, the contact and the body in 3D, so this also tests the whole structure against the planar Lagrange equations.

![3D view at t = 1 s|500](assets/20f536fa36fb.png)

**Try:** change the body mass or the height of the centre of mass with the dashboard sliders and watch the fall time. A lower centre of mass is slower to fall (the pole is about $\sqrt{g/l}$ for a light wheel).
