# Multibond structure

The plant is a **spatial multibond bond graph** (`stdlib:spatial/*`, `stdlib:multibond/*Spatial`); every power bond between the joints and the bodies is a `Power{Spatial}` bundle of six components.

```
World -- Mount -- J1 (Revolute3D, world z) -- Link1 -- BJ1 -- Arm (RigidBody3D)
 Motor (ElectricDrive) -- Shaft (ElasticShaft) -- Gear (IdealGear 70) -- J1.drive
 BJ1 -- L2 (RevoluteLink3D: T -- J (Revolute3D, arm axis) -- Link -- BJ -- B (RigidBody3D))
 L2.child -- L3 (RevoluteLink3D) ;  L3.child -- L4 (RevoluteLink3D)
 Dist (ExternalWrenchSpatial) -- TipPoint -- L4.child
```

| part | block | note |
| --- | --- | --- |
| arm joint | [J1](block:J1), `Revolute3D` | rotates about the world $z$ axis; the held directions are compliant ($k_t = k_r = 1e+08$ N/m, N·m/rad, damped near critically) so every state is integral |
| arm | [Arm](block:Arm), `RigidBody3D` | bar of 21.59 cm and 0.2570 kg, centre of mass at the middle |
| pendulum links | [L2](block:L2), [L3](block:L3), [L4](block:L4) | instances of the library subsystem `RevoluteLink3D` (`library/RevoluteLink3D.bgsub.json`, one link of a spatial serial chain): the offset `T` from the body below, the joint `J`, the offset `Link` to the centre of mass, the body `B` on its 1-junction `BJ` and the pose band `LN`, `CA`, `W`, `LC`, `P`; each instance pins every offset, the joint and the body. The bearings stay outside, on the instance's `drive` port |
| pendulum joints | `L2/J`, `L3/J`, `L4/J` | `Revolute3D` about the arm axis: the joint frame of L2/J is the arm frame rotated by $180^\circ$ about $(1,0,1)/\sqrt2$, so its $z$ axis is the arm axis and its $x$ axis is world up. Angle 0 is **upright**, $\pi$ hanging; L3/J and L4/J are relative to the link below |
| bearings | [Bearing2](block:Bearing2) ... | `RotationalDamper` on each pendulum joint's drive port, 3e-05 N·m·s/rad |
| link bodies | `L2/B`, `L3/B`, `L4/B` | `RigidBody3D`, centre of mass at the rod middle, thin-bar inertias; link 1: $l = 20.00$ cm, $m = 0.097$ kg, link 2: $l = 20.00$ cm, $m = 0.097$ kg, link 3: $l = 33.65$ cm, $m = 0.127$ kg |
| servo | [Motor](block:Motor) | `drives/ElectricDrive`: $R_m = 8.4\ \Omega$, $L_m = 1.16$ mH, $k_t = 0.0333$ N·m/A, rotor 3.87e-07 kg·m² |
| gearbox | [Shaft](block:Shaft), [Gear](block:Gear) | `ElasticShaft` (1e+07 N·m/rad and 200 N·m·s/rad at the load) and `IdealGear` 70:1. The elastic shaft keeps the rotor inertia integral: a rotor rigidly on a rate-imposing joint is derivative causal (W201) |
| poses | `ComposePose3D` chain | the body poses are composed from the joint poses and feed the gravity of every body |
| disturbance | [Dist](block:Dist) | `ExternalWrenchSpatial` on the tip of the top link through a `FixedTransform3DNeutral`; force along the body $y$ axis (perpendicular to the rod, in the pendulum plane), driven by [DistPulse](block:DistPulse) |
| firmware | [Ctrl](block:Ctrl) | project block `RotaryCtrl`, 1 kHz discrete, reads the joint coordinates and rates ([Clock](block:Clock) is the time) |
| measurement | [Angles](block:Angles) | project block `LinkAngles`: the absolute link angles $\varphi_k = q_2 + \dots + q_{k+1}$ and their largest deviation `dev` |

The joints are 100 times stiffer than in the double (1e6 there), and the gear shaft (1000 N·m/rad in the double) is a stand-in for a rigid gearbox: it only keeps the rotor inertia integral, and it is damped near critically. The triple's swing-up is chaotic, so the design model has to match the bond graph closely for the feed-forward to stay useful (see [equations](page:equations)); the stiff shaft also integrates three times faster than the 1e5 N·m/rad one.

## Parameters and their source

| quantity | value | source |
| --- | --- | --- |
| arm length / mass | 0.2159 m / 0.2570 kg | Quanser product page |
| links | link 1: $l = 20.00$ cm, $m = 0.097$ kg, link 2: $l = 20.00$ cm, $m = 0.097$ kg, link 3: $l = 33.65$ cm, $m = 0.127$ kg | Quanser short pendulum (20.0 cm, 0.097 kg) twice and the medium pendulum (33.65 cm, 0.127 kg) on top; the chain itself is assumed (not a Quanser product) |
| servo | $R_m$ 8.4 Ω, $L_m$ 1.16 mH, $k_t = k_m$ 0.0333, $J_m$ 3.87e-7, total gear ratio 70, load friction 0.015 N·m·s/rad | Quanser SRV02 manual (as in the double; recalled, not re-read) |
| amplifier limit | $\pm 15$ V | assumed: raised from the double's 10 V, see below |
| assumed | centre of mass at the bar middle, bar radii (6 mm arm, 8 mm links), gear stiffness, pendulum bearing friction, motor and gearbox efficiency folded into the viscous load friction | not published |

## Why 15 V: the feasibility estimate

Raising the chain from hanging to upright takes $\Delta E = 2.18$ J, on average 0.54 W over $T_s = 4$ s. Energy is not the limit: the winding delivers at most $V^2/(4R_m)$ = 6.7 W at 15 V (3.0 W at 10 V). **Speed** is: the back-EMF of the 70:1 servo caps the arm rate at the no-load value $n k_t V / (n^2 k_t^2 + R_m b)$ = 4.2 rad/s at 10 V and 6.3 rad/s at 15 V. The smooth triple swing-up found here needs an arm rate of 4.4 rad/s, more than 10 V allows; at 10 V the optimiser only finds whip-like trajectories (link rates of 40–60 rad/s) that no feedback can track. At 15 V the trajectory keeps the link rates below 12 rad/s. The stall torque at the arm is 4.2 N·m. The run's RMS winding current is 0.13 A (design model), so the short over-voltage is thermally harmless.
