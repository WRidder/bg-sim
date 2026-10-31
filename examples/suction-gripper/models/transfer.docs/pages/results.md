# Results

![The default transfer: acceleration, cup utilisation, vacuum, parcel position|900](assets/28950e092e53.png)

## Simulation against the hand calculation

| quantity | simulation | analytic |
| --- | --- | --- |
| operating vacuum, sealed | 57 970.6 Pa | 57 971.2 Pa |
| operating vacuum, cardboard | 48 329.8 Pa | 48 329.9 Pa |
| operating vacuum, porous | 29 022.4 Pa | 29 022.6 Pa |
| vacuum 50 ms after the valve opens (sealed / cardboard / porous) | 18 731 / 18 062 / 15 693 Pa | 18 733 / 18 064 / 15 695 Pa |
| pull of cup 5 / 1 at 1.6 m/s² (sealed, slow S-curve) | 19.46 / 13.46 N | 19.61 / 13.09 N |
| shear per cup | 2.58 N | 2.68 N |
| U of cup 5 / 1 | 0.313 / 0.239 | 0.318 / 0.238 |

The slow-move loads agree within 1.9 % for the pull and 3.8 % for the shear. The difference comes from the dynamic loads the hand calculation ignores.

## Dynamic amplification and jerk

At the same peak acceleration of 4 m/s², the dynamic U divided by the quasi-static U is:

| profile | jerk [m/s³] | DAF |
| --- | --- | --- |
| trapezoid | ∞ | 1.90 |
| S-curve λ = 0.1 | 107 | 2.51 |
| S-curve λ = 0.2 | 51 | 2.10 |
| S-curve λ = 0.3 | 32 | 1.44 |
| S-curve λ = 0.5 | 16 | 1.01 |

The bellows and the carton form lightly damped modes: about 6 Hz laterally and 9 Hz axially for six cups on 10 kg. A jerk phase much shorter than their period acts like a step. At this peak, λ = 0.1 is even slightly worse than the trapezoid, because the short acceleration phase lets the excitations of its two ends add up. From λ ≈ 0.3 the amplification falls quickly, and λ = 0.5 is quasi-static.

## Q2: the profile at equal time

All profiles move 1 m in 0.7 s:

| profile | peak a [m/s²] | max U | cups lost |
| --- | --- | --- | --- |
| trapezoid | 9.18 | 2 (lost) | 6 |
| S-curve | 13.12 | 1.18 | 0 |
| polynomial 3-4-5 | 11.78 | 1.15 | 0 |
| cycloidal | 12.82 | 1.14 | 0 |

The trapezoid has the lowest peak acceleration yet is the only profile that loses the parcel. Its acceleration steps excite the bellows mode and make the leading cups peel. The others pass the U = 1 mark only briefly and hold through the lip friction margin. None of them is safe with S = 2.

## Q1 and Q3: the shortest safe move

`design.py` bisects the transfer time until the maximum U over the transfer is 0.5, for each profile, parcel, yaw and tilt (a coarse grid, then three bisection rounds, with the real simulator):

![Shortest safe transfer time per profile and parcel (yaw 0, with and without tilt)|800](assets/f974996edb45.svg)

| parcel | trapezoid | S-curve | polynomial | cycloidal |
| --- | --- | --- | --- | --- |
| sealed | 1.50 / 1.50 | 1.54 / 1.32 | 1.29 / 1.05 | 1.29 / 1.08 |
| cardboard | 1.83 / 1.83 | 1.69 / 1.58 | 1.50 / 1.19 | 1.54 / 1.19 |
| porous | > 3.9 | 3.30 / 2.95 | 3.03 / 2.73 | 3.10 / 2.44 |

Times are T_min in seconds at yaw 0, level / tilted. The profile matters at equal peak acceleration as well. All profiles share the same quasi-static limit, but the dynamic surcharge differs (see the DAF table). A smooth profile can therefore run closer to the quasi-static limit. It also needs a higher peak for the same move time (4.5 against 5.8 to 6.4 L/T²). For cardboard the safe peak accelerations are 1.35 m/s² (trapezoid), 2.24 (S-curve), 2.57 (polynomial) and 2.66 (cycloidal), against the quasi-static limit of 2.96.

**Yaw.** At yaw 45° or 90° the short pattern side lies along the path, so the couple that balances the tipping moment has a shorter lever arm. T_min grows by 10 to 25 % (cardboard S-curve: 1.69 to 2.06 s). Keep the long side of the pattern along the path.

**Tilt.** Tilting along the specific force turns most of the shear and the tipping moment into pull, which the cups carry better. For the smooth profiles T_min drops by 8 to 21 % (cardboard polynomial: 1.50 to 1.19 s, cycloidal 1.54 to 1.19 s). In `tilt-tray` the max U falls from 0.62 (level) to 0.46 at the same 1.25 s. The trapezoid gains nothing within the sweep resolution. Its acceleration jumps, so a smooth tilt servo arrives either too early (wrong for the phase before) or too late, and the ringing peak at the step decides.

## Recommendations

- Use a smooth profile (polynomial or cycloidal) with the long side of the cup pattern along the path. Add the tray tilt if the axis is available. For cardboard this is 1.19 s against 1.83 s for a trapezoid.
- Size the generator for the most porous parcel. Porous parcels need about 2.5 times the move time, or a pump of more than 130 l/min.
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
