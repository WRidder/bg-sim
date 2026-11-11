# NEDC, ECMS

The same vehicle and cycle as [hybrid-rule-based](model:hybrid-rule-based), with the
[EMS](block:EMS) set to strategy 1, the **equivalent consumption minimisation strategy**. Every
0.1 s it weighs the fuel rate of each operating point against the battery power it causes,
valued at $s/H_l$:

$$\dot m_{eq} = \dot m_f(\omega, T) + s\,\frac{P_b + R_{bat} P_b^2/V^2}{H_l}, \qquad s = s_0 \left(1 - k_p\,\frac{soc - soc_t}{0.1}\right).$$

The fuel rates of the candidates are the plant's own engine map, so the strategy and the plant
agree. The battery term includes its internal loss, so the ECMS does not cycle the battery for
nothing.

![Diagram|1000](assets/ee78f1abb4fd.png)

## Readouts

- Fuel: [Meters/L100km/y](signal:Meters/L100km/y) **3.47 L/100 km**.
- SOC: [Battery/soc](signal:Battery/soc) ends at 0.594. The equivalence factor
  [EMS/s_eq](signal:EMS/s_eq) rises as the SOC falls below its target.
- Engine on-time [Meters/OnTime/y](signal:Meters/OnTime/y) 360 s, with fewer starts than the
  rule-based strategy.
- The chosen point: [EMS/w_ref](signal:EMS/w_ref), [EMS/T_ref](signal:EMS/T_ref) and its
  estimated battery power [EMS/P_bat_est](signal:EMS/P_bat_est).

![Engine power, SOC and fuel over the NEDC|1000](assets/80abd97dc720.png)

## What to try

- Change `s0` on the dashboard. s0 = 2.2 makes battery energy cheap, and the car ends at SOC
  0.58. A higher factor charges more.
- Change `k_p`, the SOC feedback. At 0 the equivalence factor no longer reacts to the SOC.
- Compare with the rule-based run in [the project docs](project:energy).
