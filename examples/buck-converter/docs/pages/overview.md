# Buck converter: a PID voltage loop with feed-forward

A 12 V to 5 V synchronous buck at 20 kHz, modelled as a bond graph. The switch is an ideal, power-conserving modulated transformer (`MTF`) whose modulus is the duty $d$: the switch-node voltage is $d V_{in}$ and the input current is $d\, i_L$, so the model has an input power and an efficiency. The series branch is `I(L)` with its resistance, and the output is a `C` with the load resistor and a 1 A load-current step. The controller is the stdlib `PID` block on the filtered error, plus the duty feed-forward $d_{ff} = V_{ref}/V_{in}$. The same diagram runs with `PWMAverage` (the averaged plant) and with `PWM` at 20 kHz (the switched plant).

![Output, inductor and input current, and duty of the averaged model|900](assets/4883cb25beb6.png)

**Scope.** A synchronous converter in continuous conduction only: no diode (so no discontinuous conduction), no capacitor ESR and no switch on-resistance. The only loss is the inductor resistance $R_L = 0.1\ \Omega$; its drop $R_L I$ (0.2 V at 2 A) is why the steady duty at 15 V is $(5 + 0.2)/15 = 0.3467$.

## Why this example

The other power examples in the library (`rlc-dual`, `industrial-servo`) show passive networks and a motor drive; this is the first **switching converter with a closed voltage loop**. It is also the smallest plant where you can see the three things a converter controller must do: start without overshoot, reject a load step, and reject a line step.

## The two models

- [buck-averaged](model:buck-averaged) drives the switch with `PWMAverage`, so the carrier and its ripple disappear. The run is fast and matches the scipy reference in `design/design.py`, power balance included.
- [buck-switched](model:buck-switched) uses `PWM` at `f_sw` = 20 kHz. The edges are events, the inductor current is a triangle, the input current is a pulse train, and the run is the check that the averaged model is honest.

`L`, `C`, `R_load`, `V_ref` and `f_sw` are global parameters of both models (the averaged model has no carrier and ignores `f_sw`). The controller design is on [the controller page](page:control); the measured numbers and the acceptance checks are on [the results page](page:results).

## What to try

Each of these was run; the numbers are what the model gives.

- **Derivative gain `PID1.Td`**, the crossover knob: 0.4 ms shrinks the load-step dip to 4.855 V and recovers in 0.21 ms, but the inductor current peaks at 2.86 A and the duty reaches 0.96 (41° phase margin); 0.1 ms lets the dip grow to 4.751 V.
- **Derivative filter `PID1.N`**: 10 gives a dip of 4.837 V and a 76° margin; 2.5 lowers the derivative corner to 2 kHz and the dip grows to 4.791 V (50°).
- **`PID1.Kp`** barely matters: 0.4 gives a dip of 4.833 V, 0.05 gives 4.813 V and a slower recovery (1.45 ms instead of 0.58 ms). Neither changes the startup (4.3 to 4.6 ms to the 1 % band): the feed-forward and the 1 ms reference filter set it. `Td` cannot be 0 (the block's minimum is 1e-9 s).
- **`Vin` final value 18 V**: the feed-forward adapts (steady duty 5.2/18 = 0.289) and the output moves by at most 16 mV.
- **`LoadStep` final value 2 A**: the dip grows to 4.644 V, the duty saturates at 1 for a moment, and the inductor current settles at 3 A.
- **`f_sw` 10 kHz** in the switched model: the inductor ripple doubles to 0.72 A pp and the output ripple grows four-fold to 19.4 mV pp ($\Delta V \propto 1/f_{sw}^2$).
- To see the switching in the averaged model, replace `PWMAverage` by `PWM` **and set its `frequency` to `f_sw`**: `PWM` defaults to 1000 Hz. That is exactly the switched model.
