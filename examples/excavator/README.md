# excavator — the front of a 20-t excavator digs loam: cylinder linkage with bucket four-bar, load-sensing pump, pre-compensated valves, earthmoving equation

The boom (5.70 m), arm (2.90 m) and bucket (1.50 m, 0.93 m³ heaped) of a 20-t class
crawler excavator on the planar multibond mechanics. The front has the real cylinder linkage,
including the rocker / H-link four-bar of the bucket. A **load-sensing** hydraulic system drives it,
and the bucket teeth cut soil with the **fundamental earthmoving equation** and fill the bucket.

| model | scenario |
| --- | --- |
| `excavator-kinematics` | Stiff servos set the cylinder lengths (no gravity). The bucket tip comes from the linkage and is checked against scipy forward kinematics. |
| `excavator-lift` | The front holds 1.5 t. The boom rings at its hydraulic natural frequency, then lifts through the LS system (3–6 s). |
| `excavator-dig-cycle` | A scripted 16.5 s cycle: penetrate, drag, curl, lift, arm out, dump, return. |
| `excavator-no-ls` | The same cycle on a constant-pressure supply (281 bar), for the energy comparison. |

```
uv run examples/excavator/design/design.py        # parameters and references -> design/design.json
uv run examples/excavator/design/build_model.py   # models, scenes/excavator.sdf, expected.json
uv run examples/run_checks.py --only excavator    # 50 checks
uv run tools/example_docs/build.py --only excavator
```

Docs: `docs/` (project) and `models/<model>.docs/` (per model), source
`tools/example_docs/src/excavator.md`.

## Structure

```
Engine (SpeedSource 1800 rpm) ── Pump (LoadSensingPump) ── Vpump ──┬── Relief ── Tank
                                     ▲ ls                          ├── {Boom,Arm,Bucket}Comp (pre-compensator)
                                     └── Vls (LS line) ── Bleed    │      └─ {C}Vin ── {C}Valve (4/3) ── {C}Cyl (A, B)
                                           ▲ {C}Shuttle (check)    │                   {C}LSEdge ── {C}Vls
                                                                   │      {C}MakeUpA/B (checks from tank)
{C}Cyl.rod ─ rod 1-junction ─ {C}Fric ─ barrel
            └ RackAndPinion (r = 1) ─ {C}Lever (MTF, r = dL/dq from {C}Mount) ─ Joint drive
Bucket:      BucketLever (MTF, r of the rocker) ─ FourBar (MTF, k from Linkage) ─ Joint3 drive
Ground ─ Joint1 ─ Link1 ─ Boom ─ Joint2 ─ Link2 ─ Arm ─ Joint3 ─ Link3 ─ Bucket ─ Soil
Pose chain: JointPose2D / LocalPose2D / ComposePose2D -> pin poses -> {C}Mount, Linkage, Soil, PoseTip
```

The hydraulics are **wired** (connection sets with a common pressure), and every valve sits
between two volumes. So the hydraulic network has no algebraic loop and no causality warning.

### Elements

- **Mechanics.** `GroundPlanar`, `RigidBody2D`, `Revolute2DLimit`, `FixedJoint2D` (the link offsets), `JointPose2D`, `LocalPose2D` and
  `ComposePose2D`. The joint limits are the cylinder end stops.
- **Cylinder drive.** `HydraulicCylinder` (chamber compressibility, areas, stroke), `Friction`
  (Coulomb plus viscous) and `RackAndPinion`. An `MTF` carries the virtual-work coupling
  r = dL/dq to the joint.
- **Hydraulics.**
  - stdlib `LoadSensingPump` (new, see below) on a `SpeedSource`;
  - `Volume`;
  - `PressureCompensatedFlowControl` (the section pre-compensators);
  - `DirectionalValve43` (the main spools and the LS edges);
  - `CheckValve` (the shuttles, the make-up valves, and the LS bleed held open);
  - `PressureReliefValve` and `Tank`.
- **Signals.**
  - `TimeTable` (the operator), `FirstOrder` (the spool lag);
  - `PressureSensor`, `Mux2`/`Mux3`/`Sum`/`Product`/`Abs` (cylinder force, joint torque and power);
  - `Integrator`/`Divide` (the energy meters).

### Custom blocks (`library/`) and why

- **`CylinderMount2D`.** Gives the pin-to-pin length L, the moment arm r = dL/dq, the rod
  extension and the world points of the barrel and rod ends, all from the two pin poses and the
  joint pose. No stdlib element gives a cylinder length from two planar poses, and the length
  must be a kinematic result.
- **`BucketLinkage2D`.** Solves the rocker / H-link four-bar (circle intersection): the rocker
  angle, the pin J, the ratio k = dφ/dq3 and the transmission angle. The four-bar has a closed
  form, so a constrained multibody loop (index-3) is not needed.
- **`SoilCutting2D`.** A nonlinear resistive element on the bucket's planar bond: the
  earthmoving-equation force plus the momentum flux, the bucket fill state, and the weight of
  the carried soil. There is no soil-tool element in the stdlib.

### Core change: `LoadSensingPump` (stdlib, `converters`)

A variable-displacement pump with ports a/b/shaft/ls. Its static regulator holds
p_b − p_ls = `dp_ls` (linear over `dp_reg`). It also has a pressure cut-off `p_cut` and a torque
limiter `T_max`. The losses use the efficiency form of `VariableDisplacementPump`. Its outputs
are xd, P_in and P_out. The block is tested in `julia/BGSim/test/golden/converters/test_LoadSensingPump.jl` and
`test_library.jl`. The editor has its icon, and the manual describes it on the hydraulics page.

## Parameters

| quantity | value | source |
| --- | --- | --- |
| boom + arm + bucket mass | 3606 kg (1650 / 1000 / 956) | total: Jin et al. (2024); split and CoMs: assumed |
| inertia of the front about the boom foot | 76 300 kg·m² (reference pose, no payload) | Jin et al. give 79 720 kg·m² (comparison only) |
| boom cylinders | 2 × bore 120 / rod 85 mm (11 310 / 5 635 mm² each) | Jin et al. (2024) |
| arm, bucket cylinder | 140/100, 120/85 mm | assumed (typical 20-t sizes) |
| link lengths, pin layout | boom 5.70, arm 2.90, bucket 1.50 m | assumed, typical 20-t (see `design/exc_geom.py`) |
| pump | 220 cm³/rev, 1800 rpm, η_v 0.95, η_m 0.92 | assumed |
| LS margin, regulation, cut-off, power limit | 25 bar, 2 bar, 320 bar, 100 kW | assumed (the brief: 20–30 bar) |
| main relief | 343 bar | assumed |
| section flows at full stick | boom 300, arm 280, bucket 200 l/min; compensator 10 bar | assumed |
| bulk modulus (oil and hoses) | 1.2 GPa | assumed |
| soil (loam) | γ = 18 kN/m³, c = 15 kPa, φ = 30°, δ = 20°, ρ = 1835 kg/m³, swell 1.25 | assumed, textbook ranges (McKyes 1985) |
| earthmoving factors | N_γ = 1.436, N_c = 1.998 (rake 45°) | computed, Wagner (2025) eq. 15 with α = 0 |
| payload (lift) | 1.5 t | 0.93 m³ of loose soil |

## Reference values (`expected.json`, all independent of bg-sim)

| check | bond graph | reference |
| --- | --- | --- |
| bucket tip at 6.5 s / 12.5 s | (7.383354, 2.779696) / (2.978149, −1.877105) m | scipy FK of the cylinder lengths, < 4e-7 m |
| joints, lengths, four-bar k, bucket r | | within 1e-7 |
| static cylinder forces with 1.5 t (boom / arm / bucket) | 274.4 / 10.6 / 81.0 kN | moment balance 275.2 / 10.4 / 81.1 kN |
| boom hydraulic mode | 2.483 Hz | 2.489 Hz (3-DOF eig); 1-DOF formula 2.596 Hz |
| LS margin: stand-by / lift / dig cycle | 27.0 / 26.2 / 22.6–27.0 bar | 25 + 2 bar |
| boom section flow at joystick 0.5 | 2.416e-3 m³/s | 2.5e-3 m³/s |
| relief flow, dig cycle | < 2e-9 m³/s | closed |
| bucket fill after curl / after dump | 0.753 / 0.004 | > 0.6 / < 0.05 |
| cycle energy at the engine, LS / no-LS | 0.565 / 1.524 MJ | < 0.7 / > 1.2 MJ |
| energy ledger (all hydraulic models) | closes (rel. 1e-17) | Tellegen |
| diagnostics | no W201/W202/W206, no errors | |

**Solver:** FBDF, reltol = abstol = 1e-6 (kinematics: 1e-8 / 1e-9), 100 points/s. **Run time**
(desktop PC, warm / first run including compilation): kinematics 1.6 / 15 s, lift 4.8 / 9 s,
dig cycle 4.5 / 20–30 s, no-LS about 23 s on the first run.

## What to try

- **Lift.** Raise the payload: the boom pressure rises, but the lift speed stays the same
  (pressure compensation). Lower the bulk modulus: the ringing frequency falls with √β.
- **Dig cycle.** Raise the soil cohesion (stiff clay); change the joystick scale; change the LS
  margin and watch the engine energy.
- Compare `Ein` (engine energy) in `excavator-dig-cycle` and `excavator-no-ls`.

## Simplifications

- **Cylinder coupling.** The cylinder drives its joint through a virtual-work MTF (r = dL/dq).
  The joint torques and the motion are exact; the pin reaction forces are not modelled.
- **Masses.** The rocker and the H-link are massless. The carried soil has weight but no inertia.
  In the lift model the payload is folded into the bucket body.
- **Boom lowering.** The boom lowers on its meter-out edge, so the speed depends on the load
  (no regeneration, no load-holding valve).
- **LS network.** The shuttle network is check valves into one LS line with a bleed orifice. The
  pump regulator is static (no swash-plate dynamics).
- **Pump friction.** The pump friction torque grows with the pressure even at zero stroke (the
  stdlib pump law). This is why the constant-pressure supply idles at about 25 kW (LS: 1.6 kW).
- **Machine.** The swing is fixed and the ground is flat. In the kinematics model the tip passes
  below the ground visual (there is no soil in that model).
- **Efficiency figure.** "Cylinder work / engine energy" is the net cylinder work over the
  engine shaft energy.

## Sources and licences

- **Jin et al. (2024).** Jin Z, Gong M, Zhao D, Zhang Y, Liu W, Zhu J, Su B. "MPC motion control
  of boom descending of unmanned excavator based on regenerative valve." *Heliyon*
  10(9):e29915, 2024. doi:10.1016/j.heliyon.2024.e29915. Licence: CC BY-NC-ND 4.0. Used, as
  facts only: the 3606 kg front mass, the boom cylinder areas, and the boom-foot inertia as a
  comparison.
- **Wagner (2025).** W. J. Wagner, "Deriving the Fundamental Equation of Earthmoving and
  Configuring Vortex Studio Earthmoving Simulation", arXiv:2505.19330, 2025. Used: the
  flat-ground form of the equation (eq. 15).
- **Earthmoving equation.** A. R. Reece, "The fundamental equation of earth-moving mechanics",
  *Proc. Inst. Mech. Eng.* 179(3F), 1964; E. McKyes, *Soil Cutting and Tillage*, Elsevier, 1985.
  Used: the form F = w(γd²N_γ + c d N_c) and the soil parameter ranges.
- **Pump law.** The pressure-compensated pump law follows the documented behaviour of the
  MathWorks Simscape Fluids pressure-compensated pump block. bg-sim's implementation is its own.
- All other numbers are assumed and marked as such in `design/design.py`. Everything in this
  folder is written for bg-sim; no third-party geometry or meshes are used.
