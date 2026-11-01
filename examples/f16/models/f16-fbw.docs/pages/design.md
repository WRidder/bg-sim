# Design

## Law

With $\alpha$ in deg, $q$ and $q_{cmd}$ in deg/s and the elevator $u$ in deg:

$$u = K_\alpha \alpha + K_q (q - k_{ff} q_{cmd}) + \xi, \qquad \dot\xi = K_i (q - q_{cmd}) + \frac{\mathrm{sat}(u) - u}{T_{aw}}$$

with $k_{ff} = 0.5$ and $T_{aw} = 0.1$ s. The integral accumulates $K_i$ times the error, so gains that change with the flight condition do not make the output jump.

## Gains

At every point of a 5 × 5 grid (qbar 80, 200, 400, 800, 1400 psf; Mach 0.2 to 1.0) `design/fbw.py` trims the aircraft at the altitude where that Mach gives that dynamic pressure, linearises it, and solves an LQR problem on the short-period states plus the integral of the pitch-rate error, with weights $Q = \mathrm{diag}(0.1, 0.5, 30)$ and $R = (M_\delta/6)^2$. Normalising $R$ by the elevator's pitch effectiveness $M_\delta$ makes the weights mean the same everywhere, and the gains fall roughly as $1/\bar q$: from $K_q = 3.2$ at 80 psf to 0.08 at 1400 psf.

Checked on the full linear model with the servo lag at every grid point: all closed-loop poles left of $-0.068$, pitch-rate step rise 0.21 to 0.60 s, overshoot at most 5.2 %. The book's data have no Mach effects, yet the Mach axis matters: at the same $\bar q$, a higher Mach means a higher true airspeed, and the lift and damping terms scale with $\bar q / V_t$.
