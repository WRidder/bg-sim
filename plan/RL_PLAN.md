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
   unlikely to give a robust policy (see the quad-pendulum realism assessment). Variants in scope, compared
   side by side: (a) pure RL, a single network trained from scratch; (b) RL with an imitation warm start
   (behaviour cloning on the LQR/TVLQR, then PPO), still a single network; (c) the hybrid: an RL swing-up
   that only has to bring the pendulum into the balance LQR's catch region, after which the block switches
   to the existing LQR (expected to be the more robust and verifiable balancer, while a state-feedback RL
   swing-up should beat the timed TVLQR under parameter uncertainty). If no learned variant can do a task,
   the classical LQR/TVLQR design stays the controller for it and the result is recorded. The goal is the
   RL workflow itself: FMU → training → policy block → bgsim. The robustness comparison with the classical
   designs is shared with `plan/ROBUST_CLASSICAL_PLAN.md` (its C5 table, step R1 here).

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
  quantisation, pushes), RL against TVLQR plus LQR: the C5 comparison table of
  `plan/ROBUST_CLASSICAL_PLAN.md`, shared with this step.

### Step 2: scale (deferred)

Deferred until the 2-link workflow proves viable: steps 0 and 1 stay on the double cart (the question is
whether the workflow is viable, not how far RL scales). Step 1's parameter ranges and non-idealities go into
`examples/pendulum-double-cart/design/realism.json` (C0 of `plan/ROBUST_CLASSICAL_PLAN.md`, shared with the
robust classical work), built from the plant FMU's 11 exposed globals and their ranges.

Triple and quad cart, then rotary double and triple. The rotary quad only if the realism work shows it is
feasible at all. Each task compares the variants of risk 4 (pure RL, imitation warm start, hybrid RL swing-up
with the LQR balance); if none works, the classical design stays the controller and the result is recorded.

## Step 0 result: go/no-go (R0.6)

**Verdict: go for the workflow, no-go for "pure RL from scratch" as the default recipe.**
FMU → batched C env → rsl_rl PPO → generated `@discrete` block → bgsim works end to end. It is fast
enough and agrees with the training env to round-off. On this plant (high-gain balance, saturating
at 0.1 rad), useful policies need an imitation warm start from the classical design. Details are in the
table rows R0.1-R0.5.

| question | result |
| --- | --- |
| throughput | Plant FMU (Rodas4P, fixed 1 ms): 5-6 µs per doStep (harness), 9-10 µs per step in the shim. Batched C env (200 Hz policy, 5 substeps): 21k env steps/s per core, 166k with 12 OpenMP threads, **285k with 12 processes**. In PPO training 42-48k env steps/s: the torch side (inference + update, CPU) takes 60 % of the wall time, the plant 35 %. fmpy would give 14k/s per core. |
| training effort | Balance (BC on the LQR, then PPO): **5 min, 13 M steps**; BC alone takes about 1 min. Pure-RL attempts: about 120 M steps in total (6 runs, about 1 h) without a balancing policy. Swing-up variants: see below. |
| final performance (balance, shipped) | 0.95 of rest starts within ±0.3 rad balanced for 6 s (the LQR: 0.91). In bgsim: 0.8° band, cart 3-5 cm off centre (LQR: 0.01°, 1 mm), push 0.28 N → 18.4° peak (LQR 17.8°), recovered. |
| swing-up variants (timeboxed) | @@SWINGUP@@ |
| bgsim vs env | From the same rest poses, over 4 s: x 8e-7 m, th1 3e-6 rad, th2 8e-7 rad, u 2e-3 V (the block computes in float64, the env's actor in float32). |
| compile time | 4865-weight block (66 KiB): cold flatten 2.1 s, compile 2.0 s, first run 31.8 s (Julia JIT); warm 0.16 s / 1.3 s / 2.7 s for a 6 s run. No compiler change needed. |

What worked:
- The plain C API plus a 300-line OpenMP shim. It matches fmpy bit for bit and gives 20× fmpy's throughput.
- Exposed globals with ranges, recomputed in C at init; the reset/parameter-set path is ready for domain
  randomisation.
- The generator and the operation-for-operation observation pipeline (differenced encoder rates, previous
  action) agree between env and bgsim to round-off.
- An env sanity check against the classical controller (the LQR as the actor). It separated "env bug" from
  "learning problem" in minutes and should be the first test of every new env.
- Imitation warm starts: behaviour cloning on the LQR, and on the TVLQR swing-up from the example's own design
  tables (`rl/classical.py`).

What did not:
- PPO from scratch on this plant: the needed gains are 10/rad in action units, and the actor stays 6-80× too
  small.
- PPO fine-tuning without an anchor destroys a cloned swing-up within 20 iterations, and does the same to the
  cloned balance once the swing-up is trained.
- DAgger on the time-indexed TVLQR expert (conflicting labels off the nominal).

What step 1 (domain randomisation) needs:
1. The shared parameter set `design/realism.json` (C0 of `plan/ROBUST_CLASSICAL_PLAN.md`): the plant FMU's
   11 globals and ranges plus the non-idealities.
2. Per-env parameter sampling at reset. `bgenv_reset` already takes parameter indices and values; the env
   passes none yet. The sampled values go to the critic as privileged observations.
3. Non-idealities in the wrapper: action delay (a ring buffer of 1-2 ms and more, which needs a finer
   substep or 1 kHz control), encoder quantisation and noise, filtered rates, actuator ripple, random pushes
   through `F_push`.
4. Resets with velocity: the shim sets only pose integrators (rest starts). Starting with rates needs the
   momenta (mass matrix) or a short pre-roll.
5. The classical controller as the expert, recomputed per parameter set (the LQR/TVLQR robustness of
   `ROBUST_CLASSICAL_PLAN.md`) for the imitation warm start. Then PPO with a BC anchor; the anchor weight
   decays as the randomised performance overtakes the expert.
6. Throughput: the torch update dominates. Larger minibatches or fewer epochs help; a GPU would help most. The
   plant side scales with processes (285k steps/s).
7. The motor current at 1 ms is off by 3e-2 (electrical pole); keep it critic-only, or export at 0.5 ms if
   current feedback is wanted.

## Progress tracking

| # | item | status | notes |
| --- | --- | --- | --- |
| R0.1 | plant-only FMU of the double cart with exposed parameter ranges | done | `models/pendulum-double-cart-plant` (written by `design/rlmodels.py`): `V`, `F_push` in; `x`, `q1`, `q2` (+ `v`, `w1`, `w2`, `i_m` for the critic) out; 11 globals exposed with ranges (masses, lengths, joint friction, motor R/k_t/J_m/b_m), 17 calculated parameters and 3 starts recomputed at init. `rl/export_plant.jl` + `rl/build_plant.py`. `auto` picks RK4 at 2.5 µs (the 1e8 N/m pivots and rail rotation spring, \|λ\| 1.05e5 /s, 400 substeps/ms); fixed **Rodas4P 1 ms** instead (damps those parasitic modes). fmpy validate clean, 0 allocations, C++17 ok, out-of-range refused; driven 3 s vs Rodas5P 1e-8: mechanics 1.4e-4 of peak (nominal and 6 globals changed before init), motor current 3.4e-2 (electrical pole -3000/s not resolved at 1 ms; critic-only signal). ROS2 0.5 ms: 1e-2, rejected. doStep 5-6 µs (harness) |
| R0.2 | batched C env, steps/s measured | done | `rl/cenv/bgenv.c` (N `bg_model`s, reset + set + `bg_init` + pose override, one `bgenv_step` over numpy via ctypes, OpenMP), `rl/rlpend/cbuild.py`, `rl/bench_env.py`. Shim = fmpy bit for bit (0.0). Env step = 5 × 1 ms (200 Hz). One thread: plant 9.2-10 µs per 1 ms step, ~21k env steps/s at N ≥ 16 (plant 93-100 % of the wall time; N = 1: 6k/s, 63 %). 12 OpenMP threads: 139k (N 1024) / 166k (N 4096); 12 processes × 512: **285k env steps/s**. fmpy fallback: 14k env steps/s per core (70 µs/env step). |
| R0.3 | `VecEnv` wrapper, PPO swing-up + balance (no DR) | balance done; swing-up timeboxed (below) | rsl_rl 5.5.2 (`rl/rlpend/env.py`, `rl/train.py`): 4096 envs, 200 Hz, actor obs sin/cos of th1/th2, x, differenced rates, previous action; critic + true rates, current, energy error; actor [64, 64] tanh, critic [128, 128] elu. 42-48k env steps/s in training (per 131k-step iteration: env 0.9-1.1 s, torch inference + PPO update 1.6-1.9 s; `OMP_WAIT_POLICY=PASSIVE`, 8 torch threads best). **Pure RL from scratch failed** (≈ 120 M steps over 6 runs): run 1 discarded (two env bugs found by R0.5's comparison); run 2 (sum-of-cosines reward) "link 1 up, link 2 spinning", std collapsed by 33 M; run 3 (product reward) both links tumbling at 23 M; run 4 (reset curriculum near upright / random / hanging, coordinator's suggestion) pumps energy and tumbles near E_up, 0 % from hanging and from upright at 23 M; balance-only bal1 (init_std 0.3, 10 M) and bal2 (+ drop termination, 6.6 M) never balance. **Env sanity check**: the example's balance LQR as the actor in this env (200 Hz, differenced rates, ±24 V clamp, resets at rest) balances 100 % of starts up to ±0.2 rad, 91 % at ±0.3 rad (same at 1 kHz), and still 100 % with σ = 0.3 Gaussian action noise (7 V per 5 ms): env, conventions, rate estimate, action scale and exploration noise are fine. **Diagnosis**: the learned actor had the LQR's signs but 6-80× too small gains (da/dth2 +0.14 vs +10.7 needed; the LQR saturates at 0.1 rad) and a normaliser fitted to tumbling data; PPO does not grow such high gains from scratch. **Imitation warm start works** (`--bc-lqr 3000`: 262k samples of the noisy LQR, the LQR within 0.6 rad of upright and 0 V elsewhere, normaliser frozen after BC): **balA** (BC + PPO, upright starts ±0.3 rad, init_std 0.1, entropy 0, drop termination 0.8 rad): 0.94 after BC, best **0.95** from upright (64 starts, 6 s, both links within 0.1 rad over the last second; the LQR's own rate is 0.91 at ±0.3 rad), 13.1 M steps in 5.2 min; PPO is fragile on top (one eval at 0.00, iteration 90). Run 5 (BC + curriculum toward hanging) and run 6 (+ 20-iteration critic warm-up) both lost the balance within 40-60 iterations once PPO moved the actor for the swing-up. Second opinion (Fable subagent): hand-scaled observations instead of the empirical normaliser, entropy 0, small init_std, 50 Hz policy. Hybrid probe (train7, angle catch 0.3 rad, LQR in the training loop): 16 % swing-up success from hanging at 23.6 M steps when stopped |
| R0.4 | policy-to-block generator, compile time measured | done | `rl/make_policy_block.py`: actor weights + rsl_rl normaliser mean/std (+1e-2) + action scale/clamp → `library/DoubleCartPolicy.jl` (`@discrete Ts = 0.005`, the env's observation pipeline operation for operation, `Mat * Vec`, `tanh` loops, `clamp`); numpy twin vs torch actor 9e-7; 66 KiB, 4865 weights; hybrid variant adds the latched catch z'Pz < catch_tol and the LQR (`rl/classical.py` → `rl/classical.json`). `pendulum-double-cart-rl` (`design/rlmodels.py --rl balance`): start at rest at 0.1/-0.05 rad, push 0.28 N at 3 s, 6 s. bgsim (`rl/closed_loop.jl`, Rodas5P 1e-8): **cold** flatten 2.1 s, compile 2.0 s, first run 31.8 s (Julia JIT of the generated code); **warm** flatten 0.16 s, compile 1.3 s, run 2.7 s for 6 s (other models 0.2-0.3 s compile, 1.4-2.0 s run for 4 s). Fine; the cold first run is the only slow part |
| R0.5 | bgsim closed loop vs training env | done | `rl/compare.py --task balance` (balA/model_best.pt): 4 rest starts within 0.25 rad, 4 s each, bgsim (plant + generated block) vs the batched FMU env: max deviation **x 8e-7 m, th1 3e-6 rad, th2 8e-7 rad, u 2e-3 V** over the whole 4 s. Default model in bgsim: upright inside 2° from 0.7 s, band before the push 0.81°/0.73° with the cart 47 mm off centre (the LQR firmware: 0.01°, 1 mm), push peak 18.4°/6.4° (LQR 17.8°/6.0°), back inside 1.4° by 5 s, peak 22.5 V, peak cart 0.217 m. `expected.json` entry `pendulum-double-cart-rl` (13 checks) passes with `run_checks.py --only pendulum-double-cart` (78 passed; the 1 failure is the docs KaTeX check of the existing model: `katex` not installed in this worktree's web/node_modules). Plot: `runs/cmpA/compare.png` (not committed) |
| R0.6 | go/no-go report | todo | |
| R1 | domain randomisation, non-idealities, robustness table | todo | double cart only; ranges in `design/realism.json` (C0 of `plan/ROBUST_CLASSICAL_PLAN.md`, from the plant FMU's 11 globals + non-idealities); robustness table = its C5 |
| R2.1 | triple cart | deferred | until the 2-link workflow proves viable |
| R2.2 | quad cart | deferred | until the 2-link workflow proves viable |
| R2.3 | rotary double, triple | deferred | until the 2-link workflow proves viable |
| R2.4 | rotary quad | deferred | until the 2-link workflow proves viable; only if the realism work says feasible |
