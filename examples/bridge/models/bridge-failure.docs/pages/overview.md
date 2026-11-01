# Bridge: a diagonal that snaps

A 30 m Warren truss road bridge over a river: six 5 m panels, 4 m deep, with the deck on the bottom chord. One main truss is simulated. It carries half the deck and half the lorry, and the 3D view draws both trusses. The truss is one [Truss](block:Truss) block (`stdlib:planar/Truss2D`). Its nodes, bars and supports are matrices, and each of its 23 bars is a co-rotational axial bar that fails in tension at $F_t = f_y A$ and in compression at the Euler load.

The second diagonal from the left (bar 13, from top node 11 to bottom node 4) is **undersized**: 6.78 cm² instead of 20 cm², which is 1.4 times the quasi-static peak force of the 20 t lorry the bridge was checked for. An overloaded 40 t lorry ([Truck](block:Truck), driven at 15 m/s) snaps it, the second panel shears, and the bridge folds into the river. The run stops when the midspan has dropped 3 m ([Collapsed](block:Collapsed), a `StopSimulation`).

![The model canvas|900](assets/a61497cd4e21.png)

## What to try

- **Dashboard**: move the **Lorry mass** slider to 20000 kg. The gauge of bar 13 stays below 1 and no bar fails. Back at 40000 kg, try the **Lorry speed** slider: the load on bar 13 changes with speed, because the bounce from the abutment ramp arrives at different points of the span.
- **Plots**: "Member forces" shows bar 13 ([Truss/N[13]](signal:Truss/N[13])) climbing to its strength and dropping to zero when it fails; the other members take over its load until the bottom chord fails as well.
- **3D view**: play the run. Bars are coloured by their utilisation (blue compression, red tension, full colour at failure), and a failed bar is drawn snapped.

![3D view after the diagonal has failed|700](assets/d72f8e4230f2.png)

Continue with [the structure](page:structure), [failure](page:failure) and [the results](page:results).
