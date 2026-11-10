# Flight One, 19 April 2021

The first flight on Mars: climb at 1 m/s to 3 m, hover, turn 96 deg, descend at 1 m/s and touch down, 39.1 s in the air, at 0.0165 kg/m³ and 2537 rpm. The model flies it in a steady 5 m/s wind from the east-south-east (the weather station saw 4-6 m/s, gusting to 8). See [the validation](project:validation) for the published figures.

![The model canvas|900](assets/fdfad88b7e16.png)

![Hovering after the turn: t = 25 s|500](assets/dae33fe1e8fb.png)

![Flight One against the published figures|900](assets/d9b8732a1743.png)

## What you see

- Hover power [Telem/P_el](signal:Telem/P_el) 208 W against the published 210 W.
- Collectives [Telem/coll_u_deg](signal:Telem/coll_u_deg) 8.6 deg and [Telem/coll_l_deg](signal:Telem/coll_l_deg) 9.9 deg against the flown 8.2 and 9.2 deg. JPL's pre-flight model predicted 9.0 and 9.9 deg; the flight needed 0.7 to 0.8 deg less, so the real rotor makes a little more thrust than both models.
- The wind needs 3.3 deg of cyclic ([Telem/cyc_deg](signal:Telem/cyc_deg)) to cancel the edgewise-flow moment; the published cyclic was "generally below 3 deg".
- Heading [Nav/yaw_deg](signal:Nav/yaw_deg) settles on 96 deg.

## What to try

Change the wind on the dashboard; set it to zero and the cyclic drops to zero, the power stays the same.
