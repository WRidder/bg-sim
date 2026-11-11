# NEDC, rule-based energy management

The Prius on the NEDC: four ECE-15 urban cycles and the EUDC, generated from the R83 definition
(11.013 km, 1180 s). A PI driver ([Driver](block:Driver)) follows the cycle
([Cycle](block:Cycle)) and asks for a tractive force. The [EMS](block:EMS) (`EnergyManager`,
strategy 0) chooses the engine state and operating point. The [HCU](block:HCU)
(`PowerSplitControl`) makes MG1 hold the engine speed and MG2 fill in the wheel torque. The plant
is that of [hybrid-ev-mode](model:hybrid-ev-mode). The energy management is described in
[the project docs](project:energy).

![Diagram|1000](assets/ee78f1abb4fd.png)

## Readouts

- Fuel: [Meters/L100km/y](signal:Meters/L100km/y) **3.46 L/100 km** and
  [Meters/FuelL/y](signal:Meters/FuelL/y) 0.38 l. The fuel rate is the engine map
  [FuelMap](block:FuelMap) at the engine speed and torque.
- SOC: [Battery/soc](signal:Battery/soc) ends at 0.610 (start 0.60). The BMS coulomb count
  [BMS/y](signal:BMS/y) agrees.
- Engine on-time: [Meters/OnTime/y](signal:Meters/OnTime/y) 338 s.
- Power flow: [PEng/y](signal:PEng/y), [PMG1/y](signal:PMG1/y), [PMG2/y](signal:PMG2/y),
  [PBat/y](signal:PBat/y), [PWheel/y](signal:PWheel/y).
- Braking: [Meters/RegenShare/y](signal:Meters/RegenShare/y) 0.986. Only 16 kJ of the 1.21 MJ
  braking demand goes to the friction brakes.

![EUDC: speed, planetary speeds (the lever in time), power flow and SOC|1000](assets/63c0be7c4502.png)

On the EUDC the planetary speeds show the power split at work. At 70 to 100 km/h the engine runs
slower than the ring, so the sun turns backwards. MG1 then motors and MG2 generates: the
negative split, or power circulation (at 70 km/h about 5 kW circulates for 9 kW of engine
power). Above 100 km/h MG1 would exceed 10000 rpm with the engine at rest, so the engine must
keep turning.

## What to try

- Change the rule-based engine start `P_on_kW` and the target SOC `soc_ref` on the dashboard.
- Switch the select card to ECMS: the same model then runs the [ECMS](model:hybrid-ecms) strategy.
- Look at the XY plot of the engine operating points: they lie on the optimal line.
