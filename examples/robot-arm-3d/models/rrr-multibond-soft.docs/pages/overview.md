# Soft held directions ($k = 10^6$)

The `rrr-multibond` arm with all held directions ten times softer: $k_t = k_r = 10^6$ (N/m and N·m/rad), damping scaled with it (for example `bt` = 2800 for [L1/J](block:L1/J) against 8854 at $10^7$) and the static deflection starts scaled by ten. Everything else is as in `rrr-multibond`. It exists for the error-scaling measurement: the maximum joint-angle difference to the `rrr-torque` arm is 1.11e-4, 4.4e-5 and 2.7e-5 rad for joints 1 to 3 (see the table of the `rrr-multibond` model), ten times the stiff-case order. Plot [L1/J/qout](signal:L1/J/qout) and compare with the other stiffnesses.

![The model canvas|900](assets/dd694a64026f.png)
