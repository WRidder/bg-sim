# Results and checks

![Positions, suspension travel and tire force|900](assets/71a0fe4dc9c2.png)

`design/design.py` integrates the same equations independently with RK4 at 1e-5 s. Values from the README:

| quantity | design.py (RK4) | bond graph run |
| --- | --- | --- |
| peak sprung displacement | 0.074654 m at 0.893 s | 0.0746537 m at 0.893 s |
| peak unsprung displacement | 0.052814 m at 0.809 s | 0.0528144 m at 0.809 s |
| suspension travel `Stop/x` | -0.036687 to +0.034440 m | -0.0366874 to +0.0344404 m |
| hard-stop contact | none (3.67 cm of 8 cm) | none (`Stop/a.e` is 0) |
| tire force | 1673.245 to 4948.882 N | 1673.242 to 4948.880 N |
| body mode (free decay) | 1.211 Hz | 1.211 Hz |
| body mode (FFT, 1.8 to 4.0 s) | 1.2238 Hz | 1.2238 Hz |
| wheel hop | 11.853 Hz | 11.852 Hz |
| wheel hop (FFT, 0.65 to 0.85 s) | 11.862 Hz | 11.846 Hz |
| linearised undamped modes | 1.257 Hz ($\zeta$ 0.268), 11.633 Hz ($\zeta$ 0.262) | |

The plan's targets are the undamped estimates

$$f_{body} = \frac{1}{2\pi}\sqrt{\frac{k_s k_t}{(k_s + k_t)\,m_s}} = 1.239\ \mathrm{Hz}, \qquad f_{hop} = \frac{1}{2\pi}\sqrt{\frac{k_s + k_t}{m_u}} = 11.803\ \mathrm{Hz}.$$

The measured damped body mode is 2.3 % below 1.24 Hz (1.3 % from the FFT) and the wheel hop 0.4 % above 11.8 Hz, both inside the plan's $\pm 5$ % bands. The tire force is never negative: it never gets closer than 1.673 kN to zero on this road.

## Acceptance checks (33 in `expected.json`)

- static equilibrium: both masses stay within 1e-6 m for $t < 0.5$ s; spring preloads 2943.0 N and 3335.4 N;
- road: edges +0.5 and -0.5 m/s, position 2.5 cm half way up, 5 cm on the plateau, back to 0 at 1.6 s;
- sprung-mass response: cursors at 0.6, 0.9, 1.5 and 2.0 s and the peak 7.465 cm at 0.893 s ([SInt/y](signal:SInt/y)); unsprung mass: cursors and the 5.281 cm peak ([UInt/y](signal:UInt/y));
- travel and stop: peak 3.669 cm, bound 0.08 m and `Stop/a.e` identically 0;
- tire force [Tire/F](signal:Tire/F): peak 4.949 kN, minimum 1.673 kN and [TireNeg/y](signal:TireNeg/y) below 1e-9 (the plan's "never negative");
- mode frequencies: `fft_peak` of [SInt/y](signal:SInt/y) over $[1.8, 4.0]$ s (1.224 Hz) and of [IMu/p.f](signal:IMu/p.f) over $[0.65, 0.85]$ s (11.846 Hz) against 1.24 and 11.8 Hz with a 5 % band, plus four zero-crossing period checks;
- no E901, E106, W201, W202, W205 or W206 (8 states, 68 equations, 5058 steps).

## Note on the road table

An earlier version of the `TimeTable` block wrote its conditions as a normalised table coordinate and could re-fire at every step when a sample instant coincided with an output grid time (NOTES-6). The block now writes every condition in $t$, whose roots are the sample instants, so this sample uses the stdlib block directly. The plan's 3D variant with spring cylinders is not included.
