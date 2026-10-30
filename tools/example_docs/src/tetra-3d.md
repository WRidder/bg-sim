@@ figures sequence-contact
{
  "diagram": {"kind": "diagram", "model": "sequence-contact"},
  "face": {"kind": "scene", "model": "sequence-contact", "t": 0},
  "edge": {"kind": "scene", "model": "sequence-contact", "t": 1.6},
  "vertex": {"kind": "scene", "model": "sequence-contact", "t": 3.4},
  "run": {
    "kind": "plot", "model": "sequence-contact", "xlim": [0, 3.8],
    "rows": [
      {"ylabel": "angle to balance dir. [deg]", "series": [{"signal": "Sense/ang_edge", "label": "to edge balance", "scale": 57.29577951308232}, {"signal": "Sense/ang_vert", "label": "to vertex balance", "scale": 57.29577951308232, "style": "--"}], "ylim": [0, 90], "legend": true},
      {"ylabel": "phase Seq/ph [-]", "series": [{"signal": "Seq/ph", "label": "Seq/ph", "color": "#444444"}]},
      {"ylabel": "vertex normal force [N]", "series": [{"signal": "C1/f_n", "label": "C1"}, {"signal": "C2/f_n", "label": "C2"}, {"signal": "C3/f_n", "label": "C3"}, {"signal": "C4/f_n", "label": "C4 (apex)"}], "legend": true},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "WJoint1/qdout", "label": "wheel 1"}, {"signal": "WJoint2/qdout", "label": "wheel 2"}, {"signal": "WJoint3/qdout", "label": "wheel 3"}, {"signal": "WJoint4/qdout", "label": "wheel 4"}], "legend": true, "legend_loc": "upper left"}
    ]
  },
  "height": {
    "kind": "plot", "model": "sequence-contact", "xlim": [0, 3.8],
    "rows": [
      {"ylabel": "CoM height Sense/zc [m]", "series": [{"signal": "Sense/zc", "label": "Sense/zc"}], "hlines": [{"y": 0.15309, "label": "vertex R = 0.15309 m"}, {"y": 0.08839, "label": "edge L/(2 sqrt 2) = 0.08839 m"}, {"y": 0.05103, "label": "face r = 0.05103 m"}], "legend": true, "legend_loc": "center left"},
      {"ylabel": "motor terminal voltage [V]", "series": [{"signal": "Ledger/v1", "label": "motor 1"}, {"signal": "Ledger/v2", "label": "motor 2"}, {"signal": "Ledger/v3", "label": "motor 3"}, {"signal": "Ledger/v4", "label": "motor 4"}], "hlines": [{"y": 48, "label": "supply 48 V"}], "legend": true, "legend_loc": "upper left"}
    ]
  }
}
@@ page sequence-contact overview - | Overview
# Tetrahedron with four face wheels: face, edge, vertex

A free **regular tetrahedron** (edge $L = 0.25$ m) lies on its base face on a ground plane. A **reaction wheel is tied to each of its four faces**: the spin axis is the outward normal of the face and the wheel sits inside the body 35 mm from the centre of mass towards the face centroid. A scripted torque profile spins the wheels so that the body leaves its **face**, balances on an **edge** (two contacts) and then on a single **vertex** (one contact). The ground is a compliant `ContactSurface` and every vertex is a `ContactPoint` (Hunt-Crossley normal force, regularised Coulomb friction), so the phases are *emergent*: which vertices carry load follows from the contact forces; nothing is switched by hand. It is work package X5.6 of the M5 plan; the cube version of the same idea is `cube-pyramid-3d` (X-MB5).

![The model canvas|900](@fig:diagram)

```
Tetra (RigidBody3D) <-- Pose (PoseIntegrator3D, floating base)
  |  p                          | g
  +-- Mount_k -- C_k (ContactPoint) <-- Ground (ContactSurface)        (vertices k = 1..4)
  '-- WMount_k -- WJoint_k -- WLink_k -- Wheel_k (RigidBody3D)           (faces k = 1..4)
                     ^ drive
             Shaft_k -- Drv_k (CurrentControlledDrive) <-- Alloc.i_k
Seq (TipSequencer, 1 ms) --T--> Alloc (Allocator, 1 ms) --> Drv_k;  Drv_k.tau_m --> Tap (WheelTap)
Sense (TetraSense), EnBody/EnW_k (BodyEnergy), Ledger: sensors
```

The blocks: [Tetra](block:Tetra), [Pose](block:Pose), [Ground](block:Ground), the vertex contacts [C1](block:C1) to `C4`, the firmware [Seq](block:Seq) and [Alloc](block:Alloc), the sensors [Sense](block:Sense), [Tap](block:Tap), [Ledger](block:Ledger), and per wheel a mount, joint, [Wheel1](block:Wheel1), drive [Drv1](block:Drv1) and shaft.

## Run it

Press **Run**: 3.8 s with 761 output points and the contact system; about 40 s of solving on a warm worker. Plot [Sense/ang_vert](signal:Sense/ang_vert) (the angle between the world vertical and the vertex balance direction: it ends below 0.02 deg), [Seq/ph](signal:Seq/ph), the vertex loads [C3/f_n](signal:C3/f_n) and the wheel speeds [WJoint1/qdout](signal:WJoint1/qdout).

## 3D view

`scenes/tetra-3d.sdf` shows the ground plate, the tetrahedron (the GLB mesh `meshes/tetra.glb`, translucent, vertex 3 marked red and vertex 2 dark) and the four wheel discs on the face centroids. The body link is bound by its world pose (`Pose/qw .. Pose/pz`); each wheel joint `wheel_k` (axis z of the wheel frame, the face normal) is bound to the integrated wheel angle `WJoint<k>/q`. The three pictures show the start on the face, the edge balance and the vertex balance.

![Face: t = 0 s|420](@fig:face)

![Edge balance: t = 1.6 s|420](@fig:edge)

![Vertex balance: t = 3.4 s|420](@fig:vertex)

Continue with [the geometry](page:geometry), [the firmware](page:firmware) and [the results](page:results).
@@ page sequence-contact geometry overview | Geometry, wheels, contacts
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
@@ page sequence-contact firmware overview | Firmware
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
@@ page sequence-contact results overview | Results and checks
# Results and checks

![Attitude error, phase, vertex loads and wheel speeds over the 3.8 s run|900](@fig:run)

![Centre of mass height and motor terminal voltage|900](@fig:height)

## Measured (README, `run_checks.py --only tetra-3d`)

| quantity | value |
| --- | --- |
| face rest | each base vertex 4.578 N ($\sum f_n = 13.734$ N), apex 0, CoM height 0.050657 m |
| edge reached and held | phase 2 from 1.05 s; angle to the edge balance direction 0.70 deg at 1.2 s, 0.29 deg at 1.4 s, 0.077 deg from 1.7 s (tilt 0.9560 rad = 54.78 deg, target 54.74 deg); two loaded vertices, 6.867 N each, the other two at most 4e-18 N; CoM height 0.087898 m |
| vertex reached and held | phase 4 from 2.75 s; angle to the vertex balance direction 0.18 deg at 3.3 s, 0.067 deg at 3.5 s, 0.020 deg at 3.75 s (tilt 1.23113 rad, target 1.23096); one loaded vertex, 13.734 N; CoM height 0.152315 m |
| peak wheel speed | wheel 1: 314.5 rad/s (3003 rpm) at 2.56 s; wheels 2/3/4: 119.2 / 119.3 / 212.7 rad/s |
| peak motor torque | 1.473 N·m (wheel 1, 14.7 A) of the 1.6 N·m limit; wheels 2/3/4: 0.794 / 0.799 / 1.174 N·m; the allocator never saturates |
| peak terminal voltage | 32.6 V (motor 1), 12.7 / 12.9 / 22.3 V for motors 2/3/4, supply 48 V |
| null space | $\max\lvert n\cdot\tau - \lambda\rvert = 2.6\cdot10^{-16}$, `Tap/resid` 1.8e-15, realised body torque against the allocation 4e-16 N·m |
| quaternion norm | $\lvert q\rvert^2 - 1 \le 1.4\cdot10^{-14}$ |
| energy ledger | drift 0.95e-3 J over 3.8 s while the motors do 126 J of work |
| cost | 60 checks, 0 failed, 48.5 s in total (the run itself 36 s, 2508 signals) |

The apex has a contact too: it stays above 0.2 m and its load is at most 5e-18 N for the whole run (checked), but nothing is assumed.

## Checks (`expected.json`)

Phase by phase: attitude (tilt and angle to the balance direction), the loaded-vertex count and every vertex's normal force, the CoM height and horizontal position against the geometry, each phase reached ([Seq/ph](signal:Seq/ph)) and held (error bound over the hold window); wheel speeds below 340 rad/s, torques up to 1.6 N·m, terminal voltage below 48 V and their peaks; the null-space tap and the realised torque; quaternion norm; the energy ledger; `scene_bindings`; no W201, E101, E102, E103, E106, E007 or W206. `run_timeout` is 900 s.
