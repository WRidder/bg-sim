# Controller

[XRef](block:XRef) is a step from 0 to 0.1 m at $t = 0.1$ s. [Err](block:Err) is a two-input inline block $e = x_{ref} - x$ (the stdlib `Sum` takes one vector input). [PID1](block:PID1) is a `DiscretePID` at $T_s = 1\ \mathrm{ms}$, `method` 1 (backward), output clamped to $[-1, 1]$:

| parameter | value |
| --- | --- |
| `Kp` | 14 spool/m |
| `Ti` | 20 s, so $K_i = K_p/T_i = 0.7$ spool/(m·s) |
| `Td` | 0 (a PI: the 1 ms difference of a sampled position is too noisy, the valve characteristic already damps) |
| `lower`, `upper` | -1, +1 |

$$I_k = I_{k-1} + T_s e_k, \qquad s_k = \operatorname{clamp}\!\Big(K_p e_k + \frac{K_p}{T_i} I_k,\ -1,\ 1\Big),$$

with the block's anti-windup (the increment is taken back when the output saturates). The valve is saturated while the error exceeds $1/K_p = 71$ mm.

## Initial condition

Starting both chambers at the 1 bar tank pressure leaves the closed-centre valve (leakage only) unable to hold the 50 kg rod against the area difference: the rod runs away, the cap pressure falls through the tank pressure and the orifice sign switches chatter (W206 at the event limit). The model therefore starts at the valve's **no-load equilibrium**:

- `Cyl` starts at $p_A = 3.36667\cdot10^{6}$ Pa (33.667 bar) and $p_B = 6.73333\cdot10^{6}$ Pa (67.333 bar), the solution of $p_A A_p = p_B A_r$ and of the two leakage flow balances with the trim spool $s_0 = -4.25\cdot10^{-5}$;
- the PID integrator is preloaded with $I_0 = s_0 T_i/K_p = -6.07\cdot10^{-5}$ error-seconds, so the first tick already commands the trim.

This is a bumpless-start condition of the controller, not a change of the plant.
