# Hover with a yaw kick and a roll kick

The same vehicle, released in hover at 1.32 m with the rotor at the hover speed. It starts with
a **0.8 rad/s yaw kick** and a **0.3 rad/s roll kick**, and flies a 1 m lateral step from 3 s.
There is no yaw command anywhere.

![The 1 m step, the height and the yaw](assets/661057c72ee6.png)

![During the step, 4.5 s](assets/1fad6dd95aea.png)

## What it shows

* **Passive yaw.** The fins damp the kick with the time constant $(J_z+J_a)/D=0.870$ s, so the
  heading turns by $r_0\tau(1-e^{-t/\tau})$: 0.674 rad at 3 s by `design.py`, 0.684 rad
  measured. Nothing brings the heading back.
* **Step.** The one-axis model of `design.py` overshoots the 1 m step by 1.27 cm, and by
  2.42 cm with the IMU's horizontal accelerometer bias as a disturbance. The model overshoots
  1.77 cm. The height stays between 1.3155 and 1.3228 m.
* **Hover trim.** The mean rotor speed is 539.04 rad/s, against $\sqrt{T_0/k_T}=539.11$ rad/s
  with the fin download in $T_0$. In any steady state the fin torque equals the rotor drag,
  whatever the fin law, so the trim incidence (11.54°) shows in the yaw rate instead. With the
  trim incidence, the yaw torque balances at zero rate, and the mean yaw rate over 6–8 s is
  0.029 rad/s. An imbalance of $\Delta Q$ would settle at $\Delta Q/D$, so 0.05 rad/s
  corresponds to 0.2 mN m, 0.07 % of $Q_0$.
* **Power.** The pack delivers 188.01 W at 7.565 A, against 187.94 W and 7.562 A from the
  drive's operating point (with the pack's charge at 7 s). The motor current is 10.84 A.
* **Gyroscopic plant.** With the rate loop switched off, the roll kick turns into a circular
  nutation at 2.02 Hz, against $h/\sqrt{J_xJ_y}$ = 2.06 Hz.

![Free nutation with the rate loop off](assets/8c5b579fd2e8.png)

## Checks

The checks compare the heading, the hover rotor speed, the yaw rate at the trim incidence, the
pack power and the currents, the accelerometer-bias estimate, the step overshoot and the
nutation frequency with `design.py`. They also check the height band, the navigation errors, the scene bindings and the
diagnostics.

```
uv run examples/run_checks.py --only single-propeller-drone
```
