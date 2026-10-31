# Mechanism and bond graph

| part | blocks | model |
| --- | --- | --- |
| motor | [Motor](block:Motor) (`CurrentControlledDrive`) | ideal current loop, $\tau = k_t\,i$, $k_t = 0.012$ N·m/A, rotor $J_m = 1.5\cdot10^{-6}$ kg·m² |
| gearhead | [Gearhead](block:Gearhead) | ideal 3:1 transformer |
| spindle | [Spindle](block:Spindle) (project `LeadScrew`) | 3 mm lead, efficiency $\eta = 0.7$ driving, $\eta_b = 2 - 1/\eta = 0.571$ back-driven |
| wedge hook | [Wedge](block:Wedge) (project `WedgeHook`) | jaw speed = 0.5 × nut speed |
| jaw guides | [Guides](block:Guides) (project `JawGuides`) | Stribeck friction of both guides: 4 N static, 3 N Coulomb, 10 N·s/m |
| jaws | the jaw node: both jaws share the closing travel $x$ | [JawPos](block:JawPos), [JawVel](block:JawVel) |
| controller | [Ctrl](block:Ctrl) (project `GripController`) | speed loop with a current clamp, grip zone before the part |
| carriage | [Lift](block:Lift), [Transfer](block:Transfer), [Lower](block:Lower), [Retreat](block:Retreat) (`SCurveProfile`), [Carriage](block:Carriage) | prescribed position, velocity and acceleration |

The gearhead, spindle and wedge make one transformer from the motor angle to the jaw travel: per jaw the ideal force per motor torque is

$$G = \frac{2\pi N}{\ell \cdot 2\, i_w} = \frac{2\pi \cdot 3}{0.003 \cdot 2 \cdot 0.5} = 6283\ \mathrm{N\ per\ N\,m},$$

and the rotor inertia appears on the jaw travel as $J_m (2\pi N / (\ell\, i_w))^2 = 237$ kg.

## The lead screw: direction-dependent efficiency

Power from the screw to the nut (driving) loses $1 - \eta$; power from the nut to the screw (back-driving) passes only $\eta_b$. With the nut force $F_b$ and the smoothed direction $s = \tanh(\omega/w_\varepsilon)$, $w_\varepsilon = 10^{-3}$ rad/s, the screw torque is

$$\tau_a = -\frac{\ell}{2\pi} F_b + \tau_{loss},\qquad \tau_{loss} = \frac{\ell}{2\pi}\Big(\tfrac12 |F_b|\, s\,(1/\eta - \eta_b) - \tfrac12 F_b\, s^2 (1/\eta - 2 + \eta_b)\Big),$$

which is $\tau_a = -\ell F_b/(2\pi\eta)$ while driving against the load and $\tau_a = -\ell \eta_b F_b/(2\pi)$ while back-driven. A stalled drive (motor torque $\tau$) therefore holds any jaw force in the **friction band**

$$\eta\, G\, \tau \;\le\; F \;\le\; G\,\tau / \eta_b,$$

and creeps at most at the smoothing speed. For the 46 N setting the band is [46, 115] N.

## The controller

Outside the grip zone the jaws travel at 30 mm/s with the full 2.5 A. From 1 mm before the expected part (`x_pre`) the speed limit blends to `v_grip` = 3 mm/s and the current limit to the grip current $I_{grip} = F_{set}/(\eta\, k_t\, G)$. On the part the speed error saturates the current at $I_{grip}$, so the motor torque, and through the drive train the grip force, is set by the current limit:

![Closing: travel, speed, current and grip force|900](assets/c8c65828be9b.png)
