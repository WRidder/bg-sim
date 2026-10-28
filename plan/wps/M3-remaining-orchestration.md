# M3 remaining orchestration (after Gate B)

Gate B is the last gate before Phase C. This note is the orchestrator's execution order and the
known constraints each implementer must be told; the WP text in `plan/MULTIBOND_PLAN.md` section
6 remains authoritative for scope.

## Order and parallel windows

| Step | WPs | Notes |
| --- | --- | --- |
| C1 | **J-MB8** (spatial primitives) + **W-MB2** (3-stroke web) in parallel | disjoint paths: `stdlib/multibond/` + `src/mech/` vs `web/src/editor/`. Julia agent runs the full `Pkg.test()`; web agent runs typecheck/lint/vitest/build. |
| C2 | **J-MB9** (spatial composites) | after J-MB8; owns `stdlib/spatial/` (new). Reviewer required (Lie/frames/units). |
| C2b | **J-MB11** (drives) can start after C1 if the Julia machine is free | depends only on J-MB6; owns `stdlib/drives/` (new), disjoint from J-MB9. Prefer not to run two full `Pkg.test()` at once; targeted tests may overlap. |
| C3 | **J-MB10** (six-axis arm + RNE) | after J-MB9; owns `test/golden/spatial/`. Reviewer required (solver/index). |
| C4 | **X-MB3** (3D arm example) | after J-MB10 + W-MB2; owns `examples/robot-arm-3d/`. |
| D | **J-MB12**, **X-MB4** | J-MB12 after J-MB11; X-MB4 after J-MB12 + J-MB9. |
| E | **J-MB13**, **J-MB14**, **X-MB5** | J-MB13 after J-MB9; J-MB14 after J-MB13 (impact reviewer); X-MB5 after J-MB12/J-MB13. |
| F | **J-MB15**, **W-MB3**, **X-MB6**, **C-MB2** | J-MB15 after J-MB10; W-MB3 after W-MB2; X-MB6/C-MB2 last. |
| G | Gate C, Gate D, Gate E, section 10.3 integration gate | `uv run tools/check.py --lane all` at each gate; record measured numbers in `plan/STATUS.md`. |

## Constraints to repeat in every Julia prompt

- No new solver backend; MTK/OrdinaryDiffEq only; compliant joints default; rigid only through
  MTK DAE/index reduction; record the diagnostic set, not "zero W201", where rigid.
- `Power{Planar}`/`Power{Spatial}` only; no second multibond port type. Per-component units:
  write `p.e[k]`/`p.f[k]` component-wise; torque and force must never share a unit.
- Frames: identity is by unqualified name (DEC-MB-1). Instance scoping is deferred and planned
  in `plan/wps/M3-frame-scoping.md`; do **not** change the frame semantics in J-MB8/J-MB9.
- Joints: one scalar port per axis, domain from the screw. The compliant-pivot transport term
  uses the **absolute** `child.f[1]` (FIX-MB-5); the prismatic axial rate carries
  `+ parent.f[1]*d` (J-MB7). Do not reintroduce the relative-rate bug.
- Read `julia/BGSim/NOTES.md` before touching MTK APIs; use the planar blocks as templates.
- No TODOs/stubs/`@test_broken`/skipped tests/weakened assertions; every new behaviour gets a
  test that fails without it; algebraic 1e-9, integrated 1e-6 over 10 s.
- Do not edit `plan/STATUS.md`, do not commit, do not run state-changing git commands.

## J-MB8-specific risks

- **Manifold projection.** D-MB6 asks for a `ManifoldProjection` on the floating-base quaternion.
  The flat IR/`simulate` has no manifold-callback seam. First probe whether `lower_flat`/`simulate`
  can attach one; if not, integrate the quaternion with the tangent-space RHS
  (`qdot = 0.5 q ⊗ [0,ω]`, which already has `q·qdot = 0`) and test the norm drift to solver
  tolerance. Record this as a deviation; do not add a new backend or silently skip the test.
- **Spatial inertia.** Use the diagonal principal `J` + `m` at the body origin (D-MB6/F7 v1);
  the Coriolis element takes `P`, not `M`. A full `IGeneral` is deferred.
- **Pose composition.** Fixed-base link poses are algebraic (`ComposePose3D`); only the floating
  base integrates. Test composed vs integrated truth on the same twist.
- **6x6 transforms.** `TF`/`GY` take `Mat{6,6}`; `MTF`/`MGY` are the modulated variants. Power
  continuity `a.e·a.f + b.e·b.f = 0` and `Vᵀ ad(V)ᵀ P = 0` on random data.
- **Dzhanibekov.** Diagonal principal inertia is enough; the free body must show the flip and
  conserve world angular momentum and energy.
