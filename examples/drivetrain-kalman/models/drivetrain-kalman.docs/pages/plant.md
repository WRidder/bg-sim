# Plant

```
MSe(V) -> 1-junction( R=1 Ohm, L=1 mH ) -> GY(k=0.1) -> 1-junction( J_m=5e-5, R_d=1e-4 )
      -> TF(1) * TF(0.1) (10:1) -> WheelJ1( I=1e-3 ) -> S1(0) -+- Rod1(1): C=1/150, R=0.02
                                                              '- MidJ1( I=6.7e-5 ) -> S2(0) ...
      ... -> S3(0) -> WheelJ2( I=2e-3 ) -> Load( MSe, -0.5 N m at 1 s )
```

| quantity | value |
| --- | --- |
| motor | $R = 1\ \Omega$, $L = 1$ mH, $k_t = 0.1$ N·m/A, $J_m = 5\cdot10^{-5}$ kg·m², $R_d = 10^{-4}$ N·m·s/rad |
| gearbox | $n = 10$: `TFa` ($n = 1$) then `TFb` ($n = 0.1$); a TF reverses the flow, so the pair gives +10:1 |
| wheels | $J_1 = 10^{-3}$, $J_2 = 2\cdot10^{-3}$ kg·m² |
| rod | three segments, each $C = 1/150$ (= 0.00667) and $R = 0.02$ N·m·s/rad, with two intermediate inertias $6.7\cdot10^{-5}$ kg·m² (`IM1`, `IM2`); three 150 N·m/rad springs in series give 50 N·m/rad |
| load | -0.5 N·m effort source at $t = 1$ s (a +0.5 N·m resisting torque) |
| run | 2 s, 4001 points, `solver` auto (the ideal gear makes IW1 a dependent store, so the problem is a DAE), `reltol` 1e-8 |

The rod is the real three-segment rod, not a lumped equivalent: each segment is a 0-junction (the relative speed) with a 1-junction carrying the C and R in parallel, chained through the two intermediate inertias. The equations are those of the `drivetrain` example,

$$L\,\dot i = V - R\,i - k_t\,\omega_m, \qquad J_m\,\dot\omega_m = k_t\,i - R_d\,\omega_m - T_g,$$

with the rod modelled as three torsion springs $k_i = 150$ N·m/rad and dampers $c_i = 0.02$ N·m·s/rad in series.

## Sensors

The controller sees **one** measurement, the motor angle:

- [MotorSpeed](block:MotorSpeed): a `FlowSensor` on the motor junction;
- [Theta](block:Theta): a kinematic integrator of that speed (the D28 sensor exception);
- [Encoder](block:Encoder): a `Quantizer` at 1 ms with resolution $2\pi/4096 = 0.0015340$ rad (12 bit);
- [Current](block:Current): a `FlowSensor` on the electrical junction (recorded, not used by the controller).

There is no load-side sensor: $\omega_L$ is reconstructed by the Kalman filter.
