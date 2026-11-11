# Choices WP-O3d made (O22)

## Compiler

- **Where.** `check_orientations!` (`src/compile/connect.jl`): before the direction check, every end of a valid bond
  that resolves to a power port of a block (`ep.kind == :power`: a leaf, inline or project block, including the leaf
  behind a JSON subsystem port or a textual-composite face) is looked up in that block's `@orientation` entries. A
  port named in none is E114 on its own (`_undeclared_diag!`), reported where every E114 is reported (the block node,
  the subsystem or composite node the user sees for a face, the `connect` line for a composite-internal bond).
- **Judged at the leaf.** An orientation a composite declares on its face does not stand in for an undeclared leaf
  port behind it: the leaf block is the one whose law assumes a direction. A composite face that is a junction inside
  resolves to a junction end and needs nothing (unchanged).
- **One diagnostic per bond end.** The undeclared end is dropped from the direction and `through` checks, so it gets
  exactly one E114; the other end is still checked (an undeclared end and a violated declared end give two E114, one
  each). The bond stays valid in the model, so nothing cascades into E101, E103 or causality (as all E114).
- **Text.** Message: "bond `c2` reaches `Fric.p`, but `Fric.p` declares no orientation: add `@orientation p => :in`,
  `:out` or a `(a, b) => :through` pair to the block `project:BeltFriction`" (with "(exposed as `q` of `Sub`)" after
  the leaf when the end is reached through a face). Hint: "a bond needs a declared orientation at every end that is not
  a junction: `in` when the block's law assumes the bond arrives at the port (storage, dissipation, contacts, sensors),
  `out` when it assumes the bond leaves (sources), `through` for the two sides of a pass-through two-port".

## Declarations (no bond reversed, no law of an example changed)

Every bonded undeclared port already had the bond direction its law assumes, so each block was declared by the rules
and the models did not change (no generator rerun, nothing migrated):

- **stdlib:** `contact/ImpactBody3D` `p => :in`. Its face is not a junction: it is `mount.a` of a `through` mount whose
  `b` leaves into the body junction, so a bond at `p` must already arrive (a joint's `child -> p`); the declaration
  makes the catalog and the editor say so. The other stdlib blocks with an undeclared port are composites whose faces
  are junctions inside: `RigidBody2D/3D.p`, `Free2D.p` (through `RigidBody2D`), `PinNode2D.p`, `Bar2D.a/b`,
  `FlexibleBeam2D/3D.A/B`, `ModalBody3D.A..E/S`, `Revolute2DRigid.parent/drive` (its `child` was already `out`).
  No stdlib leaf block has an undeclared power port.
- **project libraries:** `FlowSensor` (six copies: debug-tour, drivetrain-kalman, drivetrain-position,
  industrial-servo, inverted-pendulum-cart, quarter-car) `p => :in` (a flow detector); `panda-3d` `GazFriction` (R)
  and `RotorInertia` (I) `in`; `cantilever-sections` `ModalCantilever.tip` `in` (a modal storage field loaded by an
  `MSe`); `robot-arm-3d` `ArmDynamics3R.j1..j3` `in` (an IC field driven by the joint sources); `van-der-pol`
  `BeltFriction`, `StribeckFriction`, `TunnelDiode` `in` (nonlinear R); `drivetrain-kalman` `MotorGY`
  `(a, b) => :through` (the stdlib `GY` law), `LossyGear`, `GearBacklash` and the composite `GearWithBacklash` `a`, `b`
  `in` (iconic Rotation two-terminals, O20; the composite's faces as WP-O3a2 did for the stdlib composites);
  `quarter-car` `OneSidedSpring.a/b` `in` (an iconic spring). Not bonded anywhere, declared so the editor can bond
  them: `cube-3d` `CornerCube.m1..m3` and `reaction-wheel-1d` `InvertedPendulumBody.a/b` `in` (iconic, O20).
- **inline blocks (contract fixtures):** `GroundPlanar`/`GroundSpatial` `p => :out` (a zero flow source),
  `BodyPlanar`/`BodySpatial`/`ZeroMassBody` `p => :in`, `FixedTransform2D`/`FixedTransform3D` `(a, b) => :through`, in
  `model.planar.multibond`, `model.spatial.multibond`, `model.frame-bridge`, `model.scene-exaggeration`,
  `model.planar-size-four`, `model.scene-bad-exaggeration`, `model.e007-frame-mismatch`, `model.e108-invalid-inertia`.
  **Law changed:** the inline `FixedTransform2D` of `model.planar.multibond` and `model.frame-bridge` was written as
  `a.f = Ad(g) b.f`: with `a` arriving and `b` leaving it gave the body minus the frame's twist (the pre-O7 form). It is
  now `a.f = -Ad(g) b.f` (the into-block form of the stdlib transform and of the fixtures' own `FixedTransform3D`);
  `b.e = Ad^T a.e` is unchanged. Both fixtures hold the transform's `a` side on a ground, so every flow is zero and no
  value changes.

## Editor

- `undeclared` is a fifth `PortOrientation` kind (`web/src/editor/portOrientation.ts`). `allowedRoles` gives it no
  role; `orientBond` refuses a bond with it first, with the reason "`X.p` declares no orientation: add `@orientation` to
  the block" (one clause per undeclared end); `checkReverse` refuses with the same reason. The tooltip reads
  "orientation not declared", the inspector's port row "orientation" + "not declared: add `@orientation` to the block
  before bonding this port"; `data-orientation="undeclared"`.
- **Composite faces stay free.** The catalog does not say which face of a textual composite is a junction inside, so
  an undeclared power port of a catalog block whose source has `@components` (or an inline block whose source has
  one) is `any`, as before; the compiler judges a bond there at the port inside. Without this, `RigidBody2D/3D.p` and
  the other junction-faced composites could not be bonded in the editor. A subsystem port forwards `undeclared` from
  the port it exposes, as it forwards `in`/`out`.
- `suggestTargets` now carries the candidate's orientation into its descriptor, so the quick-connect suggestions are
  ones the bond rules accept (`target-suggestions.test.ts` found a suggestion the real check refused).
- The tests keep the contract catalog's orientations (`catalog.min.json` declares all its blocks) instead of
  overriding them; De is stripped to test an undeclared leaf, and a small composite `Face` stands for a junction face.

## Export scope adapter

- `scope_document` (`src/export/scope.jl`) replaces the outside of a scoped subsystem with an inline
  `ScopeAdapter_<domain>_<e|f>` bonded to each power port. Its port now declares the end it takes (O22): `in` when the
  original outside bond left the subsystem (the adapter takes the head), `out` otherwise. Its law is in port-variable
  form and holds at either end, so no value changes; `test_export_scope.jl`'s flipped case now uses an inline `R`
  declared `out` (it was undeclared, which O22 refuses), so both adapter orientations stay covered.

## Julia test rigs

Inline rig blocks with a bonded undeclared power port were declared by the same rules, with the bond each rig already
had: `test_frames.jl` (sinks `in`, grounds `out`, pass-through transforms `through`, whose law became the into-block
`a.f[k] ~ -b.f[k]`; the tests compare frames and diagnostics, not those flows), `test_units_multibond.jl` (grounds and
drives `out`, sinks and inertias `in`), `test_planar_primitives.jl` (the `JointTransform2D` bridge rig: the effort
source `out`, the flow source at the bond's head `in`), the project rig library under `test/fixtures/components/`
(`GearBacklash`, `GearWithBacklash`, `LossyGear`, `DCMotorFlat`, `in`), and the O22 rigs of `test_flatten.jl`.
`test_components.jl` expects the `@orientation` scope in the composite's scope list.

`test_units_model.jl` failed before this WP (WP-O3a2 made `electrical/Ground`, `translation/Fixed` and
`rotation/FixedShaft` `in`, and its rig bonded them out of a junction): the rig's bond now runs from the junction to
the fixed element. The test checks units only.

## Contract and tool

- `catalog.schema.json`: the `orientation` description no longer says an unnamed port is `any`; types regenerated
  (`tools/gen_contracts.py`), shape unchanged.
- `tools/migrate_bond_orientation.py` was not changed (no model needed migration); the stale "W218 check" docstring in
  its tests was reworded.
