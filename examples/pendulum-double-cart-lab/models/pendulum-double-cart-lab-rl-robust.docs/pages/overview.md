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

![Link angles, cart and voltage over the run|900](assets/fa3e72bfb12e.png)

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
