# Results and checks

![Load speed, voltage and the estimate over the whole run|900](assets/72f19f8e0de3.png)

The zoom on the load step at 1 s shows the dip, the recovery and the rod segments ringing:

![Zoom on the load step|900](assets/44d59d64147e.png)

## Acceptance checks (`expected.json`, README measurements)

| check | limit | measured (README) |
| --- | --- | --- |
| [IW2/p.f](signal:IW2/p.f) at 0.6 s | 10 +- 2 % | 10.130 rad/s |
| [IW2/p.f](signal:IW2/p.f) at 1.3 s (0.3 s after the load step) | 10 +- 2 % | 10.112 rad/s |
| [IW2/p.f](signal:IW2/p.f) at 2.0 s | 10 +- 2 % | 10.123 rad/s |
| [LQG/w_load_hat](signal:LQG/w_load_hat) at 2.0 s | 10 +- 1 % | 9.9987 rad/s |
| RMS of `w_load_hat` minus `IW2/p.f` over $[0.5, 2]$ s | below 0.2 rad/s | 0.181 rad/s |
| largest $\lvert$ [V/p.e](signal:V/p.e) $\rvert$ | at most 24 V | 24.000 V (the clamp is active on the step) |
| diagnostics | no E901, E106, W206 | W201 (IW1/IJm in derivative causality) and W205 only |

The RMS residual is the encoder's 12-bit staircase at the 1 ms sampling phase plus the three-segment rod's two mid inertias, which the 4-state design model lumps away; the estimator has no load-side measurement.
