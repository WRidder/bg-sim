# Too aggressive: the robot can, the gripper cannot

Joint blended motion (family 4) at 80 % of every joint rate, acceleration and jerk limit. The robot stays inside its limits (83 %, the wrist moment), and the cycle would take 1.36 s. But the gripper reaches 20 m/s² while it carries the carton (the optimum of the same family: 8.3 m/s²). The cups peel one after the other, each zone loses its vacuum, and the carton drops 0.2 s after the lift ([Monitor/held_ok](signal:Monitor/held_ok) falls to 0).

The optimum of the same family holds with a margin of 0.5 and takes 1.61 s (`pick-place-best`).

![Cup utilisation, vacuum per zone, drop detection and robot limits|900](assets/3102530b73c8.png)
