# Results and checks

![Mission: position, attitude and tracking error](assets/405794422b18.png)

![Actuation and drive](assets/fc061f8f49dc.png)

![Yaw: rate and torque balance](assets/6454d9081d38.png)

![Touchdown](assets/0e71c51e403c.png)

![Navigation filter errors](assets/738d78d09712.png)

## Measured against design.py

| quantity | design.py | measured |
| --- | --- | --- |
| 1.5 m leg overshoot, one-axis model with the accelerometer bias | 3.17 cm | 1.88 cm (x), 1.73 cm (y) |
| land-mode descent speed | 0.25 m/s | 0.2491 m/s |
| yaw rate in the steady descent (a model property) | 0.859 rad/s | 0.827 rad/s |
| feet reach the ground | 15.057 s | 15.061 s |
| touchdown detected by the drive (contact + at most 2.56 ms) | 15.058 s ± 0.031 | 15.0625 s |
| largest foot load sample, four damped feet at once (an upper bound) | ≤ 109.9 N | 78.7 N (true peak 85.1 N) |
| yaw rate after the touchdown without the 1/rev ripple (from 15.212 s) | ≤ 0.348 rad/s | 0.065 rad/s |
| raw yaw rate after the touchdown (from 15.087 s) | ≤ 0.782 rad/s | 0.149 rad/s |
| rise above the contact height after the touchdown | ≤ 2.16 mm | 1.53 mm |
| 1 m/s wind (±x, ±y): yaw rate through descent and landing, without the ripple | ≤ 1.375 rad/s | 1.00 to 1.01 rad/s |
| 1 m/s wind: height after the touchdown | ≤ 0.18917 m | at most 0.18399 m |
| rest height on the feet | 0.18055 m | 0.180556 m |
| yaw rate once landed | 0 (friction 1.33 N m against 0.091 N m) | below 0.001 rad/s |

The peak tilt is 0.145 rad, inside the 0.20 rad limit. Navigation errors in flight: attitude
0.0126 rad, position 0.0081 m, velocity 0.0157 m/s.

## Checks

The checks of this model compare each measurement with a reference from `design.py`: the leg
overshoot, the descent speed and yaw rate, the touchdown time, its detection, the sampled foot
load, the landing yaw (with and without the ripple) and hop, the rest height, the yaw rate on
the ground, the tilt limit and the navigation errors. Four variants land in a 1 m/s wind along
±x and ±y. They also check
the scene bindings and the absence of E901/E106/E007/W201/W202/W205/W206.

```
uv run examples/run_checks.py --only single-propeller-drone
```
