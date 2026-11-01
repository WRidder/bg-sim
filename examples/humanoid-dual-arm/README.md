# humanoid-dual-arm — two 7-DOF SRS arms hold one box: damped-least-squares IK, elbow self-motion, the 6-DOF failure

A humanoid torso with two stacked 7-DOF SRS arms (shoulder pitch, roll, yaw; elbow; forearm
yaw; wrist pitch, roll) with real shoulder and wrist offsets. Both hands grasp one box. The
1 kHz firmware moves the box along a commanded pose. A damped-least-squares IK with a
null-space pull toward home resolves each arm, and an elbow bias swings the elbows while the
box stays put. Two models:

* **`humanoid-ik`**: the firmware alone, kinematic and fast (11 s per run). The object
  trajectory drives four IK blocks: the stacked robot arms and, 1 m to the robot's right, an
  ideal SRS pair (zero shoulder and wrist offsets) for comparison. The dashboard mirrors the
  interactive page. Sliders set the object x/y/z/roll/pitch/yaw and the elbow bias, and a toggle
  locks J5 (6-DOF arms). The readouts show the hand pose error (mm, deg) and the nearest joint
  limit (%), with plots of the joint angles.
* **`humanoid-hold`**: the same firmware on the **dynamic** robot. Two multibody arms
  (`Revolute3D`, `RigidBody3D`, illustrative masses) are driven per joint by a bond-graph drive
  (motor, rotor inertia, elastic gear with a torque sensor, joint friction) under PID servos.
  They carry the 1.5 kg box on two stiff grasp springs.

```
Traj (ObjectTrajectory) ──obj──► IKL, IKR (stacked)  ──qr1..7──► ServoL/ServoR (PID) ──u1..7──► drives
                         └─obj─► IdealL, IdealR (ideal SRS, kinematic, drawn beside the robot)
Traj.g ──► BoxError ◄── BoxPose (simulated box)          LHandError, RHandError: hand vs grasp target

per arm p ∈ {L, R}:   WorldP ─ MountP ─ pJ1 ─ pLink1 ─ pBJ1 ─┬─ pB1 (RigidBody3D)
                                                            └─ pT2 ─ pJ2 ─ ... ─ pJ7 ─ pLink7 ─ pBJ7 ─ pB7
drive k:  pMotork (MSe) ─► 1 [pRotork: I] ─► 0 [pTauSensek: De] ─► 1 [pSpringk: C, pDamperk: R]
          ─► 1 [pFrictionk: R] ─► pJk.drive
grasp:    pBJ7 ─ pTip ─ pWeld (Revolute3D, all six directions sprung) ─ pGrip ─ BoxJ ─ Box (RigidBody3D)
```

Everything is generated from `design/` (Python, run with `uv`):

| file | what |
| --- | --- |
| `design/srs.py` | the page's kinematics and IK in numpy: chain, offsets, limits, home, grasp, the IK the way the page runs it (1 deg finite-difference Jacobian, 8 iterations per frame); the bg-sim world mapping |
| `design/humanoid.py` | the task (timing, start pose, bias), masses, drives, servo gains, statics; the Python **twin** of the firmware (`twin`) |
| `design/build_library.py` | `library/ObjectTrajectory.jl`, `ArmIK.jl` (generated scalar code), `ArmServo.jl`, `PoseError.jl`, `GraspLoad.jl` |
| `design/build_models.py` | `models/humanoid-ik.bgmodel.json`, `models/humanoid-hold.bgmodel.json` (diagram, plots, dashboard, 3D bindings) |
| `design/build_scene.py` | `scenes/humanoid.sdf` |
| `design/references.py` | `design/references.json`: the reference numbers (page IK, twin, forward kinematics), no bg-sim involved |
| `design/build_expected.py` | `expected.json` from the references and four measured runs |
| `design/run_model.jl` | runs one model in Julia without the backend (timings, overrides) |
| `design/compare_twin.py`, `inspect_run.py` | development aids: in-model IK vs twin, a run summary |

## Sources

The interactive page `humanoid_dual_arm_srs.html` (a kinematic three.js demo), read as a
specification. Every number below comes from its source:

* the chain: joint axes x z y x y x z of the current frame (pitch, roll, yaw, elbow pitch, forearm
  yaw, wrist pitch, wrist roll), a pitch joint turns by −q on both arms, the others by s·q
  (s = +1 the left arm, −1 the right arm: a mirror image);
* the offsets after each joint (m), stacked arm: (0, −0.06, 0.025), (0, −0.06, −0.025), (0, −0.26, 0),
  (0, −0.04, 0.02), (0, −0.20, −0.02), (0, −0.04, 0.02), (0, −0.09, 0). Ideal SRS: upper arm 0.38,
  forearm 0.28, hand 0.09, no shoulder or wrist offsets;
* the limits (deg): J1 −60..180, J2 −20..120, J3 −90..90, J4 0..140, J5 −90..90, J6 −60..60,
  J7 −90..90; the home posture (25, 12, 0, 70, 0, 0, 0) deg; the shoulder bases at (±0.2, 0.25, 0) m;
* the object: a 0.28 × 0.10 × 0.10 m box, default pose (0, −0.1, 0.4) m with zero roll, pitch and
  yaw, rotation Ry(yaw) Rx(pitch) Rz(roll); the hands grasp its ends at ±0.14 m, palms facing inward;
* the IK: the error is target − current, with position in m and orientation as 0.5·rw·Σ cᵢ × tᵢ
  (rw = 0.3 m/rad). The Jacobian is taken per degree. y = (JJᵀ + 10⁻⁵ I)⁻¹ e, z = 0.1 (home − q),
  v = (JJᵀ + 10⁻⁹ I)⁻¹ J z and d = z + Jᵀ (y − v). The page clamps d to ±8° and q to the limits,
  and runs 8 iterations per animation frame. The **elbow bias** is added to the shoulder-yaw home
  angle, mirrored by s;
* the readouts: position error in mm, orientation error asin(|e_rot|/rw) in deg, and the nearest
  limit as the smallest distance to a limit over the joint range (%). The pose counts as held below
  2 mm and 2°;
* the 6-DOF variant: J5 (forearm yaw) locked at 0.

Page frame: x right (the robot's left), y up, z forward. bg-sim world (Z up, the robot faces +X):
(X, Y, Z) = (page z, page x, page y + 1 m).

The page is kinematic. Everything dynamic is a **design choice of this example** and is
**illustrative**: the masses (a 7 kg arm of solid cylinders: 1.0, 1.0, 2.0, 0.8, 1.2, 0.4, 0.6 kg
for links 1-7), the box mass (1.5 kg), the drives, the servo gains and the grasp stiffness.

## How the IK and the redundancy work

A rigid grasp fixes the full pose of each hand (3 position + 3 orientation), so two hands on one
object give **12 constraints**. Two 7-DOF arms have **14 joints, 2 left over**: one self-motion
per arm, where the elbow swings about the shoulder-wrist line while the hand stays put.

`ArmIK` runs the page's damped least squares once per 1 kHz tick, warm-started from its last
solution. The task step `Jᵀ y` drives the hand error to zero. The pull `z` toward home is
projected out of the task space (`z − Jᵀ v` ≈ the null-space part of z), so it moves only the
self-motion: it picks, among the infinitely many postures that hold the box, the one closest to
home. The **elbow bias** shifts the home of the shoulder yaw. The null-space pull then swings the
elbow to the new posture, and the hand error stays at the micrometre level (0.006 mm) the whole
time. With bias 30° the left elbow moves 47 mm and the right elbow 52 mm. The page adds s·bias
and the yaw joint turns by s·q, so both elbows swing to the same side of the robot (the left one
inward, the right one outward).

Lock J5 (6-DOF) and there are **12 joints for 12 constraints: no slack**. The object pose alone
fixes both postures, and the elbow bias does nothing. At the page's default pose the stacked
arms run into J3 = −90° and J6 = −60° and miss the grasp by 3.5 mm and 3.3°. The ideal SRS arms
(no offsets) still reach it within 0.96 mm and 0.77°: the shoulder and wrist offsets break the
6-DOF arm, and the seventh joint absorbs them.

bg-sim specifics of the block:

* **Exact Jacobian.** Where the page takes a 1° finite difference, `ArmIK` uses the exact derivative of
  the page's error (generated scalar code, checked against a central difference to 5·10⁻¹¹). The
  two Jacobians differ slightly, so the solutions differ by up to 0.2° (stacked) and 0.4°
  (ideal) per joint; the errors agree within 10⁻⁴ mm.
* **Generated Cholesky solves.** The two 6×6 solves are generated Cholesky factorisations. The
  language spec offers `A \ b`, but the compiler rejects `\` on arrays (see
  [Limitations](#limitations)).
* **Rate limit.** One iteration per tick at 1 kHz is the page's 8 iterations per frame, slower.
  The step is **scaled down as a whole** to at most 0.05° per joint and tick (50°/s), where the
  page clamps each joint to ±8°. Scaling keeps the direction of the step, so a fast self-motion
  stays in the null space. A per-joint clamp bends the step out of it, and at the start the hands
  then left the box by 20 mm while the servos saturated. The fixed points are the page's.
* **Lock.** With the lock (`obj[8] = 1`) J5 is held at 0 and its Jacobian column is masked.

## Parameters

| quantity | value | note |
| --- | --- | --- |
| firmware period | 1 ms | `ObjectTrajectory`, `ArmIK`, `ArmServo` |
| scenario | settle 1.5 s, move 1.5 s (quintic), dwell 1.0 s, bias ramp 1.5 s (quintic, 0 → 30°), hold 1.0 s | 6.5 s |
| start pose | (0, −0.20, 0.35) m, rpy 0 | chosen so that the **6-DOF** stacked arms hold it exactly: both variants start from one posture (J = 30.02, 28.99, −90.00, 83.36, 0, −54.37, 59.98 deg) |
| commanded pose | the page default (0, −0.1, 0.4) m, rpy 0 | dashboard sliders |
| link masses | 1.0, 1.0, 2.0, 0.8, 1.2, 0.4, 0.6 kg | **illustrative**, solid cylinders along the segment |
| box | 1.5 kg, 0.28 × 0.10 × 0.10 m | |
| joint compliance (held directions) | 10⁶ N/m, N·m/rad, 0.7 of critical | `Revolute3D` |
| reflected rotor inertia | 0.2 (J1-J4), 0.05 (J5-J7) kg·m² | **assumed** |
| gear stiffness | 10⁴ (J1-J4), 2·10³ (J5-J7) N·m/rad, damping ratio 0.3 | **assumed** |
| joint friction | 0.5 N·m·s/rad | **assumed** |
| torque limit | 80 (J1-J4), 20 (J5-J7) N·m | **assumed** |
| servo | PID with ωn = 20 (J1-J4), 25 (J5-J7) rad/s, ζ = 0.8 on the rotor + link inertia, integral ωn/5, feedforward the holding torque of the start | `ArmServo` |
| grasp | 10⁵ N/m, 10³ N·m/rad in all six directions | **assumed** |

The drive springs start preloaded with the holding torque of the start posture (statics of the
arm with half the box weight on each hand), so nothing jumps at t = 0.

## Validation

`expected.json` (generated by `design/build_expected.py`) runs four scenarios:
`humanoid-ik`, `humanoid-ik-6dof` (`humanoid-ik` with `Traj/dof6 = true`), `humanoid-hold` and
`humanoid-hold-6dof`. The expected values come from `design/references.json`: the page's IK
(`srs.solve`, numpy), the twin of the firmware (`humanoid.twin`) and the forward kinematics, never
from the runs. The runs set only the tolerances (5× the measured deviation, with a floor).

| check | reference | bg-sim (measured) |
| --- | --- | --- |
| in-model IK vs its numpy twin, every tick, all four arms, 7-DOF and 6-DOF | `humanoid.twin` | max \|Δq\| 4.4·10⁻¹⁴ deg, \|Δpe\| 3·10⁻¹³ mm |
| 7-DOF at the default pose (bias 0): pe, oe, nearest limit | page: 0.0053 mm, 0.0010°, 9.7 % (J5) | 0.0052 mm, 0.00096°, 9.6 % (J5) |
| 7-DOF joints vs the page's solution | page `srs.solve` (finite-difference Jacobian) | ≤ 0.20° stacked, ≤ 0.41° ideal |
| 7-DOF holds through dwell and bias sweep (all four arms) | page limit 2 mm, 2° | peak 0.006 mm, 0.001° |
| elbow self-motion under bias 30° | twin | left elbow moves 47.1 mm, right 52.4 mm; \|Δ\| to the twin < 10⁻¹⁶ m |
| 6-DOF at the default pose: pe, oe | page 3.468 mm, 3.349° | 3.535 mm, 3.348° (twin equal to 10⁻¹³) |
| 6-DOF joints | J3 = −90°, J6 = −60° (limits), J5 = 0 | exactly; nearest limit 0 %, held off |
| 6-DOF: the bias does not move the elbow | twin | shift < 6·10⁻⁷ m |
| 6-DOF ideal SRS still holds | page 0.960 mm, 0.772° | 0.970 mm, 0.771°, held on |
| forward kinematics of the start posture (hands, left elbow, box) through the multibody pose chain | `srs.fk` in the bg-sim world | ≤ 2.2·10⁻¹⁶ |
| dynamic 7-DOF: box and hands within the hold limit over the whole run | 2 mm, 2° | box peak 1.35 mm, 0.18°; hands 1.29 mm, 0.19° |
| dynamic 7-DOF: simulated left elbow vs the twin's IK elbow (bias 0 and 30°) | twin | ≤ 0.23 mm |
| dynamic 7-DOF: joints follow the IK command over the whole run | | ≤ 0.68° (J5) |
| dynamic 7-DOF: grasp load at the dwell | half the box weight 7.36 N | 8.52 N |
| dynamic 7-DOF: servo torques | limits 80 / 20 N·m | peak 12.6 N·m (J1) |
| dynamic 6-DOF: the hands miss the grasp target | page: not held | ≥ 4.37 mm, ≥ 1.08° after the move |
| dynamic 6-DOF: the arms fight through the box | (7-DOF: 8.5 N, 0.4 N·m) | grasp force up to 109 N, moment 31 N·m; the J6 servo saturates at 20 N·m from t = 5.09 s and the wrist is pushed 1.6° past its −60° limit |
| power continuity of the bond graph (`energy_ledger`) | Tellegen residual | within 10⁻⁶ of the throughput |
| scene bindings, plots and dashboard signals, no diagnostics | | |

The page's IK uses a finite-difference Jacobian and runs from home to rest. The twin uses the
exact Jacobian and the scenario trajectory. The page solution therefore checks the result to
within 0.4° and 0.07 mm, and the twin checks it to round-off.

Run them with:

```powershell
uv run examples/run_checks.py --only humanoid-dual-arm
```

## Timings

Reference machine (Windows 11), Julia 1.13:

| model | solver | flatten | compile + init | solve | total |
| --- | --- | --- | --- | --- | --- |
| `humanoid-ik` | Tsit5 (no continuous states) | 1.5 s | 7 s | 3.4 s | 11 s |
| `humanoid-hold` | FBDF, reltol 10⁻⁴, abstol 10⁻⁶ | 2.5 s | 34 s | 31 s | 66 s |

`humanoid-hold` has 46 states and 6416 equations. Rodas5P at 10⁻⁶ / 10⁻⁸ takes 18.6 ms per step
(about 7 minutes for the run). FBDF at 10⁻⁴ / 10⁻⁶ agrees with it within 0.003° per joint over the
first 0.3 s, at a tenth of the cost.

## 3D view

`scenes/humanoid.sdf` has two torsos (pedestal, body, shoulders, head). The robot stands at the
origin: the left arm is blue, the right arm orange and the box purple, with a translucent box at
the commanded pose. The ideal-SRS pair (green, with its own box) stands 1 m to its right. Every
arm is a URDF-style tree of seven revolute joints bound to the joint angles: `LJk/qout` and
`RJk/qout` in `humanoid-hold`, `IKL/qrk` … in `humanoid-ik`. The viewer composes the arms itself.

## Limitations

* **`A \ b` on arrays is rejected.** The language spec (table "Linear algebra": "`\` via fixed-size
  LU") offers `A \ b` in all scopes. The compiler (`julia/BGSim/src/compile/instantiate.jl`,
  `the \ operator needs scalar operands`, E004) accepts only scalars. `ArmIK` works around it with
  generated Cholesky solves. This is not fixed in core: it is a spec/compiler mismatch to settle
  separately.
* **Units on angles in degrees.** A parameter declared `unit = "deg"` that meets a `rad` quantity is
  rejected (E006 "differ only in scale"), and `"%"` is not a valid unit. The degree-valued
  parameters and readouts of the blocks carry no unit attribute; the descriptions name the unit.
* **No joint hard stops in the dynamic model.** The IK clamps its solution to the limits, but the
  `Revolute3D` joints have none. In the 6-DOF hold the grasp pushes the saturated wrist 1.6° past
  its limit.
* **Illustrative dynamics.** The masses, drives and grasp are assumptions, not a particular robot.
* **The first firmware tick is at t = Ts.** Until then the IK outputs hold the start posture (node
  starts).

## Regenerating

```powershell
uv run examples/humanoid-dual-arm/design/srs.py            # page kinematics report and self checks
uv run examples/humanoid-dual-arm/design/humanoid.py       # design report and self checks
uv run examples/humanoid-dual-arm/design/build_library.py
uv run examples/humanoid-dual-arm/design/build_scene.py
uv run examples/humanoid-dual-arm/design/build_models.py
uv run examples/humanoid-dual-arm/design/references.py     # design/references.json (about 1 min)
# four runs (the 6-DOF ones with an overrides file {"Traj/dof6": true}):
julia --project=julia/BGSim examples/humanoid-dual-arm/design/run_model.jl humanoid-ik <dir>/ik
julia --project=julia/BGSim examples/humanoid-dual-arm/design/run_model.jl humanoid-ik <dir>/ik6 - dof6.json
julia --project=julia/BGSim examples/humanoid-dual-arm/design/run_model.jl humanoid-hold <dir>/hold
julia --project=julia/BGSim examples/humanoid-dual-arm/design/run_model.jl humanoid-hold <dir>/hold6 - dof6.json
uv run examples/humanoid-dual-arm/design/build_expected.py --ik <dir>/ik --ik6 <dir>/ik6 --hold <dir>/hold --hold6 <dir>/hold6
uv run tools/example_docs/build.py --only humanoid-dual-arm
```
