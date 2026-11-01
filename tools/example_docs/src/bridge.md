@@ figures bridge-failure
{
  "diagram": {"kind": "diagram", "model": "bridge-failure"},
  "scene": {"kind": "scene", "model": "bridge-failure", "t": 2.7, "zoom": 14},
  "run": {
    "kind": "plot", "model": "bridge-failure",
    "rows": [
      {"ylabel": "member force [kN]", "series": [{"signal": "Truss/N[13]", "label": "bar 13 (undersized diagonal)", "scale": 0.001}, {"signal": "Truss/N[12]", "label": "bar 12 (end diagonal)", "scale": 0.001}, {"signal": "Truss/N[4]", "label": "bar 4 (bottom chord)", "scale": 0.001}], "hlines": [{"y": 240.64, "label": "Ft of bar 13"}], "legend": true},
      {"ylabel": "failed bars", "series": [{"signal": "Truss/nfail", "label": "Truss/nfail"}, {"signal": "Seat/unseated", "label": "roller off its seat"}], "legend": true},
      {"ylabel": "roller travel [m]", "series": [{"signal": "Seat/travel", "label": "Seat/travel"}], "hlines": [{"y": -0.3, "label": "seat edge"}]},
      {"ylabel": "y [m]", "series": [{"signal": "Truss/y[6]", "label": "midspan"}, {"signal": "Truss/y[9]", "label": "right end (roller)"}], "legend": true},
      {"ylabel": "axle load [kN]", "series": [{"signal": "Truck/fn[1]", "label": "front", "scale": 0.001}, {"signal": "Truck/fn[2]", "label": "rear", "scale": 0.001}], "legend": true}
    ]
  }
}
@@ page bridge-failure overview - | Overview
# Bridge: a diagonal that snaps

A 30 m Warren truss road bridge over a river: six 5 m panels, 4 m deep, with the deck on the bottom chord. One main truss is simulated. It carries half the deck and half the lorry, and the 3D view draws both trusses. The truss is one [Truss](block:Truss) block (`stdlib:planar/Truss2D`). Its nodes, bars and supports are matrices, and each of its 23 bars is a co-rotational axial bar that fails in tension at $F_t = f_y A$ and in compression at the Euler load. The roller bearing at the right end sits on a seat of finite length ([Seat](block:Seat)).

The second diagonal from the left (bar 13, from top node 11 to bottom node 4) is **undersized**: 6.78 cm² instead of 20 cm², which is 1.4 times the quasi-static peak force of the 20 t lorry the bridge was checked for. An overloaded 40 t lorry ([Truck](block:Truck), driven at 15 m/s) snaps it, the second panel shears, the folding truss pulls the roller off its seat, and the bridge falls into the river. The run stops when the midspan has dropped 3 m ([Collapsed](block:Collapsed), a `StopSimulation`).

![The model canvas|900](@fig:diagram)

## What to try

- **Dashboard**: move the **Lorry mass** slider to 20000 kg. The gauge stays below 1 and no bar fails. Back at 40000 kg, try the **Lorry speed** slider: the load on bar 13 changes with speed, because the bounce from the abutment ramp arrives at different points of the span. The **Strength** slider scales the strength of every member (the global `strength`): from about 1.15 the 40 t lorry crosses (at 1.6 bar 13 peaks at 0.71).
- **Plots**: "Member forces" shows bar 13 ([Truss/N[13]](signal:Truss/N[13])) climbing to its strength and dropping to zero when it fails; "Roller" shows the roller's travel along its seat ([Seat/travel](signal:Seat/travel)) until it rolls off.
- **3D view**: play the run. Bars are coloured by their utilisation (blue compression, red tension, full colour at failure), a failed bar is drawn snapped, and the roller's seats turn red when it rolls off.

![3D view: the diagonal has failed and the right end has fallen off its seat|700](@fig:scene)

Continue with [the structure](page:structure), [failure](page:failure) and [the results](page:results).
@@ page bridge-failure structure overview | Structure and lorry
# Structure and lorry

```
           11 ------ 12 ------ 13 ------ 14 ------ 15 ------ 16        top chord, y = 4 m
          /  \      /  \      /  \      /  \      /  \      /  \
  1 ... 2 -- 3 ----- 4 ----- 5 ----- 6 ----- 7 ----- 8 ----- 9 ... 10   deck, nodes 1..10
```

| item | value |
| --- | --- |
| nodes | 16: deck nodes 1 to 10 first (left to right), then the top chord 11 to 16 |
| deck | node 1 (-40, 0) and node 2 (-1, -0.06) are the left approach slab (fixed; it has settled 6 cm at the abutment), nodes 3 to 9 the bottom chord at x = 0, 5, ..., 30 (3 pinned, 9 on a roller seat), node 10 (70, 0) the right approach slab |
| bars | 1 to 6 bottom chord (30 cm²), 7 to 11 top chord (40 cm²), 12 to 23 diagonals (20 cm², bar 13 6.78 cm²) |
| steel | E = 210 GPa, ρ = 7850 kg/m³, f_y = 355 MPa × `strength`, bar damping β = 1 ms |
| deck mass | 2500 kg per bottom-chord node (per truss) |
| roller seat | 0.3 m to either edge, 2 GN/m |

`Truss2D` lumps half the mass of every bar on each of its end nodes, adds the deck mass `mn`, and starts from the static dead-load deflection (the start values `ux`, `uy` from `design/design.py`), so the run begins at rest.

The lorry is the project block [Truck](block:Truck) (`library/Truck2D.jl`): half of the lorry (20 t of 40 t) as one `RigidBody2D` on a `PoseIntegrator2D`, two wheels on `DeckContact2D` (radius 0.5 m, 1.5 MN/m and 20 kN·s/m per axle, 4 m wheelbase) and the speed controller `Cruise`, which pushes through the tyre traction. The tyres are measured to the closest deck segment, so the wheels roll smoothly over the deck nodes and over the 6 cm ramp at the abutment. The ramp sets the lorry bouncing at about 2.8 Hz, which adds a dynamic load to the static weight.

The globals `v_truck`, `m_truck` and `strength` (Model, Globals) set the speed, the mass and the member strength; the starting height and momentum of the lorry follow from the first two.
@@ page bridge-failure failure overview | Member failure
# Member failure

Every bar of `Truss2D` has its force

$$N = (1 - b)\,\frac{E A}{L_0}\,\left(L - L_0 + \beta \dot L\right),$$

with $L$ the current distance between its nodes, $L_0$ the distance at the start and $b$ the held failure flag. Two events per bar (a `for` loop around `@events`) set $b = 1$:

- tension: $N > F_t = f_y A$
- compression: $-N > P_{cr} = \pi^2 E I / (K L_0)^2$ (Euler buckling)

A failed bar carries no force for the rest of the run: the model is **elastic-brittle, also in compression**. The strain energy the bar held at that instant is booked in `Elost`, so

$$E_{bal} = E_k + E_e + E_g + E_{dis} + E_{lost} - W_{ext}$$

stays constant through every failure. The utilisation `util` is $N/F_t$ in tension and $N/P_{cr}$ in compression, so the failure is at $\pm 1$.

The global `strength` sets $f_y$ = 355 MPa × `strength` and $K = 1/\sqrt{\text{strength}}$, so $F_t$ and every $P_{cr}$ scale with it and the stiffness does not: every utilisation scales with 1/`strength`.

For bar 13: $F_t$ = 355 MPa × 6.7786 cm² = 240.64 kN, and the energy it holds at failure is $F_t^2 L_0 / (2 E A)$ = 959.4 J.

## The roller seat

Node 9 is free in the truss (`fix` [0 0]). The project block [Seat](block:Seat) (`library/RollerSeat.jl`) carries it: the node rolls freely along the seat, and the seat pushes it up with

$$R = (1 - u)\,k\,\max(y_0 - y_9,\,0),$$

so it pushes but never pulls. When the roll $|x_9 - x_0|$ exceeds the seat length (0.3 m to either edge), an event latches the held flag $u$ (`Seat/unseated`): the seat carries nothing from then on and the end falls. The seat books its own energy, $E_s + E_{lost} + W$ (spring energy, the spring energy at the instant of unseating, and its work on the truss) is constant, and the truss counts the seat force in its $W_{ext}$.

The truss is statically determinate (26 joint equations, 23 bars and 3 reactions), so losing one bar makes its panel a mechanism. The truss folds about the sheared panel, which pulls the roller towards the river, off its seat.
@@ page bridge-failure results overview | Results and checks
# Results and checks

![Member forces, failed bars, roller travel, deflections and axle loads|900](@fig:run)

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
@@ figures bridge-pier
{
  "diagram": {"kind": "diagram", "model": "bridge-pier"},
  "scene": {"kind": "scene", "model": "bridge-pier", "t": 2.4, "zoom": 12},
  "run": {
    "kind": "plot", "model": "bridge-pier",
    "rows": [
      {"ylabel": "member force [kN]", "series": [{"signal": "Truss/N[27]", "label": "bar 27 (slender diagonal)", "scale": 0.001}, {"signal": "Truss/N[26]", "label": "bar 26 (its X-partner)", "scale": 0.001}, {"signal": "Truss/N[32]", "label": "bar 32 (pier column)", "scale": 0.001}], "hlines": [{"y": -153.95, "label": "-Pcr of bar 27"}], "legend": true},
      {"ylabel": "utilisation", "series": [{"signal": "Truss/util[27]", "label": "bar 27"}, {"signal": "Truss/util[26]", "label": "bar 26"}, {"signal": "Truss/util[32]", "label": "pier column"}, {"signal": "Peak/peak", "label": "peak of all bars"}], "legend": true},
      {"ylabel": "y [m]", "series": [{"signal": "Truss/y[5]", "label": "left span"}, {"signal": "Truss/y[7]", "label": "pier"}, {"signal": "Truss/y[9]", "label": "right span"}], "legend": true},
      {"ylabel": "lorry x [m]", "series": [{"signal": "Truck/g[2]", "label": "Truck/g[2]"}]}
    ]
  },
  "collapse": {
    "kind": "plot", "model": "bridge-pier", "overrides": {"global:strength": 0.5},
    "rows": [
      {"ylabel": "failed bars", "series": [{"signal": "Truss/nfail", "label": "Truss/nfail"}]},
      {"ylabel": "member force [kN]", "series": [{"signal": "Truss/N[27]", "label": "bar 27", "scale": 0.001}, {"signal": "Truss/N[19]", "label": "bar 19 (post)", "scale": 0.001}, {"signal": "Truss/N[32]", "label": "bar 32 (pier column)", "scale": 0.001}], "legend": true},
      {"ylabel": "y [m]", "series": [{"signal": "Truss/y[5]", "label": "left span"}, {"signal": "Truss/y[7]", "label": "pier"}, {"signal": "Truss/y[9]", "label": "right span"}], "legend": true}
    ]
  }
}
@@ page bridge-pier overview - | Overview
# Bridge on a pier: a buckled diagonal and a redundant truss

A truss road bridge of two 24 m spans, continuous over a 12 m steel column in the river. Eight 6 m panels, 5 m deep at the abutments and 7 m over the pier. One main truss is simulated (it carries half the deck and half the lorry), and the 3D view draws both. The truss is one [Truss](block:Truss) block (`stdlib:planar/Truss2D`) of 20 nodes and 32 bars, the pier column among them.

The two panels next to the pier are X-braced, so the truss is **statically indeterminate**: 32 bars and 5 reaction components for 17 truss nodes leave 3 redundants. One failed member need not bring it down. Diagonal 27 (top node 15 to node 7 on the pier) is **too slender**: its buckling capacity is 0.35 of the design section's (global `slender`). It holds a 20 t lorry, but an overloaded 40 t lorry ([Truck](block:Truck), 15 m/s) buckles it. Its X-partner (bar 26) then carries the panel's shear alone, nothing else fails, and the lorry crosses.

![The model canvas|900](@fig:diagram)

## What to try

- **Dashboard**: play the default run: the **A member failed** indicator turns on when bar 27 buckles, the gauge reads 1.0 (bar 27) and the **Bridge collapsed** indicator stays off.
- Move **Member strength** to 0.5: the redistributed load is too much, a post and the bottom chord next to bar 27 fail, then the pier column buckles and the bridge collapses.
- Move **Lorry mass** to 20000 kg: bar 27 holds at 77 % of its buckling load. Move **Diagonal 27: buckling capacity** to 1.0 for the design bridge.
- **3D view**: bars are coloured by their utilisation (blue compression, red tension), a failed bar is drawn snapped, and the roller's seats turn red if it rolls off.

![3D view: bar 27 has buckled, the lorry crosses the pier|700](@fig:scene)

Continue with [the structure](page:structure) and [the results](page:results). The member failure and the roller seat work as in `bridge-failure`.
@@ page bridge-pier structure overview | Structure
# Structure

| item | value |
| --- | --- |
| nodes | 20: the deck nodes 1 to 12 first (1, 2 and 12 the approach slabs; 3 to 11 the bottom chord at x = 0, 6, ..., 48), then the top chord 13 to 19 at x = 6, ..., 42 and the pier foot 20 at (24, -12) |
| depth | $h(x) = 5 + 2\,(1 - \lvert x - 24\rvert / 18)^2$ m at the top-chord nodes: 5 m at the end posts, 7 m over the pier |
| supports | node 3 pinned, node 11 on a roller seat ([Seat](block:Seat), 0.3 m to either edge), the pier foot 20 pinned |
| bars | 1 to 8 bottom chord (16 cm²), 9 to 14 top chord (20 cm²), 15 and 16 inclined end posts, 17 to 23 posts (20 over the pier), 24 to 31 diagonals (X-braced 26/27 and 28/29 next to the pier), 32 the pier column (60 cm², I = 4.3e-5 m⁴) |
| slender diagonal | bar 27: A = 18 cm², I = 0.35 × 1.5e-5 m⁴, $P_{cr}$ = 153.95 kN |
| steel | E = 210 GPa, ρ = 7850 kg/m³, f_y = 355 MPa × `strength`, β = 1 ms |
| mass | 27.0 t per truss (bars and its half of the deck) |

The reference numbers come from `design/design_pier.py`: the stiffness method for the statics (the truss is indeterminate, so the method of joints does not apply), the eigenvalue problem of the stiffness and lumped mass matrices for the modes, and a quasi-static lorry envelope with and without bar 27.

| quasi-static envelope | 20 t | 40 t |
| --- | --- | --- |
| design bridge, largest utilisation | 0.418 (pier column) | 0.570 (pier column) |
| bar 27, slender | 0.667 | 1.008 |
| without bar 27, largest utilisation | | 0.569 (post 19) |
@@ page bridge-pier results overview | Results and checks
# Results and checks

![Member forces, utilisations, deflections and the lorry, 40 t at 15 m/s|900](@fig:run)

The 40 t lorry crosses the left span. Bar 27 reaches its Euler load of 153.95 kN at t = 1.6347 s, when the lorry is 14.5 m onto the bridge, and buckles; `Elost` books 263.1 J (its strain energy $P_{cr}^2 L_0 / (2 E A)$ = 263.6 J, less a small damping part). The shear of its panel moves to bar 26: 115 kN when bar 27 fails, then up to 326 kN (51 % of its strength; the quasi-static envelope without bar 27 gives 297 kN). Nothing else fails: the pier column peaks at 63 % of its buckling load, the roller stays on its seat, and the lorry leaves the bridge. `Ebal` changes by 5e-5 J.

![The same lorry at half strength: the bridge collapses|900](@fig:collapse)

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
