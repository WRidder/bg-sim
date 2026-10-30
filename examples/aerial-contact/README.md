# aerial-contact (X5.8)

The multimodal aerial manipulator of H. W. Wopereis, W. W. van de Ridder, T. J. W. Lankhorst, L. Klooster,
E. M. Bukai, D. Wuthier, G. Nikolakopoulos, S. Stramigioli, J. B. C. Engelen and M. Fumagalli, *Multimodal Aerial
Locomotion: An Approach to Active Tool Handling*, IEEE Robotics & Automation Magazine, December 2018. A 2.1 kg
hexarotor carries a servo-driven carbon tube with a rubber shock mount and an end-effector on three omnidirectional
wheels. It flies to a wall, engages, pushes the end-effector on the wall with a tilted thrust vector under a
gain-scheduled LQR contact controller, climbs and descends the wall on its wheels while the multirotor follows, and
disengages. Z is up, units are SI.

| model | what it is |
| --- | --- |
| `aerial-contact` | the 34 s scenario, reltol 1e-4, abstol 1e-6, output every 20 ms (plus the 4 ms ticks) |

The model document and the 3D scene are **generated**: `uv run examples/aerial-contact/design/build_model.py` writes
`models/aerial-contact.bgmodel.json` and `scenes/aerial-contact.sdf` from the numbers of `design/design.py`, and
`uv run examples/aerial-contact/design/design.py` prints the derivation of every gain (cascade loops, the contact
controller, the equilibrium check and the closed-loop poles). The model docs (`models/aerial-contact.docs/`, W5.6
format with KaTeX math and result plots from a real run) are written by `design/build_docs.py` from the Markdown
sources `design/docs_pages.md`.

## Scenario (compressed version of the paper's automated run)

| t [s] | phase | what happens |
| --- | --- | --- |
| 0 to 1.5 | free flight | hover at 1 m, 0.45 m from the origin (the run starts in hover; there is no take-off and no landing gear) |
| 1.5 to 4 | free flight | minimum-jerk move of the position set-point to x = 0.75 m (end-effector 0.19 m from the wall) |
| 4.5 | engage | request; the guard (end-effector within 30 cm of the wall) is satisfied; theta_sp 12 to 20 deg over 4 s, z_sp = z_b(t_e) |
| 5.08 | engage | first impact on the wall at 0.85 m/s |
| 6.12 | contact | the wall has stopped the multirotor for 0.3 s; the LQR takes over; theta_sp reaches 27 deg at 11.5 s |
| 13 to 19 | contact | velocity command 0.125 for 6 s: the end-effector climbs 0.294 m |
| 19 to 21 | contact | pause |
| 21 to 27 | contact | command -0.125 for 6 s: back down |
| 28.5 | disengage | set-point p_sp = (x_b(t_d) - C, y_b(t_d), z_b(t_d)), C = 0.75 m, the free-flight cascade |
| 34 | disengage | hover at x_b = 0.187 m |

## Architecture

```
 Sup (Supervisor, 50 Hz): phase machine + operator script
   | p_sp, v_sp, a_sp, psi_sp, a_pos          | theta_sp, psi_sp, z_hold, sel_eng      | theta_sp, psi_sp
   v                                           v                                        v
 Pos (PositionCtrl, 50 Hz) -- qd, F --+     Eng (EngageCtrl, 50 Hz) -- qd, F --+    Con (ContactCtrl, 250 Hz: LQR K(theta_sp))
                                      v                                         v        | tau (3), F
                           Sel (PhaseSelect, 250 Hz) -- qd, F --> Att (250 Hz) -- w_sp --> Rate (250 Hz) -- tau --+
                                                                                                                  v
 Nav (NavFilter) <- Imu (250 Hz) <- SpecF (accelerometer tap) ...               Mix (Mixer N = 6) <-- F, tau2 (Con), sel_lqr
 Gps (50 Hz fix)                                                                  | w_cmd[6]
                                                                                  v
 Esc1..6 (250 Hz) -> Drv1..6 (stdlib ElectricDrive) -> Prop1..6 (Propeller) -> RW (RotorWrench) -> Wrench -> Body
 World (GroundSpatial) -- Free (Free3D) -- Body (RigidBody3D, 2.1 kg) -- MountS -- Servo (Revolute3D) -- LinkA -- Arm (RigidBody3D)
 Arm -- TipM -- Rub (Spherical3D) -- LinkE -- EE (RigidBody3D) -- MountW1..3 -- Wheel1..3 (OmniContact) ... Wall (ContactSurface)
 ServoCtl (ArmServo: PD + tanh limit) -> Servo.drive ;  RubK (RubberMount) -> Rub.drive1..3 ;  Omni (OmniDrive) -> Wheel.u
```

* **Multirotor.** `GroundSpatial -> Free3D -> RigidBody3D` (2.1 kg, J = diag(0.055, 0.055, 0.105)), six rotors of
  `Esc -> ElectricDrive -> Propeller` (950 Kv: k_t = 0.01005, R = 0.11 Ohm, 10x4.5 in: kT = 1.42e-5, kQ = 2.03e-7), 16 V
  constant supply (the tether replaces the battery), `RotorWrench` for the thrust, motor reaction, gyroscopic and drag
  wrench of the six rotors, `Mixer` with the 6 x 4 pseudo-inverse of the allocation matrix (13 N per rotor, 78 N in
  total). The run starts in hover with the rotors at 534 rad/s.
* **Manipulator.** A `Revolute3D` servo joint about y_b (frame j rotated -90 deg about x, so q = -mu, mu = arm
  elevation above the body x axis), a rigid tube (0.23 kg, L_m = 0.6 m) driven by `ArmServo` (PD with a smooth tanh
  torque limit, 8.4 N m, 40 rad/s). In free flight mu_sp = theta_b (arm level in the world), in contact mu_sp = theta_sp.
* **Flexible joint.** A stdlib `Spherical3D` between the tube tip and the end-effector; `RubberMount` supplies the exact
  conservative rotational spring-damper (U = 2 k sin^2(theta/2), 1 N m/rad, 0.03 N m s/rad) through `MSe` on the three
  rotation ports.
* **End-effector and wheels.** 0.15 kg, three wheels at 120 deg on a 4.5 cm circle. Each wheel is the example-local
  `OmniContact` (stdlib `ContactPoint` has two fixed isotropic friction tangents): Hunt-Crossley normal force from the
  penetration into the wall plane (`ContactSurface` at x = 1.6 m, normal -x) and anisotropic traction: regularised Coulomb
  along the wheel's drive direction against the slip relative to the commanded surface speed (`OmniDrive`: u_k =
  -v_max d_k . v_cmd, v_max = 0.4 m/s at command 1), 0.04 friction along the free rollers; both forces act against their
  slip, so the contact is energy-consistent. The 6 N brush spring is not modelled.
* **Sensors.** `ImuSensor` (gyro + accelerometer, bias, noise, 2nd-order Butterworth), `SpecForce` (the accelerometer
  tap: the specific force from the true body acceleration, so the arm's reaction in contact is felt), `GpsSensor`,
  `NavFilter` (fixed-gain observer; the tilt is observed through the velocity innovation, so it does not depend on the
  source of the force).
* **Controllers.** `Supervisor` (phase machine and operator script), `PositionCtrl` + `AttitudeCtrl` + `RateCtrl`
  (free flight and disengage), `EngageCtrl` (angles as references, height hold), `ContactCtrl` (LQR), `PhaseSelect` and the
  torque selection in `Mixer`.

## The contact controller (design/design.py)

With the end-effector held by the wheels, the multirotor with its arm is ONE rigid body pinned at the elastic joint. The
unknown reaction is eliminated and what remains is the Euler equation about the joint,

    I_E w' = tau - L_m u x (F e_z) - w x I_c w - M e x (w x (w x e)) + M g e x (R^T e_z),   I_E = I_c + M (|e|^2 I - e e^T)

(M = 2.33 kg multirotor + arm, e the vector from the composite centre of mass to the joint, u the arm direction), with
Z-Y-X Euler kinematics: X = [phi, phi', theta, theta', psi, psi'], U = [tau_x, F, tau_z, tau_y]. The equilibrium for a
pitch set-point theta_sp has the arm level in the world (mu_c = theta_sp), F_eq = m g / cos(theta_sp), wall force
F_N = m g tan(theta_sp) and tau_y,eq = -m_arm g L_m / 2 (the model finds it numerically and asserts the closed form).
Finite-difference linearisation gives A(theta_sp), B(theta_sp); the plane of symmetry decouples them exactly into pitch
(theta, theta' driven by F and tau_y) and the coupled roll/yaw block (phi, psi driven by tau_x and tau_z), so the two
Riccati equations are solved separately and K has **exactly** the structure of the paper (rows tau_x and tau_z: only
the phi, phi', psi, psi' columns; rows F and tau_y: only theta, theta'). K is computed on theta_sp = 10, 15, ..., 45 deg
and interpolated linearly in `ContactCtrl`. The paper's garbled input ordering is irrelevant: the order here is
[tau_x, F, tau_z, tau_y] (K rows) as the structure requires.

    K(20 deg), rows tau_x, F, tau_z, tau_y; columns phi, phi', theta, theta', psi, psi'
      tau_x   17.5468    1.1567    0         0         8.8073    5.2361
      F        0         0         6.7244    2.7637    0         0
      tau_z    0.6525   -0.0636    0         0         0.7051    0.3858
      tau_y    0         0         8.2824    3.4040    0         0

    K(27 deg)
      tau_x   15.9727    0.7880    0         0         8.6873    5.0788
      F        0         0         6.4796    2.6808    0         0
      tau_z    0.6660   -0.0995    0         0         0.7624    0.4252
      tau_y    0         0         8.4169    3.4823    0         0

(the model interpolates the 5 deg grid linearly: 15.9779 instead of 15.9727 for K[tau_x, phi] at 27 deg).

The closed-loop spectral abscissa over the grid is -2.68 (10 deg) to -1.59 (45 deg) 1/s; the open loop is the undamped
pendulum (+-1.5 to 2.2 i rad/s) with neutral roll and yaw.

## Design (design/design.py)

| loop | design | result |
| --- | --- | --- |
| ESC speed (250 Hz) | PI + motor-model feed-forward | Kp 0.035, Ki 1.6: crossover 72 rad/s, PM 57 deg, GM 15 dB |
| roll/pitch rate | Kp = (J + 0.02) 26 rad/s, Ti 0.3 s, Td 8 ms | Kp 1.95, Ki 6.5, Kd 0.0156: crossover 38 rad/s, PM 61 deg, GM 9.7 dB |
| yaw rate | largest gain with PM >= 55 deg, GM >= 12 dB (rotor-acceleration lead) | Kp 0.595: crossover 17.5 rad/s, PM 106 deg, GM 15 dB |
| attitude | P on the quaternion error, K = 5 /s | crossover 4.8 rad/s, PM 75 deg |
| velocity (xy) / position (xy) | PI 3 /s, 1.2 /s^2; P 1 /s | crossovers 2.8 and 1.2 rad/s, PM 45 and 68 deg |
| vertical | velocity 5 /s, 3 /s^2; position 1.5 /s | crossovers 5.0 and 1.6 rad/s, PM 72 deg |
| contact LQR | Q = diag(40, 2, 100, 3, 40, 3); R from 1.5 N m, 1.2 N, 0.3 N m, 1 N m | closed-loop poles at 2 to 4 rad/s, below the rate loops |

The static CoM-correction torque about y_b (arm 0.23 kg at L/2 and end-effector 0.15 kg at L + 3 cm) is -1.604 N m, added
by `RateCtrl` as `tau_ff`. The paper has no integral action in altitude; this model keeps the velocity integrator of the
position controller (and the PI vertical loop of the engage controller).

## Why some things look the way they do

* **Frame of the arm.** `Revolute3D` turns about the local z axis of its frame, so the joint frame is the body frame
  rotated -90 deg about x; the arm body frame is that frame turned back by +90 deg, so that the arm, the tip and the
  end-effector frames are aligned with the multirotor frame and the wheel geometry is written in world axes.
* **Bond direction.** A mount with the body on the `b` side must be bonded **mount to body** (`Mount.b -> Body.p`), like
  every wheel of `reaction-wheel-3d`; the same mount bonded body to mount flips the sign of the flow at the junction and
  the arm's gravity pushes the multirotor up (found by a free-fall test: two equal bodies on a joint stood still).
* **The contact starts after the wall has stopped the multirotor.** Switching to the (purely angular) contact controller
  as soon as the wheel plane is near the wall lets the multirotor bounce back and lose height: the thrust F_eq carries
  the weight only when the pitch is the equilibrium one, and nothing in the contact controller regulates the height. The
  supervisor therefore waits until the multirotor has been at rest within 2 cm of the wall (0.3 s).
* **Impact.** The wheel contact is stiff and the brush spring is not modelled, so the first impact peaks at 180 N for a
  few milliseconds (0.85 m/s); the Hunt-Crossley damping (c = 4 s/m) kills the bounces within 1 s.
* **Hand-over to the disengage.** The controller switch at 28.5 s saturates the mixer for 80 ms (pitch 27 deg to the free
  flight cascade); `Mix/sat` shows it.
* **Output size.** Every 4 ms discrete tick is recorded as a left/right event pair, so the 34 s run has 17 001 rows of
  2 566 signals (349 MB of `columns.f64`); the stdlib composites (`ElectricDrive` x6, three bodies, the joints, the
  contacts) account for most signals.

## Measured (real worker, reltol 1e-4)

| quantity | value |
| --- | --- |
| hover | height within 0.9 cm of the set-point, total thrust 24.4 N (m g = 24.33 N), rotors at 534 rad/s |
| wall force vs m g tan(theta_sp) | 6.74 N vs 6.99 N (17 deg), 8.29 vs 8.32 (20 deg), 9.53 vs 9.94 (23.5 deg), 11.4 to 11.6 vs 11.65 (27 deg); at most 0.68 N apart from 8.5 s on |
| wheel normal forces in contact | all three above 1.55 N (2.2 to 5.5 N each) |
| roll, yaw in contact | max 0.84 and 0.91 deg (the paper: below 7.5 deg) |
| pitch | follows theta_sp within 0.84 deg; 27.3 deg max |
| end-effector travel | +0.294 m in 6 s at command 0.125 (ideal 0.125 * 0.4 * 6 = 0.30 m), -0.305 m back; the multirotor follows within 0.7 cm with its set-points unchanged |
| disengage | x_b = 0.1872 m vs the latched 0.1943 m (-7 mm); wheel plane 0.7497 m from the wall; hover |
| actuators | rotor speed max 729 rad/s (limit 957), servo torque max 4.4 N m (limit 8.4) |
| cost | compile 1 to 3 s, solve about 19 s for 34 s (297 640 steps); 17 001 rows x 2 566 signals, columns.f64 349 MB; `run_checks.py --only aerial-contact` 60 s |

## Files

* `models/aerial-contact.bgmodel.json`, `bgsim.project.json`, `scenes/aerial-contact.sdf` (generated)
* `models/aerial-contact.docs/` (7 pages, 6 plots; `design/build_docs.py`, `design/docs_pages.md`)
* `library/`: `Esc`, `Propeller`, `RotorWrench`, `Mixer`, `Pack6`, `Unpack6` (the propulsion; copied and adapted from the
  quadcopter example), `ImuSensor`, `GpsSensor`, `NavFilter`, `SpecForce`, `Truth`, `PositionCtrl`, `AttitudeCtrl`,
  `RateCtrl`, `Supervisor`, `EngageCtrl`, `ContactCtrl`, `PhaseSelect`, `ArmServo`, `RubberMount`, `OmniContact`,
  `OmniDrive`, `WallForce`
* `design/design.py` (derivation and gains), `design/build_model.py`, `design/build_docs.py`, `design/docs_pages.md`
* `expected.json`: 62 checks (phase machine, normal force, the paper's 7.5 deg bound, locomotion, disengage, the K
  structure and values at three theta_sp, stability, scene bindings with the arm-axis forward-kinematics check, no
  diagnostics); the new `min_ge` kind of `examples/run_checks.py` keeps the wheel normal forces positive
* `web/tests/e2e/aerial-contact.spec.ts` (port 8786)
