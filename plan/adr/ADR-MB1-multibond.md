# ADR-MB1: multibond contracts (C-MB1)

Status: accepted, 2026-10-28 (revision 2). Scope: `contracts/` for M3, WP C-MB1.
Sources: `plan/MULTIBOND_PLAN.md` 4, 6, 7.1, 8; `plan/IMPLEMENTATION_PLAN.md` 3.2-3.4; the spec's frame discussion.

This ADR freezes the multibond decisions and the concrete contract shapes the three lanes build against. The JSON Schemas remain the single source of truth; the pydantic and TypeScript files are generated from them.

## Decisions

**D-MB1 — `Power{Planar}` / `Power{Spatial}` on the existing port abstraction.** Accepted; a second `MultiPort` would duplicate the IR, causality and editor machinery. Consequence: `DomainName` gains both names in every enum, a planar port has size 3, a spatial port size 6, and `Generic` is the only domain without a concrete unit.

**D-MB2 — angular-first `[ω; v]`, wrench `[m; f]`.** Accepted; it matches the design, the spec and Featherstone, so formulas transcribe without reordering. Consequence: component units are angular first, and the planar `ad(V)` is the spatial form restricted to the plane.

**D-MB3 — v1 inertia: body frame at the CoM on principal axes, `J::Vec{3}` and `m::Real`; full `IGeneral` later.** `M` lives only in `I`, and `Coriolis` takes the momentum `P` as a signal input, not a copy of the inertia. Consequence: `I` stays component-wise and Dzhanibekov is reachable with a diagonal inertia.

**D-MB4 — one multibond port per body; named attachment frames are external `FixedTransform`s.** Accepted; fixed-arity ports still cover arms, wheels and contacts. Consequence: no variable-arity ports or generated templates in v1; a subsystem port's declared frame is authoritative for the exposed port, and it may differ from the internal port's catalog frame only through an internal `FixedTransform`/`JointTransform`.

**D-MB5 - frame metadata + equality + `E007`; transforms are the only bridge.** Accepted; this catches the main wiring bug without dependent frame types. Consequence: optional `frame` on catalog and subsystem power ports, display-qualified `model.check.frames` values while **frame equality is by the unqualified frame name**, and no `SE3{:a,:b}` arithmetic.

**D-MB6 — only floating bases integrate a pose.** 2D angle+position; 3D quaternion+position with `ManifoldProjection`; fixed-base links compose `g_child = g_parent ∘ g(q)`. Consequence: poses fit `ODEProblem`, and `ComposePose` is a library block, not a new contract type.

**D-MB7 — one backend: the existing MTK/OrdinaryDiffEq pipeline.** Accepted because a custom articulated-body evaluator is explicitly out of scope and would be a second solver path. Compliant joints are the default; a rigid joint is a DAE handed to `mtkcompile`'s index reduction. Consequence: no articulated evaluator, and stiffness and step time remain model properties rather than contract fields.

**D-MB8 — one scalar power port per joint axis, domain from the screw, `S` a `Mat{D,n}` TF.** Accepted so the scalar unit checker can validate every drive without inventing a `JointSpace{n}` domain. Revolute exposes `Rotation`, prismatic `Translation`; a helical joint exposes its coordinate's domain and keeps the pitch in `S`. Consequence: no false unit error on a prismatic drive and no new domain.

**D-MB9 — compliance, friction and limits as per-joint variants.** A composite cannot conditionally include elements, and `k = 0` is not rigid. Consequence: separate library refs such as `Revolute2DCompliant`, with no global switch in the contract.

**D-MB10 — component-wise loops in two thin Planar/Spatial wrappers.** The unit checker is scalar, so `p.e[k]` keeps torque and force distinct. Consequence: per-component unit arrays in the catalog and at subsystem boundaries; no vector-valued unit inference in the language.

**D-MB11 — compliant `ContactPoint` in v1; `SwitchedJoint`/impact later.** Accepted because contact is buildable from existing primitives while a model-level impulse needs the corrected projection first. Fixed Hunt-Crossley and regularized-Coulomb forms ship with exposed parameters. Consequence: no contract field for mode switching; `V+ = S (SᵀMS)⁻¹SᵀMV−` waits in the plan for J-MB14.

**D-MB12 — Planar 2 strokes, Spatial 3, scalar 1, derived from the domain.** The count encodes the model dimension, not `D` (Planar has three components but two strokes). Consequence: no stroke field; `model.check.multibond` reports the count for the renderer.

**D-MB13 — real-time and export out of scope.** The adaptive stack cannot meet fixed-step, no-allocation or <1 ms targets. Consequence: `W203`/`E104` stay deferred and performance is recorded, not gated.

## Contract shapes

- `catalog.schema.json`: `CatalogDomain` is a name-partitioned union of `PlanarDomain`, `SpatialDomain` and `ScalarDomain`; an `allOf`/`if`/`then` over `name` restates the same partition. Planar requires `components` with exactly 3 units per array and `size` 3; Spatial requires exactly 6 and `size` 6; scalar domains forbid `components` and have `size` 1. The `components` arrays are authoritative; the scalar `effort`/`flow` descriptors are only the angular/first-component label kept for existing consumers. Both multibond domains declare `across = "f"` (D8). `portDecl.frame` (shared with `blockInterface`) is optional string/null, and `catalogBlock.dimension` and `blockInterface.dimension` are optional `2 | 3`.
- Planar components: effort `["N*m","N","N"]`, flow `["rad/s","m/s","m/s"]`. Spatial: effort `["N*m","N*m","N*m","N","N","N"]`, flow `["rad/s","rad/s","rad/s","m/s","m/s","m/s"]`.
- Frame rule (D-MB5): a port's frame is the frame its twist/wrench are expressed in. A subsystem port's frame is **authoritative for the exposed port**; it may differ from the internal port's catalog frame only through an internal `FixedTransform`/`JointTransform`, which the flattener must accept. `null`/absent is frame-neutral: it unifies with any adjacent frame (adopts it) and never causes E007. Two different named frames on one bond or wire are E007. `model.check.frames` values are display-qualified as `"{path}/{frame}"` (e.g. `Arm1/body`), but **equality is by the unqualified frame name**: two instances that use the same name are declaring the same frame. The documented v1 limitation is a false negative when two different bodies both name their local frame `body`; the discipline is a distinct name per body, and typed frame objects are deferred with D-MB5.
- `model.schema.json`: subsystem power port gains optional `frame` and optional `effortUnits`/`flowUnits`, each exactly 3 (`UnitArray3`) or 6 (`UnitArray6`) strings. Its `size` is pinned to the declared domain by `allOf`/`if`/`then`: `[3]` for Planar, `[6]` for Spatial and `[1]` for the scalar domains, so `domain: "Planar", size: [4]` is invalid. Derivation of the units from the port's catalog domain is preferred; the arrays exist only when a subsystem overrides a Generic port, and J-MB1 checks equality with the domain's `components`. Its domain enum gains both multibond names.
- `worker-rpc.schema.json`: `domains` gains both names. `frames` is required and maps connection id to a display-qualified frame name (`"{path}/{frame}"`, empty object valid); equality is by the unqualified frame name (D-MB5). Optional `multibond` maps connection id to `2 | 3`; it must agree with the adopted domain (2 for Planar, 3 for Spatial) and is reported for bonds only - J-MB1 invariant. A multibond port is recorded per component: `signals` carries `<path>/<port>.e[k]` and `.f[k]`, each with its own unit, plus the scalar `<path>/<port>.P` in W; `run-manifest`'s signal-id pattern accepts a field index.
- `diagnostic.schema.json` does not enumerate codes; the codes live in the sample fixture, both contract-test code lists and this ADR.

## New diagnostic codes

- **E007 — frame mismatch.** A bond or wire joins two multibond ports with different declared named frames (including the union-find over a junction or wire group). The message names both ports and both frames; `path` is the reported port, `related` names the other end of the bond, and `connection` points at the bond, so the editor can highlight both. The hint names `FixedTransform`/`JointTransform` and says a null frame unifies. Example: "frame mismatch: Planar port `p` of `Arm1` is in frame `world`, but port `a` of `Load1` is in frame `arm1`".
- **E108 — invalid inertia (parameters).** An inertia's *parameters* are invalid: `m <= 0`, a principal inertia `J <= 0`, an `IGeneral` matrix that is not symmetric positive definite, or a non-finite entry. The hint names the offending parameter and the body path; the triangle-inequality hint applies only to `IGeneral` (v1 uses a diagonal `J`). It is a parameter fault, independent of assembly.
- **E109 — singular mass (assembled).** After assembly the mass matrix of a body/subtree is singular at the current configuration although the parameters are valid - e.g. a planar body with zero out-of-plane inertia driven by a spatial wrench, or a constrained subtree that leaves a free direction. The message names the body and the singular direction; the hint asks for the missing inertia or a compliant element. It is distinct from E103 (equation balance) and E106 (fixed-causality conflict) and fires after assembly.

## Fixture inventory

Valid: `catalog.min.json` (all seven domains; Planar/Spatial size + exact components), `catalog.planar.json` (dimension 2, framed Planar port, components), `model.planar.multibond.json` (self-contained inline Ground(world) -> junction -> FixedTransform2D(world -> arm) -> BodyPlanar(arm)), `model.spatial.multibond.json` (the same chain with six-component Spatial ports), `model.frame-bridge.json` (subsystems whose port frames match their internal inline transform/body; `Mount` bridges world -> arm), `worker-rpc/valid/response.model-check.json` (`frames: {}`), `worker-rpc/valid/response.model-check.multibond.json` (instance-qualified `frames`, `multibond` 2/3, per-component signals), `worker-rpc/valid/response.block-check.planar.json` (`blockInterface.dimension` 2 and a framed Planar port), and `diagnostic/valid/diagnostics.sample.json` (E007 with `related`, E108, E109).

Invalid, each with a `$comment`: `catalog.planar-missing-components.json`, `catalog.spatial-short-components.json`, `catalog.scalar-components.json`, `catalog.bad-components-length.json`, `catalog.bad-port-domain.json`, `model.bad-domain-spelling.json`, `model.bad-frame-type.json`, `model.planar-size-four.json` (Planar subsystem port size `[4]`).

Semantic (schema-valid, `$comment` starts with `expected E<code>:`), in `model/semantic/`: `model.e007-frame-mismatch.json` (direct world -> body bond), `model.e006-unit-mismatch.json` (`N*m` torque added to `N` force), `model.e108-invalid-inertia.json` (inline body with `m = 0`), `model.e109-singular-mass.json` (an inline joint with two coincident revolute axes: `SᵀMS = J*[[1,1],[1,1]]` has rank 1, valid `J`, two independent torque drives). J-MB1/J-MB2 consume these.

## Known generator artefacts (owned by C-MB2)

The generated pydantic is laxer than JSON Schema in ways the generator cannot express. Every optional field becomes `| None = None`, so it accepts an explicit `null` for, e.g., `dimension` or `multibond`, where the schema only allows absence; pydantic's lax integer coercion also accepts `"2"` for `stats.states` where the schema requires an integer. `allOf`/`if`/`then` are not translated into validators; the domain-shape partition is therefore written as a `oneOf` of concrete variants, which Python renders as a `RootModel` union and enforces structurally. C-MB2 owns tightening or adding post-validation tests for these laxnesses. TypeScript renders `CatalogDomain` as an alias of the generated `Domain` union.

## Cross-WP invariants

J-MB1: report frames display-qualified but compare them by unqualified name (the v1 limitation is two bodies both named `body`; a distinct name per body is the discipline); make `multibond` agree with the adopted domain and report it for bonds only (plan 7.1: strokes are a bond property, so a Planar wire has no `multibond` entry); accept a subsystem port whose authoritative frame differs from its internal port's catalog frame only through a connected internal transform, not an unconnected one; treat a null subsystem face as frame-neutral; carry a textual composite's `@ports` frame; report a concrete override of a Generic internal port as E102 (a Generic internal port's flat ids are scalar, so only the scalar override is supported in v1); take a junction's width from the adopted domain and report a Generic scalar port on a multibond junction as E102; and check that subsystem `effortUnits`/`flowUnits` equal the catalog domain's `components`. W-MB1/W-MB2 consume `multibond` for the 2/3-stroke renderer; no stroke field is added.
