# Equations of motion

The design model of `design/cartpend.py` is the Lagrangian of the same mechanism. The coordinates are the cart position $x$ and the **absolute** link angles $\theta_1 \ldots \theta_3$ from the upward vertical, counter-clockwise; link $i$ points along $u_i = (-\sin\theta_i, \cos\theta_i)$.

$$p_i = p_{i-1} + L_{i-1} u_{i-1}, \qquad p_1 = (x, 0), \qquad c_i = p_i + \ell_i u_i$$

with link length $L_i$ and centre-of-mass distance $\ell_i = L_i / 2$. With $m_{\mathrm{eff}} = m_{\mathrm{cart}} + J_m (N/r)^2$ (the rotor inertia reflected through the 3:1 gearbox and the pulley):

$$T = \tfrac12 m_{\mathrm{eff}} \dot x^2 + \sum_i \left( \tfrac12 m_i \lvert \dot c_i \rvert^2 + \tfrac12 J_i \dot\theta_i^2 \right), \qquad V = g \sum_i m_i\, c_{i,y}$$

The Euler-Lagrange equations $M(q)\ddot q = Q + \partial_q L - \dot M \dot q$ have the generalised forces

$$Q = \begin{bmatrix} \alpha V - \beta \dot x \\ 0 \end{bmatrix} - \partial_{\dot q} \left( \tfrac12 \sum_i b_i (\dot\theta_i - \dot\theta_{i-1})^2 \right) + J_{\mathrm{tip}}^{\top} F_d\, n_\perp$$

where the motor acts on the cart only. With the armature inductance neglected (the electrical time constant is $L/R = 0.33$ ms):

$$\alpha = \frac{k_t N}{r R} = 3.775\ \mathrm{N/V}, \qquad \beta = \left( \frac{k_t^2}{R} + b_m \right) \frac{N^2}{r^2} = 21.45\ \mathrm{N\,s/m}$$

so a shorted motor ($V = 0$) is a viscous damper of 21.4 N s/m on the cart. $F_d$ is the disturbance force on the tip link, perpendicular to it ($n_\perp = (-\cos\theta_n, -\sin\theta_n)$), applied at the tip.

The state is $z = [x, \theta_1 \ldots \theta_3, \dot x, \dot\theta_1 \ldots \dot\theta_3]$ (8 states) and the input is the motor voltage $V$. The bond graph has the same degrees of freedom but also the stiff pivot, belt and winding states, which the design model replaces by their quasi-static limits. Its joint angles relate to $\theta$ by $q_1 = \theta_1 + \pi/2$ and $q_j = \theta_j - \theta_{j-1}$ (the quantities [Joint1](block:Joint1) etc. report).

The `triple-cart-free` model checks that the two agree: it releases the plant from rest at $\theta = (-2.3, -1.4, -2)$ rad, $x = 0.05$ m with the motor shorted and compares the angles with this ODE (maximum difference 4.21e-04 rad over 1.5 s, see [the results](page:results)).
