# Results and checks

![Angle, cart position and force of the nominal run|900](assets/eee1253560e5.png)

`design/design.py` integrates the non-linear closed loop independently (RK4, 0.1 ms, same law and clamp, but **continuous**); the model runs the 1 ms sampled controller. They agree to about 2 % in the fast recovery and the step, and to better than 0.5 % once settled. The zero-order hold shows in the initial recovery: at $t = 0.2$ s $\theta$ is about 4 % further along than the continuous reference, which is why that one cursor check carries 2.5 mrad.

| quantity | design.py (continuous) | bond graph run (1 ms hold), README |
| --- | --- | --- |
| peak $\lvert u\rvert$ (at 1.5 s) | 17.865 N | 17.877 N |
| $\theta$ over $[2.9, 3.0]$ s | 0.442 deg | 0.408 deg |
| $x(3.0\ \mathrm{s})$ (reference 0.2 m) | 0.19822 m | 0.19918 m |
| $\theta$ over $[3.5, 4.0]$ s | 0.058 deg | 0.042 deg |
| peak $\lvert\theta\rvert$ (during the step) | 6.86 deg | 6.94 deg |

## Acceptance checks (`expected.json`, 17 checks)

- the force $\lvert u \rvert$ peaks at 17.8647 N (tolerance 0.02), below the 20 N limit; the angle never exceeds the initial 0.1 rad (tolerance 1e-4) and the cart stays within 0.2 m + 1 cm;
- cursor values against the design reference: [XInt/y](signal:XInt/y) 0.086922 m at 0.2 s (tolerance 3 mm), 0.001005 at 1.45 s (1 mm), 0.096652 at 2.0 s (4 mm), 0.198217 at 3.0 s (2 mm), 0.199744 at 3.5 s and 0.199963 at 4.0 s (1 mm); [ThetaInt/y](signal:ThetaInt/y) -0.054606 at 0.2 s (2.5 mrad), 0.0028751 at 1.45 s and -0.0055751 at 3.0 s (1.5 mrad);
- recovered before the step: $\lvert x\rvert < 1$ cm and $\lvert\theta\rvert < 0.5$ deg over $[1.3, 1.45]$ s;
- settled after the step: $\lvert\theta\rvert < 0.5$ deg over $[2.9, 3.0]$ s and $< 0.1$ deg over $[3.5, 4.0]$ s;
- the scene binding is verified by forward kinematics of the pendulum tip (`scene_bindings` with `fk`, tolerance 1e-6);
- no E901, E106, W202 or W206.

The `W201`/`W205` warnings of the run are expected, see [the plant page](page:plant).
