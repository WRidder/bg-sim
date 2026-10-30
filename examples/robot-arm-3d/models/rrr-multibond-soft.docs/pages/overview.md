# Soft held directions ($k = 10^6$)

The `rrr-multibond` arm with all held directions ten times softer: $k_t = k_r = 10^6$ (N/m and N·m/rad), damping scaled with it (for example `bt` = 2800 for [J1](block:J1) against 8854 at $10^7$) and the static deflection starts scaled by ten. Everything else is as in `rrr-multibond`. It exists for the error-scaling measurement: the maximum joint-angle difference to the `rrr-torque` arm is 1.11e-4, 4.4e-5 and 2.7e-5 rad for joints 1 to 3 (see the table of the `rrr-multibond` model), ten times the stiff-case order. Plot [J1/qout](signal:J1/qout) and compare with the other stiffnesses.

![The model canvas|900](assets/8ca3c8379cf8.png)
