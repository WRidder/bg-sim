# Notes

- **Tolerances.** `reltol` 1e-4 / `abstol` 1e-6 gives the same trajectory as 1e-6 / 1e-8 to 2.3 micrometres over the whole mission and halves the run time; the discrete ticks (2 ms) limit the step anyway.
- **Output size.** Every 2 ms discrete tick is recorded as a left/right event pair, so the 18 s run has about 18 000 rows of 1559 signals.
- **Determinism.** The twin model `quadcopter-repeat` stops at 9 s on the same output grid; eight `compare` entries check that signals such as `Imu/gyro[1]` agree with the full run to 1e-12.
- **Reuse (X5.8).** The pieces are separated so the aerial-manipulator example can reuse them: `RotorWrench` (N rotors), `Propeller`, `Esc`, `Battery`, `QuadMixer` (`Minv`, `N`; a hexarotor needs a new `Minv` and `N` = 6), the sensors and `NavFilter`, and the three controller blocks, which only exchange `qd`/`F`, `w_sp` and `tau`. A manipulator reaction wrench can be added as a second `ExternalWrenchSpatial` bond on `Body.p`.
