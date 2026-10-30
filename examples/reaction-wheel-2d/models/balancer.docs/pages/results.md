# Results and checks

![Body angle, wheel speed and motor torque|900](assets/148bda074df7.png)

## Measured (README)

| quantity | value |
| --- | --- |
| $\lvert\theta\rvert$ over the run | 0.011969 rad at the pulse (band 0.02) |
| $\theta$ at 0.5 s (initial tilt recovered) | 0.000907 rad |
| tracked error before the pulse | $\max\lvert e\rvert = 1.72\cdot10^{-3}$ rad over $[0.4, 0.5]$ s |
| wheel speed | 0 to 47.046 rad/s (peak at 1.782 s), 46.213 rad/s at the end |
| motor torque | -0.195 to 0.269 N·m (limit 1.5) |
| mechanical energy | 6.3762 J to a peak of 8.5877 J (the wheel's 2.211 J) |
| states | 12 differential (2 x P[3], 2 x d[2], 2 x q), no W201 |

## Checks (`expected.json`)

$\theta_0 = 0.01$; $\lvert\theta\rvert \le 0.02$ rad over the run; the tilt is recovered to 0.9 mrad at 0.5 s and the tracked error stays under 2 mrad before the pulse; the wheel starts at rest, peaks at 47.05 rad/s and keeps 46.21 rad/s; the torque stays inside 1.5 N·m; the wheel speed stays under 50 rad/s; the mechanical energy is bounded by 8.9 J $= E_0 + \tfrac12 J_w 50^2$; no W201, E101, E102, E103, E106 or W206.
