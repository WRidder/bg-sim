@@ figures @project
{
  "diagram": {"kind": "diagram", "model": "single-propeller-drone"}
}
@@ page @project mechanism - | The swashplateless mono-rotor
# One motor, one propeller, no servos

A conventional multirotor needs one motor per rotor, and a helicopter needs servos for every
tilt. This vehicle has **one motor** and **one propeller**, and still controls roll and pitch.
The motor controller modulates the torque once per revolution:

$$\tau_m(t)=\tau_{\mathrm{base}}+c_x\cos\psi+c_y\sin\psi .$$

The rotor speeds up and slows down within each turn. The two blades sit on **lag-pitch
hinges**: when the hub accelerates, the blades lag, and the skewed hinges turn the lag into
pitch, up on one blade and down on the other. The blade with more pitch makes more lift, so the
rotor exerts a hub moment on the body. The model computes that moment from the rotor's own
state, the torque that accelerates it, $\tau_{net}=\tau_m-Q=J_a\dot W$:

$$M_x=2k_M\,\tau_{net}\cos\psi,\qquad M_y=2k_M\,\tau_{net}\sin\psi .$$

A once-per-revolution torque gives the mean moment $k_M(c_x,c_y)$ plus a ripple at twice the
rotor frequency. The amplitude of $(c_x,c_y)$ sets the size of the moment, and its phase sets
the direction. $k_M=0.25$ is an assumed value; there is no bench data for it.

There is no third actuator, so **yaw cannot be commanded**. The four red fins sit in the rotor
slipstream. The slipstream carries the angular momentum the rotor torque puts into it (the
swirl), and the fins, lifting surfaces at a fixed incidence, turn that swirl into a torque that
opposes the motor reaction. The incidence is chosen so the two balance at hover. Both scale with
the rotor speed squared, so they balance at every speed. The fins also damp the yaw rate, but
nothing holds a heading. The real vehicle therefore uses an IR beacon for its heading estimate:
a magnetometer cannot compete with the motor current.

The example follows
[`jyjblrd/single-propeller-drone`](https://github.com/jyjblrd/single-propeller-drone) and its
ArduPilot `MCOUT` / moteus `mcout` firmware: the flight controller runs the attitude loops and
the motor controller adds the phase-locked cyclic torque from its encoder.

![The model canvas](@fig:diagram)

The two models are:

| model | what it is |
| --- | --- |
| `single-propeller-drone` | 20 s: released in hover at 1.32 m (a hand launch, no take-off), two 1.5 m legs, the land mode, touchdown, disarm and run-down |
| `single-propeller-drone-hover` | 8 s: released in hover with a yaw kick and a roll kick, then a 1 m lateral step |

Start with the [flight model](model:single-propeller-drone) or the
[hover and passive-yaw model](model:single-propeller-drone-hover).
@@ figures single-propeller-drone
{
  "hover": {"kind": "scene", "model": "single-propeller-drone", "t": 5.5, "zoom": 2},
  "leg-x": {"kind": "scene", "model": "single-propeller-drone", "t": 3.5, "zoom": 2},
  "landing": {"kind": "scene", "model": "single-propeller-drone", "t": 16.5, "zoom": 2},
  "mission": {
    "kind": "plot", "model": "single-propeller-drone", "xlim": [0, 20],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Truth/x", "label": "x"}, {"signal": "Truth/y", "label": "y"}, {"signal": "Truth/z", "label": "z"}, {"signal": "Mission/p_sp[1]", "label": "set-points", "style": ":", "color": "#1f77b4"}, {"signal": "Mission/p_sp[2]", "label": "_nolegend_", "style": ":", "color": "#d95f02"}, {"signal": "Mission/p_sp[3]", "label": "_nolegend_", "style": ":", "color": "#1b9e77"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "attitude [deg]", "series": [{"signal": "Truth/roll", "label": "roll", "scale": 57.29577951308232}, {"signal": "Truth/pitch", "label": "pitch", "scale": 57.29577951308232}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "tracking error [m]", "series": [{"signal": "Err/track", "label": "Err/track", "color": "#7570b3"}]}
    ]
  },
  "actuation": {
    "kind": "plot", "model": "single-propeller-drone", "xlim": [0, 20],
    "rows": [
      {"ylabel": "rotor speed [rad/s]", "series": [{"signal": "Rotor/w", "label": "Rotor/w"}], "legend": true},
      {"ylabel": "moment request [N m]", "series": [{"signal": "Rate/tau[1]", "label": "roll"}, {"signal": "Rate/tau[2]", "label": "pitch"}], "legend": true},
      {"ylabel": "cyclic torque [N m]", "series": [{"signal": "Alloc/cyc_amp", "label": "amplitude"}, {"signal": "Alloc/cyc_x", "label": "cyc_x", "style": "--"}, {"signal": "Alloc/cyc_y", "label": "cyc_y", "style": "--"}], "legend": true},
      {"ylabel": "drive", "series": [{"signal": "Motor/Imot/y", "label": "motor current [A]"}, {"signal": "Motor/Ibat/y", "label": "pack current [A]"}, {"signal": "Motor/BusV/y", "label": "bus voltage [V]"}], "legend": true}
    ]
  },
  "yaw": {
    "kind": "plot", "model": "single-propeller-drone", "xlim": [0, 20],
    "rows": [
      {"ylabel": "yaw rate [rad/s]", "series": [{"signal": "Truth/wb[3]", "label": "Truth/wb[3]"}], "legend": true},
      {"ylabel": "yaw torque [N m]", "series": [{"signal": "Rotor/Q", "label": "rotor drag"}, {"signal": "Fins/Qz", "label": "fin torque"}], "legend": true}
    ]
  },
  "touchdown": {
    "kind": "plot", "model": "single-propeller-drone", "xlim": [14.8, 17.0],
    "rows": [
      {"ylabel": "height [m]", "series": [{"signal": "Truth/z", "label": "CoM height"}, {"signal": "Mission/p_sp[3]", "label": "set-point", "style": ":"}], "legend": true},
      {"ylabel": "feet [N]", "series": [{"signal": "Aero/fc", "label": "normal force"}, {"signal": "Aero/fc_max", "label": "peak hold", "style": "--"}], "legend": true},
      {"ylabel": "rotor speed [rad/s]", "series": [{"signal": "Rotor/w", "label": "Rotor/w"}], "legend": true},
      {"ylabel": "yaw rate [rad/s]", "series": [{"signal": "Truth/wb[3]", "label": "Truth/wb[3]"}], "legend": true},
      {"ylabel": "mode", "series": [{"signal": "Esc/td", "label": "drive brake"}, {"signal": "Mission/contact", "label": "contact"}, {"signal": "Mission/thr", "label": "thrust fraction"}, {"signal": "Mission/armed", "label": "armed", "style": "--"}], "legend": true}
    ]
  },
  "estimator": {
    "kind": "plot", "model": "single-propeller-drone", "xlim": [0, 20],
    "rows": [
      {"ylabel": "position error [cm]", "series": [{"signal": "Err/pos", "label": "Err/pos", "scale": 100}], "legend": true},
      {"ylabel": "attitude error [deg]", "series": [{"signal": "Err/att", "label": "Err/att", "scale": 57.29577951308232}], "legend": true},
      {"ylabel": "velocity error [m/s]", "series": [{"signal": "Err/vel", "label": "Err/vel"}], "legend": true}
    ]
  }
}
@@ page single-propeller-drone overview - | Flight model
# Flight model

A 1.2 kg, 12 inch single-propeller drone. It is released in hover at 1.32 m (a hand launch:
there is no take-off), flies +1.5 m in $x$ and then +1.5 m in $y$, lands in the land mode and
switches off. Everything is SI, $z$ up, body origin at the centre of mass. The model documents
are generated by `design/build_model.py` from the numbers of `design/design.py`.

![Hovering after the x leg, 5.5 s](@fig:hover)

## Run it

Press **Run**. The 20 s run takes about 14 s of solve on the development machine (about
111 000 solver steps). The hub moment follows the rotor's revolution, and the solver resolves
that ripple. The dashboard sliders set the steady wind, the plant's cyclic gain and the cyclic
limit. Auto re-run is off, so press **Run** after a change.

## The plant

* **Airframe.** [World](block:World) (`GroundSpatial`) to [Free](block:Free) (`Free3D`) to
  [Body](block:Body) (`RigidBody3D`), with gravity in the body and zero-effort `Se` on the unused
  drive ports. `design.py` computes the centre of mass from a parts list and the inertia of
  everything that does not spin, $J=(0.01460,0.01460,0.00321)$ kg m². The rotor's spin inertia
  is not part of the body inertia.
* **Rotor.** [Rotor](block:Rotor) (`PropRotor`) is a gyrostat: it stores only the axial spin
  momentum, $J_a=3.506\cdot10^{-4}$ kg m². The motor reaction and the gyroscopic torque
  $-\omega\times h\,\mathbf{e}_z$ reach the body through the spatial bond, so
  $J_x\dot p=\tau_x-hq$ and $J_y\dot q=\tau_y+hp$. Thrust and drag use the absolute spin rate.
  [Rotor](block:Rotor) also computes the hub moment from its accelerating torque
  ([the mechanism](project:mechanism)). [Psi](block:Psi) integrates the azimuth.
* **Drive.** The [Shaft](block:Shaft) 1-junction joins the rotor, the bearing loss
  [Bearing](block:Bearing) and the [Motor](block:Motor) subsystem, an instance of the project
  library subsystem `Motor` (`library/Motor.bgsub.json`). It is a bond graph: the 6S pack
  `Motor/Bat`, the bus with the avionics load `Motor/Aux`, the inverter `Motor/Inv` (an `MTF`
  whose modulus is the duty), the winding `Motor/Rw` and `Motor/Lw` and the converter
  `Motor/EM`. [Drive](block:Drive) (`CyclicDrive`) is the
  current loop: it turns the collective torque plus the cyclic torque into the duty.
* **Fins.** [Fins](block:Fins) (`FinSet`) are four flat plates at incidence $\delta=11.54°$
  inside the slipstream. The slipstream comes from momentum theory (induced velocity, the wake
  speed at the fin station, the swirl set by the rotor torque, the climb speed through the
  disc). `design.py` solves the incidence that makes the fin torque equal the rotor drag at
  hover, and the fin download (0.871 N) that the thrust carries too.
* **Air loads.** [Aero](block:Aero) (`AeroWrench`) applies the thrust, the hub moment and the
  rotor-disc and body drag. These air loads, like the fin loads, are imposed wrenches (signals
  into a wrench source), not bonds: the air itself is not modelled.
* **Landing gear.** Four [Leg](block:Leg1) subsystems, each a mount, a `ContactPoint` and its
  ground plane: Hertz contacts with damped pads (restitution about 0.2 at the landing speed).
  [Aero](block:Aero) sums their normal forces and holds the peak (`Aero/fc_max`).

![The +1.5 m x leg at 3.5 s](@fig:leg-x)

![On the ground at 16.5 s, the rotor running down](@fig:landing)

Continue with [the controller and design](page:controller) and [the results](page:results).
@@ page single-propeller-drone controller overview | Control and design
# Control and design

The controller is a PX4-style cascade with a mixer for this vehicle: the roll and pitch moment
requests become a **cyclic motor torque**, the collective thrust becomes a **rotor speed**, and
there is no yaw channel.

| block | rate | role |
| --- | --- | --- |
| [Mission](block:Mission) `Waypoints` | 50 Hz | smooth 7th-order moves with velocity, acceleration and jerk; the land mode; the touchdown latch (from the peak hold), the thrust unload, disarm and motor stop |
| [Pos](block:Pos) `PosCtrl` | 50 Hz | position P, velocity PI with acceleration and drag feed-forward; thrust direction from $(a_x,a_y,g)$, limited to 0.20 rad; the jerk as a tilt-rate feed-forward; the **measured** heading in the desired attitude |
| [Att](block:Att) `AttCtrl` | 250 Hz | quaternion-error P on roll and pitch only |
| [Rate](block:Rate) `RateCtrl` | 400 Hz | PI on the body rates plus the gyroscopic feed-forward $(hq,-hp)$, $h=J_a\omega$ |
| [Alloc](block:Alloc) `Alloc` | 400 Hz | $w_{\rm cmd}=\sqrt{F/k_T}$; cyclic amplitude $\lvert\tau\rvert/k_{M,est}$ up to 0.8 N m, phase $\operatorname{atan2}(\tau_y,\tau_x)$ |
| [Esc](block:Esc) `RotorEsc` | 400 Hz | rotor speed loop: acceleration-limited reference, drag and inertia feed-forward, PI; the touchdown brake |
| [Drive](block:Drive) `CyclicDrive` | continuous | current loop and cyclic modulation, output the inverter duty |

![Mission, attitude and tracking error](@fig:mission)

## The gyroscopic plant

At hover the rotor carries $h=J_a\omega_0=0.189$ N m s. A body torque mostly **precesses** the
body about the other axis; without control the body nutates at $h/\sqrt{J_xJ_y}=12.94$ rad/s
(2.06 Hz). The rate loop cancels the coupling with the feed-forward $(hq,-hp)$ and closes a PI
on a bare inertia per axis, crossover 20 rad/s. `design.py` checks both: the coupled two-axis
attitude and rate loops have a minimum damping of 0.691 with the feed-forward and 0.360 without.
The outer gains (attitude 5 /s, velocity $K_v=2$, $K_i=0.8$, position $K_p=0.6$) come from a
linear one-axis model with the loop delays, minimum damping 0.717.

## The swashplateless gain

The allocation inverts its own fixed estimate $k_{M,est}=0.25$; the plant gain is the global
`cyclic_gain`. A different value is a real model mismatch that the rate loop has to absorb. The
cyclic limit 0.8 N m is a hub-moment limit of 0.2 N m, which is also the rate loop's moment
limit.

## Fins and passive yaw

At hover the fin torque equals the rotor drag, $Q_0=0.3052$ N m. A body yaw rate changes the
fins' angle of attack, which gives the yaw damping $D=0.00410$ N m s/rad. Because the speed loop
holds the rotor's speed relative to the body, the rotor follows the body's yaw, and the time
constant is $(J_z+J_a)/D=0.870$ s. Four identical fins at 90° prefer no heading: a crossflow
changes the yaw torque only at second order, by 0.85 mN m at 1 m/s. The position controller
builds the desired attitude with the measured heading, so roll and pitch go in the right world
direction whatever the heading is. In a steady descent the mass flow through the disc drops, the
swirl grows, and the model's body yaws at a steady 0.859 rad/s (at 0.25 m/s).

That descent yaw rate is a property of the model's assumptions, not a prediction for the real
vehicle. The swirl uses the descent speed in the mass flow, but the thrust and drag laws
$T=k_TW^2$, $Q=k_QW^2$ ignore the inflow. The 0.859 rad/s needs a torque imbalance of only
$D\cdot 0.859=3.5$ mN m, 1.15 % of $Q_0$. In the descent the flow through the disc drops by
1.5 % (from 8.41 to 8.29 m/s). A real propeller's $k_T$ and $k_Q$ change by an amount of the
same order, so the real rate could be quite different. The check
only shows that the model agrees with its Python twin in `design.py`.

![Rotor speed, moment request, cyclic torque and the drive](@fig:actuation)

![Yaw rate and the yaw torque balance](@fig:yaw)

## Landing

The land mode descends from hover at 0.25 m/s, so the thrust carries the weight when the feet
touch the ground at 15.06 s. The fins carry the rotor drag in any state, so the only unbalanced
yaw torque on the body is the rotor's change of angular momentum. Any rotor speed lost while the
feet do not hold the body goes into its yaw, 0.109 rad/s per rad/s. The touchdown therefore runs
in three stages:

1. **Impact.** The 85 N impact lasts a few milliseconds and falls between two ticks of the
   controllers. [Aero](block:Aero) holds its peak (`Aero/fc_max`). The drive
   [Esc](block:Esc) reads the peak at its next 400 Hz tick and brakes the rotor to 97 % of its
   speed while the feet are still pressed and their friction holds the braking reaction.
2. **Hold.** The [Mission](block:Mission) latches the touchdown on its next 50 Hz tick. The
   position loop holds its last thrust instead of reacting to the rebound of the feet, and the
   drive keeps the rotor at its cap. With $0.97^2$ of the weight carried, the rebound ends in a
   hop of 1.5 mm at a constant rotor speed. The rate loop only damps while the feet are on the
   ground.
3. **Unload.** After 0.3 s the thrust comes off along a smooth step over 1 s. The rotor slows
   gently while the feet carry little, and faster as they take the weight, so their friction
   always holds the rotor's deceleration torque. Then the flight controller is off, and the
   motor stops 2 s later.

The impact's friction stops the 0.84 rad/s descent yaw within 5 ms. From then on to rest, the
yaw rate stays below 0.14 rad/s. `design.py` bounds what the landing can leave: 4.2 rad/s of the brake
may fall outside the part of the impact that holds it, which allows at most 0.457 rad/s. Before
this sequence, the 50 Hz mission missed the impact and latched the touchdown 0.2 s late. In
between, the vertical loop read the rebound as a climb and cut the thrust, and the rotor lost
35 rad/s with the body in the air, which spun the body to 3.27 rad/s.

![Touchdown, disarm and run-down](@fig:touchdown)

## Sensors

[Imu](block:Imu) (`ImuSensor`, 500 Hz): gyro and accelerometer with biases, white noise and
Butterworth low-passes. The accelerometer sees the air loads and the contact force, never
gravity. [Mocap](block:Mocap) (100 Hz): position and velocity. [Beacon](block:Beacon)
(`IrBeacon`, 50 Hz): absolute heading. [Nav](block:Nav) (`NavFilter`, 500 Hz) observes the tilt
through the velocity innovation, the heading through the beacon, and estimates the gyro bias and
the vertical accelerometer bias. A horizontal accelerometer bias looks exactly like a tilt. The
vehicle therefore leans by about $b/g$, and the position loop's integrator removes the drift.
@@ page single-propeller-drone results overview | Results and checks
# Results and checks

![Mission: position, attitude and tracking error](@fig:mission)

![Actuation and drive](@fig:actuation)

![Yaw: rate and torque balance](@fig:yaw)

![Touchdown](@fig:touchdown)

![Navigation filter errors](@fig:estimator)

## Measured against design.py

| quantity | design.py | measured |
| --- | --- | --- |
| 1.5 m leg overshoot, one-axis model with the accelerometer bias | 3.17 cm | 1.88 cm (x), 1.73 cm (y) |
| land-mode descent speed | 0.25 m/s | 0.2491 m/s |
| yaw rate in the steady descent (a model property) | 0.859 rad/s | 0.827 rad/s |
| feet reach the ground | 15.057 s | 15.061 s |
| touchdown load, four damped feet at once | ≤ 109.8 N | 85.2 N |
| yaw rate after the impact, to rest | ≤ 0.457 rad/s | 0.127 rad/s |
| rise above the contact height after the touchdown | ≤ 2.16 mm | 1.46 mm |
| rest height on the feet | 0.18055 m | 0.180556 m |
| yaw rate once landed | 0 (friction 1.33 N m against 0.091 N m) | below 0.001 rad/s |

The peak tilt is 0.145 rad, inside the 0.20 rad limit. Navigation errors in flight: attitude
0.0126 rad, position 0.0081 m, velocity 0.0157 m/s.

## Checks

The checks of this model compare each measurement with a reference from `design.py`: the leg
overshoot, the descent speed and yaw rate, the touchdown time, the touchdown load, the landing
yaw and hop, the rest height, the yaw rate on the ground, the tilt limit and the navigation
errors. They also check
the scene bindings and the absence of E901/E106/E007/W201/W202/W205/W206.

```
uv run examples/run_checks.py --only single-propeller-drone
```
@@ figures single-propeller-drone-hover
{
  "step": {
    "kind": "plot", "model": "single-propeller-drone-hover", "xlim": [0, 8],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Truth/x", "label": "x"}, {"signal": "Truth/y", "label": "y"}, {"signal": "Mission/p_sp[1]", "label": "x set-point", "style": ":"}], "legend": true},
      {"ylabel": "height [m]", "series": [{"signal": "Truth/z", "label": "z"}], "legend": true},
      {"ylabel": "yaw [rad], yaw rate [rad/s]", "series": [{"signal": "Truth/yaw", "label": "yaw"}, {"signal": "Truth/wb[3]", "label": "yaw rate", "style": "--"}], "legend": true}
    ]
  },
  "nutation": {
    "kind": "plot", "model": "single-propeller-drone-hover", "xlim": [0, 2],
    "settings": {"t_end": 2.0, "output": {"points": 2001}},
    "overrides": {"Rate/Kp": 0.0, "Rate/Ki": 0.0, "Rate/k_gyro": 0.0},
    "rows": [
      {"ylabel": "body rates [rad/s]", "series": [{"signal": "Truth/wb[1]", "label": "roll rate p"}, {"signal": "Truth/wb[2]", "label": "pitch rate q"}], "legend": true}
    ]
  },
  "hover-scene": {"kind": "scene", "model": "single-propeller-drone-hover", "t": 4.5, "zoom": 2}
}
@@ page single-propeller-drone-hover overview - | Hover and passive yaw
# Hover with a yaw kick and a roll kick

The same vehicle, released in hover at 1.32 m with the rotor at the hover speed. It starts with
a **0.8 rad/s yaw kick** and a **0.3 rad/s roll kick**, and flies a 1 m lateral step from 3 s.
There is no yaw command anywhere.

![The 1 m step, the height and the yaw](@fig:step)

![During the step, 4.5 s](@fig:hover-scene)

## What it shows

* **Passive yaw.** The fins damp the kick with the time constant $(J_z+J_a)/D=0.870$ s, so the
  heading turns by $r_0\tau(1-e^{-t/\tau})$: 0.674 rad at 3 s by `design.py`, 0.684 rad
  measured. Nothing brings the heading back.
* **Step.** The one-axis model of `design.py` overshoots the 1 m step by 1.27 cm, and by
  2.42 cm with the IMU's horizontal accelerometer bias as a disturbance. The model overshoots
  1.77 cm. The height stays between 1.3155 and 1.3228 m.
* **Hover trim.** The mean rotor speed is 539.04 rad/s, against $\sqrt{T_0/k_T}=539.11$ rad/s
  with the fin download in $T_0$. In any steady state the fin torque equals the rotor drag,
  whatever the fin law, so the trim incidence (11.54°) shows in the yaw rate instead. With the
  trim incidence, the yaw torque balances at zero rate, and the mean yaw rate over 6–8 s is
  0.029 rad/s. An imbalance of $\Delta Q$ would settle at $\Delta Q/D$, so 0.05 rad/s
  corresponds to 0.2 mN m, 0.07 % of $Q_0$.
* **Power.** The pack delivers 188.01 W at 7.565 A, against 187.94 W and 7.562 A from the
  drive's operating point (with the pack's charge at 7 s). The motor current is 10.84 A.
* **Gyroscopic plant.** With the rate loop switched off, the roll kick turns into a circular
  nutation at 2.02 Hz, against $h/\sqrt{J_xJ_y}$ = 2.06 Hz.

![Free nutation with the rate loop off](@fig:nutation)

## Checks

The checks compare the heading, the hover rotor speed, the yaw rate at the trim incidence, the
pack power and the currents, the accelerometer-bias estimate, the step overshoot and the
nutation frequency with `design.py`. They also check the height band, the navigation errors, the scene bindings and the
diagnostics.

```
uv run examples/run_checks.py --only single-propeller-drone
```
