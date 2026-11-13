# Results and checks

![Mission: position, attitude and tracking error](assets/ee66674fa573.png)

![Actuation and drive](assets/e160bdfddb08.png)

![Yaw: rate and torque balance](assets/bd7e3faa9c68.png)

![Touchdown](assets/57c04f9835eb.png)

![Navigation filter errors](assets/8219ca451036.png)

## Measured against design.py

| quantity | design.py | measured |
| --- | --- | --- |
| 1.5 m leg overshoot, one-axis model with the accelerometer bias | 3.17 cm | 1.88 cm (x), 1.73 cm (y) |
| land-mode descent speed | 0.25 m/s | 0.2491 m/s |
| yaw rate in the steady descent (a model property) | 0.859 rad/s | 0.827 rad/s |
| feet reach the ground | 15.057 s | 15.061 s |
| touchdown load, four damped feet at once | ≤ 109.8 N | 85.2 N |
| yaw rate after the impact, to rest | ≤ 0.457 rad/s | 0.127 rad/s |
| rise above the contact height after the touchdown | ≤ 2.16 mm | 1.46 mm |
| rest height on the feet | 0.18055 m | 0.180556 m |
| yaw rate once landed | 0 (friction 1.33 N m against 0.091 N m) | below 0.001 rad/s |

The peak tilt is 0.145 rad, inside the 0.20 rad limit. Navigation errors in flight: attitude
0.0126 rad, position 0.0081 m, velocity 0.0157 m/s.

## Checks

The checks of this model compare each measurement with a reference from `design.py`: the leg
overshoot, the descent speed and yaw rate, the touchdown time, the touchdown load, the landing
yaw and hop, the rest height, the yaw rate on the ground, the tilt limit and the navigation
errors. They also check
the scene bindings and the absence of E901/E106/E007/W201/W202/W205/W206.

```
uv run examples/run_checks.py --only single-propeller-drone
```
