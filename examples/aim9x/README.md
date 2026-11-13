# AIM-9X Sidewinder

The AIM-9X as a six-degree-of-freedom bond graph: a burning solid rocket motor, a slender
cruciform airframe with canard control, a two-axis thrust-vector augmentation, an imaging
infrared seeker, proportional navigation and a proximity fuze. Three flight models close more and more of the weapon loop, and a fourth is the host-interface FMU:

| model | what it shows |
| --- | --- |
| `aim9x-airframe` | the open-loop plant: cubic lift and Mach-dependent drag, the canards, the variable mass, the roll/yaw damping and a short-period ring-down |
| `aim9x-control` | the skid-to-turn autopilot: roll hold, a qbar-scheduled pitch/yaw rate loop and the TVC allocation |
| `aim9x-intercept` | the full weapon against a target: seeker gimbal and field of view, LOS rates, proportional navigation, a lift-limited guidance law and the proximity fuze |
| `aim9x-fmu` | the host-interface variant for `apps/web`: the target is supplied by the host, the fuze does not stop the instance, and the pose, air data, fins and status are FMU outputs |

## The plant

The body is a `stdlib:spatial/Free3D` joint from the world to a 1-junction. On the junction are

- a project `VariableInertia3D` (a modulated spatial inertia) and the stdlib `CoriolisSpatial` and `DfSpatial`;
- six `MR` elements on the joint's drive axes, with `r = -dm/dt` on the linear components and `r = -dJ/dt` on the angular ones: the propellant leaves with its own momentum, so the linear law is `m dv/dt = F` and the angular law is `J dw/dt = M` (the rocket example's variable-mass bond graph);
- three `ExternalWrenchSpatial` sources: `Aero`, `Motor` and `Weight`.

`MissileAero` is the constitutive law of the airframe:

$$C_N(\alpha) = C_{N\alpha}(M)\,\alpha + C_{N3}\,\alpha^3, \qquad C_D = C_{D0}(M) + k\,(C_N^2 + C_{N\beta}^2)$$

$$C_m = -0.8\,C_N + C_{m_q}\frac{q d}{2V}, \qquad C_n = +0.8\,C_{N\beta} + C_{n_r}\frac{r d}{2V}, \qquad C_l = C_{l_p}\frac{p d}{2V}$$

The canards are four fins at 45°, 135°, 225° and 315°. A fin at azimuth $\phi$ has its normal
along $(-\sin\phi,\cos\phi)$ in the body $y$-$z$ plane, so the pitch, yaw and roll moments all
come out of the same geometry. A pure roll command deflects all four together: the tangential
forces cancel and the roll moments add.

The motor is a Mk. 36-class boost: 21 kg of propellant, 2.4 s, 235 s vacuum Isp, a 0.05 s
ignition ramp, a 0.15 s tail-off and the ambient-pressure correction $T = \dot m c_{vac} - p_a A_e$.
The nozzle gimbals by ±8° in two axes; the thrust and its moment are a single wrench.

## The control laws

Guidance commands a **specific force** (m/s², up and left). The autopilot turns it into a body
rate $q_{cmd} = a_z/V$, $r_{cmd} = a_y/V$, and a rate loop

$$dp = K_q\,(q_{cmd}-q), \qquad dy = K_q\,(r_{cmd}+r_{right}), \qquad dr = K_p\,(p_{cmd}-p) + \xi_r$$

with $K_q$ scheduled on $\sqrt{\bar q}$ (the canard moment per degree grows with $\bar q$, so a
1/qbar schedule would wind up at the low-qbar end of a launch). The roll loop holds wings level.

The TVC takes a small share of the acceleration error,
$\delta = -\,k_{tvc}\,m\,(a_{cmd}-a)/T$, through a rate limit and the 8° stop. It is only active
while the motor burns.

Proportional navigation is

$$\mathbf a = N V_c\,(\boldsymbol\omega_{LOS}\times \mathbf u_{LOS}), \qquad V_c = -\dot r$$

with the LOS rates from the seeker's inertial estimate
$\boldsymbol\omega_{LOS} = \mathbf d \times (\mathbf v_{rel} - \boldsymbol\omega_{body}\times\mathbf d)/|\mathbf d|^2$.
The command is faded in after a 1 s launch transient, lagged by 0.12 s, and limited to
$a_{frac}\,\bar q S C_{N,max}/m$ (60 % of what the airframe can deliver) as well as the published
60 g.

The seeker has a 90° field of view, a 60° gimbal stop, a 20 ms gimbal lag and a 180°/s rate
limit. Its range and irradiance are $r$ and $I/r^2\,e^{-kr}$, with the target's rear-aspect
increase. The proximity fuze fires at 15 m; the continuous-rod warhead's lethal radius is 20 m.

## Parameters and sources

`[pub]` published, `[est]` engineering estimate. The published numbers are from Wikipedia's
*AIM-9 Sidewinder* page (accessed 2026-11-12) and the sources it cites: mass 85.3 kg (188 lb),
length 3.02 m, diameter 0.127 m, span 0.2794 m, warhead 9.4 kg, maximum speed Mach 2.5+, range
1.0–35.4 km, Mk. 36 motor, imaging 128 x 128 FPA seeker with 90 deg off-boresight, two-axis TVC and
60 g turn capability.

| quantity | value | source |
| --- | --- | --- |
| launch mass / dry mass | 85.3 / 64.3 kg (21 kg propellant) | [pub] mass; propellant [est] |
| length, diameter, span | 3.02 m, 0.127 m, 0.2794 m | [pub] |
| inertia, roll / pitch / yaw at launch | 0.8 / 55 / 55 kg m² | [est] slender body |
| canard total area, normal-force slope | 0.020 m², 2.0 per rad | [est] small forward canards |
| canard arm, limit, rate | 1.10 m ahead of the CG, ±25°, 200°/s | [est] |
| lift: $C_{N\alpha}$ against Mach | 2.6–3.4 per rad, 0.6–1.2 | [est] slender body + tail fins |
| cubic lift $C_{N3}$ | 80 per rad³ | [est] vortex lift |
| zero-lift drag against Mach | 0.18 subsonic, 0.38 at M 1.2, 0.22 at M 3 | [est] |
| static margin | $C_m = -0.8 C_N$ | [est] |
| boost, Isp, exit area | 2.4 s, 235 s, 0.006 m² | [est] from the published mass and speed |
| TVC gimbal, rate | ±8°, 200°/s | [est] |
| seeker FOV, gimbal, rate | 90°, 60°, 180°/s | [pub] 90 deg off-boresight; the rest [est] |
| PN constant, acceleration limit | 4, 60 g | [pub] 60 g; N [est] |
| proximity fuze, lethal radius | 15 m, 20 m | [est] continuous-rod warhead |
| target: 150 m/s at 2 km, launch 400 m/s at 6040 m | | scenario choice |

The aerodynamic coefficients are small and readable engineering estimates, not a wind-tunnel
table. The example is about the control of the airframe; the checks hold the identities that
must hold (thrust, mass, lift, drag, atmosphere, seeker range and irradiance, the PN gain) and a
linearised short-period mode.

## Checks (`expected.json`)

`design/design.py` computes the reference numbers without running the model:

| check | reference | in bg-sim |
| --- | --- | --- |
| thrust at 1 s | $\dot m c_{vac} - p_a A_e$ = 19 744 N at 3000 m | within 0.1 % |
| burnout mass | $m_0$ minus the flow profile = 65.175 kg | 65.175 kg |
| lift at alpha 2°, 600 m/s | $C_N$ = 0.11055, $n_z$ = 0.274 g | 1e-6 / 1e-4 |
| atmosphere at 3000 m | qbar 163 642 Pa | 1e-6 |
| short-period mode | 3.44 rad/s, zeta 0.128 at the start; 6.11 rad/s, 0.146 at the fit condition | fitted 6.28 rad/s, 0.206 |
| seeker range and irradiance at launch | 2000.40 m, 0.3376 W/m² | 1 m, 1 % |
| PN gain | $N V_c$: `Guide/pn_gain / Guide/vc_out` = 4 | exact |
| fuze and warhead | `Status/fuze` 1, `Status/hit` 1 | both 1 |
| closest approach | `Status/min_range` 19.8 m at the fuze (the unfuzed trajectory passes inside 13 m) | |

The extra checks hold the fin and TVC stops, the alpha and roll envelopes and the command limits.
Run them with

    uv run examples/run_checks.py --only aim9x

## What to try

- `aim9x-airframe`: raise `dp_amp` and watch the ring leave the linear range; the cubic lift and
  the induced drag take over.
- `aim9x-control`: set `tvc_on` to 0 and compare the boost; the canards alone are slower to build
  the rate.
- `aim9x-intercept`: change `nav_N` (2 or 6), move the target with `tgt_x`, `tgt_y`, `tgt_z`, or
  give it a turn with `turn_rate`. The fuze time and the miss distance respond; the 15 m fuze and
  the $a_{frac}$ limit are what bound the miss.

## The host FMU (`aim9x-fmu`)

`aim9x-fmu` is generated from `aim9x-intercept` by `design/build_fmu_model.py` and exported by
`examples/export_aim9x.jl`; `apps/web/build_fmu.py missile` builds it into `apps/web/build/aim9x_fmu.fmu`.
It is the same weapon with a host interface:

- **inputs** (`ExportInput`): `target_north_m`, `target_east_m`, `target_down_m`, `target_vn_mps`,
  `target_ve_mps`, `target_vd_mps`, `target_ir_w`, `seeker_on`. The target is launch-relative NED:
  north and east from the launch point, down absolute (negative altitude), the same frame as the
  missile's `Free` pose. `ExternalTarget` maps it to the body's north/west/up world and feeds the
  seeker; there is no `TargetMotion` in this variant.
- **outputs** (`ExportOutput`): the model-frame pose and quaternion, attitude and path angles, air
  data, rates, mass, thrust, the four fin angles, seeker range/rate, `lock`, `fuze`, `hit`,
  `min_range_m` and `t_go_s`.
- **tuning**: `design/build_fmu_model.py` sets the weapon loop up for shots well off the nose (`TUNING`): the autopilot's acceleration feedback `K_acc` 20 and rate gain `K_q` 60, guidance from 0.3 s after launch, a 50 ms command lag and 80 % of the lift limit. The other models keep the library defaults (`K_acc` 0, the pure rate command).
- **parameters** (before initialization): `vt0`, `h0`, `alpha0`, `tvc_on`, `nav_N`, `a_max_g` with
  ranges, one instance per shot. A host sets them to the carrier's speed/altitude and its guidance
  limits; the model has no `StopSimulation`, so the host latches `fuze`/`hit` and retires the
  instance.
- **step**: 5 ms communication, RK4 at 1 ms (5 substeps). About 15-30 us per doStep and no allocation
  after instantiate; multiple instances share one extracted library and are freed together.

The F-16 app uses this model for both wingtip shots: it selects a drone in the seeker cue, sets the
launch state and the launch-relative target data, steps the instance every 5 ms, and draws the body,
canards and plume from the outputs. See `apps/web/README.md`, "In the game".

## Limitations

- The aerodynamic data are estimates. The canards are small, the static margin is one value and
  there is no Mach-dependent centre of pressure; the model is for control studies, not for
  predicting a real AIM-9X envelope.
- The body stays at its centre of mass as the propellant drains; the centre-of-mass shift and
  the jet damping are not modelled.
- The seeker is a point-source model with range/irradiance and a gimbal, not an image. There is
  no flare or IRCCM in this version; the 128 x 128 FPA and the counter-countermeasures are
  described in the README but not modelled.
- The autopilot is a rate loop; it does not hold a calibrated load factor or altitude on its own.
  The guidance command includes the gravity component and the $a_{frac}$ lift limit, which is
  what keeps the intercept in the airframe's envelope.
- The target is a kinematic source (position, heading, speed, intensity); it has no dynamics of
  its own.
- The 3D scene shows the missile itself; the target is not drawn in 3D (its track is in the plots).

## Files

| file | content |
| --- | --- |
| `design/data.py` | every number and its source tag |
| `design/design.py` | the analytic reference numbers (`design.json`) |
| `design/build_model.py` | the three models, the scene and `expected.json` |
| `design/build_fmu_model.py` | the host-interface `aim9x-fmu` from `aim9x-intercept` |
| `design/make_meshes.py`, `meshes/*.glb` | the missile, canard and plume meshes (`uv run examples/aim9x/design/make_meshes.py`) |
| `scenes/aim9x.sdf` | the 3D scene: the missile at the origin, its canards, the plume and the reference grid |
| `library/MissileAero.jl`, `MissileMotor.jl`, `MissileWeight.jl`, `VariableInertia3D.jl` | the plant |
| `library/MissileAirData.jl`, `ISA1976.jl` | air data and atmosphere |
| `library/MissileAutopilot.jl`, `FinMixer.jl` | the control laws |
| `library/MissileSoloView.jl` | the 3D attitude and plume scale |
| `library/ExternalTarget.jl` | the host target input of `aim9x-fmu` |
| `library/MissileSeeker.jl`, `ProNav.jl`, `TargetMotion.jl`, `MissileStatus.jl` | the weapon loop |
| `design/run_model.jl`, `readrun.py` | iterate on a model without the backend |

    uv run examples/aim9x/design/design.py
    uv run examples/aim9x/design/make_meshes.py
    uv run examples/aim9x/design/build_model.py
    uv run examples/aim9x/design/build_fmu_model.py
    uv run examples/run_checks.py --only aim9x
    uv run tools/example_docs/build.py --only aim9x
    julia --project=julia/BGSim examples/export_aim9x.jl <out>   # the host FMU
