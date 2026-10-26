# rlc-dual — the same series RLC as an iconic diagram and as a bond graph

One model, two **independent subsystems** (plan 9.3):

- `Iconic` — a series RLC driven by a 1 V step:
  `Step1 → V1 → R1 → L1 → C1 → Ground1`;
- `Bondgraph` — the same circuit as a pure bond graph:
  `Se1 → J1 (1-junction) → R1, IL, C1`.

Neither subsystem exposes a port: the circuits do not touch, so the model is
`diagram.nodes = [Iconic, Bondgraph]` with no root connections. Internally the
node names are the ordinary flat instance names, and the full signal ids carry
the subsystem path (`Iconic/C1/p.e`, `Bondgraph/C1/p.e`).

## Parameters

| quantity | value |
| --- | --- |
| resistance `R` (iconic) / `r` (bond graph) | 10 Ω |
| inductance `L` / `i` | 10 mH |
| capacitance `C` / `c` | 100 µF |
| source | 1 V step at t = 0 (iconic `Step`; `Se` = 1 V for the bond graph) |
| `t_end` | 0.01 s |
| output grid | 20000 points, `solver = auto`, reltol 1e-10, abstol 1e-12 |

With `ω0 = 1/sqrt(LC) = 1000 rad/s` and `ζ = (R/2)·sqrt(C/L) = 0.5`, the
capacitor voltage has the analytic step response

```
v_C(t) = 1 - e^(-ζω0 t) [cos(ωd t) + (ζ/√(1-ζ²)) sin(ωd t)],  ωd = ω0√(1-ζ²)
```

so it peaks at `t = π/ωd = 3.6276 ms` with

```
v_peak = 1 + exp(-πζ/√(1-ζ²)) = 1.16303353482 V
```

i.e. a **16.303 % overshoot**. Both subsystems start from the same initial
state (`v_C = 0`, `i_L = 0`), so the two capacitor voltages are identical, not
merely similar.

## Checks

`expected.json` is the machine-readable acceptance. `uv run examples/run_checks.py`
(and `uv run tools/check.py --lane x`) runs it through the real Julia worker:

- the capacitor voltage peaks at **1.16303353426 V** at t = 3.62768 ms in both
  subsystems (`max_abs` over `[0, 0.01] s`, abs tolerance 0.001 V — the plan's
  16.3 % ± 0.1 %); the analytic peak is 1.16303353482 V, so the solver misses it
  by 5.6e-10 V;
- `Iconic/C1/p.e` and `Bondgraph/C1/p.e` agree on the union of the run's own
  time grid over the whole run: **max |Δv| = 4.22e-15 V** (limit 1e-8 V,
  `compare_signals`);
- no `W201`, `W202` or `E106` in the manifest (`no_diagnostics`): SCAP gives
  integral causality on both storage elements. The run does report **W205** for
  the pure `Generic` bond island, which plan 5.6 prescribes and the check
  deliberately allows.

## What to try

- Open the **Plots** tab: “Capacitor voltages” overlays the two subsystems;
  zoom into the first 5 ms to see the peak.
- Enter `Iconic` (double-click) and then `Bondgraph` (breadcrumbs) to see that
  one model holds both diagrams; each has its own local node names.
- Plot `Iconic/L1/i` and `Bondgraph/IL/p.f`: the inductor current is the same
  in both forms (it rings at 866 rad/s and reaches 0 A at the overshoot peak).
- Change `R1.R` in the iconic subsystem and `R1.r` in the bond graph to the same
  new value, then run: the two curves still lie on top of each other.
