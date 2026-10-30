# The multibond structure

Planar multibond elements (`stdlib:planar/*`, `stdlib:multibond/*Planar`) carry a three-component twist and wrench $(\omega, v_x, v_y)$ on every bond. The power path is a chain of bonds from the ground to the last link:

```
Ground ─ Joint1 ─ Link1 ─ BodyJ1 ─ Joint2 ─ Link2 ─ BodyJ2
```

| instance | block | role |
| --- | --- | --- |
| [Ground](block:Ground) | `stdlib:multibond/GroundPlanar` | world flow source, $f = 0$ |
| [Joint1](block:Joint1) | `stdlib:planar/Revolute2DCompliant` | joint 1: pivot at $r_x = 0$ m in the parent CoM frame, `kt` = 1e8 N/m, `bt` = 2000 N·s/m, viscous friction $b = 0.002$ N·m·s/rad; drive: the motor drive port (rotation), see below |
| [Link1](block:Link1) | `stdlib:planar/FixedJoint2D` | frame bridge from the joint to the centre of mass of link 1, $x = 0.15$ m |
| [BodyJ1](block:BodyJ1) | 1-junction | the common twist of link 1: its body and the next joint |
| [Body1](block:Body1) | `stdlib:planar/RigidBody2D` | $m = 0.22$ kg, $J = m L^2/12 = 0.00165$ kg·m², $L = 0.3$ m |
| [Joint2](block:Joint2) | `stdlib:planar/Revolute2DCompliant` | joint 2: pivot at $r_x = 0.15$ m in the parent CoM frame, `kt` = 1e8 N/m, `bt` = 2000 N·s/m, viscous friction $b = 0.0008$ N·m·s/rad; drive: a zero-torque `Se` (**passive joint**) |
| [Link2](block:Link2) | `stdlib:planar/FixedJoint2D` | frame bridge from the joint to the centre of mass of link 2, $x = 0.18$ m |
| [BodyJ2](block:BodyJ2) | 1-junction | the common twist of link 2: its body and the disturbance source |
| [Body2](block:Body2) | `stdlib:planar/RigidBody2D` | $m = 0.14$ kg, $J = m L^2/12 = 0.001512$ kg·m², $L = 0.36$ m |
| [Motor](block:Motor) | `stdlib:drives/ElectricDrive` | DC motor: $R_w$ = 2.5 Ω, $L$ = 0.5 mH, $k_t$ = 0.03 N·m/A, rotor $J_m$ = 5e-06 kg·m² |
| [Shaft](block:Shaft) | `stdlib:rotation/ElasticShaft` | the drive-train compliance $k$ = 5000 N·m/rad, $d$ = 0.2 N·m·s/rad on the motor side |
| [Gear](block:Gear) | `stdlib:drives/Gearbox` | ideal ratio $N = 5$ (motor rate $= N\,\dot q_1$) |
| [Hit](block:Hit) | `stdlib:multibond/ExternalWrenchPlanar` | the disturbance wrench on the last link, from [DistTorque](block:DistTorque), [DistAxial](block:DistAxial) and [DistForce](block:DistForce) (`stdlib:sources/Pulse`) |
| [Ctrl](block:Ctrl) | `project:DoublePendCtrl` | the 1 kHz firmware: swing-up, catch, balance; [Clock](block:Clock) supplies the time |
| [Upright](block:Upright) | inline block | the absolute link angles from upright, $a_k = q_1 + \dots + q_k - \pi/2$ |

## Joints

A rigid revolute on a three-degree-of-freedom body is index 3 (the two pivot translations are hard constraints; `Revolute2DRigid` ends in a derivative-causal DAE that does not run). `Revolute2DCompliant` keeps the **rotation exact** and lets the two pivot translations be stiff spring-dampers ($k_t = 10^8$ N/m): the pivot moves by about $m g / k_t \approx 10^{-8}$ m, and the free-swing check below shows the plant agrees with the rigid design model to 2.9e-06 rad over a 3 s swing. All states are integral, so the run reports no W201.

The joint angle `q` of joint 1 is the absolute angle of link 1 (hanging: $-\pi/2$, upright: $+\pi/2$); the angles of the other joints are relative, so the absolute angle of link $k$ is $\theta_k = q_1 + \dots + q_k$.

## Poses and gravity

The poses are composed, never integrated: `JointPose2D` turns a joint angle into an SE(2) pose, `LocalPose2D` holds the constant offsets and `ComposePose2D` multiplies them along the chain ([PoseB1](block:PoseB1), [PoseB2](block:PoseB2), [PoseTip](block:PoseTip)). Each `RigidBody2D` reads its world pose to resolve gravity in the body frame, so the weight acts at the true centre of mass.

## Drive train

[Motor](block:Motor) turns the voltage $u$ from [Ctrl](block:Ctrl) into a shaft torque; [Shaft](block:Shaft) is a stiff elastic shaft that keeps the rotor inertia integral-causal (an ideal gear between the rotor and a joint that imposes its rate would give a derivative-causal pair); [Gear](block:Gear) multiplies the torque by $N = 5$ and the rotor inertia appears at the joint as $N^2 J_m = 0.000125$ kg·m². The joint carries the reaction torque, so the motor housing is the fixed base. Taps: the winding current [Motor/isense/y](signal:Motor/isense/y), the motor speed [Motor/wsense/y](signal:Motor/wsense/y).

## Bond direction

Every bond of the chain points from the port into the junction (`Joint.parent → BodyJ`, `Link.child → BodyJ`, `Body.p → BodyJ`, `Hit.p → BodyJ`). The direction is the power orientation of the bond; reversing one of them flips the sign convention of that junction and the pendulum no longer matches its equations of motion.
