# Results and checks

![Tilt, phase, vertex loads and wheel speeds|900](assets/0b5b5e76113d.png)

## Measured (README, direct run of the pipeline)

| quantity | value |
| --- | --- |
| rest on the face | $\sum f_n/(m g) - 1$ = 1.3e-5 at 0.25 s and 5e-8 at 0.49 s; each bottom vertex 3.4335 N, top four 0 |
| edge phase | tilt 0.8271 rad at 1.17 s, settles to 0.7857 rad at 2.2 s (45.02 deg); exactly two loaded vertices (`nload` = 1.99958), $f_n$ = 6.867 N each, the other six at most 1e-17 N |
| corner phase | tilt 0.95535 rad at 4.2 s (54.74 deg), within 0.0003 rad of $\arctan\sqrt2$ from 3.15 s on; one loaded vertex, $f_n$ = 13.734 N; CoM height 0.17243 m |
| wheel speeds | peak 307.9 rad/s (wheel 4 at 2.99 s; wheels 1/2/3: 205.9 / 101.4 / 175.0) |
| motor torque | at the 1.2 N·m limit during the two tip-up moves; allocator scale factor down to 0.738 |
| null space | $\max\lvert n\cdot\tau - \lambda\rvert = 2.2\cdot10^{-16}$, `Tap/resid` 1.1e-15 |
| energy ledger | drift 1.0e-3 J over 4.5 s on 1.4 J (7e-4) |
| states | 25 |
| cost | `run_checks.py --only cube-pyramid-3d`: 82 checks, 0 failed, 765.6 s for all three runs |

Wheel speeds reach 308 rad/s (2940 rpm) in the corner move: the pyramid has to absorb the angular momentum of the tip-up.

## Checks (`expected.json`)

Initial attitude; rest on the face (the sum of the normal forces equals the weight at 0.25 s and 0.49 s, each bottom vertex a quarter, top vertices at most 1e-9); edge hold (tilt 45 deg to 2e-3, two loaded vertices carrying half the weight each, the other at most 1e-6 N); corner hold (tilt $\arctan\sqrt2$ to 1e-3, one loaded vertex carrying the weight); null-space tap; wheel speed and motor torque limits; the energy ledger (`tol` 1.5e-3 on the scale 1.4); no W201, E101, E102, E103, E106, E007 or W206. The expected file gives a per-model `run_timeout` of 900 / 600 / 600 s because building the MTK system takes minutes.
