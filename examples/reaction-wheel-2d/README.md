# reaction-wheel-2d — the planar reaction-wheel balancer

An inverted planar body on a compliant pivot with a reaction wheel on its axis: a
1 ms PD on the body angle commands the wheel torque, and the wheel's reaction holds
the body upright while it spins up. It is the planar-balancer half of X-MB2 (plan
9.10) and Gate B's arm-and-balancer pair with `robot-arm-2d`.

```
Ground ── Pivot ── LinkB ── BodyJ ─┬─ Body  (RigidBody2D, m 1.5, J 0.02, CoM 0.3 m)
         (kt, bt)  (0.3 m) (1-junc) └─ WheelJ ── Wheel (RigidBody2D, J 0.002)
                          (rx = 0.2)   (kt, bt)   (its centre on the axis)
                              ▲
       Motor: MSe(tau) ───────┘
       Pivot.pose ──► PoseJ1 ──► PoseB ──► Body.g / PoseW ──► Wheel.g
       Ref (Pulse 0.012 rad, 0.5–1.5 s) ──► Balancer (1 ms) ──► tau
```

## The physics

The body is a 3-DOF planar rigid body on the compliant-pivot revolute (`kt = 1e9
N/m`, `bt = 5e3 N·s/m`); the wheel is a second `RigidBody2D` on a second compliant
revolute whose axis is 0.5 m above the pivot (the body CoM frame offset
`rx = 0.2 m` plus the 0.3 m CoM). The body frame's `x` axis points along the link,
so the composed body angle is `θ = q + π/2` and the wheel's absolute rate is
`θ̇ + q̇_w`.

With the motor torque `τ` on the wheel, the reaction `−τ` acts on the body:

```
J_A' θ̈ = −τ + G sin θ          J_A' = J_b + m_b lc_b² + m_w L_w²
J_w (θ̈ + q̈_w) = τ
```

The **total angular momentum about the pivot** is therefore

```
H = J_A θ̇ + J_w q̇_w ,   J_A = J_A' + J_w = 0.257 kg·m²,  J_w = 0.002 kg·m²
```

and with gravity off the motor torque is internal, so `H` is constant — the
`invariant` check of the `balancer-free` variant.

The controller (project library `Balancer`, 1 ms) is

```
e   = theta − ref
tau = clamp(G sin(theta) + Kp e + Kd thetadot, −1.5, 1.5),   G = g0 (m_b lc_b + m_w L_w) = 6.3765 N·m
```

`G sin θ` is the gravity torque about the pivot, so the settled angle equals the
reference (no droop) and the closed loop is `J_A' θ̈ = −Kp e − Kd θ̇` — stable for
any positive gains. `Kp = 16`, `Kd = 4` give `ω ≈ 7.9 rad/s` and a damping ratio of
1.0. The reference is a `Pulse` of 0.012 rad from 0.5 s to 1.5 s (period 4 s, so
only one pulse is inside the 3 s run).

**Gravity-on variant (`balancer`).** The body starts 0.01 rad off upright, the
controller recovers it in about 0.5 s, then the 0.012 rad pulse tilts it and it
returns. The wheel spins up to **47.05 rad/s** and keeps **46.21 rad/s**: the
gravity torque has delivered a net angular impulse (6.3765 ∫sin θ dt) that the
wheel must store. That is the momentum-management story a real reaction wheel has
to unload.

**Gravity-off variant (`balancer-free`).** `g0 = 0` in both bodies and in the
controller; the wheel starts at **30 rad/s** (`inertia/P = [0.06, 0, 0]`). The same
pulse leans the body; the wheel **spins down to 25.99 rad/s** as the body leans and
**back up to 32.70 rad/s** as it returns, ending at 30.0007 rad/s. `H` stays at
0.06 kg·m²/s.

The **poses are composed, never integrated** (D-MB6): `JointPose2D(q)` →
`ComposePose2D` with the constant body offset `(0, 0.3, π/2)` gives the body CoM
(and the wheel axis at `rx = 0.2` in that frame), and the wheel pose adds the wheel
joint's `JointPose2D(q_w)`. `GravityPlanar` in each body reads its composed pose.

## Parameters

| parameter | value |
| --- | --- |
| body | `m_b = 1.5 kg`, `J_b = 0.02 kg·m²`, CoM `lc_b = 0.3 m` above the pivot |
| wheel | `m_w = 0.4 kg`, `J_w = 0.002 kg·m²`, axis `L_w = 0.5 m` above the pivot |
| pivots | `kt = 1e9 N/m`, `bt = 5e3 N·s/m` (both joints, both variants) |
| gravity torque | `G = g0 (m_b lc_b + m_w L_w) = 6.3765 N·m` |
| controller | 1 ms, `Kp = 16 N·m/rad`, `Kd = 4 N·m·s/rad`, `|τ| ≤ 1.5 N·m` |
| reference | `Pulse` 0.012 rad, `t_start = 0.5 s`, `period 4 s`, `duty 0.25` (high 0.5–1.5 s) |
| initial state | gravity on: `θ0 = 0.01 rad`; gravity off: `θ0 = 0`, wheel 30 rad/s |
| run | 3 s, 3001 output points, `reltol 1e-9`, `abstol 1e-11` |

## The flat graph

| instance | block | role |
| --- | --- | --- |
| `Ground` | `stdlib:multibond/GroundPlanar` | world flow source |
| `Pivot` | `stdlib:planar/Revolute2DCompliant` | compliant pivot at the ground; `bt` damps the fast translational mode |
| `LinkB` | `stdlib:planar/FixedJoint2D` | pivot child → body CoM (`y = 0.3 m`, `θ = π/2`: body `x` along the link) |
| `BodyJ` | 1-junction | common body twist: `LinkB`, `Body` and the wheel joint |
| `Body` | `stdlib:planar/RigidBody2D` | `m = 1.5`, `J = 0.02` |
| `WheelJ` | `stdlib:planar/Revolute2DCompliant` | wheel axis at `rx = 0.2 m` in the body CoM frame |
| `Wheel` | `stdlib:planar/RigidBody2D` | `m = 0.4`, `J = 0.002`, centre on the axis (direct bond, zero offset) |
| `PivotSe` | `stdlib:bondgraph/Se` | `e = 0`: the pivot's `Rotation` drive is unpowered |
| `Motor` | `stdlib:bondgraph/MSe` | wheel torque from the controller |
| `Ref` | `stdlib:sources/Pulse` | the 0.012 rad reference pulse |
| `PoseJ1`, `PoseB`, `PoseWrel`, `PoseW` | `JointPose2D` / `LocalPose2D` / `ComposePose2D` | the composed pose chain |
| `Ctrl` | `project:Balancer` | the 1 ms PD + feedforward firmware |

`Balancer` is the only non-bond-graph part (sampled firmware, the D28 exception).

## The two-stroke visual

Every `Power{Planar}` bond — `Ground–Pivot`, `Pivot–LinkB`, `LinkB–BodyJ`,
`Body–BodyJ`, `WheelJ–BodyJ`, `WheelJ–Wheel` — is a **two-stroke bundle** with one
half arrow per stroke and **one** causal bar (`data-multibond-strokes="2"`, two
`.editor-edge__multibond-stroke` paths, one `causal-stroke-<id>`). The `Rotation`
drive bonds (`Motor → drive`, `PivotSe → drive`) stay single-stroke. The stroke
count encodes the model dimension, not the port size (plan section 7).

## Measured (this example, the real worker)

| quantity | value |
| --- | --- |
| `|θ|` over the whole run, gravity on | **0.011969 rad** at the pulse (band 0.02) |
| `θ` at 0.5 s (initial tilt recovered) | 0.000907 rad |
| tracked error before the pulse | `max|e| = 1.72e-3` rad over `[0.4, 0.5] s` |
| wheel speed, gravity on | 0 → **47.046 rad/s** (peak at 1.782 s) → 46.213 rad/s |
| motor torque | `−0.195 … 0.269 N·m` (limit 1.5) |
| mechanical energy, gravity on | 6.3762 J → **8.5877 J** peak (the wheel's 2.211 J) |
| `|θ|` over the whole run, gravity off | 0.011967 rad |
| wheel speed, gravity off | 30 → **25.989** → **32.699** → 30.0007 rad/s |
| total angular momentum `H` | **0.06 kg·m²/s** constant; `max|H−H0| = 5.27e-9` = **8.78e-8** of `H` (tol 1e-6) |
| states / equations | 12 differential states (2 × P[3], 2 × d[2], 2 × q), no `W201` |
| run cost | 98 560 / 82 077 adaptive steps, 6 007 / 5 507 rows |
| diagnostics | none (`W201`, `E101`, `E102`, `E103`, `E106`, `W206` absent) |

Without the pivot damping (`Pivot/bt = 0`, `WheelJ/bt = 0`) the gravity-on run does
not finish: the 1 ms sampled drive pumps the 3.6 kHz translational mode and the
solver stops with `E901` (MaxIters) at t = 2.285 s.

## Checks (`expected.json`)

`balancer`: `θ0 = 0.01`; `|θ| ≤ 0.02 rad` over the whole run; the tilt is recovered
to 0.9 mrad at 0.5 s and the tracked error is under 2 mrad before the pulse; the
wheel starts at rest, peaks at 47.05 rad/s and keeps 46.21 rad/s; the torque stays
inside 1.5 N·m; the wheel speed stays under 50 rad/s (so the stored energy is
bounded); the mechanical energy is bounded by 8.9 J = `E0 + ½J_w·50²`; no
diagnostics.
`balancer-free`: `θ0 = 0`, wheel 30 rad/s; `|θ| ≤ 0.02`; the wheel dips to 25.99
and rises to 32.70 rad/s; the torque bound; the **invariant** `H = 0.257 θ̇ + 0.002
q̇_w` constant to 1e-6 relative; no diagnostics.

## Run it

```
uv run bgsim
```

then **Open** (Ctrl+O) → **Samples** → **reaction-wheel-2d** (imports a copy), press
**Run**, and open **Plots**: “Body angle and reference”, “Wheel speed”, “Motor
torque and momentum”. The acceptance checks:

```
uv run examples/run_checks.py
```

and the browser acceptance (real worker, two-stroke bonds, run, plot, screenshot):

```
cd web
$env:BGSIM_E2E_REAL="1"; npx playwright test tests/e2e/reaction-wheel-2d.spec.ts --workers=1
```

## What to try

- Open `balancer-free` and plot `WheelJ/qdout` next to `Pivot/qdout`: the wheel
  rate moves exactly opposite to the body rate times 128
  (`J_A/J_w = 0.257/0.002`) whenever the pulse moves the body; their weighted sum
  is the constant `H`.
- Set `Ctrl/tau_max` to 0.05 N·m: the initial tilt already needs
  `G sin(0.01) + Kp·0.01 = 0.224 N·m`, so the motor cannot arrest it, the body
  falls and the 0.02 rad band check fails — the actuator authority is what the
  limit is for.
- Set `Pivot/bt` to 0 (and `WheelJ/bt`) and rerun `balancer`: the 1 ms sampled
  drive pumps the 3.6 kHz pivot mode and the run stops with `E901` (MaxIters) at
  t = 2.29 s; the damper is part of the model, like on the arm.
