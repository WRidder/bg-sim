# Robot and trajectories

## Geometry and limits

No URDF, xacro or mesh of the LR-10iA/10 is published. The geometry is the closest FANUC arm whose sources are open, the **LR Mate 200iD/7L**: the same slim LR family, six axes, a spherical wrist and a reach of 911 mm (the LR-10iA/10 has 1101 mm). The kinematics and meshes come from `fanuc_lrmate200id_support/urdf/lrmate200id7l_macro.xacro` of github.com/ros-industrial/fanuc, branch `noetic-devel` at `d8f42bd73584b255df87098395512538882caea1` (package 0.6.0, BSD-3-Clause, see `meshes/LICENSE`).

The limits are those of the **LR-10iA/10** (catalogue RLR-10iA(E)-01):

| joint | range [°] | rate [°/s] | acceleration [°/s²] (assumed) | jerk [°/s³] (assumed) |
| --- | --- | --- | --- | --- |
| J1 | ±185 | 300 | 2000 | 40 000 |
| J2 | −96..139 | 230 | 1533 | 30 667 |
| J3 | −70..213 | 340 | 2267 | 45 333 |
| J4 | ±190 | 500 | 5000 | 100 000 |
| J5 | ±125 | 400 | 4000 | 80 000 |
| J6 | ±360 | 800 | 8000 | 160 000 |

Payload: 10 kg. Allowable wrist moment J4/J5/J6: 21/21/10 N·m. Allowable wrist inertia: 0.77/0.77/0.28 kg·m².

No FANUC document gives acceleration or jerk limits. They are **assumed**: each rate limit is reached in 0.15 s (J1–J3) or 0.10 s (J4–J6), and each acceleration limit in 0.05 s. Replace them in `design/fanuc.py` with the controller's values.

The wrist load is computed from the following, as point masses at their centres:
- the gripper (1.3 kg, its centre 121 mm below the flange);
- the carton (with its centre of mass);
- the accelerations of the plan, gravity included.

The moment is taken about the wrist centre.

## Kinematics

The tool points straight down, so the inverse kinematics is closed form:

$$q_1 = \operatorname{atan2}(y, x), \qquad r = \sqrt{x^2 + y^2} - a_1, \qquad z' = z + d_6 - d_1,$$

with the elbow-up solution of the planar two-link problem for $q_2, q_3$, then $q_4 = 0$, $q_5$ keeping the tool vertical, and $q_6 = \psi - q_1$ for the gripper yaw $\psi$. The block evaluates this IK at the tick before, at and after each tick. From the three it forms the joint rates and accelerations, the body twist of the gripper and its rate (`V`, `Vd`). The URDF chain (`design/fanuc.py`) agrees with the closed-form pose to 3e-16 m (`reference.py`), and the `scene_bindings` check confirms it in every run.

## The cycle

The cycle runs from the approach start to the depart end:

1. Approach: from `h_app` = 60 mm above the pick contact pose.
2. The cylinders extend `t_ext` before the contact, and the vacuum opens `t_vac` before it.
3. Wait `T_seal` at the pick.
4. Lift by `H_lift`, transfer (yaw turned by 90°), lower.
5. Vacuum off, vent `T_rel` = 80 ms.
6. Depart 60 mm up.

The cylinders stay out while the carton is carried (`ret_hold = 0`).

## Families

| family | path | profile |
| --- | --- | --- |
| 1 joint PTP | lift, transfer and lower are separate moves with stops | synchronised joint moves: each joint's time from `kv`, `ka` x its limits; the slowest joint sets the time |
| 2 Cartesian | straight lines with stops | along the path at `v_c`, `a_c`, `j_c`; the yaw at `w_c`, `al_c`, `jw_c`, synchronised |
| 3 Cartesian blended | straight lines; each move starts `r_b` before the end of the one before | as 2, overlapped (a rounded corner) |
| 4 joint blended | joint space; the transfer starts `r_b` before the end of the lift | as 1, overlapped |

Every move is a jerk-limited S-profile. `lam` is the jerk phase as a share of the acceleration phase: 0 is a trapezoid, 1 a pure S-curve. For a move of length $L$, the time is the largest of the velocity, acceleration and jerk bounds:

$$T = \max\left(T_0,\ \left(J\,L / j_{max}\right)^{1/3}\right), \qquad J = \frac{1}{(1-\alpha)(\alpha - t_j)\,t_j},$$

with $T_0$ the time of the velocity and acceleration limits, $\alpha$ the acceleration share and $t_j$ the jerk share of the profile.

![Joint angles and rates of the default run (family 3)|900](assets/af9527384e6f.png)
