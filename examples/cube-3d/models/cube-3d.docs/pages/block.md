# The equation block `CornerCube`

## Geometry and mass model

Body frame: the axes lie along the cube edges at the pivot, the cube occupies $[0, a]^3$. The wheel spin axes are the body axes; wheel $i$ is mounted on the inside of the face $x_i = a$, centred on the face, its centre $d$ inside the face:

| wheel | spin axis | centre $p_i$ (m) |
| --- | --- | --- |
| 1 | $x$ | (0.140, 0.075, 0.075) |
| 2 | $y$ | (0.075, 0.140, 0.075) |
| 3 | $z$ | (0.075, 0.075, 0.140) |

The arrangement is invariant under permutations of the axes, so the centre of mass stays on the body diagonal and the equilibrium is still "diagonal vertical".

| item | value | why |
| --- | --- | --- |
| wheel | steel rim wheel, radius 0.055 m, thickness $h$ = 12 mm, mass $m_w$ = 0.08 kg | leaves a 20 mm margin to the face edges and the wheels do not touch each other |
| inset $d$ | 10 mm = $h/2$ + 4 mm mounting gap | |
| axial inertia $\Theta_w$ | $1.9\cdot10^{-4}$ kg·m² (0.79 $m_w R^2$, rim-heavy) | rotor included |
| transverse inertia $\Theta_{wt}$ | $9.6\cdot10^{-5}$ kg·m² | $\Theta_w/2 + m_w h^2/12$ |
| structure | $m_s$ = 0.18 kg (frame, electronics, motors), $\Theta_s = 1.125\cdot10^{-3}$ kg·m² | thin cubic shell $\tfrac{5}{18} m_s a^2$; total mass $m_s + 3 m_w = 0.42$ kg |

The earlier example kept $\Theta_w = 6\cdot10^{-4}$ for each wheel at the cube centre. That is not possible for a wheel that fits on a 0.15 m face within a 0.42 kg total: a thin ring of radius 0.055 m has $m R^2 = 2.4\cdot10^{-4}$ for 0.08 kg, and $6\cdot10^{-4}$ would need 0.2 kg per wheel. So $\Theta_w$ is now $1.9\cdot10^{-4}$ (the wheels are three times weaker, and the design and numbers were redone).

Derived quantities (the block computes them from the parameters; `design.py` builds the same by the parallel-axis theorem body by body and the two agree to 1e-9):

$$m = m_s + 3 m_w = 0.42\ \mathrm{kg}, \qquad r = \frac{m_s\,a/2 + m_w\,(2a - d)}{m}\,(1, 1, 1) = 0.087381\ \mathrm{m}\,(1, 1, 1),$$

$$\Theta_c = \Theta_s I + m_s\big(\lvert c\rvert^2 I - c\,c^T\big) + \sum_i \Big[m_w\big(\lvert p_i\rvert^2 I - p_i p_i^T\big) + \Theta_{wt}\,(I - e_i e_i^T)\Big],$$

which comes out as a matrix with diagonal $8.2778\cdot10^{-3}$ and off-diagonal $-3.1425\cdot10^{-3}$ kg·m² (with $c = \tfrac a2 (1,1,1)$ the structure centre and $e_i$ the axis of wheel $i$). $\Theta_c$ is the inertia about the pivot with the wheels' spin excluded; the axial inertia of each wheel is $\Theta_w$ in $L_w$.

## Equations

States: the unit quaternion $q$ (body to world), the body rates $\omega$ and the wheel rates relative to the body $w_r$. With $T$ the torque the motors put on the wheels and $g_b = R^T\,(0, 0, -g)$:

$$L = \Theta_c\,\omega + \Theta_w\,(\omega + w_r), \qquad \dot\omega = \Theta_c^{-1}\big(-\omega \times L + r \times m g_b - T\big), \qquad \dot w_r = \frac{T}{\Theta_w} - \dot\omega, \qquad \dot q = \tfrac12\,q \otimes [0, \omega].$$

Block parameters of [Cube](block:Cube): `ms` 0.18, `mw` 0.08, `a` 0.15, `d` 0.01, `Ths` 1.125e-3, `Thw` 1.9e-4, `Thwt` 9.6e-5, `g` 9.81. Three `Rotation` ports `m1`, `m2`, `m3` carry `mi.f` $= w_{r,i}$ and $T_i =$ `mi.e`; the reaction $-T$ on the cube is inside the $\dot\omega$ equation, so each motor has its stator on a fixed shaft. Outputs: `pose` (the 7-element chart $(q_w, q_x, q_y, q_z, 0, 0, 0)$ that the controller reads), `omega`, `wheel`, `tilt` (angle between the body diagonal and the vertical), `qerr` ($\lvert q\rvert - 1$), `Hz` (vertical angular momentum about the pivot), `Hzw` (the wheels' part of it) and the integrated wheel angles `phi1..3`. The start value is the equilibrium tilted 2 deg about the world $x$ axis; the equilibrium rotates the diagonal $(1,1,1)/\sqrt3$ onto $(0,0,1)$: axis $(1,-1,0)/\sqrt2$, angle $\arccos(1/\sqrt3)$, $q_{eq} = (0.88807, 0.32506, -0.32506, 0)$.

Language limits met while writing it (all in the block, none in the compiler): the language has no matrix solve, so with $\Theta_c = (T_d - T_o)\,I + T_o\,u u^T$ ($u = (1,1,1)$) the inverse is written in closed form,

$$\Theta_c^{-1} = \frac{1}{T_d - T_o}\Big(I - \frac{T_o}{T_d + 2 T_o}\,u u^T\Big),$$

and `cross` needs equal units on both arguments (E006), so the cross products are written out component by component.
