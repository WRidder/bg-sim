# Buggy: rolling hills

The buggy at 8 m/s over rolling hills: an analytic height field $h(x, y) = \sum_i a_i \cos(k_{x,i} x + k_{y,i} y + \varphi_i)$ with six components (wavelengths 25 to 140 m, up to 2.2 m amplitude), with a few steering inputs. Each corner has its own `TerrainSurface` that gives the tyre the tangent plane below the wheel centre.

![The model canvas|900](assets/48cf8b5df4a0.png)

A second `TerrainSurface`, [TerrainProbe](block:TerrainProbe), evaluates the terrain at the point where the FL tyre says it touches ([FL/Tyre/zc](signal:FL/Tyre/zc)): the two heights agree to a few micrometres. The same table (`design/hills.json`) draws the hills in the 3D view and in the `apps/car-sim` host.

![3D view at t = 12 s|600](assets/8b3482436008.png)

Continue with [the results](page:results).
