# Results

![x(tau) at mu = 0.1, 1, 5 and 20|900](assets/94ee45359998.png)

At $\mu$ = 0.1 the amplitude takes about 60 time units to grow from 0.5 to 2: its rate is $\mu/2$. At $\mu$ = 5 and 20 the cycle is reached within one period, and the waveform is a square-ish relaxation wave.

![Phase portraits: the near-circle of radius 2 at small mu, the relaxation cycle at large mu|900](assets/28c20eca7f25.png)

## Checks (`expected.json`)

For each $\mu$:

| check | tolerance |
| --- | --- |
| block diagram against the equation block, $x$ and $x'$ | 1e-6 (scaled by the peak $x'$) |
| period of the last full cycle, from the zero crossings of $x$ | rtol 1e-6 against the scipy limit cycle |
| the cycle meter's period and amplitude at the end | rtol 1e-7 |
| the sampled peak of $x$ in the second half | 1e-4 |
| $x$ at $\tau$ = 200 against scipy from the same start | 1e-5 |
| $\mu \le 1$: period against $2\pi(1 + \mu^2/16)$, amplitude against 2 | twice the theory's own error |
| $\mu \ge 5$: period against the relaxation estimate | twice its error (4.8 % at 5, 0.5 % at 20) |
