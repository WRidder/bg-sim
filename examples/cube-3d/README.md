# cube-3d — a cube balanced on one corner by three reaction wheels

A 0.15 m cube stands on one corner (a ball joint at the world origin) with its body diagonal
vertical, and starts 2° off. Three reaction wheels spin about the body axes `x`, `y`, `z` (the
three cube edges that meet at the pivot). Each wheel is mounted on the inside of a face: wheel `i`
on the face opposite the pivot corner along axis `i`, centred on the face (a wheel at the cube
centre is not buildable). Three DC motors spin them; their reaction torques hold the
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
| `cube-3d` | the equation-block plant (`library/CornerCube.jl`), the plan 9.9 model, with the 3D scene | about 7 s |
| `cube-3d-mb` | the same cube from the M3 spatial stdlib, compliant ball joint `kt = 1e8 N/m` | about 12 s |
| `cube-3d-mb-soft` | the same, `kt = 1e6 N/m` (100 times softer) | about 10 s |

All three run 4 s (6001 rows, `reltol 1e-8`) with the same controller block and the same gain `K`.

## The equation block `CornerCube`

### Geometry and mass model

Body frame: the axes lie along the cube edges at the pivot, the cube occupies `[0, a]³`. The wheel
spin axes are the body axes. Wheel `i` is mounted on the **inside of the face `x_i = a`** (the face
opposite the pivot corner along axis `i`), centred on the face, its centre `d` inside the face:

| wheel | spin axis | centre `p_i` (m) |
| --- | --- | --- |
| 1 | `x` | (0.140, 0.075, 0.075) |
| 2 | `y` | (0.075, 0.140, 0.075) |
| 3 | `z` | (0.075, 0.075, 0.140) |

The arrangement is invariant under the permutations of the axes, so the centre of mass stays on
the body diagonal and the equilibrium is still "diagonal vertical".

| item | value | why |
| --- | --- | --- |
| wheel | steel rim wheel, radius 0.055 m, thickness `h` = 12 mm, mass `m_w` = 0.08 kg | the radius leaves a 20 mm margin to the face edges and the wheels do not touch each other (wheel 1 spans `y, z ∈ [0.02, 0.13]` at `x = 0.14`, wheel 2 occupies `y ≥ 0.134`) |
| inset `d` | 10 mm = `h/2` + 4 mm mounting gap | the wheel sits 4 mm off the inner face |
| axial inertia `Θw` | 1.9e-4 kg·m² (0.79 `m_w R²`, rim-heavy) | rotor included |
| transverse inertia `Θwt` | 9.6e-5 kg·m² | `Θw/2 + m_w h²/12` (thin axisymmetric body) |
| structure | `m_s` = 0.18 kg (frame, electronics, motors), `Θs` = 1.125e-3 kg·m² | thin cubic shell, `5/18 m_s a²`; total mass `m_s + 3 m_w` = **0.42 kg** (kept) |

The earlier example kept `Θw = 6e-4` for each of the three wheels at the cube centre. That is not
possible for a wheel that fits on a 0.15 m face within a 0.42 kg total: a thin ring of radius
0.055 m has `m R²` = 0.08 × 0.055² = 2.4e-4 for 0.08 kg, and `6e-4` would need 0.2 kg per wheel
(half the cube). So `Θw` is now 1.9e-4 (the wheels are three times weaker, and the design and
the numbers below are redone).

Derived (the block computes them from the parameters; `design.py` builds the same by the
parallel-axis theorem body by body and the two agree to 1e-9):

```
m      = m_s + 3 m_w                                 = 0.42 kg
r      = (m_s a/2 + m_w (2a − d)) / m · (1,1,1)      = 0.087381 m · (1,1,1)
Θc     = Θs I + m_s(|c|² I − c cᵀ) + Σ_i [ m_w(|p_i|² I − p_i p_iᵀ) + Θwt (I − e_i e_iᵀ) ]
       = diag 8.2778e-3,  off-diagonal −3.1425e-3 kg·m²  (Td = 8.278e-3, To = −3.1425e-3)
```

(`c = (a/2)(1,1,1)` the structure centre, `e_i` the axis of wheel `i`.) `Θc` is the inertia
about the pivot with the wheels' spin excluded; the axial inertia of each wheel is `Θw` in `Lw`.

### Equations

States: the unit quaternion `q` (body to world), the body rates `om` and the wheel rates relative
to the body `wr`. With `T` the torque the motors put on the wheels:

```
g_b  = Rᵀ [0, 0, −g]
L    = Θc om + Θw (om + wr)               angular momentum about the pivot (body frame)
om'  = Θc⁻¹ ( −om × L + r × m g_b − T )
wr'  = T / Θw − om'
q'   = ½ q ⊗ [0, om]
```

Parameters of the block: `ms = 0.18`, `mw = 0.08`, `a = 0.15`, `d = 0.01`, `Ths = 1.125e-3`,
`Thw = 1.9e-4`, `Thwt = 9.6e-5`, `g = 9.81`. Three `Rotation` ports `m1`, `m2`, `m3` carry
`mi.f ~ wr[i]` and `T[i] ~ mi.e`; the reaction `−T` on the cube is inside the `om'` equation, so
each motor has its stator on a fixed shaft and the motor power `Σ T_i wr_i` is what the wheels gain
relative to the body.

Outputs: `pose` (the 7-element chart `(qw, qx, qy, qz, 0, 0, 0)` that the controller reads),
`omega`, `wheel`, `tilt` (angle between the body diagonal and the vertical), `qerr` (`|q| − 1`),
`Hz` (vertical angular momentum about the pivot), `Hzw` (the wheels' part of it) and the
integrated wheel angles `phi1..3 = int(wr[i], 0)`. The start value is the equilibrium tilted 2°
about the world `x` axis. The equilibrium rotates the diagonal `(1,1,1)/√3` onto `(0,0,1)`:
axis `(1,−1,0)/√2`, angle `acos(1/√3)`, `q_eq = (0.88807, 0.32506, −0.32506, 0)`.

Language limits met while writing it (all in the block, none in the compiler):

- The language has no matrix solve (`\` on arrays is E004), so `Θc⁻¹` is written in closed form.
  `Θc = (Td − To) I + To u uᵀ` with `u = (1,1,1)`, and
  `Θc⁻¹ = (I − To/(Td + 2 To) u uᵀ)/(Td − To)` exactly.
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
it adds `J_m` to the wheel momentum (`+0.5 %` of `Θw`) and no more. `design.py` includes it
exactly (`T = em − J_m wr'`, solved as a 9×9 linear system), and the multibond models use the
same motor, so the three models agree on it.

## The design (`design/design.py`)

A numpy replica of the equations above (independent of the Julia code, with the mass model built
body by body) is linearised by central finite differences at the equilibrium. The reduced state is
`z = [tilt (2), om (3), wr (3)]` with `tilt_k = e_k · up_b`, `up_b = Rᵀ[0,0,1]` and
`e1 = (1,−1,0)/√2`, `e2 = (1,1,−2)/√6` spanning the plane perpendicular to the diagonal. The motor
is the quasi-static `T = k(u − k wr)/R` (`L/R = 0.1 ms` against the 2 ms sample). The vertical
angular momentum is conserved (gravity has no torque about a vertical axis through the pivot), so
one mode of `z` is uncontrollable at eigenvalue 1 once discretised: the Riccati equation is solved
on `(Ad/ρ, Bd/ρ)` with `ρ = 1.0005` and the gain is applied to the true `(Ad, Bd)`.

Weights `Q = diag(σ⁻²)` with `σ_tilt = 0.02`, `σ_om = 0.2 rad/s`, `σ_wr = 40 rad/s`, `R = I/12²`,
`Ts = 2 ms` (unchanged). Result, for `u = −K z`, `z = [tilt1, tilt2, om1..3, wr1..3]`:

```
K = [[ 243.44  −421.64  −53.955   14.533   14.533  −0.16979   0.071768   0.071768]
     [ 243.44   421.64   14.533  −53.955   14.533   0.071768 −0.16979    0.071768]
     [−486.87     0      14.533   14.533  −53.955   0.071768  0.071768  −0.16979 ]]
discrete closed-loop eigenvalues  0.17065, 0.69506 (x2), 0.98086 (x2), 0.99728 (x2), 1 (the vertical-momentum mode)
continuous equivalents            −884, −181.9 (x2), −9.66 (x2), −1.359 (x2), 0  1/s
open loop                         +7.36 (x2), −7.61 (x2), −6.43, −5.73 (x2), 0
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
`t = Ts`; the declared 0 V is held before it. The clamp is active only at the start (wheel 1 and 3
hit 12 V in the first samples; after 0.1 s the voltage of wheel 1 stays below 0.21 V).

## Results (real worker)

| quantity | design.py | `cube-3d` |
| --- | --- | --- |
| tilt at 0.1 s | 0.65854° | 0.65854° |
| tilt over `t ≥ 3 s` (plan: < 0.5°) | 0.006046° | 0.006046° (1.056e-4 rad) |
| inside 0.5° from | 0.120 s | 0.120 s |
| tilt at 4 s | 0.00155° | 0.00155° |
| peak wheel rates relative to the cube (plan: < 400 rad/s) | 17.693 / 4.758 / 12.936 | 17.693 / 4.758 / 12.936 rad/s |
| peak `|u|` | 12 V (wheels 1, 3); 4.45 V (wheel 2) | 12 V / 4.45 V / 12 V |
| quaternion norm error (plan: < 1e-6) | 1.4e-14 | 1.8e-14 |
| vertical momentum `Hz`: max `|Hz − Hz(0)|` | 2e-17 | 4.7e-17 |
| wheels' vertical momentum `Hzw`, peak | | 1.6e-4 N·m·s (back to 0 at the end) |

`Hz` is the strong invariant: the wheels hold up to 1.6e-4 N·m·s of vertical momentum while the
cube holds the opposite, and the sum stays at round-off. The slow closed-loop pole (−1.36 1/s)
is the wheel momentum bleeding off. The lighter wheels spin about 3.8 times faster than the
`Θw = 6e-4` wheels of the earlier version (4.7 rad/s peak there), far inside the 400 rad/s limit.

## The multibond counterpart (DEC-M5-3)

`cube-3d-mb` builds the same cube from the M3 spatial stdlib, in the structure of
`examples/reaction-wheel-3d`: `GroundSpatial` → `Spherical3D` pivot (compliant, `kt`, `bt`) →
`FixedTransform3DNeutral` (the centre `c` of the structure in the corner frame) → `RigidBody3D`
structure. Each wheel is a `RigidBody3D` on a `Revolute3D` whose axis (the joint's local `z`) is
mounted onto the body `x`, `y` or `z` by a `FixedTransform3DNeutral`, **with the face offset in the
mount**: the wheel centre is `a/2 − d = 0.065 m` from the cube centre along its body axis (`WLocal i`
holds the pose for the composed-pose chain, `WMount i` is the inverse mount the body-to-joint bond
needs, so its translation is `(0, 0, −0.065)` in the joint frame). Each wheel is driven by the same
`ElectricDrive` through a stiff `ElasticShaft` (a rotor rigidly on a rate-imposing joint is W201).
Poses are composed (`ComposePose3D`), never integrated. The controller is the same `project:CubeLQR`
with the same `K`; it reads the composed pose, the body twist (`Take3`, the first three components
of `Body.V`) and the three joint rates (`Pack3`). `TiltMeter` and `BodyMeasure` are sensors.

The parameters match the equation block exactly: structure 0.18 kg with `J = 1.125e-3`, three
wheels of 0.08 kg with `J = (9.6e-5, 9.6e-5, 1.9e-4)` (axial `Θw = 1.9e-4`, transverse `Θwt`), so
the total mass is 0.42 kg, the centre of mass `0.087381 m (1,1,1)` and the inertia about the pivot
(parallel-axis theorem inside the spatial bodies) equal `Θc + Θw`-spin of the block. The physical
differences are the compliant pivot (it sags by `m g / kt`: 4.1e-8 m at `kt = 1e8`, measured max
5.0e-8 m), the compliant wheel joints (`kt = 1e7`, `kr = 1e5`) and the shaft. The shaft stiffness
is `k = 1e4 N·m/rad` (`d = 0.02`): the original `k = 100` left a rotor-lag error in the wheel rates
that was 50 times larger and did not scale with `1/kt` (stiffer wheel joints did not change it).

**Measured differences** (equation block against multibond, max over the window, `expected.json`
`compare` and `compare_scaling`):

| signal | window | `kt = 1e8` | `kt = 1e6` |
| --- | --- | --- | --- |
| tilt | whole run | 4.2e-7 rad (1.2e-5 of the 2° start) | 2.4e-5 rad |
| quaternion (4 components) | whole run | 0.1 to 1.7 e-7 | 0.2 to 1.1 e-5 |
| body rates | from 0.05 s | 8.3e-8 / 2.7e-8 / 5.6e-8 rad/s | 4.3e-5 / 2.4e-5 / 2.0e-5 |
| body rates | from 0.5 s | 9.8e-9 / 2.7e-9 / 7.2e-9 | 7.4e-7 / 3.2e-7 / 4.3e-7 (ratios **75 / 122 / 59**) |
| wheel rates | from 0.05 s | 1.0e-5 / 2.3e-6 / 7.6e-6 rad/s | 3.8e-3 / 1.9e-3 / 1.8e-3 |
| wheel rates | from 1 s | 1.0e-6 / 3.4e-7 / 7.1e-7 | 5.9e-4 / 3.3e-4 / 2.6e-4 |

The first voltage step at 2 ms excites the pivot's ringing (decayed by 50 ms); the rest is the
quasi-static effect of the sag, which scales as `1/kt`. `compare_scaling` therefore uses the body
rates from 0.5 s, where the soft-to-stiff ratio is 75 / 122 / 59 for a stiffness ratio of 100 (band
50 to 150). The wheel rates from 1 s give ratios of 370 to 970 instead: the stiff run has a floor
of about 1e-6 rad/s that does not shrink with a stiffer shaft (1e5) or stiffer wheel joints (1e8
gives 7e-7 to 3e-7), and the soft run's wheel-rate error falls faster than `1/kt` between `kt = 1e6`
and `1e7` (5.9e-4 to 3.3e-6), so the wheel rates are not a clean `1/kt` signal and are not used for
the scaling check. The vertical momentum of body plus wheels is conserved to 5.7e-10 (`kt = 1e8`)
and 6.8e-7 (`kt = 1e6`) of the 1.6e-4 N·m·s the wheels exchange.

## 3D

`scenes/cube-3d.sdf`: the pivot corner at the world origin, a 0.15 m semi-transparent cube whose
visual is offset by `(a/2, a/2, a/2)` inside the link `cube`, and three wheel discs (orange, green,
red, radius 0.055 m, thickness 0.012 m, with a dark spoke), one against the inside of each face
opposite the pivot corner: `wheel_x` at (0.14, 0.075, 0.075), `wheel_y` at (0.075, 0.14, 0.075),
`wheel_z` at (0.075, 0.075, 0.14), with joints about the body axes. Bindings of `cube-3d`:

| target | signal | meaning |
| --- | --- | --- |
| `link:cube` `pose` | `Cube/pose[1..4]`, `PosX/y`, `PosY/y`, `PosZ/y` | quaternion `(qw, qx, qy, qz)` of the body, then the position (0, 0, 0): the pivot is the origin (the position comes from three inline `Origin` blocks with output unit m, so the pose binding passes the E303 unit check) |
| `joint:wheel_x` | `Cube/phi1` | the wheel angle relative to the cube, `int(wr[1], 0)`, 9.15 rad (1.5 turns) after 4 s |
| `joint:wheel_y` | `Cube/phi2` | −2.46 rad |
| `joint:wheel_z` | `Cube/phi3` | −6.69 rad |

`web/tests/scene-sdf.test.ts` parses the scene with zero E305/E306. The e2e spec saves a screenshot
of the 3D view at `t = 0` (`test-results/cube-3d-3d-view.png`): the three discs sit against three
faces of the cube, away from the pivot corner. The multibond models have no scene (their body frame
sits on the structure centre, not at the pivot).

## Checks

`expected.json` (82 checks), run with `uv run examples/run_checks.py --only cube-3d`:

- **`cube-3d`:** the 2° start (tilt and quaternion), tilt under 0.5° for `t ≥ 3 s` (and from
  0.15 s), tilt cursor values at 0.1 to 4 s against `design.py`, peak tilt, the three wheel rates
  under 400 rad/s and against `design.py`, the integrated wheel angle, the quaternion norm error
  under 1e-6, `Hz` conserved against the wheels' `Hzw`, the ±12 V clamp (active at the first
  samples, below 0.25 V after 0.1 s), and no `E901`, `E106`, `W201`, `W202`, `W205`, `W206`.
- **`cube-3d-mb`, `cube-3d-mb-soft`:** the same start, the tilt under 0.5° after 3 s, wheel rates
  under 400 rad/s, quaternion norm error, the vertical momentum of body plus wheels (`invariant`),
  the pivot sag `≤ 1e-7 / 1e-5 m`, and no `E901`, `E106`, `E007`, `W201`, `W202`, `W205`, `W206`.
- **Comparison:** `compare` (tilt, quaternion, wheel rates, body rates, equation block against each
  multibond model) and the `compare_scaling` kind in `run_checks.py` (the soft-to-stiff ratio
  of the body-rate difference from 0.5 s must lie in a band around the stiffness ratio).

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
