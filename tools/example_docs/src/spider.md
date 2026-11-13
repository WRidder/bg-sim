@@ figures spider-stand
{
  "diagram": {"kind": "diagram", "model": "spider-stand"},
  "scene": {"kind": "scene", "model": "spider-stand", "t": 3.0, "zoom": 2},
  "run": {
    "kind": "plot", "model": "spider-stand", "xlim": [0, 4],
    "rows": [
      {"ylabel": "height [m]", "series": [{"signal": "Status/height"}]},
      {"ylabel": "load [N]", "series": [{"signal": "Status/load"}]},
      {"ylabel": "torque [N m]", "series": [{"signal": "Leg1/Joints/tau1", "label": "coxa"}, {"signal": "Leg1/Joints/tau2", "label": "femur"}, {"signal": "Leg1/Joints/tau3", "label": "tibia"}]}
    ]
  }
}
@@ page spider-stand overview - | Overview
# Standing T8X

The eight-legged plant at rest: a 6-DOF floating body, eight three-joint legs and a
smooth foot contact, with the alternating gait held still. The model starts in its static
equilibrium (`design.py` solves it without running the model), so the plots are flat: the
analysis checks the static load, the body height, the servo torques of all 24 joints and
the analytic leg IK.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Gait](block:Gait) | the outer layer of the controller: foot targets and the attitude correction, held at zero stride and zero lift here |
| [Leg1](block:Leg1) .. [Leg8](block:Leg8) | one leg each: instances of the library subsystem `SpiderLegUnit`, with the analytic leg IK (`IK`), the reduced leg (`Joints`: servo, link gravity, Jacobian and foot contact) and the wrench on the body (`Wrench`) |
| [Body](block:Body), [Free](block:Free) | the 6-DOF body on a bond graph, carrying the mass and inertia of the whole robot |

The nominal foot is 0.16 m from the hip, the commanded body height 0.110 m and the leg
`0.045 + 0.110 + 0.140` m of coxa, femur and tibia. The IK command is
`q = (0, 15.7, -102) deg`. The body stands 1.5 mm lower, at 0.1085 m: the feet sink
0.89 mm into the contact and the servos give 0.62 mm. The eight feet carry the weight of
the 1.02 kg robot, 10.0 N, and each femur servo holds 0.102 N m.

## What to try

1. Press **Run**: everything stays where it starts; the load is the weight and the femur
   torque the static 0.102 N m.
2. Set `roll0` to 1 (degrees) and run: the body starts rolled and is level again within
   0.5 s. The attitude correction in the gait doubles the roll stiffness of the stance.
3. Change `h_stand` to 0.09: the start pose is built for 0.110 m, so the command jumps at
   t = 0; the body drops 20 mm, the feet bounce off the floor once and land at four times
   the weight, and the body settles at 0.0885 m. A smooth start at another height needs a
   rebuild with `H_STAND` in `design/data.py`.

![Height, load and the servo torques of one leg|900](@fig:run)

## 3D view

The body mesh carries the cephalothorax, the abdomen, the eight eyes, the fangs and the
hip bosses. Each leg is three links on its three joint axes; the scene binds every joint
to the model's joint angle. The tiled floor is the contact plane.

![The standing spider|600](@fig:scene)
@@ figures spider-walk
{
  "diagram": {"kind": "diagram", "model": "spider-walk"},
  "scene": {"kind": "scene", "model": "spider-walk", "t": 8.0, "zoom": 2},
  "run": {
    "kind": "plot", "model": "spider-walk", "xlim": [0, 16],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Status/x", "label": "x"}, {"signal": "Status/y", "label": "y"}]},
      {"ylabel": "yaw [deg]", "series": [{"signal": "Status/yaw_deg"}]},
      {"ylabel": "speed [m/s]", "series": [{"signal": "Status/speed", "label": "speed"}, {"signal": "Status/v_fwd", "label": "forward"}]},
      {"ylabel": "load [N]", "series": [{"signal": "Status/load"}]}
    ]
  }
}
@@ page spider-walk overview - | Overview
# Walking T8X

The same plant under the gait: an alternating tetrapod with a constant-velocity stance, an
analytic IK for every foot target and a position servo with the torque-speed line of a
hobby servo. The command profile marches in place, walks forward, turns left and then
crabs left, so the body traces a curve.

![The model canvas|900](@fig:diagram)

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

![Path, yaw, speed and ground load|900](@fig:run)

The checks hold the end position and yaw against the integrated command, the forward speed
and its ripple, the number of loaded feet, the swing apex, the mean load and height, the
roll/pitch envelope, the leg workspace of all eight legs and the torque of all 24 servos.

## 3D view

The scene at t = 8 s: the body is turning left, the four swinging legs are in the air and
the four stance legs carry the body. Every leg joint is bound to its model angle, so the
3D pose is the simulated pose, not an animation.

![The spider walking and turning|600](@fig:scene)
@@ page @project models - | Models and data
# The T8X spider example

A T8X-class eight-legged robot: a 6-DOF body, eight three-joint legs, foot contact and an
alternating tetrapod with an analytic IK. The two models are the same plant at rest and
walking.

| model | what it shows |
| --- | --- |
| `spider-stand` | the static stance, the analytic leg IK, the eight foot loads, the servo torques, the body height and level |
| `spider-walk` | the gait, the servo/contact loop, a forward / turn / crab command profile |

## The robot

The published T8X has eight legs and 26 servos, three per leg and two in the abdomen,
driven by the Bigfoot inverse-kinematics and gait engine
([Robugtix](https://www.robugtix.com/t8x/), [store](https://store.robugtix.com/t8x/)).
The walk command is 0–200 mm/s with 100 as stop, and the turn command 0–200 deg/s
([tutorial #2](https://store.robugtix.com/t8x-programming-tutorial-2/)); the T8 weighs
2.2 lb ([Open Electronics](https://www.open-electronics.org/spiderbot-a-3d-printed-eight-legs-robot/))
and used Hitec HS-35HD servos on a 4.8 V pack
([New Atlas](https://newatlas.com/robugtix-t8-robot-tarantula/28168/)). The leg lengths,
link masses and body size here are engineering estimates from the photographs, tagged
`[est]` in `design/data.py`.

## The model

The body block carries the whole robot with the legs locked in the nominal stance:
1.020 kg and principal inertias 0.01017 / 0.01169 / 0.02016 kg m² (the body alone is
0.46 kg; `design.py` adds the 24 links). Each leg is a reduced, quasi-static three-joint
unit: its joint angles carry the servo torque, the gravity of the three links at their
centres and the foot contact force through the leg Jacobian, with the diagonal of the leg
mass matrix as joint inertias. The body receives the contact force at the true foot point
and the moment of the link weights. The reduction leaves out the inertial forces of a
swinging leg on the body (up to 0.83 N per leg), the servo reactions (0.04 N m per coxa)
and the body acceleration in the joint equations; it keeps the 24 servo coordinates, the
foot forces and the static load paths, so a 16 s walk runs in under half a minute. The eight
legs are instances of one library subsystem, `library/SpiderLegUnit.bgsub.json`; each
instance sets its hip position, hip yaw and foot friction.

The IK is the exact chain used by the 3D scene:

    q1 = atan2(y, x)
    q3 = -acos((d² - b² - c²) / (2 b c))
    q2 = atan2(z, x) - atan2(c sin q3, b + c cos q3)

A foot target outside the reachable annulus is projected onto it, and `reach` falls from 1
to 0 over the last 20 mm before the outer or the inner limit.

The contact is the law of the stdlib `ContactPoint`: a smooth Hunt-Crossley normal force
`F_n = k x sqrt(x/x_ref) (1 + c xdot)`, gated by the slope of the smooth penetration, plus
regularised Coulomb friction, on the plane `z = 0`. The servo is a 12 ms command filter, a
proportional loop that saturates at the stall torque 0.333 N m beyond one degree of error,
and the back-EMF damping that makes the no-load speed 10.5 rad/s (HS-82MG at 6 V). The
attitude correction moves the foot targets by `k_att (roll y - pitch x)` through a 0.1 s
filter; without the filter the 12 ms servo lag would make the 17 Hz roll mode unstable.

## Sources

* Robugtix, *T8X*, https://www.robugtix.com/t8x/ and https://store.robugtix.com/t8x/
  (eight legs, 26 servos, Bigfoot engine).
* Robugtix, *T8X Programming Tutorial #2*,
  https://store.robugtix.com/t8x-programming-tutorial-2/ (walk and turn commands).
* Open Electronics, *Spiderbot – a 3D-Printed, eight legs Robot*,
  https://www.open-electronics.org/spiderbot-a-3d-printed-eight-legs-robot/ (2.2 lb,
  26 servos: three per leg and two in the abdomen).
* New Atlas, *Robugtix T8 robot tarantula*, 2013,
  https://newatlas.com/robugtix-t8-robot-tarantula/28168/ (Hitec HS-35HD servos, 4.8 V).
* Hitec HS-35HD and HS-82MG ratings, as listed by ServoDatabase
  (https://servodatabase.com/servo/hitec/hs-35hd, https://servodatabase.com/servo/hitec/hs-82mg)
  and Horizon Hobby (HRC32082S).
* T. Ohnishi and T. Asakura, “Spider-Robot 8-Leg Cooperative Walking Velocity Control
  Strategy Based on Environmental Information”, *JSME International Journal Series C*
  47(4), 2004 (eight-leg cooperative gait).
* “Structure and Gait Design of an Eight-legged Bionic Robot”, IEEE, 2024 (D-H leg
  kinematics and straight / turn-in-place gaits).
