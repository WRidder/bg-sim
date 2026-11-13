# Controller design

The averaged control-to-output plant at the nominal load is

$$G_{vd}(s) = \frac{V_{in}}{1 + R_L/R + s\left(\frac{L}{R} + R_L C\right) + s^2 L C},$$

with $V_{in}=12$ V, $L=470$ $\mu$H, $C=470$ $\mu$F, $R_L=0.1$ $\Omega$ and $R=5$ $\Omega$. The LC double pole is at $f_0 = 1/(2\pi\sqrt{LC}) = 339$ Hz, with $Q = R\sqrt{C/L} = 5$ for the lossless filter and $Q \approx 3.4$ with $R_L$. Above $f_0$ the plant phase approaches $-180^\circ$, so a PI controller cannot stabilise it with margin; the derivative term supplies the phase.

## The PID block is not in textbook form

The stdlib `PID` block is

$$u = K_p e + \frac{K_p}{T_i}\xi + N(e-x_d),\qquad \dot\xi = \frac{e}{T_i} + \frac{y-u}{\sqrt{T_i T_d}},\qquad \dot x_d = (e-x_d)\frac{N}{T_d},$$

clamped to $\pm1$, which is

$$C(s) = K_p + \frac{K_p/T_i^2}{s} + \frac{T_d\, s}{1 + s\,T_d/N}.$$

The gains the loop actually has:

| term | parameter | effective value |
| --- | --- | --- |
| proportional | $K_p = 0.2$ | 0.2 per V |
| integral | $T_i = 0.04472$ s | $K_p/T_i^2 = 100$ s$^{-1}$ (the design passes $T_i=\sqrt{K_p/K_i}$) |
| derivative | $T_d = 0.2$ ms | derivative gain $T_d$ itself, 0.2 ms, not $K_p T_d$ (the textbook $T_d$ would be 1 ms) |
| derivative filter | $N = 5$ | time constant $T_d/N = 40$ $\mu$s, corner 3.98 kHz |
| high-frequency gain | | $K_p + N = 5.2$ |

The loop crosses over at **1.72 kHz with 65° phase margin** (12 V, 5 $\Omega$). The derivative path, not $K_p$, sets the crossover: at 1.7 kHz the derivative term has a gain of about 2, ten times $K_p$. From `design/design.py`, with the integral gain scaling with $K_p$ as it does in the block:

| change | crossover | phase margin |
| --- | --- | --- |
| nominal | 1716 Hz | 65.0° |
| $K_p$ 0.4 / 0.05 | 1779 / 1675 Hz | 59.6 / 69.4° |
| $T_d$ 0.4 / 0.1 ms | 2363 / 1021 Hz | 40.7 / 71.9° |
| $N$ 10 / 2.5 | 1784 / 1547 Hz | 75.7 / 50.4° |

$T_d$ moves the crossover; $N$ moves the derivative corner and with it mainly the phase margin.

## Feed-forward and set-point filter

The feed-forward $d_{ff}=V_{ref}/V_{in}$ supplies the steady duty and lets the PID correct only the error; this is why the startup follows the filtered reference to the 1 % band in 4.3 ms, without overshoot and without integrator wind-up. The set-point filter `VrefFilt` (1 ms) turns the 5 V step into a ramp, so the derivative sees a bounded slope instead of an impulse. It does not remove the kick: the derivative acts on the error, and the duty still jumps to 0.71 within the first 65 $\mu$s.

Run `uv run examples/buck-converter/design/design.py` to print the LC corner, the margins, the averaged reference and the steady state at 15 V / 2 A, and `design/build_model.py` to rewrite the models from `design.json`.
