# M3 sub-agent rules (read first)

These rules apply to every M3 sub-agent (implementer, verifier, reviewer). The work package
text in `plan/MULTIBOND_PLAN.md` section 6 is authoritative for scope; this file is
authoritative for process.

## Repo and toolchain

- Repo `D:\bg-sim`, Windows 11, PowerShell by default (Git Bash available). Keep LF line endings.
- Julia 1.13.2 through juliaup. Always `julia --project=julia/BGSim ...`. Never add packages to
  the global environment; add to the project with `Pkg.add` only when the WP needs it, and say
  so in the report.
- Python only through `uv run ...`; dependencies only through `uv add`. There is no system
  Python.
- Node/npm only inside `web/`.
- Read `julia/BGSim/NOTES.md` before any Julia work: its probe results are the authority for
  ModelingToolkit/SciML APIs (MTK is v11 here: `System`, `mtkcompile`, one merged
  operating-point map). Never guess a third-party API: check the installed source or write a
  ten-line probe first.

## Binding documents

1. `CLAUDE.md`
2. `plan/MULTIBOND_PLAN.md` — the whole file. Decisions D-MB1..D-MB13 in section 4 are frozen.
3. `plan/IMPLEMENTATION_PLAN.md` sections 0.2, 0.3, 1, 2, 3 and (for Julia) 5.
4. `spec/Modeling Language Spec v0.1.md` — for anything that touches the language.
5. `plan/wps/M3-RULES.md` (this file).

## Non-negotiable engineering rules

- Touch only the paths listed in your WP's `Owns`, plus **new** test files next to them.
  Read anything. If a change outside `Owns` is genuinely required, stop and report it instead
  of editing.
- No TODOs, no stubs, no placeholder implementations, no `@test_broken`, no skipped tests, no
  weakened assertions, no try/catch that hides a failure. "Done" means the acceptance commands
  pass because the feature works.
- Errors must point at user code: every diagnostic uses the contract of plan 3.4 and names the
  instance path, source range and, where it applies, the hint that tells the user what to do.
- Every new behaviour gets a test that would fail without it. Algebraic identities: relative
  1e-9. Integrated trajectories: 1e-6 over 10 s at the stated solver settings.
- Keep the existing style of the files you touch (naming, docstrings, comment density).
- Do not edit `plan/STATUS.md` (the orchestrator owns it), do not commit, and do not run
  `git` commands that change state.
- Do not add a solver backend. The only backend is the existing MTK/OrdinaryDiffEq pipeline.
  Compliant joints are the default; rigid joints are allowed only through MTK DAE/index
  reduction.
- Use `Power{Planar}` / `Power{Spatial}`. Do not introduce a second multibond port type.
- Torque and force never share a unit: write vector elements component-wise so the scalar
  checker sees each component's own unit.

## Test commands

- Targeted Julia test (fast, use while working):
  `julia --project=julia/BGSim -e "using BGSim; include(\"julia/BGSim/test/<file>.jl\")"`.
  If the test file needs the shared helpers at the top of `test/runtests.jl`, run
  `julia --project=julia/BGSim -e "using Pkg; Pkg.test()"` instead.
- Full Julia suite (must be green before you report):
  `julia --project=julia/BGSim -e "using Pkg; Pkg.test()"` (about 4 minutes).
- Python: `uv run pytest backend/tests -q` (add `-k` for a subset while working).
- Web: `npm run typecheck`, `npm run lint`, `npm test -- --run`, `npm run build` inside `web/`.
- Playwright: `npx playwright test <spec>` inside `web/`.
- Contracts: `uv run tools/gen_contracts.py` then `uv run pytest backend/tests/test_contracts.py -q`
  and `npm test -- --run src/contracts` inside `web/` when the contracts change.
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

Paste real command output numbers (test counts, measured values). Do not claim a command passed
without running it.

## Verifier and reviewer roles (read-only)

- A verifier re-runs the acceptance commands on the committed working tree, inspects the diff
  for stubs/weakened tests, and reports exact results. It does not modify files.
- A reviewer checks the physics/mathematics against the plan and the spec (formulas, frames,
  units, signs, power continuity, tolerances) and reports findings with file:line references.
  It does not modify files. Findings are fixed by the implementer, not the reviewer.
