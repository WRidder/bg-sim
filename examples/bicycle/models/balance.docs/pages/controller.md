# Controller

![The model canvas: the 3D bicycle and the controller|1000](assets/d55e04a33c7c.png)

A state feedback on the steer torque, designed by LQR on the [linear model](model:balance-linear) at 3 m/s (`design/design.py`):

$$T_\delta = -K x + N \phi_{ref}, \qquad x = (\phi, \delta, \dot\phi, \dot\delta)$$

| | value |
| --- | --- |
| weights | $Q = \mathrm{diag}(100, 10, 10, 1)$, $R = 1$ |
| gain $K$ | (−28.45, 18.70, −7.67, 1.97) |
| reference gain $N$ | −12.44 |
| closed-loop poles | −11.01, −2.59 ± 2.71 i, −2.85 |

The gains are the [L_phi](block:L_phi), [L_delta](block:L_delta), [L_phid](block:L_phid), [L_deltad](block:L_deltad) blocks (each $-K_i$) and [N_ref](block:N_ref); [Sense](block:Sense) provides the states. $N$ makes the steady turn at lean $\phi_{ref}$ the equilibrium of the linear closed loop: in a steady turn the lean equation gives $\delta = 1.196\,\phi$ and the steer equation the holding torque $T = -6.35\,\phi$ N m.

On the nonlinear bicycle the turn settles at 0.1016 rad lean and 0.1177 rad steer (linear design: 0.1 and 0.1196). The bicycle speeds up from 3.00 to 3.05 m/s while it leans (its centre of mass drops), and the controller has no integral action. The heading rate 0.3381 rad/s agrees with the rolling kinematics $v \tan\delta \cos\lambda / (w \cos\phi)$ at the measured speed, steer and lean to 0.03 %.

The gains are fixed for 3 m/s. At other speeds the loop still balances over a range (try `v` in the Model inspector), but the steady lean is no longer exactly the set-point.
