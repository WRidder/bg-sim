# Controller: current, speed and position loops

The cascade is tuned inner to outer; `design/design.py` computes and writes all gains into the five model documents.

| loop | block | rate | law | gains |
| --- | --- | --- | --- | --- |
| current | [CurLoop](block:CurLoop) | 8 kHz (`sample_period` 125 µs) | PI on $i_d$, $i_q$, dq decoupling, back-EMF feedforward, vector voltage limit | $K_p = L\,\omega_{ci} = 18.85$ V/A, $K_i = R\,\omega_{ci} = 1570.8$ V/(A·s), $\omega_{ci} = 2\pi\cdot500$ |
| speed | [SpeedLoop](block:SpeedLoop) | 1 kHz | PI on the speed error, output $i_q$ limited to $\pm15$ A | $K_p = J\,\omega_{cs}/k_t = 0.4608$ A/(rad/s), $K_i = 46.32$, zero at $\omega_{cs}/5$, $\omega_{cs} = 2\pi\cdot80$ |
| position | [PosLoop](block:PosLoop) | 200 Hz (5 ms) | P on the position error, speed limit $\pm200$ rad/s | $K_p = 20$ 1/s |

The current PI cancels the electrical pole ($K_i/K_p = R/L$); the speed PI places its zero at one fifth of the 80 Hz crossover. A one-sample `UnitDelay` at 8 kHz ([Udd](block:Udd), [Udq](block:Udq)) sits between the current loop and the inverter in every variant. [RefSpeed](block:RefSpeed) steps to 100 rad/s at 0.05 s; [Mode](block:Mode) switches the position loop on at 0.15 s with [PosRef](block:PosRef) = 0.

$$K_p^{(c)} = L\,\omega_{ci},\quad K_i^{(c)} = R\,\omega_{ci}, \qquad K_p^{(s)} = \frac{J\,\omega_{cs}}{k_t},\quad K_i^{(s)} = K_p^{(s)}\,\frac{\omega_{cs}}{5}.$$

**Why these values.** 500 Hz is a comfortable 16 samples per period at the 8 kHz current sample with the one-sample delay. The speed crossover of 80 Hz is a decade below the 303.5 Hz coupling resonance (see the `two-mass` model). A position gain of 20 1/s gives a 50 ms time constant; the 200 rad/s limit bounds the move and the 15 A limit bounds the acceleration.

At 0.05 s the 100 rad/s error saturates $i_q$ at 15 A: this is the current-loop step used by the acceptance. At 0.15 s the accumulated position (about 9.5 rad) is put on the position loop, and the 0.9 s load step tests the speed integrator's load rejection.
