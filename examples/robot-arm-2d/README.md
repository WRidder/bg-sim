# robot-arm-2d — the planar 2-link arm on the M3 multibond mechanics

A two-link planar arm with a payload, driven by a 1 ms PD + gravity-feedforward
controller, built from the J-MB6 composites (`RigidBody2D`, `Revolute2DCompliant`,
`JointPose2D`, `LocalPose2D`) and the J-MB5 planar primitives (`ComposePose2D`,
`GravityPlanar`, `CoriolisPlanar` — the last two inside the body composite). It is
the planar-multibond arm of plan 9.10 / X-MB2, and together with
`reaction-wheel-2d` it is Gate B's arm-and-balancer pair.

```
Ground ── Joint1 ── Link1 ── BodyJ1 ─┬─ Body1 ── (1-junction: I + Coriolis + Gravity + Df)
         (kt, bt)   (0.2 m)  (1-junc) └─ Joint2 ── Link2 ── Body2
                            (rx = 0.2)  (kt, bt)   (0.2 m)  (link 2 + payload)
                              ▲            ▲
        Drive1: MSe(u1) ──────┘            └────── MSe(u2) :Drive2
                              ▲
        Joint1.pose ──► PoseJ1 ──► PoseB1 ──► Body1.g / PoseJ2 ──► PoseB2 ──► Body2.g
                                    └──────► PoseJ2 ──► PoseTip (end effector 0.3 m)
Ref1/Ref2 (Step at 0.2 s) ──► ArmPD (1 ms) ──► u1, u2
```

## The physics

Each link is a **3-DOF planar body** (`RigidBody2D`: the port is the body
1-junction with `IPlanar`, `CoriolisPlanar`, `GravityPlanar` and a zero-power
`DfPlanar` tap), attached to a **compliant-pivot revolute joint**. A rigid revolute
on a rigid 3-DOF body is index-3 — the two pivot translations are hard constraints
— so the joint is the `Revolute2DCompliant` variant of DEC-MB-2: the rotation is
exact (`q` is the link-side angle) and the two pivot translations are spring states
`d` with `kt`/`bt`. Every state stays integral (no `W201`). The second joint's
pivot is the **elbow**, expressed as `rx = 0.2 m` in the link-1 centre-of-mass
frame (the frame its parent port is bonded to).

The **poses are composed, never integrated** (D-MB6): `JointPose2D` turns the joint
angle into the SE(2) chart `(q, 0, 0)`, `LocalPose2D` holds the constant link
offsets, and `ComposePose2D` multiplies them. The chain mirrors the power chain
exactly:

| pose | composition | meaning |
| --- | --- | --- |
| `PoseJ1` | `JointPose2D(q1)` | link-1 base frame |
| `PoseB1` | `PoseJ1 ∘ (0.2, 0, 0)` | body-1 centre of mass → `Body1.g` |
| `PoseJ2` | `PoseB1 ∘ JointPose2D(rx = 0.2, q2)` | joint-2 child frame (link 2) |
| `PoseB2` | `PoseJ2 ∘ (0.2, 0, 0)` | body-2 centre of mass → `Body2.g` |
| `PoseTip` | `PoseJ2 ∘ (0.3, 0, 0)` | end effector → `PoseTip/g[2..3]` |

`GravityPlanar` reads `Body.g`, so the gravitational wrench acts at the true
centre of mass; `CoriolisPlanar` gets the inertia's momentum tap `Pm` and applies
Breedveld's `e = −ad(V)ᵀP`, so no inertia is copied out of the body (D-MB3). The
composed pose is an exact algebraic function of the measured angles, which is what
the `planar_fk` check proves: `PoseTip/g[2..3]` equals
`0.4 cos q1 + 0.3 cos(q1+q2)` and the same in `y` to **1.1e-16 m**.

The **drive** is a `Rotation` `MSe` on each joint. The 1 ms `ArmPD` block (project
library) is

```
e_i = ref_i − q_i
G_1 = g0 (m1 lc1 cos q1 + m2 (L1 cos q1 + lc2 cos(q1+q2)))
G_2 = g0 m2 lc2 cos(q1+q2)
u_i = clamp(Kp_i e_i − Kd_i qd_i + G_i, −u_i_max, u_i_max)
```

`G` is the gravity torque about each joint at the sampled configuration, so the
settled error is zero instead of the PD droop `G/Kp`; the derivative acts on the
measurement, so the reference step produces no derivative kick; `clamp` inside
`@discrete` is generated code, not a symbolic `ifelse`, so the torque limit creates
no event. `Kp = 250 / 30 N·m/rad`, `Kd = 26 / 3 N·m·s/rad` give a closed-loop
bandwidth of about 3 Hz with both modes near critical damping, and the limits are
`30 / 10 N·m`.

The arm starts at `q = 0` (horizontal) at rest, held by the feedforward. At
`t = 0.2 s` the references step to `q1 = 0.6 rad`, `q2 = −0.4 rad`; the shoulder
saturates at its 30 N·m limit for about 0.1 s and both joints settle.

### Pivot damping

`kt = 1e8 N/m` puts the pivot's translational mode at `sqrt(kt/m) ≈ 1.6 kHz`,
above the 1 ms controller. Without damping the drive's torque steps pump that
undamped mode: `d` grows from 3e-7 m to 1e-4 m and the run ends in **E901
(MaxIters) at t = 2.54 s**. The driven model therefore uses `bt = 1e3 N·s/m`
(ζ = 0.027), which is enough. The **torque-free** model keeps `bt = 0` so its
energy budget is conservative.

## Parameters

| parameter | value |
| --- | --- |
| link 1 | `L1 = 0.4 m`, `lc1 = 0.2 m`, `m1 = 2 kg`, `J1 = m1 L1²/12 = 0.02667 kg·m²` |
| link 2 + payload | `L2 = 0.3 m`, `lc2 = 0.2 m`, `m2 = 1.5 kg`, `J2 = 0.015 kg·m²` |
| payload | 0.5 kg at the tip: 1.0 kg rod → `I_elbow = 0.03`, payload → `0.045`; combined CoM 0.2 m, `J_com = 0.075 − 1.5·0.2² = 0.015` |
| pivots | `kt = 1e8 N/m`, `bt = 1e3 N·s/m` (driven) / `0` (free) |
| reference | `q1: 0 → 0.6 rad`, `q2: 0 → −0.4 rad` at `t = 0.2 s` |
| controller | 1 ms, `Kp 250 / 30`, `Kd 26 / 3`, limits `30 / 10 N·m` |
| gravity | `g0 = 9.81 m/s²` |
| run | 3 s, 3001 output points, `reltol 1e-9`, `abstol 1e-11` |

## The flat graph

Every box is a documented primitive, a joint/body composite or a junction; the
body composite opens to `Junction + IPlanar + CoriolisPlanar + GravityPlanar +
DfPlanar`, so no opaque body hides equations.

| instance | block | role |
| --- | --- | --- |
| `Ground` | `stdlib:multibond/GroundPlanar` | world flow source (`f = 0`) |
| `Joint1` | `stdlib:planar/Revolute2DCompliant` | shoulder: exact `q1`, compliant `d` (`kt`, `bt`), zero torsional spring |
| `Link1` | `stdlib:planar/FixedJoint2D` | joint-1 child → link-1 centre of mass (`x = 0.2 m`) |
| `BodyJ1` | 1-junction | common link-1 twist: `Link1`, `Body1` and the elbow joint |
| `Body1` | `stdlib:planar/RigidBody2D` | `m = 2`, `J = 0.02667`; **its port is the body 1-junction** |
| `Joint2` | `stdlib:planar/Revolute2DCompliant` | elbow: `rx = 0.2 m` in the link-1 CoM frame |
| `Link2` | `stdlib:planar/FixedJoint2D` | joint-2 child → link-2 centre of mass |
| `Body2` | `stdlib:planar/RigidBody2D` | link 2 + payload: `m = 1.5`, `J = 0.015` |
| `PoseJ1`, `PoseB1`, `PoseJ2rel`, `PoseJ2`, `PoseB2`, `PoseTip` | `JointPose2D` / `LocalPose2D` / `ComposePose2D` | the composed fixed-base pose chain |
| `Drive1`, `Drive2` | `stdlib:bondgraph/MSe` | drive effort from the controller (`gain = 1`) |
| `Ref1`, `Ref2` | `stdlib:sources/Step` | the reference step at 0.2 s |
| `Ctrl` | `project:ArmPD` | the 1 ms PD + gravity feedforward firmware |

`ArmPD` is the only non-bond-graph part: sampled firmware, the D28 exception.
`Se e = 0` on both drives is the torque-free model (`arm-free`).

## The two-stroke visual

Section 7 of the plan: the stroke count encodes the **model dimension**, not the
port size. Every `Power{Planar}` bond — `Ground–Joint1`, `Joint1–Link1`,
`Link1–BodyJ1`, `Body1–BodyJ1`, `Joint2–BodyJ1`, `Joint2–Link2`, `Link2–Body2` —
is a **two-stroke bundle** with one half arrow per stroke and **one** causal bar
across the bundle (`data-multibond-strokes="2"`, two
`.editor-edge__multibond-stroke` paths, one `causal-stroke-<id>`). The drive bonds
(`MSe → drive`, a `Rotation` port) stay single-stroke. The editor derives the count
from the connection domain; the model document has no visual field.

## Measured (this example, the real worker)

| quantity | value |
| --- | --- |
| `q1`, `q2` at `t = 3 s` | **0.600000000002**, **−0.3999999999998** rad |
| settled error | `max|e1| = 4.9e-9`, `max|e2| = 2.0e-8` rad over `[2, 3] s` |
| 1 mrad settle time | **0.63 s** after the step (`e1` last outside at 0.829 s, `e2` at 0.875 s) |
| peak joint torque | **30.000 N·m** (shoulder, at its limit) and **9.061 N·m** (elbow) |
| peak joint rate | 3.158 rad/s (`q1`), 5.056 rad/s (`q2`) |
| tip at `t = 3 s` | **(0.6241542193, 0.2854577886) m**, angle 0.2 rad |
| analytic FK of `(0.6, −0.4)` | `0.4 cos 0.6 + 0.3 cos 0.2 = 0.6241542193`, `0.4 sin 0.6 + 0.3 sin 0.2 = 0.2854577886` |
| pose chain vs FK, whole run | **max 1.11e-16 m** (x), **1.11e-16 m** (y) |
| torque-free energy drift (3 s) | **5.82e-6 J = 3.09e-7** of the **18.877 J** swing |
| states / equations | 12 differential states (2 × P[3], 2 × d[2], 2 × q), no `W201` |
| run cost | 54 899 adaptive steps (driven, 6 003 rows incl. the 1 ms tick pairs), 262 891 (free) |
| diagnostics | none (`W201`, `E101`, `E102`, `E103`, `E106`, `W206` absent) |

`arm-free` is the same plant with `Se e = 0` on both drives, `bt = 0`, and the
initial pose `q1 = 0.6`, `q2 = −0.4` at rest with relaxed pivot springs (`d = 0`).
It falls under gravity; the energy budget is

```
E = Σ_i [ ½ P_iᵀ M_i⁻¹ P_i + m_i g h_i ] + Σ_j ½ kt |d_j|²
h_i = pose_y,i + sin(q₁) d₁ + cos(q₁) d₂ [+ sin(θ₂) e₁ + cos(θ₂) e₂ for link 2]
```

with `θ₂ = PoseJ2/g[1] = q1 + q2` (the absolute angle of the joint-2 child frame)
and the swing being the potential drop from the start pose to the hanging pose,
`6.1238265 − (−12.7530) = 18.8768265 J`.

## Checks (`expected.json`)

`arm`: the two joint angles reach the reference within 1e-6 rad; the errors are
below 1e-6 rad over the last second and below 1 mrad from 0.9 s; the drive
efforts stay inside 30 / 10 N·m; `planar_fk` holds to 1e-6 m over all 6 003
samples; the tip passes through the measured cursor points at 0.3 / 0.5 / 1.0 s
(2 mm) and lands on the analytic FK at 3 s (1e-6 m); no diagnostics.
`arm-free`: the start pose, the same FK check, the multi-body energy drift
(`tol 1e-6` of the swing) and no diagnostics.

## Run it

```
uv run bgsim
```

then **Open** (Ctrl+O) → **Samples** → **robot-arm-2d** (imports a copy), press
**Run**, and open **Plots**: “Joint angles and the 0.6 / −0.4 rad reference step”,
“Joint torque”, “End-effector position”, “Joint rates”. The acceptance checks run
every example through the real worker:

```
uv run examples/run_checks.py
```

and the browser acceptance (real worker, two-stroke bonds, run, plot, screenshot):

```
cd web
$env:BGSIM_E2E_REAL="1"; npx playwright test tests/e2e/robot-arm-2d.spec.ts --workers=1
```

## What to try

- Set `Ctrl/g0` to 0: the gravity feedforward disappears and the shoulder droops
  to `G1/Kp1 = 10.98/250 ≈ 0.044 rad` (**measured 0.5549 rad** at the reference,
  with the elbow at −0.4979) — the `cursor_value` check at 3 s fails, which is the
  intended signal that the feedforward is doing the holding.
- Set `Ctrl/u1max` to 5 N·m: the arm can no longer hold the reference against
  gravity (the static demand is 10.98 N·m) and the same check fails, which is the
  intended signal that the actuator is undersized.
- Set `Joint1/bt` to 0 (and `Joint2/bt`) and rerun: the fast pivot mode is pumped
  by the 1 ms drive and the solver stops with `E901` (MaxIters) at t = 2.54 s
  (the note above).

## Notes for the next work packages

- **J-MB6 limitation found while building this example.** A `FixedJoint2D` with a
  lever arm (`x ≠ 0`) on a body's 1-junction leaves two algebraic unknowns
  (`Elbow/child.f[2]`, `Elbow/parent.e[2]`) in the compiled mass-matrix DAE. Their
  `u0` entries are NaN (no default and no start), so the run dies at `t = 0` with
  `E901`. The same topology with the offset in the joint's `rx` parameter compiles
  to 12 differential states and runs. This example therefore uses `rx` (which the
  X-MB2 brief explicitly allows); the balancer does the same for the wheel axis.
- The 1 ms controller turning the undamped 1.6 kHz pivot mode unstable is a
  physical/sampled-data effect, not a compiler bug; `bt` is the engineering
  answer and the note above records the failure without it.

## 3D view

`scenes/robot-arm-2d.sdf` draws the two links in the vertical X-Z plane (the model's x-y plane). Joints `shoulder` and `elbow` follow `Joint1/qout` and `Joint2/qout`; the tip sphere sits at the model's end-effector pose (`PoseTip`), which `expected.json` checks against the SDF kinematics along the whole run.
