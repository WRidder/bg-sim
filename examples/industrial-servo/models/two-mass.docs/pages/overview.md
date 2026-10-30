# Servo with a flexible coupling and notch filter

The `baseline` drive with a flexible motor-to-load coupling and a notch in the speed feedback path. Everything else (plant equations, three loops, averaged inverter, ideal sensors) is unchanged; see the `baseline` model for the PMSM and the controller.

![The two-mass model canvas|900](assets/8c92a64665d8.png)

## What differs

`MJ -- TF(1) -> S0(0) <- TF(1) -- LJ` with a parallel spring and damper on a 1-junction `KJ`: [TFm](block:TFm), [S0](block:S0), [TFl](block:TFl), [KJ](block:KJ), [Kc](block:Kc), [Dc](block:Dc). The 0-junction forms the relative velocity $\omega_m - \omega_L$; the 1-junction gives spring and damper the same relative flow and **adds** their efforts, so the coupling torque is

$$T_c = k_c\,\Delta\theta + c_c\,(\omega_m - \omega_L).$$

(Putting both C and R on the 0-junction would be a series Maxwell element, which lets the load creep under a constant load.) The load is [LJ](block:LJ) with [Jl](block:Jl) = 4.4e-4 kg·m², [Bl](block:Bl) = 1e-4, the load speed sensor [WlSens](block:WlSens), and the load torque source on `LJ`. The coupling is $k_c = 800$ N·m/rad (the `Kc` compliance is 1/800 = 0.00125) and $c_c = 0.02$ N·m·s/rad ([Dc](block:Dc)). The undamped resonance is

$$f_r = \frac{1}{2\pi}\sqrt{k_c\left(\frac{1}{J_m} + \frac{1}{J_L}\right)} = \frac{1}{2\pi}\sqrt{800\cdot 2\cdot\frac{1}{4.4\cdot10^{-4}}} = 303.5\ \mathrm{Hz}.$$

The speed feedback passes through a second-order **notch at 303.5 Hz** ($Q = 4$, $f_s = 1$ kHz), the `DiscreteTF` [Notch](block:Notch) with $b = (0.8045, 0.5307, 0.8045)$ and $a = (1, 0.5307, 0.6090)$ (from `iirnotch`):

$$H(z) = \frac{0.8045 + 0.5307\,z^{-1} + 0.8045\,z^{-2}}{1 + 0.5307\,z^{-1} + 0.6090\,z^{-2}}.$$

## Results

![Motor and load speed ring at the coupling resonance, and the notch input and output|900](assets/e72bedfe54dd.png)

The motor and load speeds ring at 303.5 Hz after the speed step; the notch output [Notch/y](signal:Notch/y) has visibly less high-frequency content than its input [Notch/u](signal:Notch/u): the 250 Hz high-pass RMS drops from 1.099 to 0.827 (README; the load-side ringing is 1.181). The speed step has a rise / overshoot / settle of 11.1 ms / 6.0 % / 32 ms, the position step 107 ms / 0 % / 396 ms, the peak $i_q$ is 15.80 A (7.586 N·m).
