# Race car: the FMU source

The race car with the interface of the `apps/car-sim` driving simulator, on the race track (flat, z = 0).

![The model canvas|900](assets/d20f1b764fcb.png)

- **Inputs** (`ExportInputPass`): [steer](block:steer), [throttle](block:throttle), [brake](block:brake), [reverse](block:reverse), [handbrake](block:handbrake) and the friction scale under each tyre, [mu_fl](block:mu_fl) .. [mu_rr](block:mu_rr). In bg-sim they pass a short test drive through; in the FMU the host supplies them.
- **Outputs** (`ExportOutput`): the chassis and carrier poses, the spin angles, the tyre and suspension states, the contact points, the telemetry, the motor and the battery.
- **FMU parameters**: the globals `x0`, `y0`, `z0`, `yaw0`, `soc0` (the start state is a set of expressions of them) and the motor and brake limits.

Export it with `julia --project=julia/BGSim examples/export_cars.jl <out> racecar` or from the Export dialog. It uses fixed-step RK4 at 5 ms per communication step.

![3D view at t = 8 s|600](assets/4089bf554181.png)
