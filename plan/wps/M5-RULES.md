# M5 sub-agent rules (read first)

These rules apply to every M5 sub-agent. The work package text in `plan/IMPLEMENTATION_PLAN.md`
section 10 ("M5") is authoritative for scope; this file is authoritative for process and for the
orchestrator decisions below.

## Repo and toolchain

- Repo `D:\bg-sim`, Windows 11, PowerShell by default (Git Bash available). Keep LF line endings.
- Julia 1.13.2 through juliaup. Always `julia --project=julia/BGSim ...`. Never add packages to
  the global environment. Read `julia/BGSim/NOTES.md` before any Julia/MTK work.
- Python only through `uv run ...`; dependencies only through `uv add`. There is no system Python.
- Node/npm only inside `web/`. Dependencies are pinned exactly (plan 7.1); add one only if the WP
  needs it (e.g. `@axe-core/playwright` in W5.4), pinned exactly, and say so in the report.
- Never guess a third-party API (Babylon, MTK, FastAPI, trimesh, ...): check the installed
  `.d.ts`/source or write a ten-line probe first.
- The 3D viewer reference `D:\CtrlX Agentic Machine Control\framework\hmi\src\viewer\` is
  **read-only**. Copy from it as plan 7.6 says; never modify it.

## Binding documents

1. `CLAUDE.md`
2. `plan/IMPLEMENTATION_PLAN.md` sections 0.2, 1, 2, 3 (data shapes), 7 (web) and the 9.x
   section of your example; section 10 "M5" for your WP.
3. `spec/Modeling Language Spec v0.1.md`, section "Visualization and bindings" for every M5 WP,
   and the whole spec for any WP that writes model/block code.
4. `contracts/schemas/bindings.schema.json`, `stream-handshake.schema.json`, `model.schema.json`
   (`scene`, `bindings`).
5. This file.

## Orchestrator decisions for M5

- **DEC-M5-1 (user, 2026-10-29): M5 runs before M4.** W5.3 depends on W4.3, which does not
  exist yet. W5.3 does everything except the debug pause marker; the marker moves to W4.3.
  Do not add stubs or placeholder hooks for M4.
- **DEC-M5-2: `examples/robot-arm-3d/` is shared.** It already holds the M3 multibond six-axis
  arm (X-MB3: `models/arm.bgmodel.json`, `library/ArmPD6.jl`, its `expected.json` checks and
  `web/tests/e2e/robot-arm-3d.spec.ts`). X5.3 **adds** the plan 9.8 RRR equation-block arm as new
  models/library files next to it and extends `expected.json` additively. The existing model,
  checks and spec stay byte-identical and green. A six-axis arm cannot follow an RRR motion, so
  "matches the M3 multibond arm on the same motion" means: an RRR counterpart of the same
  geometry built from the M3 spatial stdlib (`stdlib/spatial`, `stdlib/multibond`, the patterns of
  `arm.bgmodel.json`) in the same example, driven by the same torque/controller, compared joint
  by joint with a tolerance justified by the joint compliance.
- **DEC-M5-3: `examples/cube-3d/` comparison.** The M3 cube (`examples/cube-pyramid-3d`,
  `examples/reaction-wheel-3d`) uses a 4-wheel pyramid and contacts, not the plan 9.9 three
  axis-aligned wheels. X5.4 builds the multibond counterpart (compliant spherical pivot at the
  corner, rigid cube body, three body-axis `ReactionWheel` drives, same parameters) inside
  `examples/cube-3d/` and compares the two on an overlapping motion, with a compliance-justified
  tolerance.
- **DEC-M5-4: X5.1 covers every example that exists before M5** (M1, M2 and M3), because the M3
  3D cross-checks were deferred to "M5, where the viewer exists" (plan 9.10).
- **DEC-M5-5: scene files** live at `examples/<name>/scenes/<name>.sdf` (more than one per example
  is fine), referenced by each model's `scene.file` (`"scenes/<name>.sdf"`) with the model's
  `bindings`. Prefer SDF primitives; GLB meshes go under `examples/<name>/meshes/`.
- **DEC-M5-6: shared files.** Edits outside `Owns` are allowed only here, and only additively
  (re-read the file immediately before each edit; another agent may be editing it):
  - `web/src/app/BottomDock.tsx`: W5.1 mounts the viewer in the existing `viewer` tab body only.
  - `web/playwright.config.ts`: append a real-worker spec to the fake-pass `testIgnore` list.
  - `tools/check.py`: append a real-worker spec to the real-worker Playwright list.
  - `examples/run_checks.py`: add a new check kind (one new function plus one `elif`); never
    change an existing kind's behaviour.
- **DEC-M5-7: e2e ports.** Parallel agents must not share a backend. Always run Playwright with
  `BGSIM_E2E_PORT` set to your WP's port: W5.1 8771, X5.2 8772, X5.3 8773, X5.4 8774,
  W5.2 8775, W5.3 8776, X5.1 8777, W5.4 8778, P5.1 8779. Real-worker specs also need
  `BGSIM_E2E_REAL=1`. `examples/run_checks.py` picks a free port itself.

## Non-negotiable engineering rules

- Touch only your WP's `Owns` paths, new test files next to them, and DEC-M5-6 additions. If a
  change elsewhere is genuinely required (including any contract/schema change), stop and report
  it instead of editing.
- No TODOs, stubs, placeholders, skipped tests, `test.skip`/`@test_broken`, weakened assertions,
  or try/catch that hides a failure. "Done" means the acceptance commands pass because the
  feature works.
- Diagnostics use the contract of plan 3.4 and tell the user what to do next.
- Every new behaviour gets a test that would fail without it.
- Match the style of the surrounding code (naming, comment density, file layout).
- Do not edit `plan/STATUS.md`, do not commit, and do not run state-changing git commands.

## Test commands

- Web (inside `web/`): `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`;
  Playwright `npx playwright test <spec>` (build first: the backend serves `web/dist`).
- Python: `uv run pytest backend/tests -q`, `uv run ruff check backend`.
- Contracts: `uv run tools/gen_contracts.py`, then the contract tests (orchestrator approval first).
- Julia: `julia --project=julia/BGSim -e "using Pkg; Pkg.test()"` only if you changed Julia code.
- Examples: `uv run examples/run_checks.py --only <example>`.
- Only the orchestrator runs `uv run tools/check.py --lane all`.

## Report format (max 15 lines)

```
WP: <ID>
Files: <added/changed>
Decisions: <one line each>
Deviations: <none, or what and why>
Commands: <exact command> -> <exact result (counts, numbers, pass/fail)>
Measured: <the numbers the WP asks for>
Open: <anything the next WP must know, or none>
```

Paste real command output numbers. Do not claim a command passed without running it.

## Process hygiene (added during M5)

- Any backend (`uv run bgsim`) or Julia process you start yourself must be stopped with
  `taskkill /PID <pid> /T /F` before you report. Killing only the `uv` wrapper leaves the server and
  its Julia worker (≈ 0.5–2 GB each) running; leaked backends used 22 GB during wave 2.
