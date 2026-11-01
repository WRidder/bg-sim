# Two disks on a FEM shaft

Two steel disks (m = 3.157 kg, axial inertia J = 0.010101 kg·m²) sit on a slender aluminium shaft (d = 6 mm, L = 1 m) that hangs from a bearing. [Motor](block:Motor) gives the upper disk a 1 N·m torque pulse of 0.1 s, driven by [Pulse](block:Pulse). The disks then spin and twist against each other.

This is the rig of the **flex-torsion** example, with one change: the [Shaft](block:Shaft) is a `ModalBody3D`, a flexible body reduced from a finite element model, instead of the assumed-modes beam `FlexibleBeam3D`.

## The shaft as a reduced FEM model

The part spec `design/shaft.fem.json` describes the shaft as a cylinder (E = 70 GPa, ν = 0.33, ρ = 2700 kg/m³). The offline tool `julia/BGSimFEM`:

1. meshes it with quadratic tetrahedra (2 mm elements, 208 098 DOFs);
2. ties the nodes of each end face rigidly to a 6-DOF interface frame: A at the top (the reference frame of the body) and B at the bottom;
3. reduces it by **Craig–Bampton**: 4 vibration modes with both ends clamped, plus 6 **constraint modes**, the static shapes for a unit motion of each DOF of interface B. The 10 shapes are then orthogonalised, so the block has 10 modal coordinates `eta` with diagonal modal mass and stiffness.

The node's **Reduced model** setting points at the result, `data/shaft.modal.json`. The mass properties, the inertia invariants, the interface mode values and the geometric-stiffening matrices all come from that file.

## Why it is more accurate

With heavy disks at both ends, the shaft twists almost linearly along its length. The assumed-modes beam builds its twist from sine shapes with zero slope at the free end, and three of them still miss 7 % of the static twist under an end torque. That makes it 3.5 % too stiff (4.242 Hz instead of 4.098 Hz). One of the constraint modes is exactly the static twist under a torque at B, so the FEM shaft has the right stiffness: 3.3482 N·m/rad against G I_p / L = 3.3483 N·m/rad.

## What the run shows

- [Twist/y](signal:Twist/y) is the twist of interface B relative to A. It rings at the exact frequency of the shaft with end inertias, 25.7475 rad/s (4.0978 Hz).
- [Shaft/eta[9]](signal:Shaft/eta[9]) is the torsion coordinate (m: the largest displacement in the mode, here on the shaft surface). The other coordinates are bending and axial modes; the symmetric torque pulse barely moves them.
- [Shaft/f[1]](signal:Shaft/f[1]) and the other `f` entries are the modal frequencies of the shaft alone, clamped at A.
- [Bearing/qout](signal:Bearing/qout) is the upper disk's angle.

In the 3D view, the shaft mesh (`meshes/shaft.glb`) is deformed by all 10 modal coordinates through a mode-shapes binding. Use the deformation exaggeration to see the bending (the twist shows on the disk markers).
