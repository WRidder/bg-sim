# bridge: a truss road bridge, a lorry and a diagonal that snaps

A 30 m Warren truss road bridge over a river: six 5 m panels, 4 m deep, a deck on the bottom chord. One main truss is simulated (it carries half the deck and half the lorry); the 3D view draws both. The truss is one `stdlib:planar/Truss2D` block. Its node positions, bars and supports are matrix parameters and constants, every bar is a co-rotational axial bar that can fail, and the lorry is a planar rigid body on compliant tyres that rolls on the deck.

```
           11 -------- 12 -------- 13 -------- 14 -------- 15 -------- 16          top chord, y = 4 m
          /  \        /  \        /  \        /  \        /  \        /  \
         /    \      /    \      /    \      /    \      /    \      /    \       diagonals 12..23
  1 ... 2 --- 3 ----- 4 ----- 5 ----- 6 ----- 7 ----- 8 ----- 9 ... 10             deck: nodes 1..10
 (-40,0) (-1,-0.06) x=0  (13 = 11->4)                             x=30  (70,0)
         settled   pinned                                       roller
```

Nodes 1, 2 and 10 are the approach slabs (fixed). They belong to the deck polyline, so the lorry drives on and off the bridge. The left slab has settled 6 cm at the abutment (node 2), so a lorry meets a short ramp onto the bridge: that bump makes it bounce, which is the dynamic load of the crossing models. Bar 13, the second diagonal from the left (top node 11 to bottom node 4), is the member that is undersized in the failure model.

## Models

| model | what it shows |
| --- | --- |
| `bridge-failure` | **The main model, with a dashboard.** Bar 13 is undersized (A = 6.78 cm², Ft = 240.6 kN, 1.4 times the quasi-static peak force of a 20 t lorry). A 30 t lorry at 15 m/s bounces off the abutment ramp and snaps it at t = 2.187 s, the second panel shears, and the bridge folds. The run stops when the midspan has dropped 3 m (`Collapsed`, a `StopSimulation`). |
| `bridge-crossing` | the design bridge (all diagonals 20 cm²) and a 20 t lorry at 10 m/s: every member stays below 37 % of its strength |
| `bridge-static` | dead load plus a 100 kN point load at midspan: member forces and reactions against the method of joints |
| `bridge-modes` | free vibration in the first vertical bending mode (no damping): frequency against the eigenvalue problem, energy balance |
| `bridge-moving-load` | a 100 kN point load crossing at 5 m/s: influence lines of the member forces |
| `strut-buckling` | one `Bar2D` strut between two `PinNode2D` nodes, pushed by a growing force: it fails at the Euler load |

The dashboard of `bridge-failure` has sliders for the lorry's speed (global `v_truck`) and mass (global `m_truck`); every change runs the model again. Its cards show the utilisation of bar 13, the number of failed bars, the member forces, the midspan deflection and the axle loads.

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

## Failure behaviour

A bar fails in tension when N > Ft = fy A and in compression when -N > Pcr = pi^2 E I / (K L0)^2 (Euler). The failure is an event that sets the held flag `failed[k]` (`ddt(broken) ~ 0`, `reinit`), so a failed bar carries no force from then on: **elastic-brittle, also in compression**. A real strut keeps a post-buckling load. This model drops it to zero, which is the simplest behaviour that conserves the energy book: the strain energy a bar held at the instant it failed goes to `Elost`, and `Ebal = Ek + Ee + Eg + Edis + Elost - Wext` stays constant through every failure.

The truss is statically determinate (2 x 13 joint equations = 23 bars + 3 reactions), so losing one bar turns its panel into a mechanism: in `bridge-failure` bar 13 fails alone, the second panel shears, and 0.57 s later the bottom chord (bar 4) fails as the bridge folds.

## Numbers

All reference numbers come from `design/design.py` (numpy only, no bg-sim code).

| check | reference | simulation |
| --- | --- | --- |
| static member forces, dead + 100 kN at midspan (bars 3, 9, 12, 13, 17) | 308.80, -348.31, -143.92, 142.16, 74.53 kN (method of joints) | 308.99, -348.21, -143.90, 142.18, 74.07 kN (largest difference 0.13 % of the largest force: the deformed geometry) |
| support reactions | 135.250 kN each | 135.268 and 135.234 kN |
| midspan deflection, dead + 100 kN | -28.875 mm (linear) | -28.881 mm |
| first vertical bending frequency | 4.39776 Hz (eigenvalues of K, M) | 4.3990 Hz (FFT of the midspan deflection) |
| energy balance, free vibration | constant | drift 1.5e-6 J of 94 J kinetic energy |
| Euler load of the strut (2 m, I = 1e-8 m^4) | 5181.54 N | fails at 5181.54 N, t = 0.05197 s |
| strain energy lost at buckling | Pcr^2 L / (2 E A) = 0.127849 J | 0.127849 J |
| bar 13 in `bridge-failure` | Ft = 240.6 kN | fails at t = 2.1865 s (lorry at x = 7.8 m), alone for 0.57 s |

Crossing results (bar 13 utilisation with the undersized section, the largest over the run):

| lorry | 5 m/s | 10 m/s | 15 m/s | 20 m/s | 30 m/s |
| --- | --- | --- | --- | --- | --- |
| 20 t | 0.76 | | 0.95 | | |
| 30 t | 0.91 | fails | fails | 0.97 | 0.95 |

The dynamic load is not monotonic in the speed: the lorry starts to bounce at the abutment ramp (about 2.8 Hz on its tyres), and at 10 to 15 m/s the bounce peaks just as the lorry reaches the influence peak of bar 13. Faster, the lorry is past that point before the bounce has built up. The mass is the clear threshold: at 15 m/s the diagonal holds 20 t and fails at about 22 t.

## 3D view

`scenes/bridge.sdf` (with the lorry) and `scenes/bridge-load.sdf` (the point-load models) are written by `design/build_scene.py`. Every bar of both trusses is a cylinder with a `segment` binding on its two end nodes (`Truss/x[a]`, `Truss/y[a]`, `Truss/x[b]`, `Truss/y[b]`, plane `xz`, depth ±3.6 m), a `color` binding on `Truss/util[k]` (coolwarm, -1 to 1: blue compression, red tension, full colour at failure), and the broken signal `Truss/failed[k]` drawn **snapped**. The deck slabs are boxes with segment bindings between the deck nodes. The lorry is one link posed by `Truck/q` (`PlanarPose3D`), with four wheel joints on `Truck/wheel`.

## Checks (`expected.json`)

- no E101/E102/W201/W202 diagnostics; every scene binding resolves
- statics: member forces and reactions against the method of joints
- the first bending frequency (FFT) against the eigenvalue problem; `Ebal` constant without damping
- the moving load: largest midspan deflection and the largest force in bar 13
- the strut fails at the Euler load at the expected time and books Pcr^2 L / (2 E A)
- the design bridge under the 20 t lorry: no bar fails, `Ebal` constant
- the failure model: bar 13 is the first and only failed bar for 0.5 s, it fails at Ft, `Elost` jumps by its strain energy, `Ebal` stays constant through the failure, and the run stops on the collapse; the same model with a 20 t lorry and with 30 t at 5 m/s (run overrides of the globals) loses no bar

## Files

| file | content |
| --- | --- |
| `design/design.py` | the independent numbers: geometry, lumped masses, method of joints, eigenfrequencies, the quasi-static vehicle envelope; writes `design.json` |
| `design/build_scene.py` | the two SDF scenes and the bindings |
| `design/build_model.py` | the six models from `design.json` |
| `library/` | `Truck2D`, `Cruise`, `PlanarPose3D` |
| `models/` | the models and their docs |

```
uv run examples/bridge/design/design.py
uv run examples/bridge/design/build_model.py
uv run examples/run_checks.py --only bridge
```
