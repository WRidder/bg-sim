# Four-wheel pyramid with gravity

The pyramid of `gravity-off` with $g_0 = 9.81$ m/s² in all five bodies. The body hangs 0.2 m below the pivot, starts tilted 0.5 rad about the world axis $(1, 1, 0)$ (the start quaternion of [Pivot](block:Pivot) is (0.96891, 0.17494, 0.17494, 0)) and swings while the wheels are driven by the same scripted torques. See the `gravity-off` model for the construction, the allocation and the checks.

![The model canvas|900](assets/840e1c830b61.png)

## Momentum balance with gravity

With gravity the torque about the pivot is the gravity torque, so

$$\frac{d H_{total}}{dt} = \tau_{gravity}, \qquad H_{total}(t) - \int_0^t \tau_{gravity}\,dt' = \text{const},$$

which the check verifies for the x and y components (explicit scales 0.4 and 0.44, `tol` 1e-9) while $H_z$ stays 0 (no vertical torque).

![Body angular momentum and wheel speeds of the swinging body|900](assets/210e2769d1ae.png)

| quantity | gravity-on (README) |
| --- | --- |
| $\max\lvert H - \int\tau_g\rvert$ (x / y) | 2.0e-12 / 2.2e-12 kg·m²/s against $H$ peaks of 0.399 / 0.432 (5.0e-12 / 4.9e-12 relative) |
| $H_z$ | 3.9e-13 |
| gravity torque of the body alone | up to 1.34 N·m; its impulse reaches 0.250 / 0.270 kg·m²/s |
| wheel speeds at 4 s (relative) | (22.86, -4.37, 24.65, 11.89) rad/s; peak 27.9 rad/s |
| pivot deflection | 3.6e-8 m |
| quaternion norm drift | 1.0e-14 |

Further checks: initial tilt; the pendulum really swings and the gravity impulse is non-zero; wheel speeds below 35 rad/s and their 4 s values; the same tap checks; no diagnostics.

## 3D view

`scenes/reaction-wheel-3d.sdf` shows the translucent body hanging from the spherical pivot with the four pyramid wheels inside. The body and each wheel are bound by their world pose (`PoseBody`, `PoseW1..4`, quaternion first); a marker on each disc rim shows the wheel spin.

![3D view at t = 1.0 s|500](assets/7c72d94a59c0.png)
