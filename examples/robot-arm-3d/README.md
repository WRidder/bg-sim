# robot-arm-3d — a six-axis arm with PD + gravity feedforward on the spatial multibond mechanics

A UR5-like six-axis serial arm moves from a home pose to a target pose under a 1 ms sampled
**PD + gravity-feedforward** controller. It is built from the J-MB9 spatial composites
(`Revolute3D`, `RigidBody3D`, `FixedTransform3DNeutral`, `LocalPose3D`, `ComposePose3D`) with the
geometry and inertias of the J-MB10 six-axis golden test, and it is the 3D twin of `robot-arm-2d`
(plan 9 / X-MB3, Gate C). Every power bond between the joints and the links is a `Power{Spatial}`
bundle, drawn as **three strokes**.

```
World ─ Mount ─ J1 ─ Link1 ─ BJ1 ─┬─ B1 (RigidBody3D)
                (Revolute3D)  (CoM) (1-junction) └─ T2 ─ J2 ─ Link2 ─ BJ2 ─┬─ B2
                                                       (standard-DH offset)   └─ T3 ─ J3 ─ ... ─ J6 ─ Link6 ─ BJ6 ─ B6
D1..D6 (MSe torque sources) ──► J1..J6.drive            Ctrl (ArmPD6, 1 ms) ──► D1..D6
J_i.qout, J_i.qdout, Clock ──► Ctrl                      MountPose ∘ LN_i ∘ J_i.pose ∘ LC_i ──► B_i.g,  W6 ∘ LTool ──► TCP
```

## The construction

* **Joints.** `Revolute3D` rotates exactly about the local `z` of its joint frame; the other five
  directions are compliant (`kt = kr = 1e7` N/m and N·m/rad), so every state stays integral (no
  `W201`). The held-direction damping is 0.7 of critical for the distal mass (translations) and for
  a 0.3 kg·m² reference inertia (rotations), so the stiff modes die in milliseconds.
* **Geometry.** Joint `i+1` sits at the standard-DH fixed part `Tz(d) Tx(a) Rx(α)` of link `i`
  (UR5-like: `d = 0.0892, 0, 0, 0.1092, 0.0947, 0.0823 m`, `a = 0, −0.425, −0.392, 0, 0, 0 m`,
  `α = π/2, 0, 0, π/2, −π/2, 0`). The body-1-junction frame is the link's centre of mass, so the
  next joint offset is `N − c_i` in that frame (`T2..T6`), with masses 3.7, 8.4, 2.3, 1.2, 1.2,
  0.74 kg and principal inertias about the centre of mass.
* **Drives.** One `MSe` torque source per joint on the joint's `Rotation` drive port, fed by the
  controller. A flow source cannot impose the joint motion (derivative causality, `W201`), so the
  joints are torque driven.
* **Poses.** Composed, never integrated: `W_i = W_{i−1} ∘ LN_i ∘ J_i.pose`, the body pose is
  `W_i ∘ LC_i` (feeds `B_i.g`, which gravity reads), and `TCP = W6 ∘ LTool` with a
  `0.0823 + 0.1 = 0.1823 m` flange-plus-tool offset along the flange `z`.
* **Start.** The arm is released at rest at the home pose `q = (0, −1.2, 1.2, −1.5, −1.5, 0)` on
  its **consistent deflections** (`starts` of `dth`, `dl` from the independent Newton-Euler
  reference), so the held directions carry the static gravity load from `t = 0` and the start does
  not excite the stiff modes.

## The controller (`library/ArmPD6.jl`, discrete code block per D28)

```
tau  = clamp((t − t0)/Tm, 0, 1),   s = tau³ (10 − 15 tau + 6 tau²)        t0 = 0.1 s, Tm = 0.8 s
qr_i = qh_i + (qt_i − qh_i) s,     qdr_i = (qt_i − qh_i) 30 tau² (1 − tau)² / Tm
u_i  = clamp(Kp_i (qr_i − q_i) + Kd_i (qdr_i − qd_i) + G_i(q), −umax_i, umax_i)
```

The firmware samples the six angles and rates (and the clock) every 1 ms and holds the torques
(zero-order hold, so no algebraic loop closes through the plant). **The gravity feedforward is
computed inside the controller from the same geometry as the plant**: the forward kinematics of
the standard-DH chain is unrolled in the block (generated code, no arrays) and
`G_i = g0 Σ_{j≥i} m_j z_i · ((w_j − o_i) × e_z)`, the torque that holds the arm static. It agrees
with the independent Newton-Euler gravity torque of J-MB10 to 7e-15 N·m at four test poses, so the
settled error is zero instead of the PD droop `G/Kp`. The gains come from the largest
mass-matrix diagonal entry `M_ii` over five poses between home and target:
`Kp_i = M_ii ωn²`, `Kd_i = 2 M_ii ωn` (critical damping of the decoupled joint) with
`ωn = 10, 10, 12, 20, 20, 20 rad/s`:

| joint | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| `Kp` N·m/rad | 274 | 331 | 107 | 6.23 | 1.5 | 0.2 |
| `Kd` N·m·s/rad | 54.9 | 66.2 | 17.9 | 0.623 | 0.15 | 0.02 |
| limit N·m | 150 | 150 | 150 | 28 | 28 | 28 |

The target is `q = (0.8, −0.8, 0.9, −1.9, −1.2, 0.6)`. There is no inertia feedforward, so the
tracking error during the move is about `M q̈ / Kp`.

## Measured (2.0 s run, `Rodas5P`, `reltol 1e-6`, `abstol 1e-8`)

| quantity | value |
| --- | --- |
| settled joint-angle error at 2.0 s | 1.0e-5, 3.4e-5, 1.3e-5, 9.6e-5, 7.8e-5, 2.0e-5 rad |
| TCP error vs analytic FK of the target angles | 9.9e-5 m (target `(−0.44364, −0.70827, 0.21091)` m) |
| peak torque | 19.8, 54.6, 20.7, 1.53, 0.20, 0.0013 N·m (limits never reached) |
| peak tracking error | 0.038, 0.018, 0.016, 0.029, 0.105, 0.0053 rad |
| settled torque minus target gravity torque | under 7e-3 N·m |
| states of the compiled system | 72 |
| accepted steps | 8973 |
| compile (structural cache hit) | 9.6 s; a cold first compile is about 90 s |
| solve | 113 s for 2.0 s of simulated time (about 57 s per simulated second) |
| `uv run examples/run_checks.py --only robot-arm-3d` | 43 passed, 0 failed in 451 s (including the worker start) |

The check bounds are 5x the measured errors (see the notes in `expected.json`). The TCP position
differs from the rigid-body forward kinematics by the compliant joints' sag (about 1e-5 m per
joint under gravity) plus the angle error times the 0.9 m reach.

### Solver and tolerance

The solver is set to `Rodas5P`. With `solver = "auto"` (the automatic stiff/non-stiff switching)
the run exhausts its 1e6 steps at `t = 0.485 s` (`E901`, `MaxIters`): the `kt = 1e7` held
directions make the system stiff and the default switching
algorithm does not get through it. `Rodas5P` takes 8973 steps for the 2 s run. At `reltol 1e-9` / `abstol 1e-11` (the J-MB10
setting) a 2.5 s run took 43711 steps and 178 s of solve time; `1e-6` / `1e-8` is enough here
because the checks are at the 1e-4 level. The cost per step (about 13 ms) is the Jacobian of the 72
state, 2339 equation system, so the horizon is kept at 2 s; `expected.json` sets `run_timeout` to
900 s for that reason.

## Files

* `models/arm.bgmodel.json` — the model (one model, `arm`; the plots are the joint angles, the
  controller torques, the tracking errors and the TCP position).
* `library/ArmPD6.jl` — the 1 ms controller block.
* `expected.json` — 43 checks: start and settled joint angles and rates, TCP against the analytic
  forward kinematics (home and target), settled gravity torques, torque limits, tracking errors
  and `no_diagnostics` (`W201`, `E101`, `E102`, `E103`, `E106`, `E007`, `W206`).
* `web/tests/e2e/robot-arm-3d.spec.ts` — imports the sample, asserts the three-stroke Spatial
  bonds and the single-stroke drive bonds, takes the canvas screenshot, runs the model and reads
  the settled `J2/qout` and `J5/qout` from the plot legend (real worker, about 6 minutes).
