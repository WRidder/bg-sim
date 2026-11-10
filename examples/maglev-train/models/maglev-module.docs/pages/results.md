# Results

![Gap, current and voltage|900](assets/400386387ea2.png)

- **Lift-off.** The coil is energised from zero; the chopper saturates at 800 V for 25 ms and the current reaches 241 A. The module sits on the skids (gap 16.0 mm, the contact compressed by 0.65 mm under the weight) until the force exceeds the weight at about 0.45 s, then follows the reference to 10 mm without undershooting it.
- **Steady state.** The current settles at the analytic trim 150.0 A, the magnet force equals the weight $(m_b + m_c)\,g = 129.98$ kN, and the gap error is below 3 µm before the guideway step.
- **Guideway step.** A 1 mm sink of the rail gives a peak gap deviation of 0.34 mm; the loop absorbs it within about 0.3 s.
- **Payload.** An extra 2 t gives a peak deviation of 1.25 mm and the integral action brings the gap back (1.2 µm left after 4 s). The trim current rises to 160.9 A, in step with the weight.

![Gap error and current after the steps|900](assets/590a7c767431.png)

The checks in `expected.json` compare these numbers with an independent scipy simulation of the same nonlinear equations and controller; bgsim and scipy agree within 15 µm in the gap over the 8 s.
