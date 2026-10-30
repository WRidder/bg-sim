# Planar Links, forward dynamics

The same three arms as in the inverse model (see its docs), driven the other way round: the **analytical torque of the CSV file** (`tau_analytical`) is applied as the joint-side effort of every joint ([A3_Torque1](block:A3_Torque1), an `MSe`), the drive train with the gear, $J_m$ and $B$ is in the graph, and the model integrates the motion for 1 s *open loop*. The joint angle is compared with the angle column of the CSV: [A3_QErr1/e](signal:A3_QErr1/e).

![Open-loop angle drift of the 2- and 3-link arms|760](assets/0da262b0dc4e.png)

| arm, joint | max drift [rad] |
| --- | --- |
| 1-link | 1.7e-7 |
| 2-link, 1 / 2 | 1.2e-6 / 7.6e-7 |
| 3-link, 1 / 2 / 3 | 3.3e-6 / 2.2e-6 / 3.4e-7 |

## Why the drift is not zero

An open-loop arm integrates every torque error twice (the arms lie in the horizontal plane without gravity, so nothing amplifies it exponentially). The sources of the error are the interpolation error of the torque (a cubic through 1 kHz samples, about 1e-9 N·m), the pivot compliance of `Revolute2DCompliant` ($k_t = 10^8$ N/m) and the solver tolerance (`reltol` 1e-9). Together they stay below 3.5e-6 rad on a 1 rad motion, which is the check bound in `expected.json` (measured with about 1.5x margin, rounded up).

The joint is `Revolute2DCompliant` because the rigid variant is index 3 on a 3-DOF body. The CSV source, the conventions and the planar structure are described in the pages of the `planar-links` model.
