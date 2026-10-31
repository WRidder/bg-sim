# Model and checks

## Plant (bond graph)

The modulated effort source [Drive](block:Drive) pushes on the 1-junction [CartJ](block:CartJ), whose flow is the cart speed. On the junction sit the mass [Mass](block:Mass) (`I`, $m = 1$ kg), the damper [Damper](block:Damper) (`R`, $b = 2$ N·s/m) and the spring [Spring](block:Spring) (`C`, compliance 0.1 m/N, so $k = 10$ N/m). [Speed](block:Speed) is a zero-effort flow sensor with a `Translation` port, which gives the bond island its domain and units, and [Pos](block:Pos) integrates the speed into the position:

$$m\,\ddot x = F - b\,\dot x - k\,x .$$

## Controller (`library/CartPID.jl`)

[Ctrl](block:Ctrl) runs every $T_s = 10$ ms:

```julia
25    @discrete Ts = 0.01 begin
26        k += 1                                # tick counter
27        err = x_ref - x                       # position error
28        z += Ts * err                         # integrate the error
29        u = Kp * err + Ki * z - Kd * v        # PID force, not yet limited
30        F = clamp(u, -umax, umax)             # the drive saturates at +-umax
31        if aw > 0.5 && abs(u) > umax
32            z -= Ts * err                     # anti-windup: undo the integration
33        end
34    end
```

| parameter | value | meaning |
| --- | --- | --- |
| `Kp` | 40 | proportional gain, N per m |
| `Ki` | 80 | integral gain, N per m·s |
| `Kd` | 8 | velocity feedback, N per m/s |
| `umax` | 15 | drive force limit, N |
| `aw` | 0 | anti-windup switch: **0 is the bug**, 1 the fix |

`err` is a block-local temporary (it shows under *Locals* at a statement pause); `k`, `z`, `u` and `F` are held between ticks (*Held outputs*).

## Limit switch (`library/LimitSwitch.jl`)

[Limit](block:Limit) is an `@events` block wired into the drive enable, not into the controller software. When $x$ rises past `x_limit` = 1.2 m, the event at line 24 sets the latch to 1 and the force passed to the drive becomes zero:

$$F_\text{drive} = (1 - \text{latch})\,F_\text{cmd} .$$

The latch obeys `ddt(latch) ~ -leak * latch` with `leak = 0`, the same pattern as `stdlib:continuous/Relay`: written as a literal `ddt(latch) ~ 0.0`, the compiler would eliminate it as a constant and the event could not change it.

## Settings

| setting | value |
| --- | --- |
| `t_end` | 4 s |
| output | 4001 points |
| solver | `auto`, reltol 1e-8, abstol 1e-10 |
| `event_limit` | 100 |

## Checks

`expected.json` checks the shipped run (with the bug) through the real Julia worker, `uv run examples/run_checks.py --only debug-tour`:

| check | expected | tolerance |
| --- | --- | --- |
| first upward crossing of 1.1 m by `Pos/y` | 1.0233 s | 1e-3 s |
| first upward crossing of 1.2 m by `Pos/y` (the event) | 1.0936542 s | 1e-5 s |
| final `Limit/tripped` | 1 | 1e-12 |
| largest `Pos/y` | 1.2436 m | relative 2e-3 |
| largest `Ctrl/F` | at most 15 N | |
| diagnostics W201, W205, W206, E900, E901 | absent | |
| scene binding of `slide` to `Pos/y` | valid | |

The debugging flow of the [walkthrough](page:walkthrough) is covered by the real-worker Playwright spec `web/tests/e2e/debug-tour.spec.ts`. With `aw = 1` (the fixed model) the peak is 1.044 m and the switch never trips.

Back to the [overview](page:overview).
