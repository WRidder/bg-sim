# The planar bond-graph structure

Each arm is a chain of the planar multibond elements of the standard library (`stdlib:planar/*`, `stdlib:multibond/*Planar`). Ports of the `Planar` domain carry a three-component twist $(\omega, v_x, v_y)$ and wrench $(\tau, f_x, f_y)$, so every bond between them is a **two-stroke bundle**.

```
Ground ── Joint1 ── Link1 ── N1 (1-junction) ── Joint2 ── Link2 ── N2 ── Joint3 ── Link3 ── Body3
 (p)     (parent→child)  (x = c1)  │                                                (c3)
                                    └── Body1                         Body2 on N2
```

| element | block | role |
| --- | --- | --- |
| [A3_Joint1](block:A3_Joint1) | `stdlib:planar/Revolute2DCompliant` | revolute joint: exact angle $q$, pivot translations as stiff springs ($k_t = 10^8$ N/m) |
| [A3_Link1](block:A3_Link1) | `stdlib:planar/FixedJoint2D` | frame bridge from the joint to the centre of mass at $c_i = a_i + r_i$ |
| [A3_N1](block:A3_N1) | 1-junction | the common twist of link 1: its body and the next joint |
| [A3_Body1](block:A3_Body1) | `stdlib:planar/RigidBody2D` | 3-DOF body with $m_i$ and $J_i$ about the centre of mass; its port is the body 1-junction with `IPlanar`, `CoriolisPlanar` and `GravityPlanar` |
| `A3_PoseJ*`, `A3_PoseB*`, `A3_CoM*` | `ComposePose2D`, `LocalPose2D` | the pose chain, composed from the joint angles (never integrated), which feeds `GravityPlanar` |

The elbow of link $j+1$ sits at $-r_j$ in the centre-of-mass frame of link $j$ (the script's COM offset $r$ is measured from the link *end*, so the next joint is $a_j - c_j = -r_j$ behind the centre of mass).

## The drive train of one joint

Every joint $j$ has the drive train of the reference script, in plain bond-graph elements:

```
Speed (MSf)  ─ TorqueSensor ─ 1 (Drive_j) ─── Joint.drive      joint side, speed = qd
                                │
                           IdealGear (G) ─── 1 (Motor_j) ─┬─ I  (Jm)
                                                          └─ R  (B)
```

The speed source imposes the joint speed $\dot q_j$ (inverse model), or an effort source `MSe` imposes the joint-side torque (forward model). The gear makes the motor turn $G\dot q_j$, so the inertia and the friction on the motor side appear at the joint as $G^2 J_m \ddot q_j$ and $B G^2 \dot q_j$, **exactly the reflected terms of the analytical model**. The torque the source supplies is the sensor output [A3_Torque1/y](signal:A3_Torque1/y).

## Why the compliant joint

`Revolute2DRigid` is the exact joint, but a rigid revolute on a 3-DOF planar body is index 3 (two hard pivot constraints): on this arm it fails at $t = 0$ with an unstable initialisation (probed, see `julia/BGSim/NOTES.md`). `Revolute2DCompliant` with $k_t = 10^8$ N/m, $b_t = 10^5$ N·s/m keeps every state integral. The pivot moves by about $m g / k_t \approx 10^{-6}$ m; the rotation is exact. Its cost shows in the results as a ring of the first millisecond.

In the inverse model every inertia is in **derivative causality** (the speeds are prescribed), so the compiler reports `W201` for the bodies and the motor inertias, as expected. MTK differentiates the cubic CSV speed through the registered derivatives of `csv_value` ([the CSV source](page:csv)).
