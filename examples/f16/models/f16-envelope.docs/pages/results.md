# Results

![alpha, load factor and speed|900](assets/a8418a3f6b88.png)

| quantity | Protected | Unprotected |
| --- | --- | --- |
| peak load factor | 8.84 g | 10.13 g |
| peak alpha | 17.3 deg | 81.5 deg (departure) |

At high speed the g limiter holds the load factor near 8.8 g while the stick asks for 11. As the loop bleeds speed, the alpha ceiling takes over and holds alpha near 17 deg (it settles below 25 because the ceiling $3(25 - \alpha)$ has to leave the pitch rate of the loop). Without the limiter the aircraft over-stresses, and at the slow top of the loop the pitch-rate demand $g_0/V_t \cdot 10$ grows until alpha runs away beyond the 45 deg end of the tables: from there on the motion is qualitative only. bg-sim matches the scipy reference within 0.03 deg alpha and 0.005 g.
