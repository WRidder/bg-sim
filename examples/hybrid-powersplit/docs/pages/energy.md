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

![Rule-based: speed tracking, engine power and SOC on the NEDC|1000](assets/2eb9303aba88.png)

![ECMS: engine power, SOC and the SOC-corrected equivalence factor|1000](assets/9cf5a3c62b4f.png)

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
| ![Rule-based engine operating points|480](assets/028eac639d2c.png) | ![ECMS engine operating points|480](assets/97bbf6d42a07.png) |
