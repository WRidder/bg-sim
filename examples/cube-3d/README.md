# cube-3d — a cube balanced on one corner by three reaction wheels

A 0.15 m cube stands on one corner (a ball joint at the world origin) with its body diagonal
vertical, and starts 2° off. Three reaction wheels sit on the body axes `x`, `y`, `z` (the three
cube edges that meet at the pivot). Three DC motors spin them; their reaction torques hold the
cube up. A 2 ms discrete LQR on the tilt, the body rates and the wheel rates sets the three motor
voltages, clamped to ±12 V. It is the last example of M5 (plan 9.9): an equation-block plant, a
controller designed from a numpy replica, a 3D scene, and a cross-check against the same cube
built from the M3 multibond library (DEC-M5-3).

```
        Cube.pose ─┐
        Cube.omega ┼─► Ctrl (CubeLQR, 2 ms, ±12 V) ─ u1,u2,u3 ─► Drv1..3 (ElectricDrive) ─ shaft ─► Cube.m1..m3
        Cube.wheel ┘                                                  (stator fixed)              (CornerCube)
```

## Models

| model | what it is | run time (real worker) |
| --- | --- | --- |
| `cube-3d` | the equation-block plant (`library/CornerCube.jl`), the plan 9.9 model, with the 3D scene | 3 to 5 s |
| `cube-3d-mb` | the same cube from the M3 spatial stdlib, compliant ball joint `kt = 1e8 N/m` | 36 s |
| `cube-3d-mb-soft` | the same, `kt = 1e6 N/m` (100 times softer) | 49 s |

All three run 4 s (6001 rows, `reltol 1e-8`) with the same controller block and the same gain `K`.

## The equation block `CornerCube`

Body frame: the axes lie along the cube edges at the pivot, the cube occupies `[0, a]³`, so the
centre of mass is `r = (a/2)(1,1,1)`. States: the unit quaternion `q` (body to world), the body
rates `om` and the wheel rates relative to the body `wr`. With `Θc = Θcm I + m(|r|² I − r rᵀ)`
(the cube about the pivot, the wheels' spin excluded), `Θw` the wheel inertia about its axis
(rotor included) and `T` the torque the motors put on the wheels:

```
g_b  = Rᵀ [0, 0, −g]
L    = Θc om + Θw (om + wr)               angular momentum about the pivot (body frame)
om'  = Θc⁻¹ ( −om × L + r × m g_b − T )
wr'  = T / Θw − om'
q'   = ½ q ⊗ [0, om]
```

`m = 0.42 kg`, `a = 0.15 m`, `Θcm = 3e-3 kg·m²`, `Θw = 6e-4 kg·m²`, `g = 9.81`. Three `Rotation`
ports `m1`, `m2`, `m3` carry `mi.f ~ wr[i]` and `T[i] ~ mi.e`; the reaction `−T` on the cube is
inside the `om'` equation, so each motor has its stator on a fixed shaft and the motor power
`Σ T_i wr_i` is what the wheels gain relative to the body.

Outputs: `pose` (the 7-element chart `(qw, qx, qy, qz, 0, 0, 0)` that the controller reads),
`omega`, `wheel`, `tilt` (angle between the body diagonal and the vertical), `qerr` (`|q| − 1`),
`Hz` (vertical angular momentum about the pivot), `Hzw` (the wheels' part of it) and the
integrated wheel angles `phi1..3 = int(wr[i], 0)`. The start value is the equilibrium tilted 2°
about the world `x` axis. The equilibrium rotates the diagonal `(1,1,1)/√3` onto `(0,0,1)`:
axis `(1,−1,0)/√2`, angle `acos(1/√3)`, `q_eq = (0.88807, 0.32506, −0.32506, 0)`.

Language limits met while writing it (all in the block, none in the compiler):

- The language has no matrix solve (`\` on arrays is E004), so `Θc⁻¹` is written in closed form.
  `Θc = c1 I − c2 u uᵀ` with `u = (1,1,1)`, `c2 = m a²/4`, `c1 = Θcm + 3 c2`, and
  `Θc⁻¹ = (I + (c2/Θcm) u uᵀ)/c1` exactly.
- `cross` needs equal units on both arguments (E006), so the cross products are written out
  component by component, which also keeps the unit check on every term.

## The motors, and why `ElectricDrive` with a rotor of 1e-6

Each wheel is driven by the stdlib `drives/ElectricDrive` (`R = 1 Ω`, `L = 0.1 mH`, `k = 0.0335`;
the DC motor of plan 9.9 as a composite of the same primitives, with a fixed stator and one
`shaft` port). The plan asks for rotor inertia 0 because `Θw` already contains it. A rotor of
exactly 0 does not work here: the rotor `Inertia` has its rate imposed by the block (`mi.f ~ wr[i]`),
a derivative-causal element. `J_m = 0` fails at `t = 0` (`Unstable`) and `J_m ≤ 1e-8` fails at
the controller ticks (`InitialFailure` when the discrete update re-initialises the DAE); 1e-6 and
1e-5 run. The model uses **`J_m = 1e-6 kg·m²`**: the rotor spins at the relative rate `wr`, so
it adds `J_m` to the wheel momentum (`+0.17 %` of `Θw`) and no more. `design.py` includes it
exactly (`T = em − J_m wr'`, solved as a 9×9 linear system), and the multibond models use the
same motor, so the three models agree on it.

## The design (`design/design.py`)

A numpy replica of the equations above (independent of the Julia code) is linearised by central
finite differences at the equilibrium. The reduced state is `z = [tilt (2), om (3), wr (3)]`
with `tilt_k = e_k · up_b`, `up_b = Rᵀ[0,0,1]` and `e1 = (1,−1,0)/√2`, `e2 = (1,1,−2)/√6` spanning
the plane perpendicular to the diagonal. The motor is the quasi-static `T = k(u − k wr)/R`
(`L/R = 0.1 ms` against the 2 ms sample). The vertical angular momentum is conserved (gravity has
no torque about a vertical axis through the pivot), so one mode of `z` is uncontrollable at
eigenvalue 1 once discretised: the Riccati equation is solved on `(Ad/ρ, Bd/ρ)` with `ρ = 1.0005`
and the gain is applied to the true `(Ad, Bd)`.

Weights `Q = diag(σ⁻²)` with `σ_tilt = 0.02`, `σ_om = 0.2 rad/s`, `σ_wr = 40 rad/s`, `R = I/12²`,
`Ts = 2 ms`. Result, for `u = −K z`, `z = [tilt1, tilt2, om1..3, wr1..3]`:

```
K = [[ 206.77  −358.13  −46.976    7.4573    7.4573  −0.12529   0.048335   0.048335]
     [ 206.77   358.13    7.4573  −46.976    7.4573   0.048335 −0.12529    0.048335]
     [−413.54     0       7.4573    7.4573  −46.976   0.048335  0.048335  −0.12529 ]]
discrete closed-loop eigenvalues  0.28492, 0.67239 (x2), 0.98070 (x2), 0.99948 (x2), 1 (the vertical-momentum mode)
continuous equivalents            −627.8, −198.5 (x2), −9.75 (x2), −0.262 (x2), 0  1/s
open loop                         +7.24 (x2), −7.36 (x2), −2.24, −1.86 (x2), 0
```

The LQR met its checks, so the fallback (per-axis PD) was not needed. `design.py` then integrates the
**non-linear** closed loop (Radau, with the winding inductance, the 2 ms sample-and-hold and the
clamp) and writes `K` (as a Julia matrix literal) into the `K` parameter of the controller node of
all three models:

```
uv run examples/cube-3d/design/design.py
```

The controller block `CubeLQR` (`library/CubeLQR.jl`) forms `z` from the pose quaternion, the body
rates and the wheel rates in a `@discrete Ts = 2e-3` scope (`up_b` is the third row of `R(q)`, no
trigonometry), computes `K z` with the `Mat{3,8}` parameter and clamps. The first sample is at
`t = Ts`; the declared 0 V is held before it. The clamp is active only at the start (wheel 1 hits
12 V in the first samples; after 0.1 s the voltage stays below 0.07 V).

## Results (real worker)

| quantity | design.py | `cube-3d` |
| --- | --- | --- |
| tilt at 0.1 s | 0.77818° | 0.77818° |
| tilt over `t ≥ 3 s` (plan: < 0.5°) | 0.02703° | 0.02704° (4.72e-4 rad) |
| inside 0.5° from | 0.142 s | 0.141 s |
| tilt at 4 s | 0.02081° | 0.02081° |
| peak wheel rates relative to the cube (plan: < 400 rad/s) | 4.6855 / 1.2570 / 3.4286 | 4.6855 / 1.2570 / 3.4286 rad/s |
| peak `|u|` | 12 V | 12 V |
| quaternion norm error (plan: < 1e-6) | 7e-15 | 2.6e-14 |
| vertical momentum `Hz`: max `|Hz − Hz(0)|` | 3e-17 | 1.7e-16 |
| wheels' vertical momentum `Hzw`, peak | | 7.6e-5 N·m·s (back to 0 at the end) |

`Hz` is the strong invariant: the wheels hold up to 7.6e-5 N·m·s of vertical momentum while the
cube holds the opposite, and the sum stays at round-off. The slow closed-loop pole (−0.262 1/s)
is the wheel momentum bleeding off; it leaves a tilt of a few hundredths of a degree for several
seconds, far inside the limit.

## The multibond counterpart (DEC-M5-3)

`cube-3d-mb` builds the same cube from the M3 spatial stdlib, in the structure of
`examples/reaction-wheel-3d`: `GroundSpatial` → `Spherical3D` pivot (compliant, `kt`, `bt`) →
`FixedTransform3DNeutral` (the centre of mass `r` in the corner frame) → `RigidBody3D` cube. Each
wheel is a `RigidBody3D` on a `Revolute3D` whose axis (the joint's local `z`) is mounted onto the
body `x`, `y` or `z` by a `FixedTransform3DNeutral`, driven by the same `ElectricDrive` through a
stiff `ElasticShaft` (a rotor rigidly on a rate-imposing joint is W201). Poses are composed
(`ComposePose3D`), never integrated. The controller is the same `project:CubeLQR` with the same
`K`; it reads the composed pose, the body twist (`Take3`, the first three components of
`Body.V`) and the three joint rates (`Pack3`). `TiltMeter` and `BodyMeasure` are sensors.

The parameters match the equation block exactly: the wheels sit on the centre of mass (0.02 kg
each, `J = (3e-4, 3e-4, 6e-4)`: axial `Θw = 6e-4`, transverse 3e-4), the cube body is 0.36 kg with
`J = 2.4e-3`, so the total mass is 0.42 kg and the inertia about the centre of mass is
`2.4e-3 + 6e-4 + 2·3e-4 = 3.6e-3 = Θcm + Θw` on every axis, which is what the block's
`Θc + Θw I` is. The only physical difference is the pivot, which is compliant: it sags by
`m g / kt` (4.1e-8 m at `kt = 1e8`, measured max 5.3e-8 m) and the body is not held rigidly at the
corner.

**Measured differences** (equation block against multibond, max over the window, `expected.json`
`compare` and `compare_scaling`):

| signal | window | `kt = 1e8` | `kt = 1e6` | ratio |
| --- | --- | --- | --- | --- |
| tilt | whole run | 2.1e-6 rad (6e-5 of the 2° start) | 2.1e-5 rad | 10 |
| quaternion (4 components) | whole run | 0.04 to 0.96 e-6 | 0.35 to 9.2 e-6 | 9 to 10 |
| body rates | from 0.05 s | 2.2e-6 / 0.6e-6 / 1.6e-6 rad/s | 2.3e-5 / 0.6e-5 / 1.6e-5 | 10 |
| wheel rates | from 0.05 s | 3.0e-5 / 0.8e-5 / 2.2e-5 rad/s | 1.2e-4 / 0.4e-4 / 0.9e-4 | 4 to 5 |
| wheel rates | from 1 s | 3.7e-7 / 0.9e-7 / 2.9e-7 | 3.5e-5 / 0.7e-5 / 2.8e-5 | **95 / 78 / 100** |

The error has two parts. The first voltage step at 2 ms excites the pivot's ringing, a
transient whose amplitude scales like `1/√kt` (the factor 10 in the first rows) and which has
decayed by 50 ms. What remains is the quasi-static effect of the sag, which scales as `1/kt`:
from 1 s on the wheel-rate difference changes by 95 / 78 / 100 for a stiffness ratio of 100, and
`compare_scaling` requires a ratio between 50 and 150. The tolerances in `expected.json` are the
measured values plus 20 to 100 % margin (stiff) and the same shape scaled by the observed
transient ratio (soft). The vertical momentum of body plus wheels is conserved to 9.3e-10
(`kt = 1e8`) and 6.8e-7 (`kt = 1e6`) of the 6e-5 N·m·s the wheels exchange.

## 3D

`scenes/cube-3d.sdf`: the pivot corner at the world origin, a 0.15 m semi-transparent cube whose
visual is offset by `(a/2, a/2, a/2)` inside the link `cube`, and three wheel discs (orange, green,
red, with a dark spoke) on its centre with joints `wheel_x`, `wheel_y`, `wheel_z` about the body
axes. Bindings of `cube-3d`:

| target | signal | meaning |
| --- | --- | --- |
| `link:cube` `pose` | `Cube/pose[1..4]`, `PosX/y`, `PosY/y`, `PosZ/y` | quaternion `(qw, qx, qy, qz)` of the body, then the position (0, 0, 0): the pivot is the origin (the position comes from three inline `Origin` blocks with output unit m, so the pose binding passes the E303 unit check) |
| `joint:wheel_x` | `Cube/phi1` | the wheel angle relative to the cube, `int(wr[1], 0)`, 7.10 rad (1.1 turns) after 4 s |
| `joint:wheel_y` | `Cube/phi2` | −1.91 rad |
| `joint:wheel_z` | `Cube/phi3` | −5.20 rad |

`web/tests/scene-sdf.test.ts` parses the scene with zero E305/E306. The multibond models have no
scene (their body frame sits on the centre of mass, not at the pivot).

## Checks

`expected.json` (82 checks), run with `uv run examples/run_checks.py --only cube-3d`:

- **`cube-3d`:** the 2° start (tilt and quaternion), tilt under 0.5° for `t ≥ 3 s` (and from
  0.15 s), tilt cursor values at 0.1 to 4 s against `design.py`, peak tilt, the three wheel rates
  under 400 rad/s and against `design.py`, the integrated wheel angle, the quaternion norm error
  under 1e-6, `Hz` conserved against the wheels' `Hzw`, the ±12 V clamp (active at the first
  samples, below 0.1 V after 0.1 s), and no `E901`, `E106`, `W201`, `W202`, `W205`, `W206`.
- **`cube-3d-mb`, `cube-3d-mb-soft`:** the same start, the tilt under 0.5° after 3 s, wheel rates
  under 400 rad/s, quaternion norm error, the vertical momentum of body plus wheels (`invariant`),
  the pivot sag `≤ 1e-7 / 1e-5 m`, and no `E901`, `E106`, `E007`, `W201`, `W202`, `W205`, `W206`.
- **Comparison:** `compare` (tilt, quaternion, wheel rates, body rates, equation block against each
  multibond model) and the new `compare_scaling` kind in `run_checks.py` (the soft-to-stiff ratio
  of the difference must lie in a band around the stiffness ratio).

## Run it

```
uv run bgsim
```

then **Open** → **Samples** → **cube-3d** and press **Run**. Open the **3D View** tab to watch it.
Cross-check with the multibond cube: run `cube-3d-mb` and plot `Tilt/tilt` next to `Cube/tilt`.

## What to try

- Raise the start tilt (`Cube` start values `qw..qz`, and `TILT0` in `design.py` for the
  reference): the clamp stays active longer and the wheels spin faster.
- Change a mass or `a` without re-running `design.py`: the gains are no longer matched, which
  shows the margin of the design.
- Change a weight or the sample time in `design/design.py` and run it: the new `K` is written into
  all three models.
- Soften the pivot further in `cube-3d-mb-soft` (`Pivot/kt`): the multibond cube leaves the rigid
  one, and the difference to `cube-3d` grows as `1/kt`.
