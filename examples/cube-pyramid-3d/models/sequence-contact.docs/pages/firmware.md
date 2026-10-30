# Firmware (D28)

[Seq](block:Seq) (`TipSequencer`, 1 ms) produces the body torque $T$ from the cube pose (it only uses the world vertical seen from the body, $u = R^T e_z$) and the twist. With the pivot lever $r$ (face: none; edge: $r = (0, a/2, a/2)$; corner: $r = (a/2, a/2, a/2)$) it applies gravity compensation, which makes the cube a free rotor about the contact feature, plus a saturated attitude feedback and a gyroscopic decoupling term from the measured wheel speeds $h$:

$$T = m\,g\,(r \times u) + \operatorname{sat}\big(K_p\,(u_{ref} \times u) + K_d\,(w_{ref} - w_\perp) - K_y\,(w\cdot u)\,u\big) + w \times h .$$

with $K_p = 5$ N·m, $K_d = 1.2$ N·m·s, $K_y = 0.05$ N·m·s and the feedback limited to $f_{b,max} = 0.8$ N·m. The reference $u_{ref}$ moves by a minimum-jerk blend from $(0, 0, 1)$ to $(0, 1, 1)/\sqrt2$ (edge) and on to $(1, 1, 1)/\sqrt3$ (corner). The model sets `t1` = 0.5 s and `t2` = 2.3 s, so:

| phase | `Seq/ph` | interval |
| --- | --- | --- |
| face | 0 | until 0.5 s |
| edge move | 1 | 0.5 to 1.15 s |
| edge hold | 2 | to 2.3 s |
| corner move | 3 | 2.3 to 3.15 s |
| corner hold | 4 | to 4.5 s |

[Alloc](block:Alloc) (`Allocator`, 1 ms) turns $T$ into the motor currents with the minimum-norm allocation plus a free null-space term,

$$\tau = -A^{+}\,T + \lambda\,n, \qquad n = \tfrac12 (1, -1, 1, -1), \qquad \lambda = 0.005\ \mathrm{N\,m},$$

and scales the body-torque request (never the null-space term) so that no wheel exceeds 1.2 N·m (`tau_max`; `Alloc/sat` is the scale factor).
