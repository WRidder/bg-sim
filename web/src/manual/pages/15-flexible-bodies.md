# Flexible bodies

A slender rod, tube or bar that bends and twists can replace a rigid body in a multibond model. For any other part shape, see **FEM flexible bodies** below. `FlexibleBeam2D` (in the **Planar** category) and `FlexibleBeam3D` (in **Spatial**) use the **assumed-modes method**: the beam has a floating reference frame that carries its rigid motion, and up to three elastic modes per family are added on top of it. The beam's own mass and rotational inertia are inside the block, so do not add a rigid body for the rod.

## Blocks

| Block | Ports | Families | Replaces |
| --- | --- | --- | --- |
| `FlexibleBeam2D` | `A`, `B` (planar), input `gA` (pose of end A) | in-plane bending `y` | `RigidBody2D` |
| `FlexibleBeam3D` | `A`, `B` (spatial), input `gA` (pose of end A) | bending `y`, bending `z`, torsion `t` | `RigidBody3D` |

`ModalBeam2D` and `ModalBeam3D` are the cores of these blocks, with the modal bond graph and the equations. Use the `FlexibleBeam` blocks in models: their ends are 1-junctions, so they bond like a body port.

### Constants (structural)

| Constant | Values | Meaning |
| --- | --- | --- |
| `ny`, `nz`, `nt` | 0 to 3 | number of bending modes along local y, along local z, and of torsion modes (2D: `ny` only) |
| `basis` | `clamped-free`, `free-free` | the mode shapes: clamped at end A (a cantilever on a joint), or free at both ends (mean-axis frame, for a free-flying beam) |
| `section` | `rod`, `tube`, `rectangle` | the cross-section: rod `d`; tube `d`, `di`; rectangle `b` (along local y) by `h` (along local z) |

### Parameters

| Parameter | Unit | Meaning |
| --- | --- | --- |
| `L` | m | length from A to B |
| `E`, `rho` | Pa, kg/m³ | Young's modulus and density |
| `nu` | 1 | Poisson ratio (3D only), shear modulus `G = E / (2 (1 + nu))` |
| `d`, `di`, `b`, `h` | m | section dimensions, used according to `section` |
| `zeta_y`, `zeta_z`, `zeta_t` | 1 | modal damping ratio per family |
| `g0` | m/s² | gravity along world −z (2D: world −y). Set it to 0 without gravity |

### Outputs

| Output | Unit | Meaning |
| --- | --- | --- |
| `pose` | | world pose of the reference frame. Bind it to the beam's link in the 3D view |
| `poseB` | | world pose of end B, including its deflection and rotation. Compose the next link from it |
| `V` | | twist of the reference frame |
| `eta_y`, `eta_z`, `eta_t` | m, m, rad | modal coordinates, three entries each. An unused mode reads 0 |
| `f_y`, `f_z`, `f_t` | Hz | eigenfrequencies of the three modes of each family in the chosen basis, for the beam alone |
| `twist` | rad | twist of end B relative to end A (3D) |
| `dB` | m | elastic deflection of end B in the reference frame |
| `Ek`, `Ee`, `Eg` | J | the beam's kinetic, strain and gravity energy |

All outputs are also recorded as signals, for example `Rod/eta_y[1]` or `Rod/f_t[2]`.

## Frames and connections

End A sits at s = 0 with the beam axis along its local +x. End B sits at s = L. Connect the beam like a rigid body:

- bond the joint's `child` (or a fixed transform) to `A`. Anything that should move with end B is bonded to `B`. A free end B can stay unconnected;
- bond the beam like a rigid body: a joint's `child` bonds into the beam (`joint.child → A`), and the beam bonds into the next joint's `parent` (`B → joint.parent`). The ends are 1-junctions with the true twist, as the port of a rigid body is, and the `parent` port is declared `in`. A bond drawn the other way round is the error E114;
- feed `gA` with the world pose of end A, from the joint's pose chain (the same `ComposePose` signals a rigid body gets as `g`);
- for the next link, compose its pose from `poseB`.

To clamp a beam to the world, bond a stiff `CSpatial` and an `RSpatial` (2D: `CPlanar`, `RPlanar`) to `A`.

## Mode shapes and what they capture

The deflection is w(s, t) = Σ φ_n(s) η_n(t), with closed-form Euler–Bernoulli shapes normalised to (1/L) ∫ φ_n² ds = 1. Then each bending mode has the modal mass ρAL and the stiffness λ_n⁴ EI/L³. A clamped-free mode has φ_n(L) = ±2, so the tip deflection is about twice the modal coordinate. Torsion uses ψ_n(s) = √2 sin((2n−1)π s/2L). Axial stretch is rigid.

The block is energy-consistent, and it includes **geometric stiffening**:

- the **centrifugal** stiffening of a spinning beam (Southwell: the flap frequency rises as ω² = ω₀² + 1.193 Ω², the in-plane frequency as ω₀² + 0.193 Ω²);
- the axial load at the tip;
- the beam's own weight.

The deflection is accurate to second order: a beam that bends also gets shorter along its axis. The end rotations follow the end slopes, and the end twist is exact for large angles.

## How many modes?

- **Bending.** One mode gives 97 % of the static tip deflection under a tip force, two give 99.5 % and three 99.9 %. The first two frequencies of a cantilever come out exact. For most rods, `ny = nz = 2` is enough.
- **Torsion.** The series converges slowly. The static twist under an end torque is 81 % / 90 % / 93 % for 1 / 2 / 3 modes. With a heavy body at end B (a disk on a shaft), the first torsional frequency is 11 % / 5.4 % / 3.5 % too high. If torsion does not matter, use `nt = 0`.
- **Stiffness.** Every mode adds a fast frequency: a 6 mm aluminium shaft has torsion modes up to 24 000 rad/s. Use a stiff solver (`Rodas5P`) for simulation. For an [export](page:export), the explicit methods need `dt · ω_max < 2.8`, and a free beam vibrates above its clamped-free `f_*` values.

## In the 3D view

Bind the block's `pose` to the link that holds the beam's visual. Then add one **deformation** binding per family with the signals `eta_y[1..ny]`, `eta_z[1..nz]` or `eta_t[1..nt]` and the same `basis` as the block (see [Running and plotting](page:running-and-plotting)). The beam axis of the binding is the visual's direction from end A to end B. Real deflections are small; use the view's deformation exaggeration to see them. A lumped torsion spring with no modes (a shaft as one spring between two inertias) is drawn with the `linear` basis and its twist instead.

## Examples

- **cantilever-modes**: the same method by hand, as a scalar bond graph. Each mode is a 1-junction with I, C and R, coupled to the tip by a TF with modulus |φ_n(L)| = 2. All element values are global parameters.
- **cantilever-sections**: a round bar, a square bar and an IPE 100 I-beam of the same mass per metre, 2 m long and clamped to one wall, under one tip force (constant, sine or a sweep, chosen on the dashboard). Each beam is a three-mode cantilever block of the project; the 3D view bends them and colours them by their bending stress. The I-beam is about 21 times stiffer than the bars. Deflection, root moment, stress and the eigenfrequencies are checked against Euler–Bernoulli, and the step and sine responses against a finite element model.
- **flex-torsion**: two disks on a 1 m shaft with three torsion modes. The twist is checked against the exact frequency equation and the massless-shaft limit.
- **flex-rotary-pendulum**: a Furuta pendulum with a bending rod (2 + 2 modes), next to its rigid twin.
- **fem-bracket**, **fem-torsion**, **fem-gantry**: FEM flexible bodies (below). fem-gantry is an H-gantry with a FEM crossbeam, two servo-driven linear-motor X axes and a Y carriage on the beam's rail. It shows point-to-point moves plain and input-shaped, racking, and the beam's stress against the allowable on a dashboard.
- **pendulum-triple-rotary** (models `-flex`, `-flex-lowpass`, `-flex-free`): the rotary triple inverted pendulum with a flexible arm, a 3 x 50 mm steel strip (2 + 2 bending modes, 1 torsion mode). The rigid arm's controller drives the arm's first bending mode unstable. A controller designed with a 12 Hz low-pass in the loop balances the pendulum. The first mode is checked against the exact frequency equation, with the hinged pendulum chain as the tip load.

## FEM flexible bodies (any part)

A part that is not a slender beam (a bracket, a gripper finger, a robot link) can still flex. `ModalBody3D` (in **Spatial**) is a flexible body that is reduced from a finite element model of the part. The finite element work runs **offline**, once per part: a tool meshes the part, assembles its stiffness and mass, and reduces it to a few modal coordinates by the **Craig–Bampton** method. The simulation only runs the small reduced model, so it stays fast and exports to C/FMU like any other block.

### 1. Describe the part

Write a part spec (JSON) next to your project, for example `design/bracket.fem.json`:

```json
{
  "name": "bracket",
  "geometry": {"union": [
    {"box": {"corner": [0, -0.02, 0], "size": [0.12, 0.04, 0.005]}},
    {"box": {"corner": [0.08, -0.002, 0.005], "size": [0.04, 0.004, 0.15]}}
  ]},
  "material": {"E": 70e9, "nu": 0.33, "rho": 2700},
  "mesh": {"size": 0.004, "order": 2},
  "interfaces": [
    {"name": "A", "position": [0.02, 0, 0], "select": {"box": {"min": [-1, -1, -1e-6], "max": [0.04, 1, 1e-6]}}},
    {"name": "B", "position": [0.1, 0, 0.155], "select": {"box": {"min": [-1, -1, 0.154999], "max": [1, 1, 0.155001]}}}
  ],
  "modes": {"fixed_interface": 4},
  "stiffening": true,
  "validate": 8,
  "validate_attached": [{"interface": "B", "mass": 0.5, "inertia": [1.3e-4, 1.3e-4, 1.3e-4], "com": [0, 0, 0.02]}],
  "visual": {"size": 0.006},
  "output": {"model": "../data/bracket.modal.json", "glb": "../meshes/bracket.glb"}
}
```

This is the bracket of the example **fem-bracket**: a base plate and a thin upright, interface A on the bolted area under the plate, interface B on the top of the upright.

- **geometry**: `box`, `cylinder`, `sphere`, combined with `union`, `cut` and `intersect`, or a CAD file `{"step": {"file": "part.step", "scale": 0.001}}` (a STEP file in mm needs `scale` 0.001). Lengths are in metres.
- **mesh**: element size in metres. `order` 2 (quadratic tetrahedra) is accurate in bending even with two elements across a wall; keep it.
- **interfaces**: where the part connects to the rest of the model, 1 to 4 of them. Each has a frame (`position`, optional `quaternion` w, x, y, z) and a `select` region (`box`, `sphere` or `cylinder`) that picks the surface nodes tied rigidly to that frame (a bolt hole, a bearing seat, a flange face). The **first interface is the body's reference frame**: the elastic deformation is measured relative to it.
- **modes.fixed_interface**: the number of vibration modes with all interfaces clamped. The tool adds 6 static **constraint modes** per further interface, so the model has `fixed_interface + 6 (interfaces − 1)` modal coordinates.
- **visual.size**: a coarser mesh for the 3D view (the mode shapes are interpolated onto it).

### 2. Reduce it

```
julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl design/bracket.fem.json
```

It needs the separate Julia project `julia/BGSimFEM` (Gmsh, Ferrite). It writes two files:

- `data/bracket.modal.json`: the reduced model (mass properties, modal mass and stiffness, the inertia invariants, the interface mode values, geometric stiffening). The format is documented in `docs/modal-body-format.md`.
- `meshes/bracket.glb`: the part's surface with one morph target per mode, for the 3D view.

It also compares the reduced model with the full finite element model and prints the first frequencies of both, clamped at interface A and free-free. Below `band` (80 % of the first fixed-interface frequency it left out) the error should be well under 1 %. A payload or another part bolted to an interface changes the frequencies: list it under `validate_attached` (interface, mass, inertia, centre of mass) and the tool also compares the part clamped at A with that payload against the full model. From Julia, `BGSimFEM.reduce_part("design/bracket.fem.json")` does the same and returns the model.

### 3. Use the block

Add `ModalBody3D`. In the inspector's **Reduced model** section, pick the file from the list of the project's `data/*.modal.json` files, or **Upload .modal.json…** to copy one into `data/`. The section then shows a summary of the file: part name, mass, the number of modes and how many are fixed-interface modes, the interfaces and the ports they map to (A, B, C, D in file order), the first frequencies with A clamped, the validation errors, and the GLB to put in `meshes/`. The block reads all its constants from that file, so they are not editable; the parameters `zeta` and `g0` are. When you regenerate the file, the next run recompiles.

| Port / signal | Meaning |
| --- | --- |
| `A`, `B`, `C`, `D` | the interfaces, in the order of the part spec. `A` is the reference frame. An unused port can stay open. Bond them as the port of a rigid body (`joint.child → A`, `B → joint.parent`). A bond against a joint's declared orientation is the error E114 |
| `gA` | input: world pose of interface A (from the joint's pose chain, as for a rigid body) |
| `pose` | world pose of the reference frame A. Bind it to the part's link in the 3D view |
| `poseB`, `poseC`, `poseD` | world poses of the deformed interfaces. Compose the next link from them |
| `eta[1..nm]` | modal coordinates in m (each mode is scaled so that its largest displacement is 1) |
| `f[1..nm]` | modal frequencies with A clamped (Hz) |
| `Ek`, `Ee`, `Eg` | kinetic, strain and gravity energy (J) |
| `sigma_vm[1..nh]`, `sigma_max` | von Mises stress at the hotspots and the peak estimate (Pa), see **Stress** below |
| `E`, `S`, `poseE`, `s`, `sd` | the carriage on a rail (a part spec with a `rail`): the carriage frame on the deformed rail, the slide, its world pose, the rail coordinate and its rate, see **A carriage on a rail** below. Without a rail they stay open |

Parameters: `zeta` (modal damping ratio, all modes) and `g0` (gravity along world −z); with a rail also `s0` (where the carriage starts, m from the rail's start) and `ms` (the slide's own mass along the rail). The setting **geometric stiffening** (on by default) keeps the second-order terms: centrifugal stiffening of a spinning part and stiffening or softening by forces at the interfaces. Turn it off for a faster compile if the part does not spin fast and carries no large interface forces.

### Which interfaces, how many modes?

- Put an interface wherever the part is **bolted, jointed or loaded**: the constraint modes make the static response to forces and moments at the interfaces exact. That is what the assumed-modes beam misses. On the two-disk torsion shaft it is 3.5 % too stiff with three torsion modes, and the FEM shaft (2 interfaces, 4 fixed-interface modes) gets the exact frequency (example **fem-torsion**).
- Each extra interface adds 6 coordinates. A load that only pushes on the part (a payload resting on it) is better as an interface than as a distributed force.
- Choose `fixed_interface` so that the band the tool prints lies above the frequencies that matter (two to three times the highest excitation frequency). Use `modes.drop_above_hz` to drop very stiff modes you do not need.
- Up to 48 coordinates and 4 interfaces per body. Every coordinate costs compile time: the turntable of example **fem-bracket** (10 coordinates, 59 states) compiles in about 15 s, and the stiff solver's Jacobian adds about 10 s to the first run.

### Simulation and export

The modal frequencies are real: a small steel bracket has modes at several kHz. Which solver to use depends on what holds the part:

- **Joints, clamps or welds on an interface**: use the stiff solver `Rodas5P`. Once the modes are free, the reference frame of a small part has a very small rotational inertia (the L of the tests, 26 g: about 2·10⁻⁸ kg m²), so a stiff joint on it rings at 100 kHz and more. An explicit method would have to resolve that; `Rodas5P` steps over it. Its Jacobian adds about 10 s to the first run.
- **A free body** (only forces on it, no joint): an explicit method (`Vern7`, `Tsit5`) is faster; it only has to follow the highest elastic mode.
- Undamped stiff joints ring for ever: give the joints and clamps some damping (the examples use ζ ≈ 0.05 for their welds) and keep `reltol` at 1e-7 or looser for long runs.
- Make joints and clamps stiff enough, not stiffer: about 1000 times the part's own stiffness at the interface is plenty. Every factor of 100 in stiffness is a factor of 10 in the frequency the solver has to step over.
- Keep the model an ODE. A fixed offset (`FixedTransform3DNeutral`) between a rigid body that already has a joint on its port and the joint to the flexible part can leave algebraic equations (a DAE), and a stiff run then crawls. Put the offset on the flexible part's side of the joint instead (joint → offset → `A`), as in example **fem-bracket**.
- When a `FixedTransform3DNeutral` places a joint on the ground (`GroundSpatial`), put the ground on its side `b` and give the transform the inverse pose (the rotation conjugated, the offset −Rᵀp). The transform computes the flow of `a` from that of `b`; with the ground on `a`, the joint's flows and efforts form a linear algebraic loop (example **fem-gantry**: 24 algebraic unknowns, and the run crawled).
- A closed kinematic loop through the part (two axes holding the two ends of a beam) needs no special treatment when the joints are compliant: example **fem-gantry** holds its crossbeam on a welded end and a pivoted end, the usual fixed/floating pair.

For a fixed-step [export](page:export), the explicit methods need `dt · 2π f_max < 2.8`, where `f_max` is the highest frequency in `f` (the free body vibrates somewhat above it). Drop modes you do not need (`drop_above_hz`) rather than shrink the step.

### In the 3D view

Put the GLB (`meshes/bracket.glb`) as a mesh visual on the link bound to the block's `pose`. Then add a **mode-shapes** binding on that visual with the signals `Block/eta[1..nm]` (the binding editor fills them in one step; see [Running and plotting](page:running-and-plotting)). The viewer moves every vertex by Σ η_k φ_k. Use the deformation exaggeration to see small deflections. Tick **stress** on that binding to colour the mesh by its von Mises stress (see below).

### Stress

The reduction also writes the stress of every mode. Stress is linear in the deformation, so the stress anywhere in the part is the sum σ(x) = Σ σ_k(x) η_k over the modes, and von Mises is taken of the summed six components. The motion of the reference frame is rigid and adds no stress. The block has two stress outputs:

| Signal | Meaning |
| --- | --- |
| `sigma_vm[1..nh]` | von Mises stress (Pa) at the **hotspots** you name in the part spec, in that order |
| `sigma_max` | the largest von Mises over the hotspots and the tool's **peak candidates** (Pa): an estimate of the peak over the part |

Name the hotspots in the part spec (positions in part coordinates; the tool takes the nearest surface node):

```json
"stress": {
  "hotspots": [{"name": "upright 30 mm", "position": [0.1, 0.002, 0.03]}],
  "peak_points": 24
}
```

The tool picks `peak_points` surface nodes (default 24) so that their largest von Mises follows the peak of the whole surface over many load states, and it prints how well they do (for the bracket, 99.8 % of the peak on average). It leaves out the nodes tied to an interface: the rigid tie makes a stress concentration there that the real bolt or bearing does not have. `"exclude_interfaces": 0.005` also leaves out the surface within 5 mm of a tie. `"stress": false` turns the stress off.

How accurate it is:

- **Loads at an interface** (a payload, a joint force, a motor) give exact static stress: the constraint modes span them. The tool checks this against the full model (round-off for the bracket).
- **Distributed loads** (the part's own inertia when its frame accelerates, gravity) converge with the number of fixed-interface modes. The tool prints the peak error per self-weight case (under 2 % for the bracket with 4 modes). Add modes if a hotspot that matters is off.
- **Sharp inside corners** are stress singularities: the value there grows as the mesh gets finer. Model the fillet, or judge the design by a hotspot a little away from the corner.
- The stress is linear elastic. It leaves out the second-order (stiffening) strain, contact stress and stress concentrations finer than the mesh.

In the 3D view, the **stress** option of the mode-shapes binding colours every vertex of the GLB by its von Mises stress, with a colormap and a range in MPa. The colours come from the true η, so the deformation exaggeration does not change them. A GLB written before this feature has no stress table: re-run the reduction. Example **fem-bracket** shows both the outputs and the colouring.

### A carriage on a rail

A carriage that slides along the part, like the Y carriage on a gantry beam or a block on a linear guide, is not a fixed interface: where it loads the part changes as it moves. Give the part spec a `rail`:

```json
"rail": {
  "name": "Y rail", "start": [0.03, 0.15, 0.05], "end": [0.03, 1.25, 0.05], "normal": [1, 0, 0],
  "footprint": {"half_length": 0.05, "select": {"box": {"min": [0.0299, -1, 0.02], "max": [0.0301, 2, 0.08]}}},
  "load_modes": [0.25, 0.5, 0.75]
}
```

- **start**, **end**: the rail line on the part (part coordinates). The rail coordinate `s` runs from 0 at `start` to the rail's length at `end`.
- **normal**: the outward normal of the mounting face. It is the x axis of the rail frame. The z axis runs along the rail, and y = z × x.
- **footprint**: the nodes of the mounting face that the guide block rests on (`select`), and how far along the rail a block reaches (`half_length`). At each of `stations` points along the rail (default 41) the tool fits a rigid motion of each mode over those nodes, which is how the block's bearing pads follow the face. It then fits a smooth series in `s` to that (`chebyshev` terms, default 20) and prints the fit error.
- **load_modes**: points along the rail, as fractions of its length. At each one the tool adds three static responses to the basis: a force across the rail in both directions and a moment about it. A carriage load at those points is then exact, and in between it is interpolated. Without them only the vibration modes carry the load (about 97 % of a mid-span beam deflection with one mode).

The block gets two more ports. **`E`** is the carriage frame, riding on the deformed rail at `s` (its world pose is `poseE`). Attach the carriage there with a `Prismatic3D` (`E → parent`) whose axis is held by a stiff drive spring. The joint's other five directions are the guide's stiffness. **`S`** is the slide, a translation port whose flow is `ṡ`. Put the drive force on it, for example a `ForceSource` with its other side on `Fixed` and a servo on `s` and `sd`. That force acts between the part and the carriage: the carriage gets it, and the part gets the reaction at E. `ms` is the slide's own mass along the rail. Keep it small against the carriage. The frame at E includes the rail's own deformation as the carriage moves over it, and the coupling is power-continuous: undamped, the energy of the part, the slide, the carriage and the springs is conserved.

The tool checks the rail against the full finite element model: unit loads at seven points along the rail, full against reduced (printed, and in the file's `validation.rail`). For the gantry beam of example **fem-gantry** the forces across the rail are within 1.5 % between the load-mode points and exact at them. The moment about the rail bends the mounting wall locally, so it is exact only at the load-mode points and up to 27 % low between them. Add load-mode points where the carriage spends its time. The inspector's **Reduced model** section shows the rail and its length.

### Limits

- Linear elastic, isotropic material and small elastic strain. The overall motion can be large (the floating frame is exact), the deformation relative to it must stay small, and so must the elastic rotations: a long thin shaft twisted by 16° rings 0.7 % too high (example **fem-torsion**), at 1.6° the error is gone.
- Geometric stiffening is first order: the part stiffens by its rotation (centrifugal), by gravity and by forces at the interfaces, not by the acceleration of its reference frame, by interface moments or by other distributed loads. With stiffening on, keep the elastic deflection small against the part (well under 1 % of its size for a light part); a very soft, light part with large deflections should run with stiffening off.
- No plasticity or contact on the part's surface. Stress is linear elastic, at the named hotspots and the peak candidates (and per vertex in the 3D view), not a full field you can query anywhere in the simulation.
- One straight rail per part, with one carriage on it. The carriage follows the rigid fit of its footprint, not the face's waviness under each pad. The load along the rail (the drive force) has no load modes: the vibration modes and the interfaces carry it.

## For library authors

A composite block can pass its constants to a child as keyword arguments (`ModalBeam3D(ny = ny, ...)`), and `@observables` can expose a child's vector signals under the names of the composite's own outputs. Each entry is recorded as `Block/name[k]`.
