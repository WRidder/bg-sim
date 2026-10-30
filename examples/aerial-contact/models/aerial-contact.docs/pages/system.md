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
