# The flexible arm

## Choice of section

The arm is a [FlexibleBeam3D](block:Arm) with `section` = rectangle: `b` = 3 mm along the arm's local y (horizontal) and `h` = 50 mm along local z (vertical), AISI 304 stainless steel (E = 193 GPa, nu = 0.29). The density 7936 kg/m³ (the stainless grades lie at 7900 to 8000) makes the strip weigh 0.2570 kg, the rigid arm's mass, and its rigid inertia about the motor axis is the rigid arm's to 0.1 %. So the flexibility is the only difference, and the stiff limit can be checked against the rigid model.

A flat strip on edge is the classic flexible link (the Quanser rotary flexible link is one): it bends easily in the plane of the motor torque and hardly at all under the pendulum's weight. The bending stiffness is EI = 21.7 N·m² horizontally and 6031 N·m² vertically; the torsion stiffness GJ = 32.4 N·m². Modes: `ny` = 2, `nz` = 2, `nt` = 1, clamped-free, modal damping 0.01.

The first horizontal mode was put a few times above the controller's fastest closed-loop pole (131 1/s, 21 Hz) and the pendulum's fastest unstable pole (23.7 1/s, 3.8 Hz): a real arm can be that flexible, and a controller designed for a rigid arm may or may not live with it. Here it does not.

## Frequencies

| mode | value |
| --- | --- |
| bare strip, clamped-free, horizontal bending | 51.27, 321.3 Hz |
| bare strip, vertical bending | 855 Hz |
| bare strip, torsion | 417.7 Hz |
| hub clamped, chain hanging: horizontal, exact frequency equation | **42.68 Hz** (assumed modes 42.69 Hz, tap test 42.66 Hz) |
| the same, Rayleigh with the chain's high-frequency mass | 43.00 Hz |
| the same, the whole chain as a rigid tip mass | 20.71 Hz (wrong, see below) |
| hub clamped, chain hanging: vertical, exact frequency equation | 111.4 Hz (assumed modes 122.3 Hz, tap test 121.9 Hz) |
| running rig (hub on the motor, no control), upright or hanging | 74.7 Hz |

The exact values solve the Euler-Bernoulli frequency equation of a clamped beam with a body at the tip, $w(s) = C_1(\cosh \beta s - \cos \beta s) + C_2(\sinh \beta s - \sin \beta s)$ with $\beta^4 = \rho A \omega^2 / EI$ and at $s = L$

$$EI\,w'' = (J \omega^2 - k_g)\,w', \qquad EI\,w''' = -M(\omega)\,\omega^2\,w.$$

- **Horizontal.** The pendulum hangs on a hinge that is free about the arm axis. A sideways push of the tip only partly carries the chain along; the rest of it swings. Its effective mass $M(\omega) = m + \omega^2 b^T (K - \omega^2 M_q)^{-1} b$ (chain mass $m$ = 0.321 kg, coupling $b$, chain mass and gravity matrices $M_q$, $K$) falls to 28.1 g well above the pendulum frequencies. Treating the 0.321 kg as a rigid tip mass gives 20.7 Hz, half the real value. $J$ is the chain's tiny inertia about the vertical, 1.03e-05 kg·m².
- **Vertical.** In the vertical plane the hinge holds the chain rigidly: the tip carries $M$ = 0.321 kg and $J$ = 0.0526 kg·m² about the tip (the long chain), and the hanging chain's gravity is a small rotational spring $k_g = m g c$. The large tip inertia makes the mode shape differ from the clamped-free modes: two assumed modes are 10 % high, three 6 %. That is harmless here: this mode is neither driven by the motor nor seen by the encoders.
- **Torsion.** The hinge does not pass a moment about the arm axis to the arm (only its bearing friction), so the pendulum's swing does not twist the strip, although the strip is very soft in torsion. The twist stays at 66.7 µrad in the controlled run. Twist would matter for an encoder housing with an offset mass, or for a pendulum fixed to the arm.
- **In the running rig** the hub is not clamped: the motor and gear add only 1.90e-03 kg·m², and the mode becomes a pinned-free-like mode at about 75 Hz, the frequency the controller meets.

The tap test (`flex-tap` in `expected.json`) checks the first two: the free model hanging at rest, the rotor inertia overridden to 1e3 kg·m² (the hub clamped), a 2 ms push on the tip link.

![Tap test: time response and spectrum|700](assets/669cbdce1a56.png)

Back to the [overview](page:overview).
