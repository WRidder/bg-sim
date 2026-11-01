# Hand calculation

`design/analysis.py` computes these numbers. `expected.json` checks the simulations against them.

## Operating vacuum

The ejector curve meets the leak past the sealed lip: $Q_{max}(1 - \Delta p/\Delta p_{max}) = Q_{leak}(\Delta p)$ gives $\Delta p$ = 59 152 Pa. The holding capacity is $A_{eff}\Delta p$ = 29.58 N, and the static utilisation of the 0.6 kg box is $mg/F_{cap}$ = 0.199.

## Static hold and lift stroke

At rest the bellows force carries the box: $k_{ax}\,ext + A_{fold}\Delta p - F_{bot} = m g$. The vacuum lift is $A_{fold}\Delta p$ = 10.06 N, which alone would contract an unloaded cup by 4.022 mm. The box weighs 5.88 N, so

$$ext = \frac{m g - A_{fold}\Delta p}{k_{ax}} = \frac{5.884 - 10.056}{2500} = -1.668\ \text{mm}$$

The hanging cup is shorter than its rest length, so on the table the cup lifts the box 1.668 mm. The linear cup stretches to +2.354 mm instead.

## Axial mode

At the hang the folds do not touch ($-ext < s_{bot}$), so the tangent stiffness is $k_{ax}$:

$$\omega_n = \sqrt{k_{ax}/m} = 64.55\ \text{rad/s}\ (10.27\ \text{Hz}),\qquad \zeta = \frac{d_{ax}}{2\sqrt{k_{ax} m}} = 0.103$$

## Lateral modes

The box hangs on the bellows with its centre of mass $h$ = 20 mm below the lip. With the lateral bellows deflection $e$ and the box tilt $\varphi$ as coordinates, linearised about the hang:

$$\begin{bmatrix} m & -m h \\ 0 & J \end{bmatrix}\ddot q + \begin{bmatrix} k & 0 \\ h k & k_t + m g h \end{bmatrix} q = -\begin{bmatrix} m \\ 0 \end{bmatrix}\ddot x_T$$

with $k = k_{lat}k_f$, $k_t = k_{tilt}k_f$ and $k_f$ = 1.871 at the hang. The two modes are 6.55 Hz (sway: the box swings sideways) and 13.20 Hz (tilt: the box rocks on the lip). The linear cup ($k_f$ = 1) has 4.89 and 9.69 Hz. The steady-state transmissibility from the tool to the box's centre of mass peaks at 4.58 near 6.5 Hz.

## Quasi-static utilisation

For a steady tool acceleration $a$ along x: $U = (m g + 4 m a h / D_{lip} + m a/\mu)/F_{cap}$. That is 0.34, 0.47 and 0.61 for the steps at 1.5, 3 and 4.5 m/s², and the limit U = 1 is at 8.8 m/s². The 0.8 kg overload box reaches 0.996 at 6 m/s².

For a steady tool tilt θ, gravity splits into the pull $mg\cos\theta$ and the shear $mg\sin\theta$. At 30° U = 0.620 and the lateral deflection is $mg\sin\theta/(k_{lat}k_f)$ = 1.016 mm, with $k_f$ evaluated at the axial load $mg\cos\theta$.
