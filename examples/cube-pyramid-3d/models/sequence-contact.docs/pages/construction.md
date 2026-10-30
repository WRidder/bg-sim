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
