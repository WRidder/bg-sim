@@ figures bouncing-ball
{
  "scene": {"kind": "scene", "model": "bouncing-ball", "t": 0.4},
  "run": {
    "kind": "plot", "model": "bouncing-ball", "xlim": [0, 3.5],
    "rows": [
      {"ylabel": "height h [m]", "series": [{"signal": "Ball1/h", "label": "h"}],
       "hlines": [{"y": 0.64, "label": "first peak e² h0 = 0.64 m"}], "legend": true},
      {"ylabel": "velocity v [m/s]", "series": [{"signal": "Ball1/v", "label": "v", "color": "#d95f02"}]}
    ]
  }
}
@@ page bouncing-ball overview - | Overview
# Bouncing ball

A ball is released from rest at $h_0 = 1\,\mathrm{m}$, falls under gravity and loses 20 % of its speed at every impact with the floor. The model is a single **equation block** that lives in the project library (`library/Ball.jl`) and is used once, as [Ball1](block:Ball1).

What the example demonstrates (plan 9.2, milestone M2):

- a **continuous event**: the condition $h < 0$ is detected as a zero crossing of the state, not at a fixed time step;
- a **velocity reinitialisation** at the event, $v \leftarrow -e\,v$;
- an event instant that is stored **twice** at the same time (left and right limit), so the height curve shows a vertical kink at every bounce;
- a block that comes from the *project* library (`project:Ball`), not from the standard library.

## Run it

Press **Run** (Ctrl+Enter) and plot [Ball1/h](signal:Ball1/h) and [Ball1/v](signal:Ball1/v). The run covers 3.5 s with 3500 output points. Then try:

- change the restitution `e` in the inspector: with `e = 1` the ball keeps bouncing to 1 m forever, with `e = 0.5` it reaches the Zeno point after about 1.35 s (a parameter-only re-run, no recompile);
- change `g` (the Moon is 1.62 m/s²): all impact times scale with $1/\sqrt{g}$;
- set `t_end` past about 4.06 s and lower `event_limit` (for example to 25): the run stops at the limit with warning **W206** instead of chattering forever.

## 3D view

The 3D view (`scenes/bouncing-ball.sdf`) draws the floor, a 1.1 m ruler and the ball on a prismatic joint `fall`, which is bound to [Ball1/h](signal:Ball1/h). The picture shows the ball on its way up after the first bounce.

![3D view at t = 0.4 s|500](@fig:scene)

Continue with [the model](page:model) or the [results](page:results).
@@ page bouncing-ball model overview | Model and event
# Model and event

The block `Ball` has two parameters, two states and one output. The values below are those of `Ball1` in the model file.

| name | meaning | value | unit |
| --- | --- | --- | --- |
| `g` | gravity | 9.81 | m/s² |
| `e` | restitution, declared with `min = 0`, `max = 1` | 0.8 | 1 |
| `h` (state, start) | height of the lowest point of the ball above the floor | 1.0 | m |
| `v` (state, start) | vertical velocity, positive upwards | 0.0 | m/s |

## Equations

Between impacts the ball is in free fall:

$$\dot h = v, \qquad \dot v = -g, \qquad \text{height} = h$$

so that, from release at $t = 0$,

$$h(t) = h_0 + v_0\,t - \tfrac{1}{2} g\,t^2 .$$

## Event

The `@events` section of the block reads `h < 0 => reinit(v, -e * v)`. At the instant $h$ crosses zero downwards the velocity is replaced by

$$v^{+} = -e\,v^{-}, \qquad 0 \le e \le 1 ,$$

and the integration continues from the new state. The condition `h < 0` is normalised to the upward zero crossing of $-h$ (decision D19) and `reinit` becomes the affect of one continuous callback. Only the velocity is changed; $h$ is continuous.

Because the event is located by root finding, the instant is exact to the solver tolerance (`reltol` 1e-10, `abstol` 1e-12), not to the output grid. The recorder writes the instant twice, with the value before and after the event; that is why [Ball1/v](signal:Ball1/v) jumps vertically in the plot.

## Solver settings

| setting | value |
| --- | --- |
| `t_end` | 3.5 s |
| output | 3500 points |
| solver | `auto` |
| `event_limit` | 10000 |

Back to the [overview](page:overview).
@@ page bouncing-ball results overview | Results and checks
# Results and checks

## Closed-form impact times

With $h_0 = 1\,\mathrm{m}$, $g = 9.81\,\mathrm{m/s^2}$ and $e = 0.8$ the first impact happens when $h_0 = \tfrac12 g\,t_1^2$:

$$t_1 = \sqrt{\frac{2 h_0}{g}} = 0.45152\ \mathrm{s}, \qquad v_1 = \sqrt{2 g h_0} = 4.42945\ \mathrm{m/s}.$$

After the impact the ball leaves with $e\,v_1$ and is back on the floor after $2 e v_1 / g$:

$$t_2 = t_1 + \frac{2 e v_1}{g} = 1.17396\ \mathrm{s}, \qquad h_{\max,1} = e^2 h_0 = 0.64\ \mathrm{m}.$$

Every bounce shrinks the flight time by the factor $e$, so the impacts accumulate at the Zeno point

$$t_\infty = t_1 + \frac{2 e v_1}{g\,(1 - e)} \approx 4.06\ \mathrm{s}.$$

The run stops at 3.5 s, before that point; nine impacts happen in the window.

![Height and velocity of the bouncing ball|900](@fig:run)

## What the acceptance checks verify

`expected.json` is evaluated by `uv run examples/run_checks.py` against the real Julia worker:

| check | expected | tolerance |
| --- | --- | --- |
| first downward zero crossing of `Ball1/h` | 0.4515236409857309 s | 1e-6 s |
| second downward zero crossing | 1.1739614665629003 s | 1e-5 s |
| largest `Ball1/h` in $[0.5, 1.1]$ s (between the first two impacts) | 0.64 m | relative 1e-4 |
| diagnostics W206, E101, E901 | absent | |

The crossing check collapses the doubled event rows before searching for the crossing, so a vertical kink is not counted as two crossings. The 3D view check (`scene_bindings`) verifies that the binding of the joint `fall` to [Ball1/h](signal:Ball1/h) matches the scene file.

Back to the [model](page:model).
