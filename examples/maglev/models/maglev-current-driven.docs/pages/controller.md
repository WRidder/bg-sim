# Controller design

## Structure

[PID](block:PID) (the project block `ScheduledPID`) computes

$$u = f_{ff} + K_p e + K_i\!\int e\,dt + K_d\,\frac{s}{T_f s + 1}\,e, \qquad e = h - r,\quad T_f = 1\ \mathrm{ms},$$

with $f_{ff}$ = [Trim/y](signal:Trim/y). The reference uses a crossover of 50 rad/s and $T_f$ = 1 ms; we keep both and choose a phase margin of 60°.

## Gains in closed form

Write the PID in series form with a double real zero:

$$C(s) = K\,\frac{(s + z)^2}{s\,(T_f s + 1)}.$$

The design plant is the frozen linearisation $b_0/(s^2 - a_0)$ (without the feedforward). Its phase is −180° at every frequency, so the phase margin is the phase of $C$ at the crossover $\omega_c$:

$$\mathrm{PM} = 2\arctan\frac{\omega_c}{z} - 90^\circ - \arctan(\omega_c T_f) \;\Rightarrow\; z = \frac{\omega_c}{\tan\theta}, \quad \theta = \frac{\mathrm{PM} + 90^\circ + \arctan(\omega_c T_f)}{2}.$$

This gives $z$ = 12.07 rad/s, the same for every $p$. The magnitude condition $|C(j\omega_c)|\,b_0/(\omega_c^2 + a_0) = 1$ gives

$$K = \frac{\omega_c^2 + a_0}{b_0}\cdot\frac{\omega_c\sqrt{1 + (\omega_c T_f)^2}}{\omega_c^2 + z^2}.$$

The parallel gains follow by matching numerators, $K_i = K z^2$, $K_p = 2 K z - K_i T_f$, $K_d = K - K_p T_f$:

| $p$ [m] | $K_p$ [A/m] | $K_i$ [A/(m s)] | $K_d$ [A s/m] | crossover / PM, design plant | crossover / PM, with feedforward |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 297.42 | 1805.46 | 12.101 | 50.0 rad/s / 60.0° | 57.1 rad/s / 62.9° |
| 0.15 | 811.57 | 4926.51 | 33.019 | 50.0 rad/s / 60.0° | 52.4 rad/s / 61.0° |
| 0.25 | 1325.71 | 8047.55 | 53.937 | 50.0 rad/s / 60.0° | 51.4 rad/s / 60.6° |

`design/design.py` computes these numbers and checks them on a frequency grid. With the feedforward the plant is $b_0/s^2$, so the loop crosses a little higher and keeps slightly more phase. The closed-loop poles at 0.15 m are −948.9, −21.3 ± 21.0j and −8.5 (1/s).

## Scheduling: tables, not formulas

$K$ is affine in $p$: $(\omega_c^2 + 2g/p)/b_0 = (\omega_c^2 p + 2g)/(2\sqrt{g\alpha/m})$, and $z$ does not depend on $p$. So $K_p$, $K_i$ and $K_d$ are straight lines in $p$, and linear interpolation between the three design points is exact (the midpoint check in `design.json` agrees to 2·10⁻¹⁶). The model uses three `Lookup1D` blocks ([KpTab](block:KpTab), [KiTab](block:KiTab), [KdTab](block:KdTab)) on the measured gap, as the reference does with its gain tables: the design points stay visible, and a design that is not affine in $p$ fits the same blocks. Outside 0.05 … 0.25 m the tables hold the end values.

## Prefilter and ideal response

[Pre](block:Pre) is the reference's optional prefilter $10/(s + 10)$ ($\tau$ = 0.1 s). It removes the overshoot that the two PID zeros would cause on a raw step. [Ideal](block:Ideal) is the reference's target response $900/(s^2 + 42 s + 900)$ (30 rad/s, damping 0.7) on the same prefiltered setpoint.
