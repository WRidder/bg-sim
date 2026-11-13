# Offset centre of mass, gripped at the box centre

The carton of `pick-place` with its centre of mass 60 mm along its length and 30 mm across (`cx`, `cy`), gripped at the box centre, on the default trajectory.

The offset makes a moment of $m g c$ = 0.88 N·m (x) and 0.44 N·m (y) about the grip point. The cups on the heavy side pull harder. The soft bellows let the carton tilt by about 3°, and the tilt moment adds to the peel load ($4M/D_{lip}$). Already at rest the most loaded cup is at U = 0.67 (see `static-hold`), so no trajectory reaches the margin of 0.5 with this grip: `optimize.py` finds no feasible speed for any family. On the default trajectory the heavy-side cups peel during the lift, and the carton drops.

**Gripping over the centre of mass** (`gx`, `gy` = `cx`, `cy`) removes the static moment. Then the offset case is almost as fast as the centred carton: see `offset-com-best`.

![Cup utilisation, vacuum of the heavy and the light side, drop detection|900](assets/fcbce5e2375a.png)
