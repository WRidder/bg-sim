# C export and FMU: assessment and implementation plan

Status: v0.2, 2026-10-30 (J-EX1 in progress on branch `export-fmu`). Input: `spec/Modeling Language Spec v0.1.md` (target platform,
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
the target** (C only; a thin C++ wrapper on top, no separate C++ export):

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
  (`bg_interp1/2`, the `bg_*` mechanics functions in `src/lower/fnmap.jl`), so each
  needs exactly one hand-written C twin. (`bg_csv` is not exported: see section 6.)
- `ExportInput`/`ExportOutput`/`ExportParameter` blocks (`stdlib/converters/`) and stable signal
  IDs: the interface names.
- `tunable = true` on parameters, and D4 (all parameters are runtime parameters in simulation,
  folding is left to export).
- The example runner and `expected.json` checks: the place for "FMU matches simulation".

## 4. Decisions to freeze before coding

| id | topic | decision | why |
| --- | --- | --- | --- |
| D-EX1 | Target | Generated **C99**, from the `mtkcompile`d system. There is no separate C++ export: an optional header-only C++ wrapper (a class owning the instance) sits on the C API, and CI checks that the sources also compile as C++. `juliac` is dropped as the target. | Section 1. One generated language keeps the build, review and certification surface small; the wrapper and the check make embedding in a C++ application easy. |
| D-EX2 | Layers | Three layers: generated `model.c/.h` (the model), a hand-written versioned runtime (solver, tick, helpers), and a hand-written FMI wrapper. The plain C API (`bg_reset`, `bg_step`, get/set) is usable without FMI. | ctrlX apps and MCU firmware call the C API directly; FMI tools use the wrapper. Generated code stays minimal. |
| D-EX3 | Packaging | FMI **2.0 Co-Simulation** first, **3.0 Co-Simulation** second. Every FMU carries its sources (source FMU; FMI 3 adds `buildDescription.xml`) plus a binary for each platform built. Model Exchange is not offered. Scheduled Execution (FMI 3) is deferred. | Co-Simulation keeps our solver and our fixed step; Model Exchange hands integration to the host and gives up the real-time guarantees. Sources make cross-compiling for the target possible. |
| D-EX4 | Memory | One instance struct with every array sized at generation time. FMI allocates it once in `Instantiate` through the host's callback. A `BG_STATIC_INSTANCE` build option uses one static instance and no callback, for MCUs. | "No allocation after construction", provable. |
| D-EX5 | Time base | A fixed internal step `dt` (whole nanoseconds). Time is `t_start + n·dt` from an integer step counter, never accumulated. `doStep(h)` requires `h` to be a whole multiple of `dt`. Discrete periods and offsets must be multiples of `dt` (E104). | Deterministic, drift-free, matches the scheduler's integer-ns ticks. |
| D-EX6 | Integrators | Explicit Euler, RK4, and fixed-step linearly implicit Rosenbrock methods with mass-matrix support: ROS2 (spike; order 2), ROS34PW2 (Rang and Angermann 2005; order 3, 4 stages, a W-method) and Rodas4P (Steinebach 1995; order 4, 6 stages). All three are L-stable; the last two are stiffly accurate and keep their order on index-1 DAEs and on the Prothero-Robinson problem. ROS3P is not used: it is not L-stable (R(∞) = 0.73). Rodas4 and Rodas3 lose an order to order reduction on stiff, time-dependent components (measured in J-EX3). No method with an inner Newton iteration in the hot path. | Section 2, finding 3. Rosenbrock needs one Jacobian and one LU per step, a fixed cost, and handles index-1 DAEs directly. |
| D-EX7 | Step and integrator selection | The exporter proposes `dt` and the integrator: (a) a **stability** bound from the Jacobian's eigenvalues sampled along a reference run, (b) an **accuracy** check that runs the generated code against the reference and refines `dt` until a user error target is met, (c) a **cost** comparison (RK4 substeps vs one Rosenbrock step). The user can override every choice; the report shows the numbers. **Rosenbrock step rule:** every mode is resolved (the RK4 per-step error at `h·|λ| = accuracy`), or damped in one step by both the method and the exact flow (`damping`, 0.05), or **damped numerically**: the method damps it below `damping` and it is stiff relative to the step (`h·|λ| >= stiff_ratio`, 10), although the exact flow keeps it (an undamped joint stiffness). The threshold keeps an undamped mode in the bandwidth (a pendulum, an LC circuit) resolved. When a step uses this case, ROS2 is not suggested (it is not stiffly accurate); ROS34PW2 or Rodas4P is. **Over-budget fallback:** when `damping` is not set and no candidate meets the rule within `max_substeps`, `:auto` runs the selection once more with `damping` = 0.5 and suggests that pick if it fits the budget (W214). An explicit `damping` turns this off. It is meant for the compliant-joint arms, whose stiff held directions are overdamped real modes that Rodas4P damps by only 0.1 to 0.5 per step. Both cases are a recommendation, not a fact about the model: W213 counts the numerically damped modes with their lowest frequency (`spectrum.numericallyDamped` in `export.json`), `spectrum.damping` and `spectrum.relaxedDamping` show the rule used, and `method = rk4` resolves every mode. | Findings 1–3. A stability-only rule gave a 9 % error. |
| D-EX8 | Switching | Every `ifelse` condition in continuous code (including the rewritten `abs`/`min`/`max`/`clamp`/...) becomes a mode value, evaluated once at the start of each step and held through all stages. `@events` conditions are checked after each step; `reinit` is applied then. Each site is reported as W203 with its origin. | Finding 4; the spec's fixed-step semantics. |
| D-EX9 | Interface | **The user defines the interface; the exporter never publishes "the whole model".** `ExportInput` → FMU input (its `value` parameter becomes the input slot; in simulation it is a constant, later also a table source), `ExportOutput` → output (the signal on its input), `ExportParameter` or `tunable = true` → tunable parameter. Names are the marker's instance name (a `name` attribute later). Where the markers sit also decides *what* is exported: to export only the plant for SIL, a model variant replaces the controller by an `ExportInput` on its output. Without markers the export warns W209. The export dialog suggests candidates (sources as inputs, sensors as outputs) with a one-click "promote to marker". "Expose all signals" is a separate debug option that adds every recorded signal as a read-only `local`; it does not change the interface. **Scope (J-EX11):** the export can be limited to one subsystem, with its ports as the interface: a signal port becomes an input or output marker, and a power port gets an adapter that imposes the variable the user picks (effort or flow) and publishes its conjugate (`<port>_e`, `<port>_f`, the flow counted into the subsystem). Everything outside the subsystem is dropped, so a test harness or an unsupported element (a CSV source, an event the export cannot take) can stay in the model as long as it sits outside the scope. Later: the causality analysis proposes effort or flow per power port (as 20-sim does), and a library block can be the scope directly. | The spec's interface contract; the interface is a design decision of the user, not something the compiler can infer. |
| D-EX10 | Parameters | Non-tunable parameters are **folded** into constants by default. `tunable = true` parameters (and `ExportParameter`), inputs and held discrete values stay fields, settable at any time. An option (`fold_parameters = false`) keeps all parameters as fields (settable before initialization); nothing is substituted then. **Folding simplifies** (`simplify = true`, `src/export/simplify.jl`): the folded values are substituted into the right-hand side, the observed equations (in order, so an observed value that becomes a constant is substituted further), the outputs and the event conditions and values, *before* the Jacobian pattern, the symbolic Jacobian and the C code. The rules are cheap and predictable, applied bottom-up once per distinct subexpression: a call on constants is evaluated (arithmetic, comparisons, logic, the elementary functions; never `round`, an intrinsic or a domain error), SymbolicUtils' own rebuild of `+`/`*`/`/`/`^` removes `0*x`, `1*x`, `x+0`, `x^1`, `x/1` and merges coefficients, a constant `ifelse` condition selects its branch (so the frozen mode disappears too), `&`/`|` with a constant reduce. No full `simplify` (unpredictable in time and form). Tables keep their literals through `env`. The emitter adds a peephole for leftovers (`_c_product`, `_c_sum`): literal operands fold, `0.0 * x` → `0.0`, `1.0 * x` → `x`, `(-1.0) * x` → `-x`, `a + (-1.0) * b` → `a - b`. The discrete partitions (bit-exact against the Julia scheduler, section 8) get only the exact part: `1.0` factors dropped, `(-1.0)` as a negation, all-literal products folded left to right. **Accepted semantic difference:** `0*x → 0` drops the NaN of an infinite or NaN `x` and the sign of a zero product (`0.0 * -3.0` is `-0.0`), and `x + 0 → x` keeps the sign of a negative zero (`-0.0 + 0.0` is `+0.0`); every other rule is exact in IEEE arithmetic (a negation, or a swap of two addends), except that literal operands of one sum or product are combined first (a rounding-level reordering). `simplify = false` keeps the expressions as compiled (for comparisons); `export.json` reports `simplify` (RHS operations, structural Jacobian non-zeros, LU non-zeros and flops, before and after). | D4 left folding to export; folding shrinks code. gcc -O2 without `-ffast-math` may not remove `0.0 * x` or `x + 0.0`, and the structural pattern counted such terms as non-zeros, which enlarged the static sparse LU. |
| D-EX11 | Initialization | Phase 1: start values computed in Julia at export with the current parameters, and baked in. Phase 2: MTK's initialization system is generated as C and solved with a bounded Newton iteration in `ExitInitializationMode`, which is outside the hot path. **Phase 2 as built (J-EX8):** not MTK's whole initialization system, but what it reduces to for the exported models: the generated `bg_init_values` recomputes the calculated parameters, the starts and held values written over the values set before init, then `bg_init` runs a bounded Newton (50 iterations) on the algebraic block, the same Newton as `bg_project` after a tick. At export each tunable is perturbed inside its range and MTK's initialization (a Julia run with that value) is compared with this C one emulated in Julia; a difference above 1e-6 is E110 (a state that MTK's initialization moves, which the C would not). | Phase 1 suffices for fixed parameters; phase 2 is needed when initialization depends on parameters that are set before init. |
| D-EX12 | Jacobian | Symbolic by the chain rule through the observed equations (each partial of each observed local once, so common subexpressions by construction; `calculate_jacobian` substitutes everything and blows up), written on the sparse pattern. Fallback for expressions that blow up: finite differences with column colouring (fixed cost of `ncolours` derivative calls). The pattern and the partials are taken **after** the folded values are substituted and simplified (D-EX10), so a dependency through a zero folded value (an axis component, an offset, a zero gain) is not a structural non-zero, and neither the LU nor the colouring pays for it. A tunable parameter or an input is never substituted, so its entries stay structural for every value it may take. | Rosenbrock needs J every step. |
| D-EX13 | Linear algebra | Dense in-place LU with partial pivoting for small systems; generated static sparse LU (symbolic factorization at export, fixed fill-in) above a size threshold (start at nx > 40). **Row matching for DAEs:** when W = M − hγJ has a structural zero on its diagonal (an algebraic unknown its own row does not read; the compiled system pairs the k-th algebraic equation with the k-th algebraic unknown) or the identity fails the pivot check, a static row permutation is computed at export: rows with mass keep their diagonal, the algebraic rows are assigned to the algebraic unknowns on the pattern of ∂g/∂z by a maximum-product assignment over the scanned Jacobians (MC64's objective, row-scaled, worst case over the points; a structural maximum matching without Jacobians). Minimum degree then orders the row-matched pattern. The runtime cost stays fixed (one more static index table); a matched LU that still fails the check falls back to dense with W211, which says whether the matching was tried. The check runs at every scanned point with the method's γ and h and the mass matrix, and decides on the componentwise backward error. No equilibration: the target models pass without it. With the sparse LU, `bg_project` (the re-solve of the algebraic unknowns after a tick or event) factors ∂g/∂z on the same tables when that passes the same check (`BG_SPARSE_PROJECT`), else it eliminates densely. | Fixed cost, no allocation; the 72-state arm makes this real. The rigid-joint Panda (154 and 168 states, 140 algebraic) paid 2.4 to 3.1 Mflop for the dense LU; matched, the sparse LU takes 32 to 38 kflop, and both Pandas run in real time at 1 ms (section 5.4). |
| D-EX14 | Numerics | `-std=c99 -O2 -fno-math-errno`, no `-ffast-math`. Non-finite state → error status, never silently continued. Subnormal flush is a documented target setting. Results match simulation **within tolerance**, not bit-exact (answers the spec's open question: repeatability per target, not across targets). | libm differs from Julia in the last bit; bit-exact output would forbid every libm. |
| D-EX16 | Values that move the spectrum | Every runtime-settable value the Jacobian depends on (tunable parameters, inputs) needs a declared range (`min`/`max`). The step is chosen over that range (each end, and every corner of the box for up to 6 values), not only at the start values. The FMU refuses `SetReal` outside the range, so the stability proof holds for every accepted value; the range is also published as FMI `min`/`max`. A settable value without a complete range gets W210 (stable only for the scanned values). Gains that only discrete code reads are not scanned: they change the closed loop, which simulation shows as well. When ranges are wide or unknown, an L-stable Rosenbrock export is the robust choice (stable for any value on linear(ised) dynamics). Later: an eigenvalue bound recomputed when a value changes, outside the hot path. **Values set before initialization (J-EX8):** a picked block parameter takes the user's range, else its catalog `min`/`max` per end; an exposed global takes the user's range only (W210 when open). They join the scan like a tunable parameter (a global through the parameters calculated from it). The FMU **refuses**, never clamps: `fmi2SetReal` outside the range returns `fmi2Error` and logs `fmi2SetReal: parameter <name> = <v> is outside its declared range [lo, hi]` (inputs likewise), because a silently changed value would hide the mistake and the proof covers the range only. A range that leaves out the model's own value is E110 at export. | A step proven stable at the start values says nothing about a raised stiffness or gain at runtime. |
| D-EX17 | Quaternion norm | Exported code does **not** renormalize quaternion states (decided in J-EX5, section 5.4). | The spec asks for one choice in simulation and the target build, and simulation does not project. The pose blocks are norm-invariant (`R(q)` is the quadratic form over `|q|²`), so a drifting norm does not change the motion. The solver cannot tell quaternion states from others, and a projection would make the FMU differ from simulation. |
| D-EX15 | Toolchain | The backend builds binaries with a gcc/clang on PATH, or with `zig cc` from the PyPI `ziglang` package (`uv`-installable) for cross targets: x86_64-linux, aarch64-linux (ctrlX CORE), x86_64-windows. Without a compiler the export still produces a source FMU. | Fits the repo's `uv` rule; one cross-compiler for all targets. Note: the `cl` on this machine is Open Watcom, not MSVC. |

## 5. Target architecture

### 5.1 Layers and files

```
julia/BGSim/src/export/
  export.jl        entry point: export_model(flat, settings) -> ExportResult
  emit_c.jl        SymbolicUtils tree -> C (from spike gen.jl cexpr), CSE, modes
  emit_discrete.jl step_expression Expr -> C (from spike dstmt/dval)
  analysis.jl      eigenvalue scan, stability bound, accuracy loop, cost model
  (export.jl)      Export markers -> value references, folding, ranges (D-EX9, D-EX10, D-EX16)
  fmi.jl           modelDescription.xml (2.0 and 3.0), buildDescription.xml
julia/BGSim/export/runtime/      hand-written C, versioned, copied into every FMU
  bg_runtime.h     language semantics (sign, round, clamp, deadzone, mod, ...)
  bg_solver.c      Euler / RK4 / Rosenbrock, LU, modes, tick, events
  bg_intrinsics.c  interp1/interp2 over constant tables, the noise draws and the delay ring (J-EX9)
  bg_mech.c        SE2/SE3 exp/log, quaternion functions, spatial inertia
  fmi2_cs.c, fmi3_cs.c
  bg_model.hpp     optional header-only C++ wrapper on the C API
backend/src/bgsim_server/fmu_build.py compile, symbol check, allocation harness, zip
backend/src/bgsim_server/exports.py   the HTTP endpoint, store under the project (P-EX1 second half)
backend/src/bgsim_server/fake_export.py  the export runner of the fake worker (e2e)
julia/BGSim/src/export/job.jl     export_job: one dialog request (scope, flatten, reference run, export)
julia/BGSim/export/export_job.jl  the per-job Julia process the backend starts
examples/export_examples.jl, export_checks.py   the X-EX0 gate over every example
web/src/export/                   the Export dialog (W-EX1): scope, interface, settings, report, download
```

### 5.2 Flow

1. The backend starts **one Julia process per export job** (`export/export_job.jl`,
   `Export.export_job`), not a worker RPC: an export takes minutes, and the interactive
   worker must keep answering the supervisor's 5 s health ping. The job applies the scope
   (J-EX11), flattens, checks exportability (E110/E111/E112), and runs the reference
   simulation (with a time budget; its trajectory widens the spectrum scan). Its phase goes
   to the backend as `@@bgsim {"phase": ...}` lines on stdout.
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

### 5.4 Sparse Jacobian and static sparse LU (J-EX4)

`src/export/sparse.jl`. Every Rosenbrock solve goes through two functions declared in
`model.h`: `bg_w_factor(m, hg)` forms W = M − hg·J from `m->jac` and `bg_mass` and factors
it, and `bg_w_solve(m, b)` solves in place. The Rosenbrock step fills `m->jac` with
`bg_jacobian` in the layout of the LU (row-major, or the positions of the static pattern).
The dense versions are in `bg_solver.c`. With `#define BG_SPARSE_LU` in `model.h`,
`model.c` holds generated sparse versions instead.

- **Pattern.** The dependency sets of the right-hand side, followed through `observed`,
  after the folded values are substituted and simplified (D-EX10). It is
  structural, not the numeric zeros of one point. The export adds any numeric non-zero of the
  Jacobian at the start point and reports the count (`patternAddedFromNumeric`, expected 0).
- **Row matching (DAEs).** The compiled system puts the k-th algebraic equation in the row
  of the k-th algebraic unknown, an arbitrary pairing, so W can have a structural zero on an
  algebraic diagonal (the index-reduced rigid-joint chains: every one of them). When the
  diagonal of W is not structurally full, or the identity fails the pivot check,
  `row_matching` computes a static row permutation: rows with mass keep their diagonal, and
  the algebraic rows are assigned to the algebraic unknowns on the pattern of ∂g/∂z (an
  index-1 DAE has it structurally non-singular). The assignment maximises the product over
  the pivots of `min over the scanned points |J_ij| / max_k |J_ik|` (MC64's objective with
  the row scaling; hγ cancels in an algebraic row), by a Hungarian algorithm on the
  algebraic block (O(n³), milliseconds for 140 unknowns); a structural zero that is
  numerically zero at a point costs more than any non-zero entry, ties keep a row on its
  diagonal, and the result is deterministic. Without Jacobians (the cost model) it is a
  structural maximum matching (diagonal first, then augmenting paths). The matching is kept
  when it passes the check (or beats the identity's pivot ratio). `export.json` reports
  `linearAlgebra.matching`: `tried`, `used`, `rowsPermuted`, `weighted`,
  `structuralDiagonal`; W211 says whether it was tried. No equilibration: every target
  model passes without it.
- **Ordering and factors.** Exact minimum degree on the symmetric pattern of the
  row-matched W, then a symbolic LU of Pr·W·Pcᵀ with a fixed fill-in (Pr = Pc without a
  matching). C runs the factorization from static index tables: row-compressed factors, one
  destination per multiply-add, `bg_lu_rperm` (the equation of pivot k) and `bg_lu_perm`
  (its unknown). Every loop runs over these tables, so the cost is fixed. `bg_jacobian`
  writes J[i][j] (row i of the C code) at its position in the factored layout, and the mass
  goes to the position of (i, i), so nothing outside `sparse.jl` sees the permutation.
- **Static pivoting.** The pivots are the diagonal of Pr·W·Pcᵀ in a fixed order. This is
  safe when W is diagonally dominant (small hγ, W → I) or when its symmetric part is
  positive definite (J dissipative); every pivot is then at least 1. Neither holds in
  general, and an algebraic row has no mass to help. So `bg_w_factor` returns an error when
  a pivot is below 1e-12 of the largest entry of its row, and the export factors W at every
  scanned point of the spectrum scan (the start, the D-EX16 range corners and 25 reference
  rows) with the chosen method's γ and h and the mass matrix. A failed check (a pivot below
  1e-12 of its row, or a componentwise backward error of a solve above 1e-10, Oettli-Prager)
  gives W211 and falls back to the dense LU, unless the sparse LU was forced. The backward
  error replaced the earlier test, the relative difference to a pivoted dense solve below
  1e-8 (still reported as `residual`). That test is not invariant to row scaling, and a DAE's
  W is badly row-scaled: differential rows O(1), algebraic rows O(hγ|J|). On the rigid RRR
  arm (cond(W) 1e10, 3e3 after row scaling), the static LU's backward error is 2e-16 at
  every point. LAPACK's partial pivoting reaches 6e-8, because it pivots on the differential
  rows. The difference of the two solves reached 6e-9 for that reason, close to the old limit.
- **Re-solve of the algebraic unknowns (`bg_project`).** After a tick or an event a DAE
  re-solves z by Newton on 0 = g(x_d, z). With the sparse LU, its Newton matrix (identity
  rows for the states with mass, the rows of J for the algebraic equations) is factored on
  the same static tables (`bg_alg_factor`, `BG_SPARSE_PROJECT`) when its pivots pass the same
  check at the scanned points (`linearAlgebra.projection`); elimination with the identity
  rows changes nothing, so the pivots are those of ∂g/∂z in the matched order. A bad pivot
  at run time falls back to the dense elimination of the BG_NALG × BG_NALG block (the only
  path with the dense LU), which cost the rigid Panda about 2 Mflop per Newton iteration.
- **Jacobian.** Symbolic by the chain rule through `observed` (`jacobian_c`, J-EX3), while it
  needs at most `symbolic_jacobian_limit` terms (2e5) and 120 s. Above that, or when a partial
  has no C form (an intrinsic has no symbolic derivative), forward differences in C with a
  greedy distance-2 column colouring: `ncolours + 1` derivative calls, workspace on the stack
  (W212 unless `jacobian = fd` was asked). The cost model prices both, and the LU, from the
  pattern before it picks the method.
- **Settings.** `linear_solver` (`auto` = sparse above `sparse_threshold` = 40 states,
  `dense`, `sparse`) and `jacobian` (`auto`, `symbolic`, `fd`). `export.json` reports
  `linearAlgebra`: non-zeros of J and of the factors, fill-in, colours, flops of the sparse and
  dense LU, and the pivot check. The gate takes `--settings JSON` and prints a step-time table.
- **Mass matrix (J-EX3).** The forming step adds `bg_mass[i]` at the positions
  `bg_lu_mpos` of the entries (i, i) of W. A zero mass entry (algebraic row) leaves its
  pivot to J alone: −hγ·J_ii without a matching, −hγ·∂g_i/∂z_j of its matched unknown with
  one; the pivot check, which forms W with M and the chosen method's γ, then decides whether
  the static order holds.
- **Row matching and the sparse projection, measured (D-EX13).** These are gate runs
  (`export_checks.py --budget 900`, gcc 14 -O2, this machine; other agents loaded the CPU)
  on master and on this branch. The first doStep column is master. The second has the
  matching only. The third adds the sparse projection, and is the final branch.

  The double pendulum is the non-planar rigid double 3D pendulum of `test_rigid_spatial.jl`
  (1.5 s). `rrr-multibond-rigid` is `rrr-multibond` with every `Revolute3D` swapped for
  `Revolute3DRigid` (5 s, a 1 ms controller). Neither is an example model; both were built
  in a scratch project.

  | model | method, dt | states (alg) | LU flops: master (dense) → branch (sparse), nnz LU | rows matched | doStep mean / max µs: master → matching → + sparse projection | worst error vs reference |
  | --- | --- | --- | --- | --- | --- | --- |
  | `panda-3d/panda-free-rigid` | ros34pw2, 1 ms | 154 (140) | 2,423,113 → 32,005, 2948 | 84 | 581 / 1805 → 27.6 / 381 → 27.5 / 258 | 1.21e-2 (same) |
  | `panda-3d/panda-rigid` | rodas4p, 0.25 ms × 4 | 168 (140) | 3,147,116 → 38,304, 3203 | 84 | 3604 / 8872 → 668 / 3890 → 184 / 759 | 3.16e-5 (same) |
  | double pendulum (rigid) | ros2, 1 ms | 44 (40) | 55,858 → 633, 296 | 22 | 18.4 / 92 → 2.09 / 42 → 2.21 / 176 | 6.54e-4 (same) |
  | `rrr-multibond-rigid` | ros2, 1 ms | 66 (60) | 189,541 → 1,432, 518 | 36 | 99.2 / 1160 → 48.6 / 518 → 6.64 / 95 | 9.02e-4 (same) |

  The other columns:

  * **Pivot check.** The smallest pivot ratio is 1.6e-4, 5.9e-7, 2.4e-3 and 1.2e-2. The
    backward error is at most 1.5e-15 at the 26 points. The projection check passes for
    all four.
  * **Error column.** The worst error is relative to the signal's peak. For
    `panda-free-rigid` it is on a body effort `B1/inertia/p.e[4]`; the joint angles are
    better.
  * **Dense against sparse.** The dense and sparse FMUs of the two Pandas agree signal by
    signal (2375 and 2661 signals) to 1.9e-12 and 3.4e-11 of each signal's peak.
  * **Effect of the matching alone.** With the matching only, the rigid Pandas dropped
    20× and 5×.
  * **Where the remaining time went.** Profiling `panda-rigid` showed it in `bg_project`.
    The 1 ms controller tick re-solved the 140 algebraic unknowns with a dense elimination,
    1.8 Newton iterations per tick at about 2 Mflop each. That was 730 of the 900 µs of a
    doStep; with the projection disabled a doStep took 155 µs.
  * **Real time at 1 ms.** A QPC histogram of 5150 `panda-rigid` doSteps through the C API
    (three runs) gives:
    * median 178 µs, p99 430 µs, p99.9 520 to 570 µs;
    * 0 to 4 steps over 1 ms, each an isolated OS preemption on this desktop.

    `panda-free-rigid` gives median 23 to 41 µs and max 120 to 320 µs. **Both rigid Pandas
    run in real time at a 1 ms communication step with margin.** The deterministic worst
    case of `panda-rigid`'s tick is 8 Newton iterations, each one Jacobian, one derivative
    call and one sparse LU of 38 kflop.

  The control models generate the same `model.c` except the version line, and the same
  method, `dt`, LU and worst error. In the measured run, the sparse ones also had a
  `bg_lu_rperm` table equal to `bg_lu_perm`; it is now a `#define`. Their timings move only
  within the run-to-run noise:

  * `robot-arm-3d/arm` 246 → 248 µs;
  * `panda-3d/panda` 1581 → 1631 µs;
  * `cube-3d` 85.0 → 85.3 µs;
  * `drivetrain` 1.3 → 1.8 µs;
  * `inverted-pendulum-cart` 0.54 → 0.83 µs.

  `inverted-pendulum-cart` is a DAE with 3 algebraic unknowns, a structural diagonal and a
  dense LU below the threshold, so it never tries the matching.
- **Folding and simplification, measured (D-EX10).** The gate with `simplify` false and
  true on the same branch (gcc 14 -O2, this machine; doStep is the mean of three
  alternating harness runs, ±5 % between runs). RHS ops is `op_count` of `bg_derivatives`;
  J terms are the symbolic Jacobian's multiply-adds; nnz J and the LU are structural.

  | model | RHS ops | nnz J | nnz LU / LU flops | J terms | method, dt | doStep mean µs | max error vs reference |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | robot-arm-3d/arm | 9170 → 4863 | 1533 → 1473 | 1908 → 1885 / 26574 → 25972 | 17380 → 12012 | rodas4p, 1e-4 | 315 → 272 | 1.0715e-1 (same) |
  | panda-3d/panda | 11155 → 7389 | 2062 (same) | 2600 / 37195 (same) | 22729 → 22177 | rodas4p, 2.5e-5 | 1677 → 1724 (six runs each, within the noise) | 1.1572e-3 (same) |
  | panda-3d/panda-free | 10798 → 7102 | 1845 (same) | 2376 / 35530 (same) | 21268 → 20716 | rodas4p, 2.5e-5 | 1541 → 1412 (one run) | 8.4578e-6 (same to 1e-5) |
  | Panda Robot (scoped, `export_robot.jl`) | 11155 → 7389 | 2062 (same) | 2600 / 37195 (same) | 22729 → 22177 | rodas4p, 2.5e-5 | 1825 → 1795 | 4.1328e-2 (same) |
  | cube-3d | 536 → 339 | 141 → 134 | dense, 6875 | 352 → 338 | rodas4p, 5e-5 | 102 → 90 | 1.1685e-7 (same) |
  | multibond-pendulum-2d | 215 → 69 | 30 → 25 | dense, 210 | 87 → 60 | rodas4p, 4e-5 | 25.1 → 24.2 | 0.7574 (same, W213/W214) |
  | drivetrain | 44 → 36 | 16 (same) | dense, 316 | 43 (same) | rodas4p, 5e-4 | 1.39 → 1.33 | 2.6036e-5 (same) |
  | dc-motor/speed-control | 17 → 10 | (RK4) | | | rk4, 6.25e-5 | 0.41 → 0.35 | 4.0012e-5 (same) |

  No model changed its method or `dt`. The two FMUs of each model agree to rounding: on
  signals with a real peak the largest difference is about 1e-11 of the peak (cube-3d
  `domega`: 4e-12; robot-arm-3d: 3e-12 absolute); relative values up to 2e-4 occur only on
  signals whose peak is itself rounding noise (a Coriolis power of 1e-13 W, `qerr` 3e-13).
  The substitution costs at most 0.05 s (panda). The robot arm's `model.c` shrinks from
  1270 KB to 939 KB and its `(0.0 * …` / `((-1.0) * …` counts from 553 / 3626 to 0. The
  gain in step time is in the Jacobian, where `0.0 * dx` products of the chain rule were
  real multiplications (arm: 31 % fewer terms, 14 % faster); most of the RHS operations
  removed were constant subexpressions (`(0.0 * 0.0) + (1.0 * 1.0)` of a folded axis) that
  gcc already folded at compile time, so the RHS count overstates the run-time gain. The
  Panda's pattern does not shrink: its couplings are real (full inertia tensors, nonzero
  joint offsets), and its step time is set by the Jacobian and the LU, so the Panda models
  are unchanged within the measurement noise.

  The full gate (64 models, `simplify` false vs true): the same 54 compared, 3 refused
  (planar-links, E110) and 7 over budget (pendulum-*-rotary, robot-arm-3d/rrr-multibond*,
  in lowering, before any export code runs) either way. Every compared model keeps its
  worst error to three digits except two. **hydraulic-servo** changes method: its RHS
  shrinks from 810 to 544 ops, so the cost model now prices RK4 (8 substeps of 0.125 ms)
  below Rodas4P (4 of 0.25 ms); the error drops from 6.2e-4 to 1.4e-4 and the doStep from
  2.1 to 1.1 µs. **aerial-contact** (same method and step) goes from 30.8 to 46.6 on
  `EE/inertia/p.e[1]`: both runs are already far off the reference (relative error far
  above 1). The two FMUs (RK4, 0.04 ms) agree to 2e-12 of every signal's peak up to
  t = 5.07 s, when the wheels touch down (a `max`-based contact law, not a frozen mode);
  within 10 ms the contact forces differ by their own size. The touch-down amplifies a
  rounding-level difference; it is not a loss of accuracy of the simplified code.

### 5.5 Intrinsics in C (J-EX5)

Every opaque registered function of the lowering except `bg_csv` has one hand-written C
twin: `bg_intrinsics.c` (`bg_interp1`, `bg_interp2`) and `bg_mech.c` (`bg_exp2`, `bg_log2`,
`bg_exp3`, `bg_log3`, `bg_quat_exp`, `bg_quat_log`, `bg_quat_from_rotation`, `bg_inertia2`,
`bg_inertia3`). Each follows its Julia body branch for branch and in the same operation
order. The emitter maps the calls in `src/export/emit_intrinsics.jl`.

- **CSV sources are not exported.** A `CsvSource` or `CsvSourceSampled` is simulation data
  (a stimulus or comparison data). In an exported model the host supplies such a signal
  through an `ExportInput`. The export refuses the block with E110 at its path, with the
  hint to replace it with an `ExportInput` in an export variant (or remove it).
- **Tables.** An `interp1`/`interp2` table arrives as an `array_literal` of parameters. When
  all of them are folded, the table is one file-scope `static const double bg_tab<k>[]`,
  shared by every call with the same content (the gain-scheduled cart pendulums read one
  table from many observed equations). A table with a tunable element becomes a local array
  in each function that reads it. `export.json` lists every table with its bytes
  (`tables`); the double cart pendulum has 14 tables (one shared breakpoint vector) for 26
  calls, 27 KB.
- **Several results.** The Julia mechanics functions return one component per call (a
  selector `k`). The C twins write all components into an array. Within one generated
  function, each distinct argument tuple is called once into a local `double bg_mv<k>[n]`,
  declared just before the first statement that needs it, and each component is a read
  `bg_mv<k>[k - 1]`. So the seven components of one `exp` cost one call, the same
  common-subexpression property as the observed locals. The inertia entries are cheap
  polynomials and keep the scalar form `(..., i, j)`. No example reaches these calls today:
  the stdlib writes the pose algebra component-wise, and the language checker does not yet
  accept vector arguments to `exp`/`log`/`quat_*` in a block (E004). The emitter test builds
  the symbolic calls of `lower_mech` directly.
- **No error exits.** Where Julia throws (a zero quaternion, a matrix that is not a
  rotation), the C function returns NaN or computes on. A NaN that reaches a state makes the
  step fail with an error status.
- **Interval search.** `interp1`/`interp2` use a binary search, a bounded loop of
  `ceil(log2 n)` steps. For strictly increasing breakpoints it picks the same interval as the
  Julia linear scan.
- **Golden tests** (`test/test_export_intrinsics.jl`, gcc only): every C function against
  its Julia twin on 2 000 random inputs per function that cover every branch (series
  switches, angles near pi, all four Shepperd branches, non-unit quaternions, table edges).
  Numbers travel as bit patterns, so the transport is exact. The error is norm-wise, in ulp
  of the group's scale: the largest component of the group, and for a translation part also
  its largest input (`exp([w; v])` scales with `|v|`); the folded angle of `log2` in ulp of
  pi. Measured with gcc 14 (MSYS2) against Julia 1.13, on the test's 2 000 cases and on
  20 000 (seed 7); a bound above 4 is the 20 000-case maximum with a margin:

  | function | 2 000 | 20 000 | bound | why |
  | --- | --- | --- | --- | --- |
  | `bg_interp1`, `bg_interp2` | 0 | 0 | 4 | bit-identical: same interval, same operations |
  | `bg_inertia2`, `bg_inertia3` | 0 | 0 | 4 | bit-identical |
  | `bg_quat_from_rotation` | 0 | 0 | 4 | |
  | `bg_quat_exp` | 2 | 2 | 4 | libm `sin`/`cos` |
  | `bg_quat_log` | 3 | 4 | 6 | libm `atan2` |
  | `bg_log2` | 4 | 4 | 6 | libm `sin`/`cos`/`tan`/`atan2` |
  | `bg_log3` | 4 | 4 | 6 | as `quat_log`, plus StaticArrays' `muladd` chains (FMA in Julia) against plain C arithmetic |
  | `bg_exp2` | 2 | 6 | 8 | libm's last bit of `cos`, amplified by `1 - cos θ` just above the 1e-2 series switch |
  | `bg_exp3` | 5 | 8.9 | 12 | the same cancellation in `(1 - cos θ)/θ²`; the quaternion passes three rounding stages as in Julia's `chart(exp(V))` (exponential, rotation matrix, Shepperd back) |

  The C and Julia bodies do the same operations, so the remaining difference is the libm
  against Julia's own elementary functions. Matching Julia bit for bit would need its
  `sin`/`cos` in C; a different target libm moves these numbers by about an ulp.

- **Noise and delay (J-EX9).** `noise_normal(seed, k)`/`noise_uniform(seed, k)` and the
  discrete `delay(x, T)` are discrete code. They reach C through `emit_discrete.jl` as
  `bg_noise_normal`, `bg_noise_uniform` and `bg_delay_ring` (`bg_intrinsics.c`). The noise
  is counter-based: SplitMix64 bits of `(seed, k)`, an exact uniform `(2j + 1) 2^-53`, and
  Wichura's AS 241 with a logarithm of plain IEEE arithmetic (`frexp` and an atanh series)
  instead of libm's `log`. Every operation is exactly rounded and specified, so the C value
  is the Julia value bit for bit. Unlike the libm functions above, this is not "within a few
  ulp" (spec "Seeded noise and delay"). There is no generator state: the sample index is the
  `Noise` block's held tick counter, which already lives in `m->d`, so `bg_reset`
  (instantiate, `fmi2SetupExperiment`, `fmi2Reset`) restarts the stream. Each `delay` call
  site owns a ring of `T/Ts` slots in `m->ring` (laid out by `Compile.discrete_rings`, the
  same layout as the simulator's `DiscreteState.ring`) and a write position in
  `m->ring_pos`. Both are fixed-size struct members, zeroed by `bg_reset`'s `memset`. FMU
  state get/set is not offered (`fmi2GetFMUstate` refuses), so nothing else holds the rings.
  `bg_intrinsics.c` turns off FMA contraction for clang and MSVC, and the FMU builds in ISO
  C mode, where GCC does not contract. `TransportDelay` reads its two ring samples as held
  values and interpolates in the continuous code: `y = initial + ea + (t - tk)/Ts (eb - ea)`.

- **Quaternion norm (D-EX17).** Exported code does not renormalize. Simulation does not
  either: no `ManifoldProjection` is attached, and the pose blocks (`PoseIntegrator3D`,
  `Free3D`, `Spherical3D`, the transforms) divide the rotation's quadratic form by
  `s = |q|²`, so the motion does not depend on the norm. The kinematics
  `ddt(q) = 0.5 q ⊗ [0, ω]` keep `|q|` exactly; only the integrator changes it. Per step,
  RK4 shrinks it by about `(hω/2)⁶/144` (`|R(iy)|² = 1 - y⁶/72 + ...`, `ω` the body rate):
  1e-16 at 10 rad/s and 1 ms, 4e-10 per hour at 1 kHz; 1e-10 per step at 100 rad/s,
  4e-4 per hour. So the norm stays far from zero for any realistic run, and the result
  matches simulation. A projection inside
  the solver would need to know which states form a quaternion (the solver does not), and
  it would make the FMU differ from simulation. Revisit with the spec's open decision on pose
  states (Lie-group integrators, section 12): if it ever changes, it changes in simulation
  and export together.

## 6. Exportability rules

| construct | export status |
| --- | --- |
| ODE (identity mass matrix) | supported (phase A) |
| Index-1 DAE (mass matrix), torn algebraic loops (W202) | supported with Rosenbrock (phase B); RK4/Euler refuse it with E111 |
| Index > 1 after `mtkcompile` | E111 (MTK's index reduction normally prevents this) |
| `ifelse`, `abs`, `sign`, `min`, `max`, `clamp`, `saturate`, `deadzone`, `floor`, `ceil`, `round` | supported, frozen per step, W203 per site |
| `@events` with `reinit` | supported for state targets (J-EX6), checked after each step, W203 per event; an event that writes a parameter gets E110 |
| `@discrete`, `previous`, `hold`, multi-rate | supported; E104 at the clock's block when a period or an offset is not a multiple of `dt` |
| `interp1`, `interp2` over constant tables of the model | supported; each table becomes one `static const` array (phase C); W-level size report |
| `csv_value` (`CsvSource`) | not exported (E110): a CSV source is simulation data (stimulus or comparison). In an export variant an `ExportInput` replaces it, so the host supplies the signal |
| mechanics functions (`exp`/`log` on SE2/SE3, quaternions, `spatial_inertia`) | supported through `bg_mech.c` (phase C) |
| `delay` (discrete, `IntegerDelay`, `TransportDelay`) | supported (J-EX9): a discrete intrinsic with a ring buffer of `T/Ts` slots per call in the instance struct (`m->ring`, zeroed by `bg_reset`), bit-exact; `TransportDelay` interpolates between its samples in the continuous code, so it matches within the continuous tolerance. More than 2^20 slots per model is E110 |
| `noise_normal`, `noise_uniform` (`Noise`) | supported (J-EX9): counter-based (SplitMix64 + AS 241 with an IEEE-only logarithm), no generator state, bit-identical to simulation |
| debug hooks, watches | not exported |

Unsupported constructs fail with **E110** naming the block path and source range, as every
other diagnostic does.

**One internal step, in order (J-EX6).** `bg_step` advances one `dt` from `t` to `t + dt`:

1. evaluate the frozen switching conditions (`bg_modes`) and every `@events` condition `z`
   at `t`;
2. integrate the step;
3. apply each event whose `z` crossed upward in the step (`z < 0` at `t`, `z >= 0` at
   `t + dt`), in declaration order. All assignments of one event read the state before it;
   a later event reads what the earlier ones wrote;
4. run the discrete partitions due at `t + dt`. They sample the state after the `reinit`.

This is the simulator's order and edge rule. There, an event fires on DiffEq's upward edge
(`prev < 0`, `next >= 0`), and a tick at `t` runs after every event up to and including `t`.
A condition that is zero or positive at the start of a step never fires in that step. So a
condition that is already true at `t_start`, or still true after its own `reinit`, fires again
only after it has gone negative. The export does not locate the crossing: an event is up to
one `dt` late, and events that cross in the same step fire in declaration order, not in the
order of their instants. W203 reports each event at its block and source range.

## 7. Work packages

Naming follows the main plan: J (Julia), P (Python backend), W (web), X (examples and CI).

### Phase A: promote the spike (MVP)

| WP | scope | acceptance |
| --- | --- | --- |
| X-EX0 | **The standing gate: every example model is exported and compared with its simulation.** `examples/export_examples.jl` + `examples/export_checks.py`: export each model (`expose_all`), run its reference simulation (the model's solver and horizon, tolerances tightened to ≤ 1e-8/1e-10), build the FMU, run it in fmpy and compare every recorded signal (error relative to the signal's peak, right limits at event instants). The result is a coverage matrix: `compared` (with the worst error), `refused` (with the E-code and reason), `build_failed`, `diverged`, `fmu_error`. Each example's `expected.json` records its expected export outcome (`"export": {"status": "compared", "max_rel_error": …}` or `{"status": "refused", "code": "E111"}`), so a phase that adds coverage flips entries visibly and a regression fails. Examples with Export markers (dc-motor speed control first) also compare the real input/output path: the same input trajectory into the FMU and into the simulation. | runs in CI next to `run_checks.py`; the matrix is recorded in `plan/STATUS.md` after every phase |
| J-EX1 | `src/export/` with the C emitter (spike `cexpr` + CSE + modes), discrete emitter, RK4 + Euler runtime, baked initialization, interface from Export markers, folding (D-EX10), ranges (D-EX16), FMI 2.0 CS description | dc-motor `iconic`/`speed-control` and drivetrain export; generated code compiles `-std=c99 -Wall -Wextra -Werror` |
| J-EX2 | Analysis: eigenvalue scan, RK4 stability bound, accuracy loop against the reference, export report | the dc-motor report predicts the 0.72 ms bound; the accuracy loop lands on a `dt` that meets 1e-4 |
| P-EX1 | `exports.py`: compile, symbol check, counting harness, zip, `POST /api/projects/{p}/models/{m}/export` | the FMU passes `fmpy` validation; allocation count after instantiate is 0. **Done (branch `export-fmu-ui`):** `fmu_build.py` (objects compiled once, `-fPIC`, linked into the library and the harness; MSYS2 gcc found by default) and the endpoint in `exports.py`: `POST .../export` starts a cancellable job (one Julia process per job, `export/export_job.jl`, one job at a time), `GET /api/exports/{id}` is the `ExportJob` with the report, `DELETE` cancels, `GET /api/exports/{id}/fmu` downloads. Measured from the dialog on this machine: dc-motor speed-control RK4 62.5 µs, 56 s in all (Julia start 14 s, reference 2.9 s, analysis and C 10 s, build 28 s), 0 allocations over 20000 doSteps, fmpy validate OK, worst error 4e-5; panda scope `Robot` Rodas4P 25 µs, 224 s (reference 29 s, build 155 s, 87 s after the object reuse), 0 allocations, fmpy validate OK, worst error 9.6e-4 |
| X-EX1 | Export markers on the first examples (dc-motor speed control: `ExportInput` speed setpoint, `ExportOutput` measured speed and current; drivetrain: torque in, load speed out) and the input-trajectory comparison in X-EX0 | the FMU driven through its inputs matches the simulation driven by the same trajectory. **Done (branch `xex1-markers`).** *Markers.* A pass-through input marker `stdlib:converters/ExportInputPass` (`y = u` in simulation, so a model keeps its own stimulus and simulates bit for bit as before; `value` is the FMU input's start value). The export cuts its wire (`Export.host_inputs(flat)`, `src/export/interface.jl`: the marker's `y ~ u` becomes `y ~ value`, so it exports exactly like an `ExportInput`); `export_model` and the export job apply it, so the job's reference sees what the FMU sees. dc-motor `speed-control`: `speed_ref` in (between `Step1` and `Err`), `speed` (`WmSens/y`) and `current` (a series `CurrentSensor`) out. drivetrain: `voltage` and `load_torque` in (the load step now carries the 0.5 N·m, `Load.T` = 1), `load_speed` out (a `SpeedSensor` at `Wheel2`). Also inverted-pendulum-cart: `x_ref` in, `theta`, `x`, `force` out (closed loop; a plant-only force input is unstable open loop, so it is not gated). Every signal the models had is bit-identical with and without the markers (except the reshaped load step). *Driving the reference.* `simulate(flat; inputs = Dict(id => (t, u)))` (`src/sim/inputs.jl`) holds a parameter at `u[k]` on `[t[k], t[k+1])`, changed at an exact stop *after* a discrete tick at the same instant (a tick at `t_k` samples the value held before, as the FMU's tick at the end of `doStep` does before the host sets the next input), applied like a held discrete value (`setp`, algebraic re-solve, derivative refresh), recorded as a left/right pair. *Gate.* `export_examples.jl` writes a deterministic trajectory per input (splitmix64; hold the start value, a step, a ramp, a linear chirp up to 1/(20 step), a PRBS; the range from `expected.json` `export.inputs`) sampled at the communication instants, drives the reference with it and exports a second, markers-only FMU (`export-markers`). `export_checks.py` runs the FMUs in an explicit FMU2Slave loop (set sample k, read, `doStep(t_k, step)`: fmpy's `simulate_fmu(input=)` records the left limit and interpolates linearly), checks the markers-only modelDescription (exactly the marked inputs and outputs, causality, variability, start, the declared tunables, `ModelStructure/Outputs`, fmpy validation, and the names in `expected.json` `export.interface`), and gates `export.status` and `max_rel_error` (1e-3). Measured (relative to each output's peak): speed-control `speed` 2.9e-6, `current` 1.8e-5 (RK4, 62.5 µs, setpoint in [-39, 125] rad/s, PI saturating); drivetrain `load_speed` 1.7e-8 (Rodas4P, 0.5 ms); cart `theta` 1.6e-4, `x` 1.7e-4, `force` 2.3e-4 (ROS2, 1 ms, force saturating at 20 N); all signals of the `expose_all` FMUs, driven: 1.9e-5, 2.3e-5, 3.2e-4. Controls: the same FMUs with the inputs one sample late miss by 5e-2 to 1.4, undriven by 1. Open: the modelDescription carries no units yet (`expected.json` `interface.units` is checked once it does); the dialog's reference holds a pass-through input at its start value rather than the model's stimulus |
| J-EX11 | Export scope: `Export.scope_document(doc, path; power_inputs, input_values)` turns the subsystem at `path` into the exported model (markers on signal ports, an effort/flow adapter on each scalar power port, everything outside dropped); E112 for a missing scope, a node that is not a subsystem, a power port without a choice, or a vector/multibond port (later) | the subsystem's ports are exactly the interface; a harness with events outside the scope does not reach the export; the adapter's flow is the flow into the subsystem in both bond orientations; hydraulic-servo's `Valve` exports on its own |

### Phase B: stiff systems and DAEs

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX3 | Rosenbrock with mass matrix: ROS2, ROS34PW2 and Rodas4P (D-EX6); symbolic Jacobian with CSE (forward accumulation through the observed equations, a size guard, J-EX4's coloured finite differences as the fallback); the cost model in the analysis | drivetrain-kalman (keeps a linear algebraic equation), hydraulic-servo export; FIX-M2-3's DAE fixture matches |
| J-EX4 | Sparse Jacobian pattern and generated static sparse LU; finite-difference fallback with colouring | `robot-arm-2d` and the 72-state `robot-arm-3d` export; step-time table in the report |

### Phase C: language coverage

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX5 | `bg_intrinsics.c` (`interp1/2` over constant tables; `csv_value` refused with E110), `bg_mech.c` (all `bg_*` mechanics functions); golden tests of every C function against its Julia twin on random inputs | max deviation ≤ 4 ulp, or documented per function |
| J-EX6 | `@events` + `reinit` per step, W203 per site with origin; E104 against `dt` active | bouncing-ball and the hard-stop goldens export, with W203 at the expected sites |
| X-EX2 | Extend `fmu_compare` to the mechanics examples (pendulums, robot arms, reaction wheels) | within the stated tolerances |

### Phase D: targets and real time

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX7 | FMI 3.0 Co-Simulation wrapper and `buildDescription.xml` | passes FMI 3 validation (fmpy) |
| P-EX2 | Cross builds with `zig cc`: x86_64-linux, aarch64-linux, x86_64-windows | the aarch64 binary runs under qemu-user in CI with the same results |
| X-EX3 | Real-time measurement on PREEMPT_RT (ctrlX CORE or a PREEMPT_RT PC): a cyclic 1 kHz task calling `doStep`, latency and step-time histograms over ≥ 1 h | max step time and jitter recorded for dc-motor and robot-arm-3d; no deadline miss at 1 kHz |
| W-EX1 | Export dialog: platforms, `dt`/integrator (auto or manual), error target, tunables, the analysis report, download | Playwright test exports dc-motor and downloads a valid FMU. **In progress (branch `export-fmu-ui`):** done: the dialog from the toolbar (whole model) and a subsystem's context menu (J-EX11 scope preselected), the interface preview with effort/flow per power port and the W209 hint, method and `dt` (auto or manual) with step, damping, Jacobian and linear solver under Advanced, progress and cancel, the report (method, `dt`, substeps, candidate table, build and timings, diagnostics by code), refusals as a message, download; Playwright (`tests/e2e/export.spec.ts`) exports and downloads on the fake worker; the real dc-motor and panda `Robot` exports were driven from the dialog and their FMUs validated with fmpy. **Tunables editor (branch `jex8-tunables`, with J-EX8):** a Tunable parameters section, empty by default (everything folded); pick a block parameter (catalog Real parameters by instance path) or a global, or "Expose all globals (n)" in one click; each row has min/max (catalog range to start with; a range without the model's value blocks the export, an open end is noted as W210); the report lists what the host can set before initialization with ranges and units, what `fmi2ExitInitializationMode` recomputes, and the operations per right-hand side against everything folded (`tests/export-tunables.test.ts`, `tests/export-dialog.test.tsx`, `tests/e2e/export-tunables.spec.ts`). Not yet: platforms (P-EX2), the error target, input start values, and "promote to marker" suggestions |

### Phase E: completeness

| WP | scope | acceptance |
| --- | --- | --- |
| J-EX8 | Initialization in C (D-EX11 phase 2): MTK's initialization system, bounded Newton at `ExitInitializationMode` | changing a parameter before init gives the same start as a Julia run with that parameter. **Done (branch `jex8-tunables`), together with exposing global parameters (plan/GLOBAL_PARAMETERS.md) and the W-EX1 tunables editor.** `ExportSettings.tunables`/`ranges`/`expose_globals` (`src/export/tunables.jl`): a picked block parameter stays a `fixed` FMU parameter with its range; an exposed global is one too, and the block parameters, starts and held values written over it become calculated values (`calculatedParameter` in the XML); the generated `bg_init_values` recomputes them and `bg_init` (runtime 0.5.0, after J-EX9's 0.4.0) runs Newton on a DAE's algebraic block, once, in `fmi2ExitInitializationMode`. `fmi2SetReal` refuses a calculated parameter, a fixed one after initialization, and any value outside its range (`fmi2Error`, logged). Refusals: W215 (not honoured, stays folded), E110 (range without the model's value; an initialization the C cannot reproduce, from a probe per tunable against MTK's). Tests: `test/test_export_tunables.jl` (64: planning, refusals, XML, and in C the lag with `gain` set before init against the analytic answer, the globals fixture with `m = 3` against `sqrt(3) + 0.5 + 12 t` and against the folded export with `m = 3` to 1e-13, a DAE whose algebraic start depends on `c` re-solved to 1e-12 and its trajectory against Rodas5P to 1e-6, the refusals logged, 0 allocations, C++17). Acceptance `examples/export_tunables_check.py` (fmpy, values set before init, all gates passed, fmpy validate clean, 0 allocations, C++ OK): see the table below. |
| J-EX9 | `delay` (constant delay, ring buffer) and `noise_normal` (PRNG specified once, implemented in Julia and C) | bit-identical noise sequence in Julia and C. **Done (branch `jex9-delay-noise`):** counter-based noise (SplitMix64 + AS 241 with an IEEE-only log, spec "Seeded noise and delay") in `library/random.jl` and `bg_intrinsics.c`, plus a `noise_uniform` primitive for other random sources; `Noise` draws it per tick; `delay(x, T)` is a discrete intrinsic with a ring buffer per call (`DiscreteState.ring` in simulation, `m->ring` in C, at most 2^20 slots per model, else E110); new blocks `IntegerDelay` (z⁻ᴺ, exact) and `TransportDelay` (sampled ring plus linear interpolation, error ≤ Ts²/8·max\|u''\|). `test_export_noise_delay.jl`: 43402 draws (7 seeds incl. ±2^62-range, 4 counter ranges) equal bitwise between Julia and the C runtime; an exported model gives 1001/1001 noise and delayed samples bit-identical to simulation, also after `bg_reset`, and its DDE state within 6e-14; it builds with `-std=c99 -Wall -Wextra -Werror` and as C++17. New example `dead-time-noise` passes the X-EX0 gate (compared, worst 2.8e-6, zero allocations, symbol check) |
| J-EX10 | Optional C++ wrapper `bg_model.hpp` on the C API; `BG_STATIC_INSTANCE` MCU build (one static instance, no allocation callback) | the wrapper builds with `-fno-exceptions -fno-rtti`; the static build has no undefined allocation symbol |

J-EX8 acceptance (`uv run examples/export_tunables_check.py`, this machine, MSYS2 gcc): each
case exported with the tunables and folded; the tunable FMU run in fmpy with the changed values
set before initialization against a Julia run with those values (worst error over every
recorded signal, relative to its peak); the globals case also against a folded export of the
model with the changed globals at the same step.

| case | set before init (changed to) | recomputed at init | method, `dt` tunable / folded | (a) vs Julia | (b) vs folded with the globals | out of range | rhs ops tunable / folded | doStep µs tunable / folded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dc-motor speed-control | `Motor1/R` [1, 4] (3), `Motor1/J` [5e-6, 4e-5] (2e-5) | nothing | RK4 31.25 µs / 62.5 µs | 2.5e-6 | | refused | 12 / 10 | 1.61 / 0.64 |
| drivetrain-kalman (DAE) | `IW1/i` [5e-4, 2e-3] (1.5e-3), `R/r` [0.5, 2] (1.5), `IJm/i` [2.5e-5, 1e-4] (7e-5) | the algebraic unknown (Newton) | Rodas4P 125 µs / 125 µs | 7.2e-6 | | refused | 63 / 61 | 8.41 / 8.65 |
| speed-control with globals `Rm`, `Jr` (`Lm = 2.5e-4 Rm` driven) | `Rm` [1, 4] (3), `Jr` [5e-6, 4e-5] (2e-5) | 3 calculated parameters (`Motor1/R`, `L`, `J`) | RK4 62.5 µs / 62.5 µs | 3.3e-5 | 7e-16 | refused | 13 / 10 | 0.72 / 0.61 |

The real-time cost of a tunable is mostly its range, not the parameter read: speed-control's
`R` up to 4 Ω with `L` fixed moves the electrical pole `-R/L` to -8000 1/s, so the proven RK4
step halves (2.5x the step time); with `L` scaling with `R` (the globals case) the pole stays
and the step time grows 18 %. The drivetrain's step time is unchanged within noise. Every FMU:
0 allocations after instantiate, no forbidden symbol, C++17 syntax check, fmpy validate clean;
a value outside the range is refused with `fmi2SetReal: parameter Motor1/R = 5 is outside its
declared range [1, 4]`; a range that leaves out the model's value is E110 at export.

## 8. Validation and gates

- **Accuracy (X-EX0):** every example model is exported and compared with its simulation:
  the FMU in `fmpy` against the variable-step reference, max error per signal relative to its
  peak, the expected outcome and threshold in `expected.json`. A model that cannot be exported
  yet must be refused with the expected code. This is the spec's dashed "target build matches
  simulation" link, applied to the whole example set rather than to a few models.
- **No allocation:** (a) `nm -u` on the hot-path objects contains no `malloc`, `calloc`,
  `realloc`, `free`, stdio or `exit`/`abort`; (b) the counting harness reports 0 memory
  callbacks after instantiate over ≥ 1e5 `doStep` calls; (c) the static MCU build links without
  any allocator.
- **Standard:** `fmpy` validation for FMI 2.0 and 3.0; the generated sources compile as C99
  with `-Wall -Wextra -Werror`, and also as C++17 (a compatibility check for embedding in a
  C++ application, not a target).
- **Semantics:** golden tests of each C runtime function against its Julia twin; the discrete
  goldens (`test/golden/discrete/`) also run through the C partitions and must be **bit-exact**
  (the discrete code is plain arithmetic in the same operation order; the spike's PI matched).
- **Real time (phase D):** step-time and latency histograms on PREEMPT_RT, recorded in
  `plan/STATUS.md` like the existing step-time gates.

## 9. Risks and mitigations

| risk | impact | mitigation |
| --- | --- | --- |
| Expression blow-up of large multibody systems in `observed` and in the symbolic Jacobian | huge `model.c`, long C compile | CSE; observed locals as subexpressions (proven in the spike); finite-difference Jacobian fallback (D-EX12) |
| A runtime value (tunable parameter, input) moves the eigenvalues out of the stable region | divergence after a parameter change in the field | D-EX16: declared ranges scanned at export and enforced by the FMU; W210 when a range is missing |
| Very stiff parasitic modes (joint stiffness 1e7) need tiny RK4 steps | step budget exceeded | the cost model picks Rosenbrock; W207 when RK4 substeps exceed the budget; W213 when the Rosenbrock step damps an undamped stiff mode the model keeps |
| The eigenvalue scan misses states the reference run never visited | instability in the field | safety margin; the report states the scanned range; Rosenbrock (L-stable) as the robust default for models with W201/W202 |
| Frozen conditions delay a switch by up to one step | contact/friction timing differs from simulation | W203 per site; the accuracy loop reduces `dt`; documented semantics (spec) |
| Quaternion norm drift in long runs | pose error | decided in J-EX5 (D-EX17): no renormalization, as in simulation; the pose blocks are norm-invariant and RK4 drift is about 4e-10 per hour at 10 rad/s and 1 ms (section 5.4) |
| MTK version changes the compiled-system API | emitter breaks | the emitter uses only documented accessors (`unknowns`, `equations`, `observed`, `parameters`, `calculate_jacobian`); a golden of the generated C for dc-motor catches changes |
| libm differences across targets | tiny numeric differences | tolerance-based gate (D-EX14); discrete code bit-exact |
| Large interpolation tables on MCUs | flash size | size report in the export (`tables` in export.json); downsampling is the user's choice; CSV data is not exported (an ExportInput instead) |

## 10. Contract and spec changes

- `contracts/schemas/export-request.schema.json` (landed with W-EX1): the model, an optional
  scope with effort/flow per power port and input start values, and `ExportSettings` (method
  and `dt` auto or set, communication step, damping, Jacobian, linear solver, expose-all).
  Later: platforms, FMI version, error target, step budget.
- `contracts/schemas/export-report.schema.json` (landed): `export.json` as written by
  `export_model` (method, `dt`, substeps, spectrum, the candidate table, interface,
  diagnostics, linear algebra, tables) plus `build` from `fmu_build.py` (compiler, source-only
  note, symbol check, C++ check, allocations after instantiate, `doStep` mean/max). Later:
  errors per output (the accuracy loop).
- `contracts/schemas/export-job.schema.json` (landed): the job document of
  `GET /api/exports/{id}` (status, phase, timings, diagnostics, notes, report, FMU).
- `worker-rpc.schema.json`: no `model.export` method. The export runs in its own Julia
  process (5.2), which reports its phase on stdout.
- New diagnostic codes, checked against `src/diagnostics.jl` before use: E110 (construct not
  exportable), E111 (structure not supported by the chosen integrator), W207 (RK4 substeps
  above the step budget), W208 (accuracy target not met at the chosen `dt`), E112 (export
  scope unusable), W211 (the static sparse LU failed its pivot check at export), W212 (the
  symbolic Jacobian exceeded its guard or has a partial without a C form; coloured finite
  differences instead), W213 (N stiff undamped modes at or above F Hz are damped numerically
  by the Rosenbrock method; forcing rk4 resolves them), W214 (no method meets the strict
  step rule within the budget; the suggestion uses the relaxed damping 0.5; forcing rk4
  resolves all modes), W215 (a tunable request that is not honoured, so the value stays folded:
  an unknown id, a driven global, a global that sets a structural constant or a non-scalar
  value, a held value, a parameter written as an expression over globals, a runtime-tunable
  parameter computed from an exposed global; J-EX8). W203 and the `dt` part of E104
  become active.
- J-EX8 (landed): export-request `settings.tunables` (`[{id, min?, max?}]`, `id` a flat
  parameter path or `global:<name>`) and `settings.exposeGlobals`; export-report parameters
  with `causality`, `min`/`max`, `unit`, `description`, `dependsOn`, and a `tunables` section
  (requested, globals, counts of what is recomputed, `newton`, `rhsOps` against
  `rhsOpsFolded`, the initialization probes). `RUNTIME_VERSION` 0.4.0 (`bg_init`,
  `bg_p_name`/`bg_u_name`, `bg_p_tunable` 2 for a calculated parameter).
- Spec: the target-platform paragraph (generated C, FMU, C API; ctrlX runs it without Julia),
  the "Future option: C++ export" paragraph (superseded), the pipeline figure (C/FMU output),
  and the open question on bit-exactness (answered by D-EX14).
- `IMPLEMENTATION_PLAN.md` section 12: export moves from out of scope to this plan.

## 11. Recommended landing path

1. **J-EX1 + P-EX1 + X-EX0 together**: the spike's generator moved into `src/export/` with
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
