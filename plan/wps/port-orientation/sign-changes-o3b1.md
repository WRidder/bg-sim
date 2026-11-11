# Sign changes of WP-O3b1 (O18)

Examples with a build script, migrated by fixing the generator and regenerating: aerial-contact, ball-and-plate,
bicycle, bridge, excavator, gyrover, hybrid-powersplit, maglev-train, pendulum-double-fixed, pendulum-double-rotary,
pendulum-triple-fixed, pendulum-triple-rotary, robird, segway, tetra-3d.

The block-level changes of WP-O3a and WP-O3a2 (`sign-changes.md`) apply to these models as listed there: the joint
child ports (`<Joint>/child.*`, and the link transform behind the child, `<Link>/a.*`, `<Link>/b.*`), the contact ports
(`RollingDisk`, `RollingSphere`, `ContactPoint` `p.*`/`a.*`/`b.*` and the mounts between body and contact), `Rotor3D`
`p.*`, gravity and external-wrench `p.*`, and the internal `Body/gravity/p.*`. They are not repeated per model below.
Reversing a mount's body-side bond (`Mount.b -> Body.p` to `Body.p -> Mount.b`) changes no signal: the body junction
flow and the bond direction change together, so `Mount/a.*` and `Mount/b.*` keep their values.

## Project library blocks

| block | change | what changes sign in a model |
| --- | --- | --- |
| `aerial-contact/library/OmniContact.jl` | law as `contact/ContactPoint` after WP-O3a: `v = +R p.f` (was `-R p.f`), `p.e[4:6] = -(R^T F_w)` (was `+`); `@orientation p => :in` | `Wheel1..3/p.e`, `Wheel1..3/p.f`, and the wheel mounts `MountW1..3/a.*`, `MountW1..3/b.*` (kept bonds). The contact's own variables (`f_n`, `delta`, `sd`, `sr`, `fd`, `frl`, `v1..v3`) keep their sign. |
| `aerial-contact/library/Propeller.jl` | `@orientation shaft => :in` (wired only) | none |
| `robird/library/WingJoint.jl` (copy of `Revolute3DCompliant`) | the WP-O3a joint law on the child side: `V_c = -child.f`, `W_c = -child.e`; `@orientation parent => :in, child => :out, drive => :in` | `JL1/child.*`, `JL2/child.*`, `JR1/child.*`, `JR2/child.*` and their links `LinkL1/a.*`, `b.*` (and the other wing links). `q`, `qdot`, `Vrelout`, `dang`, `dlin`, the pose, `drive.*`, `parent.*` keep their sign. |
| `robird/library/Crank.jl` | `@orientation a, bL, bR => :in` (wired only) | none |
| `excavator/library/SoilCutting2D.jl` | `@orientation p => :in`; header: the body junction bonds into the port (law unchanged, it already reads the true twist) | none (the bond is reversed together with the body junction's sign: `Soil/p.*` keep their values) |
| `bridge/library/Truck2D.jl` | internal `connect(hub, contact.p)` (was `connect(contact.p, hub)`) | none (`DeckContact2D` already read the true twist; the `hub` flow and the bond direction changed together) |
| `pendulum-double-rotary/library/ALClamp.jl`, `ALFriction.jl`, `ALGearSpring.jl` | `@orientation p => :in`; every bond already ended at `p` | none |

## Models

| model(s) | how | signals that change sign |
| --- | --- | --- |
| `bicycle/whipple`, `balance` | generator: `RearFrame.p -> MountR.b`, `RearFrame.p -> MountS.b`, `Fork.p -> MountF.b` | none beyond the WP-O3a block list |
| `gyrover` (6 models with a body) | generator: `Wheel.p -> MountA.b`, `Pendulum.p -> MountT.b` | none beyond the block list |
| `segway` (4 models) | generator: `Body.p -> MountL.b`, `Body.p -> MountR.b` | none beyond the block list |
| `tetra-3d/sequence-contact` | generator: the four `Tetra.p -> WMountk.b` (reversed in the generator when the cube template still has them the old way) | none beyond the block list |
| `pendulum-double-fixed`, `pendulum-triple-fixed` (main and `free`) | shared generator `pendulum_model.py`: `BodyJk -> Joint(k+1).parent` | none beyond the block list (the hand-built `BodyJk` junction flow is now `+V`, and the parent bond turned with it) |
| `pendulum-double-rotary` (2 rotary + 11 ACTILINK models), `pendulum-triple-rotary` (2 rigid + 3 flex) | generators `rotary_build.py`, `actilink_build.py`, `triple_build.py`, `flex_build.py`: `BJ(k-1) -> Tk.b`; flex: `Arm.B -> T2.b` | none beyond the block list |
| `aerial-contact` | generator: `Body.p -> MountS.b`, `Arm.p -> TipM.b`; `OmniContact` law (above) | `Wheel1..3/p.*`, `MountW1..3/a.*`, `b.*` |
| `robird`, `robird-trim` | generator: `Parent.p -> Mount<tag>.b` (7 mounts); `WingJoint` law (above) | the `WingJoint` child ports and links (above) |
| `ball-and-plate/ball-and-plate-free` | generator: `LockX -> Gimbal.drive1`, `LockY -> Gimbal.drive2` (the drive is `in`); the lock 1-junctions now carry `+qdot`, so the preloaded spring's start is negated (`SpringX` `q` = `+tau/k`, was `-tau/k`); the energy book `Energy.dq1` keeps its value (`-lock_preload`) | `SpringX/p.e`, `SpringX/p.f`, `SpringX/q`, `DamperX/p.e`, `DamperX/p.f`, `SpringY/p.e`, `SpringY/p.f`, `SpringY/q`, `DamperY/p.e`, `DamperY/p.f` |
| `ball-and-plate/ball-and-plate-swing` | generator: `LockY -> Gimbal.drive2` (axis 1 runs through the shaker's 0-junction, unchanged) | `SpringY/p.*`, `SpringY/q`, `DamperY/p.*` |
| `bridge/bridge-crossing`, `bridge-failure`, `bridge-pier` | `Truck2D` (above) | none |
| `excavator` (4 models) | generator: `BodyJ1 -> Joint2.parent`, `BodyJ2 -> Joint3.parent`; `BodyJ3 -> Soil.p`; per cylinder `Rod -> RP.b`, and a new 1-junction `<Cyl>Pinion` (the pinion shaft) with `Pinion -> RP.a` and `Pinion -> Lever.p2` in place of the direct `RP.a -> Lever.p2` bond (in-in) | `BoomRP/a.*`, `BoomRP/b.*`, `ArmRP/a.*`, `ArmRP/b.*`, `BucketRP/a.*`, `BucketRP/b.*` (the rack now reads the rod speed `+v`, it read `-v`) |
| `hybrid-powersplit/hybrid-ev-mode`, `hybrid-rule-based`, `hybrid-ecms` | generator: `Sun -> MG1.shaft`, `Ring -> MG2.shaft`, the stator bonds into `MGk.n` with `MGk.p` grounded (terminals swapped, as the stdlib `DCMotor` wires its gyrator; `k` unchanged); `BatJ -> Battery.p` and the 0-1 bond `Bus -> BatJ` reversed; a new gain `BatDischarge = -BatCurrent` feeds the BMS and `PBat` | `MG1/shaft.*`, `MG2/shaft.*`; `BatCurrent/p.f`, `BatCurrent/y` (now the charging current, the battery's own sign; `BatDischarge/y` has the old value). **Deviation:** `MGk/p.*` and `MGk/n.*` swap roles (new `n.*` = old `p.*`, new `p.f` = old `n.f`, `p.e = 0`): a terminal swap, not a negation. `Battery/p.*`, `soc`, `BMS/y`, `PBat/y` keep their values. |
| `hybrid-powersplit/hybrid-kinematics` | generator: `Carrier2 -> Gear.carrier`, `Sun2 -> Gear.sun`, `Ring2 -> Gear.ring` (all terminals of the iconic `PlanetaryGear` flip: neutral) | `Gear/carrier.*`, `Gear/sun.*`, `Gear/ring.*` |
| `maglev-train/maglev-vehicle` | generator: `ZF -> LeverF.b`, `ZR -> LeverR.b` (0-junction: neutral); rear: `Jt -> FlipR.p1`, `FlipR.p2 -> LeverR.a` with a new `bondgraph/TF` `FlipR` (`n = -1`) in place of the reversed `LeverR.a -> Jt` bond | none (`LeverF/*`, `LeverR/*` keep their values) |

No `expected.json` entry, plot, binding or dashboard card of these examples names a signal on this list, so none was
edited.
