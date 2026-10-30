# Notes and limitations

- **W202 is expected and allowed.** The message "algebraic loop through AT, BT, FST" (and analogous ones at the other rails) is the causality pass's view of the series `FlowSensor` that exposes a rail as a subsystem power port. The rail pressure is in fact fixed by the tank through the sensor, and the DAE solves without an iteration failure.
- **Deviations from a literal plan 9.6 transcription.** The sub-spool area law uses the smooth $\max(u, 0) \approx \tfrac12\left(u + \sqrt{u^2 + 10^{-12}}\right)$ so the closed-centre spool does not sit on a kink (difference below 1e-6 in spool, 5e-12 m² in area). `Err` and `VDrive` are inline glue blocks, not plant physics. The initial pressures and the preloaded integrator are not specified by the plan.
- The closed-loop bandwidth is limited by the hydraulic resonance and the 1 ms sample: the valve is strongly oversized for the load.
