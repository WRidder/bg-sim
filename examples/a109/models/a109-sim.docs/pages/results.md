# Results

The demonstration:

![Demonstration|900](assets/15dff42d153e.png)

The scipy closed loop of `design/heli_sim.py` flies the same demonstration; bg-sim follows it to about 1e-7 over the 120 s. The rotor speed stays within 0.15 % of nominal. The power runs from 640 hp in hover down to about 430 hp at 75 kt, well inside the 740 shp take-off power.

Hands-off with the SCAS on, 0.1 forward stick from 1 s:

![Attitude hold|900](assets/475ce2504c08.png)

With the SCAS off, 0.02 forward stick:

![Bare helicopter|900](assets/8ca2dc9ddabc.png)

From the pad, collective 3 % above the hover's: the wheels unload within half a second, the SCAS engages and holds the hover attitude, and the helicopter climbs.

![Lift-off from the gear|900](assets/92f70d84d00e.png)

Parked with the collective down, it rests level on its three wheels at a CG height of 1.28 m (4 cm of tyre deflection), and the rotor stays at 100 %.

The closed loop runs with the report's hard switches smoothed (`smooth` = 1, ours). The fin-stall switch between 40 and 55 kt otherwise traps the trajectory and the closed loop chatters. The tailplane's downwash factor is a smooth max, not a condition: a fixed-step FMU holds a condition over its step, and where the descent velocity passes the induced velocity the wake-edge distance swings through ±10⁴ m within one step.
