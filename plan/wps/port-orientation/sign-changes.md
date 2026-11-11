# Sign changes (O18)

What may change sign in recorded results, per block whose convention changed, and per model that the
migration touched. Only port variables (`<path>/<port>.e`, `.f`, and a signal that is a port variable or the
integral of one) are allowed here. Golden files and `expected.json` entries are updated only for signals on this
list, by negation. A signal that changes sign and is not a port variable is listed as a deviation, with the reason.

## WP-O2: scalar and domain libraries

### Blocks

| block | change | what changes sign in a model |
| --- | --- | --- |
| `bondgraph/Sf` | law: `p.f ~ -f` (O15: at the tail of its bond the source delivers `+f`) | A migrated model keeps every signal, except: where the bond was at the head of a 1-junction and is reversed (the reversal cancels the law change, the value is kept), `<Sf>/p.e` and `<Sf>/p.f`. Where the value is negated instead (a conforming bond, a 0-junction, an element-to-element chain), nothing changes sign. |
| `bondgraph/MSf` | law: `p.f ~ -gain * u` | As `Sf`, with `gain` in place of `f`. |
| `bondgraph/Se`, `MSe` | declared `out`, law unchanged | Where a bond at the head of a 1-junction is reversed and the value negated: `<Se>/p.e`, `<Se>/p.f`. |
| `bondgraph/C`, `I`, `R` (and the other `in` one-ports) | declared `in`, law unchanged | Where a bond at the tail of a 1-junction is reversed and the junction keeps its sign: `<X>/p.e`, `<X>/p.f`, and the element's own integral of its port flow or effort (`C/q`, `I/P`). On a 0-junction or between two elements: nothing. |
| `TF`, `MTF`, `GY`, `MGY`, `PowerSensor` | `(p1, p2) => :through` (`(a, b)` for the sensor) | A reversed bond on a 0-junction or between two elements: nothing. `PowerSensor/y` (the power) never changes sign. |
| one-terminal sensors, `Volume`, `Accumulator`, `Brake`, `HeatCapacitor`, `TemperatureSensor`, `RS` | declared `in` (`RS.heat` `out`), law unchanged | Nothing: every existing bond already conformed. |

### Models

| model(s) | how | signals that change sign |
| --- | --- | --- |
| `quarter-car` | tool: `MSeGs`, `MSeGu` reversed, gains negated | `MSeGs/p.e`, `MSeGs/p.f`, `MSeGu/p.e`, `MSeGu/p.f` |
| `inverted-pendulum-cart` | tool: `IMx` reversed (0-junction, neutral); `MTFv.p2` reversed, the `VJ` junction renamed, `MSeG` gain negated | `IMv/p.e`, `IMv/p.f`, `IMv/P`, `MSeG/p.e`, `MSeG/p.f` |
| `planar-links`, `planar-links-payload` | tool: `MSf` gains negated (O15, element-to-element chain into a `TorqueSensor`) | none |
| `industrial-servo` (5 models) | tool: `IqSrc` gain negated (O15); two-mass and full: `Kc`, `Dc` reversed. By hand (review): `Bemf` reversed and its gain negated, `QJ -> MGY.p2` reversed and the MGY modulus `WeL.k` negated | `Bemf/p.e`, `Bemf/p.f`, `MGY/p2.e`, `MGY/p2.f`; two-mass and full: `Kc/p.e`, `Kc/p.f`, `Kc/q` (binding `joint:coupling_joint` gain negated), `Dc/p.e`, `Dc/p.f`. **Deviation:** `WeL/y` and `MGY/u` (the gyrator modulus `w_e L_q`, not a port variable): reversing one bond of a gyrator negates its modulus, and there is no other place for that sign. Referenced by no check, plot or binding. |
| `f16-sim` | build script: `Retract_*` reversed (0-junction), gains `-1` (O15) | none |
| `vdp-belt` | build script: `Belt` `f = v_b` (was `-v_b`, O15) | none |
| `ball-and-plate-swing` | build script: `Shaker` (MSf) driven by `ShakerRate` with amplitude `+A W` (was `-A W`, O15) | **Deviation:** `ShakerRate/y` (a Sine source output, not a port variable) changes sign; the MSf delivers the same flow. Referenced by no check, plot or binding. |
| `wind-turbine` (5 models) | build script: `Generator` reversed, gain `-1` | `Generator/p.e`, `Generator/p.f` |
| `hybrid-powersplit` (3 models) | build script: `EngineDrag`, `SpinLoss`, `Rolling` reversed, gains negated | `EngineDrag/p.e`, `EngineDrag/p.f`, `SpinLoss/p.e`, `SpinLoss/p.f`, `Rolling/p.e`, `Rolling/p.f` |
| `maglev-train` (3 models) | build script: `Weight`, `BodyWeight` (Se) and `Load` (MSe) reversed, values negated; `Rail` (MSf) reversed, value kept (O15 cancels) | `Weight/p.e`, `Weight/p.f`, `BodyWeight/p.e`, `BodyWeight/p.f`, `Load/p.e`, `Load/p.f`, `Rail/p.e`, `Rail/p.f` (vehicle: under `ModF/`, `ModR/`) |
| `cars` (9 models) | build script: the limited-slip damper bonds now arrive at the corner's `LsdTF` (element-to-element, notation only) | none |

No `expected.json` entry, golden file, plot or dashboard card of these examples names a signal on this list, so
none was edited.

### Julia tests and fixtures

| file | change | signals that change sign |
| --- | --- | --- |
| `test/fixtures/causality/two_c_series.json` | tool: both `C -> J0` bonds reversed (0-junction, neutral) | none; the stroke ends swap (`from`/`to`) with the bonds |
| `test/fixtures/causality/r_r_loop.json` | the `R -> R` bond (O4) replaced by a 1-junction with a bond to each R | none checked |
| `golden/bondgraph/test_MSf.jl` | the `gain = -1` workaround removed (`gain = 1`) | none: `MSf1/p.f = -u` as before |
| `golden/bondgraph/test_MGY.jl`, `test_MTF.jl`, `golden/converters/test_PowerSensor.jl` (model 1), `golden/rotation/test_GearBacklash.jl`, `test_GearWithBacklash.jl`, `test_components.jl` (four rigs), `test_simulate.jl` (start-survives rig) | the driving `Sf` value negated | none |
| `golden/contact/test_RollingSphere.jl`, `tyre_rig.jl` | the `-W` / `-w_rel` workaround removed | none |
| `test_multibond_slice.jl` (ScrewTF rig) | `T.b -> Sf` reversed (`Sf` is `out`), value negated | none |
| `test_export_scope.jl` (flipped bond) | stdlib `R` behind the reversed subsystem port is E114 now (asserted); the flipped case runs on an inline `R` without orientation | none: the flow is 1.5 as before |
| `golden/converters/test_PowerSensor.jl` (model 2) | the reversed placement `R -> sensor -> junction` is E114 now; asserted as a refusal | the -12 W reading is gone with the placement |

## WP-O3a: multibond mechanics

A body is a 1-junction whose flow is the body twist (O7). Before WP-O3a the `RigidBody2D`/`3D` junction carried minus
the twist, and the blocks bonded to a body read their port with that sign. "Kept" below means the bond of a migrated
model keeps its direction (the tool's sign choice renames the body junction instead).

### Blocks

| block | change | what changes sign in a model |
| --- | --- | --- |
| the 21 joints (`spatial/` `Free3D`, `Revolute3D*` (5), `Prismatic3D*` (4), `Cylindrical3D`, `Helical3D`, `Planar3D`, `Spherical3D`, `Universal3D`; `multibond/Revolute2D`; `planar/Prismatic2D`, `Revolute2DCompliant`, `Revolute2DFriction`, `Revolute2DLimit`; `contact/SwitchedPivot3D`) | law on the child side: `V_c = -child.f`, `W_c = -child.e`; `parent => :in`, `child => :out`, drives `in` | `<Joint>/child.e`, `<Joint>/child.f` (kept bond). The joint's own variables (`q`, `qdot`, `Vrel`, `d`, the pose, `drive.e`, `drive.f`, `parent.*`) keep their sign. |
| `planar/Revolute2DRigid` | internal `axis -> rate.p` reversed (the `Df` is `in`) | `<Joint>/drive.f` is now `+qdot` (was `-qdot`): a torque source on `drive` acts with the opposite sign, so a model negates its value to keep its motion, and then `<Joint>/drive.e` changes sign. `<Joint>/child.*` as for the other joints. No example uses the joint; the tool reports it as `review`. |
| `contact/ContactPoint`, `MovingPlaneContact` (`p`), `RollingDisk`, `Tyre` (`p`), `RollingSphere`, `SuctionCup` (`a`, `b`) | law: port flow = the body (point) twist, port effort = minus the wrench on the body (was the negatives) | `<Contact>/p.e`, `<Contact>/p.f` (`a.*`, `b.*`), kept bond. The contact's own variables (penetration, normal force, slip, the cup's chamber and lip states) and `p.P` keep their sign. `MovingPlaneContact.j`, `Tyre.spin`, `SuctionCup.vac`: unchanged. |
| `spatial/Rotor3D` | law: `p.f` = carrier twist, `p.e` = minus the wrench on the carrier; `drive.f ~ h/Ja - p.f[3]`, `p.e[3] ~ drive.e` | `<Rotor>/p.e`, `<Rotor>/p.f`. `h`, `w_rel`, `w_abs`, `H`, `Ek`, `drive.*` keep their sign. |
| `multibond/GravityPlanar`, `GravitySpatial` | declared `out`; law: `p.e` = the gravity wrench (was its negative) | `<Gravity>/p.e`, and `<Gravity>/p.f` where the bond is kept (the junction is renamed). |
| `multibond/ExternalWrenchPlanar`, `ExternalWrenchSpatial` | declared `out`; law: `p.e` = the input wrench (was its negative) | `<Wrench>/p.e`, `<Wrench>/p.f` (kept bond). |
| `multibond/SfPlanar`, `SfSpatial`, `MSfPlanar` | declared `out`; law: `p.f ~ -u` (O15 for the planar/spatial flow sources) | `<Sf>/p.f` (and `p.e`) on a conforming bond with the input unchanged; a model that negates the input keeps every signal. |
| `multibond/SePlanar`, `SeSpatial`, `MSePlanar`, `GroundPlanar`, `GroundSpatial` | declared `out`, law unchanged | Where the body junction is renamed: `<Se>/p.e`, `<Se>/p.f`, and the input must be negated to keep the motion (signal input: the tool reports `review`). |
| `multibond/IPlanar`, `ISpatial`, `CoriolisPlanar`, `CoriolisSpatial`, `CPlanar`, `CSpatial`, `RPlanar`, `RSpatial`, `DePlanar`, `DeSpatial`, `DfPlanar`, `DfSpatial` | declared `in`, law unchanged | Where a bond at the tail of the body junction is reversed and the junction keeps its sign: `<X>/p.e`, `<X>/p.f`, and the element's own odd variables (`I*/P`, `Pm`, `C*/q*`, `D*/y`). Where the junction is renamed instead (every element of a hand-built `RigidBody3D`-style body reversed together): nothing. |
| the `through` transforms (`TF*`, `MTF*`, `GY*`, `MGY*`, `ScrewTF`, `TFAd*`, `FixedTransform*`, `JointTransform*`, `planar/FixedJoint2D`) | `(a, b) => :through` (FixedJoint2D `(parent, child)`), law unchanged | As the chain they sit on (a mount between a body and a contact carries the contact's sign change: `<Mount>/a.*`, `b.*`). |
| `spatial/RigidBody3D`, `planar/RigidBody2D` (and `planar/Free2D`) | rebuilt: `node -> inertia.p`, `node -> coriolis.p`, `node -> flow.p`, `gravity.p -> node`; the junction flow is the body twist | Internal: `Body/gravity/p.e`, `Body/gravity/p.f` (`Body/body/gravity/p.*` in `Free2D`). `Body/inertia/*`, `Body/coriolis/*`, `Body/flow/*`, `V`, `P` keep their sign. A composite face is not a recorded signal. |
| `contact/ImpactBody3D` | rebuilt as `RigidBody3D` (`node -> inertia/coriolis/flow`) | Internal: `Body/gravity/p.*`, `Body/mount/a.*`, `Body/mount/b.*`; the face `p` behaves like a contact port (its attached joint child keeps its bond). |
| `planar/PinNode2D`, `Bar2D`, `FlexibleBeam2D`, `spatial/FlexibleBeam3D`, `ModalBody3D` | rebuilt: each node junction bonds into the element (`node -> mass.p`, `nodeA -> bar.pa`, `nodeX -> beam.pX`, `nodeX -> core.pX`) | Internal: nothing (every element at a node was reversed together). The node junction flow is now the node twist, so the blocks attached from outside follow the rows above. |
| `planar/AxialBar2D`, `ModalBeam2D`, `PointMass2D`, `DeckContact2D`, `spatial/ModalBeam3D`, `ModalBodyCore3D`, `contact/ImpactInertia3D` | declared `in`, law unchanged | Where a bond is reversed at a 1-junction that keeps its sign: the block's port variables (not odd: the tool reports `review`). |

### Models

No example was migrated in WP-O3a (WP-O3b and WP-O3c). The 2D and 3D examples do not compile until then; the list is
in the WP-O3a report.

### Julia tests and fixtures

"Rig" means the bond directions of a test model changed (reversed bonds, or a junction added between two fixed ends);
it changes no expectation unless a signal is named.

| file | change | signals that change sign (expectation negated) |
| --- | --- | --- |
| `test/fixtures/multibond/pendulum.json` | `Body` (IPlanar) and `Coriolis` bonds reversed (junction -> element) | none |
| `test_multibond_slice.jl` | rigs: free-body Coriolis, De/Df sensors, GroundPlanar + SePlanar on a 0-junction (was a direct `out`-`out` bond), TFAd/FixedTransform and ScrewTF `b` side on a 0-junction with the flow source | `C/p.f` of the Coriolis identity (`SfPlanar` law, now `+V`); `D/y` of the DfPlanar sensor (`SfPlanar` law, now `+V`); `W/p.e` of GravityPlanar (law, now the physical wrench) |
| `test_planar_primitives.jl` | rigs: TF/MTF/matrix-TF `b` and the flow source on a 1-junction (`b.f = -F` kept), GY/MGY loads reversed, ExternalWrench/TFAd/Coriolis/closed-graph inertias, C, R and TF `a` reversed (junction -> element) | `R/p.f` (`SfPlanar` law, now `+v`); `S/p.f`, `D/y` of MSfPlanar (law); `E/p.e`, `D/y` of ExternalWrenchPlanar (law); `I/P` of the TFAd run (its bond reversed on a 1-junction that keeps its sign: the start is `-P0` and the test reads `-I/P`). Closed bond graph: the junction power sum and the supplied energy are written with the new bond directions (the source now pushes `+u` into the body; no value of the old run is compared) |
| `test_planar_mechanics.jl` | rigs: prismatic drive and spring, 2-link chain and elbow parents reversed | `Joint/child.e` (pivot-offset case; joint child law). The dummy-derivative name `Body/flow/p.f[1]` is now `Body/coriolis/p.f[1]` (an alias choice after the RigidBody2D rebuild, not a sign) |
| `test_mech_planar.jl` | rigs: double-pendulum parent, prismatic drive/spring/force reversed; the rotating-parent prismatic's flow source and the joint child meet on a 1-junction | none (the same dummy-derivative name change) |
| `test_spatial_slice.jl` | rigs as the planar file | `Cor/p.f`, `C/p.f`, `C/p.e` (`SfSpatial` law); `W/p.e` (ExternalWrenchSpatial law); `G/p.e` (GravitySpatial law) |
| `test_mech_spatial.jl` (helpers for `test_rigid_spatial.jl`, `test_joint_stops.jl`) | rigs: the kinematic joint rig's child meets the flow source on a 0-junction; the double pendulum's `T2.b`, the prismatic drive/spring/force reversed; the parent `SfSpatial` input negated (O15) | none |
| `test/fixtures/joint_stops/Revolute2DBefore.jl`, `Revolute3DBefore.jl` | the frozen pre-stop joints re-based on the WP-O3a child law (bit-identity tests against the library's no-stop branch) | none |
| `test_contact.jl` | new testset "WP-O3a: one bond direction for every attachment to a body" | none |
| `test_fem_rail.jl` | rig: `Body.E -> Guide.parent`; the slide spring and damper bonded from the face `S` (an `any` translation port: kept direction would read minus the slide rate) | none |
| `test_truss.jl` | rig: `Body.p -> Contact.p` (DeckContact2D is `in`) | none |
| `golden/contact/test_MovingPlaneContact.jl` | none | `Belt/p.f[2]` (contact law: the port flow is the point twist) |
| `golden/contact/test_RollingSphere.jl` | rig: `Lock -> Bearing.drive` | none |
| `golden/contact/fixtures/library/SuctionCupLinear.jl` | the frozen linear cup re-based on the contact law (flows and efforts negated, `@orientation` added), so the comparison with the stdlib cup is like for like | none |
| `golden/spatial/jmb10_arm.jl`, `test_floating_base.jl` | rig: the parent junction bonds into the joint mount `T.b` | none |
| `src/library/chain_loader.jl` (`load_chain`, used by `test_loader.jl`) | the parent body junction bonds into the joint mount `J_t.b` | none |
