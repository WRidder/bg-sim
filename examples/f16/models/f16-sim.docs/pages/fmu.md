# The FMU

The model's export markers define the FMU interface:

| | FMI names |
| --- | --- |
| inputs | `stick_pitch`, `stick_roll`, `pedals` (−1..1), `throttle` (0..1), `wind_n`, `wind_e`, `wind_d` (m/s), `gear_cmd` (0 up, 1 down), `brake_l`, `brake_r` (0..1) |
| outputs | position `north_m`, `east_m`, `alt_m`; quaternion `q_w..q_z` and `phi_deg`, `theta_deg`, `psi_deg`, `gamma_deg`; body rates and velocities; `tas_mps`, `cas_mps`, `mach`, `qbar_pa`, `alpha_deg`, `beta_deg`, `nz_g`, `ny_g`; surfaces; `power_pct`, `thrust_n`; `p_lim_dps`, `nz_cmd_g`, `limiter_active`, `departed`, `ground_contact`; `fn_nose`, `fn_left`, `fn_right` (N), `on_ground`, `steer_rad`, `gear_pos` |
| parameters | the trim `vt0`, `h0`, `alpha0`, `el0`, `thtl0` (set together, from a trim), the start `gamma0`, `gear0`, `north0`, `east0`, `xcg`, `mass`, and the law switches |

The `ExportInputPass` markers keep the test input in bg-sim. In the FMU the wire into them is cut and the host supplies the signal. The trim globals set the start state through expressions (the quaternion, the momentum and the engine power), and the FMU recomputes them at initialization.

Export it in the **Export** dialog with these globals as tunables, or run `examples/export_f16.jl`. The script sets RK4 at 2.5 ms, two substeps per 5 ms communication step, because the analysis looks only at the model's own start, in the air, and does not see the tyres and struts. One `doStep` takes about 9 µs, with no allocations after instantiation (2.9 µs before the gear).

`examples/export_f16_check.py` drives the FMU in fmpy through seven runs and compares it with bg-sim runs driven by the same inputs: a pitch doublet, a roll and roll back, a coordinated turn and a throttle step to full afterburner in the air, and on the wheels a taxi with steering and a brake stop, a take-off with the gear coming up, and a landing. In the air the angles agree within 4e-4 deg and the altitude within 2 mm; on the wheels the wheel load agrees within 100 N of a 45 to 115 kN peak.
