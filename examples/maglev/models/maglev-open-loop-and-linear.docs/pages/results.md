# Results

## The unstable pole

![Released balls and their growth rate|900](assets/bf42f34c01cd.png)

The growth rate is read at $t = 7/\sqrt{a_0}$, where $\tanh = 1 - 1.7\cdot10^{-6}$ and the deviation is still only 5.5 µm:

| $p$ | $t$ | [Grow05/lambda](signal:Grow05/lambda) … at $t$ | scipy, same equation | $\sqrt{2g/p}$ |
| --- | --- | --- | --- | --- |
| 0.05 m | 0.353 s | 19.807977 1/s | 19.807977 1/s | 19.809089 1/s |
| 0.15 m | 0.612 s | 11.436555 1/s | 11.436555 1/s | 11.436783 1/s |
| 0.25 m | 0.790 s | 8.858782 1/s | 8.858782 1/s | 8.858894 1/s |

bgsim and scipy agree to 10⁻¹¹ (relative). Both stay within 6·10⁻⁵ of the LPV pole; the remainder is the nonlinearity (the force is $1/h^2$, not linear in $h$), which grows as the ball leaves the trim point. After the growth phase the balls hit a stop: the 0.05 m ball falls onto the pedestal (0.3 m), the 0.25 m ball has not yet reached it at 1.5 s.

## Frozen linear vs nonlinear

![Small and large steps, nonlinear and linear|900](assets/bac406e3861d.png)

| | small step (+5 mm) | large step (+60 mm) |
| --- | --- | --- |
| max \|nonlinear − linear\| | 2.45·10⁻⁵ m = 0.49 % of the step | 1.057·10⁻² m = 17.6 % of the step |
| scipy | 0.49 % | 17.6 % |
| current, nonlinear / linear | 11.77 … 13.95 A / 11.78 … 13.94 A | −6.95 … 23.03 A / −5.36 … 20.65 A |

For a small step the frozen model is as good as the nonlinear one. For the large step two things break the approximation: the gain $b_0$ is 29 % smaller at 0.21 m than at 0.15 m, and the controller asks for a **negative** current. The linear model treats the negative current as a strong push downward. The real magnet cannot push: it pulls with $\alpha i^2/h^2$ whatever the sign, so at best the ball falls freely. The nonlinear ball therefore lags behind the linear one by up to 10.6 mm at 0.26 s, and then overshoots it by up to 5.2 mm while the current is high. That is the reason for scheduling the gains and for the trim feedforward on the measured gap.
