# Results

![Descent: altitude, velocities, throttle, mass|900](assets/f7a1954a03f8.png)

The braking phase covers 470 km of range and loses most of the 1,695 m/s; the approach phase starts 8.5 km out:

![Trajectory over range|700](assets/078b06470a39.png)

In the landing phase the model follows Aldrin's calls. The vertical lines mark the time of four callouts; the model passes those altitudes close to the calls:

![Landing phase: altitude, rates, propellant, hover time|900](assets/b67a442196ae.png)

At touchdown the LM tilts 4.5° as the horizontal-velocity loop brakes the forward drift. One aft pad touches first, then the LM rocks onto the forward pad and settles level, 3 in into the soil:

![Touchdown: pad forces, tilt, pad height|900](assets/a8407181567b.png)

## Against the published data

| quantity | published | model |
| --- | --- | --- |
| throttle recovery | 386 s | 386.0 s (fitted) |
| high gate | 7,129 ft at −125 ft/s | 7,160 ft at −124 ft/s (fitted) |
| landing | 754.9 s | 758.3 s |
| touchdown vertical / horizontal | 1.7 / 2.1 ft/s | 1.6 / 2.6 ft/s |
| mass at engine cutoff | 7,374 kg | 7,427 kg |
| usable propellant left | 306 kg | 358 kg |
| velocity gained | about 6,775 ft/s | 6,997 ft/s |

The checks compare tightly (2e-4) with the independent scipy integration in `design/reference.py`, and with honest tolerances with the mission data. The forward pad's peak force is about 10 % above the 4,500 lb at which the primary strut's first honeycomb cartridge would crush; on Apollo 11 no primary strut stroked. The model's rigid struts and its 4.5° tilt at contact make that peak; the check holds it against the 9,500 lb second cartridge.
