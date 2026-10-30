# Physics

The body is a 3-DOF planar rigid body on the compliant-pivot revolute ([Pivot](block:Pivot), `kt` = 1e9 N/m, `bt` = 5e3 N·s/m); the wheel is a second `RigidBody2D` on a second compliant revolute ([WheelJ](block:WheelJ)) whose axis is 0.5 m above the pivot (the body CoM frame offset $r_x = 0.2$ m plus the 0.3 m CoM). The body frame's x axis points along the link, so the composed body angle is $\theta = q + \pi/2$ and the wheel's absolute rate is $\dot\theta + \dot q_w$.

With the motor torque $\tau$ on the wheel, the reaction $-\tau$ acts on the body:

$$J_A'\,\ddot\theta = -\tau + G\sin\theta, \qquad J_w\,(\ddot\theta + \ddot q_w) = \tau, \qquad J_A' = J_b + m_b l_{c,b}^2 + m_w L_w^2 .$$

The total angular momentum about the pivot is

$$H = J_A\,\dot\theta + J_w\,\dot q_w, \qquad J_A = J_A' + J_w = 0.257\ \mathrm{kg\,m^2},\ J_w = 0.002\ \mathrm{kg\,m^2},$$

and with gravity off the motor torque is internal, so $H$ is constant (the `invariant` check of `balancer-free`).

| parameter | value |
| --- | --- |
| body | $m_b = 1.5$ kg, $J_b = 0.02$ kg·m², CoM 0.3 m above the pivot |
| wheel | $m_w = 0.4$ kg, $J_w = 0.002$ kg·m², axis $L_w = 0.5$ m above the pivot |
| pivots | $k_t = 10^9$ N/m, $b_t = 5\cdot10^3$ N·s/m (both joints) |
| gravity torque | $G = g_0\,(m_b l_{c,b} + m_w L_w) = 9.81\,(0.45 + 0.2) = 6.3765$ N·m |
| reference | [Ref](block:Ref): `Pulse` 0.012 rad, `t_start` 0.5 s, period 4 s, duty 0.25 (high 0.5 to 1.5 s) |
| initial state | `Pivot.q0` = 0.01 rad (the start deflections are the released-from-rest values) |
| run | 3 s, 3001 points, `reltol` 1e-9, `abstol` 1e-11 |

## The flat graph

| instance | block | role |
| --- | --- | --- |
| [Ground](block:Ground) | `GroundPlanar` | world flow source |
| [Pivot](block:Pivot) | `planar/Revolute2DCompliant` | compliant pivot; `bt` damps the fast translational mode |
| [LinkB](block:LinkB) | `planar/FixedJoint2D` | pivot child to body CoM ($y = 0.3$ m, $\theta = \pi/2$) |
| [BodyJ](block:BodyJ) | 1-junction | common body twist |
| [Body](block:Body), [Wheel](block:Wheel) | `planar/RigidBody2D` | body and wheel |
| [PivotSe](block:PivotSe) | `Se` $e = 0$ | the pivot's `Rotation` drive is unpowered |
| [Motor](block:Motor) | `MSe` | wheel torque from the controller |
| [PoseJ1](block:PoseJ1), [CoMB](block:CoMB), [PoseB](block:PoseB), [PoseWrel](block:PoseWrel), [PoseW](block:PoseW) | pose blocks | the composed pose chain |
| [Ctrl](block:Ctrl) | `project:Balancer` | the 1 ms PD and feedforward firmware (the only non-bond-graph part, the D28 exception) |

The poses are composed, never integrated (D-MB6). Every `Power{Planar}` bond is a two-stroke bundle with one causal bar; the two `Rotation` drive bonds stay single-stroke.
