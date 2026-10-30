# FMU export spike (C99, FMI 2.0 Co-Simulation)

Throwaway prototype that answers one question: can a bg-sim model be exported as plain C that
is fit for hard real time (no allocation in the hot path, fixed cost per step), wrapped as an
FMU? The answer is yes. The plan built on it is `plan/EXPORT_PLAN.md`.

Date: 2026-10-30. Models: `examples/dc-motor` `iconic` (continuous only) and `speed-control`
(continuous plant, 1 ms discrete PI with anti-windup and clamp).

## Files

| file | role |
| --- | --- |
| `gen.jl` | Julia generator: flatten, `lower_model` (`mtkcompile`), then emits `model.h`/`model.c`, `modelDescription.xml`, `meta.json` and a Julia reference run (Tsit5, 1e-10/1e-12) |
| `bg_runtime.h` | language semantics in C (`sign`, `round`, `clamp`, `deadzone`, `min`/`max`, `mod`), mirroring `lower_nonsmooth` and `DiscreteRuntime` |
| `bg_solver.c` | fixed-step core: RK4 or ROS2 (2-stage L-stable Rosenbrock with an in-place LU), frozen switching conditions, the discrete tick in `run_tick!` order |
| `fmi2_cs.c` | FMI 2.0 Co-Simulation wrapper; one `allocateMemory` call in `fmi2Instantiate`, nothing else |
| `alloc_check.c` | harness: counts memory callbacks after instantiate (must be 0) and times `fmi2DoStep` |
| `build.py` | compiles (MSYS2 gcc, `-std=c99 -Wall -Wextra -Werror`), checks the undefined symbols of the hot-path objects, compiles the sources as C++17, runs the harness, zips the FMU |
| `check.py` | `fmpy` validation, then the FMU against the Julia reference on every output |
| `fmi2/` | the official FMI 2.0.4 headers (BSD-2, `LICENSE.txt`) |

## Run

```sh
julia --project=julia/BGSim spike/fmu/gen.jl examples/dc-motor speed-control spike/fmu/out/sc 1e-4 0.3 RK4 1e-3
uv run spike/fmu/build.py spike/fmu/out/sc
uv run --with fmpy spike/fmu/check.py spike/fmu/out/sc WmSens/y PID1/y Motor1/i
```

Arguments of `gen.jl`: project, model, output dir, internal `dt`, `t_end`, `RK4|ROS2`, output
interval (the `doStep` size in the check).

## Results

Every build: `fmpy` validation OK; the hot-path objects (`model.o`, `bg_solver.o`,
`fmi2_cs.o`) import only `llround` and `strcmp` from libc; 1 allocation (instantiate), **0
after it** over 100 000 `doStep` calls; the sources compile as C++17.

Max error against the Julia reference, relative to the signal's peak, on a 1 ms output grid
(mean `doStep` time for 1 ms, Windows 11 desktop, not a real-time OS):

| model | integrator, dt | `Motor1/i` | speed | worst of all signals | doStep |
| --- | --- | --- | --- | --- | --- |
| speed-control | RK4, 1 ms | diverges at t = 0.488 s | | | |
| speed-control | RK4, 0.5 ms | 9.1e-2 | 1.3e-2 | 4.0e-1 | 0.17 µs |
| speed-control | **RK4, 0.1 ms** | **2.4e-5** | **3.5e-6** | 1.1e-4 | 0.52 µs |
| speed-control | ROS2, 1 ms | 1.8e-1 | 2.6e-2 | 7.8e-1 | 0.16 µs |
| speed-control | ROS2, 0.1 ms | 9.2e-3 | 1.2e-3 | 4.4e-2 | 0.87 µs |
| iconic | RK4, 0.1 ms, live conditions | 7.3e-2 | 1.9e-3 | 2.5e-1 | 0.51 µs |
| iconic | **RK4, 0.1 ms, frozen conditions** | **2.4e-5** | **7.2e-7** | 7.5e-5 | 0.48 µs |

Steady state of `iconic` at 1 s: ω = 239.80815347721716 rad/s (analytic 239.80815347721824),
i = 0.004796163069571342 A (analytic 0.004796163069544365).

## Findings

1. **The pipeline already has what codegen needs.** After `mtkcompile`, `unknowns`,
   `equations` (D(x) ~ f in terms of observed variables), `observed` (topologically ordered),
   `parameters` and `calculate_jacobian` are all the data the C emitter needs. The observed
   equations double as common subexpressions. The discrete partitions reuse `step_expression`
   unchanged; its index-based Julia `Expr` maps to C one-to-one.
2. **Stiffness decides the step, and it can be computed.** The dc-motor's electrical pole
   (|λ| = 3871 1/s, L/R = 0.25 ms) makes RK4 unstable above 0.72 ms. `gen.jl` evaluates the
   Jacobian's eigenvalues along the reference trajectory and finds the largest stable RK4 step
   by bisection on |R(hλ)| ≤ 1. The prediction held: 1 ms diverged, 0.5 ms was stable.
3. **Stable is not accurate.** RK4 at 0.5 ms was stable but 9 % off. Substep selection needs an
   accuracy test against the reference as well, not just the stability bound.
4. **RK4 versus Rosenbrock depends on whether the fast mode matters.** Here the current is a
   real signal, so resolving it with RK4 at 0.1 ms was both more accurate and cheaper than ROS2.
   ROS2 at 1 ms is stable but smears the 0.25 ms transient. Rosenbrock pays off when the fast
   modes are parasitic (stiff joints standing in for rigid ones) and for DAEs.
5. **Switching conditions must be frozen during a step.** Evaluating `ifelse(t >= t_step)` live
   in every RK stage leaks the step into the previous interval (0.4 A = V/L·h/6 error).
   Evaluating each condition once at the start of the step and holding it fixes this exactly
   (7.3e-2 → 2.4e-5).
6. **The cost is tiny and fixed**: below 1 µs per 1 ms tick for this 3-state model, with the
   same work every call.

## Not covered by the spike

DAEs (mass matrix), algebraic loops, registered intrinsics (`interp1`/`interp2`, CSV tables,
mechanics functions), `@events` with `reinit`, inputs, initialization in C, parameter folding,
FMI 3.0, cross-compilation, and a real-time OS measurement. Start values are baked at
generation time, so changing a parameter that affects initialization does not re-initialize.
