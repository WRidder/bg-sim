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
