# Gain-scheduled fly-by-wire

The aft-CG F-16 (xcg 0.38, an unstable pole of +0.66 1/s at the book's trim) flown by a pitch-rate command law at 400 ft/s and 25 000 ft, the low-dynamic-pressure corner of the envelope (84 psf, Mach 0.39). **Sched** reads its gains from tables over dynamic pressure and Mach; **Frozen** has the same law with the gains of a 1000 ft/s, 2000 ft point (qbar 1100 psf). Both get a 5 deg/s pitch-rate command from 1 to 4 s.

![The model canvas|900](assets/57a38f68ffc6.png)

| block | role |
| --- | --- |
| [StepOn](block:StepOn), [StepOff](block:StepOff), [QCmd](block:QCmd) | the pitch-rate command (0.05 s ramps) |
| [SchedKa](block:SchedKa), [SchedKq](block:SchedKq), [SchedKi](block:SchedKi) | stdlib `Lookup2D` over (qbar in Pa, Mach) |
| [SchedLaw](block:SchedLaw) | `PitchFBW`: $u = K_\alpha \alpha + K_q (q - 0.5\, q_{cmd}) + \xi$ with anti-windup |
| [SchedAct](block:SchedAct) | the servo, an instance of the library subsystem `F16Servo` (stdlib blocks): ±25 deg, 20.2 rad/s, ±60 deg/s |

## What to try

1. Press **Run**: Sched follows the command in 0.2 s with 7 % overshoot; Frozen needs a second and overshoots by 40 %.
2. Change the step with the slider, or move the CG forward: the law holds the response.

The stabilators of the 3D view turn with the servo output.

![3D view at t = 2.5 s|600](assets/e049639bbb1a.png)

Continue with [the design](page:design) and [the results](page:results).
