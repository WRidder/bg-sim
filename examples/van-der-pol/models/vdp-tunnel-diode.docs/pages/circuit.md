# Circuit and scaling to the Van der Pol form

## The diode

A tunnel diode's static curve rises to a peak $(V_p, I_p)$, falls to a valley $(V_v, I_v)$ and rises again. The DC supply biases it in the middle of the falling branch, at $V_0 = (V_p + V_v)/2$. About that point the curve is fitted by an odd cubic in the voltage deviation $v$:

$$i_D(v) = -a\,v + b\,v^3 .$$

Its maximum and minimum fall on the real peak and valley when

$$A = \tfrac12 (V_v - V_p), \qquad a = \frac{3 (I_p - I_v)}{4 A}, \qquad b = \frac{a}{3 A^2}.$$

With a germanium diode of the 4.7 mA class (rounded values: peak 4.7 mA at 65 mV, valley 0.6 mA at 355 mV):

| quantity | value |
| --- | --- |
| bias point $V_0$, $I_0$ | 210 mV, 2.65 mA |
| amplitude scale $A$ | 145 mV |
| negative conductance $a$ | 21.207 mS (the diode is $-1/a = -47.15\ \Omega$ at the bias point) |
| cubic coefficient $b$ | 0.33622 A/V³ |

The cubic is the classic simplification. The real curve departs from it beyond the valley and in reverse. The bond graph models the AC deviations only. The bias source and the DC current through the inductor are not part of it.

## The bond graph

All elements share the voltage $v$, so they hang on one 0-junction. The capacitor is a C element and the inductor an I element. Both are in integral causality. The diode is a nonlinear R in conductance causality: the capacitor sets the voltage and the diode answers with a current. Its library block declares `@causality p => :flow_out` for this. The junction's flow balance and the two stores give

$$C \dot v = -i_L + a v - b v^3, \qquad L \dot i_L = v .$$

## Scaling

Differentiate the first equation and use the second:

$$\ddot v - \frac{1}{C}\,(a - 3 b v^2)\,\dot v + \frac{v}{L C} = 0 .$$

With $\omega_0 = 1/\sqrt{L C}$, $\tau = \omega_0 t$ and $v = A x$, where $A = \sqrt{a/(3b)}$:

$$x'' - \mu\,(1 - x^2)\,x' + x = 0, \qquad \mu = \frac{a}{\omega_0 C} = a\sqrt{\frac{L}{C}} .$$

So $\mu$ is the diode's negative conductance times the tank's characteristic impedance $Z_0 = \sqrt{L/C}$. For a fixed diode and resonance, the dashboard's mu slider changes $Z_0 = \mu/a$, and $L = Z_0/\omega_0$, $C = 1/(Z_0\omega_0)$ follow:

| $\mu$ | $Z_0$ | $L$ | $C$ | frequency |
| --- | --- | --- | --- | --- |
| 0.2 | 9.43 Ω | 150.10 nH | 1687.6 pF | 9.9751 MHz |
| 1 (default) | 47.15 Ω | 750.49 nH | 337.52 pF | 9.4296 MHz |
| 5 | 235.77 Ω | 3752.4 nH | 67.50 pF | 5.4108 MHz |

The tank resonance is $f_0$ = 10 MHz. The oscillation runs at $f_0 \cdot 2\pi/T(\mu)$, where $T(\mu)$ is the textbook period in $\tau$.

The scaled velocity is the capacitor current: $x' = \dot v/(\omega_0 A) = i_C/(\omega_0 C A)$. [Yc](block:Yc) computes it from the detector [Ic](block:Ic).

## Start

The run starts at $v(0) = A x_0$ with the inductor current equal to the diode current, $i_L(0) = a v_0 - b v_0^3$. The capacitor current is then 0, so the circuit starts at $(x, x') = (x_0, 0)$, exactly like [Ref](block:Ref).

## Energy

The tank stores $E = C v^2/2 + L i_L^2/2$ and loses exactly what the diode absorbs:

$$\dot E = -P_D, \qquad P_D = v\,i_D = -a A^2 \left(x^2 - \tfrac13 x^4\right).$$

The diode supplies energy ($P_D < 0$) while $|v| < \sqrt{a/b} = \sqrt3 A$ = 251 mV and dissipates it beyond. On the limit cycle the two parts cancel over each cycle. [Split](block:Split) integrates them separately.
