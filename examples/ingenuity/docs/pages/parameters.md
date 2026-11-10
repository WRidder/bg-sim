# Parameters and sources

Every number is **published** (source), **digitised** from a published figure, **fitted** to the JPL hover test, or an **estimate** of this example. `design/ingenuity_data.py` tags each one; the README has the full table and references.

| quantity | value | status |
| --- | --- | --- |
| mass, gravity | 1.8 kg, 3.71 m/s² | published |
| rotor | 2 x 2 blades, R = 0.605 m, 17 % R apart | published |
| blade chord and twist | 8 stations | published (Koning et al. 2018) |
| lift slope, zero-lift angle | 5.5 /rad, -3.9 deg | digitised (Grip et al. 2017) |
| induced-velocity factor, edgewise gain, rate moment, apparent inertia | 1.2, 2.5, +0.4 1/s, x 1.6 | published (Grip et al. 2017) |
| profile drag polar | $d_0$ = 0.0428, $d_2$ = 0.0510 | **fitted** to the JPL hover test |
| collective / cyclic range, servos | -4.5..17.5 deg / ±10 deg, 12 Hz | published (Balaram 2018, Grip 2018) |
| rotor speed, density | 2537 rpm, 0.0165 kg/m³ (Flight One) | published |
| motor + drive efficiency | 78 % | published (Koning 2018) |
| airframe drag area | 0.065 m² | digitised (Dull et al. 2022) |
| mass distribution, inertia, rotor heights, motor constant, gains | | estimates (`design/design.py`) |

The only fit is the profile-drag polar ($c_d = d_0 + d_2 (c_l - 0.25)^2$) to the measured power of the JPL hover test (rms 2.8 %, max 4.7 %).
