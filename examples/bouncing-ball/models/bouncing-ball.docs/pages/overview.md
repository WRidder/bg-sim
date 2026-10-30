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

![3D view at t = 0.4 s|500](assets/ab5fb1983a33.png)

Continue with [the model](page:model) or the [results](page:results).
