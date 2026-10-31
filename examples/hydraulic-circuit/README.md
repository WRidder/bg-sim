# Hydraulic circuit

A small open-loop hydraulic circuit built only from the hydraulic component library: a
motor-driven pump with a relief valve, a check valve, a hose to an accumulator, and a
4/3 proportional valve that extends and retracts a loaded cylinder. It is the showcase of
`FixedDisplacementPump`, `PressureReliefValve`, `CheckValve`, `Pipe`, `Accumulator` and
`DirectionalValve43`; every law is smooth, so the run has no switching events except the
spool command's start.

## Topology

```
 EMotor (150 rad/s) ── shaft ── Pump (10 cm³/rev) ── PumpLine (20 cm³) ── Check ── Rail (50 cm³) ── Valve P
                                 │ suction              │                          │                 │ A ── Cyl.A ┐
                                Tank ◄──── Relief (100 bar)                       Hose (2 m)          │ B ── Cyl.B ┤── rod ── Load (100 kg), Damp (2000 N·s/m)
                                Tank ◄───────────────────────────────────────── Acc (0.2 l)   Valve T ─► Tank
```

* **Supply.** `EMotor` is a `SpeedSource` at 150 rad/s (about 1430 rpm). The
  `FixedDisplacementPump` has `D = 1.6e-6 m³/rad` (10 cm³/rev), `eta_v = 0.95`,
  `eta_m = 0.9` at 100 bar and 157 rad/s; it delivers about 2.3e-4 m³/s (13.7 L/min).
* **Protection.** The `PressureReliefValve` (`p_set = 100 bar`, `dp_reg = 5 bar`) relieves the
  pump line (`PumpLine`, a 20 cm³ `Volume`) to the 1 bar `Tank`.
* **Rail.** A `CheckValve` (1 bar cracking) feeds the rail (`Rail`, 50 cm³), so the rail and
  the accumulator cannot drain back into the pump. A 2 m hose (`Pipe`, d = 10 mm,
  turbulent `f_t = 0.03`, `N = 2` segments) connects the rail to a 0.2 l `Accumulator`
  precharged to 50 bar (`n = 1.4`).
* **Actuator.** The `DirectionalValve43` (`A_max = 1e-5 m²`, 2% overlap) is driven by
  `Spool`, a sine `0.4·sin(π(t − 0.5))` from 0.5 s: P→A and B→T open from 0.5 to 1.5 s
  (extend), P→B and A→T from 1.5 to 2.5 s (retract). The `HydraulicCylinder` (piston
  2e-3 m², annulus 1e-3 m², stroke 0.5 m) moves a 100 kg `Load` against a 2000 N·s/m
  `Damp`.

## Measured results (t_end = 3 s)

| Quantity | Value |
|---|---|
| Pump flow `Pump/Q` (at 100 bar) | 2.274e-4 m³/s |
| Peak pump line pressure `PumpLine/p` | 101.24 bar (relief valve, 1.24 bar into its regulation range) |
| Peak rail pressure `Rail/p` | 101.40 bar (hose pressure wave while charging, 0.37 s) |
| `Relief/Q / Pump/Q` at 0.5 s (charged, valve centred) | 1.000002 |
| Most negative check valve flow `Check/Q` | -2e-11 m³/s (leakage only) |
| Lowest accumulator pressure `Acc/p` during the strokes | 74.05 bar at 1.21 s |
| Rod position `Cyl/x` at 1.5 s / 2.5 s | 0.09769 m / 0.02383 m |
| Peak rod speed `Load/v` (extend / retract) | 0.156 m/s / -0.119 m/s |
| Pump loss `Pump/P_loss` | 2.0 W to 393.5 W (never negative) |
| Wall time (`auto` solver, 3001 output points) | about 5 s |

## Checks (`expected.json`)

`uv run examples/run_checks.py --only hydraulic-circuit` runs the model through the real
worker. The 12 checks are:

* the relief valve caps `PumpLine/p` and `Rail/p` below 106 bar (`p_set + dp_reg` above the
  tank), and at 0.5 s the pump line sits at 101.24 bar with all of the pump flow over the
  relief valve (`Relief/Q / Pump/Q = 1`);
* the check valve never passes more than leakage backwards (`Check/Q >= -1e-9`);
* the rod positions at 1.5 s and 2.5 s, and the rod stays inside the stroke;
* the pump loss is never negative;
* the accumulator keeps the rail above 70 bar while it supplies the strokes;
* the run has no structural or solver diagnostics.

## What to try

1. Plot `PumpLine/p`, `Rail/p` and `Acc/p`: the pump charges the accumulator through the
   hose until the relief valve opens at 100 bar; during the strokes the accumulator
   supplies the peak flow.
2. Plot `Pump/Q`, `Relief/Q` and `Check/Q`: once the circuit is charged all pump flow goes
   over the relief valve, and the check valve passes only what the cylinder takes.
3. Set the accumulator `V0` to `2e-5` (a tenth): the rail pressure now drops further while
   the cylinder moves.
4. Set the valve `lap` to `-0.05` (open centre): the circuit no longer holds pressure at
   rest, and the pump flow returns to the tank through the valve.
