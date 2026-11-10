# Ingenuity: a demonstration flight

Ingenuity takes off at 1 s, climbs at 1 m/s to 3 m, flies 5 m east in 8 s, turns 90 deg, descends at 1 m/s and lands on the yellow pad, all at Flight One's density (0.0165 kg/m³) and rotor speed (2537 rpm). See [the vehicle](project:vehicle) for the model and [the validation](project:validation) for the published data.

![The model canvas|900](assets/fdfad88b7e16.png)

![Climbing: t = 4 s|300](assets/8427e6b2f0f0.png) ![Flying east: t = 13 s|300](assets/2a92bdedffc0.png) ![Turning: t = 19 s|300](assets/59c71238fa90.png)

![The flight|900](assets/b4a0e5373b0f.png)

## What you see

- On the ground the rotors spin at ground-idle collective: the four feet ([Foot1](block:Foot1) to `Foot4`) carry 90 % of the weight ([Foot1/f_n](signal:Foot1/f_n)).
- In hover the collectives are 8.6 deg (upper) and 9.9 deg (lower) ([Telem/coll_u_deg](signal:Telem/coll_u_deg), [Telem/coll_l_deg](signal:Telem/coll_l_deg)): the lower rotor works in the upper rotor's wake and needs more pitch for the same torque. The rotors take 208 W of electrical power ([Telem/P_el](signal:Telem/P_el)), Flight One measured about 210 W.
- The heading turn is made with the antisymmetric collective alone; the rotor speed ([GovL/speed_rpm](signal:GovL/speed_rpm)) never changes.
- In the 3D view the rotors turn at 1/40 of their real speed (42 rev/s), so the counter-rotation is visible; the orange blade tips mark it.

## What to try

- Lower the **air density** to 0.012 kg/m³ (the late-mission Martian summer): the collective climbs towards its 17.5 deg limit. Then raise the **rotor speed** to 2700 rpm, as the team did.
- Add **wind**: the controller holds position with cyclic, the airframe barely tilts (the drag on Mars is tiny).

## Key parameters

The globals `rho`, `rpm_set`, `wind_e`, `wind_n`, `alt` and `dist` are on the dashboard.
