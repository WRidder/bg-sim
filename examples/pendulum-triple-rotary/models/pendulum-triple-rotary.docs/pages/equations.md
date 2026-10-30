# Equations of motion

The generalised coordinates are the joint coordinates of the bond graph, $q = (q_1, \dots, q_{4})$: the arm angle $q_1$ and, for each link, its angle relative to the link below ($q_2$ from upright for the first link). With the bar poses $R_i(q)$, centres $p_i(q)$, masses $m_i$ and principal inertias $J_i$ the kinetic and potential energies are

$$T = \tfrac12 J_r \dot q_1^2 + \sum_i \tfrac12 m_i |\dot p_i|^2 + \tfrac12 \omega_i^T J_i \omega_i, \qquad V = \sum_i m_i g\, p_{i,z},$$

with $\hat\omega_i = R_i^T \dot R_i$ and the arm-axis inertia of the drive $J_r = n^2 J_m - L_m n^2 k_t^2 / R_m^2 = 1.807e-03$ kg·m² (the second term is the winding, see below). Lagrange's equations give the manipulator form

$$M(q)\,\ddot q = \frac{\partial T}{\partial q} - \dot M\,\dot q - \frac{\partial V}{\partial q} + Q, \qquad Q = \begin{pmatrix} \tau_m - b_{load} \dot q_1 \\ -b_j \dot q_2 \\ \vdots \end{pmatrix}.$$

The servo delivers at the arm axis

$$\tau_m = \frac{n k_t}{R_m} \left(u - n k_t \dot q_1\right)$$

with $u$ the clamped voltage ([Ctrl/u](signal:Ctrl/u)). `design/triple_lib.py` builds $M$ and the right-hand side with CasADi from these energies; the simulation solves $M \ddot q = \dots$ numerically, the trajectory optimisation keeps it as an implicit constraint.

## Design model against the bond graph

Released from rest at $q = [0.25, 2.4, -0.9, 0.6]$ rad with the motor terminals at 0 V, the Lagrangian model and the bond graph (model `pendulum-triple-rotary-free`) stay within **0.011 mrad** over 2 s (arm 0.001 mrad, links 0.009, 0.011, 0.009 mrad). The remaining difference is what the design model neglects: the joint compliance ($10^8$) and the gear elasticity.

**The winding.** The design model has no current state. The winding lag $\tau_e = L_m/R_m$ = 0.14 ms delays the back-EMF torque $-c_e \dot q_1$, $c_e = n^2 k_t^2/R_m$ = 0.647 N·m·s/rad; to first order in $\tau_e$ that is $-c_e \dot q_1 + c_e \tau_e \ddot q_1$, an inertia of $-c_e \tau_e$ = -8.93e-05 kg·m² at the arm axis (1.5 % of the arm), which is the second term of $J_r$. Without it the free swing differed by 1.5 mrad over the same 2 s: the winding was by far the largest mismatch, larger than the joint compliance and the gear.

![Free swing, design against bond graph|700](assets/3e5e2f67f26a.png)
