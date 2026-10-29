# reaction-wheel-1d — a cube balanced on one edge by a reaction wheel

A 0.12 m cube stands on one edge (a body diagonal vertical) and starts 0.05 rad (2.9°) off
upright. A DC motor with its housing on the cube spins a wheel inside it; the wheel's
reaction torque holds the cube up. A 2 ms discrete LQR on `[θ, θ̇, ω_rel]` sets the motor
voltage, clamped to ±12 V. It is the 1D, iconic-Rotation counterpart of `reaction-wheel-2d`
and `reaction-wheel-3d` (plan 9.7).

```
AngleSens ─ θ ──────────┐
SpeedSens ─ θ̇ ──────────┼─► LQR1 (2 ms, ±12 V) ─ u ─► Drive (motor + wheel) ─ housing ─► Body (cube)
Drive.w_w ─┐            │                                                                     │
           ├► RelSpeed ─┘ (ω_rel = wheel − body)             AngleSens, SpeedSens ◄────────────┘
SpeedSens ─┘
```

## Plant

| part | block |
| --- | --- |
| cube | project block `InvertedPendulumBody` (`library/InvertedPendulumBody.jl`), the stdlib `Inertia` modified: `J·ddt(w) ~ m·g·l·sin(θ) + a.e + b.e`, `ddt(θ) ~ w`, `a.f ~ w`, `b.f ~ w`. `J = 4e-3 kg·m²` about the edge (wheel excluded), `m = 0.6 kg`, `l = 0.085 m`, `θ(0) = 0.05 rad`. Both ports sit on the same absolute rotation: port `b` carries the sensors, port `a` the motor housing |
| motor and wheel | stdlib `drives/ReactionWheel` named `Drive`: `k = 0.0335`, `R = 1 Ω`, `L = 0.1 mH`, absolute wheel inertia `J_w = 6e-4 kg·m²` (rotor included), housing on the cube |
| sensors | `AngleSens` (`AngleSensor`, starts at `φ = θ(0) = 0.05`) and `SpeedSens` on the cube; the wheel's absolute speed is the drive's own `w_w` tap; `RelSpeed` is the inline difference of the two speeds |
| controller | project block `LQR` (`library/LQR.jl`): `u = clamp(−(K_θ·θ + K_θ̇·θ̇ + K_w·ω_rel), ±12)`, sampled every 2 ms (`@discrete Ts = 2e-3`) and held until the next tick |

Two choices deviate from the wording of the plan, and both have a reason.

1. **`ReactionWheel` instead of `DCMotor` plus a wheel `Inertia`.** The stdlib `DCMotor` is
   referenced to an inertial shaft frame: its electromagnetic torque has no stator reaction
   (STATUS NOTE-8), and its back-EMF is `k·ω_shaft`, not `k·(ω_shaft − ω_housing)`. A cube
   driven through it was measured to tip the wrong way: with `u > 0` the wheel accelerated
   positively and θ̈ *grew*, so angular momentum was not conserved and no controller could
   balance it. `drives/ReactionWheel` is the same motor written as an action/reaction pair
   (`+k·i` on the wheel, `−k·i` on the housing, back-EMF on the relative rate); it is a
   composite of stdlib blocks (`VoltageSource`, `Resistor`, `Inductor`, `TorqueSource`,
   `Inertia`, …), so the whole plant is still iconic Rotation. Its taps give the wheel speed
   (`Drive/wsense/y`), the winding current (`Drive/isense/y`) and the wheel angle relative to
   the cube (`Drive/phi_rel`, used by the 3D binding).
2. **`RelSpeed` is an inline two-input block, not the stdlib `Sum`.** `Sum` takes one vector
   input, which a JSON signal graph cannot assemble from scalar outputs (the same reason as
   the `ErrorSum` of `dc-motor/speed-control`). It is the difference of two speeds, as the
   plan's "Sum of two Speed sensors" means.

## The design

`design/design.py` (a `uv` script with `numpy`/`scipy`) linearises the equations
**analytically** at upright. With `x = [θ, θ̇, ω_rel]`, `a = m·g·l`, `τ = k·i` and the
winding inductance neglected (`L/R = 0.1 ms ≪ Ts`, the non-linear check keeps it):

```
J θ̈ = a·sinθ − τ          J_w (θ̈ + ω̇_rel) = τ          τ = k (u − k ω_rel) / R

A = [[0, 1, 0], [a/J, 0, k²/(R J)], [−a/J, 0, −(k²/R)(1/J_w + 1/J)]]
B = [0, −k/(R J), (k/R)(1/J_w + 1/J)]ᵀ
```

It discretises `(A, B)` exactly (zero-order hold, `Ts = 2 ms`), solves the discrete
Riccati equation (`scipy.linalg.solve_discrete_are`) and writes `K` into the three `K_*`
parameters of the model document. **The gains it prints are what the model uses**; re-run it
after changing a weight:

```
uv run examples/reaction-wheel-1d/design/design.py
```

Weights (`q_i = 1/σ_i²`): `Q = diag(2500, 25, 0.01)` (σ_θ = 0.02 rad, σ_θ̇ = 0.2 rad/s,
σ_ω = 10 rad/s) and `R = 1/12²`. Result, for `u = −K x`:

```
K = [−446.597400, −43.875365, −0.762835]     (V/rad, V·s/rad, V·s/rad)
discrete closed-loop poles   0.3762, 0.9802, 0.9967
continuous equivalents       −488.8, −10.0, −1.65  1/s   (open loop: +11.06, −11.35, −1.86)
```

The unclamped demand at the initial tilt is 22.3 V, so the ±12 V clamp is active for the
first three samples (the first sample is at `t = Ts`; the declared 0 V is held before it) and
never again: after 0.1 s the voltage stays below 0.083 V.

## Results

`design.py` also integrates the **non-linear** closed loop (Radau, with `sin θ`, the winding
inductance, the 2 ms sample-and-hold and the clamp). The model run through the real Julia
worker reproduces it to better than 1e-5 rad.

| quantity | design.py | model run |
| --- | --- | --- |
| peak `|u|` | 12.000 V | 12.000 V |
| peak wheel speed (absolute / relative to the cube) | 4.165 / 4.684 rad/s | 4.165 / 4.684 rad/s |
| `θ(0.1 s)` | 0.014607 rad | 0.014607 rad |
| `|θ|` over `t ≥ 2 s` | 3.8929e-4 rad (0.0223°) | 3.8929e-4 rad |
| inside 0.2° from | 0.654 s | 0.654 s |
| `θ(4 s)` | −1.44e-5 rad | −1.44e-5 rad |
| wheel angle relative to the cube at 4 s | 3.075 rad | 3.075 rad |

## Checks

`expected.json` (22 checks, plan 9.7), run with `uv run examples/run_checks.py --only reaction-wheel-1d`:

- **`|θ| < 0.2°` within 2 s:** `max_abs_le` of `Body/theta` over [2, 4] s against 0.0034907 rad
  (measured 0.0223°), plus the same band from 0.7 s (the settle time is 0.654 s).
- **Wheel speed under 300 rad/s:** `max_abs_le` of the absolute wheel speed (peak 4.17 rad/s).
- **`|u| ≤ 12`:** `max_abs_le` of `LQR1/u`, plus the clamp being active at the first samples and
  the voltage being below 0.1 V after 0.1 s.
- Cursor values of θ at 0.1, 0.5, 1 and 4 s, the wheel speed at 1 and 4 s and the wheel angle at
  4 s against `design.py`; the angle sensor agrees with the body's own angle for the whole run.
- **No diagnostics:** `no_diagnostics` forbids `E901`, `E106`, `W201`, `W202`, `W205`, `W206`
  (the run reports none at all).

## 3D

`scenes/reaction-wheel-1d.sdf` is a 0.12 m semi-transparent cube whose lowest edge is the
world Y axis, with an orange wheel disk (and a dark spoke that makes the rotation visible)
on its centre. The cube link is pitched by 45° so that an edge points down; the centre is then
`0.12·√2/2 = 0.0849 m` above the edge, the model's `l`. Two bindings (`bindings` in the model):

| joint | signal | meaning |
| --- | --- | --- |
| `joint:edge` (revolute about the world Y axis) | `Body/theta` | the cube's angle from upright (positive: the top moves towards +X) |
| `joint:wheel_joint` (continuous about Y, parent = cube) | `Drive/phi_rel` | the wheel angle relative to the cube, about half a turn over the run |

## What to try

- Open the **Plots** tab: "Cube angle" shows the saturated start-up and the small overshoot,
  "Wheel speed" the wheel absorbing the cube's momentum, "Motor voltage" the 12 V samples at
  the start.
- Raise the initial tilt (`Body` start `theta` and `AngleSens` start `phi`, together): the
  clamp stays active longer and the wheel spins faster. The ±12 V and the wheel inertia set
  the largest tilt the controller can still catch.
- Change `Body/m` without re-running `design.py`: the gains are no longer matched to the
  plant, which shows how much margin the design has.
- Change a weight in `design/design.py` and run it: the new gains are written into `LQR1`.
