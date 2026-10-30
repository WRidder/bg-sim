# The 1 kHz outer layer

## Trajectory ([Traj](block:Traj), `library/PandaTrajectory.jl`)

Waypoints of the flange (m): home (0.30689, 0, 0.59028) (the flange at the ready pose), (0.45, 0.20, 0.42), (0.45, -0.20, 0.42), (0.35, -0.12, 0.65), home. Segment $k$ starts at $t_0 + k\,(T_m + T_d)$ with $t_0 = 0.2$ s, $T_m = 0.9$ s, $T_d = 0.25$ s:

$$s = \tau^3 (10 - 15\tau + 6\tau^2), \qquad p = p_k + (p_{k+1} - p_k)\,s, \qquad \psi = \psi_k + (\psi_{k+1} - \psi_k)\,s.$$

The flange keeps its home orientation (pointing down) turned by $\psi$ about the vertical, with $\psi_k$ = atan2 of the waypoint (a slerp about $z$). With a fixed orientation the IK path asks up to 7 rad/s of the wrist; the slerp keeps every joint under 1.6 rad/s.

## Inverse kinematics ([IK](block:IK), `library/PandaIK.jl`)

The case-consistent geometric solver of He and Liu 2021 (`franka_analytical_ik`, Apache-2.0), re-derived for the flange, with $q_7$ held at $\pi/4$. Joint 4 comes from the triangle of joints 2, 4 and 6; joints 5 to 7 come from the wrist; joints 1 to 3 come from the shoulder. The branch (the sign of $q_2$ and the wrist case) is the one of the measured joint angles, so the solution stays on the branch the arm is on. If the target is out of reach or a joint limit is violated, the outputs keep the last valid solution and `flag` names the cause: 1 unreachable, 2 to 7 the limit of joint `flag - 1` (joints 1 to 6; $q_7$ is the fixed parameter).

## Joint controller ([PD](block:PD), `library/PandaPD.jl`)

$$\dot q_{r,i} = \frac{q_{r,i}(t_k) - q_{r,i}(t_{k-1})}{T_s},$$

$$u_i = \operatorname{clamp}\big(K_{p,i}(q_{r,i} - q_i) + K_{d,i}(\dot q_{r,i} - \dot q_i) + G_i(q) + \tau_{f,i}(\dot q_{r,i}),\ \pm u_{max,i}\big).$$

$G(q)$ is the Gaz gravity torque, unrolled in the block (generated code, equal to MuJoCo to 5e-14 N·m). $K_p = B\omega_n^2$ and $K_d = 2B\omega_n$, with $B$ the largest $M_{ii} + N^2 J_m$ along the path and $\omega_n$ = 15 rad/s (joints 1-4) or 20 rad/s (joints 5-7):

| joint | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $K_p$ (N·m/rad) | 320 | 522 | 356 | 296 | 51.5 | 53.0 | 42.0 |
| $K_d$ (N·m·s/rad) | 42.7 | 69.6 | 47.5 | 39.4 | 5.15 | 5.30 | 4.20 |
