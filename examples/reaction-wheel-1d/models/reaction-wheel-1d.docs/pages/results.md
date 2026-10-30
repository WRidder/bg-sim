# Results and checks

![Cube angle, wheel speeds and motor voltage, first two seconds|900](assets/53fe9b16515c.png)

`design.py` also integrates the non-linear closed loop (with $\sin\theta$, the winding inductance, the 2 ms hold and the clamp); the model run reproduces it to better than 1e-5 rad.

| quantity | design.py and model run |
| --- | --- |
| peak $\lvert u \rvert$ | 12.000 V |
| peak wheel speed (absolute / relative to the cube) | 4.165 / 4.684 rad/s |
| $\theta(0.1\ \mathrm{s})$ | 0.014607 rad |
| $\lvert\theta\rvert$ over $t \ge 2$ s | 3.8929e-4 rad (0.0223 deg) |
| inside 0.2 deg from | 0.654 s |
| $\theta(4\ \mathrm{s})$ | -1.44e-5 rad |
| wheel angle relative to the cube at 4 s | 3.075 rad |

## Acceptance checks (22, `expected.json`)

- [Body/theta](signal:Body/theta): 0.05 at $t = 0$; below 0.2 deg (0.0034906585 rad) from 0.7 s and over $[2, 4]$ s; values at 0.1, 0.5, 1 and 4 s: 0.014607, -0.004185, -0.002021, -1.4395e-5 rad (tolerance 2e-5); the angle sensor [AngleSens/y](signal:AngleSens/y) agrees with the body's own angle to 1e-6;
- [LQR1/u](signal:LQR1/u): $\lvert u\rvert \le 12$, exactly 12 in $[0, 0.01]$ s, below 0.1 V after 0.1 s, 0 at $t = 0$;
- wheel speed [Drive/wsense/y](signal:Drive/wsense/y) at most 300 rad/s (peak 4.1652 within 0.01), [RelSpeed/y](signal:RelSpeed/y) peak 4.6839, 0.9983 at 1 s, 0.0071 at 4 s, wheel angle `Drive/phi_rel` 3.075 rad at 4 s;
- no E901, E106, W201, W202, W205 or W206 (the run reports no diagnostics at all).
