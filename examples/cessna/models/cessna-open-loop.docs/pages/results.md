# Results

![Longitudinal modes|900](assets/cf12f43fcd68.png)

![Lateral modes and the mode rates|900](assets/026e338bd7bb.png)

| mode | scipy (linearised) | bg-sim (fitted on the nonlinear run) |
| --- | --- | --- |
| short period | $\zeta$ 0.604, $\omega_n$ 5.96 rad/s | 0.602, 5.97 |
| phugoid | $\zeta$ 0.085, period 24.9 s | 0.085, $\omega_n$ 0.2535 |
| dutch roll | $\zeta$ 0.183, $\omega_n$ 2.16 rad/s | 0.183, 2.158 |
| roll | $-5.57$ 1/s | [RateRo/lambda](signal:RateRo/lambda) $-5.573$ at 0.3 s |
| spiral | $-0.0107$ 1/s | [RateSl/lambda](signal:RateSl/lambda) $-0.0107$ at 0 s |

The damping fits fit a damped sinusoid to the signal (the run-check kind `damping`). The curves agree with the nonlinear scipy run to between 1e-8 and 1e-12 at every checked instant.

The spiral's rate wanders between $-0.008$ and $-0.011$ 1/s after the start (over 120 s). The 5 deg bank also excites the phugoid, which modulates the speed and so the spiral's rate.
