@@ figures bridge-failure
{
  "diagram": {"kind": "diagram", "model": "bridge-failure"},
  "scene": {"kind": "scene", "model": "bridge-failure", "t": 2.45, "zoom": 14},
  "run": {
    "kind": "plot", "model": "bridge-failure",
    "rows": [
      {"ylabel": "member force [kN]", "series": [{"signal": "Truss/N[13]", "label": "bar 13 (undersized diagonal)", "scale": 0.001}, {"signal": "Truss/N[12]", "label": "bar 12 (end diagonal)", "scale": 0.001}, {"signal": "Truss/N[4]", "label": "bar 4 (bottom chord)", "scale": 0.001}], "hlines": [{"y": 240.64, "label": "Ft of bar 13"}], "legend": true},
      {"ylabel": "failed bars", "series": [{"signal": "Truss/nfail", "label": "Truss/nfail"}]},
      {"ylabel": "midspan y [m]", "series": [{"signal": "Truss/y[6]", "label": "Truss/y[6]"}]},
      {"ylabel": "axle load [kN]", "series": [{"signal": "Truck/fn[1]", "label": "front", "scale": 0.001}, {"signal": "Truck/fn[2]", "label": "rear", "scale": 0.001}], "legend": true}
    ]
  }
}
@@ page bridge-failure overview - | Overview
# Bridge: a diagonal that snaps

A 30 m Warren truss road bridge over a river: six 5 m panels, 4 m deep, with the deck on the bottom chord. One main truss is simulated. It carries half the deck and half the lorry, and the 3D view draws both trusses. The truss is one [Truss](block:Truss) block (`stdlib:planar/Truss2D`). Its nodes, bars and supports are matrices, and each of its 23 bars is a co-rotational axial bar that fails in tension at $F_t = f_y A$ and in compression at the Euler load.

The second diagonal from the left (bar 13, from top node 11 to bottom node 4) is **undersized**: 6.78 cm² instead of 20 cm², which is 1.4 times the quasi-static peak force of the 20 t lorry the bridge was checked for. An overloaded 40 t lorry ([Truck](block:Truck), driven at 15 m/s) snaps it, the second panel shears, and the bridge folds into the river. The run stops when the midspan has dropped 3 m ([Collapsed](block:Collapsed), a `StopSimulation`).

![The model canvas|900](@fig:diagram)

## What to try

- **Dashboard**: move the **Lorry mass** slider to 20000 kg. The gauge of bar 13 stays below 1 and no bar fails. Back at 40000 kg, try the **Lorry speed** slider: the load on bar 13 changes with speed, because the bounce from the abutment ramp arrives at different points of the span.
- **Plots**: "Member forces" shows bar 13 ([Truss/N[13]](signal:Truss/N[13])) climbing to its strength and dropping to zero when it fails; the other members take over its load until the bottom chord fails as well.
- **3D view**: play the run. Bars are coloured by their utilisation (blue compression, red tension, full colour at failure), and a failed bar is drawn snapped.

![3D view after the diagonal has failed|700](@fig:scene)

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
| deck | node 1 (-40, 0) and node 2 (-1, -0.06) are the left approach slab (fixed; it has settled 6 cm at the abutment), nodes 3 to 9 the bottom chord at x = 0, 5, ..., 30 (3 pinned, 9 on a roller), node 10 (70, 0) the right approach slab |
| bars | 1 to 6 bottom chord (30 cm²), 7 to 11 top chord (40 cm²), 12 to 23 diagonals (20 cm², bar 13 6.78 cm²) |
| steel | E = 210 GPa, ρ = 7850 kg/m³, f_y = 355 MPa, bar damping β = 1 ms |
| deck mass | 2500 kg per bottom-chord node (per truss) |

`Truss2D` lumps half the mass of every bar on each of its end nodes, adds the deck mass `mn`, and starts from the static dead-load deflection (the start values `ux`, `uy` from `design/design.py`), so the run begins at rest.

The lorry is the project block [Truck](block:Truck) (`library/Truck2D.jl`): half of the lorry (20 t of 40 t) as one `RigidBody2D` on a `PoseIntegrator2D`, two wheels on `DeckContact2D` (radius 0.5 m, 1.5 MN/m and 20 kN·s/m per axle, 4 m wheelbase) and the speed controller `Cruise`, which pushes through the tyre traction. The tyres are measured to the closest deck segment, so the wheels roll smoothly over the deck nodes and over the 6 cm ramp at the abutment. The ramp sets the lorry bouncing at about 2.8 Hz, which adds a dynamic load to the static weight.

The globals `v_truck` and `m_truck` (Model, Globals) set the speed and the mass; the starting height and momentum of the lorry follow from them.
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

For bar 13: $F_t$ = 355 MPa × 6.7786 cm² = 240.64 kN, and the energy it holds at failure is $F_t^2 L_0 / (2 E A)$ = 959.4 J.

The truss is statically determinate (26 joint equations, 23 bars and 3 reactions), so losing one bar makes its panel a mechanism. The other bars take the load for a short time while the panel shears, until the bottom chord fails too.
@@ page bridge-failure results overview | Results and checks
# Results and checks

![Member forces, failed bars, midspan and axle loads|900](@fig:run)

The overloaded lorry rolls onto the bridge over the 6 cm ramp and starts to bounce. Bar 13 reaches $F_t$ = 240.64 kN at t = 2.0126 s, when the lorry's centre is 5.2 m onto the bridge, and fails. `Elost` jumps by 959.2 J, its strain energy (959.4 J from $F_t^2 L_0 / (2 E A)$; the force at failure also has a small damping part). The second panel shears, the other members take its load for 0.6 s, and the bottom chord (bar 4) fails at t = 2.613 s. The run stops at t = 2.801 s with the midspan 3 m down. `Ebal` changes by less than 0.004 J over the run, against 248 kJ of work done by the lorry on the truss.

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
| `bridge-crossing` | 20 t at 10 m/s on the design bridge: no failure, largest utilisation 0.37 (bar 12) | quasi-static envelope: 0.31 |

The static member forces differ from the method of joints by up to 0.13 % of the largest force: the model is geometrically exact, and the deflected truss carries its load in a slightly different shape.

## Acceptance checks (`expected.json`)

- statics against the method of joints, the first bending frequency against the eigenvalue problem, and the energy balance of every model;
- the strut fails at the Euler load, at the expected time, and books its strain energy;
- the design bridge carries the 20 t lorry;
- bar 13 is the first and only failed bar for 0.5 s, fails at $F_t$, and `Elost` jumps by its strain energy; the run stops on the collapse;
- run overrides of the globals: a 20 t lorry at 15 and at 30 m/s loses no bar, a 28 t lorry loses bar 13.