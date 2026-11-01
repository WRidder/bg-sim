# bridge: truss road bridges, a lorry and members that fail

Two truss road bridges over a river, each with a lorry that can be too heavy for it:

- a **30 m Warren truss** (six 5 m panels, 4 m deep). It is statically determinate, so one failed bar brings it down;
- a **2 x 24 m continuous truss on a centre pier** (eight 6 m panels, 5 m deep at the abutments, 7 m over the pier, a 12 m steel column in the river). It is statically indeterminate, so it can lose a member and stay up.

One main truss of each bridge is simulated (it carries half the deck and half the lorry); the 3D view draws both. The truss is one `stdlib:planar/Truss2D` block. Its node positions, bars and supports are matrix parameters and constants, every bar is a co-rotational axial bar that can fail, and the lorry is a planar rigid body on compliant tyres that rolls on the deck. The roller bearing sits on a seat of finite length (`RollerSeat`), so a bridge whose end is pulled too far falls off it.

## The Warren truss

```
           11 -------- 12 -------- 13 -------- 14 -------- 15 -------- 16          top chord, y = 4 m
          /  \        /  \        /  \        /  \        /  \        /  \
         /    \      /    \      /    \      /    \      /    \      /    \       diagonals 12..23
  1 ... 2 --- 3 ----- 4 ----- 5 ----- 6 ----- 7 ----- 8 ----- 9 ... 10             deck: nodes 1..10
 (-40,0) (-1,-0.06) x=0  (13 = 11->4)                             x=30  (70,0)
         settled   pinned                                       roller on a seat
```

Nodes 1, 2 and 10 are the approach slabs (fixed). They belong to the deck polyline, so the lorry drives on and off the bridge. The left slab has settled 6 cm at the abutment (node 2), so a lorry meets a short ramp onto the bridge: that bump makes it bounce, which is the dynamic load of the crossing models. Bar 13, the second diagonal from the left (top node 11 to bottom node 4), is the member that is undersized in the failure model.

## The two-span truss on a pier

```
                  13------14------15------16------17------18------19         top chord: 5 m deep at the ends, 7 m at 16
                / | \     |     / | \   / | \   / | \     |     / | \
            /     |     \ | /     | /   \ | /   \ |     \ | /     |     \
  1 .. 2  3-------4-------5-------6-------7-------8-------9-------10------11  .. 12   deck: nodes 1..12
          x=0                             | pier column (bar 32)          x=48
          pinned                          |                               roller on a seat
                                         20  foot (24, -12), pinned
```

Nodes 3 to 11 are the bottom chord at x = 0, 6, ..., 48, nodes 13 to 19 the top chord, node 20 the foot of the pier column. Bars 1 to 8 are the bottom chord, 9 to 14 the top chord, 15 and 16 the inclined end posts, 17 to 23 the posts (20 is the post over the pier), 24 to 31 the diagonals (Pratt, with both diagonals in the two panels next to the pier) and 32 the pier column. With 17 truss nodes, 32 bars and 5 reaction components the truss has **3 redundants**: the X-braced panels give two, the pier one.

Bar 27 (top node 15 to bottom node 7 on the pier, the compressed diagonal of the left pier panel) is **too slender** in `bridge-pier`: its second moment is 0.35 times the design section's (global `slender`), so it buckles at 153.95 kN instead of 439.9 kN. It holds a 20 t lorry (quasi-static utilisation 0.667), but the overloaded 40 t lorry buckles it (1.008). Its X-partner, bar 26, then carries the shear of the panel alone, and the truss carries on: without bar 27 the largest utilisation under the 40 t lorry is 0.57 (quasi-static, `design_pier.py`).

## Models

| model | what it shows |
| --- | --- |
| `bridge-failure` | **Warren, with a dashboard.** Bar 13 is undersized (A = 6.78 cm², Ft = 240.6 kN, 1.4 times the quasi-static peak force of a 20 t lorry). It holds the 20 t lorry at any speed, but an overloaded 40 t lorry at 15 m/s snaps it at t = 2.010 s, the second panel shears, the folding truss pulls the roller off its seat at t = 2.449 s, and the bridge falls. The run stops when the midspan has dropped 3 m (`Collapsed`, a `StopSimulation`). |
| `bridge-crossing` | **Warren, with a dashboard.** The design bridge (all diagonals 20 cm²) and a 20 t lorry at 10 m/s: every member stays below 37 % of its strength. The `strength` slider scales the strength of every member: it holds down to 0.4, and at 0.3 the end diagonal buckles and the bridge falls. |
| `bridge-static` | Warren: dead load plus a 100 kN point load at midspan: member forces and reactions against the method of joints |
| `bridge-modes` | Warren: free vibration in the first vertical bending mode (no damping): frequency against the eigenvalue problem, energy balance |
| `bridge-moving-load` | Warren: a point load crossing (dashboard sliders for its size and speed): influence lines of the member forces |
| `bridge-pier` | **Pier, with a dashboard.** The 40 t lorry at 15 m/s buckles the slender diagonal 27 at t = 1.635 s; its partner takes the load, nothing else fails, and the lorry crosses. With `strength` 0.5 the redistributed load is too much: a post and the bottom chord next to bar 27 fail, the pier column buckles at t = 1.415 s, and the bridge collapses. |
| `bridge-pier-static` | Pier: dead load plus 100 kN in the middle of the left span: member forces, reactions and deflection against the stiffness method |
| `bridge-pier-modes` | Pier: free vibration in the first bending mode, in which the spans swing in opposite directions: frequency against the eigenvalue problem, kinetic energy, energy balance |
| `strut-buckling` | one `Bar2D` strut between two `PinNode2D` nodes, pushed by a growing force: it fails at the Euler load |

## Dashboards and globals

| global | used in | meaning |
| --- | --- | --- |
| `strength` (1.0) | `bridge-crossing`, `bridge-failure`, `bridge-pier` | scales the strength of every member: `fy = 3.55e8*strength` and `K = 1/sqrt(strength)`, so the tensile strength and every Euler load scale with it and the stiffness does not change. At 1.0 the results are those of the design. |
| `slender` (0.35) | `bridge-pier` | the buckling capacity of bar 27, as a fraction of the design section (`I = 1.5e-5*slender`) |
| `m_truck`, `v_truck` | the lorry models | the lorry's mass (40 t in `bridge-failure` and `bridge-pier`, 20 t in `bridge-crossing`) and speed; the start height and momentum follow from them |

The dashboards of `bridge-crossing`, `bridge-failure` and `bridge-pier` have sliders for these globals and run the model again on every change (`autoRerun`). A gauge shows the peak utilisation of the run (`Peak`, the project block `PeakUtil`: a smooth peak hold of the largest |util| of all bars), indicators show a failed member, the roller off its seat and the collapse, and plots show the member forces, the utilisations, the deflections and the lorry's position, speed and axle loads. `bridge-moving-load` has sliders for the point load and its speed, and `bridge-static`, `bridge-modes`, `bridge-pier-static` and `bridge-pier-modes` show their reference numbers next to the measured ones.

## Blocks

| block | where | role |
| --- | --- | --- |
| `Truss2D` | `stdlib:planar` | the whole truss: constants `nn`, `nb`, `conn` (nb x 2), `fix` (nn x 2); parameters `xy` (nn x 2), `A`, `I`, `mn`, `E`, `rho`, `fy`, `K`, `beta`, `g0`. One failure event pair per bar (a `for` loop around `@events`). |
| `MovingLoad2D` | `stdlib:planar` | a point load moving along the deck nodes 1..nd |
| `DeckContact2D` | `stdlib:planar` | wheels of a planar body on the deck: Hunt-Crossley tyres measured to the closest deck segment, a drive traction, the reactions on the deck nodes |
| `Bar2D`, `PinNode2D` | `stdlib:planar` | the same bar and node as single blocks (the buckling model) |
| `Truck2D` | `library/` | the lorry: `RigidBody2D` on a `PoseIntegrator2D`, `DeckContact2D` with one wheel per axle, `Cruise` and the 3D pose `PlanarPose3D` |
| `Cruise` | `library/` | speed control F = m/tau (v_set - v), applied as tyre traction |
| `PlanarPose3D` | `library/` | the planar pose as a 3D pose (the model's x-y plane is the world x-z plane) and the wheel angle |
| `RollerSeat` | `library/` | the roller bearing on a seat of finite length (see below) |
| `PeakUtil` | `library/` | the largest utilisation of the run so far, for the dashboard gauge |

## Failure behaviour

A bar fails in tension when N > Ft = fy A and in compression when -N > Pcr = pi^2 E I / (K L0)^2 (Euler). The failure is an event that sets the held flag `failed[k]` (`ddt(broken) ~ 0`, `reinit`), so a failed bar carries no force from then on: **elastic-brittle, also in compression**. A real strut keeps a post-buckling load. This model drops it to zero, which is the simplest behaviour that conserves the energy book: the strain energy a bar held at the instant it failed goes to `Elost`, and `Ebal = Ek + Ee + Eg + Edis + Elost - Wext` stays constant through every failure.

**The roller seat.** In the lorry models the roller node (9 of the Warren truss, 11 of the pier truss) is free in the truss (`fix` [0 0]) and carried by `RollerSeat`, which sits in the force path from the lorry to the truss:

- the node rolls freely along the seat; `travel = x[node] - x0` is its roll from the seat centre (the node's rest place);
- the seat pushes up with `R = k max(y0 - y[node], 0)` (k = 2e9 N/m): it pushes but never pulls, so the end can lift off;
- when |travel| exceeds the seat length (0.3 m to either edge) an event latches the held flag `unseated`, and from then on R = 0: the end falls;
- the seat books its own energy: the spring energy `Es`, the work `W` it does on the truss (the truss counts it in its `Wext`) and the spring energy it held at the instant of unseating (`Elost`). `Seat/Ebal = Es + Elost + W` is constant, and the truss's `Ebal` stays constant through the unseating.

The node starts at its seated equilibrium (uy = -R/k, 43 µm for the Warren truss) and at its dead-load travel (4.99 mm for the Warren truss), so the runs start at rest.

The Warren truss is statically determinate (2 x 13 joint equations = 23 bars + 3 reactions), so losing one bar turns its panel into a mechanism: in `bridge-failure` bar 13 fails alone, the second panel shears, the truss folds about it and pulls the roller 0.3 m towards the river, off its seat (t = 2.449 s, 0.44 s after bar 13). The right end then falls: 0.5 m down at t = 2.641 s. No other bar fails.

The pier truss has 3 redundants. When bar 27 buckles, the load in its panel takes another path (its X-partner 26: 115 kN at the instant bar 27 fails, then up to 326 kN, 51 % of its strength), and no other bar fails. At half strength the same redistribution overloads the post and the bottom chord next to bar 27, the pier column buckles, and the left span drops 3 m at t = 1.950 s; the roller rolls 0.15 m but stays on its seat.

## Numbers

All reference numbers come from `design/design.py` and `design/design_pier.py` (numpy only, no bg-sim code).

Warren truss:

| check | reference | simulation |
| --- | --- | --- |
| static member forces, dead + 100 kN at midspan (bars 3, 9, 12, 13, 17) | 308.80, -348.31, -143.92, 142.16, 74.53 kN (method of joints) | 308.99, -348.21, -143.90, 142.18, 74.07 kN (largest difference 0.13 % of the largest force: the deformed geometry) |
| support reactions | 135.250 kN each | 135.268 and 135.234 kN |
| midspan deflection, dead + 100 kN | -28.875 mm (linear) | -28.881 mm |
| first vertical bending frequency | 4.39776 Hz (eigenvalues of K, M) | 4.3990 Hz (FFT of the midspan deflection) |
| energy balance, free vibration | constant | drift 1.7e-6 J of 94 J kinetic energy |
| Euler load of the strut (2 m, I = 1e-8 m^4) | 5181.54 N | fails at 5181.54 N, t = 0.05197 s |
| strain energy lost at buckling | Pcr^2 L / (2 E A) = 0.127849 J | 0.127849 J |
| roller travel at the start (dead load) | ux[9] = 4.989 mm (stiffness solve) | 4.989 mm |
| bar 13 in `bridge-failure` (40 t, 15 m/s) | Ft = 240.6 kN; strain energy Ft² L0 / (2 E A) = 959.4 J | fails at 240.6 kN at t = 2.0098 s (lorry at x = 5.2 m); `Elost` jumps by 959.1 J |
| roller unseats in `bridge-failure` | travel = seat length 0.3 m | travel -0.3000 m at t = 2.4491 s; R = 0 afterwards; `Seat/Ebal` drift 4.5e-4 J |
| `strength` in `bridge-crossing` | utilisations scale with 1/strength: 0.3696 / 0.4 = 0.924 | 0.924 at strength 0.4 (holds); at 0.3 bar 12 buckles at t = 2.939 s |

Pier truss:

| check | reference (stiffness method) | simulation |
| --- | --- | --- |
| static member forces, dead + 100 kN at x = 12 m (bars 1, 9, 15, 20, 25, 27, 32) | 90.18, -135.80, -117.39, -87.65, 149.40, -101.45, -233.59 kN | 90.34, -135.76, -117.33, -87.71, 149.48, -101.42, -233.59 kN (largest difference over all bars 323 N, 0.14 % of the largest force) |
| support reactions (left abutment, right abutment, pier) | 90.839, 40.839, 236.376 kN | 90.827, 40.835, 236.375 kN |
| deflection under the load | -16.018 mm | -16.025 mm |
| first bending frequency | 4.61480 Hz; right span / left span -0.433 | 4.6159 Hz (FFT of y[5]); amplitude ratio 0.435 |
| kinetic energy at 5 mm in the first mode | (omega a)² phi^T M phi / 2 = 554.34 J | 554.34 J; `Ebal` drift 2.2e-7 J |
| bar 27 in `bridge-pier` (40 t, 15 m/s) | Pcr = 153.95 kN; strain energy 263.6 J; quasi-static utilisation 1.008 | buckles at 153.95 kN at t = 1.6347 s (lorry at x = 14.5 m); `Elost` 263.1 J; nothing else fails |
| bar 26 after bar 27 has gone (40 t) | 297.1 kN (quasi-static envelope without bar 27) | 325.9 kN (dynamic factor 1.10) |
| bar 27 under the 20 t lorry | quasi-static utilisation 0.667 | 0.768 (dynamic factor 1.15), no failure |
| `strength` 0.5 | | bar 27 at t = 0.887 s, post 19 at 1.204 s, bottom chords 3, 6, 4, pier column 32 at 1.415 s; run stops at 1.950 s |

Warren crossing results (largest utilisation of the undersized bar 13 in `bridge-failure`; "fails" means it reached 1):

| lorry | 5 m/s | 10 m/s | 15 m/s | 30 m/s |
| --- | --- | --- | --- | --- |
| 20 t | 0.76 | 0.85 | 0.95 | 0.90 |
| 28 t | | | fails | |
| 40 t | fails | | fails | |

The lorry starts to bounce at the abutment ramp (about 2.8 Hz on its tyres), and the bounce adds a dynamic load that depends on where the lorry is when it peaks, so the load is not monotonic in the speed: at 20 t it is largest near 15 m/s. The mass is the clear threshold: the diagonal holds the 20 t lorry at every speed up to 30 m/s, and at 15 m/s it fails between 25 and 28 t.

## 3D view

`scenes/bridge.sdf` (with the lorry) and `scenes/bridge-load.sdf` (the point-load models) are written by `design/build_scene.py`, `scenes/bridge-pier.sdf` and `scenes/bridge-pier-load.sdf` by `design/build_pier.py`. Every bar of both trusses is a cylinder at its rest place with a `segment` binding on its two end nodes (`Truss/x[a]`, `Truss/y[a]`, `Truss/x[b]`, `Truss/y[b]`, plane `xz`), a `color` binding on `Truss/util[k]` (coolwarm, -1 to 1: blue compression, red tension, full colour at failure), and the broken signal `Truss/failed[k]` drawn **snapped**. The deck slabs are boxes with segment bindings between the deck nodes. The bearing seats are 0.6 m long boxes on the abutments; in the lorry models the roller's seats turn red (`Seat/unseated`) when it rolls off. The pier column is a thicker cylinder with a footing in the riverbed. The lorry is one link posed by `Truck/q` (`PlanarPose3D`), with four wheel joints `axle_*` on `Truck/wheel`.

## Checks (`expected.json`)

- no E101/E102/W201/W202 diagnostics; every scene binding resolves
- statics of both bridges: member forces and reactions against the method of joints and the stiffness method
- the first bending frequency (FFT) of both bridges against the eigenvalue problem; `Ebal` constant without damping; the pier's kinetic energy against the mode shape
- the moving load: largest midspan deflection and the largest force in bar 13
- the strut fails at the Euler load at the expected time and books Pcr^2 L / (2 E A)
- the design bridge under the 20 t lorry: no bar fails, the roller starts at its dead-load travel and stays on its seat, both energy books constant; with `strength` 0.4 it still holds at 1/0.4 the utilisation, with 0.3 it fails, unseats and collapses (run overrides of the globals)
- the failure model: bar 13 is the first and only failed bar, it fails at Ft, `Elost` jumps by its strain energy, the roller unseats when its travel reaches 0.3 m, the seat then carries nothing and the right end falls, `Ebal` stays constant, and the run stops on the collapse; the same model with a 20 t lorry at 15 and 30 m/s loses no bar, and with 28 t it loses bar 13
- the pier bridge: bar 27 buckles at its Euler load and books its strain energy, it is the only failure, its partner takes the load, the pier column stays below 70 %; with 20 t no bar fails; with `strength` 0.5 the pier column fails and the bridge collapses

## Files

| file | content |
| --- | --- |
| `design/design.py` | the independent numbers of the Warren truss: geometry, lumped masses, method of joints, eigenfrequencies, the quasi-static vehicle envelope; writes `design.json` |
| `design/design_pier.py` | the same for the pier truss with the stiffness method (it is statically indeterminate), the slender diagonal and the envelope without it; writes `design_pier.json` |
| `design/build_scene.py` | the two Warren scenes and the bindings |
| `design/build_model.py` | the six Warren models from `design.json` |
| `design/build_pier.py` | the two pier scenes and the three pier models from `design_pier.json` |
| `library/` | `Truck2D`, `Cruise`, `PlanarPose3D`, `RollerSeat`, `PeakUtil` |
| `models/` | the models and their docs |

```
uv run examples/bridge/design/design.py
uv run examples/bridge/design/design_pier.py
uv run examples/bridge/design/build_model.py
uv run examples/bridge/design/build_pier.py
uv run examples/run_checks.py --only bridge
```

The pier truss compiles in about 4 minutes on a cold worker (32 bars, each with its failure events); after that a change of a global needs no recompile.
