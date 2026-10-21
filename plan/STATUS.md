# bg-sim implementation status

Orchestrator-maintained log. One row per work package of `plan/IMPLEMENTATION_PLAN.md` section 10.
States: `todo`, `running`, `done`, `failed`, `rescoped`.

## Work packages

| WP | Lane | Milestone | Depends | State | Note |
| --- | --- | --- | --- | --- | --- |
| M0.1 | X | M0 | — | done | git init, .gitignore, .gitattributes, tools/check.py (j/p/w/x/all), STATUS table. `uv run tools/check.py --lane all` reports "no tests yet" for all four lanes, exit 0. |
| M0.2 | C | M0 | M0.1 | done | 8 schemas (catalog, model, project, diagnostic, run-manifest, worker-rpc, stream-handshake, bindings) + 44 valid / 22 invalid fixtures; catalog covers all 36 M1 blocks, diagnostic sample covers all 25 codes. `gen_contracts.py` generates pydantic v2 + TS, idempotent (10/10 files byte-identical on re-run). pytest 101 passed, vitest 52 passed, ruff + tsc clean. Also created the minimal `backend/` and `web/` harnesses for M0.4/M0.5 to extend. |
| M0.3 | J | M0 | M0.1 | done | Julia 1.13.2 (no 1.12 fallback needed). MTK 11.45.5, Symbolics 7.47.0, SII 0.3.55, OrdinaryDiffEq{Rosenbrock 2.7.5, Tsit5 2.1.5, BDF 2.4.13, Verner 2.4.2}, JSON3 1.14.3, JuliaSyntax 1.0.2, StaticArrays 1.9.24, PrecompileTools 1.3.4, RuntimeGeneratedFunctions 0.5.27, Sockets 1.11.0. `Pkg.test()` 71/71 pass. Cold `Pkg.add`+precompile 893 s; BGSim first precompile 27–30 s; cold chain ~960 s. NOTES.md is the J-lane API authority. |
| M0.4 | P | M0 | M0.2 | todo | Backend skeleton |
| M0.5 | W | M0 | M0.2 | todo | Web skeleton |
| J1.1 | J | M1 | M0.3 | todo | Parser and whitelist core |
| J1.2 | J | M1 | M0.3 | todo | Units |
| J1.3 | J | M1 | J1.1 | todo | Library loader, catalog, M1 stdlib |
| J1.4 | J | M1 | J1.1, J1.2, J1.3 | todo | Flatten, connect, junctions, domains |
| J1.5 | J | M1 | J1.4 | todo | Lowering and simulation (continuous) |
| J1.6 | J | M1 | J1.5, M0.4 | todo | Worker protocol |
| P1.1 | P | M1 | M0.4 | todo | Projects API |
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

(added when a milestone gate is run)

## Measured numbers

| Item | Target | Measured |
| --- | --- | --- |
| Julia first precompile (M0.3) | measure | 27.3 s (BGSim, workload incl.); cold depot → first green `Pkg.test()` ≈ 960 s |
| Worker cold start to ready | < 60 s | |
| block.check 40-line block | < 150 ms | |
| model.check 60-element model | < 1.5 s | |
| DC motor first run | < 10 s | |
| Parameter-only re-run | < 300 ms | |
| Decimation 1e7 × 10 | < 50 ms | |
