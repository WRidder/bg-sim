# Multibond mechanics (2D/3D): assessment and implementation plan

Status: v1.0, 2026-10-27. Input: `design/multi-bond-graph.md` (the design),
`spec/Modeling Language Spec v0.1.md` (the spec), the M2 codebase at commit `bcc5641`.

> **Visual requirement (from the reference image).**
> A **planar multibond** is drawn as **two parallel strokes**; a **spatial multibond** as
> **three parallel strokes**; scalar bonds stay **one stroke**. The stroke count is a
> property of the model dimension, not of the mathematical port size (`D = 3` planar and
> `D = 6` spatial). The reference image's 2-stroke `MGY` bond and 1-stroke `GY` bond are
> exactly this distinction. Section 7 specifies the geometry. The visual is not an optional
> polish item: it is the acceptance test for "the editor understands multibonds".

## 1. Verdict

**The physics is sound; the implementation strategy is over-specified.**

The port-Hamiltonian / screw formulation, the `Ad`/`ad` identities, the body-frame inertia,
the gyrator power neutrality and the compliance-first causality story are correct and match
the spec's spatial section. The design is a credible target.

The design's two strongest implementation claims do **not** survive contact with the codebase:

1. **"No new primitive; every high-level element is only a subsystem of existing scalar
   elements."** This is false for a spatial rigid body. A full spatial inertia is a coupled
   6x6 matrix, and the frame transformer is a 6x6 adjoint. Neither is a component-wise
   wrapper of a scalar `I`, `TF` or `GY`. The design itself lists `EulerGyrator`,
   `Gravity3D`, `ContactPoint` and the adjoint transformers as elements, so the rule cannot
   be read literally. The workable version is: **a small set of documented vector
   primitives, plus composites made only from them**. The flat graph stays inspectable and
   standard.
2. **"The existing causality assignment and ODE integrator work unchanged."** They work once
   vector ports, component units and frame checks exist, **if every joint is compliant**
   (integral causality, every state vector-space or quaternion+position). Rigid joints may
   still be expressed as DAEs and left to `mtkcompile`'s index reduction, but there is **no
   articulated-body backend**: everything runs on the existing MTK/OrdinaryDiffEq pipeline.
   The design's <1 ms and fixed-step targets are therefore out of scope.

**Recommendation:** make this **M3 (multibond mechanics)**. Deliver a **planar vertical slice
first** (2-stroke editor visual included), then spatial, drives and contact. Do not start
with the six-axis arm or the pyramid.

Indicative size: **~26 work packages** (about 20 implementation WPs plus visual, example and
integration WPs), comparable to M2, with no new solver backend. It is not a one-session task.

---

## 2. What the codebase already gives us

This is better than the design assumes. Several "new core abstractions" already exist in a
scalarized form.

| Design concept | What exists today | Remaining gap |
| --- | --- | --- |
| `MultiPort<D>` | `Power{Domain}` with `domain_size` already returning 3 for `Planar` and 6 for `Spatial` (`src/syntax/ast.jl`). A port is **one** `PortInfo` with `eids`/`fids` per component; causality is per port, i.e. already "as a whole". | The parser rejects `Planar`/`Spatial` (`POWER_DOMAINS`); contracts do not list them; units are one value per port. |
| `0<D>` / `1<D>` junctions | `src/compile/junctions.jl` already emits equations per component and uses the port's size. A `Planar` bond on an existing 0/1 junction will work once the domain is accepted. | Frame equality is not checked; visual bundle. |
| `Vec{N}` / `Mat{N,M}` values | J2.1/J2.7c: vector/matrix literals, `ddt(Vec)`, `Mat*Vec`, row-major matrices, unrolled `for`. `StateSpace` already does `ddt(x) ~ A*x + B*u`. | No per-component units; no `SE2`/`SE3` value type. |
| Subsystems / composites | J2.6/J2.6b: textual `@components`/`@connections` flatten to the same IR as model-JSON subsystems; signal wiring and `@inputs`/`@outputs` work; `@parameters` alias and `@observables` work. | No variable-arity power ports; no parameterized generator (one source per shape). |
| Causality | `src/compile/causality.jl` SCAP with strokes, W201/W202/E106, transformer/gyrator propagation. | Needs a frame check and the new element declarations; derivative-causal vector `I` is still W201. |
| Lowering / solver | `src/lower/mtk.jl` + OrdinaryDiffEq, `mtkcompile`, compile cache, recorder, discrete scheduler, events. | Group-valued states; rigid-joint DAE index; no articulated backend (by decision). |
| Editor | xyflow canvas, bond/wire/signal edges, causal strokes, domain colours, unit badges, subsystem breadcrumbs, snapshot tests. | `Planar`/`Spatial` are not contract domains; `domainColor` lacks Planar; bonds are single-stroke. |
| 3D viewer | M5, still `todo`. | Independent of this plan; the "3D graph" here is the 2D canvas schematic, not the 3D scene. |

**Consequence:** the first phase is mostly *language plumbing*, not new simulation code. The
existing vector equation machinery carries most of the load.

---

## 3. Findings

Severity: **B** = blocks the design as written; **H** = high risk or large work; **M** = medium.

| # | Finding | Sev. | Resolution in this plan |
| --- | --- | --- | --- |
| F1 | The design's new `MultiPort<D>` duplicates the existing `Power{Domain}` port. Two port abstractions would double the IR, causality and editor work. | B | Use `Power{Planar}` / `Power{Spatial}`. No `MultiPort` type. D-MB1. |
| F2 | "Component-wise wrappers of scalar elements" cannot express a full spatial inertia or a matrix adjoint. `M` is a coupled 6x6; `Ad` is 6x6. | B | Add a small vector-primitive group with `Vec`/`Mat` parameters. Start with **diagonal** inertia in the CoM/principal-axis frame (`J::Vec{3}`, `m::Real`); add `IGeneral` later. D-MB3. |
| F3 | "No opaque elements" contradictorily lists `EulerGyrator`, `Gravity3D`, `ContactPoint` as elements. Taken literally it forbids its own primitives. | B | Redefine: **no opaque composite**. High-level items are subsystems of documented vector primitives; the flat graph contains only standard elements. D-MB1/D-MB3. |
| F4 | `EulerGyrator` is not an `MGY`. It is a **1-port power-continuous** element, and tying it to a copy of `M` would duplicate the inertia parameters in two blocks. | H | Implement `Coriolis` as a 1-port element with a **signal input `P` from `I.P`** and `e = ad(V)^T P`; **no `M` parameter**. This is Breedveld's Eulerian junction structure, modulated by momentum, not by a copy of the inertia. `V^T e = 0` is the test. D-MB3. |
| F5 | Full frame typing (`SE3{:a,:b}`, `Twist{:i,:j,:k}`) is a type-system project: type parameters, unification, frame arithmetic, E007. It is in the spec's v0.3, not the current language. | H | v1: `frame` metadata on ports + equality through bonds/junctions/wires, E007. A transform declares two frames and is the legal bridge. Defer dependent frame arithmetic. D-MB5. |
| F6 | Group-valued states do not fit `ODEProblem`: the design's `g_{k+1}=g exp(V dt)` needs a per-state hook the integrator does not have. | H | Only **floating bases** integrate a pose: 2D angle+position, 3D quaternion+position, `ddt(q)=0.5 q⊗[0,ω]`, `ddt(p)=R(q)v`, plus a `ManifoldProjection` callback for `|q|=1`. **Fixed-base link poses are algebraic**: `g_child = g_parent ∘ g(q)`, propagated through the chain with `ComposePose`. No `exp` integrator. D-MB6. |
| F7 | An articulated-body (Featherstone ABA) evaluator is not an MTK lowering. A rigid serial chain is index-3; `mtkcompile` will likely reduce it with Pantelides/dummy derivatives, but it will not be fast. | H | Use compliant joints for the target models and rely on MTK's DAE/index reduction only where a rigid joint is unavoidable. Record step time, but do not promise <1 ms. D-MB7. |
| F8 | `1..k` multibond ports and parameterized subsystems do not exist. `@ports` is fixed-arity; a library block is one static source. | H | One multibond port per rigid body; attachments are external `FixedTransform`s. Typed joint blocks/composites. Variable-arity ports and generated subsystem templates later. D-MB4. |
| F9 | Per-component units are missing. `domain_effort_dims(Planar)` returns one `Dims` (N), so a torque component is checked as a force. This is exactly the bug the design warns about. | B | Add component unit vectors to `PortInfo`/catalog and write vector primitives **component-wise** (`p.e[k]`) so the scalar checker sees the right unit. D-MB10. |
| F10 | The joint's `1<n>` junction has no power domain. Existing domains are fixed at 1, 3 or 6, and a joint rate is not a `Planar`/`Spatial` twist (torque vs wrench). | H | v1: `n` scalar `Rotation` ports/junctions, one per joint axis, with an `S` matrix TF (`D×n`). A `JointSpace{n}` domain can come later. D-MB8. |
| F11 | Contact is feasible; `SwitchedJoint`/impact is not block-local. Junctions are static (no on/off input), and the impulse map needs all body momenta, which a block-local `@events` cannot see. The language also has no function-valued parameters, so "user-supplied constitutive functions" cannot ship as written. | H | Ship compliant `ContactPoint` with fixed Hunt-Crossley and regularized-Coulomb forms (parameters exposed); defer user functions and `SwitchedJoint`/impact to a dedicated WP. The impact map runs through the existing event mechanism plus a generated projection; it does not need a new solver. The design's `1<2>` tangent becomes two scalar `1` junctions. D-MB11. |
| F12 | The impact map `P+ = Proj_S(P-)` is wrong as written, and so is the first correction `V+ = V- - S (S^T M S)^-1 S^T V-` (it does not satisfy `S^T M V+ = S^T M V-`). With `S` the allowed-motion basis of the new pivot and `C` its complement (constrained directions), the impulse `M(V+ - V-) = C λ` with `C^T V+ = 0` gives `V+ = S (S^T M S)^-1 S^T M V-` or equivalently `V+ = V- - M^-1 C (C^T M^-1 C)^-1 C^T V-`. Kinetic energy is non-increasing automatically. | B (for that WP) | Use one of these forms, with `S`/`C` and `M` in the same frame; test `S^T M V+ = S^T M V-`, `C^T V+ = 0` and non-increasing KE. Fix the ADR before writing the WP. D-MB11. |
| F13 | "No allocation after construction" and the PREEMPT_RT target conflict with the MTK/OrdinaryDiffEq stack (adaptive, allocating). The main plan already defers fixed-step/export. | H | Keep real-time/export out of scope. The only backend is the existing adaptive MTK pipeline; no preallocated articulated path. D-MB13. |
| F14 | The editor has no multibond visual and no Planar/Spatial contract domains. `domainColor` lacks Planar; bonds are one stroke. | M | Add the 2/3-stroke renderer, contract domains, colours, legend, frame badges. Section 7, W-MB1/W-MB2. |
| F15 | The port `P=e·f` signal exists, but there is no model-level energy diagnostic. | M | Add an energy-balance helper over recorded signals first (tests), then an optional live monitor. Section 9. |

### 3.1 Correct formulas worth keeping

- Angular-first ordering `[ω; v]`, wrench `[m; f]` is consistent throughout the design and the spec.
- Spatial `ad(V) = [[ω̂, 0], [v̂, ω̂]]`; planar `ad(V) = [[0,0,0], [v_y,0,-ω], [-v_x,ω,0]]` is its restriction.
- `Ad_g = [[R, 0], [p̂R, R]]` for `[ω; v]`.
- `ad(V) V = 0`, hence `V^T ad(V)^T P = 0`; this is the gyrator/Coriolis power test.
- The spatial inertia formula with `J_c + m ĉ ĉ^T` and the `m ĉ` cross block is correct for `[ω; v]` with the body origin as reference. With the body frame at the CoM it reduces to `diag(J_c, m I)`, which is the v1 simplification.
- The planar revolute screw `S = [1, r_y, -r_x]^T` is correct for the screw twist (origin velocity), not the point velocity. Keep the convention documented.
- The design's planar inertia row is truncated in the source (`M = [[J + m |`). Do not
  transcribe it: derive the 3x3 from the spatial formula restricted to the plane, or use
  `diag(J, m, m)` in the CoM/principal-axis frame (the v1 choice).

### 3.2 Section-by-section verdict

| Design section | Verdict | What changes |
| --- | --- | --- |
| Core abstractions | **Adapt** | `MultiPort<D>` becomes `Power{Planar|Spatial}`; `0<D>`/`1<D>` are the existing junctions; `Frame` becomes port metadata; `Pose<D>` is a numeric library type, not a language type in v1. |
| Planar element set | **Keep the physics, split the implementation** | The elements become composites of vector primitives; `RigidBody2D` gets one port + external `FixedTransform`s; the body frame is at the CoM. |
| Spatial element set | **Keep, scope the inertia** | Diagonal principal inertia first; full `IGeneral` later. The Euler term is a 1-port `Coriolis`, not an `MGY`. |
| Joint elements | **Keep the basis table, replace `1<n>`** | `n` scalar `Rotation` ports; `S` is a `Mat{D,n}` TF; compliance/friction/limits are variants. |
| Actuator and drive elements | **Keep** | The scalar chain and existing `GY`/`TF`/`C`/`R` cover it; add the vector body/joint ports and signal taps. |
| Constraints, contact and hybrid | **Contact keep; hybrid defer** | `ContactPoint` is a composite of scalar `1` junctions + nonlinear C/R + direction TFs. `SwitchedJoint`/impact needs a model-level impulse and a corrected projection. |
| Causality, state selection and solvers | **Keep, single backend** | All models use the existing MTK/OrdinaryDiffEq pipeline. Prefer compliant joints; rigid joints rely on MTK's DAE/index reduction. No articulated backend. |
| Required elements per setup | **Keep as acceptance targets** | The pyramid's hybrid part uses the existing event mechanism; no solver gate. |
| Validation tests | **Keep** | The <1 ms and fixed-step checks are out of scope; the impact-map check remains. |
| Implementation order | **Bottom-up** | Vertical slice (planar + 2-stroke visual) before the full planar set; spatial after the planar gate; drives; contact and hybrid last. |

### 3.3 Target setups

| Setup | Verdict | What it needs first |
| --- | --- | --- |
| Planar 2-link arm | **Feasible** after the planar slice. This is the proving ground. | Vector domain, units, Lie core, planar primitives, joints, 2-stroke visual. |
| Spatial 6-axis arm | **Feasible on the existing backend**, with compliant joints. No <1 ms promise. | Spatial domain/joints, quaternion pose for the floating base, pose composition for fixed-base links. |
| Cube/pyramid with reaction wheels | **Contact model feasible; hybrid pivot high risk.** | Spatial body, drives, ContactPoint; SwitchedJoint/impact via events + a generated projection. |

---

## 4. Decisions to freeze before coding

These are the design's open decisions plus the ones this assessment adds. Freeze them in an
ADR created by C-MB1 and in `plan/STATUS.md`; do not let each WP re-litigate them.

| ID | Decision | Recommendation | Why |
| --- | --- | --- | --- |
| D-MB1 | Multibond primitive | `Power{Planar}` / `Power{Spatial}` domains on the existing port abstraction | No duplicate port/causality/editor machinery. |
| D-MB2 | Twist ordering | Angular-first `[ω; v]` | Matches the design, the spec and Featherstone. |
| D-MB3 | Inertia representation | v1: body frame at CoM and principal axes; `J::Vec{3}`, `m::Real`; `IGeneral` (full `Mat`) later. **`M` lives only in `I`; `Coriolis` takes `P` as a signal input.** | Makes `I` genuinely component-wise, avoids duplicated inertia parameters, supports Dzhanibekov. |
| D-MB4 | Body ports | One multibond port per body; named attachment frames are external `FixedTransform`s | Avoids variable-arity ports; covers serial arms, wheels and contacts. |
| D-MB5 | Frame discipline | Port `frame` metadata + equality checks + E007; transforms bridge frames; no dependent frame types in v1 | Catches the main wiring bug without a type-system rewrite. |
| D-MB6 | Pose state | Only **floating bases** integrate a pose (2D angle+position; 3D quaternion+position + `ManifoldProjection`). Fixed-base link poses are algebraic: `g_child = g_parent ∘ g(q)`. | Fits `ODEProblem`, avoids gravity-from-drifted-pose disagreement. |
| D-MB7 | Solver backend | One backend: the existing MTK/OrdinaryDiffEq pipeline. Compliant joints by default; rigid joints only through MTK DAE/index reduction. No articulated backend. | Matches the user's scope decision; honest about performance. |
| D-MB8 | Joint coordinates | One scalar power port per axis; domain from the screw (`Rotation` for revolute, `Translation` for prismatic; helical spans both, so expose the port domain matching the joint coordinate — angle or displacement — and keep the pitch coupling inside `S`). `S` is a `Mat{D,n}` TF. | Avoids a new `JointSpace{n}` domain and a unit-checker false positive on prismatic drives. |
| D-MB9 | Compliance/friction/limits | Per-joint **variants** (`Revolute2D`, `Revolute2DCompliant`, …), not a global switch | A composite cannot conditionally include elements; a `k=0` stiff spring is not rigid. |
| D-MB10 | Vector element code | Component-wise loops (`for k in 1:D`) in two thin Planar/Spatial wrappers; numeric core generic over `D` | The unit checker is scalar; loops preserve per-component units. |
| D-MB11 | Contact / hybrid | Compliant `ContactPoint` in v1; `SwitchedJoint`/impact later; fix the impact formula first | Contact is buildable; model-level impulse is not. |
| D-MB12 | Visual | Planar = 2 strokes, Spatial = 3 strokes, scalar = 1; derived per edge from the domain | The requested convention; no schema field. |
| D-MB13 | Real-time/export | Out of scope for this plan; no articulated or fixed-step backend | The existing stack cannot meet the target. |

---

## 5. Target architecture

### 5.1 Layers

```
contracts/            Planar/Spatial domains, component units, frames, E007
  │
syntax + units        Power{Planar|Spatial}, frame attr, DimsVec, E007
  │
IR / flatten          one PortInfo per vector port; component ids; frame union-find
  │
mech/                 SE2, SE3, Twist, Wrench, Ad, ad, exp, log, quat, spatial_inertia
  │
stdlib/multibond/     vector I/C/R/Se/Sf/TF/GY/MTF/MGY, Coriolis, Gravity, Ground,
  │                   ExternalWrench, FixedTransform, JointTransform, Df/De
  │
stdlib/planar|spatial/ RigidBody, Revolute, Prismatic, Free, compliance/friction/limits
  │
sim/                  the existing MTK/OrdinaryDiffEq backend (only backend)
  │
web/                  2/3-stroke bonds, frame badges, Planar/Spatial colours
```

### 5.2 The flat picture is still a bond graph

A planar body opened in the editor shows:

```
            FixedTransform (attachment)
                     │
   port p ─── 1<3> ──┼── I (P state, J/m)
                     │        └── P ──► Coriolis (e = ad(V)ᵀP)
                     └── Gravity (m, pose from ComposePose)
```

A revolute joint shows:

```
 parent ── 0<3> ── TF(Ad(q)) ── child
             │
          TF(S)            (S: 3x1)
             │
           1 (drive, domain from screw) ── Df ── Integrator ── q
             │
          [R friction, C/R compliance variants, limit C/R]
```

No opaque body or joint: every box is a standard vector primitive or a signal block. This is
the design's intent, expressed with the primitives that actually exist. The body composite
aliases a single `m` parameter into `I` and `Gravity`; the inertia `J` and the matrix `M` live
only in `I`, and `Coriolis` sees only `P`.

### 5.3 Component units and equations

Do **not** rely on vector-valued unit inference in v1. Write:

```julia
@constants D = 3
@variables P::Vec{D}
@equations begin
    for k in 1:D
        ddt(P[k]) ~ p.e[k]
        p.f[k] ~ P[k] / M[k]
    end
end
```

Each `p.e[k]` has its own unit (`N*m`, `N`, `N` for Planar effort; `rad/s`, `m/s`, `m/s` for
flow). The scalar unit checker and the existing unrolled `for` do the rest. This is more
verbose than `p.f ~ P ./ M`, but it is the only way to keep torque and force distinct with
the current checker. A `DimsVec` extension can make whole-vector equations legal later.

### 5.4 Frame propagation

- Each multibond port declares `frame` (optional; `world` for Ground/World).
- A bond between two ports requires equal frames (E007).
- All ports on one junction share a frame (union-find over the junction's bonds).
- A wire group requires equal frames.
- `FixedTransform` and `JointTransform` declare two different frames; they are the only
  legal bridge.
- `model.check` returns `{connId: frame}` for the editor badge.
- No frame *arithmetic* (`Twist{:i,:j,:k}`); that is the v0.3 type system.

### 5.5 Simulation backend and poses

**One backend.** Every model runs on the existing MTK/OrdinaryDiffEq pipeline. There is no
articulated-body path.

- **Joints.** Default to a compliant variant: integral causality, all states vector-space or
  quaternion+position, and the existing recorder/events/discrete scheduler work. The cost is
  stiff modes; use `Rodas5P`/`FBDF` and a stiffness chosen by the model. A rigid joint may
  still be expressed and handed to `mtkcompile`; MTK's index reduction decides whether it
  solves, and W201 reports the derivative causality. Do not add a custom evaluator.
  **A revolute joint's hard constraints are its two pivot translations, not its rotation**:
  a 3-DOF planar body on a 1-DOF rigid revolute is index-3 by construction, so its rigid
  variant is derivative-causal in those two joint-frame translations and may fail to
  initialise. MTK's 3-DOF twist parametrisation also reports the three momentum aliases, so the
  accepted diagnostic set is the two translations plus the aliases; assert the set, not a count.
  The compliant-pivot variant (exact rotation, compliant translations `kt`/`bt`) removes them
  and is the variant the vertical slice and Gate A use; the rigid variant is kept for the
  DAE/index-reduction tests and for `kt -> Inf` convergence.
- **Poses.** A **floating base** integrates its pose from its twist (2D angle+position; 3D
  quaternion+position). A **fixed-base chain does not integrate link poses**: the link pose
  is `g_child = g_parent ∘ g(q)`, propagated as a signal through `JointTransform` and a
  `ComposePose` block. Gravity and outputs read that algebraic pose. This keeps the joint
  angles and the pose consistent and avoids a drifted quaternion silently changing gravity
  on link 6.
- **Performance.** Record step time and state count on the arm and pyramid; the design's
  <1 ms/fixed-step/no-allocation targets are not part of this plan. If you probe a rigid
  chain, judge it by **step time, not solvability**: MTK's Pantelides + dummy derivatives
  will likely solve a 2-link chain but may be slow. Solvability is not the pass criterion.
  If the arm is too slow, reduce the model or the solver tolerances, or revisit the scope;
  do not add a backend behind the user's back.

### 5.6 Signal interface

The design needs more than power ports. Every primitive therefore exposes what a controller
or a modulation needs:

- `I.P` and `C.q` are `@outputs` (the state); `R` exposes its effort if useful. `Coriolis`
  takes `I.P` as its only signal input, so `M` is not duplicated.
- `De`/`Df` are zero-power detectors with `y::Vec{D}` outputs; `Df` is how a joint gets
  `qdot` and a body gets its twist for the floating-base pose integrator.
- `Se`, `Sf`, `MSe`, `MSf`, `MTF`, `MGY` accept signal inputs, as the scalar versions do.
- `Gravity`, `JointTransform` and `ComposePose` take a pose or angle input; `ComposePose`
  implements the fixed-base `g_parent ∘ g(q)` propagation.
- The composite's `q`, `qdot`, wheel rates and contact force are `@outputs`/`@observables`,
  so the controller can read them by path.

This is the mechanism behind "signal taps on any junction flow or effort and any C/I state".
It is a small extension of the existing `@inputs`/`@outputs`/`@observables` machinery, but it
must be designed into the primitives from the start, not added later.

---

## 6. Work packages

Lanes: C = contracts, J = Julia, W = web, X = examples/integration.
Each WP ends with tests and a report, following the main plan's rules.

### Phase A: foundations and the planar vertical slice

| WP | Lane | Depends | Owns | Deliverable / acceptance |
| --- | --- | --- | --- | --- |
| **C-MB1** | C | — | `contracts/`, `tools/gen_contracts.py`, generated files | Add `Planar`/`Spatial` to every domain enum; catalog domain component units/size; `portDecl.frame`; subsystem power-port frame; E007 (frame), E108 (invalid inertia), E109 (singular mass) in the diagnostic tables; valid/invalid fixtures; regenerate pydantic + TS. |
| **J-MB1** | J | C-MB1 | `src/syntax/{parse,ast,scopes}.jl`, `src/compile/{instantiate,connect,domains,junctions}.jl`, subsystem ports | Accept `Power{Planar}`/`Power{Spatial}`; `PortInfo.frame`; frame union-find through bonds/junctions/wires; E007 with both port paths; `model.check.frames`; `@ports ...[frame = "..."]`; subsystem ports keep the frame. Tests: 2D/3D port size, a mismatched bond gives E007, a transform bridge is legal, vector junction equations. |
| **J-MB2** | J | J-MB1 | `src/units/{dims,unitcheck}.jl`, `src/compile/domains.jl`, `src/ir/flat.jl` | Component effort/flow unit vectors for Planar/Spatial; per-component `FlatVar.unit`; catalog/port unit arrays; component-wise `p.e[k]` units in the checker; power units sum correctly. Tests: torque vs force mixed equation gives E006, a correct planar power sum is W, manifest units per component. |
| **J-MB3** | J | — | new `src/mech/{lie,se2,se3,quat}.jl`; `src/lower/fnmap.jl`; `src/syntax/whitelist.jl` | Numeric `SE2`, `SE3`, `Twist`, `Wrench`, `hat/vee`, `Ad/ad`, `exp/log` (small-angle branches), `compose/inv`, quaternion helpers, `spatial_inertia`, SPD validation. Register the algebraic functions for equations (probe Symbolics derivatives first). Tests: `Ad(g1g2)=Ad(g1)Ad(g2)`, finite-difference `ad`, planar restriction, `V^T ad(V)^T P=0`, exp/log round trip, quaternion norm. |
| **J-MB4** | J | J-MB1, J-MB2, J-MB3 | `stdlib/multibond/` first files, `src/library/catalog.jl` | Minimal vertical slice: `IPlanar` (with `P` output), `SePlanar`, `SfPlanar`, `GroundPlanar`, `TFAd`, `ScrewTF`, `FixedTransform2D`, `CoriolisPlanar` (`P` input, no `M`), `ComposePose2D`, `DfPlanar`, plus a minimal `Revolute2D` **compliant-pivot** variant (exact rotation `q`; compliant pivot translations `d` with `kt`/`bt`; a composite if the signal wiring probe passes, otherwise a native block that J-MB6 later replaces). The pivot translations are the revolute's hard constraints, so compliance there (not on the rotation) is what removes the index-3 structure. A `Ground -> Revolute2D -> Body` pendulum runs through `run.start`; the fixed-base link pose is composed from `q`, not integrated. Acceptance: small-angle period within 1e-3 of `2π√(L/g)` **and** within 1e-4 of the amplitude-corrected physical period; energy constant to 1e-6 of the KE/PE swing (static pivot deflection initialised, `½kt|d|²` in the budget); **no W201** in `model.check` or the run with the compliant pivot; catalog clean. The rigid 1-DOF variant and its two by-design W201 are J-MB6's. |
| **W-MB1** | W | C-MB1 | `web/src/editor/edges/`, `geometry.ts`, `legend.tsx`, `tokens.css`, `web/src/contracts/` | 2-stroke renderer (section 7); Planar domain colour/letter/legend; frame badge on the bond; vitest for stroke count/offset; Playwright screenshot of the pendulum with a 2-stroke bundle; `data-multibond-strokes="2"`. |
| **X-MB1** | X | J-MB4, W-MB1 | `examples/multibond-pendulum-2d/` | Project/model/README/expected.json; pendulum period and energy checks; Playwright opens/runs/plots and asserts two strokes. This is the **gate** for the whole plan. |

### Phase B: planar mechanics

| WP | Lane | Depends | Owns | Deliverable / acceptance |
| --- | --- | --- | --- | --- |
| **J-MB5** | J | J-MB4 | `stdlib/multibond/` | Full planar primitives: `I`, `C`, `R`, `Se`, `Sf`, `MSe`, `MSf`, `TF`, `GY`, `MTF`, `MGY`, `Coriolis` (`P` input), `Gravity`, `Ground`, `ExternalWrench`, `FixedTransform`, `JointTransform`, `ComposePose`, `De`, `Df`. Matrix TF/GY with `Mat`; component-wise loops; power-continuity tests for random V/W; unit tests per element. |
| **J-MB6** | J | J-MB5 | `stdlib/planar/` | Composites: `RigidBody2D` (1 port + I + Coriolis + Gravity), `Revolute2D`, `Prismatic2D`, `Free2D`, `FixedJoint2D`, compliance/friction/limit **variants**, `PoseIntegrator2D` (floating base only), `ComposePose2D` (fixed-base links). Joint `S`/`Ad`/`Df`/`Integrator` wired with signal connections; q/qdot outputs. Acceptance: a single pendulum on the existing backend; a joint with `k` converges to the rigid case as `k` grows. **The rigid 1-DOF variant is derivative-causal in exactly the two constrained pivot translations of a 3-DOF body on a 1-DOF revolute** and must be tested for that set, not "fixed"; MTK's 3-DOF twist parametrisation also reports the three momentum aliases, so assert the set (2 translations + aliases), and the model may fail to initialise (report it). The compliant-pivot variant reports none; `kt -> Inf` (and `k -> Inf` on the per-axis variant) converges to the rigid case. |
| **J-MB7** | J | J-MB6 | `test/golden/planar/`, `test_mech_planar.jl` | Planar suite: single pendulum period, energy, double pendulum compliance convergence, prismatic, free body, applied wrench, friction, limits, W201 absent with compliance, fixed-base pose composition vs integrated truth. |
| **X-MB2** | X | J-MB6, W-MB1 | `examples/robot-arm-2d/`, `examples/reaction-wheel-2d/` | 2-link arm with payload (PD or torque drive) and the planar reaction-wheel/balancer variant; checks for tip trajectory, balance and energy; 2-stroke screenshots. |

**Compliance coordinate convention (J-MB6).** The joint pose `g(q)` must use the **link-side**
coordinate. With a compliant joint, the actuator side is `q - delta` and `delta` is the `C`
state; otherwise the link pose lags by the deflection and the kinematics are wrong. Test a
locked actuator with a spring: the link settles at `tau/k`, and the pose matches the geometric
angle.

**Drive domains (J-MB6/J-MB9).** `Revolute2D` exposes a `Rotation` drive; `Prismatic2D` exposes
a `Translation` drive; a generic joint takes the domain from the screw. Never hard-code
`Rotation`, or the unit checker will reject a valid prismatic drive.

### Phase C: spatial mechanics

| WP | Lane | Depends | Owns | Deliverable / acceptance |
| --- | --- | --- | --- | --- |
| **J-MB8** | J | J-MB5, J-MB3 | `stdlib/multibond/`, `src/mech/` | Spatial primitives: `I` (diagonal `J` + `m`, `P` output), `C`, `R`, `Se`, `Sf`, `TF`/`GY` (6x6), `MTF`/`MGY` (6x6), `Coriolis` (`P` input), `Gravity`, `Ground`, `ExternalWrench`, `FixedTransform3D`, `JointTransform3D`, `ComposePose3D`, `Df/De`, `PoseIntegrator3D` (floating base only: quaternion + position + `ManifoldProjection`). Tests: free body momentum/energy, Dzhanibekov, floating-base screw motion, quaternion norm, fixed-base pose composition. |
| **J-MB9** | J | J-MB8 | `stdlib/spatial/` | Composites: `RigidBody3D`, revolute/prismatic/helical/cylindrical/universal/spherical/planar/free joints, compliance/friction/limits variants. One scalar port per axis with the **domain from the screw** (Rotation for revolute, Translation for prismatic; helical spans both, so expose the coordinate domain and keep pitch in `S`). Fixed-structure typed joints only, axis = local z of the joint frame (placed with `FixedTransform3D`), compliance on the complement; the generic `JointBasis` was dropped (user correction 2026-10-29, `plan/wps/M3-remaining-orchestration.md`). Tests: `S` columns, joint torque/rate, spherical pose storage, universal q-dependence, prismatic drive units. |
| **J-MB10** | J | J-MB9 | `test/golden/spatial/` | Six-axis arm: inverse dynamics computed from the model (rigid variant or high stiffness; validated against an independent recursive Newton-Euler helper on random `(q, qdot, qddot)`); forward dynamics to integrator order; gravity compensation; spherical pendulum; floating base. |
| **W-MB2** | W | W-MB1, C-MB1 | `web/src/editor/` | 3-stroke renderer (section 7); Spatial colour/letter/legend; a 3D graph screenshot; `data-multibond-strokes="3"`; no mixed Planar/Spatial bond island (E102). |
| **X-MB3** | X | J-MB10, W-MB2 | `examples/robot-arm-3d/` | 6-axis arm scene/model; run/plot; 3-stroke screenshot; existing-backend checks. |

### Phase D: drives

| WP | Lane | Depends | Owns | Deliverable / acceptance |
| --- | --- | --- | --- | --- |
| **J-MB11** | J | J-MB6 | `stdlib/drives/` | `ElectricDrive`, `CurrentControlledDrive`, gearbox, reaction-wheel variant; signal taps on port flow/effort, C/I states, MTF/MGY modulations; `Se`/`Sf` signal inputs. |
| **J-MB12** | J | J-MB11 | `test/golden/drives/` | Locked-joint current step `L/R_w`; no-load speed `u/k_t`; power balance; reflected rotor inertia `N²J_m`; reaction-wheel momentum. |
| **X-MB4** | X | J-MB12, J-MB9 | `examples/reaction-wheel-3d/` | Reaction wheel on a spherical pivot; total angular momentum constant with gravity off; derivative equals gravity torque with gravity on; null-space allocation tap. |

### Phase E: contact and hybrid

| WP | Lane | Depends | Owns | Deliverable / acceptance |
| --- | --- | --- | --- | --- |
| **J-MB13** | J | J-MB9 | `stdlib/contact/` | `ContactSurface` (plane), `ContactPoint` (normal nonlinear C/R, Hunt-Crossley; two scalar tangential R with regularized Coulomb; `mu` above/below `tan(angle)` tests). Dropped body rests at `f_n=mg`; slope sticks/slides. |
| **J-MB14** | J | J-MB9, J-MB13 | `stdlib/contact/`, `src/mech/impulse.jl`, `src/compile/events.jl` | `SwitchedJoint` with mode-selected `S` and the corrected impact map, implemented through the existing event mechanism plus a compiler-generated projection over the affected momentum states. Assemble the effective mass matrix `M` of the affected body/subtree at the new pivot (body inertias and transforms, not a copy of a joint parameter), then use `V+ = S (S^T M S)^-1 S^T M V-` (equivalently the `C` form). Guard is model/controller-side. Tests: `S^T M V+ = S^T M V-`, `C^T V+ = 0`, kinetic energy non-increasing, edge balance agrees with `ContactPoint`. |
| **X-MB5** | X | J-MB12, J-MB13 (J-MB14 optional) | `examples/cube-pyramid-3d/` | Four wheels, contact on all vertices, scripted face→edge→corner sequence; compare the contact and switched models on an edge phase. |

### Phase F: integration and polish

| WP | Lane | Depends | Owns | Deliverable / acceptance |
| --- | --- | --- | --- | --- |
| **J-MB15** | J | J-MB10 | `src/library/loader.jl`, `stdlib/multibond/` | Joint-chain record loader `(parent, child, type, axis, offset)` → model fragments; `lumpInto(parent)`; `inverse_dynamics`, `gravity_compensation`. Tests on the six-axis arm. |
| **W-MB3** | W | W-MB2 | `web/src/inspector/`, `web/src/library/`, `web/src/editor/` | Frame inspector, component units, robotics library group (`2D multibond`, `3D multibond`), multibond port glyphs, legend entries, accessible labels. |
| **X-MB6** | X | all | `examples/*/README.md`, `tools/check.py`, acceptance scripts | Energy diagnostic helper over `columns.f64`; all example checks; docs with the stroke convention; screenshots. |
| **C-MB2** | C | all | `contracts/`, docs | Final schema/doc review; ensure generated code is in sync; record any deviations. |

---

## 7. Visual specification: 2-stroke 2D, 3-stroke 3D

### 7.1 Rule

| Model kind | Power domain | Strokes | Notes |
| --- | --- | --- | --- |
| Scalar / 1D | Electrical, Translation, Rotation, Hydraulic, Generic | 1 | Existing rendering unchanged. |
| **2D / planar** | `Planar` (D = 3) | **2** | Matches the reference image's `MGY` bond. |
| **3D / spatial** | `Spatial` (D = 6) | **3** | The requested 3-stroke variant. |

The count is **not** `D`: a planar port has three components but is drawn with two strokes,
because the visual encodes the model dimension (2D vs 3D), not the component count. The
tooltip/aria-label says both: "Planar multibond (3 components)".

The connection kind stays `kind = "bond"`; only its `domain` changes. Signals (modulation,
sensor taps) stay thin single lines, as in the reference image.

### 7.2 Geometry

- **Path:** offset the routed polyline by `d = ±gap` along the segment normal. For `n = 2`,
  offsets `[-gap/2, +gap/2]`; for `n = 3`, `[-gap, 0, +gap]`; `gap = 4.2 px`.
- **Joins:** miter at each waypoint using the average of the adjacent segment normals;
  clamp the miter length to avoid spikes. At the endpoints use the terminal segment normal.
- **Stroke:** `strokeWidth = 1.5`, the domain colour, `fill = none`.
- **Half arrow:** **one** half arrow for the whole bundle at the `to` end (multibond notation),
  the scalar size (`10 px`), on the outer stroke the barb turns to, so the barb stays clear of
  the other strokes. (Revised 2026-10-29 at the user's request; one arrow per stroke read as
  extra strokes.)
- **Causal stroke:** **one** perpendicular bar across the whole bundle at the effort-in end,
  spanning `2 * (bundleHalf + 3)`. Do not draw one bar per stroke; that reads as several
  bonds.
- **Selection halo:** one halo around the centre path, not around each stroke.
- **Hit area:** the existing `interactionWidth = 18` plus the bundle width.
- **Port glyph:** N short parallel ticks at the block boundary; the port remains a single
  logical point.
- **Junction glyph:** keep the `0`/`1` letter; the incoming bundle already says "multibond".
  Optionally add a small `⟨3⟩`/`⟨6⟩` superscript in the tooltip, not on the canvas.
- **Label/badge:** the label sits above the bundle centre; the unit badge stays on the centre.
- **Frame badge:** a small `frame: body1` pill on hover/selection when the model has frames.
- **Colour:** `Planar` uses the existing `--domain-planar`; add `--domain-spatial` (a distinct
  violet/indigo) to light and dark themes. Do not reuse the reference image's green/purple
  literally; those are just domain colours.

Sketch:

```
scalar       A ───────────────────► B       1 stroke
planar       A ═══════════════════► B       2 strokes, one causal bar
spatial      A ≣══════════════════► B       3 strokes, one causal bar
```

### 7.3 Implementation

- `web/src/editor/edges/EditorEdges.tsx`: `BondEdge` branches on `multibondStrokes(data.domain)`.
  Extract `MultiBond` so the scalar path stays untouched.
- `web/src/editor/geometry.ts`:
  - `multibondStrokes(domain): 1 | 2 | 3`;
  - `offsetPolyline(points, distance)`;
  - `multibondPath(points, distance)`;
  - `bundleCausalBar(from, to, halfSpan)`.
- `web/src/editor/edges/edges.css`: `.editor-edge__multibond`, `.editor-edge__causal--bundle`.
- `web/src/editor/legend.tsx`: "2D multibond (2 strokes)" and "3D multibond (3 strokes)" keys.
- `web/src/theme/tokens.css`: `--domain-spatial` light/dark.
- `web/src/editor/geometry.ts`: `domainColor("Planar")` and `domainColor("Spatial")`.
- `connectionRules.ts`/`LibraryBrowser.tsx`: domain letters `P` (Planar) and `S` (Spatial);
  do not collide with `Se`/`Sf` letters in the library (the letter is a port badge, not a
  block name).
- `decorateFlow.ts`: pass `data-multibond-strokes`; the domain colour decorator already works.

### 7.4 Tests

- Vitest: `multibondStrokes` returns 2/3/1; `offsetPolyline` preserves the path length within
  1e-6 and puts the offsets on the correct side; causal bar spans the bundle; no NaN on a
  zero-length bond.
- Playwright: a planar model shows exactly two stroke paths per multibond and one causal bar;
  a spatial model shows three; a scalar model is unchanged. Assert
  `data-multibond-strokes` and a stable screenshot (`multibond-2d.png`,
  `multibond-3d.png`).
- Accessibility: the bond has `aria-label="Planar multibond, 3 components, 2 strokes"`; the
  legend entries are keyboard reachable.

---

## 8. Contract changes

| Schema | Change | Why |
| --- | --- | --- |
| `catalog.schema.json` | `DomainName` += `Planar`, `Spatial`; `domain.size` 3/6; `domain.components` (effort/flow unit per component); `portDecl.frame`; `catalogBlock.dimension` (`2`/`3`) optional; `blockInterface` same | The editor needs the domain, the per-component units and the frame. |
| `model.schema.json` | `DomainName` += `Planar`, `Spatial` in every enum; `subsystemPowerPort.frame`; optional `subsystemPowerPort.effortUnits`/`flowUnits` if not derived | Subsystems and models carry vector ports and frames. |
| `worker-rpc.schema.json` | Domain enums; `model.check` result gains `frames: {connId: frame}` and optional `multibond: {connId: 2|3}` | Editor badges and frame errors. |
| `diagnostic.schema.json` | Add E007 (frame mismatch), E108 (invalid inertia, not SPD), E109 (singular mass / underdetermined) | User-facing failures. |
| Fixtures | Valid: a Planar bond, a Spatial bond, a frame bridge; invalid: E007, E108, E109, torque/force mismatch | All three language test suites. |
| Generated | Run `uv run tools/gen_contracts.py`; commit pydantic + TS; never hand-edit | Single source of truth. |

No visual field is added for strokes: the editor derives it from `domain`. This keeps the
model document clean and makes the convention consistent across all renderers.

---

## 9. Validation and acceptance

### 9.1 Element tests

Every vector primitive gets:
1. a constitutive test (the relation, with a hand calculation);
2. a power-continuity test (`W_in^T V_in = W_out^T V_out`, or `V^T e = 0` for Coriolis);
3. a unit test (torque vs force, per component);
4. a causality test (the declared stroke; W201 only when expected).

Tolerances: relative `1e-9` for algebraic identities, `1e-6` over 10 s for integrated
trajectories at the stated step.

### 9.2 Design checklist mapping

| Design test | WP | Note |
| --- | --- | --- |
| `Ad`/`ad` identities, planar restriction | J-MB3 | Numeric + finite difference. |
| Power continuity through transforms and `S`; `V^T ad(V)^T P = 0` | J-MB5, J-MB8 | Random V/W and random P. |
| Spatial inertia parallel axis; free body momentum/energy; Dzhanibekov | J-MB8 | Diagonal principal inertia is enough for the flip. |
| Single pendulum, planar and spatial, existing backend | J-MB6, J-MB7, J-MB10 | Compliant joint; energy conserved. |
| Double pendulum compliance convergence as `k` grows | J-MB7 | Also symbolic `M/C/g` cross-check. |
| Fixed-base pose composition vs integrated truth | J-MB6, J-MB7, J-MB9 | No drift; gravity uses the composed pose. |
| Six-axis arm inverse/forward dynamics | J-MB10 | Inverse dynamics from the model, validated against an independent RNE helper. |
| Electric drive time constant, no-load speed, power | J-MB12 | Locked/free joint. |
| Reaction wheel momentum, torque cancellation | J-MB12, X-MB4 | Gravity off/on. |
| Pyramid null vector `[1,-1,1,-1]` | X-MB5 | Requires drives + spatial. |
| Contact rest `f_n=mg`, slope stick/slide | J-MB13 | Compliant contact only. |
| Contact vs SwitchedJoint on an edge | J-MB14, X-MB5 | **Optional**. |
| Impact map momentum/energy | J-MB14 | Use `V+ = S (S^T M S)^-1 S^T M V-`; test `S^T M V+ = S^T M V-` and non-increasing KE. |
| Floating-base screw motion, quaternion norm | J-MB8 | Analytic constant-twist reference; `ManifoldProjection`. |
| Energy diagnostic zero to integrator order | X-MB1, X-MB6 | Post-processing helper; live monitor later. |

### 9.3 Gates

- **Gate A (vertical slice):** `Ground -> Revolute2D -> RigidBody2D` runs from the worker; the
  pendulum period is within 1e-3; energy is constant; the editor shows two strokes; all
  existing suites are green.
- **Gate B (planar):** double pendulum compliance convergence; 2-link arm checks; no
  unexpected W201; 2-stroke screenshot stable; fixed-base pose composition matches integrated
  truth.
- **Gate C (spatial):** six-axis arm inverse dynamics; free-body/Dzhanibekov; 3-stroke
  screenshot; quaternion norm; step time recorded (no real-time gate).
- **Gate D (drives):** the four drive checks; reaction-wheel momentum.
- **Gate E (contact):** dropped body, slope, pyramid sequence; optional switched comparison.

Do not merge a gate with a red previous gate. Fix it in a `FIX-MB-n` WP.

---

## 10. Risks and mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Frame typing balloons into a type-system rewrite | High | D-MB5 metadata-only v1; E007 equality; defer `SE3{:a,:b}`. |
| Rigid joints create a high-index DAE that MTK cannot solve, or solve slowly | High | Use compliant joints for the target models (D-MB7); if a rigid joint is required, test `mtkcompile` early and report the limit. No custom backend. |
| The six-axis arm is slower than the design's <1 ms target | High | Drop the target (D-MB13); record measured step time; reduce the model or accept offline simulation. |
| Quaternion drift / projection breaks accuracy or events | Medium | `ManifoldProjection` spike; compare to the analytic constant-twist screw motion on a floating base; only floating bases integrate. |
| Per-component units become a checker rewrite | Medium | Component-wise loops in primitives; `DimsVec` only for the port field, not the whole language. |
| Composites cannot express a joint's signal path | Low | J2.6 already supports signal `@connections` and `@inputs`/`@outputs`; verify with a probe; fall back to a native joint block if needed (record the deviation). |
| Variable-arity attachments are needed immediately | Medium | D-MB4 one port + external transforms; add generated templates later. |
| Full inertia is needed before the arm works | Medium | Principal-axis links; add `IGeneral` (full `Mat`, validated inverse) when a real model needs it. |
| Contact stiffness causes event floods / solver failure | Medium | Implicit solver, Hunt-Crossley damping, `tanh` friction, event limit W206; goldens use ramps. |
| SwitchedJoint/impact is wrong or unstable | High | Treat J-MB14 as optional; derive and unit-test the mass-matrix projection independently before wiring the event; check momentum and energy. |
| 2/3-stroke bundles hurt canvas performance | Low | Memoized offset paths; only multibond edges pay; measure with the 7.5 perf harness. |
| Contract churn blocks three lanes | Medium | C-MB1 first; one `CONTRACT-MB` WP for any late change; generated files committed. |
| Energy diagnostic becomes a second model | Medium | Post-process recorded signals; do not add a parallel state model. |

---

## 11. Recommended landing path

### First three PRs (the vertical slice)

1. **C-MB1 + J-MB1 + J-MB2**: contracts, `Power{Planar}`, frame metadata, component units.
   No physics yet. Acceptance: a model with a Planar bond checks; a mismatched frame gives
   E007; a torque/force mismatch gives E006; catalog/TS/pydantic regenerated.
2. **J-MB3 + J-MB4**: Lie core + `IPlanar` (with `P` output), `SePlanar`, `SfPlanar`,
   `GroundPlanar`, `TFAd`, `FixedTransform2D`, `CoriolisPlanar` (`P` input), `ComposePose2D`,
   `DfPlanar`; a pendulum runs through `run.start` with a composed fixed-base pose.
3. **W-MB1 + X-MB1**: 2-stroke renderer and the pendulum example; screenshot and period
   checks.

Only after Gate A: Phase B (full planar), then Phase C (spatial). Do not start Phase C in
parallel with the planar gate; the frame/unit decisions will still be moving.

### Integration into the main plan

- This is **M3**, with the WP table of section 6. It runs after M2 and before M4 (debugging)
  and M5 (3D visualization). The Julia foundation (Phase A) can start as soon as M2 is green:
  it depends on the compiler, not on the viewer or the debugger. The editor visual (W-MB1)
  depends on C-MB1, not on M4/M5.
- Add the visual rule to the plan's section 7.3 (visual language) and to the legend.
- Record the decisions D-MB1..D-MB13 in `plan/STATUS.md` and the ADR.

### What not to do

- Do not add a second `MultiPort` abstraction next to `Power{Domain}`.
- Do not promise fixed-step/no-allocation or <1 ms on the existing backend.
- Do not implement full dependent frame types before the frame-metadata slice ships.
- Do not build `SwitchedJoint` before the corrected impulse projection and its momentum/energy
  tests exist.
- Do not implement a full 6x6 inertia in the first `I` primitive; diagonal CoM inertia proves
  the pipeline and the tests.

---

## 12. Out of scope (keep the door open)

- Flexible bodies, non-holonomic wheels, finite-element contact, general DAE index reduction.
- Full `SE3{:a,:b}` / `Twist{:i,:j,:k}` dependent frame typing and frame arithmetic.
- Variable-arity power ports and user-defined parameterized subsystem generators (v1 uses
  one body port + external transforms; a template generator is a later WP).
- Real-time PREEMPT_RT deployment, fixed-step export, C ABI, no-allocation guarantees.
- A custom articulated-body backend and the design's <1 ms/fixed-step targets.
- A general model-level constraint/impulse engine beyond the single-pivot `SwitchedJoint` of
  J-MB14.
- A general `JointSpace{n}` power domain (v1 uses one scalar port per axis, domain from the
  screw).
- The 3D scene viewer (M5) is a separate feature; this plan's "3D" is the multibond schematic.
