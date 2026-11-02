# Robust classical control for the pendulum rigs

The classical controllers of the pendulum examples (cart and rotary, 2 to 4 links: `pendulum-*`, `quad-pendulum`) are
designed on one nominal model: a discrete LQR for balance, and an offline-optimised swing-up trajectory tracked by a
time-varying LQR (TVLQR). They are robust to small parameter errors, but a timed swing-up cannot recover once the
pendulum leaves its planned path (a failed catch, a push, a large parameter error). This plan makes the classical
design robust over the realistic parameter ranges, so it can be compared fairly with the learned controllers of
`plan/RL_PLAN.md`.

**Scope for now: the double-cart lab rig only** (`examples/pendulum-double-cart-lab`: 2 links of 0.35 m and about
0.25 / 0.20 kg, rail ±1.0 m, the motor, gearbox and belt of `pendulum-double-cart`). The question is whether the
workflow is viable: realistic ranges, then robust design, robustness test and comparison with RL. The RL work (`plan/RL_PLAN.md`) uses
the same rig. More links and the rotary rigs come later, if at all.

Parameter ranges and non-idealities: one shared set for the lab rig, used both by this plan and by RL step R1
(`examples/pendulum-double-cart-lab/design/realism.json`: masses, lengths, friction (viscous and Coulomb), motor and
belt constants, encoder quantisation and noise, loop delay), following the approach of the quad-pendulum phase B
realism screen (`examples/quad-pendulum/design/realism.json`, `quadlib.realistic_setup`).

Status and progress: the tracking table at the end. Update it in the same commit as the work.

## Work items

1. **Multi-model / robust balance controller.** One balance controller designed against the whole parameter box,
   with the delay and the sensor filter included. Candidates, compared on the same test:
   - an LQR on stacked models (minimising the summed or worst-case cost over the box corners and samples);
   - structured (fixed-order) H∞, with the firmware structure fixed in advance (state feedback plus estimator, or a
     low-order output feedback) and tuned by nonsmooth optimisation against all models at once;
   - μ-synthesis (D-K iteration), with the masses, lengths and friction as real parametric uncertainty in an LFT and
     the delay and unmodelled dynamics as a multiplicative weight;
   - Glover–McFarlane loop shaping (robust to coprime-factor uncertainty, well suited to unstable plants).

   The controller is discretised at the firmware rate (state space in a `@discrete` block, order reduced if needed).
   Verification: μ-analysis over the box (robust stability and robust performance margins), the closed-loop
   eigenvalues at the corners, the disk margins and the delay margin. The same μ-analysis also applies to the learned
   policies, linearised at the upright. A μ peak above 1 would be a quantitative infeasibility statement for robust
   balance with those sensors and that delay (useful later for the quad and rotary rigs).
2. **Worst-case swing-up plan.** The swing-up trajectory planned over the parameter range, not on the nominal model.
   Options are multi-model collocation (one feed-forward that brings every sampled model into the catch region), a
   min-max cost, or a plan with margins on the actuator and the travel, followed by a TVLQR designed against the
   same models.
3. **State-driven (energy-based) swing-up.** A swing-up that is driven by the pendulum's state, not by a clock, so it can
   recover from a failed catch or a push. For example, energy pumping (Åström–Furuta style, extended to several links
   with a mode or virtual-constraint scheme) that hands over to the balance gain inside its catch region, with
   re-arming after a drop.

Each item is evaluated with the same robustness test as the RL controllers: Monte Carlo over the parameter box and the
non-idealities, plus pushes. Success rate, catch time, peak actuator and travel are reported. The test is defined in
`examples/pendulum-double-cart-lab/design/robustness_test.json` (truth model `lablib.setup` with every effect, the
nominal draw plus 64 Monte Carlo draws, seeds 3000-3063; scenarios `swingup`, `balance_push` and the unscored
`knockdown_recover`); the harness `design/robustness.py` runs any controller on it and writes
`design/robustness_results.json`.

## Results (double-cart lab rig, 2026-11-02)

The details and the commands are in the example's README ("Robust classical controllers").

**Harness.** `design/robustness.py run --controller module:factory --name N [--opt k=v] [--scenarios ...]`. A
controller has `rate_hz`, `reset(seed=, start=)` and `step(sensors) -> volts`. The sensors are the joint and motor
encoder counts and the controller's own previous command; a controller may run at its own rate. An `.npz` numpy
MLP is accepted for the RL policies. The nominal firmware on this test:
- with the EKF: swingup 64/64, balance_push 64/64, knockdown 0/64;
- with filtered differences: 39/64, 39/64, 0/64.

**C1.** All the balance laws share the firmware structure u = -K [x̂; u(k-1); u(k-2)] on the 1 kHz EKF, designed
with the 2-sample delay, the armature lag and the estimator in the loop (`design/robust_c1.py`). The models are
256 box corners and 64 draws.

Verification:
- the eigenvalues of every model;
- the disk and delay margins;
- μ on an LFT, every uncertain parameter a real repeated scalar, plus a complex multiplicative drive weight
  1.1(1 - z⁻¹) + 0.03 for the delay, lag and unmodelled dynamics. Two bounds are computed: the complex upper bound
  on a grid, and the mixed D-G bound (LMI) of a 12-parameter LFT at 6 frequencies around the complex peaks.

| law | disk α nominal / worst | delay margin | μ RS complex / mixed | μ RP complex / mixed | swingup | balance_push | push peak V | tail V rms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nominal LQR | 0.61 / 0.57 | 6 samples | 0.86 / 0.27 | 1.42 / 0.96 | 64/64 | 64/64 | 21.3 V | 1.45 V |
| multi-model LQR | 0.78 / 0.57 | 32 | 1.06 / 0.50 | 1.81 / 1.13 | 64/64 | 64/64 | 16.1 V | 0.78 V |
| structured H∞ | 0.46 / 0.32 | 5 | 1.27 / 0.59 | 1.60 / 0.98 | 64/64 | 49/64 | 24 V | 1.82 V |
| μ (D-K, fixed structure) | 0.55 / 0.47 | 7 | 0.95 / 0.26 | 1.14 / 1.09 | 64/64 | 64/64 | 20.8 V | 1.26 V |
| Glover-McFarlane | 0.36 / 0.10 | 14 | 1.73 / 0.77 | 2.07 / 1.42 | 62/64 | 58/64 | 19.2 V | 0.91 V |
| Glover-McFarlane, tuned shaping | 0.40 / 0.26 | 5 | 1.25 / 0.37 | 6.13 / 6.12 | 64/64 | 64/64 | 24 V | 1.25 V |

Findings:
- **Feasible.** With the real structure, robust stability holds over the box for every law (mixed RS μ ≤ 0.77).
  The complex bound exceeds 1 for four laws only because it treats the parameters as complex. So there is no μ > 1
  infeasibility statement for balance with these sensors and this delay.
- **Robust performance.** RP μ (weights scaled to the nominal LQR) is near 1: 0.96 for the nominal LQR, 0.98 for H∞.
- **Best law: the multi-model LQR.** It has the lowest voltage noise and push voltage, and the largest disk and
  delay margins. It is the balance law of the robust firmware.
- **Structured H∞.** It minimises the linear worst case (0.69 against 1.0), but its low gains saturate after a lean
  plus push and fail 15/64.
- **Loop shaping.** γ_min ≥ 5.5 for every shaping tried, so coprime-factor robustness is poor for this plant.

**C3.** The state-driven recovery is in `design/robust_ctrl.py`, `mode=rearm`:
- Drop detection at 20°.
- A stopping-distance rail guard.
- Energy removal through the cart (a = -k_E P_x - centring), with the collocated PFL V = (m_all a + βv)/α.
- The hanging LQR below 3.8 J.
- Arming at the hanging rest: the TVLQR plan, shifted to the cart position and turn count, with the catch in the
  balance law's region.

With the multi-model LQR it passes 64/64 in all three scenarios:
- knockdown_recover: re-catch median 12.9 s, peak |x| 0.80 m, 24 V at the clamp only;
- swingup: catch median 2.6 s;
- balance_push: 16.1 V.

The timed nominal firmware fails all 64 knock-downs. Pure energy pumping to the upright, with the same PFL and the
region catch, never caught within 20 s: the energy goes into a whirl of link 2. That is why the swing-up stays the
planned TVLQR, which the state machine re-arms.

**C2.** `design/robust_c2.py`. The models are the nominal and the 16 corners of the link masses, the COM shifts,
the cart and rotor mass and the drive gain.
- **Open-loop min-max plan.** One feed-forward for the nominal (hard terminal) and 4 corners, with min-max terminal
  cost. It leaves the corners 1777 times a 2° lean from upright. One open-loop input cannot swing a double pendulum
  up over the box, so the robustness must come from the feedback, and this formulation was dropped.
- **Kept: `mm_tvlqr`.** The nominal plan with a multi-model TVLQR: a common gain from the summed one-step costs,
  each model with its own cost-to-go.
- **Kept: `margin`.** A plan inside 60 % of the supply and ±0.7 m, with the same TVLQR.
- **Results.** With ideal states, the nominal TVLQR already lands all 17 models within 0.17° at T_s (mm_tvlqr 0.17°,
  margin 0.20°). On the robustness test, both plans pass swingup 64/64 with the multi-model LQR balance, the same
  as the nominal plan: catch median 3.55 / 3.57 s, 18.1 / 18.6 V, 0.41 / 0.42 m.
- **Conclusion.** The parameter box does not stress the TVLQR swing-up. The swing-up's weak spot is a disturbance
  off the plan, which C3 handles.
- **C3 with these tables.** The robust firmware uses the `mm_tvlqr` tables; C3 with them passes all three
  scenarios 64/64.

**bgsim.** `design/robustmodels.py` writes `library/DoubleCartLabRobustCtrl.jl` (the firmware: observer, 2 ms
delay, C3 state machine) and `DoubleCartLabRobustTraj.jl` (tables at the published plan time). It also writes two
models:
- `pendulum-double-cart-lab-robust`: the timed swing-up, the multi-model LQR balance and the 0.45 N push. 20
  checks pass.
- `pendulum-double-cart-lab-recover`: a knock-down at 7 s and a re-catch at 12.6 s. 22 checks pass.

A Python replica of the block on the twin switches phase at the same ticks (within 1 ms). It agrees to 3e-4 m and
7e-4 rad on the robust run, and to 6e-3 m and 1.6e-2 rad over the 20 s recover run.

## Comparison

One table (double-cart lab rig) compares five controllers:
- the nominal classical design (today's examples);
- the robust classical design (items 1 to 3);
- pure RL;
- RL with an imitation warm start;
- the hybrid: an RL swing-up into the catch region, with the LQR balance.

### C5 result (2026-11-02)

The shared test (`design/robustness_test.json`, harness `design/robustness.py`, results in
`design/robustness_results.json`): truth model `lablib.setup` with every effect of `realism.json`, 64 Monte Carlo
draws (seeds 3000-3063). Pass: |x| < 0.95 m and both links within 2° of upright over the last 2 s (in brackets: within
5.7°, the RL step-0 criterion). Tail angle and tail V rms are medians over the passing draws; peak V and peak x are the
maxima over them; catch is the median catch time.

| controller | swing-up | balance + push | knockdown + recover | tail angle | tail V rms | peak V | peak x | design / training |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nominal, filtered differences | 39/64 (64) | 39/64 (63) | 0/64 | 0.57° | 10.5 V | 24 V | 0.41 m | today's firmware |
| nominal, EKF | 64/64 | 64/64 | 0/64 | 0.26° | 1.40 V | 21.3 V | 0.41 m | today's firmware |
| **robust classical**: C1 mm_lqr balance + C3 re-arm (EKF) | 64/64, catch 2.6 s | 64/64 | **64/64**, re-catch 12.9 s | 0.40° | **0.78 V** | 16.1 V (24 V in the knockdown) | 0.80 m (knockdown) | offline design, minutes |
| RL, imitation warm start + DR (`rl-imitation-dr`) | 64/64, catch 3.0 s | 64/64 | not trained (probe 0/64) | 0.77° | 5.2 V | 24 V | 0.44 m | 25 min imitation (+ 76 min PPO, no gain) |
| RL, pure + DR (`rl-pure-dr`) | 0/64 | 8/64 (24) | – | 1.82° | 2.2 V | 11.3 V | 0.57 m | 59 M steps, 61 min |
| hybrid: RL swing-up + LQR catch (`rl-hybrid-dr`) | 15/64, catch 1.7 s | 64/64 | – | 0.78° | 4.1 V | 24 V | 0.80 m | 67 M steps, 60 min (still rising) |

Other C1 balance laws on the same swing-up (balance + push): μ D-K 64/64 (1.26 V rms), GMF tuned 64/64 (riding 24 V,
0.57 m), GMF 58/64, structured H∞ 49/64 (saturates). C2 swing-up plans (mm_tvlqr, margin) 64/64, the same as the nominal
plan.

Findings:
- Robustness over the realistic parameter box is not what separates the controllers: the nominal EKF firmware, the
  robust classical design and the imitation-trained policy all pass every draw of the two scored scenarios. What
  separates them is the voltage chatter (the estimator), the margins (C1: delay margin 32 vs 6 samples) and recovery.
- The robust classical design is the best overall: the lowest chatter, the most headroom, and the only controller that
  recovers from a knockdown (the C3 state machine re-arms the planned swing-up).
- The learned policy matches the pass rate but is about 4x noisier than the EKF designs, because it sees 4 encoder
  samples and imitates an expert labelled on the same short-window estimate; PPO did not improve it. Next step for RL
  (R2 candidate): the EKF estimate (or a recurrent policy) as the observation, and an expert for re-swing-ups.
- Pure RL and the hybrid are not competitive within a 1 h training budget.

## Progress tracking

| # | item | rig | status | notes |
| --- | --- | --- | --- | --- |
| C0 | lab rig: the example, its classical redesign, `design/realism.json` and a twin realism screen | double-cart lab rig | done | `examples/pendulum-double-cart-lab`: links 0.248 / 0.200 kg (COM 0.229 / 0.176 m), unstable poles 4.55 and 8.92 /s, swing-up energy 3.2 J. Design T_s 3.0 s: catch 4.0 s, peak 15.0 V (63 %), 6.0 A, travel 0.39 m; largest push 0.90 N (0.87 N with 2 ms delay); robust to masses ±5 %, lengths ±1 %, friction ×3, 1–2 ms delay, quantised encoders. Screen (`design/screen_results.json`): feasible with margin with an EKF (48/48 Monte Carlo); filtered differences marginal (36/48); joint Coulomb budget ~1e-3 N m (joint 2), ~5e-3 N m (joint 1). |
| C1 | robust balance: multi-model LQR, structured H∞, μ-synthesis, loop shaping; μ-analysis of all balance controllers | double-cart lab rig | done | 2026-11-02. `design/robust_lin.py`, `design/robust_c1.py`, `design/robust_c1.json`; harness `design/robustness.py`. Mixed μ: RS ≤ 0.77 for every law (robust stability over the box holds; the complex bound overstates by up to 3x); RP 0.96 (nominal LQR) to 1.42 (GMF). Best on the test: the multi-model LQR (64/64 swingup and balance_push, tail 0.78 V rms against 1.45 V, push 16.1 V against 21.3 V, disk α 0.78, delay margin 32 samples); H∞ 49/64 (saturates), GMF 58/64. See "Results". |
| C2 | worst-case swing-up plan | double-cart lab rig | done | 2026-11-02. `design/robust_c2.py`, `design/robust_c2.json`. The open-loop min-max plan does not work (with 4 corners the best plan ends 1777 leans off upright): the robustness has to come from the feedback. Kept: the multi-model TVLQR on the nominal plan (`mm_tvlqr`) and a 60 % / 0.7 m margin plan; both 64/64 on swingup, like the nominal plan (the box does not stress the TVLQR). `mm_tvlqr` is in the bgsim robust firmware. |
| C3 | energy-based swing-up with re-arm | double-cart lab rig | done | 2026-11-02. `design/robust_ctrl.py` (`mode=rearm`): energy removal through the cart (collocated PFL), rail guard, hanging LQR, re-armed TVLQR from the hanging rest, region catch. knockdown_recover 64/64 (nominal firmware 0/64), re-catch median 12.9 s, peak 0.80 m; swingup and balance_push 64/64. Pure energy pumping to the upright never caught (link 2 whirls). bgsim: `pendulum-double-cart-lab-robust` and `-recover` (`design/robustmodels.py`, `library/DoubleCartLabRobust{Ctrl,Traj}.jl`), matching a Python replica on the twin. |
| C4 | items 1 to 3 on the quad cart, then the rotary rigs | quad cart, rotary | deferred | only after the 2-link workflow proves viable |
| C5 | comparison table: classical vs robust classical vs RL vs hybrid | double-cart lab rig | done | "C5 result" in the Comparison section; robust classical best (lowest chatter, only knockdown recovery); RL imitation equally robust, 4x chatter |
