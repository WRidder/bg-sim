# Results

![Tank voltage, scaled state against the textbook equation, diode power (mu = 1)|900](assets/1be0cf902b60.png)

The circuit's scaled voltage and the textbook equation lie on top of each other from the first instant. The oscillation grows from 72.5 mV onto the limit cycle within three periods.

![Phase portrait of the circuit, from x = 0.5 to the limit cycle|560](assets/698fdf6a1cf4.png)

## Energy per cycle

![Tank energy, energy supplied and dissipated by the diode, and their per-cycle increments|900](assets/22501b6a16c8.png)

On the limit cycle the diode supplies 13.418 pJ per cycle on the inner part ($|x| < \sqrt3$) and dissipates the same 13.418 pJ near the voltage peaks. The tank energy returns to the same value every cycle.

## Relaxation at mu = 5

![Tank voltage and inductor current at mu = 5|900](assets/0b536a070060.png)

At $\mu = 5$ ($Z_0$ = 236 Ω) the voltage jumps between the branches and the current ramps slowly: the frequency falls to 5.41 MHz.

## Checks (`expected.json`)

| check | bgsim | reference (scipy) |
| --- | --- | --- |
| period of the tank voltage, last cycle | 106.04950 ns | 106.04950 ns |
| frequency (cycle meter) | 9.429558 MHz | 9.429558 MHz |
| amplitude $x_{max}$ | 2.008620 | 2.0086199 (averaging theory: 2) |
| $\max\lvert Xc - Ref/x\rvert$, $\max\lvert Yc - Ref/y\rvert$ | 1.4e-12, 2.4e-12 | 1.9e-11, 3.1e-11 (scipy circuit against scipy textbook) |
| energy invariant $E + \int P_D\,dt$ | drift 4.4e-13 of the energy scale | exact |
| supplied and dissipated per cycle | 13.41840 pJ each | 13.41840 pJ each |
| period vs $2\pi(1 + \mu^2/16)$ | +0.19 % | |

Two more runs set the dashboard's mu to 0.2 and 5 and check the same quantities: 9.975089 MHz and 5.410834 MHz.
