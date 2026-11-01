# Static hold: the cup forces against a hand calculation

The offset-CoM carton (60 mm, 30 mm), gripped at the box centre, carried slowly: Cartesian with stops at 0.1 m/s. In the cruise of the transfer, the carton hangs still. There the cup forces can be checked against a hand calculation (`design/reference.py`).

The carton is a rigid plate on five bellows. Each bellows has an axial spring in series with the cylinder end stop, giving $k_s$, and a tilt spring in series with the rod bending, giving $k_{t,i}$. The bellows are nonlinear, so both are taken at the hang point: the vacuum lift stroke ($A_{fold}\,\Delta p$) and the load $m g/5$ set the extension (−2.6 mm, the bellows pulled short), the tangent of the force-stroke law gives $k_s$, and the side-stiffness factor $k_f = (1 + c_{vac}\Delta p/p_{atm})\,e^{-c_{ext}\,ext_i/L_0}$ of each cup's own extension gives $k_{t,i} = (1/(k_{tilt} k_f) + 1/k_{r,rod})^{-1}$ (1.7 to 2.4 N·m/rad: the vacuum doubles the tilt stiffness, the loaded side is softer). The centre of mass hangs $d = H_p/2$ below the lip plane, which adds a pendulum stiffness $m g d$:

$$K = 2 k_s a^2 + \textstyle\sum_i k_{t,i} + m g d, \qquad \varphi_x = \frac{m g c_x}{K}, \quad \varphi_y = \frac{m g c_y}{K}, \qquad T_i = \frac{m g}{5} + k_s\,(x_i \varphi_x + y_i \varphi_y),$$

solved as a fixed point over the cup forces (the extensions depend on $T_i$).

| zone | hand [N] | simulation at t = 6.52 s [N] |
| --- | --- | --- |
| 1 (centre) | 2.943 | 2.942 |
| 2 (+x) | 7.571 | 7.554 |
| 3 (+y) | 5.257 | 5.251 |
| 4 (−x) | −1.685 | −1.670 |
| 5 (−y) | 0.629 | 0.633 |

The sum is $m g$ = 14.715 N. Negative forces push: the light side presses its bellows. The vacuum is at the operating point, 55.83 kPa (hand calculation 55.83 kPa). The carton tilts by $\varphi_x$ = 2.7° and $\varphi_y$ = 1.3°. With the bellows moment, the most loaded cup reaches U = 0.66 at rest (hand calculation 0.658, simulation 0.666). That is why the centre grip cannot hold this carton with a margin of 0.5 (see `offset-com`).

![Cup forces and the gripper path|900](assets/b10ae6e99880.png)
