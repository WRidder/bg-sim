# Reduced-model file of a FEM flexible body (`bgsim.modal-body`, version 1)

A `stdlib:spatial/ModalBody3D` node names a JSON file in its settings (`file`, a path relative
to the project folder). The offline tool `julia/BGSimFEM` writes it from a part spec: it meshes
the part with quadratic tetrahedra (Gmsh, OpenCASCADE geometry or a STEP file), assembles the
stiffness and consistent mass matrices (Ferrite), ties the interface nodes rigidly to 6-DOF
interface frames (RBE2), and reduces the model by Craig–Bampton with interface 1 as the
body's reference frame. The compiler reads the file while it instantiates the node
(`src/library/modaldata.jl`) and turns it into the block's constants. Next to it the tool writes
a GLB of the part's surface with one morph target per mode; the 3D viewer's `mode-shapes`
binding deforms that mesh with the block's modal coordinates `eta`.

```
julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl design/bracket.fem.json
```

## The model behind the numbers

* Reference frame R: the frame of interface 1 (position and orientation given in the part
  spec). Every vector and tensor below is expressed in R. The elastic field is measured
  relative to R: interface 1 is clamped in the reduction. This is the general form of the
  clamped-free basis of the `FlexibleBeam3D` block.
* Basis: `fixed_interface_modes` eigenmodes with every interface clamped, plus the
  `6 (ni - 1)` static constraint modes of interfaces 2..ni (unit motion of one interface DOF,
  the others clamped). The constraint modes are the static correction: the static response to
  loads at the interfaces is exact. The reduced pair is then diagonalised, so the coordinates
  are the eigenmodes of the reduced body clamped at interface 1, with diagonal modal mass and
  stiffness. A part with a rail can add load modes to the basis before that (see Rail).
* Scaling: each mode has a largest nodal translation of 1, so the modal coordinates are in
  metres (the displacement of the most-moving node).
* A material point at `x` (in R) moves to `x + Phi(x) q (+ u2(q))`. `u2` is the second-order
  field of the geometric-stiffening matrices, if present.

## Keys

| Key | Type | Meaning |
|---|---|---|
| `format`, `version` | string, int | `"bgsim.modal-body"`, `1` |
| `name`, `generator`, `units`, `frame` | strings | descriptive |
| `reference_in_part` | `{position, quaternion}` | where R sits in the part's (CAD) coordinates; quaternion (w, x, y, z) |
| `material` | `{E, nu, rho}` | Pa, 1, kg/m³ |
| `mesh` | object | `element` (tet10/tet4), `size` (m), `cells`, `nodes`, `dofs` |
| `nm` | int | number of modal coordinates (1 to 48 in the simulator) |
| `fixed_interface_modes` | int | how many of them came from fixed-interface modes |
| `mass` | number | kg |
| `first_moment` | 3 | `S0 = ∫ρ x dV` (kg·m); the centre of mass is `S0 / mass` |
| `inertia` | 3 × 3 rows | `J0 = ∫ρ (|x|² I − x xᵀ) dV` about the origin of R (kg·m²) |
| `modal_mass`, `modal_stiffness` | nm | `mk` (kg), `kk` (N/m) |
| `frequency_hz` | nm | `sqrt(kk/mk)/2π`: the eigenfrequencies of the reduced body clamped at interface 1 |
| `mode_kind` | nm strings | `"fixed-interface"`, `"constraint"` or `"load"` (a rail load mode), whichever part dominates the mode's modal mass |
| `St` | 3 × nm rows | `∫ρ Φ dV` (translational coupling) |
| `Sr` | 3 × nm rows | `∫ρ x × Φ dV` (rotational coupling) |
| `J1` | 6 × nm rows | first-order inertia per mode, `∫ρ (2 x·φ_k I − x φ_kᵀ − φ_k xᵀ) dV`, components xx yy zz xy xz yz |
| `E` | `{xx, yy, zz, xy, xz, yz}`, each nm × nm | `E_ab = ∫ρ Φ_aᵀ Φ_b dV` (second-order inertia; `E_xx + E_yy + E_zz = diag(mk)`) |
| `interfaces` | list (1 to 4) | see below; the first one is the reference frame R |
| `stiffening` | object or `null` | geometric-stiffening matrices, see below |
| `stress` | object or absent | stress per unit modal coordinate at a few surface points, see below |
| `rail` | object or absent | a straight rail a carriage slides along (the moving interface E), see below |
| `validation` | object | reduced against full FE eigenfrequencies and static stress, see below |
| `visual` | object | `glb` (file name of the GLB, looked up in the project's `meshes/`), `vertices`, `triangles` |

Each interface:

| Key | Meaning |
|---|---|
| `name` | e.g. `"A"`; the block's ports A, B, C, D are the interfaces in file order |
| `position`, `quaternion` | the interface frame in R (the first interface: origin, identity) |
| `nodes` | how many surface nodes the RBE2 tie holds |
| `translation` | 3 × nm rows: the interface origin's displacement per unit modal coordinate, in R |
| `rotation` | 3 × nm rows: the interface frame's small rotation per unit modal coordinate, in the interface's own frame |

## Geometric stiffening

The linear modes miss the stiffening (or softening) by stresses that the motion itself causes:
centrifugal stiffening of a spinning part, the stiffening by inertia loads, and buckling-like
softening by compressive interface forces. The tool computes it from the second-order field
`u2(q)` through the identity

```
∫ f · u2 dV = −½ qᵀ G(f) q,      G(f) = Φᵀ K_σ(σ_f) Φ
```

where `σ_f` is the static stress under the load `f` with interface 1 clamped and `K_σ` the
geometric stiffness matrix. The file holds `G` for the load cases the equations need:

| Key | Count | Load `f` | Enters |
|---|---|---|---|
| `translation` | 3 | `ρ e_a` | first moment `S(q)` (gravity and the rotation–translation coupling) |
| `inertia` | 6 | `ρ (2 δ_ab x − x_a e_b − x_b e_a)`, ab = xx yy zz xy xz yz | inertia tensor `J(q)` (centrifugal stiffening) |
| `rotation` | 3 | `ρ e_a × x` | not used by `ModalBody3D` (kept for other consumers) |
| `interface_force` | 3 (ni − 1) | unit force `e_a` at interface j ≥ 2 | interface positions (stiffening by interface forces) |

Each is a list of nm × nm matrices (rows). The terms are part of the kinetic energy and of the
port kinematics, so the stiffened body still conserves energy. `ModalBody3D` puts them into
`S(q)` and `J(q)` (second order in q) but not into the coupling rows between the frame and the
modes (first order in q): without the matching third-order terms of the modal mass block those
make the mass matrix indefinite already at moderate deflections of a light part. So the body
stiffens by its rotation, by gravity and by interface forces, not by the acceleration of its
reference frame. Not included either: stiffening by interface moments and by distributed loads
other than gravity. The node setting
`stiffening = 0` drops the terms (they cost equations); a file written with
`"stiffening": false` has `null` here.

## Stress

Every mode (fixed-interface and constraint modes alike) has a stress field. The tool recovers
it element by element, `σ = C : sym(∇φ_k)` at the nodes of every cell (exact for the linear
strain of a tet10), and averages it over the cells that share a node. Stress is linear in the
displacement, so the stress of the body is the superposition

```
σ(x, t) = Σ_k σ_k(x) η_k(t)          (6 components xx yy zz xy xz yz, Pa)
```

and von Mises is taken of the summed components, never summed itself. The motion of the body
frame R is rigid and gives no stress. Interface loads are exact, because the constraint modes
span their static response. A distributed load (gravity, inertia) converges with the number of
fixed-interface modes. Second-order (`u2`) stress is ignored, like the strain of the
stiffening terms.

`stress` (absent when the part spec says `"stress": false`):

| Key | Meaning |
|---|---|
| `unit`, `components`, `recovery` | `"Pa per unit modal coordinate"`, `["xx","yy","zz","xy","xz","yz"]`, a description |
| `hotspots` | how many of the points are named hotspots (they come first) |
| `points` | list: `name`, `kind` (`"hotspot"` or `"peak"`), `position` (in R), `position_in_part`, `sigma` (6 × nm rows), and for a hotspot `requested` (the position asked for, in R) and `distance` (to the surface node used) |
| `excluded` | which nodes are never chosen |

A hotspot is the surface node nearest to the position in the part spec
(`stress.hotspots: [{name, position}]`, part coordinates). The peak candidates
(`stress.peak_points`, default 24) are surface nodes the tool chooses so that the largest von
Mises over them tracks the peak over the whole surface. It chooses them greedily over a set of
load states: the static responses to unit forces and moments at each interface j ≥ 2 and to
self weight along each axis, plus random combinations of those and of single modes. Nodes tied
to an interface (the RBE2 spider) are excluded: the rigid tie concentrates stress there that
the real joint does not have. `stress.exclude_interfaces` widens that exclusion by a distance
(m) around the interface nodes.

The GLB carries the same field at its visual vertices, for the 3D view's stress colouring: a
Float32 bufferView without a target, laid out (vertex, mode, component), index
`((v − 1) nm + (k − 1)) 6 + c`, described in `asset.extras.bgsim.stress` (`bufferView`, `mesh`,
`primitive`, `vertices`, `modes`, `components`, `layout`, `unit`, `recovery`). Its vertex
order is that of the POSITION accessor of mesh 0, primitive 0.

`ModalBody3D` reads the points as the constants `ns`, `nh`, `Sxx` … `Syz` (ns × nm) of its
component `ModalStress3D`, which outputs `sigma_vm[1..nh]` (von Mises at the hotspots) and
`sigma_max` (a smooth maximum over all the points).

## Rail

A rail is a straight line on the part along which a carriage slides: the linear guide on a
gantry beam. The carriage is not a fixed interface, because it moves. The block needs the
motion of the rail frame at the carriage's position `s` for every mode, and how that motion
changes along `s`:

```
r_E(s, q) = XR + s t + PT(s) q        rail frame origin, in R
g_E(s, q) = ½ PR(s) q                 its elastic rotation (Gibbs vector), in the rail frame
```

`PT(s)` and `PR(s)` (3 × nm) are the rigid fit of each mode over the rail's footprint. The
footprint is the surface nodes of the mounting face (`footprint.select`) within `half_length`
of the station along the rail. A least-squares rigid motion of those nodes gives the
translation and rotation of a guide block there, the way its bearing pads follow the face. The
tool samples the fit at `stations` points and fits a Chebyshev series in `x = 2 s / L − 1`
(`chebyshev` terms). The block evaluates it by the recurrence, which gives exact derivatives and
no switching.

Part spec (`rail`, part coordinates):

| Key | Meaning |
|---|---|
| `name` | e.g. `"Y rail"` |
| `start`, `end` | the rail line (m); `s` runs from 0 at `start` to `L` at `end` |
| `normal` | the mounting face's outward normal: the rail frame's x. Its z is the rail direction `t`, and y = z × x |
| `stations`, `chebyshev` | samples of the fit (default 41) and terms of the series (default 20) |
| `footprint` | `half_length` (m), `select` (a node selection like an interface's, usually a thin box on the face), `surface` |
| `load_modes` | fractions of `L` (e.g. `[0.25, 0.5, 0.75]`). At each one, the static responses to a unit force along the rail frame's x and y and a unit moment about `t` are added to the basis. They are made M-orthogonal to the other modes, so the reduction stays a Ritz basis. |

File (`rail`):

| Key | Meaning |
|---|---|
| `name`, `length` | the rail's name and `L` (m) |
| `start` | `XR`, the rail's start in R |
| `quaternion`, `rotation_matrix` | the rail frame in R (rows of the matrix whose columns are its x, y, z) |
| `chebyshev`, `basis` | the number of terms `nc` and a description of the series |
| `translation` | 3 tables (one per component of `PT`, in R), each nm × nc rows: `PT_a(s) = Σ_n CT_a[:, n] T_n(x)` |
| `rotation` | the same for `PR` (in the rail frame) |
| `stations`, `footprint_half_length`, `footprint_nodes` | the sampling, and how many nodes each station's fit used |
| `fit_error` | the series' largest error, relative to the largest sampled value (`translation`, `rotation`) |

`ModalBody3D` reads these as the constants `nr` (1 with a rail, else 0), `nc`, `RL`, `XR`,
`RR`, `QR`, `CT1` … `CT3` and `CR1` … `CR3` (nm × nc). It gets two ports, `E` (Spatial: the
carriage frame on the deformed rail at `s`, with its pose output `poseE`) and `S` (Translation:
the slide). The slide's flow is `ṡ`, and its effort is the drive force along the rail (a linear
motor between the part and the carriage). Outputs `s` and `sd` are the coordinate and its rate.
The twist of the frame at E includes the term `(t + PT′(s) q) ṡ` (and `½ PR′(s) q ṡ` for the
rotation), so the carriage rides the deformed rail. The wrench at E enters the modal forces
through `PT(s)` and `PR(s)`, and the slide through the same derivatives. This keeps the model
power-continuous: with the dampers off, the energy of the body, the slide (mass `ms`), the
carriage and the springs is conserved (`test/test_fem_rail.jl`).

How to attach the carriage: a `Prismatic3D` from `E` to the carriage, with its axis held by a
stiff drive spring. The carriage then moves with `s`, and the joint's five held directions are
the guide's stiffness. Put the drive force (`ForceSource` with its other side on `Fixed`) on
`S`. `ms` is the slide's own inertia along the rail. Keep it small next to the carriage's mass,
because with `ms → 0` the motor's reaction on the part is the physical one.

Accuracy. Without load modes, a carriage load between the interfaces is carried only by the
fixed-interface modes (a point load at mid-span of a beam: about 97 % of the deflection with
the first bending mode). With load modes, a load at a load-mode station is exact. Between
stations the result is interpolated. That works well for the force directions, but a moment
about the rail that bends the mounting wall locally is only exact at the stations.
`validation.rail` measures this.

## Validation

`validation.frequencies` compares the reduced model with the full FE model (shift-invert
Lanczos on the full matrices), for the body clamped at interface 1 (`clamped`) and free-free
(`free`; the reduced values come from the linearised floating-frame equations, so this also
checks the inertia invariants). Each entry has `full_hz`, `reduced_hz` (nearest match),
`rel_error`, `in_band` and `max_rel_error_in_band`. `band_hz` is 80 % of the first discarded
fixed-interface frequency. Below it the Craig–Bampton model is expected to be accurate. Above
it the reduced model misses modes or has only constraint modes, which are too stiff.
`validation.attached` (from the part spec's `validate_attached`) is the same comparison for the
body clamped at interface 1 with rigid bodies attached at other interfaces (a payload): the
configuration of the part in its mechanism.

`validation.stress` checks the stress recovery against static solves of the full FE model
(interface 1 clamped). `cases` has one entry per load case (a unit force and moment per axis at
each interface j ≥ 2, self weight per axis), each with `full_peak` and `reduced_peak` (the
largest von Mises over the surface, and where), `peak_rel_error`, `points_peak` (the largest
over the file's points), `points_vs_reduced_peak` and the `hotspots` (full, reduced, error).
`max_peak_rel_error_interface_loads` is round-off, since the constraint modes make interface
loads exact. `max_peak_rel_error_self_weight` shows the truncation of the fixed-interface modes.
`peak_coverage` (`samples`, `min_ratio`, `mean_ratio`, `within_5_percent`) tells how well the
points' maximum tracks the surface peak, over a fresh random sample of load states.
`validation.rail` compares the static motion of the rail frame under unit loads (a force along
the rail frame's x and y and a moment about `t`, spread over the footprint) at several stations
(`fractions` of `L`) between the full FE model and the reduced model with its Chebyshev tables.
Interface 1 is clamped. `cases` has `station`, `fraction`, `load`, the six-component responses
`full` and `reduced`, the compliances in the loaded direction, `rel_error`, and
`error_of_largest` (the error relative to the largest compliance of that load along the rail,
which is the meaningful number near the clamp, where the deflection is tiny). The summary values
are `max_rel_error_force`, `max_rel_error_torsion` and `max_error_of_largest`.
`validation.cb` holds the
reduction's own numbers, `validation.seconds` the time of the check.

## Limits

* Linear elasticity, small strain, isotropic material. Large overall motion is exact (floating
  frame); the elastic deformation is small. Geometric stiffening is first order (see above).
* At most one rail per body, straight, with one carriage on it (`nc` at most 32). The guide
  block follows the rigid fit of its footprint, not the face's local waviness under the pads.
  The load along the rail (the drive force) is not among the load modes.
* At most 4 interfaces and 48 modal coordinates per body. Every coordinate is a state pair
  (`q`, `p`), so compile time grows with `nm` (about 1 to 2 minutes for nm ≈ 15).
* The modal frequencies set the stiffness of the ODE. For a fixed-step export (C/FMU),
  `dt` must resolve the highest one: drop modes above the band you need
  (`modes.drop_above_hz` in the part spec), or use an implicit solver.
