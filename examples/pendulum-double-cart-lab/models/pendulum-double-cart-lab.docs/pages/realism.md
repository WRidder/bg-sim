# Realism screen

`design/realism.json` holds every parameter of the rig with nominal, min, max, unit and a description:
the link parts, lengths and centres of mass, viscous and Coulomb friction of both joints, the carriage and
the motor, the cable springs and drag, the motor and belt constants, the encoder resolution and noise, the
loop delay, the armature current lag and the commutation ripple and cogging. `lablib.setup` builds the truth
twin and the firmware replica for any parameter set (the counterpart of the quad pendulum's
`quadlib.realistic_setup`, reusing its EKF, firmware replica and closed loop). `design/screen.py` runs the
classical controller against it; the summary is `design/screen_results.json`.

The truth is the twin with every effect (RK4, 8 substeps per 1 ms sample), the firmware has the design's
tables and gains unchanged. Scenarios: the swing-up and the balance from a 2° lean with the 0.45 N push;
"ok" means off the end stops and every link within 2° of upright over the last 2 s. Rates come from
filtered differences (`diff`, the baseline) or an EKF on the nominal twin.

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
