# WP-O0: orientation table

Inventory for `plan/PORT_ORIENTATION_PLAN.md`; nothing in the stdlib changes in WP-O0. One row per stdlib block with
a `Power{...}` port (205 blocks; the plan's per-category counts are confirmed), then the project-library blocks with
power ports (57 entries in 33 examples, 55 rows: the GearContact and VariableInertia3D rows each cover two identical
copies). The orientation column applies **O6 as written** in the plan. Where the
inventory shows that O6 is wrong or incomplete, the row says so, and the plan's section "Findings from WP-O0"
gives the amendment. The table rows are also in machine-readable form: `table_*.json` in the WP-O0 scratch folder,
which is what `violations.md` was computed from.

## 1. The sign rule, checked in the code

| Where | What the code does | Consequence |
| --- | --- | --- |
| Bond between two element ports (`connect.jl` `emit_bond_equations!`, l. 614-639) | `to.e = from.e`, `to.f = -from.f` | The equations do not change when the bond is reversed. The arrow is notation only. |
| Bond to a junction (`connect.jl` `_record_junction_bonds!`, l. 459-478; `_junction_bond_exprs`, l. 555-563) | A port at the tail (`into = flip = true`) enters as `-port.f`, a port at the head as `+port.f`; in the sum the tail is `+`, the head `-` | — |
| 0-junction (`junctions.jl` l. 174-190) | All `port.e` are equal. The flow sum is `sum(s_i * flip_i * port.f) = -sum(port.f) = 0` whatever the direction. | The direction does not change the model. |
| 1-junction (`junctions.jl` l. 191-207) | A head port has `port.f = f_J`, a tail port `port.f = -f_J`. The effort sum has `+e` for a tail port and `-e` for a head port. | Reversing one bond negates both `e` and `f` of that port. **This is the only place where the direction of a bond to a port matters.** |
| Junction-to-junction bond (`connect.jl` l. 441-457) | A virtual `(e, f)` pair, entered as "out of" the `from` junction and "into" the `to` junction, with no flip | Reversing a 1-1 or a 0-0 bond is neutral (substitute `e -> -e` or `f -> -f`). **Reversing a 0-1 bond changes the model**: the 0-junction's effort enters the 1-junction's sum with the other sign. There are 185 such bonds in 16 examples (`violations.md`). |
| Subsystem face and composite face (`instantiate.jl` l. 3379-3388, 2786-2809) | The face resolves to the internal port it exposes, or to the internal junction | A face adds no sign of its own. The outside bond acts directly on the internal port, or joins the internal junction's bond list. |
| Composite `connect(a, b)` (`instantiate.jl` l. 2881-2908) | `from = a`, `to = b`, the same as a diagram bond. A signal is swapped when `a` is an input. Two concrete scalar ports make a **wire**, not a bond (`_text_connection_kind!`). | All internal connections of the iconic composites (DCMotor, the drives, GearWithBacklash, DCMotorThermal) are wires. |
| Wire (`connect.jl` `emit_wire_equations!`, l. 574-612) | Across variables are equal and through variables sum to zero | No direction. |
| Multibond (Planar/Spatial) | The same rules, component by component (junction width 3 or 6) | — |

So the plan's "Why" paragraph is right for 1-junctions. The interim spec text (bond direction "does not change the
model" between two blocks and on a 0-junction) is also right. Two consequences shape the rest of this inventory:

1. A violating bond between two element ports, or between a port and a 0-junction, can be reversed without
   changing any equation. Enforcing O3 there is notational.
2. A change of a block's own law under O7 (for example a contact that drops the negated twist) changes every model
   that uses the block, whether or not its bond violates. On a 1-junction, reversing the bond *and* changing the law
   cancel each other. On a 0-junction or an element-to-element bond, nothing cancels the law change.

## 2. Legend

- **Orientation**: `in` = the bond's head is at this port; `out` = its tail; `any` = no constraint (O2).
- **[expects]**, for mechanics ports: what the block's equations need `port.f` to be today.
  - The reference is an O7 body 1-junction, whose flow is the true twist `V`, the one `ISpatial`/`IPlanar` see.
  - `+V`: the block takes `port.f` as the true twist of its frame and `port.e` as the wrench the body exerts *on the
    block*. This is right for an `in` port.
  - `-V`: the block takes the negated twist, and `port.e` is the wrench the block exerts *on the body*. This is right
    for an `out` port, and it is the old "contact convention".
  - `±`: the law is sign-symmetric (a zero-twist ground, an effort detector).
  - `pass`: a constant power-conserving two-port in into-block form (`a.f = -Ad b.f`, `b.e = Ad^T a.e`). It passes a
    sign straight through and works as (a in, b out) and as (a out, b in).
  - A plain `+`/`n/a` is a scalar port read in the same way.
  - On the old `RigidBody3D`/`RigidBody2D` (`inertia.p -> node`, junction flow `-V`), the `+V` blocks were bonded
    `X -> Body.p` and the `-V` blocks `Body.p -> X`. That is the NOTES/W218 table, and this inventory confirms it.
- **equations**:
  - `ok` when the block gives its documented behaviour with the declared orientation. That means (`in`, `+V`),
    (`out`, `-V`), `pass`, `±`, or for a scalar block: a source at the tail pushes the junction with `+value` and a
    sink at the head sees the physical flow.
  - `change` when the law must change (O7). Every `change` in this table means one thing: negate the port's sign
    convention (`p.f -> -p.f` in the law and `p.e -> -p.e`), or, for a composite, reverse the internal bonds named.
- **Iconic** blocks: concrete-domain blocks written for wire nodes (across/through form). Their ports are `any` under
  O6's last sentence, and their equations never change.

## 3. Count summary

Stdlib, 205 blocks, 414 power ports:

| | ports | of which |
| --- | ---: | --- |
| `in` | 136 | 101 sinks/fields/detectors/contacts/joint parents and drives, 14 odd one-ports, 21 two-port `a`/`p1` sides |
| `out` | 64 | 12 sources with a value, 29 joint `child` and other source-like ports, 21 two-port `b`/`p2` sides, 2 grounds |
| `any` | 214 | 195 iconic (wire) ports, 19 composite faces that are internal junctions (RigidBody2D/3D, Free2D, PinNode2D, Bar2D, FlexibleBeam2D/3D, ModalBody3D, Revolute2DRigid parent/drive; plus the iconic VacuumGenerator) |

| category | blocks | in | out | any | blocks whose equations change |
| --- | ---: | ---: | ---: | ---: | ---: |
| bondgraph | 15 | 11 | 9 | 0 | 2 (Sf, MSf) |
| contact | 10 | 14 | 1 | 1 | 8 |
| converters | 23 | 7 | 1 | 43 | 0 |
| drives | 4 | 0 | 0 | 5 | 0 |
| electrical | 18 | 0 | 0 | 48 | 0 |
| hydraulic | 12 | 2 | 0 | 20 | 0 |
| motion | 2 | 0 | 0 | 6 | 0 |
| multibond | 44 | 33 | 32 | 0 | 8 |
| planar | 15 | 15 | 6 | 9 | 10 |
| rotation | 18 | 1 | 0 | 33 | 0 |
| spatial | 21 | 51 | 15 | 9 | 19 |
| thermal | 14 | 2 | 0 | 24 | 0 |
| translation | 9 | 0 | 0 | 16 | 0 |
| **total** | **205** | **136** | **64** | **214** | **47** |

The 47 blocks with a `change`, by reason:

- **Flow sources written in the into-block convention** (`p.f = value`, so `Sf -> J` drives `J` with `-value`, and
  a 0-junction neighbour gets `-value` whatever the arrow): `Sf`, `MSf`, `SfPlanar`, `SfSpatial`, `MSfPlanar` (5).
  The MSf golden test works around this with `gain = -1`.
- **Effort sources written for the old body** (`p.e = -W`): `GravityPlanar`, `GravitySpatial`,
  `ExternalWrenchPlanar`, `ExternalWrenchSpatial` (4).
- **Contacts with the negated-twist convention**: `ContactPoint`, `MovingPlaneContact.p`, `RollingDisk`,
  `RollingSphere.a/b`, `SuctionCup.a/b`, `Tyre.p` (6), and `Rotor3D.p`, written the same way (1).
- **Joints, child side** (parent `in`, child `out`; the child expects `+V` today): the 15 spatial joints (Free3D,
  Revolute3D/-Compliant/-Friction/-Limit/-Rigid, Prismatic3D/-Compliant/-Friction/-Limit, Cylindrical3D, Helical3D,
  Planar3D, Spherical3D, Universal3D), `planar/Prismatic2D`, `Revolute2DCompliant`, `Revolute2DFriction`,
  `Revolute2DLimit`, `multibond/Revolute2D`, `contact/SwitchedPivot3D` (21).
- **Composites whose internal bonds are reversed** (O7 rebuild): `RigidBody2D` (and `Free2D`, which wraps it),
  `RigidBody3D`, `ImpactBody3D`, `PinNode2D`, `Bar2D`, `FlexibleBeam2D`, `FlexibleBeam3D`, `ModalBody3D`,
  `Revolute2DRigid` (10). Leaf equations do not change for these.

Project libraries: 57 entries (86 ports: 60 `in`, 10 `out`, 16 `any`). 9 need a change:
- the GearContact copies in cessna and f16;
- OmniContact, CylinderInBox, SphereInBox, ToolMotion, WingJoint, ShaftAxis;
- PistonEngine.

Under the recommended amendment A2 (iconic ports `in`; *not* recommended, see the plan's Findings), the stdlib count
would be 331 `in` / 64 `out` / 19 `any`.

## 4. Rules applied where O6 does not obviously classify a block

1. **Iconic blocks** (translation/, rotation/, electrical/, hydraulic/, thermal/, motion/, the concrete-domain
   converters, the drives) are `any` under O6's last sentence.
   - In practice their ports *are* bonded to junctions: 278 bonds in the examples. 255 of these sit at the head, and
     a bond into an iconic port reproduces the wire node exactly. The 23 tail bonds are self-consistent where every
     port on the junction is at the tail.
   - Declaring them `in` (A2) would protect those bonds. It would cost 96 more O3 bonds, of which 60 need review
     (cars, excavator, hybrid-powersplit, planar-links, maglev-train), and 12 notational O4 bonds. This inventory does
     not recommend it.
2. **One-terminal iconic blocks** are classified by function: sensors (SpeedSensor, AngleSensor, PositionSensor,
   VelocitySensor, AccelerationSensor, PressureSensor, TemperatureSensor), storage (Volume, Accumulator,
   HeatCapacitor) and dissipation (Brake) are `in`.
   - Every existing bond to them is already junction -> block.
   - One-terminal iconic **sources** (Fixed, FixedShaft, Ground, Tank, PressureSource, SpeedSource, VelocitySource,
     FixedTemperature, PrescribedTemperature, FixedHeatFlow, PrescribedHeatFlow) stay `any`. Their law is written
     for a wire node (the head position), so `out` would need `a.f = -v`, which breaks every wired use.
   - So O6's "sources are `out`" cannot apply to iconic sources.
3. **Two-terminal iconic sensors** (open point 1): `any`. See the plan.
4. **Converters between domains with Generic or bond-style ports** (`RS`, `PowerSensor`, project `TractionMachine`,
   `MotorGY`, `Crank`): two-port rule, power from the input side to the output side. `RS`: `p` in, `heat` out.
5. **Joint drive ports** are `in`: `drive.f` is the joint rate and `drive.e` the actuation into the joint.
   - All 26 stdlib drive ports are ok.
   - A passive element bonded *directly* to a drive port becomes an in-in O4 bond: 36 bonds, Free3D.drive_k -> MR in
     lunar-module and rocket. It needs a junction in between.
6. **Joints** (open point 2): `parent` in, `child` out. See the plan.
7. **Two-body fields** (AxialBar2D, ModalBeam2D/3D, ModalBodyCore3D, RollingSphere, SuctionCup, CylinderInBox,
   SphereInBox, AntiRollBar, InvertedPendulumBody) and multiport bodies (CornerCube, ArmDynamics3R): all ports `in`.
8. **Contact side ports** (MovingPlaneContact.j, Tyre.spin, SuctionCup.vac, GearContact.n/x/y): `in`. Power flows
   into the contact there, and their laws are in the wire convention.
9. **Composite faces**:
   - A face that is an internal junction is `any`. Because a face is resolved to the junction, the outside bond
     becomes a junction-to-junction bond when the outside end is a junction too: a 0-1 bond to Revolute2DRigid's
     0-junction `parent` face is a semantic direction that O3 does not check.
   - A face that exposes a block port takes that port's orientation: `ImpactBody3D.p` = `mount.a`;
     `Revolute2DRigid.child` = `xform.b`; DCMotor and the drives expose iconic ports.
10. **Pass-through two-ports** (TF, GY, MTF, MGY, PowerSensor, FixedTransform2D/3D/3DNeutral, TFAd, TFAdNeutral,
    JointTransform2D/3D, FixedJoint2D, and the flip-form TFPlanar/TFSpatial/TFPlanarMat/TFSpatialMat/MTFPlanar/
    MTFPlanarMat/MTFSpatial/ScrewTF/GYPlanar/GYSpatial/MGYPlanar/MGYSpatial):
    - They are listed `a in, b out` as O6 says.
    - For the mounts this is not enforceable (in-in with every mounted contact, sensor and joint parent; 959 O4 bonds
      in the examples). The plan's finding A1 replaces the fixed pair by a relation.
    - The `pass_sign: -1` blocks match their documented laws but have the opposite sign to the scalar TF/GY. They
      are used 4-6 times each, so aligning them is optional and cheap.

## 5. Table

### bondgraph

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| bondgraph | C | `p` (Generic) **in** |  | ok |
| bondgraph | I | `p` (Generic) **in** |  | ok |
| bondgraph | R | `p` (Generic) **in** |  | ok |
| bondgraph | MR | `p` (Generic) **in** |  | ok |
| bondgraph | De | `p` (Generic) **in** | detector | ok |
| bondgraph | Df | `p` (Generic) **in** | detector | ok |
| bondgraph | Se | `p` (Generic) **out** |  | ok |
| bondgraph | MSe | `p` (Generic) **out** |  | ok |
| bondgraph | Sf | `p` (Generic) **out** |  | **change**: `p.f ~ f` imposes the flow *into* the source, so `Sf -> J` drives the junction with -f (and a 0-junction neighbour gets -f whatever the arrow); must become `p.f ~ -f` |
| bondgraph | MSf | `p` (Generic) **out** |  | **change**: same as Sf: `p.f ~ gain*u` injects -gain*u (its golden test uses gain = -1); must become `p.f ~ -gain*u` |
| bondgraph | TF | `p1` (Generic) **in**; `p2` (Generic) **out** | two-port; pass-through (into-block law, works either way round) | ok |
| bondgraph | MTF | `p1` (Generic) **in**; `p2` (Generic) **out** | two-port; pass-through (into-block law, works either way round) | ok |
| bondgraph | GY | `p1` (Generic) **in**; `p2` (Generic) **out** | two-port; pass-through (into-block law, works either way round) | ok |
| bondgraph | MGY | `p1` (Generic) **in**; `p2` (Generic) **out** | two-port; pass-through (into-block law, works either way round) | ok |
| bondgraph | RS | `p` (Generic) **in**; `heat` (Thermal) **out** | converter between domains: power in at `p`, heat out at `heat` (`heat.f = -P`) | ok |

### contact

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| contact | ContactPoint | p (Spatial) in [-V] | | change: drop the negated-twist convention (v = R p.f, p.e = -wrench on body; ContactPoint.jl:108-138) |
| contact | ImpactBody3D | p (Spatial) in [-V] | composite; `p` is a face on the internal `mount.a`, not a junction, so it takes mount.a's orientation | change: O7 rebuild of the internals (node -> inertia/coriolis/flow); then p presents +V_pivot |
| contact | ImpactInertia3D | p (Spatial) in [+V] | | ok (ISpatial law, odd) |
| contact | MovingPlaneContact | p (Spatial) in [-V]; j (Translation) in [+V] | j: iconic side port in wire convention, power from the slide drive into the contact | p change (negated twist, :189-194, :242-247); j ok (:199-201, :248) |
| contact | RollingDisk | p (Spatial) in [-V] | | change: negated twist (:147-152, :190-195) |
| contact | RollingSphere | a (Spatial) in [-V]; b (Spatial) in [-V] | two-body multiport field, all in | change: both ports negated (:209-220, :279-290) |
| contact | SuctionCup | a (Spatial) in [-V]; b (Spatial) in [-V]; vac (Hydraulic) in [+V] | two-body field; vac: iconic storage port (flow into the chamber), wired in every example | a, b change (:182-193, :242-253); vac ok (:259-260) |
| contact | SwitchedPivot3D | parent (Spatial) in [+V]; child (Spatial) out [+V] | joint, plan default parent in / child out (open point 2) | change: child (Vrel = child.f - Ad^-1 parent.f treats both as true twists, :100-112, :142-158); no change if both ports were `in` |
| contact | Tyre | p (Spatial) in [-V]; spin (Rotation) in [+V] | spin: header bonds the spin junction -> spin; true spin rate, torque of the wheel on the tyre | p change (:225-230, :290-295); spin ok (:231, :296) |
| contact | VacuumGenerator | a (Hydraulic) any [±] | iconic one-port, only wired (98 wires): O6 last sentence. As a source it would be `out`; its law is the wire convention (a.f = flow into the generator), right for `in`/`any` | ok |

### converters

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| converters | BallScrew | `a` (Rotation) **any**; `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | CurrentSensor | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal sensor, open point 1) | ok |
| converters | DCMotor | `p`, `n` (Electrical) **any**; `shaft`, `housing` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any`; composite, faces expose iconic ports | ok |
| converters | EMConverter | `p`, `n` (Electrical) **any**; `shaft` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | Electromagnet | `p`, `n` (Electrical) **any**; `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | FixedDisplacementPump | `a`, `b` (Hydraulic) **any**; `shaft` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | FlowSensor | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal sensor, open point 1) | ok |
| converters | ForceSensor | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal sensor, open point 1) | ok |
| converters | HydraulicCylinder | `A`, `B` (Hydraulic) **any**; `rod` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | HydraulicMotor | `a`, `b` (Hydraulic) **any**; `shaft` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | LoadSensingPump | `a`, `b`, `ls` (Hydraulic) **any**; `shaft` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | RackAndPinion | `a` (Rotation) **any**; `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | TorqueSensor | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal sensor, open point 1) | ok |
| converters | VariableDisplacementPump | `a`, `b` (Hydraulic) **any**; `shaft` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | VoltageSensor | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal sensor, open point 1) | ok |
| converters | Wheel | `a` (Rotation) **any**; `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| converters | AccelerationSensor | `a` (Translation) **in** | one-terminal iconic block; O6 by function: sensor -> `in` | ok |
| converters | AngleSensor | `a` (Rotation) **in** | one-terminal iconic block; O6 by function: sensor -> `in` | ok |
| converters | PositionSensor | `a` (Translation) **in** | one-terminal iconic block; O6 by function: sensor -> `in` | ok |
| converters | SpeedSensor | `a` (Rotation) **in** | one-terminal iconic block; O6 by function: sensor -> `in` | ok |
| converters | VelocitySensor | `a` (Translation) **in** | one-terminal iconic block; O6 by function: sensor -> `in` | ok |
| converters | PressureSensor | `a` (Hydraulic) **in** | one-terminal iconic block; O6 by function: sensor -> `in` | ok |
| converters | PowerSensor | `a` (Generic) **in**; `b` (Generic) **out** | Generic through-sensor: two-port rule (power through a -> b; `y = a.e*a.f` is then the power a -> b); pass-through (into-block law, works either way round) | ok |

### drives

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| drives | CurrentControlledDrive | `shaft` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any`; composite, face exposes `tsense.b` | ok |
| drives | ElectricDrive | `shaft` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any`; composite, face exposes `tsense.b` | ok |
| drives | Gearbox | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any`; composite | ok |
| drives | ReactionWheel | `housing` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any`; composite, face exposes `torque.a` | ok |

### electrical

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| electrical | Battery | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | CCCS | `p1`, `n1`, `p2`, `n2` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | CCVS | `p1`, `n1`, `p2`, `n2` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | Capacitor | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | CurrentSource | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | IGBT | `c`, `e` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | IdealDiode | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | IdealSwitch | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | IdealTransformer | `p1`, `n1`, `p2`, `n2` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | Inductor | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | MOSFET | `d`, `s` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | MutualInductance | `p1`, `n1`, `p2`, `n2` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | OpAmp | `in_p`, `in_n`, `out` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | Resistor | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | VCCS | `p1`, `n1`, `p2`, `n2` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | VCVS | `p1`, `n1`, `p2`, `n2` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | VoltageSource | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| electrical | Ground | `p` (Electrical) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use); `p.e = 0` is sign-symmetric | ok |

### hydraulic

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| hydraulic | CheckValve | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | DirectionalValve43 | `P`, `T`, `A`, `B` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | FlowSource | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | Orifice | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | Pipe | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | PressureCompensatedFlowControl | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | PressureReliefValve | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | VariableOrifice | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| hydraulic | Volume | `a` (Hydraulic) **in** | one-terminal iconic block; O6 by function: storage -> `in` | ok |
| hydraulic | Accumulator | `a` (Hydraulic) **in** | one-terminal iconic block; O6 by function: storage -> `in` | ok |
| hydraulic | Tank | `a` (Hydraulic) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |
| hydraulic | PressureSource | `a` (Hydraulic) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |

### motion

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| motion | HBridge | `dc_p`, `dc_n`, `out_p`, `out_n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| motion | PowerAmplifier | `p`, `n` (Electrical) **any** | iconic (wire) block: O6 last sentence, `any` | ok |

### multibond

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| multibond | IPlanar | `p` (Planar) **in** [+V] | storage -> in | ok. Note: ddt(P) = p.e, p.f = P/m: defines V (the O7 reference) |
| multibond | ISpatial | `p` (Spatial) **in** [+V] | storage -> in | ok. Note: ddt(P) = p.e, p.f = P/m: defines V (the O7 reference) |
| multibond | CoriolisPlanar | `p` (Planar) **in** [+V] | body element (Eulerian junction structure), bonded like the inertia -> in | ok. Note: header prose 'the Coriolis bond carries the negative of the body twist' describes the old RigidBody junction and goes stale `p`: p.e = -ad(p.f)^T P is linear in p.f for the signal P, so odd at its port |
| multibond | CoriolisSpatial | `p` (Spatial) **in** [+V] | body element (Eulerian junction structure), bonded like the inertia -> in | ok. Note: header prose 'the Coriolis bond carries the negative of the body twist' describes the old RigidBody junction and goes stale `p`: p.e = -ad(p.f)^T P is linear in p.f for the signal P, so odd at its port |
| multibond | CPlanar | `p` (Planar) **in** [+V] | storage -> in | ok. Note: `p`: odd only with zero rest deflections q0 |
| multibond | CSpatial | `p` (Spatial) **in** [+V] | storage -> in | ok. Note: `p`: odd only with zero rest deflections q0 |
| multibond | RPlanar | `p` (Planar) **in** [+V] | dissipation -> in | ok |
| multibond | RSpatial | `p` (Spatial) **in** [+V] | dissipation -> in | ok |
| multibond | DePlanar | `p` (Planar) **in** [±] | detector -> in | ok. Note: `p`: p.f = 0 (sign-free); y = p.e is the wrench the junction exerts on the detector; a reversed bond on a 1-junction negates y |
| multibond | DeSpatial | `p` (Spatial) **in** [±] | detector -> in | ok. Note: `p`: p.f = 0 (sign-free); y = p.e is the wrench the junction exerts on the detector; a reversed bond on a 1-junction negates y |
| multibond | DfPlanar | `p` (Planar) **in** [+V] | detector -> in | ok. Note: `p`: p.e = 0, y = p.f = V at the head of an O7 body junction; a reversed bond negates y |
| multibond | DfSpatial | `p` (Spatial) **in** [+V] | detector -> in | ok. Note: `p`: p.e = 0, y = p.f = V at the head of an O7 body junction; a reversed bond negates y |
| multibond | SePlanar | `p` (Planar) **out** [-V] | source -> out | ok. Note: `p`: p.e = u, the bond-graph Se: at the tail of a body junction it pushes the body with +u (on the old RigidBody, bonded X -> Body.p, it gave -u); the value is a signal input |
| multibond | SeSpatial | `p` (Spatial) **out** [-V] | source -> out | ok. Note: `p`: p.e = u, the bond-graph Se: at the tail of a body junction it pushes the body with +u (on the old RigidBody, bonded X -> Body.p, it gave -u); the value is a signal input |
| multibond | MSePlanar | `p` (Planar) **out** [-V] | source -> out | ok. Note: `p`: p.e = (ur, ux, uy) like SePlanar; inputs are signals |
| multibond | SfPlanar | `p` (Planar) **out** [+V] | source -> out | **change**: p.f = u is the twist INTO the block; bonded out (tail) the junction gets -u: write p.f = -u (as for scalar Sf). Note: `p`: value is a signal input |
| multibond | SfSpatial | `p` (Spatial) **out** [+V] | source -> out | **change**: p.f = u is the twist INTO the block; bonded out (tail) the junction gets -u: write p.f = -u (as for scalar Sf). Note: `p`: value is a signal input |
| multibond | MSfPlanar | `p` (Planar) **out** [+V] | source -> out | **change**: p.f = (vr, vx, vy) is the twist INTO the block; bonded out (tail) the junction gets -(vr, vx, vy): write p.f = -(vr, vx, vy) (as for scalar Sf). Note: `p`: value is a signal input |
| multibond | GroundPlanar | `p` (Planar) **out** [±] | source (zero twist) -> out | ok. Note: `p`: p.f = 0: invariant under negating (e, f) |
| multibond | GroundSpatial | `p` (Spatial) **out** [±] | source (zero twist) -> out | ok. Note: `p`: p.f = 0: invariant under negating (e, f) |
| multibond | GravityPlanar | `p` (Planar) **out** [+V] | source -> out | **change**: p.e = -W_gravity (lines 9-15, written for the old inertia -> node junction); bonded out on an O7 body it must be p.e = +W_gravity |
| multibond | GravitySpatial | `p` (Spatial) **out** [+V] | source -> out | **change**: p.e = -W_gravity (header lines 7-8, equations 20-28); bonded out on an O7 body it must be p.e = +W_gravity |
| multibond | ExternalWrenchPlanar | `p` (Planar) **out** [+V] | source -> out | **change**: p.e = -w (lines 27-29, FIX-MB-4, for the old inertia -> node junction); bonded out on an O7 body it must be p.e = +w. Note: `p`: inputs are signals |
| multibond | ExternalWrenchSpatial | `p` (Spatial) **out** [+V] | source -> out | **change**: p.e = -w (lines 29-34); bonded out on an O7 body it must be p.e = +w; the uncommitted W218 prose (lines 12-18) goes. Note: `p`: inputs are signals |
| multibond | FixedTransform2D | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (fixed transform) -> a in, b out | ok. Note: a.f = -Ad b.f, a.e = Ad^-T b.e (lines 17-23): pass-through, works as (a in, b out) and (a out, b in) |
| multibond | FixedTransform3D | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (fixed transform) -> a in, b out | ok. Note: a.f = -Ad b.f, b.e = Ad^T a.e (lines 47-74): pass-through |
| multibond | FixedTransform3DNeutral | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (fixed transform / mount) -> a in, b out | ok. Note: pass-through like FixedTransform3D (lines 62-89). As a mount (b on the body, a on the attachment, the uncommitted W218 prose lines 27-30) a contact or Df on side a is bonded in-in to mount.a under a fixed `a => :in`: see the O3 finding |
| multibond | TFAd | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (adjoint transform) -> a in, b out | ok. Note: a.f = -Ad b.f, b.e = Ad^T a.e (lines 17-22): pass-through |
| multibond | TFAdNeutral | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (adjoint transform) -> a in, b out | ok. Note: pass-through (lines 20-25); used inside Revolute2DRigid |
| multibond | JointTransform2D | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (joint transform) -> a in, b out | ok. Note: a.f = -Ad b.f, a.e = Ad^-T b.e (lines 25-31): pass-through |
| multibond | JointTransform3D | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (joint transform) -> a in, b out | ok. Note: a.f = -Ad b.f, b.e = Ad^T a.e (lines 48-74): pass-through |
| multibond | TFPlanar | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (TF) -> a in, b out | ok. Note: a.f = n b.f, b.e = -n a.e: power-continuous but SIGN-FLIPPING under (a in, b out): J1 -> a, b -> J2 gives f_J1 = -n f_J2 (textbook modulus -1/n), unlike scalar TF (p2.f = -n p1.f) and the Ad transforms. Matches its documented port law, so ok; aligning with scalar TF (a.f = -n b.f, b.e = n a.e) is optional |
| multibond | TFSpatial | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (TF) -> a in, b out | ok. Note: a.f = n b.f, b.e = -n a.e: power-continuous but SIGN-FLIPPING under (a in, b out): J1 -> a, b -> J2 gives f_J1 = -n f_J2 (textbook modulus -1/n), unlike scalar TF (p2.f = -n p1.f) and the Ad transforms. Matches its documented port law, so ok; aligning with scalar TF (a.f = -n b.f, b.e = n a.e) is optional |
| multibond | TFPlanarMat | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (TF) -> a in, b out | ok. Note: a.f = M b.f, b.e = -M^T a.e: power-continuous but SIGN-FLIPPING under (a in, b out): J1 -> a, b -> J2 gives f_J1 = -n f_J2 (textbook modulus -1/n), unlike scalar TF (p2.f = -n p1.f) and the Ad transforms. Matches its documented port law, so ok; aligning with scalar TF (a.f = -n b.f, b.e = n a.e) is optional |
| multibond | TFSpatialMat | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (TF) -> a in, b out | ok. Note: a.f = M b.f, b.e = -M^T a.e: power-continuous but SIGN-FLIPPING under (a in, b out): J1 -> a, b -> J2 gives f_J1 = -n f_J2 (textbook modulus -1/n), unlike scalar TF (p2.f = -n p1.f) and the Ad transforms. Matches its documented port law, so ok; aligning with scalar TF (a.f = -n b.f, b.e = n a.e) is optional |
| multibond | MTFPlanar | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (TF) -> a in, b out | ok. Note: a.f = u b.f, b.e = -u a.e: power-continuous but SIGN-FLIPPING under (a in, b out): J1 -> a, b -> J2 gives f_J1 = -n f_J2 (textbook modulus -1/n), unlike scalar TF (p2.f = -n p1.f) and the Ad transforms. Matches its documented port law, so ok; aligning with scalar TF (a.f = -n b.f, b.e = n a.e) is optional |
| multibond | MTFPlanarMat | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (TF) -> a in, b out | ok. Note: a.f = M b.f, b.e = -M^T a.e: power-continuous but SIGN-FLIPPING under (a in, b out): J1 -> a, b -> J2 gives f_J1 = -n f_J2 (textbook modulus -1/n), unlike scalar TF (p2.f = -n p1.f) and the Ad transforms. Matches its documented port law, so ok; aligning with scalar TF (a.f = -n b.f, b.e = n a.e) is optional |
| multibond | MTFSpatial | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (TF) -> a in, b out | ok. Note: a.f = u b.f, b.e = -u a.e: power-continuous but SIGN-FLIPPING under (a in, b out): J1 -> a, b -> J2 gives f_J1 = -n f_J2 (textbook modulus -1/n), unlike scalar TF (p2.f = -n p1.f) and the Ad transforms. Matches its documented port law, so ok; aligning with scalar TF (a.f = -n b.f, b.e = n a.e) is optional |
| multibond | GYPlanar | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (GY) -> a in, b out | ok. Note: a.e = G b.f, b.e = -G^T a.f: under (a in, b out) a textbook gyrator with modulus -G, the opposite sign of scalar GY (p1.e = -r p2.f, p2.e = r p1.f). Matches its documented port law; aligning is optional |
| multibond | GYSpatial | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (GY) -> a in, b out | ok. Note: a.e = G b.f, b.e = -G^T a.f: under (a in, b out) a textbook gyrator with modulus -G, the opposite sign of scalar GY (p1.e = -r p2.f, p2.e = r p1.f). Matches its documented port law; aligning is optional |
| multibond | MGYPlanar | `a` (Planar) **in** [pass]; `b` (Planar) **out** [pass] | two-port (GY) -> a in, b out | ok. Note: a.e = G b.f, b.e = -G^T a.f: under (a in, b out) a textbook gyrator with modulus -G, the opposite sign of scalar GY (p1.e = -r p2.f, p2.e = r p1.f). Matches its documented port law; aligning is optional |
| multibond | MGYSpatial | `a` (Spatial) **in** [pass]; `b` (Spatial) **out** [pass] | two-port (GY) -> a in, b out | ok. Note: a.e = G b.f, b.e = -G^T a.f: under (a in, b out) a textbook gyrator with modulus -G, the opposite sign of scalar GY (p1.e = -r p2.f, p2.e = r p1.f). Matches its documented port law; aligning is optional |
| multibond | ScrewTF | `a` (Planar) **in** [pass]; `b` (Rotation) **out** [pass] | two-port (screw TF, Planar a / Rotation b) -> a in, b out | ok. Note: a.f = S b.f, b.e = -S^T a.e (lines 13-16): sign-flipping like TFPlanar. Revolute2DRigid relies on it: with (a in, b out) and the O7 body the composite needs only its rate bond flipped. A pass-form rewrite would need (b in, a out), i.e. power from the drive into the mechanism |
| multibond | Revolute2D | `parent` (Planar) **in** [+V]; `child` (Planar) **out** [+V]; `drive` (Rotation) **in** [+V] | joint -> parent in, child out (O6 literal); drive in | **change**: child expects +V (Vrel = child.f - Ad^-1 parent.f, child.e = +fs restoring, lines 62-81); bonded out it sees -V: negate child.f and child.e in the equations. With parent in, child in (two-body field) no change. Note: `drive`: drive.f = qdot, drive.e = actuation torque into the joint (the child gets +tau) |

### planar

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| planar | AxialBar2D | `pa` (Planar) **in** [+V]; `pb` (Planar) **in** [+V] | two-body field (bar between two pin nodes) -> all in | ok. Note: Ld = n.(pb.f - pa.f); port efforts are the forces the nodes exert on the bar (lines 15-16, 79, 88-93) |
| planar | Bar2D | `a` (Planar) **any** [n/a]; `b` (Planar) **any** [n/a] | composite: both faces are internal 1-junctions -> any | **change**: internal bar.pa -> nodeA, bar.pb -> nodeB violate (AxialBar2D in); reverse both (no physics change: the face-to-PinNode bonds are 1-1 junction bonds, direction-free) |
| planar | DeckContact2D | `p` (Planar) **in** [+V] | contact -> in | ok. Note: port flow = body twist, p.e = minus the wheel wrench on the body (lines 30-33, 115-116, 165-167): the +V convention, unlike the spatial contacts. Today bonded port -> body (tail of the old body sees +V); under O6/O7 body -> port. Header prose 'bond FROM this port TO the body' goes stale |
| planar | FixedJoint2D | `parent` (Planar) **in** [pass]; `child` (Planar) **out** [pass] | two-port (fixed joint) -> parent in, child out | ok. Note: parent.f = -Ad child.f, child.e = Ad^T parent.e (lines 31-36): pass-through. Cannot be both in (two heads would give V_p = -Ad V_c) |
| planar | FlexibleBeam2D | `A` (Planar) **any** [n/a]; `B` (Planar) **any** [n/a] | composite: both faces are internal 1-junctions -> any | **change**: internal beam.pa -> nodeA, beam.pb -> nodeB violate (ModalBeam2D in); reverse both so the end junction flow is the true end twist (O7, like RigidBody2D) |
| planar | Free2D | `p` (Planar) **any** [n/a] | composite: p is RigidBody2D's junction face -> any | **change**: inherits the RigidBody2D rebuild (O7); its own connections are signal-only (body.V -> pose.tw needs V = +twist, which the rebuilt node -> flow.p keeps). Note: planar Free2D is a floating body with one port, not a joint: it has no parent/child |
| planar | ModalBeam2D | `pa` (Planar) **in** [+V]; `pb` (Planar) **in** [+V] | flexible body (storage) with two attachment ports -> all in | ok. Note: 'Ports pa and pb are body-like (+twist, power in)' (line 9); ddt(P) gets +pa.e, +pb.e (line 277) |
| planar | PinNode2D | `p` (Planar) **any** [n/a] | composite: p is an internal 1-junction -> any | **change**: internal mass.p -> node violates (PointMass2D in); reverse to node -> mass.p (then the node junction flow is the true node velocity) |
| planar | PointMass2D | `p` (Planar) **in** [+V] | storage -> in | ok. Note: `p`: ddt(P) = p.e - m g0 (affine: gravity inside), so not odd |
| planar | Prismatic2D | `parent` (Planar) **in** [+V]; `child` (Planar) **out** [+V]; `drive` (Translation) **in** [+V] | joint -> parent in, child out (O6 literal); drive in | **change**: child expects +V (Vrel = child.f - Ad^-1 parent.f, child.e = spring/axial effort on the joint, lines 73-87); bonded out it sees -V: negate child.f and child.e. With both in, no change. Note: `drive`: drive.f = qdot, drive.e = -tau (+ stop) |
| planar | Revolute2DCompliant | `parent` (Planar) **in** [+V]; `child` (Planar) **out** [+V]; `drive` (Rotation) **in** [+V] | joint -> parent in, child out (O6 literal); drive in | **change**: child expects +V (same equations as multibond/Revolute2D, lines 51-70); bonded out it sees -V: negate child.f and child.e. With both in, no change |
| planar | Revolute2DFriction | `parent` (Planar) **in** [+V]; `child` (Planar) **out** [+V]; `drive` (Rotation) **in** [+V] | joint -> parent in, child out (O6 literal); drive in | **change**: child expects +V (same equations as multibond/Revolute2D, lines 47-67); bonded out it sees -V: negate child.f and child.e. With both in, no change |
| planar | Revolute2DLimit | `parent` (Planar) **in** [+V]; `child` (Planar) **out** [+V]; `drive` (Rotation) **in** [+V] | joint -> parent in, child out (O6 literal); drive in | **change**: child expects +V (same equations as multibond/Revolute2D, lines 54-77); bonded out it sees -V: negate child.f and child.e. With both in, no change |
| planar | Revolute2DRigid | `parent` (Planar) **any** [n/a]; `child` (Planar) **out** [+V]; `drive` (Rotation) **any** [n/a] | composite joint: parent face = 0-junction (any), child face = TFAdNeutral.b (out), drive face = 1-junction (any) | **change**: internal rate.p -> axis violates (Df in); reversing it to axis -> rate.p is also exactly what keeps qdot positive once the child sees -V on an O7 body. Note: `parent`: 0-junction face: element bonds are direction-free, but a junction-junction bond from a body 1-junction is semantic and not checked by O3; `child`: xform.b; today expects +V_c (old xform.b -> Body.p); `drive`: 1-junction face |
| planar | RigidBody2D | `p` (Planar) **any** [n/a] | composite: p is the body 1-junction -> any | **change**: O7 rebuild: node -> inertia.p, node -> coriolis.p, gravity.p -> node (with GravityPlanar's sign change), node -> flow.p |

### rotation

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| rotation | BeltDrive | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | Clutch | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | ElasticShaft | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | GearBacklash | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | GearWithBacklash | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any`; composite of LossyGear + GearBacklash (wires) | ok |
| rotation | IdealGear | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | Inertia | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | LossyGear | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | RotationalDamper | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | RotationalFriction | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | RotationalHardStop | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | TorqueSource | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | TorsionSpring | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | WormGear | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | PlanetaryGear | `sun`, `ring`, `carrier` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| rotation | Brake | `a` (Rotation) **in** | one-terminal iconic block; O6 by function: dissipation -> `in` | ok |
| rotation | FixedShaft | `a` (Rotation) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use); `a.f = 0` is sign-symmetric | ok |
| rotation | SpeedSource | `a` (Rotation) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |

### spatial

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| spatial | Free3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive1 (Rotation) in [+]; drive2 (Rotation) in [+]; drive3 (Rotation) in [+]; drive4 (Translation) in [+]; drive5 (Translation) in [+]; drive6 (Translation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Revolute3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Revolute3DCompliant | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Revolute3DFriction | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Revolute3DLimit | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Revolute3DRigid | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Prismatic3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Translation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Prismatic3DCompliant | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Translation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Prismatic3DFriction | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Translation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Prismatic3DLimit | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Translation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Cylindrical3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive1 (Rotation) in [+]; drive2 (Translation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Helical3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Planar3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive1 (Rotation) in [+]; drive2 (Translation) in [+]; drive3 (Translation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Spherical3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive1 (Rotation) in [+]; drive2 (Rotation) in [+]; drive3 (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Universal3D | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive1 (Rotation) in [+]; drive2 (Rotation) in [+] | joint: two-port parent -> child (O6), drives in | change: child expects +V (V_rel = child.f - Ad^-1 parent.f, child.e = body-on-joint wrench); as `out` it gets -V, so negate child.f and child.e. parent, drives ok. (+V, head) |
| spatial | Rotor3D | p (Spatial) in [-V]; drive (Rotation) in [+] | storage on the carrier body (gyrostat rotor inertia) -> in; drive in (motor torque into the rotor) | change: p: change - written for the NEGATIVE carrier twist (w = -p.f[1:3]) with p.e = wrench ON the carrier (Rotor3D.jl:8-24,47-50, the ContactPoint convention); as `in` p.f = +V: use w = p.f[1:3] and negate p.e. drive ok. |
| spatial | ModalBeam3D | pa (Spatial) in [+V]; pb (Spatial) in [+V] | flexible body with one port per end frame = storage at each frame (body-like, like ISpatial) -> all in | ok - header: ports 'body-like (+twist, power in)'; pa.f/pb.f are the end-frame twists of the frame twist V (ModalBeam3D.jl:10-12,578-581), efforts are the wrenches applied to the beam. |
| spatial | ModalBodyCore3D | pa (Spatial) in [+V]; pb (Spatial) in [+V]; pc (Spatial) in [+V]; pd (Spatial) in [+V]; pe (Spatial) in [+V]; ps (Translation) in [+] | flexible body with one port per interface frame = storage at each frame -> all in; rail slide ps (slider mass, drive force in) -> in | ok - pa.f = V and pb..pe.f the interface twists (+V; ModalBodyCore3D.jl:585-591,660-661); ps: ddt(psl) = ps.e + FsE, ps.f = sdr (597-598): force into the slider, + rate. |
| spatial | RigidBody3D | p (Spatial) any [junction] | composite port that IS the internal 1-junction -> any | change: change (internals, O7) - today inertia.p/coriolis.p/flow.p -> node, so f_J = -V; rebuild node -> inertia.p, node -> coriolis.p, node -> flow.p, gravity.p -> node (unchanged) so f_J = +V. GravitySpatial's own sign then changes (multibond table). Leaf ISpatial/DfSpatial need no change. |
| spatial | FlexibleBeam3D | A (Spatial) any [junction]; B (Spatial) any [junction] | composite ports that ARE internal 1-junctions -> any | change: change (internals, O7) - beam.pa -> nodeA, beam.pb -> nodeB give f_J = -V (the old RigidBody3D convention); reverse to nodeA -> beam.pa, nodeB -> beam.pb. Header line 7-8 'in any bond direction' is wrong and goes. |
| spatial | ModalBody3D | A (Spatial) any [junction]; B (Spatial) any [junction]; C (Spatial) any [junction]; D (Spatial) any [junction]; E (Spatial) any [junction]; S (Translation) any [junction] | composite ports that ARE internal 1-junctions -> any | change: change (internals, O7) - core.pX -> nodeX (X = a..e) and core.ps -> nodeS give f_J = -V / -sdr; reverse all six to nodeX -> core.pX. |

### thermal

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| thermal | BodyRadiation | `a`, `b` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| thermal | Convection | `solid`, `fluid` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| thermal | HeatFlowSensor | `a`, `b` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal sensor, open point 1) | ok |
| thermal | ThermalConductor | `a`, `b` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| thermal | ThermalResistor | `a`, `b` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| thermal | VariableConvection | `solid`, `fluid` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| thermal | ResistorHeated | `p`, `n` (Electrical) **any**; `heat` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| thermal | DCMotorThermal | `p`, `n` (Electrical) **any**; `shaft`, `housing` (Rotation) **any**; `winding` (Thermal) **any** | iconic (wire) block: O6 last sentence, `any`; composite | ok |
| thermal | HeatCapacitor | `a` (Thermal) **in** | one-terminal iconic block; O6 by function: storage -> `in` | ok |
| thermal | TemperatureSensor | `a` (Thermal) **in** | one-terminal iconic block; O6 by function: sensor -> `in` | ok |
| thermal | FixedTemperature | `a` (Thermal) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |
| thermal | PrescribedTemperature | `a` (Thermal) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |
| thermal | FixedHeatFlow | `a` (Thermal) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |
| thermal | PrescribedHeatFlow | `a` (Thermal) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |

### translation

| category | Block | ports: name (Domain) orientation [expects] | rule where O6 is not obvious | equations |
| --- | --- | --- | --- | --- |
| translation | Damper | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| translation | ForceSource | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| translation | Friction | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| translation | HardStop | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| translation | Mass | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| translation | Spring | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| translation | SpringDamper | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| translation | Fixed | `a` (Translation) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use); `a.f = 0` is sign-symmetric | ok |
| translation | VelocitySource | `a` (Translation) **any** | one-terminal iconic source: `any` (O6 last sentence; `out` would need `a.f = -v`, which breaks every wired use) | ok |

### Project libraries (`examples/*/library/*.jl`)

| example | Block | ports: name (Domain) orientation [expects] | rule | equations |
| --- | --- | --- | --- | --- |
| project:cars | AntiRollBar | `jl`, `jr` (Translation) **in** | field between two wheel junctions: all ports `in` (O6 multiport field) | ok |
| project:cars | Strut | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (field); its header documents `j.f = -dx/dt` (bump positive), bonded junction -> strut | ok |
| project:cars | TractionBattery | `p` (Electrical) **out** | project one-port with a concrete domain, bonded to junctions: O6 by function (source); into-block law, only on 0-junctions (direction-free) | ok |
| project:cars | TractionMachine | `dc` (Electrical) **in**; `shaft` (Rotation) **out** | converter between domains (modulated TF): power dc -> shaft; pass-through (into-block law, works either way round) | ok |
| project:cessna | PistonEngine | `p` (Rotation) **out** | project one-port with a concrete domain, bonded to junctions: O6 by function (source) | **change**: written for the head (`w = p.f`, `p.e = -tau`, header: 'power into the port'); as `out`: `w = -p.f`, `p.e = tau` |
| project:cessna | Propeller | `p` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (load torque) | ok |
| project:cessna | StrutDamper | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:f16 | StrutDamper | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:cessna | StrutSpring | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:f16 | StrutSpring | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:cessna | WheelFriction | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:f16 | WheelFriction | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:cessna | WheelSide | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:f16 | WheelSide | `j` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:cantilever-sections | ModalCantilever | `tip` (Translation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (field) | ok |
| project:aerial-contact | Propeller | `shaft` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (load torque) | ok |
| project:quadcopter | Propeller | `shaft` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (load torque) | ok |
| project:ingenuity | RotorBEMT | `shaft` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (rotor load) | ok |
| project:cube-3d | CornerCube | `m1`, `m2`, `m3` (Rotation) **in** | multiport storage field (body with wheel ports, `m.f = wheel rate`, `m.e` = torque in); wired today | ok |
| project:debug-tour | FlowSensor | `p` (Translation) **in** | detector (Df with a Translation port) | ok |
| project:drivetrain-kalman | FlowSensor | `p` (Generic) **in** | detector (copy of Df) | ok |
| project:drivetrain-position | FlowSensor | `p` (Generic) **in** | detector (copy of Df) | ok |
| project:industrial-servo | FlowSensor | `p` (Generic) **in** | detector (copy of Df) | ok |
| project:inverted-pendulum-cart | FlowSensor | `p` (Generic) **in** | detector (copy of Df) | ok |
| project:quarter-car | FlowSensor | `p` (Generic) **in** | detector (copy of Df) | ok |
| project:drivetrain-kalman | GearBacklash | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` (copy of the stdlib block) | ok |
| project:drivetrain-kalman | GearWithBacklash | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` (copy of the stdlib block) | ok |
| project:drivetrain-kalman | LossyGear | `a`, `b` (Rotation) **any** | iconic (wire) block: O6 last sentence, `any` (copy of the stdlib block) | ok |
| project:drivetrain-kalman | MotorGY | `a` (Electrical) **in**; `b` (Rotation) **out** | converter between domains (GY with concrete ports): power a -> b; pass-through (into-block law, works either way round) | ok |
| project:fanuc-pick | PneumaticCylinder | `p` (Translation) **out** | project one-port with a concrete domain, bonded to junctions: O6 by function (actuator = source); `v = -p.f`, `p.e = F`: written for the tail | ok |
| project:gripper | JawGuides | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal friction, wired) | ok |
| project:gripper | LeadScrew | `a` (Rotation) **any**; `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` (lossy screw, wired) | ok |
| project:gripper | WedgeHook | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` (TF with concrete ports, wired) | ok |
| project:panda-3d | GazFriction | `p` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (friction) | ok |
| project:panda-3d | RotorInertia | `p` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function (I) | ok |
| project:pendulum-double-rotary | ALClamp | `p` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:pendulum-double-rotary | ALFriction | `p` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:pendulum-double-rotary | ALGearSpring | `p` (Rotation) **in** | project one-port with a concrete domain, bonded to junctions: O6 by function | ok |
| project:quarter-car | OneSidedSpring | `a`, `b` (Translation) **any** | iconic (wire) block: O6 last sentence, `any` (two-terminal spring) | ok |
| project:reaction-wheel-1d | InvertedPendulumBody | `a`, `b` (Rotation) **in** | storage with two ports of the same rate (`a.f = b.f = w`): all `in` | ok |
| project:robird | Crank | `a` (Rotation) **in**; `bL`, `bR` (Rotation) **out** | modulated transformer with two outputs: power a -> bL, bR; pass-through (into-block law, works either way round) | ok |
| project:robot-arm-3d | ArmDynamics3R | `j1`, `j2`, `j3` (Rotation) **in** | multiport storage field (`j.f = qd`, `j.e` = joint torque in) | ok |
| project:suction-gripper | CupValve | `a`, `b` (Hydraulic) **any** | iconic (wire) block: O6 last sentence, `any` | ok |
| project:van-der-pol | BeltFriction | `p` (Generic) **in** | dissipation (R with an offset) | ok |
| project:van-der-pol | StribeckFriction | `p` (Generic) **in** | dissipation | ok |
| project:van-der-pol | TunnelDiode | `p` (Generic) **in** | nonlinear resistor | ok |
| project (excavator) | project:SoilCutting2D | `p` (Planar) **in** [+V] | contact/field on the bucket -> in | ok. Note: same convention as DeckContact2D (lines 23-26, 80-81, 99-101): p.f = bucket twist, p.e = minus the soil wrench on the bucket. Header 'bond FROM this port TO the bucket' goes stale |
| project:a109 | ShaftAxis | p (Spatial) out [+V]; s (Rotation) in [pass] | two-port Spatial<->Rotation, power from the rotor shaft to the airframe; p bonded to FixedTransform3DNeutral.a (`in` under O6) | change: p is taken as +V (s.f = -k.p.f, :26-32) and s sits on a 0-junction, so the flip reaches the mast's speed sum; negate (s.f ~ k.p.f, p.e ~ -k s.e) |
| project:aerial-contact | OmniContact | p (Spatial) in [-V] | | change: copy of ContactPoint's convention (:96-98, :128-133) |
| project:cessna, project:f16 | GearContact (same file twice) | p (Spatial) in [-V]; n, x, y (Translation) in [+V] | contact multiport; n/x/y are iconic ports on the strut 1-junctions whose C/R are also bonded junction -> element (all-in = wire node) | p change (:73-75, :88-93); n, x, y ok (:82-87) |
| project:fanuc-pick | CylinderInBox | a (Spatial) in [-V]; b (Spatial) in [-V] | two-body field (generated by build_library.py) | change both (:272-283, :542-551) |
| project:fanuc-pick | SphereInBox | a (Spatial) in [-V]; b (Spatial) in [-V] | two-body field (generated) | change both (:165-176, :276-287) |
| project:fanuc-pick | ToolMotion | p (Spatial) out [+V] | spatial flow source (generated) | change: p.f = V is the into-block flow (like stdlib Sf); out needs p.f ~ -(V + Vd(t-tk)), W ~ -p.e (:22-23) |
| project:robird | WingJoint | parent (Spatial) in [+V]; child (Spatial) out [+V]; drive (Rotation) in [+V] | joint (copy of Revolute3DCompliant), plan default | change: child (:125-131, :156-168); drive ok (:169-170) |
| project:lunar-module, project:rocket | VariableInertia3D | p (Spatial) in [+V] | modulated I | ok (odd; bonded J1 -> VI.p today, conforms) |
