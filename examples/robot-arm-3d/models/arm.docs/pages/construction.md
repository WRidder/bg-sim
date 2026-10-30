# Construction

- **Joints** ([J1](block:J1) to `J6`). `Revolute3D` rotates exactly about the local $z$ of its joint frame; the other five directions are compliant ($k_t = k_r = 10^7$ N/m and N·m/rad), so every state stays integral (no W201). The held-direction damping is 0.7 of critical for the distal mass (translations) and for a 0.3 kg·m² reference inertia (rotations), so the stiff modes die in milliseconds.
- **Geometry.** Joint $i+1$ sits at the standard-DH fixed part $T_z(d)\,T_x(a)\,R_x(\alpha)$ of link $i$ (UR5-like):

| link | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| $d$ (m) | 0.0892 | 0 | 0 | 0.1092 | 0.0947 | 0.0823 |
| $a$ (m) | 0 | -0.425 | -0.392 | 0 | 0 | 0 |
| $\alpha$ | $\pi/2$ | 0 | 0 | $\pi/2$ | $-\pi/2$ | 0 |
| mass (kg) | 3.7 | 8.4 | 2.3 | 1.2 | 1.2 | 0.74 |

  The body 1-junction frame is the link's centre of mass ([B1](block:B1) has $m = 3.7$ kg, $J = (0.0103, 0.0103, 0.0067)$ kg·m²), so the next joint offset is $N - c_i$ in that frame ([T2](block:T2) to `T6`).
- **Drives.** One `MSe` torque source per joint ([D1](block:D1) to `D6`) on the joint's `Rotation` drive port, fed by the controller. A flow source cannot impose the joint motion (derivative causality, W201), so the joints are torque driven.
- **Poses** are composed, never integrated: $W_i = W_{i-1} \circ LN_i \circ J_i.\text{pose}$, the body pose is $W_i \circ LC_i$ (it feeds `B_i.g`, which gravity reads), and the tool centre point is $W_6 \circ L_{tool}$ with a $0.0823 + 0.1 = 0.1823$ m flange-plus-tool offset along the flange $z$.
- **Start.** The arm is released at rest at the home pose $q = (0, -1.2, 1.2, -1.5, -1.5, 0)$ on its **consistent deflections** (the `starts` of `dth`, `dl` from the independent Newton-Euler reference), so the held directions carry the static gravity load from $t = 0$ and the start does not excite the stiff modes.
