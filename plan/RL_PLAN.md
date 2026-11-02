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

**Rig change (2026-11-02).** Steps 0.1-0.5 (the workflow) ran on the double cart above. Step 0's swing-up
variants and steps R1 and later run on the lab rig `examples/pendulum-double-cart-lab`: links of 0.35 m and
about 0.25/0.20 kg, a ±1.0 m rail, and the same motor, gearbox and belt. It is built by a separate branch,
with a classical redesign and `design/realism.json` (C0 of `plan/ROBUST_CLASSICAL_PLAN.md`). Its plant-only
FMU comes from the same generator (`design/rlmodels.py` pattern, `rl/export_plant.jl`), with the exposed
globals and ranges taken from `realism.json`. The ±1.0 m rail should remove the rail-end terminations that
ended almost every swing-up episode on the ±0.40 m rail. Done in R0.7; the result is the final R0.6 below.

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

Deferred until the 2-link workflow proves viable: steps 0 and 1 stay on two links (the question is
whether the workflow is viable, not how far RL scales), on the lab rig from step 0's swing-up on. Step 1's
parameter ranges and non-idealities come from `examples/pendulum-double-cart-lab/design/realism.json` (C0 of
`plan/ROBUST_CLASSICAL_PLAN.md`, shared with the robust classical work).

Triple and quad cart, then rotary double and triple. The rotary quad only if the realism work shows it is
feasible at all. Each task compares the variants of risk 4 (pure RL, imitation warm start, hybrid RL swing-up
with the LQR balance); if none works, the classical design stays the controller and the result is recorded.

## Step 0 result: go/no-go (R0.6)

**Verdict: go.** The workflow FMU → batched C env → rsl_rl PPO → generated `@discrete` block → bgsim works
end to end on both rigs, and with the lab rig's realism parameters as the FMU's exposed globals. It is
fast enough, agrees with the training env to round-off, and gives single-network controllers that bgsim
runs like any firmware. **The recommended recipe is the imitation warm start** (behaviour cloning on the
rig's own TVLQR swing-up and LQR, then PPO with a cloning anchor). On the lab rig it gives a controller as
good as the classical firmware in about 4 minutes. Pure RL and the hybrid now learn on the lab rig, which
they did not on the ±0.40 m rail, but within the timebox they reach only 16 % and 53 % of the noisy hanging
starts and leave the rail more often. Step 1 (robustness) goes ahead on the lab rig, from the imitation
warm start; pure RL stays a comparison row.

### Lab rig (`examples/pendulum-double-cart-lab`, R0.7)

| question | result |
| --- | --- |
| plant FMU | `pendulum-double-cart-lab-plant`: the 27 bond-graph parameters of `realism.json` with min < max exposed with their realism ranges; the lumped link mass, centre of mass and inertia as driven globals. Fixed Rodas4P 1 ms (with the belt, k 2-6e5 N/m), 5.5 µs per doStep, fmpy clean, 0 allocations; 1.5e-4 of the peak against Rodas5P, also with 9 globals changed before initialisation. |
| env sanity check | The rig's classical controllers as the actor at 200 Hz: the TVLQR swing-up 100 % from hanging, also with ±0.15 rad / ±0.05 m start noise and σ = 0.1 action noise (peak 0.44 m, 23 V); the LQR from rest 1.00 / 0.95 / 0.71 at ±0.1 / 0.2 / 0.3 rad. |
| swing-up variants (timeboxed) | See the table below. About 1 h 55 min of training (two runs in parallel, 6 OpenMP + 4 torch threads each; 1.7-1.8 M env steps/min per run), ≤ 47 M steps per run. |
| final performance (swing-up, shipped) | `pendulum-double-cart-lab-rl` (imiL): upright inside 2° 2.7 s after the start (the TVLQR catches at 3.0 s), 0.2° and 3 mm before the push (classical 0.002°), 0.45 N push → 10.9° / 3.7° (classical 10.7°), 15.2 V and 0.388 m peak (classical 15.0 V, 0.387 m). In the env: 0.97 of noisy hanging starts, all 3 hanging test poses, 3 of 4 upright test poses (the fourth, -0.25 rad on link 2, also fails often with the LQR alone). |
| bgsim vs env | 3 hanging and 2 upright rest poses, 4-6 s: 2e-6 m, 2e-6 rad, 4e-4 V through the whole swing-up (the cloned swing-up is smooth, so round-off does not grow). |
| compile time | The same block size (4865 weights, 66 KiB): cold flatten 2.4 s, compile 2.3 s, first run 40.8 s (Julia JIT); warm 0.18 s / 1.3 s / 5.1 s for the 12.5 s run. |

Swing-up variants on the lab rig (success = both links within 0.1 rad over the last second of a 6 s episode,
64 noisy hanging starts, ±0.95 m episode end; "test poses" = the 3 hanging and 4 upright rest poses of
`rl/compare.py`):

| variant | run | steps, time | from noisy hanging | test poses | notes |
| --- | --- | --- | --- | --- | --- |
| classical TVLQR + LQR (reference) | | | 1.00 | 3/3 hanging | 15 V, 0.39 m |
| (b) imitation warm start | imiL: BC on the TVLQR + LQR (2.3 M samples, 1 min), 20-iteration critic warm-up, PPO with a BC anchor (20 steps/iteration, KL 0.005) | 7.9 M, 4 min (stopped at 0.95 twice) | BC alone 0.98; 0.97 / 0.95 | 3/3 hanging, 3/4 upright | shipped; 15 V, 0.39-0.47 m |
| (a) pure RL | pureL: fixed observation scale, init_std 0.3, entropy 0.002, reset curriculum | 47 M, 28 min | best 0.16 (34 M), then 0.00-0.12 | 2/3 hanging, 4/4 upright | 24 V bang-bang, 0.6-0.7 m |
| (a) pure RL | pureL2: as pureL, entropy 0, KL 0.005 | 47 M, 28 min | 0.00 throughout | not evaluated | the action std collapsed (0.28 → 0.02) before any swing-up; never balanced from upright either |
| (c) hybrid | hybL: RL swing-up, the LQR takes over at z'Pz < 2e4 (catch_calib: smallest failing rest start 3.3e4), dense reward, init_std 0.5, entropy 0.005 | 47 M, 26 min | best 0.53 (45 M), rising | 2/3 hanging, 3/4 upright | 24 V, 0.78-0.86 m; the action std grew to 0.8 before it fell |
| (c) hybrid | hybL2: as hybL, init_std 0.3, entropy 0, KL 0.005 | 47 M, 29 min | best 0.44 (45 M), last 0.08 | 2/3 hanging, 1/4 upright | 24 V, 0.68-0.89 m; slower and less stable than hybL |

### Double cart (`examples/pendulum-double-cart`, R0.1-R0.5, first rig)

| question | result |
| --- | --- |
| throughput | Plant FMU (Rodas4P, fixed 1 ms): 5-6 µs per doStep (harness), 9-10 µs per step in the shim. Batched C env (200 Hz policy, 5 substeps): 21k env steps/s per core, 166k with 12 OpenMP threads, **285k with 12 processes**. In PPO training 42-48k env steps/s: the torch side (inference + update, CPU) takes 60 % of the wall time, the plant 35 %. fmpy would give 14k/s per core. |
| training effort | Balance (BC on the LQR, then PPO): **5 min, 13 M steps**; BC alone takes about 1 min. Pure-RL attempts: about 120 M steps in total (6 runs, about 1 h) without a balancing policy. Swing-up variants: see below. |
| final performance (balance, shipped) | 0.95 of rest starts within ±0.3 rad balanced for 6 s (the LQR: 0.91). In bgsim: 0.8° band, cart 3-5 cm off centre (LQR: 0.01°, 1 mm), push 0.28 N → 18.4° peak (LQR 17.8°), recovered. |
| swing-up variants (timeboxed, ±0.40 m rail) | About 1.5 h of training, each run ≤ 50 M steps. **(a) pure RL**: swing-up from scratch 0 % (runs 2-4, about 23 M steps each). Balance from scratch works only with the second opinion's fixes (pure1: fixed hand-scaled observations, entropy 0, init_std 0.1, no energy or action-rate cost, start range widened from ±0.05 rad): the first balancing policy appears at 19.7 M steps (0.91 at ±0.05 rad), then 0.98 at ±0.15 (24.9 M) and 0.91 at ±0.20 (26 M); it stalls at 0.50-0.61 at ±0.25 (pure2, resumed, stopped at 35 M). balA reaches 0.95 at ±0.3 in 13 M. **(b) imitation warm start** (BC on the TVLQR swing-up + the LQR, then PPO): BC alone gives 48 % from noisy hanging starts (the TVLQR itself: 100 %) and 0.94 from upright. PPO without an anchor drops to 0 % within 20 iterations (imi1). With a BC anchor (imi2: 20 BC steps per PPO iteration, KL 0.005, 20-iteration critic warm-up) it reaches 0.23-0.66 from noisy hanging over 39 M steps (17 min; best 0.66 at 37 M) and 0.97 from upright throughout. From the exact bgsim hanging cases: 2 of 3 (rest; ±0.1 rad); the third (x -0.1 m, -0.15/+0.05 rad) leaves the rail. This single network is the `pendulum-double-cart-rl-swingup` model: upright inside 2° 2.3 s after it starts, 0.08°/0.10° and 5 mm before the push, push 17.2°/6.3°, recovered, peak 19.6 V, cart 0.317 m. bgsim vs env: ≤ 6e-6 rad before the swing, 1e-3 rad through it (tumbling amplifies round-off), equal outcomes. **(c) hybrid** (RL swing-up into the LQR's catch region, then the LQR): train7 (angle catch 0.3 rad) 16 % at 23.6 M; with the z'Pz catch, hyb1 (sparse, < 1e4) 0 %, hyb2 (dense, < 1e4) 0-2 %, hyb3 (dense, < 2.5e4) 2-12 %, each at 26 M. **Common failure**: the rail end. The eval's max\|x\| is 0.400 m in almost every run: episodes end at the ±0.40 m rail, and the swing needs about 0.3 m of it. This motivates the lab rig (±1.0 m). |
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
  tables (`rl/classical.py`). On the lab rig cloning alone gives 0.98 (the double cart: 0.48): its classical
  swing-up was planned with margins (16.8 V of 24 V, 0.8 m of the 1.0 m rail), so the clone's small errors
  stay inside the TVLQR's region of attraction; the double cart's TVLQR used the rail to its end.
- The long rail. With ±1.0 m, pure RL (best 0.16) and the hybrid (best 0.53) learn a swing-up within 47 M
  steps; on the ±0.40 m rail both stayed at 0-16 %.
- Exposing the realism parameters directly: the FMU's globals are the names of `realism.json`, so step 1
  samples `lablib.sample` values straight into `bgenv_reset`.

What did not:
- PPO from scratch on this plant: the needed gains are 10/rad in action units, and the actor stays 6-80× too
  small.
- PPO fine-tuning without an anchor destroys a cloned swing-up within 20 iterations, and does the same to the
  cloned balance once the swing-up is trained.
- DAgger on the time-indexed TVLQR expert (conflicting labels off the nominal).
- PPO from scratch is unstable even when it learns: pureL reached 0.16 at 34 M steps and fell back to
  0.00-0.12, losing the balance from upright as well (0.94 → 0.00 → 0.59). Its policy is bang-bang (24 V)
  and uses 0.6-0.9 m of the rail, where the clone uses 15 V and 0.4 m.

What step 1 (domain randomisation) needs:
1. The shared parameter set `examples/pendulum-double-cart-lab/design/realism.json` (C0 of
   `plan/ROBUST_CLASSICAL_PLAN.md`) is in place, and the lab plant FMU exposes its 27 bond-graph parameters.
   The effects outside the bond graph (joint and cart Coulomb friction, cable springs, commutation ripple,
   cogging) need a force path: a cart force input (`F_cart`) and joint torque inputs on the plant FMU, driven
   by the wrapper, or bond-graph elements. The smooth Coulomb laws (eps 0.005 m/s, 0.01 rad/s) are stiff at a
   fixed 1 ms step, so an input driven per 1 ms substep from the sampled rates is the cheaper option.
2. **An estimator.** The lab realism screen (`design/screen_results.json`) found that the classical
   firmware needs an EKF with the 14-bit joint encoders: filtered differences are marginal (9 V rms
   chatter, 12 of 48 Monte Carlo draws limit-cycle at 2-4°). The policy's differenced rates have the same
   problem. Either give the actor an observation history (the last k encoder samples and actions, so it can
   filter) or feed it the EKF's state estimate, and generate that EKF into the bgsim block next to the
   network (or as its own `@discrete` block).
3. Per-env parameter sampling at reset. `bgenv_reset` already takes parameter indices and values; the env
   passes none yet. The sampled values go to the critic as privileged observations.
4. Non-idealities in the wrapper: action delay (a ring buffer of 1-2 ms and more, which needs a finer
   substep or 1 kHz control), encoder quantisation and noise, filtered rates, actuator ripple, random pushes
   through `F_push`.
5. Resets with velocity: the shim sets only pose integrators (rest starts). Starting with rates needs the
   momenta (mass matrix) or a short pre-roll.
6. The classical controller as the expert, recomputed per parameter set (the LQR/TVLQR robustness of
   `ROBUST_CLASSICAL_PLAN.md`) for the imitation warm start. Then PPO with a BC anchor; the anchor weight
   decays as the randomised performance overtakes the expert.
7. Throughput: the torch update dominates. Larger minibatches or fewer epochs help; a GPU would help most. The
   plant side scales with processes (285k steps/s).
8. The motor current at 1 ms is off by 3e-2 (electrical pole); keep it critic-only, or export at 0.5 ms if
   current feedback is wanted.

## Step 1 result: robustness (R1)

**Verdict: the workflow holds up under the full realism model, but in this round the learned controller is an
imitation of the classical design, not an improvement on it.** The imitation warm start passes every
Monte Carlo draw of the shared test (64/64 swing-up, 64/64 balance + push). It does so with about 5 V rms of
voltage chatter, where the EKF firmware needs 1.4 V rms and the multi-model LQR 0.8 V rms. PPO on top did
not change the policy measurably, also with an extra action-rate penalty. Within 1 h timeboxes pure RL and
the hybrid stay comparison rows. bgsim runs the robust policy like any firmware and agrees with the training
env.

Setup (`rl/train_robust.py`, `rl/rlpend/renv.py`):
- **Physics in the FMU**: the plant FMU `pendulum-double-cart-lab-plant` has the realism forces of the project
  block `LabRealism`: Coulomb friction of the carriage, the motor and the joints, cable springs, commutation
  ripple, cogging. 35 globals are exposed, so the FMU and bgsim share all of the physics. FMU vs Rodas5P
  reference 1.6e-4; FMU env vs the harness twin 5.8e-4 m / 0.083°.
- **Per episode**: a full `realism.json` draw is set before initialisation, plus the 1-2 ms loop delay
  (`bgenv_step_delay`), 14-bit joint encoders with the draw's noise, the cart encoder and random tip pushes.
- **Actor and critic**: the actor sees only the encoder history at 200 Hz: sin/cos of the measured angles,
  x, 4 position differences of all three coordinates and 4 previous actions (21 inputs, [64, 64] tanh). The
  critic sees the true state, the motor current, the energy error and the draw's parameters.
- **Expert**: the rig's TVLQR swing-up and LQR with the firmware's Coulomb compensation. It labels from a
  5-sample least-squares fit of the same encoder history (`--teacher-est 5`). Labelling with the true-state
  action gave a student that balanced in a 3° limit cycle. Regressing the true-state action on noisy rates
  shrinks the rate gains (errors in variables). A label that is a function of the observation removes that.
- **Model selection**: validation draws with seeds from 5000 run the test's two scored scenarios in the env.
  The shared test's seeds 3000-3063 are used only for scoring.

Robustness table (shared harness `design/robustness.py`, truth twin, 64 Monte Carlo draws; pass = |x| < 0.95 m
and both links within 2° (5.7°) over the last 2 s; tail angle, tail V rms and peak V are medians over the
passing draws, peak V max and peak x max over the passing draws; training on 22 shared cores, about 10 threads
per run):

| controller | training | scenario | 2° | 5.7° | tail angle | tail V rms | peak V (med / max) | peak x |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nominal-ekf (design.json firmware, EKF) | | swing-up | 64/64 | 64/64 | 0.26° | 1.40 V | 16.7 / 18.1 V | 0.41 m |
| | | balance + push | 64/64 | 64/64 | 0.28° | 1.44 V | 16.2 / 21.3 V | 0.19 m |
| nominal-diff (filtered differences) | | swing-up | 39/64 | 64/64 | 0.57° | 10.5 V | 24.0 / 24.0 V | 0.41 m |
| | | balance + push | 39/64 | 63/64 | 0.57° | 10.4 V | 24.0 / 24.0 V | 0.20 m |
| c1-mm_lqr (robust classical balance, `ROBUST_CLASSICAL_PLAN.md`) | | swing-up | 64/64 | 64/64 | 0.40° | 0.77 V | 16.7 / 18.1 V | 0.41 m |
| | | balance + push | 64/64 | 64/64 | 0.45° | 0.78 V | 12.2 / 16.1 V | 0.23 m |
| **rl-imitation-dr** (imiR2: BC + 2 DAgger, PPO with BC anchor) | 4.3 M labelled samples (17.2 M env steps) in 25 min, then 40.6 M PPO steps; 75.7 min | swing-up | 64/64 | 64/64 | 0.77° | 5.19 V | 22.9 / 24.0 V | 0.44 m |
| | | balance + push | 64/64 | 64/64 | 0.83° | 5.32 V | 23.1 / 24.0 V | 0.18 m |
| rl-bc-dr (imiR2 before PPO) | 4.3 M samples, 25 min | swing-up | 64/64 | 64/64 | 0.80° | 5.24 V | 23.6 / 24.0 V | 0.43 m |
| | | balance + push | 64/64 | 64/64 | 0.83° | 5.36 V | 22.8 / 24.0 V | 0.18 m |
| rl-pure-dr (pureR1: PPO from scratch, fixed observation scale, init_std 0.3, entropy 0.002) | 59.0 M steps, 61 min | swing-up | 0/64 | 0/64 | | | | |
| | | balance + push | 8/64 | 24/64 | 1.82° | 2.15 V | 10.2 / 11.3 V | 0.57 m |
| rl-hybrid-dr (hybR1: RL swing-up, LQR on the 5-sample fit at z'Pz < 2e4; init_std 0.5, entropy 0.005) | 66.8 M steps, 60 min (still rising: validation 0.25 at the end) | swing-up | 15/64 | 15/64 | 0.78° | 4.08 V | 24.0 / 24.0 V | 0.80 m |
| | | balance + push | 64/64 | 64/64 | 0.88° | 5.59 V | 24.0 / 24.0 V | 0.19 m |

Findings:
- **The chatter comes from the expert's labels, not from the learning.** In the env, the expert on the true
  state gives 0.5 V rms and an 18 V peak. As it labels, on the 5-sample fit, it gives 5.3 V rms and 24 V, the
  same as the student (5.2-5.3 V). The 24 V peaks are noise spikes all through the balance, not only at the
  catch. A different window does not help: 3 samples give 10 V rms; 8 samples give 3.9 V rms in balance but
  a 1.0° tail and 54/64, and the swing-up fails 0/64 because the fit's lag is too large for the TVLQR. The
  EKF wins on both counts because it uses the model. The next step for a smooth learned controller is
  therefore an observer, not more PPO. Either the block gets the firmware's EKF and the network acts on its
  estimate, with the expert labelling on the same estimate, or the actor gets a longer history or a recurrent
  layer and the expert labels on the EKF.
- **PPO did not improve on imitation.** In imiR2, 310 iterations (40.6 M steps) left the validation at 64/64
  and 64/64 with a tail of about 0.78° throughout, and the harness numbers before and after PPO are equal.
  smoR1 continued from imiR2 with a 200-fold action-rate penalty (w_rate 10) and a weaker cloning anchor
  (5 steps per iteration): 21 M steps in 30 min, tail V rms unchanged (5.0-5.4 V), 63/64 swing-up on the
  harness (one draw at 2.04°), so it is not a row. The action std was 0.01-0.05 (24 V scale) and model
  selection counted only passes. PPO would need a larger exploration and a selection that sees the voltage
  to move a policy that is already at the pass ceiling.
- **Pure RL and the hybrid** behave as in R0.7, now with randomisation. Pure RL never swings up and only
  balances some draws. The hybrid reaches 15/64 swing-ups in 1 h and is still improving. Its balance row is
  the LQR on the fit (64/64, 5.6 V rms).
- **knockdown_recover** (unscored) was not trained. The BC probe of the same recipe (bcq, 1 DAgger round), like the timed firmware, left the
  rail after the knock-down in every draw (0/64). The env has no expert for a re-swing from an arbitrary state, and PPO
  did not move the cloned policy in about 80 min (imiR2 and smoR1), so a 1 h PPO-only attempt was not started. The state-driven
  classical recovery (C3) is the reference for this case.
- **bgsim** (`pendulum-double-cart-lab-rl-robust`, `library/DoubleCartLabRobustPolicy.jl`, 5633 weights; the block
  quantises the encoders, delays its output and repeats the observation pipeline; the plant at the nominal
  draw with seeded encoder noise): numpy twin vs torch actor 6.6e-7. `rl/compare.py --task robust` (2 hanging
  and 2 upright cases on the nominal draw and two test draws, quantised encoders without noise): bgsim and the
  env agree to 1e-7 until a trajectory reaches an encoder count edge at a different time. After that they
  differ by 2-3 mm, 3-4 mrad and up to 4.7 V of chatter, with the same outcomes (tail 0.22° / 0.16°,
  0.31° / 0.24°, 1.2° / 1.2°, 1.1° / 1.1°). Default model: upright inside 2° at 3.97 s, 1.4° / 1.1° before
  the push (encoder reading), 10.8° / 4.2° after it, 0.377 m, 24 V. Warm flatten 0.3 s, compile 1.7 s,
  run 19 s for 12.5 s (cold first run 75 s). `expected.json` entry (16 checks) passes;
  `run_checks.py --only pendulum-double-cart-lab`: 163 passed, 1 failed (the docs KaTeX check: `katex` is
  not installed in this worktree).

## Progress tracking

| # | item | status | notes |
| --- | --- | --- | --- |
| R0.1 | plant-only FMU of the double cart with exposed parameter ranges | done | `models/pendulum-double-cart-plant` (written by `design/rlmodels.py`): `V`, `F_push` in; `x`, `q1`, `q2` (+ `v`, `w1`, `w2`, `i_m` for the critic) out; 11 globals exposed with ranges (masses, lengths, joint friction, motor R/k_t/J_m/b_m), 17 calculated parameters and 3 starts recomputed at init. `rl/export_plant.jl` + `rl/build_plant.py`. `auto` picks RK4 at 2.5 µs (the 1e8 N/m pivots and rail rotation spring, \|λ\| 1.05e5 /s, 400 substeps/ms); fixed **Rodas4P 1 ms** instead (damps those parasitic modes). fmpy validate clean, 0 allocations, C++17 ok, out-of-range refused; driven 3 s vs Rodas5P 1e-8: mechanics 1.4e-4 of peak (nominal and 6 globals changed before init), motor current 3.4e-2 (electrical pole -3000/s not resolved at 1 ms; critic-only signal). ROS2 0.5 ms: 1e-2, rejected. doStep 5-6 µs (harness) |
| R0.2 | batched C env, steps/s measured | done | `rl/cenv/bgenv.c` (N `bg_model`s, reset + set + `bg_init` + pose override, one `bgenv_step` over numpy via ctypes, OpenMP), `rl/rlpend/cbuild.py`, `rl/bench_env.py`. Shim = fmpy bit for bit (0.0). Env step = 5 × 1 ms (200 Hz). One thread: plant 9.2-10 µs per 1 ms step, ~21k env steps/s at N ≥ 16 (plant 93-100 % of the wall time; N = 1: 6k/s, 63 %). 12 OpenMP threads: 139k (N 1024) / 166k (N 4096); 12 processes × 512: **285k env steps/s**. fmpy fallback: 14k env steps/s per core (70 µs/env step). |
| R0.3 | `VecEnv` wrapper, PPO swing-up + balance (no DR) | done on the double cart (balance; swing-up with an imitation warm start, 2 of 3 cases); the swing-up variants move to the lab rig (R0.7) | rsl_rl 5.5.2 (`rl/rlpend/env.py`, `rl/train.py`): 4096 envs, 200 Hz, actor obs sin/cos of th1/th2, x, differenced rates, previous action; critic + true rates, current, energy error; actor [64, 64] tanh, critic [128, 128] elu. 42-48k env steps/s in training (per 131k-step iteration: env 0.9-1.1 s, torch inference + PPO update 1.6-1.9 s; `OMP_WAIT_POLICY=PASSIVE`, 8 torch threads best). **Pure RL from scratch failed** (≈ 120 M steps over 6 runs): run 1 discarded (two env bugs found by R0.5's comparison); run 2 (sum-of-cosines reward) "link 1 up, link 2 spinning", std collapsed by 33 M; run 3 (product reward) both links tumbling at 23 M; run 4 (reset curriculum near upright / random / hanging, coordinator's suggestion) pumps energy and tumbles near E_up, 0 % from hanging and from upright at 23 M; balance-only bal1 (init_std 0.3, 10 M) and bal2 (+ drop termination, 6.6 M) never balance. **Env sanity check**: the example's balance LQR as the actor in this env (200 Hz, differenced rates, ±24 V clamp, resets at rest) balances 100 % of starts up to ±0.2 rad, 91 % at ±0.3 rad (same at 1 kHz), and still 100 % with σ = 0.3 Gaussian action noise (7 V per 5 ms): env, conventions, rate estimate, action scale and exploration noise are fine. **Diagnosis**: the learned actor had the LQR's signs but 6-80× too small gains (da/dth2 +0.14 vs +10.7 needed; the LQR saturates at 0.1 rad) and a normaliser fitted to tumbling data; PPO does not grow such high gains from scratch. **Imitation warm start works** (`--bc-lqr 3000`: 262k samples of the noisy LQR, the LQR within 0.6 rad of upright and 0 V elsewhere, normaliser frozen after BC): **balA** (BC + PPO, upright starts ±0.3 rad, init_std 0.1, entropy 0, drop termination 0.8 rad): 0.94 after BC, best **0.95** from upright (64 starts, 6 s, both links within 0.1 rad over the last second; the LQR's own rate is 0.91 at ±0.3 rad), 13.1 M steps in 5.2 min; PPO is fragile on top (one eval at 0.00, iteration 90). Run 5 (BC + curriculum toward hanging) and run 6 (+ 20-iteration critic warm-up) both lost the balance within 40-60 iterations once PPO moved the actor for the swing-up. Second opinion (Fable subagent): hand-scaled observations instead of the empirical normaliser, entropy 0, small init_std, 50 Hz policy. Hybrid probe (train7, angle catch 0.3 rad, LQR in the training loop): 16 % swing-up success from hanging at 23.6 M steps when stopped. **Swing-up timebox** (pure RL / imitation warm start / hybrid, about 1.5 h, ≤ 50 M steps per run): see the R0.6 draft's "swing-up variants" row. Best: imi2 (BC on the TVLQR swing-up + PPO with a BC anchor, `rlpend/experts.py`, `--bc-expert tvlqr --bc-anchor 20`), 0.66 from noisy hanging at 37 M steps. Pure-RL balance with the fixes (`--fixed-norm --widen`): 0.91 at ±0.20 rad by 26 M, stalls at ±0.25 |
| R0.4 | policy-to-block generator, compile time measured | done | `rl/make_policy_block.py`: actor weights + rsl_rl normaliser mean/std (+1e-2) + action scale/clamp → `library/DoubleCartPolicy.jl` (`@discrete Ts = 0.005`, the env's observation pipeline operation for operation, `Mat * Vec`, `tanh` loops, `clamp`); numpy twin vs torch actor 9e-7; 66 KiB, 4865 weights; hybrid variant adds the latched catch z'Pz < catch_tol and the LQR (`rl/classical.py` → `rl/classical.json`). `pendulum-double-cart-rl` (`design/rlmodels.py --rl balance`): start at rest at 0.1/-0.05 rad, push 0.28 N at 3 s, 6 s. bgsim (`rl/closed_loop.jl`, Rodas5P 1e-8): **cold** flatten 2.1 s, compile 2.0 s, first run 31.8 s (Julia JIT of the generated code); **warm** flatten 0.16 s, compile 1.3 s, run 2.7 s for 6 s (other models 0.2-0.3 s compile, 1.4-2.0 s run for 4 s). Fine; the cold first run is the only slow part. Swing-up: `--name DoubleCartSwingPolicy` (imi2/model_280.pt, numpy twin 1e-6) and `pendulum-double-cart-rl-swingup` (`--rl swingup`: hang until 1 s, push 0.28 N at 7 s, 12 s): warm flatten 0.16 s, compile 1.2 s, run 4.3 s |
| R0.5 | bgsim closed loop vs training env | done | `rl/compare.py --task balance` (balA/model_best.pt): 4 rest starts within 0.25 rad, 4 s each, bgsim (plant + generated block) vs the batched FMU env: max deviation **x 8e-7 m, th1 3e-6 rad, th2 8e-7 rad, u 2e-3 V** over the whole 4 s. Default model in bgsim: upright inside 2° from 0.7 s, band before the push 0.81°/0.73° with the cart 47 mm off centre (the LQR firmware: 0.01°, 1 mm), push peak 18.4°/6.4° (LQR 17.8°/6.0°), back inside 1.4° by 5 s, peak 22.5 V, peak cart 0.217 m. `expected.json` entry `pendulum-double-cart-rl` (13 checks) passes with `run_checks.py --only pendulum-double-cart` (78 passed; the 1 failure is the docs KaTeX check of the existing model: `katex` not installed in this worktree's web/node_modules). Plot: `runs/cmpA/compare.png` (not committed). Swing-up: `rl/compare.py --task swingup` (imi2/model_280.pt): 3 hanging cases (6 s) and 2 upright cases (4 s): until 1 s ≤ 1e-6 m / 6e-6 rad, upright cases 3e-7 m / 2e-6 rad / 2e-3 V throughout; through the swing-up 8e-4 m and 1e-3 rad (tumbling amplifies round-off), same outcomes (the third hanging case leaves the rail in both, then 7e-2 rad). `expected.json` entry `pendulum-double-cart-rl-swingup` (13 checks) passes (`run_checks.py --only pendulum-double-cart`: 94 passed, the same 1 KaTeX failure). Plot: `runs/cmpS/compare.png` (not committed) |
| R0.6 | go/no-go report | done | "Step 0 result" above: **go**, with the imitation warm start as the recipe (lab rig: 0.97 from noisy hanging in 4 min, as good as the classical firmware in bgsim); pure RL (best 0.16) and the hybrid (best 0.53) stay comparison rows |
| R0.7 | lab rig: plant-only FMU + timeboxed swing-up variants | done | `examples/pendulum-double-cart-lab/design/rlmodels.py` → `pendulum-double-cart-lab-plant` (27 realism parameters exposed with their ranges, `design/rl_ranges.json`; link properties as driven globals, checked against `lablib.link_props`); `rl/export_plant.jl --rig=lab`, `rl/build_plant.py`: Rodas4P 1 ms, 5.5 µs/doStep, 1.5e-4 vs Rodas5P (nominal and 9 globals changed), current 3.1e-2. `rl/classical.py --rig lab` → `rl/classical_lab.json` (K = design.json Klqr, P, TVLQR tables, link properties). Env: link COM/inertia energy, end-stop state reset with the cart, `train.py --rig lab` (episode end 0.95 m). Sanity check: TVLQR 100 % from noisy hanging, LQR 1.00/0.95/0.71 at ±0.1/0.2/0.3 rad. Catch region (`catch_calib.py --rig lab`): smallest failing rest start z'Pz = 3.3e4. Timebox (about 1 h 55 min of training, 5 runs ≤ 47 M steps): imiL 0.97, pureL 0.16, pureL2 0.00, hybL 0.53, hybL2 0.44 (table in the R0.6 section). Shipped: `library/DoubleCartLabPolicy.jl` (imiL/model_best.pt) and `pendulum-double-cart-lab-rl`; `rl/compare.py --task lab`: bgsim vs env 2e-6 m / 2e-6 rad / 4e-4 V; `expected.json` entry (15 checks) passes (`run_checks.py --only pendulum-double-cart-lab`: 104 passed, the 1 failure is the docs KaTeX check, `katex` not installed in this worktree). Plots: `runs/cmpL/compare.png`, `runs/{imiL,pureL,pureL2,hybL,hybL2}/curve.png` (not committed) |
| R1 | domain randomisation, non-idealities, robustness table | done | "Step 1 result" above. Realism forces in the plant FMU (`LabRealism`, 35 globals), per-episode randomisation of every realism parameter, encoders, delay; actor on the encoder history (21 inputs), privileged critic. Scored on the shared test `examples/pendulum-double-cart-lab/design/robustness_test.json` (C5 of `plan/ROBUST_CLASSICAL_PLAN.md`): **rl-imitation-dr** 64/64 swing-up, 64/64 balance + push (tail 0.77° / 0.83°, 5.2 V rms of chatter, inherited from the expert's 5-sample-fit labels; PPO did not reduce it); rl-pure-dr 0/64 and 8/64; rl-hybrid-dr 15/64 and 64/64 (1 h each). Shipped `pendulum-double-cart-lab-rl-robust` (`library/DoubleCartLabRobustPolicy.jl`, imiR2): bgsim vs env 1e-7 until an encoder count edge, then 2-3 mm / 3-4 mrad, same outcomes; 16 checks pass. Next: an observer (EKF) in front of the network to remove the chatter |
| R2.1 | triple cart | deferred | until the 2-link workflow proves viable |
| R2.2 | quad cart | deferred | until the 2-link workflow proves viable |
| R2.3 | rotary double, triple | deferred | until the 2-link workflow proves viable |
| R2.4 | rotary quad | deferred | until the 2-link workflow proves viable; only if the realism work says feasible |
