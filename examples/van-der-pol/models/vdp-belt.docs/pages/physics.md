# Physics and scaling

## Friction curve

On the belt the slip is $w = v_b - \dot x > 0$. The friction force on the block is the Gaussian Stribeck curve plus viscous friction:

$$F(w) = F_n\left(\mu_c + (\mu_s - \mu_c)\,e^{-(w/v_s)^2}\right) + \sigma w .$$

| quantity | value |
| --- | --- |
| block mass $m$, spring $k$ | 1 kg, 100 N/m ($\omega_0$ = 10 rad/s, 1.59 Hz) |
| normal force $F_n$ | 40 N (the block's weight and a spring-loaded pressure pad) |
| $\mu_s$, $\mu_c$, $v_s$ | 0.45, 0.30, 0.1 m/s |
| belt speed $v_b = v_s/\sqrt2$ | 70.71 mm/s, the inflection point of the Gaussian drop |
| Stribeck slope $\alpha_f = -\,dF_{Stribeck}/dw$ at $v_b$ | 51.466 N s/m |
| viscous coefficient $\sigma = \alpha_f - \alpha$ | 46.466 N s/m |
| net falling slope $\alpha = \mu\sqrt{k m}$ | 5 N s/m |
| cubic coefficient $\beta = F'''(v_b)/6$ | 3431.06 N s³/m³ |
| $F_0 = F(v_b)$, $x_s = F_0/k$ | 18.925 N, 189.25 mm |

## Rayleigh, then Van der Pol

At an inflection point the Taylor series has no quadratic term. With $w - v_b = -\dot x$:

$$F = F_0 + \alpha\,\dot x - \beta\,\dot x^3 .$$

Newton's law for the block, with $y = x - x_s$, is **Rayleigh's equation**:

$$m\ddot y - \alpha\,\dot y + \beta\,\dot y^3 + k y = 0 .$$

Differentiate it and write $z = \dot y$: $m\ddot z - (\alpha - 3\beta z^2)\,\dot z + k z = 0$. This is Van der Pol in the **velocity**. With $\omega_0 = \sqrt{k/m}$, $\tau = \omega_0 t$ and $z = V x$, where $V = \sqrt{\alpha/(3\beta)}$:

$$x'' - \mu\,(1 - x^2)\,x' + x = 0, \qquad \mu = \frac{\alpha}{\sqrt{k m}} = 0.5, \qquad V = 22.04\ \mathrm{mm/s}.$$

The scaled rate is $x' = \ddot x_{block}/(\omega_0 V) = (F - k x)/(m\omega_0 V)$. [Ym](block:Ym) computes it from the force detector and the position sensor.

## Why the viscous term is needed

$V^2 = \alpha/(3\beta)$ and $v_b^2 = \alpha_f/(3\beta)$ give $V/v_b = \sqrt{\alpha/\alpha_f}$. The velocity swing is about $2V$. Without viscous friction ($\alpha = \alpha_f$) it would be $2 v_b$, so the slip would reach zero and the block would stick: that is stick-slip, a different relaxation oscillation. The viscous term keeps $\alpha/\alpha_f$ = 0.097, a swing of 62 % of the belt speed. A belt-driven oscillator is Van der Pol only near the onset of instability. The passive system, with $\sigma$ alone, would be overdamped ($\zeta$ = 2.3).

## Energy

The oscillation energy about the force balance, $E = m\dot x^2/2 + k(x - x_s)^2/2$, changes by $\dot E = (F - F_0)\,\dot x = (\alpha\dot x^2 - \beta\dot x^4)$. [Split](block:Split) integrates $-(F - F_0)\dot x$, the power the contact takes out of the oscillation. The contact feeds the oscillation while $|\dot x| < \sqrt3 V$ and takes energy back above that. The energy the belt drive dissipates in the slip, $F w$, is far larger and always positive. Only the variation of $F$ with the block's velocity matters for the oscillation.
