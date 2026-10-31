# Plant and LPV model

## The equation

With $h$ the gap from the magnet face down to the ball centre (positive down) and $i$ the coil current:

$$m\,\ddot h = m g - \alpha\,\frac{i^2}{h^2}, \qquad m = 0.02\ \mathrm{kg},\quad g = 9.81\ \mathrm{m/s^2},\quad \alpha = 2.4832\cdot10^{-5}\ \mathrm{N\,m^2/A^2}.$$

These are the reference's numbers. The force depends on $i^2$: the magnet only pulls, whatever the sign of the current. [Ball](block:Ball) adds two stiff stops (10⁴ N/m, 10 N·s/m) at 0.01 m and 0.3 m; in this model the ball never reaches them ([Ball/F_c](signal:Ball/F_c) stays 0).

## Trim

At rest ($\ddot h = 0$) the magnet carries the weight: $\alpha\bar\imath^2/\bar h^2 = m g$, so

$$\bar\imath = c\,\bar h, \qquad c = \sqrt{\frac{m g}{\alpha}} = 88.888\ \mathrm{A/m}.$$

The trim current is 4.444 A at 0.05 m, 13.333 A at 0.15 m and 22.222 A at 0.25 m.

## Linearisation (the LPV model)

Write $h = p + \delta h$, $i = c p + \delta i$ around the operating gap $p$. The derivatives of the force at the trim point are $\partial/\partial h\,(\alpha i^2/h^2) = -2 m g/p$ and $\partial/\partial i\,(\alpha i^2/h^2) = 2 m g/(c p) = 2 m \sqrt{g\alpha/m}/p$. So

$$\frac{d}{dt}\begin{bmatrix}\delta h\\ \delta v\end{bmatrix} = \underbrace{\begin{bmatrix}0 & 1\\ 2g/p & 0\end{bmatrix}}_{A(p)}\begin{bmatrix}\delta h\\ \delta v\end{bmatrix} + \underbrace{\begin{bmatrix}0\\ -2\sqrt{g\alpha/m}/p\end{bmatrix}}_{B(p)}\delta i, \qquad y = \begin{bmatrix}1 & 0\end{bmatrix}\begin{bmatrix}\delta h\\ \delta v\end{bmatrix}.$$

This is the reference's LPV model, with the gap $p$ as the scheduling parameter. Its transfer function is

$$G_p(s) = \frac{\delta h}{\delta i} = \frac{-b_0}{s^2 - a_0}, \qquad a_0 = \frac{2g}{p},\quad b_0 = \frac{2\sqrt{g\alpha/m}}{p} = \frac{0.2207}{p}.$$

| $p$ [m] | $a_0$ [1/s²] | $b_0$ [m/(A s²)] | unstable pole $\sqrt{a_0}$ [1/s] |
| --- | --- | --- | --- |
| 0.05 | 392.4 | 4.4145 | 19.81 |
| 0.15 | 130.8 | 1.4715 | 11.44 |
| 0.25 | 78.48 | 0.8829 | 8.86 |

The pole at $+\sqrt{2g/p}$ is the instability: a ball slightly too close is pulled harder and comes closer still. The open-loop model (`maglev-open-loop-and-linear`) measures it.

## The trim feedforward cancels the negative stiffness

The controller adds $c\,h_{measured}$ to the PID output. Linearised, $\delta i = c\,\delta h + u_{PID}$, and $b_0 c = 2g/p = a_0$, so the $a_0\,\delta h$ term cancels exactly: the PID sees the double integrator

$$\frac{\delta h}{u_{PID}} = \frac{-b_0}{s^2}.$$

The sign is negative (more current lifts the ball, so the gap shrinks); [PID](block:PID) therefore works on $e = h - r$.
