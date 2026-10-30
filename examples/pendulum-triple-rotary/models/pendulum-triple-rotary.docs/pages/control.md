# TVLQR and LQR

The [Ctrl](block:Ctrl) firmware runs at 1 kHz with a zero-order hold (`@discrete Ts = 1e-3`) and has three phases, recorded in [Ctrl/phase](signal:Ctrl/phase):

| phase | when | law |
| --- | --- | --- |
| 0 | $t < t_{on} = 1$ s | $u = 0$ (hanging at rest) |
| 1 | swing-up | $u = u^*(t) - K(t)\,(x - x^*(t))$, table interpolation, clamped to $\pm 15$ V |
| 2 | balance, latched | $u = -K_{lqr}\, x$, clamped to $\pm 15$ V |

**Discrete time-varying LQR.** The design model sampled at 1 kHz with a zero-order hold is $x_{k+1} = F(x_k, u_k)$ (RK4, two steps per sample). Along the nominal, $A_k = \partial F/\partial x$ and $B_k = \partial F/\partial u$ are the exact Jacobians of that step, and the discrete Riccati recursion runs backwards from the infinite-horizon cost-to-go:

$$K_k = (R + B_k^T P_{k+1} B_k)^{-1} B_k^T P_{k+1} A_k, \qquad P_k = Q + A_k^T P_{k+1} (A_k - B_k K_k), \qquad P_N = P_{lqr}.$$

The recursion is numerically stable for any weights (the continuous Riccati ODE of a fast, chaotic trajectory overflows). The collocation solution is first tracked once by the sampled model under its own TVLQR; that roll-out, consistent with the 1 kHz model, is the nominal $(x^*, u^*)$ of the table and the gains are recomputed along it. It ends 1.6e-04 from the upright. $Q = \mathrm{diag}(20, 200, 200, 200, 1, 5, 5, 5)$ (angles in rad, rates in rad/s), $R = 5$ V$^{-2}$.

**Infinite-horizon LQR** of the same sampled model at the upright, same weights: $K_{lqr}$ = (-1.89, 104.79, 11.17, 423.80, -6.09, 35.20, 32.97, 41.44); the TVLQR ends exactly in this gain. Equivalent closed-loop poles -131.4, -20.3, -20.3, -10.0, -10.0, -4.8, -4.1, -0.8 1/s.

**Catch.** Phase 2 starts once $t - t_{on} \ge T_s$ and the LQR cost-to-go $V = x^T P_{lqr}\, x$ ([Ctrl/vcost](signal:Ctrl/vcost)) is below 3e+04 (about 1.5 deg on the top link alone); it is latched. Because the last table row is the LQR gain at the upright, the switch is seamless. The catch happened at $t = 5.00$ s.

**Validation before the bond graph.** `design.py` runs the whole scenario with this firmware logic (1 kHz, table interpolation, clamp, catch) on the design model, and on six perturbed models (link masses ±3 %, link lengths +1 %, bearing friction ×3, motor $k_t$ −3 %, load friction ×1.5): all swing up, are caught at 5 s and recover the pulse.
