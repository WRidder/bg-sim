# Aggressive trapezoid: the parcel is lost

This model is the `transfer` plant with `kind` = 1 (trapezoid) and `T_move` = 0.7 s, which gives a peak acceleration of 9.18 m/s² with infinite jerk.

![Utilisation, lost cups and vacuum|900](assets/87bc044d7449.png)

The carton survives the acceleration (U briefly reaches 1.15) and the cruise. The deceleration step at t ≈ 1.42 s sets the bellows ringing, and within 80 ms the U of the trailing cups 1/2 goes past 1: braking reverses the tipping moment, so they now take the extra pull. A lifted lip leaks, the vacuum in that cup drops, and the capacity falls with it. The first cups lose their seal at 1.50 s, the load moves to the others, and [Monitor/n_lost](signal:Monitor/n_lost) reaches 6 at 1.54 s. The carton falls short of the place position.

Compare with `aggressive-scurve`: the same 0.7 s as an S-curve holds.
