# Results and checks

![Capacitor voltage and inductor current of both subsystems|900](assets/fc0c5e308cc1.png)

The two forms lie on top of each other, as they must: both start from the same state and are the same differential equations.

## Acceptance checks

| check | expected | tolerance |
| --- | --- | --- |
| peak of `Iconic/C1/p.e` over $[0, 0.01]$ s | 1.16303353426 V | 0.001 V (the plan's 16.3 % +- 0.1 %) |
| peak of `Bondgraph/C1/p.e` | 1.16303353426 V | 0.001 V |
| `Iconic/C1/p.e` against `Bondgraph/C1/p.e`, max difference over the run | 0 | 1e-8 V |
| diagnostics W201, W202, E106 | absent | |
| 3D bindings | match the scene | |

The README reports the measured peak 1.16303353426 V at $t = 3.62768$ ms (the analytic value is 1.16303353482 V, so the solver misses it by 5.6e-10 V) and a maximum difference between the subsystems of 4.22e-15 V.

**W205.** The run reports W205 for the pure `Generic` bond island of the bond graph subsystem. Plan 5.6 prescribes this warning and the check deliberately allows it. Causality is fine: SCAP assigns integral causality on both storage elements, hence no W201/W202/E106.

Back to the [model](page:model) or the [overview](page:overview).
