# Results and checks

## Closed-form impact times

With $h_0 = 1\,\mathrm{m}$, $g = 9.81\,\mathrm{m/s^2}$ and $e = 0.8$ the first impact happens when $h_0 = \tfrac12 g\,t_1^2$:

$$t_1 = \sqrt{\frac{2 h_0}{g}} = 0.45152\ \mathrm{s}, \qquad v_1 = \sqrt{2 g h_0} = 4.42945\ \mathrm{m/s}.$$

After the impact the ball leaves with $e\,v_1$ and is back on the floor after $2 e v_1 / g$:

$$t_2 = t_1 + \frac{2 e v_1}{g} = 1.17396\ \mathrm{s}, \qquad h_{\max,1} = e^2 h_0 = 0.64\ \mathrm{m}.$$

Every bounce shrinks the flight time by the factor $e$, so the impacts accumulate at the Zeno point

$$t_\infty = t_1 + \frac{2 e v_1}{g\,(1 - e)} \approx 4.06\ \mathrm{s}.$$

The run stops at 3.5 s, before that point; nine impacts happen in the window.

![Height and velocity of the bouncing ball|900](assets/7b59ce5616c8.png)

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
