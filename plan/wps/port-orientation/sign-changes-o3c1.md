# Sign changes WP-O3c1 (O18)

Models of `quad-pendulum`, `pendulum-double-cart`, `pendulum-double-cart-lab`, `pendulum-triple-cart`, `cube-3d`,
`fem-bracket`, `fem-gantry`, `fem-torsion`, `robot-arm-3d`, `panda-3d`, `humanoid-dual-arm`, `fanuc-pick`.

**No `expected.json` entry, golden file, plot, binding or dashboard card of these examples names a signal on this
list, so no expectation was negated.** (Searched: every `expected.json` and every model's `plots`, `bindings` and
`dashboard` for `child.e/f`, `parent.e/f`, `gravity/p.*`, `<mount>/a.*`, `b.*`, `p.e`, `p.f` and the clamp states;
the one hit, `fem-torsion` `Motor/a.e`, is a wired iconic `TorqueSource`, unchanged.) The RL and robust-control
material reads no port variable either (`rl/`, the `ExportOutput`s of the `-plant` models: `x`, `q1`, `q2`, `v`,
`w1`, `w2`, `i_m`; the `ExportInput`s `V`, `F_push`): no exported FMU or stored policy depends on a signal on this
list.

## What the reversals themselves change

The reversals of this package are neutral at the port level: a joint parent (`N -> Joint.parent`, `BodyJ -> T.b`),
a FEM face (`face -> Weld.parent`, `Beam.E -> YGuide.parent`, `Beam.S -> YMotor.b`/`SlideSpring.b`/`SlideDamper.b`)
reads the same flow and effort as before, because the junction it hangs on changed sign in WP-O3a and the
reversal cancels it. Two exceptions:

| model(s) | how | signals that change sign |
| --- | --- | --- |
| `humanoid-dual-arm/humanoid-hold` | generator: `LWeldJ -> LWeld.drive`, `RWeldJ -> RWeld.drive` (the drive is `in`); the junction holds only the linear `WeldSpring` (C) and `WeldDamper` (R), so its flow changes from `-qdot` to `+qdot` | `LWeldSpring/p.e`, `LWeldSpring/p.f`, `LWeldSpring/q`, `LWeldDamper/p.e`, `LWeldDamper/p.f`, and the same for `R` |
| `fanuc-pick` (18 models) | project block `ToolMotion` (O15): law `p.f ~ -(V + Vd (t - tk))`, `W ~ -p.e`, `p => :out`; the gripper junction now carries `+V` and the joint mounts are bonded `TJ -> JM.b` | `Tool/p.e`, `Tool/p.f`. `Tool/W` (plotted) keeps its sign by construction. |
| `fanuc-pick` (`loose-*`, 8 models) | project blocks `SphereInBox`, `CylinderInBox` (O7/O17): the port flows are the body twists and the efforts minus the wrenches on the bodies (as `SuctionCup` in WP-O3a); bonds kept | `Walls/a.e`, `Walls/a.f`, `Walls/b.e`, `Walls/b.f`, `WA/a.*`, `WA/b.*`, `WB/a.*`, `WB/b.*`. `Walls/F`, `Fmag`, `Fn`, `Ec`, `pos`, `vel` keep their sign. |

## What the library law changes of WP-O3a change in these models (bonds kept)

Listed by `tools/migrate_bond_orientation.py --check` on the pre-migration models, per the WP-O3a block table
(`sign-changes.md`): joint child ports, body gravity ports, the mounts on a joint's child side, the contacts and
their mounts, the external wrenches, the clamps on a FEM face.

| example | signals that change sign |
| --- | --- |
| `pendulum-double-cart`, `pendulum-double-cart-lab` (every model) | `Rail/child.e`, `Rail/child.f`, `Joint1/child.*`, `Joint2/child.*`, `Link1/parent.*`, `Link1/child.*`, `Link2/parent.*`, `Link2/child.*`, `Cart/gravity/p.*`, `Body1/gravity/p.*`, `Body2/gravity/p.*`, `Push/p.e`, `Push/p.f` |
| `pendulum-triple-cart` | as the double cart, with `Joint3`, `Link3`, `Body3` |
| `quad-pendulum` cart models | as the double cart, with `Joint1..4`, `Link1..4`, `Body1..4` |
| `quad-pendulum` rotary models | `J1..J5/child.*`, `ArmLink/a.*`, `ArmLink/b.*`, `Link1..4/a.*`, `Link1..4/b.*`, `Arm/gravity/p.*`, `Rod1..4/gravity/p.*`, `TipPoint/a.*`, `TipPoint/b.*` |
| `cube-3d` (`-mb`, `-mb-soft`) | `Pivot/child.*`, `Link/a.*`, `Link/b.*`, `WJoint1..3/child.*`, `WLink1..3/a.*`, `WLink1..3/b.*`, `Body/gravity/p.*`, `Wheel1..3/gravity/p.*` |
| `fem-torsion` | `Bearing/child.*`, `Weld1/child.*`, `Weld2/child.*`, `Mount/a.*`, `Mount/b.*`, `Disk1/gravity/p.*`, `Disk2/gravity/p.*` |
| `fem-bracket` | `Table/child.*`, `WeldA/child.*`, `WeldB/child.*`, `Seat/a.*`, `Seat/b.*`, `Offset/a.*`, `Offset/b.*`, `Hub/gravity/p.*`, `Payload/gravity/p.*`; ring-down: `Clamp/p.e`, `Clamp/p.f`, `Clamp/qrx`, `qry`, `qrz`, `qx`, `qy`, `qz`, `ClampDamping/p.e`, `ClampDamping/p.f` (the face A junction flow is now the twist) |
| `fem-gantry` | `X1/child.*`, `X2/child.*`, `X1Turn/a.*`, `b.*`, `X2Turn/a.*`, `b.*`, `WeldA/child.*`, `PivotB/child.*`, `WeldABracket/a.*`, `b.*`, `PivotBBracket/a.*`, `b.*`, `YGuide/child.*`, `YOffset/a.*`, `b.*`, `X1Car/gravity/p.*`, `X2Car/gravity/p.*`, `YCar/gravity/p.*`; static: `ClampA/p.*`, `ClampA/qrx..qz`, `ClampADamping/p.*`, `ClampB/...` likewise |
| `robot-arm-3d` (`arm`, `rrr-multibond*`) | `J1..J6/child.*`, `Link1..6/a.*`, `Link1..6/b.*`, `B1..B6/gravity/p.*` (`rrr-multibond*`: 1..3) |
| `panda-3d` | `J1..J7/child.*`, `Link1..7/a.*`, `b.*`, `B1..B7/gravity/p.*` (`panda`, `panda-rigid`: under `Robot/`) |
| `humanoid-dual-arm/humanoid-hold` | `LJ1..7/child.*`, `RJ1..7/child.*`, `LLink1..7/a.*`, `b.*` (and `R`), `LB1..7/gravity/p.*` (and `R`), `LWeld/child.*`, `RWeld/child.*`, `LGrip/a.*`, `b.*`, `RGrip/a.*`, `b.*`, `Box/gravity/p.*` |
| `fanuc-pick` | `Rod1..5/child.*`, `RM1..5/a.*`, `b.*` (joint child side), `CM1..5/a.*`, `b.*`, `Cup1..5/a.*`, `b.*`, `PM1..5/a.*`, `b.*`, `FMount1..4/a.*`, `b.*`, `Floor1..4/p.*`, `Parcel/gravity/p.*`, `RodBody1..5/gravity/p.*` (and `Content/gravity/p.*` in the `loose-*` models) |

`.*` means `.e` and `.f`.
