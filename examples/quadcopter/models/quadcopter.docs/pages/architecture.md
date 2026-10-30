# Architecture

```
Mission (Waypoints, 50 Hz) --p_sp,v_sp,a_sp,psi--> Pos (PositionCtrl, 50 Hz) --qd,F--> Att (AttitudeCtrl, 250 Hz)
                                                      ^  ^                                | w_sp
Nav (NavFilter, 500 Hz) --p,v,q----------------------+  +--- q --- Att                     v
  ^   ^                                           --- w ---------------------------> Rate (RateCtrl, 500 Hz)
  |   +-- Gps (GpsSensor, 50 Hz): p, v, heading                                            | tau
  +------ Imu (ImuSensor, 500 Hz): gyro, accel + low-pass                   Mix (QuadMixer, 500 Hz) <-- F
                                                                                           | w_cmd[4]
Esc1..4 (Esc, 500 Hz: speed PI + motor-model feed-forward, voltage and current limits) <---+
  | u                                                                   Bat (Battery) --V--> Esc
  v
Drv1..4 (stdlib ElectricDrive) --shaft--> Prop1..4 (Propeller: T = kT w|w|, Q = kQ w|w|)
  | i, w, P_el                                            | T
  +------------> RW (RotorWrench) <-- body twist, pose, wind, leg forces
                   | tx ty tz fx fy fz
World (GroundSpatial) -- Free (Free3D) -- Body (RigidBody3D) -- Wrench (ExternalWrenchSpatial)
                                             '-- Mount_k -- Leg_k (ContactPoint) ... Ground (ContactSurface)
```

- **Airframe.** [World](block:World) (`GroundSpatial`) to [Free](block:Free) (`Free3D`) to [Body](block:Body) (`RigidBody3D`): 13 states (quaternion, position and the 6 momenta), gravity inside the body, six zero-effort `Se` sources ([FreeSe1](block:FreeSe1) to `FreeSe6`) on the unused drive ports of the free joint. Body frame: $x$ forward, $y$ left, $z$ up, origin at the centre of mass.
- **Landing gear.** Four `ContactPoint` legs ([Leg1](block:Leg1) to `Leg4`; Hertz contact against one [Ground](block:Ground) `ContactSurface` plane, $k = 2\cdot10^4$ N/m, $\mu = 0.6$) at $(\pm0.11, \pm0.11, -0.085)$ m; they carry $m g = 13.24$ N on the ground and let take-off and landing happen in the same model. The accelerometer feels their normal force.
- **Rotors** (x4). Each is [Esc1](block:Esc1) to [Drv1](block:Drv1) to [Prop1](block:Prop1). `ElectricDrive` is the stdlib bond graph motor: $R = 0.11\ \Omega$, $L = 40\ \mu$H, EM gyrator $k_t = 0.01038$ N·m/A (a 920 kV motor), rotor plus propeller inertia $J_m = 5\cdot10^{-5}$ kg·m². `Propeller` is a rotation one-port load with drag torque $Q = k_Q\,\omega\lvert\omega\rvert$ ($k_Q = 2.03\cdot10^{-7}$) and thrust $T = k_T\,\omega\lvert\omega\rvert$ ($k_T = 1.42\cdot10^{-5}$: 3.19 N at the hover speed of 482 rad/s, 8.5 N at 775 rad/s). Spin directions alternate along the diagonals.
- **Airframe wrench.** [RW](block:RW) (`RotorWrench`) assembles, in the body frame, the thrust force and its moments $r_k \times T_k e_z$, the **motor reaction torque** $-\mathrm{spin}_k\,(k_t i_k - b_m\omega_k)$ (the stator is the airframe, so the reaction of the rotor's inertia torque and of the propeller drag acts on it and the motor power balances), the gyroscopic term $-\Omega \times h$ of the rotors' spin momentum, linear air drag against $(v - R^T\,\mathrm{wind})$ and a small rotational damping; the six components drive one stdlib `ExternalWrenchSpatial` ([Wrench](block:Wrench)) on the body.
- **Battery.** [Bat](block:Bat): a 3S pack with open-circuit voltage linear in the state of charge and 20 mΩ series resistance; it delivers the electrical power of the four motors, so the terminal voltage sags with the load (11.4 V at the 62 A spin-up). The ESCs limit their output by this live voltage.
- **Wind.** [Wind](block:Wind) (a new Gaussian gust every 0.5 s, mean $(0.4, -0.2)$ m/s, $\sigma = 0.5$ m/s) through a 1 s [Gust](block:Gust) lag into the drag of `RotorWrench`.
- **Mission.** [Mission](block:Mission) (`Waypoints`, 50 Hz): sums of minimum-jerk moves with exact velocity, acceleration and yaw-rate feed-forward: climb 1 m at 1 s (3 s), +2 m in $x$ at 5 s, +2 m in $y$ with a +90 degree turn at 8 s, back to the origin with a -90 degree turn at 11 s, descend at 14 s; armed 0.5 s to 17.4 s.
