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

The **f16-sim** model of the f16 example shows a complete interface:

- the pilot's controls, the gear handle, the wheel brakes and the wind come in through `ExportInputPass` markers;
- 42 `ExportOutput` markers carry what a flight-simulator host draws;
- the trim, the start position, the gear's start position, the CG, the mass and the control-law switches are globals that are kept tunable.

The **beaver-sim** model of the beaver example has a cockpit interface:

- the column, the pedals, the flaps, the elevator trim, the manifold pressure and the rpm lever come in through `ExportInputPass` markers, together with the autopilot modes and references and the wind;
- the outputs are the position, the attitude, the air data, the surfaces and the engine;
- the `drivetrain` global is kept tunable. It switches between the bond-graph drivetrain and the source's algebraic engine power.

The **racecar-sim** and **buggy-sim** models of the cars example do the same for a driving simulator (`apps/car-sim`):

- the steering, the pedals, the handbrake, the reverse switch and a friction scale per wheel come in through `ExportInputPass` markers (the host sets the friction from the surface under each tyre);
- the outputs are the chassis and wheel poses, the tyre and suspension states, the motor speeds, torques and powers, the battery's state of charge, voltage and current, and the aerodynamic downforce and drag (the host's live telemetry panel plots them);
- the start position, heading and charge are globals whose expressions set the start state, and the motor and brake limits are block parameters kept tunable, all with ranges.

The **cessna-sim** model of the cessna example is the FMU of a flight simulator that starts on the runway (`apps/cessna-sim`):

- the yoke, the pedals, the throttle, the mixture, the flap detent, the trim, the two toe brakes, the autopilot modes, the heading bug, the altitude to hold and the wind come in through 16 `ExportInputPass` markers;
- 38 `ExportOutput` markers carry the pose, the six-pack instruments, the engine, the surfaces and the three wheel loads;
- the start state is 20 globals kept tunable with ranges: the pose, the momenta, the crankshaft's momentum, the manifold pressure, the flap angle and the strut compressions. The host sets them together from the runway equilibrium or a trim.

The **a109-sim** model of the a109 example is the FMU of a helicopter simulator that starts on a helipad (`apps/a109-sim`):

- the collective, the cyclic (longitudinal and lateral), the pedals, the SCAS switch and the wind come in through 8 `ExportInputPass` markers;
- 29 `ExportOutput` markers carry the pose, the rates and velocities, the air data, the rotor speed, power, thrust and flapping, the blade angles, the three wheel loads and the weight on wheels;
- the start state is 17 globals kept tunable with ranges: the pose, the momenta, the flapping, the rotor's angular momentum and the governor's integrator. The host sets them together from the helicopter parked on its gear, a hover or a trimmed approach.

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
- Switches (`ifelse`, `abs`, `min`, `max`) and events are evaluated once per step, so an event can be up to one step late (W203). An event whose condition jumps across zero at a discrete tick, or when the host sets an input or parameter, fires at that instant, as in BG-Sim.
- Index-1 DAEs need a Rosenbrock method; Euler and RK4 refuse them (E111).
- `CsvSource` cannot be exported (E110). Replace it with an `ExportInput`.
- Delays (`TransportDelay`, `IntegerDelay`) and `Noise` are supported. A `Noise` block gives the same sequence in the FMU as in BG-Sim for the same seed.
- Debug hooks and watches are not exported.
- Flexible beams (`FlexibleBeam2D`, `FlexibleBeam3D`) export, but their modes are fast. RK4 is stable only for `dt · ω_max < 2.8`, where `ω_max` is the highest modal frequency in rad/s; a free beam vibrates up to twice its clamped-free `f_*` outputs (torsion). To follow the simulation closely, keep `dt · ω_max` near 0.1, use fewer modes (often `nt = 0`), or choose Rodas4P. See [Flexible bodies](page:flexible-bodies).

If the model cannot be exported, the dialog lists the reasons as diagnostics with their codes.
