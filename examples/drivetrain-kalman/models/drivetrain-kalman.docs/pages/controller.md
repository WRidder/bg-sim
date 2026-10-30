# LQG controller

[LQG](block:LQG) is one `@discrete Ts = 1e-3` block (`library/LQGController.jl`). Its state estimate is

$$\hat x = (\theta_m,\ \omega_m,\ \theta_L,\ \omega_L,\ T_{load}),$$

the plan's four states plus the load torque. At every tick the block executes

$$\hat x \leftarrow \hat x + L\,(y - C_d\hat x), \qquad z \leftarrow z + T_s\,(w_{ref} - \hat\omega_L),$$

$$v = -K\hat x + K_i\,z + K_{ff}\,w_{ref}, \qquad u = \operatorname{clamp}(v,\ -u_{max},\ u_{max}), \qquad \hat x \leftarrow \Phi\,\hat x + B_d\,u,$$

where $y$ is the quantised encoder angle and `w_load_hat` is $\hat\omega_L$. If $\lvert v\rvert > u_{max}$ the integration of $z$ in that tick is undone (anti-windup). The matrices are written by `design/design.py`:

| parameter | value |
| --- | --- |
| `Phi` | 5x5 zero-order-hold model at 1 ms |
| `Bd` | (7.88e-4, 1.53, 2.6e-7, 9.3e-4, 0) |
| `Cd` | (1, 0, 0, 0, 0) |
| `L` | (0.214, 25.71, 0.0803, 0.9596, -2.002) |
| `K` | (176.25, 0.3955, -1762.5, 11.99, 0) |
| `Ki` | 223.31 |
| `Kff` | 16.95 V/(rad/s) |
| `umax` | 24 V |

(The discrete matrix is called `Phi` because `Ad` is the library's adjoint builtin.)

## Two deviations from the plan's literal code

1. **The reference is fed forward.** The plan's $v = -K\hat x + K_i z$ has no reference term, so at 10 rad/s its own state feedback would ask for more than 150 V. $K_{ff} = n K_2 + K_4 + k_t n$ cancels the speed feedback at the reference point and adds the back-EMF $k_t n\,w_{ref}$; the integral then only trims the load torque (the measured steady voltage is 10.5 to 10.7 V).
2. **The Kalman filter has five states.** A four-state filter keeps a steady bias of about 1.3 rad/s in $\omega_L$ while the load acts (the model cannot tell a load torque from a voltage offset). The fifth state is a random walk with $Q_n = 10^{-6}$ (N·m)² per sample, so the 0.5 N·m step is learned in a few tens of ms.

## Design (`design/design.py`)

The design linearises a 4-state model (quasi-static electrics, one lumped rod spring of 50 N·m/rad, the motor damping), discretises it with ZOH at 1 ms, solves an LQR with integral action and the steady-state Kalman filter, writes the matrices into both model documents and integrates the sampled closed loop against a 9-state reference (three-segment rod and the 1 mH electrics, RK4 at 2e-5) to print the acceptance values.

It designs in the relative coordinates $(\delta, \omega_m, \omega_L, z)$ with $\delta = \theta_m/n - \theta_L$ and $\dot z = w_{ref} - \omega_L$: in absolute angles the integral augmentation is not controllable ($z = w_{ref}t - \theta_L$ is a linear combination of the states). The gain maps back with $K = (k_\delta/n,\ k_{\omega_m},\ -k_\delta,\ k_{\omega_L})$ and $K_i = -k_z$.

Weights with $Q_{ii} = 1/\sigma_i^2$, $R = 1/\sigma_u^2$:

| state | $\sigma$ | weight |
| --- | --- | --- |
| rod twist $\delta$ | 0.32 rad | $q = 10$ |
| motor speed error $\omega_m - n\,w_{ref}$ | 100 rad/s | $q = 10^{-4}$ |
| load speed error $\omega_L - w_{ref}$ | 1 rad/s | $q = 1$ |
| integral $z$ | 0.07 rad | $q = 200$ |
| voltage | 24 V | $R = 1/576$ |

The twist is deliberately cheap: a stiff loop would fight the 25 Hz rod mode; $q_z = 200$ sets $K_i$ and the 0.3 s load recovery. The Kalman filter uses the encoder quantisation noise $R_n = (2\pi/4096)^2/12 = 1.96\cdot10^{-7}$ rad² and the torque random walk above (the four plant states carry a $10^{-12}$ numerical floor). The Riccati equations are solved by a Newton-Kleinman iteration from a stabilising seed because `scipy.linalg.solve_discrete_are` returns the anti-stabilising root with the pure integrator.
