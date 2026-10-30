# Results and checks

The three plots come from real runs of this project. The first shows the showcase run.

![Load position, voltage and shaft twist of drivetrain-position|900](assets/97d135a26cd5.png)

The same signals with the `naive` model overlaid. The textbook PID overshoots by 104 %, rings at the shaft mode (3.8 Hz), saturates the supply on the step and still swings by 0.73 rad when the disturbance arrives:

![naive against drivetrain-position|900](assets/98b06dc9469b.png)

The estimator after the load torque step at 2.2 s (the estimate follows the load angle within 3 mrad RMS; the torque estimate converges in about 0.1 s):

![The Kalman filter after the load step|900](assets/807cc29e6800.png)

## Measured numbers

| | `naive` (PID) | `drivetrain-position` |
| --- | --- | --- |
| overshoot of the 1 rad step | 104.4 % (peak 2.044 rad at 0.36 s) | 0.02 % |
| time to stay inside the 2 % band | never (rings until the end of the step phase) | 0.66 s after the command (the trajectory takes 0.8 s) |
| oscillation 1.4 to 2.2 s | 1.15 rad peak to peak | 0.39 mrad peak to peak |
| dip at the 0.2 N·m disturbance | 0.73 rad | 0.058 rad, back inside 20 mrad in 0.13 s |
| peak voltage | 24.00 V (saturated at the step) | 13.3 V (at the disturbance) |
| maximum shaft twist | 0.90 rad | 0.33 rad |

## Checks (`expected.json`)

- rest before the step: [ThetaL/y](signal:ThetaL/y) and [IW2/p.f](signal:IW2/p.f) are zero before 0.19 s;
- settling inside 0.02 rad within 0.9 s, overshoot below 2 %, value at 2.15 s within 5 mrad of 1 rad;
- peak-to-peak below 4 mrad between 1.4 and 2.15 s (residual oscillation after settling);
- disturbance: dip of at most 0.092 rad, back within 10 mrad at 3.2 s, [Ctrl/T_hat](signal:Ctrl/T_hat) at 0.2 N·m within 5 %;
- the voltage [V/p.e](signal:V/p.e) is at most 24 V;
- seven `cursor_value` checks of [ThetaL/y](signal:ThetaL/y) against the closed-loop prediction of `design/design.py` (4 mrad tolerance; the largest difference is 2.7 mrad, in the first 100 ms after the disturbance);
- no error diagnostics.

The model `drivetrain-position-open-loop` runs the plant alone (+2 V at 0.05 s and a load step at 0.6 s) and compares load and motor angle with the ODE at eight times: the largest difference is $1.4\cdot10^{-8}$ rad.
