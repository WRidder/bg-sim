# Drivetrain, pure bond graph

The same plant as the iconic `drivetrain` model, built only from bond graph elements:

```
Step -> MSe -> 1-junction( R=1, I_L=1e-3 ) -> GY(0.1)
     -> 1-junction( I_J=5e-5, R_d=1e-4 ) -> TF(1) -> TF(0.1) -> J3( 1-junction, I_1=1e-3 )
     -> 0-junction S0 -- J4( 1-junction, I_2=2e-3, MSe(load) )
          |
       T0( 1-junction, C=0.2, R=0.02 )   # the rod: spring and damper in parallel
```

![Diagram of the bond graph drivetrain|900](assets/7f9866c5080a.png)

| block | element | value |
| --- | --- | --- |
| [MSe1](block:MSe1) | modulated effort source fed by `Step1` | 0 to 12 V at 0.01 s |
| [R1](block:R1), [IL](block:IL) | winding resistance, inductance | 1 Ω, 1e-3 H |
| [GY1](block:GY1) | gyrator (torque constant) | 0.1 |
| [IJm](block:IJm), [Rd](block:Rd) | motor rotor inertia and damping | 5e-5, 1e-4 |
| [TF1](block:TF1), [TF2](block:TF2) | transformers 1:1 and 10:1 | `n` = 1, 0.1 |
| [IW1](block:IW1), [IW2](block:IW2) | wheel inertias | 1e-3, 2e-3 |
| [Crod](block:Crod), [Rrod](block:Rrod) | rod compliance $c = 1/k$ and damper | 0.2, 0.02 |
| [MSe2](block:MSe2) | load effort source fed by `LoadStep` | 0 to -0.5 N·m at 1 s |

## Why two transformers

A transformer reverses the flow ($f_2 = -n f_1$), so a single 10:1 `TF` would make the wheels turn against the motor. The 1:1 stage reverses first, the 0.1 stage reverses again and gives the 10:1 reduction, the same ratio and sign as the iconic `IdealGear`.

## The rod

The rod is a `C` (compliance $c = 1/k = 0.2$) and an `R` (0.02) on a 1-junction, fed by the 0-junction [S0](block:S0) that forms the relative speed between the two inertia junctions [J3](block:J3) and [J4](block:J4). That is the bond graph form of a torsion spring with a parallel damper; the twist is the state `Crod/q`. The load source has effort -0.5 N·m on its port; with the power-positive-into-each-port convention that is the +0.5 N·m load seen by the wheel.

## Causality: W201

The manifest reports **W201** on `IW1`: the wheel-side inertia is in derivative causality because the two transformers make the gear rigid. Run and values are unaffected; it is the honest bond graph causality of a rigid gear.

## Results

Plot [IJm/p.f](signal:IJm/p.f), [IW1/p.f](signal:IW1/p.f), [IW2/p.f](signal:IW2/p.f) and [Crod/q](signal:Crod/q). At $t = 2$ s (relative 1e-3): `IJm/p.f` 113.86311499566987, `IW1/p.f` 11.386311499566988, `IW2/p.f` 11.388161502151661 and `Crod/q` 0.09996294068301954; the ratio `IJm/p.f` to `IW1/p.f` is 10; the largest `Crod/q` in $[0.01, 1]$ s is 0.18648149316411403. The motor speed agrees with `Motor1/shaft.f` of the iconic model to 5e-5 rad/s from $t = 0.01$ s.

## 3D view

The bond graph model has speeds only, so the three discs of the scene are coloured by speed (`IJm/p.f`, `IW1/p.f`, `IW2/p.f`).

![3D view at t = 0.3 s|500](assets/1bf286c54fa2.png)
