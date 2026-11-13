# The highest pick rate, the carton with the loose bottle

The best motion of `design/optimize_free.py` (stage A4: free timing, tilt, yaw window and gripper timing): T_cyc 1.277 s plus the 0.441 s return, **34.9 picks/min** against 30.1 for the best fixed family (`loose-cylinder-best`), at a margin of 0.34 (required 0.3), a peak tool tilt of 0.6° and 100 % of the robot limits. The transfer takes 0.837 s with 50 % of it accelerating and 44 % decelerating; the lift (0.179 s) and the lower (0.378 s) overlap it. The vacuum opens 42 ms before the contact, the vent takes 55 ms, and the approach and depart take 0.177 and 0.181 s. The angle between the tool axis and $\mathbf f$ only means something while the carton is carried: after the release the empty gripper may brake its depart harder than g, and the angle then jumps to 180°.

![Tilt, cup utilisation, margin and robot limits|900](assets/d4867dd9e4d0.png)
