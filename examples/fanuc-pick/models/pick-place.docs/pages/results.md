# Optimisation and results

`design/optimize.py` searches each load case and family for the shortest cycle time that satisfies three constraints:

- the holding margin `M_tot ≥ M_req`, with no drop, in the reduced model;
- every robot limit at 100 % or below (`planner.reference`);
- the carton bottom at least 20 mm above the support, except within 50 mm (horizontally) of the pick and the place.

**Decision variables.** A speed scale `s` and the shape of the trajectory:
- the acceleration-to-speed ratio `rho`;
- the jerk share `lam`;
- the lift height `H_lift`;
- the blend distance `r_b` (families 3 and 4);
- the vacuum wait `T_seal`.

For joint moves `kv = s` and `ka = rho s`. For Cartesian moves the speeds are `s` times 2.5 m/s and 6 rad/s, and the accelerations and jerks are `rho s` times 20 m/s², 40 rad/s², 400 m/s³ and 800 rad/s³.

**Search.** For one shape, T_cyc falls as `s` grows, and so does the margin. A bisection therefore finds the fastest feasible `s`, first on the robot limits (the planner alone) and then on the margin. The shapes are searched on a grid of two values per variable, followed by three passes of a coordinate search.

**The reduced model.** `design/reduced.py` uses the bg-sim laws of `SuctionCup`, `ContactPoint` and the content walls. It holds the rods rigid at their extended stop and uses the same planner output. Compiled with numba, a run takes about 0.5 s (6 s with the loose ball).

| Load case | Default (family 3) | Family 1 joint PTP | Family 2 Cartesian | Family 3 Cartesian blended | Family 4 joint blended | Best |
| --- | --- | --- | --- | --- | --- | --- |
| Carton 1.5 kg, centred CoM | 1.659 s, M -0.05 | 1.976 s (M 0.50, robot 57 %) | 2.044 s (M 0.50, robot 68 %) | 1.625 s (M 0.50, robot 66 %) | 1.612 s (M 0.50, robot 57 %) | **1.612 s** (family 4) |
| Carton 1.5 kg, CoM offset (60, 30) mm, gripped over the CoM | 1.683 s, M -0.04 | 1.947 s (M 0.50, robot 55 %) | 2.073 s (M 0.50, robot 66 %) | 1.631 s (M 0.50, robot 66 %) | 1.626 s (M 0.50, robot 55 %) | **1.626 s** (family 4) |
| Carton 1.5 kg, CoM offset (60, 30) mm, gripped at the box centre | 1.659 s, drop | infeasible | infeasible | infeasible | infeasible | none: margin 0.16 at 5 % speed (needs 0.5) |
| Carton 0.6 kg + loose ball 0.5 kg | 1.659 s, M -0.20 | 2.106 s (M 0.30, robot 57 %) | 1.955 s (M 0.30, robot 68 %) | 1.506 s (M 0.30, robot 68 %) | 1.626 s (M 0.30, robot 57 %) | **1.506 s** (family 3) |
| Carton 0.6 kg + loose bottle 0.5 kg | 1.659 s, M -0.11 | 1.901 s (M 0.30, robot 57 %) | 1.862 s (M 0.33, robot 68 %) | 1.492 s (M 0.31, robot 67 %) | 1.502 s (M 0.30, robot 57 %) | **1.492 s** (family 3) |

What the optimiser finds:
- **The gripper sets the cycle time, not the robot.** Every optimum uses only 55–68 % of the
  LR-10iA/10 limits. Going faster is possible for the arm (`too-aggressive`: 83 % of the limits) but not
  for the cups.
- **The default trajectory is not safe.** Family 3 at its default limits takes 1.659 s, but its margin
  is −0.05: the most loaded cup goes past its capacity during the transfer. The carton just stays on
  (bg-sim and the reduced model agree). The optimum, family 4 (joint blended), takes 1.612 s with a margin
  of 0.50: 3 % faster and safe.
- **Blending is what pays.** The families that stop at the corners take 1.98 s (joint PTP) and 2.04 s
  (Cartesian). Blending cuts 0.36–0.43 s. For the solid carton the joint blend is fastest (1.612 s against
  1.625 s for the Cartesian blend). For the loose contents the Cartesian blend is fastest (by 0.01–0.12 s).
- **No vacuum wait.** Every optimum has `T_seal` = 0: the vacuum is ready within the time the
  cylinders and the approach take. The Cartesian optima lift 30–50 mm; the joint-blended optima lift
  50–70 mm with an 80 mm blend, so the transfer starts while the carton still rises.
- **Grip over the centre of mass.** With the CoM 60/30 mm off centre, gripping over the CoM costs only
  1 % (1.626 s). Gripping at the box centre is infeasible at any speed: at 5 % speed the margin is 0.16.
- **Loose contents.** The 1.1 kg load with M_req 0.3 can go a little faster (1.51 s with the ball, 1.49 s
  with the bottle). The content's impacts on the walls set the margin.
- **The nonlinear bellows cost 2–10 %.** With the linear cups of the first version the optima were
  1.578 / 1.597 / 1.392 / 1.359 s. The bellows laws (vacuum lift stroke, vacuum- and stroke-dependent
  side stiffness) change how the carton swings on the cups, and the peaks of the most loaded cup rise.
  The loose contents lose most (8–10 %): the default trajectory goes from M +0.09 / +0.05 to −0.20 / −0.11.

The free optimisation beyond the four families is on the next page.
