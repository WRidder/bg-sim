# Switched model

The switched model is the same diagram with [PWM](block:PWM) at `f_sw` = 20 kHz in place of `PWMAverage`. Every edge is an event of the variable-step solver, so the run has 14 001 rows instead of 10 005. The switch [SW](block:SW) is still ideal (an `MTF` that conserves power): there is no diode, no discontinuous conduction, no capacitor ESR and no switch on-resistance, so the point of the variant is the ripple, the pulsed input current and the event handling, not the device losses.

![Switched run|900](assets/9d6f918e0734.png)

![The last four carrier periods: the output ripple, the inductor triangle and the input-current pulses|900](assets/06add5a0ff1e.png)

At 15 V and 2 A the inductor current is a triangle from 1.819 A to 2.181 A, 0.3616 A pp on every recorded row, and the output ripple is 4.88 mV pp. The analytic values at that operating point are $\Delta I = V_{in} D(1-D)/(L f_{sw}) = 0.3614$ A and $\Delta V = \Delta I/(8 f_{sw} C) = 4.81$ mV with $D = 0.3467$. The time-weighted means are the averaged values: 5.000006 V and 2.000 A.

The input current [Iin](block:Iin) is the inductor current while the switch is on and zero while it is off. Its mean, from the inductor current integrated over the on-intervals, is 0.6934 A, and the mean input power is 10.401 W against 10.000 W out: the inductor loss is 0.401 W, 1.1 mW more than in the averaged model because of the ripple, and the efficiency is 96.14 %. A plain trapezoid over the rows of [Pin](block:Pin) gives 11.11 W instead, because each edge is recorded with the value of only one side.

`PWMAverage` is the right model for design and for long runs; use `PWM` to check the ripple, the pulsed input, the event count and the modulator.
