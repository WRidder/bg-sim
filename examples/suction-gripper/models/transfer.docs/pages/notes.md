# Notes and limitations

- **Solver.** All models set `FBDF`. The cup chambers are stiff, with a time constant of a few milliseconds against a mechanics timescale of seconds. With `auto` the run picks Tsit5, which is about 5 times slower and stops with `MaxIters` in the porous and edge-leak cases.
- **Seal model.** The holding force is a capacity ($A_{eff}\Delta p$), not a pressure force on a moving membrane. The lip is a ring with a single gap: a lift on one side opens the gap for the whole circumference. The cup does not model a progressive peel of the lip.
- **Air.** The model is isothermal with free-air flows and one lumped chamber per cup. There is no line dynamics beyond the orifice. The Darcy law is linear in the vacuum.
- **Release.** At release the generator vents through `G_rel`. The cups do not model blow-off.
- **Regenerating.** `uv run examples/suction-gripper/design/build_model.py` writes all eight models and the scene. `uv run examples/suction-gripper/design/design.py --procs 7` reruns the analysis, which takes about 25 minutes on 7 Julia processes.
