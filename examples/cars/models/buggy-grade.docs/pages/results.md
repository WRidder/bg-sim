# Results

![Accelerator, motor torques and tyre loads|900](assets/c726b7acc3a6.png)

The reference (`design/reference.py`) solves the climb's equilibrium: grade resistance, rolling resistance and drag against the four tyre forces, the slips of the front and rear axles, and the load transfer to the rear on the slope.

| quantity | bg-sim | reference |
| --- | --- | --- |
| accelerator | 0.3238 | 0.3237 |
| motor torque (each) | 48.56 N m | 48.56 N m |
| front / rear tyre load | 1642 / 2679 N | 1649 / 2672 N |
| battery current | 30.84 A | 30.82 A |
