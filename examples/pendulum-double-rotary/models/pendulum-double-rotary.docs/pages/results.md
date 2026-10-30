# Results and checks

Numbers of the bond-graph run (real worker, `Rodas5P`, rtol 1e-6, atol 1e-8):

| quantity | bond graph | design.py (rigid model) |
| --- | --- | --- |
| upright (all links within 3 deg) | 4.984 s | 4.984 s |
| catch (phase 2) | 5.021 s | 5.021 s |
| upright band before the disturbance | 0.050 deg | 0.052 deg |
| tip deflection after the disturbance | 7.22 deg | 7.30 deg |
| recovery (inside 0.5 deg) | 1.93 s after the pulse | 1.91 s |
| peak motor voltage | 10.00 V (limit 10 V) | 10.00 V |
| largest arm angle | 1.566 rad | 1.566 rad |
| design against bond graph, free swing | 2.38 mrad | |

![Swing-up and catch|700](assets/5823471bc157.png)

![Disturbance and recovery|700](assets/58f67a345298.png)

`expected.json` holds the checks (with the tolerance of each in its note): at rest before $t_{on}$, upright by $t_{on} + T_s + 0.5$ s, the upright band before the disturbance, the disturbance peak, the recovery band, the voltage limit, the arm travel, no W201/W206/E901 diagnostics, the scene bindings, and (model `pendulum-double-rotary-free`) the free swing against `design.py`.

Back to the [overview](page:overview).
