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

---

# The RRR arm as an equation block, and its multibond counterpart (X5.3, plan 9.8)

The same example also holds the plan 9.8 three-joint arm: a hand-derived Hamiltonian
equation block (`ArmDynamics3R`) behind three DC motors and 50:1 gears, a 1 ms discrete PD +
gravity-compensation controller, and minimum-jerk `TimeTable` references. The same geometry is
rebuilt from the M3 spatial stdlib (`rrr-multibond`) and the two are compared joint by joint
(DEC-M5-2). The six-axis arm above (`arm`) is untouched.

| model | what it is | run |
| --- | --- | --- |
| `rrr` | `ArmDynamics3R` + 3 x (`VoltageSource` -> `DCMotor` -> `IdealGear` n = 50) + `ArmCtrl3R` + 3 `TimeTable` | 5 s, solver `auto`, 1e-8 / 1e-10 |
| `rrr-free` | the arm alone: zero-torque `Se` on every joint, g = 0, released with rates (2, -1.5, 2.5) rad/s; `Arm/E` is the total energy | 5 s, 1e-10 / 1e-12 |
| `rrr-torque` | the arm driven by ideal joint-torque sources (`MSe`) from the same controller and references | 5 s |
| `rrr-multibond` | the same RRR geometry from `Revolute3D` + `RigidBody3D` + `FixedTransform3DNeutral`, the same torque sources, controller and references; held directions `kt = kr = 1e7` | 5 s, `Rodas5P`, 1e-8 / 1e-10 |
| `rrr-multibond-soft`, `-stiff` | the same with `kt = kr = 1e6` and `1e8` (the error-scaling measurement) | |

```
Ref1..3 (TimeTable) ──► Ctrl (ArmCtrl3R, 1 ms) ──u_i──► Amp ─ Motor ─ Gear (n = 50) ──► Arm (ArmDynamics3R: j1 j2 j3)
                          ▲                                                               │
                          └──────────── q1..3, qd1..3 (Arm outputs) ◄─────────────────────┘
```

## `ArmDynamics3R` (`library/ArmDynamics3R.jl`)

Base yaw `q1` about world z (inertia `Jb`), shoulder `q2` = elevation of the upper arm above
horizontal, elbow `q3` relative to the upper arm, point masses `m2` at the elbow and `m3` at the
tip. The states are `q` and the momenta `p = M(q) qd`; every joint is a `Power{Rotation}` port
with `j.f = qd_i` and `j.e = tau_i` into the arm, and

```
ddt(q) ~ qd,   p ~ M * qd,   ddt(p) ~ tau + dTdq - dVdq
M11 = Jb + m2 r_e^2 + m3 r_t^2,  M22 = m2 l2^2 + m3 (l2^2 + l3^2 + 2 l2 l3 cos q3),
M23 = m3 (l3^2 + l2 l3 cos q3),  M33 = m3 l3^2,  M12 = M13 = 0
```

with `r_e`, `z_e`, `r_t`, `z_t`, the three `dM/dq` terms and `dV/dq` exactly as in the plan
(l2 = 0.4, l3 = 0.3, m2 = 2, m3 = 1, Jb = 0.05, g = 9.81). **The formulas were verified
symbolically before use**: a sympy script built `T = 1/2 qd' M qd` and `V = g (m2 z_e + m3 z_t)`
from the geometry and checked `M`, `dT/dq` and `dV/dq` against the plan's expressions: all
differences simplify to zero. `E = 1/2 qd.p + V` is a block output.

## Drives and controller (`library/ArmCtrl3R.jl`)

`ArmCtrl3R` runs at Ts = 1 ms. It samples `q`, `qd` and the three references and computes the
joint torque command

```
tc_i = Kp_i (ref_i - q_i) + Kd_i (rd_i - qd_i) + dV/dq_i(q)         rd_i = (ref_i - ref_i at the previous tick) / Ts
u_i  = clamp(R tc_i / (n k_t) + n k_t qd_i, -48, 48)                 motor voltage: static current + back-EMF cancel
```

`dV/dq` is the plant's gravity term evaluated at the measured `q` (a code block, not a copy of the
arm), so a settled arm sits exactly on its reference. The motors are `R = 1 Ohm`, `L = 0.5 mH`,
`k_t = 0.1 N m/A`, `J_m = 1e-5 kg m^2` (reflected inertia `n^2 J_m = 0.025 kg m^2` per joint). The
gains come from `design/design.py`: critical damping of the decoupled joint at the largest effective
inertia `M_ii + n^2 J_m` over the workspace, `wn = 20 rad/s`:

| joint | 1 | 2 | 3 |
| --- | --- | --- | --- |
| `Kp` N m/rad | 354 | 334 | 46 |
| `Kd` N m s/rad | 35.4 | 33.4 | 4.6 |

`tc_i` is also an output of the block, which is what the torque-source models use. The references
are `TimeTable`s (linear interpolation, 50 ms, 65 samples) of two minimum-jerk point-to-point moves
`q(t) = q0 + (q1 - q0)(10 s^3 - 15 s^4 + 6 s^5)`: from `(0, 0.6, -0.9)` to `(1.2, 1.0, -0.4)` over
0.2 .. 1.2 s and to `(-0.6, 0.3, -1.3)` over 1.8 .. 3.0 s. `design/design.py` generates the tables
(`uv run examples/robot-arm-3d/design/design.py` prints the design) and also integrates a numpy RK4
**replica of the whole sampled closed loop** (plant, motor electrics, gears, controller) that the
checks compare the Julia run with. `design/build_models.py` writes the model documents (layout,
tables, gains, static deflections), so a changed design is
`uv run examples/robot-arm-3d/design/build_models.py` away.

## Checks and measured values

| check | measured |
| --- | --- |
| free motion, g = 0, motors removed: `max|E - E0| / max|E|` over 5 s (plan: < 1e-6) | **3.2e-13** (E0 = 1.769789 J; absolute 5.6e-13 J) |
| free motion vs the numpy RK4 replica after 5 s | `q` agrees to 3.1e-12 rad |
| tracking error after the moves settle (plan: < 0.01 rad) | `max|e|` from 4.0 s: **1.5e-8, 9.1e-9, 2.0e-8 rad**; from 3.5 s: 1.2e-5, 1.5e-6, 1.5e-5 rad |
| tracking error during the moves | 0.0145, 0.0088, 0.0203 rad |
| peak motor voltage (limit 48 V) | 14.8, 6.6, 6.6 V |
| Julia run vs the numpy closed-loop replica, whole run, `Arm/q1..q3` | **6.4e-11, 5.6e-11, 1.7e-9 rad** |
| diagnostics of `rrr` | W201 only: the motor rotors behind the rigid gears are derivative-causal with the arm inertia (the reduction handles it) |
| run times (one example run, loaded machine, including the first compile of each structure) | `rrr` 74 s, `rrr-free` 10 s, `rrr-torque` 16 s, `rrr-multibond` 224 s, `-soft` 103 s, `-stiff` 114 s |
| `uv run examples/run_checks.py --only robot-arm-3d` | **109 passed, 0 failed in 793 s** (the 43 X-MB3 checks plus 66 new ones: 28 + 10 + 7 + 12 model checks and 9 `compare` entries) |

One detail of the replica: the Julia run holds the controller output at its default (0 V) through
the first period, so the first command (zero reference rate) lands at 1 ms. The replica does the
same (`first_tick = 1`); with the command at t = 0 it differs by 4e-4 rad during the first 0.2 s.

## The M3 comparison (DEC-M5-2)

`rrr-multibond` is the same arm built from the M3 spatial stdlib, following `arm.bgmodel.json`:

* a base body (1 kg at the pivot, isotropic inertia `Jb`, so its yaw inertia is the plan's `Jb`) on a
  compliant `Revolute3D` about world z (`World` -> `Mount` -> `J1`);
* joints 2 and 3 about world `-y`: the joint frame is `Rx(90 deg)` (local z = -y), so positive `q`
  raises the arm; `LN2` places joint 2 at the shoulder, `LN3` places joint 3 `l2` along the upper
  arm, `T2` and `T3` are `LN^-1 o LC`;
* point masses as `RigidBody3D` bodies (`m2` at the elbow, `m3` at the tip, 1e-8 kg m^2 principal
  moments because a point has none), links `l2` and `l3` as `FixedTransform3DNeutral` (`Link2`,
  `Link3`); the body poses for gravity come from the `ComposePose3D` chain of `arm.bgmodel.json`;
* held directions `kt = kr = 1e7` with 0.7-critical damping, released on their **static
  deflections** (`dth`, `dl` from the weight of everything distal; `design/build_models.py`).

**Why torque sources, not the motors.** Both models are driven by the same `ArmCtrl3R`, the same
`TimeTable`s and ideal joint-torque sources (`MSe`, gain 1, the controller's `tc` output); the
equation-block partner is `rrr-torque`. A clean comparison needs the plants to be the only
difference, and the motors cannot be shared: a rotor inertia rigidly coupled to the multibond
joint's rate is derivative-causal with the body inertia, and the multibond arm behind the `DCMotor`
-> `IdealGear` chain compiled with W201 on every body momentum and then stopped at t = 0 with E901
(retcode `Unstable`), measured. The closed loop pulls both arms to the same references, so the
comparison is of the dynamics under the same feedback, not of two open-loop integrations.

**Tolerance.** The difference between the models is the compliance of the held directions (and the
1e-8 point-mass inertias), an O(1/k) effect: the static sag `m g / k` of the held translations (3
to 4e-6 m at `k = 1e7`) moves the masses by a fraction of a link length. `max|dq|` over the whole
5 s motion (`compare` entries of `expected.json`, bound `C_i / k` with `C = 820, 500, 250 N m/rad`,
5x the measurement at `k = 1e7`):

| `k` (N/m, N m/rad) | joint 1 | joint 2 | joint 3 |
| --- | --- | --- | --- |
| 1e6 (`rrr-multibond-soft`) | 1.11e-4 | 4.4e-5 | 2.7e-5 |
| **1e7** (`rrr-multibond`) | **1.64e-5** | **1.00e-5** | **4.98e-6** |
| 1e8 (`rrr-multibond-stiff`) | 1.81e-6 | 1.32e-6 | 6.7e-7 |

The error falls with `k` (ratios of 4 to 9.5 per decade; the soft case carries second-order terms,
and the largest joint-2/3 values sit in the first millisecond, when the arm is released and the
controller's first command is still to come). From 0.1 s on, joints 2 and 3 differ by 2.4e-5 /
2.7e-5, 4.0e-6 / 3.5e-6 and 5.4e-7 / 4.3e-7 rad at the three stiffnesses. The settled values agree
to 1e-8 rad.

## 3D scene

`scenes/rrr.sdf` (SDF subset of plan 7.6, Z-up, metres): a base cylinder, a turret link (the joint-1
rotation carrier, with a small counterweight so the yaw is visible), an upper-arm box and a forearm
box, with small spheres marking the point masses. `joint1` axis `0 0 1`; `joint2` and `joint3` axis
`0 -1 0` (rotating +x toward +z is a rotation about -y). Every `rrr*` model sets
`"scene": {"file": "scenes/rrr.sdf"}` and binds `joint:joint1..3` `position` to its angles
(`Arm/q1..q3`, or `J1..J3/qout` in the multibond models, unit rad). The scene was checked with the
viewer's own parser and resolver (`web/src/scene`): no diagnostics, tip at (0.7, 0, 0) for q = 0,
(0, 0, 0.7) for `q2 = pi/2` and (0, 0.7, 0) for `q1 = pi/2`.

## Files (X5.3)

* `models/rrr.bgmodel.json`, `rrr-free`, `rrr-torque`, `rrr-multibond`, `rrr-multibond-soft`,
  `rrr-multibond-stiff` — the models (written by `design/build_models.py`).
* `library/ArmDynamics3R.jl`, `library/ArmCtrl3R.jl` — the equation block and the 1 ms firmware.
* `design/design.py`, `design/build_models.py` — references, gains, the numpy replica, model writer.
* `scenes/rrr.sdf` — the 3D scene.
* `expected.json` — extended additively: the 43 X-MB3 checks are unchanged; X5.3 adds the `rrr`,
  `rrr-free`, `rrr-torque` and `rrr-multibond*` checks and nine `compare` entries.
* `web/tests/e2e/robot-arm-3r.spec.ts` — opens the sample, runs `rrr`, plots `Arm/q1..q3` and reads
  the angles after each move (real worker). The 3D-playback part is added after W5.3.
