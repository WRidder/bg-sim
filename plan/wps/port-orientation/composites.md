# WP-O0: composites

Every stdlib or project block with `@components` and `@connections` whose connections include power bonds. For
each one this file lists the internal bonds, whether they conform to the orientations in `orientation-table.md`
(O6 as written), and what each becomes after O6/O7. WP-O5 does the work. Signal connections are not listed.

## How the compiler reads a composite (checked in `instantiate.jl`)

- `connect(a, b)` is a bond from `a` to `b`, the same as a diagram bond (l. 2881-2908). Two concrete-domain scalar
  ports make a **wire** (across equal, through sum zero), which has no direction.
- A connection to one of the composite's own interface ports is a **face**, not a bond. The face resolves to the
  internal port or junction it names (l. 2786-2809, 3379-3388). An outside bond on a face acts directly on that
  internal port, or joins that internal junction's bond list.
- So a face has no sign of its own. Its orientation, as WP-O5 should infer it:
  - a face on an internal **port** takes that port's orientation;
  - a face on an internal **junction** is `any`.
- One consequence is easy to miss. When the outside end is a junction too, a bond to a junction face becomes a
  junction-to-junction bond, and a 0-1 junction bond's direction is semantic (`orientation-table.md` section 1).
  `Revolute2DRigid.parent` (a 0-junction) is such a face.

## Composites with no bond to check

All internal connections of these composites are wires between iconic ports. Their faces expose iconic ports
(`any`). Nothing changes in O5.

| composite | internal power connections |
| --- | --- |
| `converters/DCMotor` | wires (electrical, rotational) |
| `converters/DCMotorThermal` | wires (electrical, rotational, thermal) |
| `drives/CurrentControlledDrive`, `drives/ElectricDrive` | wires |
| `rotation/Gearbox`, `rotation/GearWithBacklash`, `rotation/ReactionWheel` | wires |
| `examples/drivetrain-kalman/library/GearWithBacklash` (a project copy) | wires |
| `planar/Free2D` | one face (`p` = `body.p`); no internal bond. It inherits the RigidBody2D rebuild |

## planar/

### RigidBody2D (`p` = face on the 1-junction `node`: `any`)

| # | today | conforms | after O6/O7 |
| --- | --- | --- | --- |
| 1 | `connect(p, node)` | face | unchanged |
| 2 | `connect(inertia.p, node)` | no: IPlanar is `in`, here at the tail | `connect(node, inertia.p)` |
| 3 | `connect(coriolis.p, node)` | no: CoriolisPlanar is `in` | `connect(node, coriolis.p)` |
| 4 | `connect(gravity.p, node)` | yes: GravityPlanar is `out` | unchanged, but GravityPlanar's law becomes `p.e = +W` (O7). Today the inertia sits at the tail too, so `-W` was right relative to it |
| 5 | `connect(flow.p, node)` | no: DfPlanar is `in` | `connect(node, flow.p)` |

After the rebuild the junction flow is the true twist `V`; today it is `-V`. The exported `V` (`flow.y`) stays `+V`:
today `flow` sits at the tail of a `-V` junction, after the rebuild at the head of a `+V` junction. Free2D wraps
RigidBody2D, so it changes with it. Its `body.V -> pose.tw` stays `+V`.

### PinNode2D (`p` = face on the 1-junction `node`: `any`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(p, node)` | face | unchanged |
| 2 | `connect(mass.p, node)` | no: PointMass2D is `in` | `connect(node, mass.p)` |

### Bar2D (`a`, `b` = faces on the 1-junctions `nodeA`, `nodeB`: `any`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(a, nodeA)` | face | unchanged |
| 2 | `connect(bar.pa, nodeA)` | no: AxialBar2D is `in` | `connect(nodeA, bar.pa)` |
| 3 | `connect(b, nodeB)` | face | unchanged |
| 4 | `connect(bar.pb, nodeB)` | no | `connect(nodeB, bar.pb)` |

A Bar2D end bonded to a PinNode2D port is a 1-1 junction-to-junction bond, which is direction-free. Flipping bonds
2 and 4 together with PinNode2D's bond 2 changes no physics, because every node junction flow is negated
consistently. The only attachments that see the change are external loads on a node, such as a source on
`PinNode2D.p`.

### FlexibleBeam2D (`A`, `B` = faces on the 1-junctions `nodeA`, `nodeB`: `any`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(A, nodeA)` | face | unchanged |
| 2 | `connect(beam.pa, nodeA)` | no: ModalBeam2D is `in` | `connect(nodeA, beam.pa)` |
| 3 | `connect(B, nodeB)` | face | unchanged |
| 4 | `connect(beam.pb, nodeB)` | no | `connect(nodeB, beam.pb)` |

After the change the end junctions carry the true end twist, as the rebuilt RigidBody2D does, so a beam attaches
exactly like a body.

### Revolute2DRigid (`parent` = face on the 0-junction `node`: `any`; `child` = face on `xform.b`: `out`; `drive` = face on the 1-junction `axis`: `any`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(parent, node)` | face | unchanged |
| 2 | `connect(node, xform.a)` | yes: TFAdNeutral `a` is `in`, at the head | unchanged |
| 3 | `connect(node, screw.a)` | yes: ScrewTF `a` is `in` | unchanged |
| 4 | `connect(xform.b, child)` | face: `child` exposes `xform.b` (`out`) | unchanged; the outside bond must run `child -> body` |
| 5 | `connect(screw.b, axis)` | yes: ScrewTF `b` is `out`, at the tail | unchanged |
| 6 | `connect(drive, axis)` | face | unchanged |
| 7 | `connect(rate.p, axis)` | no: Df is `in` | `connect(axis, rate.p)` |

Sign check, with ScrewTF's sign-flipping law (`a.f = S b.f`) unchanged:

- The child body is an O7 body, so `xform.b` at the tail sees `-V_c`.
- The 0-junction balance gives `screw.a.f = -S qdot`, so `screw.b.f = -qdot`. That port is at the tail, so the
  `axis` flow is `+qdot`.
- `rate` at the head reads `+qdot`.
- A drive source bonded `Se -> drive` sits at the tail of `axis`. It delivers the power `tau*qdot`.

No example model uses Revolute2DRigid. `planar-links/reference/build_model.py` can generate a "rigid" variant, but
its README records that the variant fails at t = 0 (index 3). Only `test_mech_planar.jl`, `test_planar_mechanics.jl`
and `test_library.jl` exercise the block.

## spatial/

### RigidBody3D (`RigidBody3D.jl:38-48`; `p` = face on the 1-junction `node`: `any`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(inertia.p, node)` | no: ISpatial is `in`, at the tail | `connect(node, inertia.p)` |
| 2 | `connect(coriolis.p, node)` | no: CoriolisSpatial is `in` | `connect(node, coriolis.p)` |
| 3 | `connect(gravity.p, node)` | yes: GravitySpatial is `out` | unchanged; GravitySpatial's law becomes `p.e = +W` (O7) |
| 4 | `connect(flow.p, node)` | no: DfSpatial is `in` | `connect(node, flow.p)` |

Today the junction flow is `-V`; after the rebuild it is `+V`. ISpatial and DfSpatial see `p.f = +V` both before
and after, so their laws do not change, and `V = flow.y` is unchanged. CoriolisSpatial's header comment describes
the old orientation and should be updated with it.

### FlexibleBeam3D (`FlexibleBeam3D.jl:85-89`; `A`, `B` = faces on `nodeA`, `nodeB`: `any`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(beam.pa, nodeA)` | no: ModalBeam3D is `in`, at the tail | `connect(nodeA, beam.pa)` |
| 2 | `connect(beam.pb, nodeB)` | no | `connect(nodeB, beam.pb)` |

Today the end junctions carry `-V`, like the old RigidBody3D. After the change they carry `+V`. The header's claim
(l. 7-8) that the ends may be bonded "in any bond direction" is wrong for anything that is not an odd one-port, and
should go.

### ModalBody3D (`ModalBody3D.jl:163-176`; faces `A..E` = `nodeA..nodeE`, `S` = `nodeS`: `any`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1-5 | `connect(core.pa, nodeA)` ... `connect(core.pe, nodeE)` | no: ModalBodyCore3D ports are `in`, at the tail | `connect(nodeX, core.pX)` |
| 6 | `connect(core.ps, nodeS)` (Translation) | no | `connect(nodeS, core.ps)` |

Its gravity bond conforms. The law of GravitySpatial changes, as in RigidBody3D.

## contact/

### ImpactBody3D

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(p, mount.a)` | face: `p` takes `mount.a`'s orientation (`in`; under amendment A1 the mount's pair is resolved from the outside bond) | unchanged |
| 2 | `connect(mount.b, node)` | yes (`out` at the tail) | unchanged |
| 3 | `connect(inertia.p, node)` | no (`in` at the tail) | `connect(node, inertia.p)` |
| 4 | `connect(coriolis.p, node)` | no | `connect(node, coriolis.p)` |
| 5 | `connect(gravity.p, node)` | yes (`out` at the tail) | unchanged (GravitySpatial's law flips) |
| 6 | `connect(flow.p, node)` | no | `connect(node, flow.p)` |

After the rebuild the junction flow is `+V` (the CoM twist): `mount.b` sees `-V`, and `p = mount.a` sees
`+V_pivot`. The port therefore flips sign relative to today. No example model uses ImpactBody3D; cube-pyramid-3d
uses RigidBody3D behind a link instead (its README, l. 71). The block appears only in `test_switched_joint.jl`.

The other contact blocks (ContactPoint, MovingPlaneContact, RollingDisk, RollingSphere, SuctionCup, SwitchedPivot3D,
Tyre, VacuumGenerator) are primitives. They are covered in the table.

## Project libraries

There is one project composite with power bonds:

### bridge/Truck2D (`examples/bridge/library/Truck2D.jl:61-62`)

| # | today | conforms | after |
| --- | --- | --- | --- |
| 1 | `connect(contact.p, hub)` | no: DeckContact2D `p` is `in` (it already expects `+V`), here at the tail of the 1-junction `hub` | `connect(hub, contact.p)` |
| 2 | `connect(hub, body.p)` | `body.p` is the RigidBody2D `node` face, so this is a 1-1 junction-to-junction bond: direction-free | unchanged |

Today `hub` carries the old body flow `-V` (a 1-1 bond merges the two flows), and the contact at the tail sees
`+V`. After the RigidBody2D rebuild `hub` carries `+V`, and the reversed bond 1 keeps the contact at `+V`. The
rebuild and the reversal cancel. DeckContact2D's header ("bond FROM this port") then becomes stale.

No other project block in `examples/*/library/*.jl` has `@components` with power bonds. The fanuc-pick, humanoid
and panda libraries are generated sets of leaf blocks. The project fields (CylinderInBox, SphereInBox, AntiRollBar,
...) are primitives.

## How much this touches the models

These are internal bonds of composite instances in the flattened models. They violate O3 today and go away with the
O5 rebuild, without any edit to a model file (they are not in `violations.md`'s model counts).

| composite | violating internal bonds per instance | instances | internal bonds |
| --- | ---: | ---: | ---: |
| RigidBody3D | 3 | 484 | 1452 |
| RigidBody2D (Free2D included) | 3 | 112 | 336 |
| ModalBody3D | 6 | 5 | 30 |
| FlexibleBeam3D | 2 | 5 | 10 |
| bridge/Truck2D | 1 | 3 | 3 |
| PinNode2D | 1 | 2 | 2 |
| Bar2D | 2 | 1 | 2 |
| **total** (examples 1829, Julia fixtures 6) | | | **1835** |

Instances are counted over the 234 example models and the 58 Julia/contract fixtures. A body can be instantiated in
several models of one example, and each instance counts.

What the models *do* see is the O7 change of the body junction flow from `-V` to `+V`:

- Every element bonded to a body port is affected.
- The migration (O9) reverses those bonds where the junction is a 1-junction, and the reversal cancels the rebuild.
- A model that never reverses the bond (an `any` attachment, or a 0-junction neighbour) sees the change only through
  the law changes of the blocks in `orientation-table.md`.
