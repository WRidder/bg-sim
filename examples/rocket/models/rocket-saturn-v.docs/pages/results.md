# Results

![Altitude, speed, mass and acceleration|900](assets/997c30729d99.png)

The acceleration climbs to 3.9 g before the S-IC's outboard cutoff, drops at each staging, and steps down at the S-II's mixture-ratio shift.

![Pitch program, attitude and flight-path angle; the gimbal angle|900](assets/e30d27ff3484.png)

![Mach, dynamic pressure and thrust in the S-IC burn|900](assets/d66bf4bc546f.png)

## Against the flight evaluation report

| | AS-506 | model |
| --- | --- | --- |
| speed at S-IC CECO / OECO | 1,979.0 / 2,764.1 m/s | 1,965.0 / 2,750.7 |
| at S-II CECO / OECO | 5,707.5 / 6,917.3 m/s | 5,722.2 / 6,939.1 |
| at S-IVB cutoff | 7,791.2 m/s | 7,826.9 |
| maximum acceleration S-IC / S-II / S-IVB | 38.61 / 17.84 / 6.73 m/s² | 38.53 / 18.01 / 6.78 |
| mass at S-IC OECO / S-II OECO / S-IVB cutoff | 827.3 / 213.9 / 135.2 t | 826.4 / 211.7 / 132.9 |
| Mach 1 | 66.3 s | 64.4 s |
| max Q | 35.2 kPa at 83.0 s | 31.7 kPa at 75.3 s |
| altitude, flight-path angle, range at the cutoffs | | within 0.7 km, 0.1°, 7 km (fitted) |

The pitch program is fitted to the altitude, flight-path angle and range. The speeds, accelerations, masses, Mach 1 and max Q are not fitted: they test the propulsion, mass and drag data. Max Q comes 8 s early and 10 % low. The drag table is an estimate, and the report's dynamic pressure uses the measured atmosphere and winds of the day. The S-II flow, computed from the published thrust and specific impulse, burns about 2 t more than the report's mass history shows. So the masses after the S-II are 1 to 2 % low and the speeds 0.3 to 0.5 % high.

The checks compare the run tightly with an independent scipy model of the same equations (`design/reference.py`). They compare it loosely with the report, with each tolerance stating what is fitted and what is not.
