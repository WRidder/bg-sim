# Controller: PD with gravity feedforward

[Ctrl](block:Ctrl) (project library `ArmPD`, `@discrete Ts = 1e-3`) samples the two joint angles and rates and holds the torque until the next tick:

$$e_i = \mathrm{ref}_i - q_i, \qquad u_i = \operatorname{clamp}\big(K_{p,i}\,e_i - K_{d,i}\,\dot q_i + G_i,\ -u_{i,max},\ u_{i,max}\big),$$

$$G_1 = g_0\big(m_1 l_{c1}\cos q_1 + m_2\,(L_1\cos q_1 + l_{c2}\cos(q_1 + q_2))\big), \qquad G_2 = g_0\,m_2\,l_{c2}\cos(q_1 + q_2).$$

| parameter | joint 1 | joint 2 |
| --- | --- | --- |
| $K_p$ (N·m/rad) | 250 | 30 |
| $K_d$ (N·m·s/rad) | 26 | 3 |
| torque limit (N·m) | 30 | 10 |

$G$ is the gravity torque about each joint at the sampled configuration, so the settled error is zero instead of the PD droop $G/K_p$. The derivative acts on the measurement, so the reference step produces no derivative kick; `clamp` inside `@discrete` is generated code, not a symbolic `ifelse`, so the torque limit creates no event. The gains give a closed-loop bandwidth of about 3 Hz with both modes near critical damping.
