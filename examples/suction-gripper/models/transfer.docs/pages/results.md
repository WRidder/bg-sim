# Results

![The default transfer: acceleration, cup utilisation, vacuum, parcel position|900](assets/a28f547f0ce1.png)

## Simulation against the hand calculation

| quantity | simulation | analytic |
| --- | --- | --- |
| operating vacuum, sealed | 57 970.5 Pa | 57 971.2 Pa |
| operating vacuum, cardboard | 48 329.7 Pa | 48 329.9 Pa |
| operating vacuum, porous | 29 022.4 Pa | 29 022.6 Pa |
| vacuum 50 ms after the valve opens (sealed / cardboard / porous) | 18 731 / 18 062 / 15 693 Pa | 18 733 / 18 064 / 15 695 Pa |
| pull of cup 5 / 1 at 1.6 m/s² (sealed, slow S-curve) | 19.47 / 13.36 N | 19.53 / 13.17 N |
| shear per cup | 2.54 to 2.78 N | 2.68 N |
| U of cup 5 / 1 | 0.320 / 0.253 | 0.327 / 0.248 |

The slow-move loads agree within 1.0 % for the pull and 5.1 % for the shear. The difference comes from the dynamic loads the hand calculation ignores.

## Dynamic amplification and jerk

At the same peak acceleration of 4 m/s², the dynamic U divided by the quasi-static U is:

| profile | jerk [m/s³] | DAF |
| --- | --- | --- |
| trapezoid | ∞ | 1.80 |
| S-curve λ = 0.1 | 107 | 1.63 |
| S-curve λ = 0.2 | 51 | 1.37 |
| S-curve λ = 0.3 | 32 | 1.35 |
| S-curve λ = 0.5 | 16 | 0.96 |

The bellows and the carton form lightly damped modes: about 6 Hz laterally and 9 Hz axially for six cups on 10 kg. A jerk phase much shorter than their period acts like a step, so λ = 0.1 is little better than the trapezoid. From λ = 0.2 the amplification drops to about 1.36, and λ = 0.5 is quasi-static. With the linear bellows of the first version λ = 0.1 was even worse than the trapezoid (2.51 against 1.90).

## Q2: the profile at equal time

All profiles move 1 m in the same time (max U 2 means lost):

| profile | 0.70 s: peak a / max U | 0.74 s: peak a / max U | 0.80 s: peak a / max U |
| --- | --- | --- | --- |
| trapezoid | 9.18 / 2 (lost) | 8.22 / 2 (lost) | 7.03 / 1.13 |
| S-curve | 13.12 / 2 (lost) | 11.74 / 1.53 | 10.04 / 1.39 |
| polynomial 3-4-5 | 11.78 / 1.33 | 10.54 / 1.15 | 9.02 / 1.08 |
| cycloidal | 12.82 / 1.30 | 11.47 / 1.14 | 9.82 / 1.06 |

Peak accelerations are in m/s². At 0.74 s the trapezoid has the lowest peak acceleration yet is the only profile that loses the parcel; at 0.7 s the S-curve, with 43 % more peak, is lost too, and at 0.8 s all four hold. Its acceleration steps excite the bellows mode and make the leading cups peel. The others pass the U = 1 mark only briefly and hold through the lip friction margin. None of them is safe with S = 2.

## Q1 and Q3: the shortest safe move

`design.py` bisects the transfer time until the maximum U over the transfer is 0.5, for each profile, parcel, yaw and tilt (a coarse grid, then three bisection rounds, with the real simulator):

![Shortest safe transfer time per profile and parcel (yaw 0, with and without tilt)|800](assets/0963a1f02b7a.svg)

| parcel | trapezoid | S-curve | polynomial | cycloidal |
| --- | --- | --- | --- | --- |
| sealed | 1.43 / 1.61 | 1.43 / 1.39 | 1.26 / 1.08 | 1.32 / 1.08 |
| cardboard | 1.74 / 1.91 | 1.61 / 1.46 | 1.50 / 1.16 | 1.54 / 1.19 |
| porous | > 3.9 / 3.60 | 3.40 / 2.50 | 3.03 / 2.38 | 3.10 / 2.13 |

Times are T_min in seconds at yaw 0, level / tilted. The profile matters at equal peak acceleration as well. All profiles share the same quasi-static limit, but the dynamic surcharge differs (see the DAF table). A smooth profile can therefore run closer to the quasi-static limit. It also needs a higher peak for the same move time (4.5 against 5.8 to 6.4 L/T²). For cardboard the safe peak accelerations are 1.49 m/s² (trapezoid), 2.47 (S-curve), 2.57 (polynomial) and 2.66 (cycloidal), against the quasi-static limit of 2.82.

**Yaw.** At yaw 45° or 90° the short pattern side lies along the path, so the couple that balances the tipping moment has a shorter lever arm. T_min grows by 10 to 31 % (cardboard S-curve: 1.61 to 1.96 s at 45° and 2.00 s at 90°). Keep the long side of the pattern along the path.

**Tilt.** Tilting along the specific force turns most of the shear and the tipping moment into pull, which the cups carry better. For the polynomial and the cycloid T_min drops by 14 to 31 % (cardboard polynomial: 1.50 to 1.16 s, cycloidal 1.54 to 1.19 s), for the S-curve by 3 to 26 %. In `tilt-tray` the max U falls from 0.62 (level) to 0.45 at the same 1.25 s. The trapezoid gets 10 to 13 % slower with the tilt (sealed, cardboard). Its acceleration jumps, so a smooth tilt servo arrives either too early (wrong for the phase before) or too late, and the ringing peak at the step decides.

## Recommendations

- Use a smooth profile (polynomial or cycloidal) with the long side of the cup pattern along the path. Add the tray tilt if the axis is available. For cardboard this is 1.16 s against 1.74 s for a trapezoid.
- Size the generator for the most porous parcel. Porous parcels need about twice the move time, or a pump of about 140 l/min.
- With a common manifold, one cup off the parcel edge drops every cup (see `edge-leak`). Per-cup flow valves or restrictor nozzles keep the other five cups at 48.7 and 40.9 kPa.

## Checks (`expected.json`)

The 43 checks of the eight models cover the following (plus one docs check per model):

- the operating vacuum and generator flow against `sizing.operating_vacuum`;
- the pick-up vacuum at 50 ms;
- U ≤ 0.5 for every cup over the safe transfers;
- the held flag and the placed position;
- the loss of the parcel in the aggressive and porous scenarios, at the right phase;
- the topology numbers of the edge-leak variants;
- the scene bindings.
