# ball-and-plate — a 2 DOF ball-and-plate lab rig: a steel ball rolling on a servo-tilted plate, camera feedback, cascaded PID against LQR with a Kalman filter

A 1 inch steel ball rolls on a 0.35 m acrylic plate. The plate sits on a gimbal (universal joint)
and two rotary servos tilt it through cranks and push rods, one per axis. An overhead camera finds
the ball at 30 frames/s and one frame late. The layout is that of the Quanser 2 DOF Ball Balancer:
two SRV02 servos beside a plate on a 2 DOF gimbal, with an overhead camera.

| model | what it runs |
| --- | --- |
| `ball-and-plate-free` | open loop: the plate locked at 1° about y, the ball released at rest 0.15 m from the centre, 2 s. Checked against x'' = 5/7 g sin α, the roll time, zero slip, 2/7 rotational energy and the energy book |
| `ball-and-plate-swing` | open loop: the plate swings as α = −2° cos(2π·2 Hz·t) and the ball starts at rest 0.10 m off the axis. Full 3D rolling next to the linearised x'' = 5/7 g sin α of the same plate angle, 4 s |
| `ball-and-plate-pid` | cascaded PID: steps in x (1 s) and y (6 s), back to the centre (11 s), a 0.6 N / 50 ms push in y (15 s), 20 s |
| `ball-and-plate-lqr` | the same scenario under an LQR with integral action on a Kalman filter that knows the camera latency |
| `ball-and-plate-track` | the LQR with reference feed-forward tracks a figure-8 (task 3; a circle is task 2), 30 s |

## Structure

The plant is a bond graph in every model; library blocks only compute signals: kinematics,
controllers, the task and the 3D view.

* **Plate.** A `RigidBody3D` (0.875 kg, centre of mass on the gimbal centre) on a `Universal3D`
  gimbal. The first gimbal axis is world y and the second the plate's x axis. Two
  `FixedTransform3DNeutral` place the joint frame. The pose comes from `LocalPose3D` and
  `ComposePose3D`.
* **Ball.** A free `RigidBody3D` with a `PoseIntegrator3D`. The inertia is J = k_ball m r², where the
  model global `k_ball` is 0.4 for the solid ball and 2/3 for a hollow one.
* **Contact.** `stdlib:contact/RollingSphere`, a new stdlib block (see below). Both bodies bond
  straight to it, so the plate feels the ball and the plate's rotation rate and angular acceleration
  enter the ball's motion.
* **Servo, per axis.** The SRV02 as a bond graph: `MSe` (amplifier voltage) → 1-junction with `R`
  (2.6 Ω) and `I` (0.18 mH) → `GY` (k_m) → `TF` (gearbox 1:70) → 1-junction with `I` (J_eq) and `R`
  (B_eq) and an `AngleSensor`. The crank and push rod form an `MTF`, whose modulus
  dα/dθ = ρ cos θ / √(1 − ρ² sin² θ) (with ρ = r_arm/L) comes from the signal block
  `library/CrankLinkage.jl`. Their compliance is a `C`/`R` pair on a 0-junction between the rod and
  the gimbal drive.
* **Firmware.** Per servo, an `Encoder` (4096 counts/rev, 500 Hz), `library/ServoPD.jl` (PD with
  derivative on the measurement, ±10 V) and a `DeadZone` (±0.05 V) in front of the amplifier.
* **Camera, per axis.** A `Select` of the ball centre, `Noise` (seeded, 0.3 mm), a `Sum`, a
  `Quantizer` (one pixel = 0.625 mm, 30 Hz) and an `IntegerDelay` (one frame).
* **Outer loop at 30 Hz.** `library/PlatePID.jl` (PID with a filtered derivative on the measurement
  and conditional integration) or `library/PlateLQG.jl` (steady-state Kalman filter with the
  one-frame delay state, LQR with integral action and anti-windup, reference feed-forward).
* **Task and push.** `library/PlateTask.jl` holds the tasks: hold, steps (with an optional set-point
  filter `t_s`), circle and figure-8, each with its derivatives. `library/BallPush.jl` gives a
  half-sine world-frame force on the ball through `ExternalWrenchSpatial`.
* **Measurements.** `library/RigEnergy.jl` keeps the energy book of the free model.
  `library/RigViz.jl` computes the push-rod and target poses for the 3D view.

Custom blocks are used only where no stdlib block fits: the crank kinematics (an MTF modulus), the
firmware loops (each is one discrete tick), the task generator and two measurement and display
blocks.

### `stdlib:contact/RollingSphere`

This general two-body rolling contact is new in this branch. A sphere on body `b` rolls on a
finite face fixed in body `a`, which may tilt, turn or move. It has:

* a Hunt-Crossley normal force with an edge gate;
* isotropic regularised Coulomb friction, which gives rolling without slip up to a creep of
  `vs F_t/(μ f_n)`;
* a rolling-resistance moment `crr r f_n` and optional spin damping.

The reaction acts on both bodies, with `a.P + b.P = dEc/dt + Pd`. Golden tests:
`julia/BGSim/test/golden/contact/test_RollingSphere.jl`.

## Parameters and sources

| part | value | source |
| --- | --- | --- |
| ball | 1 in chrome-steel ball: r = 12.7 mm, 67.0 g, solid (J = 2/5 m r²) | AISI 52100 density 7810 kg/m³ |
| plate | 0.35 m square, 6 mm cast acrylic: 0.875 kg, J_xy = 8.93e-3 kg m²; gimbal centre 0.16 m above the base | PMMA 1190 kg/m³; Quanser's plate is 0.275 m |
| servo motor | R_m = 2.6 Ω, L_m = 0.18 mH, k_t = k_m = 7.68e-3, gearbox K_g = 70 (high gear), J_eq = 2.08e-3 kg m², B_eq = 0.015 N m s/rad, encoder 4096 counts/rev | Quanser SRV02 User Manual, Doc. 700 rev 2.3, Table 5 |
| linkage | crank r = 25.4 mm, lever L = 0.16 m (ρ = 0.159): sin α = ρ sin θ | geometry of the 2 DOF Ball Balancer; Sidi et al., JESA 57(2) 2024, eq. 8 (CC BY 4.0, doi:10.18280/jesa.570210) |
| linkage compliance | 5000 N m/rad, 1.3 N m s/rad (at the gimbal) | assumed |
| camera | 640 × 480 pixels over 0.40 m (0.625 mm per pixel), 30 frames/s, one frame of latency, 0.3 mm centroid noise | Quanser 2 DOF Ball Balancer product page (camera); noise and latency assumed |
| drive | ±10 V (the DAQ's analog output), 0.05 V dead band | dead band assumed |
| contact | Hunt-Crossley k = 1e5 N/m at 0.1 mm (softer than Hertz, for the solver), damping 20 s/m, μ = 0.4, v_s = 1 mm/s, rolling resistance crr = 0.002 | assumed |

Derived values (all in `design/design.json`): the ball's acceleration per servo angle is
K_bb = 5/7 g ρ = 1.112 m/s² per rad. The servo PD gives 50 rad/s with damping 0.8
(Kp = 27.9 V/rad, Kd = 0.28 V s/rad).

## Controllers (`design/design.py`)

Each axis is linearised to x, v, θ, ω with the closed servo loop, the ball's weight on the servo and
the camera seeing the ball centre 15.7 mm above the gimbal. The model is sampled at 30 Hz with
`n` frames of camera delay.

* **Cascaded PID.** Grid search over Kp and Kd with Ti = 5 s and τ_d = 0.05 s. The design keeps the
  overshoot at or below 8 %, stays stable with 2 frames of delay and minimises the settling time.
  Result: Kp = 3.6 rad/m, Ki = 0.72, Kd = 2.52 (rise 0.87 s, overshoot 1.9 %, 2 % settling 1.37 s).
* **LQR + Kalman.** Bryson weights: x 0.02 m, v 0.05 m/s, θ 0.2 rad, ω 5 rad/s, integral 1 m s and
  u 0.2 rad. Result: K = [6.14, 4.22, 0.093, 0.003, 0.121] (rise 1.0 s, overshoot 1.5 %, settling
  1.6 s). The steady-state Kalman filter estimates [x, v, θ, ω, c_prev] from the camera (one frame
  late) and the encoder. The tracking feed-forward commands the plate angle from the reference's
  acceleration and jerk.

## Results

| | PID | LQR + Kalman |
| --- | --- | --- |
| x step 0 → 0.10 m, rig (design) | rise 0.93 s (0.87), overshoot 0.8 % (1.9 %), settling 1.65 s (1.37) | rise 1.09 s (1.0), overshoot 1.4 % (1.5 %), settling 1.97 s (1.6) |
| y step 0 → 0.08 m, rig | settling 2.0 s, overshoot 0.5 % | settling 2.1 s, overshoot 1.5 % |
| steps through a 1 s set-point filter (`Task/t_s` = 1) | settling 2.2 s | settling 0.92 s (the feed-forward tilts the plate ahead of the ball) |
| 0.6 N, 50 ms push in y | peak 61 mm | peak 46 mm |
| circle r = 0.08 m, 6 s, RMS error (x, y) | 39, 40 mm (design 54 mm combined) | 1.8, 1.9 mm |
| circle without rolling resistance | | 0.20, 0.21 mm (design 0.20 mm combined) |
| figure-8 0.2 × 0.12 m, 8 s, RMS error (x, y) | 38, 41 mm | 1.9, 1.7 mm |
| camera delay 3 frames (x step, rig) | settling 1.2 s, overshoot 0.7 % | settling 2.1 s, overshoot 1.4 % |
| camera delay 6 frames (x step, rig) | settling 4.1 s, overshoot 24 % | settling 2.7 s, overshoot 8.8 % |
| delay that destabilises the linear loop (design) | 8 frames | 9 frames |

What the rig adds to the linear design: the servo dead band, pixel rounding, camera noise and the
rolling resistance. The resistance lets the ball rest on a tilt up to about 0.002 rad, so both
controllers stop within 1–2 mm of the set-point, and the slow LQR integral (50 s) removes that
offset more slowly than the PID integral. The rolling resistance also costs about 2 mm of tracking
error that the feed-forward does not model; without it, the rig tracks the circle as the design
predicts.

**The ball hops.** The return step at 11 s happens with the ball 0.1 m off the axis. The LQR answers
with a 0.6 rad servo set-point jump, the plate edge drops faster than gravity can follow
(x α̈ > g), and the ball leaves the plate for about 20 ms. The contact model handles the lift-off and
the landing, where the slip reaches about 1 cm/s. The 30 Hz steps of the servo set-point also make
the ball chatter on the plate: the normal force touches zero for about 2 ms. The set-point filter
(`Task/t_s`) removes the hop.

## Open-loop reference values

* **Free roll.** On a 1° tilt, a = 5/7 g sin α = 0.12229 m/s², so the ball reaches the centre after
  √(2·0.15/a) = **1.5663 s** (model 1.5662 s). For a hollow ball (k_ball = 2/3), a = 3/5 g sin α and
  the time is 1.7089 s (model 1.7088 s). The slip creep is 1.25e-5 m/s. The rotational share of the
  kinetic energy is 2/7 (hollow: 2/5). Ebal drifts by 1.7e-9 J against 2.8e-3 J of kinetic energy.
* **Swinging plate.** `design.py` integrates ẍ = 5/7 (g sin α + x α̇² − (h + 2r/5) α̈) for the ball
  centre at h = 15.7 mm above the axis. The linearised law keeps the ball at 0.10 m. The full motion
  drifts outwards by **59.0 mm in 4 s**: the centrifugal term x α̇² of the rotating plate. The bond
  graph agrees to 0.1 %.

## Checks

`uv run examples/run_checks.py --only ball-and-plate` runs every model plus five variants through
`expected.json`:

* the hollow ball;
* the track model with the circle;
* the circle without rolling resistance;
* the PID on the circle;
* the LQR with the step filter.

Each check's `note` says where its reference comes from. `design/build_model.py` writes the models
and `expected.json`, `design/build_scene.py` writes the scene, and `design/design.py` writes
`design.json` (run it first).

## What to try

* **free**: set the ball inertia to 0.667 (a hollow ball) and it rolls slower, 3/5 instead of
  5/7 g sin α. Raise the rolling resistance to 0.02 and the ball barely moves, because 1° = 0.017 <
  0.02. It creeps at about 0.2 mm/s, the regularisation of the rolling moment.
* **pid / lqr**: lower PID Kp on the dashboard and watch the overshoot grow. Set the push to 1.2 N.
  Set the set-point filter to 1 s and the LQR hop at 11 s goes away. Switch the task to figure-8 and
  compare the PID's lag with the LQR's feed-forward.
* **track**: switch to the circle. A hollow ball makes the plate too steep for the feed-forward,
  which assumes 5/7, and the error grows.

## Licences and attributions

Rig data: the Quanser SRV02 User Manual (Doc. 700 rev 2.3, Table 5) and the Quanser 2 DOF Ball
Balancer product page, cited as published specifications; no Quanser material is copied. The
linkage relation is from Sidi et al., JESA 57(2) 2024, published under CC BY 4.0. Everything else
was written for this example.
