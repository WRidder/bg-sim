# Robust classical control for the pendulum rigs

The classical controllers of the pendulum examples (cart and rotary, 2 to 4 links: `pendulum-*`, `quad-pendulum`) are
designed on one nominal model: a discrete LQR for balance, and an offline-optimised swing-up trajectory tracked by a
time-varying LQR (TVLQR). They are robust to small parameter errors, but a timed swing-up cannot recover once the
pendulum leaves its planned path (a failed catch, a push, a large parameter error). This plan makes the classical
design robust over the realistic parameter ranges, so it can be compared fairly with the learned controllers of
`plan/RL_PLAN.md`.

Parameter ranges and non-idealities: the shared realistic set from the quad-pendulum phase B work
(`examples/quad-pendulum/design/realism.json`: friction, encoder and cable mass, sensor quantisation and noise, loop
delay, actuator ripple). Both this plan and RL step R1 randomise over the same set.

Status and progress: the tracking table at the end. Update it in the same commit as the work.

## Work items

1. **Multi-model balance gain.** One balance gain designed against several models at once: the corners and samples
   of the parameter box, with the delay and the sensor filter included. Candidates are an LQR on stacked models
   (minimising the summed or worst-case cost) or a structured H∞ / mixed-sensitivity design. Verify over the box
   with the closed-loop eigenvalues, and with gain, phase and delay margins.
2. **Worst-case swing-up plan.** The swing-up trajectory planned over the parameter range, not on the nominal model.
   Options are multi-model collocation (one feed-forward that brings every sampled model into the catch region), a
   min-max cost, or a plan with margins on the actuator and the travel, followed by a TVLQR designed against the
   same models.
3. **State-driven (energy-based) swing-up.** A swing-up that is driven by the pendulum's state, not by a clock, so it can
   recover from a failed catch or a push. For example, energy pumping (Åström–Furuta style, extended to several links
   with a mode or virtual-constraint scheme) that hands over to the balance gain inside its catch region, with
   re-arming after a drop.

Each item is evaluated with the same robustness test as the RL controllers: Monte Carlo over the parameter box and the
non-idealities, plus pushes. Success rate, catch time, peak actuator and travel are reported.

## Comparison

One table per rig compares five controllers:
- the nominal classical design (today's examples);
- the robust classical design (items 1 to 3);
- pure RL;
- RL with an imitation warm start;
- the hybrid: an RL swing-up into the catch region, with the LQR balance.

## Progress tracking

| # | item | rig | status | notes |
| --- | --- | --- | --- | --- |
| C1 | multi-model balance gain | double cart | todo | after the phase B ranges exist |
| C2 | worst-case swing-up plan | double cart | todo | |
| C3 | energy-based swing-up with re-arm | double cart | todo | |
| C4 | items 1 to 3 on the quad cart, then the rotary rigs | quad cart, rotary | todo | |
| C5 | comparison table: classical vs robust classical vs RL vs hybrid | all | todo | with RL step R1 |
