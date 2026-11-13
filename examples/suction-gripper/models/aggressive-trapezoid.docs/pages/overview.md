# Aggressive trapezoid: the parcel is lost

This model is the `transfer` plant with `kind` = 1 (trapezoid) and `T_move` = 0.74 s, which gives a peak acceleration of 8.2 m/s² with infinite jerk.

![Utilisation, lost cups and vacuum|900](assets/8685e4c8ebf3.png)

The carton survives the acceleration (U briefly goes past 1) and the cruise. The deceleration step at t ≈ 1.45 s sets the bellows ringing, and within 70 ms the U of the trailing cups 1/2 goes past 1: braking reverses the tipping moment, so they now take the extra pull. A lifted lip leaks, the vacuum in that cup drops, and the capacity falls with it. The first cups lose their seal at 1.51 s, the load moves to the others, and [Monitor/n_lost](signal:Monitor/n_lost) reaches 6 at 1.55 s. The carton leaves the gripper still moving forward and is not placed.

Compare with `aggressive-scurve`: the same 0.74 s as an S-curve holds. (With the linear bellows of the first version the trapezoid was already lost at 0.7 s and the S-curve still held there; the nonlinear bellows shift both limits, so the pair now runs at 0.74 s.)
