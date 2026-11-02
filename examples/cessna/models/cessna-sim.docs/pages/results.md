# Results

![The demo run|900](assets/44d5903b9013.png)

| check | bg-sim | reference |
| --- | --- | --- |
| at rest on the runway (20 s, idle) | CG height 1.2546 to 1.2697 m | |
| 50 ft above the runway | 62.9 s | scipy reference 62.9 s |
| [Status/kias](signal:Status/kias) at 60 s, 100 s | 69.0, 76.2 kt | scipy within 1e-6 kt |
| bank in the turn | at most 18.9 deg | limit 20 deg |
| heading hold (60 deg) and altitude hold (1000 m) | within 2.6 m | `cessna-sim-autopilot` |
| full-throttle climb at the best-rate speed, 300 m | 583 fpm | POH 700 fpm (rtol 0.2) |
| full throttle at 8000 ft | 124.0 KTAS | POH 120 KTAS at 75 % power |

The climb is short of the handbook: with the engine's rated 160 hp, the c172p propeller makes too little thrust at low advance ratios. The example's README discusses this and the ISFC choice.
