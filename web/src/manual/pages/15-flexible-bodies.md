# Flexible bodies

A slender rod, tube or bar that bends and twists can replace a rigid body in a multibond model. `FlexibleBeam2D` (in the **Planar** category) and `FlexibleBeam3D` (in **Spatial**) use the **assumed-modes method**: the beam has a floating reference frame that carries its rigid motion, and up to three elastic modes per family are added on top of it. The beam's own mass and rotational inertia are inside the block, so do not add a rigid body for the rod.

## Blocks

| Block | Ports | Families | Replaces |
| --- | --- | --- | --- |
| `FlexibleBeam2D` | `A`, `B` (planar), input `gA` (pose of end A) | in-plane bending `y` | `RigidBody2D` |
| `FlexibleBeam3D` | `A`, `B` (spatial), input `gA` (pose of end A) | bending `y`, bending `z`, torsion `t` | `RigidBody3D` |

`ModalBeam2D` and `ModalBeam3D` are the cores of these blocks, with the modal bond graph and the equations. Use the `FlexibleBeam` blocks in models: their ends are 1-junctions, so they bond like a body port in either bond direction.

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

Bind the block's `pose` to the link that holds the beam's visual. Then add one **deformation** binding per family with the signals `eta_y[1..ny]`, `eta_z[1..nz]` or `eta_t[1..nt]` and the same `basis` as the block (see [Running and plotting](page:running-and-plotting)). The beam axis of the binding is the visual's direction from end A to end B. Real deflections are small; use the view's deformation exaggeration to see them.

## Examples

- **cantilever-modes**: the same method by hand, as a scalar bond graph. Each mode is a 1-junction with I, C and R, coupled to the tip by a TF with modulus |φ_n(L)| = 2. All element values are global parameters.
- **flex-torsion**: two disks on a 1 m shaft with three torsion modes. The twist is checked against the exact frequency equation and the massless-shaft limit.
- **flex-rotary-pendulum**: a Furuta pendulum with a bending rod (2 + 2 modes), next to its rigid twin.
- **pendulum-triple-rotary** (models `-flex`, `-flex-lowpass`, `-flex-free`): the rotary triple inverted pendulum with a flexible arm, a 3 x 50 mm steel strip (2 + 2 bending modes, 1 torsion mode). The rigid arm's controller drives the arm's first bending mode unstable. A controller designed with a 12 Hz low-pass in the loop balances the pendulum. The first mode is checked against the exact frequency equation, with the hinged pendulum chain as the tip load.

## For library authors

A composite block can pass its constants to a child as keyword arguments (`ModalBeam3D(ny = ny, ...)`), and `@observables` can expose a child's vector signals under the names of the composite's own outputs. Each entry is recorded as `Block/name[k]`.
