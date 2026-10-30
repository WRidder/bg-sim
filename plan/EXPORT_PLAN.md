# C export and FMU: assessment and implementation plan

Status: v0.1 draft, 2026-10-30. Input: `spec/Modeling Language Spec v0.1.md` (target platform,
fixed-step semantics, W203/E104), `plan/IMPLEMENTATION_PLAN.md` section 12 (export deferred),
the spike in `spike/fmu/` (results in `spike/fmu/README.md`), and the codebase at `3b84ce8`.

Goal: export any bg-sim model as **C99 source plus an FMU** that runs under hard real-time
constraints: no heap allocation after instantiation, no unbounded loops, a fixed cost per step.

## 1. Verdict

**Feasible, with no change to the language or the compiler front end.** Every piece of data a
code generator needs already exists after `mtkcompile`, and the spike turned the dc-motor
models into a validated FMI 2.0 FMU in about 1 250 lines (generator, runtime, FMI wrapper
and checks).

The plan changes **one** decision in the spec. The spec's target is a `juliac`-trimmed Julia
library behind a C ABI, with generated C++ as a later option. This plan makes **generated C99
the target**:

- it needs no Julia runtime or GC on the controller, so it also reaches microcontrollers, a
  vendor RTOS and PLC runtimes;
- the generated code is small, readable and reviewable (see `model.c` in the spike), which
  matters for certification;
- trimming compatibility of MTK-generated code is unknown; C sidesteps the question;
- FMI is a C API anyway.

The spec's rules for the language (whitelist = target vocabulary, static sizes, no allocation)
are exactly what makes C generation possible, so they stay. The spec's target-platform
paragraph and the compilation-pipeline figure change (section 10).

## 2. What the spike proved

Spike scope: `examples/dc-motor` `iconic` (continuous) and `speed-control` (continuous plant
plus a 1 ms discrete PI with anti-windup and clamp). FMI 2.0 Co-Simulation, Windows x64, gcc.

| claim | evidence |
| --- | --- |
| The compiled MTK system is enough to emit C | `unknowns`, `equations`, `observed`, `parameters`, `calculate_jacobian`; the observed equations act as common subexpressions |
| Discrete partitions port as they are | `Compile.step_expression` output (index-based `Expr`) translated to C one-to-one, same operation order as `run_tick!` |
| No allocation in the hot path | 1 allocation in `fmi2Instantiate`, 0 in 100 000 `fmi2DoStep` calls; the hot-path objects import only `llround` and `strcmp` from libc |
| Valid FMU | `fmpy` validation passes; it simulates in `fmpy` |
| Matches simulation | RK4 at 0.1 ms: max error 2.4e-5 of peak on the motor current, 3.5e-6 on speed, every output within 1.1e-4; steady state to 4.5e-15 |
| Cheap and fixed cost | < 1 µs per 1 ms tick (3 states, 10 substeps) |
| Portable | the generated and runtime sources compile as C++17 too |

Four findings shape this plan:

1. **Stiffness sets the internal step, and it can be computed at export.** The motor's electrical
   pole (|λ| = 3871 1/s) makes RK4 unstable above 0.72 ms. The spike predicts this from the
   Jacobian's eigenvalues along the reference run; 1 ms diverged as predicted.
2. **Stable is not accurate.** RK4 at 0.5 ms was stable but 9 % off. Substep selection needs an
   accuracy test, not only the stability bound.
3. **No single best integrator.** When the fast mode is a real signal (motor current), RK4 with
   substeps beat ROS2 on accuracy and cost. When fast modes are parasitic (stiff joints that
   stand in for rigid ones) or the system is a DAE, an L-stable Rosenbrock method wins.
4. **Switching conditions must be frozen during a step.** Live `ifelse` conditions in RK stages
   leak a step change into the previous interval (7.3 % error). Evaluating each condition once
   per step at its start fixes it exactly (2.4e-5).

## 3. What the codebase already gives us

- `lower_model` → `CompiledModel` (`src/lower/mtk.jl`): the `mtkcompile`d `System`, the
  `ODEProblem` (mass matrix tells DAE from ODE), the signal-id → symbol maps.
- `Compile.nonsmooth_conditions`, `event_callbacks` (`src/compile/events.jl`): every switching
  site with its origin, which is what W203 needs.
- `discrete_schedule` and `step_expression` (`src/sim/scheduler.jl`, `src/compile/discrete.jl`):
  partitions in topological order, integer-nanosecond periods and offsets, held/input/parameter
  index maps. E104 against `dt` is a one-line check on `period_ns`.
- The intrinsics are already opaque registered functions with plain numeric bodies
  (`bg_interp1/2`, `bg_csv`, the `bg_*` mechanics functions in `src/lower/fnmap.jl`), so each
  needs exactly one hand-written C twin.
- `ExportInput`/`ExportOutput`/`ExportParameter` blocks (`stdlib/converters/`) and stable signal
  IDs: the interface names.
- `tunable = true` on parameters, and D4 (all parameters are runtime parameters in simulation,
  folding is left to export).
- The example runner and `expected.json` checks: the place for "FMU matches simulation".

## 4. Decisions to freeze before coding

| id | topic | decision | why |
| --- | --- | --- | --- |
| D-EX1 | Target | Generated **C99**, from the `mtkcompile`d system. A header-only C++ wrapper (RAII class owning the instance) is a thin extra. `juliac` is dropped as the target. | Section 1. |
| D-EX2 | Layers | Three layers: generated `model.c/.h` (the model), a hand-written versioned runtime (solver, tick, helpers), and a hand-written FMI wrapper. The plain C API (`bg_reset`, `bg_step`, get/set) is usable without FMI. | ctrlX apps and MCU firmware call the C API directly; FMI tools use the wrapper. Generated code stays minimal. |
| D-EX3 | Packaging | FMI **2.0 Co-Simulation** first, **3.0 Co-Simulation** second. Every FMU carries its sources (source FMU; FMI 3 adds `buildDescription.xml`) plus a binary for each platform built. Model Exchange is not offered. Scheduled Execution (FMI 3) is deferred. | Co-Simulation keeps our solver and our fixed step; Model Exchange hands integration to the host and gives up the real-time guarantees. Sources make cross-compiling for the target possible. |
| D-EX4 | Memory | One instance struct with every array sized at generation time. FMI allocates it once in `Instantiate` through the host's callback. A `BG_STATIC_INSTANCE` build option uses one static instance and no callback, for MCUs. | "No allocation after construction", provable. |
| D-EX5 | Time base | A fixed internal step `dt` (whole nanoseconds). Time is `t_start + n·dt` from an integer step counter, never accumulated. `doStep(h)` requires `h` to be a whole multiple of `dt`. Discrete periods and offsets must be multiples of `dt` (E104). | Deterministic, drift-free, matches the scheduler's integer-ns ticks. |
| D-EX6 | Integrators | Explicit Euler, RK4, and fixed-step linearly implicit Rosenbrock methods with mass-matrix support: ROS2 (spike), then a 3rd/4th-order L-stable method (ROS3P or a Rodas-type method). No method with an inner Newton iteration in the hot path. | Section 2, finding 3. Rosenbrock needs one Jacobian and one LU per step, a fixed cost, and handles index-1 DAEs directly. |
| D-EX7 | Step and integrator selection | The exporter proposes `dt` and the integrator: (a) a **stability** bound from the Jacobian's eigenvalues sampled along a reference run, (b) an **accuracy** check that runs the generated code against the reference and refines `dt` until a user error target is met, (c) a **cost** comparison (RK4 substeps vs one Rosenbrock step). The user can override every choice; the report shows the numbers. | Findings 1–3. A stability-only rule gave a 9 % error. |
| D-EX8 | Switching | Every `ifelse` condition in continuous code (including the rewritten `abs`/`min`/`max`/`clamp`/...) becomes a mode value, evaluated once at the start of each step and held through all stages. `@events` conditions are checked after each step; `reinit` is applied then. Each site is reported as W203 with its origin. | Finding 4; the spec's fixed-step semantics. |
| D-EX9 | Interface | `ExportInput` → FMU input (its `value` parameter becomes the input slot), `ExportOutput` → output, `ExportParameter` → tunable parameter, named by the marker's `name` attribute. An option "expose all signals" adds every recorded signal as a `local` (debugging, SIL comparison). Without markers, the export has no inputs and exposes outputs only through that option. | The spec's interface contract. |
| D-EX10 | Parameters | Non-tunable parameters are **folded** into constants by default. `tunable = true` parameters stay fields, settable at any time. An option keeps all parameters as fields (settable before initialization). | D4 left folding to export; folding shrinks code and lets the compiler simplify. |
| D-EX11 | Initialization | Phase 1: start values computed in Julia at export with the current parameters, and baked in. Phase 2: MTK's initialization system is generated as C and solved with a bounded Newton iteration in `ExitInitializationMode`, which is outside the hot path. | Phase 1 suffices for fixed parameters; phase 2 is needed when initialization depends on parameters that are set before init. |
| D-EX12 | Jacobian | Symbolic (`calculate_jacobian`) with common-subexpression elimination, emitted as a sparse pattern (static triplet list) when it pays off. Fallback for expressions that blow up: finite differences with column colouring (fixed cost of `ncolours` derivative calls). | Rosenbrock needs J every step. |
| D-EX13 | Linear algebra | Dense in-place LU with partial pivoting for small systems; generated static sparse LU (symbolic factorization at export, fixed fill-in) above a size threshold (start at nx > 40). | Fixed cost, no allocation; the 72-state arm makes this real. |
| D-EX14 | Numerics | `-std=c99 -O2 -fno-math-errno`, no `-ffast-math`. Non-finite state → error status, never silently continued. Subnormal flush is a documented target setting. Results match simulation **within tolerance**, not bit-exact (answers the spec's open question: repeatability per target, not across targets). | libm differs from Julia in the last bit; bit-exact output would forbid every libm. |
| D-EX15 | Toolchain | The backend builds binaries with a gcc/clang on PATH, or with `zig cc` from the PyPI `ziglang` package (`uv`-installable) for cross targets: x86_64-linux, aarch64-linux (ctrlX CORE), x86_64-windows. Without a compiler the export still produces a source FMU. | Fits the repo's `uv` rule; one cross-compiler for all targets. Note: the `cl` on this machine is Open Watcom, not MSVC. |

## 5. Target architecture

### 5.1 Layers and files

```
julia/BGSim/src/export/
  export.jl        entry point: export_model(flat, settings) -> ExportResult
  emit_c.jl        SymbolicUtils tree -> C (from spike gen.jl cexpr), CSE, modes
  emit_discrete.jl step_expression Expr -> C (from spike dstmt/dval)
  analysis.jl      eigenvalue scan, stability bound, accuracy loop, cost model
  interface.jl     Export markers -> value references, folding, variability
  fmi.jl           modelDescription.xml (2.0 and 3.0), buildDescription.xml
julia/BGSim/export/runtime/      hand-written C, versioned, copied into every FMU
  bg_runtime.h     language semantics (sign, round, clamp, deadzone, mod, ...)
  bg_solver.c      Euler / RK4 / Rosenbrock, LU, modes, tick, events
  bg_intrinsics.c  interp1/interp2, CSV tables, delay ring buffer, noise
  bg_mech.c        SE2/SE3 exp/log, quaternion functions, spatial inertia
  fmi2_cs.c, fmi3_cs.c
  bg_model.hpp     optional C++ wrapper
backend/src/bgsim_server/exports.py   compile, symbol check, zip, store under the project
web: an Export dialog (settings, analysis report, download)
```

### 5.2 Flow

1. `model.export` (worker RPC) flattens, lowers and compiles as for a run (the compile cache
   applies), checks exportability (E110/E111), and runs the reference simulation.
2. The analysis proposes `dt` and the integrator (D-EX7) unless the settings fix them.
3. The emitter writes `model.c/.h` and the model description; the runtime is copied as it is.
4. The backend compiles for the requested platforms, runs the symbol and allocation checks and
   the accuracy check (the generated code against the reference), zips the FMU, and returns
   the export report: chosen `dt`/integrator, eigenvalue summary, max error per output, W203
   sites, step time on the build host.

### 5.3 Hot-path contract

`bg_step` / `fmi2DoStep` / `fmi3DoStep`: no allocation, no locks, no I/O, no recursion, every
loop bounded by a generated constant, logging only through the host callback and only on an
error. One step costs a fixed number of derivative/Jacobian evaluations and LU solves. CI
enforces this by symbol inspection and the counting harness (section 8).

## 6. Exportability rules

| construct | export status |
| --- | --- |
| ODE (identity mass matrix) | supported (phase A) |
| Index-1 DAE (mass matrix), torn algebraic loops (W202) | supported with Rosenbrock (phase B); RK4/Euler refuse it with E111 |
| Index > 1 after `mtkcompile` | E111 (MTK's index reduction normally prevents this) |
| `ifelse`, `abs`, `sign`, `min`, `max`, `clamp`, `saturate`, `deadzone`, `floor`, `ceil`, `round` | supported, frozen per step, W203 per site |
| `@events` with `reinit` | supported, checked after each step, W203 (phase C) |
| `@discrete`, `previous`, `hold`, multi-rate | supported; E104 when a period is not a multiple of `dt` |
| `interp1`, `interp2`, `csv_value` | supported; tables become `static const` arrays (phase C); W-level size report |
| mechanics functions (`exp`/`log` on SE2/SE3, quaternions, `spatial_inertia`) | supported through `bg_mech.c` (phase C) |
| `delay` | supported only with a constant delay; a ring buffer of `ceil(T/dt)` slots (phase E; also missing in simulation) |
| `noise_normal` | phase E, with a specified PRNG shared with simulation |
| debug hooks, watches | not exported |

Unsupported constructs fail with **E110** naming the block path and source range, as every
other diagnostic does.

## 7. Work packages

Naming follows the main plan: J (Julia), P (Python backend), W (web), X (examples and CI).

### Phase A: promote the spike (MVP)

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX1 | `src/export/` with the C emitter (spike `cexpr` + CSE + modes), discrete emitter, RK4 + Euler runtime, baked initialization, interface from Export markers, folding (D-EX10), FMI 2.0 CS description | dc-motor `iconic`/`speed-control` and drivetrain export; generated code compiles `-Wall -Wextra -Werror` as C99 and C++17 |
| J-EX2 | Analysis: eigenvalue scan, RK4 stability bound, accuracy loop against the reference, export report | the dc-motor report predicts the 0.72 ms bound; the accuracy loop lands on a `dt` that meets 1e-4 |
| P-EX1 | `exports.py`: compile, symbol check, counting harness, zip, `POST /api/projects/{p}/models/{m}/export` | the FMU passes `fmpy` validation; allocation count after instantiate is 0 |
| X-EX1 | Check kind `fmu_compare` in `expected.json` and the runner; first examples: dc-motor (3 models), drivetrain, rlc-dual, quarter-car | every listed example's FMU within its stated tolerance |

### Phase B: stiff systems and DAEs

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX3 | Rosenbrock with mass matrix: ROS2 and a 3rd/4th-order L-stable method; symbolic Jacobian with CSE; the cost model in the analysis | drivetrain-kalman (keeps a linear algebraic equation), hydraulic-servo export; FIX-M2-3's DAE fixture matches |
| J-EX4 | Sparse Jacobian pattern and generated static sparse LU; finite-difference fallback with colouring | `robot-arm-2d` and the 72-state `robot-arm-3d` export; step-time table in the report |

### Phase C: language coverage

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX5 | `bg_intrinsics.c` (`interp1/2`, CSV tables), `bg_mech.c` (all `bg_*` mechanics functions); golden tests of every C function against its Julia twin on random inputs | max deviation ≤ 4 ulp, or documented per function |
| J-EX6 | `@events` + `reinit` per step, W203 per site with origin; E104 against `dt` active | bouncing-ball and the hard-stop goldens export, with W203 at the expected sites |
| X-EX2 | Extend `fmu_compare` to the mechanics examples (pendulums, robot arms, reaction wheels) | within the stated tolerances |

### Phase D: targets and real time

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX7 | FMI 3.0 Co-Simulation wrapper and `buildDescription.xml` | passes FMI 3 validation (fmpy) |
| P-EX2 | Cross builds with `zig cc`: x86_64-linux, aarch64-linux, x86_64-windows | the aarch64 binary runs under qemu-user in CI with the same results |
| X-EX3 | Real-time measurement on PREEMPT_RT (ctrlX CORE or a PREEMPT_RT PC): a cyclic 1 kHz task calling `doStep`, latency and step-time histograms over ≥ 1 h | max step time and jitter recorded for dc-motor and robot-arm-3d; no deadline miss at 1 kHz |
| W-EX1 | Export dialog: platforms, `dt`/integrator (auto or manual), error target, tunables, the analysis report, download | Playwright test exports dc-motor and downloads a valid FMU |

### Phase E: completeness

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX8 | Initialization in C (D-EX11 phase 2): MTK's initialization system, bounded Newton at `ExitInitializationMode` | changing a parameter before init gives the same start as a Julia run with that parameter |
| J-EX9 | `delay` (constant delay, ring buffer) and `noise_normal` (PRNG specified once, implemented in Julia and C) | bit-identical noise sequence in Julia and C |
| J-EX10 | Optional C++ wrapper `bg_model.hpp`; `BG_STATIC_INSTANCE` MCU build | builds with `-fno-exceptions -fno-rtti`; static build has no undefined allocation symbol |

## 8. Validation and gates

- **Accuracy:** every exported example has an `fmu_compare` check: the FMU in `fmpy` against
  the variable-step reference, max error per output relative to its peak, threshold in
  `expected.json`. This is the spec's dashed "target build matches simulation" link.
- **No allocation:** (a) `nm -u` on the hot-path objects contains no `malloc`, `calloc`,
  `realloc`, `free`, stdio or `exit`/`abort`; (b) the counting harness reports 0 memory
  callbacks after instantiate over ≥ 1e5 `doStep` calls; (c) the static MCU build links without
  any allocator.
- **Standard:** `fmpy` validation for FMI 2.0 and 3.0; the generated sources compile as C99 and
  C++17 with `-Wall -Wextra -Werror`.
- **Semantics:** golden tests of each C runtime function against its Julia twin; the discrete
  goldens (`test/golden/discrete/`) also run through the C partitions and must be **bit-exact**
  (the discrete code is plain arithmetic in the same operation order; the spike's PI matched).
- **Real time (phase D):** step-time and latency histograms on PREEMPT_RT, recorded in
  `plan/STATUS.md` like the existing step-time gates.

## 9. Risks and mitigations

| risk | impact | mitigation |
| --- | --- | --- |
| Expression blow-up of large multibody systems in `observed` and in the symbolic Jacobian | huge `model.c`, long C compile | CSE; observed locals as subexpressions (proven in the spike); finite-difference Jacobian fallback (D-EX12) |
| Very stiff parasitic modes (joint stiffness 1e7) need tiny RK4 steps | step budget exceeded | the cost model picks Rosenbrock; W207 when RK4 substeps exceed the budget |
| The eigenvalue scan misses states the reference run never visited | instability in the field | safety margin; the report states the scanned range; Rosenbrock (L-stable) as the robust default for models with W201/W202 |
| Frozen conditions delay a switch by up to one step | contact/friction timing differs from simulation | W203 per site; the accuracy loop reduces `dt`; documented semantics (spec) |
| Quaternion norm drift in long runs | pose error | renormalize after each step in exported code (the spec's open decision: decide in J-EX5) |
| MTK version changes the compiled-system API | emitter breaks | the emitter uses only documented accessors (`unknowns`, `equations`, `observed`, `parameters`, `calculate_jacobian`); a golden of the generated C for dc-motor catches changes |
| libm differences across targets | tiny numeric differences | tolerance-based gate (D-EX14); discrete code bit-exact |
| Large CSV tables on MCUs | flash size | size report in the export; downsampling is the user's choice |

## 10. Contract and spec changes

- `contracts/schemas/export-settings.schema.json` (new): platforms, FMI version, `dt` or
  `auto`, integrator or `auto`, error target, step budget, expose-all-signals, keep-parameters.
- `contracts/schemas/export-report.schema.json` (new): chosen `dt`/integrator, eigenvalue
  summary, stability bound, errors per output, W203 sites, step time, file list.
- `worker-rpc.schema.json`: a `model.export` request and its result, plus progress through
  `run.phase`-style notifications.
- New diagnostic codes, checked against `src/diagnostics.jl` before use: E110 (construct not
  exportable), E111 (structure not supported by the chosen integrator), W207 (RK4 substeps
  above the step budget), W208 (accuracy target not met at the chosen `dt`). W203 and the `dt`
  part of E104 become active.
- Spec: the target-platform paragraph (generated C, FMU, C API; ctrlX runs it without Julia),
  the "Future option: C++ export" paragraph (superseded), the pipeline figure (C/FMU output),
  and the open question on bit-exactness (answered by D-EX14).
- `IMPLEMENTATION_PLAN.md` section 12: export moves from out of scope to this plan.

## 11. Recommended landing path

1. **J-EX1 + P-EX1 + X-EX1 together**: the spike's generator moved into `src/export/` with
   tests, the backend build, and `fmu_compare` on dc-motor. This is a vertical slice from
   model to validated FMU.
2. **J-EX2**: the analysis and the export report, so every later model shows its stability
   bound and error.
3. **J-EX3**: Rosenbrock with mass matrix, which unlocks most of the remaining examples.

What not to do: do not add Model Exchange to "support more tools" (it gives up the real-time
contract); do not use `-ffast-math`; do not let the generated code call into the hand-written
runtime through anything other than the fixed `bg_*` API, so the runtime can be versioned and
certified once.

## 12. Out of scope

- FMI 3.0 Scheduled Execution (clock-driven partitions as separate tasks): maps well onto our
  partitions but has little tool support yet.
- ctrlX Data Layer integration and the SIL harness (they use the C API from this plan).
- Variable-step or event-locating solvers in exported code.
- Lie-group integrators (RKMK, Crouch-Grossman) for poses; revisit with the spec's open
  decision on pose states.
- Code signing, MISRA certification of the runtime (the hot-path rules here are a start).
