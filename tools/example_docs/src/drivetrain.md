@@ figures drivetrain
{
  "diagram": {"kind": "diagram", "model": "drivetrain"},
  "scene": {"kind": "scene", "model": "drivetrain", "t": 0.3},
  "run": {
    "kind": "plot", "model": "drivetrain", "xlim": [0, 2],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "Motor1/shaft.f", "label": "motor shaft"}, {"signal": "Gear1/b.f", "label": "Gear1/b.f x 10", "scale": 10, "style": "--"}, {"signal": "Wheel2/a.f", "label": "Wheel2/a.f x 10", "scale": 10, "style": ":"}], "legend": true},
      {"ylabel": "rod twist Rod/phi [rad]", "series": [{"signal": "Rod/phi", "label": "Rod/phi", "color": "#d95f02"}],
       "hlines": [{"y": 0.1, "label": "0.5 / 5 = 0.1 rad"}], "legend": true},
      {"ylabel": "motor current [A]", "series": [{"signal": "Motor1/i", "label": "Motor1/i", "color": "#1b9e77"}]}
    ]
  }
}
@@ page drivetrain overview - | Overview
# Drivetrain: motor, gearbox and a flexible rod

The classic **two-inertia drivetrain** (plan 9, a read-only sample): a DC motor drives a first wheel through a 10:1 gearbox; a flexible rod (torsion spring with a parallel damper) connects that wheel to a second, load, wheel. It exists in two forms that give the same numbers: this iconic model `drivetrain` and the pure bond graph model `bondgraph`.

```
Step1(12 V) -> V1 -> Motor1 -> Gear1(n=10) -> Wheel1
                                               |-- Rod(k=5, d=0.02) -- Wheel2
                                               '-- RodDamper
LoadStep(0.5 N m at 1 s) -> Load -> Wheel2
```

![Diagram of the iconic drivetrain|900](@fig:diagram)

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

![3D view at t = 0.3 s|500](@fig:scene)
@@ page drivetrain physics overview | Physics
# Physics

## Parameters

| parameter | value | meaning |
| --- | --- | --- |
| `Motor1` $R$, $L$, $k_t$, $J$, $d$ | 1 Ω, 1 mH, 0.1 N·m/A, 5e-5 kg·m², 1e-4 N·m·s/rad | the DC motor |
| `Gear1.n` | 10 | `a.f` = n · `b.f` |
| `Wheel1.J`, `Wheel2.J` | 1e-3, 2e-3 kg·m² | the two inertias |
| `Rod.k`, `RodDamper.d` | 5 N·m/rad, 0.02 N·m·s/rad | the flexible rod |
| `Step1` | 0 to 12 V at 0.01 s | supply |
| `LoadStep`, `Load.T` | 0 to 1 at 1.0 s, 0.5 N·m | load torque |

The run lasts 2 s with 5000 output points (`solver` auto, `reltol` 1e-6).

## Equations

Motor (as in the `dc-motor` example), with speed $\omega_m$ and current $i$:

$$L\,\dot i = V - R\,i - k_t\,\omega_m, \qquad J_m\,\dot\omega_m = k_t\,i - d\,\omega_m - \frac{T_g}{1} .$$

The ideal gear has speed ratio $n = 10$ and conserves power, so $\omega_m = n\,\omega_1$ and the torque on the wheel side is $n\,T_g$. Wheel 1 and wheel 2 with the rod twist $\varphi = \theta_1 - \theta_2$:

$$J_1\,\dot\omega_1 = n\,T_g - k\,\varphi - c\,(\omega_1 - \omega_2), \qquad J_2\,\dot\omega_2 = k\,\varphi + c\,(\omega_1 - \omega_2) - T_L,$$

with $k = 5$ N·m/rad, $c = 0.02$ N·m·s/rad and $T_L = 0.5$ N·m for $t \ge 1$ s.

## Two-inertia mode

Reflecting the motor rotor through the gear, the near side has

$$J_1^{\mathrm{eff}} = J_{wheel1} + n^2 (J_m) = 1\cdot10^{-3} + 100\cdot 5\cdot10^{-5} = 6\cdot10^{-3}\ \mathrm{kg\,m^2}, \qquad J_2 = 2\cdot10^{-3}\ \mathrm{kg\,m^2}.$$


The undamped mode of the rod between the two inertias, with the motor rotor free, would be

$$\omega_n = \sqrt{k\left(\frac{1}{J_1^{\mathrm{eff}}} + \frac{1}{J_2}\right)} = \sqrt{5\,(166.7 + 500)} = 57.7\ \mathrm{rad/s} \approx 9.2\ \mathrm{Hz}.$$

In the model the motor is not free: the voltage source holds the armature, so the back-EMF acts as a viscous damper $k_t^2/R = 0.01$ N·m·s/rad at the motor shaft, which is $n^2 k_t^2/R = 1$ N·m·s/rad at wheel 1. That damps the mode strongly and lowers its frequency. The run shows it directly: the twist peaks at 0.0448, 0.1716, 0.2985 and 0.4253 s with heights 0.1865, 0.0722, 0.0279 and 0.0108 rad, a **period of 0.1268 s (7.9 Hz)** and a decay of 0.39 per period. The README quotes about 29 Hz; that is what an undamped rod of $k = 50$ N·m/rad would give ($\sqrt{50 \cdot 666.7} = 182.6$ rad/s), not the model value ($k = 5$ N·m/rad).

## Steady states

Before the load: $\omega_m = k_t V/(k_t^2 + R d) = 118.8$ rad/s. After the load step the reflected load torque is $T_L/n = 0.05$ N·m at the motor shaft, so $k_t i = d\,\omega_m + 0.05$ with $i = (V - k_t\omega_m)/R$ gives $\omega_m = 113.86$ rad/s, $i = 0.614$ A, and the rod carries the load with $\varphi = T_L/k = 0.1$ rad.
@@ page drivetrain results overview | Results and checks
# Results and checks

![Speeds (scaled by the gear ratio), rod twist and motor current|900](@fig:run)

The wheel speeds are multiplied by 10 in the plot to lie on the motor speed. After the load step at 1 s the twist settles at 0.1 rad.

## Acceptance checks (`expected.json`)

| signal at $t = 2$ s | expected | tolerance |
| --- | --- | --- |
| [Motor1/shaft.f](signal:Motor1/shaft.f) | 113.86311499086523 rad/s | relative 1e-3 |
| [Gear1/b.f](signal:Gear1/b.f) | 11.386311499086522 rad/s | relative 1e-3 |
| [Wheel2/a.f](signal:Wheel2/a.f) | 11.388161507683192 rad/s | relative 1e-3 |
| [Motor1/i](signal:Motor1/i) | 0.6136987112051235 A | relative 1e-3 |
| [Rod/phi](signal:Rod/phi) | 0.09996294077514448 rad | relative 1e-3 |

Further checks: the ratio [Motor1/shaft.f](signal:Motor1/shaft.f) / [Gear1/b.f](signal:Gear1/b.f) is 10 (relative 1e-6); [Wheel1/a.f](signal:Wheel1/a.f) / [Wheel2/a.f](signal:Wheel2/a.f) is 1 at 2 s (relative 1e-3); the largest $|\varphi|$ in $[0.01, 1]$ s is 0.18648149316390142 rad (relative 1e-3); the motor speed of this model and of the bond graph model agree to 5e-5 rad/s over the whole run.
@@ figures bondgraph
{
  "diagram": {"kind": "diagram", "model": "bondgraph"},
  "scene": {"kind": "scene", "model": "bondgraph", "t": 0.3}
}
@@ page bondgraph overview - | Overview
# Drivetrain, pure bond graph

The same plant as the iconic `drivetrain` model, built only from bond graph elements:

```
Step -> MSe -> 1-junction( R=1, I_L=1e-3 ) -> GY(0.1)
     -> 1-junction( I_J=5e-5, R_d=1e-4 ) -> TF(1) -> TF(0.1) -> J3( 1-junction, I_1=1e-3 )
     -> 0-junction S0 -- J4( 1-junction, I_2=2e-3, MSe(load) )
          |
       T0( 1-junction, C=0.2, R=0.02 )   # the rod: spring and damper in parallel
```

![Diagram of the bond graph drivetrain|900](@fig:diagram)

| block | element | value |
| --- | --- | --- |
| [MSe1](block:MSe1) | modulated effort source fed by `Step1` | 0 to 12 V at 0.01 s |
| [R1](block:R1), [IL](block:IL) | winding resistance, inductance | 1 Ω, 1e-3 H |
| [GY1](block:GY1) | gyrator (torque constant) | 0.1 |
| [IJm](block:IJm), [Rd](block:Rd) | motor rotor inertia and damping | 5e-5, 1e-4 |
| [TF1](block:TF1), [TF2](block:TF2) | transformers 1:1 and 10:1 | `n` = 1, 0.1 |
| [IW1](block:IW1), [IW2](block:IW2) | wheel inertias | 1e-3, 2e-3 |
| [Crod](block:Crod), [Rrod](block:Rrod) | rod compliance $c = 1/k$ and damper | 0.2, 0.02 |
| [MSe2](block:MSe2) | load effort source fed by `LoadStep` | 0 to -0.5 N·m at 1 s |

## Why two transformers

A transformer reverses the flow ($f_2 = -n f_1$), so a single 10:1 `TF` would make the wheels turn against the motor. The 1:1 stage reverses first, the 0.1 stage reverses again and gives the 10:1 reduction, the same ratio and sign as the iconic `IdealGear`.

## The rod

The rod is a `C` (compliance $c = 1/k = 0.2$) and an `R` (0.02) on a 1-junction, fed by the 0-junction [S0](block:S0) that forms the relative speed between the two inertia junctions [J3](block:J3) and [J4](block:J4). That is the bond graph form of a torsion spring with a parallel damper; the twist is the state `Crod/q`. The load source has effort -0.5 N·m on its port; with the power-positive-into-each-port convention that is the +0.5 N·m load seen by the wheel.

## Causality: W201

The manifest reports **W201** on `IW1`: the wheel-side inertia is in derivative causality because the two transformers make the gear rigid. Run and values are unaffected; it is the honest bond graph causality of a rigid gear.

## Results

Plot [IJm/p.f](signal:IJm/p.f), [IW1/p.f](signal:IW1/p.f), [IW2/p.f](signal:IW2/p.f) and [Crod/q](signal:Crod/q). At $t = 2$ s (relative 1e-3): `IJm/p.f` 113.86311499566987, `IW1/p.f` 11.386311499566988, `IW2/p.f` 11.388161502151661 and `Crod/q` 0.09996294068301954; the ratio `IJm/p.f` to `IW1/p.f` is 10; the largest `Crod/q` in $[0.01, 1]$ s is 0.18648149316411403. The motor speed agrees with `Motor1/shaft.f` of the iconic model to 5e-5 rad/s from $t = 0.01$ s.

## 3D view

The bond graph model has speeds only, so the three discs of the scene are coloured by speed (`IJm/p.f`, `IW1/p.f`, `IW2/p.f`).

![3D view at t = 0.3 s|500](@fig:scene)
