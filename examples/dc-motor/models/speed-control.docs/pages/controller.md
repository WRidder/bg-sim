# The discrete PID

[PID1](block:PID1) runs at the sample period $T_s = 1\ \mathrm{ms}$ (a constant of the block) with the parameters

| parameter | value |
| --- | --- |
| `method` | 1 (backward Euler for the integral) |
| `Kp` | 0.28 V/(rad/s) |
| `Ti` | 0.01 s (so $K_i = K_p/T_i = 28$ V/(rad/s·s)) |
| `Td` | 0 (a PI; differencing the 1 ms speed samples would be noisy) |
| `lower`, `upper` | -24 V, +24 V |

At every tick, with error $u_k$, the block updates

$$I_k = I_{k-1} + T_s\,u_k, \qquad v_k = K_p\,u_k + \frac{K_p}{T_i}\,I_k + K_p T_d\,\frac{u_k - u_{k-1}}{T_s}, \qquad y_k = \operatorname{clamp}(v_k, -24, 24).$$

**Anti-windup.** If $v_k$ would leave the limits, the increment of this tick is taken back out of the integral ($I_k \leftarrow I_k - T_s u_k$) and $v_k$ is recomputed, so the integral does not wind up while the voltage saturates.
