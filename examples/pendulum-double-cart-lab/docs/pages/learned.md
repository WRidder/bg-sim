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
