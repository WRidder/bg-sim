# Franka Emika Panda: free swing

The bare Panda arm (the [L1](block:L1) to `L7` chain of `RevoluteLink3D` instances of the `panda` model, without friction or drives: each drive port gets a zero effort source) is released at rest from the ready pose $q = (0, -\pi/4, 0, -3\pi/4, 0, \pi/2, \pi/4)$ and falls under gravity for 1 s. It checks the mechanics and the Gaz parameters against MuJoCo, which runs the same parameters from `reference/panda_gaz.xml`.

![The model canvas|900](assets/e7bc319c57d8.png)

![3D view at t = 0.5 s|500](assets/d1fd36a8f068.png)

The run: 1 s with `Rodas5P`, `reltol` 1e-8, `abstol` 1e-10, 1001 output points; about 9 s of solve time (10790 steps).

Continue with [the results](page:free-results).
