# quad-pendulum — four pendulum links swung up from hanging and balanced upright, on a cart and on a rotary arm

A chain of **four** serial pendulum links, swung up from hanging at rest and balanced upright by a single
actuator, in the spirit of the MathWorks demo "Can a single cart swing up and balance four inverted pendulums?".
Two rigs share one design method and one model generator:

- **cart** (`quad-pendulum-*`): a cart on a ±1.5 m rail, an ideal force actuator, four links of 0.275 m. Planar
  multibond bond graph (`stdlib:planar/*`).
- **rotary** (`quad-rotary-*`): a Furuta rig. A horizontal arm turns about the vertical axis, driven by an ideal
  torque, and carries the chain at its tip. The pendulum joints are perpendicular to the arm, so the links swing
  in the vertical plane tangent to the arm circle. Spatial multibond bond graph (`Revolute3D`, `RigidBody3D`).

| model | what it runs |
| --- | --- |
| `quad-pendulum-swingup` | hanging at rest for 1 s, the swing-up (5 s, **SWINGING UP**), the catch and 4 s of balance (**BALANCING**) |
| `quad-pendulum-balance` | balance only: starts leaning 2° per link, a 50 ms tip push at 3 s |
| `quad-pendulum-free` | no control: the free swing from a tilted start, the check against the Python twin |
| `quad-rotary-swingup`, `quad-rotary-balance`, `quad-rotary-free` | the same three scenarios on the rotary arm |

The cart has **two controllers** in the same firmware, chosen at run time by the dashboard's **Controller**
select (`Traj/controller`, no recompile): **full travel** (0, the original design: the whole rail) and
**short travel** (1): a swing-up and balance designed for ±0.5 m of cart travel on the **same plant**. The
rail with its soft end stops at ±1.5 m, the actuator and the scene are unchanged. The ±0.5 m limit is a
property of the controller only: thin green lines in the 3D scene (visual markers, not stops) and the limit
lines on the dashboard's cart plot, which follow the selected controller. The rotary arm has the full-travel
controller only; a short-travel controller for it (±75°) and a more realistic rotary plant are the next phase.

## Rigs (assumed values, `design/design.py`)

| | cart | rotary |
| --- | --- | --- |
| links | 4 × 0.275 m, 0.10 kg (thin rods, COM at the middle, J = mL²/12) | 4 × 0.15 m, 0.03 kg |
| joint friction | 5e-4 N m s/rad | 2e-5 N m s/rad |
| base | cart 1.0 kg, rail friction 1.0 N s/m | arm 0.30 m, 0.30 kg, hub/rotor 2e-3 kg m², bearing 0.01 N m s/rad |
| actuator | ideal force, ±40 N, slew 4000 N/s | ideal torque, ±3 N m, slew 300 N m/s |
| travel | ±1.5 m rail with soft end stops (HardStop 2e4 N/m) | ±3 rad (cable limit, checked only) |
| UPRIGHT level (Σ m g 2h of the chain) | **4.316 J** | 0.706 J |

The UPRIGHT level of the cart rig matches the 4.3 J of the reference video.

## Plant (bond graph)

```
cart:   Ground -- Rail (Prismatic2D) -- CartJ(1) -- Cart (RigidBody2D)
           |drive                        `-- Joint1 (Revolute2DCompliant) -- Link1 -- N1(1) -- Body1 ... Body4 -- Push
        Force (ForceSource) + RailFriction (Damper) + EndStops (HardStop), each against a Fixed frame

rotary: World -- Mount -- J1 (Revolute3D, world z) -- ArmLink -- BJ1 -- Arm (RigidBody3D, hub inertia lumped in)
                          |drive: Motor (TorqueSource) + ArmBearing (RotationalDamper)
                          T2 -- J2 (Revolute3D, along the arm) -- Link1 -- BJ2 -- Rod1 ... Rod4 -- Push
```

The pivots are compliant (1e8 N/m, the multibond convention). Every pendulum joint has viscous friction on its
drive port. The firmware reads the joint encoders (`qout`, `qdout`). The monitor block (`QuadCartMonitor`,
`QuadRotaryMonitor`) reads the bodies' twists and poses and computes:

- the link angles from the upward vertical, θ1..θ4 (deg);
- the energy per link E_i = ½ωᵀJω + ½m v² + m g (h − h_hang) (kinetic plus potential from the hanging rest);
- the stacked sums S1 = E1, S2 = E1 + E2, .. S4 (the stacked energy plot) and the UPRIGHT level;
- the energy ledger: W_in = ∫ u ṡ dt (actuator work), W_loss = ∫ (b_s ṡ² + b_j Σ ω_rel²) dt (friction) and
  E_tot − W_in + W_loss, which must stay constant.

## Firmware (`library/Quad*Ctrl.jl`, `@discrete Ts = 1e-3`)

| phase | indicator | control |
| --- | --- | --- |
| 0, t < 1 s | — | hold, u = 0 |
| 1 | **SWINGING UP** | u = u*(τ) − K(τ)(z − z*(τ)), τ = t − 1 s: feed-forward plus discrete time-varying LQR along the offline trajectory |
| 2 (latched) | **BALANCING** | u = −K_lqr z, the infinite-horizon discrete LQR at the upright |

z = [s, φ1..φ4, ṡ, φ̇1..φ̇4] with φ_i the absolute link angles (sums of the relative encoder angles). The
catch latches phase 2 once, when τ ≥ T_s − 0.5 s and the LQR cost-to-go z'Pz is below 1000 (the catch region).
The trajectory tables (10 ms knots) live in a separate `Quad*Traj` block as a continuous `interp1` lookup, which
the firmware samples every tick. On the cart the block holds the tables of both controllers; `Traj/controller` selects
one, and `Traj/sel` tells the firmware which balance LQR, catch matrix and swing-up duration go with it. The
cart tables hold the gain rows K and the combined feed-forward v = u* + K z*, so u = v − K z (11 tables per
controller instead of 21, see the run time below). The rotary tables hold u*, z* and K separately,
u = u* − K(z − z*).

**Assumptions.** Ideal actuator (force or torque source, no motor electrics; clamp plus slew limit), sampling
and zero-order hold at 1 kHz, exact encoder angles and rates by default, no backlash, no flexibility, no
sensor noise. Two optional non-idealities are dashboard inputs: an actuator delay of 0..10 whole samples
(`Ctrl/delay_n`) and **quantised encoders** (`Ctrl/quant`: 16-bit joint encoders, a 10 µm cart encoder, rates
from filtered backward differences with a 2 ms (cart) or 5 ms (rotary) time constant).

## Design (`design/`, `uv run`, CasADi + IPOPT + SciPy)

1. **Twin.** `quadlib.py` builds the Lagrangian of each rig in CasADi (the same masses, inertias, friction).
2. **Balance LQR.** Discrete (ZOH, 1 ms) at the upright. Cart Q = diag(100, 400×4, 10, 5×4), R = 0.3; rotary
   Q = diag(2, 100×4, 0.1, 1×4), R = 10. The open loop has four unstable poles (cart up to 24.3 /s, rotary up to 34.0 /s).
3. **Swing-up trajectory.** Hermite–Simpson direct collocation from hanging rest to upright rest in T_s = 5 s
   (warm-started solves: 100 intervals with a heavy link-rate weight, then a lighter weight, then 200 intervals),
   minimum ∫u² plus small slew and rate terms. Bounds: cart |u| ≤ 30 N, |x| ≤ 1.0 m, slew ≤ 3000 N/s; rotary
   |u| ≤ 2.5 N m, |θ_arm| ≤ 2.5 rad, slew ≤ 250 N m/s. The rotary bounds are active: the rotary swing-up needs
   the full torque and arm travel.
4. **TVLQR.** Backward Riccati recursion on the RK4-sampled twin along the trajectory; the nominal is
   re-made by one closed-loop roll-out of the sampled model, so the table is consistent with 1 kHz control.
   The last row is the balance LQR.
5. **Firmware replica.** The closed loop of the exact firmware logic (clamp, slew, catch, latch, delay line,
   quantisation) on the twin: the swing-up, the balance scenario and robustness cases.

```
uv run examples/quad-pendulum/design/design.py cart        # writes design/design_cart.json
uv run examples/quad-pendulum/design/design.py rotary      # writes design/design_rotary.json (about 10 min)
uv run examples/quad-pendulum/design/design.py cart_short  # the short-travel cart controller (after cart: it
                                                           #   reuses its balance push), design_cart_short.json
uv run examples/quad-pendulum/design/build_models.py       # library blocks, models, scenes, dashboards
uv run examples/quad-pendulum/design/finish.py             # backend runs, twin comparison, expected.json
julia --project=julia/BGSim examples/quad-pendulum/design/run_model.jl <model> <run dir>   # one direct run
```

### Design results (twin closed loop)

| | cart | rotary |
| --- | --- | --- |
| catch (phase 2) | 5.50 s | 5.50 s |
| all links within 5° | 3.97 s | 4.42 s |
| peak actuator | 14.1 N of 40 N | 3.0 N m of 3.0 N m (saturates briefly) |
| peak travel | 0.581 m of 1.5 m | 2.50 rad of 3 rad |
| largest 50 ms tip push recovered (balance) | 0.037 N | 0.010 N |
| swing-up robust to: masses ±5 %, lengths +1 %, joint friction ×3, base friction ×2, base mass +10 %, 1 ms delay | yes | yes |
| swing-up with 2 ms delay / quantised encoders | yes / yes | **no / no** |
| balance with 2 ms, 5 ms delay / quantised encoders | yes / yes | yes / yes |

The rotary rig has far less control authority per link than the cart (the arm tip moves the chain only through
the arm's rotation, at a 0.3 m radius). Its swing-up uses the full torque and arm travel and is therefore not
robust to a 2 ms actuator delay or to quantised encoders; its balance is.

## Short-travel cart controller (±0.5 m)

Same plant, same actuator limit (±40 N), a different controller: `design.py cart_short` plans the swing-up
with the cart travel as a **hard collocation constraint** and redesigns the TVLQR around it: |x| ≤ 0.40 m
(0.1 m left to the feedback), |F| ≤ 35 N, slew ≤ 3500 N/s, still in T_s = 5 s. The full-travel TVLQR weights
saturated the force and fell with 3× joint friction or quantised encoders inside ±0.4 m; heavier rate weights
(Q = diag(100, 400×4, 10, 20×4), R = 0.3) fix both. The balance LQR stays that of the full-travel design: the
balance scenario's tip push uses 38 % of the limit (0.189 m), and the largest push recovered inside ±0.5 m is
the same as on the full rail (0.037 N).

| design closed loop (twin) | full travel | short travel |
| --- | --- | --- |
| travel limit (controller) | ±1.5 m (rail) | **±0.5 m** |
| swing-up duration T_s / catch | 5 s / 5.50 s | 5 s / 5.50 s |
| all links within 5° | 3.97 s | 4.00 s |
| peak travel | 0.581 m | **0.401 m** (80 %) |
| peak force | 14.1 N | 17.0 N |
| largest 50 ms tip push recovered (balance) | 0.037 N | 0.037 N (peak 0.19 m) |
| swing-up robust to masses ±5 %, lengths +1 %, joint friction ×3, base friction ×2, base mass +10 %, 1 ms delay | yes | yes (travel ≤ 0.417 m) |
| 2 ms delay / quantised encoders | yes / yes | yes / yes |

The price of the short travel: a 20 % larger peak force (still less than half the actuator), no loss of
robustness and no longer swing-up.

## Results (bond graph)

Real worker, Rodas5P, reltol 1e-7 (the free models 1e-10), `design/measured.json`:

| quantity | cart, full travel | cart, short travel | rotary |
| --- | --- | --- | --- |
| free swing 1.5 s vs the Python twin (base / largest link angle) | **1.0e-7 m / 7.0e-4°** | (same plant) | **1.7e-6 rad / 2.6e-3°** |
| energy ledger drift, free swing (E_tot − W_in + W_loss) | 9.9e-7 J | | 6.4e-7 J |
| at rest before 1 s | exactly | exactly | exactly |
| all links within 5° | 3.97 s | 4.00 s | 4.42 s |
| catch (BALANCING) | **5.50 s** (design 5.50 s) | **5.50 s** (design 5.50 s) | **5.50 s** (design 5.50 s) |
| largest link deviation from 7.5 s | **0.00057°** | **0.0011°** | **0.0030°** |
| final link angles at 10 s | 1.1e-4° | 1.5e-4° | 3.9e-4° |
| peak actuator | **14.13 N** of 40 N (design 14.13) | **16.97 N** (design 16.97) | **3.00 N m** of 3 N m (design 3.00) |
| peak travel / the controller's limit | 0.581 m of ±1.5 m | **0.401 m of ±0.5 m** (80 %) | 2.50 rad of ±3 rad |
| stacked energy at 10 s / UPRIGHT level | 4.3164 J / 4.3164 J | 4.3164 J / 4.3164 J | 0.7063 J / 0.7063 J |
| actuator work / friction losses over the run | 6.99 J / 2.68 J | 7.14 J / 2.83 J | 1.15 J / 0.45 J |
| balance scenario: lean caught, inside 0.5° before the push | 0.33° | 0.33° | 0.21° |
| tip push (0.018 N / 0.0052 N, 50 ms): peak deviation, recovery inside 0.5° | 9.36° (design 9.36°), 1.79 s | same | 10.05° (design 10.05°), 1.60 s |
| balance scenario: peak actuator, travel (share of the limit) | 17.6 N, 0.189 m (13 %) | 17.6 N, 0.189 m (38 %) | 0.83 N m, 0.50 rad |
| run time (real worker, swing-up 10 s / balance 7 s / free 1.5 s) | see below | see below | 72 s / 69 s / 109 s |

The cart's balance LQR is the same in both controllers (the short-travel design keeps its weights), so the
balance runs are identical; only the limit lines and the travel used differ.

**Run time.** The cart firmware holds the tables of both controllers. In bg-sim the cost of an `interp1` grows
with the size of its table arguments whether or not the branch is used (see the notes below), so a first
version with both full table sets (21 tables each) ran the cart swing-up 1.95× slower than the one-controller
model. With the combined feed-forward (11 tables per controller) the two-controller swing-up runs 1.24× the
one-controller model, measured side by side on the same (busy) machine at the same number of steps (473 s
against 381 s of solver time). On a quiet machine the one-controller cart runs took 48 s / 37 s / 107 s; on
the machine loaded by other jobs during this work the two-controller runs took 86 s / 53 s / 136 s, the same
for each controller.

The bond graph and the twin agree so closely that the closed loops agree to the printed digits. The rotary
torque saturates at 3 N m for short moments during the swing-up, in the design loop and in the bond graph alike.

`expected.json` (written by `design/finish.py`) checks, per rig: no diagnostics and the scene bindings; rest
before 1 s; the hold, SWINGING UP and BALANCING indicators; the link angles at 40 % and 70 % of the swing-up
against the design closed loop (2° band); every link within 0.5° of upright from 7.5 s; |u| within the limit
and the peak within 15 % of the measured one; the travel limit; the final stacked energy at the UPRIGHT level
(1 %); the energy ledger as an invariant; the balance scenario (caught, push peak ±20 %, recovered, limits,
ledger); and the free swing against the twin every 0.25 s with a tolerance of 3× the measured difference.
The `quad-pendulum-swingup-short` and `quad-pendulum-balance-short` entries run the same cart models with the
override `Traj/controller = 1` and check the same things for the short-travel controller, plus: the cart stays
inside ±0.5 m during the swing-up, the catch and the push recovery, `Mon/use` stays below 100 %, and the limit
line `Mon/lim_hi` follows the selected controller (the last two also on the cart's full-travel entries).

### Notes on bg-sim found on the way

- A `Bool` parameter used directly as an operand of `||` / `&&` inside `@discrete` fails at the first tick
  ("non-boolean (Float64) used in boolean context"): parameters reach the step function as `Float64`, and
  `if` / `ifelse` wrap their condition in `__truthy`, but the short-circuit operators do not. The static
  checker in turn rejects `balance_only > 0.5` (E004 "cannot compare Bool and Real"). The firmware uses
  `ifelse(balance_only, 1.0, ifelse(<other conditions>, 1.0, 0.0))`.
- A `rotation/Inertia` on a `Revolute3D` drive port, next to the body the joint drives, is a second store on
  the same rate (derivative causality, W201 and an Unstable solver at t = 0). The hub inertia is lumped into
  the arm body instead.
- `ForceSource` / `TorqueSource`: port `a` takes power in (a.e = F u is the effort it receives). To push the
  driven joint along +u, port `b` faces the joint and port `a` the fixed frame.
- The run time grows with the **total size of the `interp1` tables** an equation block references, not with
  the table that is actually looked up: every table argument stays a whole vector of parameter elements
  (`_qarray_arg` in `compile/instantiate.jl`), and `bg_interp1` searches linearly. A first two-controller
  cart version with both full table sets behind an `ifelse` ran 1.95× slower than the one-controller model;
  sending the unused table a query before its first knot (an immediate return) did not help. With the
  combined feed-forward (11 tables per controller instead of 21) the two-controller swing-up runs 1.24× the
  old one at the same number of steps. The `controller` select itself is a plain run-time parameter.
- `run_model.jl` overrides: an `Int` parameter (`Traj/controller`) needs the value as an integer literal
  ("1", as the backend writes it in `sim/overrides.jl`); "1.0" is rejected with E004.

## Dashboard and 3D view

Each model has a dark dashboard: SWINGING UP / BALANCING indicators, time, θ1..θ4 readouts (green inside
±0.5°), base position and actuator readouts with sparklines, the **stacked energy-per-link plot** with the
UPRIGHT level, the link angles, base and actuator plots, the energy ledger and the catch-region cost-to-go.
Inputs: link mass scale (the controller keeps its nominal gains), tip push amplitude, actuator delay, quantised
encoders, actuator limit and, on the balance models, the four start angles. The cart dashboards add the
**Controller** select (full travel / short travel); their cart plot carries the selected controller's travel
limit as two lines (`Mon/lim_hi`, `Mon/lim_lo`), and **Travel used** shows |x| in percent of that limit
(green below 80 %, amber to 100 %, red above). The runs take one to a few minutes, so auto re-run is off: change an input, then
press **Run**.

The 3D scenes (`scenes/quad-pendulum.sdf`, `scenes/quad-pendulum-rotary.sdf`): a rail with markers every 0.5 m
and red end stops, the cart with wheels; or a column with a turning arm and a ring of markers; the four links
from deep blue to white, gold joint balls. On the rail, thin translucent green lines mark the short-travel
limit (±0.5 m): visual markers only, the plant has no stop there.

## Files

| path | what |
| --- | --- |
| `design/quadlib.py` | twin, LQR, collocation, TVLQR, firmware replica |
| `design/design.py` | the design of both rigs and of the short-travel cart controller, writes `design/design_<kind>.json` (and caches `_traj_<kind>.npz`) |
| `design/blocks.py`, `design/models.py`, `design/scenes.py`, `design/build_models.py` | the generator of the library blocks, models, scenes and dashboards |
| `design/finish.py` | backend runs, twin comparison, `design/measured.json`, `expected.json` |
| `design/run_model.jl` | a direct BGSim run (no backend) for design iterations |
| `library/` | `QuadCartCtrl`, `QuadCartTraj`, `QuadCartMonitor`, `QuadRotaryCtrl`, `QuadRotaryTraj`, `QuadRotaryMonitor` (generated) |
