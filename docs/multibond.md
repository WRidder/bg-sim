# Multibond mechanics (2D and 3D)

This page is the user-facing summary of milestone M3. The binding sources are
`plan/MULTIBOND_PLAN.md` (decisions D-MB1..D-MB13), `plan/adr/ADR-MB1-multibond.md` (the
contract shapes) and `julia/BGSim/NOTES.md` (the solver probes). Everything here runs on the
one existing pipeline (ModelingToolkit, OrdinaryDiffEq); there is no articulated-body
backend.

## 1. The stroke convention

A bond is drawn with a number of parallel strokes that encodes the **model dimension**:

| Port domain | Components `D` | Strokes | Examples |
| --- | --- | --- | --- |
| Electrical, Translation, Rotation, Hydraulic, Generic | 1 | 1 | every scalar bond graph |
| `Planar` (2D) | 3 (`[omega; vx; vy]`) | **2** | `IPlanar`, `Revolute2D`, `RigidBody2D` |
| `Spatial` (3D) | 6 (`[omega; v]`) | **3** | `ISpatial`, `Revolute3D`, `RigidBody3D` |

Why the count is not `D`: a planar port has three components but is a 2D object, and a spatial
port has six but is a 3D object. The stroke count says "2D" or "3D" at a glance, as in the
reference drawing where the 2-stroke `MGY` bond sits next to a 1-stroke `GY` bond. The count
is derived from the connection's domain (D-MB12); there is no stroke field in the model file,
and the connection kind stays `bond`.

What a multibond looks like on the canvas:

- the routed polyline is offset by +-`gap` (4.2 px) per stroke, mitred at the waypoints; one
  half arrow for the whole bundle at the `to` end, on the outer stroke the barb turns to;
- **one causal bar** across the whole bundle at the effort-in end (11.7 px at 2 strokes,
  15.9 px at 3), never one bar per stroke (that reads as several bonds);
- one selection halo around the centre path, one unit badge, and a frame pill
  (`frame: body`) on hover or selection;
- a port shows 1, 2 or 3 short ticks at the block boundary (it stays one logical point);
- one mechanics colour `--domain-mechanics` for both (`--domain-planar`/`--domain-spatial`
  alias it): 2D vs 3D is the stroke count and the letter superscript (TF², I³); the legend has
  one "Mechanics (2D/3D)" chip and the keys
  "2D multibond (2 strokes)" and "3D multibond (3 strokes)", reachable by keyboard.

Accessible names (the strings the Playwright and vitest specs assert):

| Element | `aria-label` |
| --- | --- |
| Planar bond | `Planar multibond, 3 components, 2 strokes` |
| Spatial bond | `Spatial multibond, 6 components, 3 strokes` |
| Port glyph | `Planar multibond port p, 3 components, 2 strokes, frame body` |

Each stroked group carries `data-multibond-strokes="1|2|3"`. A concrete domain is never
replaced by a different one or by `Generic` after a check result (the `consistentDomain`
guard), so a check cannot change the stroke count. A scalar port on a multibond junction is
**E102**; Planar and Spatial never share a bond island.

Screenshots (existing Playwright snapshots, regenerated only by the specs):

- `web/tests/e2e/multibond.spec.ts-snapshots/multibond-2d-chromium-win32.png` (2 strokes)
- `web/tests/e2e/multibond.spec.ts-snapshots/multibond-3d-chromium-win32.png` (3 strokes)
- `web/tests/e2e/multibond-pendulum.spec.ts-snapshots/multibond-pendulum-chromium-win32.png`
- `web/tests/e2e/robot-arm-2d.spec.ts-snapshots/robot-arm-2d-chromium-win32.png`
- `web/tests/e2e/reaction-wheel-2d.spec.ts-snapshots/reaction-wheel-2d-chromium-win32.png`

## 2. Per-component units

The unit checker is scalar, so a vector port keeps torque and force distinct by recording each
component with its own unit (D-MB10). The catalog gives every Planar and Spatial domain exactly
the component arrays below, and a subsystem power port exposes the same arrays.

| Domain | Effort | Flow |
| --- | --- | --- |
| Planar | `["N*m", "N", "N"]` | `["rad/s", "m/s", "m/s"]` |
| Spatial | `["N*m","N*m","N*m","N","N","N"]` | `["rad/s","rad/s","rad/s","m/s","m/s","m/s"]` |

Ordering is angular first (D-MB2): twist `[omega; v]`, wrench `[m; f]`. Signals are recorded per
component, `Body/p.e[1]`, `Body/p.f[2]`, and `Body/p.P` is the scalar power
`sum_k e[k] f[k]` in W. Write vector elements component-wise (torque and force never share a
unit slot). The per-component units belong to the **port**. A vector *signal* (the `u` of
`SeSpatial`, the `y` of `DeSpatial`, a pose or twist) has one `unit` in the catalog; it is
`null` when the elements differ, and the catalog carries no per-element signal units (ADR-MB1,
"M3 final").

## 3. Frames

Frames are metadata (DEC-MB-1, D-MB5), carried by `@ports p::Power{Spatial}, [frame = "body"]`
and by subsystem power ports.

- **Face-scoped identity.** Two ports are in the same frame when the frame names match, except
  that the frames claimed through the faces of two different composite or subsystem instances
  (for example `RigidBody2D`/`RigidBody3D`) always differ unless the name is `world`; a
  frame-neutral port (no `frame`) unifies with whatever it touches. Through bonds, wires and
  junctions the compiler runs a union-find over ports.
- **E007** is reported when two different named frames meet. The diagnostic names both ports
  (`path` and `related`) and the connection, e.g. a direct `GroundSpatial(world) -> ISpatial(body)`
  bond, and a direct `Body1.p`-`Body2.p` bond between two body composites. Two plain primitive
  ports that both name their frame `body` would still pass a direct bond (the documented
  residual false negative), so give each body's primitives a distinct frame name.
- **Transforms and joints are the only bridges.** `FixedTransform2D/3D`, `FixedTransform3DNeutral`,
  `JointTransform2D/3D`, `TFAd` and the joints keep their two sides as separate frame unions,
  so `a` adopting one body frame and `b` another is legal. A subsystem port's frame is
  authoritative for the exposed port; it can differ from the internal port only through an
  internal transform that is connected.
- **`model.check.frames`** (required in the check result) lists the frame of every multibond
  port as `{path}/{frame}` for display; `model.check.multibond` reports the stroke counts. The
  editor shows the pill on hover and the connection inspector explains an E007.

## 4. Poses and joints

Only a **floating base** integrates a pose (D-MB6): 2D angle plus position
(`PoseIntegrator2D`), 3D quaternion plus position with the first-integral norm
(`PoseIntegrator3D`, `Free2D`/`Free3D`). A fixed-base link composes
`g_child = g_parent o g(q)` with `ComposePose2D/3D`, `JointPose2D` and `LocalPose2D/3D`, so no
pose is a state. The 3D pose chart is `(qw, qx, qy, qz, x, y, z)`, quaternion first.

**Compliant joints are the default** (DEC-MB-2): a rigid joint on a 3-DOF body is index 3 and
needs MTK index reduction (`Revolute2DRigid` ships with a documented W201 set), so the joints
carry a stiff spring on the constrained complement (`kt`, `kr`) and a damper (`bt`, `br`).
Variants are separate blocks (D-MB9): `*Compliant`, `*Friction`, `*Limit`.

Spatial joint conventions (`stdlib/spatial/`: `Revolute3D`, `Prismatic3D`, `Helical3D`,
`Cylindrical3D`, `Universal3D`, `Spherical3D`, `Planar3D`, `Free3D`):

- **Axis = local z of the joint frame.** The joint has a fixed structure; the physical axis is
  set by the placement transform in front of it (`FixedTransform3D*`), not by a parameter. The
  chain loader (section 8) computes that placement as the rotation taking local z onto the
  requested axis.
- **Placement transforms** are the parent->joint and joint->child constant poses; DH-style
  chains are placed with `FixedTransform3DNeutral` and the link poses are algebraic.
- **Compliant complement.** The directions the joint does not allow carry integral deflection
  states `dtheta` (rotation) and `dl` (translation), and the free direction exposes one scalar
  drive port per axis (`Rotation` for a revolute, `Translation` for a prismatic; D-MB8).
- **Exact deflected chart.** The pose that feeds both adjoints and gravity is the exact pose
  of the deflected joint (closed-form chart Jacobian and its transpose, Gibbs-vector
  deflection), with the child's absolute rate in the transport term. The first-order chart
  leaked energy as O(1/k); the exact chart makes the drift 3.6e-12..1.1e-10 of the swing for
  k = 1e5..1e9 (theory review in `julia/BGSim/NOTES.md`, J-MB9).
- `Spherical3D` and `Free3D` carry relative body-frame twist components and integrate a
  relative quaternion; planar joints are in `stdlib/planar/` with the same variants.

## 5. Drives

`stdlib/drives/` (catalog group Drives) holds composites of existing primitives only:
`ElectricDrive`, `CurrentControlledDrive`, `Gearbox` and `ReactionWheel`. A drive is a
DC motor whose shaft is a `Rotation` port. `ElectricDrive` is voltage driven (`R_w`, `L`, `k_t`,
`J_m`, `b_m`; outputs `i`, `w`, `tau`, `P_el`, `P_mech`); `CurrentControlledDrive` is current
driven (`k_t`, `J_m`, `b_m`; outputs `i`, `w`, `tau`, `tau_m`, `P_mech`). `ReactionWheel`
has a housing `Rotation` port and a back-EMF on the *relative* rate, so the stator reaction
acts on the body that carries the wheel and the total angular momentum is conserved.
Language limits found while building them: a composite port or input is exposed by only one
`connect`; composite component parameters are bare names; composite outputs record under inner
paths (`Drv/isense/y`); a rotor rigidly coupled to a rate-imposing joint is derivative-causal
(W201), so couple through an `ElasticShaft` or lump `J_m`.

## 6. Contact

`stdlib/contact/`: `ContactSurface` (a port-less plane: origin, normal, heading) and
`ContactPoint` (smooth Hunt-Crossley normal force `k x sqrt(x/xref) (1 + c xdot)` with a smooth
no-pull clamp, two regularised-Coulomb tangents, wrench `[0; R^T F]`, power consistent). The
Hertz exponent is fixed at 3/2. Mount the contact on the `a` side of the transform; the port
flow is then minus the point twist. Contact is a compliant penalty model: it stores and
dissipates behind one port, so the energy ledger (section 9) classifies it as `mixed`.

## 7. Switched pivot and impact map (v1 limits)

`SwitchedPivot3D`, `ImpactInertia3D` and `ImpactBody3D` (`src/mech/impulse.jl`) model a body
that pivots about a corner, an edge or a face. The pivot integrates a quaternion and position
like `Free3D`, holds directions through deflection states times 0/1 mode masks, and a damper on
lagged velocities (tau = 1e-4 s) keeps the force exactly zero across the switch. The impact map
`SᵀMV⁺ = SᵀMV⁻`, `CᵀV⁺ = 0` is evaluated with `pivot_inertia = AdᵀMcAd` and applied by an event
that reinitialises the momentum. v1 limits:

- the impact map applies only to bodies built with `ImpactBody3D`, sharing the guard input
  `sw` and `mode_new` with the pivot (no cross-block reinit);
- pivot axes are parallel to the principal axes, and the edge mode is the pivot-z hinge;
- the event solve needs tight tolerances (reltol of the 1e-10 class);
- an impact removes kinetic energy: the energy ledger flags it as a jump, which is correct.

## 8. The chain loader

`src/library/chain_loader.jl` (exported from `BGSim`) turns a joint chain into a model
fragment. `LinkRecord`, `JointRecord` and `JointChain` map one to one onto SDF `<link>`,
`<inertial>`, `<joint>`, `<pose relative_to>` and `<axis><xyz>` (SDF parsing itself is M5).
`load_chain` emits typed joints (or the `*Limit` variant), `RigidBody3D` bodies, the algebraic
pose chain, exposed drive ports and consistent starting deflections from the Newton-Euler
wrench; `chain_model` wraps it into a model; `lumpInto` merges a fixed child into its parent
(parallel axis, re-diagonalised, principal axes carried in the record). `inverse_dynamics` and
`gravity_compensation` use the 6-vector spatial recursion for trees with revolute, prismatic
and fixed joints. A fixed joint must be lumped first (a transformer between two rigid bodies
is W201), and a chain has a single root joint.

## 9. Energy ledger (`tools/energy_balance.py`)

Post-processing of a finished run (manifest + `columns.f64`); there is no second model.

```
uv run tools/energy_balance.py <project>/runs/<run-id> --tol 1e-6 [--stored stored.json]
                               [--override 'Gear*=conversion'] [--json ledger.json] [--strict]
```

Every power port records `<path>/<port>.P` (power into the element). The ledger integrates the
sum of an element's ports with the trapezoid rule on the solver grid and groups the elements:

| Class | Elements | `W = integral P dt` is |
| --- | --- | --- |
| storage | I, C, bodies (inertia, Coriolis, gravity), compliant joints, shafts | energy gained |
| dissipation | R-type, dampers, orifices | heat produced |
| source | Se/Sf/MSe/MSf, ground, voltage/current/torque sources | minus the energy delivered |
| mixed | contact, hard stop, spring-damper | stored plus dissipated |
| conversion | TF, GY, transforms, fixed joints, EM converters | 0 |
| measure | De, Df, sensors | 0 |

Classification comes from the model: the manifest names the model and each signal's owning
instance path, `<project>/models/<model>.bgmodel.json` maps the path to a block ref, and
composites are resolved through their `@components` in `julia/BGSim/stdlib` or the project
`library/`. `--override GLOB=CLASS` (instance-path globs, first match wins) takes precedence.

Checks (all relative to the throughput `1/2 sum integral |P| dt`):

- **Tellegen residual** `sum_all integral P`: every bond has opposite power at its two ends,
  so this is zero to round-off; it catches a recorder or classification inconsistency.
- With stored-energy terms: the **storage balance** `E(t) - E(0) - integral P_storage` and the
  **supply balance** `E(t) - E(0) + integral (P_source + P_dissipation + P_mixed)` (this is
  `Delta E - integral (P_in - P_diss)`), taken at every sample. These are the checks that fail
  when the energy expression or the model is wrong; they close to the trapezoid order of the
  output grid. A damper inside a compliant joint is part of `storage`, so its heat shows up
  as a (small) balance residual: that is real dissipation the stored-energy expression does
  not contain.

In `examples/run_checks.py` the kind `energy_ledger` calls the same code
(`"stored_from": "energy"` reuses the model entry's `energy` check, `"stored_spec"` inlines
one, `"stored"` lists terms, `class_totals` pins a class total).

## 10. The M3 examples

| Example | What it proves |
| --- | --- |
| `examples/multibond-pendulum-2d` | Gate A: the planar vertical slice. Compliant-pivot `Revolute2D`, `IPlanar` + `GravityPlanar` + `CoriolisPlanar`; period 1.4187960318 s vs the amplitude-corrected physical value (2.8e-10), energy drift 7.2e-12 of the swing over 10 s, 2-stroke visual. |
| `examples/robot-arm-2d` | Planar multi-body chain: two `Revolute2DCompliant` joints, composed poses = analytic forward kinematics (1.1e-16 m), 1 ms PD + gravity feedforward, free-arm energy budget, torque limits. |
| `examples/reaction-wheel-2d` | Planar balancer with a reaction wheel: recovery from 0.01 rad, wheel spin-up, angular momentum conserved with gravity off (8.8e-8). |
| `examples/reaction-wheel-3d` | Spatial reaction-wheel stack on a `Spherical3D` pivot: four tilted wheels, null-space allocation tap, world angular momentum constant with gravity off, d/dt H = gravity torque with gravity on, 3-stroke bonds. |
| `examples/robot-arm-3d` | UR5-like six-axis arm: DH placement with `FixedTransform3DNeutral`, six compliant `Revolute3D` joints (axis = local z), `RigidBody3D` links, a 1 ms PD firmware with gravity feedforward and torque limits, TCP pose composed with `ComposePose3D`. Its geometry is the J-MB10 reference that the chain loader (J-MB15) reproduces. |
| `examples/cube-pyramid-3d` | Floating cube with four pyramid wheels and vertex contact: scripted face -> edge -> corner sequence, and the contact vs `SwitchedPivot3D` comparison on the edge phase. |

Run all example checks (starts a backend with the real worker):

```
uv run examples/run_checks.py                       # every example
uv run examples/run_checks.py --only multibond-pendulum-2d,robot-arm-2d,reaction-wheel-3d
```
