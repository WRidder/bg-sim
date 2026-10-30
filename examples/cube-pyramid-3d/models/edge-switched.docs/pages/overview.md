# Edge phase on a switched pivot

The same edge phase as `edge-contact`, but the contacts are replaced by a **`SwitchedPivot3D`** ([Joint](block:Joint)) in edge mode (J-MB14): [World](block:World) `->` `Joint` ($k_t = 10^6$ N/m, $b_t = 2000$, $k_r = 10^5$, $b_r = 100$; mode 2 from the start through [NewMode](block:NewMode), guard [Guard](block:Guard) held at 0) `->` [Link](block:Link) (`FixedTransform3DNeutral` to the centre of mass, $x = y = 0.1$ m) `->` [Cube](block:Cube) (`RigidBody3D`). The pivot frame has its $z$ axis along the edge, so the cube frame is the cyclic permutation of the pivot frame; `TwistToCube` maps the twist back so that the *same* firmware ([Seq](block:Seq), [Alloc](block:Alloc)) runs on both models. The sequencer's `t1` = -10 s and `t2` = 100 s keep it in the edge phase.

It uses `RigidBody3D` behind a link rather than `ImpactBody3D`: the wheels need several bonds on the body port and `ImpactBody3D` exposes one; no impact is needed because the guard never fires. The run lasts 1.2 s (`reltol` 1e-9, `abstol` 1e-11, 241 points); 27 states.

![The model canvas|900](assets/2a337ea8f209.png)

![Tilt and wheel speeds on the switched pivot|900](assets/ca49e0d17ca0.png)

## Comparison with the contact model

| quantity (1.2 s) | difference |
| --- | --- |
| max $\lvert\Delta\ \mathrm{tilt}\rvert$ | 1.2e-5 rad |
| max $\lvert\Delta z_{cm}\rvert$ | 1.6e-5 m (the pivot weight deflection $m g/k_t = 1.4\cdot10^{-5}$ m) |
| max $\lvert\Delta y_{cm}\rvert$ | 5.4e-6 m |
| wheel 1 speed | 4.6e-3 rad/s of 11 rad/s |

That is the size of the stated compliance and much smaller than the contact penetration of 0.5 mm: the two models are the same rocking edge. The tolerances of the `compare` entries are 4x the measured maxima (tilt, centre-of-mass height and lateral position, wheel speed).
