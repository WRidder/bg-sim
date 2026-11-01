# Quad pendulum on a rotary arm: swing-up and balance

The Furuta version: a horizontal arm (0.30 m) turns about the vertical axis, driven by an ideal torque
(±3 N m), and carries a chain of four links (4 × 0.15 m, 0.03 kg) at its tip. The pendulum joints point
along the arm, so the links swing in the vertical plane tangent to the arm circle.

- The plant is a spatial multibond bond graph: [J1](block:J1) (`Revolute3D` about world z) with
  [Motor](block:Motor) (ideal torque source) and [ArmBearing](block:ArmBearing) on its drive, the
  [Arm](block:Arm) body (the hub/rotor inertia is lumped into it), and four `Revolute3D` + `RigidBody3D`
  links with viscous bearing friction.
- [Ctrl](block:Ctrl) (`QuadRotaryCtrl`), [Traj](block:Traj) and [Mon](block:Mon) follow the cart version.

![The model canvas|900](assets/0936f66d238b.png)

![3D view at t = 10 s: the chain balanced upright on the arm|500](assets/d0c87fb3a6b9.png)

**Design.** The same method as the cart (collocation, TVLQR, discrete LQR). The rotary rig has much less
authority over the chain: the trajectory runs at its bounds (|u| ≤ 2.5 N m, |θ_arm| ≤ 2.5 rad) and the TVLQR
saturates the torque at 3 N m for short moments. In the design closed loop the swing-up is robust to ±5 %
masses, +1 % lengths, three times the joint friction and 1 ms delay, but **not** to a 2 ms delay or to
quantised encoders; the balance alone is robust to both.

![Link angles, stacked energy per link, arm and torque, phase|900](assets/784ef66d8c87.png)

## Results

| quantity | bond graph | design closed loop (twin) |
| --- | --- | --- |
| all links within 5° | 4.42 s | 4.42 s |
| catch (BALANCING) | 5.50 s | 5.50 s |
| largest link deviation from 7.5 s | 0.0030° | 0.0030° |
| peak torque | 3.00 N m of 3 N m | 3.00 N m |
| peak arm travel | 2.50 rad of ±3 rad | 2.50 rad |
| stacked energy at 10 s | 0.7063 J = UPRIGHT | |
| free swing vs twin (arm, largest angle) | 1.7e-6 rad, 2.6e-3° | |
| balance scenario: push peak, recovery inside 0.5° | 10.05°, 1.60 s | 10.05° |
