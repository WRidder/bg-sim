# The contact controller

In contact the end-effector is held on the wall by the normal force and the friction of its three wheels, and the arm is attached to it by the spherical rubber joint. The origin of $\Sigma_e$ therefore does not move, and the multirotor with its arm is **one rigid body pinned at the joint $E$**. Its three degrees of freedom are its attitude, which is why the state of the contact controller is just the angular state

$$X = [\varphi,\ \dot\varphi,\ \theta,\ \dot\theta,\ \psi,\ \dot\psi]^\top, \qquad U = [\tau_x,\ F,\ \tau_z,\ \tau_y]^\top .$$

## Constrained dynamics

Let $M = m_b + m_{arm} = 2.33$ kg be the mass carried by the thrust (the end-effector hangs on the wall), $c$ the centre of mass of the multirotor with its arm, $I_c$ the inertia about $c$, $e$ the vector from $c$ to $E$ in body axes and $u = (\cos\mu, 0, \sin\mu)$ the arm direction. Newton's law gives $M\ddot c = R F e_z - M g e_z + F_E$ with the unknown joint reaction $F_E$, and the constraint $E = c + R e = \text{const}$ gives $\ddot c = -R(\dot\omega \times e + \omega \times(\omega \times e))$. Eliminating $F_E$ (the quasi-static reaction wrench is never needed) leaves the Euler equation **about the joint**:

$$I_E \dot\omega = \tau - L_m\, u \times (F e_z) - \omega \times I_c \omega - M\, e \times (\omega \times (\omega \times e)) + M g\, e \times (R^\top e_z), \qquad I_E = I_c + M\left(\lvert e\rvert^2 I - e e^\top\right).$$

The thrust acts at the multirotor's own centre of mass, a distance $L_m$ from $E$ along $u$; $\tau$ are the rotor torques. With the Euler-angle kinematics $\omega = A(\varphi,\theta)\,[\dot\varphi, \dot\theta, \dot\psi]^\top$ this is $\dot X = f(X, U; \mu)$ (`ContactModel` in `design/design.py`; at $\theta_{sp} = 20$ degrees $e = (0.536, 0, 0.195)$ m and $\mathrm{diag}\,I_E = (0.147, 0.839, 0.797)$ kg m$^2$).

## Equilibrium

For a pitch set-point $\theta_{sp}$ the servo holds the arm at $\mu_c = \theta_{sp}$, which makes the arm **level in the world**. Then the wall reaction is horizontal and

$$\varphi = \psi = 0,\quad \theta = \theta_{sp},\quad \dot X = 0,\qquad F_{eq} = \frac{m g}{\cos\theta_{sp}},\qquad F_N = m g \tan\theta_{sp},\qquad \tau_{y,eq} = -m_{arm}\, g\, \frac{L_m}{2},$$

with all other torques zero. The pitch torque only compensates the moment of the tube's weight about the multirotor (the constant of the free-flight controller, for the tube alone, because the end-effector's weight is carried by the wall). The model checks this numerically: it finds $\tau_{y,eq}$ from the Euler equation and compares it with the closed form.

## Linearisation and LQR

Linearising $\dot X = f(X,U;\mu_c)$ about the equilibrium gives $\dot X = A(\theta_{sp})(X - X_{eq}) + B(\theta_{sp})(U - U_{eq})$. At $\theta_{sp} = 20$ degrees (rows $\varphi, \dot\varphi, \theta, \dot\theta, \psi, \dot\psi$; columns $\tau_x, F, \tau_z, \tau_y$)

$$A = \begin{bmatrix} 0.00 & 1.00 & 0.00 & 0.00 & 0.00 & 0.00 \\ -3.91 & 0.00 & 0.00 & 0.00 & 0.00 & 0.00 \\ 0.00 & 0.00 & 0.00 & 1.00 & 0.00 & 0.00 \\ 0.00 & 0.00 & 0.00 & 0.00 & 0.00 & 0.00 \\ 0.00 & 0.00 & 0.00 & 0.00 & 0.00 & 1.00 \\ 12.61 & 0.00 & 0.00 & 0.00 & 0.00 & 0.00 \end{bmatrix}, \qquad B = \begin{bmatrix} 0.00 & 0.00 & 0.00 & 0.00 \\ 16.57 & 0.00 & 5.69 & 0.00 \\ 0.00 & 0.00 & 0.00 & 0.00 \\ 0.00 & 0.67 & 0.00 & 1.19 \\ 0.00 & 0.00 & 0.00 & 0.00 \\ 5.00 & 0.00 & 2.91 & 0.00 \end{bmatrix} .$$

The plane of symmetry $x_b z_b$ makes the linearisation fall apart exactly: pitch $(\theta, \dot\theta)$ is driven by the thrust variation and the pitch torque only, roll and yaw $(\varphi, \psi)$ are coupled with each other and driven by the roll and yaw torques only. `design.py` asserts the cross terms vanish ($<10^{-6}$) and solves the two continuous Riccati equations separately, so the structure of the gain is exact, not rounded:

$$U = -K(\theta_{sp})\,(X - X_{sp}) + U_{eq}, \qquad X_{sp} = [0, 0, \theta_{sp}, 0, \psi_{sp}, 0]^\top .$$

The weights ($Q = \mathrm{diag}(40, 2, 100, 3, 40, 3)$, $R$ from 1.5 N m, 1.2 N, 0.3 N m and 1 N m as the input size that costs one unit) put the closed loops at 2 to 4 rad/s: well below the 38 rad/s rate loops and the 60 Hz gyro filter. At 20 degrees

$$K = \begin{bmatrix} 17.547 & 1.157 & 0.000 & 0.000 & 8.807 & 5.236 \\ 0.000 & 0.000 & 6.724 & 2.764 & 0.000 & 0.000 \\ 0.652 & -0.064 & 0.000 & 0.000 & 0.705 & 0.386 \\ 0.000 & 0.000 & 8.282 & 3.404 & 0.000 & 0.000 \end{bmatrix}, \qquad K(27^\circ) = \begin{bmatrix} 15.973 & 0.788 & 0.000 & 0.000 & 8.687 & 5.079 \\ 0.000 & 0.000 & 6.480 & 2.681 & 0.000 & 0.000 \\ 0.666 & -0.099 & 0.000 & 0.000 & 0.762 & 0.425 \\ 0.000 & 0.000 & 8.417 & 3.482 & 0.000 & 0.000 \end{bmatrix}$$

(rows $\tau_x, F, \tau_z, \tau_y$; columns $\varphi, \dot\varphi, \theta, \dot\theta, \psi, \dot\psi$). **Structure, as in the paper:** the roll and yaw torques use only the columns of $\varphi, \dot\varphi, \psi, \dot\psi$; the thrust and the pitch torque use only $\theta, \dot\theta$; everything else is exactly zero ([Con/kzero](signal:Con/kzero) is the sum of the twelve forbidden entries and stays 0 during the whole run).

![Scheduled gains|720](assets/3717b5e97ebf.png)

## Gain scheduling and stability

$K$ is computed on a grid $\theta_{sp} = 10, 15, \ldots, 45$ degrees and stored as the table of [Con](block:Con); the block interpolates linearly with hat functions, so the gain follows the reference as it ramps ([Con/K[1]](signal:Con/K[1]) is $K_{\tau_x \varphi}$ along the run). The spectral abscissa of $A - BK$ over the grid lies between -2.75 and -1.59 1/s ([Con/sa](signal:Con/sa)); the open-loop poles are the undamped pendulum modes $\pm 1.5$ to $2.2$ i rad/s and four zeros (roll and yaw are neutral).

![Closed-loop poles|420](assets/af832b9cc597.png)

## Implementation

[Con](block:Con) (250 Hz) converts the navigation filter's quaternion and the bias-corrected gyro to the Euler angles and rates, forms $X - X_{sp}$ ([Con/Xe[3]](signal:Con/Xe[3]) is the pitch error), interpolates $K$ and outputs the thrust and the three torques, which go straight to the mixer: no attitude or rate loop is in the way. There is no integral action; the model mismatch (the end-effector's weight, the arm's inertia, the sensor lag) leaves a pitch error below 1 degree, as in the paper.

Back to [the overview](page:overview).
