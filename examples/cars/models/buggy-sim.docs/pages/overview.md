# Buggy: the FMU source

The buggy with the interface of the `apps/web` driving simulator, on the rolling hills of `buggy-hills`. The interface is the race car's (see `racecar-sim`), with a front and a rear motor.

![The model canvas|900](assets/b8dc4ee51b92.png)

The host draws the same height field the four `TerrainSurface` blocks evaluate, so the wheels sit on the drawn ground.

![3D view at t = 8 s|600](assets/a2b13fd404fc.png)
