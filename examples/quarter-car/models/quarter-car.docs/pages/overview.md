# Quarter-car suspension

The plan 9.4 quarter car: a 300 kg sprung mass on a 20 kN/m and 1500 N·s/m suspension, a 40 kg unsprung mass on a 200 kN/m **one-sided tire**, a $\pm 0.08$ m hard stop between the masses, and a road that climbs a 5 cm plateau bump (0.1 s at +0.5 m/s from $t = 0.5$ s, flat, then 0.1 s at -0.5 m/s from $t = 1.5$ s). The continuous plant is a **bond graph** (D28); the only non-bond-graph pieces are the signal sources, three flow sensors with integrators that reconstruct the positions for plots and checks (the D28 sensor exception) and a `Min` monitor used by one check. The run lasts 4 s on a 1 ms grid (4001 points).

![The model canvas|900](assets/677842c3979e.png)

## What to try

- **Plots** tab: "Sprung mass, unsprung mass and road" ([SInt/y](signal:SInt/y), [UInt/y](signal:UInt/y), [RoadInt/y](signal:RoadInt/y)) shows the body overshooting the 5 cm plateau to 7.5 cm; "Suspension travel" ([Stop/x](signal:Stop/x)) stays inside the 8 cm stop; "Tire contact force" ([Tire/F](signal:Tire/F)) peaks at 4.95 kN and never reaches zero.
- Lower the limits of [Stop](block:Stop) to $\pm 0.02$ m and rerun: the stop makes contact, `Stop/x` reaches $\pm 0.02$ and `Stop/a.e` becomes non-zero. The guard checks in `expected.json` then fail, which is the intended signal to update them.
- Make the road bump bigger: set `values` of [RoadProfile](block:RoadProfile) to `[0.0, 2.0, 0, ..., 0, -2.0, 0.0]` (a 20 cm bump) to see lift-off: `Tire/F` reaches zero and `TireNeg/y` stays zero. A 1.0 m/s entry (a 10 cm bump) already drops the tire force to about 10 N without losing contact. Set `method` to 1 for linear interpolation instead of the hold table.
- Change `k` or `d` of [Susp](block:Susp) and rerun.

## 3D view

`scenes/quarter-car.sdf` is a side view: the road block, the wheel and the car body, each on a vertical prismatic joint bound to [RoadInt/y](signal:RoadInt/y), [UInt/y](signal:UInt/y) and [SInt/y](signal:SInt/y) (metres from static equilibrium). The picture is taken at 0.9 s, near the peak of the body.

![3D view at t = 0.9 s|500](assets/2c708825cdb0.png)

Continue with [the plant](page:plant) and [the results](page:results).
