# Signal sources

Source blocks are in the **Sources and sinks** category of the library. Delay and sampling blocks are in **Continuous** and **Discrete and logic**. Select a block and press `F1`, or click its help button in the library, for the full parameter list.

## Sources

| Block | Output | Key parameters |
| --- | --- | --- |
| `Constant` | a constant value | `value` |
| `Step` | jumps from `initial` to `final` at `t_step` | `t_step`, `initial`, `final` |
| `Ramp` | rises with `slope` from `t_start` | `t_start`, `slope`, `initial` |
| `Sine` | `offset + amplitude·sin(frequency·t + phase)` | `frequency` in **rad/s**, `phase` in rad |
| `Pulse` | a square wave | `amplitude`, `period`, `duty` (0..1), `t_start` |
| `Chirp` | a linear frequency sweep | `f_start`, `f_end` in **Hz**, `duration` |
| `Time` | the simulation time | none |
| `TimeTable` | a uniformly sampled table | `t_start`, `sample_time`, `values`, `method` (0 hold, 1 linear) |
| `CsvSource` | columns of a CSV file in the project | `file`, `time_column`, `columns`, `method`, `extrapolation` |
| `CsvSourceSampled` | like `CsvSource`, sampled and held | `sample_period` |
| `Noise` | seeded normal noise on a fixed clock | `mean`, `std`, `seed`, `sample_time` |

Notes:

- `Noise` gives the same sequence for the same `seed`, in every run and in an exported FMU. Give each `Noise` block its own seed.
- `CsvSource` reads a CSV file from the project (for example `data/trajectory.csv`) and interpolates with hold, linear or cubic (`method` 0, 1, 2). It cannot be exported to an FMU; use an `ExportInput` there (see [Export](page:export)).

<!-- TODO: add the random signal sources (stdlib/sources) once they are merged. -->

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
