# ADR-MB1: multibond contracts (C-MB1)

Status: accepted, 2026-10-27. Scope: `contracts/` for M3, WP C-MB1.
Sources: `plan/MULTIBOND_PLAN.md` 4, 6, 7.1, 8; `plan/IMPLEMENTATION_PLAN.md` 3.2-3.4; the spec's frame discussion.

This ADR freezes the multibond decisions and the concrete contract shapes the three lanes build against. The JSON Schemas remain the single source of truth; the pydantic and TypeScript files are generated from them.

## Decisions

**D-MB1 — `Power{Planar}` / `Power{Spatial}` on the existing port abstraction.** Accepted; a second `MultiPort` would duplicate the IR, causality and editor machinery. Consequence: `DomainName` gains both names in every enum, a planar port has size 3, a spatial port size 6, and `Generic` is the only domain without a concrete unit.

**D-MB2 — angular-first `[ω; v]`, wrench `[m; f]`.** Accepted; it matches the design, the spec and Featherstone, so formulas transcribe without reordering. Consequence: component units are angular first, and the planar `ad(V)` is the spatial form restricted to the plane.

**D-MB3 — v1 inertia: body frame at the CoM on principal axes, `J::Vec{3}` and `m::Real`; full `IGeneral` later.** `M` lives only in `I`, and `Coriolis` takes the momentum `P` as a signal input, not a copy of the inertia. Consequence: `I` stays component-wise and Dzhanibekov is reachable with a diagonal inertia.

**D-MB4 — one multibond port per body; named attachment frames are external `FixedTransform`s.** Accepted; fixed-arity ports still cover arms, wheels and contacts. Consequence: no variable-arity ports or generated templates in v1, and a subsystem boundary keeps the frame of the internal port.

**D-MB5 — frame metadata + equality + `E007`; transforms are the only bridge.** Accepted; this catches the main wiring bug without dependent frame types. Consequence: optional `frame` on catalog and subsystem power ports, `model.check.frames`, and no `SE3{:a,:b}` arithmetic.

**D-MB6 — only floating bases integrate a pose.** 2D angle+position; 3D quaternion+position with `ManifoldProjection`; fixed-base links compose `g_child = g_parent ∘ g(q)`. Consequence: poses fit `ODEProblem`, and `ComposePose` is a library block, not a new contract type.

**D-MB7 — one backend: the existing MTK/OrdinaryDiffEq pipeline.** Accepted because a custom articulated-body evaluator is explicitly out of scope and would be a second solver path. Compliant joints are the default; a rigid joint is a DAE handed to `mtkcompile`'s index reduction. Consequence: no articulated evaluator, and stiffness and step time remain model properties rather than contract fields.

**D-MB8 — one scalar power port per joint axis, domain from the screw, `S` a `Mat{D,n}` TF.** Accepted so the scalar unit checker can validate every drive without inventing a `JointSpace{n}` domain. Revolute exposes `Rotation`, prismatic `Translation`; a helical joint exposes its coordinate's domain and keeps the pitch in `S`. Consequence: no false unit error on a prismatic drive and no new domain.

**D-MB9 — compliance, friction and limits as per-joint variants.** A composite cannot conditionally include elements, and `k = 0` is not rigid. Consequence: separate library refs such as `Revolute2DCompliant`, with no global switch in the contract.

**D-MB10 — component-wise loops in two thin Planar/Spatial wrappers.** The unit checker is scalar, so `p.e[k]` keeps torque and force distinct. Consequence: per-component unit arrays in the catalog and at subsystem boundaries; no vector-valued unit inference in the language.

**D-MB11 — compliant `ContactPoint` in v1; `SwitchedJoint`/impact later.** Accepted because contact is buildable from existing primitives while a model-level impulse needs the corrected projection first. Fixed Hunt-Crossley and regularized-Coulomb forms ship with exposed parameters. Consequence: no contract field for mode switching; `V+ = S (SᵀMS)⁻¹SᵀMV−` waits in the plan for J-MB14.

**D-MB12 — Planar 2 strokes, Spatial 3, scalar 1, derived from the domain.** The count encodes the model dimension, not `D` (Planar has three components but two strokes). Consequence: no stroke field; `model.check.multibond` reports the count for the renderer.

**D-MB13 — real-time and export out of scope.** The adaptive stack cannot meet fixed-step, no-allocation or <1 ms targets. Consequence: `W203`/`E104` stay deferred and performance is recorded, not gated.

## Contract shapes

- `catalog.schema.json`: seven-value `DomainName`; `CatalogDomain.size` is `1 | 3 | 6`; optional `components` (`DomainComponents`) has `effort`/`flow` string arrays of 3-6 entries, angular first. Scalar domains keep the single `effort`/`flow` descriptors; Planar and Spatial declare `across = "f"` (D8). `portDecl.frame` is optional string/null (shared with `blockInterface`), and `catalogBlock.dimension` is optional `2 | 3`.
- Planar: effort `["N*m","N","N"]`, flow `["rad/s","m/s","m/s"]`. Spatial: effort `["N*m","N*m","N*m","N","N","N"]`, flow `["rad/s","rad/s","rad/s","m/s","m/s","m/s"]`.
- `model.schema.json`: subsystem power port gains optional `frame` and optional `effortUnits`/`flowUnits`; its domain enum gains both names.
- `worker-rpc.schema.json`: `domains` gains both names; `frames` is required and maps connection id to frame string (empty object valid); optional `multibond` maps connection id to `2 | 3`.
- `diagnostic.schema.json` does not enumerate codes; the new codes live in the sample fixture, both contract-test code lists and this ADR.

## New diagnostic codes

- **E007 — frame mismatch.** A bond or wire joins two multibond ports with different declared frames (including the union-find over a junction or wire group). The message names both ports and frames, `path`/`connection` point at the bond, and the hint names `FixedTransform`/`JointTransform`; e.g. "frame mismatch: Planar port `p` of `Arm1` is in frame `world`, but port `a` of `Load1` is in frame `arm1`".
- **E108 — invalid inertia (not SPD).** An inertia's parameters do not form a positive-definite mass matrix; in v1 every principal moment `J[k] > 0` and `m > 0`, and a full `IGeneral` must also satisfy the triangle inequality. `path` names the `I`/body instance.
- **E109 — singular mass (underdetermined).** The assembled mass matrix of a body or subtree is singular, so acceleration cannot be solved: a massless, inertia-free body or constraints that leave a free direction. The message names the body and the missing quantity; the hint asks for `m > 0`/`J > 0` or a compliant element.

## Fixture inventory

Valid: `catalog.min.json` (Planar and Spatial domains with size/components, exact order E, T, R, H, G, Planar, Spatial), `catalog.planar.json` (dimension 2, framed Planar port, components), `model.planar.multibond.json` (Ground → 1-junction → Arm with Planar bonds), `model.spatial.multibond.json` (Ground → 1-junction → Body plus an ExternalWrench tap), `model.frame-bridge.json` (FixedTransform2D bridging `world` and `arm1` with matching frames on both bonds), `response.model-check.json` (`frames: {}`), `response.model-check.multibond.json` (`frames` plus `multibond` 2 and 3), and `diagnostics.sample.json` (E007, E108, E109). Invalid, each with a `$comment`: `catalog.bad-components-length.json` (two units instead of three), `catalog.bad-port-domain.json` (unknown domain), `model.bad-domain-spelling.json` (`"Planer"`), `model.bad-frame-type.json` (`frame: 7`).
