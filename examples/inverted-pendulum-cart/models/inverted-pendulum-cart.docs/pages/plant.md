# Plant: a point-mass cart-pole as a bond graph

| part | bond graph |
| --- | --- |
| cart | 1-junction [CartJ](block:CartJ) with `I` [IM](block:IM) ($M$ = 1 kg), `R` [RB](block:RB) ($b$ = 0.1 N·s/m) and the effort source [MSe1](block:MSe1) (the force $u$) |
| point mass at the rod tip | two translational `I` elements [IMx](block:IMx), [IMv](block:IMv) (0.2 kg each) for the horizontal and vertical tip velocity, plus gravity [MSeG](block:MSeG) (gain $-m g = -1.962$ N) on the vertical one |
| kinematics | modulated transformers [MTFh](block:MTFh) (modulus $l\cos\theta$) and [MTFv](block:MTFv) (modulus $l\sin\theta$) between the pendulum 1-junction [PendJ](block:PendJ) and the junctions [HS](block:HS), [VJ](block:VJ) |
| sensors | two project-library `FlowSensor` blocks ([CartSensor](block:CartSensor), [PendSensor](block:PendSensor)) and two integrators [XInt](block:XInt), [ThetaInt](block:ThetaInt) that turn the flows into $x$ and $\theta$ ($\theta(0) = 0.1$ rad) |

With the cart velocity $v$ and pendulum rate $\omega$ the junctions impose

$$v_x = v + l\,\omega\cos\theta, \qquad v_y = -\,l\,\omega\sin\theta ,$$

with $l = 0.5$ m (the gains [LSin](block:LSin), [LCos](block:LCos) provide $l\sin\theta$ and $l\cos\theta$). `PendJ` carries no `I` element: the point mass has no rod inertia of its own, its inertia about the pivot $J_p = m l^2$ is exactly what the two translational masses produce through the transformers. That is the model `design.py` linearises, so design and plant agree by construction.

The equations of motion that result are

$$(M+m)\,\ddot x + m l \cos\theta\,\ddot\theta - m l \sin\theta\,\dot\theta^2 = u - b\,\dot x,$$

$$m l \cos\theta\,\ddot x + m l^2\,\ddot\theta - m g l \sin\theta = 0 .$$

| parameter | value |
| --- | --- |
| $M$ (cart) | 1 kg |
| $m$ (tip mass) | 0.2 kg |
| $l$ (rod) | 0.5 m |
| $b$ (cart friction) | 0.1 N·s/m |
| $g$ | 9.81 m/s² (through the gravity source -1.962 N) |
| $\theta(0)$ | 0.1 rad |

The two sensors and two integrators are the only non-bond-graph pieces of the plant (the D28 sensor exception): they reconstruct a position and an angle for the moduli and the controller. The run uses `reltol` 1e-8 and `abstol` 1e-10 on 4001 points for $t_{end}$ = 4 s.

## Limitation: an index-2 DAE

A point mass carries two translational stores but only one rotational degree of freedom, so one store is algebraically tied to the others. The run reports W201 for `IMv` (and the lowering for `IM`), W205 and no W202. The model still solves (derivative causality is legal bond graph practice), but the tool has no planar/vector inertia that would hold the 2x2 mass matrix $\begin{pmatrix} M+m & m l\cos\theta \\ m l\cos\theta & m l^2\end{pmatrix}$ in two integral stores. Multibond planar components are M3 work; until then the two-mass representation is the honest bond graph model and it reproduces the equations above exactly (a constant-force run agrees with an independent RK4 of those equations to 1e-9).
