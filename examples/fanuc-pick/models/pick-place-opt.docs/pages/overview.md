# The highest pick rate, the 1.5 kg carton with a centred CoM

The best motion of `design/optimize_free.py` (stage A4: free timing, tilt, yaw window and gripper timing): T_cyc 1.394 s plus the 0.447 s return, **32.6 picks/min** against 28.3 for the best fixed family (`pick-place-best`), at a margin of 0.50 (required 0.5), a peak tool tilt of 0.0° and 94 % of the robot limits. The transfer takes 1.006 s with 54 % of it accelerating and 50 % decelerating; the lift (0.344 s) and the lower (0.460 s) overlap it. The vacuum opens 166 ms before the contact, the vent takes 10 ms, and the approach and depart take 0.193 and 0.179 s. The angle between the tool axis and $\mathbf f$ only means something while the carton is carried: after the release the empty gripper may brake its depart harder than g, and the angle then jumps to 180°.

![The free optimum at mid transfer|700](assets/f3d853bed309.png)

![Tilt, cup utilisation, margin and robot limits|900](assets/bf0b1c859b73.png)
