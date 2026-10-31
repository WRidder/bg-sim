# Motor thermal (Thermal domain)

A 24 V DC motor drives a fan while its copper loss heats the winding. The winding conducts
heat through the insulation into the housing, which cools by convection to the ambient air.
The winding resistance rises with temperature, so the hot motor draws less current and runs
slower than the cold one: the electrical, mechanical and thermal parts form one loop.

## Topology

```
 One ─► Supply (24 V) ── Motor (DCMotorThermal) ── shaft ── Fan (2e-4 kg·m²), Drag (4e-4 N·m·s/rad)
                              │ winding (heat port)
                              ▼
          Loss ─► Winding (30 J/K) ── QIns ─► Insulation (1.5 W/K) ── Housing (150 J/K)
                                                                         │
                                         QConv ─► Film (h = 20 W/(m²·K), A = 0.05 m²) ─► Ambient (293.15 K)
```

* **Motor.** `DCMotorThermal`: `R = 2 Ω` at `T_ref = 293.15 K`, copper `alpha = 0.00393 1/K`,
  `L = 0.5 mH`, `k_t = 0.05 N·m/A`. Its winding resistance is a `ResistorHeated`, so the whole
  copper loss `i²·R(T)` leaves the `winding` port as heat flow.
* **Thermal network.** Pseudo bond graph ports: temperature in K, heat flow in W. Three
  `HeatFlowSensor`s (`Loss`, `QIns`, `QConv`) sit in series with the heat path, and three
  `Integrator`s turn their heat flows into energies for the first-law checks.

## Steady state

The fixed point of the loop (solved in `expected.json`): `T_winding = 322.95 K` (49.8 °C),
`T_housing = 311.03 K`, `R = 2.234 Ω`, copper loss `17.88 W`, speed `353.6 rad/s`.

## Checks

`uv run examples/run_checks.py --only motor-thermal` checks the steady state, that the heat
flow leaving the winding port equals the dissipated electrical power to 1e-9 W, the first law
of the winding and of the housing at every sample, and the port-power ledger of the
electrical and rotational side (thermal ports carry pseudo-power and are left out).
