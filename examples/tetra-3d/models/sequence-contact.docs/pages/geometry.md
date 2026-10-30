# Geometry

Body frame: origin = centre of mass = centre of the circumscribed sphere, $z$ up when the body rests on its base face. With the circumradius $R = L\sqrt6/4 = 0.15309$ m, the inradius $r = R/3 = 0.05103$ m (the face-centroid distance) and $\rho = L/\sqrt3 = 0.14434$ m (circumradius of the base triangle):

| vertex | body frame |
| --- | --- |
| $v_1$ | $(0,\ \rho,\ -r)$ |
| $v_2$ | $(-L/2,\ -\rho/2,\ -r)$ |
| $v_3$ | $(+L/2,\ -\rho/2,\ -r)$ |
| $v_4$ (apex) | $(0,\ 0,\ R)$ |

Vertices 1 to 3 form the base face; the `ContactPoint` `C_k` sits on vertex $k$ ([Mount1](block:Mount1), [Local1](block:Local1) hold the vertex position).

## Wheels

Wheel $j = 1..3$ sits on the side face opposite to base vertex $v_j$ with axis $a_j = -v_j/R$; wheel 4 sits on the base face with $a_4 = (0, 0, -1)$:

$$a_1 = (0, -\kappa, \tfrac13), \quad a_2 = (c, \tfrac\kappa2, \tfrac13), \quad a_3 = (-c, \tfrac\kappa2, \tfrac13), \quad a_4 = (0, 0, -1), \qquad \kappa = \tfrac{2\sqrt2}{3},\ c = \tfrac{\sqrt6}{3}.$$

The four normals sum to zero, so with $A = [a_1\ a_2\ a_3\ a_4]$ ($3 \times 4$) $A A^T = \tfrac43 I$ (any three wheels are independent), $A^{+} = \tfrac34 A^T$, and the null direction is $A n = 0$ for $n = \tfrac12 (1, 1, 1, 1)$: the fourth wheel is the redundant one the allocator uses for its null-space term. Each wheel frame has its $z$ axis along $a_k$ ([WMount1](block:WMount1), [WLocal1](block:WLocal1) carry the quaternion and the offset $d\,a_k$ with $d = 35$ mm).

## Mass and inertia

| part | mass | inertia about its own centre |
| --- | --- | --- |
| tetrahedron | 0.4 kg | solid regular tetrahedron, isotropic: $J = m L^2/20 = 1.25\cdot10^{-3}$ kg·m² |
| each wheel (4) | 0.25 kg | $J = (10^{-3}, 10^{-3}, 2\cdot10^{-3})$ kg·m² (axis $z$); rotor $J_m = 10^{-8}$ behind an elastic shaft $k = 100$, $d = 2\cdot10^{-3}$ |
| total | 1.4 kg (weight 13.734 N) | centre of mass at the body centre (the wheel offsets sum to zero); inertia without the wheel spin $4.73\cdot10^{-3}$ kg·m² on all axes |

The wheel inertia is the one of the cube example: a 0.25 kg wheel of $J = 2\cdot10^{-3}$ kg·m² would be 0.126 m wide, the inertia of a rim-heavy flywheel; the 3D scene draws smaller discs (0.04 m radius). Motors: `CurrentControlledDrive` with $k_t = 0.1$ N·m/A and winding resistance $R_m = 0.4\ \Omega$, so the terminal voltage is $R_m\,i + k_t\,\omega$ ([Ledger/v1](signal:Ledger/v1) to `v4`) with a 48 V supply in mind.

## Contacts

$k = 2\cdot10^4$ N/m at $x_{ref} = 1$ mm (Hertz exponent 3/2), $c = 5$ s/m, $\mu = 0.8$, $v_s = 1$ mm/s. Resting on three vertices each sinks 0.374 mm (the start height is $r - 0.374\ \mathrm{mm} = 0.050657$ m).

## Target attitudes

The firmware sees only $u = R^T e_z$, the world vertical in the body frame (the yaw about the vertical is free and damped).

| phase | contact set | $u$ (body frame) | tilt $\arccos u_z$ | CoM height |
| --- | --- | --- | --- | --- |
| face | $v_1 v_2 v_3$ | $(0, 0, 1)$ | 0 | $r = 0.05103$ m |
| edge | $v_2 v_3$ | $-(v_2 + v_3)/\lvert v_2 + v_3\rvert = (0, \sqrt{2/3}, 1/\sqrt3)$ | 54.7356 deg | $L/(2\sqrt2) = 0.08839$ m |
| vertex | $v_3$ | $-v_3/R = (-\sqrt{2/3}, \sqrt2/3, \tfrac13)$ ($= a_3$) | 70.5288 deg | $R = 0.15309$ m |

At the edge balance the CoM is above the edge midpoint $(0, -\rho/2)$; at the vertex balance it is above $v_3$, world position $(L/2, -\rho/2) = (0.125, -0.07217)$ m. The angle between the two balance directions is 54.74 deg.
