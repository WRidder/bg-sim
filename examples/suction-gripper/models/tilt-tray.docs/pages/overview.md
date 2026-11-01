# Tilt tray: the waiter's tray

This model runs a cycloidal transfer of 1.25 s (peak 4.0 m/s²) with `k_tilt` = 1. The gripper tilts along the specific force (a - g), up to [Path/theta](signal:Path/theta) = 15.2°. The preview profiles drive the tilt servo 2/ω = 0.13 s ahead of the motion, so the tilt and the acceleration coincide.

![Tilt, acceleration and utilisation|900](assets/f58613d6a7ad.png)

The maximum U is 0.45, which is safe with S = 2. Held level, the same move reaches U = 0.62 (design.py). The cycloid needs 1.54 s level and 1.19 s tilted for cardboard.
