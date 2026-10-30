# Physics

A planar multibond carries the twist $V = (\omega, v_x, v_y)$ and the wrench $W = (\tau, f_x, f_y)$ with power $W\cdot V$. A planar revolute joint couples a 3-DOF body (one rotation, two translations) to a 1-DOF rotation, and its hard constraints are the **two pivot translations**, not the rotation. A rigid revolute on a rigid 3-DOF body is therefore index-3 by construction: MTK's index reduction puts two momentum components in derivative causality and reports two W201 by design (plan 5.5, DEC-MB-2).

This example uses the **compliant-pivot** `Revolute2D` ([Joint](block:Joint)):

- the rotation is exact: $q$ is the link-side angle with joint pose $g(q) = (q, r_x, r_y)$, $r_x = r_y = 0$, so the measured period is the physical pendulum period;
- the two pivot translations are spring states $d$ with stiffness $k_t = 10^8$ N/m and damping $b_t = 0$; the joint effort is $f_s = k_t\,d + b_t\,V_{rel}$, so the body sees the restoring force and the joint stores $\tfrac12 k_t\lvert d\rvert^2$;
- the state is only $P$ (3 momenta), $d$ (2 deflections) and $q$: **six differential states**, no algebraic constraint forces, **no W201**. $k_t \to \infty$ recovers the rigid revolute.

## The flat graph

Every box is a documented primitive or a junction.

| instance | block | role |
| --- | --- | --- |
| [Ground](block:Ground) | `GroundPlanar` | world flow source, $f = 0$ |
| [Pivot](block:Pivot) | 0-junction | common pivot wrench: joins `Ground`, [De](block:De) and `Joint.parent` |
| [De](block:De) | `DePlanar` | zero-flow effort tap: the pivot reaction wrench |
| [Joint](block:Joint) | `Revolute2D` | compliant-pivot revolute, $r_x = r_y = 0$, $k_t = 10^8$, $b_t = 0$, `q0` = 0.01 |
| [Drive](block:Drive) | `Se` | $e = 0$ N·m on the `Rotation` port: torque-free |
| [Link](block:Link) | `FixedTransform2D` | pivot to CoM: $x = 0$, $y = -0.5$ m, $\theta = \pi/2$ (the 90 deg body frame) |
| [J1](block:J1) | 1-junction | common CoM twist: Body, Gravity, Coriolis, Df |
| [Body](block:Body) | `IPlanar` | $J = 10^{-4}$ kg·m², $m = 1$ kg; $P$ is the state |
| [Gravity](block:Gravity) | `GravityPlanar` | $m = 1$, $g_0 = 9.81$ m/s², CoM wrench from the composed pose |
| [Coriolis](block:Coriolis) | `CoriolisPlanar` | $e = -\mathrm{ad}(V)^T P$, $P$ from `Body.Pm` |
| [Df](block:Df) | `DfPlanar` | zero-effort flow tap: the body twist |
| [CoMOffset](block:CoMOffset) | inline `CoMOffsetPose2D` | constant local pose $(\pi/2, 0, -0.5)$ as a signal |
| [Compose](block:Compose) | `ComposePose2D` | composed CoM pose $g = g_{joint}\circ g_{offset}$ |

`CoMOffset` is the one non-bond-graph box: a constant pose signal, the role the signal sources play in the M2 examples (D28); it is an inline block because the language has no vector-constant source yet.

## Equations

The CoM pose is **composed from $q$, never integrated** (D-MB6): $\theta = q + \pi/2$. Gravity applies the body-frame effort $(0,\ \sin\theta\; m g,\ \cos\theta\; m g)$ (the negative of the physical wrench, because a 1-junction sums efforts); through the link and the joint this is the physical pendulum torque $-m g L \sin q$. The Coriolis term is Breedveld's Eulerian junction structure, $e = -\mathrm{ad}(V)^T P$, with $P$ taken as a signal from `IPlanar`, so the inertia is never copied out of `I` (D-MB3). With $L = 0.5$ m the angle obeys

$$(J + m L^2)\,\ddot q = -m g L \sin q .$$

## Initial pivot deflection

At $q_0 = 0.01$ rad the pivot carries the weight, and the released-from-rest state has the angular acceleration $\alpha = -m g L \sin q_0/(J + m L^2)$. The pivot spring must supply the tangential reaction, so

$$d_0 = \left(-\frac{m g J}{J + m L^2}\,\frac{\sin q_0}{k_t},\ -\frac{m g\cos q_0}{k_t}\right) = (-3.9223657\cdot10^{-13},\ -9.8095095\cdot10^{-8})\ \mathrm{m}$$

in the rotating child frame (the start values of `Joint.d`). This released-from-rest $d_0$ keeps the fast translational mode ($\sqrt{k_t/m} = 10^4$ rad/s) from being excited; the held static value $(-m g\sin q_0/k_t, \dots)$ would apply a spurious tangential force and let the integrator damp the spring transient as energy drift.

## The two-stroke visual

The stroke count encodes the model dimension, not the port size: a `Planar` port has three components but is drawn as two parallel strokes with one half arrow per stroke and one causal bar across the bundle; a `Spatial` port is three strokes; a scalar domain one stroke. Every `Power{Planar}` bond here carries `data-multibond-strokes="2"`, while the drive bond (`Power{Rotation}`) stays single.
