# M4 sub-agent rules (read first)

These rules apply to every M4 sub-agent. The work package text in `plan/IMPLEMENTATION_PLAN.md`
section 10 ("M4") is authoritative for scope; this file is authoritative for process and for the
M4 lead's decisions below. They adapt `plan/wps/M5-RULES.md` to M4.

## Repo and toolchain

- **Work only inside the M4 worktree** `D:\bg-sim\.claude\worktrees\agent-a3738458a52358d89`
  (branch `m4`). Never read-modify-write, run git in, or start processes against `D:\bg-sim`
  itself: another orchestrator works there.
- Windows 11, PowerShell by default (Git Bash available). Keep LF line endings.
- Julia 1.13.2 through juliaup. Always `julia --project=julia/BGSim ...`. Never add packages to
  the global environment. Read `julia/BGSim/NOTES.md` before any Julia/MTK work.
- Python only through `uv run ...`; dependencies only through `uv add`. There is no system Python.
- Node/npm only inside `web/`. Dependencies are pinned exactly (plan 7.1); add one only if the WP
  needs it, pinned exactly, and say so in the report.
- Never guess a third-party API (MTK, SciMLBase/DiffEqBase, SymbolicIndexingInterface, FastAPI,
  CodeMirror, uPlot, xyflow, Babylon): check the installed source / `.d.ts` or write a ten-line
  probe first. MTK/SciML probe findings go into `julia/BGSim/NOTES.md`.

## Binding documents

1. `CLAUDE.md`
2. `plan/IMPLEMENTATION_PLAN.md` sections 0.2, 1 (especially **D20 to D27**), 2, **3.5, 3.8**,
   **5.9, 5.13**, **7.9**, and section 10 "M4" for your WP.
3. `contracts/schemas/debug.schema.json` (after C4.0) and the other schemas your WP touches.
4. `spec/Modeling Language Spec v0.1.md` for any WP that parses or evaluates user code.
5. This file.

## Lead decisions for M4

- **DEC-M4-1: 3D pause marker.** M5 ran first (DEC-M5-1). The W5.3 3D playback in
  `web/src/viewer/` has no debug pause marker; **W4.3 adds it**: when a run is paused, the 3D
  playback bar shows the pause marker/time and the playback ends at the pause time, consistent
  with the plots.
- **DEC-M4-2: branch work.** All M4 work is committed by the lead on branch `m4`, one commit per
  WP (`<WP-ID>: <summary>`). Sub-agents never commit and never run state-changing git commands.
- **DEC-M4-3: e2e ports** 8790–8799: C4.0/P4.1 8790, W4.1 8791, W4.2 8792, W4.3 8793, X4.1 8794,
  gate 8795. Always run Playwright with `BGSIM_E2E_PORT` set to your port. The M5 agents use
  8771–8783 on the same machine at the same time; never use those (or 8765).
- **DEC-M4-4: process hygiene.** Stop every backend/Julia process you start with
  `taskkill /PID <pid> /T /F` (killing only the `uv` wrapper leaks the server and its Julia
  worker). Other heavy processes run on this machine: at most two Julia-heavy test runs at once
  across all M4 agents.
- **DEC-M4-5: concurrent change on master.** Another agent (PERF-1) is optimizing
  `julia/BGSim/src/sim/simulate.jl` and possibly other `src/sim/*` and `src/compile/*` files on
  master. Keep changes to `scheduler.jl`, `discrete.jl` and `simulate.jl` as small and localized
  as the design allows: put the logic into new files (`sim/debug.jl`, `sim/hooks.jl`,
  `sim/watch.jl`, `sim/edits.jl`, `compile/explain.jl`, `syntax/watch.jl`) and touch the existing
  files only at small, clearly marked insertion points (`# M4 debug:` comments). Never reformat or
  reorder existing code.
- **DEC-M4-6: shared files.** Edits outside a WP's `Owns` are allowed only here, and only
  additively (re-read the file immediately before each edit; another agent may be editing it):
  - `julia/BGSim/src/BGSim.jl`: `include`/`export` lines for your new files;
  - `julia/BGSim/test/runtests.jl`: one `include` line for your new test file;
  - `julia/BGSim/NOTES.md`: append your probe section;
  - `web/src/app/RunBar.tsx`, `web/src/app/BottomDock.tsx`, `web/src/app/useAppShortcuts.ts`,
    `web/src/plot/SignalBrowser.tsx`, `web/src/plot/PlotPanel.tsx`/`UPlotChart.tsx`,
    `web/src/code/CodeEditor.tsx`/`CodeTab.tsx`, the canvas context menu in `web/src/editor/`,
    `web/src/inspector/NodeInspector.tsx`, `web/src/viewer/PlaybackBar.tsx`: mount points for
    the debug UI only (the logic lives in `web/src/debug/` and the files the WP owns);
  - `web/playwright.config.ts`: append a real-worker spec to the fake-pass `testIgnore` list;
  - `tools/check.py`: append a real-worker spec to the real-worker Playwright list.
- **DEC-M4-7: Julia test files and focused runs.** New Julia test files: `test/test_debug.jl`
  (J4.1), `test/test_hooks.jl` (J4.2), `test/test_watch.jl` and `test/test_explain.jl` (J4.3),
  `test/test_edits.jl` (J4.4), `test/test_worker_debug.jl` (J4.5). Each is standalone
  (`using Test, BGSim`) like the existing ones. Iterate with a focused run, for example
  `julia --project=julia/BGSim -e 'include("julia/BGSim/test/test_debug.jl")'`, plus the
  existing files your change can affect (`test_simulate.jl`, `test_discrete.jl`,
  `test_events.jl`, `test_cache.jl`, `test_worker.jl`). The full `Pkg.test()` is the lead's.
  Two Julia agents share one precompile cache: if `using BGSim` fails in a file another WP owns,
  wait a minute and retry; never edit the other WP's files to make your run pass.
- **DEC-M4-8: the debug engine is opt-in.** `simulate(...; debug = nothing)` must stay the
  normal run, with the same code path and no added per-step work. A debug run is
  `simulate(...; debug = ctx::DebugCtx)`. Determinism requirements of plan 5.13 are tested with
  `columns.f64` byte comparison (`read(path) == read(path2)`).

## Non-negotiable engineering rules

- Touch only your WP's `Owns` paths, new test files next to them, and DEC-M4-6 additions. If a
  change elsewhere is genuinely required (including any contract/schema change after C4.0), stop
  and report it instead of editing.
- No TODOs, stubs, placeholders, skipped tests, `test.skip`/`@test_broken`, weakened assertions,
  or try/catch that hides a failure. "Done" means the acceptance commands pass because the
  feature works. Every acceptance criterion of plan 10 "M4" is met literally.
- Diagnostics use the contract of plan 3.4 and tell the user what to do next (E401, E402, W401
  per D21/D24/D27).
- Every new behaviour gets a test that would fail without it.
- Match the style of the surrounding code (naming, comment density, file layout).
- Do not edit `plan/STATUS.md`, do not commit, and do not run state-changing git commands.

## Test commands

- Web (inside `web/`): `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`;
  Playwright `npx playwright test <spec>` with `BGSIM_E2E_PORT` (build first: the backend serves
  `web/dist`).
- Python: `uv run pytest backend/tests -q`, `uv run ruff check backend`.
- Contracts: `uv run tools/gen_contracts.py`, then the contract tests.
- Julia: focused test files (DEC-M4-7).
- Only the lead runs `uv run tools/check.py --lane all`.

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
