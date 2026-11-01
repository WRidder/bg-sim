# Hydraulics

Hydraulic blocks are in the **Hydraulic** category of the library; pumps, motors, the cylinder and the pressure and flow sensors are in **Converters and sensors**. A hydraulic port carries the **pressure** in Pa (its effort) and the **volume flow** in m³/s (its flow), positive into the block. Wires join hydraulic ports into nodes with one pressure, whose flows add up to zero.

The library is isothermal: one fluid with a constant density `rho`, viscosity `nu` and bulk modulus `beta`. Select a block and press `F1` for its full parameter list.

## Blocks

| Block | Ports | What it does | Key parameters |
| --- | --- | --- | --- |
| `PressureSource` | `a`, input `u` | holds the pressure `p·u` | `p` |
| `FlowSource` | `a`, `b`, input `u` | takes `Q·u` in at `a` and pushes it out of `b` | `Q` |
| `Tank` | `a` | constant pressure (the reservoir) | `p` |
| `Volume` | `a` | fluid compressibility, `p' = beta·Q/V` | `V`, `beta` |
| `Accumulator` | `a` | gas-charged accumulator: `p·V_gas^n` constant; empty below the precharge | `p0`, `V0`, `n`, `V_dead` |
| `Orifice`, `VariableOrifice` | `a`, `b` (input `u`) | turbulent orifice, smooth through zero | `Cd`, `A`, `rho`, `p_tr` |
| `CheckValve` | `a` → `b` | opens above the cracking pressure, blocks reverse flow | `p_crack`, `dp_open`, `A_max`, `A_leak` |
| `PressureReliefValve` | `a` → `b` | opens at the set pressure and caps the pressure in `a` | `p_set`, `dp_reg`, `A_max` |
| `DirectionalValve43` | `P`, `T`, `A`, `B`, input `u` | 4/3 proportional valve; `u` is the spool position from −1 to 1 | `A_max`, `lap`, `A_leak` |
| `PressureCompensatedFlowControl` | `a`, `b`, input `u` | holds the flow `Q_nom·u` once the pressure drop exceeds `dp_c` | `Q_nom`, `dp_c` |
| `Pipe` | `a`, `b` | lumped line: friction, fluid inertia and compressibility in `N` segments | `L`, `d`, `nu`, `beta`, `f_t`, constant `N` |
| `FixedDisplacementPump` | `a` (suction), `b` (delivery), `shaft` | `Q = D·w` less leakage, torque `D·Δp` plus friction | `D`, `eta_v`, `eta_m` |
| `VariableDisplacementPump` | as above, input `u` | displacement `D·u` (−1 to 1) | `D`, `eta_v`, `eta_m` |
| `HydraulicMotor` | `a` (inlet), `b` (outlet), `shaft` | `w = Q/D`, torque `D·Δp`, less losses | `D`, `eta_v`, `eta_m` |
| `HydraulicCylinder` | `A`, `B`, `rod` | double-acting cylinder with chamber compressibility | `Ap`, `Ar`, `stroke` |
| `PressureSensor`, `FlowSensor` | output `y` | read a pressure (no flow) or a flow (no pressure drop) | none |

## Units and typical values

- Pressures are in **Pa**: 1 bar = 1e5 Pa, so 100 bar is `1e7`. Flows are in **m³/s**: 1 L/min ≈ 1.667e-5 m³/s.
- Pump and motor displacements are per **radian**: `D` in m³/rad = cm³/rev × 1e-6 / (2π). A 10 cm³/rev pump has `D = 1.59e-6`.
- Mineral oil: `rho = 850` kg/m³, `nu = 3.2e-5` m²/s (32 cSt), `beta = 1.4e9` Pa; with air and hoses the effective `beta` is often lower.

## Valves and orifices

Every orifice, valve edge and the flow control valve use the same regularized orifice law,

`Q = Cd·A·√(2/ρ)·Δp / (Δp² + p_tr²)^(1/4)`,

which is the square-root law above the transition pressure `p_tr` (default 1 bar) and linear below it, so the flow passes smoothly through zero.

- The valve openings are smooth: a check valve opens between `p_crack` and `p_crack + dp_open`, a relief valve between `p_set` and `p_set + dp_reg`, and a spool edge between the lap and full stroke. There are no switching events, so the models also run in a fixed-step [export](page:export).
- `A_leak` is the area of a closed valve. Keep it small but not zero: it keeps a closed valve and the pressure behind it well defined.
- `DirectionalValve43`: `u > 0` connects P→A and B→T, `u < 0` connects P→B and A→T. `lap > 0` is an overlap (a dead band, closed centre), `lap < 0` an underlap (an open centre), `lap = 0` a critical centre. Beyond `|u| = 1` the edges stay fully open.

## Pumps and motors

The efficiencies apply at a nominal point (`p_nom`, `w_nom`): the leakage grows linearly with the pressure, and the friction torque is proportional to the pressure and always opposes the rotation. With `eta_v = eta_m = 1` a pump or motor is ideal: the mechanical power `T·w` equals the hydraulic power `Δp·Q`. The `P_loss` signal is the power lost to leakage and friction; it is never negative.

## Pipes and accumulators

- `Pipe` splits a line into `N` segments (a constant on the block, default 1). Each segment has its share of the friction, the fluid inertia `rho·L/A` and the fluid compressibility. Friction is laminar (Hagen-Poiseuille); a turbulent friction factor `f_t > 0` adds a Darcy-Weisbach loss. More segments resolve pressure waves better but add two states each.
- `Accumulator` stores fluid against a gas precharge `p0` in the volume `V0`. Below `p0` it is empty and only the small dead volume `V_dead` remains. Its state is the fluid volume `V_f`; set its start value to start with a charged accumulator, `V_f = V0·(1 − (p0/p)^(1/n))` for a start pressure `p`.

## Building a circuit

- Put a `Volume` (or another compliance) at the node after a pump. A pump wired straight into a valve makes the node pressure an algebraic loop, and a pump wired straight into a `Pipe` cannot be solved.
- Protect every pump with a `PressureReliefValve` to the tank, as in a real circuit.
- The ends of a `Pipe` take a pressure: connect them to volumes, accumulators, cylinder chambers, valves or sources.
- Start chambers and volumes at a sensible pressure. A closed-centre valve holding a load needs its equilibrium pressures as start values.

## Vacuum gripping (pneumatics)

The **Contact** category has two blocks for suction grippers that use the hydraulic port for air: the pressure is the **gauge** pressure in Pa (negative is vacuum) and the flow is the **free-air** volume flow in m³/s (1 L/min ≈ 1.667e-5 m³/s). A `Volume` with `beta = 101325` (atmospheric pressure) is an isothermal air volume, so a manifold or a hose is a `Volume` too.

| Block | Ports | What it does | Key parameters |
| --- | --- | --- | --- |
| `SuctionCup` | spatial `a` (gripper), `b` (part), `vac`; outputs `T`, `F_lat`, `dp`, `U`, `h`, `sealed`, flows | a bellows cup: holding force `A_eff·dp`, bellows stiffness, lip friction `mu·N`, peeling, seal leak and loss; optional nonlinear bellows (bottoming, vacuum lift stroke, vacuum- and stroke-dependent side stiffness) | `A_eff`, `D_lip`, `k_ax`, `k_lat`, `k_tilt`, `mu`, `V`, `perm`, `A_lip0`; nonlinear: `k_bot`, `s_bot`, `A_fold`, `c_vac`, `c_ext` |
| `VacuumGenerator` | `a`, input `u`; outputs `Q`, `dp` | flow–pressure curve `Q = Q_max·(1 − (dp/dp_max)^n)` (`n = 1` ejector, `n ≈ 3` pump); `u = 0` vents to atmosphere | `dp_max`, `Q_max`, `n`, `G_rel` |

- Mount the cup with two `FixedTransform3DNeutral` blocks: side `a` of each on the cup, side `b` on the gripper body and on the part. The cup axis is the mount frame's −z axis, and the cup's rest length is `L0`. Set the start `rz = -L0` (and the static stretch for a hanging load).
- `U` is the cup utilisation: axial tension, peeling moment and shear as a fraction of the holding capacity `A_eff·dp`. A cup holds while `U < 1`; with a safety factor `S` keep `U ≤ 1/S`.
- When the tension or the moment exceeds the vacuum force, the lip lifts (`h > 0`). The lifted lip opens a leak, the chamber loses its vacuum, and above `h_lost` the `sealed` latch drops to 0 for the rest of the run.
- Air leaks through the part (`perm`, a Darcy permeance: 0 for sealed film, about 4e-7 m/(s·Pa) for cardboard, 2e-6 for porous material) and past the lip (`A_lip0`). The generator must supply this flow: the steady vacuum is where the generator curve meets the leak demand of all cups.
- The bellows can be made nonlinear. The extra terms are off by default, so a cup without them behaves exactly as the linear cup:
  - **Bottoming.** Beyond the compression stroke `s_bot` the folds stack up. The cup stiffens smoothly with the push `F_bot = k_bot·xb·(xb/x_bot)^(n_bot−1)`, where `xb` is the over-stroke. Set `k_bot > 0` to switch this on.
  - **Vacuum lift stroke.** The vacuum on the folded annulus `A_fold` pulls the bellows shut. An unloaded cup contracts by `A_fold·dp/k_ax` (it lifts the part), and a loaded one follows `T = k_ax·ext + A_fold·dp`. The holding capacity `A_eff·dp` does not change.
  - **Stiffness factor.** The lateral and tilt stiffness are multiplied by `kf = (1 + c_vac·dp/p_atm)·exp(−c_ext·ext/L0)`: an evacuated or compressed cup is stiffer sideways, and an extended one is softer.
  - The recorded variables `F_bot`, `xb` and `kf` show these terms.
  - Damping stays a Kelvin damper per direction (`d_ax`, `d_lat`, `d_rot`).
- Use solver **FBDF** for gripper models: the air chambers are very stiff, and the default automatic choice (Tsit5) takes too many steps.
- A cup that starts away from the part (the gripper approaches from above, so the start `rz` is below `-L0`) has its lip gap `h` fall through `h_lost` when the lip lands. FBDF can stop there ("dt was forced below floating point epsilon"); use **Rodas5P** for such models.

The example **suction-gripper** is a six-cup gripper that moves a carton: profiles, gripper yaw and tilt, parcel porosity, generator size and manifold layouts.

The example **fanuc-pick** is a pick and place of a carton by a FANUC LR-10iA/10 with a five-zone gripper (a pneumatic cylinder per zone extends its bellows cup, one ejector per zone). It compares four trajectory families and finds the shortest cycle time that keeps a holding margin, for a carton with a centred or offset centre of mass and for a carton with a loose ball or bottle inside. The arm is kinematic: it follows the plan exactly, and the plan is checked against the robot's datasheet limits.

The example **hydraulic-circuit** (in the Example gallery) is a complete circuit: an electric motor speed drives a fixed-displacement pump with a relief valve and an accumulator, and a 4/3 valve extends and retracts a loaded cylinder.
