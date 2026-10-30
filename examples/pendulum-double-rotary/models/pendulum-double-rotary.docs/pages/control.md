# TVLQR and LQR

The [Ctrl](block:Ctrl) firmware runs at 1 kHz with a zero-order hold (`@discrete Ts = 1e-3`) and has three phases, recorded in [Ctrl/phase](signal:Ctrl/phase):

| phase | when | law |
| --- | --- | --- |
| 0 | $t < t_{on} = 1$ s | $u = 0$ (hanging at rest) |
| 1 | swing-up | $u = u^*(t) - K(t)\,(x - x^*(t))$, table interpolation, clamped to $\pm 10$ V |
| 2 | balance, latched | $u = -K_{lqr}\, x$, clamped to $\pm 10$ V |

**Time-varying LQR.** Along the trajectory the model is linearised, $A(t) = \partial f/\partial x$, $B(t) = \partial f/\partial u$, and the Riccati differential equation

$$-\dot P = Q + A^T P + P A - P B R^{-1} B^T P, \qquad P(T_s) = P_{lqr}$$

is integrated backwards (RK4, 2 ms). $K(t) = R^{-1} B^T P(t)$. $Q = \mathrm{diag}(5, 200, 200, 1, 2, 2)$ (angles in rad, rates in rad/s) and $R = 0.2$ V$^{-2}$.

**Infinite-horizon LQR** at the upright with the same weights: $K_{lqr}$ = 5.00, -129.03, -266.11, 3.91, -34.37, -30.35.

**Catch.** Phase 2 starts once $t - t_{on} \ge T_s$ and the weighted norm $\sqrt{\sum c_i x_i^2} < 0.5$ ([Ctrl/enorm](signal:Ctrl/enorm)); it is latched. The catch happened at $t = 5.02$ s.

Controller and design model use the same linearisation: the gains come from `design/rotary_design.py`.
