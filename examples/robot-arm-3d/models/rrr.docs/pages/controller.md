# Drives and controller

[Ctrl](block:Ctrl) (`ArmCtrl3R`, $T_s = 1$ ms) samples $q$, $\dot q$ and the three references and computes the joint torque command and the motor voltage:

$$t_{c,i} = K_{p,i}\,(\mathrm{ref}_i - q_i) + K_{d,i}\,(\dot r_i - \dot q_i) + \frac{\partial V}{\partial q_i}(q), \qquad \dot r_i = \frac{\mathrm{ref}_i - \mathrm{ref}_i^{prev}}{T_s},$$

$$u_i = \operatorname{clamp}\!\Big(\frac{R\,t_{c,i}}{n\,k_t} + n\,k_t\,\dot q_i,\ -48,\ 48\Big).$$

$\partial V/\partial q$ is the plant's gravity term evaluated at the measured $q$ (a code block, not a copy of the arm), so a settled arm sits exactly on its reference. The motors ([Motor1](block:Motor1) to `Motor3`) have $R = 1\ \Omega$, $L = 0.5$ mH, $k_t = 0.1$ N·m/A, $J_m = 10^{-5}$ kg·m² (reflected inertia $n^2 J_m = 0.025$ kg·m² per joint) behind [Gear1](block:Gear1) to `Gear3` ($n = 50$). The gains come from `design/design.py`: critical damping of the decoupled joint at the largest effective inertia $M_{ii} + n^2 J_m$ over the workspace, $\omega_n = 20$ rad/s:

| joint | 1 | 2 | 3 |
| --- | --- | --- | --- |
| $K_p$ (N·m/rad) | 354 | 334 | 46 |
| $K_d$ (N·m·s/rad) | 35.4 | 33.4 | 4.6 |

$t_{c,i}$ is also an output of the block, which the torque-source models use. The references are `TimeTable`s (linear interpolation, 50 ms sample time) of two minimum-jerk moves $q(t) = q_0 + (q_1 - q_0)(10 s^3 - 15 s^4 + 6 s^5)$: from $(0, 0.6, -0.9)$ to $(1.2, 1.0, -0.4)$ over 0.2 to 1.2 s, and then to $(-0.6, 0.3, -1.3)$ over 1.8 to 3.0 s. `design/design.py` generates the tables and also integrates a numpy RK4 **replica of the whole sampled closed loop** (plant, motor electrics, gears, controller) that the checks compare the Julia run with. `design/build_models.py` writes the model documents.
