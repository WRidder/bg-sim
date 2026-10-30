# Controller: minimum-jerk reference with PD and gravity feedforward

[Ctrl](block:Ctrl) is the discrete code block `library/ArmPD6.jl` (D28). With $t_0 = 0.1$ s and $T_m = 0.8$ s:

$$\tau = \operatorname{clamp}\!\Big(\frac{t - t_0}{T_m},\,0,\,1\Big), \qquad s = \tau^3\,(10 - 15\tau + 6\tau^2),$$

$$q_{r,i} = q_{h,i} + (q_{t,i} - q_{h,i})\,s, \qquad \dot q_{r,i} = (q_{t,i} - q_{h,i})\,\frac{30\,\tau^2 (1 - \tau)^2}{T_m},$$

$$u_i = \operatorname{clamp}\big(K_{p,i}\,(q_{r,i} - q_i) + K_{d,i}\,(\dot q_{r,i} - \dot q_i) + G_i(q),\ -u_{max,i},\ u_{max,i}\big).$$

The firmware samples the six angles and rates (and the clock) every 1 ms and holds the torques (zero-order hold, so no algebraic loop closes through the plant). **The gravity feedforward is computed inside the controller from the same geometry as the plant**: the forward kinematics of the standard-DH chain is unrolled in the block (generated code, no arrays) and

$$G_i = g_0 \sum_{j \ge i} m_j\; z_i \cdot \big((w_j - o_i) \times e_z\big),$$

the torque that holds the arm static. It agrees with the independent Newton-Euler gravity torque of J-MB10 to 7e-15 N·m at four test poses, so the settled error is zero instead of the PD droop $G/K_p$. The gains come from the largest mass-matrix diagonal entry $M_{ii}$ over five poses between home and target: $K_{p,i} = M_{ii}\,\omega_n^2$, $K_{d,i} = 2\,M_{ii}\,\omega_n$ (critical damping of the decoupled joint) with $\omega_n = 10, 10, 12, 20, 20, 20$ rad/s:

| joint | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| $K_p$ (N·m/rad) | 274 | 331 | 107 | 6.23 | 1.5 | 0.2 |
| $K_d$ (N·m·s/rad) | 54.9 | 66.2 | 17.9 | 0.623 | 0.15 | 0.02 |
| limit (N·m) | 150 | 150 | 150 | 28 | 28 | 28 |

The target is $q = (0.8, -0.8, 0.9, -1.9, -1.2, 0.6)$. There is no inertia feedforward, so the tracking error during the move is about $M\ddot q / K_p$.
