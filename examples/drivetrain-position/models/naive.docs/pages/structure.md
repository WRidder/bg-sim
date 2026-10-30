# Structure: the bond graph

The plant is the same pure bond graph as in `drivetrain-position`:

```
MSe(V) -> 1( R, L ) -> GY(0.1) -> 1( J_m, R_d ) -> TF(1) * TF(0.1) -> 1( J1 ) -> 0 -- 1( C=1/1.2, R=0.001 )
                                                                              '-> 1( J2 ) <- MSe(load)
```

[V](block:V) is the voltage `MSe`, [Elec](block:Elec) and [MotorJ](block:MotorJ) are the electrical and the motor 1-junctions, the shaft is the spring [C](block:C) and the damper [D](block:D) on the 1-junction [Shaft](block:Shaft), which hangs on the 0-junction [S1](block:S1) between the wheels [WheelJ1](block:WheelJ1) and [WheelJ2](block:WheelJ2), and [Load](block:Load) is the load torque `MSe` driven by [LoadStep](block:LoadStep) (effort $-0.2$ N·m at 2.2 s).

[PID](block:PID) is a signal-domain block that writes the voltage; the controller is a 1 kHz digital PID (`library/PositionPID.jl`) fed by the motor angle [Theta](block:Theta). It does not use any load-side sensor.
