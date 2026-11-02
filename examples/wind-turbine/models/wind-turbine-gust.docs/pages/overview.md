# Extreme operating gust

The IEC 61400-1 extreme operating gust on a mean wind of 12 m/s, just above rated. The gust magnitude is class IB for this rotor, 5.2 m/s. The wind first dips by 1.4 m/s, then rises 3.8 m/s above the mean within 5 s, and dips again. [Gust](block:Gust) is the gust shape. See [the controller](project:controller).

![The gust|900](assets/277e4b761bc2.png)

## What you see

- In the dip the speed falls below rated, and the torque law drops back to region 2½ ([Torque/region](signal:Torque/region)).
- In the rise the rotor overspeeds while the pitch ([Aero/beta_deg](signal:Aero/beta_deg)) follows its command ([PitchCmdDeg/y](signal:PitchCmdDeg/y)).
- The thrust peak pushes the tower; [Aero/v_rel](signal:Aero/v_rel) shows the nacelle's motion in the wind the rotor sees.

## What to try

- Set `v_hub` to 9 m/s: below rated there is no pitch action, and the rotor speeds up with the gust.
- Set `v_hub` to 20 m/s: the pitch is large and the turbine reacts much more quietly.

## 3D view

The rotor turns at its real speed. The tower's sway is drawn 20 times larger than it is. The wind arrow grows with the wind.

![3D view during the gust|600](assets/b458fa4a5655.png)
