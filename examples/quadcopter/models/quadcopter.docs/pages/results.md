# Results and checks

![Mission: position against set-points, attitude, tracking error|900](assets/c806b9d289ef.png)

![Rotor speeds, battery and landing-gear forces|900](assets/3d8928147ffb.png)

![Navigation filter errors against the truth|900](assets/551c63aed80a.png)

## Measured (README, real worker, `reltol` 1e-4)

| quantity | value |
| --- | --- |
| hover reached | rise 10-90 % in 1.5 s, overshoot 0.23 %, settled inside $\pm2$ cm 2.68 s after the start of the climb, hover band $\pm0.6$ cm |
| waypoint tracking (5 to 14.4 s) | RMS x 4.6 cm, y 5.0 cm, z 0.84 cm; worst distance to the set-point 12.0 cm (moves of 2 m in 2.5 to 3 s) |
| waypoints | (2.0013, 0) at 7.9 s, y = 2.016 at 10.9 s; yaw 1.603 rad at 10.9 s (set-point 1.571) |
| attitude | peak tilt 14.2 deg (limit 25), peak body rate 1.26 rad/s |
| rotors | hover 482 rad/s (4607 rpm), mission range 403 to 558 rad/s (peak 5325 rpm), limit 775 rad/s |
| electrical | hover 99 W, 7.96 A at 12.4 V; spin-up peak 62 A (pack sags to 11.4 V); 1.35 % of the 3 Ah pack used |
| navigation filter | attitude error RMS 0.53 deg, peak 1.08 deg; position error peak 2.9 cm; velocity error peak 0.11 m/s |
| landing | touches down at 17.1 s, rests at $z = 0.0847$ m with $m g$ on the four legs (13.2435 N) |
| cost | 18 s: 51 800 solver steps, compile 1 to 3 s, solve 41 to 65 s (loaded machine), 142.6 s for `run_checks.py --only quadcopter` |

## Checks (`expected.json`, 38 on this model)

- ground start: [Truth/z](signal:Truth/z) = 0.085 m at $t = 0$ and the leg force `RW/fc` = 13.2435 N at 0.3 s; the climb step response from 0.085 to 1.085 m (settling band 0.02 m); hover at 4.9 s: 1.085 m, rotor speed 482.4 rad/s (tolerance 8), battery current 7.96 A (tolerance 1.5);
- waypoints: $x = 2.0$ at 7.9 s (0.03), $y = 2.0$ at 10.9 s (0.04), yaw 1.5707963 at 10.9 s (0.06); RMS differences to the set-points over $[5, 14.4]$ s at most 0.06 / 0.065 / 0.015 m; tracking distance at most 0.15 m;
- attitude: tilt at most 0.3 rad (measured peak 0.247), roll and pitch at most 0.3 rad, quaternion norm error at most 1e-9;
- landing: $z = 0.085$ m and `RW/fc` = 13.2435 N at 18 s;
- actuators: rotor speeds at most 774.6 rad/s (peak 557.6, tolerance 25), `Esc1/u` at most 12.6 V, motor current at most 50 A, battery current at most 70 A, state of charge 0.9865 at 18 s;
- estimator: `Err/att` at most 0.03 (measured peak 0.0188), `Err/pos` at most 0.05 m, `Err/vel` at most 0.2 m/s, the gyro noise RMS against the truth at most 0.0075 rad/s, the attitude controller's rate set-point against the filter at most 0.07;
- `scene_bindings`, and no E901, E106, E007, W201, W202, W205 or W206.
