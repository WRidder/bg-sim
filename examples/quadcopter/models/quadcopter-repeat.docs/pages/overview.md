# Determinism twin

The same document as `quadcopter`, stopped at $t = 9$ s on the same output grid (901 points; `reltol` 1e-4, `abstol` 1e-6). It exists so that the example runner can check that two runs of the same model give identical results: the check compares [Truth/z](signal:Truth/z) at 4.9 s with 1.0859 m (tolerance 1e-3) and no E901, E106, E007, W201, W202, W205 or W206 appears. The eight `compare` entries of `expected.json` check that signals of the full 18 s run (for example `Imu/gyro[1]`) agree with this twin to 1e-12 from $t = 0$. The model and its physics are documented in the `quadcopter` model.

![Mission position over the first 9 s|900](assets/498ae73fb365.png)
