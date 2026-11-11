# The linearised benchmark bicycle

The paper's equations of motion for small lean $\phi$ and steer $\delta$ about upright straight rolling at speed $v$:

$$M\ddot q + v\,C_1\dot q + (g K_0 + v^2 K_2)\,q = f, \qquad q = (\phi, \delta), \quad f = (T_\phi, T_\delta)$$

with the benchmark's matrices (the paper's eq. 6.1 to 6.4)

$$M = \begin{bmatrix} 80.817 & 2.319 \\ 2.319 & 0.298 \end{bmatrix},\quad C_1 = \begin{bmatrix} 0 & 33.866 \\ -0.850 & 1.685 \end{bmatrix},\quad K_0 = \begin{bmatrix} -80.95 & -2.600 \\ -2.600 & -0.803 \end{bmatrix},\quad K_2 = \begin{bmatrix} 0 & 76.597 \\ 0 & 2.654 \end{bmatrix}.$$

![The signal diagram|1000](assets/2c99715e9115.png)

The diagram solves for the two accelerations, $\ddot q = M^{-1}(f - v C_1 \dot q - (g K_0 + v^2 K_2) q)$, and integrates twice ([LeanRate](block:LeanRate), [Lean](block:Lean), [SteerRate](block:SteerRate), [Steer](block:Steer)). Each gain is one entry of the matrices, written as an expression of the global `v`: for example [K_phi_delta](block:K_phi_delta) is the $\phi\delta$ entry of $-M^{-1}(g K_0 + v^2 K_2)$. The steer torque enters through [B_phi](block:B_phi) and [B_delta](block:B_delta) (the second column of $M^{-1}$); here it is zero ([SteerTorque](block:SteerTorque)). The heading follows from the rolling kinematics, $\dot\psi = (v\delta + c\dot\delta)\cos\lambda / w$ ([Heading](block:Heading)).

Why a signal diagram and not a bond graph: $C_1$ and $K_2$ are not symmetric. They come from the rolling constraints and are neither stored energy nor dissipation, so in a bond graph they would be modulated sources driven by the states, i.e. this same diagram. The physical bond graph is [whipple](model:whipple).

## Run it

Press **Run** (instant; the dashboard re-runs on every change). The start is the paper's figure 4: 4.6 m/s and a lean rate of 0.5 rad/s.

![Lean, steer and heading at 4.6 m/s|900](assets/6cd869461b80.png)

Slide the **speed** and watch the self-stable band (4.29 to 6.02 m/s, [the benchmark bicycle](project:benchmark)): below it the weave grows, above it the lean drifts away slowly (capsize; lengthen the run to see it). At exactly the weave speed the weave neither grows nor decays:

![At the weave speed 4.2924 m/s the weave is undamped: 3.4350 rad/s, the paper's table 2|900](assets/e581f62dbb73.png)

## Checks

- The lean and steer of this model equal the matrix exponential of the paper's matrices (computed in `design/design.py`) to 1e-8.
- At the weave speed of table 2 the fitted damping is zero (to 2e-5) at the table's frequency 3.4350 rad/s.
- At 5 m/s the fitted weave matches table 2 to 0.2 %, and the 3D bond graph matches this model (see [whipple validation](model:whipple/validation)).
