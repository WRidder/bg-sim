# Results

![Gap, coil current and amplifier voltage|900](assets/61e05458dcb7.png)

| quantity | bgsim, noisy sensor | bgsim, ideal sensor | scipy design (continuous, no noise) |
| --- | --- | --- | --- |
| rise time 10–90 % | 0.1641 s | 0.1642 s | 0.1650 s |
| overshoot | 0.12 % | 0.13 % | 0.14 % |
| settling time (2 % band) | 0.286 s | 0.286 s | 0.287 s |
| gap error at 1.4 s | 2.16·10⁻⁵ m | 2.24·10⁻⁵ m | 2.20·10⁻⁵ m |
| coil current, min | 2.43 A | 2.43 A | 2.62 A |
| amplifier voltage | −34 … +60 V (rail) | −35 … +60 V (rail) | −35 … +35 V |

The ideal-sensor run is the same model with `IR/Noise/std` = 0 and a 52-bit ADC (run-parameter overrides, as the dashboard uses them); it is still sampled at 1 kHz. The sample-and-hold explains the small differences to the continuous scipy design. It also explains the voltage. While the ball moves at about 0.2 m/s, the held measurement climbs in 0.2 mm stairs, and every stair kicks the derivative term by $K_d\,\Delta h/T_f \approx$ 1.4 A. The 1000 rad/s current loop turns these kicks into voltage spikes, which touch the +60 V rail for 41 ms in total between 0.23 and 0.34 s. The continuous design stays within ±35 V. The anti-windup of [Ipi](block:Ipi) keeps the rail from upsetting the current loop.

## Energy

![Stored energy and the integrated port powers|900](assets/ac05baff84aa.png)

$W - E_{el} - E_{mech}$ stays at $W(0)$ = 2.69605 J to 6.2·10⁻⁹ J. Most of the electrical energy that flows in is stored (the field energy rises with $i^2$ as the ball moves down); the mechanical port takes only 7 mJ.

## Statics

Run for 6 s with the ideal sensor, the loop comes fully to rest at 0.1875 m with

| quantity | value | expected |
| --- | --- | --- |
| [EM/i](signal:EM/i) / [EM/h](signal:EM/h) | 88.8881058457 A/m | $c = \sqrt{m g/\alpha}$ = 88.8881058456 A/m |
| [EM/F](signal:EM/F) | 0.1962 N | $m g$ = 0.1962 N |

the same statics as the current-driven model.

## Noise

![Measured and true gap, amplifier voltage, before the step|900](assets/9165a0377cb2.png)

Before the step the true gap moves by 2.9 µm rms, the current by 44 mA rms and the amplifier voltage by 2 V rms. The noise sequence is seeded, so every run repeats exactly.

## Checks

`expected.json` checks this model twice (noisy and ideal sensor): the step bounds, the energy invariant (10⁻⁷ of $W(0)$), $W(0)$, the ±60 V rail, a positive current, $EM/h$ = $BallPos/y$ and $EM/F$ = $Fmag/y$, the statics above to 10⁻⁶, no W201/W202/E106/W206, and the cascade against the current-driven model (within 3 mm over the whole run).
