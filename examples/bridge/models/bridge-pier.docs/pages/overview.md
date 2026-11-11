# Bridge on a pier: a buckled diagonal and a redundant truss

A truss road bridge of two 24 m spans, continuous over a 12 m steel column in the river. Eight 6 m panels, 5 m deep at the abutments and 7 m over the pier. One main truss is simulated (it carries half the deck and half the lorry), and the 3D view draws both. The truss is one [Truss](block:Truss) block (`stdlib:planar/Truss2D`) of 20 nodes and 32 bars, the pier column among them.

The two panels next to the pier are X-braced, so the truss is **statically indeterminate**: 32 bars and 5 reaction components for 17 truss nodes leave 3 redundants. One failed member need not bring it down. Diagonal 27 (top node 15 to node 7 on the pier) is **too slender**: its buckling capacity is 0.35 of the design section's (global `slender`). It holds a 20 t lorry, but an overloaded 40 t lorry ([Truck](block:Truck), 15 m/s) buckles it. Its X-partner (bar 26) then carries the panel's shear alone, nothing else fails, and the lorry crosses.

![The model canvas|900](assets/cd6ccd7a3422.png)

## What to try

- **Dashboard**: play the default run: the **A member failed** indicator turns on when bar 27 buckles, the gauge reads 1.0 (bar 27) and the **Bridge collapsed** indicator stays off.
- Move **Member strength** to 0.5: the redistributed load is too much, a post and the bottom chord next to bar 27 fail, then the pier column buckles and the bridge collapses.
- Move **Lorry mass** to 20000 kg: bar 27 holds at 77 % of its buckling load. Move **Diagonal 27: buckling capacity** to 1.0 for the design bridge.
- **3D view**: bars are coloured by their utilisation (blue compression, red tension), a failed bar is drawn snapped, and the roller's seats turn red if it rolls off.

![3D view: bar 27 has buckled, the lorry crosses the pier|700](assets/45bee631a496.png)

Continue with [the structure](page:structure) and [the results](page:results). The member failure and the roller seat work as in `bridge-failure`.
