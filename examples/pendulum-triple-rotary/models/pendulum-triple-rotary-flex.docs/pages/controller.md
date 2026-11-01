# The controller on the flexible arm

## The rigid firmware

`RotaryCtrl` is the rigid example's firmware, unchanged: a discrete TVLQR along the collocation swing-up and the latched LQR. Near the top its gains reach about 490 V/rad on the link angles and 35 to 200 V·s/rad on the link rates. Its loop gain at the upright, broken at the motor voltage, crosses 1 at 14 Hz on the rigid arm, but then falls only slowly: it is still 0.22 at 76 Hz. The design has no roll-off, because a rigid arm needs none.

On the flexible arm the arm's first bending mode (about 75 Hz with the hub on the motor) is a resonance in the loop: it lifts the loop gain to 4.3 at 76 Hz, with a phase that feeds the mode. The link encoders sit on the arm tip, so they read the tip's sideways bending as link rotation, and the rate gains turn it into a large voltage at the mode frequency. At the upright the closed loop (1 kHz, zero-order hold, `flex_design.py`) has the pole pair +276.6 ± 411.6j 1/s: the mode grows by a factor e every 3.6 ms.

![Loop gain at the upright|700](assets/8922843a20db.png)

The run never gets that far. The swing-up's large accelerations ring the arm mode, which the loop keeps at about 106 Hz. Near the top the TVLQR gains grow towards the balance gains, and from 2.90 s the frozen-time loop (the plant linearised along the nominal, closed with each table row's gains) has an arm pole that grows at 70 1/s and more. The voltage reaches the 15 V limit at the same moment (2.88 s). From then on the amplifier is saturated, the swing-up is lost, and the chain is never caught ([Ctrl/phase](signal:Ctrl/phase) never reaches 2). The firmware ends up driving the arm round at full voltage (49 rad by the end of the run).

Up to the first saturation, the bond graph and the flexible design model of `flex_design.py` (Lagrange, two clamped-free modes) agree on the modal coordinate to 3.4 µm.

![Onset of the instability|700](assets/a06c6f3bb9a3.png)

What does not help (checked in the design study with the linear loop at the upright):

- **A notch** at the arm mode. The loop gain is 3 to 4 over a wide band around the mode, and the closed-loop mode moves when the notch removes gain. A notch centred anywhere from 55 to 90 Hz left a pole in the right half plane.
- **A gentler LQR.** The gains are set by the three unstable pendulum poles (up to 23.7 1/s). Raising R by up to four orders of magnitude lowers the gains only a little, and the loop stays unstable.
- **A stiffer arm** stabilises the linear loop at the upright from E about 23 times the steel's (bare first mode about 247 Hz). The whole scenario needs more, because the gains near the top of the swing-up are larger: on the design model the rigid firmware still fails at 26 times, is marginal at 50 times (it saturates and never latches the balance LQR) and works at 100 times (`flex-e100` in the checks).

## The fix: roll-off in the loop

`RotaryCtrlLP` keeps the rigid design's weights (Q = diag(20, 200, 200, 200, 1, 5, 5, 5), R = 5) and its swing-up nominal, but the LQR and the discrete TVLQR are computed for the rigid model with a second-order low-pass

$$F(s) = \frac{1}{s^2/\omega_c^2 + 2 \zeta s / \omega_c + 1}, \qquad \omega_c = 2\pi \cdot 12\ \mathrm{Hz},\ \zeta = 0.7071$$

between the feedback and the motor (the feed-forward $u^*(t)$ bypasses it). The filter state is part of the controller's state, so the optimisation itself compensates the filter's phase lag below the corner. The gains: $K$ = -1.91, 121, -96.4, 546, -11.8, 37.6, 32.8, 50.6, and 2.37, 0.0152 on the filter state. The loop gain now crosses 1 at 7 Hz and is 0.21 at the arm resonance, so the mode is gain-stabilised: it does not matter where exactly it is.

On the flexible design model the low-pass loop is stable for an arm stiffness from 0.5 to 100 times the steel's (the design notes list the worst pole), and the whole scenario succeeds on the rigid and the flexible design model, with the arm half or twice as stiff, and with the rigid design's perturbed links and motor. The price is a slower balance loop: the push deflects the tip link by 5.7 deg instead of 3.5 deg, and the recovery takes 2.24 s instead of 1.35 s.

Back to the [overview](page:overview).
