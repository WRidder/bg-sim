# The equation block `ArmDynamics3R`

The base yaw $q_1$ is about world $z$ (inertia $J_b$), the shoulder $q_2$ is the elevation of the upper arm above horizontal, the elbow $q_3$ is relative to the upper arm; point masses $m_2$ at the elbow and $m_3$ at the tip. The states are $q$ and the momenta $p = M(q)\,\dot q$; every joint is a `Power{Rotation}` port with `j.f` $= \dot q_i$ and `j.e` $= \tau_i$ into the arm:

$$\dot q = \dot q, \quad p = M\,\dot q, \quad \dot p = \tau + \frac{\partial T}{\partial q} - \frac{\partial V}{\partial q},$$

$$M_{11} = J_b + m_2 r_e^2 + m_3 r_t^2, \quad M_{22} = m_2 l_2^2 + m_3\,(l_2^2 + l_3^2 + 2 l_2 l_3\cos q_3), \quad M_{23} = m_3\,(l_3^2 + l_2 l_3\cos q_3), \quad M_{33} = m_3 l_3^2,$$

with $M_{12} = M_{13} = 0$, and $r_e, z_e, r_t, z_t$ and the three $\partial M/\partial q$ terms and $\partial V/\partial q$ exactly as in the plan. Parameters of [Arm](block:Arm): $l_2 = 0.4$ m, $l_3 = 0.3$ m, $m_2 = 2$ kg, $m_3 = 1$ kg, $J_b = 0.05$ kg·m², $g = 9.81$ m/s². Start $q = (0, 0.6, -0.9)$ rad. The formulas were verified symbolically (a sympy script built $T = \tfrac12 \dot q^T M \dot q$ and $V = g\,(m_2 z_e + m_3 z_t)$ from the geometry and checked $M$, $\partial T/\partial q$, $\partial V/\partial q$ against the plan's expressions; all differences simplify to zero). The total energy $E = \tfrac12 \dot q\cdot p + V$ is a block output (`Arm/E`).
