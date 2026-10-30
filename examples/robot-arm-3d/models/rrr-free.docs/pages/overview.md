# RRR arm without motors: energy conservation

The energy test of plan 9.8: [Arm](block:Arm) (`ArmDynamics3R`) with the motors removed (zero-torque `Se` on every joint: [Free1](block:Free1), [Free2](block:Free2), [Free3](block:Free3)) and $g = 0$, released with the joint rates $(2, -1.5, 2.5)$ rad/s (the start momenta of the block). The total energy $E = T + V$ is the block output [Arm/E](signal:Arm/E) and must stay constant. The block and the full model are described in the `rrr` model.

![The model canvas|900](assets/69a452bc7187.png)

![Free motion: joint rates and total energy|900](assets/06021147a077.png)

Measured (README): $\max\lvert E - E_0\rvert/\max\lvert E\rvert = 3.2\cdot10^{-13}$ over 5 s (the plan asks below 1e-6), with $E_0 = 1.769789$ J (absolute drift 5.6e-13 J), and the free motion agrees with the numpy RK4 replica to 3.1e-12 rad in $q$ after 5 s. The run uses `reltol` 1e-10, `abstol` 1e-12 and 1001 points.
