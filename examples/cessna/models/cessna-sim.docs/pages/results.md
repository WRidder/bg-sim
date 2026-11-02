# Results

![The demo run|900](assets/036a3fb6f39f.png)

| check | bg-sim | reference |
| --- | --- | --- |
| on the runway until rotation (14 s) | CG height 1.2546 to 1.2725 m | |
| 50 ft above the runway | 37.0 s, 2657 ft from brake release | scipy reference 37.0 s |
| [Status/kias](signal:Status/kias) at 60 s, 100 s | 77.3, 77.3 kt | scipy within 1e-6 kt |
| bank in the turn | at most 18.9 deg | limit 20 deg |
| heading hold (60 deg) and altitude hold (1000 m) | within 2.6 m | `cessna-sim-autopilot` |
| full-throttle climb at the best-rate speed (84 KCAS), 300 m | 703 fpm | POH 700 fpm at sea level (rtol 0.05) |
| full throttle at 8000 ft | 124.1 KTAS | POH 120 KTAS at 75 % power |

The climb matches the handbook because the propeller's low-speed thrust and power tables are fitted to it (the engine keeps its rated 160 hp). With JSBSim's own propeller tables the model climbed at 583 fpm here and needed 1492 ft of ground roll instead of the POH's 892 (now 855). The demo pilot does not fly the POH's short-field technique, so its 50 ft point is not the POH's 1628 ft. The example's README has the comparison with the POH and the fit.
