# Export (C / FMU)

BG-Sim generates C code for a model and packs it as an **FMI 2.0 Co-Simulation FMU**. The FMU contains the C sources, plus a binary when a C compiler (gcc or clang) is on the PATH of the machine running BG-Sim. Without a compiler you get a source-only FMU.

## Start an export

- **Whole model:** click **Export FMU…** in the top bar.
- **One subsystem:** right-click the subsystem on the canvas and choose **Export subsystem…**. The ports of the subsystem become the FMU interface.

In the dialog, **Scope** switches between **Whole model** and **Subsystem**. Click **Export** to start. You can close the dialog while it runs: the export goes on as a [background task](page:background-tasks). When it is done, the report has a **Download … .fmu** button.

## The interface: export markers

For a whole-model export, marker blocks define the inputs, outputs and parameters of the FMU. They are in the **Converters and sensors** category of the library.

| Block | In simulation | In the FMU |
| --- | --- | --- |
| `ExportInput` | outputs its `value` as a constant | `value` becomes an FMU input |
| `ExportInputPass` | passes its input `u` through to `y` | the wire into `u` is cut and the host supplies the signal; `value` is the start value |
| `ExportOutput` | nothing | the signal on `u` becomes an FMU output |
| `ExportParameter` | holds its `value` (no ports) | `value` becomes a tunable FMU parameter |

Use `ExportInputPass` when the model should keep its own test stimulus in BG-Sim but take the input from the host in the FMU. The FMI variable names are the instance paths of the markers.

For a subsystem export, the power ports of the subsystem are part of the interface too. For each one, choose whether the host imposes the **effort** or the **flow**.

If the export has nothing to publish, you get warning W209.

## Tunable parameters and globals

By default, every parameter is folded into the generated code as a constant, which gives the fastest step. To keep a value adjustable in the FMU:

- type its name in **Parameter or global to keep tunable** and click **Add**. You can add a block parameter (by instance path) or a [global parameter](page:parameters);
- or click **Expose all globals** to make every global that is not an equation an FMU parameter.

Each tunable can have a **Min** and a **Max**. The FMU refuses a value outside the range; it does not clamp. An open range gives warning W210.

Parameters declared `tunable = true` and `ExportParameter` markers are always FMU parameters.

## Settings

| Setting | Meaning |
| --- | --- |
| **Method** | Auto, Euler, RK4, ROS2, ROS34PW2 or Rodas4P |
| **Internal step dt [s]** | the fixed internal step; empty means Auto |
| **Advanced** | communication step, Rosenbrock damping, Jacobian (symbolic or finite differences), linear solver (dense or sparse LU), and **Expose all signals (debug, read-only)** |

The report lists the chosen method and step, the number of states, timings, and checks of the compiled FMU: no allocations after instantiation, no allocator, stdio or exit in the hot path, and the measured `doStep` time.

## Real-time rules

The FMU runs with a fixed step and allocates no memory after instantiation, so some constructs are restricted:

- Clock periods and offsets of discrete blocks must be whole multiples of `dt` (E104).
- Switches (`ifelse`, `abs`, `min`, `max`) and events are evaluated once per step, so an event can be up to one step late (W203).
- Index-1 DAEs need a Rosenbrock method; Euler and RK4 refuse them (E111).
- `CsvSource` cannot be exported (E110). Replace it with an `ExportInput`.
- Delays (`TransportDelay`, `IntegerDelay`) and `Noise` are supported. A `Noise` block gives the same sequence in the FMU as in BG-Sim for the same seed.
- Debug hooks and watches are not exported.

If the model cannot be exported, the dialog lists the reasons as diagnostics with their codes.
