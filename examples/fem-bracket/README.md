# fem-bracket — a FEM bracket with a payload on a turntable

A part that is not a beam, as a flexible body reduced from a finite element model. An aluminium L-bracket (base plate 120 × 40 × 5 mm, upright 40 × 4 × 150 mm) carries a 0.5 kg payload (a 40 mm steel cube) on a turntable that indexes 90° and back. The upright is thin along the table's tangential direction, so each move bends it and the payload rings afterwards.

```
World ─ Table (Revolute3D, speed servo) ─ Hub ─ Seat ─ Bracket (ModalBody3D) A … B ─ Clamp ─ Payload
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

## Models

- **fem-bracket**: the turntable. A speed source drives the table through a stiff spring and damper (a servo at about 60 Hz, ζ = 0.7) with two jerk-limited moves (+90° at 0.2 s, back at 1.6 s; 8 rad/s, 80 rad/s²). Gravity on. The payload rings at the first bracket mode after each move.
- **bracket-ringdown**: the bracket clamped at A, the payload given a velocity at t = 0, no gravity and no damping. The FFT peaks of the payload velocity are checked against the full-model frequencies with the payload.

## 3D view

| binding | signal |
| --- | --- |
| `link:hub` pose (turntable only) | `PHub/g` |
| `link:bracket` pose | `Bracket/pose` (interface A) |
| `link:payload` pose | `PPayload/g` (deformed interface B + 20 mm) |
| `visual:bracket_mesh` mode-shapes | `Bracket/eta[1..10]` |

The deflections are a fraction of a millimetre; set the deformation exaggeration to 50 or more to see the upright swing.

## Checks (`expected.json`)

- fem-bracket: no E101/E102/E108/W201/W202; the scene bindings resolve (10 morph targets); the table reaches 90° and returns to 0; the payload rings near the first clamped mode after the first move.
- bracket-ringdown: FFT peaks of `Payload/V[5]` and `Payload/V[4]` against the full FE model with the payload (0.3 %).

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
