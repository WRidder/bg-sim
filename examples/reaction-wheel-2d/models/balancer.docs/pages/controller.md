# Controller

[Ctrl](block:Ctrl) (project library `Balancer`, 1 ms) computes

$$e = \theta - \mathrm{ref}, \qquad \tau = \operatorname{clamp}\big(G\sin\theta + K_p\,e + K_d\,\dot\theta,\ -1.5,\ 1.5\big).$$

$G\sin\theta$ is the gravity torque about the pivot, so the settled angle equals the reference (no droop) and the closed loop is $J_A'\,\ddot\theta = -K_p\,e - K_d\,\dot\theta$, stable for any positive gains. With $K_p = 16$ N·m/rad and $K_d = 4$ N·m·s/rad: $\omega_n = \sqrt{K_p/J_A'} \approx 7.9$ rad/s, damping ratio about 1.0, and $\lvert\tau\rvert \le 1.5$ N·m.
