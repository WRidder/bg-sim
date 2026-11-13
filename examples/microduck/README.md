# microduck

A simulation model of the **microduck** of Pollen Robotics: a 25 cm, 0.74 kg biped with 15 Dynamixel
XL330-M288-T servos (14 of them in the walking policies, the mouth servo is left out) that walks
with reinforcement-learning policies trained in MuJoCo (mjlab) against Rhoban's BAM servo model.
The example is built around two **library subsystems**: `XL330` (`library/XL330.bgsub.json`, the
servo with its gear play) and `XL330Rigid` (`library/XL330Rigid.bgsub.json`, the same firmware,
winding and friction on a rigid gear, for the robot a policy drives and an FMU runs in real time).
A third, `XL330Backlash` (`library/XL330Backlash.bgsub.json`), is `XL330Rigid` with the gear play
the policy was trained with, built as the training simulator builds it.
The body repeats too: in the four robot models every jointed body is an instance of `Link`
(`library/Link.bgsub.json`: its two frames, the rigid body and the pose band, with the joint and
the servo beside it in the model), and every sole and bumper point is an instance of
`GroundContact` (`library/GroundContact.bgsub.json`).

The aim is a model in which the actuator behaves the way the policies were trained to expect,
so that a policy can move between this model and the real robot. **That transfer is not
demonstrated here**, and nothing here is validated against a real robot (see *Limits* below).
What is checked is the actuator against the BAM simulator, the torque-speed curve against its
analytic form, the held robot against a quasi-static gravity reference, the standing robot
against a behaviour the microduck authors report from their own simulation, and the exported
FMU against bg-sim. The published walking policy `velstand.onnx` drives the FMU in the browser
demo `apps/web/microduck` (see *The FMU and the policy*).

Sources (read as data, Apache-2.0):

| tag | what | where |
| --- | --- | --- |
| BAM-A | XL330 M6 fit used for training | github.com/Rhoban/bam `bam/params/xl330/m6.json` at 62bd8ce (branch `mjlab_frictionloss`, pinned by microduck_rl's `uv.lock`) |
| BAM-B | newer XL330 M6 refit, with identified delay | Rhoban/bam `main` at b41c117f (2026-08-01); comparison only |
| BAM-CODE | firmware law, current limiter, friction, simulator | Rhoban/bam `bam/dynamixel/actuator.py`, `bam/actuator.py`, `bam/model.py`, `bam/simulate.py` (62bd8ce) |
| ROBOTIS | XL330-M288-T e-manual | emanual.robotis.com/docs/en/dxl/x/xl330-m288/ |
| DUCK | robot firmware settings and design notes | github.com/pollen-robotics/microduck at 039a1a8 (`duck-control/src/model.rs`, `bus.rs`, `deploy/robotd.toml`, `docs/design/`) |
| RL | training setup, MJCF, test bench | github.com/pollen-robotics/microduck_rl at 0daab16 (`robot/microduck_constants.py`, `robot/microduck/robot_groundcontact.xml`, `robot/xl330_test_bench/`) |
| BAM paper | friction models | Duclusaud, Passault, Padois, Ly, arXiv:2410.08650 (ICRA 2025) |

## Models

| model | what | run time (this machine) |
| --- | --- | --- |
| `xl330-step` | one XL330 on the microduck_rl test bench (100 g arm, CoM 96.6 mm), goal 0 -> 1 rad at 0.1 s and back at 0.9 s, backlash pinned to 0 | ~15 s |
| `xl330-torque-speed` | one XL330 with its horn turned by a speed source from -8 to 20 rad/s, goal far ahead | ~20 s |
| `microduck-hang` | the robot held by the trunk, 14 XL330 on a 2S battery bus; at 0.2 s the legs step from HOME to a 15 mm squat pose | ~2 min |
| `microduck-stand` | the robot released 0.1 mm above the floor at the STAND pose, 4 contact points per sole, the servos holding HOME (no policy) | ~2 min |
| `xl330-rigid-step` | `xl330-step` with `XL330Rigid` (the joint carries the armature) | ~15 s |
| `xl330-rigid-torque-speed` | `xl330-torque-speed` with `XL330Rigid` | ~20 s |
| `microduck-policy` | the robot a policy drives and the FMU exports: rigid joints, 14 `XL330Rigid` on an ideal supply, soles loaded at HOME, bumper points on trunk, head and shins; 14 joint targets and the gain in, sensors out. By itself it holds HOME and steps to the squat at 0.3 s | ~4 min |
| `xl330-backlash-step` | `xl330-rigid-step` with `XL330Backlash`, play centred at the start; checked against MuJoCo running the same bench | ~20 s |
| `xl330-backlash-reversal` | `XL330Backlash` turning the bench arm in a horizontal plane (no gravity torque), goal 0 -> 0.3 rad at 0.1 s and back at 0.6 s, so each reversal crosses the play; checked against MuJoCo | ~20 s |
| `microduck-policy-backlash` | `microduck-policy` with `XL330Backlash` in every joint (play pinned per joint from the training MJCF), 0.6 s | ~4 min |

## The XL330 subsystem

```
q_goal -> Latency (t_latency) -> P law kp_fw * 4096/(2 pi)/(256*885) -> current-limit window
       -> PWM limit +-1 -> duty
vbus (0-junction) -> H-bridge MTF(duty) -> winding 1 [R] -> EMConverter kt/288.4
       -> rotor 1 [I = armature/288.4^2] -> gear TF 1/288.4 -> output 1 [BAM M6 friction]
       -> TorqueSensor -> backlash (2 deg, smooth) -> horn 1 [encoder]  -> port horn
```

* **Ports**: `q_goal` (in, rad), `vbus` (Electrical power), `horn` (Rotation power); outputs `q`
  (encoder), `dq`, `i`, `tau_m`, `tau_l` (transmitted), `duty`.
* **Pins** (set per instance): `PGain/k`, `Friction/scale`, `RotorInertia/i`, `Backlash/gap`,
  `Latency/initial`; starts `Encoder/phi`, `Backlash/phi`. These are the per-servo domain
  randomisation knobs of microduck_rl (friction 0.9..1.1, armature 0.9..1.1, backlash, gains).
* **Globals it reads** (every model defines them): `kp_fw`, `i_limit`, `t_latency`; the models also
  define `v_bat` (and the robot `r_bat`).
* **Project blocks**: `library/BamFriction.jl` (the M6 friction law as a nonlinear R) and
  `library/SmoothBacklash.jl` (the dead-zone law of `stdlib:rotation/GearBacklash` with its kinks
  smoothed, because 14 event-driven backlashes and friction kinks next to rest made the robot runs
  impractically slow).

## The XL330Rigid subsystem

```
q_goal -> Latency -> P law kp * 4096/(2 pi)/(256*885)  (kp an input) -> current-limit window -> PWM limit
vbus (0-junction) -> H-bridge MTF(duty) -> winding 1 [R] -> MotorGY kt -> horn 1 [BAM M6 friction] -> port horn
the friction's load torque: kt i - tau_f, sampled every 5 ms (LoadSample)
```

What BAM in mjlab does, and what `velstand.onnx` was trained on, apart from the backlash:

* **Rigid gear, no backlash.** The armature is the joint's (`Revolute3DRigid` `Ja` = global
  `armature`, MuJoCo's `armature`); the motor torque acts at the output (`library/MotorGY.jl`,
  a gyrator Electrical -> Rotation with `k_motor`). No rotor speed, no gear spring, no backlash
  state. Training adds 2 deg of backlash; this model does not (see *Limits*).
* **The encoder is the joint angle** (input `q`).
* **The friction reads the load torque of 5 ms ago** (`LoadSample`, a zero-order hold), as BAM in
  mjlab reads the previous physics step. That removes the algebraic loop of `XL330`.
* **The gain is an input** (`kp`, the Position P Gain register): the robot writes it every tick.
* **Pins**: `Friction/scale`, `Friction/ws`, `Latency/initial`. Globals: `i_limit`, `t_latency`,
  `k_motor`, `r_motor` (and the joint's `armature`).

Against the BAM simulator on the bench (`xl330-rigid-step`) the largest encoder difference is
10.4 mrad (`XL330`: 16 mrad), the rest angle -0.017339 vs -0.017357 rad and the holding torque
0.0492 vs 0.0508 N m; the torque-speed curve (`xl330-rigid-torque-speed`) agrees with the
analytic one plus the armature torque of the ramp within 0.42 mN m.

## The XL330Backlash subsystem

`library/XL330Backlash.bgsub.json`: `XL330Rigid` with the gear play of microduck_rl's backlash
robots, which is what velstand was trained on (`Mjlab-VelStand-Rough-Backlash-MicroDuck`:
`robot/microduck/add_backlash.py`, `tasks/backlash.py`, `actuator/friction_dr_bam.py`
`BacklashEncoderBamActuator`, all at 0daab16).

```
... MotorGY kt -> gear 1 [armature, BAM M6 friction, back-EMF speed] -> MjBacklash (2 deg) -> horn 1 [encoder] -> port horn
```

What microduck_rl does, and what this subsystem does:

* **A passive hinge after each servo joint.** `add_backlash.py` inserts `passive_<joint>_backlash`
  on the same body and axis: range +-1 deg, armature 0.001 kg m^2, damping 0.01 N m s/rad, no
  friction loss, `solreflimit` 0.01 1, `solimplimit` 0.95 0.999 0.0001 0.5 2. The servo joint is
  the motor side: BAM drives it, its armature is BAM's, the back-EMF and the friction use its
  speed. Here the gear junction carries the armature (`RotorInertia`, global `armature`), the
  motor torque, the friction and the back-EMF speed (output `dq_gear`); the joint
  (`Revolute3DRigid`) carries none.
* **The encoder reads through the play.** The firmware P law and the `joint_pos`/`joint_vel`
  observations read main + backlash (`BacklashEncoderBamActuator`, `mdp.py`
  `joint_pos_rel_backlash`): `q` is the joint angle, after the play.
* **The stop is MuJoCo's soft joint limit** (`library/MjBacklash.jl`). A MuJoCo limit row pushes
  with f = max(0, aref - a)/R, aref = -b v - k d p (b = 2/(dmax tc), k = 1/(dmax tc zeta)^2, d the
  solimp impedance, R = (1 - d)/d `invw`, `invw` the hinge's `dof_invweight0`). Inside a stop the
  play follows the critically damped reference (10 ms), statically as a spring that stiffens from
  about 200 to 1.1e4 N m/rad over the first 0.1 mrad (a load of 0.3 N m sinks it about 0.09 mrad),
  and an arriving play overshoots the stop by about its speed times tc/e (5 mrad
  in the step bench). Written literally, that law switches an inertia on and off with the contact,
  which a linearly implicit solver cannot step through; `MjBacklash` carries the reference rate as
  a state instead (it tracks the play rate while no stop pushes and follows aref while one
  does), and a stop that pushes holds the play rate on it with the damper R^-1 b. The solimp
  curve is clamped to [dmin, dmax] with min/max, because a fixed-step export holds a branch for
  the whole step and an extrapolated d above 1 turns the damper negative. Statically and in the impact
  this is MuJoCo's law. That damper is stiff (up to 2e5 1/s), so whether a stop pushes is a mode
  held between the ticks of a 1 ms clock: it closes when the play is in the stop and the force it
  would push with exceeds 1 mN m, and opens when that force falls below -1 mN m (MuJoCo's
  max(0, .), with a hysteresis against chattering) or the play leaves the stop. The fixed-step
  FMU then forms every step's Jacobian with the mode the step uses; with the contact switched
  smoothly instead, the export at 1 ms (and at 0.5 and 0.25 ms) blew up at the first impact on
  the bench, and only 0.1 ms got through. The cost of the clock: a play arriving between ticks goes
  up to its speed times 1 ms deeper before the stop closes, and a stop the load pulls away from
  holds for up to 1 ms.
  `Backlash/invw` is pinned per joint from MuJoCo (`design/mjcf_play.py` ->
  `design/play_data.json`: 802.8 to 988.3 1/(kg m^2) for the 14 play hinges of the training robot).
* **The play starts centred**, as microduck_rl resets it (`BACKLASH_HOME_FRAME`).
* **Pins**: `Friction/scale`, `Friction/ws`, `Latency/initial`, `Backlash/gap`, `Backlash/invw`;
  start `Backlash/phi`.

Against MuJoCo itself running the same bench (`design/backlash_bench.py`: the test arm on the two
hinges of `add_backlash.py`, BAM applied each 0.5 ms step as `BacklashEncoderBamActuator` does,
implicitfast; stored in `design/backlash_reference.json`):

* `xl330-backlash-step` (the `xl330-step` goal, gravity on the arm): play angle within 0.26 mrad
  at the times checked, where it rests on a flank or overshoots it, including the first impact's
  overshoot at 0.15 s (22.74 vs 22.78 mrad, the flank at 17.45 mrad); largest play difference
  2.75 mrad, at 0.97 s, while the return swings the play across; encoder within 8.4 mrad over the
  whole run (the fast swings and the friction's rest angle, as for `xl330-rigid-step`), rest angle
  8.44 vs 9.66 mrad.
* `xl330-backlash-reversal` (0.3 rad out and back, the axis vertical, the play crossing under its
  own momentum on each deceleration): play angle within 1.8 mrad throughout and 0.35 mrad at the
  times checked, encoder within 4.3 mrad.

The same two benches exported as FMUs (ROS34PW2, 1 ms) run through; the FMU and bg-sim differ by
up to 28 mrad on the step bench, as much as `xl330-rigid-step` exported the same way does
(already 3.7 vs 9.7 mrad at 0.13 s, before the play could matter; the cause, somewhere in how the
bench's internal goal pulse reaches the export, is not traced), so the play adds no difference of
its own there. The policy robot takes its goals as FMU inputs and is gated against bg-sim
separately (*The FMU and the policy*).

**In the policy robot** (`microduck-policy-backlash`: 14 `XL330Backlash`, `Backlash/invw` per
joint from the training robot, the play centred at the start). In bg-sim (Rodas5P, adaptive) it
passes the checks of `microduck-policy` (soles at half the weight at 0.25 s, the knee goal 20 ms
late, the current limit) and its own: the knee play rests on its flanks at 0.25 s (-+17.52 mrad,
the flank at 17.45 mrad), and no joint's play passes its flank by more than 6 mrad (the neck's
goes furthest, 5.0 mrad). The run (0.6 s) takes about 4 min. As an FMU it is not usable yet:

* **It does not match bg-sim.** `export_microduck_check.py --model microduck-policy-backlash`
  (ROS34PW2, 1 ms): standing, every joint angle within 6e-4 rad and the trunk height within
  7e-6 m, but `head_pitch_qd` 0.045 rad/s off (gate 0.025) and `trunk_wy` 0.011 rad/s (gate
  0.003); in the squat `left_hip_roll_q` 30 mrad off (gate 2 mrad), the trunk height 1.1 mm
  (gate 0.5 mm), `left_hip_roll_qd` 0.50 rad/s, `trunk_wz` 0.081 rad/s. The bg-sim references
  are converged (the squat at rtol 1e-6 and 1e-8 agrees to 1e-10), so the difference is the
  export's. At 0.5 ms it is not better: the squat passes the angle gates, but the standing run
  blows up at 0.44 s (`trunk_wy` 19 rad/s).
* **velstand on it** (Wasm in Node, the page's loop with the one-tick lag, 10 s per command, one
  run each): at 1 ms it stands at zero command (tilt at most 3.6 deg) and at 0.1 m/s; at 0.2,
  0.3 and 0.4 m/s it falls within a second (0.98, 0.58, 0.92 s), with launches no physical
  robot makes (tilt from 0.10 to 1.30 rad in one 20 ms tick, both feet off), and the FMU stops
  (fmi2Error) at 0.98, 4.44 and 1.30 s. At 0.5 ms it stands at zero command and falls at 0.2,
  0.3 and 0.4 m/s (8.2, 1.6, 4.3 s), stopping at 6.78 s at 0.4 m/s.
* **It costs 4 times the rigid robot**: 10.3 ms per 20 ms tick standing and 15 to 19 ms walking
  (Node, 1 ms), against 2.6 and 7.2 ms; at 0.5 ms 21 to 23 ms walking, slower than real time.

So the browser demo keeps `microduck-policy`, without gear play. What a fixed-step solver does
wrong with the play (the contact modes are sampled every 1 ms in both; the smooth contact laws
tried first blew up on the bench, see above) is not traced.

## Actuator parameters

| quantity | value | status | source |
| --- | --- | --- | --- |
| torque constant at the horn `kt` | 0.36601 N m/A | sourced | BAM-A |
| winding + driver resistance `R` | 2.8114 Ohm | sourced | BAM-A |
| armature (reflected rotor + gears) | 1.8077e-3 kg m^2 | sourced | BAM-A |
| M6 friction: base, Stribeck, load (motor/external), Stribeck load, quadratic, `dtheta_s`, `alpha`, viscous | 0.004771 N m, 0.004676 N m, 0.2668 / 8.5e-6, 1.07e-5 / 0.0808, 0.00997 / 0.00490 1/(N m), 2.890 rad/s, 8.683, 0.005360 N m s/rad | sourced | BAM-A |
| gear ratio | 288.4 | sourced | ROBOTIS (also the variant name M288) |
| encoder | 4096 counts/rev | sourced | ROBOTIS |
| P gain law | duty = kp (4096/2pi) e / (256 * 885) | sourced | BAM-CODE (divisor 256 "empirically observed", e-manual says 128) |
| P gain `kp_fw` | 200 | sourced | DUCK `robotd.toml`, RL `kp_fw` (standing 0.8x, limp 50) |
| I, D gains | 0 | sourced | DUCK `bus.rs` |
| PWM limit | 885 = 100 % | sourced | ROBOTIS, BAM-CODE |
| current limit `i_limit` | 1.75 A | sourced (training) | BAM-CODE `max_current`; the robot's impact-guard firmware uses 1.0 A, see *Limits* |
| supply `v_bat` | 7.4 V | sourced range | DUCK 2S Li-ion 6.6..8.2 V; RL trains on 6.5..8.2 V |
| latency `t_latency` | 20 ms | **assumed** inside the sourced range | RL delay 3..6 steps of 5 ms = 15..30 ms; BAM-B identifies 10.2 ms |
| delay-line tick | 5 ms | modelling choice | the 5 ms physics step of BAM and microduck_rl |
| backlash | 2 deg total | sourced (as a training assumption) | RL `add_backlash.py`, +-1 deg passive hinge, encoder read through it |
| tooth contact stiffness, damping | 100 N m/rad, 0.1 N m s/rad | **assumed** | not identified anywhere |
| friction regularisation `ws`, kink smoothing `ts`, `wb` | 2 mrad/s (20 mrad/s in `microduck-policy`), 0.1 mN m, 0.1 mrad | modelling choice | 20 mrad/s halves the cost of a bg-sim run of the policy robot; a servo held by its P law barely creeps either way |
| battery resistance `r_bat` | 0.1 Ohm | **assumed** | RL randomises a sag of 0..0.2 V per N m |
| bus capacitance | 1 mF | **assumed** | gives the bus voltage a state |
| `microduck-policy` supply | ideal source at `v_bat` (FMU parameter, 6.5..8.2 V) | modelling choice | no bus state; training randomises the voltage, not a sag model of this kind |

Derived (`uv run examples/microduck/design/xl330.py`): P stiffness 0.5544 N m/rad at 7.4 V and
kp 200 (the MJCF position actuators use kp 0.55), stall torque 0.963 N m without the limiter and
0.641 N m at 1.75 A, free speed 20.2 rad/s, back-EMF damping 0.0477 N m s/rad.

The two BAM fits of the same servo differ by 6 % in `kt`, 11 % in `R` and 13 % in the armature
(BAM-B: 0.3460 N m/A, 2.502 Ohm, 1.573e-3 kg m^2, friction base 0.0119 N m). The model uses
BAM-A because it is what the shipped policies were trained against.

## Robot parameters

Masses, inertias, joint frames and ranges come from the microduck_rl MJCF
(`robot_groundcontact.xml`, extracted by `design/extract_mjcf.py` into `design/robot_data.json`:
15 bodies, 0.7372 kg). The STAND pose is HOME of microduck (DEFAULT_POSITION) = HOME_FRAME of
microduck_rl. Each sole is reduced to its four extreme bottom vertices (sole STL meshes).
Ground contact: Hunt-Crossley, k = 2e4 N/m at 1 mm, c = 5 s/m, mu = 1.0 (the RL foot friction),
regularised over 1 mm/s (assumed except mu). The joints are `Revolute3D` with the MJCF ranges as
hard stops and 1e5 N/m, N m/rad compliance in the held directions.

Each of the 14 jointed bodies is a `Link` instance named `<joint>_link`, which pins the body's
frames, mass and principal moments; its joint `<joint>_joint` and its servo `<joint>` stay in the
model. Each contact point is a `GroundContact` instance (`FootL1`..`FootR4`, and the bumpers
`Bump<part><k>` of the policy robot), which pins the point's place and its friction coefficient;
the normal force is `FootL1/Contact/f_n`.

## Results

* `xl330-step` against the BAM simulator (`design/compare_bench.py`): largest encoder
  difference 16 mrad over the 1 rad move, all of it in the fast swings, where the 5 ms tick of
  the delay line ramps the goal step 2.5 ms early; the rest angle after the return agrees to
  0.2 mrad (-0.01720 vs -0.01736 rad).
* `xl330-torque-speed` against the analytic curve (`design/torque_speed.py`): horn torque
  within 0.3 mN m from -6 to 18 rad/s; flat at the current limit (0.641 N m motor torque) up to
  6.8 rad/s.
* `microduck-hang`: the knee goal reaches the firmware 20 ms late; no current above 1.75 A (the
  P gain asks for at most 0.87 A in this move); every encoder ends inside the friction band of
  the quasi-static gravity reference (`design/robot.py hang_reference`), short of it on the
  goal side by 15-20 mrad, as a joint that stops in its friction does.
* `microduck-stand`: the robot settles into its backlash and P stiffness and tips forward; the
  trunk passes 40 deg at 1.14 s. The microduck design notes report the same from their
  simulation ("tips past 40 deg within a second or two", `docs/design/robotd-design.md`
  2.4.2): HOME at walking gain is balanced only by a policy that keeps balancing it.

* `xl330-rigid-step`, `xl330-rigid-torque-speed`: see *The XL330Rigid subsystem*.
* `microduck-policy` by itself: at 0.25 s each sole carries half the weight (3.615 N, m g / 2 =
  3.616 N), the projected gravity has no sideways part, the knee target reaches the firmware
  20 ms after its step, the current stays under 1.75 A. HOME tips forward here too (40 deg near
  1.35 s, against 1.14 s for `microduck-stand`, whose gear play lets it sag first).

The checks are in `expected.json`, written by `design/checks.py`:
`uv run examples/run_checks.py --only microduck`.

## The FMU and the policy

`examples/export_microduck.jl` exports `microduck-policy` with the policy interface: the 14
`<joint>_target` and `kp` (ExportInputPass) are FMU inputs, the joint angles and rates, the trunk
gyro, quaternion, position, projected gravity and the two sole loads are outputs, `v_bat`
(6.5..8.2 V) and `i_limit` (1.0..1.75 A) are parameters with ranges; ROS34PW2 at a fixed 1 ms,
symbolic sparse Jacobian, static sparse LU, 20 ms communication step.
`uv run examples/export_microduck_check.py --out <dir>` builds it and compares it in fmpy with
bg-sim on two 0.6 s runs (HOME held; the squat, a gain change to 160 and back, a nod): every
joint angle within 1.7e-4 rad, the trunk height within 5.1e-6 m, the projected gravity within
4.3e-4, the sole loads within 0.014 N, every joint velocity within 3.2e-3 rad/s and every trunk
angular-velocity component within 2.5e-3 rad/s. The policy observes the velocities too, so they
are gated: 0.025 rad/s and 0.003 rad/s, a tenth of the observation noise velstand was trained
with (joint_vel ±0.25 rad/s, gyro ±0.03 rad/s). Zero allocations after instantiate, fmpy
validate clean, a supply outside its range refused. `apps/web/build_wasm.py microduck <fmu>`
makes it the plant of the browser demo.

**State selection.** The rigid joints make the model a higher-index DAE, and index reduction
picks which variables stay differential states. The model keeps minimal coordinates: the 14
joint angles and 14 joint rates (`<joint>_joint/qdot`), the trunk pose (7) and the trunk momentum
(6), 41 states, with the 299 body twists, momenta and constraint reactions algebraic. A tree in
these coordinates has no singular configuration. Until this was fixed in bg-sim's lowering, every
body momentum `ISpatial/P` declared `state = :prefer` at the same priority as the joint rate,
the tie went by variable name, and the model kept 20 child-body momentum components and no joint
rate. Recovering the rates from those momenta is pose-dependent: on the first forward command
the algebraic block's smallest scaled singular value fell from 3e-8 to 4.5e-13 and bg-sim's own
solver failed at 0.7076 s (E901), exactly where the FMU stopped. It was not the export's static
LU, and not a lift-off (both soles were loaded). A storage element in derivative causality
(W201) now passes no `:prefer` on, and W219 reports a preferred variable that index reduction
still drops. On the same forward inputs, run on to 5 s, the scaled smallest singular value stays
between 1.0e-7 and 2.0e-7, and the run agrees with the old one to 1.1e-9 rad/s up to 0.70 s.

Cost per simulated second (this machine, other jobs running; wall time / simulated time):

| model | solver, step | states | rhs | wall per sim s |
| --- | --- | --- | --- | --- |
| `microduck-stand` (compliant joints, `XL330` with backlash, battery bus) | Rodas5P, adaptive, rtol 1e-5 | 224 (ODE) | 54.6 us | 43 s |
| the same with rigid joints and `XL330` unchanged (experiment) | Rodas5P, adaptive | 353 (84 + 269 algebraic) | 6.6 us | 630 s (58 us steps: the backlash dead zone against light links) |
| `microduck-policy`, friction `ws` 2 mrad/s, before the state-selection fix (not measured since) | Rodas5P, adaptive | 309 (41 + 268 algebraic) | 13.0 us | 333 s |
| `microduck-policy` (`ws` 20 mrad/s), driven by velstand's half-forward targets for 10 s | Rodas5P, adaptive | 340 (41 + 299 algebraic) | | 102 s (182 s before the fix, on the squat; a dense finite-difference Jacobian per step) |
| its FMU, native (build harness standing / fmpy, stand and squat) | ROS34PW2, 1 ms | 340 | | 0.20 s (4.1 ms per tick) / 0.50 to 0.53 s (fmpy's Python loop included) |
| its FMU as WebAssembly, Node, velstand in the loop | ROS34PW2, 1 ms | 340 | | 0.11 to 0.13 s standing (2.2 to 2.7 ms per 20 ms tick), 0.25 to 0.29 s walking (5.0 to 5.7 ms) |
| its FMU as WebAssembly, headless Chromium, page running | ROS34PW2, 1 ms | 340 | | 0.21 s standing (4.2 ms per tick), 5.0 ms mean after 4 s of walking |
| the same in Node with the one-tick velocity lag (this branch, machine loaded) | ROS34PW2, 1 ms | 340 | | 0.13 s standing (2.6 ms per tick), 0.36 s walking at 0.4 m/s (7.2 ms) |
| `microduck-policy-backlash`, 0.6 s from HOME | Rodas5P, adaptive | 385 (91 states as bg-sim counts them) | 102 us (smooth-contact variant) | about 175 s (smooth-contact variant, profiled) to 365 s (sampled modes, other jobs running) |
| its FMU, native (build harness standing) | ROS34PW2, 1 ms / 0.5 ms | 385 | | 0.68 s (13.7 ms per tick) / 0.58 s (11.6 ms) |
| its FMU as WebAssembly, Node, velstand in the loop | ROS34PW2, 1 ms / 0.5 ms | 385 | | 0.51 s standing (10.3 / 10.0 ms per tick); walking 0.77 to 0.96 s / 1.07 to 1.16 s, until it falls |

What `velstand.onnx` does on it (`apps/web/tests/microduck.test.ts`, the page's own loop in Node,
and `apps/web/tests/microduck-fmu.mjs` in a browser):

The loop feeds the policy joint velocities one control tick (20 ms) old, as training does
(`TRAINING_VELOCITY_LAG` in `apps/web/src/microduck/loop.ts`; microduck_rl
`microduck_velocity_env_cfg.py`, `joint_vel` with a delay of exactly one policy step, because the
Dynamixel firmware averages `present_velocity` over its previous samples). The real robot needs
no lag added; its servos report the old value themselves.

One run per command, 10 s each, from standing at HOME, the stick held from the first tick
(`MICRODUCK_SECONDS=10 MICRODUCK_COMMANDS=0,0.25,0.5,0.6,0.7,0.75,0.85,1`). The FMU completes
every step of all eight. In this simulation only; it says nothing about the real robot:

* **Zero command: it stands.** Trunk 115.6 mm high at the end (the start is 116.7 mm), tilt at most
  2.31 deg, no drift (under 1 mm), no sole leaves the floor.
* **Up to 0.24 m/s asked (0.1, 0.2, 0.24 m/s): it does not walk.** It leans and shifts its weight
  (at most 11 mm forward, tilt at most 2.54 deg) and stands; no sole leaves the floor.
* **From 0.28 m/s asked: it walks, slower than asked, on a curve.** Speeds and turn rates over
  the second half of the run (5 to 10 s; speed = straight-line distance / 5 s):

  | asked | distance in 10 s | heading at 10 s | speed, 5..10 s | turn rate, 5..10 s | lift-offs left / right | tilt at most |
  | --- | --- | --- | --- | --- | --- | --- |
  | 0.28 m/s | 1.06 m | +16 deg | 0.107 m/s | +0.022 rad/s | 18 / 18 | 4.99 deg |
  | 0.30 m/s | 1.22 m | +18 deg | 0.126 m/s | +0.005 rad/s | 18 / 18 | 4.97 deg |
  | 0.34 m/s | 1.46 m | -27 deg | 0.147 m/s | -0.087 rad/s | 18 / 19 | 5.40 deg |
  | 0.40 m/s | 1.85 m (x 1.68, y -0.79) | -38 deg | 0.195 m/s (x 0.158) | -0.053 rad/s | 19 / 19 | 5.71 deg |

  Never both feet up, no fall. microduck_rl's notes on velstand (`velstand_policy.md`, sim
  evaluation on a flat floor with backlash) give 0.17 m/s achieved at 0.4 m/s asked and a
  straight-walk yaw drift of 0.05 and 0.03 rad/s at 0.3 and 0.4 m/s; how they average is not
  stated there, so the comparison is indicative only.
* **Without the lag** (`MICRODUCK_LAG=0`, how the page ran before): the same standing up to
  0.24 m/s; at 0.4 m/s 1.82 m (x 1.41, y -1.14), heading -56 deg, 0.195 m/s and -0.044 rad/s over
  5 to 10 s; at 0.3 m/s 1.13 m, heading +45 deg, 0.119 m/s, +0.092 rad/s. The lag changes the
  heading more than the speed. Starting the command 0.02, 0.1, 0.5 or 1 s later (without the lag)
  gave 1.56 to 1.81 m and -46 to -56 deg, but the gait is sensitive: the native FMU and the Wasm
  build, fed the same inputs open loop, part by 1e-6 m at 0.48 s and fall apart within a second,
  as an unstable gait without its feedback does. One run per row: a heading is not a property of
  the policy here, only of that run.
* **No policy: HOME tips forward** (past 45 deg at 1.34 s) and lands on the trunk and head
  bumpers; the FMU runs on through the impact and settles face down (3 s, tilt 82 deg). The
  export with the old state selection stopped at that impact (1.44 s).

## What to try

* `xl330-step`: drop `kp_fw` to 50 (the limp gain), or `v_bat` to 6.6 V (an empty pack).
* `xl330-torque-speed`: set `i_limit` to 1.0 A, the limit of the impact-guard firmware on the
  robot, and compare with the 1.75 A the policies were trained with.
* `microduck-stand`: raise `kp_fw` and see how much longer the robot stays up; set
  `t_latency` to 0.03 s (training's upper end).
* Per servo, pin `Friction/scale` (0.9..1.1) or `RotorInertia/i` in an instance, as the domain
  randomisation does.

## Limits to sim-to-real fidelity, most important first

1. **No real robot.** Nothing is checked against hardware. `velstand.onnx` stands on the FMU and,
   from 0.28 m/s asked, walks at about half the asked speed on a curve (*The FMU and the policy*).
   That is what the policy does on this model, not evidence about the robot, let alone transfer.
2. **No backlash in the robot the demo runs.** velstand was trained with 2 deg of play in every
   joint (microduck_rl `add_backlash.py`); `XL330Rigid` has none. `microduck-policy-backlash`
   has it as training has it, and matches MuJoCo on the bench, but its FMU disagrees with bg-sim
   and falls apart under velstand when walking (*The XL330Backlash subsystem*).
   The other differences from the simulator velstand was trained in (mjlab, BAM): a fixed 20 ms
   actuator latency where training randomises 15 to 30 ms; an ideal supply (no battery sag); the
   deploy action scale 0.9 (`robotd`, which the page uses) where training used 1.0; a flat floor
   where training used rough terrain; four contact points per sole with this model's contact
   law instead of MuJoCo's; the friction smoothed (`ws`) instead of BAM's. Each of these can
   change a gait. (The one-step lag of the observed joint velocities that training applies, the
   page now applies too.)
3. **Current limit.** Training (and this model) limit the current with BAM's 1.75 A duty window;
   the robot runs ROBOTIS impact-guard firmware with a 1.0 A current limit in position mode,
   speed-dependent PWM derating and a braking ramp, none of which BAM or this model contains.
4. **Two BAM fits disagree** (kt 6 %, R 11 %, armature 13 %, base friction 2.5x): the actuator is
   only as good as the fit, and the newer fit is not the one the policies saw.
5. **Latency** is assumed (20 ms of the 15..30 ms training range); BAM-B identifies 10 ms.
6. **Backlash and gear compliance**: 2 deg is a training assumption; in `XL330` the tooth
   stiffness and damping are guesses, and `XL330Backlash` copies MuJoCo's soft limit, which is
   what training used, not a measured gear.
7. **Firmware loop modelled as continuous**: the XL330 control period is not published; no
   encoder quantisation (4096 counts = 1.5 mrad), no PWM quantisation.
8. **Friction**: regularised (creeps at `ws atanh(tau/F)` instead of sticking), and its external
   torque is the transmitted gear torque, where BAM uses the gravity bias.
9. **Electrical**: no winding inductance, no thermal derating; the 2S pack (up to 8.2 V) exceeds
   the servo's 6.0 V rating, as on the robot, and the motor constants are extrapolated there.
10. **Contacts**: four points per sole; in `microduck-policy` also frictionless bumper points on the
   trunk, the head and the shins, so a fall lands (the stand run stops before the head would hit).
   The policy robot starts with the soles loaded at HOME (the start sinks them 51 um short of
   the static load: a 1 ms settling transient).
11. Mouth servo omitted; body masses as in the MJCF (no cable or battery placement check).

## 3D view

`microduck-stand`, `microduck-hang`, `microduck-policy` and `microduck-policy-backlash` carry a
3D scene (`scenes/microduck.sdf`, `scenes/microduck-hang.sdf`, written by `design/scene.py`):
one link per body, each bound to the pose of its body (`Free/pose` or `TrunkPose/g` for the
trunk, `<joint>_link/W/g` for the others), on a floor of 10 cm tiles. The browser game
(`apps/web/microduck`) draws the same parts from `apps/web/src/microduck/duck.glb`.

The parts are Pollen Robotics' own CAD visual meshes from microduck_rl at 0daab16
(`assets/*.stl`, placed by the visual geoms of `robot_groundcontact.xml`), the file
`design/robot_data.json` was extracted from, so every part sits in exactly the frame the model
uses: the 14 XL330 horn axes lie on the joint axes to 0.000 mm and 0.000 deg (printed by
`design/build_visuals.py`). The script decimates the 796,844 source triangles to 77,066
(quadric edge collapse, a budget per part), merges each body's parts per MJCF colour and writes
`meshes/<body>.glb` (15 files, 2.75 MiB) and `duck.glb` (2.39 MiB, a node per body and the lower
beak on the mouth servo's axis).

**The meshes are CC BY-NC-SA 4.0, non-commercial only** (Pollen Robotics, microduck_rl
`LICENSE-MODELS.md`); see `meshes/NOTICE`, `meshes/LICENSE` and
`apps/web/src/microduck/duck.glb.NOTICE`. That licence covers these mesh files only.

Two other CAD sources were looked at and not used. The MicroDuck replica
(github.com/deanxizian/MicroDuck-Replica, `Print-Colors.blend` at 51c3673) is the same robot on
HD1910 servos with modified parts; its assembly is the model's HOME pose (horn centres within
0.11 mm of the joint axes, the head roll 0.97 mm, angles within 0.01 deg), but the modifications
are under a personal non-commercial licence that needs written permission for any organisational
use. github.com/fanhao375/microduck-replica-cad (XL330 SolidWorks release v1.1) rebuilds the
same Pollen meshes as SolidWorks parts; using it would mean exporting the assembly
(`00-microduck装配体 XL330-288舵机版本.SLDASM`) as STEP in assembly coordinates or as one STL per
component.

## Rebuild

```
uv run examples/microduck/design/build_model.py     # library, models, scenes, expected.json
uv run examples/microduck/design/build_visuals.py   # meshes/*.glb and the game's duck.glb (downloads 38 STL, pinned hashes)
uv run examples/microduck/design/xl330.py           # actuator numbers
uv run examples/microduck/design/robot.py           # body numbers and the hang reference
julia --project=julia/BGSim examples/microduck/design/run_model.jl xl330-step <run_dir>
uv run examples/microduck/design/compare_bench.py <run_dir>
uv run tools/example_docs/build.py --only microduck
julia --project=julia/BGSim examples/microduck/design/profile_model.jl microduck-policy 0.1   # cost, spectrum
uv run examples/export_microduck_check.py --out <dir>   # the FMU: export, references, build, fmpy comparison
uv run examples/microduck/design/mjcf_play.py <microduck_rl>/src/mjlab_microduck/robot/microduck   # -> design/play_data.json
uv run examples/microduck/design/backlash_bench.py --write   # MuJoCo on the play bench -> design/backlash_reference.json
uv run examples/export_microduck_check.py --model microduck-policy-backlash --out <dir>   # the gear-play robot as an FMU
```
