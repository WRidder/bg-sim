# Torque-speed curve of the XL330

A dynamometer (an [MSf](block:Dyno) driven by a [ramp](block:SpeedRamp)) turns the horn of one [XL330](block:Servo) from -8 to 20 rad/s. The [goal](block:Goal) is far ahead, so the firmware asks for full PWM all the time. The torque at the horn, [Servo/Transmit/y](signal:Servo/Transmit/y), traces the servo's torque-speed curve:

- up to 6.8 rad/s, the **current limit**: the duty follows the upper edge of BAM's window, the current stays at 1.75 A, and the motor torque at $k_t \cdot 1.75 = 0.641$ N·m;
- above it, the **back-EMF line** at full PWM, $k_t (V - k_t \omega)/R$, down to the free speed $V/k_t = 20.2$ rad/s;
- minus the friction: the load-dependent M6 budget, large near rest (the Stribeck part), plus the viscous part.

Try `i_limit` = 1.0 A, the limit of the impact-guard firmware on the robot, and `v_bat` between 6.6 and 8.2 V.
