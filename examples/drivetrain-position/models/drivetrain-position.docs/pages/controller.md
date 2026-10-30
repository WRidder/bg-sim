# Controller design

[Ctrl](block:Ctrl) is one `@discrete Ts = 1e-3` block (`library/PositionController.jl`); `design/design.py` writes its gains between the `GAINS` markers. Every tick it does four things.

## 1. Smooth trajectory

A change of the command [Ref](block:Ref) starts a **septic smoothstep** from the old to the new value over $T = 0.8$ s:

$$r(t) = r_0 + (r_1 - r_0)\,s(\tau),\quad s = 35\tau^4 - 84\tau^5 + 70\tau^6 - 20\tau^7,\quad \tau = t/T,$$

with zero velocity, acceleration and jerk at both ends. A raw step has energy at every frequency, including 3.9 Hz; the smoothstep has almost none above $1/T$ = 1.25 Hz, so the command does not excite the mode, and the feedback is left with errors and disturbances. A first-order or critically damped linear prefilter would also do, but its derivatives are not exact, and the feedforward below needs $\dot r$, $\ddot r$ and $\dddot r$ in closed form. The trajectory is the output [Ctrl/r_traj](signal:Ctrl/r_traj).

## 2. Observer

A steady-state Kalman filter on $\hat x = (\theta_m, \omega_m, \theta_L, \omega_L, T_{load})$ (the load torque is a random walk, $Q = 3\cdot10^{-8}$ (N·m)² per sample) updates with **both encoders**,

$$\hat x \leftarrow \hat x + L_m\,(y_m - \hat\theta_m) + L_l\,(y_l - \hat\theta_L), \qquad \hat x \leftarrow \Phi\,\hat x + B_d\,u,$$

with the noise of the encoder quantization, $R_n = \operatorname{diag}\big((2\pi/4096)^2/12,\ (2\pi/16384)^2/12\big)$.

*Why the load encoder?* The load angle is the controlled variable, and the soft shaft decouples it from the motor: with the motor encoder alone, the load angle is only a model output, and a slow load torque ($T/k$ = 0.17 rad of twist) and a slow motion of the load look alike. The 14-bit load encoder resolves that, at the price of one cheap sensor (dual-loop servo practice). The 12-bit motor encoder gives the fast, collocated signal that the damping needs. The observer poles are at $-167$, $-88$, $-47 \pm 82j$ and $-14$ rad/s. Its load torque estimate [Ctrl/T_hat](signal:Ctrl/T_hat) and angle estimate [Ctrl/theta_L_hat](signal:Ctrl/theta_L_hat) are outputs.

## 3. Feedforward by model inversion

For the trajectory, the shaft has to carry $\tau_r = J_2\ddot r + c J_2\dddot r/k + \hat T_{load}$. From that the firmware computes the twist $\delta_r = \tau_r/k$, the motor speed $\omega_{m,r} = n(\dot r + J_2\dddot r/k)$, the motor torque $J_{eq}n\ddot r + R_d\omega_{m,r} + \tau_r/n$ and the voltage

$$u_{ff} = \frac{R}{k_t}\big(J_{eq}\,n\,\ddot r + R_d\,\omega_{m,r} + \tau_r/n\big) + k_t\,\omega_{m,r}.$$

The estimated load torque is part of $\tau_r$, so a torque step is answered at once and the integrator only trims.

## 4. LQR with integral action

The feedback acts on the error of $(\delta,\ \omega_m,\ \omega_L,\ \theta_L)$ against the reference above and on the integral $z = \int(\hat\theta_L - r)\,dt$:

$$v = u_{ff} - K\,(\delta - \delta_r,\ \hat\omega_m - \omega_{m,r},\ \hat\omega_L - \dot r,\ \hat\theta_L - r,\ z), \qquad u = \operatorname{clamp}(v, -24, 24).$$

If $\lvert v\rvert > 24$ the integration of $z$ in that tick is undone (anti-windup). $K$ is the discrete LQR (ZOH at 1 ms, quasi-static electrics) with Bryson weights $q_i = 1/\sigma_i^2$ and $R = 1/24^2$:

| state | $\sigma$ | gain in $K$ |
| --- | --- | --- |
| twist $\delta$ | 0.15 rad | 399 V/rad |
| motor speed error | 100 rad/s | 0.211 V·s/rad |
| load speed error | 0.5 rad/s | 42.9 V·s/rad |
| load position error | 0.05 rad | 458 V/rad |
| integral $z$ | 0.03 rad·s | 647 V/(rad·s) |

The LQR sees the twist and both speeds, so it **damps the shaft mode by feedback**: the closed-loop poles are $-427$, $-9.9$, $-1.7$ rad/s and a pair $-78 \pm 71j$ (16.8 Hz, $\zeta = 0.74$) where the plant had the 3.9 Hz pair with $\zeta = 0.034$. The slow poles belong to the integrator.

Since the observer sits in the loop, the quantization noise of the encoders reaches the voltage: $K_{\omega_L}$ is the largest cause. That is why the load speed weight is moderate (the voltage has a ripple of 1.3 V peak to peak at rest, 5 % of the supply). A faster design is possible, and this one is a balance between speed, noise and the margin to the limit.
