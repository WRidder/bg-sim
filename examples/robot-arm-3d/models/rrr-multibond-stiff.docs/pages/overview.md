# Stiff held directions ($k = 10^8$)

The `rrr-multibond` arm with all held directions ten times stiffer: $k_t = k_r = 10^8$, damping scaled with it (for example `bt` = 28000 for [J1](block:J1)) and the static deflection starts scaled by a tenth. Everything else is as in `rrr-multibond`. The maximum joint-angle difference to the `rrr-torque` arm is 1.81e-6, 1.32e-6 and 6.7e-7 rad for joints 1 to 3 (see the table of the `rrr-multibond` model). Plot [J1/qout](signal:J1/qout) and compare.

![The model canvas|900](assets/8ca3c8379cf8.png)
