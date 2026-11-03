# Holding and lifting 1.5 t

**Scenario.** The front holds 1.5 t of soil in the bucket at q = (10°, −95°, −95°). At t = 0 the boom cap
pressure starts 15 % below the static value, so the boom drops a little and **rings at its hydraulic natural
frequency** while all valves are closed. From **3 to 6 s** the boom joystick ([LiftStick](block:LiftStick)) is at
0.5 and the boom lifts at about 0.1 m/s of rod speed. When the spool closes at 6 s, the moving front is stopped by the oil
trapped in both chambers: the boom rings again, now with the rod side pressurised as well, and only lightly damped
(the cylinder friction and the valve leakage are the only losses).

![The model canvas: supply and LS line (left), the three valve sections and cylinders, the linkage|900](assets/dba21eae4c6b.png)

![Boom pressures, rod extension, pump and LS pressures, flows and power|900](assets/29103e39498a.png)

**Expected outcome** (checked by `expected.json`):

| quantity | bond graph | design.py |
| --- | --- | --- |
| boom cylinder force at 2.9 s | 274.4 kN | 275.2 kN (moment balance) |
| arm / bucket cylinder force | 10.6 / 81.0 kN | 10.4 / 81.1 kN |
| ringing of the boom pressure (FFT) | 2.483 Hz | 2.489 Hz: eig(M⁻¹K) of the 3-DOF front |
| LS margin stand-by / during the lift | 27.0 / 26.2 bar | 25 bar + 2 bar regulation range |
| boom section flow at joystick 0.5 | 145 l/min | 150 l/min (−3 %: compensator saturation) |

The single-DOF estimate of the boom frequency, with the boom-joint inertia and the chamber stiffness
β(A²/V_A + A_r²/V_B), gives 2.60 Hz; the coupled 3-DOF mode at 2.49 Hz is what the bond graph shows. The
cylinder forces agree within the Coulomb band of the cylinder friction.

![The front at 6 s, the end of the lift|600](assets/58362d4b34b9.png)

**Blocks.** [Pump](block:Pump) (`LoadSensingPump`), [Vpump](block:Vpump) and [Vls](block:Vls) the pump and LS
lines, [BoomComp](block:BoomComp) and [BoomValve](block:BoomValve) the boom section,
[BoomCyl](block:BoomCyl) the boom cylinders, [BoomForce](block:BoomForce) the force pA·Ap − pB·Ar. [Ein](block:Ein),
[Ecyl](block:Ecyl) and [Eff](block:Eff) integrate the engine and the cylinder energy.

**Try:** raise the payload slider to 2.5 t: the boom cap pressure during the lift rises to about 170 bar, and the
section flow stays within 5 % (the compensator). Lower the bulk modulus to 0.6 GPa: the chamber stiffness halves,
and the ringing drops by √2, to about 1.8 Hz. Set the LS margin to 15 bar: the boom section gets only about
100 l/min instead of 145, because the margin no longer covers the 10 bar compensator plus the spool drop.
