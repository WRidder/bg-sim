# Results

The short-period mode at the start, from `design/design.py`:

| quantity | value |
| --- | --- |
| natural frequency | 3.44 rad/s |
| damping ratio | 0.128 |
| lift coefficient at alpha 2 deg | 0.1106 |
| load factor at launch, 600 m/s at 3000 m | 0.274 g |

The ring-down in the run is read at the mean condition of the window (500 kPa, 1050 m/s); the fitted mode is 6.28 rad/s and zeta 0.206 against the linear 6.11 rad/s and 0.146. The difference is the thrust and the falling mass, which the linearisation holds fixed.

The motor's ideal vacuum delta-v is 620 m/s (`c ln(m0/mf)`); drag and gravity take most of it back in level flight. The `expected.json` checks the thrust, the burnout mass, the lift, the drag, the atmosphere and the fitted mode.
