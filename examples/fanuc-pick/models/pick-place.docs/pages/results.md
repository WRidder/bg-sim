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
| Carton 1.5 kg, centred CoM | 1.659 s, M -0.07 | 1.950 s (M 0.50, robot 57 %) | 2.071 s (M 0.50, robot 68 %) | 1.635 s (M 0.50, robot 68 %) | 1.578 s (M 0.50, robot 57 %) | **1.578 s** (family 4) |
| Carton 1.5 kg, CoM offset (60, 30) mm, gripped over the CoM | 1.683 s, M -0.08 | 1.956 s (M 0.51, robot 55 %) | 2.097 s (M 0.50, robot 66 %) | 1.644 s (M 0.50, robot 66 %) | 1.597 s (M 0.51, robot 55 %) | **1.597 s** (family 4) |
| Carton 1.5 kg, CoM offset (60, 30) mm, gripped at the box centre | 1.659 s, M -4.05 (drop) | infeasible | infeasible | infeasible | infeasible | none: margin 0.19 at 5 % speed (needs 0.5) |
| Carton 0.6 kg + loose ball 0.5 kg | 1.659 s, M +0.09 | 1.955 s (M 0.33, robot 57 %) | 1.751 s (M 0.30, robot 68 %) | 1.392 s (M 0.30, robot 68 %) | 1.482 s (M 0.31, robot 57 %) | **1.392 s** (family 3) |
| Carton 0.6 kg + loose bottle 0.5 kg | 1.659 s, M +0.05 | 1.799 s (M 0.33, robot 57 %) | 1.721 s (M 0.30, robot 68 %) | 1.359 s (M 0.31, robot 68 %) | 1.461 s (M 0.30, robot 57 %) | **1.359 s** (family 3) |

What the optimiser finds:
- **The gripper sets the cycle time, not the robot.** Every optimum uses only 55–68 % of the
  LR-10iA/10 limits. The peak gripper acceleration while carrying is 8.4–9.8 m/s², about 1 g. Going
  faster is possible for the arm (`too-aggressive`: 1.36 s at 83 % of the limits) but not for the cups.
- **The default trajectory is not safe.** Family 3 at its default limits takes 1.659 s, but its margin
  is −0.07: the most loaded cup goes past its capacity during the transfer. The carton just stays on
  (bg-sim and the reduced model agree). The optimum, family 4 (joint blended), takes 1.578 s with a margin
  of 0.50: 5 % faster and safe.
- **Blending is what pays.** The families that stop at the corners take 1.95 s (joint PTP) and 2.07 s
  (Cartesian). Blending cuts 0.34–0.47 s. For the solid carton the joint blend is fastest (1.578 s against
  1.635 s for the Cartesian blend). For the loose contents the Cartesian blend is fastest (by 0.09–0.10 s).
- **No vacuum wait.** Every optimum has `T_seal` = 0: the vacuum is ready within the time the
  cylinders and the approach take. The Cartesian optima lift only 30 mm; the joint-blended optima lift
  70–80 mm with an 80 mm blend, so the transfer starts while the carton still rises.
- **Grip over the centre of mass.** With the CoM 60/30 mm off centre, gripping over the CoM costs only
  1 % (1.597 s). Gripping at the box centre is infeasible at any speed: at 5 % speed the margin is 0.19.
- **Loose contents.** The 1.1 kg load with M_req 0.3 can go faster (1.39 s with the ball, 1.36 s with the
  bottle). The content's impacts on the walls set the margin.
