# Mechanical and electrical components

Beyond the basic elements (inertia, spring, damper, resistor, capacitor, …) the **Rotation** and **Electrical** categories of the library hold the common drive-train and circuit components below. Select a block and press `F1`, or click its help button in the library, for the full parameter list.

Power is positive into every port. A rotation port carries torque `e` and angular velocity `f`, an electrical port voltage `e` and current `f`.

## Rotation

| Block | Ports | What it does | Key parameters |
| --- | --- | --- | --- |
| `RotationalHardStop` | `a`, `b` | free between the limits, a stiff spring-damper outside them | `lower`, `upper` (rad, angle `a` minus `b`), `k`, `d` |
| `Clutch` | `a`, `b`, input `f_n` | friction torque proportional to the normal force `f_n` (N) | `mu_s`, `mu_c`, `r_eff`, `n_faces`, `w_s`, `w_eps` |
| `Brake` | `a`, input `f_n` | the clutch with its second side fixed to the housing | as `Clutch` |
| `PlanetaryGear` | `sun`, `ring`, `carrier` | ideal planetary set: `w_sun + ratio·w_ring = (1 + ratio)·w_carrier` | `ratio` = ring teeth / sun teeth |
| `BeltDrive` | `a`, `b` | two pulleys on a compliant belt without slip | `r_a`, `r_b` (m), `k` (N/m), `d` (N·s/m) |
| `WormGear` | `a` (worm), `b` (wheel) | gear with friction: `a.f = n·b.f` | `n`, `eta`, `eta_back`, `w_eps` |

Notes:

- **Clutch and brake.** A negative `f_n` counts as zero (open). Sticking is handled as in `RotationalFriction`: with `w_eps > 0` the friction direction is `tanh(w/w_eps)`, so a locked clutch creeps at a speed of the order of `w_eps`. `w_eps = 0` switches exactly on the sign of the slip speed. With `mu_s > mu_c` the friction coefficient falls from `mu_s` to `mu_c` over the Stribeck speed `w_s`.
- **Planetary gear.** With the ring held, the sun drives the carrier at `1/(1 + ratio)` of its speed. Connect inertias to all three shafts if you like: the solver handles the kinematic coupling.
- **Worm gear.** `eta` is the efficiency while the worm drives the wheel, `eta_back` while the wheel drives the worm. With `eta_back ≤ 0` the gear is **self-locking**: a load on the wheel cannot turn the worm (it creeps at most at the smoothing speed `w_eps`).
- **Belt drive.** The belt stretch `x` is the state; in steady state the belt speeds match, `r_a·w_a = r_b·w_b`. The belt does not slip and does not go slack.

## Contact

The **Contact** category holds compliant contacts for 3D rigid bodies: a Hunt-Crossley normal force (`k·x·sqrt(x/xref)·(1 + c·xdot)`, it never pulls) and regularised Coulomb friction. Mount a contact on a body through a `FixedTransform3DNeutral` (contact on side `a`, body on side `b`).

| Block | Ports | What it does | Key parameters |
| --- | --- | --- | --- |
| `ContactPoint` | `p` (spatial), inputs `g`, `o`, `fr` (from a `ContactSurface`) | a point of a body against a fixed plane | `k`, `xref`, `c`, `mu`, `vs` |
| `MovingPlaneContact` | `p` (spatial), `j` (translation), inputs `g`, `pc`, `vc`, `xs` | a sphere of a body against a finite rectangular face that moves: a carrier translates it (`pc`, `vc`) and the port `j` slides it along an axis, for a gripper jaw pad or a pusher | `r`, face `ox..oz`, normal `nx..nz`, tangent `tx..tz`, slide axis `ax..az`, half-widths `w1`, `w2`, `we`, `k`, `xref`, `c`, `mu`, `vs` |

Notes:

- **Moving face.** The face origin is `pc + o + a·xs`: connect the jaw position (for example a `PositionSensor` on the jaw) to `xs`. The face pushes back on the jaw with `j.e = F·a`, and `Pc` is the power the carrier puts in. Outside the half-widths the normal force fades out over `we`, so a part can slide off the face and fall.
- **Holding.** Below the friction limit a held part creeps at `s = vs·atanh(F_t/(mu·f_n))`; the output `util = F_t/(mu·f_n)` is the share of the friction limit in use (1 = slipping). `examples/gripper` sizes a parallel gripper with it.

## Electrical

| Block | Ports | What it does | Key parameters |
| --- | --- | --- | --- |
| `OpAmp` | `in_p`, `in_n`, `out` | operational amplifier, output referred to ground | constant `ideal`, `A`, `T_o`, `V_pos`, `V_neg` |
| `VCVS` | `p1`, `n1`, `p2`, `n2` | voltage-controlled voltage source, `v2 = gain·v1` | `gain` |
| `VCCS` | `p1`, `n1`, `p2`, `n2` | voltage-controlled current source, current `transconductance·v1` from `p2` through the source to `n2` | `transconductance` (1/Ohm) |
| `CCVS` | `p1`, `n1`, `p2`, `n2` | current-controlled voltage source, `v2 = transresistance·i1` | `transresistance` (Ohm) |
| `CCCS` | `p1`, `n1`, `p2`, `n2` | current-controlled current source, current `gain·i1` | `gain` |
| `MutualInductance` | `p1`, `n1`, `p2`, `n2` | two coupled coils, `M = k·sqrt(L1·L2)` | `L1`, `L2` (H), `k` (below 1) |
| `Battery` | `p`, `n` | open-circuit voltage over the state of charge, series `R0` and one `R1`‖`C1` pair | `capacity` (A·h), `soc_table`, `ocv_table`, `R0`, `R1`, `C1` |
| `MOSFET` | `d`, `s`, input `gate` | ideal switch with on-resistance and a body diode | `R_on`, `G_off`, `V_f`, `R_d` |
| `IGBT` | `c`, `e`, input `gate` | ideal one-way switch with a knee voltage and a freewheeling diode | `R_on`, `V_ce0`, `G_off`, `V_f`, `R_d` |

Notes:

- **Op-amp.** No current flows into the inputs. With the constant `ideal = 1` (the default) the op-amp holds both inputs at the same voltage; this only works with negative feedback, and the output is not limited. With `ideal = 0` the output follows `A·(v_p − v_n)`, limited to `V_neg … V_pos`, through a first-order lag `T_o` (`A/T_o` is the gain-bandwidth product in rad/s), so the op-amp can saturate and also works as a comparator. The output current comes from the (implicit) supply.
- **Controlled sources.** The voltage-controlled sources draw no current at `p1`/`n1`; the current-controlled ones are a short circuit there that measures the current `i1` from `p1` to `n1`.
- **Mutual inductance.** The two windings are dotted at `p1` and `p2`. The winding currents `i1` and `i2` are the states; set their start values for an initial current. Use `IdealTransformer` for perfect coupling (`k = 1`).
- **Battery.** `soc` is the state of charge (1 full, 0 empty); its start value is the initial charge. Charging current (into `p`) raises it. The OCV is interpolated linearly in the table and held at the edge values outside it. The constant `N` sets the table length.
- **MOSFET and IGBT.** The Boolean `gate` comes from a logic block, for example a `Compare` on a PWM carrier. The MOSFET channel conducts both ways while on; the IGBT only from `c` to `e` above `V_ce0`. Both have an antiparallel diode (forward voltage `V_f`, resistance `R_d`). Every switching instant is located exactly in a simulation; an [export](page:export) checks the switching once per step.
- **Losses.** Clutch, brake, worm gear, battery and the switches lose power as heat. There is no thermal port yet; the heat only shows up as the power balance of the block.

## Electromagnet

`Electromagnet` (in **Converters and sensors**) is a lifting magnet or maglev coil: a variable-reluctance actuator that pulls an iron armature across an air gap. It has a coil (Electrical `p`, `n`) and a gap (Translation `a` for the magnet body, `b` for the armature).

| Parameter | Unit | Meaning |
| --- | --- | --- |
| `alpha` | H·m | force constant: attraction `F = alpha·i²/(h + h0)²` |
| `L_inf` | H | coil inductance with the armature far away |
| `h0` | m | gap offset; `0` is the pure inverse-square law, a few mm keeps the force finite at contact |

The gap `h` and the coil current `i` are the states: set their start values (the armature position and the initial current). `h` grows when the armature moves away from the magnet, `dh/dt = b.f − a.f`.

How it works: the block stores magnetic energy `W = ½·L(h)·i²` with `L(h) = L_inf + 2·alpha/(h + h0)`, and both port laws come from that one energy. The coil sees `v = d(L(h)·i)/dt`, including the voltage induced while the armature moves; the gap gets the attraction `F = alpha·i²/(h + h0)²` (`b.e = F`, `a.e = −F`). So the power into the block is exactly the change of its stored energy: it neither creates nor loses energy (put the coil resistance in a separate resistor or bond graph `R`). The variables `W`, `F`, `L`, `lambda` (flux linkage), `P_el` and `P_mech` (power into the coil and into the gap) can be plotted.

Use it in a circuit and a translation diagram, or in a bond graph: bond the coil to an electrical 1-junction and the armature to the mass's 1-junction. The **maglev** example shows it levitating a steel ball with a cascade controller.

## Joint hard stops (2D and 3D)

The joints `Revolute3D`, `Prismatic3D` (Multibody 3D), `Revolute2D` and `Prismatic2D` (Multibody 2D) can stop at a limit of their coordinate `q`, like the mechanical end stops of a robot axis.

| Setting | Kind | Default | Meaning |
| --- | --- | --- | --- |
| `q_min`, `q_max` | constant | `-Inf`, `Inf` | the limits (rad for a revolute joint, m for a prismatic one); `-Inf`/`Inf` means no stop |
| `k_stop` | parameter | 1e5 N·m/rad, 1e6 N/m | stiffness of the stop |
| `d_stop` | parameter | 100 N·m·s/rad, 1000 N·s/m | damping of the stop, only beyond the limit |
| `w_stop` | parameter | 1e-5 rad, 1e-6 m | width over which the stop sets in |

- **Set the limits** in the inspector's constants, for example `q_max` = `120*deg`. They are constants: changing one recompiles the model.
- **Behaviour.** Between the limits the joint is free. Beyond a limit a stiff spring-damper pushes the joint back, and the output `tau_stop` (`f_stop` on a prismatic joint) is that torque or force. The joint goes a little past the limit, about the load divided by `k_stop`. The stop sets in smoothly over `w_stop`, without an event, so a joint that rests on its stop does not slow the solver down.
- **Choosing the stiffness.** A stiffer stop stays closer to the limit but makes the model stiffer to solve. For a damped bounce choose `d_stop` near `2·sqrt(k_stop·J)` times the damping ratio, with `J` the inertia the joint moves.
- **Without limits** the joint is exactly the joint it was before: the stop is left out of the equations.

## Wheels and flywheels (3D)

Two blocks of the 3D mechanics categories model a wheel that rolls on the ground and a fast flywheel. The **gyrover** example uses both.

| Block | Category | Ports | What it does | Key parameters |
| --- | --- | --- | --- | --- |
| `RollingDisk` | Contact | `p` (spatial), inputs `g`, `o`, `fr` | rolling contact of a wheel on a `ContactSurface` plane: the contact point is the lowest rim point at every instant | `radius`, `crown`, `k`, `xref`, `c`, `mu`, `vs`, `bsp` |
| `Rotor3D` | Spatial mechanics | `p` (spatial), `drive` (rotation) | a rotor spinning about the z axis of the body that carries it | `Ja` |

- **Mounting.** Bond the wheel body's port `p` straight to the block's `p`, with the body frame at the wheel centre and the axle along body z. Feed `RollingDisk` the body pose (`g`) and the plane (`o`, `fr` from a `ContactSurface`). Put the rotor's mass and transverse inertia into the carrier body; only the axial inertia `Ja` belongs to `Rotor3D`.
- **Rolling.** The normal force is the smooth Hertz/Hunt-Crossley law of `ContactPoint`. Friction is isotropic regularised Coulomb friction on the slip of the rim point: a wheel rolling under a side force `F` creeps at about `vs F / (mu f_n)`. The block outputs `f_n`, `s_lon`/`s_lat` (slip), `f_lon`/`f_lat`, the contact point, `camber`, the spring energy `Ec` and the dissipated power `Pd`.
- **Rotor.** Only the axial momentum `h` is a state, so a flywheel at 15 000 rpm costs no more than one at rest. The motor between carrier and rotor bonds to `drive`, and its reaction acts on the carrier. `w_rel`, `w_abs`, `H` and `Ek` are outputs.

## Vehicle tyres and terrain (3D)

Two more contact blocks build road vehicles. The **cars** example (a race car and an off-road buggy) uses both.

| Block | Category | Ports | What it does | Key parameters |
| --- | --- | --- | --- | --- |
| `Tyre` | Contact | `p` (spatial, the wheel carrier), `spin` (rotation), inputs `g`, `o`, `fr`, `mus` | a pneumatic tyre: radial spring at the lowest rim point, Magic Formula forces for longitudinal and lateral slip, combined on the friction ellipse, rolling resistance | `R0`, `kz`, `cz`, `Fz0`, `mux`, `muy`, `dmu`, `Kx`, `Cx`, `Ex`, `Ky`, `Ky2`, `Cy`, `Ey`, `cx`, `cy`, `dx`, `dy`, `frr` |
| `TerrainSurface` | Contact | inputs `g`; outputs `o`, `fr`, `hq`, `slope` | hills as a formula, `h(x, y) = h0 + sx·x + sy·y + Σ a·cos(kx·x + ky·y + ph)`: gives the ground plane under a wheel to a `Tyre` (or any contact block) | `h0`, `sx`, `sy`, `a`, `kx`, `ky`, `ph` (constant `N` components) |

- **Mounting.** The carrier is the wheel hub that does not spin: a `RigidBody3D` with the wheel's mass and transverse inertia, frame at the wheel centre, axle along body z. Bond its port to the tyre's `p` and to a `Rotor3D` (the wheel's spin inertia). Put the rotor's `drive`, the tyre's `spin`, a brake and a drive shaft on one 1-junction: the wheel's spin.
- **Forces.** `Fz` is the radial spring and damper on the deflection. `Fx` and `Fy` follow the Magic Formula of the slips `kappa` and `alpha` (the peak is `mux·Fz` and `muy·Fz`, a little lower at high load through `dmu`), and act through a small deflection of the contact patch. So a parked car stays parked on a slope, and nothing goes stiff at low speed. `mus` scales the friction, for example 1 on asphalt and 0.6 on grass.
- **Outputs.** `Fz`, `Fx`, `Fy`, `kappa`, `alpha`, the forward speed `Vx`, the wheel speed `omega`, the deflection `delta`, the contact point `xc`, `yc`, `zc`, the force in world axes `Fwx`..`Fwz`, `camber`, the stored energy `Ec` and the dissipated power `Pd`.
- **Terrain.** Feed `TerrainSurface` the wheel carrier pose; it returns the tangent plane below the wheel centre. Use one per wheel. The same formula can draw the ground in a 3D view or a simulator, so what you see is what the tyres drive on.
- **Not modelled.** The tyre has no aligning moment and no camber thrust.
