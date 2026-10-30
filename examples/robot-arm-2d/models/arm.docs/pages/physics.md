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
