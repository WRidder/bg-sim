# Results and checks

![Joint angles and flange position|900](assets/f5c78b5d9b98.png)

| quantity | value |
| --- | --- |
| gravity torque, design Newton-Euler vs MuJoCo, 1000 random poses | 5e-14 N·m |
| mass matrix, design vs MuJoCo, 200 random poses | 4e-15 |
| joint angles vs MuJoCo at 0.1 s | under 8.4e-6 rad |
| joint angles vs MuJoCo at 0.25 s | under 1.3e-4 rad |
| joint angles vs MuJoCo at 0.5 s | under 4e-3 rad |
| flange vs MuJoCo at 0.25 s | 4e-5 m |

The difference grows quickly: the held directions are compliant ($k = 10^7$, so the joints sag by about $10^{-6}$ under the reaction loads) and the fall from the ready pose is chaotic, so the small difference grows from 8e-6 rad at 0.1 s to 4e-3 rad at 0.5 s. MuJoCo integrates a rigid chain. The checks (`expected.json`, 33 for this model) compare the angles at 0.1, 0.25 and 0.5 s and the flange at 0.25 s, each within 5x the measured difference.
