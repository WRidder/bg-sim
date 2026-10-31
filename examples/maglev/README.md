# Maglev

A steel ball levitated below an electromagnet: a gain-scheduled PID on the LPV model, and a bond graph with an energy-conserving coil field.

The plant, the operating points and the scenario follow the MathWorks example
[LPV Model of Magnetic Levitation Model from Batch Linearization Results](https://nl.mathworks.com/help/control/ug/maglev-lpv-model-from-batch-linearization.html)
and its companion [LPV Model of Magnetic Levitation System](https://nl.mathworks.com/help/control/ug/maglev-lpv-model-from-equations.html).
The controllers are designed here independently, in closed form (`design/design.py`).

## Plant

    m h'' = m g - alpha i^2 / h^2        m = 0.02 kg, g = 9.81 m/s^2, alpha = 2.4832e-5 N m^2/A^2

`h` is the gap from the magnet face down to the ball (positive down), `i` the coil current.
Trim: `i_bar = c h_bar` with `c = sqrt(m g/alpha) = 88.888 A/m`. LPV model at the gap `p`:
`A(p) = [0 1; 2g/p 0]`, `B(p) = [0; -2 sqrt(g alpha/m)/p]`, `C = [1 0]`; unstable pole `sqrt(2g/p)`.

## Models

| model | what it shows |
| --- | --- |
| `maglev-current-driven` | The reference scenario: current input, gain-scheduled PID (Lookup1D tables at 0.05/0.15/0.25 m) with trim feedforward `c h` and the prefilter `10/(s+10)`, step 0.15 -> 0.1875 m at 0.2 s. A `Statics` subsystem finds the trim currents at the three gaps by integral action. |
| `maglev-open-loop-and-linear` | Three balls released 10 nm off their trim gaps (growth rate -> `sqrt(2g/p)`), and the nonlinear plant next to its LPV model frozen at 0.15 m under the same PID, for a small (+5 mm) and a large (+60 mm) step. |
| `maglev-bondgraph` | The energy-consistent version: amplifier MSe with a +-60 V rail, coil 1-junction with R and the stdlib `converters/Electromagnet` (a two-port IC-field, `L(h) = L_inf + 2 alpha/h`, `F = alpha i^2/h^2`), ball I with a gravity Se. Cascade: scheduled position PID -> current setpoint, PI current loop -> voltage. IR sensor with seeded noise and a 16-bit ADC at 1 kHz. Dashboard with a setpoint slider and gauges. |

The docs of each model (overview, plant and LPV derivation, controller design, bond graph and
co-energy, results) are under `models/<model>.docs/`.

## Parameters chosen here

| quantity | value | why |
| --- | --- | --- |
| crossover, derivative filter | 50 rad/s, 1 ms | the reference's values |
| phase margin | 60 deg | the closed-form design target |
| `L_inf`, coil `R` | 0.03 H, 2 Ohm | assumed (the reference has no coil model); `L(0.15) = 30.3 mH` |
| amplifier rail | +-60 V | 2.25 x the trim voltage at 0.15 m |
| current loop | PI, `Kp = L0 w_i`, `Ti = L0/R`, `w_i = 1000 rad/s` | zero cancels the coil pole, 20 x the outer crossover |
| IR sensor | 30 V/m around 0.15 m, 0.3 mV rms noise (10 um), 16 bit over -5..5 V, 1 kHz | a realistic, quiet sensor |
| cascade derivative filter | 5 ms | 1 ms turns the sensor noise into rail-to-rail voltage |

## PID gains

Series PID `K (s + z)^2 / (s (Tf s + 1))` on the frozen plant `b0/(s^2 - a0)`, whose phase is -180 deg
everywhere: the phase margin fixes `z`, the crossover magnitude fixes `K`. `K` is affine in `p`, so the
Lookup1D interpolation between the design points is exact.

| p [m] | Kp [A/m] | Ki [A/(m s)] | Kd [A s/m] | cascade Kp | cascade Ki | cascade Kd |
| --- | --- | --- | --- | --- | --- | --- |
| 0.05 | 297.42 | 1805.46 | 12.101 | 135.02 | 349.39 | 12.709 |
| 0.15 | 811.57 | 4926.51 | 33.019 | 368.43 | 953.36 | 34.679 |
| 0.25 | 1325.71 | 8047.55 | 53.937 | 601.83 | 1557.34 | 56.650 |

The cascade gains include the half-sample delay of the ADC, the current loop and the 5 ms filter in the
phase budget (PM 58.9 / 59.7 / 59.8 deg of the sampled loop).

## Results (`expected.json`, `uv run examples/run_checks.py --only maglev`)

| | rise 10-90 % | overshoot | settling 2 % | notes |
| --- | --- | --- | --- | --- |
| current-driven | 0.1671 s | 0 % | 0.4085 s | gap at 1.4 s equals scipy to 2e-14 m; current 1.18 ... 18.41 A |
| bond graph, noisy sensor | 0.1641 s | 0.12 % | 0.286 s | energy invariant 2.3e-9 of W(0); voltage hits the +60 V rail once |
| bond graph, ideal sensor | 0.1642 s | 0.13 % | 0.286 s | at 6 s: i/h = 88.8881058457 A/m (c = 88.8881058456) |

Open loop: growth rates 19.8080 / 11.4366 / 8.8588 1/s against the poles 19.8091 / 11.4368 / 8.8589.
Frozen linear vs nonlinear: 0.49 % of the small step, 17.6 % of the large one (the large step asks for a
negative current, and the real magnet cannot push).

## Files

- `design/design.py` writes `design/design.json` (trim, LPV, gains, margins, scipy simulations);
- `design/build_model.py` writes the three models, the two scenes and `expected.json` from it;
- `library/`: `MaglevBall` (the reference plant with soft stops), `ScheduledPID`, `CurrentPI` (anti-windup),
  `LinearBall` (the frozen LPV model), `GrowthRate`, and the small `Bias`, `Add2`, `Diff2` helpers;
- `scenes/maglev.sdf` (tabletop rig), `scenes/maglev-open-loop.sdf` (three rigs).

Regenerate: `uv run examples/maglev/design/design.py`, `uv run examples/maglev/design/build_model.py`,
`uv run tools/example_docs/build.py --only maglev`.
