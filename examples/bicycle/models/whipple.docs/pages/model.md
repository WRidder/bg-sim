# Model and bond graph

![The model canvas|1000](assets/bcb5f80dd672.png)

Every body, joint and contact is a library block:

```
Ground (ContactSurface) --> TyreR, TyreF (RollingDisk, knife edge)
RearFrame (RigidBody3D) <-- PoseB (PoseIntegrator3D)                 the floating base
RearFrame.p == MountR == RearHub (Revolute3D) == LinkRW == RearWheel (RigidBody3D) == TyreR
RearFrame.p == MountS == Steer (Revolute3D)   == LinkH  == Fork (RigidBody3D)
Fork.p      == MountF == FrontHub (Revolute3D) == LinkFW == FrontWheel (RigidBody3D) == TyreF
FreeR, FreeS, FreeF (Se, zero torque) -> the three joint drives
```

- **Bodies.** [RearFrame](block:RearFrame), [Fork](block:Fork), [RearWheel](block:RearWheel), [FrontWheel](block:FrontWheel): `RigidBody3D` with their mass and principal inertias. The paper gives the frame and fork inertias with a product of inertia $I_{xz}$, so `design/build_model.py` turns each body frame into its principal axes.
- **Floating base.** Only the rear frame's pose is integrated ([PoseB](block:PoseB)). The other bodies compose their poses through the joints (`LocalPose3D` and `ComposePose3D`), so they add no pose states.
- **Joints.** [RearHub](block:RearHub), [Steer](block:Steer) and [FrontHub](block:FrontHub) are `Revolute3D`. Their joint frames are placed by `FixedTransform3DNeutral` mounts. The steer joint's axis points *down* the steer axis, tilted 18° back, so its angle is the paper's steer angle (positive to the right). The five held directions of each joint are stiff springs ($10^6$) with dampers. They start deflected by the static load (0.6 mm at the rear hub), so the run starts in equilibrium.
- **Tyres.** [TyreR](block:TyreR) and [TyreF](block:TyreF) are `RollingDisk` contacts with a zero crown radius, i.e. the paper's knife-edge wheels. The contact point travels around the rim; the normal force is a stiff Hertz spring and the friction a regularised Coulomb law, so the wheels roll without slipping up to a creep below 0.5 mm/s. The contact radius is the wheel radius plus the static tyre deflection (0.72 mm rear, 0.46 mm front), which puts the loaded wheel centres at the paper's heights.
- **No hands.** The steer drive is a zero torque ([FreeS](block:FreeS)); so are the hub drives (no pedalling, no brakes).

Two example blocks (in `library/`) only measure:

| block | role |
| --- | --- |
| [Sense](block:Sense) `BikeSense` | the paper's coordinates: lean `phi` and its rate from the rear frame's pose and angular velocity, steer `delta` from the steer joint, heading `psi` (integrated heading rate), forward speed `v` (rear wheel rate times rolling radius) and the rear hub position |
| [Energy](block:Energy) `BikeEnergy` | kinetic and potential energy of the four bodies, the tyre and joint springs, the tyre losses and the steer torque's work: `Ebal` stays constant |

Signs: the world frame has x forward, y to the left and z up. The paper's frame (y right, z down) is the world turned by π about x, so the paper's lean and steer angles keep their signs (positive to the right).
