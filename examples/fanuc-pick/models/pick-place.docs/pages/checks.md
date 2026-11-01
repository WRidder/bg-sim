# Validation and checks

| check | reference | bg-sim | models |
| --- | --- | --- | --- |
| forward kinematics: the URDF joint tree of the 3D scene, driven by `Planner/qr`, against the planner's flange position | closed-form IK/FK of `planner.py`; URDF chain error 3e-16 m (`reference.py`) | at most 3.3e-16 m (tol 1e-6) | all 10 |
| cycle time `Planner/T_cyc` | `planner.reference`, e.g. 1.659034 s (default), 1.577796 s (`pick-place-best`) | equal within 1e-6 | all 10 |
| vacuum at the lift start `Cup1/dp` | seal ODE of `reduced.py`: 55,762 Pa | 55,761 Pa | `pick-place` |
| operating vacuum `Cup1/dp` at rest | ejector curve = lip leak + Darcy flow: 55,826.8 Pa | 55,826.6 Pa | `static-hold` |
| static cup forces `Cup1..5/T` at rest (N) | hand calculation: 2.943, 9.281, 6.112, −3.395, −0.226 | 2.943, 9.274, 6.100, −3.387, −0.213 | `static-hold` |
| most loaded cup at rest `Cup2/U` | hand calculation: 0.650 | 0.658 | `static-hold` |
| holding margin `M_tot` | reduced model: −0.073 / 0.092 / 0.049 / 0.165 | −0.076 / 0.087 / 0.063 / 0.164 | `pick-place` / `loose-sphere` / `loose-cylinder` / `static-hold` |
| holding margin of the optima (≥ M_req − 0.02) | reduced model: 0.502 / 0.506 / 0.301 / 0.311 | 0.504 / 0.507 / 0.298 / 0.301 | the four `*-best` |
| robot limits `Planner/util_max` of the optima (≤ 100 %) | `planner.reference`: 56.5 / 54.9 / 67.7 / 67.7 % | the same | the four `*-best` |
| drop: `Monitor/held_ok` falls to 0 and the carton is 20 mm off | reduced model drops both | both drop | `offset-com`, `too-aggressive` |
| power ledger | Tellegen: the bond ports' powers cancel | residual 3e-16 J (tol 1e-6) | `pick-place` |
| no solver or structure diagnostics | — | none | all 10 |
