# panda-3d — the Franka Emika Panda on bond-graph joint drives, with a Cartesian trajectory, analytical IK and PD

The seven-axis Franka Emika Panda with the physically feasible dynamics of Gaz et al. 2019, the
official kinematics and the official visual meshes, on the M3 spatial multibond mechanics. Two
models, plus their rigid-joint variants:

* **`panda`**: a **`Robot` subsystem** (the arm, seven bond-graph joint drives, the sensors) under
  a **1 kHz outer layer** of three readable discrete blocks: a Cartesian trajectory of the flange,
  the analytical inverse kinematics of He and Liu 2021, and a joint PD with gravity and friction
  feedforward. The flange tours four waypoints and returns home in 5.15 s.
* **`panda-free`**: the bare arm (no drives, no friction) released at rest from the ready pose,
  against MuJoCo running the same parameters.
* **`panda-free-rigid`, `panda-rigid`**: the same two models on the **rigid** joint
  `Revolute3DRigid` instead of the compliant `Revolute3D` (see [Rigid joints](#rigid-joints)).

```
panda:
Clock ─► Traj ──g──► IK ──qr1..7──► PD ──u1..7──► Robot.tau1..7
                     ▲              ▲ ▲
                     q1..6          q dq ◄── Robot.q1..7, Robot.dq1..7        (Robot.tauJ1..7: torque sensors)

Robot (subsystem), per joint k:
tau_k ─► Limit_k ─► Motor_k (MSe 1/N) ─► 1 [Rotor_k: I] ─► Gear_k (TF 1/N) ─► 0 [TauSense_k: De]
      ─► 1 [Spring_k: C, Damper_k: R] ─► 1 [Friction_k: GazFriction] ─► J_k.drive (Revolute3D)
J_k.qout ─► Encoder_k (Quantizer, 1 ms) ─► q_k        J_k.qdout ─► dq_k        TauSense_k ─► tauJ_k
World ─ Mount ─ J1 ─ Link1 ─ BJ1 ─┬─ B1 (RigidBody3D, principal axes)
                                  └─ T2 (modified-DH offset) ─ J2 ─ ... ─ J7 ─ Link7 ─ BJ7 ─ B7
pose chain: W_k = W_{k−1} ∘ LN_k ∘ J_k.pose,  P_k = W_k ∘ LC_k ─► B_k.g,  TCP = W_7 ∘ LFlange
```

Everything is generated from `design/` (Python, run with `uv`):

| file | what |
| --- | --- |
| `design/panda.py` | every number with its source: kinematics, Gaz parameters, friction, limits, the drive assumptions; Newton-Euler gravity, mass matrix and forward dynamics; the IK (Python port) and its round trip |
| `design/design.py` | the task: waypoints, timing, gains, start states; generated gravity code |
| `design/build_models.py` | `models/panda.bgmodel.json`, `models/panda-free.bgmodel.json` |
| `design/build_library.py` | `library/PandaTrajectory.jl`, `library/PandaIK.jl`, `library/PandaPD.jl` |
| `design/build_scene.py` | `scenes/panda.sdf`, `scenes/panda-free.sdf` |
| `design/convert_meshes.py` | `meshes/link0..7.glb` from the franka_description COLLADA files |
| `design/validate.py` | the MuJoCo reference (`reference/panda_gaz.xml`, `reference/panda_gaz.urdf`) and the validation table below |
| `design/build_expected.py` | `expected.json` from the references, with bounds from measured runs |
| `design/run_model.jl` | a run outside the backend, with the phase timings |
| `design/export_robot.jl` | the `Robot` subsystem exported alone as a plant FMU |

`library/GazFriction.jl` (the friction law as a nonlinear R element) and `library/RotorInertia.jl`
(the bond-graph I with a rotational port) are hand-written.

## Sources

| what | source | version |
| --- | --- | --- |
| kinematics (modified DH), joint limits, torque and rate limits | Franka Robotics, <https://frankaemika.github.io/docs/control_parameters.html>; `franka_description/robots/common/franka_arm.xacro` and `joint_limits.yaml` of github.com/frankaemika/franka_ros (Apache-2.0) | `develop` at ddd2fffd9de44b02ad15b4bbb2bfa2cec4d60d98 |
| visual meshes | `franka_description/meshes/visual/link0..7.dae` of the same repository | same |
| masses, centres of mass, inertia tensors, friction | C. Gaz, M. Cognetti, A. Oliva, P. Robuffo Giordano, A. De Luca, "Dynamic Identification of the Franka Emika Panda Robot With Retrieval of Feasible Parameters Using Penalty-Based Optimization", IEEE RA-L 4(4):4147–4154, 2019, doi:10.1109/LRA.2019.2931248. The feasible set `p̂`: Tables VIII and IX of the authors' supplementary material (revised 15 Oct 2019); friction: its Table I | github.com/marcocognetti/FrankaEmikaPandaDynModel `master` at 24d85ce4e648e2e894c832bfeee9b16711eb1a1a (`pdf/`) |
| `c1z` | `franka_description/robots/common/inertial.yaml` (franka_ros) | ddd2fffd |
| inverse kinematics | Y. He, S. Liu, "Analytical Inverse Kinematics for Franka Emika Panda – a Geometrical Solver for 7-DOF Manipulators with Unconventional Design", ICCMA 2021; github.com/ffall007/franka_analytical_ik (Apache-2.0), `franka_IK_EE_CC` | `main` at ab45e21e02aef71a3055d96ade7f96f00f7ec2dc |
| cross-check of the inertials only | github.com/jonasTUM/franka_panda_description (the Gaz values in URDF form) | `master` at 532c498281abd05e281ea5927658d4e95ec50332 |

The downloaded files were read as data only; none of their code was run (the authors' generated
`GravityVector.cpp` was checked with a whitelisting expression evaluator, see below).

## Parameters

Link frame `i` is `panda_link<i>`; joint `i` turns about its `z`; the flange is 0.107 m along `z7`.
`check_urdf()` in `panda.py` shows that the DH table and the URDF joint origins give the same
forward kinematics to 1.1e-16.

| joint | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `a_{i−1}` (m) | 0 | 0 | 0 | 0.0825 | −0.0825 | 0 | 0.088 |
| `d_i` (m) | 0.333 | 0 | 0.316 | 0 | 0.384 | 0 | 0 |
| `α_{i−1}` | 0 | −π/2 | π/2 | π/2 | −π/2 | π/2 | π/2 |
| mass (kg) | 4.970684 | 0.646926 | 3.228604 | 3.587895 | 1.225946 | 1.666555 | 0.735522 |
| CoM x (m) | 0.003875 | −0.003141 | 0.027518 | −0.05317 | −0.011953 | 0.060149 | 0.010517 |
| CoM y (m) | 0.002081 | −0.02872 | 0.039252 | 0.104419 | 0.041065 | −0.014117 | −0.004252 |
| CoM z (m) | −0.04762 | 0.003495 | −0.066502 | 0.027454 | −0.038437 | −0.010517 | 0.061597 |
| Ixx (kg·m²) | 0.70337 | 0.007962 | 0.037242 | 0.025853 | 0.035549 | 0.001964 | 0.012516 |
| Ixy | −0.000139 | −0.003925 | −0.004761 | 0.007796 | −0.002117 | 0.000109 | −0.000428 |
| Ixz | 0.006772 | 0.010254 | −0.011396 | −0.001332 | −0.004037 | −0.001158 | −0.001196 |
| Iyy | 0.70661 | 0.02811 | 0.036155 | 0.019552 | 0.029474 | 0.004354 | 0.010027 |
| Iyz | 0.019169 | 0.000704 | −0.012805 | 0.008641 | 0.000229 | 0.000341 | −0.000741 |
| Izz | 0.009117 | 0.025995 | 0.01083 | 0.028323 | 0.008627 | 0.005433 | 0.004815 |
| friction φ1 (N·m) | 0.54615 | 0.87224 | 0.64068 | 1.2794 | 0.83904 | 0.30301 | 0.56489 |
| friction φ2 (s/rad) | 5.1181 | 9.0657 | 10.136 | 5.5903 | 8.3469 | 17.133 | 10.336 |
| friction φ3 (rad/s) | 0.039533 | 0.025882 | −0.04607 | 0.036194 | 0.026226 | −0.021047 | 0.0035526 |
| torque limit (N·m) | 87 | 87 | 87 | 87 | 12 | 12 | 12 |
| rate limit (rad/s) | 2.175 | 2.175 | 2.175 | 2.175 | 2.61 | 2.61 | 2.61 |

The inertia tensors are about the centre of mass in link-frame axes. `RigidBody3D` takes principal
moments, so each tensor is diagonalised (`numpy.linalg.eigh`, a right-handed eigenbasis) and the
body 1-junction frame `CA_k` is the centre of mass turned to the principal axes.

Friction (Gaz, supplementary Table I), zero at rest:
`τ_f(q̇) = φ1 / (1 + exp(−φ2 (q̇ + φ3))) − φ1 / (1 + exp(−φ2 φ3))`.

### Drive assumptions

Franka publishes no gear ratio, rotor inertia or joint stiffness. **Assumed** values:

| quantity | joints 1–4 | joints 5–7 |
| --- | --- | --- |
| gear ratio `N` | 100 | 100 |
| rotor inertia `J_m` | 5e-5 kg·m² (reflected `N² J_m` = 0.5 kg·m²) | 1e-5 kg·m² (0.1 kg·m²) |
| gear stiffness `k` | 1e4 N·m/rad | 5e3 N·m/rad |
| gear damping `2 ζ √(k N² J_m)`, ζ = 0.2 | 28.28 N·m·s/rad | 8.944 N·m·s/rad |
| encoder | 20 bit per turn (2π/2²⁰ = 6.0 µrad), link side, sampled at 1 kHz | same |

## The Robot subsystem

* **Mechanics.** `Revolute3D` joints with the five other directions compliant (`k = 1e7`), damped
  at 0.7 of critical for the distal mass (translations) and for a 0.3 kg·m² reference inertia
  (rotations). `FixedTransform3DNeutral` offsets carry the modified-DH fixed parts; the poses are
  composed, never integrated.
* **Drives.** `Limit_k` (`Saturation`, ±87 / ±12 N·m) clips the link-side command; `Motor_k`
  (`MSe`, gain `1/N`) is the motor torque on the rotor 1-junction with `Rotor_k`
  (`RotorInertia`, `J_m`); `Gear_k` (`TF`, `n = 1/N`) turns it into the link-side torque; the
  elastic gear is the 0-junction (shared gear-output torque) and the 1-junction of the relative
  rate with `Spring_k` (`C`, `c = 1/k`) and `Damper_k` (`R`); the link 1-junction adds
  `Friction_k` (`GazFriction`) and drives `J_k.drive`. `RotorInertia` is the stdlib `I` with a
  `Power{Rotation}` port: with the Generic `I` the motor-side island had no concrete domain
  (W205), and the TF between it and the Rotation link side failed (E102).
* **Sensors.** `Encoder_k` (`Quantizer`, 6.0 µrad, 1 ms) on `J_k.qout`, the rate `J_k.qdout`,
  and `TauSense_k` (`De` on the gear-output 0-junction: the spring-plus-damper torque, the
  link-side joint-torque sensor).
* **Start.** At rest at the ready pose `q = (0, −π/4, 0, −3π/4, 0, π/2, π/4)`: the springs are
  preloaded with the gravity torque (`q_C = G/k`), and the held directions start on the
  deflections of the static joint reactions (`starts` of `dth`, `dl`), so nothing rings at `t = 0`.
* **Ports.** Inputs `tau1..tau7` (N·m, the link-side command); outputs `q1..q7` (encoders),
  `dq1..dq7`, `tauJ1..tauJ7`.

## The outer layer (1 kHz, discrete code blocks per D28)

* **`Traj`** (`PandaTrajectory`). Waypoints of the flange: home (0.30689, 0, 0.59028) m (the flange
  at the ready pose), (0.45, 0.20, 0.42), (0.45, −0.20, 0.42), (0.35, −0.12, 0.65), home.
  Segment `k` starts at `t0 + k (Tm + Td)`, `t0 = 0.2 s`, `Tm = 0.9 s`, `Td = 0.25 s`, quintic rest
  to rest `s = τ³ (10 − 15τ + 6τ²)`. The flange keeps its home orientation (pointing down) turned
  about the vertical by `ψ`, interpolated with the same `s` between `ψ_k = atan2(y_k, x_k)` (a
  slerp about `z`). With a fixed orientation the IK path needs 5.7 and 7.2 rad/s at joints 5 and
  7; with the yaw it stays under 1.5 rad/s. Output `g` is the target pose `(qw, qx, qy, qz, x, y, z)`.
* **`IK`** (`PandaIK`). He and Liu's case-consistent solver (`franka_IK_EE_CC`), re-derived for the
  flange (`d7e = 0.107`, no hand rotation), with `q7` held at `π/4`. The branch (the sign of `q2`
  and the wrist case) is taken from the measured angles, so the solution stays on the arm's branch.
  When the target is out of reach (`flag = 1`) or violates the limit of joint `j` (`flag = j + 1`,
  joints 1–6), the outputs keep the last valid solution. `flag = 0` means solved.
* **`PD`** (`PandaPD`). `qdr = (qr − qr_prev)/Ts`;
  `u = clamp(Kp (qr − q) + Kd (qdr − dq) + G(q) + τ_f(qdr), ±umax)`. `G` is the Gaz gravity torque
  as generated code (equal to MuJoCo to 5e-14 N·m). `Kp = B ωn²`, `Kd = 2 B ωn`, with `B` the
  largest `M_ii + N² J_m` along the joint path, `ωn` = 15 rad/s (joints 1–4) and 20 rad/s (5–7):
  `Kp` = 320, 522, 356, 296, 51.5, 53.0, 42.0 N·m/rad; `Kd` = 42.7, 69.6, 47.5, 39.4, 5.15, 5.30,
  4.20 N·m·s/rad.

## Validation

Reference: MuJoCo 3 (`mujoco` wheel) on `reference/panda_gaz.xml`, written by `validate.py` from the
same `panda.py` numbers (nested bodies at the URDF joint origins, `fullinertia`, no limits, damping
or armature). Pinocchio was the first choice, but `pin` has no Windows wheel and building it from
source fails.

| check | result |
| --- | --- |
| DH vs URDF joint origins (forward kinematics) | 1.1e-16 |
| gravity torque: design Newton-Euler vs MuJoCo, 1000 random poses | 5.0e-14 N·m |
| mass matrix: design vs MuJoCo, 200 random poses | 3.6e-15 |
| generated gravity code in `PandaPD` vs the design | exact (same expression) |
| gravity at the ready pose (MuJoCo) | (0, −1.7714, −0.6440, 18.5736, 0.6338, 1.6937, 0) N·m |
| the authors' `GravityVector.cpp` vs `p̂` (300 poses) | up to 0.21 N·m: the C++ uses the identified (non-feasible) coefficients |
| IK round trip (Python), 20000 random poses with `q4 ≤ −0.5` | all solved; 4.5e-13 m, 1.1e-12 rotation, 3.7e-10 rad |
| IK in the model vs the Python port, every output sample | 3.6e-15 rad |
| FK of the in-model IK vs its target, every output sample | 9.5e-16 m, 1.8e-15 rotation |
| free swing vs MuJoCo (DOP853, rtol 1e-12): joint angles at 0.1 / 0.25 / 0.5 s | 8.4e-6 / 1.3e-4 / 4.0e-3 rad |
| free swing: flange at 0.25 s | 3.9e-5 m |
| `panda`: TCP tracking error, max / rms over the tour | 16.6 mm / 6.6 mm |
| `panda`: TCP error at the end of each dwell | 0.64, 0.92, 0.61, 0.32 mm |
| `panda`: TCP error at 5.15 s | 0.055 mm |
| `panda`: settled torque sensors minus MuJoCo gravity at the reached pose | under 1.3e-3 N·m |
| `panda`: peak joint rates | 0.57, 1.53, 0.72, 1.48, 0.24, 1.35, 0.0065 rad/s (limits 2.175 / 2.61) |
| `panda`: peak torque commands | 8.9, 30.3, 8.1, 22.9, 1.0, 2.2, 0.06 N·m (limits 87 / 12, never reached) |
| `panda`: `IK/flag` | 0 throughout |

**The free swing diverges slowly from MuJoCo, as expected.** The bg-sim joints are compliant in the
held directions (`k = 1e7`: the joints sag by about 1e-6 under the reaction loads), while MuJoCo
integrates a rigid chain. The fall from the ready pose is chaotic, so this O(1/k) difference grows
from 8e-6 rad at 0.1 s to 4e-3 rad at 0.5 s and 0.18 rad on joint 7 at 1 s. The start is not the cause: it uses
the joint reactions of the released arm (`forward_dynamics`), and the difference is 1e-10 rad at
1 ms. The checks stop at 0.5 s.

**The tracking error is lag.** The PD has no inertia feedforward, so the flange trails the target
during the moves (`M q̈ / Kp`) and settles within each dwell.

`expected.json` (241 checks, generated by `design/build_expected.py`; 117 for the two compliant
models below, the rest for the [rigid variants](#rigid-joints)) takes its expected values from
the references and its bounds from 5x the measured deviations (1.5x for the tracking error):

* `panda-free` (33): the start, the joint angles against MuJoCo at 0.1, 0.25 and 0.5 s, the flange
  at 0.25 s, the scene bindings, and no diagnostics.
* `panda` (84): the start and return to the ready pose; the flange back home; the flange tracking
  per axis; the flange and the in-model IK at the middle of each dwell (the IK within 1e-8 rad of
  the Python port); the settled torque sensors against the MuJoCo gravity torque of the ready pose;
  the torque and rate limits; the IK flag; the scene bindings; and no diagnostics.

`uv run examples/run_checks.py --only panda-3d`: 119 passed, 0 failed (the 117 checks and the
docs lint of both models), 74 s.

## Timings

Measured on the Windows 11 development machine with `design/run_model.jl`, one fresh Julia process
per model with BGSim precompiled. Without a precompiled BGSim, loading takes about 3 min and the
first flatten about 10 s.

| | `panda-free` (1 s) | `panda` (5.15 s) |
| --- | --- | --- |
| flatten | 1.0 s | 1.3 s |
| compile (`mtkcompile` and code generation) | 3.2 s | 3.4 s |
| solve | 8.8 s, 10790 steps | 18.8 s, 23328 steps |
| states / equations | 7 / 2696 | 21 / 2907 |

The compliant held directions make the system stiff, so both models use `Rodas5P`. For
comparison, the six-axis `robot-arm-3d/arm` needs 113 s for 2 s of simulated time.

## C/FMU export

`uv run examples/export_checks.py --out <dir> --budget 900 panda-3d` (the default export settings):

| model | status | states | dt | substeps per 1 ms | worst error (rel. to peak) | signal | doStep mean / max | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `panda` | compared | 98 | 8e-8 s | 12500 | 1.16e-3 | `Robot/B1/inertia/p.e[4]` | 69.6 / 150 ms | W203, W207, W209 |
| `panda-free` | compared | 84 | 8e-8 s | 12500 | 1.05e-5 | `J7/thd[2]` | 46.0 / 70 ms | W207, W209 |

Both models export, build, pass the symbol and allocation checks, and agree with the simulation.
The default method (explicit RK4) is limited by the held directions: `|λ| = 3.2e6 1/s` needs a
step of 8e-8 s, so a 1 ms FMU step costs 12500 substeps and 46 to 70 ms (W207). That is 50 to 70
times slower than real time. W203: the `Saturation` switches of `Limit_k` are evaluated once per
step (the limits are never reached). W209: the whole models have no export markers.

**The Robot subsystem alone** (`design/export_robot.jl`, `BGSim.Export.scope_document(doc,
"Robot")`): the scope turns the ports into the FMU interface, inputs `tau1..tau7` (started at the
gravity torque of the ready pose) and outputs `q1..q7`, `dq1..dq7`, `tauJ1..tauJ7`. It flattens in
11 s and exports in 18 s (2 s against the reference). The plant has 98 states. With the default
settings it uses RK4 with dt 8e-8 s, 12500 substeps per 1 ms step (W207), 336 parameters folded,
and 7 held values (the encoder samples).

**Real time needs the Rosenbrock export** (`--settings '{"method":"ros2","linear_solver":"sparse"}'`;
`export_robot.jl <out> 1.0 ros2` for the Robot alone). It takes one linearly implicit step per
1 ms: a finite-difference Jacobian with 45 colours, nnz(J) 2062, and a sparse LU of 2600 non-zeros
and 37195 flops (the dense LU would be 622741).

| model (ros2, dt 1 ms) | status | doStep mean / max | joint angles vs reference | flange | torque sensors |
| --- | --- | --- | --- | --- | --- |
| `panda` | compared | 92 µs / 1.3 ms | under 3.0e-6 rad | under 2.4e-6 m | under 0.014 N·m |
| `panda-free` | the harness diverged | | | | |

The gate's worst relative error for `panda` under ros2 is 10.5, in `Robot/J6/Vrel[1]`. That is an
internal rate of a held direction: the 1 ms step does not resolve the `1e7` modes, and the
L-stable method damps them, which is the intent. The joint angles, flange and sensors above come
from the same FMU, compared with the reference by `fmpy`. The frictionless free fall of
`panda-free` diverges at a 1 ms ros2 step (the arm spins up to several rad/s). Its RK4 export
passes.

## Rigid joints

`panda-free-rigid` and `panda-rigid` are generated by the same code with `rigid=True`. Every
`Revolute3D` becomes `stdlib:spatial/Revolute3DRigid`:

* The held directions are hard velocity constraints, and their reactions are Lagrange
  multipliers.
* The link inertias are derivative-causal, so W201 is expected.
* `mtkcompile`'s index reduction keeps `q` and `qdot` per joint as the states.

Everything else is unchanged: the drives, the sensors and the outer layer. Section 5.7 of
plan/MULTIBOND_PLAN.md has the details.

| | `panda-free-rigid` (1 s) | `panda-rigid` (5.15 s) |
| --- | --- | --- |
| differential states / algebraic unknowns | 14 / 139 (compliant 84 / 0) | 28 / 139 (compliant 98 / 0) |
| `mtkcompile` | 4.2 s | 4.6 s |
| solve (median of 3, warm) | 4.3 s, 5266 steps | 27.6 s, 26660 steps |
| free swing vs MuJoCo at 0.1 / 0.25 / 0.5 / 1 s | 1.7e-12 / 1.2e-13 / 1.4e-12 / 3.9e-11 rad | |
| settled flange error at the end of the tour | | 5.5e-6 m (compliant 5.5e-5 m: the held directions sag) |
| joint angles against `panda` | | within 2.7e-6 rad |

**Accuracy.** The rigid chain is the chain that MuJoCo integrates, so the chaotic fall agrees
through the whole second. The compliant model is off by 4e-3 rad at 0.5 s and 0.18 rad at 1 s.

**Simulation cost.** It is not lower: the index-reduced DAE keeps every body twist, momentum and
reaction as an algebraic unknown.

**Export.** The rigid export is accurate at a 1 ms step, because the 1e7 held-direction modes
are gone (`max |λ|` is 52 1/s for `panda-free-rigid`). It is not real time yet:

* The static sparse LU has zero pivots on the algebraic rows, so the export falls back to the
  dense LU (W211).
* `panda-free-rigid` (ros34pw2, 1 ms) takes 647 µs mean and 2.3 ms max per step.
* `panda-rigid` (rodas4p at 0.25 ms x 4, which the elastic gear modes require) takes 3.9 ms per
  step.

**Checks.** `expected.json` adds 40 checks for `panda-free-rigid`: the joint angles against
MuJoCo up to 1 s, with a 1e-8 rad floor. `panda-rigid` gets the 84 checks of `panda`.
`no_diagnostics` leaves out W201 in both.

## 3D view and meshes

`scenes/panda.sdf` is the URDF tree of `franka_description`: links `panda_link0..7` at their rest
poses with `meshes/link<i>.glb`, revolute joints `panda_joint1..7` with their frames on the child
links (the axis is the child `z`). The models bind `joint:panda_joint<i>` to `J<i>/qout`
(`Robot/J<i>/qout` in `panda`), so the viewer composes the arm itself. `panda.sdf` adds the target
pose `Traj/g` (an RGB triad, `tcp_target`) and the simulated flange `Robot/TCP/g` (an orange ball,
`tcp_actual`); `panda-free.sdf` has only the ball.

The meshes are the official visual meshes (COLLADA, Z-up, metres) converted by
`design/convert_meshes.py`: trimesh with pycollada, node transforms baked, one sub-mesh per
material, the diffuse colour kept as a PBR base colour, and quadric decimation to half the faces
(sub-meshes under 400 faces are kept). Full resolution would be 2.2 MiB.

| mesh | sub-meshes | faces | size |
| --- | --- | --- | --- |
| link0.glb | 12 | 10870 | 203 KiB |
| link1.glb | 1 | 6258 | 111 KiB |
| link2.glb | 1 | 6358 | 113 KiB |
| link3.glb | 4 | 7411 | 135 KiB |
| link4.glb | 4 | 7608 | 138 KiB |
| link5.glb | 3 | 9287 | 169 KiB |
| link6.glb | 17 | 11164 | 218 KiB |
| link7.glb | 8 | 6716 | 127 KiB |
| total | | 65672 | 1.18 MiB |

License: Apache-2.0, `meshes/LICENSE` and `meshes/NOTICE` (Copyright 2023 Franka Robotics GmbH).
The meshes are modified (converted and decimated).

## Discrepancies between the sources

* **`c1z`.** It does not enter the dynamics (joint 1 turns about `z`, so the paper calls it a
  "don't care"). The values are 0 (the authors' Matlab), −0.04762 m (`franka_description`
  `inertial.yaml`, used here) and −0.1750 m (jonasTUM). The choice changes no torque and no motion.
* **The authors' C++/Matlab code** uses the identified base-parameter coefficients (January 2019),
  not the feasible `p̂`. Its gravity vector differs from the `p̂` gravity by up to 0.21 N·m. This
  example follows the paper's feasible set (Tables VIII and IX), which the brief asks for.
* **jonasTUM** inertials equal Table IX apart from `c1z`.
* The published postprint of the paper could not be downloaded (HTTP 403); the supplementary
  tables in the authors' repository were used.

## Limitations

* **The IK family.** The case-consistent solver covers the `q4 ≤ −0.467` part of joint 4's
  range (the 2-4-6 triangle on the branch the solver assumes). Near `q4 = −0.0698` (the
  stretched-out limit) a target can be reachable and still be refused. The tour stays well inside
  (`q4` between −2.41 and −2.03), and the round trip is measured for `q4 ≤ −0.5`.
* **The controller** is a textbook PD with feedforward, not Franka's; the drive values are assumed.

## Regenerating

```sh
uv run examples/panda-3d/design/panda.py                         # the design report and self checks
uv run examples/panda-3d/design/build_library.py
uv run examples/panda-3d/design/build_models.py
uv run examples/panda-3d/design/build_scene.py
uv run examples/panda-3d/design/convert_meshes.py <franka_description>/meshes/visual
julia --project=julia/BGSim examples/panda-3d/design/run_model.jl panda-free <run_dir>
julia --project=julia/BGSim examples/panda-3d/design/run_model.jl panda <run_dir>
uv run examples/panda-3d/design/validate.py --free <free run> --panda <panda run> --json <out>
uv run examples/panda-3d/design/build_expected.py --free <free run> --panda <panda run>
uv run examples/panda-3d/design/build_expected.py --free-rigid <run> --panda-rigid <run>  # keeps the others
uv run examples/run_checks.py --only panda-3d
uv run tools/example_docs/build.py --only panda-3d
julia --project=julia/BGSim examples/panda-3d/design/export_robot.jl <out_dir>
```
