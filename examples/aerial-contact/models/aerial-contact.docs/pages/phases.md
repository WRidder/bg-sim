# The phase machine

[Sup](block:Sup) holds the operator script and the discrete switching logic of Fig. 5 of the paper (50 Hz). Its output [Sup/phase](signal:Sup/phase) is 0 free flight, 1 engage, 2 contact, 3 disengage.

| transition | condition |
| --- | --- |
| 0 to 1 (engage) | the engage request at $t \ge 4.5$ s **and** the end-effector (wheel plane, estimated from the navigation filter and the arm angle) within 30 cm of the wall: the guard `d_guard`. Latches $t_e$ and $z_{sp} = z_b(t_e)$ |
| 1 to 2 (contact) | the wheel plane within 2 cm of the wall and the multirotor at rest ($\lvert v_x\rvert < 0.1$ m/s) for 0.3 s, i.e. the wall has stopped it (a fallback after 3 s) |
| 2 to 3 (disengage) | the request at $t \ge 28.5$ s. Latches $p_{sp} = (x_b(t_d) - C,\ y_b(t_d),\ z_b(t_d))$ with $C = 0.75$ m |

What runs in each phase:

1. **Free flight.** The position set-point follows a minimum-jerk move (0.45 to 0.75 m in x, the incremental set-points of the paper); the cascade of [the free-flight controller](page:flight) tracks it. $\mu_{sp} = \theta_b$.
2. **Engage.** [Eng](block:Eng) takes the three body angles as references, $(\varphi_{sp}, \theta_{sp}, \psi_{sp}) = (0, \theta_{sp}, 0)$, and holds the height $z_{sp} = z_b(t_e)$ with a PI loop on the vertical velocity: $F = m (g + a_z) / (\cos\varphi\cos\theta)$. There is no horizontal position loop; the tilted thrust carries the multirotor into the wall. The reference $\theta_{sp}$ starts at 12 degrees and ramps to 20 degrees over 4 s to soften the impact. $\mu_{sp} = \theta_b$.
3. **Contact.** The purely angular contact controller [Con](block:Con) of [its own page](page:contact) runs. It has no position input, so the multirotor follows the end-effector without any change of its set-points. $\mu_{sp} = \mu_c = \theta_{sp}$, and $\theta_{sp}$ ramps on to 27 degrees (4 s after the engage instant, over 3 s). The open-loop wheel velocity command $(v_y, v_z)$ in $[-1, 1]$ is issued only in this phase: 0.125 for 6 s from $t = 13$ s, a 2 s pause, -0.125 for 6 s, with 0.4 s smooth ramps.
4. **Disengage.** The free-flight controller runs with the latched step set-point.

[Sel](block:Sel) picks the attitude set-point and the thrust, [Mix](block:Mix) picks the torque (rate controller or contact controller); the integrators of the controllers that are not in charge are held at zero.

Back to [the overview](page:overview).
