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
  stiffness.
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
| `mode_kind` | nm strings | `"fixed-interface"` or `"constraint"`, whichever part dominates the mode's modal mass |
| `St` | 3 × nm rows | `∫ρ Φ dV` (translational coupling) |
| `Sr` | 3 × nm rows | `∫ρ x × Φ dV` (rotational coupling) |
| `J1` | 6 × nm rows | first-order inertia per mode, `∫ρ (2 x·φ_k I − x φ_kᵀ − φ_k xᵀ) dV`, components xx yy zz xy xz yz |
| `E` | `{xx, yy, zz, xy, xz, yz}`, each nm × nm | `E_ab = ∫ρ Φ_aᵀ Φ_b dV` (second-order inertia; `E_xx + E_yy + E_zz = diag(mk)`) |
| `interfaces` | list (1 to 4) | see below; the first one is the reference frame R |
| `stiffening` | object or `null` | geometric-stiffening matrices, see below |
| `validation` | object | reduced against full FE eigenfrequencies, see below |
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
configuration of the part in its mechanism. `validation.cb` holds the
reduction's own numbers, `validation.seconds` the time of the check.

## Limits

* Linear elasticity, small strain, isotropic material. Large overall motion is exact (floating
  frame); the elastic deformation is small. Geometric stiffening is first order (see above).
* At most 4 interfaces and 48 modal coordinates per body. Every coordinate is a state pair
  (`q`, `p`), so compile time grows with `nm` (about 1 to 2 minutes for nm ≈ 15).
* The modal frequencies set the stiffness of the ODE. For a fixed-step export (C/FMU),
  `dt` must resolve the highest one: drop modes above the band you need
  (`modes.drop_above_hz` in the part spec), or use an implicit solver.
