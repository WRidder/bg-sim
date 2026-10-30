# Discrete LQR design

[LQR1](block:LQR1) (`library/LQR.jl`) applies

$$u_k = \operatorname{clamp}\!\big(-(K_\theta\,\theta + K_{\dot\theta}\,\dot\theta + K_w\,\omega_{rel}),\ -12,\ 12\big)$$

in a `@discrete Ts = 2e-3` scope: it samples the state at each tick and holds $u$ until the next one (the declared 0 V output is held before the first tick at $t = T_s$).

## Design (`design/design.py`)

With $x = (\theta, \dot\theta, \omega_{rel})$, $a = m g l$ and the winding inductance neglected in the design ($L/R = 0.1$ ms is 20 times shorter than $T_s$; the non-linear check in the script keeps it):

$$A = \begin{pmatrix} 0 & 1 & 0 \\ a/J & 0 & k^2/(R J) \\ -a/J & 0 & -\frac{k^2}{R}\left(\frac{1}{J_w} + \frac{1}{J}\right) \end{pmatrix}, \qquad B = \begin{pmatrix} 0 \\ -k/(R J) \\ \frac{k}{R}\left(\frac{1}{J_w} + \frac{1}{J}\right) \end{pmatrix}.$$

$(A, B)$ is discretised exactly with a zero-order hold at $T_s = 2$ ms; the discrete Riccati equation gives $K = (R + B_d^T P B_d)^{-1} B_d^T P A_d$ for $u_k = -K x_k$.

Weights with the normalisation $q_i = 1/\sigma_i^2$:

| state / input | scale $\sigma$ | weight |
| --- | --- | --- |
| $\theta$ | 0.02 rad | $q = 2500$ |
| $\dot\theta$ | 0.2 rad/s | $q = 25$ |
| $\omega_{rel}$ | 10 rad/s | $q = 0.01$ |
| $u$ | 12 V | $r = 1/144$ |

Result written into `K_theta`, `K_thetadot`, `K_wheel` of `LQR1`:

$$K = (-446.597400,\ -43.875365,\ -0.762835)\ \text{(V/rad, V s/rad, V s/rad)}.$$

Discrete closed-loop poles 0.3762, 0.9802, 0.9967, i.e. $-488.8$, $-10.0$, $-1.65$ s$^{-1}$ continuous equivalents. The unclamped demand at the initial tilt is 22.3 V, so the 12 V clamp is active for the first three samples and never again: after 0.1 s the voltage stays below 0.083 V.

Re-run `uv run examples/reaction-wheel-1d/design/design.py` after changing a weight; it writes the new gains into `LQR1`.
