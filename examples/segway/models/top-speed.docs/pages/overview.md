# Top speed: 20 km/h

**Scenario.** The speed set-point ramps from rest to **20 km/h = 5.56 m/s**, the published top speed of the Segway i2, over 9 s and then holds. At constant speed the voltage a motor needs is the back-EMF, $k_t\,n\,v/r = 2.88 \cdot 5.556 / 0.24 = 66.7$ V: with the estimated 72 V bus there is an 8 % margin, and the speed loop's overshoot at the end of the ramp pushes the demand to 71 V.

![The model canvas|1000](assets/3c20e88464b5.png)

![Speed, pitch and the voltage the motors need|900](assets/4592aea24e4d.png)

**Checks.** The speed, pitch and voltage follow the non-linear reference simulation; the final speed is the published 5.556 m/s and the final voltage the analytic 66.7 V; the wheel torque stays below 80 N m.

![3D view at t = 9 s|500](assets/be37aa3463fd.png)

**Try:** raise the cruise speed beyond 20 km/h: the demand exceeds the bus voltage (the model does not saturate the voltage, `Ctrl/vreq_l` shows it), which is the real reason a transporter has a speed limit and tilts the platform back as a warning.
