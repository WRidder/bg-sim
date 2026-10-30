# DC motor with sampled speed control

The plant of the `iconic` model is closed with a 1 ms discrete PI controller (plan 9.1, milestone M2). The 12 V source is replaced by a [VoltageSource](block:V1) driven by a [DiscretePID](block:PID1); the reference is a 100 rad/s step at 0.01 s ([Step1](block:Step1)).

```
Step1 --> Err (u1 - u2) --> PID1 --> V1.u --> motor
  ^                                            |
  +-------- WmSens.y <-- SpeedSensor <---------+
```

![Diagram of the speed-control model|800](assets/158bc2760b65.png)

- **Error node.** [Err](block:Err) is a two-input inline block `y = u1 - u2` (the stdlib `Sum` takes one vector input, which a JSON signal graph cannot assemble from scalars).
- **Sensor.** [WmSens](block:WmSens) is a zero-effort tap on the same wire node as the motor shaft and the damper, so it reads the rotor speed.
- **Supply limit.** The controller output is clamped to $\pm 24$ V; at 24 V the motor alone would settle at 479.6 rad/s, so the drive is voltage-limited, not speed-limited.

Plant parameters are those of the `iconic` model ($R = 2\ \Omega$, $L = 0.5$ mH, $k_t = 0.05$ N·m/A, $J = 10^{-5}$ kg·m², damper $10^{-6}$ N·m·s/rad); the run lasts 0.3 s with 3001 points and `reltol` 1e-8.
