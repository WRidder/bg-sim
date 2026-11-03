# Power-split hybrid (Toyota Prius, THS-II)

A power-split hybrid electric vehicle of the Toyota Hybrid System II type (Prius NHW20, 2004)
with its energy management. The engine drives the planet carrier, MG1 the sun gear, and MG2
and the final drive the ring gear. The planetary set is a bond graph: one transformer per shaft
into the 0-junction of the internal mesh force, whose flow balance is the Willis equation.

```
                 carrier (engine)
 engine --damper--> TFc (Zs+Zr) --\
                                   0  mesh force  --> TFs (Zs) --> sun  -- MG1 (speed control)
                                   |-------------> TFr (Zr) --> ring -- MG2 -- final drive 4.113
                                                                         -- half shafts -- wheels -- car
 battery (NiMH 201.6 V) == DC bus == inverter MTF 1 (MG1), inverter MTF 2 (MG2), 12 V auxiliaries
```

## Models

| model | what it shows |
| --- | --- |
| `hybrid-kinematics` | the planetary set alone: a 60 N·m carrier torque step against viscous sun and ring loads. Willis equation, the 30 : 78 torque split and the power balance; a twin built with the stdlib `PlanetaryGear` gives identical speeds |
| `hybrid-ev-mode` | EV launch: MG2 alone (150 N·m) pulls away, MG1 holds the engine at rest (the sun turns backwards at 2.6 times the ring speed) |
| `hybrid-rule-based` | the NEDC with the rule-based energy management |
| `hybrid-ecms` | the NEDC with the ECMS (equivalent consumption minimisation) |

`hybrid-rule-based` and `hybrid-ecms` are the same model with a different `EMS/strategy`
(select card on the dashboard, no recompile).

## The bond graph

* **Planetary set** (subsystem `Planetary`): `TFc` (n = Zs + Zr), `TFs` (n = Zs), `TFr` (n = Zr)
  around the 0-junction `Mesh`. The effort of the 0-junction is the tooth-normalised mesh force F
  (`Planetary/MeshForce`); the sun carries Zs F, the ring Zr F and the carrier (Zs + Zr) F. The
  flow balance is Zs w_s + Zr w_r = (Zs + Zr) w_c. Sun, ring and carrier inertias sit on their
  shaft 1-junctions (sun + MG1 rotor, ring + MG2 rotor); the engine inertia is joined to the
  carrier through the transaxle input damper (C + R). A rigid engine-carrier joint would give
  three rigid inertias on a two-degree-of-freedom set and one of them derivative causality.
* **Engine**: an MSe with torque = throttle × WOT(w) (Lookup1D), plus a second MSe for the
  friction and pumping drag while it turns unfired. The fuel rate is a fuel-rate map (Lookup2D)
  at the engine speed and torque, multiplied by the firing flag.
* **MG1, MG2**: DC-equivalent machines. Each one is an inverter MTF from the DC bus, a stator
  1-junction with the resistance R_s (copper loss) and a small inductance L = R_s × 10 ms, and the
  stdlib `EMConverter` (torque constant k) onto the shaft. The iron loss is an R on the shaft.
  The controller sets the inverter modulus to the voltage that gives the commanded torque
  (feed-forward v = k w + R_s T/k).
* **Driveline and vehicle**: the ring drives the final drive TF (4.113), the half shafts (C + R),
  the wheel 1-junction with the friction brakes (MR) and the tyre (stdlib `Wheel` converter) onto
  the vehicle mass. The road loads are aerodynamic drag (MR with u = sqrt(v² + 0.01)), rolling
  resistance (MSe, c_rr m g tanh(v / 0.05 m/s)) and grade (Se). The transaxle spin loss on the
  ring is an MSe (Coulomb, tanh-smoothed) plus an R (viscous).
* **Battery**: the stdlib `Battery` (Thevenin: OCV table, R0, R1 ‖ C1, SOC as a state) on the
  DC bus with a DC-link capacitor and the 12 V auxiliary load (R).

The smooth (tanh or hyperbolic) Coulomb terms replace the stdlib `RotationalFriction` and
`Friction` blocks. Their Stribeck term `abs(w)` is a kink that the ring speed sits on while the
half-shaft oscillation reverses it at launch, and that the car sits on at every NEDC stop: event
chatter. The `energy_ledger` checks classify the three MSe loss elements as dissipation.

### Custom blocks (`library/`)

Only the controllers are custom blocks; no standard block does their job:

* **`EnergyManager`** (discrete, 10 Hz): the supervisory energy management, rule-based or ECMS.
  It holds an engine state and runs loops over the operating-point candidates, which needs a
  discrete block.
* **`PowerSplitControl`** (continuous): the hybrid control unit. It filters the references,
  computes the engine torque command and the firing flag, runs the MG1 speed PI that holds the
  engine on its set point, fills the wheel torque with MG2 within the MG2, battery-power and
  regeneration limits, blends in the friction brakes, and computes the two inverter moduli.

## Energy management

Both strategies use a SOC target that drops with speed, soc_t = soc_ref − η_kin ½ m v² / E_bat
(η_kin = 0.6): at speed the battery keeps room for the braking energy it will get back (a
velocity-dependent reference in the spirit of Ambühl and Guzzella, 2009).

* **Rule-based** (strategy 0). Requested power P_req = F_dem v + k_soc (soc_t − soc). The engine
  starts when P_req exceeds P_on (9 kW), when the SOC falls below 0.45, or above 70 km/h. It
  stops below 0.55 P_on or when the driver brakes. Running, it delivers max(P_req, P_min) on the
  optimal operating line (the minimum-fuel speed for each power, from the fuel map).
* **ECMS** (strategy 1; Paganelli et al., 2002; Sciarretta et al., 2004). Every 0.1 s it
  evaluates "engine off" and a 16 × 12 grid of operating points (speeds 1000 to 5000 rpm,
  torques 15 to 95 % of full load) and picks the least
  m_eq = m_fuel + s (P_batt + R_bat P_batt² / V²) / LHV with s = s0 (1 − k_p (soc − soc_t) / 0.1).
  P_batt comes from the quasi-static power balance of the planetary set with the MG losses.
  Points beyond the MG1 speed, MG2 torque or battery power limits are skipped. s0 = 2.6 is the
  charge-sustaining value on the NEDC.

Below both strategies, `PowerSplitControl` makes MG1 hold the engine speed, MG2 fill in the wheel
torque, and the friction brakes take what MG2 cannot recover. The regenerative torque fades out
around 6.6 km/h.

## Results (NEDC, hot start, 11.01 km, 1180 s)

| | rule-based | ECMS |
| --- | --- | --- |
| fuel (L/100 km) | 3.46 | 3.47 |
| final SOC (start 0.60) | 0.610 | 0.594 |
| SOC-corrected fuel (L/100 km) ¹ | 3.41 | 3.50 |
| engine on-time (s) | 338 | 360 |
| engine starts | 24 | 11 |
| mean engine efficiency when firing | 36.4 % | 36.2 % |
| mean engine power when firing (kW) | 13.2 | 12.3 |
| braking energy demand at the ring (MJ) | 1.21 | 1.20 |
| regenerative share of the braking energy | 0.986 | 0.986 |

¹ The SOC difference is valued at 30 % (engine to stored electricity): 0.01 SOC ≈ 51 kJ ≈ 4 g
of fuel.

* **Reference**: 4.3 L/100 km NEDC combined for the 2004 Prius (Toyota, EU type approval, with a
  cold start). The model starts hot, has a constant 250 W auxiliary load and no warm-up strategy,
  so 3.5 L/100 km is in line. The check accepts 3.3 to 4.7 L/100 km.
* **Rule-based against ECMS**: within 3 % of each other. The rule-based strategy runs on the same
  optimal operating line that the ECMS candidates come from. The ECMS is instantaneous (no
  look-ahead) and keeps the engine running longer at a lower power with fewer starts. The
  rule-based strategy starts 24 times and ends 1 % SOC higher. Retune s0, P_on and soc_ref on the
  dashboard.
* **Energy**: about 12.2 MJ of fuel gives 4.45 MJ of engine work (36.4 %). The `energy_ledger`
  check closes the port-power balance of the whole bond graph to a relative 1e-17: engine work =
  dissipation (the MG, spin, brake, road and battery losses, plus the auxiliaries) + ΔE_battery +
  Δ(stored kinetic and spring energy).

## Checks (`expected.json`)

`uv run examples/run_checks.py --only hybrid-powersplit` runs 44 checks:

* **kinematics**: the analytic steady state (w_s = 333.3, w_c = 170.8, w_r = 108.3 rad/s, P_c =
  10.25 kW); the Willis invariant (1e-10); the torque split T_sun / T_ring = 30/78; the power
  balance P_carrier = P_sun + P_ring; agreement with the stdlib `PlanetaryGear` twin; the energy
  ledger; no causality warnings.
* **EV launch**: 30 km/h at 6.855 s from a rigid 1-DOF ODE with the same losses (design.py;
  the closed form without losses gives 6.730 s), ±0.05 s; the Willis invariant; the engine held
  at rest (|w_e| < 5 rad/s); w_s / w_r = −Zr/Zs; battery power within the 21 kW rating; the
  energy ledger; no causality warnings.
* **NEDC** (both strategies): speed tracking within the ±2 km/h tolerance of R83; distance
  11.013 km; the Willis invariant over the whole cycle; final SOC 0.60 ± 0.03; the BMS coulomb
  count against the battery's own SOC; fuel 3.3 to 4.7 L/100 km; engine on-time between the
  cycle bounds (37 s above 100 km/h, where MG1 would overspeed with the engine at rest, and
  900 s moving); braking energy demand 1.21 MJ and regenerative share 0.986 from the cycle trace
  (design.py `regen_share`); the energy ledger; no causality warnings.

## Parameters

| parameter | value | source |
| --- | --- | --- |
| vehicle mass | 1310 kg curb + 75 kg driver; wheels 4 × 0.8 kg·m² | Toyota specification; wheels assumed |
| Cd, frontal area | 0.26, 2.2 m² | Toyota specification; area estimated |
| rolling resistance, radius | 0.009, 0.30 m (185/65 R15) | assumed; tyre size from Toyota |
| planetary set | Zs = 30, Zr = 78, final drive 4.113 | ORNL/TM-2006/423, Fig. 2.6 |
| engine 1NZ-FXE | 1.497 l Atkinson, 57 kW at 5000 rpm, 115 N·m at 4200 rpm | ORNL/TM-2006/423, Table 2.1 |
| engine efficiency | Willans line calibrated to a 37 % peak (BSFC 226 g/kWh at 2250 rpm, 92 N·m) | ANL measured 36.4 % on the gen-1 engine (Duoba et al., SAE 2000-01-3096); Toyota quotes about 37 % |
| engine friction | 7 + 1e-3 n + 2e-7 n² N·m (n in rpm) | assumed (FMEP 69 kPa at 1000 rpm, 143 kPa at 5000 rpm) |
| MG2 | 50 kW, 400 N·m, 6000 rpm; peak efficiency 93 % at 2500 rpm, 100 N·m | ORNL/TM-2006/423, Table 2.1 and section 3.3.3 |
| MG1 | 10000 rpm; 70 N·m (assumed); 93 % at 5000 rpm, 30 N·m (assumed) | ORNL/TM-2006/423, section 2.2.3 |
| spin losses | c0 tanh(w/2) + c1 w, c0 = 1.05 N·m, c1 = 0.0016 N·m·s/rad | fit to ORNL Table 3.7 gear losses × 0.8 (warm oil) |
| battery | 168 NiMH cells, 201.6 V, 6.5 A·h, 21 kW discharge | ORNL/TM-2006/423, Table 2.1 |
| battery model | R0 0.30 Ω, R1 0.10 Ω, C1 400 F, OCV 1.10 to 1.45 V/cell, 25 kW charge | assumed (typical NiMH) |
| inertias, damper, half shafts | J_e 0.18, J_mg2 0.0326 (ORNL rotor mass 10.2 kg), …; 1000 / 12000 N·m/rad | mostly assumed |
| auxiliaries | 250 W on the DC bus | assumed |

## Sources and licence

* **ORNL/TM-2006/423**: R. H. Staunton, C. W. Ayers, L. D. Marlino, J. N. Chiasson, T. A. Burress,
  *Evaluation of the 2004 Toyota Prius Hybrid Electric Drive System*, Oak Ridge National
  Laboratory, 2006. A US Government report (public). It covers the gear teeth, the ratings, the
  motor/inverter efficiency and the spin losses.
* **Toyota**: the Prius (NHW20) specifications (curb mass, Cd, tyres) and the EU type-approval
  fuel consumption of 4.3 L/100 km (NEDC combined). These are public figures quoted as facts.
* **Duoba et al., SAE 2000-01-3096** (Argonne National Laboratory testing of the first-generation
  Prius). Quoted for the peak brake efficiency only.
* **UN ECE Regulation No. 83**, Annex 4 (NEDC: ECE-15 urban cycle and EUDC). The cycle is
  generated from its published definition in `design/design.py`.
* **G. Paganelli, S. Delprat, T.-M. Guerra, J. Rimaux, J.-J. Santin**, *Equivalent consumption
  minimization strategy for parallel hybrid powertrains*, IEEE VTC 2002; **A. Sciarretta,
  M. Back, L. Guzzella**, *Optimal control of parallel hybrid electric vehicles*, IEEE TCST 12(3),
  2004; **L. Guzzella, A. Sciarretta**, *Vehicle Propulsion Systems*, Springer; **D. Ambühl,
  L. Guzzella**, *Predictive reference signal generator for hybrid electric vehicles*, IEEE TVT
  58(9), 2009. These are the methods only; no data is taken from them.

No copyrighted data tables are reproduced. The fuel map is a Willans-line model calibrated to
the published peak efficiency, not a transcribed map.

## Assumptions and simplifications

* There is no boost converter: the inverters run from the battery voltage (the real THS-II
  boosts to 500 V). There are no inverter switching losses beyond the MG efficiency model.
* The engine is a quasi-static torque source with a Willans fuel model. There are no cold
  start, warm-up, catalyst heating or idle-speed control. Fuel and spark fade in around 800 rpm
  while MG1 cranks the engine.
* The machines are DC-equivalent: loss = c T² (copper, stator R) + b w² (iron, R). Each is
  calibrated to one efficiency point.
* The battery is a single Thevenin cell with an assumed OCV shape. There is no thermal model.
* There is one wheel and one brake for the whole car: no tyre slip and no load transfer.
* The driver is a PI speed tracker; the NEDC tolerance band is ±2 km/h.
* The EnergyManager uses quasi-static estimates. The ECMS has no look-ahead, and its
  equivalence factor is tuned for the NEDC.

## What to try

* `hybrid-rule-based`: raise the rule-based engine start `P_on_kW`. The engine starts less
  often, the battery works harder, and the SOC swings further.
* `hybrid-ecms`: change `s0`. A lower factor makes battery energy look cheap: s0 = 2.2 ends at
  SOC 0.58 instead of 0.594. A higher factor charges more.
* Switch `EMS/strategy` on the same model and compare the XY plot of the engine operating points.
* `hybrid-ev-mode`: raise `grade_pct` to 10 %. The same 150 N·m launch accelerates about three
  times more slowly.
* `hybrid-kinematics`: change Zs and Zr and check the Willis equation.

## Files

* `design/design.py`: the vehicle, engine, machine, battery and cycle data and every reference
  value (writes `design/design.json`).
* `design/build_model.py`: writes the four models, `bgsim.project.json` and `expected.json`; it
  also writes the ECMS candidate tables into `library/EnergyManager.jl`.
* `design/expected_checks.py`: the acceptance checks with their notes.
* `library/EnergyManager.jl`, `library/PowerSplitControl.jl`: the controllers.
