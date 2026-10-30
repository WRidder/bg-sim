# TVLQR and LQR

## Time-varying LQR along the swing-up

Linearising the design model along the trajectory gives $A(t) = \partial_z f$, $B(t) = \partial_V f$ at $(z^*(t), V^*(t))$. The backward Riccati equation

$$-\dot P = Q + A^{\top} P + P A - P B R^{-1} B^{\top} P, \qquad P(T_s) = P_{\mathrm{LQR}}$$

with the terminal condition of the infinite-horizon problem gives the gain $K(t) = R^{-1} B^{\top} P(t)$ and the control law

$$V = V^*(t) - K(t)\, \bigl( z - z^*(t) \bigr), \qquad t \in [t_{\mathrm{on}},\, t_{\mathrm{on}} + T_s],$$

clamped to ±24 V. The gains are stored with the trajectory in [Traj](block:Traj) (10 ms knots). Because $K(T_s) = K_{\mathrm{LQR}}$ the hand-over to the balance controller is smooth.

![The time-varying LQR gains along the swing-up|900](assets/3b8d841497c9.png)

## Balance LQR

At $\tau = t - t_{\mathrm{on}} \ge T_s$ the firmware latches phase 2 and applies $V = -K_{\mathrm{lqr}}\, z$, the **discrete** infinite-horizon LQR of the linearisation at the upright, sampled with a zero-order hold at 1 ms (`scipy.linalg.solve_discrete_are`). The weights are

$$Q = \mathrm{diag}(300, 400, 400, 400, 10, 8, 8, 8), \qquad R = 3\ \mathrm{V}^{-2}$$

on $[x, \theta_1 \ldots \theta_3, \dot x, \dot\theta_1 \ldots \dot\theta_3]$. The cart position and velocity are weighted heavily: this is what widens the basin of attraction against a pulse (in the design study, light cart weights lost the pendulum to much smaller pulses). The largest gain is 440 V per rad or per m.

## The switching rule and the phase signal

The mode is latched in the firmware (a discrete variable that only increases):

| mode | condition | law |
| --- | --- | --- |
| 0 | $t < t_{\mathrm{on}}$ | $V = 0$ |
| 1 | $t_{\mathrm{on}} \le t < t_{\mathrm{on}} + T_s$ | feed-forward plus TVLQR |
| 2 | $t \ge t_{\mathrm{on}} + T_s$ | discrete LQR, until the end |

[Ctrl/phase](signal:Ctrl/phase) records the mode. The catch is time-based, not state-based: the nominal trajectory ends upright at rest, the TVLQR has driven the error to a few $10^{-4}$ rad by then, so the switch is bumpless. Every output is clamped to ±24 V inside the firmware (`clamp` in `@discrete` is generated code, not an event).
