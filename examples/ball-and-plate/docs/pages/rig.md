# The ball-and-plate rig

A **1 inch steel ball** (67 g) rolls on a **0.35 m acrylic plate**. The plate sits on a gimbal and two
rotary servos tilt it through cranks and push rods, one per axis. An overhead camera finds the ball
at **30 frames/s, one frame late**. The layout is that of the Quanser 2 DOF Ball Balancer: two SRV02
servos beside a plate on a 2 DOF gimbal, with an overhead camera.

![The rig in the 3D view: base, servos with cranks and push rods, the plate with its grid and the two reference paths, the steel ball with its painted bands and the red target ring|700](assets/27ac9a50eba8.png)

| part | value | source |
| --- | --- | --- |
| ball | r = 12.7 mm, 67.0 g, solid (J = 2/5 m r²) | chrome steel, 7810 kg/m³ |
| plate | 0.35 m × 0.35 m × 6 mm acrylic, 0.875 kg, centre of mass on the gimbal centre 0.16 m above the base | PMMA, 1190 kg/m³ |
| servo | R = 2.6 Ω, L = 0.18 mH, k_t = k_m = 7.68e-3, gearbox 70:1, J_eq = 2.08e-3 kg m², B_eq = 0.015 N m s/rad, 4096 counts/rev | SRV02 User Manual, Table 5 |
| linkage | crank 25.4 mm, lever 0.16 m: sin α = ρ sin θ, ρ = 0.159 | Sidi et al. 2024, eq. 8 |
| camera | 0.625 mm per pixel, 30 frames/s, one frame of latency, 0.3 mm noise | Quanser product page; latency and noise assumed |
| drive | ±10 V, 0.05 V dead band | dead band assumed |
| contact | Hunt-Crossley, μ = 0.4, rolling resistance crr = 0.002 | assumed |

## The bond graph

The plant is the same bond graph in every model:

- **Plate.** A `RigidBody3D` on a `Universal3D` gimbal. The first axis is world y, the second the
  plate's x axis.
- **Ball.** A free `RigidBody3D` with its `PoseIntegrator3D`. The inertia factor is the model global
  `k_ball`: 0.4 for the solid ball, 2/3 for a hollow one.
- **Contact.** The two bodies meet in `RollingSphere`, a contact between two bodies. The plate feels
  the ball, and the plate's rotation rate and angular acceleration enter the ball's motion.
- **Servos.** Each servo is `MSe` → electrical 1-junction (`R`, `I`) → `GY` → gearbox `TF` →
  output-shaft 1-junction (`I`, `R`, `AngleSensor`) → crank `MTF` → push-rod compliance (a `C`/`R`
  pair on a 0-junction) → gimbal drive. The modulus of the `MTF` is the crank kinematics
  dα/dθ = ρ cos θ/√(1 − ρ² sin² θ), computed by `CrankLinkage`.

![The PID model: plant, servos, camera chains, controllers, task and push|900](assets/c86966cfc53b.png)

## The control loops

The **firmware** of each servo runs at 500 Hz: an encoder, a PD on the encoder angle (50 rad/s,
damping 0.8) and a dead band. The **outer loop** runs at the camera's 30 Hz and gives the servo
angle set-points. The **camera** chain is the ball's world position plus seeded noise, rounded to
the pixel and delayed by one frame.

- **Cascaded PID** (`PlatePID`): Kp = 3.6 rad/m, Ki = 0.72, Kd = 2.52, with a filtered derivative on
  the measurement and conditional integration. A grid search in `design/design.py` picked these
  gains: overshoot at most 8 %, stable with 2 frames of delay, then the shortest settling time.
- **LQR + Kalman** (`PlateLQG`): a steady-state Kalman filter on [x, v, θ, ω, last camera
  reading], fed by the camera and the encoder. It estimates where the ball is now, not where the
  camera saw it. An LQR with integral action and a reference feed-forward follows: the plate angle
  comes from the reference's acceleration and jerk.

## Comparison

| | PID | LQR + Kalman |
| --- | --- | --- |
| x step 0.1 m, rig (design) | settling 1.65 s (1.37), overshoot 0.8 % (1.9 %) | settling 1.97 s (1.6), overshoot 1.4 % (1.5 %) |
| 1 s set-point filter | settling 2.2 s | settling 0.92 s |
| 0.6 N push | peak 61 mm | peak 46 mm |
| circle 0.08 m, RMS per axis | 40 mm | 1.9 mm |
| figure-8, RMS per axis | 40 mm | 1.8 mm |
| 6 frames (200 ms) of camera delay | overshoot 24 %, settling 4.1 s | overshoot 8.8 %, settling 2.7 s |

The PID settles a hard step a little faster. The LQR copes better with delay. With its
feed-forward, the LQR tracks moving references 20 times more closely. The remaining 2 mm come from
the rolling resistance, which the feed-forward does not model. Without it, the rig tracks the
circle to 0.2 mm, as the linear design predicts.

The models: [free roll](model:ball-and-plate-free), [swinging plate](model:ball-and-plate-swing),
[PID](model:ball-and-plate-pid), [LQR](model:ball-and-plate-lqr), [tracking](model:ball-and-plate-track).
