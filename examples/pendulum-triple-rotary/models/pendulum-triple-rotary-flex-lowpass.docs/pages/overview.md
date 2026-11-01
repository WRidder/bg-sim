# Triple rotary pendulum on a flexible arm, low-pass firmware

The flexible-arm rig of `pendulum-triple-rotary-flex` (a 3 x 50 mm stainless strip as the [arm](block:Arm)) with the fixed firmware [RotaryCtrlLP](block:Ctrl): the rigid design's weights and swing-up, with the LQR and the TVLQR designed for a 12 Hz second-order low-pass between the feedback and the motor. The loop rolls off well below the arm's first bending mode (about 75 Hz), which the rigid firmware drives unstable. The docs of `pendulum-triple-rotary-flex` explain the arm, the failure and the design.

It catches at 5.00 s, balances inside 0.001 deg, and recovers from the 0.1 N push within 2.24 s (the rigid example: 1.35 s). The arm bends by up to 1.62 mm sideways in the swing-up, by 0.0 µm while balancing.

![Against the rigid arm|700](assets/0a222c0fa24a.png)

## What to try

- **3D View**: the strip's bending and twist are bound to [Arm/eta_y[1]](signal:Arm/eta_y[1]), [Arm/eta_z[1]](signal:Arm/eta_z[1]) and [Arm/eta_t[1]](signal:Arm/eta_t[1]); the view opens with exaggeration x100.
- **Dashboard**: set the arm's Young's modulus between 1e11 Pa and 2e13 Pa: the low-pass firmware holds over that range.
- Plot [Ctrl/ufb](signal:Ctrl/ufb), the filtered feedback voltage, against [Ctrl/u](signal:Ctrl/u).
