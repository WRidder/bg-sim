# Results and checks

Numbers of the bond-graph run (real worker, `Rodas5P`, rtol 1e-6, atol 1e-8) against the design closed loop:

| quantity | bond graph | design.py (rigid model) |
| --- | --- | --- |
| upright (all links within 3 deg) | 3.823 s | 3.823 s |
| catch (phase 2) | 5.000 s | 5.000 s |
| upright band before the disturbance | 0.001 deg | 0.001 deg |
| tip deflection after the disturbance | 3.55 deg | 3.55 deg |
| recovery (inside 0.5 deg) | 1.35 s after the pulse | 1.35 s |
| peak motor voltage | 14.15 V (limit 15 V) | 14.15 V |
| largest arm angle | 2.500 rad | 2.500 rad |
| design against bond graph, free swing | 0.011 mrad | |

![Swing-up and catch|700](assets/29c351f0cbfa.png)

![Disturbance and recovery|700](assets/cff868010794.png)

`expected.json` holds the checks (with the tolerance of each in its note): at rest before $t_{on}$, upright by $t_{on} + T_s + 0.5$ s, the upright band before the disturbance, the disturbance peak, the recovery band, the voltage limit, the arm travel, no W201/W206/E901 diagnostics, the scene bindings, and (model `pendulum-triple-rotary-free`) the free swing against `design.py`.

Back to the [overview](page:overview).
