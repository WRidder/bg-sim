# Results

![Rod position, chamber pressures and spool command|900](assets/1fea9ef2939d.png)

## Measured numbers (README, `expected.json`)

| quantity | value |
| --- | --- |
| rod position at 0.3 / 0.5 s | 0.06945 / 0.09161 m |
| rod position at 0.9 s | 0.09982 m |
| rod position at 1.0 s | 0.10016 m (plan: 0.1 +- 0.002 m) |
| rod position at 1.5 s (peak 0.100525 m) | 0.10053 m |
| chamber A pressure, min / max | 6.13 / 92.58 bar |
| chamber B pressure, min / max | 22.89 / 67.33 bar |
| spool, min / peak | -4.28e-5 / +1.0 (saturated on the step) |
| piston speed, peak | 0.481 m/s |
| pump flow, peak | 9.22e-4 m³/s |
| run diagnostics | W202 only |

## What the 16 checks verify

- position: [XS/y](signal:XS/y) at 0.3 s (0.0694475, tolerance 0.002), at 1.0 s and 1.5 s (0.1 within 0.002 m);
- pressures: [PSensA/y](signal:PSensA/y) and [PSensB/y](signal:PSensB/y) at most 100.5 bar; the monitors [pAmin/y](signal:pAmin/y) and [pBmin/y](signal:pBmin/y) ($\min(p, 0)$) stay below 1 Pa, so both chambers stay at or above 0 bar;
- spool: $\max|s| = 1.0$ (the clamp is reached) and $|s| \le 1$ everywhere;
- flow sanity: piston speed at most 0.6 m/s, pump flow [PS/a.f](signal:PS/a.f) at most 1e-3 m³/s, orifice flows [Valve/PA/Q](signal:Valve/PA/Q) and [Valve/BT/Q](signal:Valve/BT/Q) at most 1e-3 m³/s;
- the two pressure taps agree with the chamber states [Cyl/pA](signal:Cyl/pA), [Cyl/pB](signal:Cyl/pB) to 1e-6 Pa;
- no E901, E101, E102, E103, E106 or W206.

The response is monotone: the valve saturates until about 0.166 s, then closes as the rod approaches the reference.
