# Power curve

The NREL 5 MW turbine with its baseline controller on a slow wind ramp from 4 to 25 m/s (0.02 m/s per second). The turbine passes through its operating points almost in equilibrium, so the run traces the power curve. See [the turbine](project:turbine) for the model.

![The model canvas|900](assets/0ba7dad8b2cd.png)

![The ramp|900](assets/a06b419f16c3.png)

## What you see

- Below rated (11.3 m/s), [Torque](block:Torque) holds the optimal tip-speed ratio: [Aero/lambda](signal:Aero/lambda) stays at 7.58 and [Cp/y](signal:Cp/y) at 0.485, while the power grows with $v^3$.
- From rated on, [PitchCtrl](block:PitchCtrl) pitches the blades ([Aero/beta_deg](signal:Aero/beta_deg)) to hold 12.1 rpm and [ElecPower/y](signal:ElecPower/y) at 5 MW. The thrust ([ThrustkN/y](signal:ThrustkN/y)) peaks at rated and falls above it.

## What to try

- Set `v_end` equal to `v_start` on the dashboard for one steady operating point.
- Plot [ElecPower/y](signal:ElecPower/y) over [Wind/y](signal:Wind/y) (the saved plot "Power curve").

## Key parameters

`v_start`, `v_end`, `t_ramp` and `ramp_time` set the ramp. The turbine globals (`J_rotor`, `k_shaft`, `m_tower`, ...) are shared by all models.
