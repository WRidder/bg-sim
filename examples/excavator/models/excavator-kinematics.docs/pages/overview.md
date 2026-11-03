# Kinematics: cylinder lengths in, bucket tip out

**Scenario.** The hydraulics are replaced by a stiff servo on each cylinder: a [BoomServo](block:BoomServo)
spring-damper pulls the rod towards a set length ([BoomSetL](block:BoomSetL), the integral of the rate table
[BoomRate](block:BoomRate)). The set lengths move from 1 to 4 s, hold until 7 s, move again from 7 to 10 s and
hold until 13 s. Gravity is off in this model (g0 = 0), so the servos only carry the inertia of the front and the
holds are exact.

![The model canvas|900](assets/27a482a3edcd.png)

**What it checks.** At the holds (6.5 s and 12.5 s) the bucket tip, the joint angles, the pin-to-pin lengths,
the moment arm of the bucket cylinder and the four-bar ratio [Linkage/k](signal:Linkage/k) are compared with
`design.py`, which finds the joint angle of each set length by root finding on the geometry of `exc_geom.py`
(scipy `brentq`, the bucket through the four-bar). The tip agrees to better than 4·10⁻⁷ m: (7.3834, 2.7797) m at
6.5 s and (2.9781, −1.8771) m at 12.5 s.

![Cylinder lengths and set lengths, joint angles, moment arms and four-bar ratio|900](assets/ae3c1d87d919.png)

![Bucket tip path|600](assets/7d9d673479f2.png)

**Blocks.** [BoomMount](block:BoomMount), [ArmMount](block:ArmMount) and [BucketMount](block:BucketMount)
(`CylinderMount2D`) compute each cylinder length L, the moment arm r = dL/dq and the rod extension from the pin
poses; [Linkage](block:Linkage) (`BucketLinkage2D`) solves the four-bar. The pose chain
(`JointPose2D` / `LocalPose2D` / `ComposePose2D`) gives the world poses of the pins and of the tip
([PoseTip](block:PoseTip)).

**Dashboard.** The tip path, the cylinder lengths, the four-bar ratio and its transmission angle
[Linkage/mu](signal:Linkage/mu). The slider sets the servo stiffness.

**Try:** lower the servo stiffness to 10⁷ N/m: the servos follow the set lengths more loosely, and at the 6.5 s hold the tip
is still about 12 mm from the FK reference (the check then fails).
