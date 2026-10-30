# Equations of motion

The generalised coordinates are the joint coordinates of the bond graph, $q = (q_1, \dots, q_{3})$: the arm angle $q_1$ and, for each link, its angle relative to the link below ($q_2$ from upright for the first link). With the bar poses $R_i(q)$, centres $p_i(q)$, masses $m_i$ and principal inertias $J_i$ the kinetic and potential energies are

$$T = \tfrac12 J_r \dot q_1^2 + \sum_i \tfrac12 m_i |\dot p_i|^2 + \tfrac12 \omega_i^T J_i \omega_i, \qquad V = \sum_i m_i g\, p_{i,z},$$

with $\hat\omega_i = R_i^T \dot R_i$ and the rotor inertia reflected to the arm axis $J_r = n^2 J_m = 1.90e-03$ kg·m². Lagrange's equations give

$$M(q)\,\ddot q = \frac{\partial T}{\partial q} - \dot M\,\dot q - \frac{\partial V}{\partial q} + Q, \qquad Q = \begin{pmatrix} \tau_m - c_g \dot q_1 \\ -b_j \dot q_2 \\ \vdots \end{pmatrix}.$$

The servo (winding inductance neglected in the design model) delivers at the arm axis

$$\tau_m = \frac{n k_t}{R_m} \left(u - n k_t \dot q_1\right), \qquad c_g = \frac{n^2 k_t^2}{R_m} + n^2 b_m,$$

with $u$ the clamped voltage ([Ctrl/u](signal:Ctrl/u)). `design/rotary_lib.py` builds $M$, the Coriolis terms and the gravity with CasADi from these energies, and linearises them for the LQR.

## Design model against the bond graph

Released from rest at $q = [0.25, 2.4, -0.9]$ rad with the motor terminals at 0 V, the Lagrangian model and the bond graph (model `pendulum-double-rotary-free`) stay within **2.38 mrad** over 3 s (arm 0.42 mrad, links 1.52, 2.38 mrad). The difference is the joint compliance, the winding inductance and the gear elasticity that the design model neglects.

![Free swing, design against bond graph|700](assets/cde50cbb3433.png)
