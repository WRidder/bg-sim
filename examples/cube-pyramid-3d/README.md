# cube-pyramid-3d — a four-wheel cube that tips from a face to an edge to a corner

A free cube (`a = 0.2 m`) with **four reaction wheels in a pyramid** lies on a ground plane.
A scripted torque profile spins the wheels so that the cube leaves its **face**, balances on an
**edge** (tilt 45 deg), and then on a **corner** (tilt atan √2 = 54.74 deg, the body diagonal
vertical). The ground is a compliant `ContactSurface`; every contact is a `ContactPoint`
(Hunt-Crossley normal force, regularised Coulomb friction), so the phases are *emergent*: which
vertices carry load follows from the contact forces, nothing is switched by hand. It is X-MB5
of plan 6, the cube/pyramid example of plan 3.3 and 9.

```
Cube (RigidBody3D) ◄── Pose (PoseIntegrator3D, floating base)
  │  p                           │ g
  ├── Mount_k ── C_k (ContactPoint)  ◄── Ground (ContactSurface)         (vertices k = 1..4, see below)
  └── WMount_k ── WJoint_k ── WLink_k ── Wheel_k (RigidBody3D)           (k = 1..4)
                      ▲ drive
              Shaft_k ── Drv_k (CurrentControlledDrive) ◄── Alloc.i_k
 Seq (TipSequencer, 1 ms) ──T──► Alloc (Allocator, 1 ms) ──► Drv_k;  Drv_k.tau_m ──► Tap (WheelTap)
 Sense (CubeSense), EnCube/EnW_k (BodyEnergy), Ledger: sensors
```

## The construction

* **Body.** `RigidBody3D` (`m = 0.4 kg`, `J = m a²/6` on all three axes) on a
  `PoseIntegrator3D` (D-MB6 floating base). The total mass with the wheels is
  `m_total = 0.4 + 4 · 0.25 = 1.4 kg` (weight 13.734 N).
* **Contacts.** Vertex `k` (`k − 1 = bx + 2 by + 4 bz`, coordinates `±a/2`) has a
  `FixedTransform3DNeutral` mount (contact on side `a`, body on side `b`, translation `−r`), a
  `LocalPose3D` composed with the body pose by `ComposePose3D`, and a `ContactPoint`
  (`k = 2e4 N/m` at `x_ref = 1 mm`, Hertz exponent 3/2, `c = 5 s/m`, `μ = 0.8`, `v_s = 1 mm/s`).
  Vertex 1 = (−,−,−) is the corner, vertices 1 and 2 are the edge `y = z = −a/2`, vertices 1–4
  are the bottom face.
* **Wheels** exactly as in `reaction-wheel-3d` (X-MB4): axis `a_k = (sin β cos φ_k, sin β sin φ_k,
  cos β)`, `β = atan √2`, `φ_k = 0, 90, 180, 270 deg`, so `A Aᵀ = diag(2 sin²β, 2 sin²β, 4 cos²β) = 4/3 I`
  for `A = [a_1 … a_4]`. Each wheel is a `RigidBody3D` (`0.25 kg`, `J = (1e-3, 1e-3, 2e-3)`) at
  0.06 m from the cube centre on a `Revolute3D` (`kr = 2e4`, `kt = 1e6`), driven by a
  `CurrentControlledDrive` (`k_t = 0.1 N m/A`, rotor `J_m = 1e-8`) through an `ElasticShaft`
  (`k = 100`, `d = 2e-3`). Construction rules from X-MB4 hold: each transformer's `a` side faces the
  joint and its `b` side the body (`transform.b → body.p`), and every body mount has an identity
  `WLink` for the frame check (E007).
* **Firmware (D28).** `TipSequencer` (1 ms) produces the body torque `T` from the cube pose (it
  only uses the world vertical seen from the body, `u = Rᵀ e_z`) and the twist;
  `Allocator` (1 ms) turns `T` into motor currents with the minimum-norm allocation plus a
  free null-space term, `τ = −A⁺ T + λ n`, `n = (1, −1, 1, −1)/2`, `λ = 0.005 N m`, and scales
  the *body-torque request* (never the null-space term) so no wheel exceeds
  **1.2 N m** (`Alloc/sat` is the scale factor).
* **Sequencer law.** Gravity compensation about the current pivot lever `r` (face: none; edge:
  `r = (0, a/2, a/2)`; corner: `r = (a/2, a/2, a/2)`), `T_ff = m g (r × u)`, which makes the cube
  a free rotor about the contact feature, plus a saturated attitude feedback
  `Kp (u_ref × u) + Kd (w_ref − w⊥) − Ky (w·u) u` and a gyroscopic decoupling term `w × h_wheels`
  from the measured wheel speeds. The reference `u_ref` moves by a minimum-jerk blend from
  `(0,0,1)` to `(0, 1, 1)/√2` (edge) and on to `(1,1,1)/√3` (corner). Phase times: face until
  0.5 s, edge move 0.5–1.15 s, edge hold to 2.3 s, corner move 2.3–3.15 s, corner hold to 4.5 s.
  `Seq/ph` records the phase (0 face, 1 edge move, 2 edge hold, 3 corner move, 4 corner hold).
* **Sensors.** `CubeSense` (tilt, the loaded-vertex count, the sum of the normal forces),
  `WheelTap` (the measured motor torques, null-space tap as in X-MB4), `BodyEnergy` (cube and
  each wheel) and `Ledger` (dissipated contact energy, motor input work, shaft/rotor energy).

## The models

| model | what | span | tolerances |
| --- | --- | --- | --- |
| `sequence-contact` | face → edge → corner on the bottom-four vertex contacts | 4.5 s | reltol 1e-6, abstol 1e-8 (1e-7 / 1e-9 gives the same numbers to 3e-4 rad) |
| `edge-contact` | edge phase from 0.70 rad tilt, same contacts, same wheels and firmware | 1.2 s | 1e-9 / 1e-11 |
| `edge-switched` | the same edge phase on a `SwitchedPivot3D` (edge mode, J-MB14) instead of the contacts | 1.2 s | 1e-9 / 1e-11 |

`edge-switched`: `GroundSpatial → SwitchedPivot3D (kt = 1e6, bt = 2e3, kr = 1e5, br = 1e2, mode 2
from the start, guard held at 0) → Link (FixedTransform3DNeutral to the CoM) → Cube
(RigidBody3D)`. The pivot frame has its z axis along the edge, so the cube frame is the cyclic
permutation of the pivot frame; `TwistToCube` maps the twist back so the *same* firmware runs on
both models. It uses `RigidBody3D` behind a link rather than `ImpactBody3D`: the wheels need
several bonds on the body port, and `ImpactBody3D` exposes one; no impact is needed because the
guard never fires.

## Deviations from the work-package text

* **Contacts on the four bottom vertices, not all eight.** The plan row says all vertices. The
  eight-contact version of `sequence-contact` was built and run first (3068 signals, 25 states,
  one run 452 to 626 s wall; a bare cube with eight contacts alone takes 120 to 150 s to build and run) and was too slow
  for the gate. In that run the top four vertices (5–8) stayed at least **0.114 m** above the
  plane in every phase (smallest clearance 0.114 m at 3.21 s) and their normal force was exactly
  0, so dropping them does not change the physics. Their load inputs of `CubeSense` are tied to 0.
* The cube is 0.4 kg (`J = m a²/6`) plus 1.0 kg of wheels placed at 0.06 m from the centre; the total mass is used for the weight checks and the centre of mass stays at the cube centre.
* Wheel speeds reach 308 rad/s (2940 rpm) in the corner move: the pyramid has to absorb the angular momentum of the tip-up.

## Measured (this example, direct run of the pipeline)

| quantity | value |
| --- | --- |
| initial rest on the face | `Σ f_n / (m g)` − 1 = **1.3e-5** at 0.25 s and **5e-8** at 0.49 s; each bottom vertex 3.4335 N, top four 0 |
| edge phase reached | tilt 0.8271 rad at 1.17 s (first reaching phase 2), settles to **0.7857 rad** at 2.2 s (45.02 deg; 45° = 0.7854); exactly two loaded vertices (`nload = 1.99958`), `f_n = 6.867 N` each, the other six `≤ 1e-17 N` |
| corner phase reached | tilt **0.95535 rad** at 4.2 s (54.74 deg; atan √2 = 0.95532), within 0.0003 rad of it from 3.15 s on, one loaded vertex (`nload = 0.99995`), `f_n = 13.734 N`; centre-of-mass height 0.17243 m (= √3/2·a − 0.76 mm penetration) |
| wheel speeds | peak **307.9 rad/s** (wheel 4, at 2.99 s; wheels 1/2/3: 205.9 / 101.4 / 175.0), limit stated 320 rad/s |
| motor torque | at the 1.2 N m limit during the two tip-up moves; allocator scale factor down to 0.738 |
| null space `[1,−1,1,−1]` | `max |n·τ − λ| = 2.2e-16`, `Tap/resid` 1.1e-15, realised body torque vs firmware allocation 2.2e-16 N m |
| energy ledger | `E_mech + ΣE_c + E_shaft + E_diss − W_motor` drifts by **1.0e-3 J** over 4.5 s on 1.4 J (7e-4); the wheel joints' compliance holds the rest |
| edge: contact vs switched pivot (1.2 s) | max `|Δ tilt|` **1.2e-5 rad**, max `|Δ z_cm|` 1.6e-5 m (pivot weight deflection `m g / kt = 1.4e-5 m`), max `|Δ y_cm|` 5.4e-6 m, wheel 1 speed 4.6e-3 rad/s of 11 rad/s |
| states | 25 for `sequence-contact` and `edge-contact` (cube momentum 6, pose 7, per wheel momentum 6 + joint and shaft states, contact states, energy integrals), 27 for `edge-switched` (direct pipeline stats) |
| run cost | `run_checks.py --only cube-pyramid-3d`: **82 checks, 0 failed, 765.6 s** (the three runs plus the backend start; `sequence-contact` 2512 signals, 9001 rows; roughly 8 min / 3 min / 2 min, on a machine shared with other jobs). Above the 3 min target: the cost is the MTK build of contacts plus four driven wheels (the eight-contact version was slower), not the integration |

The contact model and the switched pivot give the same edge balance to about 1e-5 (rad and
m). That is the size of the stated compliance (`m g/kt = 1.4e-5 m`), and it is much smaller
than the contact penetration of 0.5 mm, so the two models are the same rocking edge. Tolerances in
`compare` are 4x the measured maxima.

## Checks (`expected.json`)

`sequence-contact`: initial attitude; rest on the face (sum of the normal forces = weight at
0.25 s and 0.49 s, each bottom vertex a quarter, top vertices ≤ 1e-9); edge hold (tilt 45 deg to
2e-3, two loaded vertices, each carrying half the weight, the other six ≤ 1e-6 N); corner hold
(tilt atan √2 to 1e-3, one loaded vertex carrying the weight, the other seven ≤ 1e-6 N, height);
null-space tap (`nsp − λ`, `resid`, realised body torque vs allocation); wheel speed and motor
torque limits; the energy ledger (`tol 1.5e-3` on scale 1.4); no diagnostics (W201, E101, E102,
E103, E106, E007, W206).
`edge-contact` / `edge-switched`: start tilt, edge balance (tilt, loads), the same tap and limit
checks, no diagnostics. `compare`: tilt, centre-of-mass height and lateral position, and wheel
speed between the two edge models.

`expected.json` carries a per-model `run_timeout` (900 / 600 / 600 s). It is a small additive
key of `examples/run_checks.py`: building the MTK system for contacts plus four driven wheels
takes minutes, more than the default 180 s.

## Run it

```
uv run bgsim
```

then **Open** → **Samples** → **cube-pyramid-3d** and press **Run**. The acceptance checks:

```
uv run examples/run_checks.py --only cube-pyramid-3d
```
