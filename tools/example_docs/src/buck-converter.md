@@ figures @project
{
  "overview": {
    "kind": "plot", "model": "buck-averaged", "xlim": [0, 0.05],
    "rows": [
      {"ylabel": "output [V]", "series": [{"signal": "Vout/y", "label": "Vout/y"}, {"signal": "VrefFilt/y", "label": "Vref (filtered)", "style": "--"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "IL/y", "label": "IL/y"}, {"signal": "Iin/y", "label": "Iin/y"}], "legend": true},
      {"ylabel": "duty [-]", "series": [{"signal": "DutySat/y", "label": "DutySat/y"}], "hlines": [{"y": 1, "label": "1"}, {"y": 0}]}
    ]
  }
}
@@ page @project overview - | Buck converter
# Buck converter: a PID voltage loop with feed-forward

A 12 V to 5 V synchronous buck at 20 kHz, modelled as a bond graph. The switch is an ideal, power-conserving modulated transformer (`MTF`) whose modulus is the duty $d$: the switch-node voltage is $d V_{in}$ and the input current is $d\, i_L$, so the model has an input power and an efficiency. The series branch is `I(L)` with its resistance, and the output is a `C` with the load resistor and a 1 A load-current step. The controller is the stdlib `PID` block on the filtered error, plus the duty feed-forward $d_{ff} = V_{ref}/V_{in}$. The same diagram runs with `PWMAverage` (the averaged plant) and with `PWM` at 20 kHz (the switched plant).

![Output, inductor and input current, and duty of the averaged model|900](@fig:overview)

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
@@ page @project control overview | Controller design
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
@@ page @project results overview | Results and checks
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
@@ figures buck-averaged
{
  "diagram": {"kind": "diagram", "model": "buck-averaged"},
  "run": {
    "kind": "plot", "model": "buck-averaged", "xlim": [0, 0.05],
    "rows": [
      {"ylabel": "output [V]", "series": [{"signal": "Vout/y", "label": "Vout/y"}, {"signal": "VrefFilt/y", "label": "Vref (filtered)", "style": "--"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "IL/y", "label": "IL/y"}, {"signal": "Iin/y", "label": "Iin/y"}], "legend": true},
      {"ylabel": "power [W]", "series": [{"signal": "Pin/y", "label": "Pin/y"}, {"signal": "Pout/y", "label": "Pout/y"}], "legend": true},
      {"ylabel": "duty [-]", "series": [{"signal": "DutySat/y", "label": "DutySat/y"}]}
    ]
  }
}
@@ page buck-averaged overview - | Averaged model
# Averaged model

![The averaged model canvas|900](@fig:diagram)

The power stage is a bond graph. [Supply](block:Supply) (`MSe`) applies [Vin](block:Vin); the power sensor [Pin](block:Pin) reads the input power and the 1-junction [IN](block:IN) carries the input-current detector [Iin](block:Iin). The switch [SW](block:SW) is an `MTF` whose modulus is the duty from [PWM](block:PWM) (`PWMAverage` here): it passes $d V_{in}$ to the 1-junction [LJ](block:LJ) with [L](block:L), [RL](block:RL) and the current detector [IL](block:IL), and $d\, i_L$ back to the input. The 0-junction [OUT](block:OUT) carries [C](block:C) and the voltage detector [Vout](block:Vout); the 1-junction [IO](block:IO) with [Iout](block:Iout) leads to the load node [LOAD](block:LOAD) with [Rload](block:Rload) and the load step [Iload](block:Iload) (an `MSf` with gain $-1$, so it draws the [LoadStep](block:LoadStep) current). [Pout](block:Pout) multiplies the output voltage and current.

The control path is [Vref](block:Vref) → [VrefFilt](block:VrefFilt) → the error [Err](block:Err) → [PID1](block:PID1). The feed-forward [FF](block:FF) divides the filtered reference by [Vin](block:Vin); [DutySum](block:DutySum) adds the two and [DutySat](block:DutySat) clamps the result to [0, 1].

![Averaged run|900](@fig:run)

The output reaches the 1 % band in 4.3 ms without overshoot. At 20 ms the 1 A load step dips the output to 4.823 V; the inductor current peaks at 2.093 A at 20.28 ms, and the loop recovers in 0.58 ms (2 % band) with a 5.012 V overshoot at 23.5 ms. At 30 ms the input steps to 15 V; the feed-forward drops the duty at once and the output moves by less than 10 mV. The largest inductor current, 2.351 A, is the startup inrush at 0.245 ms, not the load step. The duty jumps to 0.71 in the first 65 $\mu$s: the derivative acts on the error, and the 1 ms reference filter only bounds that kick.

At 15 V and 2 A the input current is $d\, i_L = 0.6933$ A and the input power 10.400 W against 10.000 W out: the 0.400 W difference is $R_L i^2$, and the efficiency is 96.15 %.
@@ figures buck-switched
{
  "run": {
    "kind": "plot", "model": "buck-switched", "xlim": [0, 0.05],
    "rows": [
      {"ylabel": "output [V]", "series": [{"signal": "Vout/y", "label": "Vout/y"}, {"signal": "VrefFilt/y", "label": "Vref (filtered)", "style": "--"}], "legend": true},
      {"ylabel": "inductor [A]", "series": [{"signal": "IL/y", "label": "IL/y"}]},
      {"ylabel": "duty [-]", "series": [{"signal": "DutySat/y", "label": "DutySat/y"}]}
    ]
  },
  "zoom": {
    "kind": "plot", "model": "buck-switched", "xlim": [0.0498, 0.05],
    "rows": [
      {"ylabel": "output [V]", "series": [{"signal": "Vout/y", "label": "Vout/y"}]},
      {"ylabel": "current [A]", "series": [{"signal": "IL/y", "label": "IL/y"}, {"signal": "Iin/y", "label": "Iin/y"}], "legend": true}
    ]
  }
}
@@ page buck-switched overview - | Switched model
# Switched model

The switched model is the same diagram with [PWM](block:PWM) at `f_sw` = 20 kHz in place of `PWMAverage`. Every edge is an event of the variable-step solver, so the run has 14 001 rows instead of 10 005. The switch [SW](block:SW) is still ideal (an `MTF` that conserves power): there is no diode, no discontinuous conduction, no capacitor ESR and no switch on-resistance, so the point of the variant is the ripple, the pulsed input current and the event handling, not the device losses.

![Switched run|900](@fig:run)

![The last four carrier periods: the output ripple, the inductor triangle and the input-current pulses|900](@fig:zoom)

At 15 V and 2 A the inductor current is a triangle from 1.819 A to 2.181 A, 0.3616 A pp on every recorded row, and the output ripple is 4.88 mV pp. The analytic values at that operating point are $\Delta I = V_{in} D(1-D)/(L f_{sw}) = 0.3614$ A and $\Delta V = \Delta I/(8 f_{sw} C) = 4.81$ mV with $D = 0.3467$. The time-weighted means are the averaged values: 5.000006 V and 2.000 A.

The input current [Iin](block:Iin) is the inductor current while the switch is on and zero while it is off. Its mean, from the inductor current integrated over the on-intervals, is 0.6934 A, and the mean input power is 10.401 W against 10.000 W out: the inductor loss is 0.401 W, 1.1 mW more than in the averaged model because of the ripple, and the efficiency is 96.14 %. A plain trapezoid over the rows of [Pin](block:Pin) gives 11.11 W instead, because each edge is recorded with the value of only one side.

`PWMAverage` is the right model for design and for long runs; use `PWM` to check the ripple, the pulsed input, the event count and the modulator.
