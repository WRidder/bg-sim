# flex-rotary-pendulum — a Furuta pendulum with a bending rod

A rotary (Furuta) pendulum whose pendulum rod is a `FlexibleBeam3D`. A horizontal aluminium arm (0.2 m, 0.108 kg) turns about the vertical axis on a motor bearing. The rod hangs from a pivot at the arm tip and swings in the plane perpendicular to the arm. The rod is an aluminium rod, d = 5 mm and L = 0.5 m, with two bending modes per plane and clamped-free modes at the pivot.

The rod is released from 90° with the motor free. At t = 3 s, a 0.4 N·m motor torque pulse of 0.05 s kicks the arm, which bends the rod.

Model `flex-rotary-pendulum-rigid` is the same rig with the rod as a `RigidBody3D` of the same mass and inertia. It is the reference for the swing.

```
World ─ Motor (Revolute3D, Kick torque) ─ ArmLink ─ Arm ─ PivotMount ─ Pivot (Revolute3D, free) ─ Rod (FlexibleBeam3D, ny = nz = 2)
```

## 3D view

| binding | signal |
| --- | --- |
| `link:arm` pose | `PArm/g` |
| `link:rod` pose | `Rod/pose`, the beam's reference frame at the pivot (rigid model: `PRod/g`) |
| `visual:rod_bar` deformation, bending-y | `Rod/eta_y[1..2]`, clamped-free, beam axis `+z`, y `+y`, length 0.5 m |
| `visual:rod_bar` deformation, bending-z | `Rod/eta_z[1..2]`, same beam |

The modal coordinates are in metres. The tip deflection in each plane is Σ φ_n(L) η_n, with φ_n(L) = ±2. The bending is of the order of a millimetre: use the deformation exaggeration of the 3D view to see it.

## Numbers

| quantity | value |
| --- | --- |
| rod mass ρ A L | 0.02651 kg |
| clamped-free bending frequencies f1, f2 | 14.25 Hz, 89.28 Hz |
| largest `Rod/eta_y[1]` (after the kick) | 0.62 mm |
| swing of the flexible vs. the rigid rod, max abs `Pivot/qout` difference over 0–1.5 s | 0.020 rad |

The rod's gravity and centrifugal loads stiffen it geometrically (the beam's G0/G1/G2 terms), and its energy `Rod/Ek + Rod/Ee + Rod/Eg` is part of the whole graph's power balance.

## Checks (`expected.json`)

- both models: no E101/E102/W202 diagnostics (the flexible model: no W201 either); all scene bindings resolve
- flexible model: energy ledger (Tellegen residual 2.9e-18 relative); `Rod/eta_y[1]` reaches the order of 1 mm
- `Pivot/qout` of the flexible and the rigid model agree within 0.05 rad over the first 1.5 s

## Files

| file | content |
| --- | --- |
| `design/build.py` | uv script: writes both models, the scene and `expected.json` |
| `models/flex-rotary-pendulum.bgmodel.json` | the flexible model |
| `models/flex-rotary-pendulum-rigid.bgmodel.json` | the rigid reference |
| `models/flex-rotary-pendulum.docs` | the model documentation |
| `scenes/flex-rotary-pendulum.sdf` | base, arm and rod (shared by both models) |

Rebuild with `uv run examples/flex-rotary-pendulum/design/build.py`; check with `uv run examples/run_checks.py --only flex-rotary-pendulum`.
