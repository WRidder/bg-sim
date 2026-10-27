# Multibond graph elements for 2D/3D robotics — implementation guide

## Purpose and scope

This extension adds vector-valued (multibond) ports and a set of rigid-body, joint, actuator and contact elements so the existing scalar bond-graph library can model planar and spatial multibody systems: serial robot arms, reaction-wheel balancing bodies, and hybrid contact sequences. The design follows the port-Hamiltonian / screw-theory formulation (Stramigioli; Duindam & Stramigioli), in which twists are elements of se(3), wrenches of se(3)\*, frame changes are adjoint transformers and Coriolis terms are a modulated gyrator.

Design principles the implementation must keep:

- A multibond is an ordinary bond whose effort and flow are vectors; every scalar element already in the library (Se, Sf, I, C, R, TF, GY, 0, 1) gets a vector counterpart with the same causality rules and the same power accounting.
- No opaque elements. Every higher-level thing in this guide (rigid body, joint, drive, contact, switched pivot) is a subsystem built only from the standard elements and junctions, using the library's existing subsystem mechanism. Opening a subsystem shows a plain bond graph: Se, Sf, I, C, R, TF/MTF, GY/MGY, 0, 1, signal integrators and taps, nothing else. Solvers and evaluators (section 8) operate on that flat graph and never on a subsystem as a unit.
- Every element is power-continuous by construction: transformers and gyrators use a matrix and its transpose, never two independently coded directions.
- All quantities are expressed in body-fixed frames so inertia matrices are constant; configuration dependence lives only in modulated transformers and in gravity.
- Frames are first-class: every multibond port carries a frame tag and connecting two ports with different frames is a compile-time error unless an adjoint transformer sits between them.
- The 2D (planar) set is the 3D set with dimension 3 instead of 6. Implement both over a generic dimension parameter rather than as two code paths.

Out of scope for this iteration: flexible bodies, non-holonomic wheels, finite-element contact, and a general DAE index-reduction engine. Closed loops and rigid contact are handled through compliance or through the articulated-body evaluation described in section 8.

## Core abstractions

The one new primitive is a multibond port of dimension `D` (`D` = 3 planar, `D` = 6 spatial) carrying a flow vector (twist) and an effort vector (wrench), with power equal to their dot product in the chosen coordinates.

| Concept | Planar (D = 3) | Spatial (D = 6) |
| --- | --- | --- |
| Twist `V` (flow) | `[omega_z, v_x, v_y]` | `[omega (3), v (3)]` |
| Wrench `W` (effort) | `[m_z, f_x, f_y]` | `[m (3), f (3)]` |
| Power | `W^T V` | `W^T V` |
| Pose `g` | `(theta, p)` in SE(2) | `(R, p)` in SE(3) |
| Adjoint `Ad_g` | 3x3 | 6x6 |
| Lie bracket `ad_V` | 3x3 | 6x6 |

Ordering of angular before linear is a convention; pick one and enforce it in a single `Twist`/`Wrench` type. Mixing orderings is the most common bug in this kind of library.

Required core types and operations:

- `MultiPort<D>`: effort and flow vectors, a frame id, causality flag (effort-in or flow-in), same interface as the scalar port.
- `Frame`: identifier plus, at runtime, the pose relative to its parent frame. Ports carry a frame; junctions require all attached ports to share one frame.
- `Pose<D>`: SE(2) or SE(3) element with `compose`, `inverse`, `Ad()` (returns the D x D adjoint), `exp(twist * dt)` for integration, and `log`. Spatial rotation stored as a unit quaternion or rotation matrix; never Euler angles.
- `ad(V)`: the D x D Lie-bracket matrix of a twist. Spatial: `[[omega]x, 0; [v]x, [omega]x]`. Planar: `[[0, 0, 0], [v_y, 0, -omega], [-v_x, omega, 0]]`.
- `Screw<D>`: a unit twist (axis, point, pitch) convertible to a D-vector; a joint basis `S` is a D x n matrix of screws.
- Vector junctions `0<D>` and `1<D>`: identical semantics to scalar junctions, applied componentwise. A `1<D>` requires all ports in one frame.

Subsystems reuse the library's existing subsystem feature unchanged, extended only so that an external port of a subsystem can be a `MultiPort<D>` with a frame tag, and so that a subsystem can expose signal inputs and outputs. A subsystem has no behaviour of its own; flattening the model before causality assignment must yield exactly the standard elements listed inside each subsystem in sections 3 to 7.

Causality on a vector port is assigned as a whole: a port is effort-in or flow-in for all D components. Mixed-causality ports are not supported; if a model needs them, insert a transformer that splits the port (see section 5, joint `S` and its complement).

## Planar (2D) element set

The planar set is the proving ground: every element below has a direct 3D counterpart in section 4, and the tests in section 10 are first written here. Twist is `V = [omega, v_x, v_y]`, wrench is `W = [m, f_x, f_y]`, pose is `(theta, p)`.

| Element | Bond-graph type | Ports | Parameters / state | Constitutive relation |
| --- | --- | --- | --- | --- |
| `RigidBody2D` | `1<3>` + `I` + `MGY` + `Se` | 1..k multibond ports, each in a named attachment frame | mass `m`, inertia `J` about CoM, CoM offset `c`, attachment poses; state: momentum `P` (3) | \`M = \[\[J + m |
| `FixedTransform2D` | `TF` | 2 multibond ports | constant pose `g` | `V_out = Ad_g^-1 V_in`, `W_in = Ad_g^-T W_out` |
| `JointTransform2D` | `MTF` | 2 multibond ports + 1 signal input | pose `g(q)` from the joint integrator | same as above with `g` recomputed each step |
| `Revolute2D` | `MTF` + `1<1>` | 1 multibond port, 1 scalar port, integrator | `S = [1, 0, 0]^T`, axis point `r`; state `q` | `V_rel = S qdot`, `tau = S^T W` |
| `Prismatic2D` | `MTF` + `1<1>` | same | `S = [0, cos a, sin a]^T`; state `q` | same |
| `Free2D` | identity | 2 multibond ports | `S = I_3`; state `g` | floating base, no constraint |
| `Ground2D` | `Sf` | 1 multibond port | none | `V = 0` |
| `ExternalWrench2D` | `Se` | 1 multibond port | wrench in a named frame | constant or signal-driven |

Notes for the implementer:

- `RigidBody2D` is a subsystem; opening it shows a `1<3>` junction with an `I`-field, a modulated gyrator and a gravity source attached, plus one `FixedTransform2D` per attachment port. Expose attachment frames by name so a joint can be connected to "link.distal".
- The planar gyrator term reduces to `[0, -m omega v_y + ..., ...]`; implement it generically as `ad(V)^T P` and let the 2D case fall out, do not hand-code the scalar expansions.
- The joint integrator (`q = integral of qdot`) is a signal-domain integrator on the scalar junction's flow; it feeds the pose into `JointTransform2D` as a signal (activated bond, zero power).
- For a planar robot the whole chain is `Ground2D -> Revolute2D -> RigidBody2D -> Revolute2D -> RigidBody2D -> ...`, each joint connecting the previous body's distal frame to the next body's proximal frame.

## Spatial (3D) element set

The spatial set is the planar set with `D` = 6 and the full SE(3) machinery. Twist `V = [omega, v]`, wrench `W = [m, f]`, pose `g = (R, p)`, all in the body frame.

| Element | Type | Parameters / state | Constitutive relation |
| --- | --- | --- | --- |
| `RigidBody3D` | `1<6>` + `I` + `MGY` + `Se` | mass `m`, inertia `J_c` about CoM, CoM offset `c`, attachment poses; state: momentum `P` (6) | `M = [[J_c + m [c]x [c]x^T, m [c]x], [m [c]x^T, m I_3]]`; `W_I = dP/dt`, `V = M^-1 P`; `W_gy = ad(V)^T P`; `W_g = Ad_g^-T [0, m g_0]` |
| `FixedTransform3D` | `TF` | constant `g = (R, p)` | `Ad_g = [[R, 0], [[p]x R, R]]`; `V_out = Ad_g^-1 V_in`, `W_in = Ad_g^-T W_out` |
| `JointTransform3D` | `MTF` | `g(q)` from the joint | same, recomputed each step |
| `EulerGyrator` | `MGY` | modulated by the junction's own flow | `W = ad(V)^T P` with `ad(V) = [[[omega]x, 0], [[v]x, [omega]x]]` |
| `Gravity3D` | modulated `Se` | `g_0`, body absolute pose | `W_g = Ad_g^-T [0, m g_0]` |
| `Ground3D` | `Sf` | none | `V = 0` |
| `ExternalWrench3D` | `Se` | wrench in a named frame | constant or signal-driven |

The inertia matrix `M` is constant in the body frame and must be symmetric positive definite; validate at construction. The gyrator is power-neutral, `V^T ad(V)^T P = 0`, and the test suite checks this numerically (section 10).

Pose integration: `g_{k+1} = g_k * exp(V dt)` on the group, with `exp` on SE(3) implemented in closed form (Rodrigues). The body's absolute pose is needed only for gravity and for output; the chain kinematics use the joint poses `g(q)`. For a fixed-base chain the absolute pose is the composed product of joint and fixed transforms and need not be integrated separately. For a floating or pivoting body it is a state and is integrated on the group; store it as a quaternion plus translation and renormalise after each step.

Frame bookkeeping is the main source of errors. Each `RigidBody3D` owns one body frame (at the CoM or at a convenient attachment point; the inertia matrix above handles either) and any number of named attachment frames connected through `FixedTransform3D`. A joint connects two attachment frames of two different bodies and owns the `JointTransform3D` between them.

## Joint elements

A joint is a subsystem parameterised by its screw basis `S` (D x n), so adding a joint type means adding a basis, not code. Opening the subsystem shows exactly these standard elements: a `0<D>` junction on the parent side (twist addition); an `MTF: Ad_{g(q)}` between the parent-side and child-side multibond ports, modulated by the signal `q`; an `MTF: S` between the `0<D>` junction and an n-dimensional `1<n>` junction (rates `qdot`, torques `tau`); a signal integrator from the `1<n>` flow giving `q`, which feeds the `MTF: Ad_{g(q)}` modulation and the subsystem's `q` output; and, when enabled, the optional `R`, `C` and limit elements listed below. The subsystem's external ports are two multibond ports (parent, child), one n-dimensional power port for the actuator, and signal outputs `q`, `qdot`.

Constitutive relations, in the joint frame fixed to the parent body:

- Flow: `V_child = Ad_{g(q)}^-1 V_parent + S qdot`
- Effort: `tau = S^T W`, `W_parent = Ad_{g(q)}^-T W_child`
- Pose: `g(q) = exp(S_1 q_1) exp(S_2 q_2) ...` (product of exponentials over the basis columns)

The twist addition is a `0<D>` junction (common wrench, flows sum). It is visible inside the `Joint` subsystem like every other element.

| Joint | n | Spatial `S` (columns) | Planar `S` | Notes |
| --- | --- | --- | --- | --- |
| Revolute | 1 | `[a; r x a]` for axis `a` through point `r` | `[1, r_y, -r_x]^T` | `q` wraps modulo 2 pi; keep raw `q` for integration |
| Prismatic | 1 | `[0; a]` | `[0, a_x, a_y]^T` |  |
| Helical | 1 | `[a; r x a + h a]` with pitch `h` | n/a |  |
| Cylindrical | 2 | revolute + prismatic on the same axis | n/a |  |
| Universal | 2 | two revolute columns, second axis rotated by first `q` | n/a | basis is `q`-dependent; use the product-of-exponentials pose |
| Spherical | 3 | `[I_3; 0]` | n/a | store pose as a quaternion, not three angles |
| Planar | 3 | `[e_z; 0], [0; e_x], [0; e_y]` | `I_3` |  |
| Free (floating) | 6 | `I_6` | `I_3` | base of a floating body; `q` is a pose on the group |

Compliance option: every joint takes an optional stiffness `k` and damping `b` on each of its n axes. When set, the joint inserts a `0<n>` junction between the actuator-side rate and the link-side rate with `C: 1/k` and `R: b` on it. The C state is the deflection `delta`, effort `k delta`. This is the mechanism that gives the model integral causality (section 8); make it a per-joint switch, not a global one, because the pivot joint of a balancing body should be rigid while arm joints are usually compliant.

Friction: an `R` on the joint `1<n>` junction. Provide viscous (`tau = b qdot`) and a regularised Coulomb/Stribeck option (`tau = f_c tanh(qdot / v_eps) + b qdot`) so the model stays smooth for implicit solvers.

Limits: an optional one-sided stiff `C` + `R` that engages when `q` leaves `[q_min, q_max]`; same unilateral primitive as contact in section 7.

## Actuator and drive elements

Actuators are scalar bond-graph chains that attach to the joint's `1<n>` junction (one chain per axis), so they are built almost entirely from elements the library already has. Each drive is a subsystem whose interior is the scalar chain below; the only new pieces are the subsystem definitions and the signal interface.

`ElectricDrive` (per axis), as a chain from supply to joint:

1. `Se: u` supply voltage, driven by a signal.
2. `1` junction (current `i`) with `R: R_w` winding resistance and `I: L` inductance (state: flux `L i`).
3. `GY: k_t` motor: `tau_m = k_t i`, `e_back = k_t omega_m`. One constant; the gyrator guarantees `k_t = k_e` in SI units.
4. `1` junction (rotor rate `omega_m`) with `I: J_m` rotor inertia and `R: b_m` bearing loss.
5. `TF: 1/N` gearbox: `qdot_out = omega_m / N`, `tau_out = N tau_m`; optional `R` for gear loss.
6. The joint's compliance `0` junction with `C: 1/k`, `R: b` (section 5), then the joint `1<n>` junction.

Provide a `CurrentControlledDrive` variant that deletes steps 1-2 and replaces the gyrator with a modulated `Se: tau_m = k_t i_cmd` on the rotor junction. This drops the fast electrical eigenvalue and matches drives that expose a torque interface. The reflected rotor inertia `N^2 J_m` usually dominates the link inertia on high-ratio joints, so step 4 must not be omitted.

Other drive types, as further subsystems over existing scalar elements:

| Drive | Chain | New element |
| --- | --- | --- |
| Series-elastic actuator | `ElectricDrive` with a low `k` and a deflection sensor | none; sensor is a signal tap on the `C` state |
| Hydraulic cylinder | `Se: p -> 0 (pressure) -> TF: A (piston area) -> prismatic 1` with `C` for compressibility and `R` for the valve | `R` with a signal-modulated orifice coefficient |
| Cable / belt | `TF: r` (pulley radius) with a one-sided `C` | unilateral `C` (section 7) |
| Reaction wheel | `ElectricDrive` on a revolute joint whose child is a `RigidBody` with only axial inertia | none |

Signal interface: controllers connect through activated bonds that carry a value and zero power. The library needs signal taps on any junction flow or effort and on any `C`/`I` state, plus signal inputs on `Se`, `Sf`, the modulated `R` coefficient and the modulation of `MTF`/`MGY`. A controller is a separate block that reads taps and writes inputs each step; it is not a bond-graph element. Verify in tests that the sum of power over all power bonds is accounted for by storage change plus dissipation plus sources, with the signal bonds contributing nothing.

## Constraints, contact and hybrid modes

Four constraint situations occur in the target setups; the library needs one primitive for each.

**Ground / fixed base.** `Ground` is an `Sf: 0` on a multibond port. Combined with a joint it forms a pivot: `Ground -> Joint(S_pivot) -> RigidBody`. For a body balancing on a corner `S_pivot` is spherical; on an edge, revolute along the edge; resting on a face, no joint at all (the body is simply absent from the dynamics or clamped).

**Closed kinematic loops.** A loop-closing joint connects two bodies that are already connected through the tree. Rigid closure forces derivative causality on at least one body (section 8). Default implementation: the loop-closing joint is always compliant (section 5 compliance option), which keeps causality integral and adds one stiff mode per closed loop. Rigid closure through Lagrange multipliers is a later extension; reserve the interface (a `Constraint` element with a D x m basis and an effort state) but do not implement it in this iteration.

**Unilateral contact.** `ContactPoint` is a subsystem attached to a body port and referencing a `ContactSurface` (initially: a plane in the world frame). Inside: a `TF: Ad` from the body frame to the contact-point frame; an `MTF: n` (D x 1, the surface normal expressed in that frame, modulated by the body pose) feeding a scalar `1` junction for the normal direction, carrying a nonlinear one-sided `C` (state: penetration `d`, effort `max(0, k_c d^p)`) and a nonlinear `R` (effort `lambda k_c d^p ddot`, the Hunt-Crossley damping, zero when `d <= 0`); and an `MTF: T` (D x 2, the tangent basis) feeding a `1<2>` junction with a regularised Coulomb `R` (effort `-mu f_n tanh(v_t / v_eps)`, modulated by the normal force signal). The nonlinear `C` and `R` are ordinary library elements with user-supplied constitutive functions. This one subsystem covers resting, rocking, impact and jumping without any mode logic, at the cost of stiffness, and is the ground-truth model for the balancing setups.

**Switched pivots (hybrid bond graph).** For controller design, provide a `SwitchedJoint` subsystem, identical inside to `Joint` except that its `MTF: S` matrix is selected from a set `{S_face, S_edge, S_corner}` by a discrete mode signal. Switching is only allowed when the state is consistent with the new basis; the subsystem must provide an impact map for the transition: given the pre-impact momentum, project onto the new constraint, `P^+ = Proj_S(P^-)`, which conserves momentum about the new pivot and discards the rest (perfectly inelastic). A mode guard (which vertices are at ground height) is evaluated by the controller or a supervisor, not inside the subsystem. This is the Mosterman-Biswas controlled-junction pattern; implement the junction's on/off state as a signal input on the standard junction element.

Both contact representations must coexist in one model: the simulation uses `ContactPoint` instances on every vertex; the control-design model uses `SwitchedJoint`. Tests in section 10 compare the two on the same trajectory.

## Causality, state selection and solvers

A rigid serial chain puts every body `I`-field in derivative causality: ground imposes zero twist, each joint adds `S qdot`, so each body's twist is dictated from outside and the `I`-field must return `W = M dV/dt`. The independent states are the joint rates, not the body momenta; the body inertias appear only reflected through the chain as the configuration-dependent mass matrix `M(q) = sum_i J_i(q)^T M_i J_i(q)`. The library must support two evaluation modes and let the user choose per model.

**Mode A: compliant (integral causality everywhere).** Every joint uses the compliance option. States: one momentum vector per body, one deflection per joint axis, joint positions, plus rotor and electrical states. The existing scalar causality assignment and ODE integrator work unchanged. Cost: stiff modes at `sqrt(k / m_eff)`; use an implicit or semi-implicit integrator (implicit Euler, or a symplectic Euler with the stiff `C` forces treated implicitly). This mode must work first; it exercises every element with no new solver code.

**Mode B: articulated (rigid joints, joint-space states).** When a joint is rigid, the causality assigner must detect the derivative-causal `I`-fields and route the model to a chain evaluator instead of failing. Implement the evaluator as Featherstone's articulated-body algorithm expressed on the graph:

1. Outward pass from ground: propagate twists `V_i = Ad^-1 V_parent + S_i qdot_i` and the bias wrenches `ad(V_i)^T M_i V_i` and gravity.
2. Inward pass: accumulate articulated inertia `M_i^A = M_i + sum_children Ad^T (M_c^A - M_c^A S (S^T M_c^A S)^-1 S^T M_c^A) Ad` and bias forces.
3. Outward pass: solve joint accelerations `qddot_i = (S_i^T M_i^A S_i)^-1 (tau_i - S_i^T (M_i^A a_parent + bias))`.

The passes use exactly the `Ad`, `S` and `ad` matrices the elements already hold, so the evaluator is a traversal over the existing graph, not a separate model. It applies to trees; loops fall back to Mode A on the loop-closing joint.

**Mixed models.** A balancing body on a rigid pivot joint with compliant wheel joints is the common case: the pivot is rigid (3 pivot rates as states), the wheels are revolute with their own axial `I` in integral causality because the far side of the joint is free. The assigner must handle this without forcing all joints into one mode. Rule: a joint whose child subtree has no further rigid constraint back to ground leaves the child `I`-fields integral; only chains with both ends constrained need Mode B.

**Integration.** States that live on a group (free-body pose, spherical-joint orientation) are integrated with `g_{k+1} = g_k exp(V dt)`, not by adding to a vector. The integrator interface needs a hook for group-valued states. Symplectic or variational integrators are preferred for long balancing simulations because they preserve the momentum structure; a fixed-step RK4 is acceptable for Mode B tests.

**Energy accounting** (required diagnostic): at every step report `dH/dt - (P_sources - P_dissipated)` summed over the graph, where `H` is total stored energy. It must be zero to integrator order; this single check catches sign errors in `Ad^T`, `ad^T` and `S^T`.

## Required elements per target setup

The two reference setups exercise the whole element set between them. Each row is an element the setup cannot be built without.

| Element | Planar 2-link arm | Spatial 6-axis arm | Cube / pyramid with reaction wheels |
| --- | --- | --- | --- |
| `MultiPort<3>`, `0<3>`, `1<3>` | yes |  |  |
| `MultiPort<6>`, `0<6>`, `1<6>` |  | yes | yes |
| `RigidBody` (I-field, Euler gyrator, gravity, attachment frames) | yes | yes | yes (body + one per wheel) |
| `FixedTransform` | yes | yes | yes (wheel mounts, vertices) |
| `Joint` revolute | yes | yes | yes (wheels) |
| `Joint` spherical |  |  | yes (corner pivot) |
| `Joint` revolute along an arbitrary edge |  |  | yes (edge pivot) |
| `Joint` free |  | optional (mobile base) | yes (face / flight phases with contact model) |
| Compliance option on joints | yes (default) | yes (default) | wheels: no; pivot: no |
| `Ground` | yes | yes | yes |
| `ElectricDrive` with gearbox | yes | yes | yes, direct drive (N = 1) |
| `CurrentControlledDrive` | optional | yes (torque interface) | yes |
| Joint friction `R`, limits | yes | yes | wheel bearing `R` |
| `ExternalWrench` (payload, end-effector load) | yes | yes |  |
| `ContactPoint` + plane surface |  | optional | yes (every vertex) |
| `SwitchedJoint` with impact map |  |  | yes |
| Mode A solver | yes | yes | wheels |
| Mode B solver | optional | yes | pivot |
| Group-valued state integration |  | yes | yes (attitude) |
| Signal taps and inputs | yes | yes | yes |
| Energy accounting diagnostic | yes | yes | yes |

Reaction-wheel specifics the implementer must get right:

- A wheel body carries only its axial inertia `J_w` on its own `I`-field; its mass and transverse inertia are added to the carrying body's `M`. Document this lumping in the `RigidBody` API (a `lumpInto(parent)` helper) rather than leaving it to the user.
- The motor torque appears as `+tau` on the wheel junction and `-tau a_i` on the body junction through `S^T`; the test suite verifies total angular momentum about the pivot changes only through gravity and the pivot wrench.
- Four wheels on a pyramid give a 3x4 axis matrix `A` with a one-dimensional null space; the model does not need to know this, but the signal taps must expose all four wheel rates so a controller can do allocation and null-space redistribution.
- The balancing sequence face -> edge -> corner is a mode machine on the controller side. The simulation model uses `ContactPoint` on all vertices and no `SwitchedJoint`; the three per-mode control models use `SwitchedJoint` or three separate rigid models.

Arm specifics:

- Attachment frames follow the manufacturer's joint frames so that an existing kinematic description (DH or URDF-style offsets) maps one-to-one onto `FixedTransform` + `Joint` pairs. Provide a loader from a simple list of `(parent frame, child frame, joint type, axis, offset pose)` records.
- End-effector port is a plain multibond port on the last body so payloads, contact or a tool model attach without touching the chain.
- Gravity compensation and inverse dynamics come out of Mode B's inward pass with `qddot = 0`; expose that as a function because it is what a controller needs from the model most often.

## Validation tests and acceptance criteria

Each element ships with a unit test on its constitutive relation and a power-continuity test; each setup ships with a comparison against a closed-form or independent reference. Tolerances are relative `1e-9` for algebraic checks and `1e-6` over 10 s for integrated trajectories at the stated step.

- [ ] `Ad` and `ad` identities: `Ad_{g1 g2} = Ad_{g1} Ad_{g2}`, `Ad_{g^-1} = Ad_g^-1`, `ad(V)` matches finite-difference of `Ad_{exp(V t)}` at `t = 0`, and the planar versions equal the spatial ones restricted to the plane.
- [ ] Power continuity: for random twists and wrenches, `W_in^T V_in = W_out^T V_out` through `FixedTransform`, `JointTransform` and the joint `S` transformer; `V^T ad(V)^T P = 0` for random `V`, `P`.
- [ ] Spatial inertia: `M` built from `(m, J_c, c)` equals the parallel-axis result; `RigidBody` with no external wrench conserves momentum and kinetic energy; a free spinning body about its intermediate axis shows the Dzhanibekov flip.
- [ ] Single pendulum (planar and spatial, revolute joint): period matches `2 pi sqrt(L / g)` in the small-angle limit, energy conserved without friction, in both Mode A (stiff `k`) and Mode B.
- [ ] Double pendulum: Mode A with large `k` converges to Mode B as `k` grows; Mode B matches a symbolic Lagrangian derivation of `M(q)`, `C(q, qdot)`, `g(q)`.
- [ ] Six-axis arm: inverse dynamics from Mode B matches an independent recursive Newton-Euler implementation on random `(q, qdot, qddot)`; forward dynamics matches to integrator order.
- [ ] Electric drive: with the joint locked, current step response has time constant `L / R_w`; with the rotor free and no load, no-load speed is `u / k_t`; total power balance holds.
- [ ] Reaction wheel on a spherical pivot: total angular momentum about the pivot is constant with gravity off; with gravity on, its derivative equals the gravity torque; motor torque cancels between wheel and body to round-off.
- [ ] Pyramid, four wheels: accelerating wheels along the null vector `[1, -1, 1, -1]` produces zero body acceleration.
- [ ] Contact: a body dropped on the plane comes to rest with `f_n = m g`; a body on a slope with `mu` above `tan(angle)` sticks, below it slides; `ContactPoint` and `SwitchedJoint` models agree during a pure edge-balance phase.
- [ ] Impact map: momentum about the new pivot is conserved across a `SwitchedJoint` transition; kinetic energy does not increase.
- [ ] Group integration: a free body with constant body twist traces the exact screw motion; quaternion norm stays within `1e-12` of 1 after renormalisation.
- [ ] Energy diagnostic reports zero to integrator order on every model above.

Acceptance: all boxes ticked, the six-axis arm steps in Mode B at under 1 ms per step on the target real-time hardware, and the pyramid simulation with contact on all vertices runs a complete face-to-corner sequence driven by a scripted controller.

## Implementation order and open decisions

Build bottom-up so each step is testable against the previous one; the planar set is finished and tested before any spatial element is written.

1. `MultiPort<D>`, vector `0`/`1` junctions, vector `Se`/`Sf`/`I`/`C`/`R` as componentwise wrappers of the scalar elements, with the existing causality assigner extended to treat a vector port as one unit. Subsystem external ports of type `MultiPort<D>`. Energy diagnostic.
2. `Pose<D>`, `Ad`, `ad`, `exp`, `log`, `Screw<D>`; identity tests.
3. `FixedTransform`, `JointTransform`, `EulerGyrator`, `Gravity`, then the `RigidBody` subsystem with named attachment frames. Free-body tests.
4. `Joint` subsystem with the basis table, integrator, compliance option, friction and limits. Pendulum tests in Mode A.
5. `ElectricDrive`, `CurrentControlledDrive` subsystems, signal taps and inputs. Drive tests.
6. Mode B articulated evaluator on the flattened graph and the mixed-mode causality rule. Double-pendulum and arm tests.
7. `ContactPoint`, `ContactSurface` (plane), `SwitchedJoint` subsystems with impact map. Contact and pyramid tests.
8. Loader for joint-chain records; `lumpInto` helper; inverse-dynamics and gravity-compensation functions.

Decisions to settle before step 1:

- Twist ordering: angular-first `[omega, v]` (Featherstone, Murray-Li-Sastry) or linear-first (some robotics libraries). Recommendation: angular-first, matching the formulas in this guide and the port-Hamiltonian literature.
- Rotation storage: unit quaternion (compact, cheap renormalisation) or rotation matrix (cheaper `Ad`). Recommendation: quaternion as the state, matrix cached per step.
- Whether the scalar library's `TF` and `GY` already accept a matrix ratio; if not, the vector versions need a new base class rather than a wrapper.
- Integrator interface: does the existing stepper allow a per-state update hook (needed for group-valued states), or must group states be integrated as a vector and projected afterwards? The hook is preferred.
- Real-time target: fixed-step only, no allocation after construction, and all per-step matrices (`Ad`, `ad`, `M^A`) stored in preallocated buffers, if this is to run inside the existing PREEMPT\_RT control loop.

References for the implementer: Stramigioli, *Modeling and IPC Control of Interactive Mechanical Systems: A Coordinate-Free Approach* (2001); Duindam, Macchelli, Stramigioli, Bruyninckx (eds.), *Modeling and Control of Complex Physical Systems* (2009), chapter on port-based multibody modelling; Featherstone, *Rigid Body Dynamics Algorithms* (2008) for the articulated-body passes; Mosterman and Biswas, hybrid bond graphs with controlled junctions (1998); Muehlebach and D'Andrea, Cubli jump-up and balancing papers (2013-2017).
