# Power-split hybrid (Toyota Prius, THS-II)

A power-split hybrid electric vehicle of the Toyota Hybrid System II type (Prius NHW20, 2004)
with its energy management, on the NEDC. The engine drives the planet carrier, MG1 the sun gear,
MG2 and the final drive (4.113) the ring gear. All public data, with the sources in the README.

![Lever diagram of the planetary set: the speeds of sun, carrier and ring on one line|720](assets/a1370d0e8da2.svg)

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
