# Tetrahedron with four face wheels: face, edge, vertex

A free **regular tetrahedron** (edge $L = 0.25$ m) lies on its base face on a ground plane. A **reaction wheel is tied to each of its four faces**: the spin axis is the outward normal of the face and the wheel sits inside the body 35 mm from the centre of mass towards the face centroid. A scripted torque profile spins the wheels so that the body leaves its **face**, balances on an **edge** (two contacts) and then on a single **vertex** (one contact). The ground is a compliant `ContactSurface` and every vertex is a `ContactPoint` (Hunt-Crossley normal force, regularised Coulomb friction), so the phases are *emergent*: which vertices carry load follows from the contact forces; nothing is switched by hand. It is work package X5.6 of the M5 plan; the cube version of the same idea is `cube-pyramid-3d` (X-MB5).

![The model canvas|900](assets/6d126552ae4b.png)

```
Tetra (RigidBody3D) <-- Pose (PoseIntegrator3D, floating base)
  |  p                          | g
  +-- Mount_k -- C_k (ContactPoint) <-- Ground (ContactSurface)        (vertices k = 1..4)
  '-- WMount_k -- WJoint_k -- WLink_k -- Wheel_k (RigidBody3D)           (faces k = 1..4)
                     ^ drive
             Shaft_k -- Drv_k (CurrentControlledDrive) <-- Alloc.i_k
Seq (TipSequencer, 1 ms) --T--> Alloc (Allocator, 1 ms) --> Drv_k;  Drv_k.tau_m --> Tap (WheelTap)
Sense (TetraSense), EnBody/EnW_k (BodyEnergy), Ledger: sensors
```

The blocks: [Tetra](block:Tetra), [Pose](block:Pose), [Ground](block:Ground), the vertex contacts [C1](block:C1) to `C4`, the firmware [Seq](block:Seq) and [Alloc](block:Alloc), the sensors [Sense](block:Sense), [Tap](block:Tap), [Ledger](block:Ledger), and per wheel a mount, joint, [Wheel1](block:Wheel1), drive [Drv1](block:Drv1) and shaft.

## Run it

Press **Run**: 3.8 s with 761 output points and the contact system; about 40 s of solving on a warm worker. Plot [Sense/ang_vert](signal:Sense/ang_vert) (the angle between the world vertical and the vertex balance direction: it ends below 0.02 deg), [Seq/ph](signal:Seq/ph), the vertex loads [C3/f_n](signal:C3/f_n) and the wheel speeds [WJoint1/qdout](signal:WJoint1/qdout).

## 3D view

`scenes/tetra-3d.sdf` shows the ground plate, the tetrahedron (the GLB mesh `meshes/tetra.glb`, translucent, vertex 3 marked red and vertex 2 dark) and the four wheel discs on the face centroids. The body link is bound by its world pose (`Pose/qw .. Pose/pz`); each wheel joint `wheel_k` (axis z of the wheel frame, the face normal) is bound to the integrated wheel angle `WJoint<k>/q`. The three pictures show the start on the face, the edge balance and the vertex balance.

![Face: t = 0 s|420](assets/1dc816f5f8f7.png)

![Edge balance: t = 1.6 s|420](assets/585f7cb9936c.png)

![Vertex balance: t = 3.4 s|420](assets/bcb8b7d76ae8.png)

Continue with [the geometry](page:geometry), [the firmware](page:firmware) and [the results](page:results).
