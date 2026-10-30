# Servo with every refinement

The realistic drive model: all three forks of the `baseline` together.

![The full model canvas|900](assets/7d78494e106e.png)

| fork | what |
| --- | --- |
| switching inverter | [PWM](block:PWM): two-level, 4 kHz carrier, dead time 2 µs, drop 1.2 V |
| flexible coupling | [Kc](block:Kc) = 800 N·m/rad, [Dc](block:Dc) = 0.02 N·m·s/rad, load inertia [Jl](block:Jl), resonance 303.5 Hz, speed-feedback [Notch](block:Notch) |
| encoder | [Enc](block:Enc) 24 bit, [SpeedEst](block:SpeedEst), monitor [EncMon](block:EncMon); the notch sits behind the speed estimate |

The solver uses `reltol` 1e-4 and `abstol` 1e-7 with a 10 µs output interval.

![Speed of motor and load, and position|900](assets/4e2301307175.png)

## Results (README, `expected.json`)

| quantity | full |
| --- | --- |
| speed step: rise / overshoot / settle | 11.1 ms / 7.2 % / 28 ms |
| position step: rise / overshoot / settle (5 mrad) | 108 ms / 0.05 % / 549 ms |
| current step: rise / overshoot / settle (0.8 A) | 0.49 ms / 4.4 % / 2.2 ms |
| peak $i_q$ / torque | 15.74 A / 7.556 N·m |
| phase-current ripple (RMS / peak-to-peak) | 0.166 A / 0.686 A |
| position / speed at 1.15 s | -6.1e-4 rad / 0.027 rad/s |
| speed-estimate RMS error ($[1.0, 1.15]$ s) | 0.046 rad/s |
| notch input to output ripple (250 Hz high-pass) | 1.067 to 0.875 |
| load-side ringing (250 Hz high-pass) | 1.173 |

The check set has 19 model checks, the most of any variant. See the `baseline` model for the physics and the controller.

## 3D view

The joints `rotor_joint` ([Theta/y](signal:Theta/y)) and `coupling_joint` (`Kc/q`) are bound: the load marker lags and rings against the rotor marker.

![3D view at t = 0.1 s|500](assets/4eb5475f0293.png)
