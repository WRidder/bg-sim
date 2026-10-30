@@ figures panda
{
  "diagram": {"kind": "diagram", "model": "panda"},
  "scene": {"kind": "scene", "model": "panda", "t": 1.75},
  "run": {
    "kind": "plot", "model": "panda", "xlim": [0, 5.15],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Robot/J1/qout", "label": "q1"}, {"signal": "Robot/J2/qout", "label": "q2"}, {"signal": "Robot/J3/qout", "label": "q3"}, {"signal": "Robot/J4/qout", "label": "q4"}, {"signal": "Robot/J5/qout", "label": "q5"}, {"signal": "Robot/J6/qout", "label": "q6"}, {"signal": "Robot/J7/qout", "label": "q7"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "joint torque sensor [N m]", "series": [{"signal": "Robot/TauSense1/y", "label": "tauJ1"}, {"signal": "Robot/TauSense2/y", "label": "tauJ2"}, {"signal": "Robot/TauSense3/y", "label": "tauJ3"}, {"signal": "Robot/TauSense4/y", "label": "tauJ4"}, {"signal": "Robot/TauSense5/y", "label": "tauJ5"}, {"signal": "Robot/TauSense6/y", "label": "tauJ6"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "flange position [m]", "series": [{"signal": "Robot/TCP/g[5]", "label": "x"}, {"signal": "Traj/px", "label": "x target", "style": "--"}, {"signal": "Robot/TCP/g[6]", "label": "y"}, {"signal": "Traj/py", "label": "y target", "style": "--"}, {"signal": "Robot/TCP/g[7]", "label": "z"}, {"signal": "Traj/pz", "label": "z target", "style": "--"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page panda overview - | Overview
# Franka Emika Panda: Cartesian tour on bond-graph joint drives

The seven-axis Franka Emika Panda follows a Cartesian tour of its flange through four waypoints and back home. Two layers:

- **[Robot](block:Robot)**, a subsystem with the plant: the spatial multibond arm (`Revolute3D`, `RigidBody3D`, `FixedTransform3DNeutral`, the physically feasible dynamics of Gaz et al. 2019), one bond-graph drive per joint (torque limit, motor, rotor inertia, gear, elastic gear, Gaz friction) and the sensors (20-bit link-side encoders sampled at 1 kHz, joint rates, joint-torque sensors). Its ports: inputs `tau1..tau7` [N·m], outputs `q1..q7`, `dq1..dq7`, `tauJ1..tauJ7`.
- **The 1 kHz outer layer**, three discrete code blocks wired by signals: [Traj](block:Traj) (quintic rest-to-rest segments between the waypoints, yaw slerped), [IK](block:IK) (the analytical IK of He and Liu 2021 with q7 held) and [PD](block:PD) (PD with gravity and friction feedforward from the Gaz model).

![The model canvas|900](@fig:diagram)

```
Clock -> Traj -> g -> IK -> qr1..7 -> PD -> u1..7 -> Robot.tau1..7
                      ^               ^  ^
                      q1..6           q  dq       <- Robot.q1..7, Robot.dq1..7 (sensors)
```

The run: 5.15 s with `Rodas5P`, `reltol` 1e-6, `abstol` 1e-8, 1031 output points; about 3 s of compile and 19 s of solve time on the reference machine.

## What to look at

- the flange [Robot/TCP/g[5]](signal:Robot/TCP/g[5]) against the target [Traj/px](signal:Traj/px) (and `g[6]`, `g[7]` against `Traj/py`, `Traj/pz`);
- the joint-torque sensors [Robot/TauSense4/y](signal:Robot/TauSense4/y) (18.57 N·m at rest: the elbow carries the forearm);
- the IK status [IK/flag](signal:IK/flag), zero all the way (solved every tick).

## 3D view

`scenes/panda.sdf` is the URDF tree of `franka_description` with the official visual meshes (`meshes/link0..7.glb`); the seven joints are bound to `Robot/J<i>/qout`, so the viewer composes the arm itself. The RGB triad is the target pose `Traj/g`, the orange ball the simulated flange `Robot/TCP/g`.

![3D view at t = 1.75 s: the flange trails the target in the move from waypoint 1 to 2|500](@fig:scene)

Continue with [the Robot subsystem](page:robot), [the outer layer](page:control), [the results](page:results) and [the notes](page:notes).
@@ page panda robot overview | Robot subsystem
# The Robot subsystem

## Mechanics

- **Kinematics.** Modified DH (Craig) of Franka, identical to the joint origins of the URDF (`franka_arm.xacro`, checked to 1e-16): link frame $i$ is `panda_link<i>`, joint $i$ turns about its $z$.

| joint | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $a_{i-1}$ (m) | 0 | 0 | 0 | 0.0825 | -0.0825 | 0 | 0.088 |
| $d_i$ (m) | 0.333 | 0 | 0.316 | 0 | 0.384 | 0 | 0 |
| $\alpha_{i-1}$ | 0 | $-\pi/2$ | $\pi/2$ | $\pi/2$ | $-\pi/2$ | $\pi/2$ | $\pi/2$ |
| mass (kg) | 4.971 | 0.6469 | 3.229 | 3.588 | 1.226 | 1.667 | 0.7355 |

  The flange is 0.107 m along $z_7$ ([TCP](block:Robot/TCP)).
- **Bodies** ([B1](block:Robot/B1) to `B7`). Masses, centres of mass and inertia tensors are the physically feasible set of Gaz et al. 2019. `RigidBody3D` takes principal moments, so each tensor is diagonalised and the body 1-junction frame is the centre of mass turned to the principal axes ([CA1](block:Robot/CA1)).
- **Joints** ([J1](block:Robot/J1) to `J7`). `Revolute3D` with the five other directions compliant ($k = 10^7$), damped at 0.7 of critical. The arm starts at rest at the ready pose on the consistent deflections of the joint reactions, so nothing rings at $t = 0$.

## Drives (per joint)

```
tau_k -> Limit_k (+-87 / +-12 N m) -> Motor_k (MSe, 1/N) -> 1 [Rotor_k: I = J_m]
      -> Gear_k (TF, n = 1/N) -> 0 [TauSense_k: De] -> 1 [Spring_k: C = 1/k, Damper_k: R]
      -> 1 [Friction_k: Gaz] -> J_k.drive
```

The command is the link-side torque. The motor applies $\tau/N$ to the rotor, the gear multiplies it back by $N$, and the elastic gear (spring and damper on the 1-junction of the relative rate) carries it to the link 1-junction, where the Gaz friction acts. The [TauSense1](block:Robot/TauSense1) effort detector on the gear-output 0-junction measures the spring-plus-damper torque, which is the link-side torque sensor of the real arm. The springs start preloaded with the gravity torque of the ready pose.

| quantity | joints 1-4 | joints 5-7 | source |
| --- | --- | --- | --- |
| torque limit | 87 N·m | 12 N·m | Franka (`joint_limits.yaml`) |
| gear ratio $N$ | 100 | 100 | **assumed** (harmonic drive) |
| rotor inertia $J_m$ | 5e-5 kg·m² | 1e-5 kg·m² | **assumed** (reflected $N^2 J_m$ = 0.5 / 0.1 kg·m²) |
| gear stiffness $k$ | 1e4 N·m/rad | 5e3 N·m/rad | **assumed** |
| gear damping | 28.3 N·m·s/rad | 8.94 N·m·s/rad | damping ratio 0.2 of the rotor-on-spring mode |

Gaz friction (supplementary Table I), [Friction1](block:Robot/Friction1) to `Friction7`:

$$\tau_f(\dot q) = \frac{\varphi_1}{1 + e^{-\varphi_2(\dot q + \varphi_3)}} - \frac{\varphi_1}{1 + e^{-\varphi_2 \varphi_3}}.$$

## Sensors

- [Encoder1](block:Robot/Encoder1) to `Encoder7`: link-side angle quantized to $2\pi / 2^{20}$ (6 µrad) and sampled every 1 ms (`Quantizer`), the ports `q1..q7`;
- the joint rates `dq1..dq7` straight from `J_k.qdout`;
- the torque sensors `tauJ1..tauJ7`.
@@ page panda control overview | Outer layer
# The 1 kHz outer layer

## Trajectory ([Traj](block:Traj), `library/PandaTrajectory.jl`)

Waypoints of the flange (m): home (0.30689, 0, 0.59028) (the flange at the ready pose), (0.45, 0.20, 0.42), (0.45, -0.20, 0.42), (0.35, -0.12, 0.65), home. Segment $k$ starts at $t_0 + k\,(T_m + T_d)$ with $t_0 = 0.2$ s, $T_m = 0.9$ s, $T_d = 0.25$ s:

$$s = \tau^3 (10 - 15\tau + 6\tau^2), \qquad p = p_k + (p_{k+1} - p_k)\,s, \qquad \psi = \psi_k + (\psi_{k+1} - \psi_k)\,s.$$

The flange keeps its home orientation (pointing down) turned by $\psi$ about the vertical, with $\psi_k$ = atan2 of the waypoint (a slerp about $z$). With a fixed orientation the IK path asks up to 7 rad/s of the wrist; the slerp keeps every joint under 1.6 rad/s.

## Inverse kinematics ([IK](block:IK), `library/PandaIK.jl`)

The case-consistent geometric solver of He and Liu 2021 (`franka_analytical_ik`, Apache-2.0), re-derived for the flange, with $q_7$ held at $\pi/4$. Joint 4 comes from the triangle of joints 2, 4 and 6; joints 5 to 7 come from the wrist; joints 1 to 3 come from the shoulder. The branch (the sign of $q_2$ and the wrist case) is the one of the measured joint angles, so the solution stays on the branch the arm is on. If the target is out of reach or a joint limit is violated, the outputs keep the last valid solution and `flag` names the cause: 1 unreachable, 2 to 7 the limit of joint `flag - 1` (joints 1 to 6; $q_7$ is the fixed parameter).

## Joint controller ([PD](block:PD), `library/PandaPD.jl`)

$$\dot q_{r,i} = \frac{q_{r,i}(t_k) - q_{r,i}(t_{k-1})}{T_s},$$

$$u_i = \operatorname{clamp}\big(K_{p,i}(q_{r,i} - q_i) + K_{d,i}(\dot q_{r,i} - \dot q_i) + G_i(q) + \tau_{f,i}(\dot q_{r,i}),\ \pm u_{max,i}\big).$$

$G(q)$ is the Gaz gravity torque, unrolled in the block (generated code, equal to MuJoCo to 5e-14 N·m). $K_p = B\omega_n^2$ and $K_d = 2B\omega_n$, with $B$ the largest $M_{ii} + N^2 J_m$ along the path and $\omega_n$ = 15 rad/s (joints 1-4) or 20 rad/s (joints 5-7):

| joint | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $K_p$ (N·m/rad) | 320 | 522 | 356 | 296 | 51.5 | 53.0 | 42.0 |
| $K_d$ (N·m·s/rad) | 42.7 | 69.6 | 47.5 | 39.4 | 5.15 | 5.30 | 4.20 |
@@ page panda results overview | Results and checks
# Results and checks

![Joint angles, joint-torque sensors and the flange against its target|900](@fig:run)

| quantity | value |
| --- | --- |
| IK in the model vs the Python port, along the run | 4e-15 rad |
| FK of the in-model IK vs its target, along the run | 1e-15 m, 2e-15 (rotation) |
| IK round trip, 20000 random poses ($q_4 \le -0.5$) | 4.5e-13 m, 1.1e-12 (rotation), all solved |
| TCP tracking error, max / rms over the tour | 16.6 mm / 6.6 mm (lag in the moves, no inertia feedforward) |
| TCP error at the end of each dwell | 0.64, 0.92, 0.61, 0.32 mm |
| TCP error at 5.15 s | 0.055 mm |
| settled $\tau_J$ minus the MuJoCo gravity torque | under 1.6e-3 N·m |
| peak joint rates | 1.53 rad/s (joint 2; limit 2.175) |
| `IK/flag` | 0 throughout |
| compiled system | 21 states, 2907 equations |
| flatten / compile / solve | 1.3 s / 3.4 s / 18.8 s (23328 steps) |

`expected.json` holds 84 checks for this model, written by `design/build_expected.py` from the references: the start pose; the return to the ready pose; the flange back home; the flange tracking per axis (1.5x the measured value); the flange and the IK output at the middle of each dwell (the IK against the Python port within 1e-8 rad); the settled torque sensors against MuJoCo gravity; the torque and rate limits; the IK flag; and no diagnostics.
@@ page panda notes overview | Notes
# Notes

- **Speed.** The compliant held directions make the system stiff, so the run uses `Rodas5P`. The 21-state system solves in 3.7 s per simulated second, including the 5150 ticks of the 1 kHz discrete partitions.
- **Export.** `panda`, `panda-free` and the Robot subsystem on its own (`BGSim.Export.scope_document(doc, "Robot")`, `design/export_robot.jl`) export to C/FMU. The default RK4 export needs 12500 substeps per 1 ms step (about 70 ms per step); the Rosenbrock export (`ros2`, sparse LU) takes one step per 1 ms in 92 µs and keeps the joint angles of `panda` within 3e-6 rad of the simulation.
- **Assumptions.** Gear ratio, rotor inertia and gear stiffness are not published by Franka (see [the Robot subsystem](page:robot)). The controller is a textbook PD and not Franka's.
@@ figures panda-free
{
  "diagram": {"kind": "diagram", "model": "panda-free"},
  "scene": {"kind": "scene", "model": "panda-free", "t": 0.5},
  "run": {
    "kind": "plot", "model": "panda-free", "xlim": [0, 1],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "J1/qout", "label": "q1"}, {"signal": "J2/qout", "label": "q2"}, {"signal": "J3/qout", "label": "q3"}, {"signal": "J4/qout", "label": "q4"}, {"signal": "J5/qout", "label": "q5"}, {"signal": "J6/qout", "label": "q6"}, {"signal": "J7/qout", "label": "q7"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "flange position [m]", "series": [{"signal": "TCP/g[5]", "label": "x"}, {"signal": "TCP/g[6]", "label": "y"}, {"signal": "TCP/g[7]", "label": "z"}], "legend": true}
    ]
  }
}
@@ page panda-free overview - | Overview
# Franka Emika Panda: free swing

The bare Panda arm (the [J1](block:J1) to `J7` / [B1](block:B1) to `B7` chain of the `panda` model, without friction or drives: each drive port gets a zero effort source) is released at rest from the ready pose $q = (0, -\pi/4, 0, -3\pi/4, 0, \pi/2, \pi/4)$ and falls under gravity for 1 s. It checks the mechanics and the Gaz parameters against MuJoCo, which runs the same parameters from `reference/panda_gaz.xml`.

![The model canvas|900](@fig:diagram)

![3D view at t = 0.5 s|500](@fig:scene)

The run: 1 s with `Rodas5P`, `reltol` 1e-8, `abstol` 1e-10, 1001 output points; about 9 s of solve time (10790 steps).

Continue with [the results](page:free-results).
@@ page panda-free free-results overview | Results and checks
# Results and checks

![Joint angles and flange position|900](@fig:run)

| quantity | value |
| --- | --- |
| gravity torque, design Newton-Euler vs MuJoCo, 1000 random poses | 5e-14 N·m |
| mass matrix, design vs MuJoCo, 200 random poses | 4e-15 |
| joint angles vs MuJoCo at 0.1 s | under 8.4e-6 rad |
| joint angles vs MuJoCo at 0.25 s | under 1.3e-4 rad |
| joint angles vs MuJoCo at 0.5 s | under 4e-3 rad |
| flange vs MuJoCo at 0.25 s | 4e-5 m |

The difference grows quickly: the held directions are compliant ($k = 10^7$, so the joints sag by about $10^{-6}$ under the reaction loads) and the fall from the ready pose is chaotic, so the small difference grows from 8e-6 rad at 0.1 s to 4e-3 rad at 0.5 s. MuJoCo integrates a rigid chain. The checks (`expected.json`, 33 for this model) compare the angles at 0.1, 0.25 and 0.5 s and the flange at 0.25 s, each within 5x the measured difference.
