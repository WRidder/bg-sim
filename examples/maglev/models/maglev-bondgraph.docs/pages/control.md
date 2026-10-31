# Cascade controller and IR sensor

## Inner current loop

[Ipi](block:Ipi) (project block `CurrentPI`) turns the current setpoint into the amplifier voltage. The coil seen from the amplifier is $R + s L_0$ with $L_0 = L(0.15)$ = 30.33 mH. A PI whose zero cancels the coil pole,

$$C_i(s) = K_{p,i}\,\frac{1 + s T_i}{s T_i}, \qquad T_i = \frac{L_0}{R} = 15.2\ \mathrm{ms}, \quad K_{p,i} = L_0\,\omega_i = 30.33\ \mathrm{V/A},$$

makes the current loop a first-order lag $1/(s/\omega_i + 1)$ with $\omega_i$ = 1000 rad/s, twenty times the outer crossover. The PI integrator is preloaded with the trim voltage (26.67 V) and has back-calculation anti-windup against the ±60 V rail of [Sat](block:Sat). The inductance changes with the gap (30.33 mH at 0.15 m, 30.26 mH at 0.1875 m, 30.20 … 30.99 mH over 0.05 … 0.25 m), which moves $\omega_i$ by at most 2.6 %.

## IR sensor

The [IR](block:IR) subsystem models the measurement chain:

| block | what it does |
| --- | --- |
| `IR/Zero`, `IR/Gain` | the sensor is zeroed at 0.15 m and gives 30 V/m |
| `IR/Noise`, `IR/Add` | white noise, 0.3 mV rms (10 µm of gap), a new sample every 1 ms, seed 7 |
| `IR/ADC` | 16-bit ADC over −5 … +5 V at 1 kHz (one step = 5.1 µm of gap), held between samples |
| `IR/Scale`, `IR/Back` | back to metres |

## Outer position loop

The outer loop is the current-driven design with two changes forced by the sensor:

1. **Derivative filter $T_f$ = 5 ms** instead of 1 ms. With 1 ms the derivative gain at high frequency, $K_d/T_f \approx 33\,000$ A/m, turns the 10 µm noise and the 5 µm ADC steps into about 0.3 A of current noise, and the inner loop turns that into a voltage that jumps from rail to rail. With 5 ms the amplifier noise drops to about 2 V rms.
2. **The extra phase lag in the budget.** The sample-and-hold delays the measurement by half a sample, $\omega_c T/2$ = 1.4° at 50 rad/s, and the current loop adds $\arctan(\omega_c/\omega_i)$ = 2.9°. Both, plus the slower filter, go into the same closed-form design as in the current-driven model (`maglev-current-driven`, *Controller design*): $2\arctan(\omega_c/z) = \mathrm{PM} + 90^\circ + \arctan(\omega_c T_f) + 4.3^\circ$.

| $p$ [m] | $K_p$ [A/m] | $K_i$ [A/(m s)] | $K_d$ [A s/m] | crossover / PM of the sampled loop |
| --- | --- | --- | --- | --- |
| 0.05 | 135.02 | 349.39 | 12.709 | 57.2 rad/s / 58.9° |
| 0.15 | 368.43 | 953.36 | 34.679 | 52.4 rad/s / 59.7° |
| 0.25 | 601.83 | 1557.34 | 56.650 | 51.4 rad/s / 59.8° |

The double zero moves down to $z$ = 5.1 rad/s, so the integral action is slower: the last 20 µm of the step settle with a time constant of a few tenths of a second. The trim feedforward [Trim](block:Trim) and the gain tables [KpTab](block:KpTab), [KiTab](block:KiTab), [KdTab](block:KdTab) use the measured gap `IR/Back/y`.
