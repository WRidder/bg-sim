@@ figures inverted-pendulum-cart
{
  "diagram": {"kind": "diagram", "model": "inverted-pendulum-cart"},
  "scene": {"kind": "scene", "model": "inverted-pendulum-cart", "t": 1.7},
  "run": {
    "kind": "plot", "model": "inverted-pendulum-cart", "xlim": [0, 4],
    "rows": [
      {"ylabel": "pendulum angle [deg]", "series": [{"signal": "ThetaInt/y", "label": "ThetaInt/y", "scale": 57.29577951308232}]},
      {"ylabel": "cart position [m]", "series": [{"signal": "XInt/y", "label": "XInt/y"}, {"signal": "XRef/y", "label": "XRef/y (reference)", "style": "--"}], "legend": true},
      {"ylabel": "force u [N]", "series": [{"signal": "MSe1/p.e", "label": "MSe1/p.e", "color": "#1b9e77"}], "hlines": [{"y": 20, "label": "clamp +-20 N"}, {"y": -20}], "legend": true}
    ]
  }
}
@@ page inverted-pendulum-cart overview - | Overview
# Cart-pole with an LQR balance controller

The classic cart-pole stabiliser (plan 9.6c). A cart on a rail balances a rod with a point mass at its tip. The run starts with the rod tilted by 0.1 rad, the controller catches it, and at $t = 1.5$ s the cart is asked to move 0.2 m. The continuous plant is a **pure bond graph** (D28); the controller is a linear-quadratic state feedback sampled at 1 ms, whose gains come from `design/design.py`.

![The model canvas|900](@fig:diagram)

## Run it

- Press **Run** and open the **Plots** tab: "Pendulum angle" ([ThetaInt/y](signal:ThetaInt/y)) shows the 0.1 rad recovery and the swing caused by the step, "Cart position" overlays [XInt/y](signal:XInt/y) and [XRef/y](signal:XRef/y), "Controller force" shows [MSe1/p.e](signal:MSe1/p.e), which peaks at 17.9 N, inside the 20 N limit.
- Change `LQR1.K_x` (or any `K_*`) and run again: the recovery becomes slower and the cart error grows.
- Raise the initial tilt (the start `x` of [ThetaInt](block:ThetaInt) to 0.2 rad): the force then hits the 20 N clamp exactly and the cart still settles at 0.2 m.

## 3D view

`scenes/inverted-pendulum-cart.sdf` shows the cart on its rail and the rod with the tip mass. Joint `rail` follows [XInt/y](signal:XInt/y) and joint `hinge` follows [ThetaInt/y](signal:ThetaInt/y) (positive towards +X). The picture is taken at 1.7 s, just after the cart reference step.

![3D view at t = 1.7 s|500](@fig:scene)

Continue with [the plant](page:plant), [the controller](page:controller) and [the results](page:results).
@@ page inverted-pendulum-cart plant overview | Plant (bond graph)
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
@@ page inverted-pendulum-cart controller overview | LQR controller
# LQR controller

[LQR1](block:LQR1) (`library/LQR.jl`) is the state feedback

$$u = \operatorname{clamp}\!\big(-(K_x\,(x - x_{ref}) + K_v\,v + K_\theta\,\theta + K_\omega\,\omega),\ -20,\ 20\big),$$

with $x_{ref}$ from [XRef](block:XRef), a step from 0 to 0.2 m at $t = 1.5$ s. It runs in a `@discrete Ts = 1e-3` scope: each 1 ms tick samples $x, v, \theta, \omega$ and holds the force until the next tick (the declared 0 N start is held for the first millisecond).

## Design

`design/design.py` linearises the plant at upright with the state $(x, v, \theta, \omega)$,

$$A = \begin{pmatrix} 0 & 1 & 0 & 0 \\ 0 & -b/M & -m g/M & 0 \\ 0 & 0 & 0 & 1 \\ 0 & b/(Ml) & (M+m)g/(Ml) & 0 \end{pmatrix}, \qquad B = \begin{pmatrix} 0 \\ 1/M \\ 0 \\ -1/(Ml) \end{pmatrix},$$

solves the continuous algebraic Riccati equation $A^T P + P A - P B R^{-1} B^T P + Q = 0$ and sets $K = R^{-1} B^T P$. The open-loop eigenvalues are $0$, $-0.083$, $-4.86$ and $+4.84$ s$^{-1}$ (one unstable pole).

The weights follow the normalisation $q_i = 1/\sigma_i^2$:

| state | scale $\sigma$ | weight | why |
| --- | --- | --- | --- |
| $x$ | 1.1 cm | $q_x = 8\cdot10^3$ | the cart position is the slow, weakly actuated mode, so it carries the largest weight |
| $v$ | 1 m/s | $q_v = 1$ | |
| $\theta$ | 0.1 rad | $q_\theta = 100$ | the force couples to the angle directly through $-1/(Ml)$, so it is cheap to control |
| $\omega$ | 0.32 rad/s | $q_\omega = 10$ | damps the angle rate |
| $u$ | 1 N | $R = 1$ | |

The result, written into the four `K_*` parameters of `LQR1`:

$$K = (-89.442719,\ -54.686555,\ -175.121631,\ -39.152990),$$

with closed-loop poles $-7.17 \pm 5.45\mathrm{j}$, $-5.28$ and $-4.10$. The force demand is 17.512 N at the initial tilt and peaks at 17.865 N at the reference step at 1.5 s, so the 20 N clamp stays inactive in the nominal run (about 10 % margin).

To recompute the gains: `uv run examples/inverted-pendulum-cart/design/design.py` (it rewrites the `K_*` values in the model file).
@@ page inverted-pendulum-cart results overview | Results and checks
# Results and checks

![Angle, cart position and force of the nominal run|900](@fig:run)

`design/design.py` integrates the non-linear closed loop independently (RK4, 0.1 ms, same law and clamp, but **continuous**); the model runs the 1 ms sampled controller. They agree to about 2 % in the fast recovery and the step, and to better than 0.5 % once settled. The zero-order hold shows in the initial recovery: at $t = 0.2$ s $\theta$ is about 4 % further along than the continuous reference, which is why that one cursor check carries 2.5 mrad.

| quantity | design.py (continuous) | bond graph run (1 ms hold), README |
| --- | --- | --- |
| peak $\lvert u\rvert$ (at 1.5 s) | 17.865 N | 17.877 N |
| $\theta$ over $[2.9, 3.0]$ s | 0.442 deg | 0.408 deg |
| $x(3.0\ \mathrm{s})$ (reference 0.2 m) | 0.19822 m | 0.19918 m |
| $\theta$ over $[3.5, 4.0]$ s | 0.058 deg | 0.042 deg |
| peak $\lvert\theta\rvert$ (during the step) | 6.86 deg | 6.94 deg |

## Acceptance checks (`expected.json`, 17 checks)

- the force $\lvert u \rvert$ peaks at 17.8647 N (tolerance 0.02), below the 20 N limit; the angle never exceeds the initial 0.1 rad (tolerance 1e-4) and the cart stays within 0.2 m + 1 cm;
- cursor values against the design reference: [XInt/y](signal:XInt/y) 0.086922 m at 0.2 s (tolerance 3 mm), 0.001005 at 1.45 s (1 mm), 0.096652 at 2.0 s (4 mm), 0.198217 at 3.0 s (2 mm), 0.199744 at 3.5 s and 0.199963 at 4.0 s (1 mm); [ThetaInt/y](signal:ThetaInt/y) -0.054606 at 0.2 s (2.5 mrad), 0.0028751 at 1.45 s and -0.0055751 at 3.0 s (1.5 mrad);
- recovered before the step: $\lvert x\rvert < 1$ cm and $\lvert\theta\rvert < 0.5$ deg over $[1.3, 1.45]$ s;
- settled after the step: $\lvert\theta\rvert < 0.5$ deg over $[2.9, 3.0]$ s and $< 0.1$ deg over $[3.5, 4.0]$ s;
- the scene binding is verified by forward kinematics of the pendulum tip (`scene_bindings` with `fk`, tolerance 1e-6);
- no E901, E106, W202 or W206.

The `W201`/`W205` warnings of the run are expected, see [the plant page](page:plant).
