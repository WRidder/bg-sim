# drivetrain-kalman — LQG on a flexible two-inertia drivetrain

Plan 9.5's multi-domain control sample. A **pure bond-graph** plant (D28) — a DC
motor, a 10:1 gearbox, two wheel inertias and a flexible rod — is driven by a
**1 ms discrete LQG firmware**: an LQR with integral action and a steady-state
Kalman filter that reconstructs the load speed from the motor encoder alone. A
10 rad/s reference steps at 0.1 s and a −0.5 N·m load torque steps at 1 s. A
second model swaps the ideal gear for a backlash composite.

## Plant

```
MSe(V) → 1-junction( R=1 Ω, L=1 mH ) → MotorGY(k=0.1) → 1-junction( J_m=5e-5, R_d=1e-4 )
      → TF(1)·TF(0.1) ──10:1──→ WheelJ1( I=1e-3 ) → S1(0) ─┬─ Rod1(1): C=1/150, R=0.02
                                                          └─ MidJ1( I=6.7e-5 ) → S2(0) …
      → … → S3(0) → WheelJ2( I=2e-3 ) → Load( MSe, −0.5 N·m at 1 s )
```

| quantity | value |
| --- | --- |
| motor | `R = 1 Ω`, `L = 1 mH`, `k_t = 0.1 N·m/A`, `J_m = 5e-5 kg·m²`, `R_d = 1e-4 N·m·s/rad` |
| gearbox | `n = 10` (`TF(1)` then `TF(0.1)`: a TF reverses the flow, so the pair gives +10:1) |
| wheel 1 / wheel 2 | `J1 = 1e-3`, `J2 = 2e-3 kg·m²` |
| rod | 3 × (C = 1/150 F, R = 0.02 N·m·s/rad) with two 6.7e-5 kg·m² intermediate inertias → 50 N·m/rad in series |
| load | −0.5 N·m MSe effort at t = 1 s (a +0.5 N·m resisting torque) |
| run | 2 s, 4001 points, `solver = auto` (Rodas5P: the ideal gear makes IW1 a dependent store, so the problem is a DAE), reltol 1e-8 |

The rod is the **plan's real three-segment rod**, not a lumped equivalent: each
segment is a 0-junction (the relative speed) with a 1-junction carrying the C and
R in parallel, and the segments are chained through the two intermediate
inertias. The plant is assembled only from `MSe`, `I`, `C`, `R`, `TF`, `GY` and
0/1-junctions; the only code is the firmware (`library/LQGController.jl`) and the
sensors.

### Sensors

The controller sees **one** measurement, the motor angle:

- `MotorSpeed` — a `FlowSensor` on the motor 1-junction;
- `Theta` — a kinematic `Integrator` of that speed (the D28 sensor exception);
- `Encoder` — a `Quantizer` at `Ts = 1 ms` with `2*pi/4096` rad (12-bit);
- `Current` — a second `FlowSensor` on the electrical 1-junction (recorded, not
  used by the controller).

There is no load-side sensor: `ω_L` is reconstructed by the Kalman filter.

## Controller

`library/LQGController.jl` is one `@discrete Ts = 1e-3` block with the plan's
structure: predict/measurement update, the integral of the load-speed error,
anti-windup, a ±24 V clamp and `w_load_hat`. `design/design.py` writes its
matrices into the model JSON:

| parameter | value (design.py output) |
| --- | --- |
| `Phi` | 5×5 ZOH model at 1 ms |
| `Bd` | `[7.88e-4, 1.53, 2.6e-7, 9.3e-4, 0]` |
| `Cd` | `[1, 0, 0, 0, 0]` |
| `L` | `[0.214, 25.71, 0.080, 0.960, −2.00]` |
| `K` | `[176.25, 0.3955, −1762.5, 11.99, 0]` |
| `Ki` | `223.31` |
| `Kff` | `16.95 V/(rad/s)` |
| `umax` | `24 V` |

The discrete state matrix is `Phi`, not `Ad`, because `Ad` is now the library's adjoint
builtin (`Ad(H)`) and a declaration that shadows a builtin is E003.

**State.** `xhat = [θ_m, ω_m, θ_L, ω_L, T_load]`; the first four are the plan's
states and `w_load_hat = xhat[4]`, as in the plan. The fifth is the load torque.

**Two documented deviations from the plan's literal code**, both necessary for a
10 rad/s reference:

1. *The reference is fed forward.* The plan's `v = -K·xhat + Ki·z` has no
   reference term, so at 10 rad/s its own state feedback would ask for more than
   150 V. `Kff = n·K2 + K4 + k_t·n` cancels the speed feedback at the reference
   point and adds the back-EMF `k_t·n·w_ref`; the integral then only trims the
   load torque (the measured steady voltage is 10.5–10.7 V). This is the
   standard reference gain of a state-feedback servo.
2. *The Kalman filter has five states.* A four-state filter (load torque only as
   process noise) keeps a steady bias of about 1.3 rad/s in `ω_L` while the load
   acts — the model cannot distinguish a load torque from a voltage offset. The
   fifth state is a random walk with `Q_n = 1e-6 (N·m)²` per sample, so the
   0.5 N·m step is learned in a few tens of ms.

The design itself is in the plan's equivalent relative coordinates
`[δ, ω_m, ω_L, z]` with `δ = θ_m/n − θ_L` (the absolute-angle LQR with integral
augmentation is not controllable: `z = w_ref·t − θ_L` is a linear combination of
the states). The gain maps back to the plan's absolute form with
`K = [k_δ/n, k_ωm, −k_δ, k_ωL]`, `Ki = −k_z`, which is exactly feedback on
`δ, ω_m, ω_L`.

## Design (`design/design.py`)

`uv run examples/drivetrain-kalman/design/design.py` linearizes the 4-state model
(quasi-static electrics, one lumped rod spring of 50 N·m/rad, the motor damping
`R_d`), discretizes it with ZOH at 1 ms, solves the LQR with integral
augmentation and the steady-state Kalman filter, writes the matrices into both
model documents, and then integrates the sampled closed loop against a 9-state
reference (three-segment rod **and** the 1 mH electrics, RK4 at 2e-5) to print
the acceptance values.

Weights, Bryson style (`Q_ii = 1/σ_i²`, `R = 1/σ_u²`):

| state | σ | weight |
| --- | --- | --- |
| rod twist `δ` | 0.32 rad | `q = 10` |
| motor speed error `ω_m − n·w_ref` | 100 rad/s | `q = 1e-4` |
| load speed error `ω_L − w_ref` | 1 rad/s | `q = 1` |
| integral `z` | 0.07 rad | `q = 200` |
| voltage | 24 V | `R = 1/576` |

The twist is deliberately cheap: a stiff loop would fight the 25 Hz rod mode.
`q_z = 200` sets `Ki` and the 0.3 s load recovery.

The Kalman filter uses `R_n = (2π/4096)²/12 = 1.96e-7 rad²` (the encoder
quantization) and the torque random walk above; the four plant states carry a
`1e-12` numerical floor (the two angle modes have a pole at +1 and would
otherwise be undetectable from `Q_n` alone). `scipy.linalg.solve_discrete_are`
is not used: with the pure integrator it returns the *anti-stabilizing* DARE root
(closed-loop |eig| > 1), so the script uses a Newton–Kleinman iteration from a
stabilizing seed and scales `Q`/`R` by `1/R` for conditioning.

## Checks

`expected.json` is the machine-readable acceptance; `uv run examples/run_checks.py`
runs it through the real Julia worker:

| check | limit | measured |
| --- | --- | --- |
| `ω_L` at 0.6 s (0.5 s after the reference step) | 10 ± 2 % | **10.130 rad/s** (+1.3 %) |
| `ω_L` at 1.3 s (0.3 s after the load step) | 10 ± 2 % | **10.112 rad/s** (+1.1 %) |
| `ω_L` at 2.0 s | 10 ± 2 % | **10.123 rad/s** |
| `w_load_hat` at 2.0 s | 10 ± 1 % | **9.9987 rad/s** |
| RMS(`w_load_hat − ω_L`) over [0.5, 2] s | < 0.2 rad/s | **0.181 rad/s** |
| max \|u\| | ≤ 24 V | **24.000 V** (the clamp is active on the step) |
| diagnostics | no E901/E106/W206 | W201 (IW1/IJm in derivative causality) and W205 (dimensionless bond island) only |

The RMS residual is the encoder's 12-bit staircase at the 1 ms sampling phase
plus the three-segment rod's two mid inertias, which the 4-state design model
lumps away; the estimator has no load-side measurement at all. The estimation
check is the plan's 0.2 rad/s.

`rms_difference` and `max_abs_le` are the two check kinds added to the shared
`examples/run_checks.py` for this sample (an RMS between two signals and a
one-sided bound; the existing `max_abs` is an equality test).

## Backlash variant

`models/drivetrain-backlash.bgmodel.json` is the same plant with the ideal gear
replaced by the **`GearWithBacklash` composite** from J2.6 (`LossyGear` →
`GearBacklash`, `gap = 0.02 rad`, tooth `k = 1e4 N·m/rad`, `d = 5`) copied into
`library/`. The variant only has to **complete**; it runs the full 2 s and
documents the limit cycle around 10 rad/s (`w_load_hat` RMS against the plant is
0.43 rad/s). Two modelling notes:

- The composite's `LossyGear` is ideal (`eta = 1`): the fixture's 0.9 efficiency
  is a loss model, and with the phase-shifted algebraic switch the stiff DAE
  failed the solver (E901).
- The composite's ports declare `Rotation`, so the stdlib `GY` (two `Generic`
  ports) would straddle a Rotation and a Generic island (**E102**). The variant
  therefore uses `library/MotorGY.jl`, the same gyrator equations with explicit
  `Electrical`/`Rotation` ports. The final bond runs wheel 1 → gear so that the
  one transformer inside the composite has the same +10:1 sign as the ideal
  `TF(1)·TF(0.1)` chain.

## What to try

- Open **Plots**: “Load speed” overlays `IW2/p.f` with `LQG/w_load_hat`; zoom
  into t = 1 s to see the load step, the 9.0 rad/s dip and the 0.3 s recovery.
- Plot `V/p.e` to see the ±24 V saturation on the reference step.
- Plot `IW1/p.f`, `IM1/p.f`, `IM2/p.f`, `IW2/p.f` together: the three rod
  segments ring at ~25 Hz during the step and settle in phase.
- Open the backlash model and compare its load speed with the ideal one.
- Re-run `design.py` with a different `Q` and re-run the model: the gains are
  plain JSON parameters.

## Read-only sample

This directory is a **sample**: it is copied into the user's projects folder on
import. The files here are never written by the editor (only `design/design.py`
writes the gains, when invoked by hand). `expected.json` is the machine-readable
acceptance used by `examples/run_checks.py` and `tools/check.py --lane x`.

## 3D view

`scenes/drivetrain-kalman.sdf` has the motor rotor, the gearbox output, wheel 1, the two intermediate inertias of the rod and wheel 2. The model only measures the motor angle `Theta/y`, so the gearbox output is `0.1 * Theta/y` and each rod segment is a joint bound to its twist `C1/q`, `C2/q`, `C3/q`; wheel 2 lags wheel 1 by their sum. `drivetrain-backlash` also binds the gear play `Gear/play/phi` (gain -1) between the gear output and wheel 1.
