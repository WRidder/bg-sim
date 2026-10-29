# quadcopter (X5.7)

A 1.35 kg, 450 mm X quadcopter with a PX4-style cascaded flight controller, flown from the ground:
take-off to 1 m, a 2 m x 2 m mission with a 90 degree yaw turn, a landing. The airframe is a multibond
floating body, every rotor is a motor + propeller chain, the controller sees only sensors and a
navigation filter, and the plant stands on four compliant contact legs. Z is up, units are SI.

| model | what it is |
| --- | --- |
| `quadcopter` | the 18 s mission, reltol 1e-4, abstol 1e-6, output every 10 ms |
| `quadcopter-repeat` | the same document stopped at 9 s on the same output grid: the determinism twin |

The model document and the 3D scene are **generated**: `uv run examples/quadcopter/design/build_model.py`
writes `models/*.bgmodel.json` and `scenes/quadcopter.sdf` from the numbers of
`design/design.py`. `uv run examples/quadcopter/design/design.py` prints the derivation of the gains
and the loop margins (below).

## Architecture

```
 Mission (Waypoints, 50 Hz) --p_sp,v_sp,a_sp,psi--> Pos (PositionCtrl, 50 Hz) --qd,F--> Att (AttitudeCtrl, 250 Hz)
                                                       ^  ^                                  | w_sp
 Nav (NavFilter, 500 Hz) --p,v,q--------------------+  +--- q --- Att                        v
   ^   ^                                            --- w ----------------------------> Rate (RateCtrl, 500 Hz)
   |   +-- Gps (GpsSensor, 50 Hz): p, v, heading                                              | tau
   +------ Imu (ImuSensor, 500 Hz): gyro, accel + low-pass                    Mix (QuadMixer, 500 Hz) <-- F
                                                                                              | w_cmd[4]
 Esc1..4 (Esc, 500 Hz: speed PI + motor-model feed-forward, voltage and current limits) <-----+
   | u                                                                      Bat (Battery) --V--> Esc
   v
 Drv1..4 (stdlib ElectricDrive: R, L, k_t, rotor + propeller inertia) --shaft--> Prop1..4 (Propeller: T = kT w|w|, Q = kQ w|w|)
   | i, w, P_el                                              | T
   +------------> RW (RotorWrench) <-- body twist, pose, wind, leg forces
                    | tx ty tz fx fy fz
 World (GroundSpatial) -- Free (Free3D) -- Body (RigidBody3D, m, J) -- Wrench (ExternalWrenchSpatial)
                                              |-- Mount_k -- Leg_k (stdlib ContactPoint) ... Ground (ContactSurface)
```

* **Airframe.** `GroundSpatial -> Free3D -> RigidBody3D` (13 states: quaternion + position + the 6
  momenta), gravity inside the body, six zero-effort `Se` on the unused drive ports of the free joint.
  Body frame: x forward, y left, z up, origin at the centre of mass.
* **Landing gear.** Four `ContactPoint` legs (Hertz contact against one `ContactSurface` plane,
  k = 2e4 N/m, mu = 0.6) at (+-0.11, +-0.11, -0.085) m; they carry m g = 13.24 N on the ground and let
  the take-off and the landing happen in the same model. The accelerometer feels their normal force.
* **Rotors** (x4). Each is `Esc -> ElectricDrive -> Propeller`. `ElectricDrive` is the stdlib bond-graph
  motor (voltage source, R = 0.11 Ohm, L = 40 uH, EM gyrator k_t = 0.01038 N m/A for a 920 kV motor, rotor +
  propeller inertia J_m = 5e-5 kg m^2). `Propeller` is a rotation one-port load, drag torque
  Q = kQ w|w| (kQ = 2.03e-7), and outputs the thrust T = kT w|w| (kT = 1.42e-5: 3.19 N at the hover
  speed of 482 rad/s, 8.5 N at 775 rad/s). Spin directions alternate along the diagonals.
* **Airframe wrench.** `RotorWrench` assembles, in the body frame, the thrust force and its moments
  (r_k x T_k e_z), the **motor reaction torque** -spin_k (k_t i_k - b_m w_k) (the stator is the airframe,
  so the reaction of the rotor's inertia torque and of the propeller drag acts on it and the motor power
  balances), the gyroscopic term -Omega x h of the rotors' spin momentum, linear air drag
  against (v - R^T wind) and a small rotational damping; the six components drive one stdlib
  `ExternalWrenchSpatial` on the body.
* **Battery.** `Battery`: 3S pack, open-circuit voltage linear in the state of charge, 20 mOhm series
  resistance; it delivers the electrical power of the four motors, so the terminal voltage sags with the
  load (11.4 V at the 62 A spin-up). The ESCs limit their output by this live voltage.
* **Sensors.** `ImuSensor` (500 Hz): gyro and accelerometer with constant biases (0.2 deg/s, 0.05 m/s^2),
  white noise (0.01 deg/s/sqrt(Hz), 300 ug/sqrt(Hz)) and 2nd-order Butterworth low-passes (gyro 80 Hz,
  accelerometer 30 Hz, bilinear coefficients from `design.py`). `GpsSensor` (50 Hz): an RTK-quality fix
  of position (2 cm), velocity (5 cm/s) and heading (1 deg), held for 20 ms. Both read the TRUE state
  (`Truth`, `RotorWrench.fs`); the controller never does.
* **Navigation filter** (`NavFilter`, 500 Hz): fixed-gain observer for attitude (quaternion), velocity,
  position and gyro bias. A multirotor's accelerometer measures thrust, not gravity, so the tilt is observed
  through the velocity: the specific force rotated by the estimated attitude propagates the velocity, the
  fix corrects it, and the cross product of the specific force with the velocity innovation corrects the
  attitude and the gyro bias (error dynamics in `design.py`, poles -6.3+-3.3j and -0.66+-0.83j). The
  compass corrects the yaw.
* **Flight controller.** `PositionCtrl` (50 Hz): position P with velocity feed-forward and speed limits ->
  velocity PI with acceleration feed-forward and D on the measurement -> thrust vector
  F = m (a + g e_z) limited to 25 degrees of tilt -> collective thrust and the desired attitude (body z
  along F, heading psi_sp). `AttitudeCtrl` (250 Hz): quaternion-error P (PX4 `AttitudeControl`), rate limits.
  `RateCtrl` (500 Hz): PID with D on the filtered measurement, conditional-integration anti-windup, torque
  limits; the yaw axis has a first-order torque low-pass (see "the yaw actuator"). `QuadMixer` (500 Hz):
  the pseudo-inverse of the allocation matrix, attitude has priority over collective thrust when a rotor
  would saturate (scale the torque part, then shift the collective part), speed command w = sqrt(T / kT).
  `Esc` (500 Hz): rotor speed PI + the steady-state voltage of the motor model as feed-forward, limited to
  0.98 V_bat and to k_e w + R i_lim (25 A, the current limit of the spin-up).
* **Mission.** `Waypoints` (50 Hz): sums of minimum-jerk moves with exact velocity, acceleration and yaw
  rate feed-forward: climb 1 m at 1 s (3 s), +2 m x at 5 s, +2 m y with a +90 degree turn at 8 s,
  back to the origin with a -90 degree turn at 11 s, descend at 14 s; armed 0.5 s to 17.4 s.
* **Wind.** `Wind` (a new Gaussian gust every 0.5 s, mean (0.4, -0.2) m/s, sigma 0.5 m/s) through a 1 s
  `Gust` lag into the drag of `RotorWrench`.

## Why some things look the way they do

* **Hash noise in the discrete sensor blocks, not the stdlib `Noise`.** The stdlib block is a function
  of `t` through `floor`; every step of its staircase is a solver event, and at some step times
  (6.5 s with a 0.5 s staircase, measured here) the root is not representable and the solver chatters
  until the event limit (W206). The sensors therefore use the same sine-hash Box-Muller sequence inside
  the discrete scope, indexed by the tick counter: deterministic, event-free, selectable by `seed`.
* **The yaw actuator.** The yaw torque on the airframe is the rotors' reaction torque sum(spin (Q + J_m dw/dt)).
  Above Q'/J_m = 3.8 rad/s the acceleration torque dominates, so a yaw command acts through a lead with
  plateau gain Kp J_m/(J_z Q'). The first version with a roll-like yaw gain oscillated at 45 Hz. `design.py`
  models this actuator, searches the largest yaw gain with phase margin >= 55 deg and gain margin >= 14 dB
  (Kp = 0.13 N m s/rad, crossover 37 rad/s) and sets the torque low-pass (30 rad/s) of `RateCtrl`.
* **Tolerances.** reltol 1e-4 / abstol 1e-6 gives the same trajectory as 1e-6 / 1e-8 to 2.3 micrometres over
  the whole mission and halves the run time; the discrete ticks (2 ms) limit the step anyway.
* **Output size.** Every 2 ms discrete tick is recorded as a left/right event pair, so the 18 s run has
  18 001 rows of 1 559 signals (about 225 MB of `columns.f64`).

## Design (design/design.py)

| loop | design | result |
| --- | --- | --- |
| ESC speed (500 Hz) | PI + feed-forward on the linearised motor (L, R, k_t, J_m, propeller slope) | Kp 0.06 V s/rad, Ki 3 V/rad: crossover 121 rad/s, PM 62 deg, closed-loop -3 dB at 197 rad/s |
| roll/pitch rate | Kp = J w_r (w_r = 38 rad/s), Ti 0.3 s, Td 6 ms, with the 80 Hz Butterworth, the ESC lag and the holds | Kp 0.437, Ki 1.46, Kd 0.0026: crossover 40 rad/s, PM 73 deg, GM 13 dB |
| yaw rate | largest gain meeting PM >= 55 deg, GM >= 14 dB with the rotor-acceleration lead and the torque low-pass | Kp 0.13, Ki 0.087: crossover 37 rad/s, PM 100 deg, GM 14.3 dB |
| attitude | P on the quaternion error, K = 6.5 /s (roll/pitch), 2.8 /s (yaw) | crossover 6.3 rad/s, PM 76 deg |
| velocity (xy) | PI, Kv 3 /s, Ki 1.5 /s^2 | crossover 2.9 rad/s, PM 50 deg, GM 13 dB |
| position (xy) | P, 1 /s | crossover 1.2 rad/s, PM 69 deg |
| vertical | velocity Kv 5 /s, Ki 4 /s^2; position 1.5 /s | crossovers 5.1 and 1.7 rad/s, PM 71 and 73 deg |
| navigation filter | L1 6, L2 9, L3 8 /s, kth 12 /s^2, kb 0.8 /s | error poles -6.3+-3.3j, -0.66+-0.83j |

The cascade keeps a factor of 3 to 6 between the loops (rate 38, attitude 6.3, velocity 2.9, position
1.2 rad/s). The mixer's `Minv` is the pseudo-inverse of [1; r_y; -r_x; -spin kQ/kT] (`design.py` asserts
M Minv = I). Mass knowledge is 4 % off on purpose (controller 1.30 kg, plant 1.35 kg): the velocity
integrator carries the difference.

## Measured (real worker, reltol 1e-4)

| quantity | value |
| --- | --- |
| hover reached | rise 10-90 % in 1.5 s, overshoot 0.23 %, settled inside +-2 cm 2.68 s after the start of the climb, hover band +-0.6 cm |
| waypoint tracking (5 to 14.4 s) | RMS x 4.6 cm, y 5.0 cm, z 0.84 cm; worst distance to the set-point 12.0 cm (moves of 2 m in 2.5 to 3 s) |
| waypoints | (2.0013, 0) at 7.9 s, y = 2.016 at 10.9 s; yaw 1.603 rad at 10.9 s (set-point 1.571) |
| attitude | peak tilt 14.2 degrees (limit 25), peak body rate 1.26 rad/s |
| rotors | hover 482 rad/s (4607 rpm), mission range 403 to 558 rad/s (peak 5325 rpm), limit 775 rad/s |
| electrical | hover 99 W, 7.96 A at 12.4 V; spin-up peak 62 A (pack sags to 11.4 V); 1.35 % of the 3 Ah pack used |
| navigation filter | attitude error RMS 0.53 deg, peak 1.08 deg; position error peak 2.9 cm; velocity error peak 0.11 m/s |
| landing | touches down at 17.1 s, rests at z = 0.0847 m with m g on the four legs (13.2435 N) |
| cost | 18 s: 51 800 solver steps, compile 1 to 3 s, solve 41 to 65 s (loaded machine), 142.6 s for `run_checks.py --only quadcopter` (both models plus the worker start) |

## Reuse (X5.8)

The pieces are separated so the aerial-manipulator example can reuse them: `RotorWrench` (N rotors: `rx`,
`ry`, `spin`, `onev` and the constant `N`), `Propeller`, `Esc`, `Battery`, `QuadMixer` (`Minv`, `N`; a
hexarotor needs a new `Minv` and `N = 6`), the sensors and `NavFilter`, and the three controller blocks,
which only exchange `qd`/`F`, `w_sp` and `tau`. A manipulator reaction wrench can be added as a second
`ExternalWrenchSpatial` bond on `Body.p`; the `Waypoints` table holds eight moves (`W`).

## Files

* `models/quadcopter.bgmodel.json`, `models/quadcopter-repeat.bgmodel.json` (generated), `bgsim.project.json`
* `library/` `RotorWrench`, `Propeller`, `Battery`, `Esc`, `QuadMixer`, `RateCtrl`, `AttitudeCtrl`,
  `PositionCtrl`, `NavFilter`, `ImuSensor`, `GpsSensor`, `Waypoints`, `Wind`, `Gust`, `Truth`, `EstError`,
  `Pack3`, `Pack4`, `Unpack4`
* `design/design.py` (gain derivation), `design/build_model.py` (model and scene generator)
* `scenes/quadcopter.sdf`: link `body` (pose binding `Truth/q[1..4]`, `Truth/x`, `y`, `z`), joints `rotor_1..4`
  (position bindings `Drv<k>/rotor/phi`, gain -1 for the clockwise rotors 3 and 4), ground link with the pads
* `expected.json`: 38 checks on the mission, the actuators, the estimator, the scene bindings and the
  diagnostics, plus 2 on the twin and eight `compare` entries (bit-identical discrete parts against the twin)
* `web/tests/e2e/quadcopter.spec.ts` (port 8782)
