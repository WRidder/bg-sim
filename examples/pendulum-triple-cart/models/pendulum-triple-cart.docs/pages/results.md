# Results and checks

All numbers are from the real Julia worker (Rodas5P, `reltol` 1e-8); the design column is the closed loop of the Lagrangian model under the same 1 kHz firmware.

![The disturbance pulse and the recovery|900](assets/42325dae0e02.png)

| quantity | value |
| --- | --- |
| at rest before $t_{\mathrm{on}}$ | max angle change 0.0e+00 rad, cart 1.9e-18 m |
| swing-up time (all links inside 2° for good) | 2.38 s after $t_{\mathrm{on}}$ |
| catch (phase 2) | at 4.50 s |
| upright band from 0.1 s after the catch to the pulse | 0.097° (cart within 8.4 mm) |
| pulse: peak deflection of each link (deg) | 14.8, 6.7, 4.0 |
| pulse: peak cart travel | 0.226 m |
| recovery (all links inside 1° / 0.5° for good) | 1.36 s / 2.45 s after the pulse |
| last second | all links within 0.003° |
| peak motor voltage | 19.36 V of 24 V |
| peak cart travel | 0.300 m of the rail's 0.4 m |

## The design model against the bond graph

![Free swing: bond graph against the design ODE|900](assets/e4053357f77b.png)

The free swing of `pendulum-triple-cart-free` (1.5 s from rest at a pose far from equilibrium, motor shorted) agrees with the design ODE to **4.21e-04 rad** (cart: 2.2e-05 m). The residual is the stiff pivot ($O(1/k_t)$), the winding inductance, the belt and the pivot damping. The same design model produces the swing-up trajectory and the gains, which is why the bond-graph run tracks it.

## Acceptance checks (`expected.json`)

- hold: no motion and 0 V before $t_{\mathrm{on}}$; the phase signal [Ctrl/phase](signal:Ctrl/phase) is 0, 1, 2 at the three phases;
- swing-up: [Ctrl/th1](signal:Ctrl/th1), [Ctrl/th2](signal:Ctrl/th2), [Ctrl/th3](signal:Ctrl/th3) at three times match the design closed loop (tolerance 0.01 rad);
- balance: every link stays within 0.2° of upright from 0.1 s after the catch to the pulse, and the cart within 1 cm of the rail centre;
- disturbance: the peak deflections after the pulse are above the minimum (the pulse is real), the cart travel is bounded;
- recovery: back inside 0.5° after 2.4 s, within 0.2° and 1 cm over the last second;
- actuator and rail: $\lvert V \rvert \le 24$ V (peak 19.4 V), cart inside ±0.4 m (peak 0.300 m);
- the free-swing model against the design ODE at eight times (angles within 3e-3 rad, cart 2e-4 m);
- the scene bindings of the 3D view, and no diagnostics at all.
