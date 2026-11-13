# Results and checks

| quantity | averaged | switched |
| --- | --- | --- |
| output at 50 ms | 5.000000 V | time-weighted mean over [40, 50] ms 5.000006 V |
| startup (1 % band) | 4.32 ms, no overshoot | 4.38 ms |
| load-step dip at 20 ms | 4.8226 V | 4.8257 V (with the ripple) |
| recovery overshoot | 5.0124 V at 23.5 ms | 5.0133 V |
| line-step peak at 30 ms | 5.0093 V | 5.0194 V (with the ripple) |
| peak inductor current | 2.351 A at 0.245 ms (startup inrush) | 2.387 A |
| inductor current after the load step | peaks at 2.093 A at 20.28 ms | 2.240 A (with the ripple) |
| inductor current | 2.000 A | mean 2.000 A, 1.819 to 2.181 A |
| inductor ripple at 15 V / 2 A | 0 | 0.3616 A pp |
| output ripple at 15 V / 2 A | 0 | 4.88 mV pp |
| input current | 0.6933 A | mean 0.6934 A |
| input power | 10.400 W | mean 10.401 W |
| efficiency | 96.15 % | 96.14 % |

The load step is a 1 A current sink switched on at 20 ms; the line step is $V_{in}$ from 12 V to 15 V at 30 ms. The averaged model recovers from the load step in 0.58 ms (2 % band). The switched run has 14 001 output rows (the PWM edges add equal-time rows), the averaged run 10 005.

## Ripple

The check window [40, 50] ms is at 15 V and 2 A, where $D = (5 + 0.1\cdot2)/15 = 0.3467$, $\Delta I = V_{in} D(1-D)/(L f_{sw}) = 0.3614$ A pp and $\Delta V = \Delta I/(8 f_{sw} C) = 4.81$ mV pp. The switched run measures 0.3616 A and 4.88 mV on every recorded row. A uniform 5 $\mu$s grid would see only 0.332 A, because it samples the 20 kHz triangle at fixed phases and misses its corners.

## Power balance

The averaged model closes the balance to $2\cdot10^{-11}$ W over [40, 50] ms: $P_{in} = 10.400$ W $= P_{out}\ 10.000$ W $+ R_L i^2\ 0.400$ W, so $\eta = 10/10.4 = 96.15$ %. In the switched model $P_{in}$ is a pulse train ($V_{in} i_L$ while the switch is on, 0 while it is off). Its rows cannot be averaged with a trapezoid: an edge is recorded at one time with either the value before or the value after it, so the trapezoid smears the jump and gives 11.11 W. Integrating the inductor current over the on-intervals gives a mean input current of 0.6934 A and $P_{in} = 10.401$ W, against $P_{out}$ 10.000 W $+ R_L\langle i^2\rangle$ 0.401 W (the ripple adds $R_L \Delta I^2/12 = 1.1$ mW). The balance closes to 0.14 mW, and $\eta = 96.14$ % (analytic 96.144 %).

## Acceptance checks

`uv run examples/run_checks.py --only buck-converter` runs 33 checks:

- averaged: the output at 15 ms and 50 ms and its time-weighted mean over [40, 50] ms match `design.json` to 0.1 $\mu$V; the load-step minimum stays above 4.8225 V; the recovery peak is 5.01241 V; the inductor current peaks at 2.3511 A (startup) and 2.0932 A (load step) and ends at 2 A; the final duty is 0.34667, the input current 0.69333 A, the mean input power 10.4 W, the mean output power 10 W and $P_{out}/P_{in} = 0.961538$;
- switched: the time-weighted means of the output (5 V within 20 $\mu$V), the inductor current (2 A within 20 $\mu$A) and the output power (10 W within 0.1 mW); the inductor current peaks at $2 + \Delta I/2 = 2.1807$ A (within 1 mA) and stays above 1.818 A; the input current peaks at the same value; the dominant line of the inductor current is 20 kHz; the ripple on every row stays below 0.365 A and 5 mV pp; the load-step dip stays above 4.824 V. The averaged model fails the peak, input-current and 20 kHz checks, so they test the switching;
- the switched and averaged outputs agree within 3 mV over [40, 50] ms ($\Delta V/2 = 2.4$ mV);
- the saved plots and dashboard cards name recorded signals, the docs lint, and there is no solver failure, causality conflict, derivative causality, algebraic loop or event-limit stop.

The independent reference is `design/design.py`: it integrates the averaged ODE with the same PID, feed-forward, limits and both steps, and works out the ripple and the power balance at 15 V / 2 A.
