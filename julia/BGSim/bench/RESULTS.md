# PERF-1 results

Machine: Windows 11, Julia 1.13.2, `--threads` default, **shared with other agents running example
checks, Playwright and Julia suites at the same time** (timings carry roughly +-30 % noise; the
ratios are what matter). Harness: `julia/BGSim/bench/bench.jl`; raw output in `bench/out/`
(`baseline*.{txt,json}` = HEAD code with only the profile hook, `after*.{txt,json}` = this work package).
Tables are made by `bench/report.jl`.

Definitions. *cold* = first `simulate` of that model in the process (model-specific JIT included, other models
ran before in the same process, so generic solver code is warm); *warm* = second run of the same model
(compile-cache hit: `remake` + init + solve + record). *compile* in the second table is `lower_model` inside `simulate`
(`remake` on a hit, which still pays model-specific JIT the first time). Shortened cases are marked with `t_end`.
Every "after" trajectory is **bit-identical** to the baseline (`columns.f64` compared with `--compare`, max abs diff 0.0)
except `cube-3d-mb`, a chaotic balancing cube whose result already depends on the process history (see NOTES.md, PERF-1).

## 1. Before -> after per model (seconds)

| case | states | signals | cold total before -> after (s) | warm total before -> after (s) | warm solve loop before -> after | steps / rejects |
|---|---:|---:|---|---|---|---|
| dc-motor/iconic | 3 | 73 | 3.1 -> 1.4 | 1.7 -> 1.1 | 0.5 -> 0.0 | 5076 / 64 |
| drivetrain-kalman | 10 | 102 | 15.6 -> 10.1 | 2.2 -> 1.5 | 1.0 -> 0.3 | 16676 / 50 |
| industrial-servo/switching | 4 | 123 | 51.6 -> 15.0 | 44.4 -> 12.6 | 43.2 -> 11.6 | 852443 / 4 |
| robot-arm-2d/arm | 0 | 280 | 11.4 -> 2.0 | 4.1 -> 1.9 | 2.9 -> 1.0 | 54740 / 860 |
| robot-arm-3d/arm (t_end 0.5) | 0 | 2352 | 139.2 -> 17.6 | 13.6 -> 3.0 | 11.6 -> 0.9 | 2387 / 576 |
| robot-arm-3d/rrr | 15 | 478 | 33.3 -> 10.7 | 62.0 -> 3.3 | 61.1 -> 2.1 | 45478 / 70 |
| robot-arm-3d/rrr-multibond (t_end 1) | 0 | 1371 | 107.5 -> 15.0 | 23.1 -> 3.5 | 21.1 -> 1.4 | 15229 / 3140 |
| cube-3d/cube-3d-mb (t_end 1) | 24 | 1714 | 98.2 -> 3.3 | 15.3 -> 1.4 | 13.5 -> 0.4 | 41150 / 214 |
| cube-3d/cube-3d (t_end 1) | 19 | 334 | 6.6 -> 1.8 | 1.5 -> 0.8 | 0.8 -> 0.1 | 11308 / 1283 |
| cube-pyramid-3d/edge-contact | 19 | 2382 | 120.3 -> 7.3 | 20.5 -> 4.4 | 19.1 -> 2.6 | 75309 / 3279 |
| cube-pyramid-3d/sequence-contact (t_end 0.5) | 21 | 2512 | 156.0 -> 8.1 | 18.2 -> 2.0 | 16.0 -> 0.4 | 14575 / 22 |

| case | phase (cold, after) flatten / lower / System / mtkcompile / ODEProblem | compile (remake) | init | loop: step / tick / values |
|---|---|---:|---:|---|
| dc-motor/iconic | 0.1 / 0.0 / 0.0 / 0.1 / 0.9 | 0.0 | 0.8 | 0.1 / 0.0 / 0.0 |
| drivetrain-kalman | 2.2 / 0.2 / 0.0 / 0.8 / 1.7 | 0.1 | 2.6 | 3.9 / 0.8 / 0.1 |
| industrial-servo/switching | 0.4 / 0.0 / 0.0 / 0.0 / 0.7 | 0.0 | 1.0 | 7.6 / 2.9 / 0.4 |
| robot-arm-2d/arm | 0.2 / 0.0 / 0.0 / 0.1 / 0.8 | 0.1 | 0.8 | 0.5 / 0.2 / 0.1 |
| robot-arm-3d/arm (t_end 0.5) | 0.4 / 0.1 / 0.0 / 0.6 / 1.3 | 1.9 | 2.5 | 9.4 / 0.9 / 2.0 |
| robot-arm-3d/rrr | 0.1 / 0.7 / 0.0 / 0.2 / 3.6 | 0.3 | 2.3 | 2.8 / 1.4 / 2.0 |
| robot-arm-3d/rrr-multibond (t_end 1) | 0.0 / 0.1 / 0.0 / 0.3 / 0.9 | 1.6 | 1.4 | 4.0 / 1.2 / 6.3 |
| cube-3d/cube-3d-mb (t_end 1) | 0.2 / 0.2 / 0.0 / 0.2 / 0.8 | 0.6 | 0.8 | 0.2 / 0.3 / 1.0 |
| cube-3d/cube-3d (t_end 1) | 0.0 / 0.0 / 0.0 / 0.0 / 0.6 | 0.7 | 0.6 | 0.3 / 0.1 / 0.1 |
| cube-pyramid-3d/edge-contact | 0.1 / 0.1 / 0.0 / 0.4 / 1.2 | 1.0 | 1.7 | 1.6 / 0.4 / 1.8 |
| cube-pyramid-3d/sequence-contact (t_end 0.5) | 0.1 / 0.1 / 0.0 / 0.5 / 1.3 | 1.6 | 2.1 | 0.3 / 0.1 / 2.2 |

## 2. Full-length runs (the user's slow cases), cold = first run in a fresh bench process

| case | before cold (s) | after cold (s) | after warm (s) | steps / rejects | rows |
|---|---:|---:|---:|---|---:|
| robot-arm-3d `arm` (t_end 2, 72 states, 2352 signals) | 208.8 | 16.5 | 6.8 | 8973 / 2309 | 4001 |
| robot-arm-3d `rrr-multibond` (t_end 5) | 137.2 | 21.6 | 8.2 | 49575 / 10395 | 11131 |
| cube-3d `cube-3d-mb` (t_end 4) | 108.3 | 6.8 | 3.6 | 159146 / 1464 | 6001 |
| cube-pyramid-3d `sequence-contact` (t_end 4.5) | 178.3 | 13.7 | 7.7 | 194915 / 7586 | 9001 |

Where the baseline went (full `arm`, cold): getters 143 s of 209 s; after: 1.8 s of 16.5 s. What is left in the
cold run is JIT of the model's RHS/Jacobian (step 7.6 s cold vs 2.8 s warm), mtkcompile/ODEProblem (3 s) and init (2.7 s).

## 3. Worker start and the PrecompileTools workload

Measured on the loaded machine (interleaved, ±2 s noise):

| | before | after |
|---|---:|---:|
| `using BGSim` in a fresh `julia --threads=2` | 10.2-15.9 s | 11.2-16.3 s |
| `warm_up!` (catalog, checks, 2 RC runs; after: + 2 clocked runs) | 0.9-1.6 s | 1.0-2.6 s |
| `Pkg.precompile()` of BGSim incl. the PrecompileTools workload (source touched) | 196 s | 196 s |
| **first real run in a fresh worker after `warm_up!`**: robot-arm-3d `arm`, t_end 0.5 | **142.4 s** | **19.0 s** |
| first real run in a fresh worker: dc-motor `iconic` | 2.8 s | 2.5 s |

Cold worker start is package loading (MTK, Symbolics, OrdinaryDiffEq) and is unchanged; the PackageCompiler sysimage
(plan 11) remains the only lever for it and is not needed. The user-visible cold cost was the first run of a big
model, which is what changed.

## 4. What was changed (all results unchanged)

1. Recorder: one in-place generated function for all signals (`SignalReader`, `build_explicit_observed_function(...;
   return_inplace, optlevel = 0)`) instead of one `getu`/`getp` per signal; one bulk `write` per row.
2. PrecompileTools workload and `warm_up!` also run a clocked (ZOH) variant of the RC model (scheduler,
   `setp`, DAE re-init, signal reader); the workload ends with `clear_compile_cache!()` so no compiled `System`
   is baked into the image (a `KeyError` from RuntimeGeneratedFunctions otherwise).
3. `BGSim.LAST_PROFILE[]` (phase timings + solver stats of the last run) and the bench harness.

Tried and rejected (numbers in NOTES.md, PERF-1): `jac = true` (> 8 min for the 72-state arm), `FullSpecialize`
(faster event-dense runs, slower everywhere else), ODEProblem `optlevel = 0` (4 s less JIT, slower RHS),
numeric `remake` (0.9 s on the first rerun only), a vector-valued `getu` (1 ms per row, 13-24 s compile).

## 5. Verification (final code)

* `julia --project=julia/BGSim -e "using Pkg; Pkg.test()"`: all green, 159391 assertions in 123 top-level test sets (new
  `test/test_perf.jl`: 15 assertions), 13 min wall including a 3 min precompile (quiet machine).
* `uv run examples/run_checks.py` (every example): 1213 passed, 0 failed, 507 s. (An earlier run on the same recorder
  code showed two failures in the then unfinished `pendulum-triple-fixed` scene check, an example that another work
  package was still writing; it passes in the final run.)
* Discrete goldens and all bench trajectories: bit-identical (`--compare`, max abs diff 0.0), except the chaotic
  `cube-3d-mb` whose run depends on the process history (also true of the baseline code; NOTES.md, PERF-1).
