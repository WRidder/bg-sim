# Planar Links, 3-link arm with payload

The 3-link arm of the inverse model plus the **1 kg payload** 0.1 m beyond the end of link 3. The reference script models the payload as a fourth Robotics Toolbox link (`a = 0.1`, `m = 1`, no inertia) and as the `pay_*` terms of its analytical 3-link class; `data/arm3p.csv` holds both torques.

In the bond graph the point mass is lumped into the body of link 3 ([A3_Body3](block:A3_Body3)) by the parallel axis theorem: $m = 5$ kg, centre of mass 0.102 m from joint 3, $J = 0.1853$ kg·m². A point mass has no inertia of its own, so a separate body with $J = 0$ would be singular in the graph.

![Torque error with the payload against the 4-link Robotics Toolbox robot|760](assets/864f101bc187.png)

| joint | peak torque [N·m] | max error whole run | max error from 0.02 s |
| --- | --- | --- | --- |
| 1 | 131 | 0.13 | 1.4e-3 |
| 2 | 62 | 5.3e-2 | 6.0e-4 |
| 3 | 12 | 6.6e-3 | 7.4e-5 |

The torques are [A3_Torque1/y](signal:A3_Torque1/y) and the errors [A3_TauErr1/e_rtb](signal:A3_TauErr1/e_rtb). The first-millisecond ring is the compliant pivots (see the `planar-links` docs); the tolerances in `expected.json` are the measured values with about 30 % margin.
