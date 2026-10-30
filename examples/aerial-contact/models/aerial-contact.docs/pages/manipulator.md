# The manipulator and the end-effector

**Servo.** [ServoCtl](block:ServoCtl) is a PD law with a smooth torque limit, $\tau = \tau_{max}\tanh\big((K_p(q_{sp} - q) - K_d\dot q)/\tau_{max}\big)$ with $q_{sp} = -\mu_{sp}$, bandwidth 40 rad/s, 8.4 N m stall torque. It acts through a `Revolute3D` joint whose five held directions are compliant; the reaction acts on the multirotor.

**Rubber shock mount.** [RubK](block:RubK) turns the unit quaternion of the spherical joint into the exact conservative restoring torque $-2 k w v$ ($U = 2k\sin^2(\vartheta/2)$) plus a damper; the three torque components act on the end-effector through the joint's rotation ports. The end-effector's orientation is thereby decoupled from the arm's: it sags 2.5 degrees under its own weight in free flight and lines up with the wall when the three wheels touch it.

**Omni-wheel contact.** The standard `ContactPoint` has two fixed isotropic friction tangents; a wheel does not, so [Wheel1](block:Wheel1) is the example-local `OmniContact`. The normal force is the same smooth Hunt-Crossley law ($k = 4000$ N/m with the 3/2 power, $c = 4$ s/m, no pull), and the traction is anisotropic. With $e$ the wheel's drive direction (its body direction $(0, -\sin\alpha, \cos\alpha)$ rotated to the world and projected on the wall) and $r = n \times e$ the free roller direction, $u$ the commanded wheel surface speed and $v$ the velocity of the contact point:

$$s_d = e\cdot v + u,\quad s_r = r\cdot v,\qquad F_d = \mu_d f_n \tanh\frac{s_d}{v_s},\quad F_r = \mu_r f_n \tanh\frac{s_r}{v_r},\qquad F = f_n n - F_d\, e - F_r\, r$$

with $\mu_d = 0.7$, $\mu_r = 0.04$. A wheel resists slip along its driven direction (rolling without slip: $s_d = 0$) and is almost free along its rollers. The three wheels at 120 degrees therefore hold the end-effector in the plane when their commands are zero and move it with the velocity $v$ when $u_k = -v_{max}\,d_k\cdot v_{cmd}$ ([Omni](block:Omni): $v_{max} = 0.4$ m/s, the "velocity scale" of the command in $[-1, 1]$). The anisotropic traction is energy-consistent: both forces act against their slip.

Back to [the overview](page:overview).
