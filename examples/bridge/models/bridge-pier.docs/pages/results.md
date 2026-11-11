# Results and checks

![Member forces, utilisations, deflections and the lorry, 40 t at 15 m/s|900](assets/8f51981aba36.png)

The 40 t lorry crosses the left span. Bar 27 reaches its Euler load of 153.95 kN at t = 1.6347 s, when the lorry is 14.5 m onto the bridge, and buckles; `Elost` books 263.1 J (its strain energy $P_{cr}^2 L_0 / (2 E A)$ = 263.6 J, less a small damping part). The shear of its panel moves to bar 26: 115 kN when bar 27 fails, then up to 326 kN (51 % of its strength; the quasi-static envelope without bar 27 gives 297 kN). Nothing else fails: the pier column peaks at 63 % of its buckling load, the roller stays on its seat, and the lorry leaves the bridge. `Ebal` changes by 5e-5 J.

![The same lorry at half strength: the bridge collapses|900](assets/4c3085c29029.png)

At `strength` 0.5 bar 27 buckles earlier (t = 0.887 s). The load it sheds is now too much: post 19 fails at t = 1.204 s, the bottom chords 3, 6 and 4 follow, the pier column buckles at t = 1.415 s, and the run stops at t = 1.950 s with the left span 3 m down.

| model | result | reference (`design/design_pier.py`) |
| --- | --- | --- |
| `bridge-pier-static` | bars 1, 9, 15, 20, 25, 27, 32: 90.34, -135.76, -117.33, -87.71, 149.48, -101.42, -233.59 kN; reactions 90.827, 40.835, 236.375 kN; deflection under the load -16.025 mm | stiffness method: 90.18, -135.80, -117.39, -87.65, 149.40, -101.45, -233.59 kN; 90.839, 40.839, 236.376 kN; -16.018 mm |
| `bridge-pier-modes` | 4.6159 Hz (FFT of the left span), the right span at -0.435 of the left; Ek 554.34 J; `Ebal` drift 2.2e-7 J | 4.61480 Hz, mode shape ratio -0.433; Ek 554.34 J |
| `bridge-pier`, 20 t | no failure; bar 27 at 0.768 | quasi-static 0.667 |

## Acceptance checks (`expected.json`)

- the static member forces, the three reactions and the deflection against the stiffness method;
- the first bending frequency against the eigenvalue problem, the kinetic energy against the mode shape, `Ebal` constant;
- bar 27 buckles at its Euler load, books its strain energy and is the only failure; its partner takes the load; the pier column stays below 70 %; the roller stays on its seat; both energy books are constant;
- with a 20 t lorry no bar fails; with `strength` 0.5 the pier column fails and the bridge collapses.
