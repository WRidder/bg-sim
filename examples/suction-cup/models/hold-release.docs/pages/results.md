# Results

![The hold-release run: heights, vacuum, stroke and utilisation|900](assets/613d9640e4f2.png)

The vacuum builds up in about 0.1 s. While the box still rests on the table, the lift stroke pulls it up:

![Vacuum build-up and lift-off|900](assets/85b752d5c263.png)

## Simulation against the hand calculation

| quantity | simulation | hand calculation |
| --- | --- | --- |
| operating vacuum | 59 152.1 Pa | 59 152.3 Pa |
| holding capacity | 29.576 N | 29.576 N |
| hanging extension (t = 2 s) | −1.6680 mm | −1.6680 mm |
| side stiffness factor $k_f$ | 1.8713 | 1.8713 |
| static U | 0.1983 | 0.1990 |
| axial mode (bounce ring-down) | 64.547 rad/s, ζ 0.1033 | 64.55 rad/s, ζ 0.1033 |
| lateral modes (steps coast, FFT) | 6.59 / 13.13 Hz | 6.55 / 13.20 Hz |
| lateral deflection at 30° tilt | 1.013 mm | 1.016 mm |
| U at 30° tilt | 0.603 | 0.620 |
| linear vs nonlinear hang | +2.345 / −1.678 mm | +2.354 / −1.668 mm |

The hand values hold where the motion is slow or small. The dynamic runs go beyond them:

- **Steps.** The sudden pulses overshoot. U reaches 0.90 at 4.5 m/s², against 0.61 quasi-static.
- **Chirp.** The swept transmissibility peaks at 2.75 and 3.28. The steady-state model gives 4.58 at the sway mode. The 1.85 Hz/s sweep crosses each resonance in a few cycles, and the demodulator low-pass smooths the peak.
- **Bounce.** The bottoming makes the axial spring harden, so the peak response moves from 10.3 Hz to about 13.9 Hz.

`expected.json` checks every row of this table, the bottoming force, the transmissibility peaks, the loss of the overloaded box and the held outcome of every other model.
