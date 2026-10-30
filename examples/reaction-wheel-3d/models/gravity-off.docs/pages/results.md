# Results and checks

![World angular momentum of the body, wheel speeds and realised body torque|900](assets/e20775042068.png)

## Measured (README, real worker)

| quantity | gravity-off |
| --- | --- |
| $\max\lvert H - H_0\rvert / \max\lvert H\rvert$ per axis | 3.1e-14 / 7.1e-14 / 3.2e-14 ($H_0 = (0.0598, -0.03787, 0.02867)$ kg·m²/s) |
| the body alone | $H_z$ goes 0.020 to 0.0516 (the wheels carry the difference); body rate $\lvert\omega_z\rvert$ up to 1.195 rad/s |
| wheel speeds at 4 s (relative) | (23.58, -4.19, 23.31, 11.10) rad/s; peak 25.0 rad/s |
| motor torque (max over the four wheels) | 0.0481 N·m (limit 0.06) |
| null-space tap | `Tap/nsp` = 0.01 N·m exactly ($\max\lvert nsp - \lambda\rvert = 8.7\cdot10^{-18}$); `Tap/resid` 1.3e-18 |
| realised body torque | `Tap/Tb*` = `Alloc/Tb*` to 2.1e-17 N·m; against the continuous command within the zero-order-hold error $A\omega T_s$ (at most 6.3e-5 N·m, limit 1e-4) |
| quaternion norm drift | 2.3e-14 |
| pivot deflection | 1.5e-10 m |
| states | 79 by count (pivot 7, body momentum 6, per wheel 14, 10 gravity-impulse integrals) |

**Momentum tolerance.** The checks use `tol` = 1e-9 of the invariant's own scale. The compliant pivot is the only place the momentum balance can leak and its error scales as $1/k_t$: measured 7e-14 relative at $k_t = 10^9$ N/m and 3.5e-9 at a soft $k_t = 10^6$ N/m (scratch run), so the checks would fail for a pivot softer than about $10^7$ N/m.

## Checks (`expected.json`)

Initial quaternion and body momentum; the three components of the world angular momentum are invariant; the body alone exchanges momentum and tumbles ([MeasBody/H[3]](signal:MeasBody/H[3]) and `Pivot/omega[3]` peaks); wheel speeds below 30 rad/s and their 4 s values; the null-space tap; the realised body torque equals the firmware allocation and follows the command within the hold error; motor torque below 0.06 N·m; no W201, E101, E102, E103, E106, E007 or W206.
