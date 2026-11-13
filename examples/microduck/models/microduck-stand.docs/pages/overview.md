# The microduck holding HOME

The robot is released 0.1 mm above the floor in the STAND pose, on a free joint ([Free](block:Free)). Each sole has four contact points with friction 1.0, each an instance of the library subsystem `GroundContact` (such as [FootL1](block:FootL1)). The 14 servos hold the HOME goals at kp 200, and **no policy runs**.

The robot first settles into its gear play and its P stiffness: the knees bend, and the weight moves from the heels to the toes. Then it tips forward. HOME at walking gain is balanced only by a policy that keeps balancing it. The microduck design notes report the same from their own simulation: "a robot holding it on the floor tips past 40° within a second or two". Here the trunk passes 40° at 1.14 s.

Only the soles touch the ground, so the run ends at 1.3 s, before the head would hit the floor. Open the 3D view to watch the robot tip forward.

Try a higher `kp_fw` and see how long the robot stays up. A run takes a few minutes.
