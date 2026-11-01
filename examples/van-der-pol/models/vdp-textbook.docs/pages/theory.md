# Amplitude and period

## Small mu: averaging

For $\mu \ll 1$ the motion is nearly $x = r\cos(\tau + \varphi)$, with a slowly varying amplitude. Averaging the energy balance over one cycle gives

$$\frac{dr}{d\tau} = \frac{\mu}{2}\,r\left(1 - \frac{r^2}{4}\right),$$

so the amplitude grows (or shrinks) to $r = 2$ at a rate $\mu/2$. Whatever the start, the limit cycle has amplitude 2. Second-order perturbation theory (Lindstedt-Poincaré) gives the period

$$T = 2\pi\left(1 + \frac{\mu^2}{16} - \frac{5\mu^4}{3072} + \dots\right).$$

## Large mu: relaxation oscillations

For $\mu \gg 1$, write the equation in Liénard form, $x' = \mu\,(w - (x^3/3 - x))$. The state creeps along the two outer branches of the cubic $w = x^3/3 - x$ (for $|x| > 1$). At the knees $x = \pm 1$ it jumps to the other branch in a time of order $1/\mu$. The creep from $x = 2$ to $x = 1$ takes $\mu\,(3/2 - \ln 2)$, so the leading period is $(3 - 2\ln 2)\,\mu$. The corrections from the jumps near the knees give (Dorodnitsyn)

$$T \approx (3 - 2\ln 2)\,\mu + 3 a\,\mu^{-1/3}, \qquad a = 2.33811 \ \text{(the first zero of } \mathrm{Ai}(-z)\text{)},$$

so $3a$ = 7.0143. The next terms are of order $\ln\mu/\mu$, so the estimate improves slowly with $\mu$.

| $\mu$ | limit-cycle period (scipy) | $2\pi(1 + \mu^2/16)$ | relaxation estimate | amplitude |
| --- | --- | --- | --- | --- |
| 0.1 | 6.28711127 | 6.287112 (+1.6e-7) | | 2.0001040 |
| 1 | 6.66328686 | 6.675884 (+0.19 %) | 8.628 | 2.0086199 |
| 5 | 11.61223067 | 16.10 | 12.1705 (+4.81 %) | 2.0215081 |
| 20 | 34.68232331 | 163.4 | 34.8582 (+0.51 %) | 2.0077900 |

The reference periods come from `design/design.py`. It solves the equation with scipy (DOP853, or Radau for $\mu \ge 5$, tolerance 1e-13) and finds the limit cycle by shooting on the section $x = 0$, $x' > 0$.
