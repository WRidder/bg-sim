@@ figures cube-3d
{
  "diagram": {"kind": "diagram", "model": "cube-3d"},
  "scene": {"kind": "scene", "model": "cube-3d", "t": 0},
  "run": {
    "kind": "plot", "model": "cube-3d", "xlim": [0, 1],
    "rows": [
      {"ylabel": "tilt Cube/tilt [deg]", "series": [{"signal": "Cube/tilt", "label": "Cube/tilt", "scale": 57.29577951308232}]},
      {"ylabel": "wheel rate [rad/s]", "series": [{"signal": "Cube/wheel[1]", "label": "wheel 1 (x)"}, {"signal": "Cube/wheel[2]", "label": "wheel 2 (y)"}, {"signal": "Cube/wheel[3]", "label": "wheel 3 (z)"}], "legend": true},
      {"ylabel": "motor voltage [V]", "series": [{"signal": "Ctrl/u1", "label": "u1"}, {"signal": "Ctrl/u2", "label": "u2"}, {"signal": "Ctrl/u3", "label": "u3", "style": "--"}], "hlines": [{"y": 12, "label": "clamp 12 V"}, {"y": -12}], "legend": true}
    ]
  }
}
@@ page cube-3d overview - | Overview
# Cube balanced on a corner by three reaction wheels

A 0.15 m cube stands on one corner (a ball joint at the world origin) with its body diagonal vertical and starts 2 deg off. Three reaction wheels spin about the body axes $x$, $y$, $z$ (the three cube edges that meet at the pivot). Each wheel is mounted on the inside of a face: wheel $i$ on the face opposite the pivot corner along axis $i$, centred on the face (a wheel at the cube centre is not buildable). Three DC motors spin them; their reaction torques hold the cube up. A 2 ms discrete LQR on the tilt, the body rates and the wheel rates sets the three motor voltages, clamped to $\pm12$ V. It is the last example of M5 (plan 9.9): an equation-block plant, a controller designed from a numpy replica, a 3D scene, and a cross-check against the same cube built from the M3 multibond library (DEC-M5-3).

![The model canvas|900](@fig:diagram)

```
Cube.pose  --+
Cube.omega --+-> Ctrl (CubeLQR, 2 ms, +-12 V) - u1,u2,u3 -> Drv1..3 (ElectricDrive) - shaft -> Cube.m1..m3
Cube.wheel --+                                        (stator fixed)                     (CornerCube)
```

| model | what it is | run time (README, real worker) |
| --- | --- | --- |
| `cube-3d` (this one) | the equation-block plant (`library/CornerCube.jl`), the plan 9.9 model, with the 3D scene | about 7 s |
| `cube-3d-mb` | the same cube from the M3 spatial stdlib, compliant ball joint $k_t = 10^8$ N/m | about 12 s |
| `cube-3d-mb-soft` | the same, $k_t = 10^6$ N/m (100 times softer) | about 10 s |

All three run 4 s (4001 points, `reltol` 1e-8) with the same controller block and the same gain $K$.

## Run it

Press **Run**, then plot [Cube/tilt](signal:Cube/tilt) (it falls from 2 deg to 0.66 deg at 0.1 s and below 0.5 deg from 0.12 s), the wheel rates [Cube/wheel[1]](signal:Cube/wheel[1]) and the motor voltages [Ctrl/u1](signal:Ctrl/u1). Open the **3D View** tab to watch it.

## 3D view

`scenes/cube-3d.sdf`: the pivot corner at the world origin, a 0.15 m semi-transparent cube whose visual is offset by $(a/2, a/2, a/2)$ inside the link `cube`, and three wheel discs (orange, green, red; radius 0.055 m, thickness 0.012 m, with a dark spoke), one against the inside of each face opposite the pivot corner. Bindings: `link:cube` `pose` to the quaternion `Cube/pose[1..4]` and the position (0, 0, 0) (three inline `Origin` blocks with output unit m, `PosX`, `PosY`, `PosZ`, so that the pose binding passes the E303 unit check), and `joint:wheel_x`, `wheel_y`, `wheel_z` to the integrated wheel angles `Cube/phi1..3` (9.15, -2.46 and -6.69 rad after 4 s). The multibond models have no scene (their body frame sits on the structure centre, not at the pivot).

![3D view at t = 0 s|500](@fig:scene)

Continue with [the equation block](page:block), [the motors and the design](page:design), [the results](page:results) and [the multibond comparison](page:multibond).
@@ page cube-3d block overview | Equation block
# The equation block `CornerCube`

## Geometry and mass model

Body frame: the axes lie along the cube edges at the pivot, the cube occupies $[0, a]^3$. The wheel spin axes are the body axes; wheel $i$ is mounted on the inside of the face $x_i = a$, centred on the face, its centre $d$ inside the face:

| wheel | spin axis | centre $p_i$ (m) |
| --- | --- | --- |
| 1 | $x$ | (0.140, 0.075, 0.075) |
| 2 | $y$ | (0.075, 0.140, 0.075) |
| 3 | $z$ | (0.075, 0.075, 0.140) |

The arrangement is invariant under permutations of the axes, so the centre of mass stays on the body diagonal and the equilibrium is still "diagonal vertical".

| item | value | why |
| --- | --- | --- |
| wheel | steel rim wheel, radius 0.055 m, thickness $h$ = 12 mm, mass $m_w$ = 0.08 kg | leaves a 20 mm margin to the face edges and the wheels do not touch each other |
| inset $d$ | 10 mm = $h/2$ + 4 mm mounting gap | |
| axial inertia $\Theta_w$ | $1.9\cdot10^{-4}$ kg·m² (0.79 $m_w R^2$, rim-heavy) | rotor included |
| transverse inertia $\Theta_{wt}$ | $9.6\cdot10^{-5}$ kg·m² | $\Theta_w/2 + m_w h^2/12$ |
| structure | $m_s$ = 0.18 kg (frame, electronics, motors), $\Theta_s = 1.125\cdot10^{-3}$ kg·m² | thin cubic shell $\tfrac{5}{18} m_s a^2$; total mass $m_s + 3 m_w = 0.42$ kg |

The earlier example kept $\Theta_w = 6\cdot10^{-4}$ for each wheel at the cube centre. That is not possible for a wheel that fits on a 0.15 m face within a 0.42 kg total: a thin ring of radius 0.055 m has $m R^2 = 2.4\cdot10^{-4}$ for 0.08 kg, and $6\cdot10^{-4}$ would need 0.2 kg per wheel. So $\Theta_w$ is now $1.9\cdot10^{-4}$ (the wheels are three times weaker, and the design and numbers were redone).

Derived quantities (the block computes them from the parameters; `design.py` builds the same by the parallel-axis theorem body by body and the two agree to 1e-9):

$$m = m_s + 3 m_w = 0.42\ \mathrm{kg}, \qquad r = \frac{m_s\,a/2 + m_w\,(2a - d)}{m}\,(1, 1, 1) = 0.087381\ \mathrm{m}\,(1, 1, 1),$$

$$\Theta_c = \Theta_s I + m_s\big(\lvert c\rvert^2 I - c\,c^T\big) + \sum_i \Big[m_w\big(\lvert p_i\rvert^2 I - p_i p_i^T\big) + \Theta_{wt}\,(I - e_i e_i^T)\Big],$$

which comes out as a matrix with diagonal $8.2778\cdot10^{-3}$ and off-diagonal $-3.1425\cdot10^{-3}$ kg·m² (with $c = \tfrac a2 (1,1,1)$ the structure centre and $e_i$ the axis of wheel $i$). $\Theta_c$ is the inertia about the pivot with the wheels' spin excluded; the axial inertia of each wheel is $\Theta_w$ in $L_w$.

## Equations

States: the unit quaternion $q$ (body to world), the body rates $\omega$ and the wheel rates relative to the body $w_r$. With $T$ the torque the motors put on the wheels and $g_b = R^T\,(0, 0, -g)$:

$$L = \Theta_c\,\omega + \Theta_w\,(\omega + w_r), \qquad \dot\omega = \Theta_c^{-1}\big(-\omega \times L + r \times m g_b - T\big), \qquad \dot w_r = \frac{T}{\Theta_w} - \dot\omega, \qquad \dot q = \tfrac12\,q \otimes [0, \omega].$$

Block parameters of [Cube](block:Cube): `ms` 0.18, `mw` 0.08, `a` 0.15, `d` 0.01, `Ths` 1.125e-3, `Thw` 1.9e-4, `Thwt` 9.6e-5, `g` 9.81. Three `Rotation` ports `m1`, `m2`, `m3` carry `mi.f` $= w_{r,i}$ and $T_i =$ `mi.e`; the reaction $-T$ on the cube is inside the $\dot\omega$ equation, so each motor has its stator on a fixed shaft. Outputs: `pose` (the 7-element chart $(q_w, q_x, q_y, q_z, 0, 0, 0)$ that the controller reads), `omega`, `wheel`, `tilt` (angle between the body diagonal and the vertical), `qerr` ($\lvert q\rvert - 1$), `Hz` (vertical angular momentum about the pivot), `Hzw` (the wheels' part of it) and the integrated wheel angles `phi1..3`. The start value is the equilibrium tilted 2 deg about the world $x$ axis; the equilibrium rotates the diagonal $(1,1,1)/\sqrt3$ onto $(0,0,1)$: axis $(1,-1,0)/\sqrt2$, angle $\arccos(1/\sqrt3)$, $q_{eq} = (0.88807, 0.32506, -0.32506, 0)$.

Language limits met while writing it (all in the block, none in the compiler): the language has no matrix solve, so with $\Theta_c = (T_d - T_o)\,I + T_o\,u u^T$ ($u = (1,1,1)$) the inverse is written in closed form,

$$\Theta_c^{-1} = \frac{1}{T_d - T_o}\Big(I - \frac{T_o}{T_d + 2 T_o}\,u u^T\Big),$$

and `cross` needs equal units on both arguments (E006), so the cross products are written out component by component.
@@ page cube-3d design overview | Motors and LQR design
# Motors and LQR design

## The motors

Each wheel is driven by the stdlib `drives/ElectricDrive` ([Drv1](block:Drv1), [Drv2](block:Drv2), [Drv3](block:Drv3); $R = 1\ \Omega$, $L = 0.1$ mH, $k = 0.0335$ N·m/A): the DC motor of plan 9.9 as a composite of the same primitives, with a fixed stator and one `shaft` port. The plan asks for rotor inertia 0 because $\Theta_w$ already contains it, but a rotor of exactly 0 does not work: the rotor `Inertia` has its rate imposed by the block, a derivative-causal element. $J_m = 0$ fails at $t = 0$ (`Unstable`) and $J_m \le 10^{-8}$ fails at the controller ticks (`InitialFailure`); $10^{-6}$ and $10^{-5}$ run. The model uses $J_m = 10^{-6}$ kg·m², which adds 0.5 % of $\Theta_w$ to the wheel momentum and no more. `design.py` includes it exactly, and the multibond models use the same motor.

## The design (`design/design.py`)

A numpy replica of the equations (independent of the Julia code, with the mass model built body by body) is linearised by central differences at the equilibrium. The reduced state is $z = (\text{tilt}_1, \text{tilt}_2, \omega_{1..3}, w_{r,1..3})$ with $\text{tilt}_k = e_k\cdot \text{up}_b$, $\text{up}_b = R^T (0,0,1)^T$, $e_1 = (1,-1,0)/\sqrt2$, $e_2 = (1,1,-2)/\sqrt6$. The motor is the quasi-static $T = k\,(u - k\,w_r)/R$ ($L/R = 0.1$ ms against the 2 ms sample). The vertical angular momentum is conserved (gravity has no torque about a vertical axis through the pivot), so one mode of $z$ is uncontrollable at eigenvalue 1 once discretised: the Riccati equation is solved on $(A_d/\rho, B_d/\rho)$ with $\rho = 1.0005$ and the gain is applied to the true $(A_d, B_d)$.

Weights $Q = \mathrm{diag}(\sigma^{-2})$ with $\sigma_{tilt} = 0.02$, $\sigma_\omega = 0.2$ rad/s, $\sigma_{w_r} = 40$ rad/s, $R = I/12^2$, $T_s = 2$ ms. The gain for $u = -K z$ is

$$K = \begin{pmatrix} 243.44 & -421.64 & -53.955 & 14.533 & 14.533 & -0.16979 & 0.071768 & 0.071768 \\ 243.44 & 421.64 & 14.533 & -53.955 & 14.533 & 0.071768 & -0.16979 & 0.071768 \\ -486.87 & 0 & 14.533 & 14.533 & -53.955 & 0.071768 & 0.071768 & -0.16979 \end{pmatrix}.$$

Discrete closed-loop eigenvalues 0.17065, 0.69506 (x2), 0.98086 (x2), 0.99728 (x2) and 1 (the vertical-momentum mode); continuous equivalents $-884$, $-181.9$ (x2), $-9.66$ (x2), $-1.359$ (x2) and 0 s$^{-1}$ (open loop $+7.36$ (x2), $-7.61$ (x2), $-6.43$, $-5.73$ (x2), 0). `design.py` then integrates the non-linear closed loop (Radau, with the winding inductance, the 2 ms hold and the clamp) and writes $K$ as a Julia matrix literal into the `K` parameter of the controller node of all three models.

The controller block `CubeLQR` ([Ctrl](block:Ctrl), `library/CubeLQR.jl`) forms $z$ from the pose quaternion, the body rates and the wheel rates in a `@discrete Ts = 2e-3` scope ($\text{up}_b$ is the third row of $R(q)$, no trigonometry), computes $K z$ with the `Mat{3,8}` parameter and clamps to $\pm12$ V. The first sample is at $t = T_s$; the declared 0 V is held before it. The clamp is active only at the start: wheels 1 and 3 hit 12 V in the first samples; after 0.1 s the voltage of wheel 1 stays below 0.21 V.
@@ page cube-3d results overview | Results and checks
# Results and checks

![Tilt, wheel rates and motor voltages during the first second|900](@fig:run)

## Measured (README, real worker)

| quantity | design.py | `cube-3d` |
| --- | --- | --- |
| tilt at 0.1 s | 0.65854 deg | 0.65854 deg |
| tilt over $t \ge 3$ s (plan: below 0.5 deg) | 0.006046 deg | 0.006046 deg (1.056e-4 rad) |
| inside 0.5 deg from | 0.120 s | 0.120 s |
| tilt at 4 s | 0.00155 deg | 0.00155 deg |
| peak wheel rates relative to the cube (plan: below 400 rad/s) | 17.693 / 4.758 / 12.936 rad/s | 17.693 / 4.758 / 12.936 rad/s |
| peak $\lvert u\rvert$ | 12 V (wheels 1, 3); 4.45 V (wheel 2) | 12 V / 4.45 V / 12 V |
| quaternion norm error (plan: below 1e-6) | 1.4e-14 | 1.8e-14 |
| $\max\lvert H_z - H_z(0)\rvert$ | 2e-17 | 4.7e-17 |
| wheels' vertical momentum $H_{zw}$, peak | | 1.6e-4 N·m·s (back to 0 at the end) |

$H_z$ is the strong invariant: the wheels hold up to 1.6e-4 N·m·s of vertical momentum while the cube holds the opposite, and the sum stays at round-off. The slow closed-loop pole ($-1.36$ s$^{-1}$) is the wheel momentum bleeding off. The lighter wheels spin about 3.8 times faster than the $\Theta_w = 6\cdot10^{-4}$ wheels of the earlier version, far inside the 400 rad/s limit.

## Checks (`expected.json`, 82 checks in total for the three models)

`cube-3d`: the 2 deg start (tilt and quaternion), tilt under 0.5 deg for $t \ge 3$ s (and from 0.15 s), tilt cursor values at 0.1 to 4 s against `design.py`, peak tilt, the three wheel rates under 400 rad/s and against `design.py`, the integrated wheel angle, quaternion norm error under 1e-6, $H_z$ conserved against the wheels' $H_{zw}$, the $\pm12$ V clamp (active at the first samples, below 0.25 V after 0.1 s) and no E901, E106, W201, W202, W205 or W206.

## What to try

- Raise the start tilt (the `Cube` start values `qw..qz`, and `TILT0` in `design.py` for the reference): the clamp stays active longer and the wheels spin faster.
- Change a mass or `a` without re-running `design.py`: the gains are no longer matched, which shows the margin of the design.
- Change a weight or the sample time in `design/design.py` and run it: the new $K$ is written into all three models.
@@ page cube-3d multibond overview | Multibond comparison
# The multibond counterpart (DEC-M5-3)

`cube-3d-mb` builds the same cube from the M3 spatial stdlib in the structure of `reaction-wheel-3d`: `World` (`GroundSpatial`) to `Pivot` (`Spherical3D`, compliant) to `Link` (`FixedTransform3DNeutral`, the structure centre in the corner frame) to `Body` (`RigidBody3D` structure). The multibond models are documented in their own docs; this page records what is compared with the equation block.

| signal | window | $k_t = 10^8$ | $k_t = 10^6$ |
| --- | --- | --- | --- |
| tilt | whole run | 4.2e-7 rad | 2.4e-5 rad |
| body rates | from 0.05 s | 8.3e-8 / 2.7e-8 / 5.6e-8 rad/s | 4.3e-5 / 2.4e-5 / 2.0e-5 |
| body rates | from 0.5 s | 9.8e-9 / 2.7e-9 / 7.2e-9 | 7.4e-7 / 3.2e-7 / 4.3e-7 |
| wheel rates | from 0.05 s | 1.0e-5 / 2.3e-6 / 7.6e-6 rad/s | 3.8e-3 / 1.9e-3 / 1.8e-3 |

The soft-to-stiff ratio of the body-rate difference from 0.5 s is 75 / 122 / 59 for a stiffness ratio of 100; `compare_scaling` accepts a band of 50 to 150. The wheel rates are not a clean $1/k_t$ signal and are not used for the scaling check. The vertical momentum of body plus wheels is conserved to 5.7e-10 ($k_t = 10^8$) and 6.8e-7 ($k_t = 10^6$) of the 1.6e-4 N·m·s the wheels exchange.
@@ figures cube-3d-mb
{
  "diagram": {"kind": "diagram", "model": "cube-3d-mb"},
  "run": {
    "kind": "plot", "model": "cube-3d-mb", "xlim": [0, 1],
    "rows": [
      {"ylabel": "tilt Tilt/tilt [deg]", "series": [{"signal": "Tilt/tilt", "label": "Tilt/tilt", "scale": 57.29577951308232}]},
      {"ylabel": "wheel rate [rad/s]", "series": [{"signal": "Ctrl/wheel[1]", "label": "wheel 1"}, {"signal": "Ctrl/wheel[2]", "label": "wheel 2"}, {"signal": "Ctrl/wheel[3]", "label": "wheel 3"}], "legend": true}
    ]
  }
}
@@ page cube-3d-mb overview - | Overview
# Cube corner balancer on the spatial multibond stdlib

The cube of `cube-3d` rebuilt from the M3 spatial stdlib and run with the same controller (`project:CubeLQR`, the same gain $K$): [World](block:World) to the compliant [Pivot](block:Pivot) (`Spherical3D`, $k_t = 10^8$ N/m, $b_t = 1581$ N·s/m) to [Link](block:Link) (to the structure centre $(0.075, 0.075, 0.075)$) to [Body](block:Body) (structure, 0.18 kg, $J = 1.125\cdot10^{-3}$ kg·m² on all axes). Each wheel is a `RigidBody3D` ([Wheel1](block:Wheel1), 0.08 kg, $J = (9.6\cdot10^{-5}, 9.6\cdot10^{-5}, 1.9\cdot10^{-4})$) on a `Revolute3D` ([WJoint1](block:WJoint1): $k_r = 10^5$, $b_r = 10$, $k_t = 10^7$, $b_t = 1000$) whose axis (the joint's local $z$) is mounted onto the body $x$, $y$ or $z$ by a `FixedTransform3DNeutral` ([WMount1](block:WMount1)) **with the face offset in the mount**: the wheel centre is $a/2 - d = 0.065$ m from the cube centre along its body axis ([WLocal1](block:WLocal1) holds the pose for the composed-pose chain). Each wheel is driven by the same `ElectricDrive` ([Drv1](block:Drv1)) through a stiff `ElasticShaft` ([Shaft1](block:Shaft1): $k = 10^4$ N·m/rad, $d = 0.02$; a rotor rigidly on a rate-imposing joint is W201). The original $k = 100$ left a rotor-lag error in the wheel rates that was 50 times larger and did not scale with $1/k_t$.

![The model canvas|900](@fig:diagram)

Poses are composed (`ComposePose3D`), never integrated. The controller [Ctrl](block:Ctrl) reads the composed pose, the body twist (`Take3`, the first three components of `Body.V`) and the three joint rates (`Pack3`); [Tilt](block:Tilt) (`TiltMeter`) and [MeasBody](block:MeasBody) are sensors. The parameters match the equation block exactly (total mass 0.42 kg, centre of mass $0.087381\ \mathrm{m}\,(1,1,1)$); the physical differences are the compliant pivot (it sags by $m g/k_t$: 4.1e-8 m, measured maximum 5.0e-8 m), the compliant wheel joints and the shaft.

![Tilt and wheel rates, first second|900](@fig:run)

Plot [Tilt/tilt](signal:Tilt/tilt) next to `Cube/tilt` of the `cube-3d` model. The model has no 3D scene. Checks: the same start, tilt under 0.5 deg after 3 s, wheel rates under 400 rad/s, quaternion norm error, the vertical momentum of body plus wheels (`invariant`), the pivot sag at most 1e-7 m, and no E901, E106, E007, W201, W202, W205 or W206; the `compare` entries against `cube-3d` give 4.2e-7 rad in tilt (see the comparison page of `cube-3d`).
@@ figures cube-3d-mb-soft
{
  "diagram": {"kind": "diagram", "model": "cube-3d-mb-soft"}
}
@@ page cube-3d-mb-soft overview - | Overview
# Cube corner balancer, soft pivot

The `cube-3d-mb` model with a 100 times softer pivot: [Pivot](block:Pivot) has $k_t = 10^6$ N/m and $b_t = 158$ N·s/m (against $10^8$ and 1581). Everything else, including the controller and the gain $K$, is identical. The pivot sags by $m g/k_t = 4.1\cdot10^{-6}$ m (the check allows at most 1e-5 m).

![The model canvas|900](@fig:diagram)

Its purpose is the scaling measurement of DEC-M5-3: the difference between the equation block and the multibond cube is a $1/k_t$ effect, so softening the pivot by 100 makes the difference grow by about the same factor (75 / 122 / 59 for the body rates from 0.5 s; tilt difference 2.4e-5 rad against 4.2e-7 rad). Plot [Tilt/tilt](signal:Tilt/tilt). The model has no 3D scene.
