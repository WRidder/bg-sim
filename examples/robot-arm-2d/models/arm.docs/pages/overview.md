# Planar 2-link arm on the multibond mechanics

A two-link planar arm with a payload, driven by a 1 ms PD controller with gravity feedforward, built from the J-MB6 composites (`RigidBody2D`, `Revolute2DCompliant`, `JointPose2D`, `LocalPose2D`) and the J-MB5 planar primitives (`ComposePose2D`, `GravityPlanar`, `CoriolisPlanar`). It is the planar-multibond arm of plan 9.10 / X-MB2 and, together with `reaction-wheel-2d`, Gate B's arm-and-balancer pair. The model `arm-free` removes the drives to test energy conservation.

![The model canvas: two-stroke planar bonds|900](assets/66e41f78b33b.png)

```
Ground -- Joint1 -- Link1 -- BodyJ1 -+- Body1 (1-junction: I + Coriolis + Gravity + Df)
         (kt, bt)   (0.2 m)  (1-junc) '- Joint2 -- Link2 -- Body2
                                (rx = 0.2)  (kt, bt)   (0.2 m)  (link 2 + payload)
Drive1: MSe(u1) -> Joint1.drive        Drive2: MSe(u2) -> Joint2.drive
Ref1/Ref2 (Step at 0.2 s) -> ArmPD (1 ms) -> u1, u2
```

At $t = 0.2$ s the references step to $q_1 = 0.6$ rad and $q_2 = -0.4$ rad; the shoulder saturates at its 30 N·m limit for about 0.1 s and both joints settle.

## What to try

- Plot [Joint1/qout](signal:Joint1/qout), [Joint2/qout](signal:Joint2/qout), [Drive1/p.e](signal:Drive1/p.e), [PoseTip/g[2]](signal:PoseTip/g[2]), [PoseTip/g[3]](signal:PoseTip/g[3]) (the preconfigured plots show angles, torques, end effector and joint rates).
- Set `Ctrl/g0` to 0: the gravity feedforward disappears and the shoulder droops (measured 0.5549 rad at the reference with the elbow at -0.4979); the cursor check at 3 s then fails, the intended signal that the feedforward does the holding.
- Set `Ctrl/u1max` to 5 N·m: the arm cannot hold the reference against gravity (the static demand is 10.98 N·m).
- Set `Joint1/bt` and `Joint2/bt` to 0: the fast pivot mode is pumped by the 1 ms drive and the solver stops with E901 (MaxIters) at $t = 2.54$ s; see [the notes](page:notes).

## 3D view

`scenes/robot-arm-2d.sdf` draws the two links in the vertical X-Z plane (the model's x-y plane). Joints `shoulder` and `elbow` follow `Joint1/qout` and `Joint2/qout`; the tip sphere sits at the end-effector pose `PoseTip`, which `expected.json` checks against the SDF kinematics along the whole run.

![3D view at t = 0.5 s|500](assets/61e094557dcd.png)

Continue with [the physics](page:physics), [the controller](page:controller) and [the results](page:results).
