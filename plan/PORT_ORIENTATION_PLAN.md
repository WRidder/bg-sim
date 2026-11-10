# Port orientation: one bond-direction rule, enforced

Status: planned (branch `port-orientation`). No backward compatibility: existing models are
migrated or regenerated, and nothing keeps the old behaviour.

## Why

Bond direction is semantic. Port variables count power positive into their block, and a bond from
X to Y gives `Y.f = f_b`, `X.f = -f_b`. On a 1-junction a port at the head of the arrow sees
`f = f_J`, a port at the tail sees `f = -f_J`, and its effort enters the sum with the opposite sign.
Reversing one bond on a 1-junction therefore negates both the flow and the effort of that port.

Nothing tells the user which direction a block expects, and the stdlib does not agree with itself:

- `RigidBody3D` bonds its inertia *into* its junction (`inertia.p -> node`), so the junction flow is
  the negated twist. Wrench sources, gravity, `DfSpatial` and `Free3D` are bonded the same way as
  the inertia; the contact blocks (`ContactPoint`, `MovingPlaneContact`, `RollingDisk`, `Tyre`,
  `RollingSphere`, `SuctionCup`) are written for the negated twist and are bonded the other way.
- A hand-built body that bonds its inertia the textbook way (junction into inertia) needs every
  attachment reversed relative to the `RigidBody3D` pattern.

Four of the six example agents of branch `new-example-models` lost time to this (lunar-module:
the vehicle fell through the ground; ingenuity: negated thrust; rocket: position integrated `-v`;
maglev-train). Evidence, with a 2 kg body built three ways:

| Case | Correct direction | Reversed bond |
| --- | --- | --- |
| Free fall, z after 1 s | -4.805 m | +5.005 m |
| 0.1 m drop onto a `ContactPoint` | rests at -1.6 mm | falls through |
| 30 N thrust through a mount | +2.695 m | -12.305 m |

An interim warning (W218, a lookup table of known 3D blocks) exists on the side branch
`w218-interim`. It is a stop gap and is **not** merged; this plan replaces it. Its reproduction rig
and its regression tests are reused.

## Decisions

| # | Decision | Why |
| --- | --- | --- |
| O1 | The sign rule of bonds stays as it is (head `f = f_b`, tail `f = -f_b`; the half arrow is the positive power direction). | It is the orthodox bond-graph meaning of the half arrow. Making junctions ignore direction (Modelica style) would remove the pitfall too, but the arrow would stop meaning anything. |
| O2 | A power port declares its **orientation**: `in` (a bond ends here, the arrow points into the block), `out` (a bond starts here) or `any` (default). Block language: a new scope `@orientation`, written like `@causality`: `@orientation p => :in`, `@orientation begin a => :in; b => :out end`. | The direction a block's equations assume is a property of the block, so the block states it. This is 20-sim's port orientation (fixed in / fixed out / any). |
| O3 | Enforcement in the compiler: a bond whose end at an `in` port is not its head, or whose end at an `out` port is not its tail, is an **error** (new code, the next free `E1xx`; the message names the bond, the port, the declared orientation and says "reverse this bond"). Composite `@connections` are checked the same way (`connect(a, b)` runs from `a` to `b`). Wires (`kind: "wire"`) and signals have no direction and are not checked. | An error cannot be ignored and needs no lookup table. It covers scalar, planar and spatial blocks alike. |
| O4 | Two fixed ports can only be bonded `out -> in`. `in`-`in` and `out`-`out` bonds are the same error, with the hint "put a junction in between". | Two passive one-ports head to head have no consistent direction. |
| O5 | Catalog contract: `portDecl` gets `orientation: "in" \| "out" \| "any"` (required, so every language has it). TypeScript, Python and Julia shapes change together; fixtures are updated. | `contracts/` is the single source of truth. |
| O6 | Stdlib convention, every domain: **storage, dissipation, fields, contacts, detectors and sensors are `in`; sources are `out`; two-ports (`TF`, `GY`, `MTF`, `MGY`, the fixed and moving transforms, joints, converters between domains) are `a => :in`, `b => :out`**, power flowing through from `a` to `b`. Multiport fields between two bodies (`RollingSphere`, `SuctionCup`, `MovingPlaneContact`, two-sided spring-dampers used with bonds) have all ports `in`. A composite port that *is* a junction stays `any`. Iconic components that are meant for wires only stay `any`. WP-O0 produces the full table, block by block, before any block is changed. | One rule a user can remember, equal to the textbook drawing: sources point at the junction, elements are pointed at. |
| O7 | Mechanics sign rule: with the declared orientations, **every block attached to a body sees the body's true twist `V` at its port, and applies the wrench its header documents**. The contact blocks lose their negated-twist convention. `RigidBody2D`/`RigidBody3D` are rebuilt with textbook internals (`node -> inertia.p`, `node -> coriolis.p`, `gravity.p -> node`, `node -> flow.p`), so the junction flow is `V` and a hand-built body behaves exactly like the library body. Mounts pass the sign straight through. | This is the unification. With O3 a wrong direction cannot be drawn, and with O7 the right direction is the same for every block. |
| O8 | Editor: a new bond is oriented from the ports' orientations whichever end the user starts at; a bond between two fixed ports of the same kind is refused with the O4 hint; "reverse bond" is disabled when an end is fixed, with a tooltip that says why; the port tooltip and the block inspector show the orientation. Junction-to-junction bonds keep a free direction (reversing one negates only that bond's own variables, never the model). | The error of O3 should be hard to reach from the editor. |
| O9 | Migration, once: `tools/migrate_bond_orientation.py` reads the catalog and a model, reverses every bond that violates O3 and reports each reversal with its class: **neutral** (an odd-symmetric one-port: linear `I`, `C`, `R`; reversing changes nothing), **source** (the value must be negated to keep the model: the tool negates the parameter expression and says so) or **review** (an asymmetric law or a block whose law changed under O7: a person decides). Examples with a `design/build_model.py` are fixed in the script and regenerated, not migrated. | No stop gap in the models either: after migration no model relies on a reversed bond. |
| O10 | Acceptance is the existing evidence: every `expected.json` check, the Julia suite, the web and backend suites, with **no tolerance widened**. A check that fails after migration means the migration of that model is wrong. | The checks compare against independent references, so they are the safety net for a change of this size. |
| O11 | W218 is not introduced on this branch. The manual gets one section "Bond direction and port orientation" that states O1, O2, O6 and O7; the stdlib block headers state their orientation only through `@orientation` (no prose that can go stale). | One rule, one place. |
| O12 | The workarounds of the new examples are removed: lunar-module, ingenuity and rocket bond their attachments the uniform way; the README notes about bond direction go. | They exist only because of the inconsistency. |

Amendments after the WP-O0 inventory (findings F1 to F7 at the end). They override the rows above where they differ.

| # | Decision | Why |
| --- | --- | --- |
| O13 | A fourth orientation, a **relation**: `@orientation (a, b) => :through`. Exactly one of the two bonds arrives and the other leaves; which one is free. It applies to the pass-through two-ports: `TF`, `GY`, `MTF`, `MGY`, `TFAd`, `TFAdNeutral`, `FixedTransform2D/3D/3DNeutral`, `JointTransform2D/3D`, `FixedJoint2D`, `PowerSensor`. Their laws are symmetric in the into-block form, so they work either way round. This replaces "`a => :in`, `b => :out`" of O6 for these blocks. Joints and `Free3D` are not pass-through: `parent => :in`, `child => :out`, `drive => :in` (open point 2). Catalog (replaces O5's per-port field): the block gets `orientation: [{ ports: [...], kind: "in" \| "out" \| "through" }]`, shaped like `causality`; a port in no entry is `any`. | F1: a mount's `a` side carries a contact, sensor or joint parent, all `in`; a fixed `a in` gives 959 in-in errors in the examples that no reversal can fix. The check stays local: the two bonds of a `through` pair must have opposite directions. |
| O14 | Bonds between two junctions are never checked. A 1-1 or 0-0 bond is neutral. A **0-1 bond is semantic and stays free**: it sets the reference direction of everything behind it (the sign of a relative velocity, of a spring's displacement), which is the modeller's choice in any bond graph. The editor allows reversing it and says what it does ("reverses the reference direction of the sub-graph behind this bond"); it never calls it harmless. O8's last sentence is withdrawn. | F3. Fixing 0-1 bonds to one direction would take away a legitimate choice and protect nothing: no block's equations assume it. |
| O15 | "Sources are `out`" means the bond-graph sources (`Se`, `Sf`, `MSe`, `MSf` and their planar and spatial forms, gravity, external wrench). **Flow sources are corrected** so that at the tail they impose `+f` on the junction (today `Sf` at the tail injects `-f`). Iconic sources (`Fixed`, `Ground`, `SpeedSource`, `Tank`, `PressureSource`, the thermal sources) are wire components and stay `any`, like all iconic ports. | F4. |
| O16 | Joint drive ports are `in`. A dissipator on a drive goes through a 1-junction (`drive <- 1 -> R`), as any element-to-element connection does under O4. lunar-module and rocket get that junction. | F5: orthodox, and it is where a motor and the friction of the same axis meet anyway. |
| O17 | Project library blocks follow O6, O7 and O13 like the stdlib. `cars`' `Strut` exposes the true suspension rate on its junction port (today it documents `j.f = -dx/dt`). The silent odd chains of flex-torsion and flex-rotary-pendulum are checked against an independent reference in WP-O3c; a real sign error found there is fixed, not preserved. | F6. |
| O18 | What may change in recorded results: **only the sign of port variables (`p.e`, `p.f`, and signals defined as a port variable) of blocks whose convention changes**, listed per block in `plan/wps/port-orientation/sign-changes.md` by the package that changes them. Golden files and `expected.json` entries are updated only for signals on that list, by negation, never by re-recording. Positions, twists `V`, states and every physical output stay bit-comparable within the existing tolerances (O10). | 53 Julia test files name a block whose law changes. Without a closed list, "update the goldens" would hide real regressions. |
| O19 | O9's migration tool is junction-aware: it works per 1-junction cluster, follows element-to-element bonds and `through` pairs, also handles conforming bonds of blocks whose law changed, and negates the start values and the listed signal references (plots, bindings, dashboards, checks) of odd elements on a reversed chain. | F2: classifying by block kind alone gives 471 review cases; junction-aware classification gives 36. |

Choices WP-O1 made where the decisions above leave room:

- **O2/O13, syntax.** One scope, `@orientation`, holds all three kinds; the relation is not a separate
  scope. Entries are `p => :in`, `p => :out`, `(a, b) => :through`, single-line or in `begin ... end`.
  `:any` is not written (E001: a port named in no entry is `any`). Shape errors are E001 (no `=>`, a value
  that is not a symbol, an unknown kind, `:in`/`:out` on a tuple, a `:through` entry with other than two
  ports or the same port twice); name errors are E003 (an unknown name, a signal port or other
  declaration, a port named in two entries, also across a single entry and a `through` pair). A textual
  composite may declare `@orientation` for its own ports. Accessors: `orientation(pb)`,
  `port_orientation(pb, port) -> :in | :out | :through | :any`, `orientation_ports`, `orientation_kind`
  on `OrientationDecl`.
- **O13, catalog.** `orientation: [{ "ports": [...], "kind": "in" | "out" | "through" }]` on `catalogBlock`
  and `blockInterface`, required, right after `causality`; `ports` has one or two unique names
  (`orientationDecl` in `catalog.schema.json`).
- **O3, code and messages.** The code is **E114** (E106 to E113 are taken or retired: E107 became W205). It
  is an error and the bond stays in the model, so it does not cascade into E101/E103/E106. One E114 per
  violating bond: "bond `c2` runs from `p` of `C1` to junction `J1`, but `p` of `C1` is declared `in`: a
  bond must end at an `in` port", hint "reverse bond `c2`, so that it runs from ...". O4: "bond `c1` joins
  two `in` ports, ...: no direction of the bond satisfies both", hint "put a junction in between, ...".
  O13: "bond `c2` and bond `c3` both arrive at `TF1` at `a` and `b`, ...", hint naming the bond whose other
  end is free to reverse, or a junction when neither is.
- **O3, where and how.** `check_orientations!` in `src/compile/connect.jl`, run in `classify_connections!`
  after the port-conflict check, on the valid bonds of the flattened connection list. An end is checked
  against the leaf port it resolves to and against every textual-composite face it passes (the face chain
  of `_bind_boundary!`); JSON subsystem ports carry no orientation of their own. A bond reaching a face is
  reported on the subsystem/composite node; a composite-internal bond is reported on the composite node
  with `scope: "@connections"`, the composite's ref and the `connect` line as `source`, and its message
  and hint spell the `connect(a, b)`.

Open points, decided in the work package that meets them and recorded here:

- **Two-terminal iconic sensors** (decided in WP-O0): they **stay `any`**.
  - Only two of them are ever bonded, and in both cases the direction is irrelevant:
    - the hydraulic `FlowSensor.b` goes to a 0-junction (4 bonds);
    - `TorqueSensor` in planar-links sits as a through element between an `Sf` and a 1-junction (9 bonds). Its `a`
      and `b` are interchangeable, because it is a wire-law pass-through.
  - Declaring them `in` would add review cases without protecting anything.
  - The **one-terminal** iconic sensors (`SpeedSensor`, `AngleSensor`, `PositionSensor`, `VelocitySensor`,
    `AccelerationSensor`, `PressureSensor`, `TemperatureSensor`) are detectors and become `in`. All 74 of their
    existing bonds already run junction -> sensor.
- **Joints and `Free3D`** (decided in WP-O0): **`parent => :in`, `child => :out`**, with a sign change on the child
  side of every joint: negate `child.f` in the relative twist and `child.e` in the transmitted wrench.
  - In the examples, `parent` is at the head in 408 of 417 bonds and `child` at the tail in 412 of 417. A ground
    (`out`) -> parent conforms.
  - The child edit is exactly what the O7 body rebuild needs on that side, so for the joints the migration is
    neutral.
  - "Both `in`" would make 421 child bonds violate. It also cannot work for `FixedJoint2D` and `Revolute2DRigid`,
    whose child side is a mount's `b`.
  - The joint `drive` ports are `in`. They are already right for all 26 stdlib drive ports.
  - `Free2D` is not a joint: it is a one-port floating body whose face is a junction, so it is `any`.
- Further open points raised by WP-O0 are in "Findings from WP-O0" at the end (A1 is a prerequisite of WP-O1's
  enforcement).

## Work packages

Each package ends with its targeted tests green and a local commit on `port-orientation`. Packages
run in the order given unless marked parallel. Nobody pushes.

### WP-O0: inventory and orientation table (Opus)

No behaviour change. Deliverables, all under `plan/wps/port-orientation/`:

- `orientation-table.md`: every stdlib block with a power port (about 205: bondgraph 15, contact 10,
  converters 23, drives 4, electrical 18, hydraulic 12, motion 2, multibond 44, planar 15, rotation 18,
  spatial 21, thermal 14, translation 9), its ports, the orientation by O6, and for each block whether its
  equations already match that orientation or must change (O7), with the reason.
- `composites.md`: every composite (`@components`/`@connections`, 17 files) with the direction of each
  internal bond today and after O6/O7.
- `violations.md`: a count, per example, per Julia test file and per contract fixture, of the bonds that
  would violate O3 under the table (a throwaway script in the scratch folder applies the table to the
  flattened connection lists; it is not committed).
- A decision on each open point above, written back into this file.

### WP-O1: language, compiler, contract (Opus)

- `@orientation` scope: parser (`src/syntax/parse.jl`, `ast.jl`, scopes, whitelist), accessors, E001/E003
  for bad entries (unknown port, a signal port, an unknown symbol, a port named twice), including the
  `(a, b) => :through` relation (O13).
- Catalog: the block-level `orientation` list of O13 in `contracts/schemas/catalog.schema.json`
  (`catalogBlock` and `blockInterface`), fixtures, the Julia catalog writer, the Python and TypeScript types
  and their contract tests.
- Enforcement (O3, O4, O13; junction-to-junction bonds untouched, O14) in `src/compile/connect.jl` next to the bond lowering, for diagram bonds, subsystem
  ports and composite connections; the new error code in the spec's diagnostics table, the diagnostic
  fixture, `web/src/manual/pages/09-diagnostics.md`, and the code lists of `web/tests/contracts.test.ts` and
  `backend/tests/test_contracts.py`; `web/tests/diagnostics-panel.test.tsx` counts updated.
- Tests in `test_syntax.jl`, `test_library.jl`, `test_flatten.jl`: each orientation, each violation, composite
  and subsystem cases, wires untouched. No stdlib block declares an orientation yet, so every existing
  model still compiles unchanged.

### WP-O2: scalar and domain libraries (Opus)

- Declare orientations by the WP-O0 table in `bondgraph/`, `converters/`, `drives/`, `thermal/`,
  `hydraulic/`, `rotation/`, `translation/`, `electrical/`, `motion/`; fix the internal bonds of their
  composites.
- `tools/migrate_bond_orientation.py` (O9), with tests on small fixture models for the three classes.
- Fix the Julia tests and fixtures that violate; migrate or regenerate the scalar examples; every touched
  example passes `uv run examples/run_checks.py --only <name>` with unchanged tolerances.

### WP-O3: multibond mechanics (Opus), in three packages

**WP-O3a: library and tests.**
- O7 in `multibond/`, `planar/`, `spatial/`, `contact/`: rebuild `RigidBody2D`/`RigidBody3D` and the other
  composites (`composites.md`), rewrite the contact blocks and `Rotor3D` for the true twist, change the child
  side of the joints, the gravity and external-wrench blocks and the planar and spatial flow sources, and
  declare every orientation (`orientation-table.md`, O13, O16).
- A test that builds the body three ways (library body, hand-built junction, hand-built junction through a
  mount) and checks the three cases of the evidence table, plus the O3 error for each reversed bond (the rig
  and tests of `w218-interim` are the starting point).
- The Julia tests and goldens, under O18: `sign-changes.md` is written first.
- After this package the 2D/3D examples do not compile until O3b and O3c; that is expected.

**WP-O3b: examples with a build script.** Fix `design/build_model.py` and the project library blocks
(O17), regenerate, 2D first. Order: the all-neutral examples with strong checks, then the source examples, then
lunar-module, ingenuity and rocket with their workarounds removed (O12, O16), then cars.

**WP-O3c: examples without a build script.** The generator-built JSON (fanuc-pick, humanoid-dual-arm,
panda-3d) through its generator, the hand-written JSON through the migration tool (O19); flex-torsion,
flex-rotary-pendulum and the two models without a numeric check (`pendulum-double-cart(-lab)/*-plant`) get a
before/after signal comparison. Then the FMU exports and web games: rerun the `examples/export_*` checks
that involve changed blocks.

Every example passes `uv run examples/run_checks.py --only <name>` with unchanged tolerances (O10, O18).

### WP-O4: editor (Sonnet; parallel with WP-O2 and WP-O3, after WP-O1)

- O8 in `web/src/editor/` (`Canvas.tsx`, `connectionRules.ts`, `connectionAnalysis.ts`, `edges/`,
  `subsystemPorts.ts`) and `web/src/inspector/ConnectionInspector.tsx`; clipboard and paste keep directions.
- Vitest tests for auto-orientation from either end, the refused `in`-`in`/`out`-`out` bond, the disabled
  reverse action, and subsystem ports that forward an orientation.
- Works only in `web/`; reads the catalog field from WP-O1.

### WP-O5: spec, manual, docs (Sonnet; after WP-O3)

- Spec: the "Bond direction" rule rewritten for O1, O2, O6, O7; the `@orientation` scope in the block
  language chapter; the error code.
- Manual: the section of O11 in `03-building-models.md`, the block-authoring page for `@orientation`, the
  contact section of `14-mechanical-electrical.md`; `julia/BGSim/NOTES.md`; `plan/MULTIBOND_PLAN.md` where
  it describes the body internals; the `new-example-model` skill (one line: orientation is enforced).
- Example docs: rebuild the docs of every example whose diagram changed
  (`uv run tools/example_docs/build.py --only <name>`), and its thumbnail if the diagram is in the shot.

### WP-O6: integration (orchestrator)

- Full Julia suite, full web and backend suites, `uv run examples/run_checks.py` for all examples, the
  export checks, `npm run build` in `web/`.
- Review of the diff per package before its commit; merge of `port-orientation` into `master` locally.

## Risks

- **Scale of the model churn.** 234 example models, 17 contract fixtures and the Julia test rigs carry bond
  directions. WP-O0's violation count decides whether WP-O2 and WP-O3 are split further.
- **Silent sign changes during migration.** Mitigated by O9's classes and O10: sources are negated
  explicitly, asymmetric elements are reviewed by hand, and the independent checks must pass unchanged.
- **Examples without checks.** A model with no `expected.json` check has no safety net; WP-O0 lists them,
  and each gets at least a before/after `compare_signals` run in its package.
- **Parallel work in one tree.** WP-O4 touches only `web/`; all other packages run one after another.

## Findings from WP-O0

The details are in `plan/wps/port-orientation/` (`orientation-table.md`, `composites.md`, `violations.md`).
- **Measured**: the example and fixture counts. Every model was flattened by the compiler and checked bond by bond.
- **Estimated**: the Julia test counts, from a static parse.

Summary of the inventory:
- **Stdlib**: 205 blocks and 414 power ports, of which 136 are `in`, 64 `out` and 214 `any` (195 of these are
  iconic). 47 blocks need an equation change.
- **Project libraries**: 57 blocks, of which 9 need an equation change.
- **Examples**, 234 models and 6510 bonds:
  - as written: 793 O3 bonds and 959 O4 bonds;
  - with A1 below: 528 O3 (457 neutral, 4 neutral-with-start-values, 31 source, 36 review) and 30 O4.

**F1. Mounts and the other pass-through two-ports cannot be fixed `a in, b out` (amendment A1).**
- A mount's `a` side is bonded to the part it carries: a contact, a sensor, a joint parent, a `Df`. All of these are
  `in` by O6.
- So O6 as written turns 959 example bonds into in-in O4 errors. Reversing a bond does not help, and flipping a
  mount needs the inverted offset.
- **Amendment A1**: `FixedTransform2D/3D/3DNeutral`, `TFAd`, `TFAdNeutral`, `JointTransform2D/3D`, `FixedJoint2D`,
  `TF`, `GY`, `MTF`, `MGY` and `PowerSensor` declare a **relation**, "`a` and `b` opposite", instead of two fixed
  orientations. The compiler resolves it from the neighbours, the way 20-sim's port relations work.
  - Their laws are in the into-block form (`a.f = -Ad b.f`), and they work either way round.
  - O2 needs a fourth value, or a separate `@orientation_relation`. WP-O1 must decide which before the contract
    changes.
  - With A1 the plan's O4 count drops from 959 to 30.

**F2. Only bonds to a 1-junction carry a sign; O9 must be junction-aware.**
- A bond between two element ports gives `to.e = from.e`, `to.f = -from.f`, and is direction-free. A bond to a
  0-junction is direction-free too. Most O3 errors on such bonds are notation only.
- When a block's law changes (O7, `Sf`), every model that uses the block changes, whether its bond is reversed or
  not. Two consequences for the migration tool:
  - It must follow chains: element-to-element bonds and pass-through two-ports, decided per 1-junction cluster.
  - It must touch non-violating bonds of changed blocks (17 silent source chains, 3 silent review chains), and
    negate the start values of odd elements on a flipped chain.
- Classifying by block kind alone gives 471 review cases. Junction-aware classification gives 36.

**F3. O8's claim is wrong for 0-1 junction bonds.**
- Reversing a 1-1 or a 0-0 junction-to-junction bond is neutral. Reversing a 0-1 bond changes the model: the
  0-junction's effort enters the 1-junction's sum with the other sign. There are 185 such bonds in 16 examples.
- O3 does not check them, because both ends are junctions. A composite face that is a junction (for example
  `Revolute2DRigid.parent`) creates such bonds without the user seeing two junctions.
- The editor must not present "reverse" on a 0-1 bond as harmless. Whether to fix the direction of 0-1 bonds (for
  example 1 -> 0 always) is a decision for WP-O1.

**F4. "Sources are `out`" needs two qualifications.**
- *Iconic sources*: `SpeedSource`, `VelocitySource`, `Fixed`, `Ground`, `Tank`, `PressureSource`, the
  temperature and heat-flow sources. Their laws are wire laws written for the head position, so they stay `any`.
- *Flow sources*: `Sf`, `MSf`, `SfPlanar`, `SfSpatial`, `MSfPlanar` and the project `ToolMotion` are written in
  the into-block form (`p.f ~ f`), so at the tail they inject `-f`. They need an equation change, not only a
  declaration. The MSf golden test works around this today with `gain = -1`.
- Effort sources (`Se`, `MSe`) are already right at the tail. The `GravityPlanar/Spatial` and
  `ExternalWrenchPlanar/Spatial` laws change sign with the body rebuild (O7).

**F5. Joint drives `in`, iconic ports `any` (amendment A2 rejected).**
- With drives `in`, a damper bonded directly to `Free3D.drive_k` is an in-in bond: 30 bonds in lunar-module and
  rocket. Each needs a 1-junction in between, which fits O12.
- Declaring iconic ports `in` (A2) would protect the 278 junction-to-iconic bonds. But it adds 96 O3 bonds (60 of
  them review: cars, excavator, hybrid-powersplit, planar-links) and 12 O4 bonds, so it is not recommended.

**F6. Review cases and latent signs.**
- The 36 review bonds are all in cars: `Prismatic3D.drive ->` the suspension junction of the project block Strut,
  which documents `j.f = -dx/dt`. The Strut convention has to be decided before cars is regenerated.
- flex-torsion and flex-rotary-pendulum each have a silent odd chain (a joint parent on a mount on a FEM node),
  which may be a latent sign error. Settle it with `compare_signals`.
- Two models have no numeric check: `pendulum-double-cart(-lab)/*-plant`. Both get a before/after signal compare.

**F7. Stale prose to remove in WP-O5.**
- the "bond FROM this port" headers of `DeckContact2D` and `SoilCutting2D` (both already expect the true twist);
- the `CoriolisSpatial` header;
- the claim in the `FlexibleBeam3D` header that its ends may be bonded "in any bond direction";
- the W218 paragraphs in `julia/BGSim/NOTES.md`, the spec, the manual pages and the diagnostics fixture (uncommitted
  in the current tree).

**Split.**
- **WP-O2** (scalar: 40 violating bonds in 7 examples; Sf/MSf plus source negations) stays one package.
- **WP-O3** splits into three:
  - **O3a**: the A1 relation, the body and composite rebuilds (= the WP-O5 composite list), the source, contact and
    joint law changes, and the Julia tests and goldens.
  - **O3b**: the build-script examples, regenerated, 2D first.
  - **O3c**: the generator-built JSON (fanuc-pick, humanoid-dual-arm, panda-3d) and the hand-written JSON, through
    O9.
- Order within O3b/O3c:
  1. the all-neutral examples with strong checks;
  2. the source examples;
  3. lunar-module and rocket, together with O12;
  4. cars, flex-* and the two unchecked models.
