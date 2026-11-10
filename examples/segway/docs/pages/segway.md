# A two-wheeled self-balancing transporter with a rider

A **Segway-class personal transporter**: two driven wheels on one axle, a platform with a steering post, a rider, and
nothing else holding it up. A controller reads the lean of the body and the wheel speed and drives the wheels under the
rider's centre of mass, which is exactly what an inverted pendulum on a cart needs. The wheels roll on the ground, the
motors push the wheels forward and the body backward (the reaction torque), and that reaction is what rights the rider.

![The transporter leaning into an acceleration|600](assets/09010f902ff5.png)

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
