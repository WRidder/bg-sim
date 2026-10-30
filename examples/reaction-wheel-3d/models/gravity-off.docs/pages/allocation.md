# Allocation and momentum balance

## Allocation with a null space

A motor torque $\tau_k$ on wheel $k$ puts $-\tau_k a_k$ on the body, so the body torque is $T = -A\,\tau$. The firmware solves the desired torque with the minimum-norm solution plus a free null-space component:

$$\tau = -A^{+}\,T_{des} + \lambda\,n, \qquad A^{+} = A^T (A A^T)^{-1}, \qquad n = \tfrac12\,(1, -1, 1, -1)^T, \qquad A\,n = 0.$$

Three orthogonal wheels have an empty null space; the four-wheel pyramid has a one-dimensional one, which is what makes wheel-speed bias and momentum management possible without touching the body. The tap [Tap](block:Tap) reads the **measured** motor torques `Drv_k.tau_m`, not the firmware's intent:

| output | meaning |
| --- | --- |
| [Tap/Tbx](signal:Tap/Tbx), `Tbz`, `Tby` | $-A\tau$: the torque the four motors really put on the body |
| [Tap/nsp](signal:Tap/nsp) | $n\cdot\tau$: the null-space component (here $\lambda = 0.01$ N·m) |
| `Tap/ntau`, `Tap/proj` | $\lvert\tau\rvert^2$ and $\lvert A^{+}A\tau\rvert^2$, the part that reaches the body |
| `Tap/resid` | `ntau` $-$ `proj` $-$ `nsp`$^2$, identically 0 (range orthogonal to null) |
| `Alloc/nsp`, `Alloc/Tbx`... | the same two quantities from the firmware side |

The null component is visible in the wheel speeds (a constant $\lambda$ drives the pyramid mode $(1, -1, 1, -1)$ at $\lambda/(2 J_w) = 2.5$ rad/s²) and never in the body torque.

## Measurement (not plant physics)

[MeasBody](block:MeasBody) gets a body's momentum $P = [J\omega;\ m v]$ and world pose $g$ and gives, about the world origin (the pivot), the angular momentum, the gravity torque and its integral:

$$H = R\,P_{ang} + p \times (R\,P_{lin}), \qquad \tau_g = p \times (0, 0, -m g_0), \qquad I_g = \int \tau_g\,dt .$$

Summed over the five bodies:

- gravity off: $H_{total}(t)$ is constant;
- gravity on: $H_{total}(t) - I_{g,total}(t)$ is constant, i.e. $\dot H = \tau_{gravity}$.

## Why four wheels, and why the elastic shaft

Four wheels instead of the work-package's three orthogonal ones give the null-space tap something to show (and prepare X-MB5). The drive reaches the joint through an `ElasticShaft` with a tiny rotor inertia: the rotor is relative to the joint, not an inertial body, and a rigid rotor would give W201. The rotor's own momentum (at most $J_m\omega = 2.5\cdot10^{-7}$ kg·m²/s) is the only thing the world $H$ leaves out.
