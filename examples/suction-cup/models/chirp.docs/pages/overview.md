# Lateral chirp: transmissibility

The tool moves sideways with a chirp from 1.5 to 20 Hz in 10 s. The amplitude rises from 0.12 to 0.4 mm. [Transmissibility](block:Trans) demodulates the lateral motion of the box's centre of mass and of the tool at the chirp phase. It low-pass filters both and divides them: [Trans/TR](signal:Trans/TR) against the filtered frequency [Trans/fl](signal:Trans/fl).

![Chirp frequency, transmissibility, lateral deflection and U|900](assets/371fa58cd10d.png)

![Transmissibility against frequency|700](assets/186e16d383f7.png)

The curve has two peaks: 2.75 at 6.6 Hz (sway) and 3.28 at 13.4 Hz (tilt). Between them, near 8 Hz, the box hardly moves (TR 0.34). The steady-state linear model gives a peak of 4.58 at 6.5 Hz. The sweep crosses each resonance in a few cycles, too fast to reach the steady state, and the demodulator smooths the peak. The tilt resonance loads the lip most: U peaks at 0.71 there.
