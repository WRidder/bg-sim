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
| J1.1 | J | M1 | M0.3 | done | `src/diagnostics.jl` (the plan 3.4 `Diagnostic` + `to_dict`/`from_dict`), `src/syntax/{ast,constfold,whitelist,parse,scopes}.jl`. All 8 M1 scopes, Real/Int/Bool, E000–E005, W204, block-level E103, D1 `~` hint, D6 causality syntax, `block_interface` with the 7 catalog arrays. **1834 tests** (71 M0.3 + 1834) pass; all 36 catalog blocks parse, check and match the fixture interface field-for-field. `@initial/@discrete/@events/@components/@connections` rejected with a named E001. |
| J1.2 | J | M1 | M0.3 | done | `src/units/{units,dims,unitparse,unitcheck}.jl`: `Dims` = 9 exponents (7 SI + `effort`/`flow`) + scale; SI/derived units incl. rpm, deg, mm, bar, L; `* / ^`, functions, wildcard rules, `flow*s/effort` → F / m/N / rad/(N·m) per domain. 726 tests: 64 unit strings, 41 canonical spellings, 25 E006 positions, mm→m 0.001, rpm→rad/s 2π/60, all 36 blocks unit-clean. **FIX-M1-1**: its invented `I101` info code violated the diagnostic contract (`code` pattern `^[EW][0-9]{3}$`) and weakened plan 5.3 — scale-only differences in `+ - ~`/comparisons are now **E006** (the language does no runtime conversion), tests updated. |
| J1.3 | J | M1 | J1.1 | todo | Library loader, catalog, M1 stdlib |
| J1.4 | J | M1 | J1.1, J1.2, J1.3 | done | `src/ir/{blockdef,modeldoc,flat}.jl` + `src/compile/{instantiate,connect,junctions,domains,balance,pipeline}.jl`: instantiation with path prefixes, parameter-expression binding, bond/wire/signal equations, junction signs, union-find wire nodes and domain adoption, E101/E102/E103/W205 with node+connection ids, `model.check` result with `domains`, `signals`, `unitFactors`, `stats`. Measured (unknowns/equations, states): iconic DC motor 26/26, 2; bond-graph DC motor 16/16, 2; iconic RLC 22/22, 2; bond-graph RLC 10/10, 2. 10 negative models give the expected code on the expected id. 300 tests; suite 4807 green. |
| J1.5 | J | M1 | J1.4 | todo | Lowering and simulation (continuous) |
| J1.6 | J | M1 | J1.5, M0.4 | todo | Worker protocol |
| P1.1 | P | M1 | M0.4 | done | `ProjectStore` + projects/models/library CRUD via its own router (app.py untouched). Model/project documents validated against the pydantic models **and** the JSON Schemas (pydantic alone accepts nulls the contracts reject). Atomic writes (`mkstemp` + fsync + `os.replace`, LF), path-traversal rejection, create-from-example with name rewrite, catalog-cache invalidation on library writes. 57 new tests; 219 pytest total, ruff clean. Live: create 201, model PUT 200, traversal 404, invalid model 422. |
| P1.2 | P | M1 | M0.4 | done | `runs.py` (start, cancel, manifest, `/data`, CSV, run WS at both `/ws/runs/{id}` and `/api/ws/runs/{id}`, live decimated tails, history pruning) and a pure `decimate.py`. Deviation: equal-count reshape + per-row min/max instead of `np.minimum.reduceat` — reduceat measured 145 ms, reshape path **27–30 ms** for 1e7 × 10, target < 50 ms. Event rows are kept in addition to the `2*px` budget. Live smoke: run → manifest `done`, 4 signals, n=1001, `/data` 16 024 bytes, CSV 1003 lines. |
| W1.1 | W | M1 | M0.5 | done | Library browser from the live catalog, xyflow canvas with block/junction node types, the plan 7.3 port glyphs and bond/wire/signal styling, 20 SVG icons + bond-graph letters, drag-add, move/rotate/flip/delete/copy-paste, reverse bond, zustand+immer store with 200-patch undo/redo, debounced autosave/load via P1.1. 74 new vitest (159 total) incl. every refusal message exactly; 4 Playwright e2e (build DC motor → save → reload → 10 undos; reverse/delete; Electrical→Rotation refusal; smoke). typecheck/lint/build clean. Build 525 kB (164 kB gzip) — Vite chunk warning noted for the 7.5 perf gate. |
| W1.2 | W | M1 | W1.1 | done | Inspector in `web/src/inspector/` (mounted in InspectorPanel): parameters/constants/starts edited as expression strings with unit, min/max, description, options; rename with uniqueness + identifier checks; inline validation; "Open source" (read-only panel, CodeMirror tab is W2.1) and "Copy to project library". Store gained `renameNode`/`setNodeParam`/`setNodeConstant`/`setNodeStart`/`setNodeBlockRef`/`nodeNameIssue`, all undoable. 27 new vitest + 2 Playwright. |
| W1.3 | W | M1 | W1.1 | done | Diagnostics panel (filter by severity, group by path, click-to-navigate, related list) + debounced 400 ms `model.check` loop with generation guard, stale discard, 503 pause and ready gating; canvas markers (red/amber outlines + badges), adopted-domain colouring and `unitFactors` badges via a diagnostics-owned DOM decorator (deviation: `src/editor/` was outside W1.3's paths; W2.3 folds it into `EditorEdgeData`). 20 vitest + 2 Playwright (all 21 node diagnostics navigate and pan). |
| W1.4 | W | M1 | W1.1 | done | Run bar (run/stop/settings/progress, Ctrl+Enter), signal browser (tree by path, search, kind icons, drag/double-click to plot), uPlot panels with linked cursors, unit-group axis assignment (2 max, overflow suggests a panel), LRU series cache keyed `(run,id,t0,t1,px)`, zoom re-fetch, CSV export, pin-run. 4 vitest files + 4 Playwright. Verified by the orchestrator after the agent hit its usage limit mid-report: typecheck/lint/262 vitest/11 e2e all pass; the plot e2e asserts a real mouse-drag zoom produces a request with finite `t0`/`t1` and `px > 0` after the raw `px=0` request. |
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
| P2.1 | P | M2 | M1 | done | `/api/check/block` coalescing (one in-flight + one pending per `(client, ref)`, all waiters get the newest answer, stale results discarded): 5 rapid requests → 2 worker calls; per-client isolation verified; newest-error path returns 422. Live tails proven at **16.1 msg/s** (cap 20) over a 2.17 s synthetic run; late subscriber gets the backlog up to its subscribe time; history pruning keeps 19 old + the new run (configurable, `BGSIM_RUN_HISTORY`). Also fixed a P1.2 bug: a live manifest reported `time.n = 0` because it read the wrong notification field. pytest 226, ruff clean. |
| W2.1 | W | M2 | M1 | done | CodeMirror 6 code tab: Julia mode + scope-macro/`~` highlighter, 300 ms `block.check` lint with E001 tooltip and quick-fix, autocomplete from the Julia whitelist (parity test against `whitelist.jl`/`dims.jl`), read-only stdlib with copy banner, inline equation/discrete nodes whose ports update from the interface, `bgsim:open-source` navigation. Inline interfaces live in a separate store keyed by node (failed checks keep the last good ports). Store gained undoable `addInlineBlock`/`setInlineSource`. 299 vitest (37 new), 13 e2e incl. the E001→fix→port-appears acceptance. Note: the e2e stubs `/api/check/block` because the fake worker returns `interface: null` — the real worker is the authority. |
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
| C5.0 | C | M5 | M3 | todo | Debug contracts (added in plan v1.1) |
| J5.1 | J | M5 | C5.0 | todo | Debug run engine |
| J5.2 | J | M5 | J5.1 | todo | Statement hooks and line breakpoints |
| J5.3 | J | M5 | J5.1, J2.8 | todo | Watch pool, evaluate and explain |
| J5.4 | J | M5 | J5.1 | todo | Edits, replay and branch |
| J5.5 | J | M5 | J5.2, J5.3, J5.4 | todo | Worker debug methods |
| P5.1 | P | M5 | C5.0 | todo | Debug API and fake debugger |
| W5.1 | W | M5 | P5.1, W2.1 | todo | Debug controls and gutter breakpoints |
| W5.2 | W | M5 | W5.1 | todo | Debug panels, watches and explain |
| W5.3 | W | M5 | W5.1, W2.4, W3.3 | todo | Pause-aware plots and live inspector |
| X5.1 | X | M5 | J5.5, P5.1, W5.1–W5.3 | todo | Debugging walkthrough e2e |

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
| CONTRACT-2 | fixture fix | `catalog.min.json` had four metadata fields that disagreed with its own (normative) `source` text: the `Sum` parameter description carried a stray " (D11)", and `VoltageSource`/`ForceSource`/`TorqueSource` listed a `fixed` causality entry their source never declares. J1.1 had documented and skipped exactly those fields; the fixture was fixed and **the skip removed**, so the test now compares every field (1834 assertions). Iconic sources genuinely have no `@causality` declaration: SCAP runs on the bond-graph part only. |
| CONTRACT-3 | fixture fix | `model.dcmotor.json` left `V1.n` (the voltage-source return) unconnected, so the canonical iconic DC motor would legitimately raise E101 in J1.4. Added connection `c7` `V1.n → Ground1.p`; the ground node now joins `Motor1.n` and `V1.n`. No schema change. The fixture's connection count went from 6 to 7, which broke two W1.1 web tests that hard-coded the old shape (fixed after W1.1 landed). |
| CONTRACT-4 | physics fix | J1.4 found that `stdlib/bondgraph/GY` was not power-conserving (`p1.e = r·p2.f` **and** `p2.e = r·p1.f` gives `ΣP = 2r·f1·f2`); `TF` had the same bug. With the spec's "power positive into each port", the correct constitutive laws are `p2.e = -r·p1.f` (GY) and `p2.f = -n·p1.f` (TF). Fixed in both the stdlib files and the catalog fixture's normative `source` text; suite still 4807 green. No automated golden test protects these two yet — J1.5's iconic-vs-bond-graph DC-motor agreement is the first proof, and J2.7a adds the per-block golden tests. |
| NOTE-1 | finding | Pure bond-graph models (both DC-motor and RLC bond-graph fixtures use only `Power{Generic}` ports) adopt **no** concrete domain, so `domains` reports `Generic` and each island gets **W205** — exactly what plan 5.6 prescribes. Plan 9.3's phrase "Generic ports turn Electrical blue" therefore only applies when a bond island also touches a concrete-domain port (e.g. through a converter). X2.2 must treat W205 as expected for the pure bond-graph half, and the "no W201" check is unaffected. |
| DEC-1 | ordering | J1.2 is run **after** J1.1, although its plan `Depends` is only M0.3. J1.2's `check_units` consumes J1.1's AST and `Diagnostic` type, so running them concurrently would race on the same interface. The orchestrator's J1.1 brief pins the AST and diagnostic API as a contract so J1.2 can rely on it. |
| DEC-2 | tooling | `tools/check.py` needed a Windows fix (npm/npx are `.cmd` shims; `CreateProcess` cannot launch them) and now only runs npm scripts that exist. It also gained the plan-6 requirement that `--lane x` runs the `pytest -m julia` integration test. |
| DEC-3 | layout | `uv run bgsim` from the repo root failed (uv project discovery stopped at the root, which had no `pyproject.toml`). Added a root `pyproject.toml` as a **uv workspace root** (`members = ["backend"]`, project `bg-sim` exposing the same `bgsim` script) and a root `.python-version` pinned to 3.13. `uv run bgsim`, `uv run --directory backend bgsim` and `uv run tools/check.py` all work now; both environments run Python 3.13.2. |
| DEC-4 | deviation | P1.2 decimates with equal-count reshape + per-row min/max instead of plan 6's `np.minimum.reduceat`/`np.maximum.reduceat` (145 ms → 27–30 ms at 1e7 × 10, so 2× inside the 50 ms target). Buckets are equal-count, identical to equal-time on the uniform solver grid; event rows are kept on top of the `2*px` budget. |
| REQ-1 | requirement | The backend's live run tail needs the run manifest's `signals` while a run is still executing. J1.5/J1.6 must therefore write a `status: "running"` manifest with the full signal list at run start and update it at the end (the fake worker already does this). |
| DEC-5 | scaffolding | `src/BGSim.jl` and `test/runtests.jl` include the later modules/test files through an `isfile` guard (`units/units.jl`, `library/library.jl`, `test_{units,library,flatten,simulate,worker}.jl`) so that two Julia WPs adding a module in parallel cannot break each other's test run. **The M1 gate replaces the guards with plain `include` calls** (FIX-M1-n if anything is missing). |
| DEC-6 | plan v1.1 | The user added **M5 (live debugging)** to the plan as v1.1 with decisions D20–D27 and sections 3.8/5.13/7.9, and the ten M5 WP rows in this table. Milestone order is now **M0 → M1 → M2 → M3 → M5**, with M4 (planar) still the stretch goal. M5 builds on J2.2, J2.3, J2.8, W2.1, W2.4 and W3.3, so nothing in M1/M2 changes; the M3 gate now also opens C5.0. |
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
| Decimation 1e7 × 10 | < 50 ms | 27–30 ms (P1.2) |
