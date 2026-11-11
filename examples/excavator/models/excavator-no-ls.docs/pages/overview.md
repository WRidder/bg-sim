# The same cycle without load sensing

**Scenario.** The dig cycle of [excavator-dig-cycle](model:excavator-dig-cycle), with the same operator and the
same soil, on a **constant-pressure supply**: the pump's LS port sees the tank and the margin is set to 280 bar,
so [Pump](block:Pump) holds about 281 bar in the pump line whatever the load. There is no LS line and no shuttle
network; the compensators and spools throttle the difference between 281 bar and the load pressure.

![Pressures, power and energy|900](assets/3b2a9c60895f.png)

**Expected outcome:**

| quantity | no-LS | LS (dig-cycle) |
| --- | --- | --- |
| pump pressure | ≥ 201 bar (281 bar between moves) | 25 bar above the highest load |
| engine power at stand-by | 24.9 kW | 1.6 kW |
| engine energy for the cycle | 1.52 MJ | 0.57 MJ |
| cylinder work / engine energy | 0.10 | 0.27 |

The motion is almost the same, because the compensated sections deliver the same flow; only the energy changes.
The stand-by power is high because the pump friction torque grows with the pressure even at zero stroke.

**Try:** lower the constant pressure (the global `dp_ls`) to 200 bar: the cycle still runs (the bucket fills to
0.72), and the engine energy drops to 1.15 MJ, still twice that of load sensing, because the pump pressure has to
cover the highest load of the cycle all the time.
