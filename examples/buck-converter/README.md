# buck-converter — a 12 V → 5 V buck with a PID voltage loop and feed-forward

A 20 kHz synchronous buck converter as a bond graph. The switch is an ideal, power-conserving
modulated transformer (`MTF`) whose modulus is the duty, so the model has an input current,
an input power and an efficiency. The controller is the stdlib `PID` block on the filtered
error plus the duty feed-forward `Vref/Vin`. Two models share the same diagram:
`buck-averaged` drives the switch with `PWMAverage` (no carrier), `buck-switched` with `PWM`
at 20 kHz (the real ripple and edges).

**Scope.** This is a synchronous converter in continuous conduction only: there is no diode
(so no discontinuous conduction), no capacitor ESR and no switch on-resistance. The only loss
is the inductor resistance `R_L` = 0.1 Ω; its drop `R_L·I` (0.2 V at 2 A) is why the steady
duty is (5 + 0.2)/15 = 0.3467 rather than 5/15.

## Models

| model | what it runs |
| --- | --- |
| `buck-averaged` | the averaged plant: 5 V startup, a 1 A load step at 20 ms, a 12 → 15 V line step at 30 ms, 50 ms |
| `buck-switched` | the same scenario with the 20 kHz carrier: the inductor and output ripple, the pulsed input current, the PWM events |

## Plant (bond graph)

```
Vin → MSe Supply → Pin → 1 IN ─→ MTF SW ─→ 1 LJ ──→ 0 OUT ──→ 1 IO ────→ 0 LOAD
                         │ Df Iin ↑ d      │ I L    │ C       │ Df Iout  │ R Rload
                                 PWM       │ R RL   │ De Vout            ↑ MSf Iload ← LoadStep
                                           │ Df IL
```

| part | bond graph |
| --- | --- |
| input | [Vin](block:Vin) (a 12 → 15 V step at 30 ms) drives the effort source [Supply](block:Supply) (`MSe`); the stdlib power sensor [Pin](block:Pin) on its bond reads the input power |
| input current | 1-junction [IN](block:IN) with the flow detector [Iin](block:Iin) (`Df`) |
| switch | [SW](block:SW), `MTF` with modulus `d` from [PWM](block:PWM): `e_switch = d·Vin`, `i_in = d·i_L`, power in = power out |
| series branch | 1-junction [LJ](block:LJ) with [L](block:L) (`I`, 470 µH), the inductor resistance [RL](block:RL) (`R`, 0.1 Ω) and the flow detector [IL](block:IL) |
| output node | 0-junction [OUT](block:OUT) with [C](block:C) (470 µF) and the effort detector [Vout](block:Vout) (`De`) |
| load | 1-junction [IO](block:IO) with the output-current detector [Iout](block:Iout), then 0-junction [LOAD](block:LOAD) with [Rload](block:Rload) (5 Ω) and the load step [Iload](block:Iload) (`MSf`, gain −1, so the 1 A from [LoadStep](block:LoadStep) is drawn out of the node) |
| output power | [Pout](block:Pout) = `Vout·Iout` (a `PowerSensor` between OUT and LOAD would leave the load resistor's causality free: an algebraic loop, W202) |
| reference | [Vref](block:Vref) (5 V) through the 1 ms set-point filter [VrefFilt](block:VrefFilt) |

`L`, `C`, `R_load`, `V_ref` and `f_sw` are model-level global parameters (the averaged model
has no carrier and ignores `f_sw`). The averaged equations are

```
L di/dt = d·Vin − v − R_L·i          i_in = d·i
C dv/dt = i − v/R_load − i_load .
```

With `L = 470 µH` and `C = 470 µF` the LC double pole is at **f0 = 1/(2π√(LC)) = 339 Hz**, with
`Q = R·√(C/L) = 5` for the lossless filter and **Q ≈ 3.4** with `R_L` = 0.1 Ω at 5 Ω
(`design/design.py`). Above f0 the plant phase approaches −180°, so a PI loop cannot be given
much margin there; the derivative term supplies the phase.

## Controller

`library/` has no controller code: the loop is the stdlib [PID1](block:PID1) block plus two
scalar glue blocks (`Diff2`, `Add2`). The path is

```
Vref → VrefFilt → Err (VrefFilt − Vout) → PID1 ─┐
VrefFilt / Vin ─────────────────────── FF ──────┴→ DutySum → DutySat (0..1) → PWM/PWMAverage → SW
```

The stdlib `PID` block is not in textbook form:

```
u = Kp·e + (Kp/Ti)·ξ + N·(e − x_d)
ξ' = e/Ti + (y − u)/√(Ti·Td),   x_d' = (e − x_d)·N/Td,
```

which is `C(s) = Kp + (Kp/Ti²)/s + Td·s/(1 + s·Td/N)`, clamped to ±1. The loop's effective
gains are therefore

| term | parameter | effective value |
| --- | --- | --- |
| proportional | `Kp` = 0.2 | 0.2 per V |
| integral | `Ti` = 0.04472 s | `Kp/Ti²` = 100 1/s (`design.py` passes `Ti = √(Kp/Ki)`) |
| derivative | `Td` = 0.2 ms | derivative gain `Td` itself = 0.2 ms (not `Kp·Td`; the textbook `Td` would be 1 ms) |
| derivative filter | `N` = 5 | time constant `Td/N` = 40 µs, corner 3.98 kHz |
| high-frequency gain | | `Kp + N` = 5.2 |

The loop crosses over at **1.72 kHz with 65° phase margin** (nominal 12 V, 5 Ω). The derivative
path, not `Kp`, sets the crossover: at 1.7 kHz the derivative term (≈ 2) is ten times `Kp`.
From `design/design.py` (the integral gain scales with `Kp`, as in the block):

| change | crossover | phase margin |
| --- | --- | --- |
| nominal | 1716 Hz | 65.0° |
| `Kp` 0.4 / 0.05 | 1779 / 1675 Hz | 59.6 / 69.4° |
| `Td` 0.4 / 0.1 ms | 2363 / 1021 Hz | 40.7 / 71.9° |
| `N` 10 / 2.5 | 1784 / 1547 Hz | 75.7 / 50.4° |

`Td` moves the crossover; `N` moves the derivative corner and with it mainly the phase margin.

The feed-forward `d_ff = Vref/Vin` supplies the steady duty, so the PID only corrects the
error; this is why the startup follows the 1 ms filtered reference without overshoot. The
filter turns the 5 V step into a ramp, so the derivative sees a bounded slope instead of an
impulse, but it does not remove the kick: the derivative acts on the error, and the duty still
jumps to 0.71 within the first 65 µs of the startup.

Run the design and the model build with

```
uv run examples/buck-converter/design/design.py
uv run examples/buck-converter/design/build_model.py
```

`design.py` writes `design.json` (LC corner, margins, the averaged reference and the steady
state at 15 V / 2 A); `build_model.py` writes both model files and the project file.

## Results

| quantity | averaged | switched |
| --- | --- | --- |
| output at 50 ms | 5.000000 V | time-weighted mean over [40, 50] ms 5.000006 V |
| startup (1 % band) | 4.32 ms, no overshoot | 4.38 ms |
| load-step dip at 20 ms | 4.8226 V | 4.8257 V (with the ripple) |
| recovery overshoot | 5.0124 V at 23.5 ms | 5.0133 V |
| line-step peak at 30 ms | 5.0093 V | 5.0194 V (with the ripple) |
| peak inductor current | 2.351 A at 0.245 ms (startup inrush) | 2.387 A |
| inductor current after the load step | peaks at 2.093 A at 20.28 ms | 2.240 A (with the ripple) |
| inductor current | 2.000 A | mean 2.000 A, 1.819 … 2.181 A |
| inductor ripple at 15 V / 2 A | 0 | 0.3616 A pp |
| output ripple at 15 V / 2 A | 0 | 4.88 mV pp |
| input current | 0.6933 A | mean 0.6934 A (pulses of `i_L`) |
| input power | 10.400 W | mean 10.401 W |
| efficiency | 96.15 % | 96.14 % |

The ripple references are at the operating point of the check window, 15 V and 2 A, where
`D = (5 + 0.1·2)/15 = 0.3467`:
`ΔI = Vin·D·(1 − D)/(L·f_sw) = 0.3614 A pp` and `ΔV = ΔI/(8·f_sw·C) = 4.81 mV pp`. The
switched run measures 0.3616 A and 4.88 mV on every recorded row (event rows included); a
uniform 5 µs grid would see only 0.332 A, because it samples the 20 kHz triangle at fixed
phases and misses its corners.

**Power balance.** The averaged model closes it to 2·10⁻¹¹ W over [40, 50] ms:
`Pin` 10.400 W = `Pout` 10.000 W + `R_L·i²` 0.400 W, so η = 10/10.4 = 96.15 %. In the switched
model `Pin` is a pulse train (`Vin·i_L` while the switch is on, 0 while it is off). Its rows
cannot be averaged with a trapezoid: an edge is recorded at one time with either the value
before or after it, so the trapezoid smears the jump (it gives 11.11 W). Integrating the
inductor current over the on-intervals instead gives a mean input current of 0.6934 A and
`Pin` = 10.401 W, against `Pout` 10.000 W + `R_L·⟨i²⟩` 0.401 W (the ripple adds
`R_L·ΔI²/12` = 1.1 mW): the balance closes to 0.14 mW, and η = 96.14 % (analytic 96.144 %).
The load step is a 1 A current sink at 20 ms; the line step is 12 → 15 V at 30 ms. The
averaged recovery after the load step is 0.58 ms (2 % band).

## Checks

`uv run examples/run_checks.py --only buck-converter` runs 33 checks:

- averaged: output 5 V at 15 ms and 50 ms and its time-weighted mean over [40, 50] ms against
  `design.json` to 0.1 µV, the load-step minimum above 4.8225 V, the recovery peak
  5.01241 V, the startup inrush 2.3511 A and the load-step peak 2.0932 A, final inductor
  current 2 A, final duty 0.34667, input current 0.69333 A, mean input power 10.4 W, mean
  output power 10 W and the efficiency Pout/Pin = 0.961538;
- switched: time-weighted means of the output (5 V within 20 µV), the inductor current (2 A
  within 20 µA) and the output power (10 W within 0.1 mW); the inductor current peaks at
  2 + ΔI/2 = 2.1807 A (± 1 mA) and stays above 1.818 A; the input current peaks at the same
  value (the switch passes `i_L` while on); the dominant line of `IL/y` is 20 kHz (± 0.5 %);
  the ripple on every row is below 0.365 A and 5 mV pp; the load-step dip stays above 4.824 V.
  The averaged model fails the peak, input-current and 20 kHz checks, so they test the switching;
- averaged and switched outputs agree within 3 mV over [40, 50] ms (dV/2 = 2.4 mV);
- saved plots and dashboard cards name recorded signals, the docs lint, and no `E901`,
  `E106`, `W201`, `W202` or `W206` (the bond graph is Generic, so `W205` is expected).

The independent reference is `design/design.py`, which integrates the averaged ODE with the
same PID, feed-forward, limits and both steps, and works out the steady state, the ripple and
the power balance at 15 V / 2 A.

## What to try

Each line was run on the model; the numbers are the result.

- **Derivative gain `PID1.Td`** (the crossover knob): 0.4 ms shrinks the load-step dip to
  4.855 V and settles in 0.21 ms, but the inductor current peaks at 2.86 A and the duty reaches
  0.96 (phase margin 41°); 0.1 ms lets the dip grow to 4.751 V.
- **Derivative filter `PID1.N`**: 10 gives 4.837 V and a 76° margin; 2.5 lowers the
  derivative corner to 2 kHz and the dip grows to 4.791 V (50° margin).
- **`PID1.Kp`** barely matters: 0.4 gives a dip of 4.833 V, 0.05 gives 4.813 V and a slower
  recovery (1.45 ms). Neither changes the startup (4.3–4.6 ms to the 1 % band), which the
  feed-forward and the 1 ms reference filter set. `Td` cannot be set to 0 (the block's minimum
  is 1e-9 s), so the derivative cannot simply be switched off here.
- **`Vin` final 18 V**: the feed-forward adapts (steady duty 5.2/18 = 0.289) and the output
  moves by at most 16 mV.
- **`LoadStep` final 2 A**: the dip grows to 4.644 V, the duty saturates at 1 for a moment,
  and the inductor current settles at 3 A.
- **`f_sw` 10 kHz** (global, switched model): the inductor ripple doubles to 0.72 A pp and the
  output ripple grows four-fold to 19.4 mV pp (`ΔV ∝ 1/f_sw²`).
- To see the switching in the averaged model, replace `PWMAverage` by `PWM` **and set its
  `frequency` to `f_sw`**: `PWM` defaults to 1000 Hz, which is a different converter. That is
  exactly the `buck-switched` model.
