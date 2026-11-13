# T8X spider robot

An eight-legged **T8X-class** robot as a control model: a 6-DOF body, eight legs with three
servo joints each (24 joint coordinates), a Hunt-Crossley foot contact, an analytic leg IK
and an alternating tetrapod gait. Two models show the same plant at rest and walking:

| model | what it shows |
| --- | --- |
| `spider-stand` | the static stance, the analytic IK, the eight foot loads, the servo torques, the body height and level |
| `spider-walk` | the gait, the servo/contact loop, a scripted forward / turn / crab command profile |

The example follows the T8X architecture: eight legs, three servos per leg (coxa yaw,
femur and tibia), a Wi-Fi controller running the proprietary Bigfoot inverse-kinematics
and gait engine. The real robot has 26 servos, the last two in the abdomen; the abdomen
articulation is not modelled here.

## The plant

The body is a `Free3D` joint and a `RigidBody3D` on a bond graph. The eight legs are
instances `Leg1`..`Leg8` of one library subsystem, `library/SpiderLegUnit.bgsub.json`: the
leg IK (`IK`), the reduced leg (`Joints`, block `SpiderLeg`) and the wrench on the body
(`Wrench`). An instance sets only its hip position, its hip yaw and the foot friction
(pinned `Joints/mu`, set to the global `mu_foot`), so a leg signal is `Leg1/Joints/q1` or
`Leg1/IK/reach`.

### The leg reduction and what it leaves out

The leg is **quasi-static and signal-coupled**, not a multibody chain:

- the body block carries the mass and inertia of the whole robot with the legs locked in
  the nominal stance (`design.py`, `composite_body`): 1.020 kg and principal inertias
  0.01017 / 0.01169 / 0.02016 kg m² about the body origin. The body alone is 0.46 kg and
  0.00115 / 0.00205 / 0.00295 kg m²; the eight locked legs add 0.56 kg and
  0.00902 / 0.00964 / 0.01721 kg m². The products of inertia vanish by the mirror
  symmetry of the legs. The composite centre of mass is 4.4 mm below the body origin; the
  block puts it at the origin (its weight acts there, see below), which shifts the roll and
  pitch inertia by m d² = 2e-5 kg m² (0.2 %);
- each leg has its three joint angles and rates as states. A joint carries its servo
  torque, the gravity of the three links at their centres (a link-centre gravity Jacobian)
  and the foot contact force through the leg Jacobian. The joint inertias are the diagonal of
  the leg's mass matrix at the nominal pose, from the link masses (`design.py`,
  `joint_inertias`): 9.72e-4, 5.16e-4 and 1.73e-4 kg m². The rotor inertia of the servo is not
  published and is not included;
- the body receives from each leg the contact force at the true foot point and the moment
  of the leg's link weights about the body origin, with the links where the joint angles put
  them. The body block applies the whole weight at the origin, so the weight acts on the
  body exactly where the links are, in the same way as in the joint equations. In the
  static stance the eight foot loads add up to the total weight, 10.003 N (checked).

What the reduction neglects, with sizes from `design.json` and the walk run:

- the inertial forces of a swinging leg are not applied to the body: the link masses of one
  leg reach 0.83 N peak relative to the body in the swing (up to about 3.3 N for the four legs
  of a group, a third of the weight), at liftoff and touchdown, zero on average;
- the servo torques do not react on the body; the reaction of a swinging coxa is
  I1 q1'' = 0.038 N m peak per leg. The eight coxa inertias together (0.0078 kg m²) are
  locked into the composite body instead, which holds 0.0202 kg m² about z;
- the joint equations leave out the body acceleration and the coupling terms of the leg
  mass matrix. In the walk the body's vertical acceleration reaches 2.2 m/s² (the load
  swings between 7.4 and 12.3 N), a fifth of g acting on link gravity torques of about
  0.04 N m;
- in stance the tibia is held at the foot, so locking it into the body overstates the
  moving mass by up to its own 0.2 kg (eight tibias) in the worst direction.

The reduction keeps the 24 servo coordinates, the true foot point and contact force, the
servo limits and the static load paths; it is meant for gait and servo-load studies, not for
the fast swing-leg dynamics. A 16 s walk took 18 to 28 s of wall time in the backend on
the development machine.

### Data

| quantity | value | source |
| --- | --- | --- |
| coxa, femur, tibia | 0.045, 0.110, 0.140 m | [est] from the photographs |
| hip positions | four per side, ±0.072 / ±0.024 m along x, ±0.032 / ±0.040 m along y | [est] |
| nominal foot | 0.16 m from the hip, commanded body height 0.110 m | [est] |
| link masses | 0.015 + 0.030 + 0.025 kg per leg, centres at the link middles | [est] |
| total mass | 1.020 kg | [est]; the T8 is 2.2 lb (1.0 kg) [pub] |

The contact is the law of the stdlib `ContactPoint`, written out in the leg block (the leg
has no bond to the foot point):

$$F_n = \sigma\,F_c,\quad F_c = \mathrm{softplus}\big(k\,x\sqrt{x/x_{ref}}\,(1+c\,\dot x)\big),\qquad
F_t = \mu F_n \tanh(v_t/v_s) + b_t v_t$$

with the smooth positive penetration $x$, its slope $\sigma = dx/d\delta$ (the gate that makes
the force vanish off the floor, as in `ContactPoint`), $k=1500$ N/m, $x_{ref}=1$ mm,
$c=3$ s/m, $\mu=0.8$, $v_s=10$ mm/s and a $10^{-5}$ m smoothing length.

### Servo

The original T8 used 26 Hitec HS-35HD servos on a 4.8 V NiMH pack (New Atlas, 2013). The
HS-35HD is rated 11 oz-in = 0.078 N m and 0.10 s/60° at 4.8 V (Hitec data as listed by
ServoDatabase and retailers). That is below what this model's estimated 1.02 kg robot needs:
0.102 N m at the femur standing on eight feet and 0.249 N m standing on four
(`design.json`). The T8X servos are "Robugtix servo motors" with no published rating. The
model therefore uses the next Hitec class that carries the load, the **HS-82MG** (Hitec
data as listed by Horizon Hobby, Multiplex and retailers): 3.4 kg cm = 0.333 N m and
0.10 s/60° at 6.0 V (2.8 kg cm and 0.12 s/60° at 4.8 V), 19 g. It is a substitute for an
unpublished servo, not a T8X datum.

The servo is an analog P loop on a DC motor:

$$\tau = \mathrm{clamp}\big(k_p (q_f - q),\,-\tau_s,\,\tau_s\big) - \frac{\tau_s}{\omega_0}\,\dot q$$

with the stall torque $\tau_s = 0.333$ N m, the no-load speed $\omega_0 = 10.47$ rad/s (so the
back-EMF damping is 0.032 N m s/rad, the torque-speed line of the datasheet), no derivative
term, and $k_p = \tau_s / 1° = 19.1$ N m/rad (full duty beyond one degree of error, an [est]
for the proportional band, which Hitec does not publish). The command passes a 12 ms
first-order filter (a 50 Hz servo frame) and the gear train has 0.005 N m s/rad of viscous
friction [est]. With the light back-EMF damping the stance is a lightly damped spring: in
series with the contact each foot gives 849 N/m vertically, so the body rings at about 13 Hz
on eight feet and 9 Hz on four, and the roll mode at 17 Hz (`design.json`).

## The control

- **Gait.** An alternating tetrapod (L1, L3, R2, R4 against L2, L4, R1, R3) with the cycle
  `T = 0.8 s`. Each foot command has a **constant-velocity stance** for 70 % of the cycle
  (`duty = 0.7`: the foot moves from `+A` to `-A` at exactly `-v` relative to the body) and
  a **swing** for 30 % (0.24 s): a cubic Hermite return whose end slopes equal the stance
  velocity, and a lift `16 u² (1-u)²` times 35 mm (the lift term has zero height and
  zero vertical speed at both ends; the `z_unload` hand-over ramp adds 3.2 mm and a nonzero
  slope there). The stride is `A = v duty T / 2` with `v = v_cmd + ω × r` at the nominal foot,
  so the commanded speed is the delivered speed when the feet do not slip, and the same gait
  walks, turns and crabs. The phases come from `atan2` of the clock, not `mod` or `floor`,
  and the stance/swing switch is a 0.2 ms `tanh` blend of two branches that agree in
  position and velocity there, so the gait makes no simulation events. (An `ifelse` switch,
  four legs on the same root, chattered at a touchdown in a backend run that followed other
  runs: W206 at t = 4.00984 s.)
- **Load hand-over.** Each group is down for 0.16 s at either end of its stance while the
  other group is also down. In those double-support phases the foot command rises smoothly
  (`(2s/duty - 1)^8`) to 3.2 mm above the stance height at touchdown and liftoff: the height
  at which an unloaded foot just touches the floor while the other group carries the body
  (`design.py`, `z_unload`). The foot therefore lands and leaves at zero load and the load
  moves between the groups gradually; without it (`z_unload = 0`) the load swung between
  3.6 and 19.3 N and the forward speed by 0.064 m/s peak to peak. The swing adds the matching slope
  term, so the commanded apex is 43.6 mm above the stance height.
- **Attitude.** The foot targets move by `k_att (roll_f y - pitch_f x)`: a body rolled
  left side up raises the left foot targets, which lowers the left side. `roll_f` and
  `pitch_f` pass a 0.1 s filter. `k_att = 1` doubles the static roll and pitch stiffness
  (336.7 against 168.3 N m/rad). The filter is what makes it work: the linear roll model of
  `design.py` gives the 17 Hz roll mode a decay rate of 12.0 1/s without the loop, 9.9 1/s
  with `k_att = 1` through the filter, and an unstable mode (growth 12.0 1/s) with the
  same gain unfiltered, because the 12 ms servo filter lags the loop at that frequency.
- **Height.** There is no height loop (`k_h = 0`): the body rides 1.5 mm below the
  commanded height on eight feet and 2.9 mm below on four (the contact penetration plus the
  servo compliance, `design.json`).
- **IK.** For each leg, `q1 = atan2(y, x)`, `q3 = -acos((d²-b²-c²)/(2bc))`,
  `q2 = atan2(z, x) - atan2(c sin q3, b + c cos q3)`. A target outside the reachable
  annulus is projected onto it; `reach` falls from 1 to 0 over the last 20 mm before either
  the outer (straight leg) or the inner (folded leg) limit.

The command profile of `spider-walk` is a `TimeTable` with samples every 2 s, linear in
between: the gait marches in place for 2 s (the commands are zero but the feet step), the
forward command ramps to `vx_cmd` by 4 s, a left turn ramps in from 4 s to `wz_cmd` = 20 deg/s
at 6–8 s and out by 10 s while the robot walks on, the forward command falls to 0.3 `vx_cmd`
and a left crab of `vy_cmd` = 0.06 m/s comes in by 10 s and goes out by 14 s, and the last
2 s are straight forward walking. The gait ramps every command in with `1 - exp(-t/0.8 s)`.
`vx_cmd`, `vy_cmd` and `wz_cmd` scale the profile.

## Parameters and sources

`[pub]` published, `[est]` engineering estimate, `[ds]` datasheet. Accessed 2026-11-12:

- Robugtix T8X product and store pages: eight legs, 26 servos ("Robugtix servo motors"),
  the Bigfoot engine;
- T8X programming tutorial #2: walk command 0–200 mm/s with 100 as stop (100 mm/s per 100
  counts), walk-turn command 0–200 deg/s with 100 as stop;
- T8X FAQ: 20–60 min on one battery charge;
- Open Electronics, Spiderbot article: 2.2 lb (1.0 kg) for the T8, the same mechanism;
- New Atlas, 2013: the T8 uses 26 Hitec HS-35HD servos and a 4.8 V NiMH pack;
- HS-35HD and HS-82MG ratings: Hitec data as listed by ServoDatabase, Horizon Hobby,
  Multiplex and retailers.

The leg lengths, body size, inertias, link masses, the contact data and the servo's
proportional band are `[est]`; the photographs show a body about 0.20 m long and a leg span
about 0.42 m. The example is about the control of a multi-legged walker, not about predicting
the exact T8X envelope.

## Checks (`expected.json`)

`design/data.py` and `design/design.py` compute every reference without running the model:
the leg is evaluated as an independent rotation-matrix chain with finite differences, the
statics by Newton on the joint equilibrium, the roll stiffness and decay from a linear model,
and the walk path by integrating the command profile. The table lists each reference and
what the model gives (direct runs; the checker reads the same signals).

| check | reference (`design.json`) | in bg-sim |
| --- | --- | --- |
| IK of all eight legs at t = 0 | Python IK, `q = (0, 15.67, -101.95) deg` | within 1e-9 rad |
| static load | `m g = 10.003 N`, never above it by 1 % | 10.0028 N, peak 10.0029 N |
| body height | 0.110 m minus 0.886 mm penetration and 0.621 mm servo sag = 0.10849 m | 0.108493 m |
| standing servo torques, all legs | femur −0.1019 N m, tibia −0.0112 N m, coxa 0 | −0.10193 / −0.01118 / 0.0000 N m |
| standing joint angles | IK command plus `tau/kp`: q2 0.27877 rad | 0.278774 rad |
| foot penetration | 0.886 mm | 0.886 mm |
| roll stiffness (0.3 N m roll moment) | `M / K_roll` = 0.0511 deg (±10 %) | 0.0510 deg |
| roll decay from a 1° start | below 0.05° after 1 s (decay 9.9 1/s) | 0.0017° at 0.5 s, 2e-5° after 1 s |
| walk path at 16 s | x 0.319 m, y 0.701 m, yaw 79.96° (±5 % of the 1.13 m path / the turn) | 0.324 m, 0.691 m, 79.68° |
| forward speed, 14.4–16 s | 0.100 m/s (±5 %) | 0.1001 m/s |
| forward-speed ripple | 0 for the constant-velocity stance (bound 0.03 m/s p-p) | 0.015 m/s p-p |
| feet down, 14.4–16 s | 8 × 0.70 = 5.6 (±0.3); never fewer than four | 5.40; 4.0 to 8.0 |
| swing apex | 40.5 mm (±1.5 mm) | 40.2 mm |
| mean load and body height | 10.003 N (±2 %); 0.10778 m (±1.2 mm) | 10.05 N; 0.10768 m |
| servo torque, all 24 joints | HS-82MG stall 0.333 N m | 0.255 N m peak (Leg3 femur) |
| leg workspace, all legs | `reach` ≥ 0.9 | 1.0 for the whole run |

The roll checks run the stand model twice more with an override: once with a 0.3 N m roll
moment on the free joint (`FreeSe1/e`) and once with `roll0 = 1` deg. With the old sign of
the attitude correction both fail: the loop then cancels the stance's own roll stiffness
(`K_roll = 0`), so the roll moment tips the body steadily (2.7° at 3 s and still growing) and
the 1° start stays at 0.06°.

Run them with

    uv run examples/run_checks.py --only spider

## What to try

Each item was run once; the numbers are from those runs.

- `spider-stand`, `h_stand = 0.09`: the start pose is built for 0.110 m, so the IK command
  jumps at t = 0. The body drops 20 mm in 0.1 s, the feet leave the floor for a moment and
  land at four times the weight (40 N); the femur servo saturates (0.43 N m peak including
  the back-EMF term). The body settles at 0.0885 m with the femur at 0.104 N m and the tibia
  at 0.020 N m. Set `H_STAND` in `design/data.py` and rebuild for a smooth start at another
  height.
- `spider-stand`, `roll0 = 1`: the body starts rolled 1° and is level again within 0.5 s
  (0.0017°), with one overshoot of 0.03° at 0.1 s.
- `spider-walk`, `vx_cmd = 0.18`: the stride grows with the command and the delivered speed
  follows it, 0.181 m/s over the last two cycles; the path ends at (0.77, 1.21) m and the peak
  servo torque rises from 0.255 to 0.269 N m.
- `spider-walk`, `gait_lift = 0`: the swing keeps only the hand-over lift, so the feet clear
  the floor by 5.7 mm instead of 40 mm. On the flat floor the path and the speed hardly
  change (0.101 m/s; the path ends within 1 mm): the gait does not need the lift to walk,
  only to step over things.
- `spider-walk`, `mu_foot = 0.1`: the stance feet creep faster (95th percentile of the stance
  foot speed 21 instead of 7 mm/s) and the traction saturates at 0.14 of the normal load, but
  the constant-velocity stance needs traction mainly at the load hand-over, so the speed stays
  at 0.102 m/s and the path ends within 1 cm of the nominal one. The peak femur torque rises
  to 0.29 N m.

## Limitations

- The legs are quasi-static and signal-coupled (see "The leg reduction"): the swing-leg
  inertia and the servo reactions do not reach the body, and the joint equations use the
  diagonal mass matrix of the nominal pose.
- The abdomen articulation (the two extra T8X servos) is not modelled.
- The gait is a fixed tetrapod with a constant-velocity stance, not the real Bigfoot
  trajectory. It has no body-height planner and no terrain adaptation.
- The contact is a point pad with a Hunt-Crossley spring and regularised Coulomb friction;
  it has no foot shape, no rolling and no stiction beyond the regularisation.
- The leg IK ignores the joint stops: the model's joint coordinates are unconstrained, and
  the `reach` signal only reports the annulus limits. The scene joints show the same
  coordinates and have display limits.
- The servo is the HS-82MG substitute (see "Servo"); its proportional band and rotor inertia
  are estimates or left out. Battery, servo current and thermal limits are not modelled.

## Files

| file | content |
| --- | --- |
| `design/data.py` | every number, its source tag and the analytic IK/FK |
| `design/design.py` | the derived plant data and the reference values (`design.json`) |
| `design/build_model.py` | the two models, the leg subsystem, the scene and `expected.json` |
| `design/run_model.jl`, `design/readrun.py` | direct runs without the backend, for design work |
| `design/make_meshes.py`, `meshes/*.glb` | the body and the three leg meshes |
| `scenes/spider.sdf` | the 3D scene: body, eight three-link legs, a floor that covers the walk |
| `library/SpiderLegIK.jl`, `SpiderLeg.jl`, `SpiderGait.jl`, `SpiderStatus.jl` | the example blocks |
| `library/SpiderLegUnit.bgsub.json` | the leg subsystem (`IK`, `Joints`, `Wrench`); generated by `build_model.py` |

Rebuild with

    uv run examples/spider/design/design.py
    uv run examples/spider/design/make_meshes.py
    uv run examples/spider/design/build_model.py
    uv run examples/run_checks.py --only spider
    uv run tools/example_docs/build.py --only spider
