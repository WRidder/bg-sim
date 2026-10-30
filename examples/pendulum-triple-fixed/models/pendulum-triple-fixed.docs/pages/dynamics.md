# Equations of motion

With $q = (q_1, \dots, q_3)$ the joint angles, link $k$ has the absolute angle $\theta_k = \sum_{j \le k} q_j$, its centre of mass at $c_k = p_k + \ell_k (\cos\theta_k, \sin\theta_k)$ and the next pivot at $p_{k+1} = p_k + L_k (\cos\theta_k, \sin\theta_k)$. The kinetic and potential energy are

$$T = \sum_k \tfrac12 m_k \lVert \dot c_k \rVert^2 + \tfrac12 J_k \dot\theta_k^2 + \tfrac12 N^2 J_m \dot q_1^2, \qquad V = \sum_k m_k g\, c_{k,y},$$

and the Lagrange equations give

$$M(q)\,\ddot q + c(q, \dot q) + g(q) = \tau, \qquad \tau_1 = N k_t\, i - b_1 \dot q_1, \quad \tau_k = -b_k \dot q_k \ (k \ge 2).$$

The motor current follows $L\,\dot i = u - R_w\, i - N k_t\, \dot q_1$. The design neglects $L$ for the optimisation and the LQR ($L/R_w = 0.20$ ms), so $i = (u - N k_t \dot q_1)/R_w$ and the input enters through

$$\tau_1 = \frac{N k_t}{R_w}\,u - \frac{N^2 k_t^2}{R_w}\,\dot q_1 - b_1 \dot q_1 ,$$

a torque proportional to the voltage and a back-EMF damping. The sampled-data simulation in `design.py` that predicts the whole run keeps the winding inductance.

## Parameters

The values are assumed (no datasheet part); the links are aluminium rods with the centre of mass at the middle.

| link | $m$ [kg] | $L$ [m] | $\ell$ [m] | $J = m L^2/12$ [kg·m²] | $b$ [N·m·s/rad] |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.22 | 0.26 | 0.13 | 0.00123933 | 0.002 |
| 2 | 0.14 | 0.3 | 0.15 | 0.00105 | 0.0008 |
| 3 | 0.1 | 0.34 | 0.17 | 0.000963333 | 0.0006 |

Motor and drive: $R_w = 2.5\ \Omega$, $L = 0.5$ mH, $k_t = 0.03$ N·m/A, $J_m = 5e-06$ kg·m², gear ratio $N = 5$, supply limit $\pm 12$ V (stall torque at the joint $N k_t U/R_w = 0.72$ N·m). Gravity $g = 9.81$ m/s².

## Linearisation at upright

With the state $x = (q_1 - \pi/2, q_2, \dots, \dot q_1, \dots)$ the open-loop poles at upright are $-17.57, -9.41, -4.20, 4.13, 8.78, 15.40$ s$^{-1}$: 3 unstable poles (up to 15.4 s$^{-1}$). Because only joint 1 is driven, the passive links are stabilised through the dynamic coupling.

## Check against the bond graph

`models/free.bgmodel.json` is the same plant with the motor terminals at 0 V, started at the non-trivial angles $-0.3708, 0.8000, -0.6000$ rad. `design.py --compare` integrates the design ODE (the full model with the winding current, Radau, tolerance $10^{-11}$) from the same start and compares it with the bond-graph run: the maximum difference of any joint angle over the 3 s swing is **8.45e-06 rad**, and `expected.json` repeats the comparison at six times. ![Free swing of the bond graph|800](assets/f8496cedbdb1.png)

The swing covers a large part of the working range, so this proves the masses, inertias, lengths, gravity, the reflected rotor inertia and the back-EMF damping of the design model.
