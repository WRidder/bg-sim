# Thermal domain

Thermal blocks are in the **Thermal** category of the library. Use them for winding temperatures, heat sinks, housings and anything else that warms up and cools down. Their ports and wires are drawn in rose, and a thermal port shows the letter **Th** when you hover it.

## Ports: temperature and heat flow

A thermal port carries two values:

| Field | Meaning | Unit |
| --- | --- | --- |
| `e` | absolute temperature of the port | K |
| `f` | heat flow **into** the block at that port | W |

- Temperatures are absolute. Write 20 °C as `293.15` and 80 °C as `353.15`.
- Wire several thermal ports together to make one **thermal node**: all ports on it have the same temperature, and their heat flows add up to zero.
- Temperature times heat flow is not a power, so a thermal bond is a **pseudo bond**. This is the convention of Modelica, Simscape and 20-sim's iconic thermal library, and it keeps every parameter in the units of a datasheet (J/K, W/K, W/(m²·K)).
- A thermal port never connects to an electrical, mechanical or hydraulic port. The editor refuses the drop, and the compiler reports E102 for a model edited as text.

## Blocks

| Block | Ports | What it does | Key parameters |
| --- | --- | --- | --- |
| `HeatCapacitor` | `a` | stores heat: `C·dT/dt = a.f` | `C` [J/K] (= mass × specific heat), start value `T` (the initial temperature) |
| `ThermalConductor` | `a`, `b` | conducts `Q = G·(Ta − Tb)` | `G` [W/K] (k·A/L for a slab) |
| `ThermalResistor` | `a`, `b` | the same law written as `Ta − Tb = R·Q` | `R` [K/W] |
| `Convection` | `solid`, `fluid` | Newton cooling, `Q = h·A·(T_solid − T_fluid)` | `h` [W/(m²·K)], `A` [m²] |
| `VariableConvection` | `solid`, `fluid`, input `h` | the same with `h` from a signal (a fan speed map) | `A` [m²] |
| `BodyRadiation` | `a`, `b` | grey-body radiation, `Q = ε·σ·A·(Ta⁴ − Tb⁴)` | `epsilon`, `A` [m²] |
| `FixedTemperature` | `a` | holds the port at `T` (an ambient, a coolant) | `T` [K] |
| `PrescribedTemperature` | `a`, input `T` | the port temperature from a signal in K | none |
| `FixedHeatFlow` | `a` | injects the heat flow `Q` into the node | `Q` [W] |
| `PrescribedHeatFlow` | `a`, input `Q` | injects the heat flow from a signal in W | none |
| `TemperatureSensor` | `a`, output `y` | reads the temperature in K; draws no heat | none |
| `HeatFlowSensor` | `a`, `b`, output `y` | sits in series and reads the heat flow from `a` to `b` | none |

The `Q` and `dT` variables of the two-port blocks are recorded, so you can plot every heat flow without adding sensors.

## Coupling losses into the thermal network

Only three blocks connect a thermal port to another domain. Each sends **all** of the power it dissipates to its heat port, so energy is conserved exactly: the electrical or mechanical energy lost equals the heat that arrives.

| Block | Category | Ports | Law |
| --- | --- | --- | --- |
| `ResistorHeated` | Thermal | `p`, `n` (Electrical), `heat` | `R = R0·(1 + alpha·(T − T0))` at the heat port temperature; `v·i` leaves through `heat` |
| `DCMotorThermal` | Thermal | as `DCMotor`, plus `winding` | the DC motor with its copper loss `i²·R` on `winding`; `R` rises with the winding temperature (`alpha` = 0.00393 1/K for copper) |
| `RS` | Bond graph | `p` (Generic), `heat` | the bond graph R element `p.e = r·p.f`, plus `heat.f = −p.e·p.f`: any R on an electrical, mechanical or hydraulic bond that heats something |

`RS` takes its domain from its bond like every bond graph element: bonded to a rotating inertia, `r` is a viscous friction in N·m·s/rad; bonded to an electrical port, it is a resistance in Ω.

Bond graph elements also work on thermal bonds: a `C` bonded into a thermal island is a heat capacity in J/K and an `R` is a thermal resistance in K/W. A 0-junction is a thermal node. Do not use `PowerSensor` or a port's `P` signal on a thermal bond: there the product is K·W, not a power.

## Example

The **motor-thermal** example drives a fan-like load with `DCMotorThermal`. The copper loss heats the winding (`HeatCapacitor`), which conducts to the housing (`ThermalConductor`), which cools to the ambient by `Convection`. Plot `Winding/T` and `Housing/T` to see the two time constants, and `Motor/R_hot` to see the winding resistance rise with temperature.
