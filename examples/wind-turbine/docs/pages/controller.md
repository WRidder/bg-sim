# The baseline controller

The controller is the report's chapter 7, as in its DISCON source (Appendix C). It works on the generator speed, low-pass filtered at 0.25 Hz.

**Generator torque** (`VSTorque`):

| region | generator speed | torque |
| --- | --- | --- |
| 1 | below 670 rpm | 0 |
| 1½ | 670 to 871 rpm | linear up to the region-2 curve |
| 2 | 871 rpm to the 2½ line | $K\omega^2$, K = 0.0255764 N m/rpm² (the optimal tip-speed ratio) |
| 2½ | up to 1161.963 rpm | the line of an induction machine with 10 % slip |
| 3 | from 1161.963 rpm, or pitch ≥ 1° | $P/\omega$ with P = 5.29661 MW |

**Pitch** (`PitchPI`): a PI on the speed error to 1173.7 rpm.

$$\beta_{cmd} = GK\,(K_P\, e + K_I \textstyle\int e\, dt), \qquad GK = \frac{1}{1 + \beta / 6.302336°}$$

The gains are $K_P$ = 0.01882681 s and $K_I$ = 0.008068634. The integrator is clamped to the pitch limits, as in DISCON.

**Actuators** (`RateLimitedLag`): the pitch is a 50 ms lag with the 8°/s rate limit. The converter's torque loop is a 50 ms lag with the 15 kN m/s rate limit.

Differences from DISCON:
- the controller is continuous, not discrete;
- the gain correction reads the measured pitch, not the last command;
- the actuators have a small lag (DISCON's FAST model has an ideal pitch).
