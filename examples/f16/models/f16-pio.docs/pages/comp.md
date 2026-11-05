# Rate-limit compensation

A plain rate limiter follows its command at the maximum rate until it catches up. When the command reverses, the output keeps going until the command crosses it: that delay is the phase lag of the limiter, and it grows with the amplitude. The compensated limiter

$$\dot y = \mathrm{clamp}\Big(\frac{du}{dt} + k (u - y),\; \pm 60\ \mathrm{deg/s}\Big)$$

reverses as soon as the command does (the derivative term, through a `FilteredDerivative` with $T_f$ = 0.01 s); the slow pull-back $k = 0.5$ 1/s brings the output back onto the command afterwards. It gives up some amplitude for much less phase lag, the idea behind the phase-compensated rate limiter Saab introduced in the Gripen's flight control after its PIO accidents.

![theta, stabilator rate and deflection|900](assets/1289aa85e126.png)

| attitude error, peak-to-peak | 2-4 s | 4-6 s | 6-8 s | 8-10 s |
| --- | --- | --- | --- | --- |
| Plain | 29 deg | 36 deg | 41 deg | 37 deg |
| Comp | 7.0 deg | 2.2 deg | 0.45 deg | 0.14 deg |

bg-sim matches the scipy reference within 0.1 deg in theta.
