# Structure: the bond graph

```
MSe(V) -> 1( R=1 Ohm, I=L=1 mH ) -> GY(k_t=0.1) -> 1( I=J_m=5e-5, R=R_d=1e-4 )
      -> TF(1) * TF(0.1) (10:1) -> 1( I=J1=1e-3 ) -> 0 ---------- 1( C=1/k, R=c ) (the shaft)
                                                      '-> 1( I=J2=2e-3 ) <- MSe(load)
```

| element | node | value |
| --- | --- | --- |
| voltage source | [V](block:V) | `MSe`, effort = firmware voltage |
| armature | [R](block:R), [IL](block:IL) | $R = 1\ \Omega$, $L = 1$ mH on the 1-junction [Elec](block:Elec) |
| motor constant | [GY](block:GY) | $k_t = 0.1$ N·m/A = V·s/rad |
| rotor | [IJm](block:IJm), [Rd](block:Rd) | $J_m = 5\cdot10^{-5}$ kg·m², $R_d = 10^{-4}$ N·m·s/rad on [MotorJ](block:MotorJ) |
| gear | [TFa](block:TFa), [TFb](block:TFb) | $n = 10$: `TF(1)` then `TF(0.1)` (a TF reverses the flow, so the pair is +10:1) |
| wheel 1 | [IW1](block:IW1) | $J_1 = 10^{-3}$ kg·m² on [WheelJ1](block:WheelJ1) |
| shaft | [C](block:C), [D](block:D) | $k = 1.2$ N·m/rad ($C = 1/k$), $c = 10^{-3}$ N·m·s/rad on the 1-junction [Shaft](block:Shaft) |
| wheel 2 | [IW2](block:IW2) | $J_2 = 2\cdot10^{-3}$ kg·m² on [WheelJ2](block:WheelJ2) |
| load | [Load](block:Load), [LoadStep](block:LoadStep) | `MSe`, effort $-0.2$ N·m from 2.2 s (a resisting torque) |

The shaft is a spring and a damper that carry the same flow (the relative speed of the wheels), so they sit on a 1-junction. That junction is connected to the 0-junction [S1](block:S1), whose flows add and whose torque is common to wheel 1, the shaft and wheel 2. [C](block:C)'s state `C/q` is the twist.

The ideal gear welds wheel 1 to the rotor, so the compiler reports W201 (`IW1` and `IJm` in derivative causality) and the run uses a DAE solver. The compliance of the shaft is the only compliance: the rotor and wheel 1 are one rigid body.

## Sensors

- [MotorSpeed](block:MotorSpeed): a flow sensor on the motor junction; [Theta](block:Theta) integrates it to the motor angle; [Encoder](block:Encoder) samples it at 1 ms with $2\pi/4096$ rad (12 bit).
- [LoadSpeed](block:LoadSpeed), [ThetaL](block:ThetaL) and [EncoderL](block:EncoderL): the same for the load wheel, with $2\pi/16384$ rad (14 bit).
- [Current](block:Current): a flow sensor on the electrical junction, recorded only.

The load encoder is a deliberate choice: the controlled variable is the load angle, and with only a motor encoder the load angle and a load torque cannot be told apart for slow changes (see [the controller](page:controller)).
