# Results

The demonstration:

![Demonstration|900](assets/ff51e8a001f0.png)

The scipy closed loop of `design/heli_sim.py` flies the same demonstration; bg-sim follows it to about 1e-7 over the 120 s. The rotor speed stays within 0.15 % of nominal. The power runs from 640 hp in hover down to about 430 hp at 75 kt, well inside the 740 shp take-off power.

Hands-off with the SCAS on, 0.1 forward stick from 1 s:

![Attitude hold|900](assets/cbc385ca5085.png)

With the SCAS off, 0.02 forward stick:

![Bare helicopter|900](assets/1a3944457943.png)

The closed loop runs with the report's hard switches smoothed (`smooth` = 1, ours). The fin-stall switch between 40 and 55 kt otherwise traps the trajectory and the closed loop chatters.
