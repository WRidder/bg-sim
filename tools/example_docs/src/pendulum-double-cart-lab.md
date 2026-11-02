@@ figures @project
{
  "rig": {"kind": "svg", "svg": "rig"},
  "scene": {"kind": "scene", "model": "pendulum-double-cart-lab", "t": 12.5},
  "swingup": {
    "kind": "plot", "model": "pendulum-double-cart-lab", "xlim": [0.8, 4.6],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Ctrl/th1", "label": "θ1", "scale": 57.29577951308232}, {"signal": "Ctrl/th2", "label": "θ2", "scale": 57.29577951308232}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}, {"signal": "Traj/xs[1]", "label": "planned x", "style": "--"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "applied"}, {"signal": "Traj/ff", "label": "feed-forward", "style": "--"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ svg @project rig
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 400" font-family="sans-serif" font-size="12">
<rect width="760" height="400" fill="#ffffff"/>
<line x1="95" y1="236" x2="95" y2="290" stroke="#888" stroke-dasharray="4 3"/>
<line x1="665" y1="236" x2="665" y2="290" stroke="#888" stroke-dasharray="4 3"/>
<text x="665" y="230" text-anchor="middle" fill="#666" font-size="11">test limit ±0.95 m</text>
<line x1="140" y1="268" x2="140" y2="290" stroke="#2ca02c" stroke-width="3"/>
<line x1="620" y1="268" x2="620" y2="290" stroke="#2ca02c" stroke-width="3"/>
<text x="620" y="262" text-anchor="middle" fill="#2ca02c" font-size="11">swing-up plan ±0.8 m</text>
<line x1="80" y1="290" x2="680" y2="290" stroke="#555" stroke-width="4"/>
<rect x="70" y="272" width="10" height="26" fill="#d62728"/>
<rect x="680" y="272" width="10" height="26" fill="#d62728"/>
<text x="694" y="284" fill="#d62728" font-size="11">rubber</text>
<text x="694" y="297" fill="#d62728" font-size="11">end stops</text>
<text x="80" y="312" text-anchor="middle" fill="#333" font-size="11">−1.0 m</text>
<text x="140" y="312" text-anchor="middle" fill="#333" font-size="11">−0.8</text>
<text x="380" y="312" text-anchor="middle" fill="#333" font-size="11">0</text>
<text x="620" y="312" text-anchor="middle" fill="#333" font-size="11">+0.8</text>
<text x="680" y="312" text-anchor="middle" fill="#333" font-size="11">+1.0 m</text>
<rect x="58" y="325" width="644" height="14" rx="7" fill="none" stroke="#444" stroke-width="2"/>
<circle cx="66" cy="332" r="9" fill="#eeeeee" stroke="#444" stroke-width="2"/>
<circle cx="694" cy="332" r="9" fill="#eeeeee" stroke="#444" stroke-width="2"/>
<line x1="380" y1="288" x2="380" y2="325" stroke="#444" stroke-width="2"/>
<text x="560" y="355" text-anchor="middle" fill="#444" font-size="11">toothed belt 4·10⁵ N/m, idler</text>
<rect x="20" y="350" width="74" height="34" rx="4" fill="#dddddd" stroke="#444"/>
<text x="57" y="371" text-anchor="middle" fill="#222">motor</text>
<line x1="66" y1="341" x2="66" y2="350" stroke="#444" stroke-width="3"/>
<text x="104" y="364" fill="#222" font-size="11">24 V brushed DC motor, 3:1 gearbox, 16 mm pulley (3.78 N/V, stall 90 N)</text>
<text x="104" y="379" fill="#222" font-size="11">voltage-mode drive, 1 kHz firmware, 1000-line motor encoder</text>
<rect x="345" y="262" width="70" height="26" rx="3" fill="#9ecae1" stroke="#333"/>
<text x="424" y="282" fill="#222" font-size="11">cart 0.80 kg</text>
<line x1="380" y1="262" x2="394.6" y2="158" stroke="#999999" stroke-width="7" stroke-linecap="round"/>
<rect x="387.6" y="151" width="14" height="14" fill="#555"/>
<line x1="394.6" y1="158" x2="385.4" y2="53.4" stroke="#b0b0b0" stroke-width="7" stroke-linecap="round"/>
<circle cx="385.4" cy="53.4" r="6" fill="#555"/>
<circle cx="380" cy="262" r="5" fill="#333"/>
<circle cx="394.6" cy="158" r="4" fill="#ffffff" stroke="#333" stroke-width="2"/>
<text x="372" y="214" text-anchor="end" fill="#222">link 1: 0.35 m Al tube 20 × 2 mm,</text>
<text x="372" y="229" text-anchor="end" fill="#222">bearing head at the tip: 0.248 kg, COM 0.229 m</text>
<text x="380" y="104" text-anchor="end" fill="#222">link 2: 0.35 m tube, tip cap:</text>
<text x="380" y="119" text-anchor="end" fill="#222">0.200 kg, COM 0.176 m</text>
<text x="412" y="174" fill="#222" font-size="11">joint 2: 14-bit encoder</text>
<text x="392" y="252" fill="#222" font-size="11">joint 1: 14-bit encoder</text>
<line x1="450" y1="53.4" x2="398" y2="53.4" stroke="#d95f02" stroke-width="2"/>
<polygon points="394,53.4 404,48.4 404,58.4" fill="#d95f02"/>
<text x="456" y="57.4" fill="#d95f02">tip push F</text>
</svg>
@@ page @project rig - | The double-cart lab rig
# The double-cart lab rig

A cart on a **±1.0 m** rail carries a double pendulum of two **0.35 m** links, built the way a lab would build
them: aluminium tubes with clamp hubs, a bearing head at the tip of link 1, 14-bit encoders and a cable. The
cart runs on a toothed belt from a 24 V DC motor through a 3:1 gearbox and a 16 mm pulley, with a
voltage-mode drive and a 1 kHz firmware. The motor, gearbox, belt and cart are those of example
`pendulum-double-cart`. The rig is the shared platform of the robust classical work
(`plan/ROBUST_CLASSICAL_PLAN.md`) and the RL work (`plan/RL_PLAN.md`). Every value comes from
`design/realism.json`, which also holds the ranges the robustness studies draw from.

![The rig: cart, rail with end stops, the two links, belt drive and motor|760](@fig:rig)

| part | nominal (realism.json) |
| --- | --- |
| cart | 0.80 kg carriage (belt clamp, joint-1 bearing block, encoder board), carriage friction 0.5 + 0.2 N s/m |
| rail | ±1.0 m to rubber end stops (2·10⁴ N/m, 200 N s/m) |
| link 1 | 0.35 m: tube 107 g, hub, magnet, head 105 g, encoder board, cable: **0.248 kg**, COM 0.229 m (65 % of L), $J = 4.68 \cdot 10^{-3}$ kg m² |
| link 2 | 0.35 m: tube 107 g, hub 45 g, magnet, tip cap 47 g: **0.200 kg**, COM 0.176 m, $J = 3.96 \cdot 10^{-3}$ kg m² |
| motor and drive | 24 V, $R = 1.5\ \Omega$, $L = 0.5$ mH, $k_t = 0.0302$ N m/A; 3:1, 16 mm pulley, belt $4 \cdot 10^5$ N/m: 3.78 N/V, stall 90 N (16 A), effective cart 1.29 kg |
| sensors and loop | 14-bit joint encoders (0.03° rms noise), 1000-line motor encoder (8.4 µm at the cart), 1 kHz loop with a 2 ms delay |
| upright | unstable poles **4.55 and 8.92 /s**; hanging to upright takes **3.18 J** |

The bond graph is the planar multibond model of `pendulum-double-cart` (`Prismatic2D` rail, two
`Revolute2DCompliant` joints, `RigidBody2D` cart and links, `ElectricDrive` → `Gearbox` → `RackAndPinion` →
belt `SpringDamper`, `ExternalWrenchPlanar` tip push), plus the carriage friction `RailFriction` and the
`EndStops` at ±1.0 m. `design/lablib.py` builds the design model, the bond graph, the Python twin and the
firmware replica for any parameter set.

![3D view: the cart on the 2 m rail between the red rubber stops; the green posts mark the ±0.8 m swing-up plan|500](@fig:scene)

## The models

Every model has a **Dashboard** with the same layout (readouts, the link angles in degrees, the cart with the
end stops, voltage and current, the controller's phase, sliders for the next run) and its own docs page.

| model | what it shows |
| --- | --- |
| [pendulum-double-cart-lab](model:pendulum-double-cart-lab) | the nominal firmware: hanging until 1 s, the planned swing-up, the LQR catch at 4.0 s, a 0.45 N push at 7.5 s |
| [-balance](model:pendulum-double-cart-lab-balance) | balance only: a 2° lean and a large 0.70 N push at 2 s |
| [-free](model:pendulum-double-cart-lab-free) | no control: the free swing, checked against the twin |
| [-plant](model:pendulum-double-cart-lab-plant) | the plant alone (voltage and push in, encoders out): the source of the FMU for RL |
| [-rl](model:pendulum-double-cart-lab-rl) | a learned controller (R0.7) on the ideal plant, the nominal scenario |
| [-rl-robust](model:pendulum-double-cart-lab-rl-robust) | the robust learned controller (R1) on the realistic plant with noise and delay |
| [-robust](model:pendulum-double-cart-lab-robust) | the robust classical firmware (C1 balance, C2 swing-up) in the nominal scenario |
| [-recover](model:pendulum-double-cart-lab-recover) | the state-driven firmware (C3): a knock-down at 7 s, the re-armed swing-up and the re-catch |

Read on: [design and margins](page:design), [realism and the robustness test](page:realism),
[robust classical control](page:robust), [learned controllers](page:learned) and
[the comparison](page:comparison). The example's `README.md` has every command and table.
@@ page @project design rig | Design and margins
# Design and margins

The nominal controller of [pendulum-double-cart-lab](model:pendulum-double-cart-lab) and
[-balance](model:pendulum-double-cart-lab-balance). `design/design.py` reuses the design code of
`pendulum-double-cart`: the Lagrangian design model (the same equations as the twin, checked to 1e-15),
Hermite-Simpson collocation with IPOPT, the continuous TVLQR and the discrete LQR.

1. **Swing-up plan with margins.** Hanging to upright at rest in $T_s = 3.0$ s, minimum $\int V^2 dt$, with
   the voltage bounded to **16.8 V (70 % of 24 V)** and the cart to **±0.8 m**. The plan needs 14.8 V and
   ±0.39 m: neither bound is active (a 2.4 s plan hits both).
2. **TVLQR** along the plan and the **discrete LQR** (1 ms, ZOH) at the upright, both with
   $Q = \mathrm{diag}(300, 400, 400, 10, 8, 8)$, $R = 0.3\ \mathrm{V}^{-2}$; largest gain 329.
3. **Firmware** (`library/DoubleCartLabCtrl.jl`, tables in `DoubleCartLabTraj.jl`): phase 0 holds 0 V until
   1 s, phase 1 is the swing-up (feed-forward plus TVLQR), phase 2 the LQR from the timed catch at 4.0 s.

![Swing-up: the bond graph against the plan|900](@fig:swingup)

| margin | value |
| --- | --- |
| peak voltage in the swing-up | **15.0 V** of 24 V (the plan bound 16.8 V is never reached) |
| peak current | 5.3 A in the swing-up, 6.0 A over the run (stall 16 A) |
| peak travel | **0.387 m** of the ±0.8 m plan and the ±1.0 m rail |
| largest 40 ms tip push recovered (from upright) | **0.90 N** (0.87 N with 2 ms delay): 27.6° on link 1, 0.34 m |
| belt mode in closed loop (0 to 2 ms delay) | 177 Hz, ζ 0.07 to 0.13: stable (softest belt 124 Hz) |

**Robustness on the twin** (the firmware replica). Every case catches, balances and recovers from the push:
link masses ±5 %, lengths ±1 %, joint and carriage friction ×3, cart mass +10 %, 1 and 2 ms delay, quantised
encoders, and all of them at once (16.6 V, 0.385 m, 16.9° after the 0.70 N push). The bond graph matches the
design closed loop to 1.5e-3 rad and 0.3 mm in the swing-up and to 0.01° after the push.
@@ page @project realism rig | Realism and the robustness test
# Realism and the robustness test

**`design/realism.json`** is the one definition of the rig: every parameter with nominal, min, max, unit and
description. `lablib.setup` turns a draw into the truth twin (RK4, 8 substeps per 1 ms sample) with every
effect switched on.

| group | what varies (min to max) |
| --- | --- |
| mass | link tubes, hubs, head and tip cap ±5 to 10 %, encoder parts, cable 3 to 12 g/m, COM shift ±2 % of L, lengths ±2 mm, cart 0.76 to 0.84 kg |
| joint friction | viscous 1 to 6·10⁻⁴ N m s/rad, Coulomb 1 to 5·10⁻⁴ N m per joint |
| carriage and motor | viscous 0.2 to 1 N s/m, Coulomb 0.5 to 2 N (carriage), 1 to 4 mN m (motor) |
| cable | joint-1 spring up to 3·10⁻⁴ N m/rad, drag, a base spring up to 0.5 N/m |
| drive | R 1.4 to 1.8 Ω, L 0.4 to 0.6 mH, $k_t$ ±5 %, belt 2 to 6·10⁵ N/m |
| ripple and cogging | commutation ripple up to 4 % of u, cogging up to 0.5 N (14 per motor turn) |
| sensors and loop | 14-bit joint encoders, noise 0.01 to 0.08° rms; loop delay 1 or 2 samples; the armature lag L/R |

**The realism screen (C0, `design/screen.py`).** The unchanged nominal firmware against the twin, one effect at
a time and 48 Monte Carlo draws (`design/screen_results.json`). **Verdict: feasible with margin**, provided the
rates come from an **EKF** on the nominal model: 48/48 draws swing up and balance (tail median 0.22°, worst
18.2 V, 0.39 m). With filtered differences of the 14-bit encoders only 36/48 pass: the encoder noise makes the
voltage chatter to the 24 V limit and a quarter of the draws limit-cycle at 2 to 4°. The joint Coulomb friction
budget is about **1·10⁻³ N m on joint 2** and **5·10⁻³ N m on joint 1**, so ordinary ball bearings do.

**The shared robustness test** (`design/robustness_test.json`, harness `design/robustness.py`, results in
`design/robustness_results.json`). Every controller, classical or learned, runs the same draws on the same
truth twin. It sees only the sensors (joint and motor encoder counts, its own previous command) and returns
the motor voltage.

| | definition |
| --- | --- |
| draws | the nominal set plus 64 Monte Carlo draws, uniform over realism.json (seeds 3000 to 3063) |
| `swingup` | hanging at rest (2° seeded noise), the controller's swing-up, 10 s |
| `balance_push` | upright with a 2° lean, a 0.45 N / 40 ms tip push at 2 s, 7 s |
| `knockdown_recover` (unscored) | swing-up, then a 1.5 N / 100 ms push at 7 s that knocks it down; the controller must catch it again by 20 s |
| pass | the run finishes, **\|x\| < 0.95 m** throughout, both links within **2°** of upright over the last 2 s |

The dashboards draw this ±0.95 m limit next to the ±1.0 m end stops.
@@ page @project robust rig | Robust classical control
# Robust classical control

Items C1 to C3 of `plan/ROBUST_CLASSICAL_PLAN.md`, run in bgsim by
[-robust](model:pendulum-double-cart-lab-robust) and [-recover](model:pendulum-double-cart-lab-recover).

**C1, robust balance** (`design/robust_c1.py`). Every law has the firmware structure
$u = -K\,[\hat x;\ u_{k-1};\ u_{k-2}]$ (8 gains) on the 1 kHz EKF and is designed with the 2-sample delay, the
armature lag and the observer in the loop. Four designs over 256 box corners and 64 draws: the multi-model
LQR (mean H2), structured H∞, μ-synthesis by D-K iteration, and Glover-McFarlane loop shaping. Verification:
the eigenvalues of 320 models, disk and delay margins, and μ on an LFT of 12 real parameters plus a complex drive
weight for the delay, lag and unmodelled dynamics.

| balance law | disk margin α (nominal / worst) | delay margin | μ RS mixed | balance_push | push peak V | tail V rms |
| --- | --- | --- | --- | --- | --- | --- |
| nominal LQR | 0.61 / 0.57 | 6 samples | 0.27 | 64/64 | 21.3 V | 1.45 V |
| **multi-model LQR** | **0.78** / 0.57 | **32** | 0.50 | 64/64 | **16.1 V** | **0.78 V** |
| structured H∞ | 0.46 / 0.32 | 5 | 0.59 | 49/64 | 24 V | 1.82 V |
| μ (D-K) | 0.55 / 0.47 | 7 | 0.26 | 64/64 | 20.8 V | 1.26 V |
| Glover-McFarlane | 0.36 / 0.10 | 14 | 0.77 | 58/64 | 19.2 V | 0.91 V |

- **Robust stability holds for every law**: the mixed μ bound stays at or below 0.77. The complex bound
  (above 1 for four laws) overstates it, up to 3 times.
- **The multi-model LQR is the best on the test**: half the voltage noise, 24 % less voltage for the push, the
  largest disk margin and a 32-sample delay margin. It is the balance law of the robust firmware.
- Structured H∞ has the best linear worst case, but its low gains saturate after the lean plus push.

**C2, swing-up for the box** (`design/robust_c2.py`). One open-loop plan cannot swing the double pendulum up
over the parameter box (the min-max plan ends far from upright), so the robustness has to come from the
feedback. The kept plan is the nominal one with a **multi-model TVLQR** against 17 models (`mm_tvlqr`); it and a
60 % / ±0.7 m margin plan pass `swingup` 64/64, as the nominal plan does. The box does not stress the TVLQR.

**C3, state-driven recovery** (`design/robust_ctrl.py`, `mode=rearm`). A timed swing-up cannot recover from a
knock-down (the nominal firmware: 0/64). The state machine of the robust firmware can:

1. **Drop**: a link more than 20° from upright switches balance (phase 2) to settle (phase 3).
2. **Settle**: a rail guard brakes when the stopping point passes 0.8 m; the links' energy is removed through
   the cart ($a = -k_E P_x$ minus centring, applied by the collocated partial feedback linearisation); below
   3.8 J a hanging LQR settles links and cart.
3. **Re-arm**: 50 ms at the hanging rest arm the TVLQR swing-up again (phase 1), shifted to the cart position
   and the links' turn count; the catch is inside the balance law's region $z^T P z <$ tol.

| C3 with the multi-model LQR (`c3-rearm-mm_lqr`) | success | catch (median / max) | peak V | peak x |
| --- | --- | --- | --- | --- |
| swingup | 64/64 | 2.61 / 3.22 s | 18.1 V | 0.40 m |
| balance_push | 64/64 | 2.93 / 2.97 s | 16.1 V | 0.23 m |
| knockdown_recover | **64/64** | 12.94 / 13.64 s | 24 V | **0.80 m** |

Pure energy pumping to the upright never caught within 20 s (the energy goes into a whirl of link 2), so the
swing-up itself stays the planned TVLQR, re-armed by the state machine.

**In bgsim** the firmware is one 1 kHz `@discrete` block, `library/DoubleCartLabRobustCtrl.jl` (the mm_lqr
gains, the steady-state EKF gain, the 2 ms delay, the C3 state machine with `rearm = 1`), with the `mm_tvlqr`
tables in `DoubleCartLabRobustTraj.jl`. A Python replica on the twin switches phase at the same ticks (within
1 ms).
@@ page @project learned rig | Learned controllers
# Learned controllers

Steps 0 and 1 of `plan/RL_PLAN.md` (items R0.7 and R1): neural-network controllers trained on an FMU of this
rig and brought back as ordinary `@discrete` blocks.

**Pipeline.**

1. [-plant](model:pendulum-double-cart-lab-plant) is exported as an FMU (`rl/export_plant.jl --rig=lab`:
   fixed Rodas4P at 1 ms, 5.5 µs per step) with the realism parameters as exposed globals.
2. A batched C environment steps thousands of FMU instances; rsl_rl PPO trains the actor ([64, 64] tanh,
   200 Hz) and a critic that sees the true state.
3. `rl/make_policy_block.py` writes the trained actor as a project block that repeats the environment's
   observation pipeline. bgsim and the environment agree to round-off (R0.7: 2e-6 m, 2e-6 rad).

**R0.7, ideal plant** ([-rl](model:pendulum-double-cart-lab-rl)). Pure RL from scratch did not learn the
swing-up reliably in its timebox. What works is an **imitation warm start**: behaviour cloning of the rig's
own TVLQR swing-up and LQR, then PPO with a cloning anchor (4 minutes). One network swings up, balances and
takes the push about as well as the classical firmware (10.9° against 10.7°, 15.2 V against 15.0 V).

**R1, robustness** ([-rl-robust](model:pendulum-double-cart-lab-rl-robust)). Every training episode draws a
full `realism.json` parameter set, the 1 to 2 ms loop delay, encoder noise and random tip pushes. The actor
sees only the encoder history (the last 4 differences of the measured positions and its last 4 actions, 21
inputs); the critic sees the true state and the draw. Warm start: behaviour cloning plus 2 DAgger rounds
(25 min), then 310 PPO iterations (51 min).

**Why the chatter.** The robust policy passes every draw of the test (64/64 swing-up, 64/64 balance + push),
but with about **5.2 V rms** of voltage chatter and noise spikes to the 24 V clamp, where the EKF firmware needs
1.4 V rms. The chatter comes from the expert's labels: the expert labels from a 5-sample least-squares fit of
the same noisy encoder history, and that expert alone gives the same 5.3 V rms (0.5 V on the true state).
Labels from the true state gave a student that balanced in a 3° limit cycle. PPO, also with an action-rate
penalty, did not reduce the chatter. The next step is an observer (the EKF) in front of the network.

| R1 row (shared test) | swing-up | balance + push | tail V rms | training |
| --- | --- | --- | --- | --- |
| imitation + DR (`rl-imitation-dr`, shipped) | 64/64 | 64/64 | 5.2 V | 25 min imitation + 51 min PPO |
| the same before PPO (`rl-bc-dr`) | 64/64 | 64/64 | 5.2 V | 25 min |
| pure RL + DR (`rl-pure-dr`) | 0/64 | 8/64 | 2.2 V | 59 M steps, 61 min |
| hybrid: RL swing-up + LQR catch (`rl-hybrid-dr`) | 15/64 | 64/64 | 4.1 V | 67 M steps, 60 min (still rising) |

Knock-down recovery was not trained: the environment has no expert for a re-swing from an arbitrary state.
@@ page @project comparison rig | Comparison
# Comparison

Item C5 of `plan/ROBUST_CLASSICAL_PLAN.md`: every controller on the [shared robustness test](page:realism)
(64 Monte Carlo draws over `realism.json`; pass: |x| < 0.95 m and both links within 2° over the last 2 s; in
brackets the passes within 5.7°). Tail angle and tail V rms are medians over the passing draws, peak V and x
their maxima, catch the median catch time.

| controller | swing-up | balance + push | knockdown + recover | tail angle | tail V rms | peak V | peak x | design / training |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nominal, filtered differences | 39/64 (64) | 39/64 (63) | 0/64 | 0.57° | 10.5 V | 24 V | 0.41 m | today's firmware |
| nominal, EKF | 64/64 | 64/64 | 0/64 | 0.26° | 1.40 V | 21.3 V | 0.41 m | today's firmware |
| **robust classical**: C1 mm_lqr + C3 re-arm | 64/64, catch 2.6 s | 64/64 | **64/64**, re-catch 12.9 s | 0.40° | **0.78 V** | 16.1 V (24 V in the knock-down) | 0.80 m (knock-down) | offline design, minutes |
| RL, imitation + DR | 64/64, catch 3.0 s | 64/64 | not trained (probe 0/64) | 0.77° | 5.2 V | 24 V | 0.44 m | 25 min imitation (+ 76 min PPO, no gain) |
| RL, pure + DR | 0/64 | 8/64 (24) | – | 1.82° | 2.2 V | 11.3 V | 0.57 m | 59 M steps, 61 min |
| hybrid: RL swing-up + LQR catch | 15/64, catch 1.7 s | 64/64 | – | 0.78° | 4.1 V | 24 V | 0.80 m | 67 M steps, 60 min |

Findings:

- **Robustness over the parameter box does not separate the controllers.** The nominal EKF firmware, the
  robust classical design and the imitation-trained policy pass every draw of the two scored scenarios. What
  separates them is the voltage chatter (the estimator), the margins (C1: a delay margin of 32 against 6
  samples) and the recovery.
- **The robust classical design is the best overall**: the lowest chatter, the most headroom, and the only
  controller that recovers from a knock-down.
- **The learned policy matches the pass rate but is about 4 times noisier**: it sees 4 encoder samples and
  imitates an expert labelled on the same short-window estimate.
- **Pure RL and the hybrid are not competitive** within a 1 h training budget.

In bgsim: [-robust](model:pendulum-double-cart-lab-robust) and [-recover](model:pendulum-double-cart-lab-recover)
run the robust classical firmware, [-rl-robust](model:pendulum-double-cart-lab-rl-robust) the R1 policy.
@@ figures pendulum-double-cart-lab
{
  "diagram": {"kind": "diagram", "model": "pendulum-double-cart-lab"},
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab", "xlim": [0, 12.5],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "hlines": [{"y": 0.8, "label": "plan ±0.8 m"}, {"y": -0.8}], "ylim": [-1.05, 1.05], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "u"}], "hlines": [{"y": 16.8, "label": "plan ±16.8 V (70 %)"}, {"y": -16.8}], "ylim": [-25, 25], "legend": true, "legend_loc": "right"},
      {"ylabel": "current [A]", "series": [{"signal": "Motor/isense/y", "label": "i"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "phase", "series": [{"signal": "Ctrl/phase", "label": "0 hold, 1 swing-up, 2 balance"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab overview - | What you're looking at
# Swing-up, balance and a push (nominal firmware)

**Scenario.** The links hang at rest with 0 V until **1 s**. Then the planned swing-up runs for 3.0 s, the LQR
catches the pendulum at **4.0 s** and balances it, a **0.45 N, 40 ms** push on the tip
([PushPulse](block:PushPulse)) hits at **7.5 s**, and the run ends at **12.5 s** after 3 s of quiet balance.

**Controller.** [Ctrl](block:Ctrl) is the nominal 1 kHz firmware `library/DoubleCartLabCtrl.jl`: phase 0
hold, phase 1 the swing-up (feed-forward plus time-varying LQR from the tables of [Traj](block:Traj),
`library/DoubleCartLabTraj.jl`), phase 2 the discrete LQR. It sees the ideal joint and cart states, with no
delay. The design is on the project page [design and margins](project:design).

![The model canvas: the bond graph, the firmware and the dashboard monitor|900](@fig:diagram)

**Dashboard.** The phase, the peak cart travel, both link angles from upright in degrees (green within 2°),
voltage and current; plots of the angles, the cart with the end stops (±1.0 m) and the test limit (±0.95 m),
voltage and current, and the phase with the tip push. The sliders set the push, its time and the mass of link 2
for the next run. [Mon](block:Mon) (`DoubleCartLabMonitor`) computes the degrees and the peak travel. **3D
view:** the cart on the 2 m rail between the red rubber stops; the green posts mark the ±0.8 m plan.

![Link angles, cart, voltage, current and phase over the run|900](@fig:run)

**Expected outcome** (checked by `expected.json`):

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| at rest before 1 s | no motion, 0 V | |
| upright for good (inside 2°) / catch | 2.55 s after the start / 4.00 s | 2.55 s / 4.00 s |
| upright band before the push | 0.0023° (cart 0.04 mm) | 0.0017° |
| push: link 1 / link 2, cart | 10.71° / 3.98°, 0.173 m | 10.70° / 3.98° |
| back inside 0.5° after the push | 2.12 s | 2.12 s |
| peak voltage, current, travel | **15.01 V** (plan bound 16.8 V), 5.97 A, **0.387 m** (plan ±0.8 m) | 15.02 V, 5.98 A, 0.387 m |

The end stops are never touched. Raise the push above about 0.9 N to see the limit of the design (see
[-balance](model:pendulum-double-cart-lab-balance)). The rig itself: [the double-cart lab rig](project:rig).
@@ figures pendulum-double-cart-lab-balance
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-balance", "xlim": [0, 6],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "u"}], "hlines": [{"y": 24, "label": "supply ±24 V"}, {"y": -24}], "legend": true, "legend_loc": "right"},
      {"ylabel": "current [A]", "series": [{"signal": "Motor/isense/y", "label": "i"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-balance overview - | What you're looking at
# Balance and a large push (nominal firmware)

**Scenario.** Both links start leaning **2°** from upright, the cart at rest at the centre. The firmware is in
balance from the first tick. At **2 s** a **0.70 N, 40 ms** push on the tip ([PushPulse](block:PushPulse))
tests the recovery: 78 % of the largest push the design recovers (0.90 N). The run ends at **6 s**.

**Controller.** [Ctrl](block:Ctrl), the nominal firmware `library/DoubleCartLabCtrl.jl` with `t_on` = −10 s,
so the discrete LQR runs from the start (phase 2). See [design and margins](project:design).

**Dashboard.** The phase (2 throughout), the peak cart travel, the link angles in degrees, voltage and current,
with the plots of the angles, the cart with the end stops and the test limit, voltage and current, and the
push. The sliders set the push, its time and the mass of link 2. **3D view:** the links lean, are caught, then
swing out after the push.

![Link angles, cart, voltage and current|900](@fig:run)

**Expected outcome:**

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| the 2° lean, inside 0.5° before the push | 0.28° | |
| push: link 1 / link 2 | 17.35° / 5.79° | 17.32° / 5.80° |
| back inside 0.5° after the push | 2.29 s | 2.29 s |
| peak voltage, current, travel | 20.7 V, 11.0 A, 0.241 m | 20.6 V, 11.0 A, 0.242 m |
| at the end (6 s) | 0.10°, cart 2 mm | |

**Try:** raise the push slider above **0.9 N**. The voltage saturates longer and the LQR loses the pendulum (or
the cart reaches the end stops). With 2 ms of delay the limit is 0.87 N.
@@ figures pendulum-double-cart-lab-free
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-free", "xlim": [0, 2],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Joint1/qout", "label": "q1"}, {"signal": "Joint2/qout", "label": "q2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-free overview - | What you're looking at
# Free swing: the twin check

**Scenario.** No control: the motor is shorted (the firmware [Ctrl](block:Ctrl) has `t_on` = 10⁹ s and never
starts, phase 0). The plant is released from rest at θ = (−2.2, −1.2) rad from upright (−126° and −69°),
the cart at x = 0.05 m, and swings for **2 s**.

**What it checks.** `expected.json` compares the cart position and the joint angles every 0.25 s with the design
ODE, which is the Python twin of `design/lablib.py`. The bond graph agrees to **4.3e-4 rad** on the joints and
**4.3e-5 m** on the cart, so the design model, the twin of the robustness studies and the bond graph are the
same plant. The swing includes the viscous joint, cable and carriage drag and the belt; the shorted motor's
back-EMF drags the cart.

**Dashboard.** The same layout as the other models: the phase (0), the peak cart travel, the link angles in
degrees, voltage (0) and the current that the back-EMF drives through the shorted winding; the fourth plot
shows the joint encoder angles that the check compares. Sliders: the mass of link 2 and the joint-2 friction
(the check then fails, of course). **3D view:** the double pendulum swinging freely.

![Free swing: joint angles and cart|900](@fig:run)

The rig and its models: [the double-cart lab rig](project:rig).
@@ figures pendulum-double-cart-lab-plant
{
  "diagram": {"kind": "diagram", "model": "pendulum-double-cart-lab-plant"},
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-plant", "xlim": [0, 5], "overrides": {"V/value": 2.0},
    "rows": [
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "hlines": [{"y": 1.0, "label": "end stop 1.0 m"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Joint1/qout", "label": "q1"}, {"signal": "Joint2/qout", "label": "q2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "current [A]", "series": [{"signal": "Motor/isense/y", "label": "i"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "realism force", "series": [{"signal": "Realism/F", "label": "cart [N]"}, {"signal": "Realism/tau1", "label": "joint 1 [N m]"}, {"signal": "Realism/tau2", "label": "joint 2 [N m]"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-plant overview - | What you're looking at
# The plant for the FMU (RL environment)

**What it is.** The bond graph of the rig without firmware, clock or push pulse: the model that
`rl/export_plant.jl --rig=lab` exports as the FMU the RL environment steps
([learned controllers](project:learned)). Run alone it starts hanging at rest with 0 V for 5 s, so nothing
moves until you set an input.

| interface | blocks |
| --- | --- |
| inputs (`ExportInput`) | [V](block:V): motor voltage (V); [F_push](block:F_push): horizontal tip force on link 2 (N) |
| encoder outputs (`ExportOutput`) | [x](block:x): cart position (m); [q1](block:q1): link 1 from the rail's x axis (rad); [q2](block:q2): link 2 relative to link 1 (rad) |
| critic outputs | [v](block:v), [w1](block:w1), [w2](block:w2): the rates; [i_m](block:i_m): the motor current |

**Globals.** Every `realism.json` parameter is a global under its own name. The 27 that enter the bond graph and
have a range (link parts, cable, cart mass, viscous frictions, motor R, L, $k_t$, $J_m$, pulley radius, belt)
and the 8 of the realism forces are exposed in the FMU with their ranges (`design/rl_ranges.json`), so the
environment can draw a parameter set per episode. The lumped link masses, centres of mass and inertias
(`m1`, `c1`, `J1`, ...) are driven globals, recomputed at the FMU's initialisation.
[Realism](block:Realism) (`library/LabRealism.jl`) adds the forces outside the bond-graph elements: Coulomb
friction of the joints, the carriage and the motor, the cable springs, commutation ripple and cogging. Sensor
quantisation, noise and the loop delay stay in the environment.

![The plant: the bond graph, the export inputs and outputs, the realism forces|900](@fig:diagram)

**Dashboard.** The FMU's view: cart position and velocity, the joint encoder angles $q_1$, $q_2$ (rad),
voltage and current; plots of the encoders, the cart, voltage and current, and the realism forces. No monitor
block is added here, so the FMU stays the plant alone. The sliders set a constant test voltage, a constant tip
force and the cart mass (`global:m_cart`). With 2 V the cart runs at about 0.27 m/s against the back-EMF and
the carriage friction (the cogging makes the realism force ripple) and reaches the end stop at 1.0 m after
3.7 s, where the current rises to the stall value of 2 V:

![A run with V = 2 V: cart, joints, current and the realism forces|900](@fig:run)
@@ figures pendulum-double-cart-lab-rl
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-rl", "xlim": [0, 12.5],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "ylim": [-1.05, 1.05], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Policy/u", "label": "u"}], "ylim": [-25, 25], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-rl overview - | What you're looking at
# Learned controller on the ideal plant (R0.7)

**Scenario.** The nominal model's: the links hang at rest with 0 V until **1 s**, the controller swings them up
and balances, a **0.45 N, 40 ms** tip push ([PushPulse](block:PushPulse)) hits at **7.5 s**, end **12.5 s**.

**Controller.** [Policy](block:Policy) is one neural network, `library/DoubleCartLabPolicy.jl` (a [64, 64] tanh
actor, 4865 weights, 200 Hz), generated by `rl/make_policy_block.py --rig lab`. It does everything alone, with
no LQR switch-over: swing-up, catch, balance and the push. It sees sin and cos of the absolute angles, the
cart position, rates from differences of the encoder samples and its previous action. It was behaviour-cloned
on this rig's TVLQR swing-up and LQR, then trained with PPO plus a cloning anchor (see
[learned controllers](project:learned)). The plant is the bond graph at the nominal values, without the
realism forces.

**Dashboard.** There are no phases, so the first readout is the larger link angle from upright; then the peak
cart travel, both angles in degrees, voltage and current, and the plots. The fourth plot shows the angles the
policy computes from its encoders (rad) and the push. Sliders: the push and its time. **3D view:** as the
nominal model.

![Link angles, cart and voltage over the run|900](@fig:run)

**Expected outcome:**

| quantity | learned | nominal firmware |
| --- | --- | --- |
| upright inside 2° | 2.7 s after the start | 2.55 s (catch at 3.0 s) |
| before the push | 0.19° and 2.6 mm | 0.002° |
| push: link 1 / link 2, cart | 10.9° / 3.7°, 0.175 m | 10.7° / 4.0°, 0.173 m |
| last second | within 0.01° | |
| peak voltage, travel | 15.2 V, 0.388 m | 15.0 V, 0.387 m |

bgsim and the training environment (the batched FMU) agree to 2e-6 m, 2e-6 rad and 4e-4 V
(`rl/compare.py --task lab`).
@@ figures pendulum-double-cart-lab-rl-robust
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-rl-robust", "xlim": [0, 12.5],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "ylim": [-1.05, 1.05], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Policy/u", "label": "u (after the 2 ms delay)"}], "ylim": [-25, 25], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-rl-robust overview - | What you're looking at
# Robust learned controller on the realistic plant (R1)

**Scenario.** The same as the nominal model: hanging at rest with 0 V until **1 s**, the swing-up and balance,
a **0.45 N, 40 ms** tip push ([PushPulse](block:PushPulse)) at **7.5 s**, end **12.5 s**. But the plant is the
realistic one at the nominal draw: every realism effect ([Realism](block:Realism): Coulomb friction, cable
springs, ripple, cogging), 14-bit joint encoders with seeded noise ([EncNoise1](block:EncNoise1),
[EncNoise2](block:EncNoise2), `global:joint_noise`) and the 2 ms loop delay (`global:loop_delay`).

**Controller.** [Policy](block:Policy) is the R1 policy, `library/DoubleCartLabRobustPolicy.jl` (5633
weights, 200 Hz), trained with domain randomisation on the encoder history (see
[learned controllers](project:learned)). The block quantises the encoders, delays its output by the loop
delay and repeats the training environment's observation pipeline.

**Dashboard.** The larger link angle and both angles in degrees are the *true* angles (from the joint states);
the fourth plot shows the *measured* angles the policy sees, with the push. Watch the voltage readout: the
policy's chatter reaches the 24 V clamp (red zone) all through the balance. Sliders: the push and its time,
the encoder noise (0 to 0.08° rms, the realism range) and the loop delay (0 to 2 ms). **3D view:** a visible
jitter of about a degree while it balances.

![Link angles, cart and voltage over the run|900](@fig:run)

**Expected outcome:**

| quantity | value |
| --- | --- |
| at rest before 1 s | 0 V, the cart at the centre |
| upright inside 2° | at 3.97 s |
| before the push (measured angles) | 1.4° / 1.1°, cart within 25 mm |
| push: link 1 / link 2, cart | 10.8° / 4.2°, 0.171 m |
| last second | within 2° (0.59° / 0.15°) |
| peak voltage, travel | 24 V (the clamp, noise spikes), 0.377 m |

On the shared robustness test the same policy passes 64/64 swing-ups and 64/64 balance + push, with about
5.2 V rms of chatter; see [the comparison](project:comparison). A warm run takes about 20 s.
@@ figures pendulum-double-cart-lab-robust
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-robust", "xlim": [0, 12.5],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "ylim": [-1.05, 1.05], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "u"}], "ylim": [-25, 25], "legend": true, "legend_loc": "right"},
      {"ylabel": "phase", "series": [{"signal": "Ctrl/phase", "label": "0 hold, 1 swing-up, 2 balance"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-robust overview - | What you're looking at
# Robust classical firmware, timed scenario

**Scenario.** The nominal model's: hanging at rest with 0 V until **1 s**, the swing-up, the timed catch at
**4.0 s**, a **0.45 N, 40 ms** tip push ([PushPulse](block:PushPulse)) at **7.5 s**, end **12.5 s**.

**Controller.** [Ctrl](block:Ctrl) is the robust firmware `library/DoubleCartLabRobustCtrl.jl` with
`rearm = 0` (timed): the C1 multi-model LQR balance $u = -K\,[\hat x;\ u_{k-1};\ u_{k-2}]$ on an observer (the
steady-state EKF gain on the encoder angles and the cart), and the rig's **2 ms loop delay inside the block**
(the output is the command of two ticks ago). [Traj](block:Traj) (`DoubleCartLabRobustTraj.jl`) holds the C2
multi-model TVLQR tables, read at the plan time `tau` that the firmware publishes. See
[robust classical control](project:robust).

**Dashboard.** The phase (0 hold, 1 swing-up, 2 balance), the peak cart travel, the link angles in degrees,
voltage and current; the fourth plot shows the phase, the links' energy (0 hanging, about 3.3 J upright) and
the push. Sliders: the push, its time and the mass of link 2. **3D view:** as the nominal model.

![Link angles, cart, voltage and phase over the run|900](@fig:run)

**Expected outcome:**

| quantity | robust firmware | nominal firmware (no delay) |
| --- | --- | --- |
| phases | 0 until 1 s, 1 from 1 s, 2 from 4.0 s | the same |
| before the push | within 0.2° (0.005°) | 0.002° |
| push: link 1 / link 2, cart | **12.9°** / 4.9°, 0.208 m | 10.7° / 4.0°, 0.173 m |
| last second | within 0.2° | within 0.2° |
| peak voltage, travel | 15.0 V, 0.387 m | 15.0 V, 0.387 m |

The multi-model LQR is softer (lower gains, more deflection and travel for the push), which buys its margins:
a 32-sample delay margin against 6 and half the voltage noise on the realistic plant. A Python replica on the
twin (`design/robustmodels.py --replica`) agrees to 3e-4 m and 7e-4 rad.
@@ figures pendulum-double-cart-lab-recover
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-recover", "xlim": [0, 20],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Mon/th1", "label": "θ1"}, {"signal": "Mon/th2", "label": "θ2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "hlines": [{"y": 0.95, "label": "test limit ±0.95 m"}, {"y": -0.95}], "ylim": [-1.05, 1.05], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "u"}], "ylim": [-25, 25], "legend": true, "legend_loc": "right"},
      {"ylabel": "phase, energy [J]", "series": [{"signal": "Ctrl/phase", "label": "phase: 0 hold, 1 swing-up, 2 balance, 3 settle"}, {"signal": "Ctrl/energy", "label": "link energy [J]"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-recover overview - | What you're looking at
# Knock-down and recovery (C3)

**Scenario.** Hanging at rest with 0 V until **1 s**, the state-driven swing-up and catch, then a **1.5 N,
100 ms** knock-down push on the tip ([PushPulse](block:PushPulse)) at **7 s**, end **20 s**.

**Controller.** [Ctrl](block:Ctrl) is the robust firmware `library/DoubleCartLabRobustCtrl.jl` with
`rearm = 1`: the C3 state machine around the C1 balance and the C2 swing-up tables of [Traj](block:Traj). Its
phase output tells what it does:

| time | phase | what happens |
| --- | --- | --- |
| 0 to 1 s | 0 hold | 0 V |
| 1.0 s | 3 settle | the links already hang at rest |
| 1.05 s | 1 swing-up | 50 ms at the hanging rest arm the TVLQR swing-up |
| 3.75 s | 2 balance | region catch ($z^T P z <$ tol) |
| 7.0 s | 2 | the 1.5 N, 100 ms knock-down |
| 7.10 s | 3 settle | a link passes 20°: the drop; the energy (peak 5.2 J) is removed through the cart, the rail guard brakes, the hanging LQR settles |
| 9.88 s | 1 swing-up | re-armed at the hanging rest, the plan shifted to the cart position and the turn count |
| 12.58 s | 2 balance | re-caught; upright until the end |

See [robust classical control](project:robust) for the design.

**Dashboard.** The phase (colour by phase: settle in red), the peak cart travel (yellow above 0.8 m), the link
angles in degrees, voltage and current; the fourth plot shows the phase, the links' energy and the push.
Sliders: the knock-down push and its time. **3D view:** the links fall, the cart brakes and swings them down,
they come to rest and swing up again.

![Link angles, cart, voltage, phase and energy over the run|900](@fig:run)

**Expected outcome:** one drop and one recovery (`Ctrl/drops` = 1), upright within 0.2° over the last 2 s, a
peak travel of **0.767 m** after the knock-down, inside the robustness test's 0.95 m, and |V| ≤ 24 V. The
timed nominal firmware recovers none of the 64 knock-downs of the robustness test; this firmware recovers all 64.
A Python replica on the twin switches phase at the same ticks (within 1 ms) and agrees to 6e-3 m and 1.6e-2 rad
over the 20 s, through both swing-ups.
