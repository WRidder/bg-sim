@@ figures sequence-contact
{
  "diagram": {"kind": "diagram", "model": "sequence-contact"},
  "face": {"kind": "scene", "model": "sequence-contact", "t": 0.2},
  "edge": {"kind": "scene", "model": "sequence-contact", "t": 1.8},
  "corner": {"kind": "scene", "model": "sequence-contact", "t": 4.0},
  "run": {
    "kind": "plot", "model": "sequence-contact", "xlim": [0, 4.5],
    "rows": [
      {"ylabel": "cube tilt [deg]", "series": [{"signal": "Sense/tilt", "label": "Sense/tilt", "scale": 57.29577951308232}], "hlines": [{"y": 45, "label": "edge 45 deg"}, {"y": 54.7356, "label": "corner 54.74 deg"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "phase Seq/ph [-]", "series": [{"signal": "Seq/ph", "label": "Seq/ph", "color": "#444444"}]},
      {"ylabel": "vertex normal force [N]", "series": [{"signal": "C1/f_n", "label": "C1"}, {"signal": "C2/f_n", "label": "C2"}, {"signal": "C3/f_n", "label": "C3"}, {"signal": "C4/f_n", "label": "C4"}], "legend": true},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "WJoint1/qdout", "label": "wheel 1"}, {"signal": "WJoint2/qdout", "label": "wheel 2"}, {"signal": "WJoint3/qdout", "label": "wheel 3"}, {"signal": "WJoint4/qdout", "label": "wheel 4"}], "legend": true, "legend_loc": "upper left"}
    ]
  }
}
@@ page sequence-contact overview - | Overview
# Four-wheel cube: face, edge, corner

A free cube ($a = 0.2$ m) with **four reaction wheels in a pyramid** lies on a ground plane. A scripted torque profile spins the wheels so that the cube leaves its **face**, balances on an **edge** (tilt 45 deg) and then on a **corner** (tilt $\arctan\sqrt2 = 54.74$ deg, the body diagonal vertical). The ground is a compliant `ContactSurface`; every contact is a `ContactPoint` (Hunt-Crossley normal force, regularised Coulomb friction), so the phases are *emergent*: which vertices carry load follows from the contact forces, nothing is switched by hand. It is X-MB5 of plan 6, the cube/pyramid example of plans 3.3 and 9. The model `edge-contact` repeats the edge phase alone and `edge-switched` replaces the contacts by a `SwitchedPivot3D`; their pages compare the two.

![The model canvas|900](@fig:diagram)

```
Cube (RigidBody3D) <-- Pose (PoseIntegrator3D, floating base)
  |  p                          | g
  +-- Mount_k -- C_k (ContactPoint) <-- Ground (ContactSurface)         (vertices k = 1..4)
  '-- WMount_k -- WJoint_k -- WLink_k -- Wheel_k (RigidBody3D)           (k = 1..4)
                      ^ drive
              Shaft_k -- Drv_k (CurrentControlledDrive) <-- Alloc.i_k
 Seq (TipSequencer, 1 ms) --T--> Alloc (Allocator, 1 ms) --> Drv_k;  Drv_k.tau_m --> Tap (WheelTap)
 Sense (CubeSense), EnCube/EnW_k (BodyEnergy), Ledger: sensors
```

## Run it

Press **Run**. The model compiles to a 25-state system with 2512 recorded signals; the README measured roughly 8 minutes of wall time on a loaded machine (the MTK build of the contacts plus four driven wheels dominates). Plot [Sense/tilt](signal:Sense/tilt) and [Seq/ph](signal:Seq/ph), the vertex loads [C1/f_n](signal:C1/f_n) to [C4/f_n](signal:C4/f_n) and the wheel speeds [WJoint1/qdout](signal:WJoint1/qdout).

## 3D view

`scenes/cube-pyramid-3d.sdf` shows the cube (translucent) on the ground plane with its four pyramid wheels. The cube and each wheel are bound by their world pose (quaternion first).

![Face: t = 0.2 s|420](@fig:face)

![Edge balance: t = 1.8 s|420](@fig:edge)

![Corner balance: t = 4.0 s|420](@fig:corner)

Continue with [the construction](page:construction), [the firmware](page:firmware) and [the results](page:results).
@@ page sequence-contact construction overview | Construction
# Construction

- **Body.** [Cube](block:Cube) (`RigidBody3D`, $m = 0.4$ kg, $J = m a^2/6 = 2.667\cdot10^{-3}$ kg·m² on all three axes) on a [Pose](block:Pose) (`PoseIntegrator3D`, D-MB6 floating base). The total mass with the wheels is $m_{total} = 0.4 + 4\cdot0.25 = 1.4$ kg (weight 13.734 N).
- **Contacts.** Vertex $k$ ($k - 1 = b_x + 2 b_y + 4 b_z$, coordinates $\pm a/2$) has a `FixedTransform3DNeutral` mount ([Mount1](block:Mount1)), a `LocalPose3D`, composed with the body pose by `ComposePose3D`, and a `ContactPoint` ([C1](block:C1)): $k = 2\cdot10^4$ N/m at $x_{ref} = 1$ mm (Hertz exponent 3/2), $c = 5$ s/m, $\mu = 0.8$, $v_s = 1$ mm/s. Vertex 1 $= (-,-,-)$ is the corner, vertices 1 and 2 are the edge $y = z = -a/2$, vertices 1 to 4 are the bottom face. [Ground](block:Ground) is the `ContactSurface`.
- **Wheels** exactly as in `reaction-wheel-3d` (X-MB4): axis $a_k = (\sin\beta\cos\varphi_k,\ \sin\beta\sin\varphi_k,\ \cos\beta)$, $\beta = \arctan\sqrt2$, $\varphi_k = 0, 90, 180, 270$ deg, so that $A A^T = \mathrm{diag}(2\sin^2\beta,\ 2\sin^2\beta,\ 4\cos^2\beta) = \tfrac43 I$. Each wheel is a `RigidBody3D` ($0.25$ kg, $J = (10^{-3}, 10^{-3}, 2\cdot10^{-3})$ kg·m²) at 0.06 m from the cube centre on a `Revolute3D` ($k_r = 2\cdot10^4$, $k_t = 10^6$), driven by a `CurrentControlledDrive` ($k_t = 0.1$ N·m/A, rotor $J_m = 10^{-8}$) through an `ElasticShaft` ($k = 100$, $d = 2\cdot10^{-3}$). Each transformer's `a` side faces the joint and its `b` side the body, and every body mount has an identity `WLink` for the frame check (E007).
- **Sensors.** [Sense](block:Sense) (`CubeSense`: tilt, the loaded-vertex count, the sum of the normal forces), [Tap](block:Tap) (`WheelTap`), `BodyEnergy` ([EnCube](block:EnCube) and each wheel) and [Ledger](block:Ledger) (dissipated contact energy, motor input work, shaft and rotor energy).

## Contacts on the four bottom vertices

The work-package row says all eight vertices. The eight-contact version was built and run first (3068 signals, 25 states, 452 to 626 s per run; a bare cube with eight contacts alone takes 120 to 150 s to build and run) and was too slow for the gate. In that run the top four vertices (5 to 8) stayed at least 0.114 m above the plane in every phase and their normal force was exactly 0, so dropping them does not change the physics. The model has the contacts `C1` to `C4`; the load inputs of `CubeSense` for the top vertices are tied to 0.

## Models

| model | what | span | tolerances |
| --- | --- | --- | --- |
| `sequence-contact` | face, edge, corner on the bottom-four vertex contacts | 4.5 s, 901 points | `reltol` 1e-6, `abstol` 1e-8 |
| `edge-contact` | edge phase from 0.70 rad tilt, same contacts, wheels and firmware | 1.2 s, 241 points | 1e-9 / 1e-11 |
| `edge-switched` | the same edge phase on a `SwitchedPivot3D` (edge mode, J-MB14) instead of the contacts | 1.2 s, 241 points | 1e-9 / 1e-11 |
@@ page sequence-contact firmware overview | Firmware
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
@@ page sequence-contact results overview | Results and checks
# Results and checks

![Tilt, phase, vertex loads and wheel speeds|900](@fig:run)

## Measured (README, direct run of the pipeline)

| quantity | value |
| --- | --- |
| rest on the face | $\sum f_n/(m g) - 1$ = 1.3e-5 at 0.25 s and 5e-8 at 0.49 s; each bottom vertex 3.4335 N, top four 0 |
| edge phase | tilt 0.8271 rad at 1.17 s, settles to 0.7857 rad at 2.2 s (45.02 deg); exactly two loaded vertices (`nload` = 1.99958), $f_n$ = 6.867 N each, the other six at most 1e-17 N |
| corner phase | tilt 0.95535 rad at 4.2 s (54.74 deg), within 0.0003 rad of $\arctan\sqrt2$ from 3.15 s on; one loaded vertex, $f_n$ = 13.734 N; CoM height 0.17243 m |
| wheel speeds | peak 307.9 rad/s (wheel 4 at 2.99 s; wheels 1/2/3: 205.9 / 101.4 / 175.0) |
| motor torque | at the 1.2 N·m limit during the two tip-up moves; allocator scale factor down to 0.738 |
| null space | $\max\lvert n\cdot\tau - \lambda\rvert = 2.2\cdot10^{-16}$, `Tap/resid` 1.1e-15 |
| energy ledger | drift 1.0e-3 J over 4.5 s on 1.4 J (7e-4) |
| states | 25 |
| cost | `run_checks.py --only cube-pyramid-3d`: 82 checks, 0 failed, 765.6 s for all three runs |

Wheel speeds reach 308 rad/s (2940 rpm) in the corner move: the pyramid has to absorb the angular momentum of the tip-up.

## Checks (`expected.json`)

Initial attitude; rest on the face (the sum of the normal forces equals the weight at 0.25 s and 0.49 s, each bottom vertex a quarter, top vertices at most 1e-9); edge hold (tilt 45 deg to 2e-3, two loaded vertices carrying half the weight each, the other at most 1e-6 N); corner hold (tilt $\arctan\sqrt2$ to 1e-3, one loaded vertex carrying the weight); null-space tap; wheel speed and motor torque limits; the energy ledger (`tol` 1.5e-3 on the scale 1.4); no W201, E101, E102, E103, E106, E007 or W206. The expected file gives a per-model `run_timeout` of 900 / 600 / 600 s because building the MTK system takes minutes.
@@ figures edge-contact
{
  "diagram": {"kind": "diagram", "model": "edge-contact"},
  "run": {
    "kind": "plot", "model": "edge-contact", "xlim": [0, 1.2],
    "rows": [
      {"ylabel": "cube tilt [deg]", "series": [{"signal": "Sense/tilt", "label": "Sense/tilt", "scale": 57.29577951308232}], "hlines": [{"y": 45, "label": "edge balance 45 deg"}], "legend": true},
      {"ylabel": "vertex normal force [N]", "series": [{"signal": "C1/f_n", "label": "C1"}, {"signal": "C2/f_n", "label": "C2"}, {"signal": "C3/f_n", "label": "C3"}, {"signal": "C4/f_n", "label": "C4"}], "legend": true}
    ]
  }
}
@@ page edge-contact overview - | Overview
# Edge phase on contact points

The edge phase of `sequence-contact` alone: the cube starts at 0.70 rad tilt on the edge $y = z = -a/2$ (vertices 1 and 2), the same four-vertex contacts [C1](block:C1) to `C4`, the same wheels and the same firmware ([Seq](block:Seq), [Alloc](block:Alloc)); the run lasts 1.2 s with `reltol` 1e-9 and `abstol` 1e-11 (241 points). The sequencer is set to start in the edge phase.

![The model canvas|900](@fig:diagram)

![Tilt and vertex loads of the edge phase|900](@fig:run)

The model is the contact-based partner of `edge-switched`: the two models give the same edge balance to about 1e-5 (see that model's page for the numbers). The `Sense/tilt` of this run is the quantity compared. Checks: start tilt, edge balance (tilt and loads), the same tap and limit checks, no diagnostics; 25 states.
@@ figures edge-switched
{
  "diagram": {"kind": "diagram", "model": "edge-switched"},
  "run": {
    "kind": "plot", "model": "edge-switched", "xlim": [0, 1.2],
    "rows": [
      {"ylabel": "cube tilt [deg]", "series": [{"signal": "Sense/tilt", "label": "Sense/tilt", "scale": 57.29577951308232}], "hlines": [{"y": 45, "label": "edge balance 45 deg"}], "legend": true},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "WJoint1/qdout", "label": "wheel 1"}, {"signal": "WJoint2/qdout", "label": "wheel 2"}, {"signal": "WJoint3/qdout", "label": "wheel 3"}, {"signal": "WJoint4/qdout", "label": "wheel 4"}], "legend": true, "legend_loc": "upper left"}
    ]
  }
}
@@ page edge-switched overview - | Overview
# Edge phase on a switched pivot

The same edge phase as `edge-contact`, but the contacts are replaced by a **`SwitchedPivot3D`** ([Joint](block:Joint)) in edge mode (J-MB14): [World](block:World) `->` `Joint` ($k_t = 10^6$ N/m, $b_t = 2000$, $k_r = 10^5$, $b_r = 100$; mode 2 from the start through [NewMode](block:NewMode), guard [Guard](block:Guard) held at 0) `->` [Link](block:Link) (`FixedTransform3DNeutral` to the centre of mass, $x = y = 0.1$ m) `->` [Cube](block:Cube) (`RigidBody3D`). The pivot frame has its $z$ axis along the edge, so the cube frame is the cyclic permutation of the pivot frame; `TwistToCube` maps the twist back so that the *same* firmware ([Seq](block:Seq), [Alloc](block:Alloc)) runs on both models. The sequencer's `t1` = -10 s and `t2` = 100 s keep it in the edge phase.

It uses `RigidBody3D` behind a link rather than `ImpactBody3D`: the wheels need several bonds on the body port and `ImpactBody3D` exposes one; no impact is needed because the guard never fires. The run lasts 1.2 s (`reltol` 1e-9, `abstol` 1e-11, 241 points); 27 states.

![The model canvas|900](@fig:diagram)

![Tilt and wheel speeds on the switched pivot|900](@fig:run)

## Comparison with the contact model

| quantity (1.2 s) | difference |
| --- | --- |
| max $\lvert\Delta\ \mathrm{tilt}\rvert$ | 1.2e-5 rad |
| max $\lvert\Delta z_{cm}\rvert$ | 1.6e-5 m (the pivot weight deflection $m g/k_t = 1.4\cdot10^{-5}$ m) |
| max $\lvert\Delta y_{cm}\rvert$ | 5.4e-6 m |
| wheel 1 speed | 4.6e-3 rad/s of 11 rad/s |

That is the size of the stated compliance and much smaller than the contact penetration of 0.5 mm: the two models are the same rocking edge. The tolerances of the `compare` entries are 4x the measured maxima (tilt, centre-of-mass height and lateral position, wheel speed).
