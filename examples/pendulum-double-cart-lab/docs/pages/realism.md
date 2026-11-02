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
