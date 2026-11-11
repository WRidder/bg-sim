# Saturn V, Apollo 11 to orbit

The Saturn V of Apollo 11 (AS-506, 16 July 1969) from lift-off to the parking orbit, with the
masses, event times and engine performance of the *Saturn V Flight Evaluation Report AS-506*:

| range time | event |
| --- | --- |
| 0 | lift-off, 2,899 t, five F-1 engines |
| 135.2 s | centre engine cutoff (CECO) |
| 161.6 s | outboard engine cutoff (OECO) |
| 162.3 s | S-IC separation (165 t) |
| 165.5 s | five J-2 engines of the S-II |
| 192.3 s | S-II aft interstage dropped |
| 197.9 s | launch escape tower jettisoned |
| 460.6 s | S-II centre engine cutoff |
| 491.2 s | mixture-ratio shift (thrust 4.1 → 3.1 MN) |
| 548.2 s | S-II cutoff, separation (47 t) at 549.0 s |
| 552.2 s | S-IVB ignition |
| 699.3 s | S-IVB cutoff, insertion at 709.3 s |

The vehicle is the variable-mass bond graph of [variable mass on a bond graph](project:variable-mass). A pitch program (`Lookup1D` over time) commands the attitude, and a PD loop turns the engines through ±6°.

![The model canvas|900](assets/6702ec39c8a7.png)

| block | role |
| --- | --- |
| [Seq](block:Seq) | `FlightSequence`: nine engine phases, four jettisons, five inertia configurations |
| [Pitch](block:Pitch), [AP](block:AP) | the pitch program and the attitude loop (gimbal angle to [Engine](block:Engine)) |
| [Air](block:Air) | altitude, surface range on the turning Earth, flight-path angle, the air velocity |
| [SpentSIC](block:SpentSIC), [SpentIS](block:SpentIS), [SpentLET](block:SpentLET), [SpentSII](block:SpentSII) | the dropped parts, flying ballistically from their separation (for the 3D view) |

## What to try

1. Press **Run** (about 20 s). Watch the 3D view: the S-IC falls away at 162 s, the interstage ring at 192 s, the escape tower shoots ahead at 198 s, and the S-II drops at 549 s.
2. Set **tilt** to 0.95 or 1.05: the vehicle pitches over less or more, and misses the orbit.
3. Double the drag, or slow the attitude loop (**ap_wn**).

![3D view at t = 6 s: clearing the tower|600](assets/6996cc3da125.png)

Continue with [the results](page:results).
