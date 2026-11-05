# Results

All numbers come from `design/simscen.py`, a scipy simulation of the same airframe and laws. bg-sim checks against it in `expected.json`.

## Coordinated 60 deg turn (the default run)

![bank, sideslip, load factor and altitude|900](assets/da4efab97f53.png)

A 0.284 roll stick for 1 s banks the aircraft to 60 deg, and the throttle goes to 0.33 to hold the speed at 2 g. The sideslip stays below 0.6 deg and the speed within 1 m/s. A centred stick commands the load factor of a level turn, not an altitude, so the path sags slowly: 19 m after 10 s, 45 m after 30 s.

## Roll-rate step

![roll rate, surfaces and sideslip|900](assets/48ddb239c218.png)

A quarter stick commands 52.6 deg/s. The stability-axis roll rate reaches 90 % of it 0.57 s after the stick moves and overshoots by 2 %. A full-stick roll at the same point holds 217 deg/s against a limit of 219 deg/s. The ailerons saturate at 21.5 deg, and the sideslip stays below 1.5 deg.

## Dutch roll

A 5 deg rudder kick for 0.3 s, with parts of the law switched off:

![airframe alone|900](assets/48bc5be4cf50.png)

![yaw damper alone|900](assets/f15e798d4310.png)

![full law|900](assets/6ec3195c1b7e.png)

| law | damping ratio | natural frequency |
| --- | --- | --- |
| airframe alone | 0.124 | 2.76 rad/s |
| yaw damper alone | 0.524 | 1.31 rad/s |
| full law | 0.909 | 3.28 rad/s |
| full law without the yaw damper | −0.044 (unstable) | 4.22 rad/s |

These are the linearised modes of the closed loop at the trim. bg-sim's runs reproduce the first two: a damped sinusoid fitted to the sideslip from 2 s on gives the same damping and frequency (check kind `damping`). Without the yaw damper, the sideslip feedback alone would destabilise the mode. The yaw damper is what makes the stiff sideslip loop possible.

## Roll at high alpha

At 260 ft/s, 10 000 ft (alpha 15.7 deg), full stick for 1.5 s:

![about the velocity vector|900](assets/fb4631aab672.png)

![about the body axis, no ARI|900](assets/66090fd13c30.png)

Rolling about the body x axis at high alpha swaps alpha into sideslip: |beta| reaches 7.1 deg. Rolling about the velocity vector, with the ARI, keeps it at 3.1 deg. At this speed the rudder saturates in both cases.

## Pull

Full aft stick for 3 s at 500 ft/s: the limiter keeps alpha below 26.6 deg (it swings between 16 and 26 deg as the speed bleeds off) and the load factor peaks at 5.7 g. At this speed the alpha limit comes before 9 g.
