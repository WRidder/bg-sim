# Circuit and equations

## Parameters

Both subsystems use the same values:

| quantity | iconic | bond graph | value |
| --- | --- | --- | --- |
| resistance | `R1.R` | `R1.r` | 10 Ω |
| inductance | `L1.L` | `IL.i` | 10 mH |
| capacitance | `C1.C` | `C1.c` | 100 µF |
| source | `Step1` 0 to 1 at $t = 0$ s, through `V1` | `Se1.e` = 1 V constant | 1 V |

The run lasts 0.01 s on 20000 output points (`solver = auto`, `reltol` 1e-10, `abstol` 1e-12). Both start from $v_C = 0$, $i_L = 0$.

## Bond graph

The source $S_e$ drives the 1-junction (common current $i$); on the junction the efforts add up to zero. $R$ dissipates, the $I$ element (inductor) and the $C$ element (capacitor) store energy, both in integral causality:

$$L \frac{di}{dt} = V - R\,i - v_C, \qquad C \frac{dv_C}{dt} = i .$$

The iconic circuit gives the same two equations from Kirchhoff's laws, so one intermediate IR serves both and the results agree to round-off.

## Second-order step response

$$\omega_0 = \frac{1}{\sqrt{L C}} = 1000\ \mathrm{rad/s}, \qquad \zeta = \frac{R}{2}\sqrt{\frac{C}{L}} = 0.5, \qquad \omega_d = \omega_0\sqrt{1 - \zeta^2} = 866\ \mathrm{rad/s}.$$

The capacitor voltage after a 1 V step is

$$v_C(t) = 1 - e^{-\zeta\omega_0 t}\left[\cos(\omega_d t) + \frac{\zeta}{\sqrt{1-\zeta^2}} \sin(\omega_d t)\right].$$

It peaks at $t = \pi/\omega_d = 3.6276$ ms with

$$v_{peak} = 1 + \exp\!\left(-\frac{\pi\zeta}{\sqrt{1-\zeta^2}}\right) = 1.16303353482\ \mathrm{V},$$

a 16.303 % overshoot.
