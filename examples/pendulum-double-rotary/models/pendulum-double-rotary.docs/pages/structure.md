# Multibond structure

The plant is a proper **spatial multibond bond graph** (`stdlib:spatial/*`, `stdlib:multibond/*Spatial`); every power bond between the joints and the bodies is a `Power{Spatial}` bundle of six components.

```
World -- Mount -- J1 (Revolute3D, world z) -- Link1 -- BJ1 -- Arm (RigidBody3D)
 Motor (ElectricDrive) -- Shaft (ElasticShaft) -- Gear (IdealGear 70) -- J1.drive
 BJ1 -- T2 -- J2 (Revolute3D, arm axis) -- Link2 -- BJ2 -- Rod1 (RigidBody3D)  ... one joint and one body per link
 Dist (ExternalWrenchSpatial) -- TipPoint -- BJ3
```

| part | block | note |
| --- | --- | --- |
| arm joint | [J1](block:J1), `Revolute3D` | rotates about the world $z$ axis; the held directions are compliant ($k_t = k_r = 10^6$ N/m, N·m/rad) so every state is integral |
| arm | [Arm](block:Arm), `RigidBody3D` | thin bar of 21.59 cm and 0.2570 kg, centre of mass at the middle ($J_z = m l^2/12$) |
| pendulum joints | [J2](block:J2) ... | `Revolute3D` about the arm axis: the joint frame is the arm frame rotated by $180^\circ$ about $(1,0,1)/\sqrt2$, so the joint $z$ axis is the arm axis and the joint $x$ axis is world up. Angle 0 is **upright**, $\pi$ hanging |
| links | [Rod1](block:Rod1) ... | `RigidBody3D`, centre of mass at the rod middle, thin-bar inertias; link 1: $l = 20.00$ cm, $m = 0.097$ kg, link 2: $l = 33.65$ cm, $m = 0.127$ kg |
| servo | [Motor](block:Motor) | `drives/ElectricDrive`: $R_m = 8.4\ \Omega$, $L_m = 1.16$ mH, $k_t = 0.0333$ N·m/A, rotor $3.87\cdot10^{-7}$ kg·m² |
| gearbox | [Shaft](block:Shaft), [Gear](block:Gear) | `ElasticShaft` (1000 N·m/rad at the load) and `IdealGear` 70:1. The elastic shaft keeps the rotor inertia integral: a rotor rigidly on a rate-imposing joint is derivative causal (W201) |
| poses | `ComposePose3D` chain | the body poses are composed from the joint coordinates and feed the gravity of every body |
| disturbance | [Dist](block:Dist) | `ExternalWrenchSpatial` on the tip of the top link through a `FixedTransform3DNeutral`; force along the body $y$ axis (perpendicular to the rod, in the pendulum plane) |
| firmware | [Ctrl](block:Ctrl) | project block `RotaryCtrl`, 1 kHz discrete, reads the joint coordinates and rates ([Clock](block:Clock) is the time) |
| measurement | [Angles](block:Angles) | project block `LinkAngles`: the absolute link angles $\varphi_k = q_2 + \dots + q_{k+1}$ and their largest deviation |

## Parameters and their source

The arm, the two links and the SRV02 servo follow the Quanser rotary double inverted pendulum (product page and SRV02 manual, see *Parameters*).

| quantity | value | source |
| --- | --- | --- |
| arm length / mass | 0.2159 m / 0.2570 kg | Quanser product page |
| links | link 1: $l = 20.00$ cm, $m = 0.097$ kg, link 2: $l = 33.65$ cm, $m = 0.127$ kg | Quanser product page (short pendulum 20.0 cm, 0.097 kg; medium pendulum 33.65 cm, 0.127 kg) |
| servo | $R_m$ 8.4 Ω, $L_m$ 1.16 mH, $k_t = k_m$ 0.0333, $J_m$ 3.87e-7, total gear ratio 70, load friction 0.015 N·m·s/rad | Quanser SRV02 manual (recalled from the manual, not re-read) |
| assumed | centre of mass at the bar middle, bar radii (6 mm arm, 8 mm links) for the axial inertia, gear stiffness 1000 N·m/rad, pendulum bearing friction $3\cdot10^{-5}$ N·m·s/rad, 10 V amplifier limit, motor and gearbox efficiency folded into the viscous load friction | not published |
