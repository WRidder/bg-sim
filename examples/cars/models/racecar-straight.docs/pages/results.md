# Results

![Speed, motor torque and battery current|900](assets/f3cfe8e299bb.png)

The reference is the 1-D longitudinal model of `racecar-launch` with the same brake blend, started at its top speed (motor at 260 kW, 16 012 rpm, 155.1 N m). The model's pedal ramp is a step at the middle of the ramp (10.0275 s) in the reference.

| t [s] | speed [m/s] | motor torque [N m] | battery current [A] |
| --- | --- | --- | --- |
| 9.9 | 73.89 / 73.66 | 154.6 / 155.1 | 740.8 / 740.8 |
| 10.25 | 70.28 / 70.05 | -130.7 / -131.0 | -472.0 / -472.0 |
| 11 | 58.06 / 57.89 | -160.4 / -160.8 | -471.9 / -471.9 |
| 12 | 43.06 / 42.92 | -185.7 / -185.7 | -402.0 / -401.1 |
| 14 | 15.77 / 15.67 | -185.7 / -185.7 | -148.1 / -147.4 |

Each cell is bg-sim / reference. bg-sim settles 0.3 % above the reference's top speed (the reference holds the load transfer quasi-static and the tyre slip in steady state). The car then loses speed at the same rate, 58.1 and 58.0 m/s from 10 to 14 s. While the power limit is active, the regen current holds at 472 A.
