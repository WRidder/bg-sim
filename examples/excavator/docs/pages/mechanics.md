# Mechanics

The three links are `RigidBody2D` bodies on `Revolute2DLimit` joints (planar multibond bond graph, as in
robot-arm-2d). The joint angles are relative: q1 the boom against the horizontal, q2 the arm against the boom
line, q3 the bucket against the arm line. The joint limits are the **cylinder end stops**: the angles at which
each cylinder is fully retracted or extended (boom −40° to 62°, arm −158° to −52°, bucket −125° to 45°).

![The linkage and the pins|860](assets/91f001b3332f.svg)

**Masses.** The total of boom, arm and bucket, **3606 kg**, is the front mass of the 20-t excavator in Jin et al.
(2024). The split (boom 1650 kg, arm 1000 kg, bucket 956 kg with its linkage), the centres of mass and the
inertias (slender links) are ours. The lift model adds a 1.5 t payload to the bucket (0.93 m³ of loose soil).

**Cylinder linkage.** Each cylinder is a `HydraulicCylinder` (chambers with compressibility, `beta` = 1.2 GPa
for oil with hoses) whose rod drives a translational 1-junction with a `Friction` element (Coulomb plus viscous)
to the barrel. A `RackAndPinion` with radius 1 turns the rod motion into a rotation, and a modulated transformer
(`MTF`) with the moment arm r = dL/dq of the custom block `CylinderMount2D` couples it to the joint. So the
cylinder force does exactly the virtual work of the real linkage, and the cylinder length is a **kinematic
result** of the pin positions, not a state of its own. For the bucket, the arm-side `BucketLinkage2D` block solves
the rocker / H-link four-bar (circle intersection) and gives the ratio k = dφ/dq3 between the rocker angle and the
bucket angle: the bucket cylinder works on the rocker through r, and the rocker on the bucket through k.

| cylinder | bore / rod [mm] | count | stroke [m] | source |
| --- | --- | --- | --- | --- |
| boom | 120 / 85 | 2 | 1.30 | Jin et al. (2024): 11310 / 5635 mm² per cylinder |
| arm | 140 / 100 | 1 | 1.31 | typical 20-t size (assumed) |
| bucket | 120 / 85 | 1 | 1.09 | typical 20-t size (assumed) |

The strokes and the closed lengths follow from the pin layout and the joint ranges (`design.py`). The end stops
of the joints (stiffness 2·10⁷ N·m/rad) act as the cylinder end stops.
