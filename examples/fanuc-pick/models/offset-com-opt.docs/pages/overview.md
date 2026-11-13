# The highest pick rate, the offset-CoM carton gripped over its CoM

The best motion of `design/optimize_free.py` (stage A4: free timing, tilt, yaw window and gripper timing): T_cyc 1.400 s plus the 0.451 s return, **32.4 picks/min** against 28.7 for the best fixed family (`offset-com-best`), at a margin of 0.50 (required 0.5), a peak tool tilt of 1.1° and 94 % of the robot limits. The transfer takes 0.973 s with 47 % of it accelerating and 70 % decelerating; the lift (0.271 s) and the lower (0.361 s) overlap it. The vacuum opens 41 ms before the contact, the vent takes 61 ms, and the approach and depart take 0.178 and 0.177 s. The angle between the tool axis and $\mathbf f$ only means something while the carton is carried: after the release the empty gripper may brake its depart harder than g, and the angle then jumps to 180°.

![Tilt, cup utilisation, margin and robot limits|900](assets/ccf543cf1ff0.png)
