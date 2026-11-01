# The highest pick rate, the carton with the loose ball

The best motion of `design/optimize_free.py` (stage A4: free timing, tilt, yaw window and gripper timing): T_cyc 1.326 s plus the 0.445 s return, **33.9 picks/min** against 30.5 for the best fixed family (`loose-sphere-best`), at a margin of 0.30 (required 0.3), a peak tool tilt of 6.9° and 100 % of the robot limits. The transfer takes 0.836 s with 55 % of it accelerating and 40 % decelerating; the lift (0.455 s) and the lower (0.308 s) overlap it. The vacuum opens 22 ms before the contact, the vent takes 76 ms, and the approach and depart take 0.184 and 0.203 s. The angle between the tool axis and $\mathbf f$ only means something while the carton is carried: after the release the empty gripper may brake its depart harder than g, and the angle then jumps to 180°.

![The free optimum at mid transfer|700](assets/5f00fccc8793.png)

![Tilt, cup utilisation, margin and robot limits|900](assets/b58b5834dc19.png)
