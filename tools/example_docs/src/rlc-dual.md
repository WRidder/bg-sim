@@ figures rlc-dual
{
  "diagram": {"kind": "diagram", "model": "rlc-dual"},
  "scene": {"kind": "scene", "model": "rlc-dual", "t": 0.0036},
  "run": {
    "kind": "plot", "model": "rlc-dual", "xlim": [0, 0.01],
    "rows": [
      {"ylabel": "capacitor voltage [V]",
       "series": [{"signal": "Iconic/C1/p.e", "label": "Iconic/C1/p.e", "lw": 3.0}, {"signal": "Bondgraph/C1/p.e", "label": "Bondgraph/C1/p.e", "style": "--", "color": "#222222"}],
       "hlines": [{"y": 1.16303353482, "label": "analytic peak 1.16303 V"}], "legend": true},
      {"ylabel": "inductor current [A]",
       "series": [{"signal": "Iconic/L1/i", "label": "Iconic/L1/i", "lw": 3.0}, {"signal": "Bondgraph/IL/p.f", "label": "Bondgraph/IL/p.f", "style": "--", "color": "#222222"}], "legend": true}
    ]
  }
}
@@ page rlc-dual overview - | Overview
# Series RLC: iconic and bond graph in one model

One model holds two **independent subsystems** (plan 9.3) that describe the same series RLC circuit driven by a 1 V step:

- [Iconic](block:Iconic): `Step1 -> V1 -> R1 -> L1 -> C1 -> Ground1`, ordinary electrical components;
- [Bondgraph](block:Bondgraph): `Se1 -> 1-junction J1 -> R1, IL, C1`, the same circuit as a pure bond graph.

The two subsystems expose no port and the root diagram has no connection: the circuits do not touch. Inside, every node has its ordinary local name, and the signal ids carry the subsystem path, for example [Iconic/C1/p.e](signal:Iconic/C1/p.e) and [Bondgraph/C1/p.e](signal:Bondgraph/C1/p.e). Blocks inside a subsystem are reached with `block:Iconic/R1` links, for example [Iconic/R1](block:Iconic/R1) and [Bondgraph/IL](block:Bondgraph/IL).

![Root diagram with the two subsystems|700](@fig:diagram)

## What to try

- Open the **Plots** tab: "Capacitor voltages" overlays the two subsystems. Zoom into the first 5 ms to see the peak.
- Double-click `Iconic`, then use the breadcrumbs to switch to `Bondgraph`: one model holds both diagrams.
- Plot [Iconic/L1/i](signal:Iconic/L1/i) and [Bondgraph/IL/p.f](signal:Bondgraph/IL/p.f): the inductor current is the same in both forms (it rings at 866 rad/s and is 0 A at the voltage peak).
- Change `R1.R` of the iconic subsystem and `R1.r` of the bond graph to the same new value: the curves still coincide.

## 3D view

`scenes/rlc-dual.sdf` has two gauge columns on a plate, one per subsystem. Each column's height (`scale.z`) and colour follow the capacitor voltage (`Iconic/C1/v` and `Bondgraph/C1/p.e`, 0 to 1.2 V); a line on the plate marks 1 V. An electrical circuit has no geometry, so this is a gauge, not a mechanism. The picture is taken near the voltage peak at 3.6 ms.

![3D gauges at t = 3.6 ms|500](@fig:scene)

Next: [the circuit equations](page:model) and [the results](page:results).
@@ page rlc-dual model overview | Circuit and equations
# Circuit and equations

## Parameters

Both subsystems use the same values:

| quantity | iconic | bond graph | value |
| --- | --- | --- | --- |
| resistance | `R1.R` | `R1.r` | 10 Ω |
| inductance | `L1.L` | `IL.i` | 10 mH |
| capacitance | `C1.C` | `C1.c` | 100 µF |
| source | `Step1` 0 to 1 at $t = 0$ s, through `V1` | `Se1.e` = 1 V constant | 1 V |

The run lasts 0.01 s on 20000 output points (`solver = auto`, `reltol` 1e-10, `abstol` 1e-12). Both start from $v_C = 0$, $i_L = 0$.

## Bond graph

The source $S_e$ drives the 1-junction (common current $i$); on the junction the efforts add up to zero. $R$ dissipates, the $I$ element (inductor) and the $C$ element (capacitor) store energy, both in integral causality:

$$L \frac{di}{dt} = V - R\,i - v_C, \qquad C \frac{dv_C}{dt} = i .$$

The iconic circuit gives the same two equations from Kirchhoff's laws, so one intermediate IR serves both and the results agree to round-off.

## Second-order step response

$$\omega_0 = \frac{1}{\sqrt{L C}} = 1000\ \mathrm{rad/s}, \qquad \zeta = \frac{R}{2}\sqrt{\frac{C}{L}} = 0.5, \qquad \omega_d = \omega_0\sqrt{1 - \zeta^2} = 866\ \mathrm{rad/s}.$$

The capacitor voltage after a 1 V step is

$$v_C(t) = 1 - e^{-\zeta\omega_0 t}\left[\cos(\omega_d t) + \frac{\zeta}{\sqrt{1-\zeta^2}} \sin(\omega_d t)\right].$$

It peaks at $t = \pi/\omega_d = 3.6276$ ms with

$$v_{peak} = 1 + \exp\!\left(-\frac{\pi\zeta}{\sqrt{1-\zeta^2}}\right) = 1.16303353482\ \mathrm{V},$$

a 16.303 % overshoot.
@@ page rlc-dual results overview | Results and checks
# Results and checks

![Capacitor voltage and inductor current of both subsystems|900](@fig:run)

The two forms lie on top of each other, as they must: both start from the same state and are the same differential equations.

## Acceptance checks

| check | expected | tolerance |
| --- | --- | --- |
| peak of `Iconic/C1/p.e` over $[0, 0.01]$ s | 1.16303353426 V | 0.001 V (the plan's 16.3 % +- 0.1 %) |
| peak of `Bondgraph/C1/p.e` | 1.16303353426 V | 0.001 V |
| `Iconic/C1/p.e` against `Bondgraph/C1/p.e`, max difference over the run | 0 | 1e-8 V |
| diagnostics W201, W202, E106 | absent | |
| 3D bindings | match the scene | |

The README reports the measured peak 1.16303353426 V at $t = 3.62768$ ms (the analytic value is 1.16303353482 V, so the solver misses it by 5.6e-10 V) and a maximum difference between the subsystems of 4.22e-15 V.

**W205.** The run reports W205 for the pure `Generic` bond island of the bond graph subsystem. Plan 5.6 prescribes this warning and the check deliberately allows it. Causality is fine: SCAP assigns integral causality on both storage elements, hence no W201/W202/E106.

Back to the [model](page:model) or the [overview](page:overview).
