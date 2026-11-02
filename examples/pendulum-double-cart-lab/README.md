# pendulum-double-cart-lab — the double-cart lab rig: 0.35 m tube links on a ±1 m rail, swing-up with margins, balance, push, and the realism parameter set for RL and robust control

The rig of `pendulum-double-cart` (same DC motor, 3:1 gearbox, 16 mm pulley, belt and cart carriage) with two
**0.35 m** links built the way a lab would build them, on a **±1.0 m** rail with soft end stops. It is the
shared platform of the RL workflow (`plan/RL_PLAN.md`) and the robust classical work
(`plan/ROBUST_CLASSICAL_PLAN.md`, item C0): `design/realism.json` is the one definition of the rig, with
nominal, min, max, unit and a description for every parameter, and `design/lablib.py` builds the design
model, the bond graph, the twin and the firmware replica for any parameter set. `pendulum-double-cart` itself
is unchanged.

| model | what it runs |
| --- | --- |
| `pendulum-double-cart-lab` | hanging at rest 1 s, the swing-up (3.0 s), the catch at 4.0 s, balance, a 0.45 N / 40 ms tip push at 7.5 s, recovery, end 12.5 s |
| `pendulum-double-cart-lab-balance` | balance only: both links start leaning 2°, a 0.70 N / 40 ms tip push at 2 s (78 % of the largest the design recovers), end 6 s |
| `pendulum-double-cart-lab-free` | no control, motor shorted: the free swing from rest at θ = (−2.2, −1.2) rad, x = 0.05 m, checked against the twin |
| `pendulum-double-cart-lab-rl` | the swing-up model's scenario with a learned controller: one neural network (`library/DoubleCartLabPolicy.jl`, 200 Hz) swings up, balances and catches the push (see "Learned controller") |
| `pendulum-double-cart-lab-rl-robust` | the same scenario with the R1 robust policy (`library/DoubleCartLabRobustPolicy.jl`, trained with domain randomisation on the encoder history) on the realistic plant: every realism effect, the 2 ms loop delay and the encoder noise (see "Robust policy") |
| `pendulum-double-cart-lab-plant` | the plant without firmware, for the FMU of the RL environment: voltage and tip push in, encoders out, the realism parameters as globals |
| `pendulum-double-cart-lab-robust` | the swing-up model's scenario with the robust classical firmware: the multi-model LQR balance (C1) on an observer, with the rig's 2 ms loop delay in the loop (see "Robust classical controllers") |
| `pendulum-double-cart-lab-recover` | the state-driven firmware (C3): swing-up, a 1.5 N / 100 ms knock-down at 7 s, energy removal, the hanging rest, a re-armed swing-up and the re-catch, end 20 s |

The firmware has the structure of `pendulum-double-cart` (1 kHz, `library/DoubleCartLabCtrl.jl` with the
tables of `library/DoubleCartLabTraj.jl`):

| time | phase (`Ctrl/phase`) | what happens |
| --- | --- | --- |
| 0 – 1 s | 0, hold | hanging at rest, motor voltage 0 (checked: nothing moves) |
| 1 s | 1, swing-up | trajectory feed-forward from the offline optimisation, tracked by a time-varying LQR (TVLQR) |
| 4.0 s | 2, balance | after T_s = 3.0 s the nominal ends upright; the 1 kHz discrete LQR takes over |
| 7.5 s | 2 | 40 ms, 0.45 N force pulse on the tip link |
| to 12.5 s | 2 | recovery, then 3 s of quiet balance |

## Rig (`design/realism.json`, nominal column)

| part | value |
| --- | --- |
| cart | 0.80 kg carriage (belt clamp, joint-1 bearing block and encoder board, share of the cable chain), J = 1.5e-3 kg m²; viscous 0.5 N s/m (guide, belt) + 0.2 N s/m (cable chain) |
| rail | ±1.0 m of free travel of the cart centre to rubber end stops (`HardStop`, 2e4 N/m, 200 N s/m) |
| link 1 | 0.35 m: Al tube 20 × 2 mm 107 g, clamp hub 30 g and encoder magnet 1 g at the pivot, head 105 g (joint-2 bearing block with two 688 bearings) and encoder board 3 g at the tip, joint-2 cable 6 g/m along it: **0.248 kg, COM 0.229 m (65 % of L), J = 4.68e-3 kg m²** |
| link 2 | 0.35 m: Al tube 107 g, clamp hub 45 g (8 mm shaft) and magnet 1 g at the pivot, tip cap 47 g: **0.200 kg, COM 0.176 m, J = 3.96e-3 kg m²** |
| joints | viscous 2e-4 N m s/rad each (joint 1 + 1e-5 cable drag); Coulomb 2e-4 N m per joint and 1e-4 N m/rad cable spring on joint 1 in the realism set only |
| motor | 24 V supply, R = 1.5 Ω, L = 0.5 mH, k_t = k_e = 0.0302 N m/A, rotor 1.4e-5 kg m², bearing 2e-6 N m s/rad (the 90 W-class brushed servo of `pendulum-double-cart`) |
| transmission | 3:1 gearbox, 16 mm pulley radius, belt 4e5 N/m with 60 N s/m |
| derived | 3.78 N/V, stall force 90 N (16 A), rotor reflected to the cart 0.49 kg, effective cart 1.29 kg, back-EMF damping 21.4 N s/m |

**How the COM and inertia are set.** `lablib.link_props` lumps the parts list of each link (the same list
`realism.json` randomises): the tube as a thin-walled cylinder about its own centre (J = m (L²/12 + (r_o² +
r_i²)/4), its COM at L/2 plus `com_shift` L), the hubs, the head and the tip cap as small cubes at the pivot or
the tip (J = m s²/6, s = 30, 40, 25 mm), the magnet and the encoder board as point masses, the cable as a
uniform rod; the link's mass is the sum, its COM the mass-weighted mean, its inertia about the COM the sum of
the parts' own inertias plus the parallel-axis terms. The heavy head at the tip of link 1 puts its COM at 65 %
of the length.

**Linearised upright.** Unstable poles **4.55 and 8.92 /s** (stable −4.26, −8.64, −16.9 and the cart's 0).
As a check of the estimate for uniform 0.25/0.25 kg rods on the same 1.29 kg effective cart: 4.66 and 12.3 /s
(estimated 5.1 and 12.5 /s). The lab links are slower in the second mode because the head and the tip cap
give link 2 more inertia about its pivot.

**Energy to swing up.** Hanging to upright raises the potential energy by Σ m g 2h = **3.18 J** (3.8 times the
0.83 J of `pendulum-double-cart`). The design swing-up draws 10.8 J from the supply over its 3 s, 6.8 J of it
copper loss; the mechanical power peaks at 38 W, the rms current is 1.2 A.

## Plant (bond graph)

The bond graph of `pendulum-double-cart` (see its README: `Prismatic2D` rail, `Revolute2DCompliant` joints
with 1e8 N/m pivots, `RigidBody2D` cart and links, `ElectricDrive` → `Gearbox` → `RackAndPinion` →
`SpringDamper` belt, `ExternalWrenchPlanar` push), generated by the same `cartmodel.py`, plus two elements on
the rail drive: `RailFriction` (`Damper`, the carriage and cable-chain friction) and `EndStops` (`HardStop` at
±1.0 m). Both are options of `cartpend.Plant` (`b_cart`, `k_stop`, `d_stop`, default off), so the original
example regenerates byte-identically (checked, and `pendulum-triple-cart` as well).

## Design (`design/design.py`, `uv run`, CasADi + IPOPT + SciPy)

`design/design.py` builds the plant from `realism.json` (`lablib.design_plant`) and runs the design code of
`pendulum-double-cart` (`cartpend.py`): the Lagrangian design model (identical to the twin, checked to 1e-15),
Hermite-Simpson collocation, the continuous TVLQR, the discrete LQR, the table writer, and `cartmodel.py`.

1. **Swing-up plan with margins**: 75 intervals, T_s = 3.0 s, minimum ∫V² dt from hanging to upright at rest,
   **|V| ≤ 16.8 V (70 % of 24 V)** and **|x| ≤ 0.8 m**. Result: feed-forward 14.8 V peak (62 %), the cart reaches
   ±0.387 m. Neither bound is active (a 2.4 s plan hits both).
2. **TVLQR**: Q = diag(300, 400, 400, 10, 8, 8), R = 0.3 V⁻² along the trajectory.
3. **Balance LQR**: discrete (ZOH, 1 ms), same weights, largest gain 329.
4. **Firmware replica** (`lablib.firmware`, the quadlib replica with the time-based catch) on the twin: the
   robustness table, the largest push and the realism screen.

```
uv run examples/pendulum-double-cart-lab/design/design.py --write --robust   # library, models, design/design.json
uv run examples/pendulum-double-cart-lab/design/finish.py                    # backend runs, expected.json, measured.json
uv run examples/pendulum-double-cart-lab/design/screen.py all --jobs 5       # the realism screen (about 10 min)
```

### Design results and margins (design closed loop; the bond graph agrees, see Results)

| quantity | value |
| --- | --- |
| catch (phase 2) | 4.00 s (all links inside 2° for good 2.55 s after the start of the swing-up) |
| peak voltage, swing-up | **15.0 V of 24 V** (63 %; the plan bound 16.8 V is never reached) |
| peak current, swing-up / whole run | 5.3 A / 6.0 A (stall 16 A) |
| peak travel | **0.387 m** of the ±0.8 m plan and the ±1.0 m rail |
| push 0.45 N / 40 ms at 7.5 s | 10.7° / 4.0°, cart 0.17 m, back inside 0.5° after 2.12 s |
| balance model push 0.70 N | 17.3° / 5.8°, 20.6 V, 11.0 A, cart 0.24 m, back inside 0.5° after 2.29 s |
| **largest 40 ms push recovered** (balance from upright) | **0.90 N** (0.87 N with 2 ms delay); 27.6° on link 1, cart 0.34 m, the voltage saturates briefly |
| belt mode in closed loop (0–2 ms delay) | 177 Hz, ζ 0.07–0.13 (softest belt 2e5 N/m: 124 Hz; lowest damping 30 N s/m: ζ 0.03): stable |

### Robustness (firmware replica on the twin)

Swing-up with the 0.45 N push, and the balance model's 0.70 N push. "ok": inside the rail and within 1° over
the last second. Every case passes.

| case | swing-up: ok, peak V, peak x | balance: ok, push deflection, peak V |
| --- | --- | --- |
| nominal | yes, 15.0 V, 0.387 m | yes, 17.3°, 20.6 V |
| link masses −5 % / +5 % | yes / yes, 14.9 / 15.1 V | yes / yes, 18.4° / 16.4° |
| link lengths +1 % / −1 % | yes / yes, 14.8 / 15.3 V | yes / yes, 17.1° / 17.5° |
| joint friction ×3 | yes, 15.8 V | yes, 17.6° |
| carriage friction ×3 | yes, 15.3 V | yes, 17.3° |
| cart mass +10 % | yes, 15.1 V | yes, 17.6° |
| delay 1 ms / 2 ms | yes / yes, 15.0 / 15.0 V | yes / yes, 17.5° / 17.6° |
| quantised encoders (14 bit joints, 8.4 µm cart, 2 ms rate filter) | yes, 18.5 V, tail 0.03° | yes, 17.5°, 24 V briefly |
| quantised encoders + 2 ms delay | yes, 17.4 V | yes, 17.8° |
| masses +5 %, lengths +1 %, both frictions ×3, 2 ms delay, quantised | yes, 16.6 V, 0.385 m | yes, 16.9° |

## Realism screen (twin only, `design/screen.py`)

`uv run examples/pendulum-double-cart-lab/design/screen.py all --jobs 5 --n 48` (about 4 min on 5 cores; the
raw runs go to `design/_screen/`, ignored; `screen.py summary` rewrites the summary). The truth is the twin of
`lablib.setup` with every effect of `realism.json` (RK4, 8 substeps per 1 ms sample); the firmware replica has
the design's tables and gains unchanged, the sensors, the 2 ms delay and the armature lag L/R. Scenarios: the
swing-up (to 8 s) and the balance from a 2° lean with the 0.45 N push at 2 s (to 7 s). "ok": the cart stays
off the end stops and every link is within 2° of upright over the last 2 s. Summary, verdict and the
per-case evidence: `design/screen_results.json`.

| study (all effects nominal unless noted) | filtered differences (`diff`, τ_f 2 ms) | EKF (q_acc (1, 10)) |
| --- | --- | --- |
| all effects together, tail deviation swing-up / balance | ok **0.61° / 0.37°**, but 9 V rms chatter, 24 V peaks, 17 A | ok **0.13° / 0.21°**, 15.1 / 16.3 V, 5.8 / 8.9 A |
| the effect that matters | the joint encoders (noise alone: 0.5°, 24 V, 20 A) | joint and carriage friction (≈0.1° each) |
| mass spread, drive, cable, loop delay, ripple and cogging | negligible | negligible |
| joint-2 Coulomb friction (nominal 2e-4 N m) | 1e-3 ok 0.69°, 2e-3 ok 0.87°, 5e-3 fails (3.6°) | 1e-3 ok 0.41°, 2e-3 marginal 1.7°, 5e-3 fails (3.9°) |
| joint-1 Coulomb friction | 5e-3 ok 0.93°, 1e-2 ok 1.5°, 2e-2 fails (3.3°) | 5e-3 ok 0.87°, 1e-2 ok 1.8°, 2e-2 fails (3.6°) |
| both joints | 1e-3 ok 0.73°, 2e-3 ok 1.5°, 5e-3 fails | 1e-3 ok 0.86°, 2e-3 marginal 1.9°, 5e-3 fails |
| encoders 12 bit 0.08° / 14 bit 0.08° / 16 bit 0.005° / 18 bit | **fail** / **fail** / ok 0.13° (15.7 V) / ok | ok 0.34° / ok 0.41° / ok 0.14° / ok |
| rate filter τ_f 1 / 5 / 10 ms | 1.4° (24 V) / 0.22° (22 V) / 0.21° (21 V) | — |
| EKF process noise (0.3, 3) … (10, 100) | — | all ok 0.13–0.21°; (10, 100) raises u to 20 V |
| cart Coulomb compensation 0 / 0.5 / 1 | 0.63° / 0.55° / 0.61° | 0.44° / 0.14° / 0.13° (carriage at 2 N: 0.44° / 0.19° / 0.15°) |
| **Monte Carlo, 48 draws over every range** | **36/48** (failures: 2.0–3.7° limit cycles, all with joint noise ≥ 0.055° rms; 24 V, 21 A) | **48/48 swing-up and 48/48 balance**: tail median 0.22°, max 0.41° / 0.48°; worst 18.2 V, 8.5 A, 0.39 m |

**Verdict: feasible with margin.** The unchanged classical controller passes every effect at its nominal
value and all 48 Monte Carlo draws over the ranges of `realism.json`, provided the rates come from an
**EKF** on the nominal model (or the joint encoders are 16-bit class). Filtered differences with the
AS5048-class 14-bit encoders are only marginal (the voltage chatters to the 24 V limit, a quarter of the
draws limit-cycle at 2–4°). The **joint Coulomb friction budget** is about **1e-3 N m on joint 2** and
**5e-3 N m on joint 1**, 5–25× the assumed 2e-4 N m of small ball bearings, so the 0.35 m links take
ordinary bearings (the cart quad needs 5e-5 N m). The cart Coulomb compensation helps (0.44° → 0.13°) but is
not required. The recommendations (EKF tuning, encoder grade, bearing budget) are in `design/screen_results.json`.

## Results (real worker, Rodas5P, reltol 1e-8, `design/measured.json`)

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| design vs bond graph, free swing 2 s (max angle difference / cart) | **4.3e-4 rad** / 4.3e-5 m | — |
| at rest before 1 s | exactly (0 motion) | |
| swing-up time (all links inside 2° for good) | 2.55 s after the start | 2.55 s |
| catch (phase 2) | 4.00 s | 4.00 s |
| swing-up, max difference to the design closed loop (angles / cart) | 1.5e-3 rad / 0.3 mm | |
| upright band from 0.1 s after the catch to the push | 0.0023° (cart 0.04 mm) | 0.0017° |
| push 0.45 N: peak deflection link 1 / link 2 | 10.71° / 3.98° | 10.70° / 3.98° |
| recovery, inside 1° / 0.5° after the push | 1.06 s / 2.12 s | 2.12 s (0.5°) |
| peak motor voltage (swing-up and push) | 15.01 V of 24 V | 15.02 V |
| peak motor current | 5.97 A | 5.98 A |
| peak cart travel | 0.387 m of ±0.8 m (plan) / ±1.0 m (rail) | 0.387 m |
| balance model: lean caught, push 0.70 N peak link 1 / link 2 | 0.28° before the push; 17.35° / 5.79° | 17.32° / 5.80° |
| balance model: peak voltage, current, travel; recovery inside 0.5° | 20.7 V, 11.0 A, 0.241 m; 2.29 s | 20.6 V, 11.0 A, 0.242 m; 2.29 s |
| run time (backend, swing-up 12.5 s / balance 6 s / free 2 s) | 56 s / 11 s / 4 s | |

## Checks (`expected.json`, written by `design/finish.py`)

Machine-checked by `uv run examples/run_checks.py --only pendulum-double-cart-lab`. Swing-up model: at rest
before 1 s; the phase signal 0 / 1 / 2; the link angles at 40 %, 70 % and 100 % of the swing-up against the
design closed loop (0.01 rad); every link within 0.2° of upright from 0.1 s after the catch to the push and
the cart within 1 cm; the push deflection (the push is real); back inside 0.5° after the recovery and within
0.2° over the last second; |V| ≤ 24 V, **the swing-up within the planned 16.8 V and the cart within the planned
±0.8 m** (so the end stops are never touched), the peak voltage, current and travel; the scene bindings; no
diagnostics. Balance model: balance from the first tick, the lean caught, the push deflection, the recovery,
the voltage, current and travel. Free model: the cart and joint angles against the design ODE (the twin)
every 0.25 s.

## Learned controller (`pendulum-double-cart-lab-plant`, `pendulum-double-cart-lab-rl`, `pendulum-double-cart-lab-rl-robust`)

Steps 0 and 1 of `plan/RL_PLAN.md` (items R0.7 and R1) on this rig: neural-network controllers trained on the
exported plant FMU and brought back as ordinary `@discrete` blocks. The models are written by
`design/rlmodels.py`.

- **`pendulum-double-cart-lab-plant`**: the bond graph without Clock, firmware and push pulse. The motor
  voltage `V` and the tip push `F_push` are `ExportInput`s; the encoders `x`, `q1`, `q2` and, for the
  critic, `v`, `w1`, `w2`, `i_m` are `ExportOutput`s. Every `realism.json` parameter is a global under its own
  name. The 27 that enter the bond graph and have a range (link tubes, hubs, head, tip cap, encoder parts,
  cable, cart mass, viscous frictions, motor R/L/k_t/J_m/b, pulley radius, belt) are exposed in the FMU with the
  realism min/max (`design/rl_ranges.json`). The lumped link masses, centres of mass and inertias
  (`lablib.link_props`) are driven globals recomputed at the FMU's initialisation. The realism forces outside
  the bond-graph elements (Coulomb friction of the joints, the carriage and the motor, the cable springs,
  commutation ripple and cogging) are the project block `library/LabRealism.jl` (the twin's laws, from the
  plant's own signals) on a rail force source and the joint drives, with their globals exposed as well (35
  in all, ranges down to 0). The FMU and bgsim therefore share all of the physics. Sensors and loop delay
  stay in the env wrapper. Export: fixed Rodas4P 1 ms (`rl/export_plant.jl --rig=lab`, `rl/build_plant.py`),
  5.5 µs per step, 1.5e-4 of the peak against Rodas5P, also with 9 globals changed before initialisation.
- **`pendulum-double-cart-lab-rl`**: the plant (nominal values) with `library/DoubleCartLabPolicy.jl`, a
  [64, 64] tanh actor (4865 weights, 200 Hz) generated by `rl/make_policy_block.py --rig lab`. The block
  repeats the training env's observation pipeline: sin/cos of the absolute angles, the cart position, rates
  from differences of the encoder samples, and the previous action. A single network runs alone, with no LQR
  switch-over. It hangs until 1 s, then swings up, balances and gets the classical model's 0.45 N push at 7.5 s.
  The policy was behaviour-cloned on this rig's TVLQR swing-up and LQR (`rl/classical.py --rig lab`), then
  trained with PPO plus a cloning anchor. In bgsim it is upright inside 2° 2.7 s after it starts (the TVLQR
  catches at 3.0 s), holds 0.2° and 3 mm before the push (the classical firmware: 0.002°), deflects by
  10.9° / 3.7° (classical 10.7°), and uses at most 15.2 V and 0.388 m of the rail (classical 15.0 V, 0.387 m).
- **Agreement**: from three hanging and two upright rest poses, bgsim (Rodas5P, reltol 1e-8) and the training
  env (the batched FMU) agree to 2e-6 m, 2e-6 rad and 4e-4 V over 4-6 s (`rl/compare.py --task lab`).
- **Checks**: `expected.json` → `pendulum-double-cart-lab-rl` (0 V and at rest before 1 s, the upright band,
  the push deflection and travel, recovery, |V| ≤ 24 V, the peak voltage and travel, the scene bindings, no
  diagnostics). `design/finish.py` keeps this entry when it rewrites the file.

Regenerate (the `rl/` uv project; the runs go to the ignored `runs/`):

```
uv run examples/pendulum-double-cart-lab/design/rlmodels.py --rl
julia --project=julia/BGSim rl/export_plant.jl runs/plantL --rig=lab
uv run --project rl rl/build_plant.py runs/plantL
uv run rl/classical.py --rig lab
uv run --project rl rl/train.py runs/plantL/export runs/imiL --rig lab --bc-lqr 10000 --bc-expert tvlqr --bc-sigma 0.1 --bc-anchor 20 --critic-warmup 20 --no-curriculum --p-up 0.2 --p-random 0.1 --init-std 0.05 --entropy 0 --desired-kl 0.005 --gamma 0.998 --drop-penalty 20 --iterations 340 --eval-every 20 --threads 6 --torch-threads 4 --stop-success 0.95
uv run --project rl rl/make_policy_block.py runs/imiL --checkpoint model_best.pt --name DoubleCartLabPolicy --rig lab
uv run --project rl rl/compare.py runs/imiL runs/plantL/export runs/cmpL --checkpoint model_best.pt --task lab
```

PPO training is not bit-reproducible across thread counts; the checkpoint refers to the run that produced the
committed block.

### Robust policy (R1: `pendulum-double-cart-lab-rl-robust`)

- **Training** (`rl/train_robust.py`, env `rl/rlpend/renv.py`): every episode draws a full `realism.json`
  parameter set (masses, lengths, frictions, motor, ripple, cogging, cable, 1-2 ms loop delay, encoder noise)
  and sets it in the FMU before initialisation. The env adds the 14-bit joint encoders with noise, the cart
  encoder, the loop delay and random tip pushes. The actor sees only the encoder history: the last 4
  differences of the measured positions and its last 4 actions, 21 inputs at 200 Hz. The critic sees the
  true state and the draw's parameters. Warm start: behaviour cloning of the rig's TVLQR swing-up and LQR
  with Coulomb compensation, plus 2 DAgger rounds, 4.3 M samples in 25 min. The expert labels its actions
  from a 5-sample least-squares fit of the same encoder history. Labels from the true state gave a
  student that balanced in a 3° limit cycle: regressing on noisy rates shrinks the rate gains. Then 310 PPO
  iterations with a cloning anchor (40.6 M env steps, 51 min; 75.7 min in all).
- **Shared robustness test** (`design/robustness.py`, entry `rl-imitation-dr`): 64/64 swing-up and 64/64
  balance + push on the Monte Carlo draws, tail 0.77° / 0.83° (median), peak cart travel 0.44 m. The
  weakness is the voltage. The tail holds about 5.2 V rms of chatter, and noise spikes reach the 24 V clamp
  all through the balance, not only at the catch. The nominal firmware with its EKF needs 1.4 V rms and the multi-model LQR 0.8 V rms. The
  chatter comes from the expert's labels: the expert on the 5-sample fit gives the same 5.3 V rms in the env
  (0.5 V on the true state). PPO, with or without an extra action-rate penalty, did not reduce it
  (`rl-bc-dr`, the same run before PPO: 5.2 V rms). In their 1 h timeboxes pure RL swung up none of the
  draws (`rl-pure-dr`: 0/64, balance + push 8/64). The hybrid, an RL swing-up with the LQR catch, swung up
  15/64 and was still improving (`rl-hybrid-dr`; see `plan/RL_PLAN.md`, R1).
- **`pendulum-double-cart-lab-rl-robust`**: the realistic plant at the nominal draw (every realism effect,
  the 2 ms loop delay, seeded encoder noise through stdlib `Noise` blocks) with
  `library/DoubleCartLabRobustPolicy.jl` (5633 weights; the block quantises the encoders, delays its output and
  repeats the env's observation pipeline). Same scenario as `pendulum-double-cart-lab-rl`: upright inside 2° at
  3.97 s, 1.4° / 1.1° (measured) before the push, 10.8° / 4.2° after it, 0.377 m peak travel, 24 V peak.
  Warm run in bgsim: flatten 0.3 s, compile 1.7 s, run 19 s (cold first run 75 s).
- **Agreement** (`rl/compare.py --task robust`, quantised encoders without noise, the nominal draw and two
  test draws): bgsim and the env agree to 1e-7 until a trajectory reaches an encoder count edge at a
  different time. A count of difference then changes the rate estimate, so over 4-6 s they differ by
  2-3 mm, 3-4 mrad and up to 4.7 V of chatter, with the same outcome (tail 0.22° / 0.16°, 0.31° / 0.24°,
  1.2° / 1.2°, 1.1° / 1.1° bgsim / env).
- **Checks**: `expected.json` → `pendulum-double-cart-lab-rl-robust` (0 V and at rest before 1 s, within 2° before
  the push, the push deflection and travel, within 2° over the last second, |V| ≤ 24 V, the peak travel, the
  scene bindings, no diagnostics).

```
uv run examples/pendulum-double-cart-lab/design/rlmodels.py --rl-robust
julia --project=julia/BGSim rl/export_plant.jl runs/plantR --rig=lab
uv run --project rl rl/build_plant.py runs/plantR
uv run --project rl rl/train_robust.py runs/plantR/export rl/runs/imiR2 --iterations 400 --max-minutes 75 --eval-threads 2
uv run examples/pendulum-double-cart-lab/design/robustness.py run --controller rl/lab_policy.py:robust_policy --name rl-imitation-dr --opt weights=rl/runs/imiR2/policy.npz --jobs 6
uv run --project rl rl/make_policy_block.py rl/runs/imiR2 --robust --checkpoint policy.npz
uv run --project rl rl/compare.py rl/runs/imiR2 runs/plantR/export runs/cmpR1 --checkpoint policy.npz --task robust
```

## Robust classical controllers (`pendulum-double-cart-lab-robust`, `pendulum-double-cart-lab-recover`)

Items C1 to C3 of `plan/ROBUST_CLASSICAL_PLAN.md`. Every controller runs on the shared robustness test
(`design/robustness_test.json`, harness `design/robustness.py`). The truth is the twin with every realism effect:
Coulomb friction, cable springs, ripple and cogging, 14-bit encoders with noise, the 1-2 sample loop delay and the
armature lag. The test has the nominal draw plus 64 Monte Carlo draws. The scenarios are `swingup`,
`balance_push` and the unscored `knockdown_recover`. The pass rule: |x| < 0.95 m throughout, and both links
within 2° of upright over the last 2 s.

```
uv run examples/pendulum-double-cart-lab/design/robustness.py run --controller robust_ctrl:make --name <name> --opt balance=mm_lqr [--opt mode=rearm --opt pfl=simple] [--scenarios ...]
uv run examples/pendulum-double-cart-lab/design/robustness.py show
```

A controller is any object with `rate_hz`, `reset(seed=, start=)` and `step(sensors) -> volts`: a
`module:factory`, or a `.npz` MLP policy. It sees the joint and motor encoder counts and its previous command.

**C1, robust balance** (`design/robust_lin.py`, `design/robust_c1.py`, `design/robust_c1.json`). Every design has
the firmware structure u = -K [x̂; u(k-1); u(k-2)] (8 gains) on the 1 kHz EKF, and is designed with the 2-sample
delay, the armature lag and the observer in the loop. The 8 gains are designed four ways:
- **mm_lqr**: the multi-model LQR, mean H2 over 256 box corners and 64 draws.
- **hinf**: structured H∞, the worst weighted H∞ norm over the same models.
- **mu**: μ-synthesis by D-K iteration with the fixed structure.
- **gmf**: Glover-McFarlane loop shaping, in two shapings: `gmf` and `gmf_tuned`.

The verification has three parts:
- the closed-loop eigenvalues over 320 models;
- the disk and delay margins at the motor input;
- μ: the LFT of 12+ parameters (each a real repeated scalar) plus a complex multiplicative drive weight for the
  delay, lag and unmodelled dynamics. The table gives the complex upper bound over a frequency grid, and the
  mixed (real/complex) D-G bound of a 12-parameter LFT at the 6 frequencies around the complex peaks. The RP
  weights are scaled so that the nominal LQR's nominal performance peaks at 0.5.

| balance law | disk margin α (nominal / worst model) | delay margin (samples) | μ RS complex / mixed | μ RP complex / mixed | swingup | balance_push | balance_push peak V / x | tail V rms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nominal LQR (design.json) | 0.61 / 0.57 | 6 | 0.86 / 0.27 | 1.42 / 0.96 | 64/64 | 64/64 | 21.3 V / 0.194 m | 1.45 V |
| **mm_lqr** | **0.78** / 0.57 | **32** | 1.06 / 0.50 | 1.81 / 1.13 | 64/64 | 64/64 | **16.1 V** / 0.225 m | **0.78 V** |
| hinf | 0.46 / 0.32 | 5 | 1.27 / 0.59 | 1.60 / 0.98 | 64/64 | **49/64** | 24 V / 0.207 m | 1.82 V |
| mu | 0.55 / 0.47 | 7 | 0.95 / 0.26 | 1.14 / 1.09 | 64/64 | 64/64 | 20.8 V / 0.205 m | 1.26 V |
| gmf | 0.36 / 0.10 | 14 | 1.73 / 0.77 | 2.07 / 1.42 | 62/64 | 58/64 | 19.2 V / 0.281 m | 0.91 V |
| gmf_tuned | 0.40 / 0.26 | 5 | 1.25 / 0.37 | 6.13 / 6.12 | 64/64 | 64/64 | 24 V / 0.570 m | 1.25 V |

Findings:
- With the real structure, every law is robustly stable over the box: mixed RS μ ≤ 0.77. The complex bound
  overstates it, by 3x for the nominal LQR.
- The multi-model LQR is the best law on the test. It halves the voltage noise, takes the push with 24 % less
  voltage, and has the largest disk margin and a 32-sample delay margin. Its RP μ against the H∞ weights is
  higher, because those weights are tuned to the nominal LQR.
- The structured H∞ design has the best worst-case linear norm. Its low gains still saturate after the lean plus
  push, so it fails 15/64.
- Loop shaping has γ_min ≥ 5.5 for every shaping (ε ≤ 0.18): coprime-factor robustness is poor on this plant.

**C3, state-driven recovery** (`design/robust_ctrl.py`, `mode=rearm`). A drop sends the controller into a
settle phase, and the swing-up re-arms from the hanging rest:
- **Drop**: a link more than 20° from upright.
- **Rail guard**: brakes when the stopping point passes 0.8 m.
- **Energy removal**: through the cart, a = -k_E P_x - centring (P_x is the links' horizontal momentum). The
  collocated partial feedback linearisation V = (m_all a + βv)/α applies it.
- **Hanging LQR**: takes over below 3.8 J.
- **Re-arm**: 50 ms at the hanging rest re-arms the TVLQR swing-up, shifted to the cart position and the links'
  turn count, with the catch in the balance law's region z'Pz < tol.

With the mm_lqr balance and the nominal plan (`c3-rearm-mm_lqr`):

| scenario | success | catch time (median / max) | peak V | peak x |
| --- | --- | --- | --- | --- |
| swingup | 64/64 | 2.61 / 3.22 s | 18.1 V | 0.40 m |
| balance_push | 64/64 | 2.93 / 2.97 s | 16.1 V | 0.23 m |
| knockdown_recover | **64/64** | 12.94 / 13.64 s | 24 V | **0.80 m** (< 0.95 m) |

The timed nominal firmware recovers 0/64 knock-downs. Pure energy pumping to the upright, with the same
linearisation and the region catch, never caught within 20 s: the energy goes into a whirl of link 2 while link 1
stays low. So the swing-up itself stays the planned TVLQR, and the state machine re-arms it.

**C2, swing-up for the box** (`design/robust_c2.py`, `design/robust_c2.json`). The models are the design models
of the nominal set and the 16 corners of four groups: link masses, COM shifts, cart and rotor mass, and drive gain.
- **Open-loop min-max plan** (`minmax`): one feed-forward for the nominal (hard terminal) and 4 corners, with
  min-max terminal cost. It ends 1777 times a 2° lean away from upright. One open-loop input cannot swing up a
  double pendulum over the box, so the robustness has to come from the feedback.
- **The two plans that are kept**:
  - `mm_tvlqr`: the nominal plan with a TVLQR designed against all 17 models. It uses a common gain from the
    models' summed one-step costs, each model with its own cost-to-go.
  - `margin`: a plan inside 60 % of the supply and ±0.7 m, with the same multi-model TVLQR.
- **On the corners** (ideal states): the nominal TVLQR already lands every corner within 0.17° at T_s. The
  multi-model TVLQR gives 0.17° and the margin plan 0.20°.
- **On the robustness test** (mm_lqr balance, timed catch): both pass swingup 64/64, like the nominal plan.
  - mm_tvlqr: catch median 3.55 s, 18.1 V, 0.41 m.
  - margin: catch median 3.57 s, 18.6 V, 0.42 m.
- **Conclusion**: the box does not stress the TVLQR swing-up. The robust models use the `mm_tvlqr` tables. With
  them the C3 re-arm passes all three scenarios 64/64 (`c3-rearm-mm_lqr-mm_tvlqr`: the knock-down re-caught at a median
  12.95 s, peak 0.80 m).

**bgsim models** (`design/robustmodels.py`, `library/DoubleCartLabRobustCtrl.jl`, `library/DoubleCartLabRobustTraj.jl`):
- **What the block is**: the harness controller as one 1 kHz `@discrete` block on the bond graph's states. It has
  the mm_lqr gains, the observer (the steady-state EKF gain on the encoder angles and the cart), and the 2 ms loop
  delay (the output is the command of two ticks ago). It also has the C3 state machine (`rearm = 1`), with the
  energy, the simple partial feedback linearisation, the hanging LQR and the rail guard. The tables block (the C2 `mm_tvlqr` plan) reads
  the plan time `tau` that the firmware publishes, so a re-armed swing-up restarts the plan.
- **`pendulum-double-cart-lab-robust`**: the classical scenario (timed swing-up, catch at 4.0 s, 0.45 N push at
  7.5 s). The link 1 deflection is 12.9° and the travel 0.208 m; the classical LQR without delay gives 10.7° and
  0.173 m.
- **`pendulum-double-cart-lab-recover`**: settle and arm at 1.05 s, catch at 3.75 s, then a 1.5 N / 100 ms
  knock-down at 7 s. A drop follows at 7.10 s, energy removal from 5.2 J, the hanging rest, the re-arm at
  9.88 s and the re-catch at 12.58 s. Peak travel is 0.767 m, and the run ends upright.
- **Agreement**: a Python replica of the block on the twin (`robustmodels.py --replica`) has the same phase
  timeline (every switch within 1 ms). It agrees with bgsim to 3e-4 m and 7e-4 rad on the robust model, and to 6e-3 m and
  1.6e-2 rad over the 20 s recover run, through two swing-ups.
- **Checks**: `expected.json`, written by `robustmodels.py --expected`.

```
uv run examples/pendulum-double-cart-lab/design/robust_c1.py design|verify|mixed|harness
uv run examples/pendulum-double-cart-lab/design/robust_c2.py design|harness
uv run examples/pendulum-double-cart-lab/design/robustmodels.py --balance mm_lqr --plan mm_tvlqr
uv run examples/pendulum-double-cart-lab/design/robustmodels.py --replica <out.npz>
julia --project=julia/BGSim rl/closed_loop.jl <bg dir> --project=examples/pendulum-double-cart-lab examples/pendulum-double-cart-lab/models/pendulum-double-cart-lab-robust.bgmodel.json examples/pendulum-double-cart-lab/models/pendulum-double-cart-lab-recover.bgmodel.json
uv run examples/pendulum-double-cart-lab/design/robustmodels.py --expected <bg dir> --replica-npz <out.npz>
```

## What to try

- **Plots**: "Link angles from upright" (`Ctrl/th1`, `Ctrl/th2`), "Cart position" (`Rail/qout`), "Motor voltage and
  phase" (`Ctrl/u`, `Ctrl/phase`), "Motor current" (`Motor/isense/y`).
- **3D view**: the cart rides on a 2 m rail between red rubber stops; thin green posts mark the ±0.8 m the
  swing-up is planned inside.
- Raise `PushPulse/amplitude` of the balance model above 0.9 N: the voltage saturates longer and the LQR loses the
  pendulum (or the cart reaches the end stops).
- Change a mass in the model (e.g. `Body2/m`) to see the controller's robustness on the bond graph.

## Files

| path | what |
| --- | --- |
| `design/realism.json` | the rig: every parameter with nominal, min, max, unit, group and description; shared with RL step R1 and the robust classical items |
| `design/lablib.py` | parameter set → design plant (`design_plant`), link lumping (`link_props`), quadlib twin with the DC motor (`LabPlant`, `twin_rig`), realistic setup (`setup`), firmware replica (`firmware`), belt check |
| `design/design.py` | the design, the robustness table, the largest push, the belt check; writes the library, the models and `design/design.json` |
| `design/finish.py`, `design/measured.json` | backend runs, comparison with the design, `expected.json` |
| `design/screen.py`, `design/screen_results.json` | the realism screen and its summary |
| `library/` | `DoubleCartLabCtrl` (firmware), `DoubleCartLabTraj` (tables), generated |
| `scenes/pendulum-double-cart-lab.sdf` | the 3D scene |
| `design/rlmodels.py`, `design/rl_ranges.json` | the RL plant and closed-loop models, the exposed globals and their ranges |
| `library/DoubleCartLabPolicy.jl` | the learned controller, generated by `rl/make_policy_block.py` |
| `library/DoubleCartLabRobustPolicy.jl`, `library/LabRealism.jl` | the R1 robust policy (generated by `rl/make_policy_block.py --robust`) and the realism forces of the plant |
| `design/robustness_test.json`, `design/robustness.py`, `design/robustness_results.json` | the shared robustness test, its harness and the results of every controller run on it |
| `design/robust_lin.py`, `design/robust_c1.py`, `design/robust_c1.json` | C1: the linear toolkit (loops, margins, LFT, μ bounds), the robust balance designs and their verification |
| `design/robust_c2.py`, `design/robust_c2.json` | C2: the multi-model swing-up plan and TVLQR |
| `design/robust_ctrl.py` | the harness controllers (C1 balance, C2 plan, C3 re-arm) |
| `design/robustmodels.py`, `library/DoubleCartLabRobustCtrl.jl`, `library/DoubleCartLabRobustTraj.jl` | the robust and recover models, their firmware and tables, the Python replica and their checks |
