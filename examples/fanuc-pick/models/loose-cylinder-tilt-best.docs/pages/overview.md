# The waiter tilt, the carton with the loose bottle

Stage A1 of `design/optimize_free.py`: the fixed families 3 and 4 of `optimize.py`, now with the tool tilted towards the specific force $\mathbf f = \mathbf g - \mathbf a$ of the carton, like a waiter carrying a tray. The planner turns the tool axis by `tilt_gain` times the angle of $\mathbf f$ (limited to `tilt_max_deg` through a smooth saturation, filtered with `T_tw` and faded in after the lift and out before the place over `T_tr`), so the carton is level at both contacts. The best is Cartesian blended (family 3) with a gain of 0.40, a largest tilt of 6.7° and a peak tilt of 6.5°: T_cyc 1.354 s, with the return 32.9 picks/min against 30.1 for the level optimum (`loose-cylinder-best`), at a margin of 0.30 and 80 % of the robot limits.

The optimum tilts much less than the specific force (the third trace is the angle between the tool axis and $\mathbf f$): the search found the best margin with a partial tilt. The dashboard has the tilt gain and the largest tilt as sliders.

![Tilt, cup utilisation, margin and robot limits|900](assets/ca8661d0b70f.png)
