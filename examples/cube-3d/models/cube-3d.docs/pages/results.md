# Results and checks

![Tilt, wheel rates and motor voltages during the first second|900](assets/25eef469a8b3.png)

## Measured (README, real worker)

| quantity | design.py | `cube-3d` |
| --- | --- | --- |
| tilt at 0.1 s | 0.65854 deg | 0.65854 deg |
| tilt over $t \ge 3$ s (plan: below 0.5 deg) | 0.006046 deg | 0.006046 deg (1.056e-4 rad) |
| inside 0.5 deg from | 0.120 s | 0.120 s |
| tilt at 4 s | 0.00155 deg | 0.00155 deg |
| peak wheel rates relative to the cube (plan: below 400 rad/s) | 17.693 / 4.758 / 12.936 rad/s | 17.693 / 4.758 / 12.936 rad/s |
| peak $\lvert u\rvert$ | 12 V (wheels 1, 3); 4.45 V (wheel 2) | 12 V / 4.45 V / 12 V |
| quaternion norm error (plan: below 1e-6) | 1.4e-14 | 1.8e-14 |
| $\max\lvert H_z - H_z(0)\rvert$ | 2e-17 | 4.7e-17 |
| wheels' vertical momentum $H_{zw}$, peak | | 1.6e-4 N·m·s (back to 0 at the end) |

$H_z$ is the strong invariant: the wheels hold up to 1.6e-4 N·m·s of vertical momentum while the cube holds the opposite, and the sum stays at round-off. The slow closed-loop pole ($-1.36$ s$^{-1}$) is the wheel momentum bleeding off. The lighter wheels spin about 3.8 times faster than the $\Theta_w = 6\cdot10^{-4}$ wheels of the earlier version, far inside the 400 rad/s limit.

## Checks (`expected.json`, 82 checks in total for the three models)

`cube-3d`: the 2 deg start (tilt and quaternion), tilt under 0.5 deg for $t \ge 3$ s (and from 0.15 s), tilt cursor values at 0.1 to 4 s against `design.py`, peak tilt, the three wheel rates under 400 rad/s and against `design.py`, the integrated wheel angle, quaternion norm error under 1e-6, $H_z$ conserved against the wheels' $H_{zw}$, the $\pm12$ V clamp (active at the first samples, below 0.25 V after 0.1 s) and no E901, E106, W201, W202, W205 or W206.

## What to try

- Raise the start tilt (the `Cube` start values `qw..qz`, and `TILT0` in `design.py` for the reference): the clamp stays active longer and the wheels spin faster.
- Change a mass or `a` without re-running `design.py`: the gains are no longer matched, which shows the margin of the design.
- Change a weight or the sample time in `design/design.py` and run it: the new $K$ is written into all three models.
