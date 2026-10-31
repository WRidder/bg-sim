# Results

![Gap, current and scheduled gain|900](assets/e07716032809.png)

| quantity | bgsim | scipy design (`design.json`) |
| --- | --- | --- |
| rise time 10–90 % | 0.1671 s | 0.1671 s |
| overshoot | 0 % | 0 % |
| settling time (2 % band), from the step | 0.4085 s | 0.4086 s |
| gap at 1.4 s | 0.187498994108 m | 0.187498994108 m |
| current, min / max | 1.1846 / 18.4099 A | 1.1824 / 18.4099 A |
| contact force [Ball/F_c](signal:Ball/F_c) | 0 (always levitated) | – |

The scipy simulation (`design/design.py`) integrates the same closed loop independently; the gap at 1.4 s agrees to 2·10⁻¹⁴ m. [Ball/h](signal:Ball/h) follows [Pre/y](signal:Pre/y) more slowly than [Ideal/y](signal:Ideal/y) at first (the loop crosses at about 50 rad/s, but the slow PID zero at 12 rad/s leaves a tail), then settles within 0.41 s.

## Statics

The [Statics](block:Statics) subsystem holds three balls at 0.05, 0.15 and 0.25 m with the scheduled PID but **no** feedforward; the integrators start at 98 % of the trim value. At 1.4 s the currents are

| gap | [Statics/PID05/u](signal:Statics/PID05/u), … | $c\,p$ | relative difference |
| --- | --- | --- | --- |
| 0.05 m | 4.44440527 A | 4.44440529 A | 5·10⁻⁹ |
| 0.15 m | 13.33321588 A | 13.33321588 A | 9·10⁻¹² |
| 0.25 m | 22.22202644 A | 22.22202646 A | 8·10⁻¹⁰ |

![The integrators find the trim currents|900](assets/cf39d4e2170d.png)

The checks in `expected.json` require 10⁻⁶.
