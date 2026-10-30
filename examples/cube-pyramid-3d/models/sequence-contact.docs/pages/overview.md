# Four-wheel cube: face, edge, corner

A free cube ($a = 0.2$ m) with **four reaction wheels in a pyramid** lies on a ground plane. A scripted torque profile spins the wheels so that the cube leaves its **face**, balances on an **edge** (tilt 45 deg) and then on a **corner** (tilt $\arctan\sqrt2 = 54.74$ deg, the body diagonal vertical). The ground is a compliant `ContactSurface`; every contact is a `ContactPoint` (Hunt-Crossley normal force, regularised Coulomb friction), so the phases are *emergent*: which vertices carry load follows from the contact forces, nothing is switched by hand. It is X-MB5 of plan 6, the cube/pyramid example of plans 3.3 and 9. The model `edge-contact` repeats the edge phase alone and `edge-switched` replaces the contacts by a `SwitchedPivot3D`; their pages compare the two.

![The model canvas|900](assets/d67112e0b920.png)

```
Cube (RigidBody3D) <-- Pose (PoseIntegrator3D, floating base)
  |  p                          | g
  +-- Mount_k -- C_k (ContactPoint) <-- Ground (ContactSurface)         (vertices k = 1..4)
  '-- WMount_k -- WJoint_k -- WLink_k -- Wheel_k (RigidBody3D)           (k = 1..4)
                      ^ drive
              Shaft_k -- Drv_k (CurrentControlledDrive) <-- Alloc.i_k
 Seq (TipSequencer, 1 ms) --T--> Alloc (Allocator, 1 ms) --> Drv_k;  Drv_k.tau_m --> Tap (WheelTap)
 Sense (CubeSense), EnCube/EnW_k (BodyEnergy), Ledger: sensors
```

## Run it

Press **Run**. The model compiles to a 25-state system with 2512 recorded signals; the README measured roughly 8 minutes of wall time on a loaded machine (the MTK build of the contacts plus four driven wheels dominates). Plot [Sense/tilt](signal:Sense/tilt) and [Seq/ph](signal:Seq/ph), the vertex loads [C1/f_n](signal:C1/f_n) to [C4/f_n](signal:C4/f_n) and the wheel speeds [WJoint1/qdout](signal:WJoint1/qdout).

## 3D view

`scenes/cube-pyramid-3d.sdf` shows the cube (translucent) on the ground plane with its four pyramid wheels. The cube and each wheel are bound by their world pose (quaternion first).

![Face: t = 0.2 s|420](assets/67fad8bdba29.png)

![Edge balance: t = 1.8 s|420](assets/dae7e6feaeab.png)

![Corner balance: t = 4.0 s|420](assets/7b245ce91563.png)

Continue with [the construction](page:construction), [the firmware](page:firmware) and [the results](page:results).
