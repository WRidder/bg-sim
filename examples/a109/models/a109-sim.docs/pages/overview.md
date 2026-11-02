# The flyable A109

The A109 of the open-loop model with ground effect at 15 m, flown with collective, cyclic and pedals:

* `Rigging` maps the sticks to the blade angles.
* A switchable SCAS holds the attitude and the heading.
* A demonstration pilot flies 120 s:
  * hover;
  * accelerate and climb to 75 kt and about 45 m;
  * a coordinated 20 deg bank turn through 146 deg;
  * decelerate and hover.

The sticks and the wind pass through export markers: in bg-sim they carry the demonstration pilot, in an FMU the host's pilot drives them.

![The model canvas|900](assets/00c70727e8ab.png)

| block | role |
| --- | --- |
| [Heli](block:Heli) | the airframe (as in `a109-open-loop`), with wind inputs, ground effect and smoothed switches |
| [Pilot](block:Pilot) | `DemoPilot`: speed by pitch attitude, height by collective, the turn by bank |
| [UCmd](block:UCmd), [HCmd](block:HCmd), [PhTurn](block:PhTurn) | the schedule over time (`Lookup1D`) |
| [collective](block:collective), [cyclic_lon](block:cyclic_lon), [cyclic_lat](block:cyclic_lat), [pedals](block:pedals) | `ExportInputPass`: the sticks |
| [Rig](block:Rig) | `Rigging`: percent of travel to blade angle, fitted to the report's control-position charts |
| [Scas](block:Scas) | `Scas`: attitude command and hold, yaw-rate command, turn coordination; trim feedforward from the `FF_*` tables |

## What to try

1. Press **Run** and watch the demonstration in 3D.
2. Set **demo** to 0. The helicopter hovers hands-off. Add a longitudinal offset of 0.1: the SCAS holds the commanded 1.5 deg nose-down attitude and the helicopter accelerates gently.
3. Then set **SCAS** to 0. The bare helicopter's hover phugoid diverges within 10 s.

![3D view at t = 100 s, decelerating|600](assets/85d06880af55.png)

Continue with [the results](page:results).
