# Standing T8X

The eight-legged plant at rest: a 6-DOF floating body, eight three-joint legs and a
smooth foot contact, with the alternating gait held still. The model starts in its static
equilibrium (`design.py` solves it without running the model), so the plots are flat: the
analysis checks the static load, the body height, the servo torques of all 24 joints and
the analytic leg IK.

![The model canvas|900](assets/2a03ef4d6670.png)

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

![Height, load and the servo torques of one leg|900](assets/fe5e8d91aa91.png)

## 3D view

The body mesh carries the cephalothorax, the abdomen, the eight eyes, the fangs and the
hip bosses. Each leg is three links on its three joint axes; the scene binds every joint
to the model's joint angle. The tiled floor is the contact plane.

![The standing spider|600](assets/365ba7aed652.png)
