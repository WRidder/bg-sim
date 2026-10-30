@@ figures quadcopter
{
  "diagram": {"kind": "diagram", "model": "quadcopter"},
  "climb": {"kind": "scene", "model": "quadcopter", "t": 3.0},
  "turn": {"kind": "scene", "model": "quadcopter", "t": 9.5},
  "landing": {"kind": "scene", "model": "quadcopter", "t": 16.8},
  "mission": {
    "kind": "plot", "model": "quadcopter", "xlim": [0, 18],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Truth/x", "label": "x"}, {"signal": "Truth/y", "label": "y"}, {"signal": "Truth/z", "label": "z"}, {"signal": "Mission/p_sp[1]", "label": "set-points", "style": ":", "color": "#1f77b4"}, {"signal": "Mission/p_sp[2]", "label": "_nolegend_", "style": ":", "color": "#d95f02"}, {"signal": "Mission/p_sp[3]", "label": "_nolegend_", "style": ":", "color": "#1b9e77"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "attitude [deg]", "series": [{"signal": "Truth/roll", "label": "roll", "scale": 57.29577951308232}, {"signal": "Truth/pitch", "label": "pitch", "scale": 57.29577951308232}, {"signal": "Truth/yaw", "label": "yaw", "scale": 57.29577951308232}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "tracking error [m]", "series": [{"signal": "Err/track", "label": "Err/track", "color": "#7570b3"}]}
    ]
  },
  "actuators": {
    "kind": "plot", "model": "quadcopter", "xlim": [0, 18],
    "rows": [
      {"ylabel": "rotor speed [rad/s]", "series": [{"signal": "Drv1/rotor/w", "label": "rotor 1"}, {"signal": "Drv2/rotor/w", "label": "rotor 2"}, {"signal": "Drv3/rotor/w", "label": "rotor 3"}, {"signal": "Drv4/rotor/w", "label": "rotor 4"}], "legend": true},
      {"ylabel": "battery [V] / [A]", "series": [{"signal": "Bat/V", "label": "Bat/V"}, {"signal": "Bat/I", "label": "Bat/I", "style": "--"}], "legend": true},
      {"ylabel": "leg normal force [N]", "series": [{"signal": "Leg1/f_n", "label": "Leg1"}, {"signal": "Leg2/f_n", "label": "Leg2"}, {"signal": "Leg3/f_n", "label": "Leg3"}, {"signal": "Leg4/f_n", "label": "Leg4"}], "legend": true}
    ]
  },
  "estimator": {
    "kind": "plot", "model": "quadcopter", "xlim": [0, 18],
    "rows": [
      {"ylabel": "position error [cm]", "series": [{"signal": "Err/pos", "label": "Err/pos", "scale": 100}], "legend": true},
      {"ylabel": "attitude error [deg]", "series": [{"signal": "Err/att", "label": "Err/att", "scale": 57.29577951308232}], "legend": true},
      {"ylabel": "velocity error [m/s]", "series": [{"signal": "Err/vel", "label": "Err/vel"}], "legend": true}
    ]
  }
}
@@ page quadcopter overview - | Overview
# Quadcopter with a cascaded flight controller

A 1.35 kg, 450 mm X quadcopter with a PX4-style cascaded flight controller, flown from the ground: take-off to 1 m, a 2 m x 2 m mission with a 90 degree yaw turn, a landing (X5.7). The airframe is a multibond floating body, every rotor is a motor plus propeller chain, the controller sees only sensors and a navigation filter, and the plant stands on four compliant contact legs. $z$ is up, units are SI.

| model | what it is |
| --- | --- |
| `quadcopter` (this model) | the 18 s mission, `reltol` 1e-4, `abstol` 1e-6, output every 10 ms (1801 points) |
| `quadcopter-repeat` | the same document stopped at 9 s on the same output grid: the determinism twin |

The model document and the 3D scene are **generated**: `uv run examples/quadcopter/design/build_model.py` writes `models/*.bgmodel.json` and `scenes/quadcopter.sdf` from the numbers of `design/design.py`; `uv run examples/quadcopter/design/design.py` prints the derivation of the gains and the loop margins.

![The model canvas|900](@fig:diagram)

## Run it

Press **Run**. The README measured 41 to 65 s of solve time on a loaded machine (51 800 solver steps, compile 1 to 3 s); every 2 ms discrete tick is recorded as a left/right event pair, so the run holds about 18 000 rows of 1559 signals (about 225 MB of data). Plot the mission ([Truth/x](signal:Truth/x), [Truth/y](signal:Truth/y), [Truth/z](signal:Truth/z) with [Mission/p_sp[1]](signal:Mission/p_sp[1])), the rotor speeds ([Drv1/rotor/w](signal:Drv1/rotor/w)), the battery ([Bat/V](signal:Bat/V), [Bat/I](signal:Bat/I)) and the estimator errors ([Err/pos](signal:Err/pos), [Err/att](signal:Err/att), [Err/vel](signal:Err/vel)).

## 3D view

`scenes/quadcopter.sdf` has the link `body` (pose binding `Truth/q[1..4]`, `Truth/x`, `y`, `z`), the joints `rotor_1..4` (position bindings `Drv<k>/rotor/phi`, gain -1 for the clockwise rotors 3 and 4) and the ground link with the pads. Three moments of the mission: the climb, the first turn and the final descent.

![Climb: t = 3 s|420](@fig:climb)

![Yaw turn: t = 9.5 s|420](@fig:turn)

![Descent: t = 16.8 s|420](@fig:landing)

Continue with [the architecture](page:architecture), [the flight controller](page:controller), [the estimator](page:estimator), [the results](page:results) and [the notes](page:notes).
@@ page quadcopter architecture overview | Architecture
# Architecture

```
Mission (Waypoints, 50 Hz) --p_sp,v_sp,a_sp,psi--> Pos (PositionCtrl, 50 Hz) --qd,F--> Att (AttitudeCtrl, 250 Hz)
                                                      ^  ^                                | w_sp
Nav (NavFilter, 500 Hz) --p,v,q----------------------+  +--- q --- Att                     v
  ^   ^                                           --- w ---------------------------> Rate (RateCtrl, 500 Hz)
  |   +-- Gps (GpsSensor, 50 Hz): p, v, heading                                            | tau
  +------ Imu (ImuSensor, 500 Hz): gyro, accel + low-pass                   Mix (QuadMixer, 500 Hz) <-- F
                                                                                           | w_cmd[4]
Esc1..4 (Esc, 500 Hz: speed PI + motor-model feed-forward, voltage and current limits) <---+
  | u                                                                   Bat (Battery) --V--> Esc
  v
Drv1..4 (stdlib ElectricDrive) --shaft--> Prop1..4 (Propeller: T = kT w|w|, Q = kQ w|w|)
  | i, w, P_el                                            | T
  +------------> RW (RotorWrench) <-- body twist, pose, wind, leg forces
                   | tx ty tz fx fy fz
World (GroundSpatial) -- Free (Free3D) -- Body (RigidBody3D) -- Wrench (ExternalWrenchSpatial)
                                             '-- Mount_k -- Leg_k (ContactPoint) ... Ground (ContactSurface)
```

- **Airframe.** [World](block:World) (`GroundSpatial`) to [Free](block:Free) (`Free3D`) to [Body](block:Body) (`RigidBody3D`): 13 states (quaternion, position and the 6 momenta), gravity inside the body, six zero-effort `Se` sources ([FreeSe1](block:FreeSe1) to `FreeSe6`) on the unused drive ports of the free joint. Body frame: $x$ forward, $y$ left, $z$ up, origin at the centre of mass.
- **Landing gear.** Four `ContactPoint` legs ([Leg1](block:Leg1) to `Leg4`; Hertz contact against one [Ground](block:Ground) `ContactSurface` plane, $k = 2\cdot10^4$ N/m, $\mu = 0.6$) at $(\pm0.11, \pm0.11, -0.085)$ m; they carry $m g = 13.24$ N on the ground and let take-off and landing happen in the same model. The accelerometer feels their normal force.
- **Rotors** (x4). Each is [Esc1](block:Esc1) to [Drv1](block:Drv1) to [Prop1](block:Prop1). `ElectricDrive` is the stdlib bond graph motor: $R = 0.11\ \Omega$, $L = 40\ \mu$H, EM gyrator $k_t = 0.01038$ N·m/A (a 920 kV motor), rotor plus propeller inertia $J_m = 5\cdot10^{-5}$ kg·m². `Propeller` is a rotation one-port load with drag torque $Q = k_Q\,\omega\lvert\omega\rvert$ ($k_Q = 2.03\cdot10^{-7}$) and thrust $T = k_T\,\omega\lvert\omega\rvert$ ($k_T = 1.42\cdot10^{-5}$: 3.19 N at the hover speed of 482 rad/s, 8.5 N at 775 rad/s). Spin directions alternate along the diagonals.
- **Airframe wrench.** [RW](block:RW) (`RotorWrench`) assembles, in the body frame, the thrust force and its moments $r_k \times T_k e_z$, the **motor reaction torque** $-\mathrm{spin}_k\,(k_t i_k - b_m\omega_k)$ (the stator is the airframe, so the reaction of the rotor's inertia torque and of the propeller drag acts on it and the motor power balances), the gyroscopic term $-\Omega \times h$ of the rotors' spin momentum, linear air drag against $(v - R^T\,\mathrm{wind})$ and a small rotational damping; the six components drive one stdlib `ExternalWrenchSpatial` ([Wrench](block:Wrench)) on the body.
- **Battery.** [Bat](block:Bat): a 3S pack with open-circuit voltage linear in the state of charge and 20 mΩ series resistance; it delivers the electrical power of the four motors, so the terminal voltage sags with the load (11.4 V at the 62 A spin-up). The ESCs limit their output by this live voltage.
- **Wind.** [Wind](block:Wind) (a new Gaussian gust every 0.5 s, mean $(0.4, -0.2)$ m/s, $\sigma = 0.5$ m/s) through a 1 s [Gust](block:Gust) lag into the drag of `RotorWrench`.
- **Mission.** [Mission](block:Mission) (`Waypoints`, 50 Hz): sums of minimum-jerk moves with exact velocity, acceleration and yaw-rate feed-forward: climb 1 m at 1 s (3 s), +2 m in $x$ at 5 s, +2 m in $y$ with a +90 degree turn at 8 s, back to the origin with a -90 degree turn at 11 s, descend at 14 s; armed 0.5 s to 17.4 s.
@@ page quadcopter controller overview | Flight controller and design
# Flight controller

| block | rate | role |
| --- | --- | --- |
| [Pos](block:Pos) `PositionCtrl` | 50 Hz | position P with velocity feed-forward and speed limits, velocity PI with acceleration feed-forward and D on the measurement, thrust vector $F = m\,(a + g\,e_z)$ limited to 25 degrees of tilt; outputs the collective thrust and the desired attitude (body $z$ along $F$, heading $\psi_{sp}$) |
| [Att](block:Att) `AttitudeCtrl` | 250 Hz | quaternion-error P (PX4 `AttitudeControl`), rate limits |
| [Rate](block:Rate) `RateCtrl` | 500 Hz | PID with D on the filtered measurement, conditional-integration anti-windup, torque limits; the yaw axis has a first-order torque low-pass |
| [Mix](block:Mix) `QuadMixer` | 500 Hz | the pseudo-inverse of the allocation matrix; attitude has priority over collective thrust when a rotor would saturate (scale the torque part, then shift the collective part); speed command $\omega = \sqrt{T/k_T}$ |
| [Esc1](block:Esc1) `Esc` | 500 Hz | rotor speed PI plus the steady-state voltage of the motor model as feed-forward, limited to $0.98\,V_{bat}$ and to $k_e\omega + R\,i_{lim}$ ($i_{lim}$ = 25 A, the current limit of the spin-up) |

The mixer's `Minv` is the pseudo-inverse of the matrix with rows $(1,\ r_y,\ -r_x,\ -\mathrm{spin}\,k_Q/k_T)$ (`design.py` asserts $M\,M^{-1} = I$).

## Design (`design/design.py`)

| loop | design | result |
| --- | --- | --- |
| ESC speed (500 Hz) | PI plus feed-forward on the linearised motor | $K_p = 0.06$ V·s/rad, $K_i = 3$ V/rad: crossover 121 rad/s, PM 62 deg, closed-loop -3 dB at 197 rad/s |
| roll/pitch rate | $K_p = J\,\omega_r$ ($\omega_r = 38$ rad/s), $T_i = 0.3$ s, $T_d = 6$ ms, with the 80 Hz Butterworth, the ESC lag and the holds | $K_p = 0.437$, $K_i = 1.46$, $K_d = 0.0026$: crossover 40 rad/s, PM 73 deg, GM 13 dB |
| yaw rate | largest gain meeting PM $\ge$ 55 deg, GM $\ge$ 14 dB with the rotor-acceleration lead and the torque low-pass | $K_p = 0.13$, $K_i = 0.087$: crossover 37 rad/s, PM 100 deg, GM 14.3 dB |
| attitude | P on the quaternion error, $K$ = 6.5 /s (roll/pitch), 2.8 /s (yaw) | crossover 6.3 rad/s, PM 76 deg |
| velocity (xy) | PI, $K_v$ = 3 /s, $K_i$ = 1.5 /s² | crossover 2.9 rad/s, PM 50 deg, GM 13 dB |
| position (xy) | P, 1 /s | crossover 1.2 rad/s, PM 69 deg |
| vertical | velocity $K_v$ = 5 /s, $K_i$ = 4 /s²; position 1.5 /s | crossovers 5.1 and 1.7 rad/s, PM 71 and 73 deg |
| navigation filter | $L_1$ = 6, $L_2$ = 9, $L_3$ = 8 /s, $k_\theta$ = 12 /s², $k_b$ = 0.8 /s | error poles $-6.3 \pm 3.3\mathrm{j}$, $-0.66 \pm 0.83\mathrm{j}$ |

The cascade keeps a factor of 3 to 6 between the loops (rate 38, attitude 6.3, velocity 2.9, position 1.2 rad/s). The mass knowledge is 4 % off on purpose (controller 1.30 kg, plant 1.35 kg): the velocity integrator carries the difference.

## The yaw actuator

The yaw torque on the airframe is the rotors' reaction torque $\sum \mathrm{spin}\,(Q + J_m\dot\omega)$. Above $Q'/J_m = 3.8$ rad/s the acceleration torque dominates, so a yaw command acts through a lead with plateau gain $K_p J_m/(J_z Q')$. The first version with a roll-like yaw gain oscillated at 45 Hz. `design.py` models this actuator, searches the largest yaw gain with PM $\ge$ 55 deg and GM $\ge$ 14 dB ($K_p = 0.13$ N·m·s/rad, crossover 37 rad/s) and sets the torque low-pass (30 rad/s) of `RateCtrl`.
@@ page quadcopter estimator overview | Sensors and navigation filter
# Sensors and navigation filter

- [Imu](block:Imu) (`ImuSensor`, 500 Hz): gyro and accelerometer with constant biases (0.2 deg/s, 0.05 m/s²), white noise (0.01 deg/s/$\sqrt{\mathrm{Hz}}$, 300 µg/$\sqrt{\mathrm{Hz}}$) and 2nd-order Butterworth low-passes (gyro 80 Hz, accelerometer 30 Hz, bilinear coefficients from `design.py`).
- [Gps](block:Gps) (`GpsSensor`, 50 Hz): an RTK-quality fix of position (2 cm), velocity (5 cm/s) and heading (1 deg), held for 20 ms.
- Both read the true state ([Truth](block:Truth) and `RotorWrench.fs`); the controller never does.
- [Nav](block:Nav) (`NavFilter`, 500 Hz): a fixed-gain observer for attitude (quaternion), velocity, position and gyro bias. A multirotor's accelerometer measures thrust, not gravity, so the tilt is observed through the velocity: the specific force rotated by the estimated attitude propagates the velocity, the fix corrects it, and the cross product of the specific force with the velocity innovation corrects the attitude and the gyro bias (error dynamics in `design.py`, poles $-6.3 \pm 3.3\mathrm{j}$ and $-0.66 \pm 0.83\mathrm{j}$). The compass corrects the yaw.
- [Err](block:Err) (`EstError`) compares the estimate with the truth: `Err/pos`, `Err/vel`, `Err/att`, and the tracking distance `Err/track`.

## Why hash noise instead of the stdlib `Noise`

The stdlib block is a function of $t$ through `floor`; every step of its staircase is a solver event, and at some step times (6.5 s with a 0.5 s staircase, measured here) the root is not representable and the solver chatters until the event limit (W206). The sensors therefore use the same sine-hash Box-Muller sequence inside the discrete scope, indexed by the tick counter: deterministic, event-free, selectable by `seed`.
@@ page quadcopter results overview | Results and checks
# Results and checks

![Mission: position against set-points, attitude, tracking error|900](@fig:mission)

![Rotor speeds, battery and landing-gear forces|900](@fig:actuators)

![Navigation filter errors against the truth|900](@fig:estimator)

## Measured (README, real worker, `reltol` 1e-4)

| quantity | value |
| --- | --- |
| hover reached | rise 10-90 % in 1.5 s, overshoot 0.23 %, settled inside $\pm2$ cm 2.68 s after the start of the climb, hover band $\pm0.6$ cm |
| waypoint tracking (5 to 14.4 s) | RMS x 4.6 cm, y 5.0 cm, z 0.84 cm; worst distance to the set-point 12.0 cm (moves of 2 m in 2.5 to 3 s) |
| waypoints | (2.0013, 0) at 7.9 s, y = 2.016 at 10.9 s; yaw 1.603 rad at 10.9 s (set-point 1.571) |
| attitude | peak tilt 14.2 deg (limit 25), peak body rate 1.26 rad/s |
| rotors | hover 482 rad/s (4607 rpm), mission range 403 to 558 rad/s (peak 5325 rpm), limit 775 rad/s |
| electrical | hover 99 W, 7.96 A at 12.4 V; spin-up peak 62 A (pack sags to 11.4 V); 1.35 % of the 3 Ah pack used |
| navigation filter | attitude error RMS 0.53 deg, peak 1.08 deg; position error peak 2.9 cm; velocity error peak 0.11 m/s |
| landing | touches down at 17.1 s, rests at $z = 0.0847$ m with $m g$ on the four legs (13.2435 N) |
| cost | 18 s: 51 800 solver steps, compile 1 to 3 s, solve 41 to 65 s (loaded machine), 142.6 s for `run_checks.py --only quadcopter` |

## Checks (`expected.json`, 38 on this model)

- ground start: [Truth/z](signal:Truth/z) = 0.085 m at $t = 0$ and the leg force `RW/fc` = 13.2435 N at 0.3 s; the climb step response from 0.085 to 1.085 m (settling band 0.02 m); hover at 4.9 s: 1.085 m, rotor speed 482.4 rad/s (tolerance 8), battery current 7.96 A (tolerance 1.5);
- waypoints: $x = 2.0$ at 7.9 s (0.03), $y = 2.0$ at 10.9 s (0.04), yaw 1.5707963 at 10.9 s (0.06); RMS differences to the set-points over $[5, 14.4]$ s at most 0.06 / 0.065 / 0.015 m; tracking distance at most 0.15 m;
- attitude: tilt at most 0.3 rad (measured peak 0.247), roll and pitch at most 0.3 rad, quaternion norm error at most 1e-9;
- landing: $z = 0.085$ m and `RW/fc` = 13.2435 N at 18 s;
- actuators: rotor speeds at most 774.6 rad/s (peak 557.6, tolerance 25), `Esc1/u` at most 12.6 V, motor current at most 50 A, battery current at most 70 A, state of charge 0.9865 at 18 s;
- estimator: `Err/att` at most 0.03 (measured peak 0.0188), `Err/pos` at most 0.05 m, `Err/vel` at most 0.2 m/s, the gyro noise RMS against the truth at most 0.0075 rad/s, the attitude controller's rate set-point against the filter at most 0.07;
- `scene_bindings`, and no E901, E106, E007, W201, W202, W205 or W206.
@@ page quadcopter notes overview | Notes and reuse
# Notes

- **Tolerances.** `reltol` 1e-4 / `abstol` 1e-6 gives the same trajectory as 1e-6 / 1e-8 to 2.3 micrometres over the whole mission and halves the run time; the discrete ticks (2 ms) limit the step anyway.
- **Output size.** Every 2 ms discrete tick is recorded as a left/right event pair, so the 18 s run has about 18 000 rows of 1559 signals.
- **Determinism.** The twin model `quadcopter-repeat` stops at 9 s on the same output grid; eight `compare` entries check that signals such as `Imu/gyro[1]` agree with the full run to 1e-12.
- **Reuse (X5.8).** The pieces are separated so the aerial-manipulator example can reuse them: `RotorWrench` (N rotors), `Propeller`, `Esc`, `Battery`, `QuadMixer` (`Minv`, `N`; a hexarotor needs a new `Minv` and `N` = 6), the sensors and `NavFilter`, and the three controller blocks, which only exchange `qd`/`F`, `w_sp` and `tau`. A manipulator reaction wrench can be added as a second `ExternalWrenchSpatial` bond on `Body.p`.
@@ figures quadcopter-repeat
{
  "run": {
    "kind": "plot", "model": "quadcopter-repeat", "xlim": [0, 9],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Truth/x", "label": "x"}, {"signal": "Truth/y", "label": "y"}, {"signal": "Truth/z", "label": "z"}], "legend": true, "legend_loc": "upper left"}
    ]
  }
}
@@ page quadcopter-repeat overview - | Overview
# Determinism twin

The same document as `quadcopter`, stopped at $t = 9$ s on the same output grid (901 points; `reltol` 1e-4, `abstol` 1e-6). It exists so that the example runner can check that two runs of the same model give identical results: the check compares [Truth/z](signal:Truth/z) at 4.9 s with 1.0859 m (tolerance 1e-3) and no E901, E106, E007, W201, W202, W205 or W206 appears. The eight `compare` entries of `expected.json` check that signals of the full 18 s run (for example `Imu/gyro[1]`) agree with this twin to 1e-12 from $t = 0$. The model and its physics are documented in the `quadcopter` model.

![Mission position over the first 9 s|900](@fig:run)
