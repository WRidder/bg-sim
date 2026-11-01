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
