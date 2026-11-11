# Electric parallel gripper: grip-force sizing

An electric parallel-jaw gripper on a pick-and-place carriage picks a **50 mm steel ball** (0.514 kg), lifts it, moves it 0.4 m sideways with a fast jerk-limited transfer (20 m/s²), sets it down and lets go. The question is the one every gripper selection starts with: **what grip force does the part need, and does the gripper deliver it?**

The ball is a free 3D rigid body ([Ball](block:Ball), [BallPose](block:BallPose)) held only by compliant contacts with regularised Coulomb friction ([JawA](block:JawA), [JawB](block:JawB), [Table](block:Table)), so holding, creeping, slipping and dropping all come out of the contact physics. The drive train is a bond graph from the motor current to the jaw node; the monitor [Grip](block:Grip) compares what the ball needs with what the jaws deliver.

![The model|900](assets/cb96e1ef8e9e.png)

![The 3D view in the transfer (1.1 s): pads coloured by the friction utilisation|600](assets/9e6f0af9fbd6.png)

## What to try

- Run it and open the **3D View**: the pads turn from blue towards red while the transfer loads the friction ([JawA/util](signal:JawA/util)), the status light on the housing stays blue ([Grip/holds](signal:Grip/holds)); it turns red when the ball slips.
- **Dashboard**: lower the grip setting to 12 N and the ball slips in the transfer (at 8 N it falls out of the jaws); raise the transfer acceleration and the requirement grows with it (the sized setting still holds at the 40 m/s² slider end: the 56.8 N locked in by the closing carry up to about 54 m/s²). Raise the closing speed at the part to see the impact lock in a larger force.
- The second model, `block-gripper`, holds a block above its centre of mass: the transfer acceleration also tilts it.

Continue with [the mechanism](page:mechanism), [the contact model](page:contact), [the sizing](page:sizing) and [the validation](page:validation).
