# LQR controller

[LQR1](block:LQR1) (`library/LQR.jl`) is the state feedback

$$u = \operatorname{clamp}\!\big(-(K_x\,(x - x_{ref}) + K_v\,v + K_\theta\,\theta + K_\omega\,\omega),\ -20,\ 20\big),$$

with $x_{ref}$ from [XRef](block:XRef), a step from 0 to 0.2 m at $t = 1.5$ s. It runs in a `@discrete Ts = 1e-3` scope: each 1 ms tick samples $x, v, \theta, \omega$ and holds the force until the next tick (the declared 0 N start is held for the first millisecond).

## Design

`design/design.py` linearises the plant at upright with the state $(x, v, \theta, \omega)$,

$$A = \begin{pmatrix} 0 & 1 & 0 & 0 \\ 0 & -b/M & -m g/M & 0 \\ 0 & 0 & 0 & 1 \\ 0 & b/(Ml) & (M+m)g/(Ml) & 0 \end{pmatrix}, \qquad B = \begin{pmatrix} 0 \\ 1/M \\ 0 \\ -1/(Ml) \end{pmatrix},$$

solves the continuous algebraic Riccati equation $A^T P + P A - P B R^{-1} B^T P + Q = 0$ and sets $K = R^{-1} B^T P$. The open-loop eigenvalues are $0$, $-0.083$, $-4.86$ and $+4.84$ s$^{-1}$ (one unstable pole).

The weights follow the normalisation $q_i = 1/\sigma_i^2$:

| state | scale $\sigma$ | weight | why |
| --- | --- | --- | --- |
| $x$ | 1.1 cm | $q_x = 8\cdot10^3$ | the cart position is the slow, weakly actuated mode, so it carries the largest weight |
| $v$ | 1 m/s | $q_v = 1$ | |
| $\theta$ | 0.1 rad | $q_\theta = 100$ | the force couples to the angle directly through $-1/(Ml)$, so it is cheap to control |
| $\omega$ | 0.32 rad/s | $q_\omega = 10$ | damps the angle rate |
| $u$ | 1 N | $R = 1$ | |

The result, written into the four `K_*` parameters of `LQR1`:

$$K = (-89.442719,\ -54.686555,\ -175.121631,\ -39.152990),$$

with closed-loop poles $-7.17 \pm 5.45\mathrm{j}$, $-5.28$ and $-4.10$. The force demand is 17.512 N at the initial tilt and peaks at 17.865 N at the reference step at 1.5 s, so the 20 N clamp stays inactive in the nominal run (about 10 % margin).

To recompute the gains: `uv run examples/inverted-pendulum-cart/design/design.py` (it rewrites the `K_*` values in the model file).
