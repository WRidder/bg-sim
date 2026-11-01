# Suction gripper: pick, transfer, place

A six-cup bellows vacuum gripper on a gantry picks a closed 10 kg carton (0.5 x 0.3 x 0.3 m) from a conveyor, lifts it 0.15 m, moves it 1 m, lowers it onto the place table and releases it. The parcel is a free rigid body. It hangs on six [SuctionCup](block:Cup1) elements. Each cup holds by its vacuum, has a compliant bellows, slips by friction, peels when a tilting moment lifts one side of the lip, and leaks air through its lip, through the material and through a lifted lip. A [VacuumGenerator](block:Gen) with an ejector characteristic evacuates a [manifold](block:Manifold), and a [line](block:Line1) runs from the manifold to each cup.

![The model canvas|900](assets/8814d21528ff.png)

The example answers three questions:

1. **How fast can the parcel move without losing it, with a safety factor of 2?** The answer depends on the parcel: sealed (plastic film), cardboard (the default) or porous.
2. **Does the motion profile matter?** The example compares trapezoid, S-curve, polynomial 3-4-5 and cycloidal profiles at equal move time and at equal peak acceleration.
3. **Does the orientation matter?** The example checks (a) the yaw of the cup pattern relative to the path and (b) tilting the gripper along the specific force, like a waiter's tray.

It also covers the air side: the operating vacuum against generator size and porosity, the pick-up time, and one leaking cup on a shared manifold versus flow valves, restrictor nozzles or a generator per cup.

The default run is this model: an S-curve transfer of 1.75 s, which keeps every cup at U ≤ 0.5 with cardboard (the shortest such S-curve is 1.61 s, see [results](page:results)).

## What to try

1. Press **Run** and open the **Dashboard** tab. The two plots show the cup utilisation and the vacuum. The indicator and the counter show whether the parcel is held and how many cups are lost.
2. Set **Profile** to 1 (trapezoid) and **Transfer time** to 0.74 s, then run again. At the deceleration step the bellows ring, the cups peel one after the other, and all six lose their seal.
3. Keep 0.74 s and set the profile to 2 (S-curve). The peak acceleration rises to 11.7 m/s², yet no cup is lost.
4. Set **Parcel permeance** to 2e-6 (porous) and **Generator flow** to 6e-4 (36 l/min). The vacuum drops to 21.6 kPa and a 1.1 s move tears the parcel off.
5. Set **Tilt gain** to 1, or **Yaw of the cup pattern** to 45°, to see the effect of the tray tilt and of the pattern orientation.

All of these are global parameters. The Parameters tab lists them and the dashboard sliders change them. A change keeps the compiled plant, so a rerun takes about a second.

## 3D view

`scenes/suction-gripper.sdf` draws the gantry, the conveyor, the place table with its yellow mark, the gripper with six bellows cups, and the carton with its tape. The bindings colour each cup by its utilisation, from blue (U = 0) to red (U ≥ 1). A lost cup turns grey. The picture is taken at 1.9 s, mid transfer.

![3D view at t = 1.9 s|600](assets/1717ffb51cf5.png)

Continue with [the gripper model](page:plant), [the air side](page:air), [the sizing](page:sizing) and [the results](page:results).
