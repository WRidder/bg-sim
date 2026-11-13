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
