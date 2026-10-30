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
