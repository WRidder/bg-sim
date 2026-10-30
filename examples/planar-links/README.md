# planar-links — three planar arms against a robotics toolbox (X5.9, F5.1)

The 1-, 2- and 3-link planar robot arms of `reference/planar_robot.py` (closed-form inverse
dynamics, checked in that script against Peter Corke's Robotics Toolbox, RTB), built three times,
side by side, from **proper planar (2D) bond-graph elements** and compared with the reference
through **CSV input sources** (`stdlib:sources/CsvSource`, the F5.1 feature).

```
Ground ─ Joint (Revolute2DCompliant) ─ Link (FixedJoint2D) ─ 1-junction ─ Joint ─ ... ─ Body
                │                                              │
             Drive 1-junction ── IdealGear (G) ── Motor 1-junction ──┬─ I (Jm)
                │                                                    └─ R (B)
   MSf (CSV speed) + TorqueSensor          (forward model: MSe with the CSV torque)
```

## Files

| path | what |
| --- | --- |
| `models/planar-links.bgmodel.json` | **inverse dynamics**: 1-, 2- and 3-link arm (offset 0 / 2.0 / 4.2 m in the scene); CSV joint speeds in, required torque and the errors `tau_bg - tau_rtb`, `tau_bg - tau_analytical` out |
| `models/planar-links-fwd.bgmodel.json` | **forward dynamics**: the CSV torque drives the joints (open loop, 1 s), the angle error against the CSV is the drift |
| `models/planar-links-payload.bgmodel.json` | 3-link arm with the 1 kg payload against the 4-link RTB robot |
| `data/arm1.csv ... arm3p.csv` | reference data at 1 kHz: `t, q, qd, qdd, tau_analytical, tau_rtb` per joint |
| `reference/planar_robot.py` | the user's script, **unchanged** |
| `reference/generate.py` | `uv run reference/generate.py` writes `data/*.csv` (analytical classes and RTB `rne_python`) |
| `reference/build_model.py`, `make_expected.py`, `plots.py` | generate the model documents and scenes, `expected.json`, and the docs plots |
| `scenes/planar-links.sdf`, `planar-links-payload.sdf` | the arms side by side with the six joint bindings |
| `library/TorqueError.jl`, `AngleError.jl` | the two small error blocks |
| `models/*.docs/` | the model docs (overview, structure, equations, conventions, CSV source, results) |

## The conventions

The CSV files and the model use the joint data **after** the script's `transform_joint_data`
(`q -> -q`, joint 1 offset `-pi/2`, `qd -> -qd`, `qdd -> -qdd`): the angle is counter-clockwise
from +x in the x-y plane, gravity acts along -y, joint 1 hangs straight down at `t = 0` and the
arm swings clockwise by 1 rad per joint. Torques are joint-side torques with the reflected
motor terms `G^2 Jm qdd + B G^2 qd`, so the bond graph has the motor inertia `Jm` and the viscous
friction `B` on the motor side of an ideal gear `G`. Link parameters are the script's; the COM
offset `r` is measured from the link end, so the COM sits at `a + r` from the joint.

Details of the script worth knowing:

- `get_total_mass` adds a list to a number; it is unused. The copy is unchanged.
- `transform_joint_data` on a 1-D array (the 1-link case) adds the offset to element 0 only. The
  generator writes the intended full offset (the 1-link torque is independent of it, asserted).
- The 1-link arm has no gravity (`gravity=0`; the RTB default points along z). The 2-link
  analytical class ignores the payload.

## Why `Revolute2DCompliant`

`Revolute2DRigid` on a 3-DOF planar body is index 3; on this arm it fails at t = 0 (unstable
initialisation, even with every joint speed prescribed). The joints are
`Revolute2DCompliant` with `kt = 1e8 N/m`, `bt = 1e5 N s/m`: the rotation is exact, the pivot
moves by about 1e-6 m, and every state stays integral. The cost is a ring of the first
millisecond in the torque.

## Method: the inverse dynamics

Each joint speed is prescribed by an `MSf` driven by the **cubic CSV speed** (a C2 not-a-knot
spline), so every inertia is in derivative causality (`W201`, expected) and ModelingToolkit
differentiates the interpolant through the registered derivatives of `csv_value`. No numerical
differentiation and no workaround were needed; the probes are in `julia/BGSim/NOTES.md`.

## Measured (real worker, `uv run examples/run_checks.py --only planar-links`: 64 checks)

| quantity | value |
| --- | --- |
| analytical vs RTB (the script's own comparison, 1 kHz) | 3.6e-15 / 2.8e-14 / 8.5e-14 N m (1/2/3-link), payload 5.7e-14 |
| torque error bond graph vs RTB, whole run (first ms) | 4.9e-4 (1-link); 1.3e-2, 3.6e-3 (2-link); 8.1e-2, 3.0e-2, 3.9e-4 (3-link); 0.13, 5.3e-2, 6.6e-3 (payload) N m |
| the same from t = 0.02 s | 7.8e-6; 1.8e-4, 5.0e-5; 9.5e-4, 3.5e-4, 4.5e-6; 1.4e-3, 6.0e-4, 7.4e-5 N m |
| peak torques | 8.6; 45, 17; 99, 43, 2.3; 131, 62, 12 N m |
| forward dynamics, max angle drift over 1 s | 1.7e-7; 1.3e-6, 1.9e-6; 3.4e-6, 4.8e-6, 7.0e-7 rad |
| scene tips vs model signals | 1e-15 m |
| compile / run (inverse, 3 arms) | about 3 s / 0.3 s; forward 5 s / 5 s |

## Run it

```
uv run bgsim
```

then **Open** → **Samples** → **planar-links**, select `A3_Csv` to see the file picker, the
preview and the 12 columns it outputs, press **Run**, plot `A3_TauErr1/e_rtb`, and open the
**3D View**. Regenerate the data and models:

```
uv run reference/generate.py        # needs Python < 3.13 for roboticstoolbox-python (inline metadata)
uv run reference/build_model.py
uv run reference/make_expected.py
```

Browser acceptance (real worker): `cd web; $env:BGSIM_E2E_REAL="1"; $env:BGSIM_E2E_PORT="8784"; npx playwright test tests/e2e/planar-links.spec.ts`.
