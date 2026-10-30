# Plant

## Supply and valve

[PS](block:PS) is a `PressureSource` with `p` = 1e7 Pa; [TK](block:TK) a `Tank` at `p` = 1e5 Pa. The [Valve](block:Valve) subsystem holds four `VariableOrifice` elements around four hydraulic 0-junctions `JP`, `JT`, `JA`, `JB` (a common pressure on each rail, flows sum to zero):

| orifice | path | normalised area input |
| --- | --- | --- |
| `Valve/PA` | P to A | $\max(s, 0) + 10^{-4}$ |
| `Valve/BT` | B to T | the same as PA |
| `Valve/PB` | P to B | $\max(-s, 0) + 10^{-4}$ |
| `Valve/AT` | A to T | the same as PB |

with the spool command $s \in [-1, 1]$. All four orifices have `A` = $A_{max} = 10^{-5}\ \mathrm{m^2}$, `Cd` = 0.62, `rho` = 850 kg/m³ and `p_tr` = 1e5 Pa, so the open area is $A_{max}\max(\pm s, 0) + 10^{-9}\ \mathrm{m^2}$, the 10^-9 m² being the leakage area. The inline block `Valve/VDrive` splits the one spool input into the two normalised areas.

The orifices use the shipped regularised law

$$Q = C_d\,A\,\sqrt{\frac{2}{\rho}}\;\frac{\Delta p}{(\Delta p^2 + p_{tr}^2)^{1/4}},$$

which is linear for $|\Delta p| \ll p_{tr}$ and square-root for $|\Delta p| \gg p_{tr}$.

The four valve ports are exposed through series `FlowSensor` elements (`FSP`, `FST`, `FSA`, `FSB`, zero pressure drop) because a JSON subsystem power port must attach to a power port, not to a junction face (E102).

## Cylinder

`HydraulicCylinder` with piston area $A_p = 2\cdot10^{-3}\ \mathrm{m^2}$, annulus $A_r = 10^{-3}\ \mathrm{m^2}$, dead volumes $V_{0A} = V_{0B} = 5\cdot10^{-5}\ \mathrm{m^3}$, bulk modulus $\beta = 1.4\cdot10^9$ Pa and stroke $0.2$ m. Its chamber pressures are states:

$$\dot p_A = \frac{\beta\,(Q_A - A_p v)}{V_{0A} + A_p x}, \qquad \dot p_B = \frac{\beta\,(Q_B + A_r v)}{V_{0B} + A_r(\text{stroke} - x)}, \qquad F_{rod} = p_B A_r - p_A A_p .$$

Here $Q_A$, $Q_B$ are the volume flows into the chambers (the `A.f`, `B.f` of the cylinder) and $v$ is the rod speed. The rod effort is positive into the cylinder, so the load sees $-F_{rod} = p_A A_p - p_B A_r$.

## Load

The rod port connects to a translation 1-junction `Jrod` (common velocity $v$) with `IM` = 50 kg, `RD` = 500 N·s/m and the `PositionSensor` `XS`, which integrates the rod velocity (the D28 exception: a kinematic integrator):

$$m\,\dot v = p_A A_p - p_B A_r - c\,v, \qquad \dot x = v, \qquad m = 50\ \mathrm{kg},\ c = 500\ \mathrm{N\,s/m}.$$

## Units

| quantity | unit |
| --- | --- |
| pressure (`Cyl/pA`, `Cyl/pB`, `PSensA/y`, orifice `dp`) | Pa (1 bar = 1e5 Pa) |
| volume flow (orifice `Q`, `PS/a.f`) | m³/s |
| position, velocity (`XS/y`, `IM/p.f`) | m, m/s |
| force (`IM/p.e`, `RD/p.e`) | N |
| spool (`PID1/y`) and normalised area (`VDrive/ap`) | dimensionless |
