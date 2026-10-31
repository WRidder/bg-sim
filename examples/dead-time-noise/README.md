# dead-time-noise

The J-EX9 example: a process with dead time under discrete PI control, with seeded
measurement noise.

- **Process.** `Plant` is a first-order lag (K = 1, tau = 1 s). Its input passes a 0.2 s
  `TransportDelay` (`DeadTime`). The delay stores its input every 1 ms in a ring buffer and
  interpolates linearly between the samples.
- **Controller.** `PI` is a 10 ms `DiscretePID` (Kp = 2, Ti = 1 s, Td = 0, output limits
  +-5). Its command reaches the process through a 2-sample `IntegerDelay` (`Comm`), a
  communication delay of 20 ms.
- **Measurement.** `Meas` is the process value plus `Noise`: seeded normal noise with
  std 0.02 and seed 42 on a 1 ms clock. The noise is counter-based (SplitMix64 and AS 241,
  spec "Seeded noise and delay"), so every run, and the exported FMU, draws the same
  sequence bit for bit.

The setpoint steps from 0 to 1 at 0.5 s. The process cannot move before
0.5 + 0.02 + 0.2 = 0.72 s, and then settles at the setpoint.

`PV` (an `ExportOutput`) publishes the process value when the model is exported. The
`expected.json` checks the dead time, the settled value, the noise level and one pinned
noise sample.
