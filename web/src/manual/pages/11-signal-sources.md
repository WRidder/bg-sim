# Signal sources

Source blocks are in the **Sources and sinks** category of the library. Delay and sampling blocks are in **Continuous** and **Discrete and logic**. Select a block and press `F1`, or click its help button in the library, for the full parameter list.

## Sources

Frequencies are angular (**rad/s**) in `Sine`, `MultiSine` and `ExpSine`, and in **Hz** in `Chirp`. Most sources have an `offset` and a `t_start`; before `t_start` the output is the offset (the first table value for the tables).

| Block | Output | Key parameters |
| --- | --- | --- |
| `Constant` | a constant value | `value` |
| `Step` | jumps from `initial` to `final` at `t_step` | `t_step`, `initial`, `final` |
| `Ramp` | rises with `slope` from `t_start`, for `duration` seconds | `t_start`, `slope`, `initial`, `duration` (default: no end) |
| `Sine` | `offset + amplitude·sin(frequency·τ + phase)` with `τ = t − t_start` | `amplitude`, `frequency` in **rad/s**, `phase` in rad, `offset`, `t_start` |
| `MultiSine` | a sum of N sines | `amplitudes`, `frequencies` (rad/s), `phases`, `offset`, `t_start` |
| `ExpSine` | a damped sine, `amplitude·e^(−damping·τ)·sin(frequency·τ + phase)` with `τ = t − t_start` | `damping` in 1/s, `offset`, `t_start` |
| `Exponentials` | a first-order rise for `rise_time`, then a first-order fall | `amplitude`, `rise_time`, `tau_rise`, `tau_fall` |
| `Pulse` | a square wave | `amplitude`, `period`, `duty` (0..1), `t_start`, `offset` |
| `Trapezoid` | rise, high, fall and low within each period (as in Modelica) | `rising`, `width`, `falling`, `period`, `n_periods` (−1: forever) |
| `Sawtooth` | rises over each period, then drops back | `amplitude`, `period`, `offset`, `t_start` |
| `Triangle` | rises over half a period and falls back | `amplitude`, `period`, `offset`, `t_start` |
| `Chirp` | a frequency sweep, linear or logarithmic | `f_start`, `f_end` in **Hz**, `duration`, `amplitude`, `offset`, `start_phase`, `method` |
| `Time` | the simulation time | none |
| `TimeTable` | a uniformly sampled table, once | `t_start`, `sample_time`, `values`, `method` (0 hold, 1 linear) |
| `RepeatingTable` | the table repeated every `N·sample_time` | as `TimeTable`; linear wraps from the last value back to the first |
| `CsvSource` | columns of a CSV file in the project | `file`, `time_column`, `columns`, `method`, `extrapolation` |
| `CsvSourceSampled` | like `CsvSource`, sampled and held | `sample_period` |

Notes:

- A staircase or a multi-step signal is a `TimeTable` with `method` 0 (hold).
- `Sine` starts at `t_start` with the phase `phase`, as in Modelica. With a non-zero `phase` the output jumps at `t_start`, from `offset` to `offset + amplitude·sin(phase)`; the jump is an exact event. A cosine is `phase = π/2`.
- `Pulse` locates its edges from a smooth condition. When an edge falls exactly on an output time, the solver can stop with W206 (event limit). `Trapezoid` with `rising = falling = 0` and `width = duty·period` is the same pulse with exact edges. `Sawtooth`, `Triangle`, `Trapezoid` and `RepeatingTable` locate every edge exactly.
- `CsvSource` reads a CSV file from the project (for example `data/trajectory.csv`) and interpolates with hold, linear or cubic (`method` 0, 1, 2). It cannot be exported to an FMU; use an `ExportInput` there (see [Export](page:export)).

## Random sources

| Block | Output | Key parameters |
| --- | --- | --- |
| `Noise` | normal noise, `mean + std·z` | `mean`, `std`, `seed`, `sample_time` |
| `UniformNoise` | uniform noise between `y_min` and `y_max` | `y_min`, `y_max`, `seed`, `sample_time` |
| `BandLimitedWhiteNoise` | white noise with power spectral density `noise_power` (as in Simulink): `sqrt(noise_power/sample_time)·z` | `noise_power`, `seed`, `sample_time` |
| `PRBS` | a pseudo-random binary signal, `offset ± amplitude` | `amplitude`, `offset`, `bit_ticks` (ticks per bit), `seed`, `sample_time` |
| `RandomWalk` | a Gaussian random walk; each tick adds `step_std·z` | `step_std`, `initial`, `seed`, `sample_time` |

Every random source draws a new sample at each tick of its own clock (`sample_time`, set in the block's code) and holds it until the next tick. Before the first tick the output is its middle value: `mean`, the midpoint, 0, `offset` or `initial`.

The samples are deterministic. Each one is a fixed function of the block's integer `seed` and the sample number, so:

- the same seed gives the same sequence in every run, on every machine, and in an exported FMU, bit for bit;
- a different seed gives a different sequence;
- two random blocks with the same seed draw the same sequence. The compiler warns about this with W216. Give each random block its own `seed`.

## Delays and sampling

| Block | Category | What it does |
| --- | --- | --- |
| `TransportDelay` | Continuous | delays the input by `delay_time`, stored every `sample_period` and interpolated |
| `UnitDelay` | Discrete and logic | delays the input by one sample |
| `IntegerDelay` | Discrete and logic | delays the input by `N` samples |
| `ZOH` | Discrete and logic | samples the input and holds it until the next tick |
| `OnOffDelay` | Discrete and logic | the Boolean output follows the input after `t_on` / `t_off` |

## Sinks

- `Scope` opens a plot panel for its inputs; it has no effect on the simulation.
- `Recorder` marks a signal for recording. Every signal is recorded anyway, so you can also [plot any signal](page:running-and-plotting) without one.
