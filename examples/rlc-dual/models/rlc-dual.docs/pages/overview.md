# Series RLC: iconic and bond graph in one model

One model holds two **independent subsystems** (plan 9.3) that describe the same series RLC circuit driven by a 1 V step:

- [Iconic](block:Iconic): `Step1 -> V1 -> R1 -> L1 -> C1 -> Ground1`, ordinary electrical components;
- [Bondgraph](block:Bondgraph): `Se1 -> 1-junction J1 -> R1, IL, C1`, the same circuit as a pure bond graph.

The two subsystems expose no port and the root diagram has no connection: the circuits do not touch. Inside, every node has its ordinary local name, and the signal ids carry the subsystem path, for example [Iconic/C1/p.e](signal:Iconic/C1/p.e) and [Bondgraph/C1/p.e](signal:Bondgraph/C1/p.e). Blocks inside a subsystem are reached with `block:Iconic/R1` links, for example [Iconic/R1](block:Iconic/R1) and [Bondgraph/IL](block:Bondgraph/IL).

![Root diagram with the two subsystems|700](assets/9f6e9229941d.png)

## What to try

- Open the **Plots** tab: "Capacitor voltages" overlays the two subsystems. Zoom into the first 5 ms to see the peak.
- Double-click `Iconic`, then use the breadcrumbs to switch to `Bondgraph`: one model holds both diagrams.
- Plot [Iconic/L1/i](signal:Iconic/L1/i) and [Bondgraph/IL/p.f](signal:Bondgraph/IL/p.f): the inductor current is the same in both forms (it rings at 866 rad/s and is 0 A at the voltage peak).
- Change `R1.R` of the iconic subsystem and `R1.r` of the bond graph to the same new value: the curves still coincide.

## 3D view

`scenes/rlc-dual.sdf` has two gauge columns on a plate, one per subsystem. Each column's height (`scale.z`) and colour follow the capacitor voltage (`Iconic/C1/v` and `Bondgraph/C1/p.e`, 0 to 1.2 V); a line on the plate marks 1 V. An electrical circuit has no geometry, so this is a gauge, not a mechanism. The picture is taken near the voltage peak at 3.6 ms.

![3D gauges at t = 3.6 ms|500](assets/37c63c821c6d.png)

Next: [the circuit equations](page:model) and [the results](page:results).
