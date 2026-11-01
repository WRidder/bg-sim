# Static hold: the cup forces against a hand calculation

The offset-CoM carton (60 mm, 30 mm), gripped at the box centre, carried slowly: Cartesian with stops at 0.1 m/s. In the cruise of the transfer, the carton hangs still. There the cup forces can be checked against a hand calculation (`design/reference.py`).

The carton is a rigid plate on five bellows. Each bellows has an axial spring $k_{ax}$ in series with the cylinder end stop, giving $k_s$, and a tilt spring $k_{tilt}$ in series with the rod bending, giving $k_t$. The centre of mass hangs $d = H_p/2$ below the lip plane, which adds a pendulum stiffness $m g d$:

$$K = 2 k_s a^2 + 5 k_t + m g d, \qquad \varphi_x = \frac{m g c_x}{K}, \quad \varphi_y = \frac{m g c_y}{K}, \qquad T_i = \frac{m g}{5} + k_s\,(x_i \varphi_x + y_i \varphi_y).$$

| zone | hand [N] | simulation at t = 6.52 s [N] |
| --- | --- | --- |
| 1 (centre) | 2.943 | 2.943 |
| 2 (+x) | 9.281 | 9.274 |
| 3 (+y) | 6.112 | 6.100 |
| 4 (−x) | −3.395 | −3.387 |
| 5 (−y) | −0.226 | −0.213 |

The sum is $m g$ = 14.715 N. Negative forces push: the light side presses its bellows. The vacuum is at the operating point, 55.83 kPa (hand calculation 55.83 kPa). The carton tilts by $\varphi_x$ = 3.7°. With the bellows moment, the most loaded cup reaches U = 0.65 at rest. That is why the centre grip cannot hold this carton with a margin of 0.5 (see `offset-com`).

![Cup forces and the gripper path|900](assets/46cee6ca1a28.png)
