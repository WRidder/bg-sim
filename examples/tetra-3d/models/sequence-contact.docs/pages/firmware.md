# Firmware (1 ms, D28)

## Sequencer

[Seq](block:Seq) (`TipSequencer`, the law of the cube sequencer adapted to the tetrahedron). Gravity compensation about the current pivot lever $r = \mathrm{CoM} - \mathrm{pivot}$ (edge: $(0, \rho/2, r)$, vertex: $(-L/2, \rho/2, r)$) makes the body a free rotor about the contact feature,

$$T_{ff} = m\,g\;(r \times u),$$

plus a saturated attitude feedback and a gyroscopic decoupling term from the measured wheel speeds $h$:

$$T = T_{ff} + K_p\,(u_{ref} \times u) + K_d\,(w_{ref} - w_\perp) - K_y\,(w\cdot u)\,u + w \times h, \qquad K_p = 5,\ K_d = 1.2,\ K_y = 0.05,$$

with the feedback limited to $f_{b,max} = 0.8$ N·m. The reference $u_{ref}$ moves by a minimum-jerk blend. Phase times:

| phase | `Seq/ph` | times |
| --- | --- | --- |
| face | 0 | until 0.4 s |
| edge move | 1 | compensation ramp 0.15 s, move 0.55 to 1.05 s |
| edge hold | 2 | to 1.9 s |
| vertex move | 3 | lever ramp 1.9 to 2.05 s, move 2.05 to 2.75 s |
| vertex hold | 4 | to 3.8 s |

## Allocator

[Alloc](block:Alloc) (`Allocator`, 1 ms) uses the minimum-norm allocation plus a free null-space term,

$$\tau = -\tfrac34\,A^T\,T + \lambda\,n, \qquad \lambda = 0.005\ \mathrm{N\,m},$$

and scales the *body-torque request* (never the null-space term) so no wheel exceeds **1.6 N·m** (`Alloc/sat` is the scale factor; it stays 1 in this run). The edge-to-vertex lift needs about $m g L/2 = 1.7$ N·m of body torque just to start (the weight acts at the distance $L/2$ from the vertex), so the limit is larger than the 1.2 N·m of the cube; the allocator capacity along the worst axis is $1.6\,\sum\lvert a_k\cdot d\rvert \ge 2.6$ N·m.

## Sensors

[Sense](block:Sense) (`TetraSense`: attitude errors to the two balance directions, CoM position, loaded-vertex count, normal-force sum, quaternion norm), [Tap](block:Tap) (`WheelTap`: measured motor torques, null-space tap), `BodyEnergy` ([EnBody](block:EnBody) and `EnW_k`) and [Ledger](block:Ledger) (dissipated contact energy, motor input work, shaft and rotor energy, motor terminal voltage).

## Design script

`design/design.py` holds the geometry, prints the targets and runs a numpy replica of the closed loop (hinge about the edge, then a ball joint at $v_3$, ideal motors, the same firmware) that was used to pick the edge length, the torque limit and the timing: with the 1.4 kg of the cube and $L = 0.30$ m the vertex lift saturated 1.2 N·m wheels and failed; $L = 0.25$ m with 1.6 N·m works. `design/build_model.py` writes the model, the scene and `meshes/tetra.glb`.
