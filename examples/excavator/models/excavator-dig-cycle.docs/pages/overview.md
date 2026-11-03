# A dig cycle

**Scenario.** A scripted operator ([BoomStick](block:BoomStick), [ArmStick](block:ArmStick),
[BucketStick](block:BucketStick), linear ramps of 0.25 s) runs one cycle in 16.5 s. The spool commands
(positive extends the cylinder):

| phase | time [s] | boom | arm | bucket |
| --- | --- | --- | --- | --- |
| penetrate | 0.5 – 2.0 | −0.15 | 0 | 0.25 |
| drag | 2.0 – 5.0 | −0.03 | 0.5 | 0.22 |
| curl | 5.0 – 6.5 | 0.13 | 0.33 | 0.38 |
| lift | 6.5 – 9.5 | 0.9 | −0.06 | 0 |
| arm out | 9.5 – 11.0 | 0.15 | −0.65 | 0 |
| dump | 11.0 – 12.8 | 0 | 0 | −0.85 |
| return | 12.8 – 15.3 | −0.17 | 0.02 | 0.38 |

The global `u_scale` scales all three sticks ([BoomCmd](block:BoomCmd) and the others).

![The bucket tip path: into the soil, drag, curl, up and out, back to the start|600](assets/8cee246bf1d7.png)

![Joysticks, soil, pressures, LS margin and power|900](assets/9e701628f801.png)

**Expected outcome** (checked by `expected.json`):

| quantity | bond graph | check |
| --- | --- | --- |
| LS margin | 22.6 – 27.0 bar | 20 – 32 bar |
| main relief flow | < 2·10⁻⁹ m³/s | closed |
| bucket fill after the curl / after the dump | 0.75 / 0.004 | > 0.6 / < 0.05 |
| deepest cut, peak cutting force | 0.43 m, 22.2 kN | < 0.6 m |
| engine energy / cylinder work ratio | 0.57 MJ / 0.27 | < 0.7 MJ |
| port-power ledger | closes | |

The margin dips below its setting when a load pressure steps up and the LS line follows through its shuttle: the
largest dip (22.6 bar) is at 9.7 s, when the arm swings out with the full bucket and the boom cap pressure peaks at
290 bar. The margin never runs out, so every section gets its flow.

![The front at 9 s: lifting the full bucket|600](assets/6d2f1bf990c4.png)

![The model canvas|900](assets/f9174f3051eb.png)

**Blocks.** [Soil](block:Soil) (`SoilCutting2D`) at the bucket body; the three sections with their
compensators ([BoomComp](block:BoomComp), [ArmComp](block:ArmComp), [BucketComp](block:BucketComp)), spools
([BoomValve](block:BoomValve)…), LS edges ([BoomLSEdge](block:BoomLSEdge)…) and shuttles
([BoomShuttle](block:BoomShuttle)…); the supply with [Pump](block:Pump), [Relief](block:Relief) and
[Bleed](block:Bleed).

**Try:** set the soil cohesion to 50 kPa (stiff clay): the peak cutting force doubles to 44 kN, the cut stays
shallower (0.33 m) and the bucket fills only to 0.64. Raise the joystick scale to 1.2: the operator digs deeper
(0.52 m), the bucket fills to 0.83 and the cycle costs 0.72 MJ. Compare the engine energy with [excavator-no-ls](model:excavator-no-ls).
