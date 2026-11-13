# XL330 on the bench

One [XL330](block:Servo) swings the 100 g test arm of microduck_rl (the arm's centre of mass is 96.6 mm from the axis). The [goal](block:Goal) steps from 0 to 1 rad at 0.1 s and back at 0.9 s. The [supply](block:Supply) is 7.4 V. The arm is a `Revolute3D` joint `J` with a rigid body `B`, so gravity pulls it back to hanging.

![Diagram|800](assets/d2aca79d1a2b.png)

This instance pins the backlash to 0, because the BAM simulator it is checked against has a rigid gear.

## Run it

1. Press **Run** and plot [Servo/Encoder/y](signal:Servo/Encoder/y) against the [goal](signal:Goal/y). The arm starts moving 20 ms after the goal: that is the firmware latency.
2. Change the global `kp_fw` to 50, the limp gain of the robot. The arm stops well short of 1 rad.
3. Set `v_bat` to 6.6 V (an empty pack): the P stiffness falls with the voltage.

See [Results](page:results).
