# The FMU

`examples/export_cessna.jl` exports this model with the host interface:

- 16 inputs, `ExportInputPass` markers: the yoke, the pedals, the throttle, the mixture, the flap detent, the trim, the two toe brakes, the autopilot modes, the heading bug and altitude, and the wind;
- 38 outputs, `ExportOutput` markers: the pose, the instruments, the engine, the surfaces, the wheel loads;
- 20 parameters: the start state, set together from a trim or the runway equilibrium.

The analysis picks RK4 at 2.5 ms, 2 substeps per 5 ms communication step. A step takes about 10 µs, with no allocation after instantiate.

`examples/export_cessna_check.py` drives the FMU in fmpy through a take-off roll, a braked run-up and nose-wheel steering in a crosswind, and compares every output with bg-sim:

- every output agrees to about 1e-4 of its peak;
- the exception is the stall flag, whose threshold switch the FMU evaluates once per step.

The browser game Short Final (`apps/web` in the repository) flies the FMU, compiled to WebAssembly.
