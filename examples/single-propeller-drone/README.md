# single-propeller-drone — a swashplateless mono-rotor with one motor, no servos, no yaw actuator

A 1.2 kg drone that flies on **one propeller and one motor**. Roll and pitch come from a
once-per-revolution modulation of the motor torque: the rotor speeds up and slows down within
each turn, the lag-pitch hinges turn that acceleration into a cyclic blade pitch, and the
unequal lift of the two blades is a hub moment that tilts the vehicle (the model applies a pure
hub moment; the thrust stays on the body axis). Throttle is rotor speed. There is
**no yaw actuator at all**: four fins in the rotor slipstream carry the motor reaction and damp
the yaw rate. Nothing holds the heading; the vehicle flies on whatever heading it has.

It is inspired by Joshua Bird's
[`jyjblrd/single-propeller-drone`](https://github.com/jyjblrd/single-propeller-drone) and its
ArduPilot `MCOUT` / moteus `mcout` firmware, which streams roll/pitch/throttle to a motor
controller that adds a phase-locked cyclic torque from the encoder angle.

| model | what it is |
| --- | --- |
| `single-propeller-drone` | 20 s: released in hover at 1.32 m (a hand launch, no take-off), +1.5 m in x, +1.5 m in y, the land mode (a steady 0.25 m/s descent from hover until the feet carry weight), touchdown, disarm and motor run-down |
| `single-propeller-drone-hover` | 8 s: released in hover with a 0.8 rad/s yaw kick and a 0.3 rad/s roll kick, then a 1 m lateral step from 3 s: the control and passive-yaw test |

Both run with `reltol` 1e-5, `abstol` 1e-7 and an output every 10 ms. The model documents, the
`Leg` and `Motor` subsystems and the 3D scene are **generated**:
`uv run examples/single-propeller-drone/design/build_model.py` writes them from
`design/design.py`. Run `uv run examples/single-propeller-drone/design/design.py` for every
reference number quoted below.

## Plant

* **Airframe.** A 6-DOF multibond rigid body (`GroundSpatial -> Free3D -> RigidBody3D`), z up,
  origin at the centre of mass. `design.py` places a parts list (body tube, stator, fins, legs,
  rotor) and computes the CoM (10.8 mm above the body-tube centre) and the inertia of
  everything that does not spin, $J=(0.01460,0.01460,0.00321)$ kg m². The rotor's spin
  inertia $J_a=3.506\cdot10^{-4}$ kg m² is **not** in $J_z$; it lives in `PropRotor`.
* **Rotor.** `PropRotor` is a gyrostat on the body 1-junction: it stores only the axial spin
  momentum, so the gyroscopic torque $-\omega\times h\,e_z$ reaches the body through the
  spatial bond. Its sign is $J_x\dot p=\tau_x-hq$, $J_y\dot q=\tau_y+hp$. Thrust and drag use the
  absolute spin rate $W=h/J_a$: $T=k_TW|W|$, $Q=k_QW|W|$.
* **Swashplateless hub moment.** `PropRotor` computes it from its **own state**, not from the
  command: $\tau_{net}=\tau_{motor}-Q=J_a\dot W$ is the torque that accelerates the rotor, and the
  quasi-static lag-pitch hinges give $M_x=2k_M\tau_{net}\cos\psi$, $M_y=2k_M\tau_{net}\sin\psi$.
  A once-per-revolution torque $c_x\cos\psi+c_y\sin\psi$ therefore gives the mean moment
  $k_M(c_x,c_y)$ plus a 2/rev ripple; whatever else accelerates the rotor (the speed loop
  pushing back on the ripple, the current loop's lag) shows up in the moment too, so the
  realised moment is not exactly the request (table below). $k_M=0.25$ is
  an assumed value (no bench data); the global `cyclic_gain` sets it, while the allocation keeps
  its own fixed estimate 0.25, so a different `cyclic_gain` is a real model mismatch.
* **Drive.** A `Shaft` 1-junction joins the rotor's motor port, a bearing loss `R` and the
  `Motor` subsystem, an instance of the library subsystem `library/Motor.bgsub.json` (both
  models use it with the same values, so it pins nothing), a bond graph: the stdlib `Battery` (6S, 3 Ah, OCV table, $R_0$ and an RC
  branch), the bus 0-junction with the 3 W avionics as a flow source, the inverter `MTF`
  (modulus = duty), the winding `R` (0.08 Ω) and `I` (50 µH) and the `EMConverter`
  ($k_t=0.030$ N m/A). `CyclicDrive` is the moteus current loop: it turns the collective torque
  of the speed loop (`RotorEsc`) plus the cyclic torque of the allocation into a duty
  (600 Hz current-loop bandwidth).
* **Fins.** `FinSet`: four low-aspect-ratio flat plates (90 cm² each, $C_{L\alpha}=0.856$/rad)
  inside the slipstream. The slipstream comes from momentum theory in axial flight,
  $v_i=-V_c/2+\sqrt{V_c^2/4+T/(2\rho A)}$, the axial wake speed at the fins is
  $k_wv_i$ ($k_w=1.854$ for the 0.25 m below the disc) and the swirl is set by the rotor torque,
  $u_t=Q/(\dot m\,r_f)$, $\dot m=\rho A(V_c+v_i)$. Nothing is calibrated: `design.py` solves the
  fin incidence (11.54°) that makes the fin yaw torque equal $Q$ at hover. Because the fin
  forces and $Q$ both scale with $\omega^2$, that balance holds at every rotor speed.
* **Air loads are imposed wrenches.** Thrust, hub moment, disc and body drag (`AeroWrench`) and
  the fin loads (`FinSet`) enter the body through `ExternalWrenchSpatial` sources: signals into
  a wrench source, not bonds; the air is not modelled. The motor reaction and the gyroscopic
  torque are bonded (through `PropRotor`).
* **Landing gear.** Four `Leg` subsystems (`library/Leg.bgsub.json`: a mount, a stdlib
  `ContactPoint` and its ground plane): Hertz contacts with damped pads, sized by
  Flores' relation for a restitution of 0.2 at the landing speed.
* **Sensors.** A 500 Hz IMU with bias and noise (the accelerometer reads the specific force of
  the air loads and the contacts, never gravity, each load once), a 100 Hz motion-capture fix,
  a 50 Hz IR-beacon heading.

## Controller

PX4-style cascade: `Waypoints` (50 Hz smooth 7th-order moves with velocity, acceleration and
jerk feed-forward; the land mode; the touchdown latch and the unload) → `PosCtrl` (50 Hz; thrust direction
from $(a_x,a_y,g)$, drag feed-forward, the jerk as a tilt-rate feed-forward) → `AttCtrl`
(250 Hz) → `RateCtrl` (400 Hz PI with the gyroscopic feed-forward $(hq,-hp)$) → `Alloc`
(400 Hz: thrust to rotor speed, moment to cyclic torque) → `RotorEsc` (400 Hz speed loop) →
`CyclicDrive` (current loop). `NavFilter` (500 Hz) fuses the IMU, the motion-capture fix and the
beacon; it also estimates the vertical accelerometer bias. A horizontal accelerometer bias
cannot be told from a tilt, so the vehicle really leans by about $b/g$ and the position loop's
integrator removes the drift.

Gains come from stated targets in `design.py` (rate crossover 20 rad/s, attitude 5 rad/s,
velocity $K_v=2$, $K_i=0.8$, position $K_p=0.6$), checked on a linear one-axis model with the
loop delays: minimum closed-loop damping 0.717. With the gyroscopic feed-forward the coupled
two-axis attitude/rate loops have damping 0.691; without it 0.360. The free nutation is at
$h/\sqrt{J_xJ_y}=12.94$ rad/s (2.060 Hz).

## Measured against design.py

Every reference below is derived in `design.py`; the measurement is from the checks
(`uv run examples/run_checks.py --only single-propeller-drone`).

| quantity | design.py | measured |
| --- | --- | --- |
| hover rotor speed $\sqrt{T_0/k_T}$, $T_0=mg+$ fin download 0.871 N | 539.11 rad/s | 539.04 rad/s (mean, 6–8 s) |
| yaw rate at hover with the trim incidence (the fin-law check) | 0 | 0.029 rad/s (mean, 6–8 s) |
| realised hub moment / moment request ($k_M/k_{M,est}$) | 1, no rotation | 1.084, rotated 4.2° (not a check; see below) |
| pack power / current at 7 s, motor current at hover | 187.94 W, 7.562 A, 10.84 A | 188.01 W, 7.565 A, 10.840 A |
| heading 3 s after the 0.8 rad/s kick, $r_0\tau(1-e^{-t/\tau})$, $\tau=(J_z+J_a)/D=0.870$ s | 0.674 rad | 0.684 rad |
| free nutation (rate loop off), $h/\sqrt{J_xJ_y}$ | 2.060 Hz | 2.020 Hz |
| 1 m step overshoot (linear model; with the accelerometer bias) | 1.27 cm; 2.42 cm | 1.77 cm |
| 1.5 m leg overshoot (with the bias) | 3.17 cm | 1.88 cm (x), 1.73 cm (y) |
| vertical accelerometer bias estimate | 0.08 m/s² (the IMU's) | 0.0796 m/s² |
| yaw rate in the 0.25 m/s descent (a model property, see below) | 0.859 rad/s | 0.827 rad/s (mean, 13–14.9 s) |
| feet reach the ground | 15.057 s | 15.061 s |
| touchdown load, four damped Hertz feet at once | ≤ 109.8 N | 85.2 N (peak hold `Aero/fc_max`; the feet touch one after another) |
| yaw rate after the impact, to rest | ≤ 0.457 rad/s | 0.127 rad/s |
| rise of the CoM above the contact height after the touchdown | ≤ 2.16 mm | 1.46 mm |
| yaw rate once landed (from 16.41 s) | 0 (friction 1.33 N m against 0.091 N m) | below 0.001 rad/s |
| rest height on the feet (static Hertz penetration 0.279 mm) | 0.18055 m | 0.180556 m |

Height in the hover model stays between 1.3155 and 1.3228 m (set-point 1.32). Peak tilt 0.145 rad
in the flight. Navigation errors in flight: attitude 0.0126 rad, position 0.0081 m, velocity
0.0157 m/s. The checks are not pinned to earlier runs: each compares a measurement with an
independent reference or a stated bound.

**Fin torque.** In any steady state the fin torque equals the rotor drag: the rotor gives the
motor torque $Q$, and the body passes the reaction on to the fins. So $Q_z=k_Q\omega^2$ holds
whatever the fin law, and the example does not check it. What the trim incidence sets is the
yaw rate at which the two balance, zero by `design.py`. An imbalance $\Delta Q$ would settle at
$\Delta Q/D$, so the hover check's 0.05 rad/s band is 0.2 mN m, 0.07 % of $Q_0$.

**Hub moment.** The realised hub moment per requested moment is 1.084, rotated 4.2°. This
comes from a separate run of the hover model over 0–5 s with the output every 0.1 ms. Both the
moment (`Rotor/Mx`, `Rotor/My`) and the request (`Rate/tau`) are averaged over one revolution and
fitted as one complex gain. It is not a check.

**Descent yaw.** The 0.859 rad/s in the 0.25 m/s descent is a property of the model's
assumptions, not a prediction for the real vehicle. The swirl uses the descent speed in the mass
flow through the disc, but $T=k_TW^2$ and $Q=k_QW^2$ ignore the inflow. The rate needs a torque
imbalance of only $D\cdot0.859=3.5$ mN m, 1.15 % of $Q_0$. In the descent the flow through the
disc drops by 1.5 % (8.41 to 8.29 m/s), which changes a real propeller's $k_T$ and $k_Q$ by an
amount of the same order. The check (6 %) shows only that the model agrees with its Python twin.

**Landing.** The land mode descends at 0.25 m/s, so the thrust carries the weight when the feet
touch. The fins carry the rotor drag in any state, so the only unbalanced yaw torque on the body
is the rotor's change of angular momentum. Any rotor speed lost while the feet do not hold the
body goes into its yaw ($J_a/J_z=0.109$ rad/s per rad/s). Before this was handled, the
50 Hz mission missed the 85 N impact (it sampled 0.31 N at 15.06 s) and latched the touchdown
only 0.2 s later. In between, the vertical loop read the rebound as a climb and cut the thrust,
and the speed loop slowed the rotor by 35 rad/s while the body was in the air: 3.27 rad/s of
yaw. The touchdown sequence now runs in three stages:

1. **Impact (15.060 s).** The drive (`RotorEsc`, 400 Hz) reads the peak hold `Aero/fc_max`, so it
   sees the impact at its next tick (15.0625 s). It brakes the rotor to 97 % of its speed at
   4000 rad/s², inside the 1.2 N m braking limit. The feet are pressed hard enough to hold the
   1.5 N m braking reaction from 0.32 to 5.59 ms of `design.py`'s impact simulation. At the
   latest tick, 4.2 rad/s of the brake falls outside that window, so the landing can leave at
   most 0.457 rad/s of yaw. The impact's friction stops the 0.84 rad/s descent yaw within 5 ms.
2. **Hold.** The mission latches the touchdown on its next tick (15.08 s), also from the peak
   hold. The position loop then holds its last thrust instead of reacting to the rebound, and
   the drive keeps the rotor at its cap. The thrust carries $0.97^2$ of the weight, so the
   rebound comes back down in a short hop: at most $(ev)^2/(2g(1-0.97^2))=2.16$ mm with the
   pads' design restitution $e=0.2$, measured 1.46 mm. The rate loop only damps while the feet
   are on the ground. An attitude or integral term would lean on the lightly loaded feet with the
   attitude estimate's error and rock the body.
3. **Unload (from 15.38 s).** The thrust comes off along a smooth step over 1 s, starting at the
   drive's cap. The rotor slows gently while the feet carry little and faster as they take the
   weight. The deceleration torque stays below 0.53 of the feet's friction. The flight
   controller is off at 16.38 s and the motor 2 s later.

The yaw rate after the impact peaks at 0.127 rad/s (0.135 rad/s inside the impact). Once landed,
the feet's friction (1.33 N m) holds the run-down torque ($J_a\cdot 260$ rad/s² $=0.091$ N m),
and the yaw rate stays below 0.001 rad/s.

**Cost.** Hover model: 23 790 solver steps (8 s, 10 s of solve on this machine); flight model:
110 969 steps (20 s, 14 s of solve). An earlier version of the example took 8 805 and 29 840 steps. The hub moment
now follows the rotor's revolution (a 2/rev ripple the solver resolves), and the winding current
is a state with a 0.6 ms time constant.

## What to try

* **Plant cyclic gain.** `cyclic_gain` (dashboard slider 0.10–0.40) changes the plant, not the
  allocation's estimate (0.25). In the hover model, 0.15 still flies the step (overshoot
  2.02 cm, cyclic torque up to 0.52 N m) and 0.40 too (1.88 cm). At 0.10 the attitude loop
  rings at 0.89 Hz after the roll kick and the step drives it unstable: the vehicle leaves the
  set-point (2.9 m off at 8 s) with the cyclic torque at its 0.8 N m limit.
* **Wind.** `wind_x = 2` m/s in the hover model: the vehicle is blown 0.36 m downwind before the
  velocity integrator builds the lean (−0.64 m/s² at 3 s), the step then overshoots 11.9 cm, and
  the heading keeps turning (2.58 rad at 8 s): a crossflow changes the fin torque only at second
  order (design.py: +0.85 mN m at 1 m/s), and nothing holds the heading.
* **No gyroscopic feed-forward.** Set `Rate/k_gyro = 0`: the rate loop then fights the
  precession with its PI alone (design.py: coupled damping 0.360 instead of 0.691).
* **Free nutation.** Set `Rate/Kp`, `Rate/Ki` and `Rate/k_gyro` to 0 in the hover model and plot
  `Truth/wb[1]`, `Truth/wb[2]`: the roll kick turns into a 2 Hz circular nutation.

## Files

* `models/single-propeller-drone.bgmodel.json`, `models/single-propeller-drone-hover.bgmodel.json` (generated)
* `library/Leg.bgsub.json` (generated: one landing leg, used four times)
* `library/Motor.bgsub.json` (generated: battery, bus, inverter, winding and EM converter, used
  once per model)
* `bgsim.project.json`, `expected.json`, `scenes/single-propeller-drone.sdf` (generated)
* `library/` `PropRotor`, `CyclicDrive`, `RotorEsc` (with the touchdown brake), `AeroWrench`, `FinSet`, `Alloc`, `PosCtrl`,
  `AttCtrl`, `RateCtrl`, `NavFilter`, `ImuSensor`, `Mocap`, `IrBeacon`, `Truth`, `EstError`,
  `Waypoints`, `AddVec3`
* `design/design.py` (mass properties, slipstream and fin trim, yaw damping, drive and battery
  operating point, gains and the linear models, nutation, landing and the touchdown sequence), `design/build_model.py`
  (model, subsystem and scene generator), `design/design.json`
* `tools/example_docs/src/single-propeller-drone.md` (docs source)

## 3D view

`scenes/single-propeller-drone.sdf` is generated from the same dimensions: the red body tube
(radius 0.05 m, 0.26 m long), the four fins at the fin station, the motor and bell, the 12 in
two-blade propeller (joint `rotor`, bound to the azimuth `Psi/y`), four feet, the start pad
under the release point and the landing pad at (1.5, 1.5). The body pose is bound to `Truth/q[1..4]`, `Truth/x`,
`Truth/y`, `Truth/z`.
