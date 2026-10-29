# tetra-3d — a tetrahedron with a reaction wheel on every face tips from a face to an edge to a vertex

A free **regular tetrahedron** (edge `L = 0.25 m`) lies on its base face on a ground plane. A
**reaction wheel is tied to each of its four faces**: the spin axis is the outward normal of the
face and the wheel sits inside the body, 35 mm from the centre of mass towards the face centroid.
A scripted torque profile spins the wheels so that the body leaves its **face**, balances on an
**edge** (two contacts) and then on a single **vertex** (one contact). The ground is a compliant
`ContactSurface` and every vertex is a `ContactPoint` (Hunt-Crossley normal force, regularised
Coulomb friction), so the phases are *emergent*: which vertices carry load follows from the contact
forces, nothing is switched by hand. It is work package X5.6 of the M5 plan; the cube version of
the same idea is `examples/cube-pyramid-3d` (X-MB5), which stays unchanged.

```
Tetra (RigidBody3D) ◄── Pose (PoseIntegrator3D, floating base)
  │  p                           │ g
  ├── Mount_k ── C_k (ContactPoint)  ◄── Ground (ContactSurface)        (vertices k = 1..4)
  └── WMount_k ── WJoint_k ── WLink_k ── Wheel_k (RigidBody3D)           (faces k = 1..4)
                      ▲ drive
              Shaft_k ── Drv_k (CurrentControlledDrive) ◄── Alloc.i_k
 Seq (TipSequencer, 1 ms) ──T──► Alloc (Allocator, 1 ms) ──► Drv_k;  Drv_k.tau_m ──► Tap (WheelTap)
 Sense (TetraSense), EnBody/EnW_k (BodyEnergy), Ledger (energy and motor voltage): sensors
```

## Geometry

Body frame: origin = centre of mass = centre of the circumscribed sphere, z up when the body rests
on its base face. With `R = L √6/4 = 0.15309 m` (circumradius), `r = R/3 = 0.05103 m` (inradius, the
face-centroid distance) and `ρ = L/√3 = 0.14434 m` (circumradius of the base triangle):

| vertex | body frame |
| --- | --- |
| `v1` | `(0, ρ, −r)` |
| `v2` | `(−L/2, −ρ/2, −r)` |
| `v3` | `(+L/2, −ρ/2, −r)` |
| `v4` (apex) | `(0, 0, R)` |

Vertices 1–3 form the base face; `ContactPoint` `C_k` sits on vertex `k` (`Mount_k` / `Local_k` hold
the vertex position, translation `∓v_k`).

**Wheels.** Wheel `j = 1..3` sits on the side face opposite to base vertex `v_j`, its axis is
`a_j = −v_j/R`, and wheel 4 sits on the base face with `a_4 = (0, 0, −1)`:

```
a1 = (0, −κ, 1/3)   a2 = (c, κ/2, 1/3)   a3 = (−c, κ/2, 1/3)   a4 = (0, 0, −1)       κ = 2√2/3, c = √6/3
```

The four normals sum to zero, so with `A = [a1 a2 a3 a4]` (3 × 4) `A Aᵀ = 4/3 I` (any three wheels are
independent), `A⁺ = ¾ Aᵀ`, and the null direction is `A n = 0` for `n = (1, 1, 1, 1)/2`: the fourth wheel
is the redundant one the allocator uses for its null-space term. Each wheel frame has its z axis along
`a_k` (`WMount_k` / `WLocal_k` carry the quaternion and the offset `d a_k`, `d = 35 mm`).

**Mass and inertia** (same class as the cube of cube-pyramid-3d):

| part | mass | inertia about its own centre |
| --- | --- | --- |
| tetrahedron | 0.4 kg | solid regular tetrahedron, isotropic: `J = m L²/20 = 1.25e-3 kg m²` |
| each wheel (4) | 0.25 kg | `J = (1e-3, 1e-3, 2e-3)` kg m² (axis z); rotor `J_m = 1e-8` behind an elastic shaft `k = 100`, `d = 2e-3` |
| total | **1.4 kg** (weight 13.734 N) | centre of mass at the body centre (the wheel offsets sum to zero); inertia without the wheel spin `4.73e-3 kg m²` on all axes |

The wheel inertia is the one of the cube example. A 0.25 kg wheel of `J = 2e-3 kg m²` would be 0.126 m
wide: it is the inertia of a rim-heavy flywheel, not of a disc that fits the 0.25 m body; the 3D scene
draws smaller discs (0.04 m radius). Motors: `CurrentControlledDrive` `k_t = 0.1 N m/A`, winding
resistance `R_m = 0.4 Ω`, so the terminal voltage is `R_m i + k_t ω` (`Ledger/v1..v4`) with a 48 V supply in mind.

**Contacts.** `k = 2e4 N/m` at `x_ref = 1 mm` (Hertz exponent 3/2), `c = 5 s/m`, `μ = 0.8`,
`v_s = 1 mm/s`. Resting on three vertices each sinks `0.374 mm` (the start height is
`r − 0.374 mm = 0.050657 m`).

## Target attitudes (`design/design.py`)

The firmware sees only `u = Rᵀ e_z`, the world vertical in the body frame (the yaw about the vertical is
free and damped).

| phase | contact set | `u` (body frame) | tilt `acos u_z` | CoM height above the ground |
| --- | --- | --- | --- | --- |
| face | `v1 v2 v3` | `(0, 0, 1)` | 0 | `r = 0.05103 m` |
| edge | `v2 v3` | `−(v2+v3)/\|v2+v3\| = (0, √(2/3), 1/√3)` | `acos(1/√3) =` **54.7356°** | `L/(2√2) = 0.08839 m` |
| vertex | `v3` | `−v3/R = (−√(2/3), √2/3, 1/3)` (= `a_3`) | `acos(1/3) =` **70.5288°** | `R = 0.15309 m` |

At the edge balance the CoM is above the edge midpoint `(0, −ρ/2)`; at the vertex balance it is above
`v3`, world position `(L/2, −ρ/2) = (0.125, −0.07217) m`. The angle between the two balance directions
is 54.74°. The wheel on the face opposite to `v3` has its axis vertical at the vertex balance, and the
two wheels 2 and 3 are symmetric about the vertical at the edge balance.

## Firmware (1 ms, D28)

* `TipSequencer` (law of the cube sequencer, adapted to the tetrahedron geometry). Gravity
  compensation about the current pivot lever `r = CoM − pivot` (edge: `(0, ρ/2, r)`, vertex:
  `(−L/2, ρ/2, r)`), `T_ff = m g (r × u)`, which makes the body a free rotor about the contact feature,
  plus a saturated attitude feedback `Kp (u_ref × u) + Kd (w_ref − w⊥) − Ky (w·u) u`
  (`Kp = 5`, `Kd = 1.2`, `Ky = 0.05`, limit `fb_max = 0.8 N m`) and a gyroscopic decoupling term `w × h`
  from the measured wheel speeds. The reference `u_ref` moves by a minimum-jerk blend. Phase times:
  face until 0.4 s; edge: compensation ramp 0.15 s, move 0.55–1.05 s, hold to 1.9 s; vertex: lever ramp
  1.9–2.05 s, move 2.05–2.75 s, hold to 3.8 s. `Seq/ph` records the phase (0 face, 1 edge move, 2 edge
  hold, 3 vertex move, 4 vertex hold).
* `Allocator`: minimum-norm allocation plus a free null-space term, `τ = −¾ Aᵀ T + λ n`,
  `λ = 0.005 N m`; it scales the *body-torque request* (never the null-space term) so no wheel exceeds
  **1.6 N m** (`Alloc/sat` is the scale factor, it stays 1 in this run). The edge-to-vertex lift needs about
  `m g L/2 = 1.7 N m` of body torque just to start (the weight acts at the distance `L/2` from the
  vertex), so the limit is larger than the 1.2 N m of the cube; the allocator capacity along the worst
  axis is `1.6 · Σ|a_k·d| ≥ 2.6 N m`.
* Sensors: `TetraSense` (attitude errors to the two balance directions, CoM position, loaded-vertex
  count, normal-force sum, quaternion norm), `WheelTap` (measured motor torques, null-space tap),
  `BodyEnergy` (body and each wheel), `Ledger` (dissipated contact energy, motor input work, shaft/rotor
  energy, motor terminal voltage).

`design/design.py` holds the geometry, prints the targets and runs a numpy replica of the closed loop
(hinge about the edge, then a ball joint at `v3`, ideal motors, the same firmware) that was used to pick
the edge length, the torque limit and the timing: with the 1.4 kg of the cube and `L = 0.30 m` the
vertex lift saturated 1.2 N m wheels and failed, `L = 0.25 m` with 1.6 N m works.
`design/build_model.py` writes `models/sequence-contact.bgmodel.json`, `scenes/tetra-3d.sdf` and
`meshes/tetra.glb` (the wiring and layout come from the cube example's `sequence-contact`).

## Model

| model | what | span | tolerances |
| --- | --- | --- | --- |
| `sequence-contact` | face → edge → vertex on the four vertex contacts | 3.8 s | reltol 1e-6, abstol 1e-8 |

All four vertices have a contact, including the apex: it stays above 0.2 m, its load is
`≤ 5e-18 N` for the whole run (checked), but nothing is assumed.

## Measured (direct pipeline, `run_checks.py --only tetra-3d`)

| quantity | value |
| --- | --- |
| face rest | each base vertex 4.578 N (`Σ f_n = 13.734 N`), apex 0, CoM height 0.050657 m, `nload = 2.9986` |
| edge reached and held | phase 2 from 1.05 s; angle to the edge balance direction 0.70° at 1.2 s, 0.29° at 1.4 s, 0.077° from 1.7 s (tilt 0.9560 rad = 54.78°, target 54.74°); two loaded vertices, 6.867 N each, the other two ≤ 4e-18 N; CoM height 0.087898 m (= 0.088388 − 0.49 mm penetration), above `(0, −0.07223)` |
| vertex reached and held | phase 4 from 2.75 s; angle to the vertex balance direction 0.18° at 3.3 s, 0.067° at 3.5 s, 0.020° at 3.75 s (tilt 1.23113 rad, target 1.23096); one loaded vertex, 13.734 N; CoM height 0.152315 m (= 0.153093 − 0.78 mm), above `(0.12506, −0.07217)` |
| peak wheel speed | wheel 1: **314.5 rad/s** (3003 rpm) at 2.56 s; wheels 2/3/4: 119.2 / 119.3 / 212.7 rad/s (design replica without contact compliance: 388 / 152 / 146 / 266) |
| peak motor torque | 1.473 N m (wheel 1, 14.7 A) of the 1.6 N m limit; wheels 2/3/4: 0.794 / 0.799 / 1.174 N m; the allocator never saturates |
| peak terminal voltage | **32.6 V** (motor 1), 12.7 / 12.9 / 22.3 V for motors 2/3/4, supply 48 V |
| null space `n = (1,1,1,1)/2` | `max \|n·τ − λ\| = 2.6e-16`, `Tap/resid` 1.8e-15, realised body torque vs firmware allocation 4e-16 N m |
| quaternion norm | `\|q\|² − 1` ≤ 1.4e-14 |
| energy ledger | `E_mech + ΣE_c + E_shaft + E_diss − W_motor` drifts by **0.95e-3 J** over 3.8 s while the motors do 126 J of work (1e-5 relative to the work, 0.14 % of the 0.70 J potential energy at the start) |
| run cost | `run_checks.py --only tetra-3d`: **60 checks, 0 failed, 48.5 s** in total (the run itself 36 s, 7601 rows, 2508 signals); a bare Julia worker start is the rest |

## Checks (`expected.json`)

Phase by phase: attitude (tilt, angle to the balance direction), the loaded-vertex count and every
vertex's normal force, the CoM height and horizontal position against the geometry, each phase
reached (`Seq/ph`) and held (error bound over the hold window); wheel speeds (< 340 rad/s) and
torques (≤ 1.6 N m), terminal voltage (< 48 V) and their peaks; the null-space tap and the realised
torque; quaternion norm; the energy ledger; no diagnostics (W201, E101, E102, E103, E106, E007, W206);
`scene_bindings`.

## Run it

```
uv run bgsim
```

then **Open** → **Samples** → **tetra-3d** and press **Run**. The acceptance checks:

```
uv run examples/run_checks.py --only tetra-3d
```

## 3D view

`scenes/tetra-3d.sdf` shows the ground plate, the tetrahedron (the GLB mesh `meshes/tetra.glb`,
translucent, vertex 3 marked red and vertex 2 dark) and the four wheel discs on the face centroids. The
body link `tetra` is bound by its world pose (`Pose/qw .. Pose/pz`, which carry the units the viewer wants:
quaternion dimensionless, position m). Each wheel link `wheel_k_link` hangs on a revolute joint `wheel_k`
(axis z of the wheel frame = the face normal) bound to the integrated wheel angle `WJoint<k>/q` (rad,
relative to the body; the sign matches the SDF joint, checked against the wheel pose of the model to 5e-10 rad),
so the tip-up from the face onto the edge and then onto the vertex and the wheel rotation are visible
directly. Importing the example copies `meshes/` with the rest of the project; the viewer fetches the mesh
from `GET /api/projects/{p}/meshes/tetra.glb`. `web/tests/e2e/tetra-3d.spec.ts` runs the model with the real
worker, plots `Sense/ang_vert`, opens the 3D View, checks the bindings and the wheel angles, and screenshots
the start, edge and vertex phases to `web/test-results/tetra-3d-3d*.png`.
