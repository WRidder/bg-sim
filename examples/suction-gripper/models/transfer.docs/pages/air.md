# Air flow

Pressures are gauge pressures, so vacuum is negative. Flows are free-air volume flows in m³/s, as generator datasheets give them. The pneumatics reuse the hydraulic domain. The [Manifold](block:Manifold) is a `Volume` with bulk modulus $p_{atm}$, which is the isothermal gas law.

## Generator

`stdlib:contact/VacuumGenerator` (new) follows its suction curve:

$$Q = Q_{max}\left(1 - x\lvert x\rvert^{n-1}\right),\quad x = \Delta p/\Delta p_{max}$$

n = 1 is the straight line of an ejector, and n = 2 to 4 gives the flatter curve of a displacement pump. The example uses an ejector with $\Delta p_{max}$ = 60 kPa and $Q_{max}$ = 60 l/min (1e-3 m³/s). [Valve](block:Valve) switches the generator on at t = 0 and to release (vent) when the gripper has pressed the carton onto the table.

## Leaks per cup

Each cup chamber is a capacitance: $\dot p = p_{atm}(Q_{leak} + Q_{por} + Q_{vac})/V$. It has three leaks:

- **Lip roughness**: an orifice of $A_{lip0}$ = 0.03 mm², with the regularised law $Q = C_d A\,\Delta p\sqrt{2/(\rho\sqrt{\Delta p^2 + p_{tr}^2})}$.
- **Lifted lip**: the same law, with the gap ring $\pi D_{lip} h$ added to the area. A peeling cup therefore loses vacuum, which lowers its capacity and makes it peel further. This feedback is the loss mechanism.
- **Darcy flow through the material**: $Q_{por} = k_{perm} A_{eff}\,\Delta p$. The example uses $k_{perm}$ = 0 for a sealed parcel, 4e-7 for cardboard and 2e-6 m/(s·Pa) for porous material.

## Supply topology

[Line1](block:Line1) to `Line6` are `CupValve` blocks: an orifice of 7 mm² (a 3 mm line) with two options. A flow-closing valve shuts to a 2 % bleed when the pressure drop exceeds `dp_close`. A check valve is the reverse-flow fraction `r_rev`. The three supply variants are:

| variant | how | model |
| --- | --- | --- |
| common manifold | plain lines | `transfer`, `edge-leak` |
| per-cup flow valves | `dp_close` = 8 kPa | `edge-leak-valves` |
| restrictor nozzles | `A_line` = 1 mm² | design.py |
| a generator per cup | six 10 l/min generators, no manifold | `separate-generators` |

## Pick-up

![Vacuum build-up and flows (cardboard, 60 l/min)|800](assets/216684b27989.png)

When the valve opens, the generator first evacuates the manifold and the six chambers. The steady state is where the generator curve meets the leak demand. With cardboard and 60 l/min this is 48.3 kPa per cup, with a free-air flow of 11.6 l/min.
