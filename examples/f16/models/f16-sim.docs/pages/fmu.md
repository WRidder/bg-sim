# The FMU

The model's export markers define the FMU interface:

| | FMI names |
| --- | --- |
| inputs | `stick_pitch`, `stick_roll`, `pedals` (−1..1), `throttle` (0..1), `wind_n`, `wind_e`, `wind_d` (m/s) |
| outputs | position `north_m`, `east_m`, `alt_m`; quaternion `q_w..q_z` and `phi_deg`, `theta_deg`, `psi_deg`, `gamma_deg`; body rates and velocities; `tas_mps`, `cas_mps`, `mach`, `qbar_pa`, `alpha_deg`, `beta_deg`, `nz_g`, `ny_g`; surfaces; `power_pct`, `thrust_n`; `p_lim_dps`, `nz_cmd_g`, `limiter_active`, `departed`, `ground_contact` |
| parameters | the trim `vt0`, `h0`, `alpha0`, `el0`, `thtl0` (set together, from a trim), `xcg`, `mass`, and the law switches |

The `ExportInputPass` markers keep the test input in bg-sim. In the FMU the wire into them is cut and the host supplies the signal. The trim globals set the start state through expressions (the quaternion, the momentum and the engine power), and the FMU recomputes them at initialization.

Export it in the **Export** dialog with these globals as tunables, or run `examples/export_f16.jl`. The analysis picks RK4 with one 5 ms step per 5 ms communication step: the fastest closed-loop poles (the servos at 20.2 rad/s, the roll loop) are slow enough. One `doStep` takes about 3.5 µs, with no allocations after instantiation.

`examples/export_f16_check.py` drives the FMU in fmpy through four manoeuvres and compares it with bg-sim runs driven by the same inputs: a pitch doublet, a roll and roll back, a coordinated turn and a throttle step to full afterburner. The angles agree within 2e-3 deg and the altitude within 1 cm. The largest relative deviation is the engine power, 0.7 % of its peak for a moment: the FMU evaluates the switch at military power once per step.
