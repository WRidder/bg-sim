# Validation

`expected.json` checks three things, and every note says which:

1. **An independent integration.** `design/reference.py` integrates the same equations as a 6-DOF rigid body in scipy (quaternion attitude, DOP853 at rtol 1e-10, mode switches as events). The bond-graph models match it to 2e-4 in altitude and speed, 2e-5 in mass, and within 0.1 s in the event times.
2. **Analytic cases.** In vacuum with the thrust held vertical, the ascent stage's speed is Tsiolkovsky's $c \ln(m_0/m)$ to 1e-6. A hover burns $m(t) = m_0 e^{-g t / c}$, so it runs dry at $(c/g)\ln(m_0/m_\text{empty})$ to 0.01 s.
3. **Apollo 11.** Fitted quantities are marked as such; the rest are independent:

| quantity | published | model |
| --- | --- | --- |
| landing | 754.9 s after ignition | 758.3 s |
| mass at engine cutoff | 7,374 kg | 7,427 kg (+0.7 %) |
| usable propellant left | 674 lb = 306 kg | 358 kg |
| velocity gained to touchdown | about 6,775 ft/s | 6,997 ft/s (+3 %) |
| velocity gained to high gate / low gate (premission) | 5,375 / 6,176 ft/s | 5,411 / 6,157 ft/s |
| inertial speed at 176, 258, 384, 402 s (premission) | 4,000, 3,065, 1,456, 1,315 ft/s | within 4 % |
| Aldrin's altitude callouts, 400 ft to 20 ft | ALSJ | within 35 ft at the called times |
| ascent burn | 434.9 s | 437.4 s |
| ascent stage at insertion | 2,689 kg | 2,666 kg |
| orbit after the ascent burn | 88.9 × 16.9 km | 88.3 × 16.9 km |

The descent burns 0.7 % less propellant than Eagle did and gains 3 % more velocity: the model has no gimbal trim, no slosh and no attitude jitter, and Armstrong's 140 s landing phase (104 s nominal) flew pitch and roll excursions that the pilot model leaves out.
