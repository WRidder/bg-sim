# inverted-pendulum-cart — a bond-graph cart-pole with an LQR balance controller

The classic cart–pole stabiliser (plan 9.6c): a cart on a rail balances a rod with a point
mass at its tip, starting from a 0.1 rad tilt, and then follows a 0.2 m cart-position
step at t = 1.5 s. The continuous plant is a **pure bond graph** (D28); the controller is a
linear-quadratic state feedback sampled at 1 ms (`@discrete Ts = 1e-3`), whose gains come
from `design/design.py`.

## Plant (bond graph)

| part | bond graph |
| --- | --- |
| cart | 1-junction `CartJ` with `I(M)` (1 kg), `R(b)` (0.1 N·s/m) and `MSe1` (`gain = 1`, the force `u`) |
| point mass at the rod tip | two translational `I(m)` elements (`IMx`, `IMv`, 0.2 kg) for the tip's horizontal and vertical velocity, plus the gravity `MSeG` (`gain = −m·g`, `u = 1`) on the vertical one |
| kinematics | `MTFh` (modulus `l·cos θ`) between `PendJ` and the 0-junction `HS`, so `v_x = v + l·ω·cos θ`; `MTFv` (modulus `l·sin θ`) between `PendJ` and the 1-junction `VJ`, so `v_y = −l·ω·sin θ` |
| sensors | two project-library `FlowSensor`s on the cart and pendulum 1-junctions, and two `Integrator`s that turn the flows into `x` and `θ` (θ(0) = 0.1 rad) |

`PendJ` is the pendulum's angular 1-junction; it carries no `I` element, because the point
mass has **no rod inertia of its own**: its inertia about the pivot is `J_p = m·l²`, which
is exactly what the two translational masses produce through the two transformers. That is
the model `design.py` linearises, so the design and the plant agree by construction.

With `v` the cart velocity and `ω` the pendulum rate, the graph is

```
MSe1(u) ─ CartJ(1) ─ R(b), I(M) ─ HS(0) ─ I(m)=IMx
                    │                    ╰─ MTFh(l·cosθ) ─ PendJ(1) ─ MTFv(l·sinθ) ─ VJ(1) ─ I(m)=IMv, MSe(−m·g)
                    ╰─ FlowSensor = v
PendJ ─ FlowSensor = ω
v, ω ─ Integrators ─ x, θ ─ MTF moduli and the LQR
```

The two `FlowSensor`s and the two `Integrator`s are the only non-bond-graph pieces of the
plant: they reconstruct a position and an angle for the moduli and the controller (the D28
"sensor" exception, as in section 9.6c); the physics itself is all `I`, `R`, `0`/`1`-junctions,
`MTF` and `MSe`.

## Controller

`library/LQR.jl` is the state feedback

```
u = clamp(−(K_x·(x − x_ref) + K_v·v + K_theta·θ + K_omega·ω), −20, 20)
```

with the four entries of the Riccati gain vector `K` as parameters, `x_ref` a `Step` from 0
to 0.2 m at t = 1.5 s and a ±20 N force limit. The feedback law is the firmware: it runs in a
`@discrete Ts = 1e-3` scope, so each 1 ms tick samples `x`, `v`, `θ` and `ω` and holds the
force until the next tick (the declared 0 N start is held for the first millisecond).
`design/design.py` (a `uv` script with `numpy`/`scipy`) linearises the plant at upright,

```
A = [[0, 1, 0, 0], [0, −b/M, −m·g/M, 0], [0, 0, 0, 1], [0, b/(M·l), (M+m)·g/(M·l), 0]]
B = [0, 1/M, 0, −1/(M·l)]'
```

solves the continuous Riccati equation and writes `K` into the four `K_*` parameters of the
model document (the committed literals are its output). Run it with

```
uv run examples/inverted-pendulum-cart/design/design.py
```

**Weights** (`Q = diag(q_x, q_v, q_theta, q_omega)`, `R`), normalised as `q_i = 1/σ_i²`:

| state | scale `σ` | weight | why |
| --- | --- | --- | --- |
| `x` | 1.1 cm | `q_x = 8e3` | the cart position is the slow, weakly actuated mode (the force only reaches it through the pendulum), so it carries the largest weight |
| `v` | 1 m/s | `q_v = 1` | |
| `θ` | 0.1 rad | `q_theta = 100` | the force couples to the angle directly through `−1/(M·l)`, so it is cheap to control |
| `ω` | 0.32 rad/s | `q_omega = 10` | damps the angle's rate |
| `u` | 1 N | `R = 1` | 1 N² of force costs 1 |

The result is `K = [−89.442719, −54.686555, −175.121631, −39.152990]` with closed-loop poles
`−7.17 ± 5.45j`, `−5.28` and `−4.10`. The peak force demand is **17.86 N** (at the t = 1.5 s
step; 17.51 N at the initial tilt), so the ±20 N clamp stays inactive in the nominal run —
about 10 % of margin.

## Results

`design/design.py` integrates the non-linear closed loop independently (RK4, the same
controller and clamp, but **continuous** in time); `uv run examples/run_checks.py` runs the
bond-graph model with the 1 ms sampled controller through the real Julia worker. The two
agree to about 2 % during the fast recovery and the step, and to better than 0.5 % once
settled. The zero-order hold is visible in the fastest part of the initial recovery (one
millisecond of the declared 0 N output plus the average half-sample delay): at t = 0.2 s
`θ` is 4 % further along than the continuous reference, which is why that one cursor check
carries a 2.5 mrad tolerance.

| quantity | design.py (continuous) | bond-graph run (1 ms ZOH) |
| --- | --- | --- |
| peak `|u|` (at t = 1.5 s) | 17.865 N | 17.877 N |
| `θ` over [2.9, 3.0] s | 0.442° | 0.408° |
| `x(3.0 s)` (reference 0.2 m) | 0.19822 m | 0.19918 m |
| `θ` over [3.5, 4.0] s | 0.058° | 0.042° |
| `x(3.5 s)` / `x(4.0 s)` | 0.199744 / 0.199963 m | 0.199910 / 0.199990 m |
| peak `|θ|` (during the step) | 6.86° | 6.94° |

The 0.1 rad tilt is recovered well before the step (`|x| < 2 mm` and `|θ| < 0.3°` at
t = 1.45 s), the tilt never exceeds the initial 0.1 rad, and after the step the cart settles
inside 1 cm in well under 2 s while the angle stays below 0.5°.

## Checks

`expected.json` is the machine-readable acceptance (17 checks, plan 9.6c):

- **`|θ| < 0.5°` and the cart inside 1 cm around t = 3 s.** The angle band is
  `max_abs` over [2.9, 3.0] s against 0.5° (0.0087266 rad), and the cart band is the tracking
  error: the cart sits at the 0.2 m reference, so the check pins `x(3.0)` to the design's
  0.19822 m with 2 mm of tolerance — well inside 1 cm of the reference. (Before the step the
  same 1 cm band is checked on `x` itself, over [1.3, 1.45] s.)
- **The reference settles within 2 s:** `|θ| < 0.1°` over [3.5, 4.0] s and `x` at 3.5 s and
  4.0 s within 1 mm of 0.2 m.
- **`|u| ≤ 20 N`:** the peak force is compared against the design's 17.86 N with 20 mN of
  tolerance; the value itself is 10 % below the limit.
- **No solver failure:** `no_diagnostics` forbids `E901`, `E106`, `W202` and `W206`
  (the run reports `W201` three times and `W205` three times, see below).
- Cursor values at t = 0.2, 1.45 and 2.0 s pin the shape of the recovery and of the step
  against the design reference. The 0.2 s angle cursor carries 2.5 mrad because that is the
  fastest part of the recovery and the 1 ms sample-and-hold is visible there (~4 %).

## One documented limitation

1. **The plant is an index-2 DAE, not an ODE.** A point mass carries two translational
   stores but only one rotational degree of freedom, so one store is algebraically tied to
   the others: SCAP reports `W201` for `IMv` (and the lowering for `IM` as well). The model
   still solves (derivative causality is legal bond-graph practice), but the tool has no
   **planar / vector inertia (an `I`-field, or a 2-port `Power{Planar}`)** that would hold
   the 2×2 mass matrix `[[M+m, m·l·cos θ], [m·l·cos θ, m·l²]]` in two integral stores and
   make the plant a plain ODE. Planar components are M4 work; until then the two-mass
   representation is the honest bond-graph model, and it reproduces the plan's equations
   exactly (a constant-force run agrees with an independent RK4 of those equations to 1e-9).

   The discrete scheduler drives this DAE correctly (FIX-M2-3): a tick that changes a held
   output is a *parameter* discontinuity, so `run_tick!` writes it with `setp`, re-solves
   the algebraic unknowns at the current differential state (`BrownFullBasicInit`) and only
   then flags the integrator's derivative data stale. The continuous state — the momentum
   and the two integrals — is never re-initialised from `u0`.

## What to try

- Open the **Plots** tab: “Pendulum angle” shows the 0.1 rad recovery and the step-induced
  swing; “Cart position” overlays `XInt/y` and `XRef/y`; “Controller force” shows the
  17.9 N peak that stays inside the ±20 N limit.
- Change `LQR1.K_x` (or any `K_*`) in the inspector and run again: the recovery becomes
  slower and the cart error grows. `uv run examples/inverted-pendulum-cart/design/design.py`
  recomputes the gains from the weights.
- Raise the initial tilt (`ThetaInt` start `x` = 0.2 rad) to watch the force hit the ±20 N
  clamp: the peak becomes exactly 20.0 N and the cart still settles at 0.2 m. A design that
  demands more than the clamp *for a long time* can make the nonsmooth `clamp` chatter and
  hit the `W206` event limit, which is why the sample's own weights stay 10 % below it.
