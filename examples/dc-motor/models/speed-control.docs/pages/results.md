# Results

![Speed, voltage command and winding current|900](assets/ff18960edd42.png)

From the README and `expected.json` (all verified by `uv run examples/run_checks.py`):

- the command is clamped to exactly 24.000 V for the first sample of the step (`max_abs` of [PID1/y](signal:PID1/y) = 24, abs 1e-6, and `max_abs_le` 24);
- the measured speed [WmSens/y](signal:WmSens/y) is 100 +- 1 rad/s at $t = 0.1$ s and 100 +- 0.05 at $t = 0.15$ s (measured 99.996 and 100.000), with no overshoot (peak 100.000 rad/s, abs 0.05);
- the winding current [Motor1/i](signal:Motor1/i) peaks at 11.03 A on the step (24 V / 2 Ω minus the back-EMF building up), stays below the 12 A bound and settles at the 2.0 mA load current;
- no diagnostics E901, E101, E102, E103, E106 or W206.

Other numbers quoted in the README: 91.9 rad/s at 0.015 s and 99.14 rad/s at 0.04 s.
