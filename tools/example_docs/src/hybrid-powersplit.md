@@ figures @project
{
  "lever": {"kind": "svg", "svg": "lever"},
  "soc": {
    "kind": "plot", "model": "hybrid-rule-based", "xlim": [0, 1180],
    "rows": [
      {"ylabel": "speed [km/h]", "series": [{"signal": "Cycle/y", "label": "NEDC", "scale": 3.6}, {"signal": "VehicleSpeed/y", "label": "vehicle", "scale": 3.6, "style": "--"}], "legend": true},
      {"ylabel": "engine power [kW]", "series": [{"signal": "PEng/y", "label": "rule-based", "scale": 0.001}], "legend": true},
      {"ylabel": "SOC [-]", "series": [{"signal": "Battery/soc", "label": "rule-based"}], "legend": true}
    ]
  },
  "soc-ecms": {
    "kind": "plot", "model": "hybrid-ecms", "xlim": [0, 1180],
    "rows": [
      {"ylabel": "engine power [kW]", "series": [{"signal": "PEng/y", "label": "ECMS", "scale": 0.001}], "legend": true},
      {"ylabel": "SOC [-]", "series": [{"signal": "Battery/soc", "label": "ECMS"}, {"signal": "EMS/s_eq", "label": "s(soc) / 10", "scale": 0.1, "style": "--"}], "legend": true}
    ]
  },
  "points-rb": {
    "kind": "plot", "model": "hybrid-rule-based",
    "rows": [
      {"ylabel": "torque [N m]", "x": "EngineSpeed/y", "xlabel": "engine speed [rad/s]", "series": [{"signal": "WOT/y", "label": "full load", "style": "-"}, {"signal": "OOL/y", "label": "optimal line", "style": "."}, {"signal": "HCU/T_e", "label": "rule-based", "style": "."}], "legend": true}
    ]
  },
  "points-ecms": {
    "kind": "plot", "model": "hybrid-ecms",
    "rows": [
      {"ylabel": "torque [N m]", "x": "EngineSpeed/y", "xlabel": "engine speed [rad/s]", "series": [{"signal": "WOT/y", "label": "full load", "style": "-"}, {"signal": "OOL/y", "label": "optimal line", "style": "."}, {"signal": "HCU/T_e", "label": "ECMS", "style": "."}], "legend": true}
    ]
  }
}
@@ svg @project lever
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 380" font-family="sans-serif" font-size="12">
<rect width="720" height="380" fill="#ffffff"/>
<line x1="60" y1="200" x2="660" y2="200" stroke="#999" stroke-dasharray="4 3"/>
<text x="664" y="204" fill="#666" font-size="11">0</text>
<line x1="100" y1="40" x2="100" y2="350" stroke="#333" stroke-width="3"/>
<line x1="461" y1="40" x2="461" y2="350" stroke="#333" stroke-width="3"/>
<line x1="600" y1="40" x2="600" y2="350" stroke="#333" stroke-width="3"/>
<text x="100" y="30" text-anchor="middle" fill="#222">sun: MG1</text>
<text x="461" y="30" text-anchor="middle" fill="#222">carrier: engine</text>
<text x="600" y="30" text-anchor="middle" fill="#222">ring: MG2, wheels</text>
<line x1="100" y1="368" x2="461" y2="368" stroke="#666"/>
<line x1="461" y1="368" x2="600" y2="368" stroke="#666"/>
<text x="280" y="363" text-anchor="middle" fill="#666" font-size="11">Zr = 78</text>
<text x="530" y="363" text-anchor="middle" fill="#666" font-size="11">Zs = 30</text>
<line x1="100" y1="330" x2="600" y2="150" stroke="#1b9e77" stroke-width="2.5"/>
<circle cx="100" cy="330" r="5" fill="#1b9e77"/>
<circle cx="461" cy="200" r="5" fill="#1b9e77"/>
<circle cx="600" cy="150" r="5" fill="#1b9e77"/>
<text x="112" y="334" fill="#1b9e77">EV: w_s = -2.6 w_r</text>
<text x="470" y="222" fill="#1b9e77">engine at rest</text>
<line x1="100" y1="84" x2="600" y2="100" stroke="#d95f02" stroke-width="2.5"/>
<circle cx="100" cy="84" r="5" fill="#d95f02"/>
<circle cx="461" cy="95.5" r="5" fill="#d95f02"/>
<circle cx="600" cy="100" r="5" fill="#d95f02"/>
<text x="112" y="74" fill="#d95f02">hybrid: engine 2000 rpm, 52 km/h</text>
<text x="20" y="200" fill="#444" font-size="11" text-anchor="start">speed</text>
<text x="200" y="300" fill="#444" font-size="11">108 w_c = 30 w_s + 78 w_r: the three speeds lie on one straight line</text>
</svg>
@@ page @project overview - | Power-split hybrid
# Power-split hybrid (Toyota Prius, THS-II)

A power-split hybrid electric vehicle of the Toyota Hybrid System II type (Prius NHW20, 2004)
with its energy management, on the NEDC. The engine drives the planet carrier, MG1 the sun gear,
MG2 and the final drive (4.113) the ring gear. All public data, with the sources in the README.

![Lever diagram of the planetary set: the speeds of sun, carrier and ring on one line|720](@fig:lever)

The **lever diagram** shows why one planetary set is a continuously variable transmission. The
three speeds always lie on a straight line, the Willis equation
$108\,\omega_c = 30\,\omega_s + 78\,\omega_r$. The ring is tied to the wheels; MG1 on the sun moves the other end of the lever
and so sets the engine speed independently of the vehicle speed. In EV mode the engine stands
still and the sun turns backwards at 2.6 times the ring speed.

## Models

- [hybrid-kinematics](model:hybrid-kinematics): the planetary set alone. Willis equation, torque
  split and power balance, with a twin built from the stdlib `PlanetaryGear` for comparison.
- [hybrid-ev-mode](model:hybrid-ev-mode): the EV launch with MG2 alone.
- [hybrid-rule-based](model:hybrid-rule-based): the NEDC with the rule-based energy management.
- [hybrid-ecms](model:hybrid-ecms): the NEDC with the ECMS.

## The planetary set as a bond graph

The set is `Planetary` in every model, an instance of the library subsystem `Planetary`
(`library/Planetary.bgsub.json`). It has three transformers around one
0-junction:

```
 carrier --TFc (Zs+Zr)--\
                         0 --- MeshForce (De)      effort F: the mesh force (per tooth)
 sun     --TFs (Zs)  ---/|
 ring    --TFr (Zr)  ----/
```

The common effort F of the 0-junction is the tooth-normalised mesh force. Each TF turns it into
its shaft torque: Zs F on the sun, Zr F on the ring and (Zs + Zr) F on the carrier. So the torques
always split 30 : 78, and the carrier carries their sum. The flow balance of the 0-junction is the
Willis equation. The set stores no energy, so it is power conserving: $P_c = P_s + P_r$.

Inertias sit on the shaft 1-junctions: the sun with the MG1 rotor, and the ring with the MG2
rotor. The engine inertia reaches the carrier through the transaxle input damper (C + R). A
rigid joint there would put three rigid inertias on a two-degree-of-freedom set, and one of them
would get derivative causality.

## Data

| part | value |
| --- | --- |
| vehicle | 1385 kg with driver, Cd 0.26, A 2.2 m², c_rr 0.009, r 0.30 m |
| planetary set | Zs 30, Zr 78, final drive 4.113 (ORNL/TM-2006/423) |
| engine | 1NZ-FXE, 1.5 l Atkinson, 57 kW at 5000 rpm, 115 N·m at 4200 rpm; Willans fuel model, 37 % peak efficiency (226 g/kWh) |
| MG2 | 50 kW, 400 N·m, 6000 rpm, 93 % peak |
| MG1 | 10000 rpm, 70 N·m (assumed) |
| battery | NiMH 168 cells, 201.6 V, 6.5 A·h, 21 kW; Thevenin model |
@@ page @project energy overview | Energy management
# Energy management

Two strategies run in the discrete block `EnergyManager` (10 Hz), chosen by its `strategy`
parameter (the select card on the dashboard). Below it, the continuous `PowerSplitControl` holds
the chosen engine point. MG1 runs a speed PI on the engine through the sun gear. MG2 fills in the
wheel torque within its own limits and the battery's. The friction brakes take the braking that
MG2 cannot recover, which is mainly below 6.6 km/h, where the regenerative torque fades out.

Both strategies aim at a SOC target that drops with speed:
$soc_t = soc_{ref} - \eta_{kin}\,\tfrac12 m v^2 / E_{bat}$ ($\eta_{kin} = 0.6$). At 120 km/h the
target is 0.09 below the standstill target, which leaves room for the braking energy.

- **Rule-based.** The requested power is $P_{req} = F_{dem} v + k_{soc}(soc_t - soc)$. The engine
  starts above $P_{on}$ = 9 kW, at low SOC or above 70 km/h. It stops below $0.55\,P_{on}$ or
  when the driver brakes. Running, it delivers $\max(P_{req}, P_{min})$ on the **optimal operating
  line**, the minimum-fuel speed for each power.
- **ECMS** (equivalent consumption minimisation). Every tick it compares "engine off" with 192
  operating points (16 speeds × 12 torques) and picks the least
  $\dot m_{eq} = \dot m_f + s\,(P_b + R_{bat} P_b^2/V^2)/H_l$ with
  $s = s_0\,(1 - k_p (soc - soc_t)/0.1)$. Here $P_b$ is the battery power of the quasi-static
  planetary balance with the machine losses, and $s_0 = 2.6$ is the charge-sustaining factor.

![Rule-based: speed tracking, engine power and SOC on the NEDC|1000](@fig:soc)

![ECMS: engine power, SOC and the SOC-corrected equivalence factor|1000](@fig:soc-ecms)

## Comparison (NEDC, hot start, 11.01 km)

| | rule-based | ECMS |
| --- | --- | --- |
| fuel (L/100 km) | 3.46 | 3.47 |
| final SOC (start 0.60) | 0.610 | 0.594 |
| SOC-corrected fuel (L/100 km), 0.01 SOC ≈ 4 g | 3.41 | 3.50 |
| engine on-time (s) | 338 | 360 |
| engine starts | 24 | 11 |
| mean engine efficiency when firing | 36.4 % | 36.2 % |
| regenerative share of the braking energy | 0.986 | 0.986 |

The published figure is 4.3 L/100 km for the 2004 Prius (EU type approval, NEDC combined, cold
start). The model starts hot, with 250 W of auxiliaries and no warm-up, so about 3.5 L/100 km is
in line with it.

The two strategies end within 3 % of each other. The rule-based one runs exactly on the optimal
line that the ECMS candidates also follow. The ECMS has no look-ahead: it keeps the engine on
longer at lower power and starts it half as often.

| rule-based | ECMS |
| --- | --- |
| ![Rule-based engine operating points|480](@fig:points-rb) | ![ECMS engine operating points|480](@fig:points-ecms) |
@@ figures hybrid-kinematics
{
  "diagram": {"kind": "diagram", "model": "hybrid-kinematics"},
  "run": {
    "kind": "plot", "model": "hybrid-kinematics", "xlim": [0, 10],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "SunSpeed/y", "label": "sun"}, {"signal": "CarrierSpeed/y", "label": "carrier"}, {"signal": "RingSpeed/y", "label": "ring"}, {"signal": "Ring2Speed/y", "label": "ring, stdlib PlanetaryGear", "style": ":"}], "legend": true},
      {"ylabel": "power [W]", "series": [{"signal": "PCarrier/y", "label": "carrier"}, {"signal": "PSun/y", "label": "sun"}, {"signal": "PRing/y", "label": "ring"}], "legend": true}
    ]
  }
}
@@ page hybrid-kinematics overview - | Overview
# Planetary set: kinematics

The THS-II planetary set alone. A 60 N·m torque step at 0.5 s on the carrier (the engine)
drives the sun and the ring against viscous loads: 0.05 N·m·s/rad on the sun (inertia 0.02
kg·m²) and 0.4 N·m·s/rad on the ring (0.2 kg·m²).

![Diagram: the bond-graph planetary (top) and the stdlib PlanetaryGear twin (bottom)|900](@fig:diagram)

Blocks: [Engine](block:Engine) (MSe, fed by [EngineStep](block:EngineStep)) on the
[Carrier](block:Carrier) 1-junction, the [Planetary](block:Planetary) subsystem (TFc, TFs, TFr
around the mesh 0-junction), the [Sun](block:Sun) and [Ring](block:Ring) 1-junctions with
their inertias and loads. Below them is the same set built with the stdlib
[Gear](block:Gear) (`PlanetaryGear`).

## What it shows

- **Torque split**: [SunTorque/y](signal:SunTorque/y) : [RingTorque/y](signal:RingTorque/y) =
  30 : 78 at every instant, from the mesh force [Planetary/MeshForce/y](signal:Planetary/MeshForce/y).
- **Willis**: $30\,\omega_s + 78\,\omega_r - 108\,\omega_c = 0$ to 1e-15 over the run.
- **Steady state**: $T_s = 30/108 \cdot 60 = 16.67$ N·m $= 0.05\,\omega_s$, so
  [SunSpeed/y](signal:SunSpeed/y) → 333.3 rad/s; $T_r = 43.33$ N·m $= 0.4\,\omega_r$, so
  [RingSpeed/y](signal:RingSpeed/y) → 108.3 rad/s; and [CarrierSpeed/y](signal:CarrierSpeed/y) →
  170.8 rad/s.
- **Power**: [PCarrier/y](signal:PCarrier/y) = [PSun/y](signal:PSun/y) + [PRing/y](signal:PRing/y).

![Speeds and powers; the stdlib twin lies on the bond-graph ring speed|900](@fig:run)

## What to try

- Change the teeth on the dashboard (Zs, Zr): the split and the steady speeds follow.
- Plot [Ring2Speed/y](signal:Ring2Speed/y) against [RingSpeed/y](signal:RingSpeed/y): the two
  sets agree exactly.
@@ figures hybrid-ev-mode
{
  "diagram": {"kind": "diagram", "model": "hybrid-ev-mode"},
  "run": {
    "kind": "plot", "model": "hybrid-ev-mode", "xlim": [0, 10],
    "rows": [
      {"ylabel": "speed [km/h]", "series": [{"signal": "VehicleSpeed/y", "label": "vehicle", "scale": 3.6}], "hlines": [{"y": 30, "label": "30 km/h"}], "vlines": [{"x": 6.8545, "label": "reference 6.85 s"}], "legend": true},
      {"ylabel": "speed [rad/s]", "series": [{"signal": "EngineSpeed/y", "label": "engine"}, {"signal": "SunSpeed/y", "label": "sun (MG1)"}, {"signal": "RingSpeed/y", "label": "ring (MG2)"}], "legend": true},
      {"ylabel": "battery [kW]", "series": [{"signal": "PBat/y", "label": "battery power", "scale": 0.001}], "hlines": [{"y": 21, "label": "21 kW rating"}], "legend": true}
    ]
  }
}
@@ page hybrid-ev-mode overview - | Overview
# EV launch

MG2 alone pulls the Prius away from rest. A step of the tractive force demand at 0.5 s asks for
150 N·m at the ring. The energy manager is replaced by constants (engine off, speed reference 0),
so MG1 holds the engine at rest through the sun gear while the sun turns backwards.

![Diagram of the plant: engine and damper, planetary subsystem, MG1 and MG2 with their inverters, driveline, vehicle and battery|1000](@fig:diagram)

Plant blocks: [EngineTorque](block:EngineTorque) and [EngineDrag](block:EngineDrag) on the
engine inertia; [Damper](block:Damper) onto the carrier; [Planetary](block:Planetary); MG1
([Inv1](block:Inv1), [Rs1](block:Rs1), [Ls1](block:Ls1), [MG1](block:MG1)) on the [Sun](block:Sun);
MG2 ([Inv2](block:Inv2), [Rs2](block:Rs2), [Ls2](block:Ls2), [MG2](block:MG2)) on the
[Ring](block:Ring) with the [SpinLoss](block:SpinLoss); [FinalDrive](block:FinalDrive), the half
shafts ([ShaftK](block:ShaftK), [ShaftD](block:ShaftD)), [Brakes](block:Brakes),
[Tyre](block:Tyre) and the [VehicleMass](block:VehicleMass) with [Aero](block:Aero),
[Rolling](block:Rolling) and [Grade](block:Grade); the [Battery](block:Battery), [DCLink](block:DCLink)
and [Aux](block:Aux) on the DC bus. The controller is [HCU](block:HCU) (`PowerSplitControl`).

## What it shows

- **Launch time**: [VehicleSpeed/y](signal:VehicleSpeed/y) reaches 30 km/h at 6.86 s. A rigid
  1-DOF ODE with the same losses gives 6.855 s (the closed form without losses gives 6.730 s).
- **MG1 holds the engine**: [EngineSpeed/y](signal:EngineSpeed/y) stays within 3.5 rad/s of rest,
  and [SunSpeed/y](signal:SunSpeed/y) = −2.6 × [RingSpeed/y](signal:RingSpeed/y).
- **Battery limit**: above about 30 km/h, MG2's electrical power ($T\omega + R_s T^2/k^2$) reaches
  the 21 kW battery rating. The HCU then lowers the torque, so [PBat/y](signal:PBat/y) stays at
  the rating.

![Speed, shaft speeds and battery power|900](@fig:run)

## What to try

- Raise the mass or the grade on the dashboard. At 10 % grade the launch is about three times
  slower.
- Plot [HCU/T_m](signal:HCU/T_m) (MG2 torque) and [HCU/T_g](signal:HCU/T_g) (the small MG1
  torque that holds the engine).
@@ figures hybrid-rule-based
{
  "diagram": {"kind": "diagram", "model": "hybrid-rule-based"},
  "run": {
    "kind": "plot", "model": "hybrid-rule-based", "xlim": [780, 1180],
    "rows": [
      {"ylabel": "speed [km/h]", "series": [{"signal": "Cycle/y", "label": "NEDC", "scale": 3.6}, {"signal": "VehicleSpeed/y", "label": "vehicle", "scale": 3.6, "style": "--"}], "legend": true},
      {"ylabel": "speed [rad/s]", "series": [{"signal": "CarrierSpeed/y", "label": "carrier (engine)"}, {"signal": "SunSpeed/y", "label": "sun (MG1)"}, {"signal": "RingSpeed/y", "label": "ring (MG2)"}], "legend": true},
      {"ylabel": "power [kW]", "series": [{"signal": "PEng/y", "label": "engine", "scale": 0.001}, {"signal": "PMG1/y", "label": "MG1", "scale": 0.001}, {"signal": "PMG2/y", "label": "MG2", "scale": 0.001}, {"signal": "PBat/y", "label": "battery", "scale": 0.001}], "legend": true},
      {"ylabel": "SOC [-]", "series": [{"signal": "Battery/soc", "label": "SOC"}], "legend": true}
    ]
  }
}
@@ page hybrid-rule-based overview - | Overview
# NEDC, rule-based energy management

The Prius on the NEDC: four ECE-15 urban cycles and the EUDC, generated from the R83 definition
(11.013 km, 1180 s). A PI driver ([Driver](block:Driver)) follows the cycle
([Cycle](block:Cycle)) and asks for a tractive force. The [EMS](block:EMS) (`EnergyManager`,
strategy 0) chooses the engine state and operating point. The [HCU](block:HCU)
(`PowerSplitControl`) makes MG1 hold the engine speed and MG2 fill in the wheel torque. The plant
is that of [hybrid-ev-mode](model:hybrid-ev-mode). The energy management is described in
[the project docs](project:energy).

![Diagram|1000](@fig:diagram)

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

![EUDC: speed, planetary speeds (the lever in time), power flow and SOC|1000](@fig:run)

On the EUDC the planetary speeds show the power split at work. At 70 to 100 km/h the engine runs
slower than the ring, so the sun turns backwards. MG1 then motors and MG2 generates: the
negative split, or power circulation (at 70 km/h about 5 kW circulates for 9 kW of engine
power). Above 100 km/h MG1 would exceed 10000 rpm with the engine at rest, so the engine must
keep turning.

## What to try

- Change the rule-based engine start `P_on_kW` and the target SOC `soc_ref` on the dashboard.
- Switch the select card to ECMS: the same model then runs the [ECMS](model:hybrid-ecms) strategy.
- Look at the XY plot of the engine operating points: they lie on the optimal line.
@@ figures hybrid-ecms
{
  "diagram": {"kind": "diagram", "model": "hybrid-ecms"},
  "run": {
    "kind": "plot", "model": "hybrid-ecms", "xlim": [0, 1180],
    "rows": [
      {"ylabel": "engine [kW]", "series": [{"signal": "PEng/y", "label": "engine power", "scale": 0.001}], "legend": true},
      {"ylabel": "SOC [-]", "series": [{"signal": "Battery/soc", "label": "SOC"}], "legend": true},
      {"ylabel": "fuel [l]", "series": [{"signal": "Meters/FuelL/y", "label": "fuel used"}], "legend": true}
    ]
  }
}
@@ page hybrid-ecms overview - | Overview
# NEDC, ECMS

The same vehicle and cycle as [hybrid-rule-based](model:hybrid-rule-based), with the
[EMS](block:EMS) set to strategy 1, the **equivalent consumption minimisation strategy**. Every
0.1 s it weighs the fuel rate of each operating point against the battery power it causes,
valued at $s/H_l$:

$$\dot m_{eq} = \dot m_f(\omega, T) + s\,\frac{P_b + R_{bat} P_b^2/V^2}{H_l}, \qquad s = s_0 \left(1 - k_p\,\frac{soc - soc_t}{0.1}\right).$$

The fuel rates of the candidates are the plant's own engine map, so the strategy and the plant
agree. The battery term includes its internal loss, so the ECMS does not cycle the battery for
nothing.

![Diagram|1000](@fig:diagram)

## Readouts

- Fuel: [Meters/L100km/y](signal:Meters/L100km/y) **3.47 L/100 km**.
- SOC: [Battery/soc](signal:Battery/soc) ends at 0.594. The equivalence factor
  [EMS/s_eq](signal:EMS/s_eq) rises as the SOC falls below its target.
- Engine on-time [Meters/OnTime/y](signal:Meters/OnTime/y) 360 s, with fewer starts than the
  rule-based strategy.
- The chosen point: [EMS/w_ref](signal:EMS/w_ref), [EMS/T_ref](signal:EMS/T_ref) and its
  estimated battery power [EMS/P_bat_est](signal:EMS/P_bat_est).

![Engine power, SOC and fuel over the NEDC|1000](@fig:run)

## What to try

- Change `s0` on the dashboard. s0 = 2.2 makes battery energy cheap, and the car ends at SOC
  0.58. A higher factor charges more.
- Change `k_p`, the SOC feedback. At 0 the equivalence factor no longer reacts to the SOC.
- Compare with the rule-based run in [the project docs](project:energy).
