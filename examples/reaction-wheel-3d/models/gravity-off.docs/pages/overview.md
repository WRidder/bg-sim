# Four-wheel pyramid on a spherical pivot

A rigid body hangs on a compliant **spherical pivot** and carries **four reaction wheels** in a pyramid. Every wheel is a real `RigidBody3D` on a `Revolute3D`, driven by a `CurrentControlledDrive`, so the gyroscopic coupling between the tumbling body and the spinning wheels is physical, not assumed. It is the 3D twin of `reaction-wheel-2d` (X-MB2) and the actuator half of plan 9.10 / X-MB4. With gravity off (this model) the **total angular momentum about the pivot**, body plus four wheels in the world frame, is constant. The model `gravity-on` releases the body 0.5 rad off the vertical; there the derivative of the angular momentum equals the gravity torque.

![The model canvas (flat graph)|900](assets/840e1c830b61.png)

```
World -- Pivot -- Link ------+-- Body            (RigidBody3D: m 2, J 0.06/0.05/0.04)
(ground) (Spherical3D) (CoM 0.2 m below)
                             +-- WMount_k -- WJoint_k -- WLink_k -- Wheel_k   (k = 1..4)
                             |   (Revolute3D, axis = z)  (identity)  (RigidBody3D)
                             |                      Shaft_k -- Drv_k <-- Alloc.i_k
 TxCmd/TyCmd/TzCmd (Sine) + Lambda --> Alloc (1 ms) --> Drv_k      Drv_k.tau_m --> Tap
```

The pages of this documentation: [construction](page:construction), [allocation and momentum balance](page:allocation), [results](page:results).

## Run it

Press **Run**: 4 s, 801 output points, about three minutes with the first compile. Plot [MeasBody/H[1]](signal:MeasBody/H[1]) to see the body exchange momentum with the wheels, [WJoint1/qdout](signal:WJoint1/qdout) to [WJoint4/qdout](signal:WJoint4/qdout) for the wheel speeds, and [Tap/nsp](signal:Tap/nsp) for the null-space tap.
