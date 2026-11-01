# Free optimisation: the highest pick rate

`uv run examples/fanuc-pick/design/optimize_free.py [--refine] [--loose-strict]` (about 75 min per pass on
20 cores) drops the fixed families and optimises every freedom the cell has, for the highest **pick rate**:
picks per minute = 60 / (T_cyc + T_ret), where T_ret is the empty joint move from the depart end back to
the approach start at the robot's full rates. The constraints are those of `optimize.py` (margin, no drop,
every LR-10iA/10 limit at 100 % or below, the carton corners clear of the support, now with the tilted
carton) plus a vent condition: the residual holding force at the depart start is at most 20 % of the
parcel weight.

The freedoms are added one at a time, each stage warm-started from the one before (CMA-ES on the reduced
model, then a push along the stage's own time scale to the constraint boundary; two passes, the second
restarting every stage from the first pass's optimum):

| stage | freedoms |
| --- | --- |
| A0 | the best of families 1–4 (`optimize.py`) |
| A1 | families 3 and 4 with the **waiter tilt**: the tool axis leans towards the specific force g − a of the carton (`tilt_gain`, largest tilt `tilt_max_deg`, filter `T_tw`, fade at the pick and the place `T_tr`); level at both contacts |
| A2 | **family 5, free timing**: own durations for lift, transfer and lower, the transfer starts and ends anywhere inside the carry (lift and lower overlap it), asymmetric acceleration and deceleration shares, with the tilt |
| A3 | + the **yaw turn spread** over its own window of the carry |
| A4 | + the **gripper timing**: vacuum on before the contact, seal wait, vent time, approach and depart durations |

Picks per minute (T_cyc + T_ret, holding margin, peak tool tilt, robot limit use); "no gain" means the
stage did not beat the best so far:

| Load case | A0 baseline (best of families 1-4) | A1 + tilt (waiter) | A2 + free timing (family 5) | A3 + yaw spreading | A4 + vacuum/approach/depart overlap |
| --- | --- | --- | --- | --- | --- |
| Carton 1.5 kg, centred CoM (M ≥ 0.5) | **28.3/min** (1.612 + 0.504 s, M 0.50, tilt 0°, robot 57 %) | **30.4/min** (1.534 + 0.440 s, M 0.50, tilt 4°, robot 58 %) | no gain | **30.7/min** (1.522 + 0.433 s, M 0.50, tilt 1°, robot 95 %) | **32.6/min** (1.394 + 0.447 s, M 0.50, tilt 0°, robot 94 %) |
| Carton 1.5 kg, CoM offset (60, 30) mm, gripped over the CoM (M ≥ 0.5) | **28.7/min** (1.626 + 0.467 s, M 0.50, tilt 0°, robot 55 %) | **30.0/min** (1.556 + 0.443 s, M 0.50, tilt 4°, robot 55 %) | **30.4/min** (1.525 + 0.446 s, M 0.50, tilt 3°, robot 65 %) | no gain | **32.4/min** (1.400 + 0.451 s, M 0.50, tilt 1°, robot 94 %) |
| Carton 0.6 kg + loose ball 0.5 kg (M ≥ 0.3) | **30.5/min** (1.506 + 0.464 s, M 0.30, tilt 0°, robot 68 %) | **31.5/min** (1.471 + 0.434 s, M 0.30, tilt 1°, robot 57 %) | **32.7/min** (1.399 + 0.434 s, M 0.30, tilt 2°, robot 81 %) | no gain | **33.9/min** (1.326 + 0.445 s, M 0.30, tilt 7°, robot 100 %) |
| Carton 0.6 kg + loose bottle 0.5 kg (M ≥ 0.3) | **30.1/min** (1.492 + 0.504 s, M 0.31, tilt 0°, robot 67 %) | **32.9/min** (1.354 + 0.472 s, M 0.30, tilt 7°, robot 80 %) | **33.2/min** (1.367 + 0.438 s, M 0.30, tilt 3°, robot 74 %) | **33.6/min** (1.344 + 0.440 s, M 0.30, tilt 1°, robot 74 %) | **34.9/min** (1.277 + 0.441 s, M 0.34, tilt 1°, robot 100 %) |
| Carton 0.6 kg + loose ball 0.5 kg (M ≥ 0.5) | not feasible | **25.4/min** (1.916 + 0.449 s, M 0.50, tilt 4°, robot 67 %) | **25.7/min** (1.899 + 0.437 s, M 0.50, tilt 11°, robot 85 %) | no gain | **27.5/min** (1.747 + 0.435 s, M 0.50, tilt 3°, robot 64 %) |
| Carton 0.6 kg + loose bottle 0.5 kg (M ≥ 0.5) | not feasible | **26.5/min** (1.825 + 0.443 s, M 0.50, tilt 11°, robot 58 %) | **28.5/min** (1.656 + 0.446 s, M 0.50, tilt 9°, robot 98 %) | no gain | no gain |

What the free optimisation finds:
- **15 % more picks for the solid carton**: 28.3 → 32.6 picks/min (box), 28.7 → 32.4 (offset CoM), at the
  same margin of 0.5. The loose contents gain 11 % (ball, 30.5 → 33.9) and 16 % (bottle, 30.1 → 34.9).
- **The waiter tilt pays within the fixed families** (A1: +1.0 to +2.8 picks/min; 1–7° of tilt, gain
  0.05–0.5). With free timing (A2–A4) the optimiser shapes the transfer itself (asymmetric
  acceleration and deceleration, the transfer overlapping the lift and the lower), and the tilt drops to
  0–1° for the solid carton: the smooth profile already keeps the shear low. The loose ball keeps 7°.
- **The gripper timing adds as much again** (A4: +1.2 to +2.0 picks/min). The vacuum opens
  0.02–0.17 s before the contact so the seal wait is zero, the vent takes 10–76 ms instead of 80 ms (the
  cup chamber vents in about 0.4 ms), and the approach and depart run in 0.18–0.20 s instead of 0.24–0.26 s.
- **Spreading the yaw turn** adds little (0–0.4 picks/min): the 90° turn is not what loads the cups.
- **The robot becomes the limit.** The fixed-family optima use 55–68 % of the LR-10iA/10 limits; the free
  optima 94–100 %. For the bottle the robot limit is active and the margin (0.34) is above the required
  0.3.
- **Loose contents at a margin of 0.5** (`--loose-strict`): reachable with the tilt and free timing, at
  27.5 picks/min (ball, 3° tilt) and 28.5 picks/min (bottle, 9° tilt). The fixed-family optima for 0.3 (A0)
  do not hold 0.5; families 3/4 with the tilt (A1) do, at 25.4 and 26.5 picks/min.
- The models `<case>-tilt-best` (stage A1) and `<case>-opt` (the best stage) carry these optima; the
  `-best` models keep the fixed-family optima. CMA-ES is a stochastic local search: the numbers are good
  optima, not proven global ones (the second pass still gained up to 4 % in some stages).
