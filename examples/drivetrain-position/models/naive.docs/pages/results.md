# Results and checks

![Load position, voltage and shaft twist of the naive PID|900](assets/669cc584c2df.png)

| quantity | measured |
| --- | --- |
| overshoot of the 1 rad step | 104.4 % (peak 2.044 rad at 0.36 s) |
| ringing frequency | 3.83 Hz (the shaft mode) |
| oscillation 1.4 to 2.2 s | 1.15 rad peak to peak, peaks of 1.45 rad at 1.9 s |
| dip at the 0.2 N·m disturbance | 0.73 rad |
| peak voltage | 24.00 V (saturated at the step) |
| maximum shaft twist | 0.90 rad |

`expected.json` checks the contrast, not a good response: the first load peak is above 1.835 rad (a peak lower bound, measured 2.015 over the window around the peak), the peak near 1.93 s is still above 1.281 rad (measured 1.453), the ringing frequency is 3.83 Hz $\pm 6$ %, the voltage is at most 24 V ([V/p.e](signal:V/p.e)) and there are no error diagnostics. The load position is [ThetaL/y](signal:ThetaL/y) and the shaft twist [C/q](signal:C/q).

The model `drivetrain-position` runs the same task with the firmware that handles the mode.
