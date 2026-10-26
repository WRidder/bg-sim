# bouncing-ball — a continuous event with a velocity reinit (plan 9.2, milestone M2)

A single **project-library** equation block, `library/Ball.jl`, and one instance
`Ball1` in `models/bouncing-ball.bgmodel.json`. The ball starts at `h = 1 m` with
`v = 0`, falls under gravity and reverses its velocity at every impact:

```julia
@block Ball begin
    @parameters begin
        g::Real = 9.81, [unit = "m/s^2"]
        e::Real = 0.8, [min = 0, max = 1, description = "restitution"]
    end
    @variables begin
        h::Real = 1.0, [unit = "m"]
        v::Real = 0.0, [unit = "m/s"]
    end
    @outputs height::Real
    @equations begin
        ddt(h) ~ v
        ddt(v) ~ -g
        height ~ h
    end
    @events begin
        h < 0 => begin
            reinit(v, -e * v)
        end
    end
end
```

`h < 0` is normalised to the upward zero crossing of `-h` (decision D19), and
`reinit(v, -e * v)` lowers to one `SymbolicContinuousCallback` affect on that
rising edge. The event instant is recorded twice at the same `t` (left and right
limits, plan 3.5), so the height curve has a vertical kink at every bounce.

## Parameters

| quantity | value |
| --- | --- |
| initial height `h(0)` | 1 m |
| gravity `g` | 9.81 m/s² |
| restitution `e` | 0.8 |
| `t_end` | 3.5 s |
| `event_limit` | 10000 |
| output grid | 3500 points, `solver = auto`, reltol 1e-10, abstol 1e-12 |

With `h(t) = h0 - g·t²/2` before the first impact:

```
t1 = sqrt(2·h0/g)              = 0.45152 s
v1 = sqrt(2·g·h0)              = 4.42945 m/s
t2 = t1 + 2·e·v1/g             = 1.17396 s
peak after the first bounce   = e²·h0 = 0.64 m
```

The run stops at 3.5 s. The impacts accumulate geometrically and reach the Zeno
point at `t1 + 2·e·v1/(g·(1−e)) ≈ 4.06 s`; nine impacts happen before `t_end`.

## Checks

`expected.json` is the machine-readable acceptance. `uv run examples/run_checks.py`
(and `uv run tools/check.py --lane x`) runs it through the real Julia worker:

- the first `h` downward crossing of 0 is at **0.45152 s** (abs 1e-6,
  `zero_crossing`);
- the second is at **1.17396 s** (abs 1e-5, `zero_crossing`);
- `max_abs` of `Ball1/h` over `[0.5, 1.1] s` — strictly between the two impacts —
  is **0.64 m** (rtol 1e-4);
- no `W206`, `E101` or `E901` in the manifest (`no_diagnostics`).

`zero_crossing` collapses the recorder's doubled event rows (equal `t`, left and
right limits) before looking for the crossing, so the vertical kinks do not count
as two crossings.

## What to try

- Press **Run** (Ctrl+Enter) and plot `Ball1/h` and `Ball1/v`: the height bounces
  to 0.64 m, 0.41 m, 0.26 m, … while the velocity flips sign at each impact.
- Change the restitution `e` in the inspector. `e = 1` keeps bouncing to 1 m
  forever (no energy loss, no Zeno point); `e = 0.5` gives a peak of 0.25 m and
  reaches the Zeno point after about 1.35 s. This is a parameter-only re-run, so
  there is no recompile.
- Change `g` (the Moon is 1.62 m/s²): all impact times scale with `1/sqrt(g)`.
- Set `t_end` past about 4.06 s and lower `event_limit` (e.g. to 25) for the
  plan's W206 check: the run stops at the limit with **W206** ("the event limit
  was reached") instead of chattering forever. The Diagnostics tab shows the
  warning, and the manifest still says `done`; there is no `E901`.
- Open `library/Ball.jl` in the code editor: it is a project block, so
  `project:Ball` resolves from the project itself, not from the standard library.
