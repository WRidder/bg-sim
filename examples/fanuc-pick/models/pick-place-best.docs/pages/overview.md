# Optimum for the solid carton (family 4, joint blended)

The fastest trajectory `design/optimize.py` found for the 1.5 kg carton with a centred CoM: joint blended motion at 35 % of the joint rate limits and 24 % of the acceleration limits, jerk share 0.9, lift 70 mm and a 80 mm blend. The cycle takes 1.612 s, 3 % faster than the default trajectory, and the holding margin stays at 0.50 (the default trajectory goes to −0.05). The robot uses 57 % of its limits. The cups, not the robot, set the speed: the peak gripper acceleration while carried is 8.3 m/s². The free optimisation goes further: see `pick-place-tilt-best` and `pick-place-opt`.

![The optimum at mid transfer|700](assets/4b9557217647.png)

![Cup utilisation, holding margin and robot limits|900](assets/4834d66ec106.png)
