# Results

![Block velocity (cubic rig, textbook, full Stribeck curve), position and slip, first 10 s|900](assets/106c05cb46d4.png)

![Phase portrait of the cubic rig in Van der Pol units, against the textbook equation|560](assets/2feaa72298a9.png)

![The friction force along the run against the slip: the cubic fit and the full curve|560](assets/7222fb8ced49.png)

| quantity | cubic fit | full Stribeck curve |
| --- | --- | --- |
| period | 0.638068 s ($= T(0.5)/\omega_0$) | 0.638438 s (+0.058 %) |
| velocity amplitude | 44.135 mm/s (2.00249 V) | 44.959 mm/s (+1.87 %) |
| smallest slip | 26.58 mm/s | 25.75 mm/s |
| position swing | 184.74 ... 193.75 mm | 184.40 ... 193.67 mm |
| energy fed and taken back per cycle | 0.4309 mJ each | |

The fit is close because the swing stays within $\pm 0.62\,v_b$ of the inflection point. The fifth-order term of the Gaussian makes the real curve fall a little further, so the full-curve oscillation is 1.9 % larger.

## Checks (`expected.json`)

- the cubic rig's scaled velocity and acceleration against [Ref](block:Ref): maximum difference 1.5e-11 (the check allows 1e-6);
- both periods and amplitudes against scipy (SI units, the same friction laws), rtol 1e-6;
- the slip stays positive in both rigs;
- the energy invariant $E + \int -(F - F_0)\dot x\,dt$ drifts by 4.0e-11 of the energy scale (the check allows 1e-7);
- energy fed and taken back per cycle, 0.43090 mJ each;
- the 3D bindings match the scene.
