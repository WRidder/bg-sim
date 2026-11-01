# Validation and checks

| check | reference | bg-sim | models |
| --- | --- | --- | --- |
| forward kinematics: the URDF joint tree of the 3D scene, driven by `Planner/qr`, against the planner's flange position | closed-form IK/FK of `planner.py`; URDF chain error 3e-16 m (`reference.py`) | at most 2.8e-16 m (tol 1e-6) | all 18 |
| cycle time `Planner/T_cyc` | `planner.reference`, e.g. 1.659034 s (default), 1.612353 s (`pick-place-best`), 1.3937 s (`pick-place-opt`) | equal within 1e-6 | all 18 |
| vacuum at the lift start `Cup1/dp` | seal ODE of `reduced.py`: 55,762 Pa | 55,761 Pa | `pick-place` |
| operating vacuum `Cup1/dp` at rest | ejector curve = lip leak + Darcy flow: 55,826.8 Pa | 55,826.5 Pa | `static-hold` |
| static cup forces `Cup1..5/T` at rest (N) | hand calculation with the bellows taken at the hang point: 2.943, 7.571, 5.257, −1.685, 0.629 | 2.942, 7.554, 5.251, −1.670, 0.633 | `static-hold` |
| most loaded cup at rest `Cup2/U` | hand calculation: 0.658 | 0.666 | `static-hold` |
| holding margin `M_tot` | reduced model: −0.053 / −0.200 / −0.108 / 0.145 | −0.054 / −0.207 / −0.067 / 0.146 | `pick-place` / `loose-sphere` / `loose-cylinder` / `static-hold` |
| holding margin of the optima (≥ M_req − 0.02, tol 0.03 solid, 0.05 loose) | reduced model: 0.503 / 0.503 / 0.301 / 0.310 (`*-best`), 0.500 / 0.501 / 0.301 / 0.302 (`*-tilt-best`), 0.500 / 0.501 / 0.301 / 0.340 (`*-opt`) | 0.498 / 0.504 / 0.320 / 0.313, 0.500 / 0.500 / 0.307 / 0.312, 0.500 / 0.500 / 0.307 / 0.334 | the twelve optima |
| robot limits `Planner/util_max` of the optima (≤ 100 %) | `planner.reference`: 56.5 / 54.9 / 67.7 / 66.7 % (`*-best`), 58.0 / 54.9 / 57.2 / 80.0 % (`*-tilt-best`), 94.3 / 94.1 / 99.8 / 100.0 % (`*-opt`) | the same | the twelve optima |
| tool axis against the specific force `Planner/tilt_err` while carried | the planned angle + 10 % + 0.5° | 24.4 / 25.1 / 10.3 / 28.9° (`*-tilt-best`), 29.5 / 30.6 / 52.8 / 38.3° (`*-opt`) | the eight tilt models |
| drop: `Monitor/held_ok` falls to 0 and the carton is 20 mm off | reduced model drops both | both drop | `offset-com`, `too-aggressive` |
| power ledger | Tellegen: the bond ports' powers cancel | residual 3e-16 J (tol 1e-6) | `pick-place` |
| no solver or structure diagnostics | — | none | all 18 |

All 241 checks pass (`run_checks.py --only fanuc-pick`, 800 s). The tilt angle check only pins the planner to its own plan: the optima tilt the tool partially (gain 0.05 to 0.5), so the tool axis stays 10 to 53° off the specific force in the hardest part of the carry.
