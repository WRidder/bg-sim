# fem-bracket — a FEM bracket with a payload on a turntable

A part that is not a beam, as a flexible body reduced from a finite element model. An aluminium L-bracket (base plate 120 × 40 × 5 mm, upright 40 × 4 × 150 mm) carries a 0.5 kg payload (a 40 mm steel cube) on a turntable that indexes 90° and back. The upright is thin along the table's tangential direction, so each move bends it and the payload rings afterwards.

```
World ─ Table (Revolute3D, speed servo) ─ Hub ─ WeldA ─ Seat ─ Bracket (ModalBody3D) A … B ─ WeldB ─ Offset ─ Payload
```

## The reduced model

`design/bracket.fem.json` builds the bracket from two boxes (CSG) and names two interfaces: **A**, the bolted area of the base plate (the body's reference frame), and **B**, the top face of the upright under the payload clamp. `julia/BGSimFEM` meshes it with quadratic tetrahedra (13 116 nodes, 39 348 DOFs) and reduces it by Craig–Bampton to 4 fixed-interface modes plus the 6 constraint modes of B (10 coordinates, stiffening matrices included). It writes `data/bracket.modal.json` and `meshes/bracket.glb` (the surface, 1228 vertices, one morph target per mode).

Validation printed by the tool (and stored in the file):

| configuration | full FE model | reduced model |
| --- | --- | --- |
| clamped at A, first 4 modes | 121.256, 156.132, 773.196, 978.811 Hz | 121.264, 156.171, 774.150, 989.408 Hz |
| free-free, first 4 modes | 605.712, 724.313, 1092.21, 1407.70 Hz | 606.026, 725.342, 1096.13, 1422.83 Hz |
| clamped at A, **0.5 kg payload at B** | 18.5719, 30.8750, 170.964, 264.890 Hz | 18.5719, 30.8750, 170.965, 264.902 Hz |

The largest error below the accuracy band (2976 Hz, 80 % of the first fixed-interface mode it left out) is 1.1 % clamped and 2.7 % free. With the payload on interface B the first modes agree to 5e-5: the constraint modes make the static response to a load at an interface exact.

## Stress

The part spec names two stress hotspots on the upright's face (y = +2 mm): **upright 30 mm**, 25 mm above the plate where beam theory holds, and **upright root**, on the sharp re-entrant corner where the upright meets the plate. The tool adds 24 peak candidates, so `Bracket/sigma_max` tracks the peak over the part. Every mode carries its stress field (element-wise recovery at the nodes, averaged), so the stress anywhere is Σ σ_k η_k, with von Mises taken of the sum.

Static load cases on the full FE model, interface A clamped, against the reduced model (from `validation.stress` in the file):

| load case | full FE peak von Mises | reduced | error | upright 30 mm (full / reduced) |
| --- | --- | --- | --- | --- |
| 1 N along y at B | 1.9615 MPa | 1.9615 MPa | 4e-10 | 1.1088 / 1.1088 MPa |
| 1 N along x at B | 1.4954 MPa | 1.4954 MPa | 7e-11 | 0.0287 / 0.0287 MPa |
| 1 N·m about x at B | 12.943 MPa | 12.943 MPa | 7e-10 | 8.935 / 8.935 MPa |
| self weight along y | 0.6294 MPa | 0.6297 MPa | +0.05 % | 0.2926 / 0.2944 MPa (+0.6 %) |
| self weight along x | 0.4834 MPa | 0.4753 MPa | −1.7 % | 0.0116 / 0.0100 MPa |
| self weight along z | 0.3154 MPa | 0.3094 MPa | −1.9 % | 0.0049 / 0.0072 MPa |

Loads at an interface are exact (round-off), because the constraint modes span their static response. A distributed load (self weight, the part's own inertia) converges with the number of fixed-interface modes: four modes give the peak within 2 %, while a hotspot that carries almost no stress in that case can be off by much more in relative terms (the axial self weight at 30 mm: 4.9 kPa against 7.2 kPa). Over 400 random load states, the largest von Mises at the 26 points is on average 99.8 % of the surface peak (98.8 % of the states within 5 %, the worst 86 %).

Beam theory: 1 N along y at B bends the upright with M = F (155 − 30) mm at the 30 mm hotspot, σ_zz = M c / I = 1.172 MPa (c = 2 mm, I = 40 · 4³ / 12 mm⁴). The reduced model gives σ_zz = −1.161 MPa there (0.9 %). Its von Mises is 1.109 MPa, lower, because the wide upright is partly in plane strain (σ_xx ≈ 0.1 σ_zz). The peak (1.96 MPa) sits on the re-entrant corner at the upright's edge (x = 80 mm), 1.4 times the beam-theory root stress. A sharp corner is a stress singularity, so this value grows with mesh refinement. Model a fillet if the peak matters, and judge a sharp design by a hotspot away from the corner.

In the ring-down the stress outputs are checked against a linear modal superposition of the reduced model with the payload rigid at B (computed in `design/build.py`, without BGSim). Over the first swing (30 ms) the reference gives 8.20 MPa at upright 30 mm, 4.71 MPa at the root and 21.7 MPa peak; the simulation gives 8.08, 4.68 and 21.6 MPa (−1.5 %, −0.6 %, −0.2 %). The check stops at 30 ms because the reference is undamped, while the clamp and the welds damp the higher modes (171 Hz and up) that later beat with the first ones. As a sanity check, beam theory gives σ_zz ≈ 7.9 MPa at 30 mm from the payload's inertia force alone (F = m ω v = 5.8 N).

## Models

- **fem-bracket**: the turntable. A speed source drives the table through a stiff spring and damper (a servo at about 60 Hz, ζ = 0.7) with two jerk-limited moves (+90° at 0.2 s, back at 1.6 s; 8 rad/s, 80 rad/s²). Gravity on. The payload rings at the first bracket mode after each move.
- **bracket-ringdown**: the bracket clamped at A, the payload given a velocity at t = 0, no gravity and no damping. The FFT peaks of the payload velocity are checked against the full-model frequencies with the payload.

## 3D view

| binding | signal |
| --- | --- |
| `link:hub` pose (turntable only) | `PHub/g` |
| `link:bracket` pose | `Bracket/pose` (interface A) |
| `link:payload` pose | `PPayload/g` (deformed interface B + 20 mm) |
| `visual:bracket_mesh` mode-shapes, stress colouring | `Bracket/eta[1..10]`, von Mises 0 to 20 MPa (heat) |

The deflections are a fraction of a millimetre, so both models open the 3D view with the deformation drawn ×100 (`"exaggeration": 100` in the model's `scene`; the view marks it as exaggerated). The mesh is coloured by its von Mises stress, recovered at every visual vertex from the true modal coordinates (the exaggeration does not change the colours).

## Checks (`expected.json`)

- fem-bracket: no E101/E102/E108/W201/W202; the scene bindings resolve (10 morph targets, the stress table); the table reaches 90° and returns to 0; the payload rings near the first clamped mode after the first move; the peak stress stays below half the yield strength.
- bracket-ringdown: FFT peaks of `Payload/flow/y[5]` and `Payload/flow/y[4]` against the full FE model with the payload (0.3 %); the largest `Bracket/sigma_vm[1]`, `sigma_vm[2]` and `sigma_max` against the modal superposition (2 %).

## Files

| file | content |
| --- | --- |
| `design/bracket.fem.json` | the part spec for BGSimFEM (geometry, material, mesh, interfaces, modes, payload for the validation) |
| `design/build.py` | uv script: writes both models, the scenes and `expected.json` from the reduced model |
| `data/bracket.modal.json` | the reduced model (written by BGSimFEM) |
| `meshes/bracket.glb` | the bracket surface with one morph target per mode (written by BGSimFEM) |
| `models/*.bgmodel.json`, `models/*.docs` | the models and their documentation |
| `scenes/*.sdf` | the scenes |

Rebuild:

```
julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl examples/fem-bracket/design/bracket.fem.json
uv run examples/fem-bracket/design/build.py
uv run examples/run_checks.py --only fem-bracket
```
