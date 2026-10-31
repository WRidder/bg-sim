# Control design

## The paper's loops

The paper splits the linearised robot into a **longitudinal** part (pendulum angle $\theta_1$, pendulum rate $w_1$, wheel rate $\omega_{0z}$; input the drive torque $\tau_1$) and a **lateral** part (lean, tilt $\theta_2$, tilt rate $w_2$, roll rate $\omega_{0x}$, heading-rate component $\omega_{0y}$; input the tilt servo reference $u_2$), and closes each with a state feedback, $u = K x$. Block [Ctrl](block:Ctrl) does the same with true states (the paper used a Kalman filter):

- **balance and speed**: $\tau_1 = K_1 (x_1 - x_{1r})$ with the reference $x_{1r} = (0, -\omega_r, \omega_r)$, $\omega_r = v_{ref}/R$, so the same gain rolls the wheel at the set speed; saturated at 4 N m;
- **lean via the tilt**: $u_2 = K_2 (x_2 - x_{2r})$, saturated at 0.8 rad, feeds the paper's servo (eq. 7). The servo is realised by a stiff PD on the tilt motor, $\tau_2 = 40000\,(r - \theta_2) + 20\,(\dot r - w_2)$, which tracks the servo model's state $r$; a softer PD (gain 400) is destabilised by the gyroscopic load on the tilt axis;
- **flywheel speed**: $\tau_3 = 0.05\,(\omega_{3,ref} - \omega_3)$.

## Steering (ours)

The paper stabilises the robot; it does not steer it. Heading control works through the lean: a lean set-point $\phi_r = -0.35\tanh((\psi_r - \psi)/0.35)$ with a feed-forward of the steady-turn heading rate in the $\omega_{0y}$ reference, and a pre-scale of 2.04 (the inverse of the lean that the $K_2$ loop realises in steady state). With the mission of [Plan](block:Plan) the robot turns at 0.31 rad/s (radius 3.8 m) and closes the square within 0.025 rad of heading.

![Mission: heading, lean, speed and the motor torques|1000](assets/553c76d7bbd5.png)

## The paper's figure 3

Recovery from rest with $\theta_1(0) = 0.075$ rad and $\theta_2(0) = -0.2$ rad (model `fig3`):

| feature | paper (fig. 3, read from the plot) | here |
| --- | --- | --- |
| pendulum $\theta_1$ | dips to about -0.025 near 0.5 s, settled by about 1 s | crosses 0 at 0.31 s, minimum -0.008 at 0.72 s, within 0.002 after 1.24 s |
| wheel rate dip | about -0.08 to -0.1 rad/s near 0.2 s | -0.085 rad/s at 0.17 s |
| roll rate peak | about 0.22 rad/s near 0.3 s | 0.80 rad/s at 0.13 s |
| tilt $\theta_2$ | returns to 0 by about 2 s | -0.2 to -0.056 at 0.39 s, then settles at **-0.089 rad** |

![Figure 3 scenario|1000](assets/5fbb5924dfa6.png)

**What could not be reproduced.** The longitudinal response matches in shape and time scale. The lateral one does not end at upright: our robot settles in a slow steady precession (lean 0.112 rad, heading rate -0.252 rad/s) with the tilt at -0.089 rad. The reason is physical: standing on the rim, the vertical angular momentum about the contact is conserved (no yaw friction), so a start with the flywheel tilted cannot return to tilt 0 without turning. The paper's own linear model has the same zero pole; its matrices give the final tilt -0.30 rad. The larger roll-rate peak follows from the larger tilt coupling of our parameters in the roll row.

**Dissipation destabilises.** Adding drilling damping to the tyre (0.3 N m s/rad, model `fig3-drill`) makes the slow precession **unstable** under $K_2$: the lean grows to 0.29 rad at 4 s and 0.53 rad at 8 s. This is the Kelvin-Tait-Chetaev effect: a mode held only by gyroscopic coupling is lost when damping is added. A heading-rate loop around $K_2$ (as in the showcase) removes it.

![Figure 3 with drilling damping|1000](assets/1912812f7c67.png)
