# Results and checks

![Speeds (scaled by the gear ratio), rod twist and motor current|900](assets/b72ac05e7ea7.png)

The wheel speeds are multiplied by 10 in the plot to lie on the motor speed. After the load step at 1 s the twist settles at 0.1 rad.

## Acceptance checks (`expected.json`)

| signal at $t = 2$ s | expected | tolerance |
| --- | --- | --- |
| [Motor1/shaft.f](signal:Motor1/shaft.f) | 113.86311499086523 rad/s | relative 1e-3 |
| [Gear1/b.f](signal:Gear1/b.f) | 11.386311499086522 rad/s | relative 1e-3 |
| [Wheel2/a.f](signal:Wheel2/a.f) | 11.388161507683192 rad/s | relative 1e-3 |
| [Motor1/i](signal:Motor1/i) | 0.6136987112051235 A | relative 1e-3 |
| [Rod/phi](signal:Rod/phi) | 0.09996294077514448 rad | relative 1e-3 |

Further checks: the ratio [Motor1/shaft.f](signal:Motor1/shaft.f) / [Gear1/b.f](signal:Gear1/b.f) is 10 (relative 1e-6); [Wheel1/a.f](signal:Wheel1/a.f) / [Wheel2/a.f](signal:Wheel2/a.f) is 1 at 2 s (relative 1e-3); the largest $|\varphi|$ in $[0.01, 1]$ s is 0.18648149316390142 rad (relative 1e-3); the motor speed of this model and of the bond graph model agree to 5e-5 rad/s over the whole run.
