@@ figures arm
{
  "diagram": {"kind": "diagram", "model": "arm"},
  "scene": {"kind": "scene", "model": "arm", "t": 0.5},
  "run": {
    "kind": "plot", "model": "arm", "xlim": [0, 3],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Joint1/qout", "label": "q1"}, {"signal": "Joint2/qout", "label": "q2"}, {"signal": "Ref1/y", "label": "q1 ref", "style": "--", "color": "#1f77b4"}, {"signal": "Ref2/y", "label": "q2 ref", "style": "--", "color": "#d95f02"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "joint torque [N m]", "series": [{"signal": "Drive1/p.e", "label": "Drive1/p.e"}, {"signal": "Drive2/p.e", "label": "Drive2/p.e"}], "hlines": [{"y": 30, "label": "limit 1: 30 N m"}], "legend": true},
      {"ylabel": "end effector [m]", "series": [{"signal": "PoseTip/g[2]", "label": "x"}, {"signal": "PoseTip/g[3]", "label": "y"}], "legend": true}
    ]
  }
}
@@ page arm overview - | Overview
# Planar 2-link arm on the multibond mechanics

A two-link planar arm with a payload, driven by a 1 ms PD controller with gravity feedforward, built from the J-MB6 composites (`RigidBody2D`, `Revolute2DCompliant`, `JointPose2D`, `LocalPose2D`) and the J-MB5 planar primitives (`ComposePose2D`, `GravityPlanar`, `CoriolisPlanar`). It is the planar-multibond arm of plan 9.10 / X-MB2 and, together with `reaction-wheel-2d`, Gate B's arm-and-balancer pair. The model `arm-free` removes the drives to test energy conservation.

![The model canvas: two-stroke planar bonds|900](@fig:diagram)

```
Ground -- Joint1 -- Link1 -- BodyJ1 -+- Body1 (1-junction: I + Coriolis + Gravity + Df)
         (kt, bt)   (0.2 m)  (1-junc) '- Joint2 -- Link2 -- Body2
                                (rx = 0.2)  (kt, bt)   (0.2 m)  (link 2 + payload)
Drive1: MSe(u1) -> Joint1.drive        Drive2: MSe(u2) -> Joint2.drive
Ref1/Ref2 (Step at 0.2 s) -> ArmPD (1 ms) -> u1, u2
```

At $t = 0.2$ s the references step to $q_1 = 0.6$ rad and $q_2 = -0.4$ rad; the shoulder saturates at its 30 N·m limit for about 0.1 s and both joints settle.

## What to try

- Plot [Joint1/qout](signal:Joint1/qout), [Joint2/qout](signal:Joint2/qout), [Drive1/p.e](signal:Drive1/p.e), [PoseTip/g[2]](signal:PoseTip/g[2]), [PoseTip/g[3]](signal:PoseTip/g[3]) (the preconfigured plots show angles, torques, end effector and joint rates).
- Set `Ctrl/g0` to 0: the gravity feedforward disappears and the shoulder droops (measured 0.5549 rad at the reference with the elbow at -0.4979); the cursor check at 3 s then fails, the intended signal that the feedforward does the holding.
- Set `Ctrl/u1max` to 5 N·m: the arm cannot hold the reference against gravity (the static demand is 10.98 N·m).
- Set `Joint1/bt` and `Joint2/bt` to 0: the fast pivot mode is pumped by the 1 ms drive and the solver stops with E901 (MaxIters) at $t = 2.54$ s; see [the notes](page:notes).

## 3D view

`scenes/robot-arm-2d.sdf` draws the two links in the vertical X-Z plane (the model's x-y plane). Joints `shoulder` and `elbow` follow `Joint1/qout` and `Joint2/qout`; the tip sphere sits at the end-effector pose `PoseTip`, which `expected.json` checks against the SDF kinematics along the whole run.

![3D view at t = 0.5 s|500](@fig:scene)

Continue with [the physics](page:physics), [the controller](page:controller) and [the results](page:results).
@@ page arm physics overview | Physics and graph
# Physics

Each link is a **3-DOF planar body** (`RigidBody2D`: the port is the body 1-junction with `IPlanar`, `CoriolisPlanar`, `GravityPlanar` and a zero-power `DfPlanar` tap) attached to a **compliant-pivot revolute joint** ([Joint1](block:Joint1), [Joint2](block:Joint2)). A rigid revolute on a rigid 3-DOF body is index-3 (the two pivot translations are hard constraints), so the joint is the `Revolute2DCompliant` of DEC-MB-2: the rotation is exact ($q$ is the link-side angle) and the two pivot translations are spring states $d$ with $k_t$, $b_t$. Every state stays integral: 12 differential states (2 x P[3], 2 x d[2], 2 x q) and no W201. The elbow pivot is expressed as $r_x = 0.2$ m in the link-1 centre-of-mass frame.

The **poses are composed, never integrated** (D-MB6). The chain mirrors the power chain:

| pose | composition | meaning |
| --- | --- | --- |
| [PoseJ1](block:PoseJ1) | `JointPose2D(q1)` | link-1 base frame |
| [PoseB1](block:PoseB1) | $\text{PoseJ1} \circ (0.2, 0, 0)$ ([CoM1](block:CoM1)) | body-1 centre of mass, feeds `Body1.g` |
| [PoseJ2](block:PoseJ2) | $\text{PoseB1} \circ \text{JointPose2D}(r_x = 0.2, q_2)$ ([PoseJ2rel](block:PoseJ2rel)) | joint-2 child frame |
| [PoseB2](block:PoseB2) | $\text{PoseJ2} \circ (0.2, 0, 0)$ ([CoM2](block:CoM2)) | body-2 centre of mass, feeds `Body2.g` |
| [PoseTip](block:PoseTip) | $\text{PoseJ2} \circ (0.3, 0, 0)$ ([TipOffset](block:TipOffset)) | end effector, `PoseTip/g[2..3]` |

`GravityPlanar` reads `Body.g`, so gravity acts at the true centre of mass; `CoriolisPlanar` takes the momentum tap `Pm` and applies Breedveld's $e = -\mathrm{ad}(V)^T P$ (D-MB3). The composed pose is an exact function of the measured angles, which the `planar_fk` check proves:

$$x_{tip} = 0.4\cos q_1 + 0.3\cos(q_1 + q_2), \qquad y_{tip} = 0.4\sin q_1 + 0.3\sin(q_1 + q_2),$$

to $1.1\cdot10^{-16}$ m.

## Parameters

| parameter | value |
| --- | --- |
| link 1 | $L_1 = 0.4$ m, $l_{c1} = 0.2$ m, $m_1 = 2$ kg, $J_1 = m_1 L_1^2/12 = 0.02667$ kg·m² |
| link 2 and payload | $L_2 = 0.3$ m, $l_{c2} = 0.2$ m, $m_2 = 1.5$ kg, $J_2 = 0.015$ kg·m² |
| payload | 0.5 kg at the tip: the 1.0 kg rod gives $I_{elbow} = 0.03$, the payload 0.045; combined CoM 0.2 m, $J_{com} = 0.075 - 1.5\cdot0.2^2 = 0.015$ |
| pivots | $k_t = 10^8$ N/m, $b_t = 10^3$ N·s/m (driven), 0 (free) |
| reference | $q_1: 0 \to 0.6$ rad, $q_2: 0 \to -0.4$ rad at $t = 0.2$ s ([Ref1](block:Ref1), [Ref2](block:Ref2)) |
| gravity | $g_0 = 9.81$ m/s² |
| run | 3 s, 3001 output points, `reltol` 1e-9, `abstol` 1e-11 |

## The flat graph

[Ground](block:Ground) (world flow source), [Joint1](block:Joint1) shoulder, [Link1](block:Link1) (`FixedJoint2D`, $x = 0.2$ m), [BodyJ1](block:BodyJ1) (common link-1 twist), [Body1](block:Body1) ($m = 2$, $J = 0.02667$), [Joint2](block:Joint2) elbow, [Link2](block:Link2), [Body2](block:Body2) ($m = 1.5$, $J = 0.015$), the drives [Drive1](block:Drive1), [Drive2](block:Drive2) (`MSe`, gain 1), the firmware [Ctrl](block:Ctrl). `ArmPD` is the only non-bond-graph part (sampled firmware, the D28 exception).

Every `Power{Planar}` bond is a two-stroke bundle with one half arrow per stroke and one causal bar; the drive bonds (`Rotation`) stay single-stroke.
@@ page arm controller overview | Controller
# Controller: PD with gravity feedforward

[Ctrl](block:Ctrl) (project library `ArmPD`, `@discrete Ts = 1e-3`) samples the two joint angles and rates and holds the torque until the next tick:

$$e_i = \mathrm{ref}_i - q_i, \qquad u_i = \operatorname{clamp}\big(K_{p,i}\,e_i - K_{d,i}\,\dot q_i + G_i,\ -u_{i,max},\ u_{i,max}\big),$$

$$G_1 = g_0\big(m_1 l_{c1}\cos q_1 + m_2\,(L_1\cos q_1 + l_{c2}\cos(q_1 + q_2))\big), \qquad G_2 = g_0\,m_2\,l_{c2}\cos(q_1 + q_2).$$

| parameter | joint 1 | joint 2 |
| --- | --- | --- |
| $K_p$ (N·m/rad) | 250 | 30 |
| $K_d$ (N·m·s/rad) | 26 | 3 |
| torque limit (N·m) | 30 | 10 |

$G$ is the gravity torque about each joint at the sampled configuration, so the settled error is zero instead of the PD droop $G/K_p$. The derivative acts on the measurement, so the reference step produces no derivative kick; `clamp` inside `@discrete` is generated code, not a symbolic `ifelse`, so the torque limit creates no event. The gains give a closed-loop bandwidth of about 3 Hz with both modes near critical damping.
@@ page arm results overview | Results and checks
# Results and checks

![Joint angles, torques and end effector position|900](@fig:run)

## Measured (README, real worker)

| quantity | value |
| --- | --- |
| $q_1$, $q_2$ at $t = 3$ s | 0.600000000002, -0.3999999999998 rad |
| settled error | $\max\lvert e_1\rvert = 4.9\cdot10^{-9}$, $\max\lvert e_2\rvert = 2.0\cdot10^{-8}$ rad over $[2, 3]$ s |
| 1 mrad settle time | 0.63 s after the step |
| peak joint torque | 30.000 N·m (shoulder, at its limit) and 9.061 N·m (elbow) |
| peak joint rate | 3.158 rad/s ($q_1$), 5.056 rad/s ($q_2$) |
| tip at $t = 3$ s | (0.6241542193, 0.2854577886) m, angle 0.2 rad |
| analytic FK of (0.6, -0.4) | $0.4\cos0.6 + 0.3\cos0.2 = 0.6241542193$, $0.4\sin0.6 + 0.3\sin0.2 = 0.2854577886$ |
| pose chain against FK over the run | 1.11e-16 m |
| run cost | 54899 adaptive steps (driven, 6003 rows), 262891 (free) |

## Acceptance checks (`expected.json`)

- [Joint1/qout](signal:Joint1/qout) = 0.6 and [Joint2/qout](signal:Joint2/qout) = -0.4 at 3 s within 1e-6 rad; the errors [Ctrl/e1](signal:Ctrl/e1), [Ctrl/e2](signal:Ctrl/e2) below 1e-6 rad over $[2, 3]$ s and below 1 mrad from 0.9 s;
- drive efforts within 30 / 10 N·m;
- `planar_fk` holds to 1e-6 m over all samples; the tip passes the cursor points at 0.3, 0.5 and 1.0 s (2 mm) and the analytic FK at 3 s (1e-6 m);
- an `energy_ledger` check on the driven run (tolerance 2e-4) in addition to what the README lists; no W201, E101, E102, E103, E106 or W206.
@@ page arm notes overview | Notes and limitations
# Notes

## Pivot damping

$k_t = 10^8$ N/m puts the pivot's translational mode at $\sqrt{k_t/m} \approx 1.6$ kHz, above the 1 ms controller. Without damping the drive's torque steps pump that undamped mode: $d$ grows from 3e-7 m to 1e-4 m and the run ends in **E901 (MaxIters) at $t = 2.54$ s**. The driven model therefore uses $b_t = 10^3$ N·s/m ($\zeta = 0.027$). The torque-free model keeps $b_t = 0$ so its energy budget is conservative.

## J-MB6 limitation found while building this example

A `FixedJoint2D` with a lever arm ($x \ne 0$) on a body's 1-junction leaves two algebraic unknowns in the compiled mass-matrix DAE whose initial values are NaN, so the run dies at $t = 0$ with E901. The same topology with the offset in the joint's `rx` parameter compiles to 12 differential states and runs; this model therefore uses `rx` for the elbow. The 1 ms controller turning the undamped 1.6 kHz pivot mode unstable is a physical, sampled-data effect, not a compiler bug.
@@ figures arm-free
{
  "diagram": {"kind": "diagram", "model": "arm-free"},
  "run": {
    "kind": "plot", "model": "arm-free", "xlim": [0, 3],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Joint1/qout", "label": "q1"}, {"signal": "Joint2/qout", "label": "q2"}], "legend": true},
      {"ylabel": "end effector [m]", "series": [{"signal": "PoseTip/g[2]", "label": "x"}, {"signal": "PoseTip/g[3]", "label": "y"}], "legend": true}
    ]
  }
}
@@ page arm-free overview - | Overview
# Torque-free arm: an energy budget

The same plant as the `arm` model with both drives removed ([Drive1](block:Drive1), [Drive2](block:Drive2) are `Se` with $e = 0$), no pivot damping ($b_t = 0$) and no controller. The start pose is $q_1 = 0.6$ rad, $q_2 = -0.4$ rad (the `q0` of the joints) at rest with relaxed pivot springs ($d = 0$). The arm falls under gravity and swings; the plant is conservative.

![The model canvas|900](@fig:diagram)

![Joint angles and end effector of the falling arm|900](@fig:run)

## Energy budget

The total mechanical energy, kinetic plus gravitational plus the two pivot strain terms, must stay constant:

$$E = \sum_i \Big[\tfrac12 P_i^T M_i^{-1} P_i + m_i g\,h_i\Big] + \sum_j \tfrac12 k_t\,\lvert d_j\rvert^2, \qquad h_i = y_{pose,i} + \sin q_1\,d_1 + \cos q_1\,d_2\ \big[+ \sin\theta_2\,e_1 + \cos\theta_2\,e_2\ \text{for link 2}\big],$$

with `PoseJ2/g[1]` $= \theta_2 = q_1 + q_2$ (the absolute angle of the joint-2 child frame) and the swing being the potential drop from the start pose to the hanging pose, $6.1238265 - (-12.7530) = 18.8768265$ J. The README measures a drift of $5.82\cdot10^{-6}$ J over 3 s, that is $3.09\cdot10^{-7}$ of the swing, with 262891 adaptive steps.

## Checks

The start pose ([Joint1/qout](signal:Joint1/qout) = 0.6, [Joint2/qout](signal:Joint2/qout) = -0.4 at $t = 0$); the `planar_fk` check to 1e-6 m; the multi-body `energy` drift (tolerance 1e-6 of the swing); an `energy_ledger` check with tolerance 2e-6 and zero source work; no W201, E101, E102, E103, E106, W206.
