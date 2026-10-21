# bg-sim implementation status

Orchestrator-maintained log. One row per work package of `plan/IMPLEMENTATION_PLAN.md` section 10.
States: `todo`, `running`, `done`, `failed`, `rescoped`.

## Work packages

| WP | Lane | Milestone | Depends | State | Note |
| --- | --- | --- | --- | --- | --- |
| M0.1 | X | M0 | — | done | git init, .gitignore, .gitattributes, tools/check.py (j/p/w/x/all), STATUS table. `uv run tools/check.py --lane all` reports "no tests yet" for all four lanes, exit 0. |
| M0.2 | C | M0 | M0.1 | done | 8 schemas (catalog, model, project, diagnostic, run-manifest, worker-rpc, stream-handshake, bindings) + 44 valid / 22 invalid fixtures; catalog covers all 36 M1 blocks, diagnostic sample covers all 25 codes. `gen_contracts.py` generates pydantic v2 + TS, idempotent (10/10 files byte-identical on re-run). pytest 101 passed, vitest 52 passed, ruff + tsc clean. Also created the minimal `backend/` and `web/` harnesses for M0.4/M0.5 to extend. |
| M0.3 | J | M0 | M0.1 | done | Julia 1.13.2 (no 1.12 fallback needed). MTK 11.45.5, Symbolics 7.47.0, SII 0.3.55, OrdinaryDiffEq{Rosenbrock 2.7.5, Tsit5 2.1.5, BDF 2.4.13, Verner 2.4.2}, JSON3 1.14.3, JuliaSyntax 1.0.2, StaticArrays 1.9.24, PrecompileTools 1.3.4, RuntimeGeneratedFunctions 0.5.27, Sockets 1.11.0. `Pkg.test()` 71/71 pass. Cold `Pkg.add`+precompile 893 s; BGSim first precompile 27–30 s; cold chain ~960 s. NOTES.md is the J-lane API authority. |
| M0.4 | P | M0 | M0.2 | done | FastAPI + `/api/health` + TCP worker supervisor (u32 len / u8 kind framing, concurrent requests, timeouts, restart backoff) + fake worker over a real socket + Julia `BGSim.Worker` stub answering `ping`. pytest 126 + 1 julia-marked, ruff clean. Measured: real-worker cold start 18.9 s first / 14.0 s warm, ping 1.01 ms first / 0.24 ms warm, framing round-trip 0.09 ms, fake ready in 58 ms. |
| M0.5 | W | M0 | M0.2 | done | Vite 8.3.1 + React 19.3.0 + TS 6.0.3, all plan 7.1 versions pinned (xyflow 12.12.0, uplot 1.6.32, CodeMirror 6.43.15, react-resizable-panels 4.14.8, immer 11.2.7, fontsource). Theme tokens light/dark with the domain colours, layout shell of 7.2 with resizable persisted panels, API client + health indicator, ESLint 10 + Vitest 5.0.2 (85 tests) + Playwright smoke. typecheck/lint/test/build/e2e all pass; real-worker smoke passes in 10.8 s. |
| P1.3 | P | M0/M1 | M0.4 | done | Added by orchestrator: `GET /api/catalog` (per-project cache with mtime fingerprint + invalidation), `POST /api/check/block` and `/api/check/model` (5 s / 60 s timeouts → 504, worker errors → 422), empty `projects.py`/`runs.py` router skeletons. pytest 137 passed, ruff clean; live catalog returns 36 blocks, unknown project → 404. |
| J1.1 | J | M1 | M0.3 | todo | Parser and whitelist core |
| J1.2 | J | M1 | M0.3 | todo | Units |
| J1.3 | J | M1 | J1.1 | todo | Library loader, catalog, M1 stdlib |
| J1.4 | J | M1 | J1.1, J1.2, J1.3 | todo | Flatten, connect, junctions, domains |
| J1.5 | J | M1 | J1.4 | todo | Lowering and simulation (continuous) |
| J1.6 | J | M1 | J1.5, M0.4 | todo | Worker protocol |
| P1.1 | P | M1 | M0.4 | done | `ProjectStore` + projects/models/library CRUD via its own router (app.py untouched). Model/project documents validated against the pydantic models **and** the JSON Schemas (pydantic alone accepts nulls the contracts reject). Atomic writes (`mkstemp` + fsync + `os.replace`, LF), path-traversal rejection, create-from-example with name rewrite, catalog-cache invalidation on library writes. 57 new tests; 219 pytest total, ruff clean. Live: create 201, model PUT 200, traversal 404, invalid model 422. |
| P1.2 | P | M1 | M0.4 | todo | Runs, decimation, CSV |
| W1.1 | W | M1 | M0.5 | todo | Library and canvas |
| W1.2 | W | M1 | W1.1 | todo | Inspector |
| W1.3 | W | M1 | W1.1 | todo | Diagnostics panel and canvas markers |
| W1.4 | W | M1 | W1.1 | todo | Run controls and Plot v1 |
| X1.1 | X | M1 | J1.6, P1.1, P1.2, W1.1–W1.4 | todo | DC motor example, M1 e2e |
| J2.1 | J | M2 | M1 | todo | Language completion |
| J2.2 | J | M2 | J2.1 | todo | Discrete scheduler |
| J2.3 | J | M2 | J2.1 | todo | Events and nonsmooth |
| J2.4 | J | M2 | M1 | todo | Causality (SCAP) |
| J2.5 | J | M2 | J2.1 | todo | Units completion |
| J2.6 | J | M2 | J2.1 | todo | @components / @connections |
| J2.7a | J | M2 | J2.1 | todo | Stdlib: bond graph |
| J2.7b | J | M2 | J2.1, J2.3 | todo | Stdlib: sources and sinks |
| J2.7c | J | M2 | J2.1, J2.3 | todo | Stdlib: continuous |
| J2.7d | J | M2 | J2.1, J2.2 | todo | Stdlib: discrete and logic |
| J2.7e | J | M2 | J2.1, J2.3 | todo | Stdlib: electrical |
| J2.7f | J | M2 | J2.1, J2.3 | todo | Stdlib: translation |
| J2.7g | J | M2 | J2.1, J2.3 | todo | Stdlib: rotation, hydraulic, converters |
| J2.8 | J | M2 | J1.5 | todo | Compile cache and remake |
| P2.1 | P | M2 | M1 | todo | Live tails and check fast path |
| W2.1 | W | M2 | M1 | todo | Code editor and inline blocks |
| W2.2 | W | M2 | M1 | todo | Subsystems |
| W2.3 | W | M2 | J2.4, J2.5, W1.3 | todo | Domain visual language complete |
| W2.4 | W | M2 | P2.1, W1.4 | todo | Plot v2 |
| X2.1 | X | M2 | J2.3, J2.7 | todo | Example bouncing-ball |
| X2.2 | X | M2 | J2.4, J2.7 | todo | Example rlc-dual |
| X2.3 | X | M2 | J2.3, J2.7 | todo | Example quarter-car |
| X2.4 | X | M2 | J2.2, J2.6 | todo | Example drivetrain-kalman |
| X2.5 | X | M2 | J2.7 | todo | Example hydraulic-servo + speed-control |
| W3.1 | W | M3 | M2 | todo | Viewer core port |
| W3.2 | W | M3 | W3.1 | todo | SDF parser and scene builder |
| W3.3 | W | M3 | W3.2, W2.4 | todo | Bindings and playback |
| P3.1 | P | M3 | M2 | todo | Stream endpoint and meshes |
| X3.1 | X | M3 | W3.2 | todo | Scenes for M1/M2 examples |
| X3.2 | X | M3 | M2 | todo | Example reaction-wheel-1d |
| X3.3 | X | M3 | M2 | todo | Example robot-arm-3d |
| X3.4 | X | M3 | M2 | todo | Example cube-3d |
| W3.4 | W | M3 | W3.3 | todo | Polish |
| J4.1 | J | M4 | M3 | todo | Planar domain |
| J4.2 | J | M4 | J4.1 | todo | Planar components |
| X4.1 | X | M4 | J4.2 | todo | Planar examples and cross-checks |

## Milestone summaries

### M0 — Foundations (gate: green, 2026-10-22)

**Works.** `uv run tools/check.py --lane all` → 9 checks pass, 0 fail, 0 skipped (Julia
`Pkg.test` 71 tests, pytest 126 + 1 julia-marked, ruff, tsc typecheck, ESLint, Vitest 85 +
54 contract tests, Vite build, Playwright). Playwright also passes against `uv run bgsim` with
the **real** Julia worker (10.8 s, worker cold). One command `uv run bgsim` starts the API on
127.0.0.1:8765, serves `web/dist`, and reports `worker: ready`; `BGSIM_FAKE_WORKER=1` swaps in a
fixture-driven fake that speaks the same framing over a real socket.

**Measured.** Cold dependency install + precompile 893 s; BGSim precompile 27.3 s; cold
`Pkg.test` chain ~960 s. Worker cold start to `ready` 18.9 s (first) / 14.0 s (warm);
`ping` round-trip 1.01 ms first, 0.24 ms warm; framing round-trip 0.09 ms; fake ready 58 ms.
Web build 275 kB JS / 16 kB CSS (gzip 86 kB / 5.5 kB).

**Known gaps.** `/api/catalog` and the two check proxies are not implemented yet (P1.3).
Julia worker answers only `ping`/`cache.clear` (M0.4 scope; J1.6 completes the protocol).
`@initial`, `@discrete`, `@events`, `@components`, `@connections` are not parsed yet (J2.1/J2.6).

**Deviations.** DEC-3 (root uv workspace so `uv run bgsim` works as the plan states), DEC-2
(check.py Windows fix + julia-marked step in lane x), P1.3 (a WP the plan was missing).


## Contract changes and orchestrator decisions

| ID | Kind | Note |
| --- | --- | --- |
| CONTRACT-1 | fixtures added | `model.rlc.iconic.json` and `model.rlc.bondgraph.json` added to `contracts/fixtures/model/valid/` (plan 9.3, R = 10 Ω, L = 10 mH, C = 100 µF) because J1.4's acceptance names RLC fixtures that M0.2 did not create. No schema change, so no binding change was needed; pytest 105 and vitest 54 pass with them. |
| DEC-1 | ordering | J1.2 is run **after** J1.1, although its plan `Depends` is only M0.3. J1.2's `check_units` consumes J1.1's AST and `Diagnostic` type, so running them concurrently would race on the same interface. The orchestrator's J1.1 brief pins the AST and diagnostic API as a contract so J1.2 can rely on it. |
| DEC-2 | tooling | `tools/check.py` needed a Windows fix (npm/npx are `.cmd` shims; `CreateProcess` cannot launch them) and now only runs npm scripts that exist. It also gained the plan-6 requirement that `--lane x` runs the `pytest -m julia` integration test. |
| DEC-3 | layout | `uv run bgsim` from the repo root failed (uv project discovery stopped at the root, which had no `pyproject.toml`). Added a root `pyproject.toml` as a **uv workspace root** (`members = ["backend"]`, project `bg-sim` exposing the same `bgsim` script) and a root `.python-version` pinned to 3.13. `uv run bgsim`, `uv run --directory backend bgsim` and `uv run docs/tools/check.py` all work now; both environments run Python 3.13.2. |
| P1.3 | WP added | The plan's WP list leaves `GET /api/catalog`, `POST /api/check/block` and `POST /api/check/model` (plan 3.7) unowned, and the web lane needs all three in M1. Added **P1.3 Catalog and check proxies**; it also creates the empty `projects.py`/`runs.py` router skeletons so P1.1 and P1.2 never edit `app.py` concurrently. |

## Measured numbers

| Item | Target | Measured |
| --- | --- | --- |
| Julia first precompile (M0.3) | measure | 27.3 s (BGSim, workload incl.); cold depot → first green `Pkg.test()` ≈ 960 s |
| Worker cold start to ready | < 60 s | 18.9 s first, 14.0 s warm (M0.4) |
| block.check 40-line block | < 150 ms | |
| model.check 60-element model | < 1.5 s | |
| DC motor first run | < 10 s | |
| Parameter-only re-run | < 300 ms | |
| Decimation 1e7 × 10 | < 50 ms | |
