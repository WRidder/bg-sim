# Gripper, cups and motion

## Mechanics (spatial multibond)

The gripper is a prescribed motion. [Path](block:Path) turns the profiles into the gripper pose and twist: x along the path, z for lift and lower, and the tilt about the transverse axis. [Grip](block:Grip), an `SfSpatial` on the 1-junction `GJ`, imposes that twist. The carton is a [RigidBody3D](block:Parcel) of 10 kg with the box inertia. [Pose](block:Pose) integrates its pose.

Each cup sits between two `FixedTransform3DNeutral` mounts:

- [GMount1](block:GMount1) carries the cup frame on the gripper.
- [PMount1](block:PMount1) carries the attach point on the carton top.

The cups form a 2 x 3 pattern, 0.36 m along the carton and 0.16 m across. Cups 1/2 trail, 3/4 sit in the middle and 5/6 lead, for a move in +x at yaw 0.

Four [ContactPoint](block:Floor1) corners carry the carton on the conveyor and on the place table until the lift and after the release.

## The suction cup

`stdlib:contact/SuctionCup` (new) is a two-port spatial element with a pneumatic port `vac`. The relative pose of the attach point in the cup frame is a state. Its loads are:

| part | law |
| --- | --- |
| bellows axial | $F_s = k_{ax}(s - L_0) + d_{ax}\dot s$ (pull > 0) |
| holding capacity | $F_{cap} = A_{eff}\,\Delta p$ |
| transmitted pull | $T = \mathrm{smin}(F_s, F_{cap})$, with lip contact $N = F_{cap} - T$ |
| bending, torsion | $M = 2 q_w (k_{tilt} q_x, k_{tilt} q_y, k_{tor} q_z) + d_{rot}\,\omega$ |
| peeling | lip gap $h = \mathrm{pos}((F_s + 4\lvert M_{xy}\rvert/D_{lip} - F_{cap})/k_{ax})$ |
| shear | bellows deflection $e$ plus a Dahl slip law: elastic below $\mu N$, sliding at it |

The utilisation index combines pull-off, peel and slip in one number:

$$U = \frac{T + 4\lvert M_{xy}\rvert / D_{lip} + \lvert F_{lat}\rvert/\mu}{F_{cap}}$$

U = 1 is the edge of loss. A safety factor S means U ≤ 1/S, so S = 2 means U ≤ 0.5. The cup sets its `lost` latch when the lip gap exceeds 2 mm. [Monitor](block:Monitor) counts lost cups in [Monitor/n_lost](signal:Monitor/n_lost). It clears [Monitor/held](signal:Monitor/held) when the carton has dropped 5 cm away from the gripper before the release.

The cup parameters are those of a 50 mm two-fold bellows cup:

- effective area 14 cm², so 58 kPa holds 81 N;
- axial stiffness 5 kN/m, lateral 2.5 kN/m, tilt 3 N·m/rad;
- μ = 0.5 on cardboard;
- chamber volume 20 cm³.

## Motion

Lift and lower are S-curves of 0.15 m (2.5 m/s², 40 m/s³). The vacuum valve opens at t = 0, the lift starts at 0.35 s, and the transfer starts at 0.956 s. The transfer profile is chosen by the global `kind`:

| kind | profile | peak acceleration for L in T |
| --- | --- | --- |
| 1 | trapezoid (1/3 acceleration, 1/3 cruise, 1/3 deceleration) | $4.5\,L/T^2$ |
| 2 | S-curve, jerk phases λ = 0.3 of each ramp | $4.5\,L/T^2/(1-\lambda)$ |
| 3 | polynomial 3-4-5 | $5.77\,L/T^2$ |
| 4 | cycloidal | $2\pi\,L/T^2$ |

[Profile](block:Profile) selects the transfer profile. A second set of the same profiles, [Preview](block:Preview), runs $2/\omega_{tilt}$ earlier and feeds the tilt servo. With `k_tilt` > 0 the gripper tilts towards $\theta_c = \theta_{max}\tanh(k\,\mathrm{atan}(a/(g + a_z))/\theta_{max})$, following a critically damped second-order servo at 15 rad/s. The pivot is the carton centre of mass, so the tilt adds no translation. The preview cancels the servo lag, so the tilt arrives together with the acceleration.

`psi` (yaw) turns the cup pattern relative to the path.
