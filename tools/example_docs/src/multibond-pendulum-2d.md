@@ figures pendulum
{
  "diagram": {"kind": "diagram", "model": "pendulum"},
  "scene": {"kind": "scene", "model": "pendulum", "t": 0.35},
  "run": {
    "kind": "plot", "model": "pendulum", "xlim": [0, 4],
    "rows": [
      {"ylabel": "joint angle q [rad]", "series": [{"signal": "Joint/q", "label": "Joint/q"}], "hlines": [{"y": 0.01}, {"y": -0.01}]},
      {"ylabel": "pivot deflection d [nm]", "series": [{"signal": "Joint/dout[1]", "label": "tangential d1", "scale": 1e9}, {"signal": "Joint/dout[2]", "label": "normal d2", "scale": 1e9}], "legend": true},
      {"ylabel": "angular rate Df/y[1] [rad/s]", "series": [{"signal": "Df/y[1]", "label": "Df/y[1]", "color": "#1b9e77"}]}
    ]
  }
}
@@ page pendulum overview - | Overview
# Planar multibond pendulum

The M3 vertical slice and the gate for the multibond plan (plan 9.3, row X-MB1): a rigid link hanging from a **compliant-pivot planar revolute joint**, built from the `Power{Planar}` primitives of `stdlib/multibond/`. A planar multibond is drawn as **two parallel strokes**; this model shows the 2-stroke convention end to end (editor, worker, run, plot). The pendulum is torque-free and the run is conservative.

![The model canvas: two-stroke planar bonds|900](@fig:diagram)

## What to try

- **Run** (Ctrl+Enter) and open the Plots tab: "Joint angle and pivot deflection", "Body momentum" and "CoM height and body twist".
- Set `Joint.q0` to 0.2 rad and rerun: the period rises by about $q_0^2/16 \approx 0.25\,\%$. The period check then fails until you update `expected.json`, which is the intended signal that the physical input changed.
- Lower `Joint.kt` and recompute the start of `Joint.d` from the formula on [the physics page](page:physics): the released-from-rest value keeps the fast $\sqrt{k_t/m}$ mode out of the energy budget. Changing one without the other makes the energy check report the leftover transient (at $k_t = 10^6$ the deflection is 9.8 µm, a hundred times larger).
- Put a torque on [Drive](block:Drive) (`e` = 0.01 N·m): the pendulum gains energy linearly and the `energy` check fails: the budget tells you the drive does work.
- Plot the pivot reaction `De/y[2]`, `De/y[3]` next to `Df/y[1]`: the vertical reaction peaks at the bottom of the swing, once per half period.

## 3D view

`scenes/multibond-pendulum-2d.sdf` draws the pendulum in the vertical X-Z plane (the model's x-y plane, gravity along -z). The revolute joint `pivot` follows `Joint/qout`; the bob is the 0.5 m centre of mass, and `expected.json` checks the SDF kinematics against the composed CoM pose.

![3D view at t = 0.35 s|500](@fig:scene)
@@ page pendulum physics overview | Physics and equations
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
@@ page pendulum results overview | Results and checks
# Results and checks

![Joint angle, pivot deflection and angular rate over the 4 s run|900](@fig:run)

The editor's Run uses `t_end` = 4 s (4001 points, `reltol` 1e-9, `abstol` 1e-11); the checks re-run the same model with a 10 s settings override for the energy budget.

## Measured values (README)

| quantity | value |
| --- | --- |
| period from `Joint/q` up-crossings | 1.41879603183 s |
| amplitude-corrected physical period (with $L_{eff} = 0.5000000981$ m and $q_0^2/16$) | 1.41879603223 s (relative -2.8e-10) |
| simple reference $2\pi\sqrt{L/g}$ | 1.41850335344 s (relative +2.1e-4) |
| energy drift over 10 s | 1.77636e-15 J |
| KE/PE swing $m g L (1 - \cos q_0)$ | 2.4524796e-4 J |
| drift divided by swing | 7.2431e-12 (target 1e-6) |
| states | 6 (P 3, d 2, q 1), all differential |
| adaptive steps | 4072 for 4 s, 10072 for 10 s |

## What `expected.json` checks

1. [Joint/q](signal:Joint/q) = 0.01 rad and the static $d_0$ at $t = 0$ (three `cursor_value` checks);
2. the **period** from the first two upward zero crossings within 1e-5 of the amplitude-corrected physical period, and a second `period` check against the simple $2\pi\sqrt{L/g}$ at relative 1e-3;
3. the amplitude $\max\lvert q\rvert = 0.01$ over 4 s;
4. the **energy** budget $E = \tfrac12 P^T M^{-1} P + m g h + \tfrac12 k_t\lvert d\rvert^2$ with $h = g_y + \sin q\,d_1 + \cos q\,d_2$, normalised by the swing (the runner's `energy` kind);
5. `no_diagnostics` (W201, E101, E102, E103, E106, W206) on both runs.
