# Results and checks

![Member forces, failed bars, roller travel, deflections and axle loads|900](assets/52cfb2c9d9e8.png)

The overloaded lorry rolls onto the bridge over the 6 cm ramp and starts to bounce. Bar 13 reaches $F_t$ = 240.64 kN at t = 2.0098 s, when the lorry's centre is 5.2 m onto the bridge, and fails. `Elost` jumps by 959.1 J, its strain energy (959.4 J from $F_t^2 L_0 / (2 E A)$; the force at failure also has a small damping part). The second panel shears and the truss folds about it, pulling the roller towards the river. At t = 2.4491 s its travel reaches the seat edge, -0.3 m, and it rolls off; the right end is 0.5 m down at t = 2.641 s. No other bar fails. The run stops at t = 2.818 s with the midspan 3 m down. The `Ebal` of the truss changes by less than 0.001 J over the run, and so does the seat's.

| lorry | 5 m/s | 10 m/s | 15 m/s | 30 m/s |
| --- | --- | --- | --- | --- |
| 20 t | 0.76 | 0.85 | 0.95 | 0.90 |
| 28 t | | | fails | |
| 40 t | fails | | fails | |

The table gives the largest utilisation of bar 13. The bounce from the ramp adds a load that depends on where the lorry is when it peaks, so it is not monotonic in the speed. The mass is the clear threshold: the diagonal holds the 20 t lorry at every speed, and at 15 m/s it fails between 25 and 28 t.

## The other models

| model | result | reference (`design/design.py`) |
| --- | --- | --- |
| `bridge-static` | bars 3, 9, 12, 13, 17: 308.99, -348.21, -143.90, 142.18, 74.07 kN; reactions 135.27 and 135.23 kN; midspan -28.881 mm | method of joints 308.80, -348.31, -143.92, 142.16, 74.53 kN; 135.25 kN; -28.875 mm (linear) |
| `bridge-modes` | 4.3990 Hz (FFT of the midspan), `Ebal` drift 1.7e-6 J | 4.39776 Hz (eigenvalues of K and M) |
| `bridge-moving-load` | largest midspan deflection 28.82 mm, top chord 347.75 kN | static, load at midspan: 28.87 mm, 348.31 kN |
| `strut-buckling` | fails at 5181.54 N at t = 0.05197 s, `Elost` 0.127849 J | Euler load 5181.54 N; $P_{cr}^2 L / (2 E A)$ = 0.127849 J |
| `bridge-crossing` | 20 t at 10 m/s on the design bridge: no failure, largest utilisation 0.370 (bar 12); the roller starts at 4.989 mm travel and stays within 10.6 mm | quasi-static envelope: 0.31; dead-load travel 4.989 mm |
| `bridge-crossing`, `strength` 0.4 and 0.3 | 0.924: holds; at 0.3 bar 12 buckles at t = 2.939 s, the roller rolls off at 3.394 s | 0.3696 / 0.4 = 0.924 |
| `bridge-pier` | a two-span truss on a pier: see its own docs | `design/design_pier.py` |

The static member forces differ from the method of joints by up to 0.13 % of the largest force: the model is geometrically exact, and the deflected truss carries its load in a slightly different shape.

## Acceptance checks (`expected.json`)

- statics against the method of joints, the first bending frequency against the eigenvalue problem, and the energy balance of every model;
- the strut fails at the Euler load, at the expected time, and books its strain energy;
- the design bridge carries the 20 t lorry and its roller stays on its seat; at `strength` 0.4 it still holds, at 0.3 it fails and falls;
- bar 13 is the first and only failed bar, fails at $F_t$, and `Elost` jumps by its strain energy; the roller rolls off when its travel reaches 0.3 m, the seat then carries nothing, and the right end falls; the run stops on the collapse;
- run overrides of the globals: a 20 t lorry at 15 and at 30 m/s loses no bar, a 28 t lorry loses bar 13.
