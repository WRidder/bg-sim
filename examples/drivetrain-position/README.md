# drivetrain-position — load-position servo on a compliant drivetrain

The plant of `drivetrain` (DC motor, 10:1 gear, two inertias, a shaft with a damper), with the shaft made **40 times softer** (1.2 N·m/rad). The load wheel and the shaft spring form a torsional mode at **3.9 Hz with a damping of 0.034**, right where a useful position loop wants its crossover. The task is a **position step of the load wheel** (1 rad at 0.2 s) and a **load-torque step** (0.2 N·m at 2.2 s), with a 24 V motor supply.

Two models run the same plant side by side:

| model | controller | what it shows |
| --- | --- | --- |
| `naive` | textbook PID on the motor-side position, tuned for a rigid drivetrain, 1 kHz | 104 % overshoot, rings at the mode for seconds, saturates on the step |
| `drivetrain-position` | 1 kHz firmware: smooth trajectory, Kalman filter on two encoders, model-inversion feedforward, LQR with integral action | 0.02 % overshoot, no ringing, the disturbance gone in 0.13 s |
| `drivetrain-position-open-loop` | none (voltage and load steps) | the plant against the ODE of `design/design.py` |

## Plant (a pure bond graph)

```
MSe(V) → 1( R=1 Ω, I=L=1 mH ) → GY(k_t=0.1) → 1( I=J_m=5e-5, R=R_d=1e-4 )
      → TF(1)·TF(0.1) ──10:1──→ 1( I=J1=1e-3 ) → 0 ─┬─ 1( C=1/1.2, R=1e-3 )  (the shaft)
                                                     └→ 1( I=J2=2e-3 ) ← MSe(load)
```

The model is built only from `MSe`, `I`, `R`, `C`, `GY`, `TF` and 0/1-junctions (the stdlib bond-graph elements, as in `drivetrain` and `drivetrain-kalman`). The shaft is a spring and a damper on one 1-junction (they carry the relative speed), hung on the 0-junction between the two wheels. The sensors are flow sensors with kinematic integrators (the D28 exception) and two `Quantizer`s at 1 ms. `design/build_model.py` writes the three model documents.

| quantity | value |
| --- | --- |
| motor | `R = 1 Ω`, `L = 1 mH`, `k_t = 0.1`, `J_m = 5e-5 kg·m²`, `R_d = 1e-4 N·m·s/rad`, supply limit 24 V |
| gear | `n = 10` (`TF(1)` then `TF(0.1)`) |
| wheels | `J1 = 1e-3`, `J2 = 2e-3 kg·m²` |
| shaft | `k = 1.2 N·m/rad`, `c = 1e-3 N·m·s/rad` |
| mode of the voltage-driven plant | **3.91 Hz, ζ = 0.034** (poles −0.84 ± 24.5j, −213, −788, 0 rad/s) |
| motor held / motor free | 3.90 Hz / 4.50 Hz (ζ = 0.012 from the shaft damper alone) |
| load | −0.2 N·m `MSe` effort at 2.2 s (a +0.2 N·m resisting torque, 0.17 rad of static shaft twist) |
| run | 3.2 s, 3201 points, solver auto (the ideal gear makes `IW1` a dependent store: a DAE), reltol 1e-8 |

## `naive`

Rigid-body view: `J_tot = J_m + (J1+J2)/n² = 8e-5 kg·m²`, the motor angle follows the voltage through `K_g/(τ s+1)` with `K_g = 9.9 rad/s/V` and `τ = 7.9 ms`. The textbook recipe `T_d = τ`, crossover `ω_c = 30 rad/s` (about 5 Hz), `T_i = 4/ω_c` gives `K_p = 3.03 V/rad`, `T_i = 0.133 s`, `T_d = 7.9 ms`, filter `N = 10`, with back-calculation anti-windup (`library/PositionPID.jl`, a 1 kHz digital PID; the stdlib `PID` has the integral gain `K_p/T_i²` and the derivative gain `T_d`, so the textbook form is a small project block). The loop is collocated, so it is stable, and it holds the motor tightly, so the load wheel rings on the shaft spring with the damping of the shaft alone.

## `drivetrain-position` (the showcase)

`library/PositionController.jl` is one `@discrete Ts = 1e-3` block:

1. **Trajectory.** A change of the command starts a septic smoothstep of 0.8 s (zero velocity, acceleration and jerk at both ends). A raw step has energy at 3.9 Hz, the smoothstep has almost none above 1/0.8 s = 1.25 Hz, so the command does not excite the mode. The closed form gives `r, r′, r″, r‴`, which the feedforward needs (a linear prefilter gives inexact derivatives).
2. **Kalman filter** on `[θ_m, ω_m, θ_L, ω_L, T_load]` (the load torque is a random walk, `Q = 3e-8 (N·m)²` per sample) with both encoders.
3. **Feedforward** by model inversion: shaft torque `J2·r″ + c·J2·r‴/k + T̂`, twist, motor speed, motor torque and the voltage `R/k_t·τ_m + k_t·ω_m,r`.
4. **LQR with integral action** (ZOH 1 ms, quasi-static electrics) on `[δ−δ_r, ω_m−ω_m,r, ω_L−r′, θ_L−r, z]`, clamp to ±24 V with back-off of the integrator.

Why this and not a notch: the loop has to *use* the mode (it needs the shaft twist to damp it), and a notch on the motor loop only keeps the controller out of the mode, leaving the load wheel to ring by itself; an observer-based state feedback damps it actively (the lightly damped pair at 3.9 Hz, ζ 0.034 becomes a pair at 16.8 Hz, ζ 0.74).

**Sensor choice.** The motor angle (12 bit, `2π/4096`) *and* the load angle (14 bit, `2π/16384`). The load angle is the controlled variable and the soft shaft decouples it from the motor; with the motor encoder alone, a slow load torque (`T/k` = 0.17 rad of twist) and a slow load motion cannot be told apart, and the load position would be a model output, not a measurement. A cheap load encoder (dual-loop servo practice) removes that; the motor encoder supplies the fast collocated information for the damping.

| parameter | value (design.py output) |
| --- | --- |
| LQR gain `K` on `[δ, ω_m, ω_L, θ_L, z]` | `[399.0, 0.2108, 42.94, 458.4, 646.8]` |
| Bryson `σ` (δ, ω_m, ω_L, θ, z, u) | 0.15 rad, 100 rad/s, 0.5 rad/s, 0.05 rad, 0.03 rad·s, 24 V |
| closed-loop poles | −427, −9.9, −1.7 rad/s and −78 ± 71j (16.8 Hz, ζ 0.74) |
| Kalman: noise | `R_n = diag((2π/4096)²/12, (2π/16384)²/12)`; `Q = diag(1e-12, 1e-6, 1e-12, 1e-7, 3e-8)` |
| observer poles | −167, −88, −47 ± 82j, −14 rad/s |
| trajectory | septic smoothstep, `Ttraj = 0.8 s` |

`Phi`, `Bd`, `Lm`, `Ll`, `K` and the plant constants are the defaults of the block parameters in `library/PositionController.jl`; `design.py` rewrites them between the `GAINS` markers.

## Measured numbers (real worker)

| | `naive` | `drivetrain-position` |
| --- | --- | --- |
| overshoot of the 1 rad step | **104.4 %** (peak 2.044 rad at 0.36 s) | **0.02 %** |
| settling into the 2 % band (0.02 rad), from the command | never (rings on) | **0.66 s** |
| oscillation 1.4 to 2.2 s, peak to peak | 1.15 rad | **0.39 mrad** |
| dip at the 0.2 N·m disturbance | 0.73 rad | **0.058 rad**, back inside 20 mrad in 0.13 s |
| peak voltage | 24.00 V (saturated at the step) | 13.3 V (at the disturbance) |
| maximum shaft twist | 0.90 rad | 0.33 rad |
| ringing frequency | 3.83 Hz (the mode) | — |

## Design against the bond graph

- Open loop (`drivetrain-position-open-loop`, +2 V at 0.05 s, −0.2 N·m at 0.6 s): the 5-state ODE (rotor, inductance, shaft, load, exact ZOH) against the bond graph at eight times: largest difference **1.4e-8 rad** for the load angle and the motor angle; the checks allow 1 µrad and 10 µrad.
- Closed loop: the prediction of `design/design.py` (the algorithm of the firmware against the exact ZOH truth with the inductance, encoders and clamp) against the real run: the largest difference of the load angle at the seven checked times is **2.7 mrad** (at 2.3 s, 100 ms after the disturbance; 0.3 mrad or less elsewhere); the check allows 4 mrad.
- Estimator: RMS(`θ_L_hat − θ_L`) is 0.73 mrad over 0.3 to 3.2 s; the torque estimate reaches 0.1999 N·m.

## Checks

`expected.json` (run with `uv run examples/run_checks.py --only drivetrain-position`):

- showcase: rest before the step; `step_response` (2 % band within 0.9 s, overshoot below 2 %); value at 2.15 s within 5 mrad; residual oscillation 1.4 to 2.15 s below 4 mrad peak to peak; disturbance dip at most 0.092 rad and the load back within 10 mrad at 3.2 s; `|V| ≤ 24 V`; the torque estimate within 5 % of 0.2 N·m; the angle estimate within 3 mrad RMS; seven `cursor_value` checks against the closed-loop prediction (4 mrad); no E003/E006/E102/E106/E303/E901/W206; `scene_bindings`;
- naive: the first load peak is at least 1.835 rad and the peak near 1.93 s at least 1.281 rad (`min_ge` windows around the peaks: a lower bound on the peak, so the contrast is real), ringing at 3.83 Hz ± 6 %, `|V| ≤ 24 V`, no error diagnostics, `scene_bindings`;
- open loop: 16 `cursor_value` checks against the ODE.

The tolerances are margins on the measured differences above and are explained in the `note` of every check. W201 (the ideal gear welds `IW1` to `IJm`) and W205 (a dimensionless bond island) are expected.

## What to try

- Open **Plots**: "Load position" of both models, zoom into the first second of `naive` and look at the shaft twist.
- Run `drivetrain-position` and plot `Ctrl/T_hat` against the 0.2 N·m load step.
- Shorten `Ttraj` of `Ctrl` and watch the twist and the voltage.
- Change the weights `SIGMA` in `design/design.py` and re-run it, then re-run the model: the gains are plain block defaults.

## Regenerate

```
uv run examples/drivetrain-position/design/build_model.py     # the three model documents
uv run examples/drivetrain-position/design/design.py          # gains into library/*.jl, expected.json, predictions
uv run examples/drivetrain-position/design/build_docs.py      # models/*.docs from design/docs.md (real runs, needs web/dist)
uv run examples/run_checks.py --only drivetrain-position
```

`design/build_docs.py` is the repository's docs builder pointed at `design/docs.md`; a plot series with `"model"` and `"signal_in"` overlays a second model's real run.

## 3D view

`scenes/drivetrain-position.sdf`: motor, gearbox, wheel 1, a thin shaft (0.705 m, from the face of wheel 1 to the face of wheel 2), wheel 2. Bindings: `rotor_joint ← Theta/y`, `wheel1_joint ← 0.1·Theta/y`, `wheel2_joint ← ThetaL/y`, and a torsion deformation of `visual:shaft_rod` with the **linear** basis driven by `C/q` (the wheel-2 minus the wheel-1 angle: `0.1·Theta/y + C/q = ThetaL/y` to 1e-13). The shaft belongs to the wheel-1 link, so it turns with wheel 1 and twists linearly towards wheel 2, θ(s) = s/L · `C/q`, the lumped spring's twist distribution; its far end sits at the wheel-2 angle. The twist (up to 0.33 rad in the showcase move, 0.9 rad in the `naive` ringing, 0.17 rad under the load) shows at true scale between the wheel markers, but on the shaft only as its stripes winding round it, by radius × angle (1.4 mm for 0.17 rad on the 8 mm shaft). All three models therefore set `scene.exaggeration` to **10** (`SCENE_EXAGGERATION` in `design/build_model.py`): the view opens with the twist drawn ×10, 1.7 to 3.3 rad in the showcase (the `naive` ringing briefly winds the stripes by more than a turn). Joints are never exaggerated; switch to ×1 for the true geometry.

## Read-only sample

This directory is a **sample**: it is copied into the user's projects folder on import. `expected.json` is the machine-readable acceptance used by `examples/run_checks.py` and `tools/check.py --lane x`.
