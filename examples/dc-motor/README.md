# DC motor (plan 9.1, milestone M1)

The walking skeleton: one physical model, built twice — once from iconic components
(voltage source, motor, ground, a damper and two fixed shafts) and once as a bond graph
(`Se → 1-junction(R, I) → GY → 1-junction(I, R)`). Both must produce the same rotor speed.

## Parameters

| Quantity | Value |
| --- | --- |
| Winding resistance `R` | 2 Ω |
| Winding inductance `L` | 0.5 mH |
| Torque constant `k_t` | 0.05 N·m/A |
| Rotor inertia `J` | 1e-5 kg·m² |
| Viscous damping `d` | 1e-6 N·m·s/rad (in the separate `RotationalDamper`) |
| Supply | 12 V step at t = 0.01 s |
| `t_end` | 1 s |

## What to try

1. Open **iconic**, press **Run** (Ctrl+Enter), and add `Motor1/shaft.f` to a plot. It settles
   at `k·V / (k² + R·d) = 239.808 rad/s`.
2. Open **bondgraph** and run it. The `Se` is a constant 12 V (no step), so compare the settled
   part: from t = 0.5 s the two models agree to better than 1e-12 rad/s.
3. Inspect the motor: change `R` and run again — the parameter-only re-run reuses the compiled
   system (a few tens of milliseconds), so it is a good place to feel the edit/run loop.
4. Drag the damper's `d` up and watch the steady-state speed drop: `ω = k·V/(k² + R·d)`.
5. Zoom the plot: the UI re-requests `/data` with the new time window and pixel width.

## Checks

`expected.json` holds the acceptance values, and `uv run examples/run_checks.py` runs them
through the real Julia worker:

- steady state at t = 1 s: `239.80815347721824 rad/s` (rtol 1e-4);
- cursor readout at t = 0.2 s: `239.8 ± 0.1 rad/s` (the same number the Playwright test
  asserts);
- iconic vs bond graph from t = 0.5 s: max |Δω| < 1e-6 rad/s.

The file is read by `examples/run_checks.py` and uses three machine-readable check kinds:

- `final_value` — the named signal at `t`, compared with `rtol` (relative to `value`);
- `cursor_value` — the same interpolation, with an absolute `abs` tolerance;
- `compare` — model `a`'s `signal_a` against model `b`'s `signal_b` on the union of
  their time grids from `from_t`, with a maximum absolute difference `max_abs`.

The signal ids are the plan 3.1 ids in the run manifest. The runner reads `columns.f64`
in manifest order, behind the time column. The legend shows the rotation unit as `1/s`
(radians are dimensionless in plan 5.3); the plan quotes the same quantity as rad/s.
