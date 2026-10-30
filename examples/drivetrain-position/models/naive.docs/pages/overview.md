# Naive: a textbook PID on the motor position

The same compliant drivetrain as in `drivetrain-position` (1.2 N·m/rad shaft, first mode 3.9 Hz with damping 0.034), controlled the way a rigid drivetrain would be: a **PID on the motor-side position**, reference $n\,r$, tuned for the rigid-body plant. It is here as the contrast to the showcase: it overshoots the 1 rad step by 104 % and rings for seconds.

![The model canvas|900](assets/ed5f9f1e8182.png)

The plant is the bond graph described in the other model: [V](block:V), [Elec](block:Elec), [GY](block:GY), [MotorJ](block:MotorJ), the gear [TFa](block:TFa) and [TFb](block:TFb), [WheelJ1](block:WheelJ1), the shaft ([S1](block:S1), [Shaft](block:Shaft), [C](block:C), [D](block:D)), [WheelJ2](block:WheelJ2) and the load source [Load](block:Load). The reference [Ref](block:Ref) is multiplied by the gear ratio in [ToMotor](block:ToMotor) and goes with the motor angle [Theta](block:Theta) into [PID](block:PID).

Continue with [the structure](page:structure), [the PID](page:controller) and [the results](page:results).
