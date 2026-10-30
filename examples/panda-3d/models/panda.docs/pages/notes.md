# Notes

- **Speed.** The compliant held directions make the system stiff, so the run uses `Rodas5P`. The 21-state system solves in 3.7 s per simulated second, including the 5150 ticks of the 1 kHz discrete partitions.
- **Export.** `panda`, `panda-free` and the Robot subsystem on its own (`BGSim.Export.scope_document(doc, "Robot")`, `design/export_robot.jl`) export to C/FMU. The default RK4 export needs 12500 substeps per 1 ms step (about 70 ms per step); the Rosenbrock export (`ros2`, sparse LU) takes one step per 1 ms in 92 µs and keeps the joint angles of `panda` within 3e-6 rad of the simulation.
- **Assumptions.** Gear ratio, rotor inertia and gear stiffness are not published by Franka (see [the Robot subsystem](page:robot)). The controller is a textbook PD and not Franka's.
