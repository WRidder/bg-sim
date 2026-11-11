# Results and checks

## The step (default run)

![250 N step at 0.2 s: tip deflection and root stress|900](assets/a38e63bc672c.png)

![Settled at 9.9 s (x10): the bars bend 41 and 39 mm, the I-beam 1.9 mm|700](assets/5da617b60d2b.png)

| at 10 s | round bar | square bar | IPE 100 | reference |
| --- | --- | --- | --- | --- |
| tip deflection | 40.68 mm | 38.85 mm | 1.944 mm | $FL^3/(3EI)$, 0.2 % |
| root moment | 500 N m | 500 N m | 500 N m | $FL$, 0.1 % |
| stress | 113.8 MPa | 96.3 MPa | 15.3 MPa | $FL/W$, 0.1 % |
| utilisation | 0.484 | 0.410 | 0.065 | $\sigma/f_y$ |
| largest deflection after the step | 77.47 mm | 73.97 mm | 3.701 mm | finite elements, 0.5 % |
| largest root moment after the step | 1105 N m | 1105 N m | (not resolved) | finite elements: 1104 N m = 2.21 F L, 2 % |
| largest utilisation after the step | 1.07 | 0.905 | (FE: 0.144) | finite elements, 2 % |
| f1 (FFT of the ring-down) | 6.42 Hz | 6.57 Hz | 29.4 Hz | $1 + \cos\lambda\cosh\lambda = 0$, 1 % |

The ratios $w_{round}/w_{IPE} = 20.93$ and $w_{square}/w_{IPE} = 19.99$ are the ratios of the second moments (0.2 %).

## Resonance

![10 N at 6.42 Hz, the round bar's first eigenfrequency|900](assets/2dfd61024f4b.png)

| steady state, 10 N at 6.4233 Hz | round bar | square bar | IPE 100 |
| --- | --- | --- | --- |
| tip amplitude | 39.49 mm | 25.32 mm | 0.0815 mm |
| stress amplitude | 129.5 MPa | 73.1 MPa | 0.65 MPa |

The references are a finite element model of each beam (60 Hermite elements, every mode damped by ζ = 0.02), checked over 10 to 12 s to 1 %. The same checks at 50 N and 4 Hz, below every resonance, give 13.13, 12.20 and 0.396 mm.

## Sweep

![10 N swept from 2 to 40 Hz in 10 s|900](assets/c8ff4892cf3c.png)

The sweep passes the bars' first modes at about 1.4 s and the I-beam's at 7.4 s. It moves fast through each narrow resonance (0.26 Hz wide for the bars), so the peaks stay below the steady-state amplitudes.

## Acceptance checks

`expected.json` runs the model as `cantilever-sections` (the step), `-sine`, `-resonance`, `-weight` (own weight on: $w = FL^3/(3EI) + qL^4/(8EI)$, $M = FL + qL^2/2$, q = 76.26 N/m) and `-sweep`, with the dashboard's run overrides. The references come from `design/reference.py` (numpy/scipy only).
