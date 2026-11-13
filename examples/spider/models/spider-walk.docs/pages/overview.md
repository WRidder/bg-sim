# Walking T8X

The same plant under the gait: an alternating tetrapod with a constant-velocity stance, an
analytic IK for every foot target and a position servo with the torque-speed line of a
hobby servo. The command profile marches in place, walks forward, turns left and then
crabs left, so the body traces a curve.

![The model canvas|900](assets/65fc507b8531.png)

| block | role |
| --- | --- |
| [Gait](block:Gait) | the alternating tetrapod, the load hand-over and the attitude correction |
| [Leg1](block:Leg1) .. [Leg8](block:Leg8) | instances of the library subsystem `SpiderLegUnit`: leg IK, three-joint leg with servo, link gravity, contact and the body wrench |
| [Body](block:Body) | the 6-DOF body bond graph |

The legs L1, L3, R2, R4 and L2, L4, R1, R3 form the two groups, half a cycle apart, with
the cycle `T = 0.8 s`. Each foot command is

* **stance** for 70 % of the cycle: the foot moves from `+A` to `-A` at the constant
  speed `-v` relative to the body, so a foot that does not slip carries the body at exactly
  `v`. The stride is `A = v duty T / 2` with `duty = 0.7`, and `v` includes the yaw term
  `omega x r`, so the same gait turns and crabs;
* **swing** for 30 % (0.24 s): a cubic Hermite return whose end slopes match the stance,
  and the lift `16 u² (1-u)²` times `gait_lift` = 35 mm;
* **load hand-over**: in the two double-support phases at either end of the stance the
  foot command rises to 3.2 mm, the height at which the foot just touches the floor while
  the other group carries the body. The foot lands and leaves at zero load and the load
  moves over gradually. The commanded apex is 43.6 mm; the foot reaches 40.2 mm.

The phases come from `atan2` of the clock instead of `mod` or `floor`, and the stance/swing
switch is a 0.2 ms wide `tanh` blend between two branches that already agree in position
and velocity, so the gait creates no simulation events.

The servo is a Hitec **HS-82MG** class servo (0.333 N m stall, 0.10 s/60°): the T8X servos
have no published rating, and the HS-35HD of the original T8 (0.078 N m) cannot hold this
1.02 kg model, whose femur needs 0.25 N m on four feet.

## What to try

1. Press **Run**: the body marches in place for 2 s, walks forward, turns left and crabs
   left. Over the last two cycles the forward speed is 0.100 m/s, the command, with a
   0.015 m/s ripple at the group hand-over; the load swings between 7.4 and 12.3 N around
   the 10.0 N weight.
2. Change `vx_cmd` to 0.18: the stride grows and the speed follows, 0.181 m/s at the end;
   the peak servo torque rises from 0.255 to 0.269 N m.
3. Set `gait_lift` to 0: the swing keeps only the 5.7 mm hand-over lift. On the flat floor
   the robot walks the same path; the lift is for stepping over things.
4. Set `mu_foot` to 0.1: the stance feet creep three times faster, but the
   constant-velocity stance needs little traction, so the path moves by less than 1 cm.

![Path, yaw, speed and ground load|900](assets/decc97a375e2.png)

The checks hold the end position and yaw against the integrated command, the forward speed
and its ripple, the number of loaded feet, the swing apex, the mean load and height, the
roll/pitch envelope, the leg workspace of all eight legs and the torque of all 24 servos.

## 3D view

The scene at t = 8 s: the body is turning left, the four swinging legs are in the air and
the four stance legs carry the body. Every leg joint is bound to its model angle, so the
3D pose is the simulated pose, not an animation.

![The spider walking and turning|600](assets/2d712ac5a986.png)
