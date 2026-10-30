@@ figures balancer
{
  "diagram": {"kind": "diagram", "model": "balancer"},
  "scene": {"kind": "scene", "model": "balancer", "t": 1.0},
  "run": {
    "kind": "plot", "model": "balancer", "xlim": [0, 3],
    "rows": [
      {"ylabel": "body angle [rad]", "series": [{"signal": "Pivot/qout", "label": "Pivot/qout"}, {"signal": "Ctrl/ref", "label": "Ctrl/ref", "style": "--"}], "legend": true},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "WheelJ/qdout", "label": "WheelJ/qdout (relative to the body)"}], "legend": true},
      {"ylabel": "motor torque [N m]", "series": [{"signal": "Motor/p.e", "label": "Motor/p.e", "color": "#1b9e77"}]}
    ]
  }
}
@@ page balancer overview - | Overview
# Planar reaction-wheel balancer (gravity on)

An inverted planar body on a compliant pivot with a reaction wheel on its axis. A 1 ms PD controller on the body angle commands the wheel torque, and the wheel's reaction holds the body upright while the wheel spins up. This is the planar-balancer half of X-MB2 (plan 9.10) and Gate B's arm-and-balancer pair with `robot-arm-2d`. The body starts 0.01 rad off upright, the controller recovers it in about 0.5 s, then a 0.012 rad reference pulse (0.5 s to 1.5 s) tilts it and it returns. The sibling model `balancer-free` has gravity off.

![The model canvas|900](@fig:diagram)

```
Ground -- Pivot -- LinkB -- BodyJ -+- Body  (RigidBody2D, m 1.5, J 0.02, CoM 0.3 m)
         (kt, bt)  (0.3 m) (1-junc) '- WheelJ -- Wheel (RigidBody2D, J 0.002)
                          (rx = 0.2)   (kt, bt)   (its centre on the axis)
       Motor: MSe(tau) --------> WheelJ.drive
       Ref (Pulse 0.012 rad, 0.5-1.5 s) -> Balancer (1 ms) -> tau
```

## What to try

- Open **Plots**: "Body angle and reference", "Wheel speed", "Motor torque and momentum". The wheel spins up to 47 rad/s and keeps 46.2 rad/s at the end: gravity has delivered a net angular impulse that the wheel must store, the momentum-management story a real reaction wheel has to unload.
- Set `Ctrl/tau_max` to 0.05 N·m: the initial tilt already needs $G\sin(0.01) + K_p\cdot0.01 = 0.224$ N·m, so the motor cannot arrest it and the body falls (the 0.02 rad band check would fail).
- Set `Pivot/bt` and `WheelJ/bt` to 0 and rerun: the 1 ms sampled drive pumps the 3.6 kHz pivot mode and the run stops with E901 (MaxIters) at $t = 2.29$ s; the damper is part of the model.

## 3D view

`scenes/reaction-wheel-2d.sdf` draws the body bar on its pivot with the wheel at its top in the vertical X-Z plane. Joint `pivot` follows [Pivot/qout](signal:Pivot/qout) and `wheel_axis` follows [WheelJ/qout](signal:WheelJ/qout); the spoke makes the wheel spin visible.

![3D view at t = 1.0 s|500](@fig:scene)

Continue with [the physics](page:physics), [the controller](page:controller) and [the results](page:results).
@@ page balancer physics overview | Physics and graph
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
@@ page balancer controller overview | Controller
# Controller

[Ctrl](block:Ctrl) (project library `Balancer`, 1 ms) computes

$$e = \theta - \mathrm{ref}, \qquad \tau = \operatorname{clamp}\big(G\sin\theta + K_p\,e + K_d\,\dot\theta,\ -1.5,\ 1.5\big).$$

$G\sin\theta$ is the gravity torque about the pivot, so the settled angle equals the reference (no droop) and the closed loop is $J_A'\,\ddot\theta = -K_p\,e - K_d\,\dot\theta$, stable for any positive gains. With $K_p = 16$ N·m/rad and $K_d = 4$ N·m·s/rad: $\omega_n = \sqrt{K_p/J_A'} \approx 7.9$ rad/s, damping ratio about 1.0, and $\lvert\tau\rvert \le 1.5$ N·m.
@@ page balancer results overview | Results and checks
# Results and checks

![Body angle, wheel speed and motor torque|900](@fig:run)

## Measured (README)

| quantity | value |
| --- | --- |
| $\lvert\theta\rvert$ over the run | 0.011969 rad at the pulse (band 0.02) |
| $\theta$ at 0.5 s (initial tilt recovered) | 0.000907 rad |
| tracked error before the pulse | $\max\lvert e\rvert = 1.72\cdot10^{-3}$ rad over $[0.4, 0.5]$ s |
| wheel speed | 0 to 47.046 rad/s (peak at 1.782 s), 46.213 rad/s at the end |
| motor torque | -0.195 to 0.269 N·m (limit 1.5) |
| mechanical energy | 6.3762 J to a peak of 8.5877 J (the wheel's 2.211 J) |
| states | 12 differential (2 x P[3], 2 x d[2], 2 x q), no W201 |

## Checks (`expected.json`)

$\theta_0 = 0.01$; $\lvert\theta\rvert \le 0.02$ rad over the run; the tilt is recovered to 0.9 mrad at 0.5 s and the tracked error stays under 2 mrad before the pulse; the wheel starts at rest, peaks at 47.05 rad/s and keeps 46.21 rad/s; the torque stays inside 1.5 N·m; the wheel speed stays under 50 rad/s; the mechanical energy is bounded by 8.9 J $= E_0 + \tfrac12 J_w 50^2$; no W201, E101, E102, E103, E106 or W206.
@@ figures balancer-free
{
  "diagram": {"kind": "diagram", "model": "balancer-free"},
  "run": {
    "kind": "plot", "model": "balancer-free", "xlim": [0, 3],
    "rows": [
      {"ylabel": "body angle [rad]", "series": [{"signal": "Pivot/qout", "label": "Pivot/qout"}, {"signal": "Ctrl/ref", "label": "Ctrl/ref", "style": "--"}], "legend": true},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "WheelJ/qdout", "label": "WheelJ/qdout"}], "hlines": [{"y": 30, "label": "initial 30 rad/s"}], "legend": true},
      {"ylabel": "motor torque [N m]", "series": [{"signal": "Motor/p.e", "label": "Motor/p.e", "color": "#1b9e77"}]}
    ]
  }
}
@@ page balancer-free overview - | Overview
# Balancer with gravity off: conservation of angular momentum

The same balancer as the `balancer` model, with `g0` = 0 in both bodies and in the controller ([Ctrl](block:Ctrl)). The wheel starts at **30 rad/s** (`inertia/P` = (0.06, 0, 0) of [Wheel](block:Wheel)) and the body at $\theta_0 = 0$. The total angular momentum about the pivot

$$H = 0.257\,\dot\theta + 0.002\,\dot q_w$$

must then stay constant at 0.06 kg·m²/s: the motor only exchanges momentum between body and wheel. See the `balancer` model for the physics, the controller (without the gravity term) and the parameters.

![The model canvas|900](@fig:diagram)

## Results

![Body angle, wheel speed and motor torque without gravity|900](@fig:run)

The same 0.012 rad pulse leans the body; the wheel **spins down to 25.99 rad/s** as the body leans and **back up to 32.70 rad/s** as it returns, ending at 30.0007 rad/s. $H$ stays at 0.06 kg·m²/s: $\max\lvert H - H_0\rvert = 5.27\cdot10^{-9}$, that is $8.78\cdot10^{-8}$ of $H$ (tolerance 1e-6, the `invariant` check on `Pivot/qdout` with coefficient 0.257 and `WheelJ/qdout` with 0.002). $\lvert\theta\rvert$ stays below 0.011967 rad (band 0.02).

Checks: $\theta_0 = 0$, wheel 30 rad/s; the wheel dips to 25.99 and rises to 32.70 rad/s; torque bound; the invariant; no W201, E101, E102, E103, E106, W206.

## What to try

Plot [WheelJ/qdout](signal:WheelJ/qdout) next to [Pivot/qdout](signal:Pivot/qdout): the wheel rate moves exactly opposite to the body rate times 128 ($J_A/J_w = 0.257/0.002$) whenever the pulse moves the body; their weighted sum is the constant $H$.
