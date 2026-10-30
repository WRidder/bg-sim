# Drivetrain: motor, gearbox and a flexible rod

The classic **two-inertia drivetrain** (plan 9, a read-only sample): a DC motor drives a first wheel through a 10:1 gearbox; a flexible rod (torsion spring with a parallel damper) connects that wheel to a second, load, wheel. It exists in two forms that give the same numbers: this iconic model `drivetrain` and the pure bond graph model `bondgraph`.

```
Step1(12 V) -> V1 -> Motor1 -> Gear1(n=10) -> Wheel1
                                               |-- Rod(k=5, d=0.02) -- Wheel2
                                               '-- RodDamper
LoadStep(0.5 N m at 1 s) -> Load -> Wheel2
```

![Diagram of the iconic drivetrain|900](assets/71bf364046ce.png)

Blocks: [Step1](block:Step1) and [V1](block:V1) form the 12 V step source (at 0.01 s), [Motor1](block:Motor1) is the DC motor, [Gear1](block:Gear1) the ideal gear, [Wheel1](block:Wheel1) and [Wheel2](block:Wheel2) the two inertias, [Rod](block:Rod) the torsion spring, [RodDamper](block:RodDamper) its parallel damper, [Load](block:Load) with [LoadStep](block:LoadStep) the 0.5 N·m load torque at 1 s.

## What it shows

- **The gearbox is algebraic**: [Motor1/shaft.f](signal:Motor1/shaft.f) $= 10 \times$ [Gear1/b.f](signal:Gear1/b.f) at every instant, not only at steady state (check `ratio`, relative 1e-6).
- **The flexible rod is visible**: the voltage step at 0.01 s excites the two-inertia mode; the twist [Rod/phi](signal:Rod/phi) overshoots to 0.186 rad before the damper settles it.
- **The load is carried by the rod**: after the 0.5 N·m step at $t = 1$ s the twist settles at $0.5/5 = 0.1$ rad and the motor speed drops from 118.8 to 113.86 rad/s.

## What to try

- Open the **Plots** tab: "Speeds" and "Flexible rod" are preconfigured.
- Raise `Rod.k` to 50 N·m/rad: the oscillation moves up (see [the physics](page:physics)) and the transient twist shrinks; lower it to 1 and the two wheels drift apart.
- Set `RodDamper.d` to 0 to see the mode ring for the whole run.
- Plot [Motor1/shaft.f](signal:Motor1/shaft.f), [Wheel1/a.f](signal:Wheel1/a.f) and [Wheel2/a.f](signal:Wheel2/a.f) together.

## 3D view

`scenes/drivetrain.sdf` lines up the motor rotor, the first wheel behind the 10:1 gear and the load wheel behind the flexible rod, each a disc with a marker, turning with `Motor1/rotor/phi`, `Wheel1/phi` and `Wheel2/phi`. The rod twist is the angle between the two wheel markers.

![3D view at t = 0.3 s|500](assets/d83c6bcf7150.png)
