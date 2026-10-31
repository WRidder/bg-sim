# Motion servo: S-curve position loop with encoder feedback

A DC motor turns one revolution along a jerk-limited S-curve. A sampled PD controller
closes the loop on a 4096-count encoder and commands the duty of an averaged H-bridge on
a 24 V bus. The model shows the blocks of the **Motion and drive electronics** library
group working together: `SCurveProfile`, `Encoder` and `HBridge`.

## Model `position-loop`

```
Ref (SCurveProfile) ──q──► Err ──► PD (DiscretePID, 1 ms) ──duty──► Bridge (HBridge) ──► Motor (DCMotor)
                            ▲                                          ▲                     │ shaft
                            └──── Enc (Encoder, 4096 cpr, 1 ms) ◄── Angle ◄──────────────────┘
                                                          Bus 24 V ──┘
```

| Quantity | Value |
| --- | --- |
| Move | 0 → 2π rad from t = 0.1 s, `v_max` 20 rad/s, `a_max` 200 rad/s², `j_max` 4000 rad/s³ (ends at 0.564 s) |
| Motor | `R` 2 Ω, `L` 0.5 mH, `k_t` 0.05 N·m/A, rotor plus load 1.1e-4 kg·m², 1e-5 N·m·s/rad friction |
| Bridge | 24 V bus, `R_on` 0.05 Ω, duty −1..1 |
| Controller | `DiscretePID`, 1 ms, `Kp` 10 /rad (240 V/rad), `Td` 6 ms, integral off (`Ti` 1000 s), output −1..1 |
| Encoder | 4096 counts per revolution (1.53 mrad), 1 ms |

The S-curve takes 0.05 s per jerk phase, 0.15 s to accelerate, cruises for 0.164 s and
mirrors the acceleration. The setpoint position, velocity, acceleration and jerk are all
plotted.

## What to look at

1. Run the model. The measured angle follows the setpoint within 18 mrad during the move.
   The error is largest at the end of the acceleration, because the loop has no velocity
   feedforward.
2. After the move the motor holds 2π within one encoder count. The error is the encoder
   quantization: the controller only sees whole counts, and it dithers between neighbouring
   counts.
3. Compare `Bridge/i` (winding current) with `Bridge/i_dc` (bus current): the bridge draws
   `duty·i` from the bus, so the bus current is small while the duty is small.
4. Replace the `SCurveProfile` with a `TrapezoidalProfile` with the same `v_max` and `a_max`.
   The acceleration then jumps, and the tracking error during the move grows.
5. Put a `PWM` (`low` −1, `high` 1, a few hundred Hz) between `PD` and `Bridge` to see the
   switching ripple in `Bridge/i`. Every edge is a solver event, so raise the event limit
   in the run settings for a fast carrier.

## Checks

`expected.json` checks the end of the setpoint, the tracking error during and after the
move, the final angle and the current, and that the run has no solver or event-limit
diagnostics (`uv run examples/run_checks.py --only motion-servo`).
