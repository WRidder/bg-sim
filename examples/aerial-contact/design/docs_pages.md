@@ overview | - | Overview
# Multimodal aerial manipulator with a contact controller

A hexarotor flies up to a wall, pushes an end-effector on it with a tilted thrust vector, and drives the end-effector's three omnidirectional wheels so that it climbs and descends the wall while the multirotor follows it. This is the system of Wopereis, van de Ridder, Lankhorst, Klooster, Bukai, Wuthier, Nikolakopoulos, Stramigioli, Engelen and Fumagalli, *Multimodal Aerial Locomotion: An Approach to Active Tool Handling*, IEEE Robotics & Automation Magazine, December 2018 (X5.8).

The model contains

- a 2.1 kg hexarotor (80 cm across, 950 Kv motors, 10x4.5 in propellers, 16 V tether, 78 N maximum thrust) as a multibond floating body, every rotor a chain [Esc1](block:Esc1) - [Drv1](block:Drv1) - [Prop1](block:Prop1) (six of them), the air and rotor wrench in [RW](block:RW);
- a one-DoF manipulator: a position servo [Servo](block:Servo) about the body y axis, driven by [ServoCtl](block:ServoCtl), and a 0.6 m carbon tube [Arm](block:Arm) (0.23 kg, rigid);
- the rubber shock mount [Rub](block:Rub), a compliant spherical joint with the spring-damper [RubK](block:RubK), and the 0.15 kg end-effector [EE](block:EE);
- three omnidirectional wheels at 120 degrees, each an anisotropic contact [Wheel1](block:Wheel1), [Wheel2](block:Wheel2), [Wheel3](block:Wheel3) against the wall [Wall](block:Wall), driven open loop by [Omni](block:Omni);
- the firmware: sensors ([Imu](block:Imu), [Gps](block:Gps)) and the navigation filter [Nav](block:Nav), the phase machine [Sup](block:Sup), and three controllers: the free-flight cascade ([Pos](block:Pos), [Att](block:Att), [Rate](block:Rate)), the engage controller [Eng](block:Eng) and the gain-scheduled LQR contact controller [Con](block:Con), selected by [Sel](block:Sel) and allocated to the rotors by [Mix](block:Mix).

The run lasts 34 s and starts in hover (there is no take-off; the landing legs of the quadcopter example are not part of this model). It approaches the wall in free flight, engages with the pitch reference $\theta_{sp}$ ramping from 12 to 20 degrees, holds contact while $\theta_{sp}$ ramps to 27 degrees, climbs 0.30 m and descends again by an open-loop wheel velocity command, disengages by $C = 0.75$ m and hovers.

@RUN@

## Run it

Press **Run** (about 25 s of wall time; every 4 ms discrete tick is recorded as a left/right event pair, so the run holds 17 001 rows of about 2 560 signals, 350 MB). Then plot [WallForce/N](signal:WallForce/N) against [WallForce/Npred](signal:WallForce/Npred): the measured normal force follows the quasi-static prediction $m g \tan\theta_{sp}$ of the paper. Open the 3D view: the arm joint turns with [Servo/qout](signal:Servo/qout), the wheels with [Omni/phi1](signal:Omni/phi1).

Continue with [the system](page:system), [the phase machine](page:phases), [the free-flight controller](page:flight), [the contact controller](page:contact), [the manipulator and the end-effector](page:manipulator) or [the results](page:results).

@@ system | overview | The system and its conventions
# The system and its conventions

| part | data |
| --- | --- |
| multirotor | 2.1 kg, inertia $\mathrm{diag}(0.055, 0.055, 0.105)$ kg m$^2$, six rotors at radius 0.4 m, angles 30, 90, ..., 330 degrees (the arm passes between the two front rotors), spin alternating |
| propulsion | 950 Kv, $k_t = k_e = 0.01005$ N m/A, $R = 0.11\ \Omega$, $L = 40\ \mu$H, rotor + propeller inertia $5\cdot 10^{-5}$ kg m$^2$; thrust $T = 1.42\cdot 10^{-5}\,\omega\,\lvert\omega\rvert$, drag torque $Q = 2.03\cdot 10^{-7}\,\omega\,\lvert\omega\rvert$; 16 V constant supply; 13 N (957 rad/s) per rotor, 78 N in total |
| manipulator | servo (stall torque 8.4 N m) about $y_b$ at the centre of mass, rigid tube $L_m = 0.6$ m, 0.23 kg |
| flexible joint | rotational spring 1 N m/rad, damper 0.03 N m s/rad between the tube tip and the end-effector (a spherical joint) |
| end-effector | 0.15 kg, centre of mass 3 cm ahead of the joint, wheel contact points on a circle of radius 4.5 cm, 6 cm ahead of the joint |
| wall | plane $x_w = 1.6$ m, normal $-x$ |

**Frames.** $\Sigma_w$ is the world frame with $z$ up. $\Sigma_b$ is the multirotor frame at its centre of mass: $x_b$ forward, $y_b$ left, $z_b$ along the thrust. $\Sigma_e$ has the orientation of $\Sigma_w$ in contact and its origin at the elastic joint; the origin of $\Sigma_e$ always lies in the $(x_b, z_b)$ plane. Roll, pitch and yaw $(\varphi, \theta, \psi)$ are Z-Y-X Euler angles, $R = R_z(\psi) R_y(\theta) R_x(\varphi)$: a positive pitch is a rotation about $+y$, it tips the nose down and tilts the thrust vector forward, towards the wall.

**The manipulator angle.** $\mu$ is the elevation of the arm above the body $x$ axis; the servo joint angle is $q = -\mu$ ([ServoCtl/mu](signal:ServoCtl/mu) shows $\mu$). In free flight $\mu_{sp} = \theta_b$ keeps the arm level in the world, so the end-effector is in front of the multirotor.

**Modelling choices.** The model starts in hover. Air is still. The sensors are a 250 Hz IMU and a 50 Hz position fix; the accelerometer feels the arm's reaction ([SpecF](block:SpecF)), which is large in contact. The brush of the end-effector (a constant 6 N once compressed) is not modelled.

Back to [the overview](page:overview).

@@ phases | overview | The phase machine
# The phase machine

[Sup](block:Sup) holds the operator script and the discrete switching logic of Fig. 5 of the paper (50 Hz). Its output [Sup/phase](signal:Sup/phase) is 0 free flight, 1 engage, 2 contact, 3 disengage.

| transition | condition |
| --- | --- |
| 0 to 1 (engage) | the engage request at $t \ge 4.5$ s **and** the end-effector (wheel plane, estimated from the navigation filter and the arm angle) within 30 cm of the wall: the guard `d_guard`. Latches $t_e$ and $z_{sp} = z_b(t_e)$ |
| 1 to 2 (contact) | the wheel plane within 2 cm of the wall and the multirotor at rest ($\lvert v_x\rvert < 0.1$ m/s) for 0.3 s, i.e. the wall has stopped it (a fallback after 3 s) |
| 2 to 3 (disengage) | the request at $t \ge 28.5$ s. Latches $p_{sp} = (x_b(t_d) - C,\ y_b(t_d),\ z_b(t_d))$ with $C = 0.75$ m |

What runs in each phase:

1. **Free flight.** The position set-point follows a minimum-jerk move (0.45 to 0.75 m in x, the incremental set-points of the paper); the cascade of [the free-flight controller](page:flight) tracks it. $\mu_{sp} = \theta_b$.
2. **Engage.** [Eng](block:Eng) takes the three body angles as references, $(\varphi_{sp}, \theta_{sp}, \psi_{sp}) = (0, \theta_{sp}, 0)$, and holds the height $z_{sp} = z_b(t_e)$ with a PI loop on the vertical velocity: $F = m (g + a_z) / (\cos\varphi\cos\theta)$. There is no horizontal position loop; the tilted thrust carries the multirotor into the wall. The reference $\theta_{sp}$ starts at 12 degrees and ramps to 20 degrees over 4 s to soften the impact. $\mu_{sp} = \theta_b$.
3. **Contact.** The purely angular contact controller [Con](block:Con) of [its own page](page:contact) runs. It has no position input, so the multirotor follows the end-effector without any change of its set-points. $\mu_{sp} = \mu_c = \theta_{sp}$, and $\theta_{sp}$ ramps on to 27 degrees (4 s after the engage instant, over 3 s). The open-loop wheel velocity command $(v_y, v_z)$ in $[-1, 1]$ is issued only in this phase: 0.125 for 6 s from $t = 13$ s, a 2 s pause, -0.125 for 6 s, with 0.4 s smooth ramps.
4. **Disengage.** The free-flight controller runs with the latched step set-point.

[Sel](block:Sel) picks the attitude set-point and the thrust, [Mix](block:Mix) picks the torque (rate controller or contact controller); the integrators of the controllers that are not in charge are held at zero.

Back to [the overview](page:overview).

@@ flight | overview | The free-flight controller
# The free-flight controller

The same PX4-style cascade as the quadcopter example (X5.7), re-tuned for the hexarotor and the 250 Hz firmware (`design/design.py` derives every gain and prints the loop margins):

| loop | block | design |
| --- | --- | --- |
| position (P) | [Pos](block:Pos) | $K_p = 1$ 1/s, speed limit 2 m/s |
| velocity (PI) | [Pos](block:Pos) | $K_v = 3$ 1/s, $K_i = 1.2$ 1/s$^2$, thrust vector $F = m(a + g e_z)$, tilt limit 25 degrees |
| attitude (P) | [Att](block:Att) | quaternion error, $K = 5$ 1/s |
| rate (PID) | [Rate](block:Rate) | $K_p = (J + 0.02) \cdot 26$ rad/s: crossover 38 rad/s, phase margin 61 degrees |
| allocation | [Mix](block:Mix) | pseudo-inverse of the $4\times 6$ allocation matrix; attitude has priority over thrust when a rotor saturates |
| rotor speed | [Esc1](block:Esc1) | PI + motor-model feed-forward at 250 Hz: crossover 72 rad/s, phase margin 57 degrees |

**Gravity compensation and the CoM correction.** The thrust feedforward is $m_{nom}(a_{cmd} + g)$ with the total mass (2.5 kg assumed, 2.48 kg true). The arm and the end-effector hang ahead of the centre of mass and tip the nose down with the static torque $-g\,(m_{arm} L_m/2 + m_{ee}(L_m + 0.03)) = @TAUFF@$ N m about $y_b$; the rate controller adds this constant after its limits (`tau_ff`), as the paper does with a tuned constant. The integrators have nothing static to carry, so the hover is clean (height within 1 cm of the set-point). The paper has no integral action in altitude; this model keeps the velocity integrator, which removes the small steady-state height error.

**Sensors.** [Imu](block:Imu) (gyro and accelerometer with bias, noise and Butterworth low-passes) and [Gps](block:Gps) (a 2 cm, 5 cm/s position and velocity fix) read the true state; [Nav](block:Nav) is a fixed-gain observer that observes the tilt through the velocity innovation, so it works with the strong, unmodelled arm reaction in contact: the accelerometer measures *all* non-gravitational forces.

Back to [the overview](page:overview).

@@ contact | overview | The contact controller
# The contact controller

In contact the end-effector is held on the wall by the normal force and the friction of its three wheels, and the arm is attached to it by the spherical rubber joint. The origin of $\Sigma_e$ therefore does not move, and the multirotor with its arm is **one rigid body pinned at the joint $E$**. Its three degrees of freedom are its attitude, which is why the state of the contact controller is just the angular state

$$X = [\varphi,\ \dot\varphi,\ \theta,\ \dot\theta,\ \psi,\ \dot\psi]^\top, \qquad U = [\tau_x,\ F,\ \tau_z,\ \tau_y]^\top .$$

## Constrained dynamics

Let $M = m_b + m_{arm} = @MC@$ kg be the mass carried by the thrust (the end-effector hangs on the wall), $c$ the centre of mass of the multirotor with its arm, $I_c$ the inertia about $c$, $e$ the vector from $c$ to $E$ in body axes and $u = (\cos\mu, 0, \sin\mu)$ the arm direction. Newton's law gives $M\ddot c = R F e_z - M g e_z + F_E$ with the unknown joint reaction $F_E$, and the constraint $E = c + R e = \text{const}$ gives $\ddot c = -R(\dot\omega \times e + \omega \times(\omega \times e))$. Eliminating $F_E$ (the quasi-static reaction wrench is never needed) leaves the Euler equation **about the joint**:

$$I_E \dot\omega = \tau - L_m\, u \times (F e_z) - \omega \times I_c \omega - M\, e \times (\omega \times (\omega \times e)) + M g\, e \times (R^\top e_z), \qquad I_E = I_c + M\left(\lvert e\rvert^2 I - e e^\top\right).$$

The thrust acts at the multirotor's own centre of mass, a distance $L_m$ from $E$ along $u$; $\tau$ are the rotor torques. With the Euler-angle kinematics $\omega = A(\varphi,\theta)\,[\dot\varphi, \dot\theta, \dot\psi]^\top$ this is $\dot X = f(X, U; \mu)$ (`ContactModel` in `design/design.py`; at $\theta_{sp} = 20$ degrees $e = (@E_X@, 0, @E_Z@)$ m and $\mathrm{diag}\,I_E = (@IE@)$ kg m$^2$).

## Equilibrium

For a pitch set-point $\theta_{sp}$ the servo holds the arm at $\mu_c = \theta_{sp}$, which makes the arm **level in the world**. Then the wall reaction is horizontal and

$$\varphi = \psi = 0,\quad \theta = \theta_{sp},\quad \dot X = 0,\qquad F_{eq} = \frac{m g}{\cos\theta_{sp}},\qquad F_N = m g \tan\theta_{sp},\qquad \tau_{y,eq} = -m_{arm}\, g\, \frac{L_m}{2},$$

with all other torques zero. The pitch torque only compensates the moment of the tube's weight about the multirotor (the constant of the free-flight controller, for the tube alone, because the end-effector's weight is carried by the wall). The model checks this numerically: it finds $\tau_{y,eq}$ from the Euler equation and compares it with the closed form.

## Linearisation and LQR

Linearising $\dot X = f(X,U;\mu_c)$ about the equilibrium gives $\dot X = A(\theta_{sp})(X - X_{eq}) + B(\theta_{sp})(U - U_{eq})$. At $\theta_{sp} = 20$ degrees (rows $\varphi, \dot\varphi, \theta, \dot\theta, \psi, \dot\psi$; columns $\tau_x, F, \tau_z, \tau_y$)

$$A = @A20@, \qquad B = @B20@ .$$

The plane of symmetry $x_b z_b$ makes the linearisation fall apart exactly: pitch $(\theta, \dot\theta)$ is driven by the thrust variation and the pitch torque only, roll and yaw $(\varphi, \psi)$ are coupled with each other and driven by the roll and yaw torques only. `design.py` asserts the cross terms vanish ($<10^{-6}$) and solves the two continuous Riccati equations separately, so the structure of the gain is exact, not rounded:

$$U = -K(\theta_{sp})\,(X - X_{sp}) + U_{eq}, \qquad X_{sp} = [0, 0, \theta_{sp}, 0, \psi_{sp}, 0]^\top .$$

The weights ($Q = \mathrm{diag}(40, 2, 100, 3, 40, 3)$, $R$ from 1.5 N m, 1.2 N, 0.3 N m and 1 N m as the input size that costs one unit) put the closed loops at 2 to 4 rad/s: well below the 38 rad/s rate loops and the 60 Hz gyro filter. At 20 degrees

$$K = @K20@, \qquad K(27^\circ) = @K27@$$

(rows $\tau_x, F, \tau_z, \tau_y$; columns $\varphi, \dot\varphi, \theta, \dot\theta, \psi, \dot\psi$). **Structure, as in the paper:** the roll and yaw torques use only the columns of $\varphi, \dot\varphi, \psi, \dot\psi$; the thrust and the pitch torque use only $\theta, \dot\theta$; everything else is exactly zero ([Con/kzero](signal:Con/kzero) is the sum of the twelve forbidden entries and stays 0 during the whole run).

@GAINS@

## Gain scheduling and stability

$K$ is computed on a grid $\theta_{sp} = 10, 15, \ldots, 45$ degrees and stored as the table of [Con](block:Con); the block interpolates linearly with hat functions, so the gain follows the reference as it ramps ([Con/K[1]](signal:Con/K[1]) is $K_{\tau_x \varphi}$ along the run). The spectral abscissa of $A - BK$ over the grid lies between @SA_MIN@ and @SA_MAX@ 1/s ([Con/sa](signal:Con/sa)); the open-loop poles are the undamped pendulum modes $\pm 1.5$ to $2.2$ i rad/s and four zeros (roll and yaw are neutral).

@POLES@

## Implementation

[Con](block:Con) (250 Hz) converts the navigation filter's quaternion and the bias-corrected gyro to the Euler angles and rates, forms $X - X_{sp}$ ([Con/Xe[3]](signal:Con/Xe[3]) is the pitch error), interpolates $K$ and outputs the thrust and the three torques, which go straight to the mixer: no attitude or rate loop is in the way. There is no integral action; the model mismatch (the end-effector's weight, the arm's inertia, the sensor lag) leaves a pitch error below 1 degree, as in the paper.

Back to [the overview](page:overview).

@@ manipulator | overview | The manipulator and the end-effector
# The manipulator and the end-effector

**Servo.** [ServoCtl](block:ServoCtl) is a PD law with a smooth torque limit, $\tau = \tau_{max}\tanh\big((K_p(q_{sp} - q) - K_d\dot q)/\tau_{max}\big)$ with $q_{sp} = -\mu_{sp}$, bandwidth 40 rad/s, 8.4 N m stall torque. It acts through a `Revolute3D` joint whose five held directions are compliant; the reaction acts on the multirotor.

**Rubber shock mount.** [RubK](block:RubK) turns the unit quaternion of the spherical joint into the exact conservative restoring torque $-2 k w v$ ($U = 2k\sin^2(\vartheta/2)$) plus a damper; the three torque components act on the end-effector through the joint's rotation ports. The end-effector's orientation is thereby decoupled from the arm's: it sags 2.5 degrees under its own weight in free flight and lines up with the wall when the three wheels touch it.

**Omni-wheel contact.** The standard `ContactPoint` has two fixed isotropic friction tangents; a wheel does not, so [Wheel1](block:Wheel1) is the example-local `OmniContact`. The normal force is the same smooth Hunt-Crossley law ($k = 4000$ N/m with the 3/2 power, $c = 4$ s/m, no pull), and the traction is anisotropic. With $e$ the wheel's drive direction (its body direction $(0, -\sin\alpha, \cos\alpha)$ rotated to the world and projected on the wall) and $r = n \times e$ the free roller direction, $u$ the commanded wheel surface speed and $v$ the velocity of the contact point:

$$s_d = e\cdot v + u,\quad s_r = r\cdot v,\qquad F_d = \mu_d f_n \tanh\frac{s_d}{v_s},\quad F_r = \mu_r f_n \tanh\frac{s_r}{v_r},\qquad F = f_n n - F_d\, e - F_r\, r$$

with $\mu_d = 0.7$, $\mu_r = 0.04$. A wheel resists slip along its driven direction (rolling without slip: $s_d = 0$) and is almost free along its rollers. The three wheels at 120 degrees therefore hold the end-effector in the plane when their commands are zero and move it with the velocity $v$ when $u_k = -v_{max}\,d_k\cdot v_{cmd}$ ([Omni](block:Omni): $v_{max} = 0.4$ m/s, the "velocity scale" of the command in $[-1, 1]$). The anisotropic traction is energy-consistent: both forces act against their slip.

Back to [the overview](page:overview).

@@ results | overview | Results and checks
# Results and checks

Every number is measured on the real worker (reltol 1e-4); `expected.json` holds the checks.

@FORCE@

**Normal force against the prediction.** The wall force follows $m g \tan\theta_{sp}$ of the paper while $\theta_{sp}$ ramps and the end-effector climbs:

| $\theta_{sp}$ | measured $N$ | $m g \tan\theta_{sp}$ |
| --- | --- | --- |
| 17 deg (t = 7 s) | 6.74 N | 6.99 N |
| 20 deg (t = 8.5 s) | 8.29 N | 8.32 N |
| 23.5 deg (t = 10 s) | 9.53 N | 9.94 N |
| 27 deg (t = 12 to 28 s) | 11.4 to 11.6 N | 11.65 N |

The two differ by at most 0.68 N (6 %) between 8.5 and 28.4 s. The formula ignores the 0.38 kg of arm and end-effector and the geometry of the wheels, as the paper notes; the wheels share the force unevenly (2.2 to 5.5 N each) because the end-effector is tilted a little by the rubber mount. The normal force of every wheel stays positive through the contact phase (minimum 1.55 N).

**The impact.** The engage reference 12 degrees accelerates the multirotor over the last 20 cm: it meets the wall at 0.85 m/s at $t = 5.08$ s. The wheel contact is stiff (the brush spring of the real end-effector is not modelled), so the first impact peaks at 180 N for a few milliseconds and the multirotor bounces three times (the peaks of 75 N, 40 N and 25 N in the plot, the axis is clipped at 20 N); the damping of the contact ($c = 4$ s/m) and the angular engage controller let the bouncing die out within 1 s, and the contact phase starts at 6.12 s once the multirotor has been at rest at the wall for 0.3 s.

@ANGLES@

**Roll and yaw** stay below 0.9 degrees in contact (the paper reports below 7.5 degrees).

@LOCO@

**Locomotion.** At the command 0.125 the end-effector climbs 0.294 m in 6 s (the ideal is $0.125 \cdot 0.4 \cdot 6 = 0.30$ m) and returns 0.305 m after the 2 s pause; the multirotor follows within 0.7 cm with no change of any set-point: [TruthE/z](signal:TruthE/z) and [Truth/z](signal:Truth/z) are on top of each other. The driven slip of the wheels stays near 1 mm/s.

**Disengage.** The multirotor backs off to $x_b(t_d) - C$: 0.1872 m against the latched 0.1943 m (7 mm), the wheel plane is 0.7497 m from the wall, and the hover is quiet.

**Cost.** Compile 1 to 3 s, solve about 20 s for 34 s (300 000 solver steps) on the development machine; 17 001 rows $\times$ 2 566 signals, a 349 MB `columns.f64`.

Back to [the overview](page:overview).
