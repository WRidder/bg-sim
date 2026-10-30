# Six-axis arm with PD and gravity feedforward

A UR5-like six-axis serial arm moves from a home pose to a target pose under a 1 ms sampled **PD + gravity-feedforward** controller. It is built from the J-MB9 spatial composites (`Revolute3D`, `RigidBody3D`, `FixedTransform3DNeutral`, `LocalPose3D`, `ComposePose3D`) with the geometry and inertias of the J-MB10 six-axis golden test, and it is the 3D twin of `robot-arm-2d` (plan 9 / X-MB3, Gate C). Every power bond between the joints and the links is a `Power{Spatial}` bundle, drawn as **three strokes**.

This example folder also holds the X5.3 RRR arm models (`rrr`, `rrr-free`, `rrr-torque`, `rrr-multibond`, `rrr-multibond-soft`, `rrr-multibond-stiff`) which are documented in their own models.

![The model canvas (three-stroke spatial bonds)|900](assets/6ec29dfc2e79.png)

```
World - Mount - J1 - Link1 - BJ1 -+- B1 (RigidBody3D)
               (Revolute3D)  (CoM) '- T2 - J2 - Link2 - BJ2 -+- B2
                                        (standard-DH offset)  '- T3 - J3 - ... - J6 - Link6 - BJ6 - B6
D1..D6 (MSe torque sources) -> J1..J6.drive          Ctrl (ArmPD6, 1 ms) -> D1..D6
```

The run: 2 s with `Rodas5P`, `reltol` 1e-6, `abstol` 1e-8, 201 output points; the solver is set explicitly because `auto` fails here (see [the notes](page:notes)). Expect about two minutes of solve time on first run.

## What to look at

- the joint angles [J1/qout](signal:J1/qout) to `J6/qout` settling on the target;
- the controller torques [Ctrl/u2](signal:Ctrl/u2) (about -45.9 N·m settled: the gravity torque of the shoulder) and the tracking errors `Ctrl/e1..6`;
- the tool centre point [TCP/g[5]](signal:TCP/g[5]), [TCP/g[6]](signal:TCP/g[6]), [TCP/g[7]](signal:TCP/g[7]) (pose is quaternion first, so entries 5 to 7 are x, y, z).

## 3D view

`scenes/arm.sdf` draws the six-axis arm: every link is bound by its world pose to the model's composed body pose `P<i>/g[1..7]` (quaternion first), so the viewer needs no joint axes or kinematics of its own. A hub cylinder marks each joint axis and the bars run to the next joint; the red sphere is the tool centre point.

![3D view at t = 0.6 s|500](assets/464ee1a21de6.png)

Continue with [the construction](page:construction), [the controller](page:controller), [the results](page:results) and [the notes](page:notes).
