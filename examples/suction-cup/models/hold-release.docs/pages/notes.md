# Notes and limitations

- **Solver.** All models use `FBDF`: the cup chamber is stiff.
- **Estimates.** The nonlinear bellows parameters (`s_bot`, `k_bot`, `A_fold`, `c_vac`, `c_ext`) are estimates for a 1.5-fold cup.
- **U below zero.** U has a smooth floor at −1. A bellows pushed hard against the box (compression, no pull) reads −1, so the bounce plots dip to −1.
- **Seal model.** The lip is a ring with one gap. A lift on one side opens the gap for the whole circumference.
- **Release.** After the release the tool retracts and the lip leaves the box: `sealed` drops to 0, but `held` stays 1 because the box was put down.
- **Regenerating.** `uv run examples/suction-cup/design/build_model.py` writes all seven models and the scenes. `uv run examples/suction-cup/design/analysis.py --sim` reruns the hand calculation and compares it with the hold and swing runs.
