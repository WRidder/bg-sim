# Edge phase on contact points

The edge phase of `sequence-contact` alone: the cube starts at 0.70 rad tilt on the edge $y = z = -a/2$ (vertices 1 and 2), the same four-vertex contacts [C1](block:C1) to `C4`, the same wheels and the same firmware ([Seq](block:Seq), [Alloc](block:Alloc)); the run lasts 1.2 s with `reltol` 1e-9 and `abstol` 1e-11 (241 points). The sequencer is set to start in the edge phase.

![The model canvas|900](assets/06b2e5e30146.png)

![Tilt and vertex loads of the edge phase|900](assets/6e98a8ad9eea.png)

The model is the contact-based partner of `edge-switched`: the two models give the same edge balance to about 1e-5 (see that model's page for the numbers). The `Sense/tilt` of this run is the quantity compared. Checks: start tilt, edge balance (tilt and loads), the same tap and limit checks, no diagnostics; 25 states.
