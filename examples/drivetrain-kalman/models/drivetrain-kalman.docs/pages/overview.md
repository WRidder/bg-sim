# LQG on a flexible two-inertia drivetrain

Plan 9.5's multi-domain control sample. A **pure bond graph plant** (D28), made of a DC motor, a 10:1 gearbox, two wheel inertias and a flexible three-segment rod, is driven by a **1 ms discrete LQG firmware**: an LQR with integral action and a steady-state Kalman filter that reconstructs the load speed from the motor encoder alone. A 10 rad/s reference steps at 0.1 s and a -0.5 N·m load torque steps at 1 s. The model `drivetrain-backlash` swaps the ideal gear for a backlash composite.

![The model canvas|900](assets/15ebb8a52987.png)

Parts: the electrical 1-junction [Elec](block:Elec) with [R](block:R) and [IL](block:IL), the gyrator [GY](block:GY), the motor junction [MotorJ](block:MotorJ) with [IJm](block:IJm) and [Rd](block:Rd), the gear transformers [TFa](block:TFa) and [TFb](block:TFb), [WheelJ1](block:WheelJ1), the three rod segments ([Rod1](block:Rod1), [Rod2](block:Rod2), [Rod3](block:Rod3)), [WheelJ2](block:WheelJ2) with the load source [Load](block:Load), the sensors [MotorSpeed](block:MotorSpeed), [Theta](block:Theta), [Encoder](block:Encoder), [Current](block:Current) and the firmware [LQG](block:LQG).

## What to try

- **Plots** tab: "Load speed" overlays [IW2/p.f](signal:IW2/p.f) with [LQG/w_load_hat](signal:LQG/w_load_hat); zoom into $t = 1$ s to see the load step, the 9.0 rad/s dip and the 0.3 s recovery.
- Plot [V/p.e](signal:V/p.e) to see the $\pm 24$ V saturation on the reference step.
- Plot [IW1/p.f](signal:IW1/p.f), [IM1/p.f](signal:IM1/p.f), [IM2/p.f](signal:IM2/p.f) and [IW2/p.f](signal:IW2/p.f) together: the three rod segments ring at about 25 Hz during the step and settle in phase.
- Re-run `design/design.py` with a different `Q`: the gains are plain JSON parameters of `LQG` (the script rewrites them in both model files).

## 3D view

`scenes/drivetrain-kalman.sdf` has the motor rotor, the gearbox output, wheel 1, the two intermediate inertias of the rod and wheel 2. Only the motor angle [Theta/y](signal:Theta/y) is measured, so the gearbox output is $0.1\times$ `Theta/y` and each rod segment is a joint bound to its twist `C1/q`, `C2/q`, `C3/q`; wheel 2 lags wheel 1 by their sum.

![3D view at t = 0.5 s|500](assets/7fbf26bf205f.png)

Continue with [the plant](page:plant), [the LQG design](page:controller) and [the results](page:results). The variant with a backlash gear is documented in the model `drivetrain-backlash`.
