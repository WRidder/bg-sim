# drivetrain — motor, gearbox and a flexible rod between two inertias

A read-only **sample** of the classic two-inertia drivetrain: a DC motor drives a
10:1 gearbox, which drives the near wheel inertia; the far wheel inertia is
connected to it by a flexible rod (a torsion spring with a parallel damper). A
load-torque step is applied at t = 1 s. Only M1 stdlib blocks are used, so it is
the natural follow-up to the `dc-motor` sample.

```
Step1(12 V) → V1 → Motor1 → Gear1(n=10) → Wheel1(1e-3)
                                            ├── Rod(k=5, d=0.02) ── Wheel2(2e-3)
                                            └── RodDamper
LoadStep(0.5 N·m at 1 s) → Load → Wheel2 node
```

## What it shows

- **The gearbox is algebraic**: `Motor1/shaft.f = 10 × Gear1/b.f` at every
  instant, not only at steady state (`ratio` check).
- **The flexible rod is visible**: the 12 V voltage step at t = 0.01 s excites
  the two-inertia mode at about **29 Hz** (J₁ = 6e-3 kg·m² including the motor
  rotor reflected through the gear, J₂ = 2e-3 kg·m², k = 5 N·m/rad). The rod
  twist `Rod/phi` overshoots to **0.186 rad** (`max_abs` check) before the
  damper settles it.
- **The load is carried by the rod**: after the 0.5 N·m step at t = 1 s the rod
  settles at `phi = 0.1 rad` (0.5 / 5), the motor speed drops from 118.8 to
  **113.86 rad/s**, and both wheel speeds agree again.
- The motor current follows the torque balance `k·i = d·ω + reflected load`
  (**0.614 A** after the step).

## Parameters

| parameter | value | meaning |
| --- | --- | --- |
| Motor `R`, `L`, `k_t`, `J`, `d` | 1 Ω, 1 mH, 0.1, 5e-5 kg·m², 1e-4 N·m·s/rad | the DC motor |
| `Gear1.n` | 10 | `a.f = n·b.f` |
| `Wheel1.J`, `Wheel2.J` | 1e-3, 2e-3 kg·m² | the two inertias |
| `Rod.k`, `RodDamper.d` | 5 N·m/rad, 0.02 N·m·s/rad | the flexible rod |
| `Step1.final`, `t_step` | 12 V, 0.01 s | the voltage step |
| `Load.T`, `LoadStep.t_step` | 0.5 N·m, 1.0 s | the load step |

Simulation: `t_end = 2 s`, 5000 points, solver `auto`, reltol 1e-6.

## What to try

- Open the **Plots** tab: “Speeds” and “Flexible rod” are preconfigured.
- Raise `Rod.k` to 50 N·m/rad and watch the oscillation move to ~90 Hz and the
  transient twist shrink; lower it to 1 and watch the two wheels drift apart.
- Set `RodDamper.d` to 0 to see the mode ring for the whole run.
- Plot `Motor1/shaft.f`, `Wheel1/a.f` and `Wheel2/a.f` together: the far wheel
  lags the near one during the voltage step and catches it after the rod has
  transferred the torque.

## Read-only sample

This directory is a **sample**: it is copied into the user's projects folder on
import (the copy gets a new project name, e.g. `drivetrain-2`, if one already
exists). The files here are never written by the editor. `expected.json` is the
machine-readable acceptance used by `examples/run_checks.py` and
`tools/check.py --lane x`.
