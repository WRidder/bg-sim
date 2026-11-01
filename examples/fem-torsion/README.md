# fem-torsion — two disks on a FEM shaft

The rig of [flex-torsion](../flex-torsion/README.md) with the shaft as a **FEM flexible body**. Two steel disks on a slender aluminium shaft (d = 6 mm, L = 1 m) hang from a bearing. A 0.1 N·m motor torque pulse of 0.1 s on the upper disk sets the pair spinning and twisting against each other (by up to 0.029 rad, 1.6°).

```
World ─ Bearing (Revolute3D, motor torque) ─ Disk1 ─ Weld1 ─ Mount ─ Shaft (ModalBody3D) ─ Weld2 ─ Disk2
```

The shaft is not a beam block here. `design/shaft.fem.json` describes it as a cylinder; `julia/BGSimFEM` meshes it with quadratic tetrahedra (69 366 nodes, 208 098 DOFs), ties the two end faces rigidly to the interfaces A and B, and reduces it by Craig–Bampton to 4 fixed-interface modes plus the 6 constraint modes of B. The model reads the result, `data/shaft.modal.json`, and the 3D view deforms `meshes/shaft.glb` with the 10 modal coordinates.

## Why: the static correction

In flex-torsion, the assumed-modes beam (`FlexibleBeam3D`, 3 clamped-free torsion modes) rings 3.5 % too high. With heavy disks at both ends the shaft twists almost linearly, and a sine series with zero end slope converges slowly to that shape. The Craig–Bampton basis contains the static response to a torque at B (a constraint mode), so the linear twist is in the basis exactly.

| quantity | value |
| --- | --- |
| exact first torsional frequency (transcendental root, μ = 29404) | 25.7475 rad/s, **4.0978 Hz** |
| assumed modes, 3 torsion modes (flex-torsion) | 26.655 rad/s, 4.2423 Hz (+3.53 %) |
| FEM shaft: torsional stiffness from the reduced model / G I_p / L | 3.3482 / 3.3483 N·m/rad (−0.004 %) |
| FEM shaft: two-inertia frequency with that stiffness | 25.7471 rad/s (−0.002 %) |
| FFT of `Twist/y` (simulation) | see `expected.json` (checked to 0.4 % of the exact root) |

The reduction also checks itself against the full FE model (printed by the tool, stored in the file's `validation`): the clamped bending frequencies 4.2754 / 26.790 / 74.999 Hz are matched to 0.37 %, the free-free ones to 0.44 %.

The pulse is a tenth of flex-torsion's. With 1 N·m the twist reaches 0.29 rad (16°) and the simulated frequency comes out 0.7 % high: the reduced model's displacement field is linear in its coordinates, and although the interface rotation uses an exact chart (Gibbs vector, as in the beam blocks), a 16° rotation of the end face is no longer a small deformation. Keep the elastic rotations of a FEM body to a few degrees.

`Twist/y` is the twist of interface B relative to A: the torsion coordinate `Shaft/eta[9]` (the mode with the largest rotation of B about the shaft axis) times its rotation per unit coordinate, 333.3 rad/m (`EtaT` selects it, `Twist` scales it).

## 3D view

| binding | signal |
| --- | --- |
| `link:disk1` pose | `PDisk1/g` |
| `link:shaft` pose | `Shaft/pose` (the reference frame, interface A) |
| `link:disk2` pose | `PDisk2/g` |
| `visual:shaft_mesh` mode-shapes | `Shaft/eta[1..10]` |

## Checks (`expected.json`)

- no E101/E102/E108/W201/W202 diagnostics; all scene bindings resolve (the GLB has 10 morph targets)
- FFT peak of `Twist/y` against the exact root (0.4 %, the assumed-modes value is outside)
- the largest twist is 0.0287 rad (5 %)

## Files

| file | content |
| --- | --- |
| `design/shaft.fem.json` | the part spec for BGSimFEM |
| `design/build.py` | uv script: writes the model, scene and `expected.json` from the reduced model |
| `data/shaft.modal.json` | the reduced model (written by BGSimFEM) |
| `meshes/shaft.glb` | the shaft surface with one morph target per mode (written by BGSimFEM) |
| `models/fem-torsion.bgmodel.json`, `models/fem-torsion.docs` | the model and its documentation |
| `scenes/fem-torsion.sdf` | frame, disks and the shaft mesh |

Rebuild:

```
julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl examples/fem-torsion/design/shaft.fem.json
uv run examples/fem-torsion/design/build.py
uv run examples/run_checks.py --only fem-torsion
```
