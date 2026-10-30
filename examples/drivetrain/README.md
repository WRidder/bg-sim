# drivetrain — motor, gearbox and a flexible rod between two inertias

A read-only **sample** of the classic two-inertia drivetrain, in two forms:
- `drivetrain` — the iconic model: `DCMotor` → `IdealGear` → `Inertia` → `TorsionSpring`
  + `RotationalDamper` → `Inertia`;
- `bondgraph` — the same plant in **pure bond graph**: `MSe` → 1-junction (`R`, `I`) →
  `GY` → 1-junction (`I`, `R`) → two `TF`s → 1-junction (`I`) → rod (0/1-junctions with
  `C` and `R`) → 1-junction (`I`, load `MSe`).

Both run for 2 s and produce the same numbers to ~1e-8. A 12 V step starts the motor at
t = 0.01 s and a 0.5 N·m load step arrives at t = 1 s. Only M1 stdlib blocks are used, so
this is the natural follow-up to the `dc-motor` sample.

```
Step1(12 V) → V1 → Motor1 → Gear1(n=10) → Wheel1(1e-3)
                                            ├── Rod(k=5, d=0.02) ── Wheel2(2e-3)
                                            └── RodDamper
LoadStep(0.5 N·m at 1 s) → Load → Wheel2 node
```

The pure bond-graph model:

```
Step → MSe → 1-junction( R=1, I_L=1e-3 ) → GY(k=0.1)
     → 1-junction( I_J=5e-5, R_d=1e-4 ) → TF(1) → TF(0.1) → J3( 1-junction, I_1=1e-3 )
     → 0-junction ── J4( 1-junction, I_2=2e-3, MSe(load) )
          │
       1-junction( C=0.2, R=0.02 )      # the rod: spring and damper in parallel
```

The two transformers are 1:1 and 10:1: a TF reverses the flow
(`p2.f = -n·p1.f`), so a single 10:1 TF would make the wheels turn against the
motor. The 1:1 stage first reverses, the 0.1 stage reverses again and gives the
10:1 reduction — the same ratio and the same sign as the iconic `IdealGear`.
The rod is a `C` (compliance `c = 1/k = 0.2`) and an `R` (0.02) in parallel on a
1-junction, fed by a 0-junction that forms the relative speed between the two
inertia junctions. That is the bond-graph form of a torsion spring with a
parallel damper. The load `MSe` has effort −0.5 N·m on its port; with the
power-positive-into-each-port convention that is the +0.5 N·m load seen by the
wheel.

## What it shows

- **The gearbox is algebraic**: `Motor1/shaft.f = 10 × Gear1/b.f` at every
  instant, not only at steady state (`ratio` check).
- **The flexible rod is visible**: the 12 V voltage step at t = 0.01 s excites
  the two-inertia mode at about **7.9 Hz** (J₁ = 6e-3 kg·m² including the motor
  rotor reflected through the gear, J₂ = 2e-3 kg·m², k = 5 N·m/rad). The rod
  twist `Rod/phi` overshoots to **0.186 rad** (`max_abs` check) before the
  damper settles it.
- **The load is carried by the rod**: after the 0.5 N·m step at t = 1 s the rod
  settles at `phi = 0.1 rad` (0.5 / 5), the motor speed drops from 118.8 to
  **113.86 rad/s**, and both wheel speeds agree again.
- The motor current follows the torque balance `k·i = d·ω + reflected load`
  (**0.614 A** after the step).

The pure bond-graph model reproduces all of these: `IJm/p.f` = 113.863,
`IW1/p.f` = 11.386, `IW2/p.f` = 11.388, `Crod/q` = 0.09996, and the `compare`
checks against the iconic model are below 1e-6 over the whole run. Its manifest
reports **W201** on `IW1` (the wheel-side inertia is in derivative causality
because the two transformers make the gear rigid). The run and values are
unaffected; the warning is the honest bond-graph causality of a rigid gear.

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

## 3D view

`scenes/drivetrain.sdf` lines up the motor rotor, the first wheel behind the 10:1 gear and the load wheel behind the flexible rod, each a disc with a marker. In `drivetrain` they turn with `Motor1/rotor/phi`, `Wheel1/phi` and `Wheel2/phi`; the rod twist is the angle between the two wheel markers. The `bondgraph` model has speeds only, so its three discs are coloured by speed (`IJm/p.f`, `IW1/p.f`, `IW2/p.f`).
