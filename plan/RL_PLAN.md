# RL plan: robust learned controllers for the cart and rotary pendulums

Goal: train a small, CPU-friendly, robust neural-network controller with
[rsl_rl](https://github.com/leggedrobotics/rsl_rl) (PPO) on the exported FMUs of the cart and rotary
pendulums (2, 3 and 4 links), with domain randomisation over realistic parameter ranges, and import the
trained policy back into bgsim as an ordinary controller block that simulates (and exports) like any
other firmware.

Status and progress: the tracking table at the end of this file. Update it in the same commit as the work.

## Feasibility (assessment, 2026-11-01)

Feasible: most pieces already exist.

| need | what bgsim has |
| --- | --- |
| plant as an FMU | FMI 2.0 / 3.0 Co-Simulation export with a fixed step (`plan/EXPORT_PLAN.md`), and the plain C API (`bg_reset`, `bg_step`, get/set) without FMI. Plant-only export: `ExportInput` on the actuator command, `ExportOutput` on the sensors, or a subsystem scope (J-EX11). |
| domain randomisation | Exposed globals and picked block parameters become FMU parameters with min/max (J-EX8), set before initialisation, and the start state is recomputed in C. The FMU refuses values outside the range, and the export proves the fixed step stable over the whole range (D-EX16). One randomisation per episode: reset, set, initialise. |
| sensor/actuator non-idealities | Seeded noise and `delay()` intrinsics, bit-identical in simulation and C. For training they are cheaper and more flexible per environment in the Python wrapper. |
| policy back in bgsim | Discrete blocks have `Vec{N}`, `Mat{N,M}`, `A * x`, `tanh`, `exp`, `max`: an MLP is an ordinary `@discrete` block with constant weights. It also exports to C, so a controller FMU with the trained policy comes for free. |
| rsl_rl | PPO via `OnPolicyRunner(env, train_cfg, log_dir, device="cpu")`; the env implements `VecEnv` (`step` returns a TensorDict of observation groups); `obs_groups` gives the critic privileged observations (the true randomised parameters) while the actor sees only sensor data; policies export to TorchScript and ONNX. |

Risks:

1. **Throughput.** rsl_rl expects thousands of parallel environments. One `fmpy` call per environment
   per step costs more in Python overhead than the physics. Remedy: a small C shim that steps N
   instances per call over numpy arrays (the plain C API), one worker process per core. The doStep cost
   of the stiff multibond plants (compliant joints) must be measured first.
2. **Policy import.** No ONNX import is needed: a generator writes the block (observation normalisation
   with the stored mean and std, the layers, the output scale, the clamp). Matrix code unrolls, so keep
   the net small ([32, 32] or [64, 64]) and measure compile time; a non-unrolled matrix product is the
   fallback if needed.
3. **Control rate.** The four-link plants have unstable poles of 24 to 34 /s, so the policy must run at
   200 Hz or more (the classical firmwares run at 1 kHz).
4. **Difficulty grows steeply with the number of links.** Double cart swing-up and balance is
   established for PPO; triple is hard; quad is very hard (tiny catch region); the rotary quad is
   unlikely to give a robust policy (see the quad-pendulum realism assessment). Fallbacks: RL swing-up
   with the existing LQR balance, or an RL residual on top of the TVLQR.

## Approach

### Step 0: spike on the double cart (go/no-go)

`examples/pendulum-double-cart` (DC motor, gearbox, belt, ±0.40 m rail; the action is the motor voltage).

1. Plant-only FMU: motor voltage in; cart position and joint angles out (encoders), optionally rates;
   masses, lengths, friction, motor constants as exposed globals with ranges.
2. Batched C environment over the plain C API; measure steps per second per core and in total.
3. `VecEnv` wrapper and PPO training of swing-up plus balance from hanging rest, without randomisation.
4. Generator: trained weights to a bgsim library block (`@discrete`), observations and action exactly as
   in the training env.
5. Closed loop in bgsim against the training env from the same initial states.

Go/no-go: training wall-clock time on this machine (22 cores), and agreement between the bgsim closed
loop and the training env.

### Step 1: robustness

- Parameter ranges from the quad-pendulum phase B realism work (masses, lengths, centres of mass, viscous
  and Coulomb friction, encoder and cable mass, cable drag), one shared definition with the classical
  designs.
- Per environment in the wrapper: action delay (1 to 2 ms and more), encoder quantisation and noise,
  rates from filtered differences, actuator ripple, random pushes.
- Asymmetric actor-critic: the critic sees the randomised parameters.
- Reward: upright, energy shaping for the swing-up, penalties near the travel limit and on action rate.
- Evaluation: the same robustness table as the classical designs (masses, lengths, friction, delay,
  quantisation, pushes), RL against TVLQR plus LQR.

### Step 2: scale

Triple and quad cart, then rotary double and triple. The rotary quad only if the realism work shows it is
feasible at all. If end-to-end RL stalls, the fallbacks above.

## Progress tracking

| # | item | status | notes |
| --- | --- | --- | --- |
| R0.1 | plant-only FMU of the double cart with exposed parameter ranges | done | `models/pendulum-double-cart-plant` (written by `design/rlmodels.py`): `V`, `F_push` in; `x`, `q1`, `q2` (+ `v`, `w1`, `w2`, `i_m` for the critic) out; 11 globals exposed with ranges (masses, lengths, joint friction, motor R/k_t/J_m/b_m), 17 calculated parameters and 3 starts recomputed at init. `rl/export_plant.jl` + `rl/build_plant.py`. `auto` picks RK4 at 2.5 µs (the 1e8 N/m pivots and rail rotation spring, \|λ\| 1.05e5 /s, 400 substeps/ms); fixed **Rodas4P 1 ms** instead (damps those parasitic modes). fmpy validate clean, 0 allocations, C++17 ok, out-of-range refused; driven 3 s vs Rodas5P 1e-8: mechanics 1.4e-4 of peak (nominal and 6 globals changed before init), motor current 3.4e-2 (electrical pole -3000/s not resolved at 1 ms; critic-only signal). ROS2 0.5 ms: 1e-2, rejected. doStep 5-6 µs (harness) |
| R0.2 | batched C env, steps/s measured | done | `rl/cenv/bgenv.c` (N `bg_model`s, reset + set + `bg_init` + pose override, one `bgenv_step` over numpy via ctypes, OpenMP), `rl/rlpend/cbuild.py`, `rl/bench_env.py`. Shim = fmpy bit for bit (0.0). Env step = 5 × 1 ms (200 Hz). One thread: plant 9.2-10 µs per 1 ms step, ~21k env steps/s at N ≥ 16 (plant 93-100 % of the wall time; N = 1: 6k/s, 63 %). 12 OpenMP threads: 139k (N 1024) / 166k (N 4096); 12 processes × 512: **285k env steps/s**. fmpy fallback: 14k env steps/s per core (70 µs/env step). |
| R0.3 | `VecEnv` wrapper, PPO swing-up + balance (no DR) | todo | |
| R0.4 | policy-to-block generator, compile time measured | todo | |
| R0.5 | bgsim closed loop vs training env | todo | |
| R0.6 | go/no-go report | todo | |
| R1 | domain randomisation, non-idealities, robustness table | todo | needs the quad phase B parameter ranges |
| R2.1 | triple cart | todo | |
| R2.2 | quad cart | todo | |
| R2.3 | rotary double, triple | todo | |
| R2.4 | rotary quad | blocked | only if the realism work says feasible |
