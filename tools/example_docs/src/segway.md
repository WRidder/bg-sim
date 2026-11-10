@@ figures @project
{
  "scene": {"kind": "scene", "model": "balance", "t": 4.6}
}
@@ page @project segway - | The balancing transporter
# A two-wheeled self-balancing transporter with a rider

A **Segway-class personal transporter**: two driven wheels on one axle, a platform with a steering post, a rider, and
nothing else holding it up. A controller reads the lean of the body and the wheel speed and drives the wheels under the
rider's centre of mass, which is exactly what an inverted pendulum on a cart needs. The wheels roll on the ground, the
motors push the wheels forward and the body backward (the reaction torque), and that reaction is what rights the rider.

![The transporter leaning into an acceleration|600](@fig:scene)

## How it is modelled

The mechanics are a **3D bond graph** built from the spatial multibond library, with no equation block for the plant:

| part | block |
| --- | --- |
| body (rider, platform, frame, batteries) | `RigidBody3D` named `Body` on a `PoseIntegrator3D` (`Pose`); the body frame has its origin at the centre of mass, x forward, y left, z up |
| two wheels | `RigidBody3D` `WheelL`, `WheelR` hanging on `Revolute3D` axle joints (`AxleL`, `AxleR`; axis = body y through a `FixedTransform3DNeutral` mount); their poses are composed from the body pose, the mount and the joint pose (`ComposePose3D`) |
| rolling on the ground | one `RollingDisk` per wheel (`TyreL`, `TyreR`) against a `ContactSurface`: a compliant tyre with a friction cone, so rolling without slipping is a force, not a constraint |
| motors | `MSe` torque sources on the axle joints (`MotorL`, `MotorR`). The joint carries the reaction, so a torque on the wheel acts with the opposite sign on the body |
| push | `ExternalWrenchSpatial` on the body (`Push`) |
| sensing | project block `SegwaySense`: pitch from the body rotation, pitch rate and yaw rate from the body twist, heading as the integral of the yaw rate |
| firmware | project block `SegwayCtrl`: LQR balance and speed loop plus a PD heading loop |

The only library blocks of the example are these three signal blocks (sensor, controller, mission). A rotor inertia on the
joint rate would be a derivative-causal store next to the body and wheel inertias, so the motors are ideal torque
sources (current loop, torque constant and gear ratio are folded into the torque command; the controller reports the
voltage each motor would need).

## Control

The pitch plane has four states, $x = [\xi, v - v_{ref}, \theta, \dot\theta]$, where $\xi$ is the integral of the speed
error and $v = r(\bar{\dot q} + \dot\theta)$ the axle speed from the wheel encoders. The wheel torque (both wheels) is

$$\tau_c = -(K_\xi\,\xi + K_v\,(v - v_{ref}) + K_\theta\,\theta + K_\omega\,\dot\theta).$$

`design/design.py` linearises the Lagrange model analytically at upright, solves the Riccati equation with `scipy`, and
writes the gains. The open-loop plant has the unstable pole $+5.23\ \mathrm{s^{-1}}$ (the body falls over in about
0.2 s); the closed loop has the poles $-53.4,\ -3.79,\ -1.39,\ -1.26\ \mathrm{s^{-1}}$. A PD law on the heading gives the
differential torque $\tau_d$ that steers (natural frequency 6 rad/s, damping 0.9). Each wheel gets
$\tau = \tau_c/2 \pm \tau_d$, limited to 80 N m.

## Parameters

The parameters are estimates for a Segway PT with a rider, unless a published value is named. No Segway parameter set
with a rider was found in print, and no flight or test log, so the model is checked against the analytic design and an
independent simulation, and against the published specifications below.

| parameter | value | status |
| --- | --- | --- |
| body mass $m_b$ (rider + platform + frame + batteries) | 105 kg | estimate: rider 75 kg (the 75 kg person + platform of Moore's published Segway model) plus 30 kg |
| centre of mass above the axle $l$ | 0.52 m | estimate |
| body inertia $J_{by}$ (pitch) | 16 kg m² | estimate, close to the 14 kg m² of Moore's published model |
| roll and yaw inertia $J_{bx}, J_{bz}$ | 12, 3 kg m² | estimate |
| wheel radius $r$ | 0.24 m | estimate (the Segway PT has a tyre of about 19 in) |
| wheel mass, inertia about the axle | 5 kg, 0.15 kg m² | estimate |
| distance between the wheels $b$ | 0.45 m | estimate (overall width 0.635 m) |
| gear ratio $n$, torque constant $k_t$ | 24, 0.12 N m/A | estimate (wheel side: 2.88 N m/A) |
| winding resistance $R$ | 0.15 Ω | estimate |
| torque limit per wheel | 80 N m | estimate |
| battery bus | 72 V | estimate (recalled for the PT, not verified in a source) |
| top speed | 20 km/h = 5.56 m/s | published: Segway i2 specifications |
| rider mass range | 45 to 118 kg (rider and cargo) | published: Segway i2 reference manual |
| tyre contact | $k = 5\cdot10^5$ N/m, μ = 0.9 | estimate of a pneumatic tyre |

@@ figures balance
{
  "diagram": {"kind": "diagram", "model": "balance"},
  "run": {
    "kind": "plot", "model": "balance", "xlim": [0, 14],
    "rows": [
      {"ylabel": "pitch [deg]", "series": [{"signal": "Sense/theta", "label": "body pitch", "scale": 57.29577951308232}], "legend": true},
      {"ylabel": "speed [m/s]", "series": [{"signal": "Ctrl/v", "label": "axle speed"}, {"signal": "VRef/y", "label": "set-point", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "wheel torque [N m]", "series": [{"signal": "Ctrl/tau_l", "label": "per wheel"}], "hlines": [{"y": 80, "label": "limit 80 N m"}, {"y": -80}], "legend": true},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/vreq_l", "label": "needed per motor"}], "hlines": [{"y": 72, "label": "bus 72 V"}], "legend": true}
    ]
  },
  "scene": {"kind": "scene", "model": "balance", "t": 4.6}
}
@@ page balance overview - | What you're looking at
# Balance, speed and a push

**Scenario.** The rider stands on the transporter, released **0.03 rad (1.7°)** off upright. The LQR catches it in about a second. From **3 s** the speed set-point ramps to **1.5 m/s** in 1.5 s, so the body leans forward (up to 10.8°) to accelerate, then settles back upright. At **9 s** a **150 N push** lasting 0.15 s on the centre of mass shoves the vehicle; the controller steps forward under it and recovers.

![The model canvas|1000](@fig:diagram)

The motors ([MotorL](block:MotorL), [MotorR](block:MotorR)) turn the wheels against the body through the axle joints [AxleL](block:AxleL) and [AxleR](block:AxleR); the wheels roll on the ground through [TyreL](block:TyreL) and [TyreR](block:TyreR). [SegwayCtrl](block:Ctrl) reads the pitch and pitch rate from [Sense](block:Sense) and the joint rates from the axles.

![Pitch, speed, wheel torque and the voltage the motors need|900](@fig:run)

**Checks.** The bond graph agrees with the independent non-linear Lagrange simulation of `design/design.py` (same controller, RK4) to four digits: the pitch ([Sense/theta](signal:Sense/theta)) and speed ([Ctrl/v](signal:Ctrl/v)) at the times in `expected.json`, the peak torque 42.8 N m per wheel (limit 80) and peak voltage 23 V (bus 72 V). The load on each wheel at rest is the static 564 N ([TyreL/f_n](signal:TyreL/f_n)).

![3D view while accelerating (t = 4.6 s)|500](@fig:scene)

**Dashboard.** The push force and the rider's mass (the gains stay designed for 105 kg, so a different mass shows the margin of the design), the pitch gauge, speed, torque and voltage, and the plots of speed and pitch.

**Try:** raise the push to 400 N; the controller still recovers, with a larger torque. Change the body mass to 70 or 140 kg without re-running `design.py`. Increase the push until the torque limit saturates and the vehicle falls.

@@ figures open-loop
{
  "diagram": {"kind": "diagram", "model": "open-loop"},
  "run": {
    "kind": "plot", "model": "open-loop", "xlim": [0, 1],
    "rows": [
      {"ylabel": "pitch [deg]", "series": [{"signal": "Sense/theta", "label": "body pitch", "scale": 57.29577951308232}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "pitch rate [rad/s]", "series": [{"signal": "Sense/w", "label": "pitch rate"}], "legend": true, "legend_loc": "upper left"}
    ]
  },
  "scene": {"kind": "scene", "model": "open-loop", "t": 1.0, "zoom": 8}
}
@@ page open-loop overview - | What you're looking at
# Open loop: the unstable pole

**Scenario.** No control: the gains are zero and the motors give no torque. The transporter starts **0.002 rad** off upright and falls forward with free wheels. The tilt grows as $e^{5.23\,t}$, so it doubles every 0.13 s: the controller has to react within a few hundredths of a second.

![The model canvas|1000](@fig:diagram)

![Pitch and pitch rate of the free fall|700](@fig:run)

**Checks.** The unstable open-loop eigenvalue of the analytic linearisation is $+5.2287\ \mathrm{s^{-1}}$ (the positive root of the linear model with the mass matrix $M = [[a_{11}, a_{12}], [a_{12}, a_{22}]]$ of `design/design.py`). The pitch at 0.2, 0.4, 0.6, 0.8 and 1.0 s agrees with the non-linear reference to 3 %. The bond graph has the wheels, the contact and the body in 3D, so this also tests the whole structure against the planar Lagrange equations.

![3D view at t = 1 s|500](@fig:scene)

**Try:** change the body mass or the height of the centre of mass with the dashboard sliders and watch the fall time. A lower centre of mass is slower to fall (the pole is about $\sqrt{g/l}$ for a light wheel).

@@ figures top-speed
{
  "diagram": {"kind": "diagram", "model": "top-speed"},
  "run": {
    "kind": "plot", "model": "top-speed", "xlim": [0, 17],
    "rows": [
      {"ylabel": "speed [m/s]", "series": [{"signal": "Ctrl/v", "label": "axle speed"}, {"signal": "VRef/y", "label": "set-point", "style": "--"}], "hlines": [{"y": 5.556, "label": "20 km/h"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "pitch [deg]", "series": [{"signal": "Sense/theta", "label": "body pitch", "scale": 57.29577951308232}], "legend": true},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/vreq_l", "label": "needed per motor"}], "hlines": [{"y": 72, "label": "bus 72 V"}], "legend": true, "legend_loc": "lower right"}
    ]
  },
  "scene": {"kind": "scene", "model": "top-speed", "t": 9.0}
}
@@ page top-speed overview - | What you're looking at
# Top speed: 20 km/h

**Scenario.** The speed set-point ramps from rest to **20 km/h = 5.56 m/s**, the published top speed of the Segway i2, over 9 s and then holds. At constant speed the voltage a motor needs is the back-EMF, $k_t\,n\,v/r = 2.88 \cdot 5.556 / 0.24 = 66.7$ V: with the estimated 72 V bus there is an 8 % margin, and the speed loop's overshoot at the end of the ramp pushes the demand to 71 V.

![The model canvas|1000](@fig:diagram)

![Speed, pitch and the voltage the motors need|900](@fig:run)

**Checks.** The speed, pitch and voltage follow the non-linear reference simulation; the final speed is the published 5.556 m/s and the final voltage the analytic 66.7 V; the wheel torque stays below 80 N m.

![3D view at t = 9 s|500](@fig:scene)

**Try:** raise the cruise speed beyond 20 km/h: the demand exceeds the bus voltage (the model does not saturate the voltage, `Ctrl/vreq_l` shows it), which is the real reason a transporter has a speed limit and tilts the platform back as a warning.

@@ figures figure-eight
{
  "diagram": {"kind": "diagram", "model": "figure-eight"},
  "path": {
    "kind": "plot", "model": "figure-eight", "width": 620, "row_height": 5.2,
    "rows": [
      {"ylabel": "y [m]", "x": "Sense/xa", "xlabel": "x [m]", "equal": true, "series": [{"signal": "Sense/ya", "label": "axle path"}]}
    ]
  },
  "run": {
    "kind": "plot", "model": "figure-eight", "xlim": [0, 28],
    "rows": [
      {"ylabel": "heading [rad]", "series": [{"signal": "Sense/heading", "label": "heading"}, {"signal": "Plan/psi_ref", "label": "set-point", "style": "--"}], "legend": true},
      {"ylabel": "wheel torque [N m]", "series": [{"signal": "Ctrl/tau_l", "label": "wheel at +y"}, {"signal": "Ctrl/tau_r", "label": "wheel at -y"}], "legend": true, "legend_loc": "upper right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/vreq_l", "label": "needed, wheel at +y"}, {"signal": "Ctrl/vreq_r", "label": "needed, wheel at -y"}], "legend": true, "legend_loc": "upper right"}
    ]
  },
  "scene": {"kind": "scene", "model": "figure-eight", "t": 10.0}
}
@@ page figure-eight overview - | What you're looking at
# A figure of eight

**Scenario.** The transporter accelerates to **1.5 m/s** and, from 4 s, the heading set-point turns **+2π** in 11 s and then back by 2π in the next 11 s: two circles of opposite sense (radius $v\,T/2\pi = 2.6$ m) that join into an eight. Differential wheel torque steers: the wheel on the outside torques more than the one on the inside; the pitch loop is the same as in [the balance model](model:balance).

![The model canvas|1000](@fig:diagram)

![Path of the axle|620](@fig:path)

![Heading, wheel torques and the voltage the motors need|900](@fig:run)

**Checks.** The heading, the position and the yaw rate follow the reference of `design/design.py` (non-linear pitch plane, yaw loop and the kinematic path of the axle): the heading returns to 0, and the axle passes the crossing point of the eight at the start of the first circle, between the circles and again at the end of the second one (the speed-up before the first circle is not part of the eight). The tyres creep less than 0.13 mm/s.

![3D view at t = 10 s|500](@fig:scene)

**Try:** change the cruise speed and the loop time with the dashboard sliders; a tighter or faster loop raises the lateral acceleration $v\,\dot\psi$, and the tyre friction cone ($\mu = 0.9$) is the limit.
