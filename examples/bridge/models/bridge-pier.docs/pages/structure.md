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
