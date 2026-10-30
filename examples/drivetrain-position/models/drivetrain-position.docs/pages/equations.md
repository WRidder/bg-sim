# Equations

With the ideal gear, $J_{eq} = J_m + J_1/n^2 = 6\cdot10^{-5}$ kg·m². The state is $x = (\theta_m, \omega_m, i, \theta_L, \omega_L)$, the shaft twist $\delta = \theta_m/n - \theta_L$ and the shaft torque $\tau = k\,\delta + c\,\dot\delta$:

$$L\,\dot i = V - R\,i - k_t\,\omega_m,$$

$$J_{eq}\,\dot\omega_m = k_t\,i - R_d\,\omega_m - \frac{\tau}{n}, \qquad J_2\,\dot\omega_L = \tau - T_{load}.$$

These are the equations of the bond graph; `design/design.py` integrates them (exactly, with a zero-order hold) and the model `drivetrain-position-open-loop` checks the bond graph against them to $10^{-8}$ rad.

## The mode

With the motor held by its back-EMF, the load wheel hangs on the shaft spring:

$$f_{mode} = \frac{1}{2\pi}\sqrt{\frac{k}{J_2}} = 3.90\ \text{Hz}.$$

The poles of the voltage-driven plant are $-0.84 \pm 24.5\,j$ (3.91 Hz, $\zeta = 0.034$), two real poles at $-213$ and $-788$ rad/s (the mechanical and the electrical time constant) and one pole at zero (the position). With the motor free instead (shaft damping alone) the mode is 4.50 Hz with $\zeta = 0.012$; the back-EMF damps it a little and keeps it near 3.9 Hz.

A position loop with a bandwidth of 5 Hz or more, which a rigid-body design asks for, has to cross over beside this mode.

## Design model

For the controller the electrical pole at 160 Hz is treated as quasi-static ($i = (V - k_t\omega_m)/R$):

$$\dot\delta = \frac{\omega_m}{n} - \omega_L, \quad J_{eq}\dot\omega_m = -\Big(\frac{k_t^2}{R} + R_d + \frac{c}{n^2}\Big)\omega_m - \frac{k}{n}\,\delta + \frac{c}{n}\,\omega_L + \frac{k_t}{R}\,V, \quad J_2\dot\omega_L = k\,\delta + \frac{c}{n}\,\omega_m - c\,\omega_L - T_{load}.$$

The firmware discretizes this model with a zero-order hold at 1 ms. The prediction in `design/design.py` uses the full 5-state model with the inductance, so the difference between the two is part of what `expected.json` checks.
